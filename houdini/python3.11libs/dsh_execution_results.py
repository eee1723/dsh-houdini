"""Bounded serialization and projections of completed execution facts.

This module does not call HOM or decide whether a scene operation may run.
"""
from __future__ import annotations

import io
import json
import math
import os

_MAX_STREAM_BYTES = 1024 * 1024          # cap captured stdout/stderr per exec


_MAX_RESULT_BYTES = 4 * 1024 * 1024      # cap the serialized __result__


_MAX_RESULT_DEPTH = 20                   # recursion depth for __result__ coercion


_MAX_RESULT_ITEMS = 1000                 # items per container before repr fallback


_VERB_VALUE_CHARS = 2000      # 单个入参/出参序列化后的截断长度


class _CappedStringIO(io.StringIO):
    """StringIO that stops growing past `limit`, appending a truncation marker."""

    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit
        self.overflowed = False

    def write(self, s) -> int:
        if self.overflowed:
            return len(s)
        remaining = self.limit - self.tell()
        if len(s) <= remaining:
            return super().write(s)
        super().write(s[:remaining])
        super().write("\n... [dsh-houdini: output truncated]\n")
        self.overflowed = True
        return len(s)


def _jsonable(value, _depth: int = 0):
    """Deep-coerce `value` to a JSON-safe object; non-JSON leaves become `repr`."""
    if _depth > _MAX_RESULT_DEPTH:
        return repr(value)
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return repr(value)
        # dsh-tools requires lossless JSON and deliberately rejects -0 because a
        # normal JSON snapshot may collapse it to +0. Houdini vectors/matrices and
        # quaternion probes commonly produce -0.0, so normalize it at the single
        # bridge boundary used by __result__ and the verb ledger.
        return 0.0 if value == 0.0 else value
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_RESULT_ITEMS:
            return repr(value)
        return [_jsonable(v, _depth + 1) for v in value]
    if isinstance(value, dict):
        if len(value) > _MAX_RESULT_ITEMS:
            return repr(value)
        return {str(k): _jsonable(v, _depth + 1) for k, v in value.items()}
    try:
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError):
        return repr(value)


def _clip(obj) -> str:
    """序列化并截断，供 stdout 摘要行使用。"""
    try:
        text = json.dumps(obj, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):
        text = repr(obj)
    return text if len(text) <= _VERB_VALUE_CHARS else text[:_VERB_VALUE_CHARS] + "..."


def _artifact_candidates(ledger, images, execution_ok):
    """Project authoritative output paths; never declare user deliverables here."""
    found = {}

    def add(path, kind, role, source):
        if not isinstance(path, str):
            return
        try:
            if not os.path.isabs(path) or os.path.islink(path) or not os.path.isfile(path):
                return
            size = os.stat(path).st_size
            absolute = os.path.abspath(path)
            key = os.path.normcase(absolute)
        except (OSError, ValueError):
            return
        if size <= 0:
            return
        found[key] = {'path': absolute, 'kind': kind,
                      'role': role if execution_ok else 'diagnostic',
                      'source': source, 'bytes': int(size)}

    for entry in ledger:
        if len(found) >= 16 or not entry.get('ok') or not isinstance(entry.get('result'), dict):
            continue
        name, result = entry['verb'], entry['result']
        verified = (result.get('ok') is not False and not result.get('errors') and not result.get('warnings')
                    and result.get('fresh') is not False and result.get('stale') is not True
                    and result.get('warning_free') is not False
                    and result.get('pixel_status') not in ('failed', 'needs_review')
                    and result.get('file_status') != 'failed')
        role = 'delivery-candidate' if verified else 'diagnostic'
        if name in ('scene_save', 'scene_save_as'):
            add(result.get('path'), 'scene', role, name)
        elif name == 'component_export':
            add(result.get('file'), 'component', role, name)
        elif name in ('hda_create', 'hda_fork'):
            add(result.get('hda_file'), 'asset', role, name)
        elif name == 'tool_package_create':
            add(result.get('package_file'), 'tool-package', role, name)
        elif name == 'render_frame':
            add(result.get('output'), 'render', role, name)
        elif name in ('render_view', 'viewport_screenshot'):
            artifact = result.get('artifact')
            policy = artifact.get('output_policy') if isinstance(artifact, dict) else None
            path = artifact.get('actual_path') if isinstance(artifact, dict) else None
            if not path:
                path = result.get('output') if name == 'render_view' else result.get('path')
            default_role = 'visual-check' if name == 'render_view' else 'diagnostic'
            add(path, 'image', role if policy in ('explicit', 'delivery') and verified else default_role if verified else 'diagnostic', name)
    for path in images:
        if len(found) >= 16:
            break
        try:
            key = os.path.normcase(os.path.abspath(path)) if isinstance(path, str) and os.path.isabs(path) else None
        except (OSError, ValueError):
            key = None
        if key not in found:
            add(path, 'image', 'visual-check', 'reported-image')
    return list(found.values())


