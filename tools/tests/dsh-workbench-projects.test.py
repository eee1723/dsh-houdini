from pathlib import Path
import json
import queue
import sys
import tempfile
import os
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_workbench_projects as projects
from dsh_deployment import FileLease


with tempfile.TemporaryDirectory(prefix='dsh-launch-中文 空格-') as directory:
    root = Path(directory)
    registry = root / 'executors'
    context = {'root': str(root), 'executorRegistry': str(registry), 'contextFile': str(root / 'context.json')}
    callbacks, spawned, records = [], [], []
    intents = queue.Queue()
    manager = projects.ProjectManager({'hfs': str(root / 'Houdini')}, context, ROOT, 'desktop-generation',
        lambda method, value: callbacks.append((method, value)) or {'sessionId': 'task', 'executorId': value['executorId']}, intents)
    runtime = {'hfs': str(root / 'Houdini'), 'executable': str(root / 'Houdini/bin/houdini.exe'), 'version': '21.0.440'}
    manager.installations = lambda: [runtime]
    manager.candidates = lambda: records
    class Process:
        pid = 12345
        def poll(self):
            return None
        def terminate(self):
            raise AssertionError('closing progress must never terminate Houdini')
    def spawn(args, **kwargs):
        spawned.append((args, kwargs))
        return Process()
    with patch.object(projects.subprocess, 'Popen', spawn), patch.object(projects, '_process_started', lambda pid: 'birth' if pid == 12345 else None):
        project = root / '工程 与 空格.hip'
        project.write_bytes(b'fixture')
        opened = manager.launch('open', runtime['hfs'], project)
        assert len(spawned) == 1 and spawned[0][0][2] == str(project)
        assert spawned[0][1]['env']['HOUDINI_PATH'].split(';')[0].endswith(opened['id'])
        assert (Path(spawned[0][1]['env']['HOUDINI_PATH'].split(';')[0]) / 'python3.11libs/uiready.py').is_file()
        assert 'after_save(globals(),' in (Path(spawned[0][1]['env']['HOUDINI_PATH'].split(';')[0]) / 'scripts/afterscenesave.py').read_text(encoding='utf-8')
        try:
            manager.launch('open', runtime['hfs'], project)
        except RuntimeError as error:
            assert '已经在启动' in str(error)
        else:
            raise AssertionError('duplicate startup accepted')
        assert len(spawned) == 1
        for action, hfs, filename in [('open', runtime['hfs'], root / 'malicious.py'), ('open', root / 'foreign', project), ('guess', runtime['hfs'], project)]:
            try:
                manager.launch(action, hfs, filename)
            except ValueError:
                pass
            else:
                raise AssertionError('invalid executable or file accepted')
        payload = {'id': opened['id'], 'executorId': 'a' * 32, 'registrationId': 'b' * 32, 'expectedHip': str(project)}
        record = {'executor_id': 'a' * 32, 'registration_id': 'b' * 32, 'pid': 54321, 'hip_path': str(project)}
        records.append(record)
        try:
            manager.attached(payload)
        except RuntimeError:
            pass
        else:
            raise AssertionError('different process attached')
        assert not callbacks
        record['pid'] = 12345
        record['houdini_version'] = '22.0.368'
        with patch.object(projects, 'endpoint_presence', lambda *args: {'status': 'online'}):
            try:
                manager.launch('open', runtime['hfs'], project)
            except RuntimeError as error:
                assert '要换版本' in str(error)
            else:
                raise AssertionError('reusing a different Houdini version silently ignored the user selection')
        try:
            manager.attached({**payload, 'expectedHip': str(root / 'other.hip')})
        except RuntimeError:
            pass
        else:
            raise AssertionError('wrong loaded HIP attached')
        manager.detach(opened['id'])
        accepted = manager.attached(payload)
        assert accepted['sessionId'] == 'task' and intents.empty()
        assert manager.attached(payload) == accepted and len(callbacks) == 1
        try:
            manager.attached({**payload, 'executorId': 'c' * 32})
        except RuntimeError:
            pass
        else:
            raise AssertionError('changed callback replay accepted')
        records.clear()
        new = manager.launch('new', runtime['hfs'])
        ticket = manager._read(new['id'])
        assert ticket['hip'] is None and Path(ticket['workspace']).is_dir()
        assert not list(Path(ticket['workspace']).glob('*.hip'))
        ticket['generation'] = 'old-desktop'
        manager._write(ticket)
        try:
            manager.attached({**payload, 'id': new['id']})
        except RuntimeError as error:
            assert '重开' in str(error)
        else:
            raise AssertionError('old desktop generation accepted')
    for invalid in ({'action': 'new', 'hip': str(project)}, {'action': 'open', 'command': 'anything'}, {'action': 'reopen', 'hip': 'relative.hip'}, []):
        try:
            projects.dialog_request(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('forged dialog input accepted')
    executor = 'd' * 32
    record = {'executor_id': executor, 'scene_epoch': 'e' * 32, 'hip_path': str(project), 'state': 'registered',
              'bridge_url': 'http://127.0.0.1:1', 'runtime_id': 'f' * 32}
    assert projects.endpoint_presence(record, registry)['status'] == 'offline'
    with FileLease(registry / 'leases' / (executor + '.lock')):
        assert projects.endpoint_presence(record, registry)['status'] == 'unknown', 'timeout or failed HTTP with a live lease is not an exit proof'
    assert 'hou' not in sys.modules, 'desktop discovery and launch preparation must not import HOM'
    import dsh_workbench_entry as entry
    import dsh_workbench as workbench
    ticket = root / 'workbench/launches' / ('1' * 32 + '.json')
    ticket.write_text(json.dumps({'id': '1' * 32, 'root': str(root), 'plugin': str(ROOT), 'generation': 'fixture',
        'hfs': str(root / 'Houdini'), 'hip': None, 'workspace': str(root / 'workspace')}), encoding='utf-8')
    messages = []
    facts = {'executor_id': '2' * 32, 'hip': str(root / 'untitled.hip')}
    class Immediate:
        def __init__(self, target, **kwargs):
            self.target = target
        def start(self):
            self.target()
    modules = {'hou': SimpleNamespace(isUIAvailable=lambda: True),
        'dsh_launcher': SimpleNamespace(__file__=str(ROOT / 'houdini/python3.11libs/dsh_launcher.py'), _MANAGED=None),
        'dsh_shared_executor': SimpleNamespace(prepare_registration=lambda **kwargs: facts, publish_registration=lambda *args: {'registration_id': '3' * 32}),
        'dsh_workbench_client': SimpleNamespace(install_observation=lambda: None)}
    with patch.dict(sys.modules, modules), patch.object(entry.threading, 'Thread', Immediate), \
            patch.object(workbench, 'running', lambda unused: {'generation': 'fixture'}), \
            patch.object(workbench, 'control', lambda record, action, value, **kwargs: messages.append((action, value))), \
            patch.dict(os.environ, {'DSH_HOUDINI_LAUNCH_TICKET': str(ticket), 'HFS': str(root / 'Houdini'), 'DSH_HOUDINI_EXECUTOR_REGISTRY': str(registry)}):
        entry.attach()
        assert messages[-1][0] == 'projects/attached', 'the actual entry must read the Path ticket and return its exact handshake'
        os.environ['DSH_HOUDINI_LAUNCH_TICKET'] = str(ticket)
        os.environ['HFS'] = str(root / 'other-version')
        entry.attach()
        assert messages[-1][0] == 'projects/failed', 'wrong launch runtime reports a failure instead of silently waiting forever'
    first_hook, inherited_hook, user_hook, unused_hook = [root / name for name in ('first.py','inherited.py','user.py','unused.py')]
    inherited_hook.write_text('from dsh_workbench_entry import after_save\nafter_save(globals(), '+repr(str(inherited_hook))+')', encoding='utf-8')
    user_marker = root / 'user-save.json'
    user_hook.write_text('import json\nfrom pathlib import Path\nassert native_value==42\nPath('+repr(str(user_marker))+').write_text(json.dumps(kwargs))\nkwargs["success"]=True', encoding='utf-8')
    unused_hook.write_text('raise AssertionError("do not run additional studio hooks that native Houdini would not select")', encoding='utf-8')
    notified = []
    arguments = {'file':'saved.hip','success':False,'autosave':True}
    with patch.dict(sys.modules, {'hou':SimpleNamespace(findFiles=lambda pattern:tuple(map(str,[first_hook,inherited_hook,user_hook,unused_hook]))),
            'dsh_scene_recovery':SimpleNamespace(after_save=lambda filename,success:notified.append((filename,success)))}):
        entry.after_save({'kwargs':arguments,'native_value':42}, first_hook)
        assert notified == [('saved.hip',False),('saved.hip',False)]
        assert json.loads(user_marker.read_text()) == arguments and arguments['success'] is False
        assert not entry._SAVE_HOOKS, 'nested inherited launch hooks must not form a cycle or retain state'
        with patch.dict(sys.modules, {'dsh_scene_recovery':SimpleNamespace(after_save=lambda *args:(_ for _ in ()).throw(RuntimeError('notification failed')))}):
            user_marker.unlink()
            try:
                entry.after_save({'kwargs':arguments,'native_value':42}, first_hook)
            except RuntimeError as error:
                assert str(error) == 'notification failed'
            else:
                raise AssertionError('save notification failure was hidden')
            assert user_marker.exists() and not entry._SAVE_HOOKS
print('workbench launch: exact executable/file, duplicate prevention, PID birth/scene/generation fencing, replay, background hide, no implicit save, untrusted dialog payloads and unknown-versus-offline passed')
