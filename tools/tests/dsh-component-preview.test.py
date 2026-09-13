"""Source preview configuration and fail-closed menu path; no GUI, Host, or HIP writes."""
from pathlib import Path
import json
import os
import sys
import tempfile
import types
import xml.etree.ElementTree as ET
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
messages = []
sys.modules.setdefault('hou', types.SimpleNamespace(
    isUIAvailable=lambda: True, ui=types.SimpleNamespace(displayMessage=messages.append)))
import dsh_component_preview as preview
import dsh_launcher as launcher
import dsh_managed_runtime as runtime

with tempfile.TemporaryDirectory(prefix='dsh-component-preview-test-') as temporary:
    root = Path(temporary)
    binary = root / 'cli/lib/bin.js'
    binary.parent.mkdir(parents=True)
    binary.write_text('', encoding='utf-8')
    (binary.parent.parent / 'package.json').write_text(json.dumps({'name': '@deepseek-ai/dsh'}), encoding='utf-8')
    python, houdini = root / 'python.exe', root / 'houdini.exe'
    python.touch(); houdini.touch()
    run = root / 'run-1'
    config = {'schema': 1, 'source': str(ROOT), 'bin': str(binary), 'python': str(python),
              'houdini': str(houdini), 'run': str(run),
              **{key: str(run / key) for key in ('home', 'workers', 'registry')}}
    assert preview._validate_config(config, root) is config
    with patch.object(preview.sys, 'executable', str(houdini)):
        assert preview._houdini_hint() == str(houdini.resolve())
    hfs = root / 'Houdini'
    (hfs / 'bin').mkdir(parents=True)
    (hfs / 'bin' / 'houdini.exe').touch()
    with patch.object(preview.sys, 'executable', str(root / 'hython.exe')), \
         patch.dict(os.environ, {'HFS': str(hfs)}):
        assert preview._houdini_hint() == str((hfs / 'bin' / 'houdini.exe').resolve())
    with patch.object(preview.sys, 'executable', str(root / 'hython.exe')), \
         patch.dict(os.environ, {'HFS': str(root / 'missing')}, clear=True):
        assert preview._houdini_hint() == ''
    with patch.object(preview.sys, 'executable', str(houdini)), \
         patch.object(preview.shutil, 'which', return_value=str(python)):
        assert preview._python_hint() == str(python.resolve())
    alias = root / 'Microsoft' / 'WindowsApps' / 'python.exe'
    alias.parent.mkdir(parents=True)
    alias.touch()
    local_python = root / 'Python' / 'pythoncore-3.14-64' / 'python.exe'
    local_python.parent.mkdir(parents=True)
    local_python.touch()
    with patch.object(preview.sys, 'executable', str(houdini)), \
         patch.object(preview.shutil, 'which', return_value=str(alias)), \
         patch.dict(os.environ, {'LOCALAPPDATA': str(root)}):
        assert preview._python_hint() == str(local_python.resolve())
        second = root / 'Python' / 'pythoncore-3.13-64' / 'python.exe'
        second.parent.mkdir(parents=True)
        second.touch()
        assert preview._python_hint() == '', 'ambiguous Python installations require a user choice'
    import dsh_launcher as launcher
    gui = types.SimpleNamespace(ui=types.SimpleNamespace(readInput=Mock(side_effect=AssertionError('unexpected path dialog'))))
    with patch.dict(os.environ, {'DSH_HOUDINI_COMPONENT_BIN': str(binary)}), \
         patch.object(preview, '_python_hint', return_value=str(python)), \
         patch.object(preview, '_houdini_hint', return_value=str(houdini)), \
         patch.object(launcher, 'NODE', str(python)):
        assert preview._new_config(gui, root)['bin'] == str(binary)
    gui.ui.readInput = Mock(return_value=(0, str(binary)))
    with patch.dict(os.environ, {'DSH_HOUDINI_COMPONENT_BIN': '', 'DSH_HOUDINI_DSH_BIN': str(binary)}), \
         patch.object(preview, '_python_hint', return_value=str(python)), \
         patch.object(preview, '_houdini_hint', return_value=str(houdini)), \
         patch.object(launcher, 'NODE', str(python)):
        assert preview._new_config(gui, root)['bin'] == str(binary)
    assert gui.ui.readInput.call_count == 1
    assert gui.ui.readInput.call_args.kwargs['initial_contents'] == str(binary)
    gui.ui.readInput = Mock(return_value=(1, ''))
    with patch.dict(os.environ, {'DSH_HOUDINI_COMPONENT_BIN': '', 'DSH_HOUDINI_DSH_BIN': ''}), \
         patch.object(preview, '_python_hint', side_effect=AssertionError('cancel must not inspect later hints')):
        assert preview._new_config(gui, root) is None
    for invalid in ({**config, 'source': 'elsewhere'}, {**config, 'workers': str(root / 'other')},
                    {**config, 'run': str(root.parent)}):
        try: preview._validate_config(invalid, root)
        except RuntimeError: pass
        else: raise AssertionError('invalid preview source/directory was accepted')
    root.joinpath('config.json').write_text(json.dumps(config), encoding='utf-8')
    try: preview._read_config(root)
    except RuntimeError as error: assert 'incomplete' in str(error)
    else: raise AssertionError('an incomplete profile was silently adopted')

