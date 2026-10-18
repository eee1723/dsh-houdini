from pathlib import Path
import ctypes
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli
from dsh_workbench import ensure, control, running
from dsh_runtime_compat import preferred_cached_bin
from dsh_houdini_installations import discover


def windows(pid):
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetWindow.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    rows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(window, unused):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == pid and user.IsWindowVisible(window):
            title = ctypes.create_unicode_buffer(512)
            user.GetWindowTextW(window, title, len(title))
            if 'DSH-Houdini' in title.value:
                rows.append(window)
        return True
    user.EnumWindows(callback_type(collect), 0)
    return user, rows


def main():
    reexec_unpacked_test_cli()
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('hfs', nargs='?', default='D:/houdini')
    parser.add_argument('--runtime-cache', type=Path, default=None)
    args = parser.parse_args()
    folder = Path(tempfile.mkdtemp(prefix='workbench-', dir=ROOT / 'tools/out'))
    env = isolated_environment(folder / 'env', gui=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        debug_port = probe.getsockname()[1]
    env['DSH_WORKBENCH_TEST_ROOT'] = str(folder)
    home = env['DSH_HOME']
    binary = (preferred_cached_bin(ROOT / '.npm-cache') if args.runtime_cache is None
              else args.runtime_cache.resolve() / 'node_modules/@deepseek-ai/dsh/lib/bin.js')
    if binary is None:
        raise RuntimeError('No prepared DSH runtime matching this plugin; run npm run runtime:prepare')
    workers = sorted(discover(args.hfs), key=lambda item: item['version'])
    if len(workers) < 2:
        raise RuntimeError('This composition needs two installed Houdini versions (H21 and H22)')
    worker_hfs = [Path(item['hfs']) for item in workers[:2]]
    worker_hython = [item / 'bin/hython.exe' for item in worker_hfs]
    node = shutil.which('node')
    subprocess.run([node, str(ROOT / 'tools/tests/prepare-shared-host-fixture.mjs'), str(binary), home, str(ROOT)],
                   env=env, cwd=ROOT, check=True, timeout=60)
    (Path(home) / 'profiles/web/cordis.patch.yml').write_text(json.dumps([{'insert': [{
        'id': 'workbench-fixture', 'name': (ROOT / 'tools/tests/workbench-dsh-fixture.mjs').as_uri()}]}]), encoding='utf-8')
    desktop_hfs = Path(args.hfs)
    desktop_python = next(desktop_hfs.glob('python3*/python.exe'))
    config = {'root': str(folder / 'desktop'), 'installation': str(ROOT), 'plugin': str(ROOT),
              'node': node, 'binary': str(binary), 'home': home, 'hfs': str(desktop_hfs),
              'python': str(desktop_python), 'debugPort': debug_port}
    previous = dict(os.environ)
    children, streams = [], []
    desktop = None
    project_temp = tempfile.TemporaryDirectory(prefix='dsh-workbench-project-')
    config['initialWorkspace'] = project_temp.name

    def command(session, tool=None, args=None, action=None):
        request = {'id': uuid.uuid4().hex, 'sessionId': session, 'tool': tool, 'args': args, 'action': action}
        temporary = folder / 'command.tmp'
        temporary.write_text(json.dumps(request), encoding='utf-8')
        # The fixture may have the previous command open for reading; Windows
        # refuses the replace while that handle exists. Retry the atomic rename
        # instead of writing the target in place.
        for attempt in range(50):
            try:
                temporary.replace(folder / 'command.json')
                break
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(.05)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
                if result['id'] == request['id']:
                    assert result['ok'], result
                    return result
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            time.sleep(.1)
        raise AssertionError('Host tool fixture timed out: ' + str(folder))

    def browser(session, label, directory, hip=None, refresh_title=False):
        result = subprocess.run([node, str(ROOT / 'tools/tests/workbench-browser.mjs'), str(debug_port), session,
                        str(folder / (label + '.png')), str(directory), str(hip) if hip else '', 'refresh-title' if refresh_title else ''], env=env, cwd=ROOT, timeout=50,
                       capture_output=True, text=True, errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
        (folder / (label + '.browser.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
        result.check_returncode()
    try:
        os.environ.clear()
        os.environ.update(env)
        config_file = folder / 'config.json'
        config_file.write_text(json.dumps(config), encoding='utf-8')
        racers = [subprocess.Popen([sys.executable, str(ROOT / 'tools/tests/workbench-start-racer.py'),
                  str(config_file), str(folder / ('racer-' + str(index) + '.json'))],
                  env=env, cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW) for index in range(2)]
        for racer in racers:
            assert racer.wait(timeout=150) == 0
        desktop = ensure(config)
        record = desktop['record']
        assert all(json.loads((folder / ('racer-' + str(index) + '.json')).read_text(encoding='utf-8'))['pid'] == record['pid'] for index in range(2))
        assert ensure(config)['record']['pid'] == record['pid']
        assert record['pid'] != os.getpid()
        deadline = time.monotonic() + 10
        while True:
            user, handles = windows(record['pid'])
            if handles or time.monotonic() >= deadline:
                break
            time.sleep(.1)
        assert len(handles) == 1, handles
        assert not user.GetWindow(handles[0], 4), 'desktop must not have a Houdini owner window'
        # Wide enough for the native sidebar; the conversation-row menu used by
        # the browser probe is not rendered in the compact rail layout.
        user.SetWindowPos(handles[0], None, 12000, 12000, 1440, 900, 0x0010)
        bad = {**record, 'token': '0' * 64}
        try:
            control(bad, 'status', timeout=5)
        except Exception:
            pass
        else:
            raise AssertionError('unauthenticated activation accepted')
        registry = Path(desktop['context']['executorRegistry'])
        project = Path(project_temp.name)
        endpoints = []
        for index, hython in enumerate(map(str, worker_hython)):
            hip = project / ('工程-' + str(index) + '.hip')
            hip.write_bytes(b'fixture path identity; not loaded')
            output = (folder / ('houdini-' + str(index) + '.log')).open('wb')
            streams.append(output)
            worker_env = isolated_environment(folder / ('houdini-env-' + str(index)), executable=Path(hython))
            worker_env['DSH_HOUDINI_RECOVERY_ROOT'] = str(folder / 'recovery')
            process = subprocess.Popen([hython, str(ROOT / 'tools/tests/dsh-multi-executor.test.py'), '--worker', '--workbench',
                '--registry', str(registry), '--hip', str(hip), '--task', 'unused'],
                cwd=Path(hython).parent, env=worker_env,
                stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            children.append(process)
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                values = [json.loads(path.read_text(encoding='utf-8')) for path in (registry / 'endpoints').glob('*.json')]
                matched = [value for value in values if value['pid'] == process.pid and value.get('workspace_path')]
                if matched:
                    endpoints.append(matched[0])
                    break
                if process.poll() is not None:
                    raise AssertionError('Houdini fixture failed: ' + str(folder))
                time.sleep(.1)
            else:
                raise AssertionError('registration timeout: ' + str(folder))
        results = []
        for endpoint in endpoints:
            request = {'executorId': endpoint['executor_id'], 'registrationId': endpoint['registration_id'],
                       'expectedHip': endpoint['hip_path'], 'requestId': uuid.uuid4().hex}
            value = control(record, 'open', request)
            results.append(value)
            assert control(record, 'open', {**request, 'requestId': uuid.uuid4().hex})['sessionId'] == value['sessionId']
            browser(value['sessionId'], 'project-' + str(len(results)), project, endpoint['hip_path'])
            idle = command(value['sessionId'], action='idle')
            assert idle['idle'] and not idle['started'], 'opening a project must not wake an Agent or call a model'
            assert idle['title'] is None, 'project opening must not pin a filename as a user-owned title'
        assert results[0]['sessionId'] != results[1]['sessionId'], 'same-directory projects must not select each other'
        original = children[0]
        original.kill()
        original.wait(timeout=10)
        output = (folder / 'empty-reopen.log').open('wb')
        streams.append(output)
        empty_hython = str(worker_hython[0])
        empty_env = isolated_environment(folder / 'empty-reopen-env', executable=Path(empty_hython))
        empty_env['DSH_HOUDINI_RECOVERY_ROOT'] = str(folder / 'recovery')
        empty_reopen = subprocess.Popen([empty_hython, str(ROOT / 'tools/tests/dsh-multi-executor.test.py'),
            '--worker', '--workbench', '--registry', str(registry), '--hip', endpoints[0]['hip_path'], '--task', 'unused'],
            cwd=str(worker_hfs[0] / 'bin'), env=empty_env, stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)
        children[0] = empty_reopen
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            values = [json.loads(path.read_text(encoding='utf-8')) for path in (registry / 'endpoints').glob('*.json')]
            matched = [value for value in values if value['pid'] == empty_reopen.pid and value.get('workspace_path')]
            if matched:
                break
            assert empty_reopen.poll() is None
            time.sleep(.1)
        assert matched
        endpoints[0] = matched[0]
        empty_request = {'executorId': endpoints[0]['executor_id'], 'registrationId': endpoints[0]['registration_id'],
            'expectedHip': endpoints[0]['hip_path'], 'requestId': uuid.uuid4().hex, 'sessionId': results[0]['sessionId']}
        assert control(record, 'open', empty_request)['sessionId'] == results[0]['sessionId'], 'explicitly selected unexecuted conversations need no fictional recovery checkpoint'
        assert control(record, 'open', {**empty_request, 'requestId': uuid.uuid4().hex})['sessionId'] == results[0]['sessionId']
        for index, value in enumerate(results):
            session = value['sessionId']
            inspected = command(session, 'houdini_inspect', {'code': '__result__=hou.applicationVersionString()'})['value']
            assert inspected['ok'] and inspected['result'] == endpoints[index]['houdini_version'], inspected
            assert inspected['execution']['executor_id'] == endpoints[index]['executor_id']
            created = command(session, 'houdini_exec', {'code': "__result__=tab_create('/obj','geo',name='desktop_owned').path()"})['value']
            assert created['ok'], created
            destination = project / ('saved-' + str(index)) / 'project.hip'
            saved = command(session, 'houdini_exec', {'code': 'scene_save_as(' + repr(str(destination)) + ', ' +
                repr(endpoints[index]['hip_path']) + ", 'isolated test save target')"})['value']
            assert saved['ok'] and destination.is_file(), saved
            followed = command(session, action='beforeStep')
            assert Path(followed['cwd']).resolve() == destination.parent.resolve(), followed
            summary = command(session, action='idle')
            assert summary['title'] and summary['title']['source']['kind'] != 'user', 'actual DSH automatic naming must survive project binding'
            old_workspace = next(item for item in summary['workspaces'] if Path(item['path']).resolve() == project.resolve())
            assert session not in old_workspace['sessionIds']
            if index == 0:
                assert results[1]['sessionId'] in old_workspace['sessionIds'], 'Save As must not move the other conversation'
            new_workspace = next(item for item in summary['workspaces'] if Path(item['path']).resolve() == destination.parent.resolve())
            assert session in new_workspace['sessionIds'], 'same conversation follows the saved file without cloning'
            endpoints[index] = json.loads((registry / 'endpoints' / (endpoints[index]['executor_id'] + '.json')).read_text(encoding='utf-8'))
            control(record, 'open', {'executorId': endpoints[index]['executor_id'], 'registrationId': endpoints[index]['registration_id'],
                'expectedHip': endpoints[index]['hip_path'], 'requestId': uuid.uuid4().hex})
            if index == 0:
                command(session, action='pinTitle')
            browser(session, 'saved-project-' + str(index), destination.parent, str(destination).replace('\\', '/'), refresh_title=index == 0)
            if index == 0:
                renamed = command(session, action='idle')
                assert renamed['title']['source']['kind'] != 'user', 'explicit native menu must release the old pinned filename title'
                assert renamed['turns'] == summary['turns'], 'title refresh must not start a new agent work turn'
        with ThreadPoolExecutor(max_workers=1) as pool:
            interrupted = pool.submit(command, results[0]['sessionId'], 'houdini_exec', {
                'code': "import time\ntime.sleep(30)\ntab_create('/obj','geo',name='must_not_replay')"})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 12
            while True:
                request = urllib.request.Request(endpoints[0]['bridge_url'] + '/health',
                    headers={'X-DSH-Houdini-Executor': endpoints[0]['executor_id']})
                with opener.open(request, timeout=3) as response:
                    health = json.load(response)
                if health['activeRequests'] > 0:
                    break
                assert time.monotonic() < deadline, 'fixture operation never became active'
                time.sleep(.1)
            live_endpoint = endpoints[1]
            control(record, 'open', {'executorId': live_endpoint['executor_id'], 'registrationId': live_endpoint['registration_id'],
                'expectedHip': live_endpoint['hip_path'], 'requestId': uuid.uuid4().hex})
            browser(results[1]['sessionId'], 'while-other-houdini-is-busy', Path(live_endpoint['hip_path']).parent)
            children[0].kill()
            children[0].wait(timeout=10)
            assert not interrupted.result(timeout=30)['value']['ok'], 'a lost live operation must not be reported as success'
        assert control(record, 'status')['record']['pid'] == record['pid']
        endpoint = endpoints[1]
        assert control(record, 'open', {'executorId': endpoint['executor_id'], 'registrationId': endpoint['registration_id'],
            'expectedHip': endpoint['hip_path'], 'requestId': uuid.uuid4().hex})['sessionId'] == results[1]['sessionId']
        browser(results[1]['sessionId'], 'after-other-houdini-crash', Path(endpoint['hip_path']).parent)
        still_live = command(results[1]['sessionId'], 'houdini_inspect', {'code': '__result__=hou.applicationVersionString()'})['value']
        assert still_live['ok'] and still_live['result'] == endpoint['houdini_version']
        nested = command(results[1]['sessionId'], 'run_code', {'code':
            'return await tools.houdini_inspect({code:"__result__=hou.applicationVersionString()"});',
            'description': 'Verify the same selected executor through the nested transport'})['value']
        assert nested['ok'] and nested['result'] == endpoint['houdini_version']
        assert nested['execution']['executor_id'] == endpoint['executor_id']
        output = (folder / 'replacement.log').open('wb')
        streams.append(output)
        replacement_env = isolated_environment(folder / 'replacement-env', executable=Path(empty_hython))
        replacement_env['DSH_HOUDINI_RECOVERY_ROOT'] = str(folder / 'recovery')
        replacement = subprocess.Popen([empty_hython, str(ROOT / 'tools/tests/dsh-multi-executor.test.py'),
            '--worker', '--workbench', '--load', '--registry', str(registry), '--hip', endpoints[0]['hip_path'], '--task', 'unused'],
            cwd=str(worker_hfs[0] / 'bin'), env=replacement_env, stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)
        children.append(replacement)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            values = [json.loads(path.read_text(encoding='utf-8')) for path in (registry / 'endpoints').glob('*.json')]
            matched = [value for value in values if value['pid'] == replacement.pid and value.get('workspace_path')]
            if matched:
                break
            assert replacement.poll() is None, 'replacement fixture failed: ' + str(folder)
            time.sleep(.1)
        assert matched
        reopened = matched[0]
        resumed = control(record, 'open', {'executorId': reopened['executor_id'], 'registrationId': reopened['registration_id'],
            'expectedHip': reopened['hip_path'], 'requestId': uuid.uuid4().hex})
        assert resumed['sessionId'] == results[0]['sessionId'], 'manual reopen must retain the original conversation'
        command(resumed['sessionId'], action='beforeStep')
        not_replayed = command(resumed['sessionId'], 'houdini_inspect', {'code': "__result__=hou.node('/obj/must_not_replay') is None"})['value']
        assert not_replayed['ok'] and not_replayed['result'] is True, 'an interrupted mutation must not be replayed after recovery'
        deleted = command(resumed['sessionId'], 'houdini_exec', {'code': "delete_node('/obj/desktop_owned')"})['value']
        assert deleted['ok'], deleted
        unaffected = command(results[1]['sessionId'], 'houdini_inspect', {'code': "__result__=hou.node('/obj/desktop_owned') is not None"})['value']
        assert unaffected['ok'] and unaffected['result'] is True
        browser(resumed['sessionId'], 'manually-reopened-original-task', Path(reopened['hip_path']).parent)
        user.PostMessageW(handles[0], 0x0010, 0, 0)
        deadline = time.monotonic() + 20
        while running(config['root']) and time.monotonic() < deadline:
            time.sleep(.1)
        assert running(config['root']) is None, 'closing the desktop must exit rather than silently hide'
        assert children[1].poll() is None, 'closing the desktop must not terminate Houdini'
        previous_generation = record['generation']
        desktop = ensure(config)
        record = desktop['record']
        assert record['generation'] != previous_generation
        retained = control(record, 'open', {'executorId': endpoint['executor_id'], 'registrationId': endpoint['registration_id'],
            'expectedHip': endpoint['hip_path'], 'requestId': uuid.uuid4().hex})
        assert retained['sessionId'] == results[1]['sessionId'], 'desktop restart must reuse durable original DSH history'
        browser(retained['sessionId'], 'after-workbench-restart', Path(endpoint['hip_path']).parent, endpoint['hip_path'])
        retained_result = command(retained['sessionId'], 'houdini_inspect', {'code': '__result__=hou.applicationVersionString()'})['value']
        assert retained_result['ok'] and retained_result['result'] == endpoint['houdini_version']
        user, handles = windows(record['pid'])
        assert len(handles) == 1
        user.PostMessageW(handles[0], 0x0010, 0, 0)
        deadline = time.monotonic() + 20
        while running(config['root']) and time.monotonic() < deadline:
            time.sleep(.1)
        assert running(config['root']) is None and children[1].poll() is None
        print('PASS simultaneous launch and initiator exit, independent Python/Qt desktop, one Host, unowned taskbar window, authentication, actual Qt session/cwd, H21/H22 tools and Save As, A crash/B survives, manual original-project recovery, desktop restart retains history and live Houdini: ' + str(folder), flush=True)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)
        for stream in streams:
            stream.close()
        project_temp.cleanup()
        if desktop and running(config['root']):
            user, handles = windows(desktop['record']['pid'])
            for handle in handles:
                user.PostMessageW(handle, 0x0010, 0, 0)
        os.environ.clear()
        os.environ.update(previous)


if __name__ == '__main__':
    main()
