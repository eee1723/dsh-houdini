"""Actual isolated Qt construction and interaction; never controls a live desktop."""
from __future__ import annotations
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
from unittest.mock import patch
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
from hutil.Qt import QtWidgets, QtGui, QtCore
import dsh_deployment as d
import dsh_install_ui as ui

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline, "Qt worker did not finish"
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(25, loop.quit)
        loop.exec()


def button(window, text):
    return next(widget for widget in window.findChildren(QtWidgets.QPushButton) if widget.text() == text)


def labels(window):
    return [widget.text() for widget in window.findChildren(QtWidgets.QLabel)]


def visible_buttons(window):
    return [widget.text() for widget in window.findChildren(QtWidgets.QPushButton) if widget.isVisible()]


def close(window):
    window.close()
    app.processEvents()
    assert ui._WINDOW is None


def release(version):
    return ui.releases.validate_published_release({
        "id": 1, "draft": False, "prerelease": False,
        "published_at": "2026-09-09T00:00:00Z", "tag_name": "v" + version,
        "html_url": "https://untrusted.invalid/",
    })


for font in ("segoeui.ttf", "consola.ttf", "msyh.ttc", "msyhbd.ttc"):
    QtGui.QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / font))
output = ROOT / "tools/out"
output.mkdir(exist_ok=True)
suffix = f"python{sys.version_info.major}{sys.version_info.minor}"
with tempfile.TemporaryDirectory(prefix="dsh-install-ui-") as temporary:
    root = Path(temporary)
    parent = QtWidgets.QWidget()
    running = {"loaded": None}
    window = ui.show(d.Store(root, {"schemaVersion": 1, "keys": []}), parent=parent,
                     context_provider=lambda: (None, running["loaded"]))
    app.processEvents()
    assert not window.windowFlags() & QtCore.Qt.WindowStaysOnTopHint
    assert window.windowFlags() & QtCore.Qt.WindowMinimizeButtonHint
    assert window.windowFlags() & QtCore.Qt.WindowCloseButtonHint
    assert window.windowFlags() & QtCore.Qt.WindowSystemMenuHint
    assert window.parentWidget() is parent and window.isWindow()
    assert visible_buttons(window) == ["检查更新", "高级设置"], visible_buttons(window)
    window.showMinimized()
    app.processEvents()
    assert window.isMinimized()
    assert ui.show(d.Store(root, {"schemaVersion": 1, "keys": []}), parent=parent) is window
    app.processEvents()
    assert not window.isMinimized(), "explicit Version & Updates reopen must restore the same tool"
    assert window.grab().save(str(output / f"deployment-ui-{suffix}.png"))
    button(window, "高级设置").click()
    assert button(window, "安装本地包…").isVisible()
    for text in ("修复当前版本", "回退到上一版本", "运行诊断…", "登记共享执行端…"):
        assert not button(window, text).isVisible(), text
    running["loaded"] = {"installId": "1.0.0-aaaaaaaaaaaa-bbbbbbbb"}
    wait_until(lambda: button(window, "运行诊断…").isVisible())
    close(window)

    source = root / "source checkout"
    source.mkdir()
    (source / "package.json").write_text('{"version":"7.8.9"}', encoding="utf-8")
    with patch.object(d, "Store", side_effect=AssertionError("source must not create a store")):
        window = ui.show(source_root=source, parent=parent)
        refresh = button(window, "刷新源码版本")
        check = button(window, "检查更新")
        wait_until(refresh.isEnabled)
        assert "7.8.9" in labels(window)
        assert "源码开发 · 磁盘版本，未核验当前运行代码" in labels(window)
        assert visible_buttons(window) == ["检查更新", "高级设置"], visible_buttons(window)
        assert window.windowTitle() == "DSH-Houdini · 版本与更新"
        assert window.height() < 420, window.height()
        assert window.grab().save(str(output / f"source-ui-{suffix}.png"))
        button(window, "高级设置").click()
        assert str(source.resolve()) in labels(window)
        assert button(window, "运行诊断…").isVisible()
        button(window, "源码更新说明").click()
        assert "npm run build" in window.findChild(QtWidgets.QPlainTextEdit).toPlainText()
        for text in ("修复当前版本", "回退到上一版本", "取消下次切换"):
            assert not button(window, text).isVisible(), text
        called = []
        diagnostics = types.ModuleType("dsh_manager")
        diagnostics.show_version_manager = lambda: called.append("diagnostics")
        shared = types.ModuleType("dsh_shared_executor")
        shared.show_registration = lambda **kw: called.append(kw)
        with patch.dict(sys.modules, {"dsh_manager": diagnostics, "dsh_shared_executor": shared}):
            button(window, "运行诊断…").click()
            button(window, "登记共享执行端…").click()
            button(window, "修复共享连接…").click()
        assert called == ["diagnostics", {"repair": False}, {"repair": True}], called
        assert window.grab().save(str(output / f"source-advanced-ui-{suffix}.png"))
        button(window, "收起高级设置").click()

        with patch.object(ui.releases, "latest_stable_release", return_value=release("7.9.0")), \
             patch.object(QtGui.QDesktopServices, "openUrl", return_value=True) as opened:
            check.click()
            wait_until(check.isEnabled)
            view = button(window, "查看新版 7.9.0")
            assert view.isVisible()
            view.click()
            assert opened.call_args.args[0].toString() == release("7.9.0")["url"]
        with patch.object(ui.releases, "latest_stable_release", return_value=release("7.8.9")):
            check.click()
            wait_until(check.isEnabled)
            assert not view.isVisible()
            assert "源码版本与正式版一致。" in labels(window)
            assert "源码开发 · 磁盘版本，未核验当前运行代码" in labels(window)
        with patch.object(ui.releases, "latest_stable_release", return_value=None):
            check.click()
            wait_until(check.isEnabled)
            assert "暂未发布正式版本。" in labels(window)
        with patch.object(ui.releases, "latest_stable_release", side_effect=TimeoutError("offline fixture")):
            check.click()
            wait_until(check.isEnabled)
            assert "操作未完成，请展开高级设置查看原因。" in labels(window)
            assert not view.isVisible()
            assert "offline fixture" in window.findChild(QtWidgets.QPlainTextEdit).toPlainText()

        responded = threading.Event()
        def delayed_check():
            assert responded.wait(3)
            return release("8.0.0")
        with patch.object(ui.releases, "latest_stable_release", side_effect=delayed_check):
            check.click()
            button(window, "取消操作").click()
            responded.set()
            wait_until(check.isEnabled)
            assert not view.isVisible(), "cancelled release check must not publish an actionable release"
            assert any("操作已取消" in text for text in labels(window))

        (source / "package.json").write_text("broken", encoding="utf-8")
        refresh.click()
        wait_until(refresh.isEnabled)
        assert "无法读取" in labels(window)
        assert not (root / "state.json").exists()
        close(window)

    class StageStore:
        def __init__(self):
            self.root = root
            self.data = {"current": "1.0.0-current", "previous": "0.9.0-previous", "pending": "1.1.0-pending"}
        def state(self):
            return dict(self.data)
        def cancel_pending(self):
            self.data["pending"] = None
        def stage(self, directory, report):
            assert directory == root / "verified-package"
            report("fixture package verified")
            self.data["pending"] = "1.1.0-pending"
            return "1.1.0-pending"
    store = StageStore()
    window = ui.show(store, parent=parent, loaded={"installId": "1.0.0-current"})
    assert "1.0.0" in labels(window) and "1.1.0" in labels(window)
    assert "版本已准备好，完整重开 Houdini 后生效。" in labels(window)
    assert window.grab().save(str(output / f"managed-pending-ui-{suffix}.png"))
    button(window, "高级设置").click()
    assert button(window, "修复当前版本").isVisible() and button(window, "回退到上一版本").isVisible()
    cancel_pending = button(window, "取消下次切换")
    cancel_pending.click()
    wait_until(lambda: button(window, "检查更新").isEnabled())
    assert not cancel_pending.isVisible()
    assert "已取消下次切换，版本和数据保留。" in labels(window)
    check = button(window, "检查更新")
    with patch.object(ui.releases, "latest_stable_release", return_value=release("1.0.0")):
        check.click()
        wait_until(check.isEnabled)
        assert "已是最新正式版本。" in labels(window)
        assert not any(text.startswith("更新至") for text in visible_buttons(window))
    button(window, "收起高级设置").click()
    with patch.object(ui.releases, "latest_stable_release", return_value=release("1.1.0")):
        check.click()
        wait_until(check.isEnabled)
        update = button(window, "更新至 1.1.0")
        assert update.isVisible()
        assert window.grab().save(str(output / f"managed-update-ui-{suffix}.png"))
        with patch.object(ui, "confirm_dialog", return_value=False), \
             patch.object(ui.deployment, "fetch_release", side_effect=AssertionError("cancelled installation downloaded")):
            update.click()
            assert store.data["pending"] is None
        with patch.object(ui, "confirm_dialog", return_value=True), \
             patch.object(ui.deployment, "fetch_release", return_value=root / "verified-package") as fetched:
            update.click()
            wait_until(check.isEnabled)
            assert fetched.call_args.args[:2] == (store, release("1.1.0"))
            assert store.data["pending"] == "1.1.0-pending"
            assert not update.isVisible()
            assert "版本已准备好，完整重开 Houdini 后生效。" in labels(window)
    close(window)

    # Rollback verifies potentially large payloads. Cancel and close must reach
    # its last checkpoint before any next-start selection is changed.
    for close_while_running in (False, True):
        window = ui.show(store, parent=parent, loaded={"installId": "1.0.0-current"})
        button(window, "高级设置").click()
        entered, proceed, finished = threading.Event(), threading.Event(), threading.Event()
        previous_pending = store.data["pending"]
        def delayed_rollback(report):
            try:
                entered.set()
                assert proceed.wait(3)
                report("Preparing rollback for the next Houdini start")
                store.data["pending"] = store.data["previous"]
                return store.data["pending"]
            finally:
                finished.set()
        with patch.object(store, "rollback", delayed_rollback, create=True), \
             patch.object(ui, "confirm_dialog", return_value=True):
            button(window, "回退到上一版本").click()
            wait_until(entered.is_set)
            if close_while_running:
                close(window)
            else:
                button(window, "取消操作").click()
            proceed.set()
            wait_until(finished.is_set)
            assert store.data["pending"] == previous_pending
            if not close_while_running:
                wait_until(lambda: button(window, "检查更新").isEnabled())
                assert any("操作已取消" in text for text in labels(window))
                close(window)

    # Confirmation uses Chinese labels even with an English Houdini/Qt locale,
    # and the default button remains cancellation for restart/install actions.
    def dismiss_confirmation():
        dialog = app.activeModalWidget()
        assert isinstance(dialog, QtWidgets.QMessageBox)
        assert sorted(item.text() for item in dialog.buttons()) == ["取消", "继续安装"]
        assert dialog.defaultButton().text() == "取消"
        dialog.defaultButton().click()
    QtCore.QTimer.singleShot(0, dismiss_confirmation)
    assert not ui.confirm_dialog(parent, "测试确认", "测试安装说明", "继续安装")

    for menu_path in (ROOT / "houdini/MainMenuCommon.xml", ROOT / "installer/MainMenuCommon.xml"):
        menu = ET.parse(menu_path)
        assert all((item.text or "").isascii() for item in menu.findall(".//label"))
        assert [item.text for item in menu.findall(".//scriptItem/label")] == ["Open Workspace", "Version & Updates..."]
    menu = ET.parse(ROOT / "houdini/MainMenuCommon.xml")
    script = menu.find(".//scriptItem[@id='dsh.version_manager']/scriptCode").text
    with patch.object(ui, "show_source") as entry:
        exec(script, {})
        entry.assert_called_once_with()