def _operation_summary(name: str, result):
    """Small, untruncated evidence before verbose node lists/service metadata."""
    if not isinstance(result, dict):
        return None
    if name.startswith('tool_package_'):
        return {k: result[k] for k in (
            'ok', 'action', 'dry_run', 'applied', 'phase', 'restored', 'restore_errors',
            'package_file', 'resource_root', 'created', 'config_sha256', 'config_unchanged', 'source_unchanged',
            'declared_resource_roots', 'effective_resource_roots', 'resource_roots', 'runtime_only', 'enabled_in_config',
            'file_count', 'bytes', 'conflicts', 'blockers', 'affected_instances', 'unsupported_resource_locations', 'missing_resource_roots',
            'runtime', 'runtime_root_matches_config', 'cached_python_modules', 'restart_required_for_python_cache',
            'startup_directory_detected', 'startup_load_verified', 'package_exists', 'registration_created',
            'cleanup_errors', 'native_action_attempted', 'scene_writes', 'file_writes', 'dispatched', 'scope',
            'source_files_retained', 'unverified') if k in result}
    if name in ('hda_create', 'hda_fork'):
        return {k: result[k] for k in (
            'ok', 'node', 'category', 'type', 'hda_file', 'source_node', 'source_type', 'source_library',
            'copied', 'source_instances_migrated', 'instances_created', 'min_inputs', 'max_inputs', 'max_outputs',
            'pending_spare_parameter_count', 'verification_scope', 'next_action', 'phase', 'restored',
            'restore_errors', 'scene_writes') if k in result}
    r = result.get('validation', result) if name == 'build_module' else result
    if name in ('set_parm','set_parms') and ('evaluation' in r or 'evaluations' in r):
        return r
    if name == 'set_parm' and 'patch' in r:
        return r
    if name == 'set_parms' and r.get('patched'):
        return {'node': r['node'], 'ok': r['ok'],
                'patches': {key: r['set'][key] for key in r['patched']}}
    if name == 'node_info':
        components = [{'name':p['name'],'components':p['components']} for p in r.get('parameters',[]) if len(p.get('components',[]))>1]
        return {k:r[k] for k in ('parent','type','version','visible','operation_card','usage_notes','operation_parameters','operation_parameters_missing','operation_parameter_scope','filter_mode','filter','parameter_count','total_parameter_count','next_action') if k in r} | {
            'tuple_components':components[:20], 'tuple_components_truncated':len(components)>20,
            'setting_cards':[{k:p[k] for k in ('name','type','components','default','menu','menu_dynamic') if k in p}
                             for p in r.get('parameters',[])[:24]],
            'setting_cards_truncated':len(r.get('parameters',[]))>24,
            'parameter_scope':'returned filtered parameter card only; retain components and menu set_value when summarizing'}
    if name in ('connect','disconnect_input'):
        return result
    if name == 'camera_fit':
        return result
    if name == 'geo_attrib_stats' and 'unique_count' in result:
        return result
    if name == 'create_spare_parms' and result.get('mode') == 'update_defaults':
        return result
    if name == 'bind_controls' or name == 'create_spare_parms' and result.get('mode') == 'layout':
        return {k: result[k] for k in ('ok','mode','controller','node','dry_run','applied','phase',
            'scene_writes','created','current_state_preserved','plan_sha256','bindings','restored','restore_errors','scope') if k in result}
    if name == 'hda_edit':
        return result
    if name == 'hda_set_interface':
        return {k: result[k] for k in ('ok', 'mode', 'node', 'dry_run', 'applied', 'phase',
                'scene_writes', 'before_sha256', 'after_sha256', 'current_state_preserved',
                'preserved_channels', 'restored', 'restore_errors', 'scope') if k in result}
    if name in ('present_nodes','focus_node'):
        return {k:result[k] for k in ('kind','scene_writes','requires_save','id','path','parent','network_current','parameter_current','scope') if k in result}
    if name == 'network_controls':
        return {k:result[k] for k in ('ok','parent','scene_writes','declared','removed','scope') if k in result}
    if name == 'network_boxes':
        return {k: result[k] for k in (
            'ok','dry_run','applied','phase','scene_writes','plan_sha256','parent',
            'created','updated','removed','unchanged','protected_items',
            'current_state_preserved','restored','restore_errors','identity_remaps',
            'original_error','recovery_exception','journaled','scope','layout_status') if k in result} | {
            'box_count': len(result.get('boxes') or [])}
    if name == 'network_notes':
        return {k: result[k] for k in ('ok','parent','phase','scene_writes','created','updated','removed','unchanged',
                                      'restored','restore_errors','identity_remaps','scope') if k in result} | {
            'note_count': len(result.get('notes') or [])}
    if name == 'layout_nodes' and result.get('mode') in ('handoff','component'):
        return {k:result[k] for k in ('ok','mode','dry_run','applied','scene_writes','plan_sha256','profile','parent',
            'box_count','movable_node_count','moved_node_count','changed_box_count','node_overlap_count',
            'box_overlap_count','obstacle_overlap_count','containment_failures','clearance_failures',
            'component_box_count','leaf_box_count','moved_leaf_box_count','changed_component_box_count',
            'leaf_box_overlap_count','component_box_overlap_count',
            'required_clearances','achieved_clearances','minimum_clearances',
            'fixed_obstacles','skipped_items','layout_status','restored','restore_errors','scope') if k in result}
    if name == 'geo_piece_stats' and 'method' in r:
        return {k:r[k] for k in ('node','frame','group','method','status','reason','selected_primitives','selected_points',
            'boundary_edges','boundary_review_status','nonmanifold_edges','orientation_conflicts',
            'orientation_review_status',
            'zero_area_faces','zero_length_edges','duplicate_boundary_faces','duplicate_face_sample',
            'risk_status','risk_reasons','scope','shell_orientation','shading_normals',
            'planar_face_crossings',
            'extents','bounds_min','bounds_max') if k in r}
    if name in ('cop_layer_stats', 'cop_compare_layers', 'test_cop_controls'):
        return {k:r[k] for k in ('ok','status','semantic_status','node','output','output_port','controller',
                'frame','checked_at','scope','resolution','channels','statistics','sha256','freshness','cache',
                'formula','max_abs_difference','max_abs_error','tolerance','before','after','expected_delta',
                'restored','parameter_writes','coverage','case_id','reason','results') if k in r}
    if name not in ('verify_network', 'build_module', 'render_view', 'render_frame',
                    'viewport_screenshot', 'geo_point_spacing','geo_check_interfaces','test_controls'):
        return None
    fields = ('ok','output','target','frame','checked_at','scope','scope_signature','node_count','nonempty','healthy',
              'warning_free','failure_reasons','next_action','file_status','pixel_status','semantic_status',
               'fresh','file_bytes','bytes','stale','capture_unresolved','user_state_restored','restore_errors','dry_run','valid','node','status','scene_writes','applied','restored','phase','dispatched',
              'expected','tolerance','order','closed','coordinate_space','coverage','pair_count',
              'min_distance','max_distance','failure_count','failures','failures_truncated','sequence_sha256',
              'results','geometry_sha256','contract_sha256','restored','baseline_sha256','controller',
              'baseline_interfaces','baseline_topology','baseline_domain','baseline','expectation','case_id','control_summary',
              'baseline_captures','capture_status','representation',
              'pair_tests','reason','parameter_writes','required_outputs','geometry_status','update_mode',
              'scene_unit_length_meters','bbox_size_sop_local_mm','handoff_output',
              'cook_details','cook_errors','geometry_restore','frame_restored')
    out = {k: r[k] for k in fields if k in r}
    if name == 'verify_network' and isinstance(r.get('geometry'), dict):
        out['geometry'] = {k:r['geometry'][k] for k in
            ('points','prims','bbox_min','bbox_max','bbox_size') if k in r['geometry']}
    if name in ('render_view', 'viewport_screenshot') and isinstance(r.get('artifact'), dict):
        out['artifact'] = {k:r['artifact'].get(k) for k in (
            'purpose','output_policy','actual_path','hip_relative_path','managed_root',
            'run_id','capture_id','frame','reservation_retained')}
    if name in ('render_view','render_frame') and isinstance(r.get('framing'), dict):
        out['framing'] = r['framing']
    if 'framing_status' in r:
        out.update({k:r[k] for k in ('framing_status','products','reasons','render_started','projected_bounds_ndc','margin_px','depth_check','crop_reasons') if k in r})
    if result.get('interface_checks') is not None:
        out['interface_checks'] = result['interface_checks']
    for field in ('error_nodes','warning_nodes','errors','warnings'):
        if field in r:
            values = r[field]
            out[field] = [str(v)[:400] for v in values[:12]]
            out[field + '_count'] = len(values)
    fp = r.get('output_fingerprint') or r.get('source_fingerprint_after')
    if isinstance(fp, dict):
        out['source'] = {k: fp[k] for k in ('path','frame','signature','signature_scope','points','prims') if k in fp}
    check = r.get('check')
    if isinstance(check, dict):
        out['check'] = check
        out['pixels'] = check  # compatibility alias; matches the Python result
    return out


