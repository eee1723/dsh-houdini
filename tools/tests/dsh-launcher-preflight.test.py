"""The menu owns only its local Bridge; no DSH Host or unrelated process."""
import importlib
import os
from pathlib import Path
import queue
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
sys.modules.setdefault('hou', SimpleNamespace())
import dsh_launcher as launcher

with tempfile.TemporaryDirectory(prefix='desktop-menu-local-') as temporary:
    current = {'hip_dir': None}
    context = SimpleNamespace(hip_file_identity=lambda: current)
    with patch.dict(sys.modules, {'dsh_context': context}), \
         patch.object(launcher, '_FALLBACK_WORKSPACE', temporary), \
         patch.object(launcher, '_UNSAVED_WORKSPACE', None):
        first = launcher._hip_dir()
        assert Path(first).parent == Path(temporary)
        assert launcher._hip_dir() == first
        current['hip_dir'] = str(Path(temporary) / 'named')
        assert launcher._hip_dir() == current['hip_dir']
        current['hip_dir'] = None
        assert launcher._hip_dir() != first

calls = []
shortcut = SimpleNamespace(open_workspace=lambda actual, **kwargs: calls.append((actual, kwargs)))
with patch.dict(sys.modules, {'dsh_workbench_client': shortcut}):
    launcher.open_workspace()
    launcher.repair_current_runtime()
    launcher.launch()
assert [kwargs for actual, kwargs in calls] == [{}, {'reload': True}, {}]
assert all(actual is launcher for actual, kwargs in calls)

# Issue #3: a newer registry imported an older cached dsh_deployment without
# _process_started. Refuse that generation before any Bridge reload/import.
old_state = SimpleNamespace(__file__=str(ROOT / 'houdini/python3.11libs/dsh_deployment.py'),
                            FileLease=lambda *args: None, atomic_json=lambda *args: None)
with patch.dict(sys.modules, {'dsh_deployment': old_state}):
    try:
        launcher.require_local_modules()
    except RuntimeError as error:
        assert '重开' in str(error) and '旧版连接模块' in str(error)
    else:
        raise AssertionError('mixed helper APIs were accepted')
with patch.dict(sys.modules, {'dsh_deployment': SimpleNamespace(__file__=str(ROOT / 'tools/out/old-helper/dsh_deployment.py'))}):
    try:
        launcher.require_local_modules()
    except RuntimeError as error:
        assert '另一版本' in str(error)
    else:
        raise AssertionError('foreign helper path was accepted')

busy = [True]
bridge = SimpleNamespace(
    _request_registry=SimpleNamespace(active_count=lambda: 1 if busy[0] else 0),
    _job_activity=lambda: {'activeJobs': 0}, _work_queue=queue.Queue(),
    stop=lambda: calls.append('stop'), start=lambda port, host: SimpleNamespace(server_port=45678))
loaded = []
with patch.dict(sys.modules, {'dsh_bridge': bridge}), \
     patch.object(launcher.importlib, 'reload', lambda module: module), \
     patch.object(launcher.importlib, 'import_module', lambda name: loaded.append(name) or SimpleNamespace()):
    try:
        launcher.restart_bridge(port=0)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Bridge was reloaded while a request was active')
    assert not loaded and 'stop' not in calls
    busy[0] = False
    assert '45678' in launcher.restart_bridge(port=0)
assert 'dsh_curve_paths' in loaded, 'preserve current Houdini helper reload coverage'
assert loaded[-1] == 'dsh_execution'

# Helper selection is a maintenance action for the next process. Disk/process
# work stays on a worker, cancellation performs no selection, and no module reloads.
with tempfile.TemporaryDirectory(prefix='helper-selection-') as temporary:
    folder = Path(temporary)
    (folder / 'installer').mkdir()
    (folder / 'installer/install.ps1').write_text('# trusted fixture', encoding='utf-8')
    lane, timers, executions, displays = ['main'], [], [], []
    rows = [{'id': 'a' * 16, 'version': 'first', 'path': str(folder), 'valid': True},
            {'id': 'b' * 16, 'version': 'second', 'path': str(folder / 'second'), 'valid': True}]

    class Thread:
        def __init__(self, target, **kwargs): self.target = target
        def start(self):
            lane[0] = 'worker'
            try: self.target()
            finally: lane[0] = 'main'

    class Timer:
        def __init__(self, *args): self.timeout = self; timers.append(self)
        def connect(self, callback): self.callback = callback
        def start(self, interval): pass
        def stop(self): pass

    def process(arguments, **kwargs):
        import json
        assert lane[0] == 'worker'
        executions.append(arguments)
        return SimpleNamespace(returncode=0, stdout=json.dumps(rows) if '-ListHelpers' in arguments else '', stderr='')

    qt = ModuleType('hutil.Qt')
    qt.QtCore = SimpleNamespace(QTimer=Timer)
    hou = SimpleNamespace(qt=SimpleNamespace(mainWindow=lambda: None), ui=SimpleNamespace(
        selectFromList=lambda *args, **kwargs: (), displayMessage=lambda *args, **kwargs: displays.append(args)))
    with patch.object(launcher, '_PROJECT_ROOT', str(folder)), patch.object(launcher, 'hou', hou), \
         patch.dict(sys.modules, {'hutil': ModuleType('hutil'), 'hutil.Qt': qt}), \
         patch.dict(os.environ, {'DSH_HOUDINI_INSTALL_ROOT': str(folder / 'installation'), 'SystemRoot': 'C:/Windows'}), \
         patch('threading.Thread', Thread), patch('subprocess.run', process):
        launcher.select_helper_version()
        timers[-1].callback()
        assert launcher._HELPER_SWITCH_TIMER is None and len(executions) == 1
        hou.ui.selectFromList = lambda *args, **kwargs: (1,)
        launcher.select_helper_version()
        timers[-1].callback()
        timers[-1].callback()
    assert executions[-1][-2:] == ['-SelectHelper', 'b' * 16]
    assert len(displays) == 1 and '重开' in displays[0][0]
    assert launcher._HELPER_SWITCH_TIMER is None
