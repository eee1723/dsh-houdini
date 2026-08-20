"""One-click launcher for the dsh-houdini dev loop.

Single action: restart BOTH ends to pick up code changes, then open the UI.

  1. restart the Houdini bridge INSIDE this Houdini session (stop → reload
     dsh_bridge / dsh_hou_helpers → start), so the latest Python helpers are live
  2. restart the dsh web frontend (kill the node process on :3081 → relaunch),
     so the latest compiled plugin (lib/) is live
  3. WAIT until the frontend listens on :3081 (GUI: staged percentage dialog;
     a cold npx cache downloads the whole dsh CLI and takes minutes),
     then open the embedded web UI (dsh_webview); external browser fallback is disabled

This is the dev-loop button: click it after `npm run build` or after editing
any Houdini-side Python and both ends refresh without restarting Houdini.

The frontend boots the `web` profile WITHOUT a patch overlay; the `houdini`
agent preset mounts dsh-houdini (by package name, after
`dsh plugin --profile web add E:/dsh-houdini`).

Use it from Houdini's Python Shell (after installing the package):

    import dsh_launcher
    dsh_launcher.launch()

Or wire it into a menu — see MainMenuCommon.xml.
"""

from __future__ import annotations

import importlib
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser

import hou

# --- editable configuration --------------------------------------------------

# This repository's root, derived from THIS file's own location so the package
# works from any checkout path (no hardcoded drive letters or usernames).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8765

FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 3081
FRONTEND_URL = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"

# Where the frontend process writes its stdout/stderr.
FRONTEND_LOG = os.path.join(_PROJECT_ROOT, ".dsh-web.log")

# The frontend boots the `web` profile without a patch overlay — the `houdini`
# agent preset mounts dsh-houdini. (The old `--patch cordis.dev.yml` file://
# overlay is retired: it cannot be discovered as a package for the client half.)

# How to boot the dsh web frontend.
#   * Default (SHELL=True): use the published npm package and its normal npx
#     cache. Set DSH_HOUDINI_DSH_SPEC to test a specific CLI release without
#     editing this file (for example @deepseek-ai/dsh@0.1.0-rc.7).
#   * To pin a local install instead, set SHELL=False and set DSH_BIN to your
#     local dsh CLI's bin.js (NODE falls back to `node` on PATH).
SHELL = True
DSH_SPEC = os.environ.get("DSH_HOUDINI_DSH_SPEC", "@deepseek-ai/dsh")
FRONTEND_SHELL_CMD = 'npx --yes {spec} web --port {port}'

# npm cache for npx. The default cache is write-blocked on sandboxed machines
# (EPERM), so point npm at a project-local cache — works everywhere.
NPM_CACHE = os.path.join(_PROJECT_ROOT, ".npm-cache")

# Local-install fallback (used only when SHELL is False):
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
DSH_BIN = ""

# Agent presets live in this repo as templates (presets/<name>/); the dsh host
# reads them from ~/.dsh/.agent-presets/<name>/. launch() syncs them so prompt
# or config edits take effect from the menu — no manual Copy-Item step.
PRESET_SRC = os.path.join(_PROJECT_ROOT, "presets")
PRESET_DST = os.path.join(os.path.expanduser("~"), ".dsh", ".agent-presets")


# hip 未保存时的中立工作区（仓库的兄弟目录，按需创建）：产出永不落仓库。
_FALLBACK_WORKSPACE = os.path.join(os.path.dirname(_PROJECT_ROOT), "dsh-houdini-workspace")


def _hip_dir() -> str:
    """当前 hip 文件的目录——前端工作区种子。

    dsh 的默认工作区 = 前端进程的启动目录（"the invoking directory is the
    default workspace root"）。工作区决定 workspace-write 沙箱的边界和
    vision 等 dsh 侧工具的可读范围，所以它必须对准 $HIP，而不是插件仓库
    （2026-08-18 复盘：工作区=仓库时，agent 为让 vision 工具读到截图被迫
    把产出写进仓库根目录）。hip 从未保存过时用中立的后备工作区目录，
    再失败才回退项目根。注意：访问 hou —— 只能在主线程调用本函数。
    """
    try:
        p = hou.hipFile.path()
        if p and os.path.basename(p).lower() != "untitled.hip":
            d = os.path.dirname(os.path.abspath(p))
            if os.path.isdir(d):
                return d
    except Exception:
        pass
    try:
        os.makedirs(_FALLBACK_WORKSPACE, exist_ok=True)
        return _FALLBACK_WORKSPACE
    except Exception:
        return _PROJECT_ROOT

