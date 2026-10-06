"""Shared Chinese Qt installation UI; network and file verification run in workers."""
from __future__ import annotations

from pathlib import Path
import json
import queue
import threading

import dsh_deployment as deployment
import dsh_release_policy as releases

_WINDOW = None

from dsh_ui_style import style_dialog, confirm_dialog, show_tool_window


def show_source(*, parent=None):
    """Open the shared panel without creating or selecting a managed installation."""
    return show(source_root=Path(__file__).resolve().parents[2], parent=parent)


def show(store=None, *, source_root=None, pinned=None, loaded=None, startup_error=None, parent=None, context_provider=None):
    global _WINDOW
    from hutil.Qt import QtCore, QtGui, QtWidgets
    source_root = Path(source_root).resolve() if source_root is not None else None
    source_mode = source_root is not None
    if source_mode == (store is not None):
        raise ValueError("Choose either a source checkout or a managed installation store")
    if _WINDOW is not None:
        if context_provider is not None:
            _WINDOW._dsh_context_provider = context_provider
        show_tool_window(_WINDOW)
        return _WINDOW
    if parent is None:
        import hou
        parent = hou.qt.mainWindow()
    window = QtWidgets.QDialog(parent)
    window._dsh_context_provider = context_provider
    window.setWindowTitle("DSH-Houdini · 版本与更新")
    window.setMinimumWidth(560)
    style_dialog(window)
    layout = QtWidgets.QVBoxLayout(window)
    layout.setContentsMargins(24, 24, 24, 20)
    layout.setSpacing(16)

    def label(text, name=None):
        widget = QtWidgets.QLabel(text)
        widget.setTextFormat(QtCore.Qt.PlainText)
        widget.setWordWrap(True)
        if name:
            widget.setObjectName(name)
        return widget

    heading = QtWidgets.QHBoxLayout()
    heading.addWidget(label("版本与更新", "title"))
    heading.addStretch(1)
    heading.addWidget(label("DSH-Houdini", "caption"))
    layout.addLayout(heading)
    track = QtWidgets.QFrame()
    track.setObjectName("track")
    versions = QtWidgets.QGridLayout(track)
    versions.setContentsMargins(18, 16, 18, 16)
    versions.setHorizontalSpacing(24)
    versions.setVerticalSpacing(8)
    current_heading = label("源码版本" if source_mode else "当前版本", "caption")
    pending_heading = label("下次启动", "caption")
    current = label("读取中…", "version")
    pending = label("", "version")
    runtime_note = label("源码开发 · 磁盘版本，未核验当前运行代码" if source_mode else "", "caption")
    versions.addWidget(current_heading, 0, 0)
    versions.addWidget(pending_heading, 0, 1)
    versions.addWidget(current, 1, 0)
    versions.addWidget(pending, 1, 1)
    versions.addWidget(runtime_note, 2, 0, 1, 2)
    versions.setColumnStretch(0, 1)
    versions.setColumnStretch(1, 1)
    pending_heading.hide()
    pending.hide()
    layout.addWidget(track)
    status = label("启动遇到问题，请展开高级设置查看详情。" if startup_error else "尚未检查更新。", "summary")
    layout.addWidget(status)
    actions = QtWidgets.QHBoxLayout()
    online = QtWidgets.QPushButton("检查更新")
    online.setObjectName("primary")
    install = QtWidgets.QPushButton("安装更新")
    install.setObjectName("primary")
    install.hide()
    cancel = QtWidgets.QPushButton("取消操作")
    cancel.hide()
    actions.addWidget(online)
    actions.addWidget(install)
    actions.addStretch(1)
    actions.addWidget(cancel)
    layout.addLayout(actions)
    progress_bar = QtWidgets.QProgressBar()
    progress_bar.setTextVisible(False)
    progress_bar.hide()
    layout.addWidget(progress_bar)

    advanced_toggle = QtWidgets.QPushButton("高级设置")
    advanced_toggle.setObjectName("quiet")
    advanced_toggle.setCheckable(True)
    advanced_toggle.setStyleSheet("text-align: left; padding-left: 0;")
    layout.addWidget(advanced_toggle)
    advanced = QtWidgets.QFrame()
    advanced.setObjectName("advanced")
    advanced_layout = QtWidgets.QVBoxLayout(advanced)
    advanced_layout.setContentsMargins(16, 16, 16, 16)
    advanced_layout.setSpacing(12)
    advanced_layout.addWidget(label("源码开发" if source_mode else "受管安装 · 插件与运行依赖一起更新", "name"))
    location = label(str(source_root if source_mode else store.root), "caption")
    location.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    advanced_layout.addWidget(location)
    source_help = ("在源码目录依次执行 git pull --ff-only、npm install、npm run build。\n"
                   "随后在运行诊断中修复并重启运行环境；菜单、安装配置或内嵌网页窗口有改动时，需要完整重开 Houdini。\n"
                   "构建通过不代表当前 Houdini 已加载新版本。")
    maintenance = QtWidgets.QGridLayout()
    local = QtWidgets.QPushButton("源码更新说明" if source_mode else "安装本地包…")
    verify_button = QtWidgets.QPushButton("刷新源码版本" if source_mode else "检查安装文件")
    repair = QtWidgets.QPushButton("修复当前版本")
    rollback = QtWidgets.QPushButton("回退到上一版本")
    cancel_pending = QtWidgets.QPushButton("取消下次切换")
    diagnostics = QtWidgets.QPushButton("运行诊断…")
    diagnostics.setToolTip("查看真实运行版本、连接状态及重启选项")
    maintenance.addWidget(local, 0, 0)
    maintenance.addWidget(verify_button, 0, 1)
    maintenance.addWidget(repair, 1, 0)
    maintenance.addWidget(rollback, 1, 1)
    maintenance.addWidget(cancel_pending, 2, 0)
    maintenance.addWidget(diagnostics, 1 if source_mode else 2, 0 if source_mode else 1)
    advanced_layout.addLayout(maintenance)
    shared_label = label("实验功能 · 将当前 Houdini 连接到共享服务", "caption")
    shared_buttons = QtWidgets.QHBoxLayout()
    shared_register = QtWidgets.QPushButton("登记共享执行端…")
    shared_repair = QtWidgets.QPushButton("修复共享连接…")
    shared_buttons.addWidget(shared_register)
    shared_buttons.addWidget(shared_repair)
    advanced_layout.addWidget(shared_label)
    advanced_layout.addLayout(shared_buttons)
    details = QtWidgets.QPlainTextEdit()
    details.setReadOnly(True)
    details.setMaximumBlockCount(120)
    details.setPlaceholderText("操作详情会显示在这里。")
    details.setFixedHeight(138)
    if startup_error:
        details.setPlainText(str(startup_error))
    advanced_layout.addWidget(details)
    advanced.hide()
    layout.addWidget(advanced)
    events = queue.Queue()
    cancelled = threading.Event()
    state = {"busy": False, "release": None, "checked": False, "source_version": None,
             "version": None, "pending": None, "error": bool(startup_error)}
    buttons = [online, install, local, verify_button, repair, rollback, cancel_pending, diagnostics,
               shared_register, shared_repair]

    def toggle_advanced(checked):
        advanced.setVisible(checked)
        advanced_toggle.setText("收起高级设置" if checked else "高级设置")
        window.adjustSize()

    def report(text):
        if cancelled.is_set():
            raise InterruptedError("操作已取消。当前运行版本不变，已下载的文件保留。")
        events.put(("progress", text))

    def release_action():
        release = state["release"]
        install.hide()
        online.setObjectName("primary")
        if state["pending"]:
            return "版本已准备好，完整重开 Houdini 后生效。"
        if not state["checked"]:
            return None
        if release is None:
            return "暂未发布正式版本。"
        version = state["version"]
        try:
            comparison = (releases.stable_version(release["version"]), releases.stable_version(version))
            newer, equal = comparison[0] > comparison[1], comparison[0] == comparison[1]
        except (ValueError, TypeError):
            newer, equal = False, False
        if not source_mode and version is None:
            install.setText("安装 " + release["version"])
            summary = "正式版本 " + release["version"] + " 可安装。"
        elif newer:
            install.setText(("查看新版 " if source_mode else "更新至 ") + release["version"])
            summary = "发现新版本 " + release["version"] + ("，源码安装需手动更新。" if source_mode else "。")
        elif equal:
            return "源码版本与正式版一致。" if source_mode else "已是最新正式版本。"
        elif version is not None:
            return "最新正式版为 " + release["version"] + "；当前版本不同，无需自动切换。"
        else:
            return "已找到正式版 " + release["version"] + "，当前版本无法比较。"
        install.show()
        online.setObjectName("quiet")
        return summary

    def refresh():
        for button in buttons:
            button.setEnabled(not state["busy"])
        for button in (repair, rollback, cancel_pending):
            button.hide()
        runtime_available = source_mode or loaded is not None
        diagnostics.setVisible(runtime_available)
        shared_label.setVisible(runtime_available)
        shared_register.setVisible(runtime_available)
        shared_repair.setVisible(runtime_available)
        if source_mode:
            state["version"] = state["source_version"]
            current.setText(state["source_version"] or "无法读取")
        else:
            verify_button.hide()
            install.hide()
            data = store.state()
            ident = data["current"]
            state["version"] = ident.split("-")[0] if ident else None
            process_ident = loaded["installId"] if loaded else pinned
            next_ident = data["pending"] or (ident if process_ident and process_ident != ident else None)
            state["pending"] = next_ident
            current_heading.setText("当前运行" if loaded else "当前安装")
            current.setText(loaded["installId"].split("-")[0] if loaded else state["version"] or "尚未安装")
            pending.setText(next_ident.split("-")[0] if next_ident else "")
            pending.setVisible(bool(next_ident))
            pending_heading.setVisible(bool(next_ident))
            runtime_note.setText("受管安装 · 本次运行版本已加载" if loaded else
                                 "版本已选定，尚未启动工作区" if pinned else "从正式发行包安装，或在高级设置中选择本地包")
            repair.setVisible(bool(data["current"]))
            rollback.setVisible(bool(data["previous"]))
            cancel_pending.setVisible(bool(data["pending"]))
            verify_button.setVisible(bool(data["pending"] or data["current"]))
        summary = release_action()
        for button in (online, install):
            button.style().unpolish(button)
            button.style().polish(button)
        return summary

    def run(task, message="正在处理…", *, summarize=False):
        if state["busy"]:
            return
        state["busy"] = True
        state["summarize"] = summarize
        state["error"] = False
        cancelled.clear()
        for button in buttons:
            button.setEnabled(False)
        status.setText(message)
        cancel.setText("取消操作")
        cancel.setEnabled(True)
        cancel.show()
        progress_bar.setRange(0, 0)
        progress_bar.show()

        def worker():
            try:
                result = task()
                events.put(("done", result or "操作完成。"))
            except InterruptedError as exc:
                events.put(("cancelled", str(exc)))
            except Exception as exc:
                events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def check_updates():
        # A failed retry must never keep an older actionable release result.
        state["checked"] = False
        state["release"] = None
        install.hide()
        def check():
            value = releases.latest_stable_release()
            report("更新检查已响应。")
            events.put(("release", value))
            return "更新检查完成。"
        run(check, "正在检查正式版本…", summarize=True)

    def install_release():
        release = state["release"]
        if release is None:
            return
        if source_mode:
            if not QtGui.QDesktopServices.openUrl(QtCore.QUrl(release["url"])):
                status.setText("无法打开发行页面，链接已放入高级设置。")
                details.appendPlainText(release["url"])
            return
        answer = confirm_dialog(
            window, "准备安装", "下载并校验完整发行包？\n\n新版本将在完整重开 Houdini 后启用，当前版本和数据会保留。",
            "下载并准备安装")
        if answer:
            def install_task():
                directory = deployment.fetch_release(store, release, report)
                store.stage(directory, report)
                return "版本已准备好，完整重开 Houdini 后生效。"
            run(install_task, "正在下载并校验发行包…")

    def local_action():
        if source_mode:
            details.setPlainText(source_help)
            return
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            window, "选择与安装包及签名放在一起的 release.json", "", "发行清单 (release.json)")
        if filename:
            run(lambda: store.stage(Path(filename).parent, report) and "本地版本已准备好，完整重开 Houdini 后生效。", "正在检查本地发行包…")

    def verify():
        if source_mode:
            def read_source():
                package = json.loads((source_root / "package.json").read_text(encoding="utf-8"))
                events.put(("source", str(package["version"])))
                return "源码版本已读取；尚未检查更新。"
            state["source_version"] = None
            current.setText("读取中…")
            run(read_source, "正在读取源码版本…", summarize=True)
            return
        def task():
            data = store.state()
            ident = data["pending"] or data["current"]
            manifest = store.manifest(ident)
            deployment.verify_inventory(store.installation(ident), manifest, report)
            return f"安装文件检查通过 · Node {manifest['nodeVersion']} · DSH {manifest['dshVersion']}。运行版本请查看运行诊断。"
        run(task, "正在检查安装文件…")

    def rollback_action():
        answer = confirm_dialog(
            window, "回退到上一版本", "下次启动恢复上一版本和它的数据快照？\n\n新版会话会单独保留，不会合并到旧版。",
            "准备回退")
        if answer:
            run(lambda: store.rollback(report) and "已准备回退，完整重开 Houdini 后生效。新版数据单独保留。")

    def repair_current():
        def task():
            ident = store.state()["current"]
            manifest = store.manifest(ident)
            metadata = releases._read_json(releases.REPOSITORY_API + "/releases/tags/v" + manifest["version"])
            release = releases.validate_published_release(metadata)
            if release["version"] != manifest["version"]:
                raise ValueError("修复包与当前版本不一致")
            directory = deployment.fetch_release(store, release, report)
            store.stage(directory, report)
            return "同版本修复包已准备好，完整重开 Houdini 后生效。"
        run(task, "正在准备当前版本的修复包…")

    def tick():
        nonlocal loaded, pinned
        provider = window._dsh_context_provider
        if provider is not None:
            new_pinned, new_loaded = provider()
            if new_loaded is not loaded or new_pinned != pinned:
                pinned, loaded = new_pinned, new_loaded
                if not state["busy"]:
                    try:
                        refresh()
                    except Exception as exc:
                        details.appendPlainText(str(exc))
        while not events.empty():
            kind, value = events.get_nowait()
            if kind == "source":
                state["source_version"] = value
                continue
            if kind == "release":
                state["release"] = value
                state["checked"] = True
                continue
            if kind != "progress" or not details.toPlainText().endswith(value):
                details.appendPlainText(value)
            if kind == "progress":
                # Technical progress belongs to the advanced log. The main
                # status retains the concise description of the operation.
                continue
            if kind in ("done", "error", "cancelled"):
                state["busy"] = False
                state["error"] = kind == "error"
                cancel.hide()
                progress_bar.hide()
                try:
                    summary = refresh()
                except Exception as exc:
                    details.appendPlainText(str(exc))
                    summary = None
                    state["error"] = True
                status.setText("操作未完成，请展开高级设置查看原因。" if state["error"] else
                               summary if kind == "done" and state.get("summarize") and summary else value)
                window.adjustSize()

    def runtime_diagnostics():
        import dsh_manager
        dsh_manager.show_version_manager()

    def shared_action(repair=False):
        import dsh_shared_executor
        dsh_shared_executor.show_registration(repair=repair)

    def request_cancel():
        cancelled.set()
        cancel.setText("正在取消…")
        cancel.setEnabled(False)

    online.clicked.connect(check_updates)
    install.clicked.connect(install_release)
    local.clicked.connect(local_action)
    verify_button.clicked.connect(verify)
    repair.clicked.connect(repair_current)
    rollback.clicked.connect(rollback_action)
    cancel_pending.clicked.connect(lambda: run(lambda: store.cancel_pending() or "已取消下次切换，版本和数据保留。"))
    cancel.clicked.connect(request_cancel)
    diagnostics.clicked.connect(runtime_diagnostics)
    shared_register.clicked.connect(lambda: shared_action())
    shared_repair.clicked.connect(lambda: shared_action(repair=True))
    advanced_toggle.toggled.connect(toggle_advanced)

    def close():
        global _WINDOW
        if state["busy"]:
            cancelled.set()
        timer.stop()
        _WINDOW = None

    timer = QtCore.QTimer(window)
    timer.timeout.connect(tick)
    timer.start(100)
    window.finished.connect(close)
    try:
        initial_summary = refresh()
        if initial_summary and not startup_error:
            status.setText(initial_summary)
    except Exception as exc:
        status.setText("无法读取安装状态，请展开高级设置查看原因。")
        details.appendPlainText(str(exc))
    _WINDOW = window
    window.show()
    if source_mode:
        verify()
    return window
