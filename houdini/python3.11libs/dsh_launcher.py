"""Launcher and runtime-refresh paths for dsh-houdini.

``open_workspace()`` is the normal menu action. It preserves a healthy DSH
frontend and current browser session, starts only missing services, and brings
the embedded UI forward.

``launch()`` is the explicit repair/development path used by the diagnostics
panel. It synchronizes presets, restarts the in-process Houdini bridge, restarts
the DSH frontend, waits until :3081 and Host RPC are ready, then opens the current
``$HIP`` workspace. The native client owns session selection and archive state.
Use it after ``npm run build``, Houdini-side Python changes, or when
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
import tempfile
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
DSH_RPC_TIMEOUT = 20

# Where the frontend process writes its stdout/stderr.
FRONTEND_LOG = os.path.join(_PROJECT_ROOT, ".dsh-web.log")
FRONTEND_RUNTIME_STATE = os.path.join(_PROJECT_ROOT, ".dsh-runtime.json")

# The frontend boots the `web` profile without a patch overlay — the `houdini`
# agent preset mounts dsh-houdini. (The old `--patch cordis.dev.yml` file://
# overlay is retired: it cannot be discovered as a package for the client half.)

# How to boot the dsh web frontend.
#   * Default: directly execute the plugin-required CLI in the project-local
#     npx cache. This avoids a warm launch blocking on npm registry resolution.
#   * With no matching cache, fall back to npx for that exact version.
#   * Set DSH_HOUDINI_DSH_SPEC to test/update a specific CLI release through
#     npx, or DSH_HOUDINI_DSH_BIN to pin an already-installed bin.js.
#   * SHELL=False + DSH_BIN remains as a source-compatible developer override.
SHELL = True
DEFAULT_DSH_SPEC = "@deepseek-ai/dsh"
DSH_SPEC = os.environ.get("DSH_HOUDINI_DSH_SPEC", DEFAULT_DSH_SPEC).strip()
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
# reads them from its configured home/.agent-presets/<name>/. launch() syncs them so prompt
# or config edits take effect from the menu — no manual Copy-Item step.
PRESET_SRC = os.path.join(_PROJECT_ROOT, "presets")

# Required profile bundles are declared once at the package root and reconciled
# through the official `dsh plugin` command before the frontend starts.
PROFILE_REQUIREMENTS = os.path.join(_PROJECT_ROOT, "dsh-profile.requirements.json")

_module_dir = os.path.dirname(os.path.abspath(__file__))
if _module_dir not in sys.path:
    sys.path.append(_module_dir)
import dsh_web_auth
import dsh_runtime_compat
import dsh_managed_runtime
importlib.reload(dsh_managed_runtime)  # implementation refresh preserves Job/lock/Popen
import dsh_profile_sync

_MANAGED = dsh_managed_runtime.context(_PROJECT_ROOT)
if _MANAGED:
    NODE = os.path.join(_MANAGED["install"], "node", "node.exe")
    FRONTEND_PORT = _MANAGED["frontendPort"]
    BRIDGE_PORT = _MANAGED["bridgePort"]
    FRONTEND_URL = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"
    FRONTEND_LOG = os.path.join(_MANAGED["runtimeDir"], "frontend.log")
    FRONTEND_RUNTIME_STATE = os.path.join(_MANAGED["runtimeDir"], "runtime.json")
    NPM_CACHE = os.path.join(_MANAGED["root"], "cache")

_DSH_WEB_SESSION = dsh_web_auth.shared_session(
    FRONTEND_URL, FRONTEND_LOG, FRONTEND_RUNTIME_STATE,
)


# hip 未保存时的中立工作区（仓库的兄弟目录，按需创建）：产出永不落仓库。
_FALLBACK_WORKSPACE = os.path.join(os.path.dirname(_PROJECT_ROOT), "dsh-houdini-workspace")
if _MANAGED:
    _FALLBACK_WORKSPACE = os.path.join(_MANAGED["root"], "workspaces", "unsaved")


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
    # An unsaved scene has no project boundary. Use a neutral scratch directory
    # outside the plugin repository; never widen tool access to source code just
    # because the preferred sibling directory cannot be created.
    for candidate in (
        _FALLBACK_WORKSPACE,
        os.path.join(tempfile.gettempdir(), "dsh-houdini-workspace"),
    ):
        try:
            os.makedirs(candidate, exist_ok=True)
            return candidate
        except Exception:
            continue
    raise RuntimeError("cannot create a neutral workspace for the unsaved Houdini scene")

# Helper processes (netstat / frontend tree) must never pop a
# visible terminal window when launched from Houdini's GUI.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

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
            env=dict(dsh_managed_runtime.environment(), NPM_CONFIG_CACHE=NPM_CACHE),
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
    if _MANAGED:
        ok, message = _plugin_runtime_probe()
        if not ok:
            _append_dependency_failure(message)
            return "managed dependency check FAILED; use Version & Diagnostics to install / repair the signed package"
        return "managed dependencies ok (no package manager)"
    probe_ok, probe_output = _plugin_runtime_probe()
    if probe_ok:
        return "dependencies ok"
    if not _is_module_resolution_failure(probe_output):
        _append_dependency_failure(probe_output)
        return "dependency check FAILED (compiled plugin import error)"
    if on_install is not None:
        on_install(["runtime module resolution"])
    try:
        proc = subprocess.run(
            "npm install --no-audit --no-fund --loglevel=error",
            cwd=_PROJECT_ROOT, capture_output=True, timeout=600, shell=True,
            creationflags=_CREATE_NO_WINDOW,
            env=dict(os.environ, NPM_CONFIG_CACHE=NPM_CACHE),
        )
        if proc.returncode != 0:
            raw = (proc.stdout or b"") + b"\n" + (proc.stderr or b"")
            _append_dependency_failure(raw.decode("utf-8", errors="replace"))
            return "dependency restore FAILED (runtime import failed)"
    except Exception:
        _append_dependency_failure(traceback.format_exc())
        return "dependency restore FAILED (runtime import failed)"
    probe_ok, probe_output = _plugin_runtime_probe()
    if not probe_ok:
        _append_dependency_failure(probe_output)
        return "dependency restore FAILED (compiled plugin still cannot be imported)"
    return "dependencies restored"


def sync_presets() -> str:
    """Copy repo presets into the same DSH home used by profile synchronization."""
    if _MANAGED:
        return "managed presets prepared in the isolated DSH home"
    if not os.path.isdir(PRESET_SRC):
        return "no presets/ directory in repo"
    preset_dst = dsh_profile_sync.dsh_home() / ".agent-presets"
    synced = []
    for name in sorted(os.listdir(PRESET_SRC)):
        src = os.path.join(PRESET_SRC, name)
        if os.path.isdir(src):
            shutil.copytree(src, preset_dst / name, dirs_exist_ok=True)
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


def _frontend_online() -> bool:
    """Check readiness without borrowing another Houdini/process's listener."""
    if not _port_open(FRONTEND_HOST, FRONTEND_PORT):
        return False
    pid = _port_pid(FRONTEND_PORT)
    if not dsh_managed_runtime.owns_pid(pid):
        raise RuntimeError(
            f"frontend port conflict on {FRONTEND_URL}: listener PID {pid or 'unknown'} "
            "is not owned by this Houdini. No external process was stopped; "
            "close it from its owning application or choose an isolated installation."
        )
    return True


