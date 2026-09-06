"""Headless regression for HTTP rejection, thread boundary and job truthfulness."""
from pathlib import Path
import http.client
import json
import sys
import threading
import time
from http.server import ThreadingHTTPServer

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
    assert post('/exec', {'code': 'pass'}, {'Content-Type': 'text/plain'})[0] == 403
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
