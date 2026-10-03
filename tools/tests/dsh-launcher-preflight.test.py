"""Pure regression for launcher listener preflight and external-process policy."""

from __future__ import annotations

from pathlib import Path
import importlib
import os
import sys
import tempfile
import types
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))
sys.modules.setdefault("hou", types.SimpleNamespace())

import dsh_launcher
import dsh_context

# Opening diagnostics during startup can reload the launcher implementation.
# The live preflight/worker lifetime and its UI references must survive it.
original_tracking = (dsh_launcher._PENDING, dsh_launcher._MAIN_DISPATCHES,
                     dsh_launcher._SERVICE_PREFLIGHT_ACTIVE, dsh_launcher._ACTIVE_STARTUP)
try:
    pending, dispatches, active = {"dialog": object()}, [object()], {"canceled": False}
    dsh_launcher._PENDING, dsh_launcher._MAIN_DISPATCHES = pending, dispatches
    dsh_launcher._SERVICE_PREFLIGHT_ACTIVE, dsh_launcher._ACTIVE_STARTUP = True, active
    importlib.reload(dsh_launcher)
    assert dsh_launcher._PENDING is pending and dsh_launcher._MAIN_DISPATCHES is dispatches
    assert dsh_launcher._SERVICE_PREFLIGHT_ACTIVE and dsh_launcher._ACTIVE_STARTUP is active
finally:
    (dsh_launcher._PENDING, dsh_launcher._MAIN_DISPATCHES,
     dsh_launcher._SERVICE_PREFLIGHT_ACTIVE, dsh_launcher._ACTIVE_STARTUP) = original_tracking

# Unsaved scenes must never reopen the last saved project. Their scratch
# workspace remains stable until a named project is selected in this process.
with tempfile.TemporaryDirectory(prefix='dsh-unsaved-workspace-') as temporary:
    current = {'path': str(Path(temporary) / 'untitled.hiplc'), 'new': True}
    hip_file = types.SimpleNamespace(path=lambda: current['path'], isNewFile=lambda: current['new'])
    fake_hou = types.SimpleNamespace(hipFile=hip_file, isUIAvailable=lambda: True)
    with patch.object(dsh_launcher, 'hou', fake_hou), patch.object(dsh_context, 'hou', fake_hou), \
         patch.object(dsh_launcher, '_FALLBACK_WORKSPACE', str(Path(temporary) / 'workspaces')), \
         patch.object(dsh_launcher, '_UNSAVED_WORKSPACE', None):
        first = dsh_launcher._hip_dir()
        assert Path(first).is_dir() and Path(first).parent == Path(temporary) / 'workspaces'
        assert first != str(Path(current['path']).parent)
        assert dsh_launcher._hip_dir() == first
        # Distinct default extensions and even an unrelated existing default
        # filename do not override the authoritative GUI new-file flag.
        for suffix in ('.hip', '.hiplc', '.hipnc'):
            current['path'] = str(Path(temporary) / ('untitled' + suffix))
            Path(current['path']).touch()
            assert dsh_launcher._hip_dir() == first
            assert dsh_context.hip_file_state()['hip_dir'] is None
        # A saved file named untitled is still a real project in the GUI.
        current['new'] = False
        assert dsh_launcher._hip_dir() == temporary
        assert dsh_launcher._UNSAVED_WORKSPACE is None
        current['path'] = str(Path(temporary) / 'other-project' / 'saved.hip')
        assert dsh_launcher._hip_dir() == str(Path(temporary) / 'other-project')
        current.update(path=str(Path(temporary) / 'untitled.hip'), new=True)
        second = dsh_launcher._hip_dir()
        assert second != first and Path(first).is_dir()


# Preflight and the worker are one startup lifetime. Repeated menu actions
# select the latest HIP intent rather than spawn a second frontend.
callbacks = []
with patch.object(dsh_launcher, '_dispatch_service_preflight', side_effect=callbacks.append), \
     patch.object(dsh_launcher, '_hip_dir', return_value=r'E:\before-preflight') as current_workspace, \
     patch.object(dsh_launcher, 'open_ui', return_value='fixture selected') as delayed_open, \
     patch.object(dsh_launcher, '_report'):
    dsh_launcher.open_workspace()
    current_workspace.return_value = r'E:\changed-during-preflight'
    callbacks[0]({'frontend_online': True, 'bridge_online': True}, None)
    delayed_open.assert_called_once_with(r'E:\changed-during-preflight')