with patch.dict(os.environ, {'DSH_HOME': 'foreign', 'HOUDINI_PATH': 'foreign',
                              'OPENAI_API_KEY': 'secret', 'HOUDINI_LICENSE_SERVER': 'license'}, clear=True):
    env = preview._host_environment(config)
    assert env['DSH_HOME'] == config['home'] and env['HOUDINI_LICENSE_SERVER'] == 'license'
    assert 'HOUDINI_PATH' not in env and 'OPENAI_API_KEY' not in env

with patch.object(launcher, '_MANAGED', None), patch.object(runtime, 'has_owned_frontend', return_value=True), \
     patch.object(preview, '_HOST_PROCESS', None), \
     patch.object(preview, '_preview_root', side_effect=AssertionError('must not prepare profile')):
    preview.open_workspace()
assert messages and 'another DSH frontend' in messages[-1]

with patch.object(preview, '_HOST_PROCESS', types.SimpleNamespace(poll=lambda: 1)), \
     patch.object(runtime, 'has_owned_frontend', return_value=False), \
     patch.object(preview, '_preview_root', side_effect=AssertionError('stopped Host must not be restarted')):
    preview.open_workspace()
assert 'no automatic restart' in messages[-1]

workspace = ROOT / 'tools/out'
hip = workspace / 'assembly.hip'
session = types.SimpleNamespace(launch_url=lambda: 'http://127.0.0.1:2345/?token=fixture',
                                base_url='http://127.0.0.1:2345')
view = types.SimpleNamespace(show_webview=Mock())
import dsh_executor_registry as registry
import dsh_shared_executor as shared
with patch.object(preview, '_HOST_PROCESS', types.SimpleNamespace(poll=lambda: None)), \
     patch.object(preview, '_STATE', {'result': 'ready'}), patch.object(preview, '_SESSION', session), \
     patch.object(preview, '_preview_root', return_value=Path(config['run']).parent), \
     patch.object(preview, '_read_config', return_value=config), \
     patch.object(runtime, 'has_owned_frontend', return_value=True), \
     patch.object(launcher, '_hip_dir', return_value=str(workspace)), \
     patch.object(registry, 'is_shared_executor', return_value=True), \
     patch.object(registry, 'active_registration', return_value=types.SimpleNamespace(
         root=Path(config['registry']).resolve(), registered_hip=lambda: str(hip))), \
     patch.object(shared, 'prepare_registration', side_effect=AssertionError('repeat open must not re-register')), \
     patch.object(sys.modules['hou'], 'hipFile', types.SimpleNamespace(isNewFile=lambda: False, path=lambda: str(hip)),
                  create=True), patch.dict(sys.modules, {'dsh_webview': view}):
    preview.open_workspace()
view.show_webview.assert_called_once_with(workspace_dir=str(workspace),
    authenticated_url=session.launch_url(), frontend_url=session.base_url)

menu = ET.parse(ROOT / 'houdini/MainMenuCommon.xml')
script = menu.find(".//scriptItem[@id='dsh.open_workspace']/scriptCode").text
assert 'dsh_launcher.open_workspace(select_mode=True)' in script
assert menu.find(".//scriptItem[@id='dsh.component_workspace']") is None
assert len([item for item in menu.findall('.//scriptItem')
            if 'Workspace' in item.findtext('label', '')]) == 1
with patch.object(preview, '_BUSY', True), patch.object(launcher, '_dispatch_service_preflight',
                                                       side_effect=AssertionError('ordinary launch crossed preview startup')), \
     patch.object(launcher, '_report') as report:
    launcher.open_workspace()
    assert 'preparing its component workspace' in report.call_args.args[0]
with patch.object(preview, '_HOST_PROCESS', types.SimpleNamespace(poll=lambda: None)), \
     patch.object(preview, 'open_workspace') as reopen, \
     patch.object(launcher, '_dispatch_service_preflight', side_effect=AssertionError('duplicate Host attempted')), \
     patch.object(registry, 'is_shared_executor', return_value=False):
    launcher.open_workspace()
    reopen.assert_called_once_with()
