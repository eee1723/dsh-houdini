"""Focused version status and safe update UI for DSH-Houdini."""

from __future__ import annotations

import collections
import importlib
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import hou


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NPM_CACHE = os.path.join(_PROJECT_ROOT, ".npm-cache")
_FRONTEND_LOG = os.path.join(_PROJECT_ROOT, ".dsh-web.log")
_RUNTIME_STATE = os.path.join(_PROJECT_ROOT, ".dsh-runtime.json")
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PACKAGE_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+-]*$")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_NPM_TARBALL_PENDING_RE = re.compile(
    r"no local data for .*?@(https?://\S+?\.tgz)\. Extracting by manifest"
)
_NPM_TARBALL_FETCH_RE = re.compile(r"http fetch GET 200 (https?://\S+?\.tgz)(?:\s|$)")
_DEFAULT_DSH_SPEC = "@deepseek-ai/dsh"
_FRONTEND_PORT = 3081
_BRIDGE_PORT = 8765

_module_dir = os.path.dirname(os.path.abspath(__file__))
if _module_dir not in sys.path:
    sys.path.append(_module_dir)
import dsh_web_auth
import dsh_runtime_compat
import dsh_managed_runtime

_MANAGED = dsh_managed_runtime.context(_PROJECT_ROOT)
if _MANAGED:
    _FRONTEND_PORT = _MANAGED["frontendPort"]
    _BRIDGE_PORT = _MANAGED["bridgePort"]
    _FRONTEND_LOG = os.path.join(_MANAGED["runtimeDir"], "frontend.log")
    _RUNTIME_STATE = os.path.join(_MANAGED["runtimeDir"], "runtime.json")

_DSH_WEB_SESSION = dsh_web_auth.shared_session(
    f"http://127.0.0.1:{_FRONTEND_PORT}", _FRONTEND_LOG, _RUNTIME_STATE,
)

