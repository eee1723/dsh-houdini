"""Shared menu/launch pipeline with real local HTTP retries and fake HOM facts.

No Desktop, Houdini process, model, or user data is accessed. The fake scheduler
marks main/worker dispatch; the local server changes authentication generation
after committing one request and deliberately drops its first HTTP response.
"""
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_desktop_client as desktop
import dsh_workbench_client as shared
import dsh_deployment


with tempfile.TemporaryDirectory(prefix='dsh-connection-operation-') as temporary:
    # The production launch identity canonicalizes HFS. Use that same existing
    # root spelling when TEMP is a Windows 8.3 alias, without weakening identity.
    folder = Path(temporary).resolve()
    descriptor = folder / 'desktop.json'
    launches = folder / 'launches'
    launches.mkdir()
    identity = {'pid': os.getpid(), 'processStarted': '1001', 'hfs': str(folder),
                'hipPath': str(folder / 'scene.hip'), 'hipIsNew': False}
    state = {}
    request_log = []
    lane = ['main']
    scheduled = []

    def save_descriptor():
        value = {'schemaVersion': 1, 'pid': os.getpid(), 'generation': state['generation'],
                 'token': state['token'], 'port': server.server_port,
                 'pluginRoot': str(folder / 'separate-node-package'),
                 'executorRegistry': str(folder / 'registry'), 'launchesRoot': str(launches)}
        descriptor.write_text(json.dumps(value), encoding='utf-8')

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            request_log.append((self.path, body, state['generation']))
            code = 200
            if state.get('rotate401') and self.path in ('/open-workspace', '/launch-attached'):
                state['rotate401'] = False
                state['generation'], state['token'] = 'e' * 32, 'd' * 64
                save_descriptor()
            if self.headers.get('Authorization') != 'Bearer ' + state['token']:
                code, result = 401, {'ok': False, 'error': 'retired Host token'}
            elif self.path in state['pending503']:
                state['pending503'].remove(self.path)
                code, result = 503, {'ok': False, 'error': 'fixture: original process observation is temporarily unknown'}
            elif self.path == '/status':
                result = {'ok': True, 'value': {'generation': state['generation']}}
            elif self.path == '/ticket-current':
                assert {key: body[key] for key in identity} == identity
                assert body['id'] == state['operationId']
                if state.get('refuse'):
                    code, result = 400, {'ok': False, 'error': 'fixture: original launch was not admitted'}
                else:
                    result = {'ok': True, 'value': {'id': body['id'], 'phase': state['phase'],
                              'workspace': str(folder), 'hfs': str(folder), 'hip': identity['hipPath']}}
            elif self.path == '/launch-progress':
                result = {'ok': True, 'value': {}}
            elif self.path in ('/open-workspace', '/launch-attached'):
                detached_receipt = self.path == '/launch-attached' and state['phase'] == 'detached'
                operation = body.get('id') or body['requestId']
                signature = json.dumps(body, sort_keys=True)
                if operation not in state['receipts']:
                    state['receipts'][operation] = signature
                    state['stored'] += 1
                    if not detached_receipt:
                        state['bindings'] += 1
                assert state['receipts'][operation] == signature, 'retries must retain the exact receipt/request'
                value = {'phase': 'detached'} if detached_receipt else {'sessionId': 'fixture-session'}
                if state.get('drop'):
                    state['drop'] = False
                    state['generation'], state['token'] = 'e' * 32, 'd' * 64
                    save_descriptor()
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                result = {'ok': True, 'value': value}
            elif self.path == '/launch-failed':
                state['failed'].append(body)
                result = {'ok': True, 'value': {}}
            else:
                raise AssertionError(self.path)
            raw = json.dumps(result).encode()
            self.send_response(code)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()

    class Worker:
        def __init__(self, target, **kwargs): self.target = target
        def start(self):
            previous = lane[0]
            lane[0] = 'worker'
            try: self.target()
            finally: lane[0] = previous

    class Timer:
        def __init__(self, *args): self.timeout = self; self.stopped = False
        def connect(self, callback): self.callback = callback
        def start(self, interval): pass
        def stop(self): self.stopped = True
        @staticmethod
        def singleShot(delay, callback): scheduled.append(callback)

    def run(mode, *, drop=False, rotate401=False, pending503=False, detached=False, refusal=False, preparation_error=False, pending_menu=False):
        state.clear()
        state.update(generation='f' * 32, token='b' * 64, operationId='a' * 32,
                     phase='detached' if detached else 'waiting', drop=drop, rotate401=rotate401, refuse=refusal,
                     receipts={}, bindings=0, stored=0, failed=[],
                     pending503=['/ticket-current', '/launch-attached'] if pending503 else [])
        request_log.clear()
        scheduled.clear()
        save_descriptor()
        ticket_path = launches / ('a' * 32 + '.json')
        ticket_path.write_text(json.dumps({'id': state['operationId'], 'generation': 'c' * 32,
            'hfs': str(folder), 'workspace': str(folder), 'hip': identity['hipPath'], 'pid': os.getpid()}), encoding='utf-8')
        counts = {'capture': 0, 'publish': 0, 'local': 0, 'activate': 0}
        errors, messages = [], []

        def fact(value):
            assert lane[0] == 'main'
            return value

        fake_hou = ModuleType('hou')
        fake_hou.isUIAvailable = lambda: fact(True)
        fake_hou.hipFile = SimpleNamespace(path=lambda: fact(identity['hipPath']), isNewFile=lambda: fact(False))
        fake_hou.qt = SimpleNamespace(mainWindow=lambda: fact(None))
        fake_hou.ui = SimpleNamespace(setStatusMessage=lambda text: (fact(None), messages.append(text)))
        qt = ModuleType('hutil.Qt')
        qt.QtCore = SimpleNamespace(QTimer=Timer)

        def prepare_registration(**kwargs):
            fact(None)
            counts['capture'] += 1
            if preparation_error: raise RuntimeError('fixture: native preparation failed')
            return {'executor_id': '1' * 32, 'hip': identity['hipPath'], 'scene': {}}

        def publish_registration(*args):
            assert lane[0] == 'worker'
            counts['publish'] += 1
            return {'registration_id': '2' * 32}

        def require_local():
            fact(None)
            counts['local'] += 1

        def activate():
            assert lane[0] == 'worker'
            counts['activate'] += 1

        original_request = desktop.request
        def worker_request(*args, **kwargs):
            assert lane[0] == 'worker', 'HTTP must never execute in the main dispatch'
            return original_request(*args, **kwargs)

        launcher = SimpleNamespace(require_local_modules=require_local, _hip_dir=lambda: fact(str(folder)),
                                    _startup_failure=lambda error: (fact(None), errors.append(str(error))))
        with ExitStack() as patches:
            patches.enter_context(patch.dict(sys.modules, {'hou': fake_hou, 'hutil': ModuleType('hutil'), 'hutil.Qt': qt,
                'dsh_shared_executor': SimpleNamespace(prepare_registration=prepare_registration, publish_registration=publish_registration)}))
            patches.enter_context(patch.dict(os.environ, {'HFS': str(folder), 'DSH_HOUDINI_DESKTOP_DESCRIPTOR': str(descriptor)}))
            patches.enter_context(patch.object(shared, 'threading', SimpleNamespace(Thread=Worker)))
            patches.enter_context(patch.object(shared, 'install_observation', lambda: fact(None)))
            patches.enter_context(patch.object(desktop, 'activate_desktop', activate))
            patches.enter_context(patch.object(desktop, 'request', worker_request))
            patches.enter_context(patch.object(dsh_deployment, '_process_started', lambda pid: '1001'))
            if os.name == 'nt':
                patches.enter_context(patch('ctypes.windll.user32.AllowSetForegroundWindow', return_value=True))
            assert shared.open_workspace(launcher, launch_ticket=ticket_path if mode == 'launch' else None)
            if pending_menu:
                assert shared.open_workspace(launcher) is False, 'the busy call should retain one explicit menu intention'
            for _ in range(20):
                timer = shared._TIMER
                if timer is not None:
                    timer.callback()
                elif scheduled:
                    scheduled.pop(0)()
                else:
                    break
            assert shared._TIMER is None and not shared._BUSY and shared._PENDING_MENU is None and not scheduled
        return counts, errors, messages, list(request_log), dict(state)

    try:
        counts, errors, messages, log, result = run('launch', drop=True)
        assert not errors, errors
        assert counts['capture'] == counts['publish'] == result['stored'] == result['bindings'] == 1
        receipts = [body for route, body, generation in log if route == '/launch-attached']
        assert len(receipts) == 2 and receipts[0] == receipts[1]
        admitted = [(body, generation) for route, body, generation in log if route == '/ticket-current']
        assert len(admitted) == 2 and admitted[0][0] == admitted[1][0]
        assert [generation for body, generation in admitted] == ['f' * 32, 'e' * 32]
        assert [body['stage'] for route, body, generation in log if route == '/launch-progress'] == ['capturing', 'registering', 'binding']
        assert not result['failed'], 'a dropped response is not launch failure'

        counts, errors, messages, log, result = run('launch', rotate401=True)
        assert not errors and counts['capture'] == counts['publish'] == result['stored'] == 1
        assert len([row for row in log if row[0] == '/ticket-current']) == 2
        assert len([row for row in log if row[0] == '/launch-attached']) == 2
        assert not result['failed'], 'retired authentication is not a launch failure'

        counts, errors, messages, log, result = run('launch', pending503=True)
        assert not errors and counts['capture'] == counts['publish'] == result['stored'] == result['bindings'] == 1
        assert len([row for row in log if row[0] == '/ticket-current']) == 2
        assert len([row for row in log if row[0] == '/launch-attached']) == 2
        assert not result['failed'], 'temporary observation failure must retry the original operation'

        counts, errors, messages, log, result = run('menu', drop=True)
        assert not errors and counts['capture'] == counts['publish'] == 1
        assert result['stored'] == result['bindings'] == 1
        requests = [body for route, body, generation in log if route == '/open-workspace']
        assert len(requests) == 2 and requests[0] == requests[1]
        assert not any(route.startswith('/ticket') or route.startswith('/launch') for route, body, generation in log)
        assert counts['activate'] == 1

        counts, errors, messages, log, result = run('launch', detached=True)
        assert not errors and counts['capture'] == counts['publish'] == result['stored'] == 1
        assert result['bindings'] == 0 and '没有换绑' in messages[-1]

        counts, errors, messages, log, result = run('launch', refusal=True)
        assert errors == ['fixture: original launch was not admitted']
        assert counts['capture'] == counts['publish'] == 0 and not result['failed']

        counts, errors, messages, log, result = run('launch', preparation_error=True)
        assert counts['capture'] == 1 and counts['publish'] == 0
        assert len(result['failed']) == 1 and result['failed'][0]['id'] == 'a' * 32
        assert errors == ['fixture: native preparation failed']

        counts, errors, messages, log, result = run('launch', pending_menu=True)
        assert not errors and counts['capture'] == counts['publish'] == result['bindings'] == 1
        assert counts['activate'] == 1
        assert not any(route == '/open-workspace' for route, body, generation in log), \
            'successful automatic connection reveals the same Desktop instead of creating another conversation'

        counts, errors, messages, log, result = run('launch', detached=True, pending_menu=True)
        assert not errors and counts['capture'] == counts['publish'] == 2
        assert result['bindings'] == 1
        assert len([row for row in log if row[0] == '/launch-attached']) == 1
        assert len([row for row in log if row[0] == '/open-workspace']) == 1, \
            'the explicit pending menu gets fresh scene facts, not a replay of the old launch receipt'

        counts, errors, messages, log, result = run('launch', refusal=True, pending_menu=True)
        assert not errors and counts['capture'] == counts['publish'] == result['bindings'] == 1
        assert len([row for row in log if row[0] == '/ticket-current']) == 1
        assert len([row for row in log if row[0] == '/open-workspace']) == 1

        channel = desktop.DesktopConnection(timeout=1)
        channel.record = desktop.read_descriptor(descriptor)
        channel.deadline = 0
        before = len(request_log)
        try:
            channel.call('open-workspace', {'requestId': '9' * 32})
        except desktop.DesktopUnavailable:
            pass
        else:
            raise AssertionError('expired worker budget still delivered a request')
        assert len(request_log) == before
    finally:
        server.shutdown()
        server.server_close()
        serving.join(timeout=5)

print('Shared launch/menu admission, cross-Host receipt retry, one capture/publication, detached receipt and failure boundaries passed')