def project_result(*, ledger, images, stdout, stderr, error, rollback, raw_usage,
                   gate_outcome, allow_raw, namespace, advisories):
    """Build the public result solely from captured facts; no scene inspection."""
    verb_ledger = ledger
    envelope = {'ok': error is None, 'stdout': stdout, 'stderr': stderr}
    # Execution completion, raised operations and returned validation findings
    # are distinct facts. A caught read error can coexist with a useful fallback;
    # neither batch completion nor a passed check certifies the user's task.
    check_counts = {status: sum(v.get('ok') is True and v.get('check_status') == status
                                for v in verb_ledger)
                    for status in ('failed', 'warning', 'unverified')}
    envelope['outcome'] = {
        'batch': 'completed' if error is None else 'failed',
        'operations': {'total': len(verb_ledger),
                       'failed': sum(v.get('ok') is False for v in verb_ledger)},
        'checks': check_counts,
    }
    # Only images produced by this request enter the Host's native attachments.
    if images:
        envelope["images"] = images
    candidates = _artifact_candidates(verb_ledger, images, error is None)
    if candidates:
        envelope['artifactCandidates'] = candidates
    if verb_ledger:
        envelope["verbs"] = verb_ledger
        evidence = [{'ledgerIndex': i + 1, 'verb': v['verb'], **v['summary']}
                    for i, v in enumerate(verb_ledger) if isinstance(v.get('summary'), dict)]
        if evidence:
            envelope['evidence'] = evidence
        checks = [{"verb": v["verb"], "status": v["check_status"]}
                  for v in verb_ledger if v.get('ok') is True
                  and v.get("check_status") in ("failed", "warning", "unverified")]
        if checks:
            envelope["checks"] = checks
    if (
        raw_usage.get("directCalls")
        or raw_usage.get("coveredMutations")
        or raw_usage.get("suspectedMutations")
        or gate_outcome not in ("not_applicable", "read_only")
    ):
        raw_usage["gateOutcome"] = gate_outcome
        if allow_raw:
            raw_usage["exemptionReason"] = allow_raw
        envelope["rawUsage"] = raw_usage
    if advisories:
        envelope["advisory"] = "\n".join(advisories)
    if rollback is not None:
        envelope["rollback"] = rollback
    if error is not None:
        envelope["error"] = error
    if error is None and "__result__" in namespace:
        result = _jsonable(namespace["__result__"])
        try:
            if len(json.dumps(result, allow_nan=False)) > _MAX_RESULT_BYTES:
                result = f"[dsh-houdini: __result__ serialized to more than {_MAX_RESULT_BYTES} bytes; omitted]"
        except (TypeError, ValueError):
            result = repr(result)
        envelope["result"] = result
    return envelope