_WINDOW = None
_TIMER = None


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _port_open(port: int) -> bool:
    """Worker-thread-only localhost probe."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.25)
        sock.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _port_pid(port: int) -> int | None:
    if os.name != "nt":
        return None
    try:
        proc = subprocess.run(
            ["netstat", "-ano"], capture_output=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception:
        return None
    text = (proc.stdout or b"").decode("utf-8", errors="replace")
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP":
            if parts[1].endswith(f":{port}") and "LISTENING" in parts:
                try:
                    return int(parts[-1])
                except ValueError:
                    pass
    return None


def _selected_cached_dsh_version() -> str | None:
    cached = dsh_runtime_compat.preferred_cached_bin(_NPM_CACHE)
    return dsh_runtime_compat.preferred_version() if cached is not None else None


def _require_cached_dsh(version: str) -> None:
    """Validate readiness; cache timestamps no longer promote a release."""
    dsh_runtime_compat.require_verified(version)
    if version != dsh_runtime_compat.preferred_version():
        raise RuntimeError("DSH repair must use the plugin-required version")
    if dsh_runtime_compat.preferred_cached_bin(_NPM_CACHE) is None:
        raise RuntimeError(f"DSH {version} finished but was not found in {_NPM_CACHE}")


def _dsh_launch_override() -> str | None:
    if _MANAGED:
        return "managed signed release (repair from the installation manager)"
    explicit_bin = os.environ.get("DSH_HOUDINI_DSH_BIN", "").strip()
    if explicit_bin:
        return "DSH_HOUDINI_DSH_BIN"
    spec = os.environ.get("DSH_HOUDINI_DSH_SPEC", _DEFAULT_DSH_SPEC).strip()
    if spec != _DEFAULT_DSH_SPEC:
        return f"DSH_HOUDINI_DSH_SPEC={spec or '(empty)'}"
    return None


def _runtime_dsh_info() -> dict:
    if not _port_open(_FRONTEND_PORT):
        return {"online": False, "verified": False, "version": None, "note": "DSH Web is offline"}
    listener_pid = _port_pid(_FRONTEND_PORT)
    marker = _read_json(_RUNTIME_STATE)
    marker_pid = marker.get("pid")
    version = marker.get("version")
    verified = bool(
        listener_pid is not None and isinstance(marker_pid, int)
        and marker_pid == listener_pid and isinstance(version, str) and version
        and dsh_managed_runtime.owns_pid(listener_pid)
    )
    if verified:
        note = f"PID {listener_pid} · {marker.get('source', 'unknown')}"
    else:
        note = "Listener ownership or recorded runtime identity is unverified; no running version can be confirmed"
        version = None
    return {"online": True, "verified": verified, "version": version, "note": note}


def _http_json(url: str, data: dict | None = None, timeout: int = 5) -> dict:
    encoded = json.dumps(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(
        url, data=encoded,
        headers={"content-type": "application/json"} if encoded is not None else {},
        method="POST" if encoded is not None else "GET",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[-1000:]}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("service returned a non-object response")
    return value


def _dsh_rpc_wire(method: str, payload: dict) -> dict:
    body = json.dumps({
        "type": "client-request",
        "rpcId": "dsh-houdini-manager-" + uuid.uuid4().hex,
        "method": method,
        "payload": payload,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{_FRONTEND_PORT}/api/{method}",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        try:
            response = _DSH_WEB_SESSION.open(request, timeout=5)
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise
            exc.close()
            _DSH_WEB_SESSION.authorize(5)
            response = _DSH_WEB_SESSION.open(request, timeout=5)
        with response:
            decoded = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DSH RPC {method} failed over HTTP {exc.code}: {detail[-1000:]}") from exc
    result = decoded.get("result")
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError(f"DSH RPC {method} did not return a successful envelope")
    value = result.get("value")
    if not isinstance(value, dict):
        raise RuntimeError(f"DSH RPC {method} returned a non-object value")
    return value


def _runtime_activity() -> dict:
    """Fail closed when a running service cannot prove it is idle."""
    reasons = []
    active_sessions = 0
    active_jobs = 0
    active_requests = 0
    frontend_online = _port_open(_FRONTEND_PORT)
    bridge_online = _port_open(_BRIDGE_PORT)
    if frontend_online:
        try:
            value = _dsh_rpc_wire("session/list", {"args": {"_request": {}}})
            items = value.get("items", [])
            if not isinstance(items, list):
                raise RuntimeError("session/list items is not a list")
            active_sessions = sum(
                1 for item in items if isinstance(item, dict) and item.get("running") is True
            )
        except Exception as exc:
            reasons.append(f"DSH activity unknown: {exc}")
    if bridge_online:
        active_jobs = active_requests = None
        try:
            health = _http_json(f"http://127.0.0.1:{_BRIDGE_PORT}/health")
            if health.get('ok') is not True or any(type(health.get(key)) is not int or health[key] < 0
                                                  for key in ('activeJobs', 'activeRequests')):
                raise RuntimeError('Bridge cannot confirm all in-flight requests; let existing work settle and fully restart Houdini to load the current Bridge')
            active_jobs = health['activeJobs']
            active_requests = health['activeRequests']
        except Exception as exc:
            reasons.append(f"Houdini execution activity unknown: {exc}")
    if active_sessions:
        reasons.append(f"{active_sessions} DSH session(s) are running")
    if active_jobs:
        reasons.append(f"{active_jobs} Houdini job(s) are active")
    if active_requests:
        reasons.append(f"{active_requests} Houdini request(s)/job links are still active")
    return {
        "safe": not reasons, "activeSessions": active_sessions, "activeJobs": active_jobs,
        "activeRequests": active_requests,
        "note": "; ".join(reasons) if reasons else "Runtime is idle",
    }


def _directory_size(path: str) -> int:
    """Best-effort recursive byte count for the project-local npm content cache."""
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _format_bytes(value: float) -> str:
    value = max(0.0, float(value))
    units = ("B", "KiB", "MiB", "GiB")
    for unit in units[:-1]:
        if value < 1024.0:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} {units[-1]}"


def _format_elapsed(seconds: float) -> str:
    whole = max(0, int(seconds))
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _download_progress_message(progress: dict) -> str:
    stage = str(progress.get("stage") or "Preparing download")
    done = int(progress.get("packages_done") or 0)
    total = int(progress.get("packages_total") or 0)
    package_count = f"{done}/{total} packages" if total else f"{done}/? packages"
    received = _format_bytes(float(progress.get("bytes_downloaded") or 0))
    speed = _format_bytes(float(progress.get("speed_bps") or 0)) + "/s"
    elapsed = _format_elapsed(float(progress.get("elapsed") or 0))
    parts = [stage, package_count, f"{received} received", speed, elapsed]
    current = str(progress.get("current") or "").strip()
    if current:
        parts.append(current)
    return "  ·  ".join(parts)


class _NpmDownloadTracker:
    """Extract deterministic package counts and stages from streamed npm output."""

    def __init__(self) -> None:
        self.pending: set[str] = set()
        self.downloaded: set[str] = set()
        self.stage = "Starting npm"
        self.current = ""

    @staticmethod
    def _package_label(url: str) -> str:
        filename = urllib.parse.unquote(url.rsplit("/", 1)[-1])
        return filename[:-4] if filename.endswith(".tgz") else filename

    def feed(self, raw_line: str) -> None:
        line = _ANSI_ESCAPE_RE.sub("", raw_line).strip()
        if not line:
            return
        if "idealTree buildDeps" in line or "fetch manifest" in line:
            self.stage = "Resolving dependency graph"
        pending = _NPM_TARBALL_PENDING_RE.search(line)
        if pending:
            url = pending.group(1)
            self.pending.add(url)
            self.stage = "Preparing package downloads"
            self.current = self._package_label(url)
        fetched = _NPM_TARBALL_FETCH_RE.search(line)
        if fetched:
            url = fetched.group(1)
            self.pending.add(url)
            self.downloaded.add(url)
            self.stage = "Downloading packages"
            self.current = self._package_label(url)
        if " info run " in f" {line} " or line.startswith("npm info run "):
            self.stage = "Installing package scripts"
            self.current = line.split(" run ", 1)[-1][:160]
        if line.startswith("npm info ok") or line == "info ok":
            self.stage = "Verifying DSH CLI"
            self.current = ""

    def snapshot(self) -> dict:
        return {
            "stage": self.stage,
            "packages_done": len(self.downloaded),
            "packages_total": len(self.pending),
            "current": self.current,
        }


def _run_npx_dsh(version: str, on_progress=None) -> str:
    if not _PACKAGE_VERSION_RE.fullmatch(version):
        raise RuntimeError(f"refusing invalid DSH version: {version!r}")
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx was not found; check the Node.js installation")
    args = [npx, "--yes", "--loglevel=silly", f"@deepseek-ai/dsh@{version}", "--version"]
    env = dict(
        os.environ,
        NPM_CONFIG_CACHE=_NPM_CACHE,
        NPM_CONFIG_PROGRESS="false",
        FORCE_COLOR="0",
    )
    command: list[str] | str = args
    use_shell = False
    if os.name == "nt":
        # .CMD launchers require cmd.exe. There is deliberately no total
        # timeout: large first-time DSH installs can legitimately take tens of
        # minutes. The UI remains live because output and cache growth stream
        # through the progress callback below.
        command = subprocess.list2cmdline(args)
        use_shell = True
    content_cache = os.path.join(_NPM_CACHE, "_cacache", "content-v2")
    baseline_bytes = _directory_size(content_cache)
    proc = subprocess.Popen(
        command,
        cwd=_PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=_CREATE_NO_WINDOW if os.name == "nt" else 0,
        env=env,
        shell=use_shell,
    )
    output_queue: queue.Queue[str | None] = queue.Queue()
    output_tail: collections.deque[str] = collections.deque(maxlen=400)
    tracker = _NpmDownloadTracker()

    def read_output() -> None:
        try:
            if proc.stdout is not None:
                for line in proc.stdout:
                    output_queue.put(line)
        finally:
            output_queue.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    started_at = time.monotonic()
    samples: collections.deque[tuple[float, int]] = collections.deque()
    reader_finished = False
    last_emit = 0.0

    while True:
        lines: list[str | None] = []
        try:
            lines.append(output_queue.get(timeout=0.2))
        except queue.Empty:
            pass
        while True:
            try:
                lines.append(output_queue.get_nowait())
            except queue.Empty:
                break
        for line in lines:
            if line is None:
                reader_finished = True
                continue
            clean = _ANSI_ESCAPE_RE.sub("", line).rstrip()
            if clean:
                output_tail.append(clean)
            tracker.feed(clean)

        now = time.monotonic()
        if on_progress is not None and (
            now - last_emit >= 0.5 or (proc.poll() is not None and reader_finished)
        ):
            current_bytes = max(0, _directory_size(content_cache) - baseline_bytes)
            samples.append((now, current_bytes))
            while len(samples) > 1 and now - samples[0][0] > 5.0:
                samples.popleft()
            speed_bps = 0.0
            if len(samples) > 1:
                duration = samples[-1][0] - samples[0][0]
                if duration > 0:
                    speed_bps = max(0.0, (samples[-1][1] - samples[0][1]) / duration)
            progress = tracker.snapshot()
            progress.update(
                bytes_downloaded=current_bytes,
                speed_bps=speed_bps,
                elapsed=now - started_at,
            )
            try:
                on_progress(progress)
            except Exception:
                pass
            last_emit = now

        if proc.poll() is not None and reader_finished and output_queue.empty():
            break

    if proc.returncode != 0:
        message = "\n".join(output_tail).strip() or f"exit {proc.returncode}"
        raise RuntimeError(message[-12000:])
    reported = next((line.strip() for line in reversed(output_tail) if line.strip() == version), "")
    if not reported:
        raise RuntimeError(f"DSH {version} installed but its CLI did not report the expected version")
    return reported


def _summary_for_state(state: dict) -> str:
    status = state.get("dsh_status")
    if status == "blocked" and state.get("dsh_action") == "Await compatibility":
        return "配套版本尚未通过兼容检查，暂不能启用。"
    return {
        "current": "运行环境与配套版本一致。",
        "blocked": "运行版本由安装包或启动配置管理。",
        "staged": "配套版本已就绪，可在空闲时启用。",
        "update": "当前运行版本与插件配套版本不同。",
        "offline": "运行环境尚未启动。",
        "unknown": "服务已启动，运行版本尚未核验。",
        "error": "无法核验运行环境，请查看技术详情。",
    }.get(status, "正在检查运行环境…")


def _check_updates(state: dict) -> None:
    updates = {
        "busy": False, "result": "render", "checked": True,
        "dsh_can_update": False,
        "frontend_online": False, "bridge_online": False,
    }
    try:
        runtime = _runtime_dsh_info()
        updates["frontend_online"] = runtime["online"]
        updates["dsh_current"] = runtime["version"] or ("Not running" if not runtime["online"] else "Unknown")
        updates["dsh_note"] = runtime["note"]
        latest = dsh_runtime_compat.preferred_version()
        selected = _selected_cached_dsh_version()
        override = _dsh_launch_override()
        compatible = latest in dsh_runtime_compat.verified_versions()
        updates.update(
            dsh_latest=latest, dsh_target=latest,
            dsh_cached_ready=selected == latest,
        )
        if runtime["verified"] and runtime["version"] == latest:
            updates.update(dsh_status="current", dsh_action="Up to date")
        elif override:
            updates.update(dsh_status="blocked", dsh_action="Pinned", dsh_note=f"Pinned by {override}")
        elif not compatible:
            updates.update(
                dsh_status="blocked", dsh_action="Await compatibility",
                dsh_can_update=False,
                dsh_note=(
                    f"DSH {latest} is available but is not compatibility-verified; "
                    f"serving remains on {runtime['version'] or selected or 'the last verified release'}"
                ),
            )
        elif selected == latest:
            action = "Start required version"
            updates.update(
                dsh_status="staged", dsh_action=action, dsh_can_update=True,
                dsh_note=f"DSH {latest} is cached and ready to activate",
            )
        else:
            status = "update" if runtime["verified"] else ("offline" if not runtime["online"] else "unknown")
            action = "Install required DSH"
            updates.update(dsh_status=status, dsh_action=action, dsh_can_update=True)
    except Exception as exc:
        updates.update(
            dsh_status="error", dsh_latest="Unavailable", dsh_action="Unavailable",
            dsh_note=f"DSH check failed: {exc}",
        )
    updates["bridge_online"] = _port_open(_BRIDGE_PORT)
    updates["message"] = _summary_for_state(updates)
    state.update(updates)


def _stage_or_activate(state: dict, component: str, success_message: str) -> None:
    activity = _runtime_activity()
    if activity["safe"]:
        state.update(
            busy=False, result="activate", activation="services",
            message=success_message + " Restarting services now…",
        )
    else:
        state.update({
            f"{component}_status": "staged",
            f"{component}_can_update": True,
            f"{component}_action": "Restart when idle",
            "busy": False,
            "result": "render",
            "message": success_message + " Restart deferred: " + activity["note"],
        })


def _prepare_activation(state: dict, component: str, success_message: str = "Update is ready.", *, force_frontend=False) -> None:
    try:
        if force_frontend:
            if component != 'repair':
                raise RuntimeError('Force restart is only available for explicit runtime repair')
            state.update(busy=False, result='activate', activation='force-services',
                         message='Force repair requested; verifying process identity and Houdini execution state…')
            return
        if component == "dsh":
            if _dsh_launch_override() or state.get("dsh_target") != dsh_runtime_compat.preferred_version():
                raise RuntimeError("required DSH selection changed; refresh before starting")
        _stage_or_activate(state, component, success_message)
    except Exception as exc:
        state.update(busy=False, result="render", message=f"Could not restart safely: {exc}")


def _update_dsh(state: dict) -> None:
    try:
        latest = dsh_runtime_compat.preferred_version()
        if state.get("dsh_target", latest) != latest:
            raise RuntimeError("required DSH version changed; refresh before installing")
        dsh_runtime_compat.require_verified(latest)
        override = _dsh_launch_override()
        if override:
            raise RuntimeError(f"launcher is pinned by {override}; remove that override before updating")

        def publish_progress(progress: dict) -> None:
            message = _download_progress_message(progress)
            state.update(
                download_progress=progress,
                message=message,
                dsh_note=message,
            )

        output = _run_npx_dsh(latest, on_progress=publish_progress)
        _require_cached_dsh(latest)
        state.update(
            dsh_latest=latest, dsh_target=latest, dsh_status="staged",
            dsh_action="Restart when idle", dsh_can_update=True,
            dsh_note=f"DSH {latest} downloaded and verified ({output or 'ok'})",
            download_progress=None,
        )
        _stage_or_activate(state, "dsh", f"DSH {latest} is ready.")
    except Exception as exc:
        message = f"DSH update failed: {exc}"
        state.update(
            busy=False, result="render", message=message,
            dsh_status="error", dsh_note=message, download_progress=None,
        )


def show_version_manager() -> None:
    """Show runtime facts and explicit repair, separate from release installation."""
    global _WINDOW, _TIMER
    from hutil.Qt import QtCore, QtGui, QtWidgets
    from dsh_ui_style import style_dialog, confirm_dialog

    if _WINDOW is not None and _WINDOW.isVisible():
        _WINDOW.raise_()
        _WINDOW.activateWindow()
        return

    dialog = QtWidgets.QDialog(hou.qt.mainWindow())
    dialog.setWindowTitle("DSH-Houdini · 运行诊断")
    dialog.setWindowModality(QtCore.Qt.NonModal)
    dialog.setMinimumWidth(620)
    style_dialog(dialog)
    layout = QtWidgets.QVBoxLayout(dialog)
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
    heading.addWidget(label("运行诊断", "title"))
    heading.addStretch(1)
    refresh_btn = QtWidgets.QPushButton("刷新状态")
    refresh_btn.setObjectName("quiet")
    heading.addWidget(refresh_btn)
    layout.addLayout(heading)
    summary_label = label("正在检查运行环境…", "summary")
    layout.addWidget(summary_label)
    frame = QtWidgets.QFrame()
    frame.setObjectName("rail")
    grid = QtWidgets.QGridLayout(frame)
    grid.setContentsMargins(18, 16, 18, 16)
    grid.setHorizontalSpacing(24)
    grid.setVerticalSpacing(8)
    grid.addWidget(label("当前运行 DSH", "caption"), 0, 0)
    grid.addWidget(label("插件配套 DSH", "caption"), 0, 1)
    dsh_current = label("检查中…", "version")
    dsh_latest = label("检查中…", "version")
    grid.addWidget(dsh_current, 1, 0)
    grid.addWidget(dsh_latest, 1, 1)
    service_label = label("", "caption")
    grid.addWidget(service_label, 2, 0, 1, 2)
    layout.addWidget(frame)

    actions = QtWidgets.QHBoxLayout()
    dsh_action = QtWidgets.QPushButton("准备配套版本")
    dsh_action.setObjectName("primary")
    dsh_action.hide()
    repair_btn = QtWidgets.QPushButton("修复并重启运行环境…")
    log_btn = QtWidgets.QPushButton("打开运行日志")
    actions.addWidget(dsh_action)
    actions.addWidget(repair_btn)
    actions.addWidget(log_btn)
    actions.addStretch(1)
    layout.addLayout(actions)
    download_bar = QtWidgets.QProgressBar()
    download_bar.setTextVisible(False)
    download_bar.hide()
    layout.addWidget(download_bar)
    advanced_toggle = QtWidgets.QPushButton("技术详情")
    advanced_toggle.setObjectName("quiet")
    advanced_toggle.setStyleSheet("text-align: left; padding-left: 0;")
    advanced_toggle.setCheckable(True)
    layout.addWidget(advanced_toggle)
    details = QtWidgets.QPlainTextEdit()
    details.setReadOnly(True)
    details.setFixedHeight(160)
    details.hide()
    layout.addWidget(details)
    state = {"busy": False, "result": None, "dsh_status": None,
             "dsh_can_update": False, "operation": "check"}

    def set_busy(message, operation):
        if state["busy"]:
            return False
        state.update(busy=True, result=None, message=message, download_progress=None, operation=operation)
        summary_label.setText(message)
        for button in (refresh_btn, dsh_action, repair_btn):
            button.setEnabled(False)
        return True

    def check_updates():
        if set_busy("正在检查运行版本和连接…", "check"):
            threading.Thread(target=_check_updates, args=(state,), daemon=True).start()

    def update_dsh():
        if state.get("dsh_status") == "staged":
            if set_busy("正在检查运行环境是否空闲…", "activate"):
                threading.Thread(target=_prepare_activation, args=(state, "dsh"), daemon=True).start()
            return
        target = state.get("dsh_target", "配套版本")
        answer = confirm_dialog(
            dialog, "准备配套运行环境", f"下载并校验 DSH {target}？\n\n"
            "完成后会在空闲时重启运行环境。有对话任务或 Houdini 操作正在执行时，将推迟重启。",
            "继续")
        if answer and set_busy("正在下载并校验配套运行环境…", "update"):
            threading.Thread(target=_update_dsh, args=(state,), daemon=True).start()

    def repair_runtime():
        answer = confirm_dialog(
            dialog, "修复并重启运行环境",
            "停止本安装的 DSH 服务并重新启动？\n\n"
            "进行中的对话和外部工具可能被中断；会话文件会保留，但未完成的结果可能丢失。\n\n"
            "此操作不会关闭 Houdini。Houdini 仍在执行操作，或无法确认空闲时，将拒绝重启。",
            "继续")
        if answer and set_busy("正在核验服务身份并准备修复…", "repair"):
            threading.Thread(target=_prepare_activation, args=(state, "repair", "运行环境已准备好修复。"),
                             kwargs={"force_frontend": True}, daemon=True).start()

    def open_log():
        if not os.path.isfile(_FRONTEND_LOG):
            summary_label.setText("尚无运行日志，请先打开一次工作区。")
            return
        if not QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(_FRONTEND_LOG)):
            summary_label.setText("无法打开日志，文件位置已放入技术详情。")
            details.appendPlainText(_FRONTEND_LOG)

    def toggle_advanced(checked):
        details.setVisible(checked)
        advanced_toggle.setText("收起技术详情" if checked else "技术详情")
        dialog.adjustSize()

    def launch_services(force_frontend=False):
        dialog.close()
        import dsh_launcher
        importlib.reload(dsh_launcher)
        dsh_launcher.launch(force_frontend=True) if force_frontend else dsh_launcher.launch()

    def render_state():
        download_bar.hide()
        message = _summary_for_state(state)
        if state.get("operation") in ("repair", "activate"):
            message = "暂未重启，请查看技术详情中的原因。"
        elif state.get("operation") == "update" and state.get("dsh_status") == "error":
            message = "配套运行环境准备失败，请查看技术详情。"
        summary_label.setText(message)
        current = str(state.get("dsh_current", "Unknown"))
        dsh_current.setText({"Unknown": "未核验", "Not running": "未启动"}.get(current, current))
        required = str(state.get("dsh_latest", "Unavailable"))
        dsh_latest.setText("无法读取" if required == "Unavailable" else required)
        frontend = "服务端口可用" if state.get("frontend_online") else "服务端口未开启"
        bridge = "Houdini 端口可用" if state.get("bridge_online") else "Houdini 端口未开启"
        service_label.setText(frontend + " · " + bridge)
        dsh_action.setText("启用配套版本" if state.get("dsh_status") == "staged" else "准备配套版本")
        dsh_action.setVisible(bool(state.get("dsh_can_update")))
        for button in (refresh_btn, dsh_action, repair_btn):
            button.setEnabled(True)
        details.setPlainText(f"DSH 服务端口：{_FRONTEND_PORT}\nHoudini 连接端口：{_BRIDGE_PORT}\n"
                             + str(state.get("dsh_note", "")) + "\n" + str(state.get("message", "")))
        dialog.adjustSize()

    def tick():
        if state.get("busy"):
            progress = state.get("download_progress")
            if isinstance(progress, dict):
                total, done = int(progress.get("packages_total") or 0), int(progress.get("packages_done") or 0)
                download_bar.setRange(0, total)
                if total:
                    download_bar.setValue(min(done, total))
                download_bar.show()
                summary_label.setText(f"正在准备依赖 · 已完成 {done}/{total or '…'} 个包 · "
                                      f"{_format_bytes(progress.get('bytes_downloaded', 0))}")
                details.setPlainText(_download_progress_message(progress))
            return
        result = state.pop("result", None)
        if result == "activate":
            activation = state.pop("activation", None)
            if activation in ("services", "force-services"):
                launch_services(force_frontend=activation == "force-services")
                return
        if result is not None:
            render_state()

    def cleanup(_code):
        global _WINDOW, _TIMER
        if _TIMER is not None:
            _TIMER.stop()
        _WINDOW = None
        _TIMER = None

    refresh_btn.clicked.connect(check_updates)
    dsh_action.clicked.connect(update_dsh)
    advanced_toggle.toggled.connect(toggle_advanced)
    repair_btn.clicked.connect(repair_runtime)
    log_btn.clicked.connect(open_log)
    dialog.finished.connect(cleanup)
    timer = QtCore.QTimer(dialog)
    timer.timeout.connect(tick)
    timer.start(100)
    _WINDOW, _TIMER = dialog, timer
    dialog.show()
    QtCore.QTimer.singleShot(0, check_updates)


if __name__ == "__main__":
    show_version_manager()
