"""Houdini request execution: verb dispatch, undo transaction and scene facts.

The Bridge schedules this runtime on Houdini's owning thread. There is no HTTP,
job registry or background HOM work here.
"""
from __future__ import annotations

import contextlib
from copy import deepcopy
import difflib
import inspect
import json
import os
from pathlib import Path
import threading
import time
import traceback
import uuid

import hou
import dsh_hou_helpers
import dsh_component_contracts
import dsh_network_boxes
from dsh_code_analysis import CodeAnalysis, _raw_hou_advisory, _repo_write_advisory
from dsh_execution_results import (
    _MAX_STREAM_BYTES, _CappedStringIO, _jsonable,
    _clip, _operation_summary, project_result,
)

# Cache the actual callable, not only its name, so repair/reload and test
# replacements obtain their own precise argument signature.
_VERB_SIGNATURES = {}
_VERB_OPERATION_CONTRACTS = None


def _verb_signature(name, fn):
    cached = _VERB_SIGNATURES.get(name)
    if cached is not None and cached[0] is fn:
        return cached[1]
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        signature = None
    _VERB_SIGNATURES[name] = (fn, signature)
    return signature


def _verb_help(name: str | list[str] | tuple[str, ...], detail: str = 'brief') -> dict:
    """Read callable signatures and brief purpose; detail='full' adds complete docs/contracts.

    name may be one verb or a list of 1..16 unique names. Both forms default to
    brief help. Full help includes maintained input/output schemas and examples;
    these are discovery metadata, not execution validation.
    """
    if detail not in ('brief', 'full'):
        raise ValueError("detail must be 'brief' or 'full'; e.g. verb_help('build_module', detail='full')")
    registry = _VERBS
    if isinstance(name, (list, tuple)):
        if not 1 <= len(name) <= 16:
            raise ValueError("name 列表必须包含 1..16 个动词名")
        if any(not isinstance(item, str) or not item.strip() for item in name):
            raise ValueError("name 列表中的每项都必须是非空动词名")
        keys = [item.strip() for item in name]
        if len(set(keys)) != len(keys):
            raise ValueError("name 列表中的动词名必须唯一")
        return {"items": [_verb_help(key, detail=detail) for key in keys], "count": len(keys)}
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name 必须是非空动词名或 1..16 项名称列表")
    key = name.strip()
    fn = registry.get(key)
    if fn is None:
        suggestions = difflib.get_close_matches(key, sorted(registry), n=8, cutoff=0.35)
        raise ValueError(f"未知动词 {key!r}；相似动词：{suggestions}")
    inspected = _verb_signature(key, fn)
    signature = str(inspected) if inspected is not None else None
    returns = inspected.return_annotation if inspected is not None else inspect.Signature.empty
    return_type = None if returns is inspect.Signature.empty else inspect.formatannotation(returns)
    doc = inspect.getdoc(fn) or ''
    result = {
        "name": key,
        "signature": signature,
        "return_type": return_type,
        "call_mode": "exec" if key in _MUTATING_VERB_NAMES else "query_or_exec",
        "detail": detail,
        "doc": doc,
    }
    global _VERB_OPERATION_CONTRACTS
    if _VERB_OPERATION_CONTRACTS is None:
        source = Path(__file__).resolve().parent.parent / 'verb-operation-contracts.json'
        _VERB_OPERATION_CONTRACTS = json.loads(source.read_text(encoding='utf8'))
    contract = _VERB_OPERATION_CONTRACTS['verbs'].get(key)
    if detail == 'brief':
        # Use the maintained concise purpose where available; keep doc readable
        # for existing consumers that print it, without shipping entire schemas.
        result['doc'] = contract['summary'] if contract else doc.split('\n', 1)[0]
        result['full_help'] = f'verb_help({key!r}, detail="full")'
    elif contract is not None:
        result['operation_contract'] = {
            'schema_version': _VERB_OPERATION_CONTRACTS['schema_version'],
            'schema_scope': _VERB_OPERATION_CONTRACTS['schema_scope'],
            'execution_scope': _VERB_OPERATION_CONTRACTS['execution_scope'],
            **deepcopy(contract),
        }
    return result