# Component removal is an explicit, local, next-start action. Confirmation and
# completion stay on the native thread; file discovery and the bounded PS call
# run only on the worker. The current Bridge/Houdini/Host are never stopped.
with tempfile.TemporaryDirectory(prefix='helper-removal-') as temporary:
    installation = Path(temporary) / 'installation'
    helper = installation / 'helpers' / ('c' * 16)
    (helper / 'installer').mkdir(parents=True)
    script = helper / 'installer/uninstall.ps1'
    script.write_text('# installed helper fixture', encoding='utf-8')
    source_checkout = installation.parent / 'source-checkout'
    (source_checkout / 'installer').mkdir(parents=True)
    (source_checkout / 'installer/uninstall.ps1').write_text('# source script must not be executed', encoding='utf-8')
    lane, timers, executions, displays, failures = ['main'], [], [], [], []
    confirm, fail = [1], [False]

    class Timer:
        def __init__(self, *args):
            self.timeout = self
            self.stopped = self.deleted = False
            timers.append(self)
        def connect(self, callback): self.callback = callback
        def start(self, interval): assert lane[0] == 'main'
        def stop(self): self.stopped = True
        def deleteLater(self): self.deleted = True

    def display(message, **kwargs):
        assert lane[0] == 'main'
        displays.append((message, kwargs))
        return confirm[0] if kwargs.get('buttons') == ('移除组件', '取消') else None

    def process(arguments, **kwargs):
        assert lane[0] == 'worker'
        executions.append(arguments)
        assert arguments[arguments.index('-File') + 1] == str(script)
        assert arguments[arguments.index('-Root') + 1] == str(installation)
        assert kwargs['timeout'] == 30 and kwargs['encoding'] == 'utf-8'
        return SimpleNamespace(returncode=1 if fail[0] else 0,
                               stdout='Reversible unregister report: fixture-report', stderr='fixture failure' if fail[0] else '')

    original_is_file, original_resolve = Path.is_file, Path.resolve
    def worker_file(path):
        assert lane[0] == 'worker', 'maintenance file checks must not block the GUI'
        return original_is_file(path)
    def worker_resolve(path, **kwargs):
        assert lane[0] == 'worker', 'maintenance path resolution must not block the GUI'
        return original_resolve(path, **kwargs)
    def failure(error):
        assert lane[0] == 'main'
        failures.append(str(error))

    qt.QtCore = SimpleNamespace(QTimer=Timer)
    hou = SimpleNamespace(qt=SimpleNamespace(mainWindow=lambda: None),
                          ui=SimpleNamespace(displayMessage=display))
    with patch.object(launcher, '_PROJECT_ROOT', str(helper)), patch.object(launcher, 'hou', hou), \
         patch.object(launcher, '_startup_failure', failure), \
         patch.dict(sys.modules, {'hutil': ModuleType('hutil'), 'hutil.Qt': qt}), \
         patch.dict(os.environ, {'DSH_HOUDINI_INSTALL_ROOT': str(installation), 'SystemRoot': 'C:/Windows'}), \
         patch('threading.Thread', Thread), patch('subprocess.run', process), \
         patch.object(Path, 'is_file', worker_file), patch.object(Path, 'resolve', worker_resolve), \
         patch.object(launcher, 'restart_bridge', side_effect=AssertionError('removal must not restart Bridge')):
        launcher.remove_local_components()
        assert not executions and not timers, 'cancel must not create a worker or timer'
        confirm[0] = 0
        launcher.remove_local_components()
        assert len(executions) == 1 and launcher._HELPER_SWITCH_TIMER is timers[-1]
        assert len(displays) == 2, 'worker may not display completion directly'
        launcher.remove_local_components()
        assert len(executions) == 1 and len(displays) == 2, 'one local maintenance action at a time'
        timer = timers[-1]
        timer.callback()
        assert timer.stopped and timer.deleted and launcher._HELPER_SWITCH_TIMER is None
        assert '解除登记' in displays[-1][0] and 'fixture-report' in displays[-1][1]['details']
        timer.callback()
        assert len(displays) == 3, 'retired timer cannot report completion twice'
        fail[0] = True
        launcher.remove_local_components()
        timers[-1].callback()
        assert failures == ['fixture failure'] and launcher._HELPER_SWITCH_TIMER is None
        with patch.object(launcher, '_PROJECT_ROOT', str(source_checkout)):
            launcher.remove_local_components()
            timers[-1].callback()
        assert len(executions) == 2 and len(failures) == 2, 'uninstall cannot execute a source or other installation script'
        assert '不可变 helper' in failures[-1]
        assert launcher._HELPER_SWITCH_TIMER is None

# The existing ASCII native menu opens this Chinese information dialog; its new
# removal button routes to the same explicit action without building another UI.
with patch.object(launcher.hou, 'ui', SimpleNamespace(displayMessage=lambda *args, **kwargs: 3), create=True), \
     patch.object(launcher, 'remove_local_components') as remove:
    launcher.show_plugin_info()
    remove.assert_called_once_with()
print('Desktop menu routing, idle-only repair, helper version selection and confirmed worker-only component removal passed')
