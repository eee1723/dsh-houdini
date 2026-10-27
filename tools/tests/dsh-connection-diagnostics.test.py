"""Offline maintenance UI consumer: no Host, HOM scene, network or real Qt window."""
import base64
import io
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_connection_diagnostics as diagnostics
import dsh_support_report as reports

lane = ['main']
widgets, timers, workers, open_paths, save_paths, browser = [], [], [], [], [], []
def main():
    assert lane[0] == 'main', 'Qt or Houdini accessed from worker'

class Signal:
    def __init__(self): self.callbacks = []
    def connect(self, callback): main(); self.callbacks.append(callback)
    def emit(self, *args):
        main()
        for callback in self.callbacks: callback(*args)

class Widget:
    def __init__(self, *args):
        main(); widgets.append(self)
        self.text = args[0] if args and isinstance(args[0], str) else ''
        self.enabled, self.visible, self.items = True, True, []
        self.clicked, self.finished, self.destroyed, self.currentIndexChanged = [Signal() for _ in range(4)]
    def setText(self, text): main(); self.text = text
    def setPlainText(self, text): main(); self.text = text
    def setEnabled(self, enabled): main(); self.enabled = enabled
    def hide(self): main(); self.visible = False
    def show(self): main(); self.visible = True
    def clear(self): main(); self.items = []
    def addItem(self, label, data): main(); self.items.append((label, data))
    def currentData(self): main(); return self.items[0][1] if self.items else None
    def click(self):
        main()
        if self.enabled: self.clicked.emit()
    def close(self): main(); self.finished.emit(0); self.destroyed.emit(self)
    def __getattr__(self, name):
        assert name.startswith(('set', 'add', 'resize')), name
        return lambda *args, **kwargs: main()

class Timer:
    def __init__(self, parent): main(); timers.append(self); self.timeout = Signal(); self.active = False
    def start(self, interval): main(); self.active = True
    def stop(self): main(); self.active = False

class Thread:
    def __init__(self, target, **kwargs): self.target = target
    def start(self): main(); workers.append(self.target)

def run_worker():
    target = workers.pop(0)
    lane[0] = 'worker'
    try: target()
    finally: lane[0] = 'main'
    timers[-1].timeout.emit()

def choose(paths):
    main()
    return paths.pop(0), ''

def worker_file(function):
    def call(*args, **kwargs):
        assert lane[0] == 'worker', 'filesystem accessed from GUI thread'
        return function(*args, **kwargs)
    return call

def forbidden(*args, **kwargs): raise AssertionError('network or process probe not allowed')
def open_html(url):
    assert lane[0] == 'worker', 'browser startup must stay off the GUI thread'
    browser.append(url)
    return True

qt = ModuleType('hutil.Qt')
qt.QtCore = SimpleNamespace(QTimer=Timer, Qt=SimpleNamespace(WA_DeleteOnClose=1, PlainText=2, TextSelectableByMouse=3),
                          QUrl=SimpleNamespace(fromLocalFile=lambda path: ('local', path)))
qt.QtWidgets = SimpleNamespace(**{name: Widget for name in ('QDialog','QLabel','QVBoxLayout','QHBoxLayout',
                               'QPushButton','QComboBox','QPlainTextEdit')},
    QFileDialog=SimpleNamespace(getOpenFileName=lambda *args: choose(open_paths), getSaveFileName=lambda *args: choose(save_paths)))
style = SimpleNamespace(style_dialog=lambda *args: main(), show_tool_window=lambda *args: main())