_VERBS: dict[str, object] = {
    "component_export": dsh_component_contracts.component_export,
    "component_import": dsh_component_contracts.component_import,
    "component_replace": dsh_component_contracts.component_replace,
    "package_info": dsh_hou_helpers.package_info,
    "verb_help": _verb_help,
    "scene_info": dsh_hou_helpers.scene_info,
    "scene_save": dsh_hou_helpers.scene_save,
    "scene_save_as": dsh_hou_helpers.scene_save_as,
    "set_timeline": dsh_hou_helpers.set_timeline,
    "list_bookmarks": dsh_hou_helpers.list_bookmarks,
    "create_bookmark": dsh_hou_helpers.create_bookmark,
    "delete_bookmark": dsh_hou_helpers.delete_bookmark,
    "search_tab_menu": dsh_hou_helpers.search_tab_menu,
    "search_tab_entries": dsh_hou_helpers.search_tab_entries,
    "resolve_latest_type": dsh_hou_helpers.resolve_latest_type,
    "tab_create": dsh_hou_helpers.tab_create,
    "node_info": dsh_hou_helpers.node_info,
    "build_module": dsh_hou_helpers.build_module,
    "verify_network": dsh_hou_helpers.verify_network,
    "tab_apply": dsh_hou_helpers.tab_apply,
    "find_nodes": dsh_hou_helpers.find_nodes,
    "graph": dsh_hou_helpers.graph,
    "describe": dsh_hou_helpers.describe,
    "node_provenance": dsh_hou_helpers.node_provenance,
    "connect": dsh_hou_helpers.connect,
    "set_object_parent": dsh_hou_helpers.set_object_parent,
    "disconnect_input": dsh_hou_helpers.disconnect_input,
    "rename_node": dsh_hou_helpers.rename_node,
    "delete_node": dsh_hou_helpers.delete_node,
    "cook_node": dsh_hou_helpers.cook_node,
    "set_update_mode": dsh_hou_helpers.set_update_mode,
    "sop_set_output": dsh_hou_helpers.sop_set_output,
    "sop_output_node": dsh_hou_helpers.sop_output_node,
    "set_object_visible": dsh_hou_helpers.set_object_visible,
    "visible_objects": dsh_hou_helpers.visible_objects,
    "layout_nodes": dsh_hou_helpers.layout_nodes,
    "network_boxes": dsh_hou_helpers.network_boxes,
    "list_parms": dsh_hou_helpers.list_parms,
    "read_parms": dsh_hou_helpers.read_parms,
    "set_parm": dsh_hou_helpers.set_parm,
    "set_parms": dsh_hou_helpers.set_parms,
    "set_keyframes": dsh_hou_helpers.set_keyframes,
    "create_spare_parms": dsh_hou_helpers.create_spare_parms,
    "parameter_ui": dsh_hou_helpers.parameter_ui,
    "bind_controls": dsh_hou_helpers.bind_controls,
    "hda_create": dsh_hou_helpers.hda_create,
    "hda_edit": dsh_hou_helpers.hda_edit,
    "hda_get_section": dsh_hou_helpers.hda_get_section,
    "hda_set_section": dsh_hou_helpers.hda_set_section,
    "hda_patch_section": dsh_hou_helpers.hda_patch_section,
    "hda_set_interface": dsh_hou_helpers.hda_set_interface,
    "geo_attrib_stats": dsh_hou_helpers.geo_attrib_stats,
    "geo_point_spacing": dsh_hou_helpers.geo_point_spacing,
    "geo_check_interfaces": dsh_hou_helpers.geo_check_interfaces,
    "test_controls": dsh_hou_helpers.test_controls,
    "sop_recipe": dsh_hou_helpers.sop_recipe,
    "modeling_dimensions": dsh_hou_helpers.modeling_dimensions,
    "control_test_plan": dsh_hou_helpers.control_test_plan,
    "cop_layer_stats": dsh_hou_helpers.cop_layer_stats,
    "cop_compare_layers": dsh_hou_helpers.cop_compare_layers,
    "test_cop_controls": dsh_hou_helpers.test_cop_controls,
    "geo_piece_stats": dsh_hou_helpers.geo_piece_stats,
    "geo_frame_diff": dsh_hou_helpers.geo_frame_diff,
    "usd_stage_summary": dsh_hou_helpers.usd_stage_summary,
    "usd_prim_info": dsh_hou_helpers.usd_prim_info,
    "render_frame": dsh_hou_helpers.render_frame,
    "camera_fit": dsh_hou_helpers.camera_fit,
    "render_check": dsh_hou_helpers.render_check,
    "render_view": dsh_hou_helpers.render_view,
    "viewport_screenshot": dsh_hou_helpers.viewport_screenshot,
}


