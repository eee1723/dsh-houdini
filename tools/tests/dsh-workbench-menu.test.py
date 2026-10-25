from pathlib import Path
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli
from dsh_workbench import running, control, close_when_idle, ensure
from dsh_deployment import read_json
from dsh_runtime_compat import preferred_cached_bin


def start_gui_probe():
    import hou
    from hutil.Qt import QtCore
    import dsh_launcher
    import dsh_workbench_client
    import dsh_bridge
    import dsh_workbench
    from dsh_executor_registry import active_registration
    folder = Path(os.environ['DSH_WORKBENCH_MENU_FIXTURE'])
    (folder / 'inherited-qt-environment.json').write_text(json.dumps({key: value for key, value in os.environ.items()
        if key.upper().startswith(('QT_', 'QTWEBENGINE_', 'QML', 'PYSIDE', 'SHIBOKEN'))}), encoding='utf-8')
    source_config = dsh_workbench_client.source_config
    dsh_workbench_client.source_config = lambda launcher: {**source_config(launcher), 'debugPort': int(os.environ['DSH_WORKBENCH_MENU_DEBUG_PORT'])}
    # A historical marker can name a PID now owned by an unrelated live Python
    # process. Exercise the actual menu path with the old, birth-time-free format.
    legacy_marker = folder / 'legacy-runtime.json'
    legacy_marker.write_text(json.dumps({
        'pid': int(os.environ['DSH_WORKBENCH_MENU_LEGACY_PID']),
        'source': 'cached-cli', 'bin': os.environ['DSH_HOUDINI_DSH_BIN'],
        'startedAt': '2026-10-07T00:00:00+0800',
    }), encoding='utf-8')
    legacy_marker_bytes = legacy_marker.read_bytes()
    dsh_launcher.FRONTEND_RUNTIME_STATE = str(legacy_marker)
    dsh_launcher._FALLBACK_WORKSPACE = str(folder / 'projects')
    node = hou.node('/obj').createNode('geo', 'maintenance_preserved')
    hou.hipFile.save(str(folder / 'maintenance.hip'))
    node.setSelected(True)
    hou.setFrame(7)
    hou.qt.mainWindow().move(12000, 12000)
    state = {'reported': False, 'reloading': False}
    original_control = dsh_workbench.control
    def observed_control(record, action, *args, **kwargs):
        result = original_control(record, action, *args, **kwargs)
        if action == 'open':
            state['session_id'] = result['sessionId']
        return result
    dsh_workbench.control = observed_control
    dsh_launcher.open_workspace()
    timer = QtCore.QTimer(hou.qt.mainWindow())

    def tick():
        if (folder / 'close-houdini').exists():
            import faulthandler
            (folder / 'exit-requested').touch()
            faulthandler.dump_traceback_later(15)
            timer.stop()
            hou.hipFile.clear(suppress_save_prompt=True)
            hou.qt.mainWindow().close()
            return
        if state['reported'] and not state['reloading'] and (folder / 'reload').exists():
            state.update(reloading=True, reported=False)
            dsh_workbench_client.open_workspace(dsh_launcher, reload=True)
            return
        if dsh_workbench_client._BUSY or state['reported']:
            return
        try:
            if dsh_launcher._LAST_STARTUP_FAILURE:
                raise RuntimeError(dsh_launcher._LAST_STARTUP_FAILURE)
            assert legacy_marker.read_bytes() == legacy_marker_bytes, 'opening/reloading rewrote the historical marker'
            if not state.get('edited'):
                node.parm('tx').set(2)
                state['edited'] = True
            registration = active_registration()
            result = {'ok': True, 'sessionId': state['session_id'], 'executorId': registration.executor_id,
                      'pythonPrefix': sys.prefix, 'cwd': registration.scene['workspace_path'],
                      'runtimeId': dsh_bridge._RUNTIME_ID, 'reloaded': state['reloading'],
                      'scene': {'hip': hou.hipFile.path(), 'frame': hou.frame(), 'dirty': hou.hipFile.hasUnsavedChanges(),
                                'selected': [item.path() for item in hou.selectedNodes()], 'nodeId': node.sessionId()}}
        except Exception:
            result = {'ok': False, 'error': traceback.format_exc()}
        temporary = folder / 'gui-result.tmp'
        temporary.write_text(json.dumps(result), encoding='utf-8')
        temporary.replace(folder / 'gui-result.json')
        state['reported'] = True

    timer.timeout.connect(tick)
    timer.start(100)
    hou.session._workbench_menu_test_timer = timer


