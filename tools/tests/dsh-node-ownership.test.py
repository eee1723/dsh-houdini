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
import dsh_hou_helpers


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

    # Undo resurrects a deleted node with its original id but recreates native
    # init-script children under fresh ids; the bridge must reconcile those
    # identities or the resurrected subtree stays foreign and undeletable.
    wrangle_result = dsh_bridge.run_code(
        f"g = tab_create('/obj', 'geo', name='undo_geo_{suffix}')\n"
        "w = tab_create(g, 'attribwrangle', name='undo_wrangle')\n"
        "__result__ = w.path()",
        owner_session=session_a,
        owner_call="call-create-wrangle",
    )
    assert wrangle_result["ok"] is True, wrangle_result
    wrangle_path = wrangle_result["result"]
    geo_path = hou.node(wrangle_path).parent().path()
    inner_before = hou.node(wrangle_path).allSubChildren(sync_delayed_definition=True)
    assert inner_before, "attribwrangle should carry a native inner VOP child"
    inner_id_before = int(inner_before[0].sessionId())

    failed_delete = dsh_bridge.run_code(
        f"delete_node({wrangle_path!r})\nraise RuntimeError('intentional wrangle rollback')",
        owner_session=session_a,
        owner_call="call-rollback-wrangle",
    )
    assert failed_delete["ok"] is False, failed_delete
    assert failed_delete["rollback"]["applied"] is True, failed_delete
    resurrected = hou.node(wrangle_path)
    assert resurrected is not None, failed_delete
    inner_after = resurrected.allSubChildren(sync_delayed_definition=True)
    assert inner_after, failed_delete
    if int(inner_after[0].sessionId()) != inner_id_before:
        assert inner_after[0].path() in failed_delete["rollback"].get("reconciled_resurrected_identities", []), failed_delete
    inner_prov = dsh_bridge.run_code(
        f"__result__ = node_provenance({inner_after[0].path()!r})",
        owner_session=session_a,
        owner_call="call-inner-provenance",
    )
    assert inner_prov["result"]["status"] == "owned_current_session", inner_prov
    cleanup = dsh_bridge.run_code(
        f"delete_node({wrangle_path!r})",
        owner_session=session_a,
        owner_call="call-delete-wrangle",
    )
    assert cleanup["ok"] is True, cleanup
    assert hou.node(wrangle_path) is None
    dsh_bridge.run_code(f"delete_node({geo_path!r})", owner_session=session_a)

    # Negative: a same-path replacement of a different node type (even under a
    # registered live ancestor) must never be adopted as the dead identity.
    wr = dsh_bridge.run_code(
        f"g2 = tab_create('/obj', 'geo', name='undo_geo2_{suffix}')\n"
        "w2 = tab_create(g2, 'attribwrangle', name='undo_wrangle2')\n"
        "__result__ = {'geo': g2.path(), 'wrangle': w2.path()}",
        owner_session=session_a,
        owner_call="call-create-wrangle2",
    )
    assert wr["ok"] is True, wr
    wrangle2_path = wr["result"]["wrangle"]
    geo2_path = wr["result"]["geo"]
    snapshot = dict(dsh_hou_helpers._OWNED_NODE_SESSIONS)
    gone = dsh_bridge.run_code(
        f"delete_node({wrangle2_path!r})",
        owner_session=session_a,
        owner_call="call-delete-wrangle2",
    )
    assert gone["ok"] is True and hou.node(wrangle2_path) is None, gone
    replacement = hou.node(geo2_path).createNode("box", "undo_wrangle2")
    assert replacement.type().name() != "attribwrangle"
    restored = dsh_hou_helpers._reconcile_undo_resurrected(snapshot)
    assert restored == [], restored
    assert int(replacement.sessionId()) not in dsh_hou_helpers._OWNED_NODE_SESSIONS, restored
    replacement.destroy()

    # Negative (cross-author): a same-path node registered by another session is
    # never re-registered under the dead identity's record.
    dsh_bridge.run_code(f"delete_node({geo2_path!r})", owner_session=session_a)
    bg = dsh_bridge.run_code(
        f"g3 = tab_create('/obj', 'geo', name='undo_geo2_{suffix}')\n"
        "w3 = tab_create(g3, 'attribwrangle', name='undo_wrangle2')\n"
        "__result__ = w3.path()",
        owner_session=session_b,
        owner_call="call-create-b",
    )
    assert bg["ok"] is True, bg
    b_wrangle_path = bg["result"]
    assert b_wrangle_path == wrangle2_path, (b_wrangle_path, wrangle2_path)
    b_id = int(hou.node(b_wrangle_path).sessionId())
    restored_b = dsh_hou_helpers._reconcile_undo_resurrected(snapshot)
    assert restored_b == [], restored_b
    assert b_id in dsh_hou_helpers._OWNED_NODE_SESSIONS, restored_b
    prov_b = dsh_bridge.run_code(
        f"__result__ = node_provenance({b_wrangle_path!r})",
        owner_session=session_b,
        owner_call="call-prov-b",
    )
    assert prov_b["result"]["status"] == "owned_current_session", prov_b
    b_geo_path = hou.node(b_wrangle_path).parent().path()
    dsh_bridge.run_code(f"delete_node({b_wrangle_path!r})", owner_session=session_b)
    dsh_bridge.run_code(f"delete_node({b_geo_path!r})", owner_session=session_b)

    # Negative (unrelated-failure rollback): a failing batch elsewhere removes
    # only its own created node and never reconciles unrelated identities.
    keep = dsh_bridge.run_code(
        f"gk = tab_create('/obj', 'geo', name='undo_keep_{suffix}')\n"
        "wk = tab_create(gk, 'attribwrangle', name='keep_wrangle')\n"
        "__result__ = wk.path()",
        owner_session=session_a,
        owner_call="call-create-keep",
    )
    assert keep["ok"] is True, keep
    keep_path = keep["result"]
    unrelated = dsh_bridge.run_code(
        f"g4 = tab_create('/obj', 'geo', name='undo_fail_{suffix}')\n"
        "w4 = tab_create(g4, 'attribwrangle', name='doomed')\n"
        "raise RuntimeError('intentional unrelated rollback')",
        owner_session=session_a,
        owner_call="call-unrelated-rollback",
    )
    assert unrelated["ok"] is False, unrelated
    assert unrelated["rollback"]["applied"] is True, unrelated
    assert unrelated["rollback"].get("reconciled_resurrected_identities") in (None, []), unrelated
    assert hou.node(keep_path) is not None, unrelated
    prov_keep = dsh_bridge.run_code(
        f"__result__ = node_provenance({keep_path!r})",
        owner_session=session_a,
        owner_call="call-prov-keep",
    )
    assert prov_keep["result"]["status"] == "owned_current_session", prov_keep
    keep_geo = hou.node(keep_path).parent().path()
    dsh_bridge.run_code(f"delete_node({keep_path!r})", owner_session=session_a)
    dsh_bridge.run_code(f"delete_node({keep_geo!r})", owner_session=session_a)

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
    # Repair reloads implementation, not the owning Houdini process. Preserve
    # exact runtime identities, never adopt nodes merely because paths match.
    import importlib
    import dsh_hou_helpers as helpers
    registry = helpers._OWNED_NODE_SESSIONS
    importlib.reload(helpers)
    assert helpers._OWNED_NODE_SESSIONS is registry
    same_owner = dsh_bridge.run_code(f'__result__=node_provenance({owned_path!r})', owner_session=session_a)
    assert same_owner['result']['status'] == 'owned_current_session', same_owner
    other_owner = dsh_bridge.run_code(f'__result__=node_provenance({owned_path!r})', owner_session=session_b)
    assert other_owner['result']['status'] == 'owned_other_session', other_owner

finally:
    # Test cleanup is outside a host-owned bridge execution on purpose; direct
    # Python-shell workflows remain permissive and do not redefine provenance.
    if parent_path:
        parent = hou.node(parent_path)
        if parent is not None:
            parent.destroy()

print("node ownership regression passed")
