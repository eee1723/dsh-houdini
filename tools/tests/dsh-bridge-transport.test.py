"""Headless regression for HTTP rejection, thread boundary and job truthfulness."""
from pathlib import Path
import copy
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


def contract():
    return {'version': b._EXECUTION_CONTRACT_VERSION, 'hash': b._VERB_CATALOG_HASH}


def prepare(owner='fixture'):
    status, prepared = post('/requests/prepare', {'owner_session': owner})
    assert status == 200 and prepared['requestRef'].startswith(prepared['runtimeId'] + '.'), prepared
    return prepared['requestRef']


def admission(code, owner='fixture', call='call-1', ticket=None, read_only=None, body_contract=None):
    """Complete HTTP admission envelope: Host identity + contract + one-time ticket."""
    body = {'code': code, 'owner_session': owner, 'owner_call': call,
            'request_ref': ticket if ticket is not None else prepare(owner),
            'expected_contract': contract() if body_contract is None else body_contract}
    if read_only is not None:
        body['read_only'] = read_only
    return body


def job_control(owner='fixture', call='call-1', body_contract=None):
    return {'owner_session': owner, 'owner_call': call,
            'expected_contract': contract() if body_contract is None else body_contract}


def post_rejecting(path, value, headers=None):
    """Executor-mismatch probes answer 409 without reading the request body, so
    Windows may abort the connection with an RST after the response. Retrying on
    a fresh connection is side-effect-free: nothing is routed for these probes."""
    for attempt in range(3):
        try:
            return post(path, value, headers)
        except (ConnectionError, OSError):
            if attempt == 2:
                raise


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
        status,result=post_rejecting(path,{'code':'raise RuntimeError("should never execute")'},headers)
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

    assert post_rejecting('/exec', {'code': 'pass'}, {'Content-Type': 'text/plain'})[0] == 403
    assert post_rejecting('/requests/prepare', {'owner_session':'fixture'}, {'Content-Type':'application/json','Origin':'https://untrusted.example'})[0] == 403
    assert post('/requests/prepare', {'owner_session':''})[0] == 400
    assert post('/requests/prepare', {'owner_session':'fixture','code':'must not execute'})[0] == 400
    status, prepared = post('/requests/prepare', {'owner_session':'fixture'})
    assert status == 200 and prepared['requestRef'].startswith(prepared['runtimeId']+'.')
    assert b._work_queue.empty(), 'preparing a receipt must not run or queue HOM'
    assert post_rejecting('/exec', {'code': 'pass'}, {'Content-Type': 'application/json', 'Origin': 'https://untrusted.example'})[0] == 403
    assert post('/exec', [], None)[0] == 400
    assert post_rejecting('/exec', {'code': 'pass'}, {'Content-Type': 'application/json', 'Content-Length': '-1'})[0] == 413
    # Complete admission is mandatory: identity, contract and one-time ticket.
    complete = admission('pass')
    for missing in ('owner_session', 'owner_call', 'request_ref', 'expected_contract'):
        broken = dict(complete); broken.pop(missing)
        assert post('/exec', broken)[0] == 400, missing
    assert post('/requests/prepare', {'owner_session': '   '})[0] == 400, 'whitespace-only session identity is rejected'
    assert post('/exec', {'code': 'pass', 'owner_session': '  ', 'owner_call': 'c', 'request_ref': 'x',
                          'expected_contract': contract()})[0] == 400, 'whitespace identity never reaches the registry'
    assert post('/exec', {'code': 'pass', 'owner_session': 'fixture', 'owner_call': 'c',
                          'expected_contract': contract()})[0] == 400, 'untracked HTTP execution is gone'
    assert post('/jobs', {'code': 'pass', 'owner_session': 'fixture', 'owner_call': 'c',
                          'expected_contract': contract()})[0] == 400, 'untracked job submission is gone'
    assert post('/exec', admission('pass', body_contract={'version': 1}))[0] == 400, 'malformed contract shape is 400'
    # Contract version typing: bools are int subclasses in Python and must read
    # as 400 (type error), not 409 (version mismatch); floats/strings/null too.
    for bad_version in (True, False, 53.0, '53', None):
        envelope = {'version': bad_version, 'hash': b._VERB_CATALOG_HASH}
        assert post('/exec', admission('pass', body_contract=envelope))[0] == 400, bad_version
        assert post('/jobs', admission('pass', body_contract=envelope))[0] == 400, bad_version
        assert post('/jobs/zz/status', job_control(body_contract=envelope))[0] == 400, bad_version
        assert post('/jobs/zz/cancel', job_control(body_contract=envelope))[0] == 400, bad_version
    assert post('/exec', admission('pass', body_contract={'version': b._EXECUTION_CONTRACT_VERSION - 1, 'hash': b._VERB_CATALOG_HASH}))[0] == 409
    assert b._work_queue.empty(), 'contract rejections must not queue anything'
    # Old-Host/new-Bridge mixed combination: the stale envelope must be refused
    # with ZERO scene modification - the would-be mutation never reaches exec.
    marker = hou.node('/obj').createNode('null', 'contract_probe_marker')
    stale = post('/exec', admission("g=tab_create('/obj','geo','never_created')", body_contract={'version': b._EXECUTION_CONTRACT_VERSION - 1, 'hash': b._VERB_CATALOG_HASH}))
    assert stale[0] == 409, stale
    assert hou.node('/obj/never_created') is None, 'a stale-contract exec must not touch the scene'
    marker.destroy()
    assert post('/exec', admission('pass', read_only='tru'))[0] == 400
    assert post('/exec', admission('pass', body_contract={'version': 0, 'hash': 'stale'}))[0] == 409
    status, error = post('/exec', admission('raise Exception("must not execute")'))
    assert status == 500 and 'pump is unavailable' in error['error'], error

    # Real HTTP -> queue -> owning-thread HOM -> JSON response, in this
    # disposable hython process (no live Houdini session is contacted).
    responses, finished = [], threading.Event()
    def inspect_via_http():
        try:
            responses.append(post('/exec', admission("__result__ = scene_info()['version']", read_only=True)))
        finally:
            finished.set()
    b._pump_active = True
    client = threading.Thread(target=inspect_via_http); client.start()
    deadline = time.monotonic() + 3
    while not finished.is_set() and time.monotonic() < deadline:
        b._pump()
        finished.wait(0.01)
    client.join(3)
    # A ticket rejected for contract mismatch was never consumed: the same
    # reference still admits exactly one normal submission, and a replay of the
    # same payload returns the original result without a second execution.
    reuse_done, reuse_responses = threading.Event(), []
    def reuse_flow():
        reusable = prepare()
        reuse_responses.append(post('/exec', admission('pass', ticket=reusable,
            body_contract={'version': b._EXECUTION_CONTRACT_VERSION - 1, 'hash': b._VERB_CATALOG_HASH})))
        reuse_responses.append(post('/exec', admission("__result__ = 'reused-ticket'", ticket=reusable, read_only=True)))
        reuse_responses.append(post('/exec', admission("__result__ = 'reused-ticket'", ticket=reusable, read_only=True)))
        reuse_done.set()
    flow = threading.Thread(target=reuse_flow); flow.start()
    deadline = time.monotonic() + 3
    while not reuse_done.is_set() and time.monotonic() < deadline:
        b._pump(); reuse_done.wait(0.01)
    flow.join(3)
    assert [entry[0] for entry in reuse_responses] == [409, 200, 200], reuse_responses
    assert reuse_responses[1][1]['result'] == 'reused-ticket', reuse_responses
    assert reuse_responses[2][1]['execution']['sequence'] == reuse_responses[1][1]['execution']['sequence'], \
        'same-payload replay returns the original execution without running code again'
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

    # --- Job control authorization matrix (F04) ------------------------------
    # Fixtures carry owner records, initialized comparable timestamps and
    # result material: every rejected control must leave all three untouched,
    # verified by full before/after snapshots, not just HTTP status codes.
    fixtures = {
        'qa': {'jobId': 'qa', 'status': 'queued', 'ok': False, 'stdout': '', 'stderr': '',
               'owner_session': 'alice', 'owner_call': 'c1'},
        'ra': {'jobId': 'ra', 'status': 'running', 'ok': False, 'stdout': 'secret-out', 'stderr': '',
               'owner_session': 'alice', 'owner_call': 'c1'},
        'da': {'jobId': 'da', 'status': 'done', 'ok': True, 'stdout': '', 'stderr': '',
               'result': {'media': 'Z:/hip/a.png'}, 'owner_session': 'alice', 'owner_call': 'c1'},
        'fa': {'jobId': 'fa', 'status': 'failed', 'ok': False, 'stdout': '', 'stderr': 'boom',
               'error': 'traceback-text', 'owner_session': 'alice', 'owner_call': 'c1'},
        'ca': {'jobId': 'ca', 'status': 'cancelled', 'ok': False, 'stdout': '', 'stderr': '',
               'owner_session': 'alice', 'owner_call': 'c1'},
        'qb': {'jobId': 'qb', 'status': 'queued', 'ok': False, 'stdout': '', 'stderr': '',
               'owner_session': 'bob', 'owner_call': 'c2'},
        'legacy': {'jobId': 'legacy', 'status': 'queued', 'ok': False, 'stdout': '', 'stderr': ''},
    }
    with b._jobs_lock:
        # Deep-copy the fixtures into the registry: the expected state must never
        # alias objects that participate in execution, or a rejection bug could
        # mutate the "expected" value together with the registry and pass.
        b._jobs.update(copy.deepcopy(fixtures))
        for name in fixtures:
            b._job_meta[name] = 1700.0 + len(name)   # initialized, distinct, comparable
    def jobs_state():
        """Independent deep snapshot of the whole registry, including nested
        result payloads; taken inside the lock, never rebuilt from fixtures."""
        with b._jobs_lock:
            return copy.deepcopy(b._jobs), copy.deepcopy(b._job_meta)
    state_before = jobs_state()   # frozen BEFORE the first rejection request
    # Envelope typing on job control: missing identity 400, bool version 400,
    # foreign contract value 409 - all before any job lookup or mutation.
    assert post('/jobs/qa/cancel', {})[0] == 400, 'job control without identity is rejected'
    assert post('/jobs/qa/cancel', job_control(body_contract={'version': True, 'hash': b._VERB_CATALOG_HASH}))[0] == 400, 'bool version is a type error'
    assert post('/jobs/qa/cancel', job_control(body_contract={'version': 0, 'hash': 'x'}))[0] == 409
    # Foreign session: every state is a uniform 404 with no payload/evidence
    # leak; queued, running, done, failed and cancelled all covered.
    for jid in ('qa', 'ra', 'da', 'fa', 'ca'):
        status, body = post('/jobs/' + jid + '/status', job_control(owner='stranger'))
        assert status == 404 and set(body) <= {'ok', 'error'}, (jid, status, body)
        assert 'result' not in body and not body.get('stdout') and not body.get('images'), body
    for jid in ('qa', 'ra'):
        status, body = post('/jobs/' + jid + '/cancel', job_control(owner='stranger'))
        assert status == 404 and set(body) <= {'ok', 'error'}, (jid, status, body)
    # Unknown, ownerless and other-session jobs share one error structure (same
    # shape, same text with the job id substituted); an ownerless job is never
    # claimed by whichever identity asks.
    uniform = []
    for jid in ('missing', 'legacy', 'qb'):
        s1, e1 = post('/jobs/' + jid + '/status', job_control())
        s2, e2 = post('/jobs/' + jid + '/cancel', job_control())
        assert s1 == s2 == 404 and e1 == e2, (jid, e1, e2)
        assert set(e1) == {'ok', 'error'}, e1
        uniform.append((s1, sorted(e1), e1['error'].replace(jid, '<id>')))
    assert len({repr(entry) for entry in uniform}) == 1, 'unknown/ownerless/foreign must share one error structure'
    after_state = jobs_state()
    assert after_state == state_before, \
        'rejected controls changed the registry; diff: ' + repr({
            'jobs': {k: (state_before[0].get(k), after_state[0].get(k))
                      for k in set(state_before[0]) | set(after_state[0])
                      if state_before[0].get(k) != after_state[0].get(k)},
            'meta': {k: (state_before[1].get(k), after_state[1].get(k))
                      for k in set(state_before[1]) | set(after_state[1])
                      if state_before[1].get(k) != after_state[1].get(k)}})
    assert all('advisory' not in job for job in after_state[0].values()), 'foreign cancel must not add advisory'
    # Snapshot self-check: the comparator must catch a mutated top-level owner
    # field AND a mutated nested result field, then the fixture is restored.
    with b._jobs_lock:
        b._jobs['da']['owner_call'] = 'tampered'
        b._jobs['da']['result']['media'] = 'Z:/hip/TAMPERED.png'
    assert jobs_state() != state_before, 'snapshot comparator must detect real mutations'
    with b._jobs_lock:
        b._jobs['da']['owner_call'] = 'c1'
        b._jobs['da']['result']['media'] = 'Z:/hip/a.png'
    assert jobs_state() == state_before, 'fixture must be restored after the self-check'
    assert b._work_queue.empty(), 'rejected job control must not queue anything'
    # Same session, new callId: later tool calls collect results and cancel.
    status, snapshot = post('/jobs/qa/status', job_control(owner='alice', call='later-call'))
    assert status == 200 and snapshot['status'] == 'queued', snapshot
    assert 'owner_session' not in snapshot and 'owner_call' not in snapshot, 'internal identity must not leak'
    status, cancelled = post('/jobs/qa/cancel', job_control(owner='alice', call='later-call'))
    assert status == 200 and cancelled['status'] == 'cancelled' and 'owner_session' not in cancelled
    status, running = post('/jobs/ra/cancel', job_control(owner='alice'))
    assert running['status'] == 'running' and 'cannot be interrupted' in running['advisory'], running
    # Long poll, deterministic: a fixture-level gate on the module sleep only
    # opens after the HTTP handler thread has provably reached the polling wait
    # (past authorization and the first terminal check). While the handler is
    # inside that wait, another thread must be able to take _jobs_lock and write
    # the terminal state; an implementation that holds the lock while waiting is
    # caught by the timed lock acquisition instead of a lucky schedule.
    with b._jobs_lock:
        b._jobs['ra2'] = {'jobId': 'ra2', 'status': 'queued', 'ok': False, 'stdout': '', 'stderr': '',
                          'owner_session': 'alice', 'owner_call': 'c1'}
        b._job_meta['ra2'] = 1710.0
    entered, release = threading.Event(), threading.Event()
    poll_result, poll_error = [], []
    def poller():
        try:
            poll_result.append(post('/jobs/ra2/status', {**job_control(owner='alice'), 'wait': 5}))
        except BaseException as error:
            poll_error.append(repr(error))
    original_sleep = b.time.sleep
    def gated_sleep(seconds):
        if seconds >= 0.2 and not entered.is_set():
            entered.set()   # observation point: the handler is inside the wait loop now
            if not release.wait(5):
                poll_error.append('release gate never opened')
        return original_sleep(seconds)
    b.time.sleep = gated_sleep
    poll_thread = threading.Thread(target=poller); poll_thread.start()
    try:
        assert entered.wait(3), 'handler never reached the polling wait (or returned early)'
        got_lock = b._jobs_lock.acquire(timeout=2)
        assert got_lock, 'long-poll wait must not hold _jobs_lock while a poll is in flight'
        b._jobs['ra2']['status'] = 'done'; b._jobs['ra2']['ok'] = True; b._job_meta['ra2'] = 1711.0
        b._jobs_lock.release()
    finally:
        release.set()
        b.time.sleep = original_sleep
    poll_thread.join(5)
    assert not poll_thread.is_alive() and not poll_error, (poll_error, poll_result)
    assert poll_result and poll_result[0][0] == 200 and poll_result[0][1]['status'] == 'done', poll_result
    with b._jobs_lock:
        b._jobs.pop('ra2', None); b._job_meta.pop('ra2', None)
    original = b._execute
    try:
        b._execute = lambda fn: {'ok': True, 'stdout': 'actual result', 'stderr': ''}
        b._run_job('ra', 'pass')
        assert b._jobs['ra']['status'] == 'done' and b._jobs['ra']['stdout'] == 'actual result'
        def fail(fn):
            raise RuntimeError('pump failed')
        b._execute = fail
        b._jobs['ra']['status'] = 'queued'
        b._run_job('ra', 'pass')
        assert b._jobs['ra']['status'] == 'failed' and 'pump failed' in b._jobs['ra']['error']
    finally:
        b._execute = original

    with b._jobs_lock:
        for i in range(b._MAX_ACTIVE_JOBS):
            b._jobs[str(i)] = {'jobId': str(i), 'status': 'queued', 'owner_session': 'fixture', 'owner_call': 'call-1'}
    assert post('/jobs', admission('pass'))[0] == 429

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
