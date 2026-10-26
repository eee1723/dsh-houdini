"""Official Desktop menu/launch handshake, entirely against owned fixtures."""
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_desktop_client as desktop


with tempfile.TemporaryDirectory(prefix='dsh-desktop-client-') as temporary:
    folder = Path(temporary)
    home = folder / 'simulated-official-home'
    descriptor = home / 'dsh-houdini/desktop.json'
    received = []
    token = 'b' * 64
    generation = 'f' * 32

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.headers['Authorization'] == 'Bearer ' + token
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append((self.path, body))
            refused = body.get('expectedHip') == 'fixture-refusal'
            response = {'ok': False, 'error': 'Fixture: selected scene changed'} if refused else (
                {'ok': True, 'value': {'generation': generation}} if self.path == '/status' else {
                'ok': True, 'value': {'sessionId': 'fixture-session'}})
            data = json.dumps(response).encode()
            self.send_response(400 if refused else 200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    with patch.dict(os.environ, {'DSH_HOME': str(home)}, clear=True):
        assert desktop.descriptor_path() == descriptor
        try:
            desktop.connect(timeout=0, activate=False)
        except RuntimeError:
            pass
        else:
            raise AssertionError('missing Desktop was silently accepted')
        assert not home.exists(), 'a missing host must not initialize official data'

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    try:
        record = {'schemaVersion': 1, 'pid': os.getpid(), 'generation': generation,
                  'port': server.server_port, 'token': token, 'pluginRoot': str(folder / 'separate-desktop-plugin'),
                  'executorRegistry': str(folder / 'registry'), 'launchesRoot': str(folder / 'launches')}
        descriptor.parent.mkdir(parents=True)
        descriptor.write_text(json.dumps(record), encoding='utf-8')
        before = descriptor.read_bytes()
        with patch.dict(os.environ, {'DSH_HOME': str(home), 'HTTP_PROXY': 'http://127.0.0.1:1'}, clear=True):
            assert desktop.connect(timeout=1, activate=False) == record
            payload = {'executorId': 'a' * 32, 'registrationId': 'c' * 32,
                       'expectedHip': str(folder / 'named.hip'), 'requestId': 'd' * 32}
            assert desktop.request(record, 'open-workspace', payload)['sessionId'] == 'fixture-session'
            assert received[-1] == ('/open-workspace', payload)
            try:
                desktop.request(record, 'open-workspace', {**payload, 'expectedHip': 'fixture-refusal'})
            except RuntimeError as error:
                assert str(error) == 'Fixture: selected scene changed'
            else:
                raise AssertionError('Desktop refusal was hidden')
            try:
                desktop.request(record, 'arbitrary-shell', {'command': 'must-not-run'})
            except ValueError:
                pass
            else:
                raise AssertionError('arbitrary control action was accepted')
            assert descriptor.read_bytes() == before
            descriptor.unlink()
            with patch.object(desktop, 'activate_desktop', side_effect=lambda: descriptor.write_bytes(before)) as activate, \
                 patch.object(desktop.time, 'sleep'):
                assert desktop.connect(timeout=1) == record
                activate.assert_called_once()
            with patch.object(desktop, 'request', side_effect=[{'generation': 'retired'}, {'generation': generation}]), \
                 patch.object(desktop, 'activate_desktop') as activate, patch.object(desktop.time, 'sleep'):
                assert desktop.connect(timeout=1) == record
                activate.assert_called_once()
            with patch.object(desktop.os, 'startfile', side_effect=OSError('fixture: no protocol handler'), create=True):
                try:
                    desktop.activate_desktop()
                except RuntimeError as error:
                    assert '官方 DSH Desktop' in str(error)
                else:
                    raise AssertionError('missing native Desktop handler was hidden')
        ticket_root = Path(record['launchesRoot'])
        ticket_root.mkdir()
        ticket_path = ticket_root / ('e' * 32 + '.json')
        ticket = {'id': 'e' * 32, 'generation': generation, 'hfs': str(folder / 'HFS'),
                  'hip': None, 'workspace': str(folder / 'workspace'), 'pid': os.getpid()}
        ticket_path.write_text(json.dumps(ticket), encoding='utf-8')
        assert desktop.read_launch_ticket(ticket_path, record) == ticket
        ticket['generation'] = 'e' * 32
        ticket_path.write_text(json.dumps(ticket), encoding='utf-8')
        assert desktop.read_launch_ticket(ticket_path, record) == ticket, 'operation generation is independent of current Host authentication'
        ticket['generation'] = 'retired'
        ticket_path.write_text(json.dumps(ticket), encoding='utf-8')
        try:
            desktop.read_launch_ticket(ticket_path, record)
        except ValueError:
            pass
        else:
            raise AssertionError('retired Desktop launch was accepted')
        invalid = {**record, 'executorRegistry': 'relative'}
        descriptor.write_text(json.dumps(invalid), encoding='utf-8')
        try:
            desktop.read_descriptor(descriptor)
        except ValueError:
            pass
        else:
            raise AssertionError('relative registry was accepted')
    finally:
        server.shutdown()
        server.server_close()
        serving.join(timeout=5)

    # Source registration reads/writes only its explicit Houdini package target.
    spec = importlib.util.spec_from_file_location('desktop_helper_installer', ROOT / 'houdini/install.py')
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    explicit_packages = folder / 'houdini-packages'
    with patch.dict(os.environ, {'DSH_HOME': str(home)}, clear=True), patch.object(sys, 'argv', [
            'install.py', '--packages-dir', str(explicit_packages)]), redirect_stdout(io.StringIO()):
        assert installer.main() == 0
    package = json.loads((explicit_packages / 'dsh-houdini.json').read_text(encoding='utf-8'))
    assert package['path'] == '$DSH_HOUDINI_PATH'
    assert descriptor.read_text(encoding='utf-8') == json.dumps(invalid)
    assert not (home / 'profiles').exists()

    # Both native entry points delegate to the shared connection operation.
    import dsh_workbench_entry as entry
    starts = []
    launcher = SimpleNamespace(_startup_failure=lambda error: starts.append(('error', str(error))))
    shared = SimpleNamespace(open_workspace=lambda actual, **kwargs: starts.append((actual, kwargs)) or True)
    with patch.dict(sys.modules, {'dsh_launcher': launcher, 'dsh_workbench_client': shared}), \
         patch.dict(os.environ, {'DSH_HOUDINI_LAUNCH_TICKET': str(ticket_path)}, clear=True):
        assert entry.attach() is True
        assert entry.attach() is False
    assert starts == [(launcher, {'launch_ticket': str(ticket_path)})]

print('Desktop descriptor/authentication, source registration isolation and stable launch entry delegation passed')
