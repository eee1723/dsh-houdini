"""Headless regression for HTTP rejection, thread boundary and job truthfulness."""
from pathlib import Path
import http.client
import json
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import dsh_bridge as b

server = ThreadingHTTPServer(('127.0.0.1', 0), b._Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()


def post(path, value, headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
    connection.request('POST', path, json.dumps(value), headers=headers or {'Content-Type': 'application/json'})
    response = connection.getresponse()
    status, result = response.status, json.loads(response.read())
    connection.close()
    return status, result


try:
    from dsh_managed_runtime import executor_identity
    assert executor_identity()==b._EXECUTOR_ID
    import importlib
    import dsh_managed_runtime as runtime
    identity=runtime.executor_identity()
    importlib.reload(runtime)
    assert identity==runtime.executor_identity(), 'module reload must not replace process identity'
    wrong='0'*32 if identity!='0'*32 else '1'*32
    headers={'Content-Type':'application/json','X-DSH-Houdini-Executor':wrong}
    for path in ('/exec','/jobs','/jobs/not-ours/cancel','/jobs/not-ours/status',
                 '/context','/requests/prepare','/requests/status'):
        status,result=post(path,{'code':'raise RuntimeError("should never execute")'},headers)
        assert status==409 and 'executor_mismatch' in result['error'],(path,status,result)
    connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
    connection.request('GET','/media?path=never-read.png',headers={'X-DSH-Houdini-Executor':wrong})
    response=connection.getresponse()
    assert response.status==409 and 'executor_mismatch' in response.read().decode()
    connection.close()
    good={'Content-Type':'application/json','X-DSH-Houdini-Executor':identity}
    status,prepared=post('/requests/prepare',{'owner_session':'bound-client'},good)
    assert status==200 and prepared['executorId']==identity,(status,prepared)
    # The Qt callback yields after a slow item, rather than draining an entire
    # scene backlog in one tick. The next tick resumes FIFO, including failures.
    order = []
    work = [(threading.Event(), {}) for _ in range(3)]
    def first():
        order.append('first')
        return 'completed'
    def second():
        order.append('second')
        raise ValueError('fixture failure')
    for fn, (done, holder) in zip((first, second, lambda: order.append('cancelled')), work):
        b._work_queue.put((fn, done, holder))
    work[2][1]['cancelled'] = True
    with patch.object(b.time, 'monotonic', side_effect=[0, 0, 0.010]):
        b._pump()
    assert order == ['first'] and work[0][0].is_set() and not work[1][0].is_set()
    assert work[0][1]['result'] == 'completed'
    with patch.object(b.time, 'monotonic', return_value=1):
        b._pump()
    assert order == ['first', 'second'] and all(done.is_set() for done, _ in work)
    assert isinstance(work[1][1]['error'], ValueError)

    assert post('/exec', {'code': 'pass'}, {'Content-Type': 'text/plain'})[0] == 403
    assert post('/requests/prepare', {'owner_session':'fixture'}, {'Content-Type':'application/json','Origin':'https://untrusted.example'})[0] == 403
    assert post('/requests/prepare', {'owner_session':''})[0] == 400
    assert post('/requests/prepare', {'owner_session':'fixture','code':'must not execute'})[0] == 400
    status, prepared = post('/requests/prepare', {'owner_session':'fixture'})
    assert status == 200 and prepared['requestRef'].startswith(prepared['runtimeId']+'.')
    assert b._work_queue.empty(), 'preparing a receipt must not run or queue HOM'
    assert post('/exec', {'code': 'pass'}, {'Content-Type': 'application/json', 'Origin': 'https://untrusted.example'})[0] == 403
    assert post('/exec', [], None)[0] == 400
    assert post('/exec', {'code': 'pass'}, {'Content-Type': 'application/json', 'Content-Length': '-1'})[0] == 413
    assert post('/exec', {'code': 'pass', 'read_only': 'tru'})[0] == 400
    assert post('/exec', {'code': 'pass', 'expected_contract': {'version': 0, 'hash': 'stale'}})[0] == 409
    status, error = post('/exec', {'code': 'raise Exception("must not execute")'})
    assert status == 500 and 'pump is unavailable' in error['error'], error

    # Real HTTP -> queue -> owning-thread HOM -> JSON response, in this
    # disposable hython process (no live Houdini session is contacted).
    responses, finished = [], threading.Event()
    def inspect_via_http():
        try:
            responses.append(post('/exec', {
                'code': "__result__ = scene_info()['version']", 'read_only': True,
                'expected_contract': {'version': b._EXECUTION_CONTRACT_VERSION, 'hash': b._VERB_CATALOG_HASH},
            }))
        finally:
            finished.set()
    b._pump_active = True
    client = threading.Thread(target=inspect_via_http); client.start()
    deadline = time.monotonic() + 3
    while not finished.is_set() and time.monotonic() < deadline:
        b._pump()
        finished.wait(0.01)
    client.join(3)
    b._pump_active = False
    assert responses and responses[0][0] == 200 and responses[0][1]['result'] == b._HOU_VERSION, responses

    # Stopping a pump releases waiting clients and does not replay queued work
    # if a new pump later starts.
    cancelled, queued_done = [], threading.Event()
    holder = {}
    b._work_queue.put((lambda: cancelled.append('must not run'), queued_done, holder))
    b.stop()
    assert queued_done.is_set() and holder['cancelled'] and 'error' in holder
    b._pump()
    assert cancelled == []

    with b._jobs_lock:
        for name, state in [('q', 'queued'), ('r', 'running')]:
            b._jobs[name] = {'jobId': name, 'status': state, 'ok': False, 'stdout': '', 'stderr': ''}
    assert post('/jobs/q/cancel', {})[1]['status'] == 'cancelled'
    status, running = post('/jobs/r/cancel', {})
    assert running['status'] == 'running' and 'cannot be interrupted' in running['advisory'], running
    original = b._execute
    try:
        b._execute = lambda fn: {'ok': True, 'stdout': 'actual result', 'stderr': ''}
        b._run_job('r', 'pass')
        assert b._jobs['r']['status'] == 'done' and b._jobs['r']['stdout'] == 'actual result'
        def fail(fn):
            raise RuntimeError('pump failed')
        b._execute = fail
        b._jobs['r']['status'] = 'queued'
        b._run_job('r', 'pass')
        assert b._jobs['r']['status'] == 'failed' and 'pump failed' in b._jobs['r']['error']
    finally:
        b._execute = original

    with b._jobs_lock:
        for i in range(b._MAX_ACTIVE_JOBS):
            b._jobs[str(i)] = {'jobId': str(i), 'status': 'queued'}
    assert post('/jobs', {'code': 'pass'})[0] == 429

    # Reaching the trace cap cannot silently turn guarded execution into an
    # untraced path whose caught failures escape rollback.
    original_limit = b._VERB_ENTRY_LIMIT
    try:
        b._VERB_ENTRY_LIMIT = 1
        result = b.run_code("scene_info()\ntry:\n    scene_info()\nexcept Exception:\n    pass")
        assert result['ok'] is False and result['verbs'][-1]['ok'] is False, result
    finally:
        b._VERB_ENTRY_LIMIT = original_limit
finally:
    b._pump_active = False
    server.shutdown(); server.server_close(); thread.join(3)
    with b._jobs_lock:
        b._jobs.clear(); b._job_meta.clear()

print('bridge transport/thread/job regressions passed')
