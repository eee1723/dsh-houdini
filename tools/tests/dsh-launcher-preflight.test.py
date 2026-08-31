"""Pure regression for launcher listener preflight and external-process policy."""

from __future__ import annotations

from pathlib import Path
import os
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

import dsh_launcher


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