with tempfile.TemporaryDirectory(prefix='offline-connection-ui-') as temporary:
    folder = Path(temporary).resolve()
    (folder/'package.json').write_text('{"version":"offline-fixture"}', encoding='utf-8')
    version_calls = []
    hou = SimpleNamespace(applicationVersionString=lambda: main() or version_calls.append(True) or '21.0.fixture',
                          qt=SimpleNamespace(mainWindow=lambda: main()))
    launcher = SimpleNamespace(_PROJECT_ROOT=str(folder), _LAST_STARTUP_FAILURE='actual failure token=DO_NOT_EXPORT', hou=hou)
    bridge = SimpleNamespace(__file__=str(folder/'dsh_bridge.py'), _server=SimpleNamespace(server_address=('127.0.0.1',23456)),
                             token='BRIDGE_SECRET', environment={'SECRET':'ENV_SECRET'}, scene='HIP_CONTENT_SECRET')
    registry = SimpleNamespace(_ACTIVE=SimpleNamespace(_closed=False,executor_id='e'*32,_runtime_id='r'*32,
                                                       version='fixture',token='REGISTRY_SECRET',_hip='HIP_PATH_SECRET'))
    with patch.dict(sys.modules, {'hutil':ModuleType('hutil'),'hutil.Qt':qt,'dsh_ui_style':style,
                                  'dsh_bridge':bridge,'dsh_executor_registry':registry}), \
         patch('threading.Thread', Thread), patch('socket.socket', forbidden), patch('subprocess.Popen', forbidden), \
         patch.object(diagnostics.webbrowser, 'open', open_html), \
         patch('io.open', worker_file(io.open)), patch('builtins.open', worker_file(open)), \
         patch.object(Path,'resolve',worker_file(Path.resolve)), patch.object(Path,'stat',worker_file(Path.stat)):
        snapshot = diagnostics.capture_snapshot(launcher, hou)
        assert snapshot['bridge'] == {'loaded':True,'listening':True,'port':23456}
        assert snapshot['desktop_reachability'] == 'not_probed'
        assert not any(secret in str(snapshot) for secret in ('BRIDGE_SECRET','ENV_SECRET','HIP_CONTENT_SECRET','REGISTRY_SECRET','HIP_PATH_SECRET'))
        window = diagnostics.show(launcher)
        assert diagnostics.show(launcher) is window and not workers
        button = lambda name: next(widget for widget in widgets if widget.text == name)
        generate, inspect = button('生成接入诊断'), button('查看已有诊断包…')
        save, view, close = button('保存诊断包…'), button('保存并查看 HTML…'), button('关闭')
        assert not save.enabled and not view.enabled
        generate.click()
        assert len(workers) == 1 and not save.enabled and not generate.enabled
        generate.click()
        assert len(workers) == 1, 'busy UI may not start another report'
        run_worker()
        assert save.enabled and view.enabled and not timers[-1].active, [widget.text for widget in widgets]
        assert not save_paths and not browser, 'generation may not save or open a file without user selection'
        saved = folder/'explicit-report.zip'
        save_paths.append(str(saved)); save.click(); run_worker()
        # HTML and ZIP paths are supplied by the user, not guessed from the install.
        html = folder/'explicit-report.html'
        save_paths.append(str(html)); view.click(); run_worker()
        assert browser == [html.as_uri()]
        open_paths.append(str(saved)); inspect.click(); run_worker()
        assert view.enabled and not save.enabled, 'viewing an existing report must not offer regenerating its original bytes'
        # No worker completion may touch a dialog the user has already closed.
        generate.click(); assert workers
        close.click(); assert diagnostics._WINDOW is None
        run_worker()
        assert not timers[-1].active and len(browser) == 1
    manifest, files = reports.inspect_report(saved)
    assert manifest['session'] is None and not manifest['content_included']
    assert 'actual failure' in files['timeline.jsonl'] and 'DO_NOT_EXPORT' not in str(files)
    assert "default-src 'none'" in html.read_text(encoding='utf-8')
    assert not list(folder.glob('.*.zip.*')) and not list(folder.glob('.*.html.*'))
    assert version_calls and all('offline_connection' not in str(path) for path in save_paths)

print('Offline connection diagnostics: whitelisted snapshot, worker-only I/O, exact support-v1 ZIP, explicit save/HTML, existing ZIP viewer and closed-window completion passed')
