"""Real HTTP and main-thread FIFO cancellation, with an isolated UI-work probe.

No running Houdini is contacted. The tiny UI body is replaced by a call recorder;
the HTTP routes, queue and receipt registry are production implementations.
"""
from pathlib import Path
from http.server import ThreadingHTTPServer
import http.client
import json
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import dsh_bridge as bridge

owner = 'node-navigation-http-fixture'
server = ThreadingHTTPServer(('127.0.0.1', 0), bridge._Handler)
serving = threading.Thread(target=server.serve_forever, daemon=True)
serving.start()
contract = {'version': bridge._EXECUTION_CONTRACT_VERSION, 'hash': bridge._VERB_CATALOG_HASH}
calls, responses, errors = [], [], []
original_run, original_pump = bridge.run_code, bridge._pump_active


def post(path, body):
    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
    connection.request('POST', path, json.dumps(body), headers={'Content-Type': 'application/json'})
    response = connection.getresponse()
    result = response.status, json.loads(response.read())
    connection.close()
    return result


def prepare(kind='node_navigation'):
    body = {'owner_session': owner}
    if kind == 'node_navigation':
        body['request_kind'] = kind
    status, result = post('/requests/prepare', body)
    assert status == 200, result
    return result['requestRef']


def envelope(token):
    return {'owner_session': owner, 'owner_call': 'click', 'expected_contract': contract,
            'request_ref': token}


def navigation(token):
    return {**envelope(token), 'reference': {'id': 'c' * 32},
            'expected_hip': 'E:/工程/自行车 "交付".hip'}


def start_queued(body):
    def submit():
        try:
            responses.append(post('/nodes/navigate', body))
        except BaseException as error:
            errors.append(repr(error))
    worker = threading.Thread(target=submit)
    worker.start()
    deadline = time.monotonic() + 3
    while bridge._work_queue.empty() and time.monotonic() < deadline:
        time.sleep(.005)
    assert not bridge._work_queue.empty(), errors
    return worker


def probe(code, allow_raw, owner_session, owner_call, read_only):
    assert threading.get_ident() == bridge._HOU_THREAD_ID
    assert allow_raw is None and read_only is True
    assert owner_session == owner and owner_call == 'click'
    assert code.startswith('__result__=focus_node(') and 'expected_hip=' in code
    calls.append(code)
    return {'ok': True, 'stdout': '', 'stderr': '', 'result': {'path': '/obj/control'}}


try:
    bridge.run_code, bridge._pump_active = probe, True
    # Cancellation can win before a delayed navigation reaches admission.
    token = prepare()
    assert post('/nodes/cancel', envelope(token))[1]['status'] == 'not_executed'
    assert post('/nodes/navigate', navigation(token))[0] == 409
    assert bridge._work_queue.empty() and not calls
    # Only typed tickets admit UI navigation; neither generic execution nor a
    # foreign task can cancel an issued or already queued ordinary request.
    generic = prepare('exec')
    assert post('/nodes/cancel', envelope(generic))[0] == 409
    assert post('/nodes/navigate', navigation(generic))[0] == 409
    foreign = prepare()
    assert post('/nodes/cancel', {**envelope(foreign), 'owner_session': 'other'})[0] == 409
    assert post('/nodes/navigate', {**navigation(foreign), 'code': 'pass'})[0] == 400
    assert bridge._work_queue.empty()
    # A caller cannot relabel arbitrary Python as UI navigation to obtain
    # cancellable generic mutation admission with a typed navigation ticket.
    typed = prepare()
    for route in ('/exec', '/jobs'):
        generic_body = {**envelope(typed), 'code': 'raise RuntimeError("must never dispatch")'}
        assert post(route, {**generic_body, 'request_kind': 'node_navigation'})[0] == 400
        assert post(route, generic_body)[0] == 409
    assert bridge._work_queue.empty() and not calls
    # An admitted request waits in the real owning-thread queue. Cancellation
    # retires it before the pump resumes and the UI body is never invoked.
    token = prepare()
    worker = start_queued(navigation(token))
    assert bridge._request_registry.status(token, owner)['status'] == 'queued'
    assert post('/nodes/cancel', envelope(token))[1]['cancelled'] is True
    bridge._pump()
    worker.join(3)
    assert not worker.is_alive() and not errors and not calls
    assert responses[-1][1]['requestReceipt']['status'] == 'not_executed', responses
    # A native navigation already executing cannot be interrupted; cancellation
    # reports running and preserves the real result without a second invocation.
    token = prepare()
    entered, release = threading.Event(), threading.Event()
    running_cancel = []
    def running_probe(*args):
        entered.set()
        assert release.wait(3)
        return probe(*args)
    def cancel_running():
        assert entered.wait(3)
        running_cancel.append(post('/nodes/cancel', envelope(token)))
        release.set()
    bridge.run_code = running_probe
    worker = start_queued(navigation(token))
    observer = threading.Thread(target=cancel_running)
    observer.start()
    bridge._pump()
    worker.join(3)
    observer.join(3)
    assert not worker.is_alive() and not observer.is_alive() and not errors
    assert running_cancel[0][1]['status'] == 'running' and not running_cancel[0][1]['cancelled']
    assert len(calls) == 1 and responses[-1][1]['ok'] is True
    replay = post('/nodes/navigate', navigation(token))
    assert replay[1]['ok'] is True and len(calls) == 1, 'same ticket returns original result only'
    print('navigation HTTP: issued/queued cancellation, fixed payload, task isolation and non-interrupted running UI passed')
finally:
    bridge.run_code, bridge._pump_active = original_run, original_pump
    server.shutdown()
    server.server_close()
    serving.join(3)
