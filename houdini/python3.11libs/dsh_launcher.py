"""Launcher and runtime-refresh paths for dsh-houdini.

``open_workspace()`` is the normal menu action. It preserves a healthy DSH
frontend and current browser session, starts only missing services, and brings
the embedded UI forward.

``launch()`` is the explicit repair/development path used by the diagnostics
panel. It synchronizes presets, restarts the in-process Houdini bridge, restarts
the DSH frontend, waits until :3081 and Host RPC are ready, then reuses or
creates the newest Houdini-preset session whose workspace matches the current
``$HIP``. Use it after ``npm run build``, Houdini-side Python changes, or when
the runtime/workspace needs repair; it intentionally replaces the frontend.

The frontend boots the `web` profile WITHOUT a patch overlay; the `houdini`
agent preset mounts dsh-houdini (by package name, after
`dsh plugin --profile web add E:/dsh-houdini`).

Use it from Houdini's Python Shell (after installing the package):

    import dsh_launcher
    dsh_launcher.launch()

The menu wiring is defined in ``MainMenuCommon.xml``.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
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
HOUDINI_AGENT_PRESET = "houdini"
DSH_RPC_TIMEOUT = 20

# Where the frontend process writes its stdout/stderr.
FRONTEND_LOG = os.path.join(_PROJECT_ROOT, ".dsh-web.log")
FRONTEND_RUNTIME_STATE = os.path.join(_PROJECT_ROOT, ".dsh-runtime.json")

# The frontend boots the `web` profile without a patch overlay — the `houdini`
# agent preset mounts dsh-houdini. (The old `--patch cordis.dev.yml` file://
# overlay is retired: it cannot be discovered as a package for the client half.)

# How to boot the dsh web frontend.
#   * Default: directly execute a valid CLI already present in the project-local
#     npx cache. This avoids a warm launch blocking on npm registry resolution.
#   * With no cache, fall back to npx for the first download.
#   * Set DSH_HOUDINI_DSH_SPEC to test/update a specific CLI release through
#     npx, or DSH_HOUDINI_DSH_BIN to pin an already-installed bin.js.
#   * SHELL=False + DSH_BIN remains as a source-compatible developer override.
SHELL = True
DEFAULT_DSH_SPEC = "@deepseek-ai/dsh"
DSH_SPEC = os.environ.get("DSH_HOUDINI_DSH_SPEC", DEFAULT_DSH_SPEC)
FRONTEND_SHELL_CMD = 'npx --yes {spec} web --port {port} --no-open'

# npm cache for npx. The default cache is write-blocked on sandboxed machines
# (EPERM), so point npm at a project-local cache — works everywhere.
NPM_CACHE = os.path.join(_PROJECT_ROOT, ".npm-cache")

# Warm starts execute a known local CLI and should fail quickly. Only the cold
# npx fallback is allowed enough time to download the CLI and its dependency
# graph. Both waits happen on a worker thread, never Houdini's GUI thread.
FRONTEND_WARM_WAIT_TIMEOUT = 60
FRONTEND_COLD_WAIT_TIMEOUT = 600

# Local-install overrides:
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
DSH_BIN = ""
DSH_BIN_ENV = os.environ.get("DSH_HOUDINI_DSH_BIN", "")

# Agent presets live in this repo as templates (presets/<name>/); the dsh host
# reads them from ~/.dsh/.agent-presets/<name>/. launch() syncs them so prompt
# or config edits take effect from the menu — no manual Copy-Item step.
PRESET_SRC = os.path.join(_PROJECT_ROOT, "presets")
PRESET_DST = os.path.join(os.path.expanduser("~"), ".dsh", ".agent-presets")

# Required profile bundles are declared once at the package root and reconciled
# through the official `dsh plugin` command before the frontend starts.
PROFILE_REQUIREMENTS = os.path.join(_PROJECT_ROOT, "dsh-profile.requirements.json")


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


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _plugin_runtime_probe() -> tuple[bool, str]:
    """Actually import the compiled plugin using Node's real ESM resolver."""
    if not NODE or not os.path.exists(NODE):
        return False, f"node executable not found: {NODE}"
    try:
        proc = subprocess.run(
            [
                NODE, "--input-type=module", "-e",
                "await import('./lib/index.js')",
            ],
            cwd=_PROJECT_ROOT, capture_output=True, timeout=30,
            creationflags=_CREATE_NO_WINDOW,
            env=dict(os.environ, NPM_CONFIG_CACHE=NPM_CACHE),
        )
        raw = (proc.stdout or b"") + b"\n" + (proc.stderr or b"")
        output = raw.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0:
            return True, output
        return False, output or f"node import exited with code {proc.returncode}"
    except Exception:
        return False, traceback.format_exc()