# Render the real runtime dialog with deterministic worker facts. All probes
# and restarts are mocked; Qt event delivery and the user action path are real.
import hou
import dsh_manager as manager
with patch.object(hou, "qt", types.SimpleNamespace(mainWindow=lambda: parent), create=True), \
     patch.dict(sys.modules, {"dsh_install_ui": types.ModuleType("old_bootstrap_ui")}), \
     patch.object(manager, "_runtime_dsh_info", return_value={"online": True, "verified": True,
                      "version": manager.dsh_runtime_compat.preferred_version(), "note": "fixture runtime"}), \
     patch.object(manager, "_selected_cached_dsh_version", return_value=manager.dsh_runtime_compat.preferred_version()), \
     patch.object(manager, "_dsh_launch_override", return_value=None), \
     patch.object(manager, "_port_open", return_value=True):
    manager.show_version_manager()
    window = manager._WINDOW
    wait_until(lambda: button(window, "刷新状态").isEnabled() and "运行环境与配套版本一致。" in labels(window))
    window.showMinimized()
    app.processEvents()
    assert window.isMinimized()
    manager.show_version_manager()
    app.processEvents()
    assert manager._WINDOW is window and not window.isMinimized()
    assert "准备配套版本" not in visible_buttons(window)
    assert window.grab().save(str(output / f"runtime-ui-{suffix}.png"))
    window.close()
    app.processEvents()
    assert manager._WINDOW is None