_MUTATING_VERB_NAMES = {
    "component_export", "component_import", "component_replace",
    "cop_layer_stats", "cop_compare_layers", "test_cop_controls",
    "scene_save", "scene_save_as", "build_module", "verify_network", "test_controls", "set_timeline", "create_bookmark", "delete_bookmark",
    "tab_create", "tab_apply", "connect", "set_object_parent", "disconnect_input", "rename_node",
    "delete_node", "cook_node", "sop_set_output",
    "set_object_visible", "layout_nodes", "network_boxes", "set_parm", "set_parms",
    "set_keyframes", "create_spare_parms", "hda_create", "hda_set_section",
    "hda_patch_section", "hda_set_interface", "hda_edit", "render_frame", "render_view",
    "viewport_screenshot", "camera_fit", "bind_controls", "set_update_mode",
}


_OBSERVATION_VERBS = {'cop_layer_stats', 'cop_compare_layers', 'test_cop_controls', 'scene_save', 'create_bookmark', 'delete_bookmark', 'layout_nodes', 'network_boxes',
    'cook_node', 'verify_network', 'test_controls', 'render_frame', 'render_view', 'viewport_screenshot'}


_GLOBAL_EDIT_VERBS = {'set_timeline', 'set_update_mode', 'scene_save_as', 'hda_create', 'hda_set_section', 'bind_controls',
                     'hda_patch_section', 'hda_set_interface', 'hda_edit'}


def _observe_impact(nodes, impact, descendants=False):
    """No cook: bounded native wire/expression references, before and after edits.

    HOM dependents are based on last cook and cannot prove all dynamic/external
    dependencies. This is an invalidation hint, never an unaffected-scene proof.
    """
    pending = list(nodes)
    seen = set()
    while pending:
        if len(impact['nodes']) >= 256 or len(seen) >= 256:
            impact['truncated'] = True
            break
        node = pending.pop()
        try:
            identity = node.sessionId()
            if identity in seen:
                continue
            seen.add(identity)
            impact['nodes'][identity] = node.path()
            pending.extend(node.outputs())
            pending.extend(node.dependents(include_children=False))
            if descendants and node.isNetwork():
                pending.extend(node.children())
        except Exception:
            impact['unavailable'] = True


def _verb_value(value, _depth: int = 0):
    """把动词的入参/出参转成紧凑 JSON 安全形式（hou.Node → path，逐层递归）。"""
    if _depth > 8:
        return repr(value)
    if isinstance(value, hou.Node):
        try:
            return {"node": value.path()}
        except Exception:
            return {"node": repr(value)}
    if isinstance(value, (hou.Vector2, hou.Vector3, hou.Vector4)):
        return [_jsonable(float(x)) for x in value]
    if isinstance(value, hou.Color):
        return [_jsonable(float(x)) for x in (
            value.r(), value.g(), value.b(), value.a(),
        )]
    if isinstance(value, (hou.Matrix3, hou.Matrix4)):
        return [[_jsonable(float(x)) for x in row] for row in value]
    if isinstance(value, (list, tuple)):
        if len(value) > 50:
            return repr(value)
        return [_verb_value(v, _depth + 1) for v in value]
    if isinstance(value, dict):
        if len(value) > 50:
            return repr(value)
        return {str(k): _verb_value(v, _depth + 1) for k, v in value.items()}
    return _jsonable(value)


class _DispatchBlockedError(RuntimeError):
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = evidence


class _VerbArgumentError(TypeError):
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = evidence


def _unrecovered_mutation(entry):
    """Only a failed dispatched write without recovery evidence poisons a batch."""
    if entry.get('ok') or entry.get('verb') not in _MUTATING_VERB_NAMES:
        return False
    facts = entry.get('summary') or {}
    restored = facts.get('restored', facts.get('batch_parameter_state_restored',
                                               facts.get('parameter_state_restored')))
    return facts.get('scene_writes') != 0 and restored is not True


