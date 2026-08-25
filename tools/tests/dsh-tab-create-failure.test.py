"""A failed semantic Tab creation must not degrade to bare createNode.

Run with Houdini's hython. The injected failure simulates a SideFX shelf tool
that creates one partial node and then raises.
"""

from __future__ import annotations

from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

import hou
import dsh_bridge
import dsh_hou_helpers


parent = hou.node("/obj").createNode("geo", f"__dsh_tab_failure_{uuid.uuid4().hex[:8]}")
original = dsh_hou_helpers._run_shelf_tool


def fail_after_partial_create(tool, target, type_name):
    target.createNode("null", "partial_from_failed_tool")
    raise RuntimeError("synthetic shelf initialization failure")


try:
    dsh_hou_helpers._run_shelf_tool = fail_after_partial_create
    outcome = dsh_bridge.run_code(
        f"tab_create({parent.path()!r}, 'copytopoints')",
        owner_session="tab-create-failure-test",
        owner_call="call-create",
    )
    assert outcome["ok"] is False, outcome
    assert "synthetic shelf initialization failure" in outcome["error"], outcome
    assert parent.children() == (), [child.path() for child in parent.children()]
finally:
    dsh_hou_helpers._run_shelf_tool = original
    if parent is not None:
        parent.destroy()

print("tab_create failure regression passed")