import dsh_launcher as launcher
def startup_fixture(state):
    launcher._set_startup_state(state, 38, 2, "正在准备插件", "检查 Houdini 工作配置")
    state["worker_done"] = True

with patch.object(hou, "qt", types.SimpleNamespace(mainWindow=lambda: parent), create=True), \
     patch.dict(sys.modules, {"dsh_install_ui": types.ModuleType("old_bootstrap_ui")}), \
     patch.object(launcher, "_start_and_wait_frontend", side_effect=startup_fixture):
    launcher.open_ui_when_ready("isolated UI fixture", frontend_cwd=str(ROOT))
    window = launcher._PENDING["dialog"]
    wait_until(lambda: "正在准备插件" in labels(window))
    active_startup = launcher._ACTIVE_STARTUP
    window.showMinimized()
    app.processEvents()
    assert window.isMinimized()
    launcher._dispatch_service_preflight(lambda *_: (_ for _ in ()).throw(
        AssertionError("repeat Open Workspace must not start another preflight")))
    app.processEvents()
    assert launcher._PENDING["dialog"] is window and not window.isMinimized()
    assert launcher._ACTIVE_STARTUP is active_startup
    progress = window.findChild(QtWidgets.QProgressBar)
    assert progress.minimum() == progress.maximum() == 0, "startup stages must not invent a completion percentage"
    assert not progress.isTextVisible()
    assert window.grab().save(str(output / f"startup-ui-{suffix}.png"))
    button(window, "取消启动").click()
    wait_until(lambda: launcher._ACTIVE_STARTUP is None)