def _make_tracer(name: str, fn, ledger: list, observed_nodes=None, impact=None):
    # Give a precise, zero-write recovery path for repeated discovery mistakes;
    # do not label TypeErrors raised inside the implementation as argument errors.
    discovery_signature = _verb_signature(name, fn)
    def wrapped(*args, **kwargs):
        if observed_nodes is not None and (name in _MUTATING_VERB_NAMES or name in
                ('describe', 'read_parms', 'list_parms', 'node_provenance', 'sop_output_node')):
            for value in list(args[:2]) + [kwargs[k] for k in ('node', 'parent', 'output', 'controller', 'camera', 'target') if k in kwargs]:
                try:
                    node = value if isinstance(value, hou.Node) else hou.node(value) if isinstance(value, str) and value.startswith('/') else None
                    if node is not None: observed_nodes[node.sessionId()] = node.path()
                except hou.Error:
                    pass
        start = time.time()
        args_json = _verb_value(list(args))
        kwargs_json = {str(k): _verb_value(v) for k, v in kwargs.items()}
        try:
            if name in _MUTATING_VERB_NAMES:
                failed = next((entry for entry in ledger if _unrecovered_mutation(entry)), None)
                if failed is not None:
                    raise _DispatchBlockedError(
                        f"{name} blocked before dispatch: earlier verb {failed['verb']} failed; "
                        "its scene recovery is unverified. Read-only diagnostics may continue; repair in a new exec.",
                        {'ok': False, 'phase': 'prior_verb_failure', 'scene_writes': 0,
                         'dispatched': False, 'failed_verb': failed['verb']})
            bound_arguments = {}
            if discovery_signature is not None:
                try:
                    bound_arguments = discovery_signature.bind(*args, **kwargs).arguments
                except TypeError as error:
                    hint = ( ' parent is an existing creation network, not a category. '
                             'For SOPs use node_info(existing_geo, "box"); if no geometry container exists, '
                             'first create one with tab_create("/obj", "geo", name=...) through houdini_exec.'
                             if name == 'node_info' else '')
                    message = (f'{error}. Call {name}{discovery_signature}. '
                               f'Use verb_help("{name}") for return type and documentation. '
                               'This call was not dispatched and made no scene writes.' + hint)
                    raise _VerbArgumentError(message, {'ok': False, 'phase': 'argument_binding',
                        'scene_writes': 0, 'dispatched': False, 'signature': str(discovery_signature),
                        'next_action': f'verb_help("{name}")'}) from error
            targets = []
            edits_content = name in _MUTATING_VERB_NAMES and name not in _OBSERVATION_VERBS
            if bound_arguments.get('dry_run') is True:
                edits_content = False
            if impact is not None and edits_content:
                impact['attempted'] = True
                if name in _GLOBAL_EDIT_VERBS:
                    impact['global'] = True
                for value in list(args[:2]) + [kwargs[k] for k in ('node', 'parent', 'output', 'controller', 'target', 'src', 'dst') if k in kwargs]:
                    try:
                        node = value if isinstance(value, hou.Node) else hou.node(value) if isinstance(value, str) and value.startswith('/') else None
                        if node is not None:
                            targets.append(node)
                    except hou.Error:
                        impact['unavailable'] = True
                if not targets:
                    impact['global'] = True
                _observe_impact(targets, impact, descendants=name in ('delete_node', 'rename_node'))
            result = fn(*args, **kwargs)
            if impact is not None:
                if edits_content:
                    impact['last_edit_ledger_index'] = len(ledger) + 1
                    if name != 'delete_node':
                        _observe_impact(targets, impact, descendants=name == 'rename_node')
                if name in ('test_controls', 'test_cop_controls') and isinstance(result, dict) and result.get('restored') is not True:
                    impact['global'] = True
                    impact['attempted'] = True
            entry = {
                "verb": name,
                "ts": round(start, 3),  # 绝对时间戳（epoch 秒）：跨 exec 重建真实调用顺序
                "args": args_json,
                "kwargs": kwargs_json,
                "ok": True,
                # Help is already pure JSON. Preserve its nested schema rather
                # than converting fields beyond the compact HOM snapshot depth
                # to repr strings; __result__ and ledger then carry one contract.
                "result": _jsonable(result) if name == 'verb_help' else _verb_value(result),
                "ms": round((time.time() - start) * 1000, 1),
            }
            check = result.get("validation", result) if isinstance(result, dict) else None
            if name=='set_parm' and isinstance(check,dict) and isinstance(check.get('evaluation'),dict):
                status=check['evaluation'].get('status')
                entry['check_status']={'failed':'failed','warning':'warning','unverified':'unverified'}.get(status,'passed')
                entry['check_scope']='parameter evaluation only; geometry effect unverified'
            if name == 'geo_piece_stats' and isinstance(check, dict):
                if check.get('status') == 'unverified':
                    entry['check_status'] = 'unverified'
                elif check.get('risk_status') == 'needs_review' or check.get('boundary_review_status') == 'open_boundary_unreviewed':
                    entry['check_status'] = 'warning'
                elif check.get('risk_status') == 'no_detected_integrity_risk':
                    entry['check_status'] = 'passed'
                entry['check_scope'] = 'Polygon surface integrity only; no contact, self-intersection, appearance or intended-open-port certification'
            if name in ("set_parms", "cook_node", "verify_network", "build_module", "render_frame", "render_view", "viewport_screenshot", "camera_fit", "geo_point_spacing","geo_check_interfaces","test_controls", "cop_layer_stats", "cop_compare_layers", "test_cop_controls") and isinstance(check, dict):
                if check.get('status') in ('unverified', 'not_evaluated_manual', 'not_cooked_manual'):
                    entry['check_status'] = 'unverified'
                elif check.get("ok") is False or check.get("errors") or check.get("fresh") is False:
                    entry["check_status"] = "failed"
                elif check.get("healthy") is False or check.get("warning_free") is False or check.get('pixel_status') == 'needs_review':
                    entry["check_status"] = "warning"
                else:
                    entry["check_status"] = "passed" if not result.get("dry_run") else "unverified"
            summary = _operation_summary(name, result)
            if summary is not None:
                entry['summary'] = _jsonable(summary)
            ledger.append(entry)
            kw = f", {_clip(kwargs_json)}" if kwargs_json else ""
            print(f"[verb] {name}({_clip(args_json)}{kw}) -> {_clip(entry['result'])}  ({entry['ms']}ms)")
            return result
        except BaseException as e:  # 记录失败调用并原样抛出，不改变原语义
            if impact is not None and name in ('test_controls', 'test_cop_controls'):
                impact['global'] = True
                impact['attempted'] = True
            ledger.append({
                "verb": name,
                "ts": round(start, 3),
                "args": args_json,
                "kwargs": kwargs_json,
                "ok": False,
                "error": str(e),
                "ms": round((time.time() - start) * 1000, 1),
            })
            if isinstance(e, dsh_hou_helpers.CheckpointError):
                ledger[-1]['summary'] = _jsonable(_operation_summary(name, e.evidence) or e.evidence)
                ledger[-1]['check_status'] = 'failed'
            if isinstance(e, (dsh_hou_helpers.PreflightError, dsh_hou_helpers.ParameterPatchError,
                              _DispatchBlockedError, _VerbArgumentError)):
                ledger[-1]['summary'] = _jsonable(e.evidence)
            elif not isinstance(e, dsh_hou_helpers.CheckpointError) and isinstance(getattr(e, 'evidence', None), dict):
                ledger[-1]['summary'] = _jsonable(e.evidence)
            kw = f", {_clip(kwargs_json)}" if kwargs_json else ""
            print(f"[verb] {name}({_clip(args_json)}{kw}) -> ERROR: {e}")
            raise
    return wrapped


