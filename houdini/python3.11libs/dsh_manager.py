"""Focused version status and safe update UI for DSH-Houdini."""

from __future__ import annotations

import collections
import glob
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

_WINDOW = None
_TIMER = None


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _run_process(args: list[str], timeout: int = 20, *, env: dict | None = None):
    return subprocess.run(
        args, cwd=_PROJECT_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
        creationflags=_CREATE_NO_WINDOW if os.name == "nt" else 0, env=env,
    )


def _run(args: list[str], timeout: int = 20, *, env: dict | None = None) -> str:
    proc = _run_process(args, timeout, env=env)
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
        raise RuntimeError(message.splitlines()[-1])
    return proc.stdout.strip()


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


def _plugin_identity() -> tuple[str, str, bool]:
    version = _read_json(os.path.join(_PROJECT_ROOT, "package.json")).get("version", "unknown")
    branch = _run(["git", "branch", "--show-current"], 5) or "detached"
    commit = _run(["git", "rev-parse", "--short", "HEAD"], 5)
    dirty = bool(_run(["git", "status", "--porcelain"], 5))
    return str(version), f"{branch}@{commit}", dirty


def _cached_dsh_installations() -> list[dict]:
    pattern = os.path.join(
        _NPM_CACHE, "_npx", "*", "node_modules", "@deepseek-ai", "dsh", "package.json",
    )
    installs = []
    for path in glob.glob(pattern):
        version = _read_json(path).get("version")
        bin_path = os.path.join(os.path.dirname(path), "lib", "bin.js")
        if not version or not os.path.isfile(bin_path):
            continue
        try:
            modified = os.path.getmtime(bin_path)
        except OSError:
            modified = 0.0
        installs.append({"version": str(version), "bin": bin_path, "modified": modified})
    return sorted(installs, key=lambda item: item["modified"], reverse=True)


def _cached_dsh_versions() -> list[str]:
    return list(dict.fromkeys(item["version"] for item in _cached_dsh_installations()))


def _selected_cached_dsh_version() -> str | None:
    installs = _cached_dsh_installations()
    return installs[0]["version"] if installs else None


def _promote_cached_dsh(version: str) -> None:
    matches = [item for item in _cached_dsh_installations() if item["version"] == version]
    if not matches:
        raise RuntimeError(f"DSH {version} finished but was not found in {_NPM_CACHE}")
    os.utime(matches[0]["bin"], None)


def _dsh_release_info() -> tuple[str, str]:
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm was not found; check the Node.js installation")
    raw = _run([npm, "view", "@deepseek-ai/dsh", "version", "dist-tags", "--json"], 45)
    npm_info = json.loads(raw)
    tags = npm_info.get("dist-tags", {}) if isinstance(npm_info, dict) else {}
    latest = str(tags.get("latest") or npm_info.get("version", "")).strip()
    next_version = str(tags.get("next") or "n/a").strip()
    if not latest or not _PACKAGE_VERSION_RE.fullmatch(latest):
        raise RuntimeError(f"npm returned an invalid DSH version: {latest!r}")
    return latest, next_version


def _dsh_launch_override() -> str | None:
    explicit_bin = os.environ.get("DSH_HOUDINI_DSH_BIN", "").strip()
    if explicit_bin:
        return "DSH_HOUDINI_DSH_BIN"
    spec = os.environ.get("DSH_HOUDINI_DSH_SPEC", _DEFAULT_DSH_SPEC).strip()
    if spec != _DEFAULT_DSH_SPEC:
        return f"DSH_HOUDINI_DSH_SPEC={spec or '(empty)'}"
    return None


def _git_is_ancestor(older: str, newer: str) -> bool:
    proc = _run_process(["git", "merge-base", "--is-ancestor", older, newer], 10)
    if proc.returncode not in (0, 1):
        message = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
        raise RuntimeError(message.splitlines()[-1])
    return proc.returncode == 0


