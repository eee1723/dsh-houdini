"""在 Houdini GUI 里内嵌 dsh web UI（QWebEngineView 加载 http://127.0.0.1:3081）。

- 仅适用于带 Qt GUI 的 Houdini（hython 无 GUI，show 时会明确报错）。
- QWebEngineView 只能在主线程创建/操作；Houdini 菜单和 Python Shell 都在主线程，
  直接调用即可。
- 幂等：重复调用唤起已有窗口，不重复创建。
- 完整启动传 workspace_dir；client 使用 DSH 原生工作区/任务状态处理归档与 Houdini preset。
- 同 HIP 的已有页面（包括隐藏的窗口）只唤起，保留当前浏览任务、输入草稿和滚动。
- 前端未就绪时每 2s 自动重试加载，直到连上（配合 launcher 的完整启动路径）。

用法（Houdini GUI 菜单或 Python Shell，主线程）：
    import dsh_webview
    dsh_webview.show_webview()
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.parse
import uuid
import dsh_managed_runtime

from PySide6.QtCore import QCoreApplication, Qt, QThread, QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 3081
_MANAGED = dsh_managed_runtime.context()
if _MANAGED:
    FRONTEND_PORT = _MANAGED["frontendPort"]
FRONTEND_URL = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"
SESSION_HINT_PARAM = "dsh-houdini-session"
WORKSPACE_HINT_PARAM = "dsh-houdini-workspace"
REQUEST_HINT_PARAM = "dsh-houdini-request"

_RETRY_INTERVAL_MS = 2000

# 性能实测（2026-08-18，经桥在真实 Houdini webview 里测）：设置弹窗的遮罩用
# backdrop-filter 全屏毛玻璃，Houdini 的 QtWebEngine 6.5.3（Chrome 108）走软件
# 光栅，每次滚动都对整屏背景重新模糊 —— 滚动 FPS 6 → 关闭后 45。遮罩仍保留
# 半透明底色，只是没有模糊，观感几乎无损。SPA 单页注入一次即可。
_DISABLE_BACKDROP_FILTER_JS = """
(function(){
  if (document.getElementById('dsh-perf-no-backdrop-filter')) return;
  var s = document.createElement('style');
  s.id = 'dsh-perf-no-backdrop-filter';
  s.textContent = '* { -webkit-backdrop-filter: none !important; backdrop-filter: none !important; }';
  document.head.appendChild(s);
})()
"""

# H21 内嵌 QtWebEngine 6.5.3 = Chrome 108：dsh-client-connection 的 postJson 用
# AbortSignal.any（Chrome 116+），缺失时发消息即报
# "AbortSignal.any is not a function (internal)"。在 DocumentCreation 注入
# 规范语义的 polyfill（早于页面任何脚本执行）。AbortSignal.timeout 108 已有，
# 不重复 polyfill。
_POLYFILL_ABORT_SIGNAL_ANY_JS = """
(function(){
  if (typeof AbortSignal === 'undefined' || typeof AbortSignal.any === 'function') return;
  AbortSignal.any = function(signals){
    var controller = new AbortController();
    var list = Array.from(signals || []);
    for (var i = 0; i < list.length; i++) {
      if (list[i].aborted) { controller.abort(list[i].reason); return controller.signal; }
    }
    var onAbort = function(ev){ controller.abort(ev.target.reason); };
    for (var j = 0; j < list.length; j++) {
      list[j].addEventListener('abort', onAbort, { once: true });
    }
    return controller.signal;
  };
})()
"""

# DSH 0.1.2 的新版 client/runtime 及 vision-toolkit 间接使用 ES2024
# Promise.withResolvers。H21/H22 的 QtWebEngine 6.5.3（Chrome 108）没有该
# API，会在 Cordis inventory 建立前抛错，随后所有 RPC 都退化成 Failed to
# fetch。与 AbortSignal.any 一样必须在 DocumentCreation、MainWorld 注入。
_POLYFILL_PROMISE_WITH_RESOLVERS_JS = """
(function(){
  if (typeof Promise === 'undefined' || typeof Promise.withResolvers === 'function') return;
  Object.defineProperty(Promise, 'withResolvers', {
    configurable: true,
    writable: true,
    value: function(){
      var C = this;
      var resolve, reject;
      var promise = new C(function(res, rej){ resolve = res; reject = rej; });
      return { promise: promise, resolve: resolve, reject: reject };
    }
  });
})()
"""

_window: QWidget | None = None
_view: QWebEngineView | None = None
_retry_timer: QTimer | None = None
_target_url = FRONTEND_URL
_after_auth_url: str | None = None
_quit_connected = False
_workspace_dir: str | None = None
_load_failed = False


def _dispose_webview() -> None:
    """Release our page before its profile/application; do not touch other views."""
    global _window, _view, _retry_timer, _after_auth_url, _workspace_dir, _load_failed
    window, view, timer = _window, _view, _retry_timer
    _window = _view = _retry_timer = None
    _after_auth_url = None
    _workspace_dir = None
    _load_failed = False
    if timer is not None:
        timer.stop()
    if view is not None:
        view.stop()
    if window is not None:
        window.close()
        window.deleteLater()


def _on_main_thread() -> bool:
    app = QCoreApplication.instance()
    return app is not None and QThread.currentThread() is app.thread()


def _retry_load() -> None:
    """QWebEngine 异步加载失败后重试；GUI 线程不做 socket 探测。"""
    if _view is None or _window is None or not _window.isVisible():
        return
    _view.load(QUrl(_target_url))


def _load_finished(ok: bool) -> None:
    """Run the page patch on success, or schedule one cancellable async retry."""
    global _target_url, _after_auth_url, _load_failed
    _load_failed = not ok
    if ok:
        if _retry_timer is not None:
            _retry_timer.stop()
        if _after_auth_url is not None and _view is not None:
            target = _after_auth_url
            _after_auth_url = None
            _target_url = target
            # The token exchange already redirects to the app. Navigating here
            # bootstraps it twice and aborts its inventory/inspect RPCs. The
            # The first document already has its intent; the client selects the
            # task when the native workspace/session snapshots arrive.
        if _view is not None:
            _clear_launch_session_hint(_view)
            _view.page().runJavaScript(_DISABLE_BACKDROP_FILTER_JS)
        return
    if (_retry_timer is not None and _window is not None
            and _window.isVisible() and not _retry_timer.isActive()):
        _retry_timer.start(_RETRY_INTERVAL_MS)


def _bring_to_front(win: QWidget) -> None:
    """把窗口带到 Houdini 主窗口之上。

    Windows 的焦点策略下，新顶层窗口常被已在前台的主窗口压住；短暂开一下
    置顶再立刻取消，是最可靠的提神方式（不会常驻置顶）。
    """
    win.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    win.show()
    win.raise_()
    win.activateWindow()
    win.setWindowFlag(Qt.WindowStaysOnTopHint, False)
    win.show()


def raise_workspace(workspace_dir: str | None = None) -> bool:
    """Raise our existing page without authentication, navigation or session IO."""
    if _window is None or _view is None:
        return False
    if workspace_dir is not None and _workspace_dir != os.path.normcase(os.path.abspath(workspace_dir)):
        return False
    _bring_to_front(_window)
    if _load_failed and _retry_timer is not None and not _retry_timer.isActive():
        _retry_timer.start(0)
    return True


def _navigation_url(workspace_dir: str | None, session_id: str | None) -> str:
    query = {}
    if workspace_dir is not None:
        query[WORKSPACE_HINT_PARAM] = workspace_dir
    elif session_id is not None:
        query[SESSION_HINT_PARAM] = session_id
    if not query:
        return FRONTEND_URL
    # A manual retry keeps one prospective Session identity, including after a
    # create response is lost. This is a navigation attempt, not a second registry.
    query[REQUEST_HINT_PARAM] = "dsh-houdini-" + uuid.uuid4().hex
    return FRONTEND_URL + "?" + urllib.parse.urlencode(query)


def _install_abort_signal_polyfill(view: QWebEngineView) -> None:
    """在 DocumentCreation 注入 QtWebEngine 缺失的 Web runtime API。"""
    script = QWebEngineScript()
    script.setName("dsh-qtwebengine-runtime-polyfills")
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setRunsOnSubFrames(False)
    script.setSourceCode(
        _POLYFILL_ABORT_SIGNAL_ANY_JS + ";\n" + _POLYFILL_PROMISE_WITH_RESOLVERS_JS
        + ";\n" + Path(__file__).with_name("dsh_iterator_polyfill.js").read_text(encoding="utf-8")
    )
    view.page().scripts().insert(script)


def _clear_launch_session_hint(view: QWebEngineView) -> None:
    scripts = view.page().scripts()
    for prior in scripts.find("dsh-launch-session-hint"):
        scripts.remove(prior)


def _install_launch_session_hint(view: QWebEngineView, target_url: str | None) -> None:
    """Put one navigation intent in the redirected app URL before its JS runs.

    DSH's token exchange redirects to /, dropping query parameters. Only the
    same-origin non-token app document receives the hint; no fetch, second
    navigation, token embedding, or synchronous GUI-thread networking.
    """
    _clear_launch_session_hint(view)
    if target_url is None:
        return
    script = QWebEngineScript()
    script.setName("dsh-launch-session-hint")
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setRunsOnSubFrames(False)
    script.setSourceCode("""