# Helper processes (netstat / taskkill / frontend tree) must never pop a
# visible terminal window when launched from Houdini's GUI.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Runtime deps the compiled plugin (lib/) imports; the frontend resolves them
# from THIS repo's node_modules. 2026-08-17 根因实录：node_modules 被 npm 和
# pnpm 混管时，pnpm 会把「别的包管理器装的包」挪进 node_modules/.ignored/
# （hideAlienModules），前端随即 ERR_MODULE_NOT_FOUND。每次启动自检：优先从
# .ignored 挪回（免费），仍缺再 npm install。
REQUIRED_PACKAGES = ["@deepseek-ai/schemastery", "@deepseek-ai/dsh-tools"]


def ensure_dependencies(on_install=None) -> str:
    """Make sure the plugin's runtime deps are resolvable from node_modules."""
    nm = os.path.join(_PROJECT_ROOT, "node_modules")
    restored = []
    for pkg in REQUIRED_PACKAGES:
        dest = os.path.join(nm, *pkg.split("/"))
        if os.path.isdir(dest):
            continue
        hidden = os.path.join(nm, ".ignored", *pkg.split("/"))
        if os.path.isdir(hidden):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(hidden, dest)
            restored.append(pkg)
    missing = [
        pkg for pkg in REQUIRED_PACKAGES
        if not os.path.isdir(os.path.join(nm, *pkg.split("/")))
    ]
    if missing:
        if on_install is not None:
            on_install(missing)
        failure_output = ""
        try:
            proc = subprocess.run(
                "npm install --no-audit --no-fund --loglevel=error",
                cwd=_PROJECT_ROOT, capture_output=True, timeout=600, shell=True,
                creationflags=_CREATE_NO_WINDOW,
                env=dict(os.environ, NPM_CONFIG_CACHE=NPM_CACHE),
            )
            ok = proc.returncode == 0
            if not ok:
                raw = (proc.stdout or b"") + b"\n" + (proc.stderr or b"")
                failure_output = raw.decode("utf-8", errors="replace")
        except Exception:
            ok = False
            failure_output = traceback.format_exc()
        if not ok:
            try:
                with open(FRONTEND_LOG, "ab") as log:
                    diagnostic = (
                        "\n[dsh-houdini] plugin dependency restore failed\n"
                        + failure_output[-12000:] + "\n"
                    )
                    log.write(diagnostic.encode("utf-8", errors="replace"))
            except Exception:
                pass
            return "dependency restore FAILED (missing: " + ", ".join(missing) + ")"
        restored.extend(missing)
    if restored:
        return "dependencies restored: " + ", ".join(restored)
    return "dependencies ok"


def sync_presets() -> str:
    """Copy repo presets over ~/.dsh/.agent-presets/ (adds/overwrites, never deletes)."""
    if not os.path.isdir(PRESET_SRC):
        return "no presets/ directory in repo"
    synced = []
    for name in sorted(os.listdir(PRESET_SRC)):
        src = os.path.join(PRESET_SRC, name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(PRESET_DST, name), dirs_exist_ok=True)
            synced.append(name)
    return "presets synced: " + (", ".join(synced) if synced else "(none)")


