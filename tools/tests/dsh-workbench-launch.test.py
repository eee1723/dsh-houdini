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
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli
from dsh_workbench import desktop_environment, running, control
from dsh_deployment import _process_started


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
            (root / ('saved-' + str(os.getpid()) + '.json')).write_text(json.dumps(dsh_scene_recovery.facts()), encoding='utf-8')
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


def main():
    reexec_unpacked_test_cli()
    folder = Path(tempfile.mkdtemp(prefix='workbench-launch-', dir=ROOT / 'tools/out'))
    env = isolated_environment(folder / 'environment', gui=True)
    env.update(DSH_WORKBENCH_TEST_ROOT=str(folder), DSH_HOUDINI_RECOVERY_ROOT=str(folder / 'recovery'))
    binary = ROOT / '.npm-cache/_npx/dsh-houdini-4e2f5452611c/node_modules/@deepseek-ai/dsh/lib/bin.js'
    node = shutil.which('node')
    subprocess.run([node, str(ROOT / 'tools/tests/prepare-shared-host-fixture.mjs'), str(binary), env['DSH_HOME'], str(ROOT)],
                   cwd=ROOT, env=env, check=True, timeout=60)
    (Path(env['DSH_HOME']) / 'profiles/web/cordis.patch.yml').write_text(json.dumps([{'insert': [{
        'id': 'workbench-fixture', 'name': (ROOT / 'tools/tests/workbench-dsh-fixture.mjs').as_uri()}]}]), encoding='utf-8')
    for version, python in [('21.0', '3.11'), ('22.0', '3.13')]:
        prefs = Path(env['HOUDINI_USER_PREF_DIR'].replace('__HVER__', version))
        hook = prefs / ('python' + python + 'libs/uiready.py')
        hook.parent.mkdir(parents=True)
        hook.write_text("import importlib.util\nspec=importlib.util.spec_from_file_location('launch_probe'," + repr(str(Path(__file__).resolve())) + ")\nmodule=importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\nmodule.gui_probe()\n", encoding='utf-8')
        save_hook = prefs / 'scripts/afterscenesave.py'
        save_hook.parent.mkdir(parents=True, exist_ok=True)
        save_hook.write_text("import os\nfrom pathlib import Path\nPath(os.environ['DSH_WORKBENCH_TEST_ROOT'],'save-hook-'+str(os.getpid())).write_text(str(kwargs.get('success')))\n", encoding='utf-8')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        debug_port = probe.getsockname()[1]
    config = {'root': str(folder / 'desktop'), 'installation': str(ROOT), 'plugin': str(ROOT), 'node': node,
        'binary': str(binary), 'home': env['DSH_HOME'], 'hfs': 'D:/houdini', 'python': 'D:/houdini/python311/python.exe', 'debugPort': debug_port}
    (folder / 'config.json').write_text(json.dumps(config), encoding='utf-8')
    previous = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    output = (folder / 'desktop.log').open('wb')
    desktop = subprocess.Popen([config['python'], str(ROOT / 'tools/tests/workbench-desktop-driver.py'), str(folder / 'config.json')],
        cwd='D:/houdini/bin', env=desktop_environment(config['hfs'], config['python'], debug_port),
        stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    record = None
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
    def browser(action, label, status='', session=''):
        result = subprocess.run([node, str(ROOT / 'tools/tests/workbench-project-browser.mjs'), str(debug_port), action,
            str(folder / label), status, session], env=env, cwd=ROOT, capture_output=True, text=True, errors='replace', timeout=35,
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
            wait(lambda: any(item['id'] not in known for item in receipts()), 15)
        except AssertionError as error:
            raise AssertionError(entry.get('afterText', str(error))) from error
        value = wait(lambda: next((item for item in receipts() if item['id'] not in known and item['phase'] in ('ready', 'failed')), None))
        assert value['phase'] == 'ready', value
        assert (folder / ('gui-ready-' + str(value['pid']))).is_file(), 'the private hook must coexist with the original GUI startup hook'
        selected = browser('state', label, 'online', value['result']['sessionId'])
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
    def cold_resume():
        for installation,label in [('D:/houdini','cold-21'),('D:/Houdini22','cold-22')]:
            seed,_ = launch('new', installation, label + '-seed')
            new_session = seed['result']['sessionId']
            filename = Path(project_temp.name) / label / '原生保存.hip'
            (folder / ('save-' + str(seed['pid']) + '.json')).write_text(json.dumps({'path':str(filename)}), encoding='utf-8')
            saved_marker = folder / ('saved-' + str(seed['pid']) + '.json')
            wait(saved_marker.exists)
            seed_facts = json.loads(saved_marker.read_text(encoding='utf-8'))
            assert (folder / ('save-hook-' + str(seed['pid']))).read_text() == 'True', 'the original save hook must still execute'
            saved_scene = seed_facts['scene_id']
            wait(lambda:(folder / 'recovery/checkpoints' / (seed_facts['checkpoint_id'] + '.json')).is_file())
            command(new_session, action='beforeStep')
            browser('state', label + '-saved', 'online', new_session)
            saved_bytes = filename.read_bytes()
            (folder / ('close-' + str(seed['pid']))).touch()
            wait(lambda: _process_started(seed['pid']) != seed['processStarted'], 35)
            cold, _ = launch('reopen', installation, label + '-open')
            assert cold['result']['sessionId'] == new_session
            checked = command(new_session, 'houdini_inspect', {'code': '__result__=scene_info()'})['value']
            assert checked['ok'] and checked['execution']['scene_recovery']['scene_id'] == saved_scene, checked
            unsaved = command(new_session, 'houdini_exec', {'code': "__result__=tab_create('/obj','geo',name='unsaved_progress').path()"})['value']
            assert unsaved['ok'], unsaved
            (folder / ('close-' + str(cold['pid']))).touch()
            wait(lambda: _process_started(cold['pid']) != cold['processStarted'], 35)
            assert filename.read_bytes() == saved_bytes, 'closing without saving must not invent a checkpoint'
            control(record, 'show', {'sessionId': new_session})
            resumed, _ = launch('reopen', installation, label + '-resume')
            assert resumed['result']['sessionId'] == new_session
            observed = command(new_session, 'houdini_inspect', {'code': "__result__=hou.node('/obj/unsaved_progress') is None"})['value']
            assert observed['ok'] and observed['result'] is True, observed
            assert observed['execution']['scene_recovery']['scene_id'] == saved_scene, observed
            foreign = command(new_session, 'houdini_exec', {'code': "set_parms('/obj/native_user_geometry',{'tx':99})"})['value']
            assert not foreign['ok'], 'resuming a task must not adopt user-created nodes'
    try:
        record = wait(lambda: running(config['root']))
        assert not receipts(), 'standalone workspace boot must not start Houdini'
        initial = browser('snapshot', 'standalone-start')
        assert '工作台' in initial['text'], 'cold start must prepare a user workspace, not use the plugin source directory'
        if initial.get('selection'):
            assert Path(initial['selection']['cwd']).resolve() != ROOT
        if '--standalone-only' in sys.argv:
            print('PASS standalone desktop opens without Houdini and without granting a task the plugin source directory: ' + str(folder), flush=True)
            return
        if '--cold-only' in sys.argv:
            cold_resume()
            print('PASS H21/H22 native save hook coexistence, late install identity, two cold opens, original conversation, unsaved discard and foreign nodes: ' + str(folder), flush=True)
            return
        discussion = browser('new-chat', 'discussion-start')['selection']['sessionId']
        talked = command(discussion)
        assert any(event['type'] == 'user/message' and event['data']['source']['kind'] == 'user' for event in talked['events'])
        before = command(discussion, action='idle')
        first, first_ui = launch('new', 'D:/houdini', 'new-21')
        first_session = first['result']['sessionId']
        assert first_session == discussion, 'creating a project from an unbound discussion must keep that exact conversation'
        assert command(first_session, action='idle')['turns'] == before['turns'], 'binding must not launch a hidden model turn'
        assert first_ui['label'] == '未保存工程 1'
        facts = command(first_session, 'houdini_inspect', {'code': '__result__={"version":hou.applicationVersionString(),"new":hou.hipFile.isNewFile(),"path":hou.hipFile.path()}'})['value']
        assert facts['ok'] and facts['result']['new'] and facts['result']['version'].startswith('21.')
        command(first_session, 'houdini_exec', {'code': "__result__=tab_create('/obj','geo',name='launch_owned').path()"})
        destination = Path(project_temp.name) / 'test104' / '工程.hip'
        saved = command(first_session, 'houdini_exec', {'code': 'scene_save_as(' + repr(str(destination)) + ', ' + repr(facts['result']['path']) + ", 'isolated launch fixture')"})['value']
        assert saved['ok'] and destination.is_file(), saved
        command(first_session, action='beforeStep')
        saved_ui = browser('state', 'save-as', 'online', first_session)
        assert Path(saved_ui['selection']['cwd']).resolve() == destination.parent.resolve()
        second, second_ui = launch('new', 'D:/Houdini22', 'new-22')
        assert second_ui['label'] == '未保存工程 2' and second['pid'] != first['pid']
        second_session = second['result']['sessionId']
        inspected = command(second_session, 'houdini_inspect', {'code': '__result__={"version":hou.applicationVersionString(),"path":hou.hipFile.path()}'})['value']
        assert inspected['ok'] and inspected['result']['version'].startswith('22.')
        other_file = Path(project_temp.name) / 'other-folder' / '另一个工程.hip'
        other_saved = command(second_session, 'houdini_exec', {'code': 'scene_save_as(' + repr(str(other_file)) + ', ' + repr(inspected['result']['path']) + ", 'isolated file-picker fixture')"})['value']
        assert other_saved['ok'], other_saved
        command(second_session, action='beforeStep')
        count = len(receipts())
        (folder / 'dialog-choice.json').write_text(json.dumps({'cancel': True}), encoding='utf-8')
        browser('new', 'cancel-entry')
        wait(lambda: (folder / 'dialog-cancelled').exists())
        assert len(receipts()) == count, 'cancel before launch must create no process or request'
        (folder / ('close-' + str(first['pid']))).touch()
        wait(lambda: _process_started(first['pid']) != first['processStarted'], 35)
        control(record, 'show', {'sessionId': first_session})
        browser('state', 'closed-original', 'offline', first_session)
        reopened, reopened_ui = launch('reopen', 'D:/houdini', 'reopened-original')
        assert reopened['result']['sessionId'] == first_session and reopened['pid'] != first['pid']
        editable = command(first_session, 'houdini_exec', {'code': "__result__=set_parms('/obj/launch_owned',{'tx':2})"})['value']
        assert editable['ok'], editable
        assert command(second_session, 'houdini_inspect', {'code': '__result__=hou.applicationVersionString()'})['value']['ok']
        (folder / ('close-' + str(second['pid']))).touch()
        wait(lambda: _process_started(second['pid']) != second['processStarted'], 35)
        opened_file, opened_ui = launch('open', 'D:/Houdini22', 'opened-file', hip=other_file)
        assert opened_file['result']['sessionId'] == second_session, 'ordinary file opening must resume the matching saved task as well'
        count = len(receipts())
        (folder / 'dialog-finished').unlink(missing_ok=True)
        (folder / 'dialog-choice.json').write_text(json.dumps({'hfs': str(Path('D:/Houdini22')), 'hip': str(other_file)}), encoding='utf-8')
        browser('open', 'reuse-live-file')
        wait(lambda: (folder / 'dialog-finished').is_file(), 15)
        assert (folder / 'dialog-finished').read_text() == '1' and len(receipts()) == count, 'an already open file must not spawn another process'
        control(record, 'show', {'sessionId': first_session})
        (folder / ('clear-' + str(reopened['pid']))).touch()
        browser('state', 'changed-scene', 'changed', first_session)
        assert control(record, 'status')['record']['pid'] == desktop.pid
        cold_resume()
        print('PASS standalone boot without Houdini; real native project dialogs; H21/H22 GUI new scenes, automatic routing, distinct unsaved names, Save As history, cancelled/double launch, proven offline, reopen original task/ownership and changed-scene amber: ' + str(folder), flush=True)
    finally:
        for item in receipts():
            if item.get('pid') and _process_started(item['pid']) == item.get('processStarted'):
                (folder / ('close-' + str(item['pid']))).touch()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline and any(item.get('pid') and _process_started(item['pid']) == item.get('processStarted') for item in receipts()):
            time.sleep(.2)
        assert not any(item.get('pid') and _process_started(item['pid']) == item.get('processStarted') for item in receipts()), 'owned test Houdini did not exit'
        for log in (Path(config['root']) / 'workbench/launches').glob('*.log'):
            assert 'Fatal error' not in log.read_text(encoding='utf-8', errors='replace'), 'Houdini crash is not a normal exit pass'
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
        project_temp.cleanup()
        os.environ.clear()
        os.environ.update(previous)


if __name__ == '__main__':
    main()
