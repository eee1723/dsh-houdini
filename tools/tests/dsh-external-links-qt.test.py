"""Real H21/H22 Qt popup handoff, including DSH's delayed BrowserLogin.

Only an owned loopback fixture is requested. QDesktopServices is intercepted;
no account, model, browser, Houdini process or HIP is opened. The login helper
is extracted unchanged from the exact installed DSH client bundle.

python tools/tests/dsh-external-links-qt.test.py \
  --python D:/houdini/python311/python.exe --python D:/Houdini22/python313/python.exe
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli


def browser_login_source():
    package = ROOT / 'node_modules/@deepseek-ai/dsh-client-ui-settings-account'
    version = json.loads((package / 'package.json').read_text(encoding='utf-8'))['version']
    assert version == '0.2.1-rc.2', 'Requalify this fixture against the preferred DSH login helper'
    bundle = (package / 'lib/client.js').read_text(encoding='utf-8')
    start = bundle.index('var BrowserLogin = class {')
    end = bundle.index('//#endregion', start)
    source = bundle[start:end].strip()
    assert 'window.open("about:blank", "_blank")' in source
    assert 'this.popup.location.replace(this.destination(attempt.authorizeUrl))' in source
    return version, source


def worker(output):
    if os.name == 'nt':
        dll_directory = os.add_dll_directory(str(Path(os.environ['HFS']) / 'bin'))
    from PySide6 import __version__ as qt_binding
    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QPoint, QTimer, Qt
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtTest import QTest
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWidgets import QApplication
    import dsh_webview as webview

    version, login = browser_login_source()
    requests, opened, window_requests, renderer_failures, loads = [], [], [], [], []
    rpc_received = threading.Event()
    rpc_release = threading.Event()
    login_url = 'https://login.example.invalid/authorize?attempt=isolated-qt&theme=dark'
    fixture = '''<!doctype html><meta charset="utf-8"><style>
      button,a {display:block; width:350px; height:36px; margin:12px}
      </style><script>window.fixtureErrors=[];window.onerror=(message)=>fixtureErrors.push(String(message));</script>
      <h1>Isolated DSH login popup fixture</h1>
      <button id="login">Start delayed account login</button>
      <a id="direct" target="_blank" href="http://links.example.invalid/help">Direct HTTP link</a>
      <button id="cancel">Cancel blank account popup</button>
      <button id="file">Reject file popup</button>
      <button id="credentials">Reject URL credentials</button>
      <script>LOGIN_SOURCE
      window.probe={marker:'main-document-preserved',done:false};
      const browserLogin=window.browserLogin=new BrowserLogin(value=>value);
      document.querySelector('#login').onclick=()=>{
        browserLogin.start(()=>fetch('/mock-account-start').then(reply=>reply.json()),()=>null)
          .then(()=>probe.done=true,error=>probe.error=String(error));
      };
      document.querySelector('#cancel').onclick=()=>{browserLogin.begin();probe.blankOpened=true};
      document.querySelector('#file').onclick=()=>window.open('file:///C:/isolated-fixture.txt','_blank');
      document.querySelector('#credentials').onclick=()=>window.open('https://user:password@links.example.invalid/','_blank');
      </script>'''.replace('LOGIN_SOURCE', login)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            requests.append(self.path)
            if self.path == '/mock-account-start':
                rpc_received.set()
                if not rpc_release.wait(10):
                    self.send_error(504)
                    return
                body = json.dumps({'attempt': {'id': 'isolated-login', 'phase': 'waiting-browser',
                                               'authorizeUrl': login_url}}).encode()
                mime = 'application/json'
            elif self.path.startswith('/favicon'):
                self.send_response(204)
                self.end_headers()
                return
            else:
                body, mime = fixture.encode(), 'text/html; charset=utf-8'
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    base = 'http://127.0.0.1:' + str(server.server_address[1])
    result = {'ok': False, 'dshVersion': version, 'qtBinding': qt_binding, 'cases': []}

    def pump(milliseconds=30):
        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def wait(predicate, label, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            pump()
        raise AssertionError('Timed out: ' + label)

    def javascript(source):
        values = []
        # JSON also preserves booleans across H21/H22's different QVariant
        # conversions; a native callback is not itself a JavaScript truth test.
        page.runJavaScript('JSON.stringify(eval(' + json.dumps(source) + '))', 0, values.append)
        wait(lambda: bool(values), 'JavaScript callback')
        return json.loads(values[0]) if values[0] else None

    def click(identifier):
        point = json.loads(javascript("JSON.stringify((()=>{const r=document.getElementById("
            + json.dumps(identifier) + ").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})())"))
        target = webview._view.focusProxy() or webview._view
        QTest.mouseClick(target, Qt.LeftButton, Qt.NoModifier, QPoint(round(point['x']), round(point['y'])))
        pump()

    def main_unchanged():
        assert webview._view.page() is page, 'external link replaced the main page object'
        assert page.url().toString() == base + '/', page.url().toString()
        assert javascript('window.probe.marker') == 'main-document-preserved'
        assert requests.count('/') == 1, requests
        assert not renderer_failures, renderer_failures

    try:
        with patch.object(QDesktopServices, 'openUrl', side_effect=lambda url: opened.append(url.toString()) or True):
            webview.show_webview(frontend_url=base, authenticated_url=base + '/', standalone=True)
            window = webview._window
            window.move(12000, 12000)
            page = webview._view.page()
            page.loadFinished.connect(loads.append)
            page.renderProcessTerminated.connect(lambda status, code: renderer_failures.append([str(status), code]))
            page.newWindowRequested.connect(lambda request: window_requests.append({
                'url': request.requestedUrl().toString(), 'userInitiated': request.isUserInitiated()}))
            wait(lambda: any(loads), 'fixture page load')
            wait(lambda: javascript("Boolean(window.probe && document.getElementById('login'))") is True,
                 'fixture JavaScript initialization')
            assert page.profile().isOffTheRecord()

            click('login')
            wait(rpc_received.is_set, 'local delayed start RPC')
            pending = window._dsh_external_links
            assert len(pending) == 1 and not opened, {'pending': len(pending), 'opened': opened}
            assert any(item['userInitiated'] and item['url'] in ('', 'about:blank') for item in window_requests), window_requests
            assert javascript('Boolean(browserLogin.popup && !browserLogin.popup.closed)') is True
            main_unchanged()
            rpc_release.set()
            wait(lambda: len(opened) == 1, 'delayed popup location.replace to system browser')
            wait(lambda: not pending, 'navigated popup disposal')
            assert opened == [login_url], opened
            wait(lambda: javascript('window.probe.done') is True, 'BrowserLogin.start completion')
            assert javascript('browserLogin.navigated') is True
            assert not javascript('window.probe.error'), javascript('window.probe.error')
            main_unchanged()
            result['cases'].append('actual BrowserLogin preopen -> delayed local RPC -> popup.location.replace')

            click('direct')
            wait(lambda: len(opened) == 2, 'direct HTTP link handoff')
            assert opened[-1] == 'http://links.example.invalid/help', opened
            assert not pending
            main_unchanged()
            result['cases'].append('direct user HTTP target=_blank')

            click('cancel')
            wait(lambda: len(pending) == 1, 'new empty popup')
            assert javascript('Boolean(browserLogin.popup && !browserLogin.popup.closed)') is True
            javascript('browserLogin.dispose(); true')
            wait(lambda: not pending, 'cancelled blank popup disposal')
            assert len(opened) == 2
            main_unchanged()
            result['cases'].append('cancel closes and disposes the preopened blank popup')

            page.settings().setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)
            request_count = len(window_requests)
            javascript("window.open('https://unrequested.example.invalid/','_blank'); true")
            pump(250)
            assert len(opened) == 2 and not pending
            assert len(window_requests) > request_count and window_requests[-1]['userInitiated'] is False, window_requests
            result['cases'].append('non-user-initiated HTTP popup refused')
            click('file')
            pump(250)
            assert len(opened) == 2 and not pending
            result['cases'].append('file scheme popup refused')
            click('credentials')
            pump(250)
            assert len(opened) == 2 and not pending
            main_unchanged()
            result['cases'].append('HTTP URL with embedded credentials refused')
            result.update(ok=True, opened=opened, windowRequests=window_requests,
                          mainPageUnchanged=True, pendingPopups=len(pending), offTheRecord=True,
                          mainDocumentRequests=requests.count('/'), requests=requests)
    except Exception:
        result['error'] = traceback.format_exc()
        result.update(requests=requests, loads=loads, rendererFailures=renderer_failures)
        if any(loads) and not renderer_failures:
            result['fixtureState'] = javascript("JSON.stringify({errors:window.fixtureErrors,probe:window.probe,login:typeof BrowserLogin,url:location.href})")
    finally:
        rpc_release.set()
        if webview._retry_timer is not None:
            webview._retry_timer.stop()
        webview._dispose_webview()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
        Path(output).write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return 0 if result['ok'] else 1


def main():
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, action='append', default=[])
    parser.add_argument('--worker', type=Path)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker)
    assert args.python, 'Provide the H21/H22 ordinary Python executables'
    from dsh_workbench import desktop_environment
    root = Path(tempfile.mkdtemp(prefix='external-links-qt-', dir=ROOT / 'tools/out'))
    failures = []
    for python in args.python:
        python = python.resolve(strict=True)
        hfs = python.parent.parent
        folder = root / hfs.name
        environment = isolated_environment(folder / 'environment', gui=True)
        with patch.dict(os.environ, environment, clear=True):
            environment = desktop_environment(hfs, python)
        output = folder / 'result.json'
        process = subprocess.run([str(python), str(Path(__file__).resolve()), '--worker', str(output)],
            cwd=hfs / 'bin', env=environment, capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=90, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        print(hfs.name, process.stdout, flush=True)
        (folder / 'qt.log').write_text(process.stderr, encoding='utf-8')
        if process.returncode:
            failures.append({'hfs': str(hfs), 'exitCode': process.returncode, 'output': str(output),
                             'stderr': process.stderr[-4000:]})
    print('Evidence:', root, flush=True)
    assert not failures, json.dumps(failures, ensure_ascii=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