def _raise_caught_verb_failure(verb_ledger: list) -> None:
    """Fail an exec that caught a verb exception and continued.

    The tracer records an exception before re-raising it. Agent code used to
    catch that exception, print diagnostics, and let the outer exec commit a
    potentially partial scene as ``ok: true``. This check runs while the same
    undo group is still open, so the normal failure path can roll back every
    Houdini-undoable edit in the batch.
    """
    failed = [entry for entry in verb_ledger if _unrecovered_mutation(entry)]
    if not failed:
        return
    names = ", ".join(str(entry.get("verb", "?")) for entry in failed[:8])
    if len(failed) > 8:
        names += f", +{len(failed) - 8} more"
    raise RuntimeError(
        "agent code caught and suppressed a verb exception "
        f"({names}); the exec is failed so undoable scene edits can roll back. "
        "The failed mutation has no confirmed zero-write or restored state; re-raise it."
    )


def _execute_edit(compiled, namespace, verb_ledger, created_nodes, box_journal):
    """Execute one admitted edit batch and restore the same ownership on undo."""
    error = rollback = None
    undo_enabled = bool(hou.undos.areEnabled())
    if undo_enabled:
        label = f"dsh-houdini exec {uuid.uuid4().hex}"
        ownership_before = dict(dsh_hou_helpers._OWNED_NODE_SESSIONS)
        # Component provenance rides the same transaction as the scene:
        # a rollback must restore _IMPORT_RECORDS together with the nodes,
        # or a later expected_contract operation sees stale provenance.
        imports_before = dict(dsh_component_contracts._IMPORT_RECORDS)
        # Causal binding, part 1: only entries whose identity was ALIVE
        # at batch start are eligible for undo-resurrection adoption,
        # and each records the path it ACTUALLY held at batch start
        # (renames included). Stale entries left by a leaked deletion
        # route (destroy without unregister) were already dead before
        # this batch; their undo cannot resurrect anything.
        alive_at_start = {}
        for _identity, _entry in dsh_hou_helpers._OWNED_NODE_SESSIONS.items():
            _live = hou.nodeBySessionId(_identity)
            if _live is not None:
                alive_at_start[_identity] = (_entry, _live.path())
        try:
            with hou.undos.group(label):
                exec(compiled, namespace)
                _raise_caught_verb_failure(verb_ledger)
        except BaseException:
            original_error = traceback.format_exc()
            applied = False
            rollback_error = None
            removed_residuals = []
            reconciled = []
            try:
                # Causal binding, part 2: the deleted set is computed
                # BEFORE the undo - identities alive at batch start that
                # are dead after this batch's own deletions. Exactly
                # these can be resurrected by the undo below.
                deleted_by_batch = {identity: alive_at_start[identity]
                                    for identity in alive_at_start
                                    if hou.nodeBySessionId(identity) is None}
                labels = list(hou.undos.undoLabels())
                if labels and labels[0] == label:
                    hou.undos.performUndo()
                    applied = True
                    dsh_hou_helpers._OWNED_NODE_SESSIONS.clear()
                    dsh_hou_helpers._OWNED_NODE_SESSIONS.update(ownership_before)
                    removed_residuals = dsh_hou_helpers._cleanup_failed_creations(created_nodes, ownership_before)
                    # Undo resurrects deleted nodes with their original ids but gives
                    # recreated native children fresh ones; re-register those with the
                    # bounded evidence of the pre-batch record. Adoption is causally
                    # bound to THIS batch (deleted_by_batch) and locates candidates
                    # by the path each identity actually held at batch start -
                    # path_at_creation is audit-only and must never select targets
                    # after renames.
                    reconciled = dsh_hou_helpers._reconcile_undo_resurrected(deleted_by_batch)
                    dsh_component_contracts._IMPORT_RECORDS.clear()
                    dsh_component_contracts._IMPORT_RECORDS.update(imports_before)
                    box_reconciliation = dsh_network_boxes.reconcile_transaction(box_journal)
                    if not box_reconciliation['ok']:
                        raise RuntimeError('Network Box rollback reconciliation failed: ' +
                                           '; '.join(box_reconciliation['errors']))
            except BaseException as undo_error:
                rollback_error = str(undo_error)
            rollback = {
                "supported": True,
                "applied": applied,
                "scope": "Houdini undoable scene edits only",
            }
            if not applied and rollback_error is None:
                rollback["note"] = (
                    "exec failed but produced no matching undo group；"
                    "file I/O/HDA library edits and non-undoable effects cannot roll back"
                )
            if rollback_error is not None:
                rollback["error"] = rollback_error
            if removed_residuals:
                rollback['removed_created_residuals'] = removed_residuals
            if reconciled:
                rollback['reconciled_resurrected_identities'] = reconciled
            if 'box_reconciliation' in locals():
                rollback['network_boxes'] = box_reconciliation
            error = original_error
    else:
        try:
            exec(compiled, namespace)
            _raise_caught_verb_failure(verb_ledger)
        except BaseException:
            rollback = {
                "supported": False,
                "applied": False,
                "scope": "Houdini undo stack disabled (commonly headless)",
            }
            error = traceback.format_exc()
    return error, rollback


