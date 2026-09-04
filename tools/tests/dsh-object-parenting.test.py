"""H21/H22 regression: explicit OBJ parenting is semantic and audited."""

from __future__ import annotations

from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

import hou
import dsh_bridge


suffix = uuid.uuid4().hex[:8]
session = f"object-parenting-{suffix}"
paths = []
foreign_child = None


def run(code, call):
    return dsh_bridge.run_code(
        code,
        owner_session=session,
        owner_call=f"object-parenting-{call}",
    )


try:
    help_result = run("__result__ = verb_help('set_object_parent')", "help")
    assert help_result["ok"] is True, help_result
    assert "child" in help_result["result"]["signature"], help_result
    assert "reason" in help_result["result"]["signature"], help_result

    created = run(
        "parent = tab_create('/obj', 'null', name='__dsh_parent_" + suffix + "')\n"
        "child = tab_create('/obj', 'geo', name='__dsh_child_" + suffix + "')\n"
        "set_parms(parent, {'tx': 10.0, 'ry': 30.0})\n"
        "set_parms(child, {'tx': 2.0, 'ty': 3.0})\n"
        "__result__ = {'parent': parent.path(), 'child': child.path()}",
        "create",
    )
    assert created["ok"] is True, created
    parent_path = created["result"]["parent"]
    child_path = created["result"]["child"]
    paths.extend([child_path, parent_path])

    world_before = tuple(hou.node(child_path).worldTransform().asTuple())

    generic = run(
        f"connect({parent_path!r}, {child_path!r})",
        "generic-refused",
    )
    assert generic["ok"] is False, generic
    assert "set_object_parent" in generic["error"], generic
    assert hou.node(child_path).input(0) is None

    missing_reason = run(
        f"set_object_parent({child_path!r}, {parent_path!r})",
        "reason-refused",
    )
    assert missing_reason["ok"] is False, missing_reason
    assert "reason" in missing_reason["error"], missing_reason
    assert hou.node(child_path).input(0) is None

    parented = run(
        f"__result__ = set_object_parent({child_path!r}, {parent_path!r}, "
        "keep_world=True, reason='scene_assembly')",
        "parent",
    )
    assert parented["ok"] is True, parented
    result = parented["result"]
    assert result["child"] == child_path, result
    assert result["parent"] == parent_path, result
    assert result["verified"] is True, result
    assert result["world_transform_preserved"] is True, result
    assert result["world_delta_max"] <= 1e-6, result
    assert hou.node(child_path).input(0).path() == parent_path
    world_after = tuple(hou.node(child_path).worldTransform().asTuple())
    assert max(abs(a - b) for a, b in zip(world_before, world_after)) <= 1e-6

    cycle = run(
        f"set_object_parent({parent_path!r}, {child_path!r}, "
        "reason='scene_assembly')",
        "cycle-refused",
    )
    assert cycle["ok"] is False, cycle
    assert "形成环" in cycle["error"], cycle

    generic_unparent = run(
        f"disconnect_input({child_path!r}, 0)",
        "generic-unparent-refused",
    )
    assert generic_unparent["ok"] is False, generic_unparent
    assert "set_object_parent" in generic_unparent["error"], generic_unparent
    assert hou.node(child_path).input(0).path() == parent_path

    unparented = run(
        f"__result__ = set_object_parent({child_path!r}, None, "
        "keep_world=True, reason='scene_assembly')",
        "unparent",
    )
    assert unparented["ok"] is True, unparented
    assert unparented["result"]["parent"] is None, unparented
    assert unparented["result"]["previous_parent"] == parent_path, unparented
    assert unparented["result"]["world_transform_preserved"] is True, unparented
    assert hou.node(child_path).input(0) is None

    # A user-created child remains inspectable but needs the existing one-call
    # ownership exemption even when the parent is an agent-owned source.
    foreign_child = hou.node("/obj").createNode("geo", f"__dsh_foreign_child_{suffix}")
    foreign_path = foreign_child.path()
    foreign_refused = run(
        f"set_object_parent({foreign_path!r}, {parent_path!r}, "
        "reason='explicit_user')",
        "foreign-refused",
    )
    assert foreign_refused["ok"] is False, foreign_refused
    assert "ownership guard" in foreign_refused["error"], foreign_refused
    assert foreign_child.input(0) is None

    foreign_authorized = run(
        f"__result__ = set_object_parent({foreign_path!r}, {parent_path!r}, "
        "reason='explicit_user', "
        "allow_foreign='user explicitly requested parenting this object')",
        "foreign-authorized",
    )
    assert foreign_authorized["ok"] is True, foreign_authorized
    assert "[ownership] foreign-node exemption" in foreign_authorized["stdout"], foreign_authorized
    assert foreign_child.input(0).path() == parent_path

    print("object parenting regression: ok")
finally:
    if foreign_child is not None:
        foreign_child.destroy()
    for path in paths:
        node = hou.node(path)
        if node is not None:
            node.destroy()
