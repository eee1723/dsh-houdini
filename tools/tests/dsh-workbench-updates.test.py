"""Real isolated DSH/Qt update entry; no Houdini, model request or user state.

Run with a built checkout and its preferred prepared DSH cache:
  D:/houdini/python311/python.exe -B tools/tests/dsh-workbench-updates.test.py
The only mocked boundary is GitHub discovery in this test's desktop process.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'houdini/python3.11libs')]
from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value), encoding='utf8')
    for attempt in range(100):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 99:
                raise
            time.sleep(.02)


def worker(config_file):
    import dsh_release_policy as policy
    import dsh_workbench as desktop
    config = json.loads(config_file.read_text(encoding='utf8'))
    dll_directory = os.add_dll_directory(str(Path(config['hfs']) / 'bin'))
    import dsh_webview
    folder = config_file.parent
    captured, handled = {}, None
    original_check = policy.ReleaseCheck
    class ObservedCheck(original_check):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured['check'] = self
    def discover():
        (folder / 'query-started').touch()
        deadline = time.monotonic() + 120
        while True:
            query = json.loads((folder / 'query.json').read_text(encoding='utf8'))
            if query['ready']:
                break
            if time.monotonic() > deadline:
                raise TimeoutError('authored discovery was not released')
            time.sleep(.05)
        if query['kind'] == 'failure':
            raise TimeoutError('isolated release network failure')
        return policy.validate_published_release({'id': 987654, 'draft': False, 'prerelease': False,
            'published_at': '2026-10-20T00:00:00Z', 'tag_name': 'v99.0.0'})
    policy.latest_stable_release, policy.ReleaseCheck = discover, ObservedCheck
    original_show = dsh_webview.show_webview
    def show(**kwargs):
        original_show(**kwargs)
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QLabel, QPushButton
        import dsh_install_ui as manager
        dsh_webview._window.resize(1440, 900)
        dsh_webview._window.move(12000, 12000)
        def tick():
            nonlocal handled
            command_file = folder / 'command.json'
            if not command_file.exists():
                return
            command = json.loads(command_file.read_text(encoding='utf8'))
            if command['id'] == handled:
                return
            handled = command['id']
            value = {'id': handled}
            try:
                window = manager._WINDOW
                action = command['action']
                if action in ('check', 'cancel'):
                    wanted = '检查更新' if action == 'check' else '取消操作'
                    button = next(button for button in window.findChildren(QPushButton) if button.text() == wanted)
                    assert button.isEnabled(), wanted
                    button.click()
                elif action == 'close-manager':
                    window.close()
                elif action == 'quit':
                    if window:
                        window.close()
                    QApplication.instance().quit()
                elif action != 'snapshot':
                    raise ValueError(action)
                window = manager._WINDOW
                value.update(ok=True, manager=bool(window), identity=id(window) if window else None,
                    labels=[label.text() for label in window.findChildren(QLabel)] if window else [],
                    buttons=[{'text': button.text(), 'visible': button.isVisible(), 'enabled': button.isEnabled()}
                        for button in window.findChildren(QPushButton)] if window else [],
                    release=captured['check'].snapshot() if 'check' in captured else None,
                    houImported='hou' in sys.modules)
                if command.get('capture') and window:
                    window.grab().save(str(folder / command['capture']))
            except Exception as error:
                value.update(ok=False, error=repr(error))
            write(folder / 'result.json', value)
        timer = QTimer(dsh_webview._window)
        timer.timeout.connect(tick)
        timer.start(30)
        dsh_webview._window._updates_test_timer = timer
    dsh_webview.show_webview = show
    desktop.run(config)


def main():
    reexec_unpacked_test_cli()
    from dsh_runtime_compat import preferred_cached_bin
    from dsh_workbench import desktop_environment
    parser = argparse.ArgumentParser()
    parser.add_argument('--hfs', type=Path, default=Path('D:/houdini'))
    parser.add_argument('--capture-only', action='store_true', help='Capture the confirmed update and native manager without repeating failure/cancel scenarios')
    args = parser.parse_args()
    folder = Path(tempfile.mkdtemp(prefix='workbench-updates-', dir=ROOT / 'tools/out'))
    print('Isolated update verification: ' + str(folder), flush=True)
    node, binary = shutil.which('node'), preferred_cached_bin(ROOT / '.npm-cache')
    assert node and binary, 'Build the exact preferred DSH runtime first'
    python = next(args.hfs.glob('python3*/python.exe'))
    env = isolated_environment(folder / 'environment', gui=True)
    subprocess.run([node, str(ROOT / 'tools/tests/prepare-shared-host-fixture.mjs'), str(binary), env['DSH_HOME'], str(ROOT)],
                   env=env, cwd=ROOT, check=True, timeout=60)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        debug = probe.getsockname()[1]
    previous = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(env)
        desktop_env = desktop_environment(args.hfs, python, debug)
    finally:
        os.environ.clear()
        os.environ.update(previous)
    workspace = folder / 'project'
    workspace.mkdir()
    config = {'root': str(folder / 'desktop'), 'installation': str(ROOT), 'plugin': str(ROOT),
        'node': node, 'binary': str(binary), 'home': env['DSH_HOME'], 'hfs': str(args.hfs),
        'python': str(python), 'debugPort': debug, 'initialWorkspace': str(workspace)}
    write(folder / 'config.json', config)
    write(folder / 'query.json', {'kind': 'new', 'ready': False})
    spec = importlib.util.spec_from_file_location('owned_gui_job_fixture', ROOT / 'tools/tests/dsh-source-webview.test.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    job = module.GuiProcessJob()
    output = (folder / 'desktop.log').open('wb')
    process = subprocess.Popen([str(python), '-B', str(Path(__file__).resolve()), '--worker', str(folder / 'config.json')],
        cwd=args.hfs / 'bin', env=desktop_env, stdout=output, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
    job.assign(process)
    observed = []
    def command(action='snapshot', capture=None):
        ident = uuid.uuid4().hex
        write(folder / 'command.json', {'id': ident, 'action': action, 'capture': capture})
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = folder / 'result.json'
            if result.exists():
                value = json.loads(result.read_text(encoding='utf8'))
                if value['id'] == ident:
                    assert value['ok'], value
                    return value
            assert process.poll() is None, 'desktop exited: ' + str(folder / 'desktop.log')
            time.sleep(.05)
        raise AssertionError('Qt fixture command timed out: ' + action)
    def browser(action):
        result = subprocess.run([node, str(ROOT / 'tools/tests/workbench-updates-browser.mjs'), str(debug), action,
            str(folder), str(workspace)], cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf8', errors='replace', timeout=65,
            creationflags=subprocess.CREATE_NO_WINDOW)
        (folder / (action + '.browser.log')).write_text(result.stdout + result.stderr, encoding='utf8')
        assert result.returncode == 0, result.stdout + result.stderr
    try:
        browser('hidden')
        hidden = command()
        assert hidden['release']['checking'] and not hidden['manager'] and not hidden['houImported']
        record = json.loads((folder / 'desktop/workbench/desktop.json').read_text(encoding='utf8'))
        def request_update(payload, token):
            request = urllib.request.Request('http://127.0.0.1:' + str(record['controlPort']) + '/updates/open',
                data=json.dumps(payload).encode(), method='POST', headers={'Authorization': 'Bearer ' + token,
                    'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.load(response)
        try:
            request_update({}, '0' * 64)
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError('update manager accepted a wrong token')
        assert request_update({'install': True}, record['token'])['ok'] is False
        assert not command()['manager'], 'rejected update requests opened a manager'
        write(folder / 'query.json', {'kind': 'new', 'ready': True})
        browser('open')
        for _ in range(100):
            opened = command(capture='manager-new.png')
            if opened['manager'] and '查看新版 99.0.0' in [button['text'] for button in opened['buttons'] if button['visible']]:
                break
            time.sleep(.05)
        assert opened['manager'] and any('99.0.0' in label for label in opened['labels']), opened
        assert not opened['houImported'], 'standalone version management imported HOM'
        if args.capture_only:
            observed = [hidden, opened]
            print('PASS confirmed update and shared native manager visual capture', flush=True)
            return
        browser('reopen')
        repeated = command()
        assert repeated['identity'] == opened['identity'], 'repeated update clicks created another version manager'
        write(folder / 'query.json', {'kind': 'failure', 'ready': True})
        command('check')
        for _ in range(100):
            failed = command(capture='manager-offline.png')
            if failed['release']['error'] and not failed['release']['checking'] and any('失败' in label or '无法' in label for label in failed['labels']):
                break
            time.sleep(.05)
        assert failed['release']['error'] and not any(button['visible'] and button['text'].startswith('查看新版') for button in failed['buttons']), failed
        browser('offline')
        write(folder / 'query.json', {'kind': 'new', 'ready': False})
        command('check')
        command('cancel')
        write(folder / 'query.json', {'kind': 'new', 'ready': True})
        for _ in range(100):
            cancelled = command(capture='manager-cancelled.png')
            if not cancelled['release']['checking'] and any('操作已取消' in label for label in cancelled['labels']):
                break
            time.sleep(.05)
        assert any('操作已取消' in label for label in cancelled['labels']), cancelled
        assert not any(button['visible'] and button['text'].startswith('查看新版') for button in cancelled['buttons']), cancelled
        browser('preserved')
        observed = [hidden, opened, repeated, failed, cancelled]
        command('quit')
        assert process.wait(timeout=30) == 0
    finally:
        if process.poll() is None:
            try:
                command('quit')
                process.wait(timeout=20)
            except Exception:
                pass  # The owned Job remains the final cleanup boundary.
        cleanup = job.close()
        process.wait(timeout=10)
        output.close()
        write(folder / 'report.json', {'observations': observed, 'exitCode': process.poll(), 'cleanup': cleanup})
    print('PASS real DSH/Qt discovery, shared manager, explicit failure/cancel, selected task/preset/cwd and document/draft preservation', flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        worker(Path(sys.argv[2]))
    else:
        main()