def _port_open(host: str, port: int) -> bool:
    """Return True when something is already listening on host:port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.3)
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _port_pid(port: int) -> int | None:
    """PID of the process listening on :port (any local address), or None."""
    if os.name != "nt":
        return None
    try:
        proc = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception:
        return None
    raw = proc.stdout or b""
    # 中文 Windows 的 netstat 输出可能是 GBK；我们只解析 ASCII 列（TCP/地址/状态/PID），
    # 用 errors="replace" 容错解码即可。
    text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        if not parts[1].endswith(f":{port}"):
            continue
        if "LISTENING" not in parts:
            continue
        try:
            return int(parts[-1])
        except ValueError:
            continue
    return None


def _kill_port_process(port: int) -> bool:
    """Force-kill whatever process listens on :port (never the Houdini process)."""
    pid = _port_pid(port)
    if pid is None or pid == os.getpid():
        return False
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        return True
    except Exception:
        return False


def _module_path_on_syspath() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.append(here)


def restart_bridge() -> str:
    """Stop the old bridge, reload the Python modules, start a fresh bridge."""
    _module_path_on_syspath()
    import dsh_bridge
    import dsh_hou_helpers

    dsh_bridge.stop()                      # 停进程内旧 server（线程）
    _kill_port_process(BRIDGE_PORT)        # 若 8765 被外部 hython 占用则杀掉
    importlib.reload(dsh_hou_helpers)      # 拾取最新 helper
    importlib.reload(dsh_bridge)           # 拾取最新 bridge
    dsh_bridge.start(BRIDGE_PORT, BRIDGE_HOST)
    return f"bridge restarted on {BRIDGE_HOST}:{BRIDGE_PORT}"


def restart_frontend() -> str:
    """Kill the dsh web frontend process so it can be relaunched fresh."""
    if _kill_port_process(FRONTEND_PORT):
        time.sleep(0.5)  # 让端口释放，避免 TIME_WAIT 影响重启
        return f"frontend stopped (port {FRONTEND_PORT})"
    return "frontend not running"


def start_frontend(workspace_dir: str | None = None) -> str:
    """Boot the dsh web frontend if it is not already up; returns status text.

    workspace_dir = 前端进程 cwd = dsh 默认工作区根（应对准 $HIP 目录，
    由调用方在主线程用 _hip_dir() 解析后传入；None 回退项目根）。
    """
    if _port_open(FRONTEND_HOST, FRONTEND_PORT):
        return f"frontend already running on {FRONTEND_URL}"

    cwd = workspace_dir or _PROJECT_ROOT

    if SHELL:
        cmd: list[str] | str = FRONTEND_SHELL_CMD.format(
            port=FRONTEND_PORT, spec=DSH_SPEC,
        )
    else:
        if not NODE or not os.path.exists(NODE) or not DSH_BIN or not os.path.exists(DSH_BIN):
            return (
                "frontend command not found:\n"
                f"  NODE={NODE}\n  DSH_BIN={DSH_BIN}\n"
                "Set SHELL=True (npx) or fix NODE/DSH_BIN at the top of dsh_launcher.py"
            )
        cmd = [NODE, DSH_BIN, "web", "--port", str(FRONTEND_PORT)]

    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stderr": subprocess.STDOUT,
        "cwd": cwd,
        "close_fds": True,
        "shell": SHELL,
        "env": dict(os.environ, NPM_CONFIG_CACHE=NPM_CACHE),
    }
    if os.name == "nt":
        # DETACHED_PROCESS would leave the cmd/npx/node tree console-less, and
        # every console-subsystem child then allocates its OWN visible terminal
        # window. CREATE_NO_WINDOW gives the whole tree a single hidden console.
        kwargs["creationflags"] = _CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP

    with open(FRONTEND_LOG, "ab") as log:
        kwargs["stdout"] = log
        _PENDING["proc"] = subprocess.Popen(cmd, **kwargs)
    return f"frontend starting on {FRONTEND_URL} (workspace: {cwd}; log: {FRONTEND_LOG})"


def open_ui() -> str:
    """Open only the embedded web UI; never launch an external browser."""
    _module_path_on_syspath()
    try:
        import dsh_webview
        return dsh_webview.show_webview()
    except Exception as exc:
        message = f"Could not open the embedded DSH workspace: {exc}"
        _report(message)
        try:
            hou.ui.displayMessage(
                message + "\nOpen DSH-Houdini > Version & Diagnostics to inspect the log.",
                severity=hou.severityType.Error,
                title="DSH-Houdini",
            )
        except Exception:
            pass
        return message


# --- wait-for-readiness ------------------------------------------------------

# A first-ever launch downloads the whole dsh CLI into NPM_CACHE and can take
# many minutes; opening the UI before the port listens shows
# ERR_CONNECTION_REFUSED. The external npm/npx process can hang on a broken
# network without exiting, so cap the wait at a diagnosable terminal state.
FRONTEND_WAIT_INTERVAL = 0.5     # seconds (headless poll cadence)
FRONTEND_WAIT_TIMEOUT = 600      # seconds; cold installs normally finish sooner
DIALOG_TICK_MS = 100             # GUI tick — elapsed time + worker state refresh

# Keeps the spawned frontend process / QTimer / QProgressDialog alive across
# event-loop turns (GC would kill them).
_PENDING: dict = {}


def _report(detail: str) -> None:
    """最终状态只输出到 Houdini 控制台（右下角），不再弹模态窗口。"""
    print("[dsh-houdini] " + detail.replace("\n", "; "))


def _set_startup_state(
    state: dict, progress: int, phase: int, title: str, message: str,
) -> None:
    """Publish one startup snapshot from the worker thread."""
    state.update(
        progress=max(0, min(100, progress)),
        phase=phase,
        title=title,
        message=message,
    )


def _terminate_pending_frontend() -> None:
    """Stop only the frontend process tree spawned by this launch attempt."""
    proc = _PENDING.get("proc")
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=10,
                creationflags=_CREATE_NO_WINDOW,
            )
        else:
            proc.terminate()
    except Exception:
        pass


def _start_and_wait_frontend(state: dict) -> None:
    """Worker thread: restart the frontend, then poll until it listens or dies.

    MUST run off the main thread: on this machine a connect() to a closed
    localhost port blocks until the timeout (~300ms — no instant RST), so
    probing on the GUI thread freezes Houdini's event loop between ticks.
    Writes stage snapshots and `result` (ready/dead/timeout/error) into state.
    Exits early when state["canceled"] is set.
    """
    try:
        details = []
        _set_startup_state(state, 12, 1, "Checking plugin environment", "Verifying local dependencies")

        def on_install(missing: list[str]) -> None:
            _set_startup_state(
                state, 18, 1, "Installing plugin dependencies",
                "The first install may take several minutes: " + ", ".join(missing),
            )

        dependency_status = ensure_dependencies(on_install)
        details.append(dependency_status)
        if "FAILED" in dependency_status:
            raise RuntimeError(dependency_status)

        _set_startup_state(state, 32, 2, "Stopping previous frontend", f"Releasing port {FRONTEND_PORT}")
        details.append(restart_frontend())

        _set_startup_state(
            state, 48, 2, "Starting DSH", f"Creating frontend process: {DSH_SPEC}",
        )
        details.append(start_frontend(state.get("frontend_cwd")))
        state["detail"] = "\n".join(details)
        proc = _PENDING.get("proc")
        if proc is None:
            raise RuntimeError("frontend process was not created")

        started_at = time.monotonic()
        _set_startup_state(
            state, 62, 3, "Waiting for DSH service", f"Connecting to {FRONTEND_URL}",
        )
        while not state["canceled"]:
            if _port_open(FRONTEND_HOST, FRONTEND_PORT):
                _set_startup_state(state, 90, 4, "Opening Houdini workspace", "Service is ready")
                state["result"] = "ready"
                return
            if proc is not None and proc.poll() is not None:
                state["result"] = "dead"  # died without ever listening
                return
            if time.monotonic() - started_at >= FRONTEND_WAIT_TIMEOUT:
                state["result"] = "timeout"
                _terminate_pending_frontend()
                return
            time.sleep(FRONTEND_WAIT_INTERVAL)
    except Exception:
        state["error"] = traceback.format_exc()
        state["result"] = "error"


def open_ui_when_ready(detail: str, frontend_cwd: str | None = None) -> None:
    """Restart the frontend, then open the UI once it listens on FRONTEND_PORT.

    The frontend restart AND the port polling run on a worker thread (the
    connect-to-closed-port probe blocks ~300ms on this machine — on the GUI
    thread it froze the dialog animation and even window dragging). The main
    thread only refreshes the staged progress snapshot and checks a state flag.
    A timeout prevents a stalled npm/network operation from spinning forever.

    frontend_cwd = 前端进程 cwd（= dsh 默认工作区根），由调用方在主线程经
    _hip_dir() 解析（worker 线程禁止碰 hou）。
    """
    try:
        from hutil.Qt import QtCore, QtWidgets
        parent = hou.qt.mainWindow()
    except Exception:
        # hython: no Qt — run the same worker inline, then open the browser.
        headless: dict = {"canceled": False, "result": None, "detail": "", "frontend_cwd": frontend_cwd}
        _start_and_wait_frontend(headless)
        detail += "\n" + headless["detail"]
        if headless["result"] == "ready":
            _report(detail + "\n" + open_ui())
        else:
            _report(
                detail
                + f"\nfrontend exited without listening on {FRONTEND_URL}; "
                + f"see log: {FRONTEND_LOG}"
            )
        return

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("dsh-houdini")
    dialog.setWindowModality(QtCore.Qt.NonModal)
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(
        "QDialog { background: #23262b; }"
        "QLabel#eyebrow { color: #ff8a2a; font: 700 10px 'Segoe UI'; }"
        "QLabel#main { color: #eef0f2; font: 600 17px 'Segoe UI'; }"
        "QLabel#percent { color: #eef0f2; font: 700 28px 'Consolas'; }"
        "QLabel#sub { color: #a9afb7; font: 12px 'Segoe UI'; }"
        "QLabel#pipeline { color: #7f8791; font: 11px 'Segoe UI'; }"
        "QLabel#elapsed { color: #7f8791; font: 11px 'Consolas'; }"
        "QProgressBar { background: #34383f; border: none; border-radius: 3px;"
        " height: 6px; text-align: center; color: transparent; }"
        "QProgressBar::chunk { background: #ff8a2a; border-radius: 3px; }"
        "QPushButton { color: #e8eaed; background: #373b42; border: 1px solid #474c55;"
        " border-radius: 4px; padding: 6px 16px; }"
        "QPushButton:hover { background: #444952; }"
    )

    eyebrow = QtWidgets.QLabel("DSH / HOUDINI  STARTUP")
    eyebrow.setObjectName("eyebrow")
    main_label = QtWidgets.QLabel("Preparing startup")
    main_label.setObjectName("main")
    percent_label = QtWidgets.QLabel("08%")
    percent_label.setObjectName("percent")
    header = QtWidgets.QHBoxLayout()
    header.addWidget(main_label)
    header.addStretch(1)
    header.addWidget(percent_label)

    progress_bar = QtWidgets.QProgressBar()
    progress_bar.setRange(0, 100)
    progress_bar.setValue(8)
    progress_bar.setTextVisible(False)
    pipeline_label = QtWidgets.QLabel()
    pipeline_label.setObjectName("pipeline")

    def pipeline_text(active: int) -> str:
        names = ["ENV", "PLUGIN", "FRONTEND", "SERVICE", "WORKSPACE"]
        rendered = []
        for index, name in enumerate(names):
            color = "#ff8a2a" if index == active else ("#d4d8dd" if index < active else "#707781")
            marker = "[x]" if index <= active else "[ ]"
            rendered.append(f'<span style="color:{color}">{marker} {name}</span>')
        return "&nbsp;&nbsp;--&nbsp;&nbsp;".join(rendered)

    pipeline_label.setText(pipeline_text(0))
    sub_label = QtWidgets.QLabel("Presets synced and Houdini bridge started")
    sub_label.setObjectName("sub")
    sub_label.setWordWrap(True)
    elapsed_label = QtWidgets.QLabel("00:00")
    elapsed_label.setObjectName("elapsed")
    log_btn = QtWidgets.QPushButton("Open Log")
    log_btn.setVisible(False)
    cancel_btn = QtWidgets.QPushButton("Stop")

    buttons = QtWidgets.QHBoxLayout()
    buttons.addWidget(elapsed_label)
    buttons.addStretch(1)
    buttons.addWidget(log_btn)
    buttons.addWidget(cancel_btn)
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(22, 20, 22, 18)
    layout.setSpacing(11)
    layout.addWidget(eyebrow)
    layout.addLayout(header)
    layout.addWidget(progress_bar)
    layout.addWidget(pipeline_label)
    layout.addWidget(sub_label)
    layout.addSpacing(4)
    layout.addLayout(buttons)
    dialog.show()

    # 主线程只刷新 worker 快照；前端重启和端口探测全在 worker 线程。
    state: dict = {
        "canceled": False,
        "result": None,
        "detail": "",
        "frontend_cwd": frontend_cwd,
        "progress": 8,
        "phase": 0,
        "title": "Preparing startup",
        "message": "Presets synced and Houdini bridge started",
    }
    launched_at = time.monotonic()

    def open_log() -> None:
        try:
            if os.name == "nt":
                os.startfile(FRONTEND_LOG)  # type: ignore[attr-defined]
            else:
                webbrowser.open("file://" + os.path.abspath(FRONTEND_LOG))
        except Exception as exc:
            _report(f"cannot open log: {exc}; {FRONTEND_LOG}")

    def cancel() -> None:
        state["canceled"] = True
        _terminate_pending_frontend()

    def cleanup_dialog(_code: int) -> None:
        # Closing the window while startup is still running means cancel.
        # A successful close must leave the now-serving frontend alive.
        if state.get("result") != "ready":
            state["canceled"] = True
            _terminate_pending_frontend()
        _PENDING.clear()

    log_btn.clicked.connect(open_log)
    cancel_btn.clicked.connect(cancel)
    dialog.finished.connect(cleanup_dialog)
    threading.Thread(target=_start_and_wait_frontend, args=(state,), daemon=True).start()

    def finish(status: str) -> None:
        timer.stop()
        dialog.close()
        _PENDING.clear()
        _report(detail + "\n" + state["detail"] + "\n" + status)

    def fail(message: str) -> None:
        timer.stop()
        main_label.setText("Startup failed")
        sub_label.setText(message + "\nOpen the log to inspect Node, npm, network, or DSH configuration errors.")
        progress_bar.setStyleSheet(
            "QProgressBar::chunk { background: #e85d55; border-radius: 3px; }"
        )
        log_btn.setVisible(True)
        cancel_btn.setText("Close")
        try:
            cancel_btn.clicked.disconnect(cancel)
        except Exception:
            pass
        cancel_btn.clicked.connect(dialog.close)
        _report(
            detail + "\n" + state.get("detail", "") + "\n" + message
            + "\nlog: " + FRONTEND_LOG
        )

    def tick() -> None:
        elapsed = int(time.monotonic() - launched_at)
        elapsed_label.setText(f"{elapsed // 60:02d}:{elapsed % 60:02d}")
        progress = state.get("progress", 8)
        progress_bar.setValue(progress)
        percent_label.setText(f"{progress:02d}%")
        main_label.setText(state.get("title", "Starting"))
        pipeline_label.setText(pipeline_text(state.get("phase", 0)))
        message = state.get("message", "")
        if elapsed >= 90 and state.get("phase") == 3:
            message += "\nThis is taking longer than expected. Check the network; startup stops after 10 minutes."
        sub_label.setText(message)
        if state["canceled"]:
            timer.stop()
            dialog.close()
            _PENDING.clear()
            print("[dsh-houdini] startup cancelled")
            return
        result = state["result"]
        if result == "ready":
            progress_bar.setValue(100)
            percent_label.setText("100%")
            finish(open_ui())
        elif result == "dead":
            fail(f"The frontend exited before listening on {FRONTEND_URL}")
        elif result == "timeout":
            fail("DSH did not become ready within 10 minutes. This startup was stopped.")
        elif result == "error":
            error_tail = state.get("error", "unknown").splitlines()[-1]
            fail("Startup error: " + error_tail)

    timer = QtCore.QTimer(parent)
    timer.timeout.connect(tick)
    _PENDING["timer"] = timer
    _PENDING["dialog"] = dialog
    timer.start(DIALOG_TICK_MS)


def launch() -> None:
    """Restart the bridge, then restart the frontend and open the UI when ready.

    The frontend restart/poll happens on a worker thread inside
    open_ui_when_ready (blocking probes must not touch the GUI thread);
    only the bridge restart — which touches `hou` — runs here. The frontend
    cwd is resolved here too (main thread): it seeds the dsh default
    workspace, which must track the current hip directory.
    """
    detail = "\n".join([
        sync_presets(),
        restart_bridge(),
    ])
    print("[dsh-houdini] " + detail.replace("\n", "; "))
    open_ui_when_ready(detail, _hip_dir())


def open_workspace() -> None:
    """Open the embedded workspace without restarting a healthy frontend.

    If the web service is absent, fall back to the full launch path. Keeping
    "open" separate from "restart" avoids destroying a live dsh session just
    because the user wants to bring its Houdini window to the front.
    """
    if not _port_open(FRONTEND_HOST, FRONTEND_PORT):
        launch()
        return

    details = [sync_presets()]
    if _port_open(BRIDGE_HOST, BRIDGE_PORT):
        details.append(f"bridge already running on {BRIDGE_HOST}:{BRIDGE_PORT}")
    else:
        details.append(restart_bridge())
    status = open_ui()
    _report("\n".join(details + [status]))


if __name__ == "__main__":
    launch()
