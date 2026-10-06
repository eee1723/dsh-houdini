"""Isolated real QtWebEngine auth redirect and startup-RPC regression.

Run with hython and QT_QPA_PLATFORM=offscreen, using isolated Houdini prefs.
Only a local fixture server is used; never connects to the user's DSH or HIP.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import sys
import threading
import time
import urllib.parse

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))
import dsh_webview as webview

requests = []
TOKEN = "isolated-fixture-token"
fail_auth_once = False

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        global fail_auth_once
        if self.path == "/?token=" + TOKEN:
            if fail_auth_once:
                fail_auth_once = False
                self.send_response(503)
                self.end_headers()
                return
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", "fixture_auth=1; Path=/; HttpOnly; SameSite=Strict")
            self.end_headers()
            return
        if "fixture_auth=1" not in (self.headers.get("Cookie") or ""):
            self.send_response(401)
            self.end_headers()
            return
        if self.path.startswith("/favicon"):
            self.send_response(204)
            self.end_headers()
            return
        requests.append(self.path)
        body = b'''<!doctype html><script>
        window.probe = {urlAtBoot: location.href, done: false, intents: []};
        window.addEventListener('dsh-houdini-open-workspace', function () {
          probe.intents.push(location.href);
        });
        try {
          probe.resourceHost = new URL('dsh-resource://file/session/fixture/example.txt').hostname;
          probe.reviewHost = new URL('dsh-resource://changes-review/session/fixture/1/1').hostname;
          var ordinary = new URL('https://example.com/path'); ordinary.hostname = 'example.org';
          probe.ordinaryHost = ordinary.hostname;
          // PDF.js module-evaluation failure and its later iterator helper use.
          if (typeof Iterator.prototype.join !== 'function') Iterator.prototype.join = function(s) {return [...this].join(s);};
          probe.iterator = [1,2].values().map(x => x*2).toArray().join(',');
          probe.iteratorSome = new Map([[1,2]]).values().some(x => x === 2);
          const providers = ['custom', 'deepseek-official', 'deepseek-account'];
          const rank = id => id === 'deepseek-account' ? 0 : id === 'deepseek-official' ? 1 : 2;
          probe.modelProviders = providers.toSorted((a,b) => rank(a) - rank(b)).join(',');
          probe.originalProviders = providers.join(',');
        } catch(e) { probe.iteratorError = String(e); }
        Promise.all(['/api/inventory', '/api/syncInspectManifest'].map(path =>
          fetch(path, {method:'POST', body:'{}'}).then(r => r.json())))
          .then(() => {probe.done = true;}, e => {probe.error = String(e);});
        </script><p>isolated startup fixture</p>'''
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        time.sleep(0.3)  # Keep initialization requests in flight at loadFinished.
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)
base = "http://127.0.0.1:" + str(server.server_address[1])
webview.FRONTEND_URL = base

def settle():
    rows = []
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(100)
    def received(value):
        if not value:
            return
        observed=json.loads(value)
        if observed.get('done') or observed.get('error'):
            rows.append(observed)
            loop.quit()
    def probe():
        webview._view.page().runJavaScript(
            "window.probe && JSON.stringify(Object.assign({}, window.probe, {urlNow: location.href}))",
            0, received)
    poll.timeout.connect(probe)
    poll.start()
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    poll.stop()
    assert rows, f"fixture did not complete at {webview._view.url().toString()}; requests={requests} failed={webview._load_failed}"
    return rows[-1]

try:
    webview.show_webview(session_id="task /中文?&", authenticated_url=base + "/?token=" + TOKEN)
    webview.show_webview()  # Reopen before the initial auth/redirect has completed.
    observed = settle()
    assert len(requests) == 1, f"auth bootstrap loaded the app {len(requests)} times: {requests}"
    assert observed["done"] and "error" not in observed, observed
    assert observed.get("iterator") == "2,4" and observed.get("iteratorSome") is True, observed
    assert observed.get("modelProviders") == "deepseek-account,deepseek-official,custom", observed
    assert observed.get("originalProviders") == "custom,deepseek-official,deepseek-account", observed
    assert observed.get("resourceHost") == "file", observed
    assert observed.get("reviewHost") == "changes-review" and observed.get("ordinaryHost") == "example.org", observed
    assert "iteratorError" not in observed, observed
    assert "dsh-houdini-session=task" in observed["urlAtBoot"], observed
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(observed["urlAtBoot"]).query)["dsh-houdini-session"] == ["task /中文?&"]
    assert "token=" not in observed["urlAtBoot"], "launch token must not reach the app URL"
    assert not webview._view.page().scripts().find("dsh-launch-session-hint"), "one-navigation hint must be retired"

    # Tools remain above Houdini, but background page callbacks honor the user's
    # minimize. An explicit Open Workspace restores the same page and draft.
    flags = webview._window.windowFlags()
    assert not flags & Qt.WindowStaysOnTopHint and flags & Qt.WindowMinimizeButtonHint
    assert flags & Qt.WindowCloseButtonHint and flags & Qt.WindowSystemMenuHint
    import hou
    owner = hou.qt.mainWindow() if hou.isUIAvailable() else None
    assert webview._window.isWindow() and webview._window.parentWidget() is owner
    window, view = webview._window, webview._view
    window.showMinimized()
    app.processEvents()
    assert window.isMinimized()
    webview._load_finished(True)
    webview._retry_load()
    observed = settle()
    assert window.isMinimized(), "background load must not restore a user-minimized tool"
    assert webview.raise_workspace()
    app.processEvents()
    assert not window.isMinimized() and window.isVisible()
    assert webview._window is window and webview._view is view
    assert window.windowFlags() == flags, "explicit reopen must not change owner or window hints"

    # Plain reopen does not reload or switch the existing selected task.
    webview.show_webview()
    assert settle() == observed
    assert len(requests) == 2
    # A new explicit target replaces the old hint without an extra app bootstrap.
    webview.show_webview(session_id="next", authenticated_url=base + "/?token=" + TOKEN)
    observed = settle()
    assert len(requests) == 3
    assert observed["done"] and urllib.parse.parse_qs(urllib.parse.urlsplit(observed["urlAtBoot"]).query)["dsh-houdini-session"] == ["next"]
    webview.show_webview(authenticated_url=base + "/?token=" + TOKEN)
    observed = settle()
    assert len(requests) == 4 and observed["urlAtBoot"] == base + "/"
    assert observed["done"]
    webview.show_webview(session_id="direct")
    observed = settle()
    assert len(requests) == 5 and observed["done"]
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(observed["urlAtBoot"]).query)["dsh-houdini-session"] == ["direct"]
    # A later ordinary document must not receive a stale injected session hint.
    webview._view.load(webview.QUrl(base + "/"))
    observed = settle()
    assert len(requests) == 6 and observed["urlAtBoot"] == base + "/"
    # Failed auth must retain the pending hint across the existing async retry.
    fail_auth_once = True
    webview._RETRY_INTERVAL_MS = 100
    webview.show_webview(session_id="retry", authenticated_url=base + "/?token=" + TOKEN)
    observed = settle()
    assert not fail_auth_once and len(requests) == 7
    assert observed["done"] and urllib.parse.parse_qs(urllib.parse.urlsplit(observed["urlAtBoot"]).query)["dsh-houdini-session"] == ["retry"]
    assert not webview._retry_timer.isActive()
    assert not webview._view.page().scripts().find("dsh-launch-session-hint")

    # Workspace requests publish fresh intents into the same loaded app. The
    # fixture observes delivery only; actual DSH selection is covered by the
    # real-client navigation regression, not a Python selected-workspace cache.
    workspace_a, workspace_b = r"E:\fixture A", r"E:\fixture B"
    webview.show_webview(workspace_dir=workspace_a, authenticated_url=base + "/?token=" + TOKEN)
    observed = settle()
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(observed["urlNow"]).query)
    assert len(requests) == 7 and query["dsh-houdini-workspace"] == [workspace_a]
    assert query["dsh-houdini-request"][0].startswith("dsh-houdini-")
    assert "dsh-houdini-session" not in query
    assert observed['intents']==[observed['urlNow']]
    prior_request=query['dsh-houdini-request'][0]
    assert webview.raise_workspace(workspace_a)
    webview._window.hide()
    webview.show_webview(workspace_dir=workspace_a, authenticated_url=base + "/?token=" + TOKEN)
    repeated=settle()
    query=urllib.parse.parse_qs(urllib.parse.urlsplit(repeated['urlNow']).query)
    assert len(requests)==7 and len(repeated['intents'])==3
    assert query['dsh-houdini-workspace']==[workspace_a] and query['dsh-houdini-request'][0]!=prior_request
    assert webview.raise_workspace(workspace_b)
    webview.show_webview(workspace_dir=workspace_b, authenticated_url=base + "/?token=" + TOKEN)
    changed = settle()
    assert len(requests) == 7 and len(changed['intents'])==5
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(changed["urlNow"]).query)["dsh-houdini-workspace"] == [workspace_b]
    assert not webview._view.page().scripts().find('dsh-launch-session-hint'), 'loaded-page intent must not leak into a later document'
    webview.show_webview(workspace_dir=workspace_b, authenticated_url=base + "/?token=" + TOKEN, force_reload=True)
    restarted = settle()
    assert len(requests) == 8 and restarted["done"] and restarted['intents']==[]
    assert restarted["urlAtBoot"] != changed["urlNow"], "Repair needs a new navigation intent after auth"
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(restarted['urlNow']).query)['dsh-houdini-workspace']==[workspace_b]

    # A failed load while the window is hidden has no active retry timer. Raising
    # it must resume the existing intent, not strand an otherwise healthy host.
    fail_auth_once = True
    webview.show_webview(workspace_dir=workspace_a, authenticated_url=base + "/?token=" + TOKEN, force_reload=True)
    webview._window.hide()
    loop = QEventLoop()
    QTimer.singleShot(1000, loop.quit)
    loop.exec()
    assert webview._load_failed and not webview._retry_timer.isActive()
    assert webview.raise_workspace(workspace_a)
    recovered = settle()
    assert len(requests) == 9 and recovered["done"]
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(recovered["urlAtBoot"]).query)["dsh-houdini-workspace"] == [workspace_a]
    # An independently allocated loopback Host origin requires a new document.
    webview.FRONTEND_URL = 'http://127.0.0.1:1'
    assert not webview.raise_workspace(workspace_a)
    webview.show_webview(workspace_dir=workspace_a, authenticated_url=base + '/?token=' + TOKEN,
                         frontend_url=base, force_reload=True)
    assert settle()['done'] and len(requests) == 10
    assert webview.raise_workspace(workspace_a, frontend_url=base)
    assert not webview.raise_workspace(workspace_a)
    webview.FRONTEND_URL = base
    print("Qt WebView: one auth bootstrap, hidden-page reuse, HIP switch, Repair and native-client workspace hints passed")
finally:
    if webview._retry_timer is not None:
        webview._retry_timer.stop()
    if webview._view is not None:
        assert webview._view.page().profile().isOffTheRecord(), "plugin views must not share Houdini's persistent default profile"
    webview._dispose_webview()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    assert webview._view is None and webview._window is None
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
