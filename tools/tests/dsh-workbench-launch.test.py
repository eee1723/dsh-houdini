from pathlib import Path
import importlib.util
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli
from dsh_workbench import desktop_environment, running, control
from dsh_deployment import _process_started, atomic_json
from dsh_houdini_installations import discover, installation


def gui_probe():
    import hou
    from hutil.Qt import QtCore
    root = Path(os.environ['DSH_WORKBENCH_TEST_ROOT'])
    (root / ('gui-ready-' + str(os.getpid()))).touch()
    hou.qt.mainWindow().move(12000, 12000)
    timer = QtCore.QTimer(hou.qt.mainWindow())
    def tick():
        clear = root / ('clear-' + str(os.getpid()))
        close = root / ('close-' + str(os.getpid()))
        save = root / ('save-' + str(os.getpid()) + '.json')
        if save.exists():
            filename = Path(json.loads(save.read_text(encoding='utf-8'))['path'])
            save.unlink()
            filename.parent.mkdir(parents=True, exist_ok=True)
            hou.node('/obj').createNode('geo', 'native_user_geometry')
            hou.hipFile.save(filename.as_posix())
            import dsh_scene_recovery
            atomic_json(root / ('saved-' + str(os.getpid()) + '.json'), dsh_scene_recovery.facts())
        if clear.exists():
            clear.unlink()
            hou.hipFile.clear(suppress_save_prompt=True)
        if close.exists():
            timer.stop()
            hou.hipFile.clear(suppress_save_prompt=True)
            hou.qt.mainWindow().close()
    timer.timeout.connect(tick)
    timer.start(100)
    hou.session._workbench_launch_probe = timer