(function(){
  var target = new URL(%s);
  var current = new URL(window.location.href);
  if (current.origin !== target.origin || current.pathname !== target.pathname
      || current.searchParams.has('token')) return;
  ['dsh-houdini-workspace', 'dsh-houdini-session', 'dsh-houdini-request'].forEach(function(key){
    if (target.searchParams.has(key)) current.searchParams.set(key, target.searchParams.get(key));
  });
  window.history.replaceState(window.history.state, '', current.pathname + current.search + current.hash);
  // User intent can arrive before the client plugin finishes loading. Carry only
  // this document's cancellation bit, never a second copy of DSH session state.
  var intent = {id: target.searchParams.get('dsh-houdini-request'), cancelled: false};
  var cancel = function(event){
    if (['Tab', 'Shift', 'Control', 'Alt', 'Meta'].includes(event.key)) return;
    intent.cancelled = true;
  };
  window.addEventListener('pointerdown', cancel, true);
  window.addEventListener('keydown', cancel, true);
  intent.dispose = function(){
    window.removeEventListener('pointerdown', cancel, true);
    window.removeEventListener('keydown', cancel, true);
  };
  window.__dshHoudiniLaunchIntent = intent;
})()
""" % json.dumps(target_url))
    view.page().scripts().insert(script)


def show_webview(
    session_id: str | None = None,
    authenticated_url: str | None = None,
    *, workspace_dir: str | None = None, force_reload: bool = False,
) -> str:
    """唤起当前工作区页面；新导航/Repair 先认证，再由 client 选择任务。"""
    if QCoreApplication.instance() is None:
        raise RuntimeError(
            "dsh_webview 需要 Qt GUI：当前是 hython/无 UI 进程，无法内嵌 web UI。"
            "请在 Houdini GUI 的菜单或 Python Shell 里调用。"
        )
    if not _on_main_thread():
        raise RuntimeError(
            "show_webview() 必须在主线程调用（Houdini 菜单 / Python Shell 即主线程）。"
        )

    global _window, _view, _retry_timer, _target_url, _after_auth_url, _quit_connected, _workspace_dir, _load_failed
    if (not force_reload and session_id is None
            and (workspace_dir is not None or authenticated_url is None)
            and raise_workspace(workspace_dir)):
        return "webview already open"
    target_url = _navigation_url(workspace_dir, session_id)
    initial_url = authenticated_url or target_url

    if _window is None:
        win = QWidget()
        win.setWindowTitle("DSH-Houdini")
        view = QWebEngineView(win)
        # Never share Houdini's disk-based default browser profile between
        # processes/versions. Server-side DSH data remains persistent; browser
        # cookies/cache are scoped to this one plugin window's lifetime.
        # The view is created before the profile so its page is destroyed first.
        profile = QWebEngineProfile(win)
        view.setPage(QWebEnginePage(profile, view))
        _install_abort_signal_polyfill(view)
        # QWebEngine 的网络加载是异步的：成功后注入性能修复 CSS，失败则由
        # cancellable QTimer 重试。主线程不再同步探测 localhost 端口。
        retry_timer = QTimer(view)
        retry_timer.setSingleShot(True)
        retry_timer.timeout.connect(_retry_load)
        view.loadFinished.connect(_load_finished)
        lay = QVBoxLayout(win)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(view)
        win.resize(1200, 800)
        _window = win
        _view = view
        _retry_timer = retry_timer
        if not _quit_connected:
            QCoreApplication.instance().aboutToQuit.connect(_dispose_webview)
            _quit_connected = True

    _after_auth_url = target_url if authenticated_url is not None else None
    _install_launch_session_hint(_view, target_url if workspace_dir is not None or session_id is not None else None)
    _workspace_dir = os.path.normcase(os.path.abspath(workspace_dir)) if workspace_dir is not None else None
    _target_url = initial_url
    _load_failed = False
    _retry_timer.stop()
    _bring_to_front(_window)
    _view.load(QUrl(_target_url))
    return "opened authenticated DSH workspace" if authenticated_url else f"opened {target_url}"


if __name__ == "__main__":
    print(show_webview())
