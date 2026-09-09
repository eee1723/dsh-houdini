"""Standard-library regression for version state and safe activation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import types


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))
if "hou" not in sys.modules:
    sys.modules["hou"] = types.SimpleNamespace()

import dsh_launcher as launcher
import dsh_manager as manager
import dsh_bridge as bridge


assert manager._PACKAGE_VERSION_RE.fullmatch("0.1.1-rc.2")
assert not manager._PACKAGE_VERSION_RE.fullmatch("0.1.1 && whoami")


# Streamed npm output yields a deterministic missing-package denominator and
# completed tarball numerator. Byte/s formatting is independent of Qt.
tracker = manager._NpmDownloadTracker()
tarballs = (
    "https://registry.example.test/foo/-/foo-1.0.0.tgz",
    "https://registry.example.test/bar/-/bar-2.0.0.tgz",
)
for url in tarballs:
    tracker.feed(f"npm silly tarball no local data for pkg@{url}. Extracting by manifest.")
tracker.feed(f"npm http fetch GET 200 {tarballs[0]} 125ms (cache miss)")
snapshot = tracker.snapshot()
assert snapshot["packages_done"] == 1 and snapshot["packages_total"] == 2, snapshot
assert snapshot["stage"] == "Downloading packages", snapshot
message = manager._download_progress_message({
    **snapshot,
    "bytes_downloaded": 3 * 1024 * 1024,
    "speed_bps": 1.5 * 1024 * 1024,
    "elapsed": 65,
})
assert "1/2 packages" in message and "3.0 MiB received" in message, message
assert "1.5 MiB/s" in message and "01:05" in message, message

with bridge._jobs_lock:
    original_jobs = dict(bridge._jobs)
    bridge._jobs.clear()
    bridge._jobs.update({
        "queued": {"status": "queued"},
        "running": {"status": "running"},
        "done": {"status": "done"},
    })
try:
    assert bridge._job_activity() == {"activeJobs": 2, "queuedJobs": 1, "runningJobs": 1}
finally:
    with bridge._jobs_lock:
        bridge._jobs.clear()
        bridge._jobs.update(original_jobs)


# Repair validates the required cached release, never promotes by modification time.
original_cache = manager._NPM_CACHE
try:
    with tempfile.TemporaryDirectory() as raw_cache:
        manager._NPM_CACHE = raw_cache
        npx_root = Path(raw_cache) / "_npx"
        for index, version in enumerate(("0.1.1-rc.2", "0.1.2-rc.1"), start=1):
            package = npx_root / str(index) / "node_modules" / "@deepseek-ai" / "dsh"
            (package / "lib").mkdir(parents=True)
            (package / "package.json").write_text(
                json.dumps({"name": "@deepseek-ai/dsh", "version": version}), encoding="utf-8",
            )
            bin_path = package / "lib" / "bin.js"
            bin_path.write_text("// test", encoding="utf-8")
            os.utime(bin_path, (index, index))

        assert manager._selected_cached_dsh_version() == "0.1.2-rc.1"
        manager._require_cached_dsh("0.1.2-rc.1")
        assert manager._selected_cached_dsh_version() == "0.1.2-rc.1"
        try:
            manager._require_cached_dsh("0.1.1-rc.2")
        except RuntimeError as exc:
            assert "not compatibility-verified" in str(exc)
        else:
            raise AssertionError("unverified cached DSH must not be promoted")
finally:
    manager._NPM_CACHE = original_cache


# The current DSH version is trusted only when the marker PID owns :3081.
original_runtime = manager._RUNTIME_STATE
original_port_open = manager._port_open
original_port_pid = manager._port_pid
try:
    with tempfile.TemporaryDirectory() as raw_dir:
        marker = Path(raw_dir) / "runtime.json"
        marker.write_text(json.dumps({"pid": 42, "version": "0.1.1-rc.2", "source": "test"}))
        manager._RUNTIME_STATE = str(marker)
        manager._port_open = lambda port: True
        manager._port_pid = lambda port: 42
        info = manager._runtime_dsh_info()
        assert info["verified"] is True and info["version"] == "0.1.1-rc.2", info
        manager._port_pid = lambda port: 43
        info = manager._runtime_dsh_info()
        assert info["verified"] is False and info["version"] is None, info
finally:
    manager._RUNTIME_STATE = original_runtime
    manager._port_open = original_port_open
    manager._port_pid = original_port_pid


assert manager._summary_for_state({"dsh_status": "current", "plugin_status": "current"}) == (
    "Everything is up to date"
)
assert "1 component" in manager._summary_for_state(
    {"dsh_status": "update", "plugin_status": "current"}
)
assert "attention" in manager._summary_for_state(
    {"dsh_status": "blocked", "plugin_status": "current"}
)


originals = {
    "required": manager.dsh_runtime_compat.preferred_version,
    "selected": manager._selected_cached_dsh_version,
    "runtime": manager._runtime_dsh_info,
    "plugin": manager.dsh_release_policy.latest_stable_release,
    "identity": manager._plugin_identity,
    "override": manager._dsh_launch_override,
    "port_open": manager._port_open,
    "rpc": manager._dsh_rpc,
    "rpc_wire": manager._dsh_rpc_wire,
    "http": manager._http_json,
    "run_npx": manager._run_npx_dsh,
    "cached": manager._require_cached_dsh,
    "activity": manager._runtime_activity,
    "run": manager._run,
}
try:
    manager.dsh_runtime_compat.preferred_version = lambda: "0.1.2-rc.1"
    manager._selected_cached_dsh_version = lambda: "0.1.0-rc.7"
    manager._runtime_dsh_info = lambda: {
        "online": True, "verified": True, "version": "0.1.0-rc.7", "note": "PID 42",
    }
    manager._dsh_launch_override = lambda: None
    manager._plugin_identity = lambda: ("0.1.0", "source main@aaaaaaa", False)
    manager.dsh_release_policy.latest_stable_release = lambda: {
        "version": "0.1.1", "url": manager.dsh_release_policy.RELEASES_URL + "/tag/v0.1.1",
        "installable": False,
    }
    def forbidden_process(*args, **kwargs):
        raise AssertionError("release check must not fetch Git or resolve npm latest")
    manager._run = forbidden_process
    manager._port_open = lambda port: True
    state = {"busy": True}
    manager._check_updates(state)
    assert state["dsh_status"] == "update" and state["dsh_can_update"] is True, state
    assert state["plugin_status"] == "update" and state["plugin_can_update"] is True, state
    assert state["plugin_action"] == "View release", state
    assert "not verified" in state["plugin_note"], state

    manager._selected_cached_dsh_version = lambda: "0.1.2-rc.1"
    state = {"busy": True}
    manager._check_updates(state)
    assert state["dsh_status"] == "staged" and state["dsh_action"] == "Start required version", state
    manager._selected_cached_dsh_version = lambda: "0.1.0-rc.7"

    manager.dsh_runtime_compat.preferred_version = lambda: "0.1.3-unverified"
    state = {"busy": True}
    manager._check_updates(state)
    assert state["dsh_status"] == "blocked" and state["dsh_can_update"] is False, state
    assert state["dsh_action"] == "Await compatibility", state
    manager.dsh_runtime_compat.preferred_version = lambda: "0.1.2-rc.1"

    manager._dsh_launch_override = lambda: "DSH_HOUDINI_DSH_SPEC=@deepseek-ai/dsh@old"
    state = {"busy": True}
    manager._check_updates(state)
    assert state["dsh_status"] == "blocked" and state["dsh_can_update"] is False, state
    manager._dsh_launch_override = lambda: None

    # Dirty source trees do not block read-only release discovery or get overwritten.
    manager._plugin_identity = lambda: ("0.1.0", "source main@aaaaaaa", True)
    state = {"busy": True}
    manager._check_updates(state)
    assert state["plugin_status"] == "update" and state["plugin_action"] == "View release", state
    assert "local changes" in state["plugin_note"], state

    # A source tree at the same version is not falsely called a verified installation.
    manager._plugin_identity = lambda: ("0.1.1", "source (no Git identity)", False)
    manager._check_updates(state)
    assert state["plugin_status"] == "release", state
    manager.dsh_release_policy.latest_stable_release = lambda: None
    manager._check_updates(state)
    assert state["plugin_status"] == "unpublished" and not state["plugin_can_update"], state
    assert state["plugin_release_url"] is None, state

    def offline():
        raise TimeoutError("offline fixture")
    manager.dsh_release_policy.latest_stable_release = offline
    manager._check_updates(state)
    assert state["plugin_status"] == "error" and not state["plugin_can_update"], state
    assert state["plugin_release_url"] is None and "offline fixture" in state["plugin_note"], state

    # Both DSH turns and bridge jobs participate in the restart guard.
    manager._port_open = lambda port: True
    manager._dsh_rpc = lambda method, payload: {"items": [{"running": True}, {"running": False}]}
    manager._http_json = lambda url, data=None, timeout=5: {"activeJobs": 2}
    activity = manager._runtime_activity()
    assert activity["safe"] is False
    assert activity["activeSessions"] == 1 and activity["activeJobs"] == 2, activity

    manager._runtime_activity = lambda: {"safe": False, "note": "1 session is running"}
    state = {}
    manager._stage_or_activate(state, "dsh", "Ready.")
    assert state["result"] == "render" and state["dsh_status"] == "staged", state

    manager._runtime_activity = lambda: {"safe": True, "note": "Runtime is idle"}
    state = {}
    manager._stage_or_activate(state, "dsh", "Ready.")
    assert state["result"] == "activate" and state["activation"] == "services", state

    def fake_run_npx(version, on_progress=None):
        if on_progress is not None:
            on_progress({
                "stage": "Downloading packages",
                "packages_done": 2,
                "packages_total": 4,
                "bytes_downloaded": 1024,
                "speed_bps": 512,
                "elapsed": 2,
                "current": "fixture",
            })
        return version

    manager._run_npx_dsh = fake_run_npx
    manager._require_cached_dsh = lambda version: None
    state = {"busy": True, "dsh_target": "0.1.2-rc.1"}
    manager._update_dsh(state)
    assert state["result"] == "activate", state
    assert state["download_progress"] is None, state
    state = {"busy": True, "dsh_target": "0.1.1-rc.2"}
    manager._run_npx_dsh = forbidden_process
    manager._update_dsh(state)
    assert state["result"] == "render" and state["dsh_status"] == "error", state
    assert "refresh" in state["message"], state
    state = {"dsh_target": "0.1.1-rc.2"}
    manager._prepare_activation(state, "dsh")
    assert state["result"] == "render" and "refresh" in state["message"], state
finally:
    manager.dsh_runtime_compat.preferred_version = originals["required"]
    manager._selected_cached_dsh_version = originals["selected"]
    manager._runtime_dsh_info = originals["runtime"]
    manager.dsh_release_policy.latest_stable_release = originals["plugin"]
    manager._plugin_identity = originals["identity"]
    manager._dsh_launch_override = originals["override"]
    manager._port_open = originals["port_open"]
    manager._dsh_rpc = originals["rpc"]
    manager._dsh_rpc_wire = originals["rpc_wire"]
    manager._http_json = originals["http"]
    manager._run_npx_dsh = originals["run_npx"]
    manager._require_cached_dsh = originals["cached"]
    manager._runtime_activity = originals["activity"]
    manager._run = originals["run"]


# Launcher marker is atomic data derived from the selected CLI package.
original_launcher_state = launcher.FRONTEND_RUNTIME_STATE
original_pending = dict(launcher._PENDING)
try:
    with tempfile.TemporaryDirectory() as raw_dir:
        package = Path(raw_dir) / "dsh"
        (package / "lib").mkdir(parents=True)
        (package / "package.json").write_text(json.dumps({"version": "9.9.9-test"}), encoding="utf-8")
        bin_path = package / "lib" / "bin.js"
        bin_path.write_text("// test", encoding="utf-8")
        launcher.FRONTEND_RUNTIME_STATE = str(Path(raw_dir) / "runtime.json")
        launcher._PENDING.clear()
        launcher._PENDING.update(frontend_bin=str(bin_path), frontend_source="test-cli")
        launcher._PENDING["frontend_version"] = launcher._dsh_version_for_bin(str(bin_path))
        launcher._write_frontend_runtime_state(1234)
        marker = json.loads(Path(launcher.FRONTEND_RUNTIME_STATE).read_text(encoding="utf-8"))
        assert marker["pid"] == 1234 and marker["version"] == "9.9.9-test", marker
        launcher._clear_frontend_runtime_state()
        assert not Path(launcher.FRONTEND_RUNTIME_STATE).exists()
finally:
    launcher.FRONTEND_RUNTIME_STATE = original_launcher_state
    launcher._PENDING.clear()
    launcher._PENDING.update(original_pending)


print("dsh manager update tests passed")
