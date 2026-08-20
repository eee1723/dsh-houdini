"""Houdini-native version and diagnostics panel for DSH-Houdini."""

from __future__ import annotations

import glob
import json
import os
import shutil
import socket
import subprocess
import threading

import hou


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NPM_CACHE = os.path.join(_PROJECT_ROOT, ".npm-cache")
_FRONTEND_LOG = os.path.join(_PROJECT_ROOT, ".dsh-web.log")
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_WINDOW = None
_TIMER = None


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _run(args: list[str], timeout: int = 20) -> str:
    proc = subprocess.run(
        args,
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
        raise RuntimeError(message.splitlines()[-1])
    return proc.stdout.strip()


def _port_open(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.2)
        sock.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _plugin_identity() -> tuple[str, str]:
    version = _read_json(os.path.join(_PROJECT_ROOT, "package.json")).get("version", "unknown")
    try:
        branch = _run(["git", "branch", "--show-current"], 5) or "detached"
        commit = _run(["git", "rev-parse", "--short", "HEAD"], 5)
        dirty = bool(_run(["git", "status", "--porcelain"], 5))
        revision = f"{branch}@{commit}" + (" | local changes" if dirty else " | clean")
    except Exception as exc:
        revision = f"Git status unavailable: {exc}"
    return str(version), revision


def _cached_dsh_versions() -> list[str]:
    pattern = os.path.join(
        _NPM_CACHE, "_npx", "*", "node_modules", "@deepseek-ai", "dsh", "package.json",
    )
    versions = {
        str(_read_json(path).get("version"))
        for path in glob.glob(pattern)
        if _read_json(path).get("version")
    }
    return sorted(versions, reverse=True)


def _check_updates(state: dict) -> None:
    try:
        npm = shutil.which("npm")
        if not npm:
            raise RuntimeError("npm was not found; check the Node.js installation")
        raw = _run([npm, "view", "@deepseek-ai/dsh", "version", "dist-tags", "--json"], 45)
        npm_info = json.loads(raw)
        tags = npm_info.get("dist-tags", {}) if isinstance(npm_info, dict) else {}
        latest = tags.get("latest") or npm_info.get("version", "unknown")
        next_version = tags.get("next", "n/a")

        remote_note = "remote not configured"
        try:
            remote = _run(["git", "ls-remote", "origin", "refs/heads/main"], 30)
            remote_head = remote.split()[0] if remote else ""
            local_head = _run(["git", "rev-parse", "HEAD"], 5)
            remote_note = "matches origin/main" if remote_head == local_head else "origin/main has a different commit"
        except Exception as exc:
            remote_note = f"remote check failed: {exc}"

        state.update(
            checking=False,
            result="ok",
            dsh_latest=f"latest {latest} | next {next_version}",
            plugin_remote=remote_note,
            message="Check complete. DSH is a developer preview; verify Houdini tools and Trace after upgrading.",
        )
    except Exception as exc:
        state.update(
            checking=False,
            result="error",
            message=f"Update check failed: {exc}",
        )


def show_version_manager() -> None:
    """Show the non-modal version/diagnostics panel; must run on Houdini's GUI thread."""
    global _WINDOW, _TIMER

    from hutil.Qt import QtCore, QtWidgets

    if _WINDOW is not None and _WINDOW.isVisible():
        _WINDOW.raise_()
        _WINDOW.activateWindow()
        return

    plugin_version, plugin_revision = _plugin_identity()
    cached = _cached_dsh_versions()

    dialog = QtWidgets.QDialog(hou.qt.mainWindow())
    dialog.setWindowTitle("DSH-Houdini - Version & Diagnostics")
    dialog.setWindowModality(QtCore.Qt.NonModal)
    dialog.setMinimumWidth(590)
    dialog.setStyleSheet(
        "QDialog { background: #23262b; }"
        "QLabel#eyebrow { color: #ff8a2a; font: 700 10px 'Segoe UI'; }"
        "QLabel#title { color: #eef0f2; font: 600 20px 'Segoe UI'; }"
        "QLabel#hint { color: #9299a3; font: 12px 'Segoe UI'; }"
        "QLabel#section { color: #ffb06b; font: 600 12px 'Segoe UI'; }"
        "QLabel#key { color: #9299a3; font: 11px 'Segoe UI'; }"
        "QLabel#value { color: #e5e8eb; font: 12px 'Consolas'; }"
        "QFrame#card { background: #2c3036; border: 1px solid #3b4048; border-radius: 6px; }"
        "QPushButton { color: #e8eaed; background: #373b42; border: 1px solid #4a5059;"
        " border-radius: 4px; padding: 7px 14px; }"
        "QPushButton:hover { background: #454a53; }"
        "QPushButton#primary { background: #c86118; border-color: #ee7d2d; }"
        "QPushButton#primary:hover { background: #df7122; }"
    )

    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(22, 20, 22, 18)
    layout.setSpacing(12)

    eyebrow = QtWidgets.QLabel("DSH-HOUDINI / CONTROL")
    eyebrow.setObjectName("eyebrow")
    title = QtWidgets.QLabel("Version & Diagnostics")
    title.setObjectName("title")
    hint = QtWidgets.QLabel("Inspect the runtime even when the Web UI cannot start.")
    hint.setObjectName("hint")
    layout.addWidget(eyebrow)
    layout.addWidget(title)
    layout.addWidget(hint)

    service_label = QtWidgets.QLabel()
    service_label.setObjectName("value")
    layout.addWidget(service_label)

    card = QtWidgets.QFrame()
    card.setObjectName("card")
    grid = QtWidgets.QGridLayout(card)
    grid.setContentsMargins(16, 14, 16, 14)
    grid.setHorizontalSpacing(18)
    grid.setVerticalSpacing(9)

    def add_row(row: int, key: str, value: str):
        key_label = QtWidgets.QLabel(key)
        key_label.setObjectName("key")
        value_label = QtWidgets.QLabel(value)
        value_label.setObjectName("value")
        value_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        grid.addWidget(key_label, row, 0)
        grid.addWidget(value_label, row, 1)
        return value_label

    add_row(0, "DSH-Houdini", f"v{plugin_version}")
    add_row(1, "Git revision", plugin_revision)
    plugin_remote_label = add_row(2, "Plugin update", "Not checked")
    add_row(3, "DSH launch spec", os.environ.get("DSH_HOUDINI_DSH_SPEC", "@deepseek-ai/dsh"))
    add_row(4, "Cached DSH", ", ".join(cached) if cached else "Not found")
    dsh_latest_label = add_row(5, "DSH release channel", "Not checked")
    layout.addWidget(card)

    message_label = QtWidgets.QLabel("Version checks are read-only. Updates still run through Git and npm.")
    message_label.setObjectName("hint")
    message_label.setWordWrap(True)
    layout.addWidget(message_label)

    buttons = QtWidgets.QHBoxLayout()
    restart_btn = QtWidgets.QPushButton("Restart Services")
    restart_btn.setObjectName("primary")
    check_btn = QtWidgets.QPushButton("Check Updates")
    copy_btn = QtWidgets.QPushButton("Copy Update Commands")
    log_btn = QtWidgets.QPushButton("Open Log")
    close_btn = QtWidgets.QPushButton("Close")
    buttons.addWidget(restart_btn)
    buttons.addWidget(check_btn)
    buttons.addWidget(copy_btn)
    buttons.addWidget(log_btn)
    buttons.addStretch(1)
    buttons.addWidget(close_btn)
    layout.addLayout(buttons)

    state = {"checking": False, "result": None, "message": ""}

    def refresh_services() -> None:
        bridge = _port_open(8765)
        frontend = _port_open(3081)
        bridge_color = "#62c987" if bridge else "#e17068"
        frontend_color = "#62c987" if frontend else "#e17068"
        bridge_state = "ONLINE" if bridge else "OFFLINE"
        frontend_state = "ONLINE" if frontend else "OFFLINE"
        service_label.setText(
            f'<span style="color:{bridge_color}">[{bridge_state}]</span> Houdini Bridge :8765&nbsp;&nbsp;&nbsp;'
            f'<span style="color:{frontend_color}">[{frontend_state}]</span> DSH Web :3081'
        )

    def restart_services() -> None:
        dialog.close()
        import dsh_launcher
        dsh_launcher.launch()

    def check_updates() -> None:
        if state["checking"]:
            return
        state.update(checking=True, result=None, message="Checking npm and GitHub...")
        check_btn.setEnabled(False)
        check_btn.setText("Checking...")
        message_label.setText(state["message"])
        threading.Thread(target=_check_updates, args=(state,), daemon=True).start()

    def copy_commands() -> None:
        command = (
            f'Set-Location -LiteralPath "{_PROJECT_ROOT}"\r\n'
            "git pull --ff-only\r\n"
            "npm install\r\n"
            "npm run build"
        )
        QtWidgets.QApplication.clipboard().setText(command)
        message_label.setText("Update commands copied. Restart Houdini after launcher or menu changes.")

    def open_log() -> None:
        if not os.path.isfile(_FRONTEND_LOG):
            message_label.setText("No frontend log exists yet. Start the service once, then try again.")
            return
        try:
            os.startfile(_FRONTEND_LOG)  # type: ignore[attr-defined]
        except Exception as exc:
            message_label.setText(f"Could not open the log: {exc}\n{_FRONTEND_LOG}")

    def tick() -> None:
        refresh_services()
        if not state["checking"] and state["result"] is not None:
            check_btn.setEnabled(True)
            check_btn.setText("Check Again")
            if state["result"] == "ok":
                plugin_remote_label.setText(state["plugin_remote"])
                dsh_latest_label.setText(state["dsh_latest"])
            message_label.setText(state["message"])
            state["result"] = None

    def cleanup(_code: int) -> None:
        global _WINDOW, _TIMER
        if _TIMER is not None:
            _TIMER.stop()
        _WINDOW = None
        _TIMER = None

    restart_btn.clicked.connect(restart_services)
    check_btn.clicked.connect(check_updates)
    copy_btn.clicked.connect(copy_commands)
    log_btn.clicked.connect(open_log)
    close_btn.clicked.connect(dialog.close)
    dialog.finished.connect(cleanup)

    timer = QtCore.QTimer(dialog)
    timer.timeout.connect(tick)
    timer.start(1000)
    _WINDOW = dialog
    _TIMER = timer
    refresh_services()
    dialog.show()


if __name__ == "__main__":
    show_version_manager()