def _plugin_remote_status() -> dict:
    _run(["git", "fetch", "--quiet", "origin", "main"], 90)
    local_head = _run(["git", "rev-parse", "HEAD"], 5)
    remote_head = _run(["git", "rev-parse", "refs/remotes/origin/main"], 5)
    local_version, revision, dirty = _plugin_identity()
    remote_package = json.loads(_run(["git", "show", f"{remote_head}:package.json"], 10))
    remote_version = str(remote_package.get("version", "unknown"))

    if local_head == remote_head:
        relation, update_available, blocked = "current", False, False
    elif _git_is_ancestor(local_head, remote_head):
        relation, update_available, blocked = "behind", True, dirty
    elif _git_is_ancestor(remote_head, local_head):
        relation, update_available, blocked = "ahead", False, False
    else:
        relation, update_available, blocked = "diverged", True, True

    note = f"{revision} · {relation} origin/main"
    if dirty:
        note += " · local changes"
    return {
        "localHead": local_head, "remoteHead": remote_head,
        "localVersion": local_version, "remoteVersion": remote_version,
        "dirty": dirty, "relation": relation,
        "updateAvailable": update_available, "blocked": blocked,
        "canUpdate": update_available and not blocked, "note": note,
    }


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
    )
    if verified:
        note = f"PID {listener_pid} · {marker.get('source', 'unknown')}"
    else:
        note = "Running service predates version tracking; restart once to verify"
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


