"""Pure regression for launcher listener preflight and external-process policy."""

from __future__ import annotations

from pathlib import Path
import os
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

import dsh_launcher


# DSH 0.1.2 session rows project agentPreset instead of duplicating it at the
# row root. Both wire generations must select the same newest Houdini session.
selected = dsh_launcher._select_houdini_session([
    {
        "sessionId": "older", "cwd": r"E:\fixture", "updatedAt": 1,
        "agentPreset": "houdini",
    },
    {
        "sessionId": "modern", "cwd": r"E:\fixture", "updatedAt": 2,
        "projections": {"values": {"agentPreset": "houdini"}},
    },
], r"E:\fixture")
assert selected is not None and selected["sessionId"] == "modern", selected


original_rpc = dsh_launcher._dsh_rpc
original_wire = dsh_launcher._dsh_rpc_wire
try:
    calls = []

    def legacy_missing(method, payload, timeout=dsh_launcher.DSH_RPC_TIMEOUT):
        calls.append((method, payload))
        raise RuntimeError(f"DSH RPC {method} failed over HTTP 404: not found")

    def modern(method, payload, timeout=dsh_launcher.DSH_RPC_TIMEOUT):
        calls.append((method, payload))
        if method == "workspace/create":
            return {"workspace": {
                "workspaceId": "workspace-modern",
                "path": r"E:\modern-workspace",
                "sessionIds": [],
            }, "created": True}
        if method == "session/list":
            return {"items": []}
        if method == "session/create":
            return {"sessionId": "created-modern", "agentPreset": "houdini"}
        raise AssertionError(method)

    dsh_launcher._dsh_rpc = legacy_missing
    dsh_launcher._dsh_rpc_wire = modern
    session_id, _status = dsh_launcher.ensure_houdini_session(r"E:\modern-workspace")
    assert session_id == "created-modern"
    assert calls == [
        ("session.list", {}),
        ("workspace/create", {"args": {"request": {"path": r"E:\modern-workspace"}}}),
        ("session/list", {"args": {"_request": {}}}),
        ("session/create", {"args": {"request": {
            "workspaceId": "workspace-modern", "agentPreset": "houdini",
        }}}),
    ], calls
finally:
    dsh_launcher._dsh_rpc = original_rpc
    dsh_launcher._dsh_rpc_wire = original_wire


original_port_open = dsh_launcher._port_open
original_port_pid = dsh_launcher._port_pid
original_kill = dsh_launcher._kill_port_process
try:
    dsh_launcher._port_open = lambda _host, _port: True
    dsh_launcher._port_pid = lambda _port: os.getpid() + 100
    killed = []
    dsh_launcher._kill_port_process = lambda port: killed.append(port) or True

    ordinary = dsh_launcher._service_preflight(clear_external_bridge=False)
    assert ordinary["frontend_online"] is True
    assert ordinary["bridge_online"] is True
    assert ordinary["external_bridge_cleared"] is False
    assert killed == [], "Open Workspace preflight must preserve an existing listener"

    repair = dsh_launcher._service_preflight(clear_external_bridge=True)
    assert repair["bridge_online"] is False
    assert repair["external_bridge_cleared"] is True
    assert killed == [dsh_launcher.BRIDGE_PORT]
finally:
    dsh_launcher._port_open = original_port_open
    dsh_launcher._port_pid = original_port_pid
    dsh_launcher._kill_port_process = original_kill


print("launcher preflight regression passed")
