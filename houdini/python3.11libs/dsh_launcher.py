"""One-click launcher for the dsh-houdini dev loop.

Single action: restart BOTH ends to pick up code changes, then open the UI.

  1. restart the Houdini bridge INSIDE this Houdini session (stop → reload
     dsh_bridge / dsh_hou_helpers → start), so the latest Python helpers are live
  2. restart the dsh web frontend (kill the node process on :3081 → relaunch),
     so the latest compiled plugin (lib/) is live
  3. WAIT until the frontend listens on :3081 (GUI: cancellable progress
     dialog; a cold npx cache downloads the whole dsh CLI and takes minutes),
     then open the embedded web UI (dsh_webview), falling back to the browser

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
#   * Default (SHELL=True): `npx --yes @deepseek-ai/dsh` — portable, npx fetches
#     the published CLI on first run.
#   * To pin a local install instead, set SHELL=False and set DSH_BIN to your
#     local dsh CLI's bin.js (NODE falls back to `node` on PATH).
SHELL = True
FRONTEND_SHELL_CMD = 'npx --yes @deepseek-ai/dsh web --port {port}'

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


def ensure_dependencies() -> str:
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
        try:
            proc = subprocess.run(
                "npm install --no-audit --no-fund --loglevel=error",
                cwd=_PROJECT_ROOT, capture_output=True, timeout=600, shell=True,
                creationflags=_CREATE_NO_WINDOW,
                env=dict(os.environ, NPM_CONFIG_CACHE=NPM_CACHE),
            )
            ok = proc.returncode == 0
        except Exception:
            ok = False
        if not ok:
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
        cmd: list[str] | str = FRONTEND_SHELL_CMD.format(port=FRONTEND_PORT)
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


def open_browser() -> str:
    webbrowser.open(FRONTEND_URL)
    return f"opened {FRONTEND_URL}"


def open_ui() -> str:
    """Open the embedded web UI; fall back to the default browser."""
    _module_path_on_syspath()
    try:
        import dsh_webview
        return dsh_webview.show_webview()
    except Exception:
        return open_browser()


# --- wait-for-readiness ------------------------------------------------------

# A first-ever launch downloads the whole dsh CLI into NPM_CACHE and can take
# many minutes; opening the UI before the port listens shows
# ERR_CONNECTION_REFUSED. There is deliberately NO time cap on the wait: the
# GUI dialog's cancel button is the escape hatch, and both paths bail out as
# soon as the frontend process dies without ever listening.
FRONTEND_WAIT_INTERVAL = 0.5     # seconds (headless poll cadence)
DIALOG_TICK_MS = 30              # GUI tick — drives the progress sweep smoothly

# Keeps the spawned frontend process / QTimer / QProgressDialog alive across
# event-loop turns (GC would kill them).
_PENDING: dict = {}


def _report(detail: str) -> None:
    """最终状态只输出到 Houdini 控制台（右下角），不再弹模态窗口。"""
    print("[dsh-houdini] " + detail.replace("\n", "; "))


def _start_and_wait_frontend(state: dict) -> None:
    """Worker thread: restart the frontend, then poll until it listens or dies.

    MUST run off the main thread: on this machine a connect() to a closed
    localhost port blocks until the timeout (~300ms — no instant RST), so
    probing on the GUI thread freezes Houdini's event loop between ticks.
    Writes into `state`: "detail" (restart/start status lines), then "result"
    as "ready" / "dead" / "error". Exits early when state["canceled"] is set.
    """
    try:
        state["detail"] = "\n".join([
            ensure_dependencies(),
            restart_frontend(),
            start_frontend(state.get("frontend_cwd")),
        ])
        proc = _PENDING.get("proc")
        while not state["canceled"]:
            if _port_open(FRONTEND_HOST, FRONTEND_PORT):
                state["result"] = "ready"
                return
            if proc is not None and proc.poll() is not None:
                state["result"] = "dead"  # died without ever listening
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
    thread only spins the loading animation and checks a state flag. No time
    cap: cancel is the escape hatch; both paths stop waiting the moment the
    spawned frontend process exits without ever listening.

    frontend_cwd = 前端进程 cwd（= dsh 默认工作区根），由调用方在主线程经
    _hip_dir() 解析（worker 线程禁止碰 hou）。
    """
    try:
        from hutil.Qt import QtCore, QtGui, QtWidgets
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

    class _Spinner(QtWidgets.QWidget):
        """无限循环的圆弧旋转加载动画（QPainter 手绘，按 tick 推进角度）。"""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._angle = 0
            self.setFixedSize(30, 30)

        def advance(self, step: int = 10) -> None:
            self._angle = (self._angle + step) % 360
            self.update()

        def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            pen = QtGui.QPen(QtGui.QColor("#5b9dff"))
            pen.setWidthF(3.0)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(self.rect().adjusted(3, 3, -3, -3), -self._angle * 16, 270 * 16)
            painter.end()

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("dsh-houdini")
    dialog.setWindowModality(QtCore.Qt.NonModal)
    dialog.setMinimumWidth(400)
    dialog.setStyleSheet(
        "QDialog { background: #26272b; }"
        "QLabel#main { color: #f0f0f0; font-size: 15px; font-weight: 700; }"
        "QLabel#sub { color: #9a9ba2; font-size: 12px; }"
        "QPushButton { color: #e8e8e8; background: #3a3b41; border: none;"
        " border-radius: 4px; padding: 5px 18px; }"
        "QPushButton:hover { background: #4a4b52; }"
    )
    main_label = QtWidgets.QLabel("正在启动 dsh 前端…")
    main_label.setObjectName("main")
    sub_label = QtWidgets.QLabel(
        "首次运行需下载 dsh CLI，可能需要几分钟。\n"
        "随时可以取消，稍后在浏览器打开 " + FRONTEND_URL
    )
    sub_label.setObjectName("sub")
    sub_label.setAlignment(QtCore.Qt.AlignCenter)
    spinner = _Spinner(dialog)
    cancel_btn = QtWidgets.QPushButton("取消")
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(16, 18, 16, 16)
    layout.setSpacing(8)
    layout.addWidget(spinner, alignment=QtCore.Qt.AlignCenter)
    layout.addWidget(main_label, alignment=QtCore.Qt.AlignCenter)
    layout.addWidget(sub_label, alignment=QtCore.Qt.AlignCenter)
    layout.addWidget(cancel_btn, alignment=QtCore.Qt.AlignRight)
    dialog.show()

    # 主线程只转动画 + 查标志位；前端重启和端口探测全在 worker 线程。
    state: dict = {"canceled": False, "result": None, "detail": "", "frontend_cwd": frontend_cwd}
    cancel_btn.clicked.connect(lambda: state.update(canceled=True))
    threading.Thread(target=_start_and_wait_frontend, args=(state,), daemon=True).start()

    def finish(status: str) -> None:
        timer.stop()
        dialog.close()
        _PENDING.clear()
        _report(detail + "\n" + state["detail"] + "\n" + status)

    def tick() -> None:
        spinner.advance()
        if state["canceled"]:
            timer.stop()
            dialog.close()
            _PENDING.clear()
            print(f"[dsh-houdini] wait cancelled; frontend may still come up on {FRONTEND_URL}")
            return
        result = state["result"]
        if result == "ready":
            finish(open_ui())
        elif result == "dead":
            finish(f"前端进程已退出且未监听 {FRONTEND_URL}，请查看日志：\n{FRONTEND_LOG}")
        elif result == "error":
            finish(f"前端启动等待线程出错：\n{state.get('error', 'unknown')}")

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


if __name__ == "__main__":
    launch()