def _module_path_on_syspath() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.append(here)


def restart_bridge(*, port=None) -> str:
    """Main thread: stop/reload/start the in-process bridge without probing ports."""
    _module_path_on_syspath()
    target_port = BRIDGE_PORT if port is None else port
    if type(target_port) is not int or not 1024 <= target_port <= 65535:
        raise ValueError('Invalid Bridge restart port')
    import dsh_bridge
    import dsh_requests
    import dsh_hou_helpers
    import dsh_hda_interfaces
    import dsh_hda_ui
    import dsh_parameter_ui
    import dsh_control_bindings
    import dsh_cook_control
    import dsh_cop_contracts
    import dsh_quality_contracts
    import dsh_sop_contracts
    import dsh_camera_framing
    import dsh_geometry_observation
    import dsh_operation_cards

    # Recheck on the owning thread: the worker's HTTP snapshot may already be old.
    # This uses only in-process counters; no socket/process probe on the GUI thread.
    registry = getattr(dsh_bridge, '_request_registry', None)
    activity = getattr(dsh_bridge, '_job_activity', None)
    if registry is None or not callable(activity):
        raise RuntimeError('Bridge cannot verify restart safety; fully reopen Houdini after saving your work')
    jobs = activity().get('activeJobs')
    requests = registry.active_count()
    if (type(jobs) is not int or type(requests) is not int or jobs != 0 or requests != 0
            or not dsh_bridge._work_queue.empty()):
        raise RuntimeError('Bridge restart deferred: scene work arrived after preflight; no modules were reloaded')
    dsh_bridge.stop()                      # 停进程内旧 server（线程）
    importlib.reload(dsh_hou_helpers)      # 拾取最新 helper
    importlib.reload(dsh_hda_interfaces)
    importlib.reload(dsh_parameter_ui)
    importlib.reload(dsh_control_bindings)
    importlib.reload(dsh_cook_control)
    importlib.reload(dsh_cop_contracts)
    importlib.reload(dsh_hda_ui)
    importlib.reload(dsh_camera_framing)
    importlib.reload(dsh_geometry_observation)
    importlib.reload(dsh_operation_cards)
    importlib.reload(dsh_sop_contracts)
    importlib.reload(dsh_quality_contracts)
    importlib.reload(dsh_requests)
    importlib.reload(dsh_bridge)           # 拾取最新 bridge
    dsh_bridge.start(target_port, BRIDGE_HOST)
    return f"bridge restarted on {BRIDGE_HOST}:{target_port}"