worker_states = []
def startup_fixture(state):
    worker_states.append(state)
    with patch.object(dsh_launcher, '_hip_dir', return_value=r'E:\test51'):
        dsh_launcher.open_workspace()
        dsh_launcher.open_workspace()
    state.update(result='ready', detail='fixture ready')

with patch.object(dsh_launcher, '_hip_dir', return_value=r'E:\test49'), \
     patch.object(dsh_launcher, '_service_preflight', return_value={'frontend_online': False, 'bridge_online': True}), \
     patch.object(dsh_launcher.hou, 'isUIAvailable', return_value=False, create=True), \
     patch.object(dsh_launcher, '_start_and_wait_frontend', side_effect=startup_fixture), \
     patch.object(dsh_launcher, 'open_ui', return_value='fixture selected') as startup_open, \
     patch.object(dsh_launcher, '_report'):
    dsh_launcher.open_workspace()
    assert len(worker_states) == 1
    startup_open.assert_called_once_with(r'E:\test51', force_reload=True)
    assert dsh_launcher._ACTIVE_STARTUP is None
    assert dsh_launcher._SERVICE_PREFLIGHT_ACTIVE is False

# Closing the dialog is a cancellation intent. The same startup stays active
# until its worker exits, so its dependency/restart stages cannot race a retry.
canceled_state = {'canceled': True, 'worker_done': False}
with patch.object(dsh_launcher, '_ACTIVE_STARTUP', canceled_state):
    dsh_launcher._finish_startup(canceled_state)
    assert dsh_launcher._ACTIVE_STARTUP is canceled_state
    canceled_state['worker_done'] = True
    dsh_launcher._finish_startup(canceled_state)
    assert dsh_launcher._ACTIVE_STARTUP is None


# Startup checks one read-only native RPC. Session creation, preset selection and
# archive handling belong to the client navigation tests, not a Python mirror.
with patch.object(dsh_launcher, "_dsh_rpc_wire", return_value={"items": []}) as rpc:
    dsh_launcher._check_host_ready()
    rpc.assert_called_once_with("session/list", {"args": {"_request": {}}})
for detail in ("failed over HTTP 404: not found", "failed over HTTP 503: unavailable",
               "failed: gateway/bad-request: invalid request", "transport failed: offline"):
    failure = RuntimeError("DSH RPC session/list " + detail)
    with patch.object(dsh_launcher, "_dsh_rpc_wire", side_effect=failure) as rpc:
        try:
            dsh_launcher._check_host_ready()
        except RuntimeError as exc:
            assert exc is failure
        else:
            raise AssertionError("RPC failure was swallowed")
        assert rpc.call_count == 1
for invalid_items in (None, {}, "unknown"):
    with patch.object(dsh_launcher, "_dsh_rpc_wire", return_value={"items": invalid_items}):
        try:
            dsh_launcher._check_host_ready()
        except RuntimeError as exc:
            assert "session/list returned invalid items" in str(exc)
        else:
            raise AssertionError("invalid readiness response was accepted")


# Raising a healthy same-HIP page performs no auth, RPC or browser reload.
shown = []
webview = types.ModuleType('dsh_webview')
webview.raise_workspace = lambda path: True
webview.show_webview = lambda **kwargs: shown.append(kwargs) or "shown"
with patch.dict(sys.modules, {"dsh_webview": webview}), \
     patch.object(dsh_launcher._DSH_WEB_SESSION, "launch_url", side_effect=AssertionError("same-page auth")), \
     patch.object(dsh_launcher, "_dsh_rpc_wire", side_effect=AssertionError("same-page session IO")):
    assert dsh_launcher.open_ui(r"E:\fixture") == "Houdini workspace selection requested"
assert shown == []
with patch.dict(sys.modules, {"dsh_webview": webview}), \
     patch.object(dsh_launcher._DSH_WEB_SESSION, "launch_url", return_value="fixture-auth"):
    dsh_launcher.open_ui(r"E:\fixture", force_reload=True)
    webview.raise_workspace = lambda path: False
    dsh_launcher.open_ui(r"E:\different")
assert shown == [
    {"workspace_dir": r"E:\fixture", "authenticated_url": "fixture-auth", "force_reload": True},
    {"workspace_dir": r"E:\different", "authenticated_url": "fixture-auth", "force_reload": False},
]

# The normal menu path only opens an existing UI; presets are bundle declarations.
with patch.object(dsh_launcher, "_hip_dir", return_value=r"E:\fixture"), \
     patch.object(dsh_launcher, "_dispatch_service_preflight", side_effect=lambda callback: callback({
         "frontend_online": True, "bridge_online": True}, None)), \
     patch.object(dsh_launcher, "_report"), \
     patch.object(dsh_launcher, "open_ui", return_value="raised") as opened:
    dsh_launcher.open_workspace()
    opened.assert_called_once_with(r"E:\fixture")


