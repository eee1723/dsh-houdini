"""在 Houdini GUI 里内嵌 dsh web UI（QWebEngineView 加载 http://127.0.0.1:3081）。

- 仅适用于带 Qt GUI 的 Houdini（hython 无 GUI，show 时会明确报错）。
- QWebEngineView 只能在主线程创建/操作；Houdini 菜单和 Python Shell 都在主线程，
  直接调用即可。
- 幂等：重复调用唤起已有窗口，不重复创建。
- 完整启动可传 session_id；URL hint 由 dsh-houdini client 半通过公开
  sessions.refresh/open 消费。无 id 的 Open Workspace 不重载、不切换当前会话。
- 前端未就绪时每 2s 自动重试加载，直到连上（配合 launcher 的完整启动路径）。

用法（Houdini GUI 菜单或 Python Shell，主线程）：
    import dsh_webview
    dsh_webview.show_webview()
"""

from __future__ import annotations

import urllib.parse

from PySide6.QtCore import QCoreApplication, Qt, QThread, QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 3081
FRONTEND_URL = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"
SESSION_HINT_PARAM = "dsh-houdini-session"

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
    global _target_url, _after_auth_url
    if ok:
        if _retry_timer is not None:
            _retry_timer.stop()
        if _after_auth_url is not None and _view is not None:
            target = _after_auth_url
            _after_auth_url = None
            _target_url = target
            _view.load(QUrl(target))
            return
        if _view is not None:
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


def _session_url(session_id: str | None) -> str:
    if not session_id:
        return FRONTEND_URL
    return FRONTEND_URL + "?" + urllib.parse.urlencode({SESSION_HINT_PARAM: session_id})


def _install_abort_signal_polyfill(view: QWebEngineView) -> None:
    """在 DocumentCreation 注入 QtWebEngine 缺失的 Web runtime API。"""
    script = QWebEngineScript()
    script.setName("dsh-qtwebengine-runtime-polyfills")
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setRunsOnSubFrames(False)
    script.setSourceCode(
        _POLYFILL_ABORT_SIGNAL_ANY_JS + ";\n" + _POLYFILL_PROMISE_WITH_RESOLVERS_JS
    )
    view.page().scripts().insert(script)


def show_webview(
    session_id: str | None = None,
    authenticated_url: str | None = None,
) -> str:
    """打开内嵌 UI；先建立 DSH 浏览器 cookie，再路由显式 session。"""
    if QCoreApplication.instance() is None:
        raise RuntimeError(
            "dsh_webview 需要 Qt GUI：当前是 hython/无 UI 进程，无法内嵌 web UI。"
            "请在 Houdini GUI 的菜单或 Python Shell 里调用。"
        )
    if not _on_main_thread():
        raise RuntimeError(
            "show_webview() 必须在主线程调用（Houdini 菜单 / Python Shell 即主线程）。"
        )

    global _window, _view, _retry_timer, _target_url, _after_auth_url
    target_url = _session_url(session_id)
    initial_url = authenticated_url or target_url
    if _window is not None and _window.isVisible():
        # A full service restart carries an explicit Host-created/reused
        # session target. Plain Open Workspace intentionally does not reload or
        # change the user's current conversation.
        if (session_id is not None or authenticated_url is not None) and _view is not None:
            _after_auth_url = target_url if authenticated_url is not None else None
            _target_url = initial_url
            _view.load(QUrl(_target_url))
        else:
            _after_auth_url = None
        _bring_to_front(_window)
        return (
            f"webview routed to {session_id}"
            if session_id is not None else "webview already open"
        )

    if _window is None:
        win = QWidget()
        win.setWindowTitle("DSH-Houdini")
        view = QWebEngineView()
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

    _after_auth_url = target_url if authenticated_url is not None else None
    _target_url = initial_url
    _bring_to_front(_window)
    _view.load(QUrl(_target_url))
    return "opened authenticated DSH workspace" if authenticated_url else f"opened {target_url}"


if __name__ == "__main__":
    print(show_webview())
