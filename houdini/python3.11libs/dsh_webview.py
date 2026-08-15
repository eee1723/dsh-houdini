"""在 Houdini GUI 里内嵌 dsh web UI（QWebEngineView 加载 http://127.0.0.1:3081）。

- 仅适用于带 Qt GUI 的 Houdini（hython 无 GUI，show 时会明确报错）。
- QWebEngineView 只能在主线程创建/操作；Houdini 菜单和 Python Shell 都在主线程，
  直接调用即可。
- 幂等：重复调用唤起已有窗口，不重复创建。
- 前端未就绪时每 2s 自动重试加载，直到连上（配合 launcher 的一键启动）。

用法（Houdini GUI 菜单或 Python Shell，主线程）：
    import dsh_webview
    dsh_webview.show_webview()
"""

from __future__ import annotations

import socket

from PySide6.QtCore import QCoreApplication, QThread, QTimer, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 3081
FRONTEND_URL = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"

_RETRY_INTERVAL_MS = 2000

_window: QWidget | None = None
_view: QWebEngineView | None = None


def _on_main_thread() -> bool:
    app = QCoreApplication.instance()
    return app is not None and QThread.currentThread() is app.thread()


def _port_open(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.3)
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _retry_load() -> None:
    """前端端口没就绪时，每 2s 重试一次，直到连上或窗口被关闭。"""
    if _view is None or _window is None or not _window.isVisible():
        return
    if _port_open(FRONTEND_HOST, FRONTEND_PORT):
        _view.load(QUrl(FRONTEND_URL))
    else:
        QTimer.singleShot(_RETRY_INTERVAL_MS, _retry_load)


def show_webview() -> str:
    """打开（或唤起）内嵌的 dsh web UI 窗口；幂等，须在主线程调用。"""
    if QCoreApplication.instance() is None:
        raise RuntimeError(
            "dsh_webview 需要 Qt GUI：当前是 hython/无 UI 进程，无法内嵌 web UI。"
            "请在 Houdini GUI 的菜单或 Python Shell 里调用。"
        )
    if not _on_main_thread():
        raise RuntimeError(
            "show_webview() 必须在主线程调用（Houdini 菜单 / Python Shell 即主线程）。"
        )

    global _window, _view
    if _window is not None and _window.isVisible():
        _window.raise_()
        _window.activateWindow()
        return "webview already open"

    if _window is None:
        win = QWidget()
        win.setWindowTitle("dsh")
        view = QWebEngineView()
        lay = QVBoxLayout(win)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(view)
        win.resize(1200, 800)
        _window = win
        _view = view

    _window.show()
    _view.load(QUrl(FRONTEND_URL))
    if not _port_open(FRONTEND_HOST, FRONTEND_PORT):
        QTimer.singleShot(_RETRY_INTERVAL_MS, _retry_load)
    return f"opened {FRONTEND_URL}"


if __name__ == "__main__":
    print(show_webview())
