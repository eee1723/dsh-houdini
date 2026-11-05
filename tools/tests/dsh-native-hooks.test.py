"""Forward the next save hook; let Houdini run its own uiready scripts once."""
from pathlib import Path
import sys
import os
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
    hou.isUIAvailable = lambda: True
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
    with patch.dict(sys.modules, {'hou': hou, 'hutil': ModuleType('hutil'), 'hutil.Qt': qt}), \
            patch.object(entry, '_READY_SCHEDULED', False):
        assert entry.after_ui_ready() is True
        assert entry.after_ui_ready() is False
        for version in ['3.11', '3.13']:
            source = ROOT / f'houdini/python{version}libs/uiready.py'
            exec(compile(source.read_bytes(), str(source), 'exec'), {})
    assert calls == before and scheduled == [entry.attach]

    # GUI discovery and explicit launch intent have separate effects. Neither
    # headless import nor ordinary GUI readiness may create a Desktop session.
    requested = []
    launcher = SimpleNamespace(_report=lambda text: requested.append(('error', text)),
                               _startup_failure=lambda error: requested.append(('window', str(error))))
    connection = SimpleNamespace(discover_current_scene=lambda actual: requested.append(('discover', actual)) or True,
        open_workspace=lambda actual, **kwargs: requested.append(('open', kwargs)) or True)
    with patch.dict(sys.modules, {'hou': hou, 'dsh_launcher': launcher, 'dsh_workbench_client': connection}), \
            patch.dict(os.environ, {}, clear=True):
        assert entry.attach() is True
        assert requested == [('discover', launcher)]
        requested.clear()
        os.environ['DSH_HOUDINI_LAUNCH_TICKET'] = str(folder / 'explicit-ticket.json')
        assert entry.attach() is True
        assert requested == [('open', {'launch_ticket': str(folder / 'explicit-ticket.json')})]
        assert 'DSH_HOUDINI_LAUNCH_TICKET' not in os.environ
        requested.clear()
        hou.isUIAvailable = lambda: False
        assert entry.attach() is False
        with patch.object(entry, '_READY_SCHEDULED', False):
            assert entry.after_ui_ready() is False
        assert not requested and scheduled == [entry.attach]

    # Native AfterLoad/Clear callbacks can still expose the previous new-file
    # flag. Invalidate immediately, then coalesce one capture after returning
    # to the UI loop, when Houdini has committed the final scene metadata.
    import dsh_workbench_client as client
    callbacks, deferred, captured, invalidations = [], [], [], []
    current = {'new': True}
    after_load, after_clear = object(), object()
    hou.hipFile = SimpleNamespace(addEventCallback=callbacks.append)
    hou.hipFileEventType = SimpleNamespace(AfterLoad=after_load, AfterClear=after_clear)
    qt.QtCore.QTimer.singleShot = lambda delay, callback: deferred.append(callback)
    publisher = SimpleNamespace(invalidate_observation=lambda: invalidations.append(True))
    with patch.dict(sys.modules, {'hou': hou, 'hutil': ModuleType('hutil'), 'hutil.Qt': qt,
                                 'dsh_shared_executor': publisher}), \
            patch.object(client, '_CALLBACK', None), patch.object(client, '_OBSERVATIONS', None), \
            patch.object(client.threading, 'Thread', lambda **kwargs: SimpleNamespace(start=lambda: None)), \
            patch.object(client, 'observe_scene', lambda: captured.append(current['new'])):
        client.install_observation()
        callbacks[0](after_load)
        callbacks[0](after_clear)
        assert not captured, 'Native transition callback published intermediate scene state'
        assert len(invalidations) == 2 and len(deferred) == 1
        current['new'] = False
        deferred[0]()
        assert captured == [False]

print('Native save forwarding, idempotent GUI discovery/ticket separation and headless exclusion passed')