with patch.object(preview, '_HOST_PROCESS', types.SimpleNamespace(poll=lambda: 1)), \
     patch.object(preview, 'open_workspace') as refuse_stopped, \
     patch.object(launcher, '_dispatch_service_preflight', side_effect=AssertionError('stopped Host restarted')):
    launcher.open_workspace()
    refuse_stopped.assert_called_once_with()
with patch.object(preview, '_HOST_PROCESS', None), \
     patch.object(registry, 'is_shared_executor', return_value=True), \
     patch.object(launcher, '_dispatch_service_preflight', side_effect=AssertionError('foreign Host adopted')), \
     patch.object(launcher, '_report') as report:
    launcher.open_workspace()
    assert 'another shared Host' in report.call_args.args[0]
with patch.object(preview, '_HOST_PROCESS', None), \
     patch.object(registry, 'is_shared_executor', return_value=False), \
     patch.object(launcher, '_hip_dir', return_value=str(workspace)), \
     patch.object(launcher, '_dispatch_service_preflight') as ordinary:
    launcher.open_workspace()
    ordinary.assert_called_once()
with patch.object(launcher, '_MANAGED', None), \
     patch.object(runtime, 'has_owned_frontend', return_value=False), \
     patch.object(sys.modules['hou'], 'hipFile', types.SimpleNamespace(isNewFile=lambda: False, path=lambda: str(hip)),
                  create=True), \
     patch.object(launcher.os.path, 'isfile', return_value=True), \
     patch.object(preview, '_HOST_PROCESS', None), \
     patch.object(registry, 'is_shared_executor', return_value=False), \
     patch.object(launcher, '_dispatch_service_preflight', side_effect=AssertionError('preview started ordinary Host')), \
     patch.object(preview, 'open_workspace') as chosen, \
     patch.object(sys.modules['hou'].ui, 'displayMessage', return_value=1) as prompt:
    launcher.open_workspace(select_mode=True)
    chosen.assert_called_once_with()
    assert prompt.call_args.kwargs['default_choice'] == 0
with patch.object(launcher, '_MANAGED', None), \
     patch.object(runtime, 'has_owned_frontend', return_value=False), \
     patch.object(sys.modules['hou'], 'hipFile', types.SimpleNamespace(isNewFile=lambda: False, path=lambda: str(hip)),
                  create=True), patch.object(launcher.os.path, 'isfile', return_value=True), \
     patch.object(preview, '_HOST_PROCESS', None), \
     patch.object(registry, 'is_shared_executor', return_value=False), \
     patch.object(launcher, '_hip_dir', return_value=str(workspace)), \
     patch.object(preview, 'open_workspace', side_effect=AssertionError('regular choice entered preview')), \
     patch.object(sys.modules['hou'].ui, 'displayMessage', return_value=0), \
     patch.object(launcher, '_dispatch_service_preflight') as ordinary:
    launcher.open_workspace(select_mode=True)
    ordinary.assert_called_once()
with patch.object(launcher, '_MANAGED', None), \
     patch.object(runtime, 'has_owned_frontend', return_value=False), \
     patch.object(sys.modules['hou'], 'hipFile', types.SimpleNamespace(isNewFile=lambda: False, path=lambda: str(hip)),
                  create=True), patch.object(launcher.os.path, 'isfile', return_value=True), \
     patch.object(preview, '_HOST_PROCESS', None), \
     patch.object(registry, 'is_shared_executor', return_value=False), \
     patch.object(launcher, '_dispatch_service_preflight', side_effect=AssertionError('cancel started Host')), \
     patch.object(preview, 'open_workspace', side_effect=AssertionError('cancel started preview')), \
     patch.object(sys.modules['hou'].ui, 'displayMessage', return_value=2):
    launcher.open_workspace(select_mode=True)
with patch.object(launcher, '_MANAGED', {'fixture': True}), \
     patch.object(preview, '_HOST_PROCESS', None), \
     patch.object(registry, 'is_shared_executor', return_value=False), \
     patch.object(launcher, '_hip_dir', return_value=str(workspace)), \
     patch.object(sys.modules['hou'].ui, 'displayMessage', side_effect=AssertionError('managed mode prompt')), \
     patch.object(launcher, '_dispatch_service_preflight') as ordinary:
    launcher.open_workspace(select_mode=True)
    ordinary.assert_called_once()
print('single source menu, explicit preview choice and ordinary/owned/foreign routing passed')
