"""One-click launcher for the dsh-houdini dev loop.

Single action: restart BOTH ends to pick up code changes, then open the UI.

  1. restart the Houdini bridge INSIDE this Houdini session (stop → reload
     dsh_bridge / dsh_hou_helpers → start), so the latest Python helpers are live
  2. restart the dsh web frontend (kill the node process on :3081 → relaunch),
     so the latest compiled plugin (lib/) is live
  3. open the embedded web UI (dsh_webview), falling back to the browser

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
import time
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


def start_frontend() -> str:
    """Boot the dsh web frontend if it is not already up; returns status text."""
    if _port_open(FRONTEND_HOST, FRONTEND_PORT):
        return f"frontend already running on {FRONTEND_URL}"

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
        "cwd": _PROJECT_ROOT,
        "close_fds": True,
        "shell": SHELL,
        "env": dict(os.environ, NPM_CONFIG_CACHE=NPM_CACHE),
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    with open(FRONTEND_LOG, "ab") as log:
        kwargs["stdout"] = log
        subprocess.Popen(cmd, **kwargs)
    return f"frontend starting on {FRONTEND_URL} (log: {FRONTEND_LOG})"


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


def launch() -> None:
    """Restart both ends and open the UI; reported through a Houdini message box."""
    detail = "\n".join([
        restart_bridge(),
        restart_frontend(),
        start_frontend(),
        open_ui(),
    ])
    print("[dsh-houdini]\n" + detail)
    hou.ui.displayMessage(detail, title="dsh-houdini", severity=hou.severityType.Message)


if __name__ == "__main__":
    launch()