def _append_dependency_failure(message: str) -> None:
    try:
        with open(FRONTEND_LOG, "ab") as log:
            diagnostic = (
                "\n[dsh-houdini] plugin dependency restore failed\n"
                + message[-12000:] + "\n"
            )
            log.write(diagnostic.encode("utf-8", errors="replace"))
    except Exception:
        pass


def _is_module_resolution_failure(output: str) -> bool:
    markers = (
        "ERR_MODULE_NOT_FOUND",
        "Cannot find package",
        "Cannot find module",
        "MODULE_NOT_FOUND",
    )
    return any(marker in output for marker in markers)


def ensure_dependencies(on_install=None) -> str:
    """Make sure the compiled plugin is resolvable, not merely present on disk."""
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
    probe_ok, probe_output = _plugin_runtime_probe()
    if not probe_ok and not missing and not _is_module_resolution_failure(probe_output):
        _append_dependency_failure(probe_output)
        return "dependency check FAILED (compiled plugin import error)"
    if missing or not probe_ok:
        if on_install is not None:
            on_install(missing or ["runtime module resolution"])
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
            _append_dependency_failure(failure_output or probe_output)
            reason = ", ".join(missing) if missing else "runtime import failed"
            return "dependency restore FAILED (" + reason + ")"
        restored.extend(missing)
        probe_ok, probe_output = _plugin_runtime_probe()
        if not probe_ok:
            _append_dependency_failure(probe_output)
            return "dependency restore FAILED (compiled plugin still cannot be imported)"
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
    _clear_frontend_runtime_state()
    if _kill_port_process(FRONTEND_PORT):
        time.sleep(0.5)  # 让端口释放，避免 TIME_WAIT 影响重启
        return f"frontend stopped (port {FRONTEND_PORT})"
    return "frontend not running"


def _dsh_version_for_bin(bin_path: str | None) -> str | None:
    """Read the CLI package version owning one dsh/lib/bin.js path."""
    if not bin_path:
        return None
    package = _read_json(os.path.join(os.path.dirname(os.path.dirname(bin_path)), "package.json"))
    version = package.get("version")
    return str(version) if version else None


def _clear_frontend_runtime_state() -> None:
    try:
        os.remove(FRONTEND_RUNTIME_STATE)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _write_frontend_runtime_state(pid: int | None) -> None:
    """Publish the verified listener identity for the diagnostics panel."""
    if pid is None:
        return
    bin_path = _PENDING.get("frontend_bin")
    version = _PENDING.get("frontend_version")
    if not version:
        cached = _newest_cached_dsh_bin()
        if cached is not None:
            bin_path = cached[0]
            version = _dsh_version_for_bin(bin_path)
    payload = {
        "pid": pid,
        "version": version,
        "source": _PENDING.get("frontend_source", "unknown"),
        "bin": bin_path,
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    temporary = FRONTEND_RUNTIME_STATE + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, FRONTEND_RUNTIME_STATE)
    except OSError:
        try:
            os.remove(temporary)
        except OSError:
            pass


