from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import base64
import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import zipfile

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton, QLabel, QPlainTextEdit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'houdini/python3.11libs'))
import dsh_downloads
import dsh_support_ui

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)
fixture = Path(os.environ['DSH_SUPPORT_QT_ROOT'])
payload = b'DSH download evidence\n' * 30000


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/zip')
        self.send_header('Content-Disposition', 'attachment; filename="../evidence.zip"')
        self.send_header('Content-Length', str(len(payload) + (10000 if self.path == '/broken' else 0)))
        self.end_headers()
        try:
            if self.path == '/slow':
                for offset in range(0, len(payload), 10000):
                    self.wfile.write(payload[offset:offset+10000]);self.wfile.flush();time.sleep(.04)
            else:
                self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Qt condition timeout')


server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
view = QWebEngineView()
profile = QWebEngineProfile(view)
dsh_downloads.install(profile,view)
page = QWebEnginePage(profile,view)
view.setPage(page)
view.resize(700,400)
view.show()
base = 'http://127.0.0.1:'+str(server.server_address[1])
observed = []
profile.downloadRequested.connect(lambda item: observed.append(item))
original_dialog = QFileDialog.getSaveFileName
try:
    destination = fixture/'实际下载.zip'
    QFileDialog.getSaveFileName = lambda *_args,**_kwargs:(str(destination),'')
    page.download(QUrl(base+'/file'))
    wait_for(lambda: observed and observed[-1].isFinished())
    assert observed[-1].state() == observed[-1].DownloadState.DownloadCompleted
    assert destination.read_bytes() == payload
    assert any('已保存' in label.text() for label in view.findChildren(QLabel))
    QFileDialog.getSaveFileName = lambda *_args,**_kwargs:('','')
    before = len(observed)
    page.download(QUrl(base+'/file'))
    wait_for(lambda:len(observed)>before)
    assert len(list(fixture.glob('*.zip'))) == 1
    (fixture/'blocked').write_text('not a directory')
    QFileDialog.getSaveFileName = lambda *_args,**_kwargs:(str(fixture/'blocked'/'broken.zip'),'')
    before = len(observed)
    page.download(QUrl(base+'/file'))
    wait_for(lambda:len(observed)>before and observed[-1].isFinished())
    assert observed[-1].state() in (observed[-1].DownloadState.DownloadInterrupted, observed[-1].DownloadState.DownloadCancelled), (str(observed[-1].state()),observed[-1].downloadDirectory(),observed[-1].downloadFileName())
    assert any('下载失败' in label.text() for label in view.findChildren(QLabel))
    QFileDialog.getSaveFileName = lambda *_args,**_kwargs:(str(fixture/'cancelled.zip'),'')
    before = len(observed)
    page.download(QUrl(base+'/slow'))
    wait_for(lambda:len(observed)>before and observed[-1].receivedBytes()>0)
    buttons = [button for button in view.findChildren(QPushButton) if button.text()=='取消下载']
    assert buttons
    buttons[-1].click()
    wait_for(lambda:observed[-1].isFinished())
    assert observed[-1].state() == observed[-1].DownloadState.DownloadCancelled
    dialog = dsh_support_ui.show(parent=view,source_root=fixture,startup_error='offline bridge token=SECRET_SENTINEL')
    save = next(button for button in dialog.findChildren(QPushButton) if button.text()=='保存报告…')
    assert save.isEnabled(), 'saving must not require a separate preview step'
    assert not any(widget.isReadOnly() and widget.isVisible() for widget in dialog.findChildren(QPlainTextEdit))
    QFileDialog.getSaveFileName = lambda *_args,**_kwargs:(str(fixture/'offline-report.zip'),'')
    save.click()
    wait_for(lambda:(fixture/'offline-report.zip').exists() and save.isEnabled())
    assert zipfile.is_zipfile(fixture/'offline-report.zip')
    with zipfile.ZipFile(fixture/'offline-report.zip') as archive:
        content = '\n'.join(archive.read(name).decode('utf-8') for name in archive.namelist())
        assert 'SECRET_SENTINEL' not in content and 'offline bridge' in content
        assert 'session_not_collected_from_native_window' in content
    assert dialog.grab().save(str(fixture/'support-dialog.png'))
    inspect = next(button for button in dialog.findChildren(QPushButton) if button.text()=='查看报告内容')
    inspect.click()
    assert not any(widget.isReadOnly() and widget.isVisible() for widget in dialog.findChildren(QPlainTextEdit))
    next(button for button in dialog.findChildren(QPushButton) if button.text()=='出错前后发生了什么    查看').click()
    app.processEvents()
    reader = next(widget for widget in dialog.findChildren(QPlainTextEdit) if widget.accessibleName()=='出错前后发生了什么详情')
    assert reader.isVisible() and 'offline bridge' in reader.toPlainText()
    reader.verticalScrollBar().setValue(reader.verticalScrollBar().maximum())
    collapse = next(button for button in dialog.findChildren(QPushButton) if button.text()=='收起详情')
    close_button = next(button for button in dialog.findChildren(QPushButton) if button.text()=='关闭')
    assert collapse.isVisible() and close_button.isVisible() and save.isVisible()
    assert dialog.grab().save(str(fixture/'support-details.png'))
    collapse.click()
    assert not reader.isVisible()
    inspect.click()
    editor = next(widget for widget in dialog.findChildren(QPlainTextEdit) if not widget.isReadOnly())
    editor.setPlainText('changed report scope')
    assert save.isEnabled(), 'edited scope must be collected by the next save, not disable saving'
    QFileDialog.getSaveFileName = lambda *_args,**_kwargs:(str(fixture/'changed-report.zip'),'')
    save.click()
    wait_for(lambda:(fixture/'changed-report.zip').exists() and save.isEnabled())
    with zipfile.ZipFile(fixture/'changed-report.zip') as archive:
        assert 'changed report scope' in archive.read('issue.md').decode('utf-8')
    dialog.close()
    print(json.dumps({'ok':True,'qt':profile.httpUserAgent(),'artifact':str(fixture)},ensure_ascii=True),flush=True)
finally:
    QFileDialog.getSaveFileName = original_dialog
    view.close()
    page.deleteLater()
    app.processEvents()
    server.shutdown()
