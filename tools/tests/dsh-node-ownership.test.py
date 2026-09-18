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
    snapshot_now = {identity: (entry, entry.get('path_at_creation'))
                    for identity, entry in snapshot.items()}
    restored = dsh_hou_helpers._reconcile_undo_resurrected(snapshot_now)
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
    restored_b = dsh_hou_helpers._reconcile_undo_resurrected(snapshot_now)
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

    # Causal binding: adoption candidates come only from THIS batch's deletions.
    # A stale entry left behind by an earlier leaked deletion (destroy without
    # unregister) must never graft its author onto a later batch's resurrected
    # nodes — the reconcile serves each candidate first-come-first-served, so a
    # full-registry scan would let the oldest stale entry win the race. The
    # stale record below is seeded explicitly (dead id, exact future path,
    # recorded type, another session's authorship) to simulate that leak class
    # deterministically; everything after it runs through the real bridge.
    stale_id = 900000000 + int(suffix, 36) % 100000
    assert hou.nodeBySessionId(stale_id) is None and stale_id not in dsh_hou_helpers._OWNED_NODE_SESSIONS
    stale_path = f"/obj/causal_geo_{suffix}/causal_wrangle/attribvop1"
    dsh_hou_helpers._OWNED_NODE_SESSIONS[stale_id] = {
        "session": session_a, "call": "leaked-deletion-from-earlier-batch",
        "path_at_creation": stale_path, "type": "attribwranglecore",
    }
    same_paths = dsh_bridge.run_code(
        f"g = tab_create('/obj', 'geo', name='causal_geo_{suffix}')\n"
        "w = tab_create(g, 'attribwrangle', name='causal_wrangle')\n"
        "__result__ = {'geo': g.path(), 'wrangle': w.path()}",
        owner_session=session_b,
        owner_call="call-causal-create-b",
    )
    assert same_paths["ok"] is True, same_paths
    assert same_paths["result"]["geo"] == f"/obj/causal_geo_{suffix}", same_paths
    live_wrangle = same_paths["result"]["wrangle"]
    assert hou.node(live_wrangle).allSubChildren(sync_delayed_definition=True)[0].path() == stale_path, live_wrangle
    live_inner_id = int(hou.node(stale_path).sessionId())
    failed_causal = dsh_bridge.run_code(
        f"delete_node({live_wrangle!r})\nraise RuntimeError('causal binding rollback probe')",
        owner_session=session_b,
        owner_call="call-causal-rollback",
    )
    assert failed_causal["ok"] is False and failed_causal["rollback"]["applied"] is True, failed_causal
    resurrected_wrangle = hou.node(live_wrangle)
    assert resurrected_wrangle is not None, failed_causal
    resurrected_inner = resurrected_wrangle.allSubChildren(sync_delayed_definition=True)[0]
    if int(resurrected_inner.sessionId()) != live_inner_id:
        # Fresh-id recreation: the causal-binding regime. The resurrected child
        # must be adopted only from THIS batch's deletion (session b's entry),
        # never from the stale entry poisoned by session a's earlier leak.
        assert resurrected_inner.path() in failed_causal["rollback"].get("reconciled_resurrected_identities", []), failed_causal
        causal_prov = dsh_bridge.run_code(
            f"__result__ = node_provenance({resurrected_inner.path()!r})",
            owner_session=session_b,
            owner_call="call-causal-prov",
        )
        assert causal_prov["result"]["status"] == "owned_current_session", causal_prov
        assert causal_prov["result"]["runtime_owner"]["session"] == session_b, causal_prov
    else:
        raise AssertionError('this Houdini build resurrects the inner child with its original id; '
                             'the causal-binding fresh-id scenario is not exercisable here')
    causal_cleanup = dsh_bridge.run_code(f"delete_node({same_paths['result']['geo']!r})", owner_session=session_b,
                                         owner_call="call-causal-cleanup")
    assert causal_cleanup["ok"] is True, causal_cleanup
    dsh_hou_helpers._OWNED_NODE_SESSIONS.pop(stale_id, None)  # purge the injected poison

    # Rename + user node at the old creation path + undo: adoption must locate
    # candidates by the batch-start path, never by path_at_creation (audit-only).
    renamed = dsh_bridge.run_code(
        f"g = tab_create('/obj', 'geo', name='rename_geo_{suffix}')\n"
        "w = tab_create(g, 'attribwrangle', name='part')\n"
        "__result__ = {'geo': g.path(), 'wrangle': w.path()}",
        owner_session=session_b,
        owner_call="call-rename-create",
    )
    assert renamed["ok"] is True, renamed
    rename_geo, part_path = renamed["result"]["geo"], renamed["result"]["wrangle"]
    renamed_path = run_rename = dsh_bridge.run_code(
        f"__result__ = rename_node({part_path!r}, 'renamed')",
        owner_session=session_b,
        owner_call="call-rename",
    )
    assert run_rename["ok"] is True and run_rename["result"] == f"/obj/rename_geo_{suffix}/renamed", run_rename
    # The user rebuilds a same-type node at the OLD creation path (outside any
    # session: direct native creation, unregistered, foreign to every author).
    user_node = hou.node(rename_geo).createNode("attribwrangle", "part")
    assert user_node.path() == part_path, user_node.path()
    user_inner = user_node.allSubChildren(sync_delayed_definition=True)[0]
    failed_rename_batch = dsh_bridge.run_code(
        f"delete_node('/obj/rename_geo_{suffix}/renamed')\nraise RuntimeError('rename rollback probe')",
        owner_session=session_b,
        owner_call="call-rename-rollback",
    )
    assert failed_rename_batch["ok"] is False and failed_rename_batch["rollback"]["applied"] is True, failed_rename_batch
    # The user's node is never claimed by any session.
    user_prov = dsh_bridge.run_code(
        f"__result__ = node_provenance({user_node.path()!r})",
        owner_session=session_b,
        owner_call="call-user-prov",
    )
    assert user_prov["result"]["status"] == "foreign", user_prov
    assert dsh_bridge.run_code(
        f"delete_node({user_node.path()!r})", owner_session=session_b,
        owner_call="call-user-delete")["ok"] is False, 'a foreign user node must stay undeletable by the author'
    # The REAL resurrected node (at its renamed path) and its fresh-id inner are
    # the adopted identities; the fresh-id regime is asserted explicitly.
    resurrected_renamed = hou.node(f"/obj/rename_geo_{suffix}/renamed")
    assert resurrected_renamed is not None, failed_rename_batch
    renamed_prov = dsh_bridge.run_code(
        f"__result__ = node_provenance('/obj/rename_geo_{suffix}/renamed')",
        owner_session=session_b,
        owner_call="call-renamed-prov",
    )
    assert renamed_prov["result"]["status"] == "owned_current_session", renamed_prov
    fresh_inner = resurrected_renamed.allSubChildren(sync_delayed_definition=True)[0]
    if int(fresh_inner.sessionId()) != int(hou.node(f"/obj/rename_geo_{suffix}/part/attribvop1").sessionId()):
        inner_prov = dsh_bridge.run_code(
            f"__result__ = node_provenance({fresh_inner.path()!r})",
            owner_session=session_b,
            owner_call="call-fresh-inner-prov",
        )
        assert inner_prov["result"]["status"] == "owned_current_session", inner_prov
        assert inner_prov["result"]["runtime_owner"]["session"] == session_b, inner_prov
    # Cleanup: the author removes its own subtree; the user node is removed the
    # same way it arrived (directly, outside any session).
    assert dsh_bridge.run_code(f"delete_node('/obj/rename_geo_{suffix}/renamed')",
                               owner_session=session_b, owner_call="call-rename-cleanup")["ok"] is True
    user_node.destroy()
    assert dsh_bridge.run_code(f"delete_node({rename_geo!r})", owner_session=session_b,
                               owner_call="call-rename-geo-cleanup")["ok"] is True

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