def _newest_cached_dsh_bin() -> tuple[str, str] | None:
    """Return the most recently written cached CLI without contacting npm."""
    npx_root = os.path.join(NPM_CACHE, "_npx")
    candidates: list[tuple[float, str]] = []
    try:
        entries = os.scandir(npx_root)
    except OSError:
        return None
    with entries:
        for entry in entries:
            if not entry.is_dir():
                continue
            bin_path = os.path.join(
                entry.path, "node_modules", "@deepseek-ai", "dsh", "lib", "bin.js",
            )
            if os.path.isfile(bin_path):
                try:
                    modified = os.path.getmtime(bin_path)
                except OSError:
                    modified = 0.0
                candidates.append((modified, bin_path))
    if not candidates:
        return None
    return max(candidates)[1], "cached-cli"


def _resolve_cached_dsh_bin() -> tuple[str, str] | None:
    """Return the default launch candidate, respecting explicit spec pins."""
    # A custom spec means the caller explicitly asked npx to resolve/update a
    # version. Do not silently substitute an unrelated cached default version.
    if DSH_SPEC != DEFAULT_DSH_SPEC:
        return None
    return _newest_cached_dsh_bin()


def _frontend_command() -> tuple[list[str] | str, bool, str, int]:
    """Choose a deterministic warm command or the explicit cold npx path."""
    if not NODE or not os.path.exists(NODE):
        raise RuntimeError(f"node executable not found: {NODE}")

    if DSH_BIN_ENV:
        explicit = os.path.abspath(os.path.expanduser(DSH_BIN_ENV))
        if not os.path.isfile(explicit):
            raise RuntimeError(
                "DSH_HOUDINI_DSH_BIN does not point to a file: " + explicit
            )
        return (
            [NODE, explicit, "web", "--port", str(FRONTEND_PORT), "--no-open"],
            False, "explicit-cli", FRONTEND_WARM_WAIT_TIMEOUT,
        )

    if not SHELL:
        if not DSH_BIN or not os.path.isfile(DSH_BIN):
            raise RuntimeError(
                "frontend command not found:\n"
                f"  NODE={NODE}\n  DSH_BIN={DSH_BIN}\n"
                "Set SHELL=True or fix DSH_BIN in dsh_launcher.py"
            )
        return (
            [NODE, DSH_BIN, "web", "--port", str(FRONTEND_PORT), "--no-open"],
            False, "configured-cli", FRONTEND_WARM_WAIT_TIMEOUT,
        )

    cached = _resolve_cached_dsh_bin()
    if cached is not None:
        bin_path, source = cached
        return (
            [NODE, bin_path, "web", "--port", str(FRONTEND_PORT), "--no-open"],
            False, source, FRONTEND_WARM_WAIT_TIMEOUT,
        )

    if not DSH_SPEC.strip():
        raise RuntimeError("DSH_HOUDINI_DSH_SPEC is empty")
    return (
        FRONTEND_SHELL_CMD.format(port=FRONTEND_PORT, spec=DSH_SPEC),
        True, "npx-cold", FRONTEND_COLD_WAIT_TIMEOUT,
    )


def _profile_sync_command() -> tuple[list[str] | str, bool, str, int]:
    """Choose the same DSH CLI source as frontend startup, without `web`."""
    frontend, use_shell, source, timeout = _frontend_command()
    if isinstance(frontend, list):
        return frontend[:-4], use_shell, source, timeout
    suffix = f" web --port {FRONTEND_PORT} --no-open"
    if not frontend.endswith(suffix):
        raise RuntimeError(f"cannot derive DSH CLI command from: {frontend}")
    return frontend[:-len(suffix)], use_shell, source, timeout


def sync_profile_plugins(on_install=None) -> str:
    """Install/activate every required web-profile bundle, only when needed."""
    _module_path_on_syspath()
    import dsh_profile_sync

    prefix, use_shell, _source, timeout = _profile_sync_command()
    return dsh_profile_sync.sync_profile_plugins(
        prefix,
        use_shell=use_shell,
        project_root=dsh_profile_sync.PROJECT_ROOT,
        env=dict(os.environ, NPM_CONFIG_CACHE=NPM_CACHE),
        timeout=max(timeout, dsh_profile_sync.SYNC_TIMEOUT_SECONDS),
        on_install=on_install,
    )


