"""Runtime regression for task-scoped node provenance and mutation guards.

Run with Houdini's hython.  The direct ``hou`` calls below simulate user edits
made between agent tool calls; bridge executions themselves use verbs only.
"""

from __future__ import annotations

from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

import hou
import dsh_bridge


suffix = uuid.uuid4().hex[:8]
session_a = f"ownership-a-{suffix}"
session_b = f"ownership-b-{suffix}"
parent_path = None
foreign = None

try:
    created = dsh_bridge.run_code(
        "parent = tab_create('/obj', 'subnet', name='__dsh_owner_parent_"
        + suffix
        + "')\n"
        "owned = tab_create(parent, 'null', name='agent_owned')\n"
        "__result__ = {'parent': parent.path(), 'owned': owned.path()}",
        owner_session=session_a,
        owner_call="call-create",
    )
    assert created["ok"] is True, created
    parent_path = created["result"]["parent"]
    owned_path = created["result"]["owned"]
    parent = hou.node(parent_path)
    owned = hou.node(owned_path)
    assert parent is not None and owned is not None

    # Undo restores Houdini nodes; the bridge must restore its process-local
    # ownership registry in the same transaction.
    rolled_back = dsh_bridge.run_code(
        f"delete_node({owned_path!r})\nraise RuntimeError('intentional ownership rollback')",
        owner_session=session_a,
        owner_call="call-rollback",
    )
    assert rolled_back["ok"] is False, rolled_back
    assert rolled_back["rollback"]["applied"] is True, rolled_back
    owned = hou.node(owned_path)
    assert owned is not None, rolled_back
    restored_owner = dsh_bridge.run_code(
        f"__result__ = node_provenance({owned_path!r})",
        owner_session=session_a,
        owner_call="call-after-rollback",
    )
    assert restored_owner["ok"] is True, restored_owner
    assert restored_owner["result"]["status"] == "owned_current_session", restored_owner

    # Simulate a user-created/copied node.  Even a copied/forged durable tag is
    # audit metadata only; a fresh Houdini sessionId is not runtime-owned.
    foreign = parent.createNode("null", "copytopoints2")
    foreign.setUserData("dsh_houdini_task_owner", session_a)
    foreign.setPosition(hou.Vector2(19.0, 7.0))
    foreign_path = foreign.path()
    foreign_position = tuple(float(v) for v in foreign.position())

    inspected = dsh_bridge.run_code(
        f"__result__ = node_provenance({foreign_path!r})",
        owner_session=session_a,
        owner_call="call-inspect",
    )
    assert inspected["ok"] is True, inspected
    assert inspected["result"]["status"] == "foreign", inspected
    assert inspected["result"]["audit_owner_session"] == session_a, inspected
    assert inspected["result"]["writable"] is False, inspected

    laid_out = dsh_bridge.run_code(
        f"__result__ = layout_nodes({parent_path!r})",
        owner_session=session_a,
        owner_call="call-layout",
    )
    assert laid_out["ok"] is True, laid_out
    assert foreign_path in laid_out["result"]["foreign_nodes_skipped"], laid_out
    assert tuple(float(v) for v in foreign.position()) == foreign_position, laid_out

    refused = dsh_bridge.run_code(
        f"rename_node({foreign_path!r}, 'must_not_change')",
        owner_session=session_a,
        owner_call="call-refuse",
    )
    assert refused["ok"] is False, refused
    assert "ownership guard" in refused["error"], refused["error"]
    assert foreign.name() == "copytopoints2"

    other_session = dsh_bridge.run_code(
        f"__result__ = node_provenance({owned_path!r})",
        owner_session=session_b,
        owner_call="call-other-session",
    )
    assert other_session["ok"] is True, other_session
    assert other_session["result"]["status"] == "owned_other_session", other_session
    assert other_session["result"]["writable"] is False, other_session

    authorized = dsh_bridge.run_code(
        f"__result__ = rename_node({foreign_path!r}, 'user_authorized', "
        "allow_foreign='user explicitly requested this node')",
        owner_session=session_a,
        owner_call="call-authorized",
    )
    assert authorized["ok"] is True, authorized
    assert "[ownership] foreign-node exemption" in authorized["stdout"], authorized
    foreign = hou.node(authorized["result"])
    assert foreign is not None and foreign.name() == "user_authorized"

finally:
    # Test cleanup is outside a host-owned bridge execution on purpose; direct
    # Python-shell workflows remain permissive and do not redefine provenance.
    if parent_path:
        parent = hou.node(parent_path)
        if parent is not None:
            parent.destroy()

print("node ownership regression passed")
