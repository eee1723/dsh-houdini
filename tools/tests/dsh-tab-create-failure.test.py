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
    missing = dsh_bridge.run_code(
        f"tab_create({parent.path()!r}, 'null', inputs=['missing'])",
        owner_session="tab-create-failure-test", owner_call="call-preflight")
    assert not missing['ok'] and missing['transaction']['status']=='no_scene_change', missing
    assert missing['verbs'][0]['summary']['phase']=='preflight', missing
    assert missing['verbs'][0]['summary']['scene_writes']==0, missing
    dsh_hou_helpers._run_shelf_tool = original
    relative = dsh_bridge.run_code(
        f"p=hou.node({parent.path()!r})\na=tab_create(p,'box',name='source')\n"
        "b=tab_create(p,'null',name='out',inputs=['source'])\n"
        "__result__=verify_network(p,output='out',nodes=['source','out'])",
        owner_session="tab-create-failure-test", owner_call="call-relative")
    assert relative['ok'] and relative['result']['ok'], relative
    assert parent.node('out').input(0)==parent.node('source')
    not_network = dsh_bridge.run_code(
        f"tab_create({parent.node('out').path()!r}, 'box', name='invalid_child')",
        owner_session="tab-create-failure-test", owner_call="call-leaf-parent")
    assert not not_network['ok'], not_network
    assert 'is not a network that can create nodes' in not_network['error'], not_network
    assert repr(parent.path()) in not_network['error'], not_network
    assert not_network['verbs'][0]['summary']['scene_writes'] == 0, not_network
    assert not_network['transaction']['status'] == 'no_scene_change', not_network
finally:
    dsh_hou_helpers._run_shelf_tool = original
    if parent is not None:
        parent.destroy()

print("tab_create failure regression passed")
