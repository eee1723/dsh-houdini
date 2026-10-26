"""Forward the next save hook; let Houdini run its own uiready scripts once."""
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_workbench_entry as entry

with tempfile.TemporaryDirectory(prefix='dsh-native-hooks-') as temporary:
    folder = Path(temporary)
    wrapper = folder / 'plugin/scripts/afterscenesave.py'
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text('fixture', encoding='utf-8')
    user = folder / 'user-save.py'
    user.write_text("calls.append(('user', dict(kwargs)))", encoding='utf-8')
    shadowed = folder / 'shadowed-save.py'
    shadowed.write_text("raise AssertionError('normally shadowed hook must not run')", encoding='utf-8')
    calls = []
    arguments = {'file': str(folder / 'scene.hip'), 'success': True}
    recovery = SimpleNamespace(after_save=lambda filename, success: calls.append(('plugin', filename, success)),
                               save_unverified=lambda message: calls.append(('unverified', message)))
    hou = ModuleType('hou')
    hou.findFiles = lambda relative: [str(wrapper), str(user), str(shadowed)]
    hou.findFile = lambda relative: str(wrapper)
    with patch.dict(sys.modules, {'hou': hou, 'dsh_scene_recovery': recovery}):
        entry.after_save({'kwargs': arguments, 'calls': calls}, wrapper)
        assert calls == [('plugin', arguments['file'], True), ('user', arguments)]
        assert arguments == {'file': str(folder / 'scene.hip'), 'success': True}
        calls.clear()
        # Native Houdini callback globals do not supply __file__ (H21 GUI).
        source = ROOT / 'houdini/scripts/afterscenesave.py'
        exec(compile(source.read_bytes(), str(source), 'exec'), {'kwargs': arguments, 'calls': calls})
        assert calls == [('plugin', arguments['file'], True), ('user', arguments)]
        calls.clear()
        user.write_text("calls.append(('user-without-kwargs', kwargs))", encoding='utf-8')
        entry.after_save({'calls': calls}, wrapper)
        assert calls[0][0] == 'unverified' and calls[1] == ('user-without-kwargs', None)
    assert not entry._SAVE_HOOKS

    scheduled = []
    user.write_text("calls.append('native-ready')", encoding='utf-8')
    before = list(calls)
    hou.findFiles = lambda relative: (_ for _ in ()).throw(AssertionError('uiready must not redispatch native scripts'))
    qt = ModuleType('hutil.Qt')
    qt.QtCore = SimpleNamespace(QTimer=SimpleNamespace(singleShot=lambda delay, callback: scheduled.append(callback)))
    with patch.dict(sys.modules, {'hou': hou, 'hutil': ModuleType('hutil'), 'hutil.Qt': qt}):
        entry.after_ui_ready()
    assert calls == before and scheduled == [entry.attach]

print('Native save success/missing-kwargs forwarding and non-duplicating uiready scheduling passed')