def _dsh_rpc(method: str, payload: dict) -> dict:
    decoded = _http_json(
        f"http://127.0.0.1:{_FRONTEND_PORT}/api/{method}",
        {"type": "client-request", "rpcId": "dsh-houdini-manager-" + uuid.uuid4().hex,
         "method": method, "payload": payload},
    )
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
    frontend_online = _port_open(_FRONTEND_PORT)
    bridge_online = _port_open(_BRIDGE_PORT)
    if frontend_online:
        try:
            value = _dsh_rpc("session.list", {})
            items = value.get("items", [])
            if not isinstance(items, list):
                raise RuntimeError("session.list items is not a list")
            active_sessions = sum(
                1 for item in items if isinstance(item, dict) and item.get("running") is True
            )
        except Exception as exc:
            reasons.append(f"DSH activity unknown: {exc}")
    if bridge_online:
        try:
            health = _http_json(f"http://127.0.0.1:{_BRIDGE_PORT}/health")
            active_jobs = int(health.get("activeJobs", 0))
        except Exception as exc:
            reasons.append(f"Houdini job activity unknown: {exc}")
    if active_sessions:
        reasons.append(f"{active_sessions} DSH session(s) are running")
    if active_jobs:
        reasons.append(f"{active_jobs} Houdini job(s) are active")
    return {
        "safe": not reasons, "activeSessions": active_sessions, "activeJobs": active_jobs,
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
    if state.get("busy"):
        return state.get("message") or "Checking versions…"
    statuses = [state.get("dsh_status"), state.get("plugin_status")]
    if "error" in statuses:
        return "Some version information could not be verified"
    if "blocked" in statuses:
        return "An update is available but needs attention"
    count = sum(status in ("update", "offline", "unknown", "staged") for status in statuses)
    if count:
        verb = "needs" if count == 1 else "need"
        return f"{count} component{'s' if count != 1 else ''} {verb} attention"
    if statuses == ["current", "current"]:
        return "Everything is up to date"
    return "Version status is not checked yet"


def _check_updates(state: dict) -> None:
    updates = {
        "busy": False, "result": "render", "checked": True,
        "dsh_can_update": False, "plugin_can_update": False,
        "frontend_online": False, "bridge_online": False,
    }
    try:
        runtime = _runtime_dsh_info()
        updates["frontend_online"] = runtime["online"]
        updates["dsh_current"] = runtime["version"] or ("Not running" if not runtime["online"] else "Unknown")
        updates["dsh_note"] = runtime["note"]
        latest, next_version = _dsh_release_info()
        selected = _selected_cached_dsh_version()
        override = _dsh_launch_override()
        updates.update(
            dsh_latest=latest, dsh_target=latest, dsh_next=next_version,
            dsh_cached_ready=selected == latest,
        )
        if override:
            updates.update(dsh_status="blocked", dsh_action="Pinned", dsh_note=f"Pinned by {override}")
        elif runtime["verified"] and runtime["version"] == latest:
            updates.update(dsh_status="current", dsh_action="Up to date")
        elif selected == latest:
            action = "Restart to latest" if runtime["online"] else "Start latest"
            updates.update(
                dsh_status="staged", dsh_action=action, dsh_can_update=True,
                dsh_note=f"DSH {latest} is cached and ready to activate",
            )
        else:
            status = "update" if runtime["verified"] else ("offline" if not runtime["online"] else "unknown")
            action = "Update and restart" if runtime["online"] else "Install and start"
            updates.update(dsh_status=status, dsh_action=action, dsh_can_update=True)
    except Exception as exc:
        updates.update(
            dsh_status="error", dsh_latest="Unavailable", dsh_action="Unavailable",
            dsh_note=f"DSH check failed: {exc}",
        )
    try:
        plugin = _plugin_remote_status()
        updates.update(
            plugin_current=f"{plugin['localVersion']} · {plugin['localHead'][:7]}",
            plugin_latest=f"{plugin['remoteVersion']} · {plugin['remoteHead'][:7]}",
            plugin_note=plugin["note"],
        )
        if plugin["blocked"]:
            updates.update(plugin_status="blocked", plugin_action="Resolve local Git state")
        elif plugin["updateAvailable"]:
            updates.update(plugin_status="update", plugin_action="Update plugin", plugin_can_update=True)
        else:
            updates.update(plugin_status="current", plugin_action="Up to date")
    except Exception as exc:
        try:
            version, revision, dirty = _plugin_identity()
            current = f"{version} · {revision.split('@')[-1]}"
            note = ("local changes · " if dirty else "") + f"remote check failed: {exc}"
        except Exception:
            current, note = "Unknown", f"remote check failed: {exc}"
        updates.update(
            plugin_current=current, plugin_latest="Unavailable", plugin_status="error",
            plugin_action="Unavailable", plugin_note=note,
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


def _prepare_activation(state: dict, component: str, success_message: str = "Update is ready.") -> None:
    try:
        _stage_or_activate(state, component, success_message)
    except Exception as exc:
        state.update(busy=False, result="render", message=f"Could not restart safely: {exc}")


def _update_dsh(state: dict) -> None:
    try:
        latest = str(state.get("dsh_target") or _dsh_release_info()[0])
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
        _promote_cached_dsh(latest)
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


_HOUDINI_RESTART_FILES = {"houdini/MainMenuCommon.xml", "houdini/install.py"}


def _update_plugin(state: dict) -> None:
    try:
        status = _plugin_remote_status()
        if status["blocked"]:
            raise RuntimeError("Git history diverged or the working tree has local changes")
        if not status["updateAvailable"]:
            state.update(
                busy=False, result="render", plugin_status="current",
                message="DSH-Houdini is already current.",
            )
            return
        before = status["localHead"]
        _run(["git", "pull", "--ff-only", "origin", "main"], 180)
        after_head = _run(["git", "rev-parse", "HEAD"], 5)
        changed = set(_run(["git", "diff", "--name-only", before, after_head], 20).splitlines())
        npm = shutil.which("npm")
        if not npm:
            raise RuntimeError("npm was not found; source updated but dependencies were not installed")
        _run([npm, "install", "--no-audit", "--no-fund"], 600)
        _run([npm, "run", "build"], 600)
        after = _plugin_remote_status()
        state.update(
            plugin_current=f"{after['localVersion']} · {after['localHead'][:7]}",
            plugin_latest=f"{after['remoteVersion']} · {after['remoteHead'][:7]}",
            plugin_note=after["note"], plugin_status="current",
            plugin_action="Up to date", plugin_can_update=False, reload_manager=True,
        )
        if changed & _HOUDINI_RESTART_FILES:
            state.update(
                busy=False, result="render",
                message="Plugin updated. Restart Houdini to reload menu or installation files.",
            )
        else:
            _stage_or_activate(state, "plugin", "DSH-Houdini was updated and built.")
    except Exception as exc:
        state.update(busy=False, result="render", message=f"DSH-Houdini update failed: {exc}")


def show_version_manager() -> None:
    """Show a non-modal, version-focused panel on Houdini's GUI thread."""
    global _WINDOW, _TIMER
    from hutil.Qt import QtCore, QtWidgets

    if _WINDOW is not None and _WINDOW.isVisible():
        _WINDOW.raise_()
        _WINDOW.activateWindow()
        return

    dialog = QtWidgets.QDialog(hou.qt.mainWindow())
    dialog.setWindowTitle("DSH-Houdini - Version status")
    dialog.setWindowModality(QtCore.Qt.NonModal)
    dialog.setMinimumWidth(720)
    dialog.setStyleSheet(
        "QDialog { background: #202327; color: #E8EAED; }"
        "QLabel#title { color: #F3F4F5; font: 600 21px 'Segoe UI'; }"
        "QLabel#summary { color: #C8CDD2; font: 12px 'Segoe UI'; padding-bottom: 6px; }"
        "QLabel#column { color: #7F8891; font: 10px 'Segoe UI'; }"
        "QLabel#name { color: #F1F2F3; font: 600 13px 'Segoe UI'; }"
        "QLabel#version { color: #E3E6E8; font: 12px 'Consolas'; }"
        "QLabel#note { color: #929AA2; font: 11px 'Segoe UI'; }"
        "QFrame#rail { background: #292D32; border: 1px solid #3A4047; border-radius: 5px; }"
        "QFrame#advanced { background: #25292D; border-top: 1px solid #373C42; }"
        "QPushButton { color: #E7E9EB; background: #343940; border: 1px solid #48505A;"
        " border-radius: 4px; padding: 6px 12px; font: 11px 'Segoe UI'; }"
        "QPushButton:hover { background: #40464E; }"
        "QPushButton:disabled { color: #777F87; background: #2C3035; border-color: #383D43; }"
        "QPushButton#update { background: #C85F19; border-color: #E97824; color: white; }"
        "QPushButton#update:hover { background: #DE6D21; }"
        "QPushButton#quiet { background: transparent; border-color: transparent; color: #A8AFB6; }"
        "QProgressBar { background: #343940; border: none; border-radius: 3px;"
        " height: 7px; color: transparent; }"
        "QProgressBar::chunk { background: #E97824; border-radius: 3px; }"
    )

    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(22, 20, 22, 18)
    layout.setSpacing(10)
    heading = QtWidgets.QHBoxLayout()
    title = QtWidgets.QLabel("Version status")
    title.setObjectName("title")
    refresh_btn = QtWidgets.QPushButton("Refresh")
    refresh_btn.setObjectName("quiet")
    refresh_btn.setToolTip("Check npm and origin/main again")
    heading.addWidget(title)
    heading.addStretch(1)
    heading.addWidget(refresh_btn)
    layout.addLayout(heading)
    summary_label = QtWidgets.QLabel("Checking installed and latest versions…")
    summary_label.setObjectName("summary")
    layout.addWidget(summary_label)

    columns = QtWidgets.QGridLayout()
    columns.setContentsMargins(14, 0, 14, 0)
    columns.setHorizontalSpacing(16)
    for column in range(3):
        columns.setColumnStretch(column, 2)
    columns.setColumnStretch(3, 0)
    for column, text in ((1, "CURRENT"), (2, "LATEST")):
        label = QtWidgets.QLabel(text)
        label.setObjectName("column")
        columns.addWidget(label, 0, column)
    layout.addLayout(columns)

    def component_rail(name: str):
        frame = QtWidgets.QFrame()
        frame.setObjectName("rail")
        grid = QtWidgets.QGridLayout(frame)
        grid.setContentsMargins(14, 12, 14, 11)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(5)
        for column in range(3):
            grid.setColumnStretch(column, 2)
        grid.setColumnStretch(3, 0)
        name_label = QtWidgets.QLabel(name)
        name_label.setObjectName("name")
        current_label = QtWidgets.QLabel("Checking…")
        current_label.setObjectName("version")
        latest_label = QtWidgets.QLabel("Checking…")
        latest_label.setObjectName("version")
        action_btn = QtWidgets.QPushButton("Checking…")
        action_btn.setMinimumWidth(132)
        note_label = QtWidgets.QLabel("")
        note_label.setObjectName("note")
        note_label.setWordWrap(True)
        grid.addWidget(name_label, 0, 0)
        grid.addWidget(current_label, 0, 1)
        grid.addWidget(latest_label, 0, 2)
        grid.addWidget(action_btn, 0, 3)
        grid.addWidget(note_label, 1, 0, 1, 4)
        layout.addWidget(frame)
        return current_label, latest_label, action_btn, note_label

    dsh_current, dsh_latest, dsh_action, dsh_note = component_rail("DeepSeek Harness")
    plugin_current, plugin_latest, plugin_action, plugin_note = component_rail("DSH-Houdini")
    download_panel = QtWidgets.QFrame()
    download_panel.setObjectName("rail")
    download_layout = QtWidgets.QVBoxLayout(download_panel)
    download_layout.setContentsMargins(14, 10, 14, 11)
    download_layout.setSpacing(7)
    download_bar = QtWidgets.QProgressBar()
    download_bar.setTextVisible(False)
    download_label = QtWidgets.QLabel("")
    download_label.setObjectName("note")
    download_label.setWordWrap(True)
    download_layout.addWidget(download_bar)
    download_layout.addWidget(download_label)
    download_panel.setVisible(False)
    layout.addWidget(download_panel)
    advanced_toggle = QtWidgets.QPushButton("Advanced diagnostics  ▸")
    advanced_toggle.setObjectName("quiet")
    advanced_toggle.setCheckable(True)
    advanced_toggle.setStyleSheet("text-align: left;")
    layout.addWidget(advanced_toggle)
    advanced = QtWidgets.QFrame()
    advanced.setObjectName("advanced")
    advanced_layout = QtWidgets.QVBoxLayout(advanced)
    advanced_layout.setContentsMargins(12, 10, 12, 8)
    service_label = QtWidgets.QLabel("Service state is checked in the background.")
    service_label.setObjectName("note")
    detail_label = QtWidgets.QLabel("")
    detail_label.setObjectName("note")
    detail_label.setWordWrap(True)
    advanced_buttons = QtWidgets.QHBoxLayout()
    repair_btn = QtWidgets.QPushButton("Repair and restart runtime")
    log_btn = QtWidgets.QPushButton("Open frontend log")
    advanced_buttons.addWidget(repair_btn)
    advanced_buttons.addWidget(log_btn)
    advanced_buttons.addStretch(1)
    advanced_layout.addWidget(service_label)
    advanced_layout.addWidget(detail_label)
    advanced_layout.addLayout(advanced_buttons)
    advanced.setVisible(False)
    layout.addWidget(advanced)

    state = {
        "busy": False, "result": None, "checked": False,
        "message": "Checking installed and latest versions…",
        "dsh_status": None, "plugin_status": None,
        "dsh_can_update": False, "plugin_can_update": False,
    }

    def set_busy(message: str) -> bool:
        if state["busy"]:
            return False
        state.update(busy=True, result=None, message=message, download_progress=None)
        download_panel.setVisible(False)
        summary_label.setText(message)
        for button in (refresh_btn, dsh_action, plugin_action, repair_btn):
            button.setEnabled(False)
        return True

    def check_updates() -> None:
        if set_busy("Checking DSH on npm and DSH-Houdini on origin/main…"):
            threading.Thread(target=_check_updates, args=(state,), daemon=True).start()

    def update_dsh() -> None:
        if state.get("dsh_status") == "staged":
            if set_busy("Checking whether the runtime is idle…"):
                threading.Thread(target=_prepare_activation, args=(state, "dsh"), daemon=True).start()
            return
        target = state.get("dsh_target", "the latest release")
        answer = QtWidgets.QMessageBox.question(
            dialog, "Update DeepSeek Harness",
            f"Download DSH {target} and restart services when the runtime is idle?\n\n"
            "Package count, received bytes, and download speed remain visible throughout. "
            "There is no automatic total timeout.\n\n"
            "If an agent turn or Houdini job is active, the restart will be deferred.",
        )
        if answer == QtWidgets.QMessageBox.Yes and set_busy(f"Downloading and verifying DSH {target}…"):
            threading.Thread(target=_update_dsh, args=(state,), daemon=True).start()

    def update_plugin() -> None:
        if state.get("plugin_status") == "staged":
            if set_busy("Checking whether the runtime is idle…"):
                threading.Thread(target=_prepare_activation, args=(state, "plugin"), daemon=True).start()
            return
        answer = QtWidgets.QMessageBox.question(
            dialog, "Update DSH-Houdini",
            "Fast-forward origin/main, install dependencies, build, and restart services when idle?\n\n"
            "Updates are blocked when local Git changes would make the operation unsafe.",
        )
        if answer == QtWidgets.QMessageBox.Yes and set_busy("Updating and building DSH-Houdini…"):
            threading.Thread(target=_update_plugin, args=(state,), daemon=True).start()

    def repair_runtime() -> None:
        answer = QtWidgets.QMessageBox.question(
            dialog, "Repair runtime",
            "Restart the Houdini bridge and DSH frontend when no active work is detected?",
        )
        if answer == QtWidgets.QMessageBox.Yes and set_busy("Checking whether the runtime is idle…"):
            threading.Thread(
                target=_prepare_activation,
                args=(state, "repair", "Runtime repair is ready."),
                daemon=True,
            ).start()

    def open_log() -> None:
        if not os.path.isfile(_FRONTEND_LOG):
            detail_label.setText("No frontend log exists yet. Start the service once, then try again.")
            return
        try:
            os.startfile(_FRONTEND_LOG)  # type: ignore[attr-defined]
        except Exception as exc:
            detail_label.setText(f"Could not open the log: {exc} · {_FRONTEND_LOG}")

    def toggle_advanced(checked: bool) -> None:
        advanced.setVisible(checked)
        advanced_toggle.setText("Advanced diagnostics  ▾" if checked else "Advanced diagnostics  ▸")
        dialog.adjustSize()

    def launch_services() -> None:
        dialog.close()
        import dsh_launcher
        importlib.reload(dsh_launcher)
        dsh_launcher.launch()

    def render_state() -> None:
        download_panel.setVisible(False)
        summary_label.setText(state.get("message") or _summary_for_state(state))
        dsh_current.setText(str(state.get("dsh_current", "Unknown")))
        dsh_latest.setText(str(state.get("dsh_latest", "Unknown")))
        dsh_detail = str(state.get("dsh_note", ""))
        show_dsh_note = state.get("dsh_status") in ("blocked", "error", "unknown", "offline", "staged")
        dsh_note.setText(dsh_detail if show_dsh_note else "")
        dsh_note.setVisible(show_dsh_note)
        plugin_current.setText(str(state.get("plugin_current", "Unknown")))
        plugin_latest.setText(str(state.get("plugin_latest", "Unknown")))
        plugin_detail = str(state.get("plugin_note", ""))
        show_plugin_note = state.get("plugin_status") in ("blocked", "error", "staged")
        plugin_note.setText(plugin_detail if show_plugin_note else "")
        plugin_note.setVisible(show_plugin_note)
        dsh_action.setText(str(state.get("dsh_action", "Unavailable")))
        plugin_action.setText(str(state.get("plugin_action", "Unavailable")))
        for button, enabled in (
            (dsh_action, bool(state.get("dsh_can_update"))),
            (plugin_action, bool(state.get("plugin_can_update"))),
        ):
            button.setObjectName("update" if enabled else "")
            button.style().unpolish(button)
            button.style().polish(button)
            button.setEnabled(enabled)
        refresh_btn.setEnabled(True)
        repair_btn.setEnabled(True)
        bridge = "ONLINE" if state.get("bridge_online") else "OFFLINE"
        frontend = "ONLINE" if state.get("frontend_online") else "OFFLINE"
        service_label.setText(f"Houdini Bridge :8765  {bridge}    ·    DSH Web :3081  {frontend}")
        detail_label.setText(
            f"DSH: {dsh_detail}\nDSH-Houdini: {plugin_detail}\n{state.get('message', '')}"
        )

    def render_download_progress() -> None:
        progress = state.get("download_progress")
        if not isinstance(progress, dict):
            download_panel.setVisible(False)
            summary_label.setText(state.get("message") or "Working…")
            return
        total = int(progress.get("packages_total") or 0)
        done = int(progress.get("packages_done") or 0)
        if total:
            download_bar.setRange(0, total)
            download_bar.setValue(min(done, total))
        else:
            download_bar.setRange(0, 0)
        message = _download_progress_message(progress)
        download_label.setText(message)
        summary_label.setText(message)
        dsh_note.setText(message)
        dsh_note.setVisible(True)
        download_panel.setVisible(True)

    def tick() -> None:
        if state.get("busy"):
            render_download_progress()
            return
        if state.get("result") is None:
            return
        result = state.pop("result", None)
        if result == "activate" and state.pop("activation", None) == "services":
            launch_services()
            return
        render_state()

    def cleanup(_code: int) -> None:
        global _WINDOW, _TIMER
        if _TIMER is not None:
            _TIMER.stop()
        if state.get("reload_manager"):
            sys.modules.pop(__name__, None)
        _WINDOW = None
        _TIMER = None

    refresh_btn.clicked.connect(check_updates)
    dsh_action.clicked.connect(update_dsh)
    plugin_action.clicked.connect(update_plugin)
    advanced_toggle.toggled.connect(toggle_advanced)
    repair_btn.clicked.connect(repair_runtime)
    log_btn.clicked.connect(open_log)
    dialog.finished.connect(cleanup)
    timer = QtCore.QTimer(dialog)
    timer.timeout.connect(tick)
    timer.start(100)
    _WINDOW = dialog
    _TIMER = timer
    dialog.show()
    QtCore.QTimer.singleShot(0, check_updates)


if __name__ == "__main__":
    show_version_manager()
