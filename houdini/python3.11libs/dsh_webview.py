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
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings, QWebEngineUrlScheme
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

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

# Keep the software-rendered Qt view free of expensive backdrop blur. DSH's
# shared menu materials depend on that blur to hide underlying text, so their
# fills must become opaque together (including the GoalBar pseudo-element).
# Use DSH's existing light/dark menu-header RGB, not component class hashes.
# Modal dimmers, disabled controls and hover overlays retain their own alpha.
_WEBVIEW_STYLE_JS = """
(function(){
  if (document.getElementById('dsh-qtwebengine-style')) return;
  var s = document.createElement('style');
  s.id = 'dsh-qtwebengine-style';
  s.textContent = `
    body {
      --dsw-menu-surface-fill: #f8f9fa !important;
      --dsw-specific-menu: #f8f9fa !important;
      --dsw-alias-menu-group-header-fill: #f8f9fa !important;
      --dsw-menu-backdrop-filter: none !important;
    }
    body[data-ds-dark-theme] {
      --dsw-menu-surface-fill: #303136 !important;
      --dsw-specific-menu: #303136 !important;
      --dsw-alias-menu-group-header-fill: #303136 !important;
    }
    *, *::before, *::after {
      -webkit-backdrop-filter: none !important;
      backdrop-filter: none !important;
    }
    /* Chromium 108 rejects the entire composer background when its zero-alpha
       stop uses color-mix(). Transparent is equivalent and supported. */
    @supports not (color: color-mix(in srgb, red, blue)) {
      [data-phase="active"] [data-composer-seat],
      [data-content-phase="active"] [data-composer-seat] {
        background-image: linear-gradient(180deg, transparent 0px, var(--dsw-alias-bg-base) 36px) !important;
      }
    }
  `;
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

# 当前 DSH client/runtime 间接使用 ES2024
# Promise.withResolvers。H21 的 Chrome 108 与 H22 的 Chrome 122 都缺少该
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

# Qt WebEngine may have initialized another page before this plugin opens its
# view. A then-late QWebEngineUrlScheme registration is ignored by Chromium:
# the virtual DSH address remains opaque and URL.hostname is empty. Keep the
# fallback strictly on dsh-resource addresses; it changes no fetch/navigation
# authority and never installs a local-file scheme handler.
_POLYFILL_DSH_RESOURCE_URL_JS = r"""
(function(){
  var probe = new URL('dsh-resource://file/session/probe/file.txt');
  if (probe.hostname === 'file') return;
  if (probe.protocol !== 'dsh-resource:' || probe.hostname !== '') return;
  var descriptor = Object.getOwnPropertyDescriptor(URL.prototype, 'hostname');
  if (!descriptor || !descriptor.configurable || typeof descriptor.get !== 'function') return;
  Object.defineProperty(URL.prototype, 'hostname', {
    configurable: descriptor.configurable,
    enumerable: descriptor.enumerable,
    get: function(){
      var host = descriptor.get.call(this);
      if (host !== '' || this.protocol !== 'dsh-resource:') return host;
      var match = /^dsh-resource:\/\/([a-z0-9][a-z0-9-]*)(?:\/|$)/i.exec(this.href);
      return match ? match[1].toLowerCase() : host;
    },
    set: descriptor.set && function(value){ descriptor.set.call(this, value); }
  });
})()
"""

_window: QWidget | None = None
_view: QWebEngineView | None = None
_retry_timer: QTimer | None = None
_target_url = FRONTEND_URL
_after_auth_url: str | None = None
_quit_connected = False
_active_frontend_url: str | None = None
_load_failed = False
_page_loading = False
_renderer_failed = False
_failure_panel = None
_failure_label = None


def _register_dsh_resource_scheme() -> None:
    """Give DSH's virtual resource addresses an authority in Qt WebEngine.

    The browser client uses ``new URL('dsh-resource://file/...').hostname`` to
    select its file provider. Qt's default custom-scheme Path syntax yields an
    empty hostname, so register Host syntax before creating a WebEngine page.
    No scheme handler is installed: file bytes still use authenticated Host RPC.
    """
    name = b"dsh-resource"
    current = QWebEngineUrlScheme.schemeByName(name)
    if current.name():
        if current.syntax() != QWebEngineUrlScheme.Syntax.Host:
            raise RuntimeError("dsh-resource URL scheme has incompatible Qt WebEngine syntax")
        return
    scheme = QWebEngineUrlScheme(name)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    QWebEngineUrlScheme.registerScheme(scheme)


def _dispose_webview() -> None:
    """Release our page before its profile/application; do not touch other views."""
    global _window, _view, _retry_timer, _after_auth_url, _active_frontend_url, _load_failed, _page_loading
    global _renderer_failed, _failure_panel, _failure_label
    window, view, timer = _window, _view, _retry_timer
    _window = _view = _retry_timer = None
    _after_auth_url = None
    _active_frontend_url = None
    _load_failed = False
    _page_loading = False
    _renderer_failed = False
    _failure_panel = _failure_label = None
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
    if _renderer_failed or _view is None or _window is None or not _window.isVisible():
        return
    _view.load(QUrl(_target_url))


def _load_started() -> None:
    global _page_loading
    _page_loading = True


def _load_finished(ok: bool) -> None:
    """Run the page patch on success, or schedule one cancellable async retry."""
    global _target_url, _after_auth_url, _load_failed, _page_loading
    _page_loading = False
    _load_failed = not ok
    if _renderer_failed:
        # A crashed renderer is not a transient Host/HTTP readiness failure.
        return
    if ok:
        if _retry_timer is not None:
            _retry_timer.stop()
        if _after_auth_url is not None and _view is not None:
            target = _after_auth_url
            _after_auth_url = None
            _target_url = target
            # The token exchange already redirects to the app. Navigating here
            # bootstraps it twice and aborts its inventory/inspect RPCs. The
            # first document already has its intent; the client selects the
            # task when the native workspace/session snapshots arrive.
        if _view is not None:
            _clear_launch_session_hint(_view)
            _view.page().runJavaScript(_WEBVIEW_STYLE_JS)
        return
    if (_retry_timer is not None and _window is not None
            and _window.isVisible() and not _retry_timer.isActive()):
        _retry_timer.start(_RETRY_INTERVAL_MS)


def _render_process_terminated(status, exit_code) -> None:
    """Keep a native recovery surface when the embedded renderer has exited."""
    global _renderer_failed, _load_failed, _page_loading
    if _view is None or _window is None:
        return
    _renderer_failed = _load_failed = True
    _page_loading = False
    if _retry_timer is not None:
        _retry_timer.stop()
    status_name = getattr(status, "name", str(status))
    diagnostic = f"{status_name} · 退出码 {exit_code} (0x{exit_code & 0xffffffff:08X})"
    if _failure_label is not None:
        _failure_label.setText("内嵌页面进程已退出，已停止自动重试。\n"
                               "可以重新加载页面；若仍失败，请在 Version & Updates... 的高级设置中查看运行诊断。\n"
                               + diagnostic)
    if _failure_panel is not None:
        _failure_panel.show()


def _retry_renderer() -> None:
    """User requested a fresh page load after a renderer failure."""
    global _renderer_failed, _load_failed
    _renderer_failed = _load_failed = False
    if _failure_panel is not None:
        _failure_panel.hide()
    _retry_load()


def _bring_to_front(win: QWidget) -> None:
    """显式打开恢复窗口；置顶规则由共享工具样式维护。"""
    from dsh_ui_style import show_tool_window
    show_tool_window(win)


def raise_workspace(workspace_dir: str | None = None, *, frontend_url: str | None = None) -> bool:
    """Raise the page, issuing an explicit directory intent when requested.

    True means the existing WebView accepted the request. DSH's actual selected
    session confirms completion in the client; Python keeps no selected-cwd cache.
    """
    global _after_auth_url
    if _window is None or _view is None:
        return False
    if _active_frontend_url != (frontend_url or FRONTEND_URL):
        return False
    _bring_to_front(_window)
    if workspace_dir is not None:
        target_url = _navigation_url(workspace_dir, None, frontend_url)
        # If auth/app initialization is still in flight, the next document must
        # receive the newest intent. A loaded app consumes the same intent now.
        _install_launch_session_hint(_view, target_url if _page_loading or _load_failed else None)
        if _after_auth_url is not None:
            _after_auth_url = target_url
        _view.page().runJavaScript(_launch_intent_js(target_url))
    if _load_failed and not _renderer_failed and _retry_timer is not None and not _retry_timer.isActive():
        _retry_timer.start(0)
    return True


def _navigation_url(workspace_dir: str | None, session_id: str | None, frontend_url: str | None = None) -> str:
    base = frontend_url or FRONTEND_URL
    query = {}
    if workspace_dir is not None:
        query[WORKSPACE_HINT_PARAM] = workspace_dir
    elif session_id is not None:
        query[SESSION_HINT_PARAM] = session_id
    if not query:
        return base
    # A manual retry keeps one prospective Session identity, including after a
    # create response is lost. This is a navigation attempt, not a second registry.
    query[REQUEST_HINT_PARAM] = "dsh-houdini-" + uuid.uuid4().hex
    return base + "?" + urllib.parse.urlencode(query)


def _install_abort_signal_polyfill(view: QWebEngineView) -> None:
    """在 DocumentCreation 注入 QtWebEngine 缺失的 Web runtime API。"""
    script = QWebEngineScript()
    script.setName("dsh-qtwebengine-runtime-polyfills")
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setRunsOnSubFrames(False)
    script.setSourceCode(
        _POLYFILL_ABORT_SIGNAL_ANY_JS + ";\n" + _POLYFILL_PROMISE_WITH_RESOLVERS_JS
        + ";\n" + _POLYFILL_DSH_RESOURCE_URL_JS
        # Generated core-js asset includes Iterator helpers and Array.toSorted,
        # which DSH's model selection/settings call during their first render.
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
    script.setSourceCode(_launch_intent_js(target_url))
    view.page().scripts().insert(script)


def _launch_intent_js(target_url: str) -> str:
    """Publish directory/session intent; only the client can confirm selection."""
    return """