class ExecutionRuntime:
    def __init__(self, thread_id, runtime_id, executor_id):
        self.thread_id = thread_id
        self.runtime_id = runtime_id
        self.executor_id = executor_id
        self.sequence = 0

    def run_code(self, code: str, allow_raw: str | None = None,
                 owner_session: str | None = None,
                 owner_call: str | None = None,
                 read_only: bool = False, *, raw_gate: bool = True) -> dict:
        """Execute code with `hou` available; capture stdout/stderr and `__result__`.

        Must run on Houdini's main thread (see module docstring) — callers route
        through `_execute`. BaseException is caught so agent code calling
        `sys.exit()` or raising KeyboardInterrupt cannot kill a handler/job thread
        or leave a job stuck in `running` forever.

        allow_raw：词表未覆盖的低层修改的一次性豁免理由（见 _gate_message）；
        它不能旁路已被动词覆盖的裸调用。豁免会打印 [gate] 行进 stdout，进结果与 trace。
        """
        if threading.get_ident() != self.thread_id:
            raise RuntimeError("run_code must execute on Houdini's owning thread")
        self.sequence += 1
        execution_sequence = self.sequence
        verb_ledger: list = []
        observed_nodes = {}
        impact = {'nodes': {}, 'attempted': False, 'global': False, 'truncated': False, 'unavailable': False}
        namespace = {"hou": hou}
        for _name, _fn in _VERBS.items():
            if read_only and _name in _MUTATING_VERB_NAMES:
                continue
            namespace[_name] = _make_tracer(_name, _fn, verb_ledger, observed_nodes, impact)
        stdout = _CappedStringIO(_MAX_STREAM_BYTES)
        stderr = _CappedStringIO(_MAX_STREAM_BYTES)
        error = None
        rollback = None
        analysis = CodeAnalysis(code)
        raw_usage = analysis.raw_usage
        gate_outcome = "not_applicable"
        creation_scope = contextlib.nullcontext(set()) if read_only else dsh_hou_helpers._track_created_nodes()
        box_scope = contextlib.nullcontext({'entries': [], 'boxes': 0, 'nodes': 0}) if read_only else dsh_network_boxes.transaction_journal()
        with (dsh_hou_helpers._execution_owner(owner_session, owner_call),
              creation_scope as created_nodes, box_scope as box_journal):
            # Each serialized request reports only its own produced media,
            # including requests rejected during preflight.
            dsh_hou_helpers._PRODUCED_IMAGES.clear()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    if not read_only:
                        from dsh_executor_registry import require_active_writer
                        require_active_writer(owner_session, hou.hipFile.path())
                    error, gate_outcome = analysis.preflight(mutating_verbs=_MUTATING_VERB_NAMES,
                        read_only=read_only, raw_gate=raw_gate, allow_raw=allow_raw)
                    if error is None:
                        has_covered = bool(raw_usage.get("coveredMutations"))
                        has_suspected = bool(raw_usage.get("suspectedMutations"))
                        has_direct = bool(raw_usage.get("directCalls"))
                        if raw_gate and allow_raw and has_suspected and not has_covered:
                            gate_outcome = "exempted"
                            print(f"[gate] raw-hou exemption: {allow_raw}")
                        elif not raw_gate and (has_covered or has_suspected):
                            gate_outcome = "disabled"
                        elif has_direct and not has_covered and not has_suspected:
                            gate_outcome = "read_only"
                        elif has_covered or has_suspected:
                            gate_outcome = "allowed"
                        compiled = analysis.compile()
                        if read_only:
                            exec(compiled, namespace)
                            _raise_caught_verb_failure(verb_ledger)
                        else:
                            error, rollback = _execute_edit(compiled, namespace, verb_ledger, created_nodes, box_journal)
                except BaseException:
                    if error is None:
                        error = traceback.format_exc()
            images = [p for p in dsh_hou_helpers._PRODUCED_IMAGES if os.path.isfile(p)]
        advisories = [a for a in (_raw_hou_advisory(analysis, verb_ledger), _repo_write_advisory(code)) if a]
        envelope = project_result(ledger=verb_ledger, images=images,
            stdout=stdout.getvalue(), stderr=stderr.getvalue(), error=error, rollback=rollback,
            raw_usage=raw_usage, gate_outcome=gate_outcome, allow_raw=allow_raw,
            namespace=namespace, advisories=advisories)
        mutation_attempted = any(v['verb'] in _MUTATING_VERB_NAMES and
            (v.get('summary') or {}).get('scene_writes') != 0 and
            (v.get('ok') or (v.get('summary') or {}).get('restored') is not True)
            for v in verb_ledger) or bool(raw_usage.get('coveredMutations') or raw_usage.get('suspectedMutations'))
        if error is None:
            transaction_status = 'committed' if mutation_attempted else 'no_scene_change'
        elif rollback and rollback.get('applied') and not rollback.get('error'):
            transaction_status = 'rolled_back'
        elif not mutation_attempted or gate_outcome in ('blocked', 'forbidden', 'read_only_blocked'):
            transaction_status = 'no_scene_change'
        elif not created_nodes and not raw_usage.get('coveredMutations') and not raw_usage.get('suspectedMutations') and all(
                (v.get('summary') or {}).get('scene_writes') == 0 for v in verb_ledger if v['verb'] in _MUTATING_VERB_NAMES):
            transaction_status = 'no_scene_change'
        else:
            transaction_status = 'recovery_unverified'
        identities = sorted(set(observed_nodes) | created_nodes | set(impact['nodes']))
        states = []
        for identity in identities[:64]:
            node = hou.nodeBySessionId(identity)
            states.append({'identity': identity, 'prior_path': observed_nodes.get(identity, impact['nodes'].get(identity)),
                           'exists': node is not None, 'path': node.path() if node else None})
        envelope['transaction'] = {'status': transaction_status, 'scope': 'Houdini undoable scene edits only; file/external side effects are separate',
                                   'nodes': states, 'nodes_truncated': len(identities) > 64,
                                   'coverage': 'created identities, primary arguments and bounded native dependency cone; not all implicit dependencies'}
        if box_journal.get('entries'):
            envelope['transaction']['network_boxes'] = {
                'entry_count': len(box_journal['entries']), 'box_count': box_journal['boxes'],
                'node_count': box_journal['nodes'],
                'scope': 'typed Network Box presentation snapshots; never node identities or geometry evidence'}
        if transaction_status != 'no_scene_change':
            _observe_impact([node for identity in created_nodes if (node := hou.nodeBySessionId(identity)) is not None], impact)
            if raw_usage.get('coveredMutations') or raw_usage.get('suspectedMutations'):
                impact['global'] = True
                impact['attempted'] = True
        else:
            impact = {'nodes': {}, 'attempted': False, 'global': False, 'truncated': False, 'unavailable': False}
        scene = dsh_hou_helpers.scene_info()
        envelope['execution'] = {'runtime_id': self.runtime_id, 'executor_id': self.executor_id, 'sequence': execution_sequence,
            'observed_at': time.time(), 'frame': scene['frame'], 'hip_path': scene['hip_path'],
            'hip_dir': scene['hip_dir'], 'hip_is_new': scene['hip_is_new'],
            'update_mode': scene['update_mode'],
            'owner_session': owner_session, 'read_only': read_only,
            'impact': {**{k:v for k,v in impact.items() if k != 'nodes'},
                'nodes': [{'identity': identity, 'path': path} for identity, path in impact['nodes'].items()],
                'scope': 'bounded native wires and last-cook expression dependents; excludes unobserved GUI, dynamic and external changes'}}
        bindings = []
        for item in envelope.get('evidence', []):
            if len(bindings) >= 64:
                break
            if item.get('verb') in ('render_view', 'render_frame'):
                source = item.get('source')
                target = item.get('target') or (source.get('path') if isinstance(source, dict) else None)
            else:
                target = item.get('output') if isinstance(item.get('output'), str) else item.get('node')
                if item.get('verb') == 'cop_compare_layers':
                    target = (item.get('after') or {}).get('node')
            if isinstance(target, str) and target.startswith('/'):
                try:
                    node = hou.node(target)
                    binding = {'ledger_index': item['ledgerIndex'], 'verb': item['verb'],
                                     'path': target, 'identity': node.sessionId() if node else None,
                                     'exists': node is not None}
                    if item.get('verb') == 'cop_compare_layers':
                        binding['dependencies'] = [{k: m[k] for k in ('node', 'identity', 'output') if k in m}
                            for m in (item.get('before'), item.get('after'), item.get('expected_delta')) if isinstance(m, dict)]
                    bindings.append(binding)
                except Exception:
                    envelope['execution']['outputs_unavailable'] = True
        envelope['execution']['outputs'] = bindings
        return envelope