def default_runtime_cache():
    """The prepared runtime identity comes from the runtime-fix manifest, never a
    hardcoded cache directory name. An old cache lacks deleteEmpty and silently
    keeps empty scratch workspace rows."""
    import subprocess as _subprocess
    probe = ("import('./tools/runtime-fix-inputs.mjs').then(async m=>{const fs=await import('node:fs');"
             "const manifest=JSON.parse(fs.readFileSync('deployment/dsh-runtime-fixes/manifest.json','utf8'));"
             "process.stdout.write(m.runtimeFixKey(m.runtimeFixInputs(process.cwd(),manifest)));})")
    result = _subprocess.run([shutil.which('node'), '-e', probe], cwd=ROOT, capture_output=True, text=True,
                             timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('无法计算 DSH 运行时缓存标识：' + result.stderr[-2000:])
    cache = ROOT / '.npm-cache/_npx' / ('dsh-houdini-' + result.stdout.strip())
    if not (cache / 'node_modules/@deepseek-ai/dsh/lib/bin.js').is_file():
        raise RuntimeError('DSH 运行时缓存尚未准备，请先运行 npm run runtime:prepare：' + str(cache))
    return cache


def main():
    reexec_unpacked_test_cli()
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-cache', type=Path, default=None)
    parser.add_argument('--standalone-only', action='store_true')
    # Native cold initialization may exceed the ordinary RPC/UI waits;
    # keep its budget independent, without changing product startup behavior.
    parser.add_argument('--native-startup-timeout', type=float, default=240, help='Native Houdini cold-start budget only; other waits are unchanged')
    parser.add_argument('--profile-native-startup', action='store_true', help='Profile only owned native Houdini startup and sample its real Qt waiting feedback')
    parser.add_argument('--hfs', help='Use this installed Houdini for both Qt desktop and native project windows')
    args = parser.parse_args()
    if not math.isfinite(args.native_startup_timeout) or args.native_startup_timeout <= 0:
        parser.error('--native-startup-timeout must be a finite positive number')
    installed = discover(args.hfs)
    assert installed, 'This GUI check needs an installed Houdini'
    desktop_installation = installation(args.hfs) if args.hfs else installed[0]
    folder = Path(tempfile.mkdtemp(prefix='workbench-launch-', dir=ROOT / 'tools/out'))
    env = isolated_environment(folder / 'environment', gui=True)
    env.update(DSH_WORKBENCH_TEST_ROOT=str(folder), DSH_HOUDINI_RECOVERY_ROOT=str(folder / 'recovery'))
    binary = (args.runtime_cache or default_runtime_cache()).resolve() / 'node_modules/@deepseek-ai/dsh/lib/bin.js'
    node = shutil.which('node')
    subprocess.run([node, str(ROOT / 'tools/tests/prepare-shared-host-fixture.mjs'), str(binary), env['DSH_HOME'], str(ROOT)],
                   cwd=ROOT, env=env, check=True, timeout=60)
    (Path(env['DSH_HOME']) / 'profiles/web/cordis.patch.yml').write_text(json.dumps([{'insert': [{
        'id': 'workbench-fixture', 'name': (ROOT / 'tools/tests/workbench-dsh-fixture.mjs').as_uri()}]}]), encoding='utf-8')
    for version, python in [('21.0', '3.11'), ('22.0', '3.13')]:
        prefs = Path(env['HOUDINI_USER_PREF_DIR'].replace('__HVER__', version))
        hook = prefs / ('python' + python + 'libs/uiready.py')
        hook.parent.mkdir(parents=True)
        hook.write_text(("import os\nfrom pathlib import Path\nPath(os.environ['DSH_WORKBENCH_TEST_ROOT'],'uiready-entered-'+str(os.getpid())).touch()\n" if args.profile_native_startup else "") + "import importlib.util\nspec=importlib.util.spec_from_file_location('launch_probe'," + repr(str(Path(__file__).resolve())) + ")\nmodule=importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\nmodule.gui_probe()\n", encoding='utf-8')
        save_hook = prefs / 'scripts/afterscenesave.py'
        save_hook.parent.mkdir(parents=True, exist_ok=True)
        save_hook.write_text("import os\nfrom pathlib import Path\nPath(os.environ['DSH_WORKBENCH_TEST_ROOT'],'save-hook-'+str(os.getpid())).write_text(str(kwargs.get('success')))\n", encoding='utf-8')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        debug_port = probe.getsockname()[1]
    config = {'root': str(folder / 'desktop'), 'installation': str(ROOT), 'plugin': str(ROOT), 'node': node,
        'binary': str(binary), 'home': env['DSH_HOME'], 'hfs': desktop_installation['hfs'],
        'python': desktop_installation['python'], 'debugPort': debug_port}
    (folder / 'config.json').write_text(json.dumps(config), encoding='utf-8')
    previous = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    output = (folder / 'desktop.log').open('wb')
    driver = ROOT / 'tools/tests/workbench-desktop-driver.py'
    if args.profile_native_startup:
        # Test-only instrumentation around the real driver and production launch.
        # Profiles and GUI samples stay in this fixture; no HFS/prefs are changed.
        wrapper = folder / 'profile-desktop-driver.py'
        wrapper.write_text("""import json, os, runpy, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, %r)
import dsh_workbench_projects as projects
folder = Path(os.environ['DSH_WORKBENCH_TEST_ROOT'])
original_spawn, original_dialog = subprocess.Popen, projects.show_project_dialog
samples, dialog_serial = [], 0
def profiled_spawn(args, **kwargs):
    if str(args[0]).lower().endswith('houdini.exe'):
        ticket = Path(kwargs['env']['DSH_HOUDINI_LAUNCH_TICKET'])
        args = [args[0], '-profile-startup=' + str(ticket.with_suffix('.hperf')), *args[1:]]
    return original_spawn(args, **kwargs)
def sampled_dialog(*args, **kwargs):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QLabel, QPushButton
    global dialog_serial
    dialog = original_dialog(*args, **kwargs)
    dialog_serial += 1
    serial, started, seen = dialog_serial, time.monotonic(), set()
    timer = QTimer(dialog)
    def sample():
        elapsed = time.monotonic() - started
        slot = int(elapsed // 10)
        if elapsed < 50 or slot in seen or len(seen) >= 3:
            return
        seen.add(slot)
        samples.append({'dialog': serial, 'elapsedSeconds': round(elapsed, 3), 'observedAt': time.time(),
            'visible': dialog.isVisible(), 'enabled': dialog.isEnabled(),
            'labels': [label.text() for label in dialog.findChildren(QLabel)],
            'buttons': [{'text': button.text(), 'enabled': button.isEnabled()} for button in dialog.findChildren(QPushButton)]})
        (folder / 'native-progress-samples.json').write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding='utf-8')
    timer.timeout.connect(sample)
    dialog.finished.connect(lambda *_: timer.stop())
    timer.start(1000)
    return dialog
subprocess.Popen = profiled_spawn
projects.show_project_dialog = sampled_dialog
sys.argv = [%r, %r]
runpy.run_path(sys.argv[0], run_name='__main__')
""" % (str(ROOT / 'houdini/python3.11libs'), str(driver), str(folder / 'config.json')), encoding='utf-8')
        driver = wrapper
    desktop = subprocess.Popen([config['python'], str(driver), str(folder / 'config.json')],
        cwd=str(Path(config['hfs']) / 'bin'), env=desktop_environment(config['hfs'], config['python'], debug_port),
        stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    record = None
    native_timings = []
    test_result = None
    project_temp = tempfile.TemporaryDirectory(prefix='dsh-new-project-')
    def wait(predicate, seconds=120):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            assert desktop.poll() is None, 'test desktop stopped: ' + str(folder)
            time.sleep(.1)
        raise AssertionError('Timed out: ' + str(folder))
    def browser(action, label, status='', session='', executor=''):
        result = subprocess.run([node, str(ROOT / 'tools/tests/workbench-project-browser.mjs'), str(debug_port), action,
            str(folder / label), status, session, executor], env=env, cwd=ROOT, capture_output=True, text=True, errors='replace', timeout=35,
            creationflags=subprocess.CREATE_NO_WINDOW)
        (folder / (label + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
        result.check_returncode()
        return json.loads((folder / (label + '.json')).read_text(encoding='utf-8'))
    def receipts():
        return [json.loads(filename.read_text(encoding='utf-8')) for filename in (Path(config['root']) / 'workbench/launches').glob('*.json')]
    def launch(action, version, label, hip=None):
        known = {item['id'] for item in receipts()}
        (folder / 'dialog-choice.json').write_text(json.dumps({'hfs': str(Path(version)), **({'hip': str(hip)} if hip else {})}), encoding='utf-8')
        entry = browser(action, label + '-entry')
        try:
            first_seen = wait(lambda: next((item for item in receipts() if item['id'] not in known), None), 15)
            timing = {'id': first_seen['id'], 'label': label, 'firstObservedAt': time.time(), 'createdAt': first_seen['createdAt'], 'budgetSeconds': args.native_startup_timeout}
            native_timings.append(timing)
        except AssertionError as error:
            raise AssertionError(entry.get('afterText', str(error))) from error
        value = wait(lambda: next((item for item in receipts() if item['id'] not in known and item['phase'] in ('ready', 'failed')), None), args.native_startup_timeout)
        timing['readyObservedAt'] = time.time()
        timing['readyElapsedSeconds'] = round(timing['readyObservedAt'] - timing['createdAt'], 3)
        assert value['phase'] == 'ready', value
        assert (folder / ('gui-ready-' + str(value['pid']))).is_file(), 'the private hook must coexist with the original GUI startup hook'
        selected = browser('state', label, 'ready', value['result']['sessionId'], value['result']['executorId'])
        timing['consumerConfirmedAt'] = time.time()
        timing['consumerElapsedSeconds'] = round(timing['consumerConfirmedAt'] - timing['createdAt'], 3)
        assert selected['selectedTarget']['executor_id'] == value['result']['executorId']
        assert selected['selectedTarget']['runtime_id'] == value['result']['selectedTarget']['runtime_id']
        assert len([item for item in receipts() if item['id'] not in known]) == 1, 'double submit started multiple Houdini processes'
        return value, selected
    def command(session, tool=None, arguments=None, action=None):
        identifier = uuid.uuid4().hex
        temporary = folder / 'command.tmp'
        temporary.write_text(json.dumps({'id': identifier, 'sessionId': session, 'tool': tool, 'args': arguments, 'action': action}), encoding='utf-8')
        temporary.replace(folder / 'command.json')
        def result():
            try:
                value = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
                return value if value['id'] == identifier else None
            except (FileNotFoundError, json.JSONDecodeError):
                return None
        value = wait(result, 50)
        assert value['ok'], value
        return value
    def choose(session, endpoint, label):
        control(record, 'show', {'sessionId': session})
        browser('snapshot', label + '-before', session=session)
        return browser('select-target', label, executor=endpoint['executor_id'])
    def native_save(ticket, filename):
        atomic_json(folder / ('save-' + str(ticket['pid']) + '.json'), {'path': str(filename)})
        marker = folder / ('saved-' + str(ticket['pid']) + '.json')
        wait(marker.exists)
        assert (folder / ('save-hook-' + str(ticket['pid']))).read_text() == 'True', 'the original save hook must coexist'
        wait(lambda: Path(next(item for item in candidates() if item['pid'] == ticket['pid'])['hip_path']).resolve() == filename.resolve())
        return next(item for item in candidates() if item['pid'] == ticket['pid'])
    def candidates():
        return [json.loads(file.read_text(encoding='utf-8')) for file in Path(config['root'], 'workbench/executors/endpoints').glob('*.json')]
    def close_houdini(ticket):
        (folder / ('close-' + str(ticket['pid']))).touch()
        wait(lambda: _process_started(ticket['pid']) != ticket['processStarted'], 35)
    try:
        record = wait(lambda: running(config['root']))
        assert not receipts(), 'standalone workspace boot must not start Houdini'
        initial = browser('snapshot', 'standalone-start')
        assert initial['entry'] or initial.get('selection'), 'native workbench must expose the compact project entry or its selected conversation'
        if initial.get('selection'):
            assert Path(initial['selection']['cwd']).resolve() != ROOT
        if args.standalone_only:
            test_result = {'ok': True, 'standaloneOnly': True}
            print('PASS standalone native workbench and user-directory isolation: ' + str(folder), flush=True)
            return
        hfs = desktop_installation['hfs']
        series = desktop_installation['series']
        discussion_ui = browser('new-chat', 'discussion-start')
        discussion = discussion_ui['selection']['sessionId']
        discussion_cwd = discussion_ui['selection']['cwd']
        talked = command(discussion)
        assert any(event['type'] == 'user/message' and event['data']['source']['kind'] == 'user' for event in talked['events'])
        before = command(discussion, action='idle')
        first, first_ui = launch('new', hfs, 'native-new-first')
        first_session = first['result']['sessionId']
        assert first_session == discussion, 'new project from an unbound discussion keeps that exact native conversation'
        assert first_ui['selection']['cwd'] == discussion_cwd, 'project selection does not move conversation file scope'
        assert first_ui['selectedTarget']['hip_is_new'] is True
        assert command(first_session, action='idle')['turns'] == before['turns'], 'project launch must not start a hidden model turn'
        inspected = command(first_session, 'houdini_inspect', {'code': '__result__={"version":hou.applicationVersionString(),"new":hou.hipFile.isNewFile()}' })['value']
        assert inspected['ok'] and inspected['execution']['executor_id'] == first['result']['executorId'], inspected
        assert inspected['result']['version'].startswith(series), inspected
        first_path = Path(project_temp.name) / 'first' / '原生保存.hip'
        first_endpoint = native_save(first, first_path)
        selected_first = choose(first_session, first_endpoint, 'native-save-explicit-reselect')
        assert selected_first['selection']['cwd'] == discussion_cwd
        assert Path(selected_first['selectedTarget']['hip_path']).resolve() == first_path.resolve()
        second, second_ui = launch('new', hfs, 'native-new-second')
        second_session = second['result']['sessionId']
        assert second['pid'] != first['pid'] and second_session != first_session, 'a bound conversation is not silently repointed by default new-project navigation'
        assert second_ui['selectedTarget']['hip_is_new'] is True
        second_cwd = second_ui['selection']['cwd']
        second_path = Path(project_temp.name) / 'second' / '另一个工程.hip'
        second_endpoint = native_save(second, second_path)
        choose(second_session, second_endpoint, 'second-native-save-reselect')
        switched = choose(first_session, second_endpoint, 'old-discussion-chooses-second-window')
        assert switched['selection']['sessionId'] == first_session and switched['selection']['cwd'] == discussion_cwd
        observed = command(first_session, 'houdini_inspect', {'code': '__result__=hou.hipFile.path()'})['value']
        assert observed['ok'] and Path(observed['result']).resolve() == second_path.resolve(), observed
        assert observed['execution']['executor_id'] == second_endpoint['executor_id']
        cleared = browser('clear-target', 'explicit-clear')
        assert cleared['selectedTarget'] is None and cleared['selection']['cwd'] == discussion_cwd
        assert command(first_session, action='targets')['state']['status'] == 'unbound'
        count = len(receipts())
        (folder / 'dialog-choice.json').write_text(json.dumps({'cancel': True}), encoding='utf-8')
        browser('new', 'cancel-entry')
        wait(lambda: (folder / 'dialog-cancelled').exists())
        assert len(receipts()) == count, 'cancel before native launch creates no process or request'
        # Bind again so default Open creates a fresh native conversation instead
        # of reusing the unbound discussion. No scene-history matching is used.
        choose(first_session, second_endpoint, 'before-file-open')
        close_houdini(first)
        opened, opened_ui = launch('open', hfs, 'native-open-saved-file', hip=first_path)
        opened_session = opened['result']['sessionId']
        assert opened_session not in (first_session, second_session)
        assert Path(opened_ui['selectedTarget']['hip_path']).resolve() == first_path.resolve()
        assert Path(opened_ui['selection']['cwd']).resolve() == first_path.parent.resolve(), 'a genuinely new conversation starts in the opened project workspace'
        new_endpoint = next(item for item in candidates() if item['pid'] == opened['pid'])
        rebound = choose(first_session, new_endpoint, 'executed-discussion-chooses-opened-file')
        assert rebound['selection']['cwd'] == discussion_cwd, 'manual retarget of an executed discussion preserves its native workspace'
        count = len(receipts())
        (folder / 'dialog-finished').unlink(missing_ok=True)
        (folder / 'dialog-choice.json').write_text(json.dumps({'hfs': hfs, 'hip': str(first_path)}), encoding='utf-8')
        browser('open', 'reuse-already-open-file-entry')
        wait(lambda: (folder / 'dialog-finished').is_file(), 15)
        assert (folder / 'dialog-finished').read_text() == '1' and len(receipts()) == count, 'opening an already live HIP reuses its actual Houdini window'
        reused = browser('new-target', 'reuse-already-open-file', 'ready', first_session, new_endpoint['executor_id'])
        assert reused['selectedTarget']['runtime_id'] == new_endpoint['runtime_id']
        close_houdini(opened)
        control(record, 'show', {'sessionId': opened_session})
        browser('state', 'closed-saved-file', 'offline', opened_session)
        reopened, reopened_ui = launch('reopen', hfs, 'explicit-reopen-associated-file')
        assert reopened['result']['sessionId'] == opened_session and reopened['pid'] != opened['pid']
        assert Path(reopened_ui['selectedTarget']['hip_path']).resolve() == first_path.resolve()
        (folder / ('clear-' + str(reopened['pid']))).touch()
        browser('state', 'changed-scene-awaits-selection', 'changed', opened_session)
        fresh = next(item for item in candidates() if item['pid'] == reopened['pid'])
        changed = choose(opened_session, fresh, 'changed-scene-explicit-selection')
        assert changed['selectedTarget']['hip_is_new'] is True
        assert control(record, 'status')['record']['pid'] == desktop.pid
        test_result = {'ok': True, 'houdini': desktop_installation['version'],
            'nativeNew': True, 'nativeOpen': True, 'explicitReopen': True, 'selectedExactInstance': True,
            'manualRetargetPreservesCwd': True, 'clearStaysUnbound': True, 'cancelAndDoubleClick': True,
            'reuseLiveFileWindow': True, 'sceneChangeRequiresSelection': True}
        atomic_json(folder / 'result.json', test_result)
        print('PASS ' + series + ' actual workbench native New/Open/Reopen, exact selected targets, explicit retarget with unchanged cwd, clear, cancel/double launch, live-file window reuse and changed-scene selection: ' + str(folder), flush=True)
    finally:
        failure = sys.exc_info()[1]
        for item in receipts():
            if item.get('pid') and _process_started(item['pid']) == item.get('processStarted'):
                (folder / ('close-' + str(item['pid']))).touch()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline and any(item.get('pid') and _process_started(item['pid']) == item.get('processStarted') for item in receipts()):
            time.sleep(.2)
        houdini_still_active = any(item.get('pid') and _process_started(item['pid']) == item.get('processStarted') for item in receipts())
        crashed = any('Fatal error' in log.read_text(encoding='utf-8', errors='replace')
                      for log in (Path(config['root']) / 'workbench/launches').glob('*.log'))
        if record:
            spec = importlib.util.spec_from_file_location('desktop_fixture', ROOT / 'tools/tests/dsh-workbench.test.py')
            fixture = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fixture)
            user, windows = fixture.windows(record['pid'])
            for window in windows:
                user.PostMessageW(window, 0x0010, 0, 0)
            try:
                desktop.wait(timeout=20)
            except subprocess.TimeoutExpired:
                desktop.terminate()
                desktop.wait(timeout=10)
        output.close()
        for timing in native_timings:
            ticket_path = Path(config['root']) / 'workbench/launches' / (timing['id'] + '.json')
            ticket = json.loads(ticket_path.read_text(encoding='utf-8'))
            timing.update(pid=ticket.get('pid'), phase=ticket['phase'])
            for key, name in [('guiHookEnteredAt', 'uiready-entered-'), ('guiReadyAt', 'gui-ready-')]:
                marker = folder / (name + str(ticket.get('pid')))
                if marker.is_file():
                    timing[key] = marker.stat().st_mtime
                    timing[key.replace('At', 'ElapsedSeconds')] = round(timing[key] - timing['createdAt'], 3)
            if ticket.get('callback'):
                timing['attachCallbackReceived'] = True
            profile = ticket_path.with_suffix('.hperf')
            if profile.is_file():
                timing.update(profile=str(profile), profileBytes=profile.stat().st_size)
        # Command replies share result.json while running. Only the completed
        # scenario can mark the final report successful.
        final_result = dict(test_result or {'ok': False})
        if failure is not None:
            final_result.update(ok=False, error=type(failure).__name__ + ': ' + str(failure))
        cleanup_failures = []
        if houdini_still_active:
            cleanup_failures.append('owned test Houdini did not exit')
        if crashed:
            cleanup_failures.append('Houdini crashed')
        if cleanup_failures:
            final_result.update(ok=False, cleanupErrors=cleanup_failures)
        final_result.update(nativeStartupTimings=native_timings, nativeStartupBudgetSeconds=args.native_startup_timeout,
                            startupProfiling=args.profile_native_startup, ownedHoudiniStillActive=houdini_still_active,
                            desktopExited=desktop.poll() is not None)
        samples = folder / 'native-progress-samples.json'
        if samples.is_file():
            final_result['nativeProgressSamples'] = json.loads(samples.read_text(encoding='utf-8'))
        atomic_json(folder / 'result.json', final_result)
        project_temp.cleanup()
        os.environ.clear()
        os.environ.update(previous)
        assert not houdini_still_active, 'owned test Houdini did not exit'
        assert not crashed, 'Houdini crash is not a normal exit pass'


if __name__ == '__main__':
    main()