(function(){
  var target = new URL(%s);
  var current = new URL(window.location.href);
  if (current.origin !== target.origin || current.pathname !== target.pathname
      || current.searchParams.has('token')) return;
  ['dsh-houdini-workspace', 'dsh-houdini-session', 'dsh-houdini-request'].forEach(function(key){
    current.searchParams.delete(key);
    if (target.searchParams.has(key)) current.searchParams.set(key, target.searchParams.get(key));
  });
  window.history.replaceState(window.history.state, '', current.pathname + current.search + current.hash);
  window.dispatchEvent(new Event('dsh-houdini-open-workspace'));
})()
""" % json.dumps(target_url)


def show_webview(
    session_id: str | None = None,
    authenticated_url: str | None = None,
    *, workspace_dir: str | None = None, force_reload: bool = False,
    frontend_url: str | None = None,
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

    global _window, _view, _retry_timer, _target_url, _after_auth_url, _quit_connected, _active_frontend_url, _load_failed, _page_loading
    global _renderer_failed, _failure_panel, _failure_label
    base = frontend_url or FRONTEND_URL
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.port is None or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('Embedded DSH frontend must be an exact loopback HTTP origin')
    if authenticated_url is not None:
        auth = urllib.parse.urlsplit(authenticated_url)
        if auth.scheme != parsed.scheme or auth.hostname != parsed.hostname or auth.port != parsed.port:
            raise ValueError('DSH launch token must belong to the selected frontend origin')
    if (not force_reload and session_id is None
            and (workspace_dir is not None or authenticated_url is None)
            and raise_workspace(workspace_dir, frontend_url=base)):
        return "webview already open"
    target_url = _navigation_url(workspace_dir, session_id, base)
    initial_url = authenticated_url or target_url

    if _window is None:
        _register_dsh_resource_scheme()
        import hou
        # A normal top-level window owned by Houdini stays above Houdini but
        # follows it behind other applications. Keep the independent minimize
        # and close behavior instead of making the WebView a child widget.
        parent = hou.qt.mainWindow() if hou.isUIAvailable() else None
        win = QWidget(parent, Qt.Window)
        win.setWindowTitle("DSH-Houdini · 工作区")
        from dsh_ui_style import style_dialog
        style_dialog(win)
        view = QWebEngineView(win)
        # Never share Houdini's disk-based default browser profile between
        # processes/versions. Server-side DSH data remains persistent; browser
        # cookies/cache are scoped to this one plugin window's lifetime.
        # The view is created before the profile so its page is destroyed first.
        profile = QWebEngineProfile(win)
        view.setPage(QWebEnginePage(profile, view))
        # DSH's shared copy helper uses navigator.clipboard.writeText. Qt
        # disables this by default: H21 rejects, H22 waits for an unanswered
        # ClipboardReadWrite request. Enable writes on our page; clipboard
        # reading/paste permission remains at Qt's default (disabled).
        view.page().settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        _install_abort_signal_polyfill(view)
        # QWebEngine 的网络加载是异步的：成功后注入性能修复 CSS，失败则由
        # cancellable QTimer 重试。主线程不再同步探测 localhost 端口。
        retry_timer = QTimer(view)
        retry_timer.setSingleShot(True)
        retry_timer.timeout.connect(_retry_load)
        view.loadStarted.connect(_load_started)
        view.loadFinished.connect(_load_finished)
        view.page().renderProcessTerminated.connect(_render_process_terminated)
        lay = QVBoxLayout(win)
        lay.setContentsMargins(0, 0, 0, 0)
        failure_panel = QFrame(win)
        failure_panel.setObjectName("rail")
        failure_layout = QHBoxLayout(failure_panel)
        failure_layout.setContentsMargins(18, 16, 18, 16)
        failure_label = QLabel()
        failure_label.setTextFormat(Qt.PlainText)
        failure_label.setWordWrap(True)
        retry_button = QPushButton("重新加载页面")
        retry_button.setObjectName("primary")
        retry_button.clicked.connect(_retry_renderer)
        failure_layout.addWidget(failure_label, 1)
        failure_layout.addWidget(retry_button)
        failure_panel.hide()
        lay.addWidget(failure_panel)
        lay.addWidget(view, 1)
        win.resize(1200, 800)
        _window = win
        _view = view
        _retry_timer = retry_timer
        _failure_panel, _failure_label = failure_panel, failure_label
        if not _quit_connected:
            QCoreApplication.instance().aboutToQuit.connect(_dispose_webview)
            _quit_connected = True

    _after_auth_url = target_url if authenticated_url is not None else None
    _install_launch_session_hint(_view, target_url if workspace_dir is not None or session_id is not None else None)
    _active_frontend_url = base
    _target_url = initial_url
    _load_failed = False
    _page_loading = True
    _renderer_failed = False
    _failure_panel.hide()
    _retry_timer.stop()
    _bring_to_front(_window)
    _view.load(QUrl(_target_url))
    return "opened authenticated DSH workspace" if authenticated_url else f"opened {target_url}"


if __name__ == "__main__":
    print(show_webview())