# The native recovery surface must remain usable even when Chromium never
# renders a document. This tests crash signals, not successful WebEngine load.
import dsh_webview as webview
recovery_window = QtWidgets.QWidget()
recovery_window.show()
panel = QtWidgets.QFrame(recovery_window)
notice = QtWidgets.QLabel(panel)
retry_timer = QtCore.QTimer(recovery_window)
retry_timer.setSingleShot(True)
loads = []
fake_view = types.SimpleNamespace(load=lambda url: loads.append(url.toString()))
with patch.multiple(webview, _window=recovery_window, _view=fake_view, _retry_timer=retry_timer,
                    _failure_panel=panel, _failure_label=notice, _target_url="http://127.0.0.1:12345/",
                    _renderer_failed=False, _load_failed=False, _page_loading=True):
    retry_timer.start(2000)
    webview._render_process_terminated(webview.QWebEnginePage.CrashedTerminationStatus, -1073741515)
    assert panel.isVisible() and "0xC0000135" in notice.text()
    assert "已停止自动重试" in notice.text() and not retry_timer.isActive()
    webview._load_finished(False)
    webview._retry_load()
    assert not retry_timer.isActive() and not loads, "renderer failures cannot loop HTTP retries"
    webview._retry_renderer()
    assert loads == ["http://127.0.0.1:12345/"] and not panel.isVisible()
    webview._load_finished(False)
    assert retry_timer.isActive(), "ordinary transient HTTP load failure retains the existing automatic retry"
    retry_timer.stop()
recovery_window.close()
print("Chinese source/managed panels, advanced actions, release/cancel/error states and runtime diagnostics passed")