def _command_text(cmd: list[str] | str) -> str:
    if isinstance(cmd, str):
        return cmd
    return subprocess.list2cmdline(cmd)


def _write_frontend_attempt_header(
    log, *, source: str, cwd: str, cmd: list[str] | str, timeout: int,
) -> None:
    header = (
        "\n\n===== dsh-houdini frontend attempt "
        + time.strftime("%Y-%m-%d %H:%M:%S %z")
        + " =====\n"
        + f"source: {source}\n"
        + f"cwd: {cwd}\n"
        + f"timeout: {timeout}s\n"
        + f"command: {_command_text(cmd)}\n"
        + "----- frontend output -----\n"
    )
    log.write(header.encode("utf-8", errors="replace"))
    log.flush()


def start_frontend(workspace_dir: str | None = None) -> str:
    """Boot the dsh web frontend if it is not already up; returns status text.

    workspace_dir = 前端进程 cwd = dsh 默认工作区根（应对准 $HIP 目录，
    由调用方在主线程用 _hip_dir() 解析后传入；None 回退项目根）。
    """
    if _port_open(FRONTEND_HOST, FRONTEND_PORT):
        return f"frontend already running on {FRONTEND_URL}"

    cwd = workspace_dir or _PROJECT_ROOT
    # A failed command-selection attempt must never reuse the process handle
    # from an earlier launch and misreport it as the newly created frontend.
    for key in ("proc", "frontend_source", "frontend_bin", "frontend_version", "wait_timeout"):
        _PENDING.pop(key, None)

    try:
        cmd, use_shell, source, wait_timeout = _frontend_command()
    except RuntimeError as exc:
        return str(exc)

    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stderr": subprocess.STDOUT,
        "cwd": cwd,
        "close_fds": True,
        "shell": use_shell,
        "env": dict(os.environ, NPM_CONFIG_CACHE=NPM_CACHE),
    }
    if os.name == "nt":
        # DETACHED_PROCESS would leave the cmd/npx/node tree console-less, and
        # every console-subsystem child then allocates its OWN visible terminal
        # window. CREATE_NO_WINDOW gives the whole tree a single hidden console.
        kwargs["creationflags"] = _CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP

    with open(FRONTEND_LOG, "ab") as log:
        _write_frontend_attempt_header(
            log, source=source, cwd=cwd, cmd=cmd, timeout=wait_timeout,
        )
        kwargs["stdout"] = log
        _PENDING["proc"] = subprocess.Popen(cmd, **kwargs)
    _PENDING["frontend_source"] = source
    bin_path = cmd[1] if isinstance(cmd, list) and len(cmd) > 1 else None
    _PENDING["frontend_bin"] = bin_path
    _PENDING["frontend_version"] = _dsh_version_for_bin(bin_path)
    _PENDING["wait_timeout"] = wait_timeout
    return (
        f"frontend starting on {FRONTEND_URL} "
        f"(source: {source}; workspace: {cwd}; log: {FRONTEND_LOG})"
    )


