"""Dependency-free Qt install manager; expensive work is queued to workers."""
from __future__ import annotations

from pathlib import Path
import queue
import threading

import dsh_deployment as deployment
import dsh_release_policy as releases

_WINDOW = None


def show(store, *, pinned=None, loaded=None, startup_error=None, parent=None, context_provider=None):
    global _WINDOW
    from hutil.Qt import QtCore, QtGui, QtWidgets
    if _WINDOW is not None:
        if context_provider is not None:
            _WINDOW._dsh_context_provider = context_provider
        _WINDOW.raise_()
        return _WINDOW
    if parent is None:
        import hou
        parent = hou.qt.mainWindow()
    window = QtWidgets.QDialog(parent)
    window._dsh_context_provider = context_provider
    window.setWindowTitle("DSH-Houdini · Version & Diagnostics")
    window.setMinimumSize(760, 660)
    window.setFont(QtGui.QFont("Segoe UI", 10))
    window.setStyleSheet("""
        QDialog { background: #2B2D30; color: #E3E3E4; }
        QLabel { color: #E3E3E4; font: 12px 'Segoe UI'; }
        QLabel#title { font: 26px 'Bahnschrift'; }
        QLabel#caption { color: #BBC0C7; font: 11px 'Segoe UI'; }
        QLabel#version { font: 17px 'Consolas'; padding: 10px 0; }
        QFrame#track { background: #373A3F; border-left: 3px solid #F49943; padding: 8px; }
        QPushButton { background: #44474D; color: #E3E3E4; border: 1px solid #62666D; padding: 9px 14px; }
        QPushButton:hover { background: #50545A; }
        QPushButton:focus { border: 2px solid #F49943; }
        QPushButton:disabled { color: #8B9098; border-color: #44474D; }
        QPushButton#primary { background: #F49943; color: #212327; font-weight: 600; }
        QPlainTextEdit { background: #242629; color: #BBC0C7; border: 1px solid #51545B; font: 11px 'Consolas'; }
        QProgressBar { background: #373A3F; border: none; height: 5px; }
        QProgressBar::chunk { background: #F49943; }
    """)
    layout = QtWidgets.QVBoxLayout(window)
    layout.setContentsMargins(24, 22, 24, 20)
    layout.setSpacing(14)
    def label(text, name=None):
        widget = QtWidgets.QLabel(text)
        widget.setTextFormat(QtCore.Qt.PlainText)
        widget.setWordWrap(True)
        if name:
            widget.setObjectName(name)
        return widget
    layout.addWidget(label("DSH-Houdini", "title"))
    layout.addWidget(label("Managed installation · plugin + Node + DeepSeek Harness", "caption"))
    track = QtWidgets.QFrame()
    track.setObjectName("track")
    versions = QtWidgets.QGridLayout(track)
    versions.addWidget(label("THIS HOUDINI PROCESS", "caption"), 0, 0)
    versions.addWidget(label("NEXT HOUDINI START", "caption"), 0, 1)
    current = label("Not loaded", "version")
    pending = label("Not installed", "version")
    versions.addWidget(current, 1, 0)
    versions.addWidget(pending, 1, 1)
    layout.addWidget(track)
    status = label(startup_error or "Install once. Updates are prepared alongside the running version.")
    layout.addWidget(status)
    controls = QtWidgets.QGridLayout()
    online = QtWidgets.QPushButton("Check for a release")
    online.setObjectName("primary")
    local = QtWidgets.QPushButton("Install local package…")
    repair = QtWidgets.QPushButton("Repair current version")
    verify_button = QtWidgets.QPushButton("Verify installation")
    rollback = QtWidgets.QPushButton("Prepare rollback")
    cancel_pending = QtWidgets.QPushButton("Cancel pending change")
    cancel = QtWidgets.QPushButton("Cancel operation")
    buttons = [online, local, repair, verify_button, rollback, cancel_pending]
    for index, button in enumerate(buttons):
        button.setMinimumHeight(38)
        button.setFont(QtGui.QFont("Segoe UI", 10))
        controls.addWidget(button, index // 2, index % 2)
    cancel.setMinimumHeight(38)
    controls.addWidget(cancel, 3, 1)
    cancel.setEnabled(False)
    layout.addLayout(controls)
    progress_bar = QtWidgets.QProgressBar()
    progress_bar.setTextVisible(False)
    progress_bar.setRange(0, 1)
    layout.addWidget(progress_bar)
    details = QtWidgets.QPlainTextEdit()
    details.setReadOnly(True)
    details.setMaximumBlockCount(120)
    details.setPlaceholderText("Installation checks and progress appear here. Existing DSH sessions and HIP files are never removed.")
    details.setMinimumHeight(110)
    layout.addWidget(details)
    advanced = QtWidgets.QPushButton("Advanced runtime diagnostics")
    advanced.setMinimumHeight(38)
    advanced.setEnabled(loaded is not None)
    layout.addWidget(advanced)
    events = queue.Queue()
    cancelled = threading.Event()
    state = {"busy": False, "release": None}
    def report(text):
        if cancelled.is_set():
            raise InterruptedError("Cancelled. The running installation is unchanged; partial downloads are retained.")
        events.put(("progress", text))
    def refresh():
        data = store.state()
        def version(ident):
            return ident.split("-")[0] if ident else "Not installed"
        current.setText(version(loaded["installId"]) if loaded else (version(pinned) + " · not started" if pinned else "Not loaded"))
        pending.setText(version(data["pending"] or data["current"]))
        rollback.setEnabled(bool(data["previous"]) and not state["busy"])
        cancel_pending.setEnabled(bool(data["pending"]) and not state["busy"])
        repair.setEnabled(bool(data["current"]) and not state["busy"])
        verify_button.setEnabled(bool(data["pending"] or data["current"]) and not state["busy"])
    def run(task):
        if state["busy"]:
            return
        state["busy"] = True
        cancelled.clear()
        for button in buttons:
            button.setEnabled(False)
        cancel.setEnabled(True)
        progress_bar.setRange(0, 0)
        def worker():
            try:
                result = task()
                events.put(("done", result or "Operation completed"))
            except Exception as exc:
                events.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()
    def online_action():
        if state["release"] is None:
            def check():
                value = releases.latest_stable_release()
                events.put(("release", value))
                return "No stable release is published." if value is None else "Published version found. Install / repair downloads a signed complete package."
            run(check)
        else:
            release = state["release"]
            if QtWidgets.QMessageBox.question(window, "Prepare installation", "Download and verify this complete release? It will be used after restarting Houdini. Your current installation is retained.") == QtWidgets.QMessageBox.Yes:
                def install():
                    directory = deployment.fetch_release(store, release, report)
                    store.stage(directory, report)
                    return "Ready. Restart Houdini, then Open Workspace to activate the new installation."
                run(install)
    def local_action():
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(window, "Select signed release.json beside its ZIP and signature", "", "Release manifest (release.json)")
        if filename:
            run(lambda: store.stage(Path(filename).parent, report) and "Local package ready for the next Houdini start.")
    def verify():
        def task():
            data = store.state()
            ident = data["pending"] or data["current"]
            manifest = store.manifest(ident)
            deployment.verify_inventory(store.installation(ident), manifest, report)
            return f"Files verified · Node {manifest['nodeVersion']} · DSH {manifest['dshVersion']}. This does not prove the running version. To repair damage, install the signed package again."
        run(task)
    def rollback_action():
        if QtWidgets.QMessageBox.question(window, "Prepare rollback", "Restore the previous program and its separate data snapshot at the next start? New-version sessions remain stored separately and are not merged into the old version.") == QtWidgets.QMessageBox.Yes:
            run(lambda: store.rollback() and "Rollback prepared. Restart Houdini. Newer data is retained separately.")
    def repair_current():
        def task():
            ident = store.state()["current"]
            # Identity comes from signed metadata even when executable files are damaged.
            manifest = store.manifest(ident)
            metadata = releases._read_json(releases.REPOSITORY_API + "/releases/tags/v" + manifest["version"])
            release = releases.validate_published_release(metadata)
            if release["version"] != manifest["version"]:
                raise ValueError("Repair publication does not match the current version")
            directory = deployment.fetch_release(store, release, report)
            store.stage(directory, report)
            return "The same version was repaired alongside the damaged copy. Restart Houdini."
        run(task)
    def tick():
        nonlocal loaded, pinned
        provider = window._dsh_context_provider
        if provider is not None:
            new_pinned, new_loaded = provider()
            if new_loaded is not loaded or new_pinned != pinned:
                pinned, loaded = new_pinned, new_loaded
                advanced.setEnabled(loaded is not None)
                if not state["busy"]:
                    try:
                        refresh()
                    except Exception as exc:
                        details.appendPlainText(str(exc))
        while not events.empty():
            kind, value = events.get_nowait()
            if kind == "release":
                state["release"] = value
                online.setText("Install / repair " + value["version"] if value else "Check for a release")
                continue
            status.setText(value)
            if kind != "progress" or not details.toPlainText().endswith(value):
                details.appendPlainText(value)
            if kind in ("done", "error"):
                state["busy"] = False
                cancel.setEnabled(False)
                progress_bar.setRange(0, 1)
                for button in buttons:
                    button.setEnabled(True)
                try:
                    refresh()
                except Exception as exc:
                    details.appendPlainText(str(exc))
    online.clicked.connect(online_action)
    local.clicked.connect(local_action)
    repair.clicked.connect(repair_current)
    verify_button.clicked.connect(verify)
    rollback.clicked.connect(rollback_action)
    cancel_pending.clicked.connect(lambda: run(lambda: store.cancel_pending() or "Pending change cancelled. Files and data were retained."))
    cancel.clicked.connect(cancelled.set)
    def runtime_diagnostics():
        import dsh_manager
        dsh_manager.show_version_manager()
    advanced.clicked.connect(runtime_diagnostics)
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
        refresh()
    except Exception as exc:
        status.setText(str(exc))
    _WINDOW = window
    window.show()
    return window
