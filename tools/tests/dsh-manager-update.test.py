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


# Cache ordering is the launch selection contract; promotion makes an already
# cached exact release become the next deterministic launcher candidate.
original_cache = manager._NPM_CACHE
try:
    with tempfile.TemporaryDirectory() as raw_cache:
        manager._NPM_CACHE = raw_cache
        npx_root = Path(raw_cache) / "_npx"
        for index, version in enumerate(("0.1.0-rc.7", "0.1.1-rc.2"), start=1):
            package = npx_root / str(index) / "node_modules" / "@deepseek-ai" / "dsh"
            (package / "lib").mkdir(parents=True)
            (package / "package.json").write_text(
                json.dumps({"name": "@deepseek-ai/dsh", "version": version}), encoding="utf-8",
            )
            bin_path = package / "lib" / "bin.js"
            bin_path.write_text("// test", encoding="utf-8")
            os.utime(bin_path, (index, index))

        assert manager._selected_cached_dsh_version() == "0.1.1-rc.2"
        manager._promote_cached_dsh("0.1.0-rc.7")
        assert manager._selected_cached_dsh_version() == "0.1.0-rc.7"
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
    "release": manager._dsh_release_info,
    "selected": manager._selected_cached_dsh_version,
    "runtime": manager._runtime_dsh_info,
    "plugin": manager._plugin_remote_status,
    "identity": manager._plugin_identity,
    "override": manager._dsh_launch_override,
    "port_open": manager._port_open,
    "rpc": manager._dsh_rpc,
    "http": manager._http_json,
    "run_npx": manager._run_npx_dsh,
    "promote": manager._promote_cached_dsh,
    "activity": manager._runtime_activity,
}
try:
    manager._dsh_release_info = lambda: ("0.1.1-rc.2", "0.1.1-rc.2")
    manager._selected_cached_dsh_version = lambda: "0.1.0-rc.7"
    manager._runtime_dsh_info = lambda: {
        "online": True, "verified": True, "version": "0.1.0-rc.7", "note": "PID 42",
    }
    manager._dsh_launch_override = lambda: None
    manager._plugin_remote_status = lambda: {
        "localVersion": "0.1.0", "remoteVersion": "0.1.1",
        "localHead": "a" * 40, "remoteHead": "b" * 40,
        "blocked": False, "updateAvailable": True, "canUpdate": True,
        "note": "main@aaaaaaa · behind origin/main",
    }
    manager._port_open = lambda port: True
    state = {"busy": True}
    manager._check_updates(state)
    assert state["dsh_status"] == "update" and state["dsh_can_update"] is True, state
    assert state["plugin_status"] == "update" and state["plugin_can_update"] is True, state

    manager._selected_cached_dsh_version = lambda: "0.1.1-rc.2"
    state = {"busy": True}
    manager._check_updates(state)
    assert state["dsh_status"] == "staged" and state["dsh_action"] == "Restart to latest", state
    manager._selected_cached_dsh_version = lambda: "0.1.0-rc.7"

    manager._dsh_launch_override = lambda: "DSH_HOUDINI_DSH_SPEC=@deepseek-ai/dsh@old"
    state = {"busy": True}
    manager._check_updates(state)
    assert state["dsh_status"] == "blocked" and state["dsh_can_update"] is False, state
    manager._dsh_launch_override = lambda: None

    manager._plugin_remote_status = lambda: {
        "localVersion": "0.1.0", "remoteVersion": "0.1.1",
        "localHead": "a" * 40, "remoteHead": "b" * 40,
        "blocked": True, "updateAvailable": True, "canUpdate": False,
        "note": "local changes",
    }
    state = {"busy": True}
    manager._check_updates(state)
    assert state["plugin_status"] == "blocked" and state["plugin_can_update"] is False, state

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

    manager._run_npx_dsh = lambda version: version
    manager._promote_cached_dsh = lambda version: None
    state = {"busy": True, "dsh_target": "0.1.1-rc.2"}
    manager._update_dsh(state)
    assert state["result"] == "activate", state
finally:
    manager._dsh_release_info = originals["release"]
    manager._selected_cached_dsh_version = originals["selected"]
    manager._runtime_dsh_info = originals["runtime"]
    manager._plugin_remote_status = originals["plugin"]
    manager._plugin_identity = originals["identity"]
    manager._dsh_launch_override = originals["override"]
    manager._port_open = originals["port_open"]
    manager._dsh_rpc = originals["rpc"]
    manager._http_json = originals["http"]
    manager._run_npx_dsh = originals["run_npx"]
    manager._promote_cached_dsh = originals["promote"]
    manager._runtime_activity = originals["activity"]


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