def restart_frontend() -> str:
    """Restart only our frontend tree; an unrelated listener is a conflict."""
    _frontend_online()  # Check conflicts before stopping even our own Job.
    if _terminate_pending_frontend():
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
    if (not version and _PENDING.get("frontend_source") == "npx-cold"
            and DSH_SPEC == DEFAULT_DSH_SPEC and not DSH_BIN_ENV):
        # Only the default exact cold command can be identified by its required
        # cache. A developer override must never borrow the default's identity.
        cached = _preferred_cached_dsh_bin()
        if cached is not None:
            bin_path = cached[0]
            version = _dsh_version_for_bin(bin_path)
    payload = {
        "pid": pid,
        "version": version,
        "source": _PENDING.get("frontend_source", "unknown"),
        "bin": bin_path,
        "authLogOffset": _PENDING.get("auth_log_offset", 0),
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


def _preferred_cached_dsh_bin() -> tuple[str, str] | None:
    """Return only the plugin-required cached CLI; cache recency has no authority."""
    cached = dsh_runtime_compat.preferred_cached_bin(NPM_CACHE)
    return (str(cached), "cached-cli") if cached is not None else None


def _resolve_cached_dsh_bin() -> tuple[str, str] | None:
    """Return the default launch candidate, respecting explicit spec pins."""
    # A custom spec means the caller explicitly asked npx to resolve/update a
    # version. Do not silently substitute an unrelated cached default version.
    if DSH_SPEC != DEFAULT_DSH_SPEC:
        return None
    return _preferred_cached_dsh_bin()


def _frontend_command() -> tuple[list[str] | str, bool, str, int]:
    """Choose a deterministic warm command or the explicit cold npx path."""
    if not NODE or not os.path.exists(NODE):
        raise RuntimeError(f"node executable not found: {NODE}")

    if _MANAGED:
        binary = os.path.join(_MANAGED["install"], "app", "node_modules", "@deepseek-ai", "dsh", "lib", "bin.js")
        if not os.path.isfile(binary):
            raise RuntimeError("Managed DSH is missing. Install / repair the signed package.")
        return [NODE, binary, "web", "--port", str(FRONTEND_PORT), "--no-open"], False, "managed-cli", FRONTEND_WARM_WAIT_TIMEOUT

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
    cold_spec = DSH_SPEC
    if DSH_SPEC == DEFAULT_DSH_SPEC:
        cold_spec = dsh_runtime_compat.preferred_spec()
    return (
        FRONTEND_SHELL_CMD.format(port=FRONTEND_PORT, spec=cold_spec),
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
    if _MANAGED:
        return "managed profile initialized through the bundled DSH API (no package manager)"
    _module_path_on_syspath()
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


def start_frontend(workspace_dir: str | None = None, *, attempt: dict | None = None) -> str:
    """Boot the dsh web frontend if it is not already up; returns status text.

    workspace_dir = 前端进程 cwd = dsh 默认工作区根（应对准 $HIP 目录，
    由调用方在主线程用 _hip_dir() 解析后传入；None 回退项目根）。
    """
    if _frontend_online():
        return f"frontend already running on {FRONTEND_URL}"

    cwd = workspace_dir or (_FALLBACK_WORKSPACE if _MANAGED else _PROJECT_ROOT)
    if _MANAGED:
        os.makedirs(cwd, exist_ok=True)
    # A failed command-selection attempt must never reuse the process handle
    # from an earlier launch and misreport it as the newly created frontend.
    for key in (
        "proc", "frontend_source", "frontend_bin", "frontend_version",
        "wait_timeout", "auth_log_offset",
    ):
        _PENDING.pop(key, None)

    try:
        cmd, use_shell, source, wait_timeout = _frontend_command()
    except RuntimeError as exc:
        return str(exc)

    kwargs: dict = {
        "stderr": subprocess.STDOUT,
        "cwd": cwd,
        "close_fds": True,
        "env": dict(dsh_managed_runtime.environment(), NPM_CONFIG_CACHE=NPM_CACHE,
                    DSH_HOUDINI_EXECUTOR_ID=dsh_managed_runtime.executor_identity()),
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
        auth_log_offset = log.tell()
        _PENDING["auth_log_offset"] = auth_log_offset
        _DSH_WEB_SESSION.reset(log_offset=auth_log_offset)
        kwargs["stdout"] = log
        if os.name == "nt":
            process = dsh_managed_runtime.spawn_frontend(
                cmd, node=NODE, shell=use_shell, **kwargs,
            )
        else:
            process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, shell=use_shell, **kwargs)
        if attempt is not None:
            attempt["proc"] = process
        _PENDING["proc"] = process
    _PENDING["frontend_source"] = source
    bin_path = cmd[1] if isinstance(cmd, list) and len(cmd) > 1 else None
    _PENDING["frontend_bin"] = bin_path
    _PENDING["frontend_version"] = _dsh_version_for_bin(bin_path)
    _PENDING["wait_timeout"] = wait_timeout
    return (
        f"frontend starting on {FRONTEND_URL} "
        f"(source: {source}; workspace: {cwd}; log: {FRONTEND_LOG})"
    )


def _dsh_rpc_wire(method: str, payload: dict, timeout: int = DSH_RPC_TIMEOUT) -> dict:
    """Call one exact DSH Host RPC wire endpoint and return its value object."""
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
        try:
            response = _DSH_WEB_SESSION.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise
            # DSH 0.1.2+: every Host RPC uses the browser-session cookie.
            # The first 401 triggers the documented root-token exchange;
            # older DSH releases continue to succeed on the first request.
            exc.close()
            _DSH_WEB_SESSION.authorize(timeout)
            response = _DSH_WEB_SESSION.open(request, timeout=timeout)
        with response:
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


def _host_rpc_not_ready(exc: RuntimeError) -> bool:
    """True when an RPC failure means the frontend is still warming up.

    The port accepts TCP before dsh mounts its /api routes, so an early
    session/list answers 404; a mid-restart call can also hit a refused
    connection. Structured RPC errors (validation, unknown session) are real
    failures and must not be retried.
    """
    message = str(exc)
    return "over HTTP 404" in message or "transport failed" in message


def _check_host_ready() -> None:
    """Read-only startup probe; the browser owns workspace/session navigation."""
    sessions = _dsh_rpc_wire(
        "session/list", {"args": {"_request": {}}},
    ).get("items")
    if not isinstance(sessions, list):
        raise RuntimeError("session/list returned invalid items")


def open_ui(workspace_dir: str, *, force_reload: bool = False) -> str:
    """Raise the current HIP page or issue one workspace navigation to the client."""
    _module_path_on_syspath()
    try:
        import dsh_webview
        if not force_reload and dsh_webview.raise_workspace(workspace_dir):
            return "Houdini workspace already open"
        return dsh_webview.show_webview(
            workspace_dir=workspace_dir,
            authenticated_url=_DSH_WEB_SESSION.launch_url(),
            force_reload=force_reload,
        )
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
_MAIN_DISPATCHES: list = []
_SERVICE_PREFLIGHT_ACTIVE = False


def _require_bridge_idle():
    """Worker-only guard: forcing DSH shutdown never authorizes live HOM reload."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://{BRIDGE_HOST}:{BRIDGE_PORT}/health', timeout=5) as response:
        health = json.loads(response.read().decode('utf-8'))
    if (not isinstance(health, dict) or health.get('ok') is not True or
            any(type(health.get(key)) is not int or health[key] != 0 for key in ('activeJobs', 'activeRequests'))):
        raise RuntimeError('Force repair deferred: Houdini execution is active or unknown; stop/wait for scene work before retrying. Houdini was not terminated.')


def _force_frontend_repair():
    if not _port_open(FRONTEND_HOST, FRONTEND_PORT):
        return
    pid = _port_pid(FRONTEND_PORT)
    if dsh_managed_runtime.owns_pid(pid):
        _terminate_pending_frontend()
        _report(f'Force repair stopped owned DSH frontend tree (listener PID {pid})')
    else:
        roots = [os.path.join(_PROJECT_ROOT, '.npm-cache', '_npx')]
        if _MANAGED:
            roots = [os.path.join(_MANAGED['install'], 'app', 'node_modules')]
        identity = dsh_managed_runtime.stop_verified_frontend(
            pid, cli_roots=roots, port=FRONTEND_PORT, listener_pid=lambda: _port_pid(FRONTEND_PORT))
        _clear_frontend_runtime_state()
        _report(f"Force repair stopped verified legacy DSH listener PID {identity['pid']}; session files were not deleted")
    deadline = time.monotonic() + 5
    while _port_open(FRONTEND_HOST, FRONTEND_PORT):
        if time.monotonic() >= deadline:
            raise RuntimeError('Frontend port is still occupied after force repair; no new runtime started')
        time.sleep(.1)


def _service_preflight(*, force_frontend=False) -> dict:
    """Worker only: reject unrelated listeners before any service is changed."""
    bridge_online = _port_open(BRIDGE_HOST, BRIDGE_PORT)
    bridge_pid = _port_pid(BRIDGE_PORT) if bridge_online else None
    if bridge_online and bridge_pid != os.getpid():
        raise RuntimeError(
            f"bridge port conflict on {BRIDGE_HOST}:{BRIDGE_PORT}: listener PID {bridge_pid or 'unknown'} "
            "is not this Houdini process. No external process was stopped; "
            "close it from its owning application or choose an isolated installation."
        )
    if force_frontend:
        if bridge_online:
            _require_bridge_idle()
        _force_frontend_repair()
        # A request may have been admitted between the first check and shutdown.
        if bridge_online:
            _require_bridge_idle()
    frontend_online = _frontend_online()
    return {
        "frontend_online": frontend_online,
        "bridge_online": bridge_online,
    }


def _dispatch_service_preflight(callback, *, force_frontend=False) -> None:
    """Run blocking listener/process checks off-GUI, then invoke callback on main."""
    global _SERVICE_PREFLIGHT_ACTIVE
    if _SERVICE_PREFLIGHT_ACTIVE:
        _report("a service preflight is already running")
        return
    _SERVICE_PREFLIGHT_ACTIVE = True
    preflight = (lambda: _service_preflight(force_frontend=True)) if force_frontend else _service_preflight
    try:
        ui_available = bool(hou.isUIAvailable())
    except Exception:
        ui_available = False
    if not ui_available:
        try:
            callback(preflight(), None)
        except Exception as exc:
            _report(f"service startup failed: {exc}")
        finally:
            _SERVICE_PREFLIGHT_ACTIVE = False
        return
    try:
        from hutil.Qt import QtCore
        parent = hou.qt.mainWindow()
    except Exception as exc:
        _SERVICE_PREFLIGHT_ACTIVE = False
        _report(f"cannot schedule non-blocking service preflight: {exc}")
        return

    state: dict = {"done": False, "result": None, "error": None}
    timer = QtCore.QTimer(parent)

    def worker() -> None:
        try:
            state["result"] = preflight()
        except Exception:
            state["error"] = traceback.format_exc()
        finally:
            state["done"] = True

    def tick() -> None:
        global _SERVICE_PREFLIGHT_ACTIVE
        if not state["done"]:
            return
        timer.stop()
        if timer in _MAIN_DISPATCHES:
            _MAIN_DISPATCHES.remove(timer)
        _SERVICE_PREFLIGHT_ACTIVE = False
        try:
            callback(state["result"], state["error"])
        except Exception as exc:
            _report(f"service startup failed: {exc}")

    timer.timeout.connect(tick)
    _MAIN_DISPATCHES.append(timer)
    threading.Thread(target=worker, daemon=True).start()
    timer.start(50)


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


def _terminate_pending_frontend(**ownership) -> bool:
    """Stop the owned Job (including npx descendants), never a port-selected PID."""
    if os.name == "nt":
        stopped = dsh_managed_runtime.stop_owned(**ownership)
    else:
        proc = _PENDING.get("proc")
        stopped = proc is not None and ownership.get("expected_process", proc) is proc and proc.poll() is None
        if stopped:
            proc.terminate()
            proc.wait(timeout=10)
    if stopped:
        _clear_frontend_runtime_state()
    return stopped


def _cancel_startup(state: dict) -> None:
    """A delayed UI callback can stop its own attempt, never a newer frontend."""
    state["canceled"] = True
    process = state.get("proc")
    if process is not None:
        threading.Thread(
            target=_terminate_pending_frontend, kwargs={"expected_process": process}, daemon=True,
        ).start()


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
        if state["canceled"]:
            return

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
        if state["canceled"]:
            return

        _set_startup_state(
            state, 52, 2, "Starting DSH", f"Creating frontend process: {DSH_SPEC}",
        )
        details.append(start_frontend(state.get("frontend_cwd"), attempt=state))
        if state["canceled"]:
            _terminate_pending_frontend(expected_process=state.get("proc"))
            return
        state["detail"] = "\n".join(details)
        proc = state.get("proc")
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
            if _frontend_online():
                _write_frontend_runtime_state(_port_pid(FRONTEND_PORT) or proc.pid)
                _set_startup_state(
                    state, 82, 4, "Checking DSH service", "Waiting for the native session API",
                )
                try:
                    _check_host_ready()
                except RuntimeError as exc:
                    # Warmup race: the port listens before /api is mounted.
                    # Keep polling within the same readiness budget; a
                    # persistent failure surfaces as the original error.
                    if not _host_rpc_not_ready(exc) or (
                        time.monotonic() - started_at >= wait_timeout
                    ):
                        raise
                    time.sleep(FRONTEND_WAIT_INTERVAL)
                    continue
                _set_startup_state(
                    state, 90, 4, "Opening Houdini workspace",
                    "The native client will restore this workspace's Houdini task",
                )
                state["result"] = "ready"
                return
            if proc is not None and proc.poll() is not None:
                state["detail"] += f"\nfrontend exit code: {proc.returncode}"
                state["result"] = "dead"  # died without ever listening
                return
            if time.monotonic() - started_at >= wait_timeout:
                state["result"] = "timeout"
                _terminate_pending_frontend(expected_process=proc)
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
        # hython: run the same worker inline; the UI reports its own availability.
        headless: dict = {"canceled": False, "result": None, "detail": "", "frontend_cwd": frontend_cwd}
        _start_and_wait_frontend(headless)
        detail += "\n" + headless["detail"]
        if headless["result"] == "ready":
            _report(detail + "\n" + open_ui(frontend_cwd, force_reload=True))
        else:
            _report(
                detail
                + "\n" + (headless["error"].splitlines()[-1] if headless.get("error")
                           else f"frontend exited without listening on {FRONTEND_URL}") + "; "
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
        _cancel_startup(state)

    def cleanup_dialog(_code: int) -> None:
        # Closing the window while startup is still running means cancel.
        # A successful close must leave the now-serving frontend alive.
        if state.get("result") != "ready":
            _cancel_startup(state)
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
            finish(open_ui(frontend_cwd, force_reload=True))
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


def launch(*, force_frontend=False) -> None:
    """Restart the bridge, then restart the frontend and open the UI when ready.

    The frontend restart/poll happens on a worker thread inside
    open_ui_when_ready (blocking probes must not touch the GUI thread);
    only the bridge restart — which touches `hou` — runs here. The frontend
    cwd is resolved here too (main thread): it seeds the dsh default
    workspace, which must track the current hip directory.
    """
    from dsh_executor_registry import is_shared_executor
    if is_shared_executor():
        _report('This is a shared executor. Use Repair This Shared Executor; restarting the shared DSH Host is a separate operation affecting all tasks.')
        return
    frontend_cwd = _hip_dir()

    def after_preflight(preflight: dict | None, error: str | None) -> None:
        if error:
            _report("service preflight failed: " + error.splitlines()[-1])
            return
        detail = "\n".join([
            sync_presets(),
            restart_bridge(),
        ])
        print("[dsh-houdini] " + detail.replace("\n", "; "))
        open_ui_when_ready(detail, frontend_cwd)

    if force_frontend:
        _dispatch_service_preflight(after_preflight, force_frontend=True)
    else:
        _dispatch_service_preflight(after_preflight)


def open_workspace() -> None:
    """Open the embedded workspace without restarting a healthy frontend.

    If the web service is absent, fall back to the full launch path. Keeping
    "open" separate from "restart" avoids destroying a live dsh session just
    because the user wants to bring its Houdini window to the front.
    """
    frontend_cwd = _hip_dir()

    def after_preflight(preflight: dict | None, error: str | None) -> None:
        if error:
            _report("service preflight failed: " + error.splitlines()[-1])
            return
        facts = preflight or {}
        if not facts.get("frontend_online"):
            bridge_status = (
                f"bridge already running on {BRIDGE_HOST}:{BRIDGE_PORT}"
                if facts.get("bridge_online") else restart_bridge()
            )
            detail = "\n".join([sync_presets(), bridge_status])
            print("[dsh-houdini] " + detail.replace("\n", "; "))
            open_ui_when_ready(detail, frontend_cwd)
            return

        details = []
        if facts.get("bridge_online"):
            details.append(f"bridge already running on {BRIDGE_HOST}:{BRIDGE_PORT}")
        else:
            details.append(restart_bridge())
        details.append(open_ui(frontend_cwd))
        _report("\n".join(details))

    _dispatch_service_preflight(after_preflight)


if __name__ == "__main__":
    launch()