def _dsh_rpc(method: str, payload: dict, timeout: int = DSH_RPC_TIMEOUT) -> dict:
    """Call one official loopback DSH Host RPC and return its value object."""
    body = json.dumps({
        "type": "client-request",
        "rpcId": "dsh-houdini-" + uuid.uuid4().hex,
        "method": method,
        "payload": payload,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{FRONTEND_URL}/api/{method}",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        # Never send loopback control traffic through a configured HTTP proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DSH RPC {method} failed over HTTP {exc.code}: {detail[-2000:]}") from exc
    except Exception as exc:
        raise RuntimeError(f"DSH RPC {method} transport failed: {exc}") from exc

    result = decoded.get("result") if isinstance(decoded, dict) else None
    if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
        raise RuntimeError(f"DSH RPC {method} returned an invalid envelope")
    if not result["ok"]:
        error = result.get("error")
        if isinstance(error, dict):
            code = error.get("code", "unknown")
            message = error.get("message", "unknown error")
            raise RuntimeError(f"DSH RPC {method} failed: {code}: {message}")
        raise RuntimeError(f"DSH RPC {method} failed without a structured error")
    value = result.get("value")
    if not isinstance(value, dict):
        raise RuntimeError(f"DSH RPC {method} returned a non-object value")
    return value


def _canonical_workspace_path(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _select_houdini_session(
    items: object, workspace_dir: str, archived_session_ids: object = (),
) -> dict | None:
    """Pick the newest root Houdini session whose cwd exactly matches $HIP."""
    if not isinstance(items, list):
        return None
    wanted = _canonical_workspace_path(workspace_dir)
    archived = {
        value for value in archived_session_ids
        if isinstance(value, str)
    } if isinstance(archived_session_ids, (list, tuple, set)) else set()
    matches = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("agentPreset") != HOUDINI_AGENT_PRESET:
            continue
        cwd = item.get("cwd")
        session_id = item.get("sessionId")
        if not isinstance(cwd, str) or not isinstance(session_id, str):
            continue
        if session_id in archived:
            continue
        if _canonical_workspace_path(cwd) != wanted:
            continue
        matches.append(item)
    if not matches:
        return None
    return max(
        matches,
        key=lambda item: item.get("updatedAt") if isinstance(item.get("updatedAt"), (int, float)) else 0,
    )


def _workspace_id_for_path(items: object, workspace_dir: str) -> str | None:
    if not isinstance(items, list):
        return None
    wanted = _canonical_workspace_path(workspace_dir)
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        workspace_id = item.get("workspaceId")
        if isinstance(path, str) and isinstance(workspace_id, str):
            if _canonical_workspace_path(path) == wanted:
                return workspace_id
    return None


def _session_rpc_not_ready(exc: RuntimeError) -> bool:
    """True when an RPC failure means the frontend is still warming up.

    The port accepts TCP before dsh mounts its /api routes, so an early
    session.list answers 404; a mid-restart call can also hit a refused
    connection. Structured RPC errors (validation, unknown session) are real
    failures and must not be retried.
    """
    message = str(exc)
    return "over HTTP 404" in message or "transport failed" in message


def ensure_houdini_session(workspace_dir: str) -> tuple[str, str]:
    """Reuse or create the correct preset session through official Host RPC."""
    sessions = _dsh_rpc("session.list", {}).get("items")
    workspace_value = _dsh_rpc("workspace.list", {})
    existing = _select_houdini_session(
        sessions, workspace_dir, workspace_value.get("archivedSessionIds"),
    )
    if existing is not None:
        session_id = str(existing["sessionId"])
        return session_id, f"Houdini session reused: {session_id}"

    workspaces = workspace_value.get("items")
    workspace_id = _workspace_id_for_path(workspaces, workspace_dir)
    create_payload = {
        **({"workspaceId": workspace_id} if workspace_id is not None else {"cwd": workspace_dir}),
        "agentPreset": HOUDINI_AGENT_PRESET,
    }
    created = _dsh_rpc("session.create", create_payload)
    session_id = created.get("sessionId")
    agent_preset = created.get("agentPreset")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError("session.create succeeded without a sessionId")
    if agent_preset != HOUDINI_AGENT_PRESET:
        raise RuntimeError(
            "session.create did not activate the Houdini preset "
            f"(expected {HOUDINI_AGENT_PRESET!r}, got {agent_preset!r})"
        )
    attachment = f"workspace {workspace_id}" if workspace_id is not None else f"cwd {workspace_dir}"
    return session_id, f"Houdini session created: {session_id} ({attachment})"


def open_ui(session_id: str | None = None) -> str:
    """Open the embedded UI, optionally routing one Host-resolved session."""
    _module_path_on_syspath()
    try:
        import dsh_webview
        return dsh_webview.show_webview(session_id=session_id)
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
    _clear_frontend_runtime_state()
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

        _set_startup_state(state, 28, 2, "Stopping previous frontend", f"Releasing port {FRONTEND_PORT}")
        details.append(restart_frontend())

        _set_startup_state(
            state, 38, 2, "Synchronizing DSH plugins", "Checking the complete Houdini profile",
        )

        def on_plugin_install(specs: list[str]) -> None:
            _set_startup_state(
                state, 42, 2, "Installing required DSH plugins",
                "The first install may take several minutes: " + ", ".join(specs),
            )

        details.append(sync_profile_plugins(on_plugin_install))

        _set_startup_state(
            state, 52, 2, "Starting DSH", f"Creating frontend process: {DSH_SPEC}",
        )
        details.append(start_frontend(state.get("frontend_cwd")))
        state["detail"] = "\n".join(details)
        proc = _PENDING.get("proc")
        if proc is None:
            raise RuntimeError("frontend process was not created")
        wait_timeout = int(_PENDING.get("wait_timeout", FRONTEND_WARM_WAIT_TIMEOUT))
        source = str(_PENDING.get("frontend_source", "unknown"))
        state["wait_timeout"] = wait_timeout
        state["frontend_source"] = source

        started_at = time.monotonic()
        _set_startup_state(
            state, 62, 3, "Waiting for DSH service",
            f"Connecting to {FRONTEND_URL} ({source}; limit {wait_timeout}s)",
        )
        while not state["canceled"]:
            if _port_open(FRONTEND_HOST, FRONTEND_PORT):
                _write_frontend_runtime_state(_port_pid(FRONTEND_PORT) or proc.pid)
                _set_startup_state(
                    state, 82, 4, "Selecting Houdini session",
                    f"Resolving the {HOUDINI_AGENT_PRESET} preset for this $HIP workspace",
                )
                workspace_dir = state.get("frontend_cwd") or _PROJECT_ROOT
                try:
                    session_id, session_status = ensure_houdini_session(workspace_dir)
                except RuntimeError as exc:
                    # Warmup race: the port listens before /api is mounted.
                    # Keep polling within the same readiness budget; a
                    # persistent failure surfaces as the original error.
                    if not _session_rpc_not_ready(exc) or (
                        time.monotonic() - started_at >= wait_timeout
                    ):
                        raise
                    time.sleep(FRONTEND_WAIT_INTERVAL)
                    continue
                state["target_session_id"] = session_id
                state["detail"] += "\n" + session_status
                _set_startup_state(
                    state, 90, 4, "Opening Houdini workspace",
                    f"Service is ready; session {session_id}",
                )
                state["result"] = "ready"
                return
            if proc is not None and proc.poll() is not None:
                state["detail"] += f"\nfrontend exit code: {proc.returncode}"
                state["result"] = "dead"  # died without ever listening
                return
            if time.monotonic() - started_at >= wait_timeout:
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
            _report(detail + "\n" + open_ui(headless.get("target_session_id")))
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
        wait_timeout = int(state.get("wait_timeout", FRONTEND_WARM_WAIT_TIMEOUT))
        source = state.get("frontend_source", "unknown")
        warning_after = 90 if source == "npx-cold" else 30
        if elapsed >= warning_after and state.get("phase") == 3:
            if source == "npx-cold":
                message += (
                    "\nThe first CLI download is taking longer than expected. "
                    f"Check the network; this attempt stops after {wait_timeout} seconds."
                )
            else:
                message += (
                    "\nA local CLI should start quickly. This attempt will stop after "
                    f"{wait_timeout} seconds; inspect the log for a startup deadlock."
                )
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
            finish(open_ui(state.get("target_session_id")))
        elif result == "dead":
            fail(f"The frontend exited before listening on {FRONTEND_URL}")
        elif result == "timeout":
            seconds = int(state.get("wait_timeout", FRONTEND_WARM_WAIT_TIMEOUT))
            source = state.get("frontend_source", "unknown")
            fail(
                f"DSH did not become ready within {seconds} seconds "
                f"using {source}. This startup was stopped."
            )
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