def main():
    reexec_unpacked_test_cli()
    executable = Path(sys.argv[1])
    version = '22.0' if '22' in executable.parent.parent.name else '21.0'
    folder = Path(tempfile.mkdtemp(prefix='workbench-menu-', dir=ROOT / 'tools/out'))
    env = isolated_environment(folder / 'environment', executable=executable, gui=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    binary = preferred_cached_bin(ROOT / '.npm-cache')
    if binary is None:
        raise RuntimeError('No prepared DSH runtime matching this plugin; run npm run runtime:prepare')
    node = shutil.which('node')
    env.update(DSH_HOUDINI_DSH_BIN=str(binary), DSH_WORKBENCH_MENU_FIXTURE=str(folder),
               DSH_WORKBENCH_MENU_LEGACY_PID=str(os.getpid()),
               DSH_HOUDINI_RECOVERY_ROOT=str(folder / 'recovery'), DSH_WORKBENCH_MENU_DEBUG_PORT=str(port))
    subprocess.run([node, str(ROOT / 'tools/tests/prepare-shared-host-fixture.mjs'), str(binary), env['DSH_HOME'], str(ROOT)],
                   cwd=ROOT, env=env, check=True, timeout=60)
    prefs = Path(env['HOUDINI_USER_PREF_DIR'].replace('__HVER__', version))
    hook = prefs / ('python3.13libs' if version == '22.0' else 'python3.11libs') / 'uiready.py'
    hook.parent.mkdir(parents=True)
    hook.write_text("import importlib.util\nspec=importlib.util.spec_from_file_location('workbench_menu_test'," + repr(str(Path(__file__).resolve())) + ")\nmodule=importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\nmodule.start_gui_probe()\n", encoding='utf-8')
    desktop_root = Path(env['DSH_HOME']) / 'houdini-workbench'
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    with (folder / 'houdini.log').open('wb') as output:
        gui = subprocess.Popen([str(executable), '-foreground', '-geometry=1200x800+12000+12000'], cwd=executable.parent,
            env=env, stdout=output, stderr=subprocess.STDOUT, startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
    desktop = None
    try:
        deadline = time.monotonic() + 150
        while not (folder / 'gui-result.json').exists():
            assert gui.poll() is None, 'GUI failed: ' + str(folder)
            assert time.monotonic() < deadline, 'Menu launch timed out: ' + str(folder)
            time.sleep(.1)
        value = json.loads((folder / 'gui-result.json').read_text(encoding='utf-8'))
        assert value['ok'], value
        assert value['scene']['dirty'], 'fixture must contain actual unsaved edits before reloading'
        desktop = running(desktop_root)
        assert desktop and desktop['pid'] != gui.pid
        before = control(desktop, 'status')
        subprocess.run([node, str(ROOT / 'tools/tests/workbench-browser.mjs'), str(port), value['sessionId'],
                        str(folder / 'actual-menu-workspace.png'), value['cwd'], '', 'maintenance-draft'], cwd=ROOT, env=env, check=True, timeout=30,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        (folder / 'reload').touch()
        deadline = time.monotonic() + 150
        while True:
            after = json.loads((folder / 'gui-result.json').read_text(encoding='utf-8'))
            assert after.get('ok'), after
            if after.get('reloaded'):
                break
            assert gui.poll() is None and time.monotonic() < deadline, 'reload timed out: ' + str(folder)
            time.sleep(.1)
        assert after['ok'] and after['scene'] == value['scene'], after
        assert after['runtimeId'] != value['runtimeId'] and after['executorId'] == value['executorId'], after
        desktop = running(desktop_root)
        loaded = control(desktop, 'status')
        assert loaded['record']['generation'] != before['record']['generation']
        assert loaded['context']['frontendPort'] == before['context']['frontendPort']
        assert loaded['context']['browserStorage'] == before['context']['browserStorage']
        subprocess.run([node, str(ROOT / 'tools/tests/workbench-browser.mjs'), str(port), value['sessionId'],
                        str(folder / 'after-runtime-reload.png'), value['cwd'], '', 'maintenance-restored'],
                       cwd=ROOT, env=env, check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        (folder / 'close-houdini').touch()
        gui.wait(timeout=30)
        assert gui.returncode == 0, 'Houdini did not exit normally: ' + str(gui.returncode) + ' ' + str(folder)
        assert 'Fatal error' not in (folder / 'houdini.log').read_text(encoding='utf-8', errors='replace'), 'Houdini crash is not a normal-exit pass'
        assert control(desktop, 'status')['record']['pid'] == desktop['pid'], 'the desktop died with its actual Houdini launcher'
        if '--cross-hfs' in sys.argv:
            cross_hfs = Path(sys.argv[sys.argv.index('--cross-hfs') + 1])
            config = read_json(desktop_root / 'workbench/launch-config.json')
            close_when_idle(config, desktop)
            config.update(hfs=str(cross_hfs), python=str(next(cross_hfs.glob('python3*/python.exe'))))
            previous = dict(os.environ)
            try:
                os.environ.clear()
                os.environ.update(env)
                crossed = ensure(config)
            finally:
                os.environ.clear()
                os.environ.update(previous)
            desktop = crossed['record']
            assert crossed['context']['frontendPort'] == loaded['context']['frontendPort']
            assert crossed['context']['browserStorage'] == loaded['context']['browserStorage']
            subprocess.run([node, str(ROOT / 'tools/tests/workbench-browser.mjs'), str(port), value['sessionId'],
                            str(folder / 'after-qt-change.png'), value['cwd'], '', 'maintenance-restored'],
                           cwd=ROOT, env=env, check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            (folder / 'cross-qt.json').write_text(json.dumps({'from': version, 'to': str(cross_hfs),
                'sessionId': value['sessionId'], 'frontendPort': crossed['context']['frontendPort'],
                'browserStorage': crossed['context']['browserStorage'], 'nativeDraftRetained': True}), encoding='utf-8')
            print('PASS same installation/data profile across Qt runtimes: ' + version + ' -> ' + str(cross_hfs), flush=True)
        print('PASS real Houdini ' + version + ' menu reload, native draft/selection and unsaved scene preservation, same executor/new runtime, independent desktop lifetime: ' + str(folder), flush=True)
    finally:
        if gui.poll() is None:
            gui.kill()
            gui.wait(timeout=15)
        desktop = running(desktop_root)
        if desktop:
            spec = importlib.util.spec_from_file_location('workbench_fixture', ROOT / 'tools/tests/dsh-workbench.test.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            user, windows = module.windows(desktop['pid'])
            for window in windows:
                user.PostMessageW(window, 0x0010, 0, 0)
            deadline = time.monotonic() + 10
            while running(desktop_root) and time.monotonic() < deadline:
                time.sleep(.1)
            assert running(desktop_root) is None, 'test desktop did not close'


if __name__ == '__main__':
    main()