# Real module resolution is the one dependency check. No restoration from a
# previous package manager's .ignored tree, no npm for syntax/runtime errors.
with patch.object(dsh_launcher, "_MANAGED", None), \
     patch.object(dsh_launcher.shutil, "move", side_effect=AssertionError("legacy package move")), \
     patch.object(dsh_launcher, "_append_dependency_failure"):
    with patch.object(dsh_launcher, "_plugin_runtime_probe", return_value=(True, "")), \
         patch.object(dsh_launcher.subprocess, "run", side_effect=AssertionError("unnecessary npm")):
        assert dsh_launcher.ensure_dependencies() == "dependencies ok"
    with patch.object(dsh_launcher, "_plugin_runtime_probe", return_value=(False, "SyntaxError: fixture")), \
         patch.object(dsh_launcher.subprocess, "run", side_effect=AssertionError("npm cannot repair code")):
        assert "FAILED" in dsh_launcher.ensure_dependencies()
    with patch.object(dsh_launcher, "_plugin_runtime_probe", side_effect=[(False, "ERR_MODULE_NOT_FOUND"), (True, "")]), \
         patch.object(dsh_launcher.subprocess, "run", return_value=types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")) as install:
        assert dsh_launcher.ensure_dependencies() == "dependencies restored"
        assert install.call_count == 1 and install.call_args.args[0].startswith("npm install ")
    with patch.object(dsh_launcher, "_MANAGED", {"fixture": True}), \
         patch.object(dsh_launcher, "_plugin_runtime_probe", return_value=(False, "ERR_MODULE_NOT_FOUND")), \
         patch.object(dsh_launcher.subprocess, "run", side_effect=AssertionError("managed npm")):
        assert "managed dependency check FAILED" in dsh_launcher.ensure_dependencies()


# Unknown listeners are conflicts, never permission to kill or reuse them.
with patch.object(dsh_launcher, "_port_open", return_value=True), \
     patch.object(dsh_launcher, "_port_pid", return_value=os.getpid()), \
     patch.object(dsh_launcher.dsh_managed_runtime, "owns_pid", return_value=True), \
     patch.object(dsh_launcher.dsh_managed_runtime, "stop_owned", side_effect=AssertionError("preflight must not stop processes")):
    assert dsh_launcher._service_preflight() == {"frontend_online": True, "bridge_online": True}

    for unknown_pid in (os.getpid() + 100, None):
        with patch.object(dsh_launcher, "_port_pid", return_value=unknown_pid):
            try:
                dsh_launcher._service_preflight()
            except RuntimeError as exc:
                assert "bridge port conflict" in str(exc)
            else:
                raise AssertionError("another or unidentified Houdini must not be reused")

    with patch.object(dsh_launcher.dsh_managed_runtime, "owns_pid", return_value=False):
        for operation in (dsh_launcher._service_preflight, dsh_launcher.restart_frontend,
                          dsh_launcher.start_frontend):
            try:
                operation()
            except RuntimeError as exc:
                assert "frontend port conflict" in str(exc)
            else:
                raise AssertionError("an unrelated frontend listener was reused or stopped")

# The real menu dispatch must surface conflicts before syncing/restarting anything.
for service in ("frontend", "bridge"):
    reports = []
    failure = RuntimeError(f"{service} port conflict: no external process was stopped")
    with patch.object(dsh_launcher, "_hip_dir", return_value=r"E:\fixture"), \
         patch.object(dsh_launcher, "_service_preflight", side_effect=failure), \
         patch.object(dsh_launcher, "_report", side_effect=reports.append), \
         patch.object(dsh_launcher, "restart_bridge", side_effect=AssertionError("conflict restarted bridge")), \
         patch.object(dsh_launcher, "open_ui_when_ready", side_effect=AssertionError("conflict started frontend")), \
         patch.object(dsh_launcher, "open_ui", side_effect=AssertionError("conflict opened frontend")):
        dsh_launcher.launch()
        dsh_launcher.open_workspace()
    assert len(reports) == 2 and all(str(failure) in message for message in reports), reports

with patch.object(dsh_launcher.dsh_managed_runtime, "stop_owned", return_value=False), \
     patch.object(dsh_launcher, "_clear_frontend_runtime_state", side_effect=AssertionError("unowned marker removed")):
    assert dsh_launcher._terminate_pending_frontend() is False

# UI cancellation captures its own Popen before queuing work, not the mutable
# _PENDING global. No process yet means flag cancellation without a stop request.
scheduled = []
class DelayedThread:
    def __init__(self, *, target, kwargs, daemon):
        self.target, self.kwargs = target, kwargs
    def start(self):
        scheduled.append((self.target, self.kwargs))

old_process, newer_process = object(), object()
with patch.object(dsh_launcher.threading, "Thread", DelayedThread), \
     patch.object(dsh_launcher, "_terminate_pending_frontend") as terminate, \
     patch.dict(dsh_launcher._PENDING, {}, clear=True):
    early = {}
    dsh_launcher._cancel_startup(early)
    assert early["canceled"] and scheduled == []
    prior = {"proc": old_process}
    dsh_launcher._cancel_startup(prior)
    dsh_launcher._cancel_startup(prior)
    dsh_launcher._PENDING["proc"] = newer_process
    for target, kwargs in scheduled:
        target(**kwargs)
    assert terminate.call_count == 2
    assert all(call.kwargs == {"expected_process": old_process} for call in terminate.call_args_list)

# Cancellation during dependency/profile work prevents a later spawn; if it
# arrives while spawn is publishing its handle, the worker stops that attempt.
for cancel_stage in ("dependencies", "profile", "spawn"):
    state = {"canceled": False, "result": None, "detail": "", "frontend_cwd": r"E:\fixture"}
    calls = []
    process = object()
    def stage(name):
        calls.append(name)
        if cancel_stage == name:
            dsh_launcher._cancel_startup(state)
        if name == "spawn":
            dsh_launcher._PENDING["proc"] = process
            state["proc"] = process
        return name + " ok"
    with patch.dict(dsh_launcher._PENDING, {}, clear=True), \
         patch.object(dsh_launcher, "ensure_dependencies", side_effect=lambda callback: stage("dependencies")), \
         patch.object(dsh_launcher, "restart_frontend", side_effect=lambda: stage("stop previous")), \
         patch.object(dsh_launcher, "sync_profile_plugins", side_effect=lambda callback: stage("profile")), \
         patch.object(dsh_launcher, "start_frontend", side_effect=lambda cwd, attempt: stage("spawn")), \
         patch.object(dsh_launcher, "_frontend_online", side_effect=AssertionError("cancelled startup polled")), \
         patch.object(dsh_launcher, "_terminate_pending_frontend") as terminate:
        dsh_launcher._start_and_wait_frontend(state)
    assert state["canceled"] and not state.get("error"), state
    if cancel_stage == "spawn":
        terminate.assert_called_once_with(expected_process=process)
    else:
        terminate.assert_not_called()
        assert "spawn" not in calls

# Exact publication race: GUI cleanup clears _PENDING and cancels while the
# process creator is returning. start_frontend must publish directly to state.
with tempfile.TemporaryDirectory(prefix="dsh-cancel-publication-") as temporary:
    state = {"canceled": False, "result": None, "detail": "", "frontend_cwd": temporary}
    process = object()
    def spawn_before_gui_cleanup(*args, **kwargs):
        assert kwargs['env']['DSH_HOUDINI_EXECUTOR_ID'] == dsh_launcher.dsh_managed_runtime.executor_identity()
        dsh_launcher._PENDING.clear()
        dsh_launcher._cancel_startup(state)
        return process
    with patch.dict(dsh_launcher._PENDING, {}, clear=True), \
         patch.object(dsh_launcher, "FRONTEND_LOG", str(Path(temporary) / "frontend.log")), \
         patch.object(dsh_launcher, "_frontend_online", return_value=False), \
         patch.object(dsh_launcher, "_frontend_command", return_value=(
             [dsh_launcher.NODE, str(Path(temporary) / "fixture.js"), "web", "--port", "3081", "--no-open"],
             False, "fixture-cli", 60)), \
         patch.object(dsh_launcher._DSH_WEB_SESSION, "reset"), \
         patch.object(dsh_launcher, "ensure_dependencies", return_value="dependencies ok"), \
         patch.object(dsh_launcher, "restart_frontend", return_value="frontend stopped"), \
         patch.object(dsh_launcher, "sync_profile_plugins", return_value="profile ok"), \
         patch.object(dsh_launcher.dsh_managed_runtime, "spawn_frontend", side_effect=spawn_before_gui_cleanup), \
         patch.object(dsh_launcher, "_terminate_pending_frontend") as terminate:
        dsh_launcher._start_and_wait_frontend(state)
    assert state["proc"] is process and state["canceled"] and not state.get("error"), state
    terminate.assert_called_once_with(expected_process=process)


print("launcher preflight regression passed")
