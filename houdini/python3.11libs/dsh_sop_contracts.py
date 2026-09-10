"""Small SOP construction/checkpoint contracts. No host, network or UI services.

Only called by the main-thread verb layer. Helpers are imported lazily to keep
the original primitive API independent of this higher-level composition layer.
"""
from __future__ import annotations

import re
import time
import math
import hashlib
import struct
import hou


def geo_point_spacing(node, expected: float, tolerance: float, closed: bool = False,
                      order_attrib=None, max_points: int = 10000) -> dict:
    """Check EVERY adjacent point in one explicitly ordered sequence, local space.

    This measures Euclidean chord distances, not arc length, mesh connectivity,
    surface clearance or physical link assembly. Point-number order is the
    default and reported; a scalar unique numeric order attribute may override.
    Reject oversize inputs instead of silently sampling and missing an interior
    defect. Failed constraints return measured evidence (diagnostic read).
    """
    import dsh_hou_helpers as h
    n = h._resolve(node)
    expected, tolerance = float(expected), float(tolerance)
    if not math.isfinite(expected) or expected <= 0 or not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError('expected must be positive/finite; tolerance nonnegative/finite (SOP local units)')
    if not isinstance(closed, bool) or type(max_points) is not int or not 2 <= max_points <= 100000:
        raise ValueError('closed must be bool; max_points integer in 2..100000')
    from dsh_cook_control import require_evaluation
    require_evaluation('geo_point_spacing')
    g = n.geometry() if n.type().category() == hou.sopNodeTypeCategory() else None
    if g is None or n.errors():
        raise ValueError('geo_point_spacing requires an error-free SOP geometry output')
    count = int(g.intrinsicValue('pointcount'))
    if not 2 <= count <= max_points or (closed and count < 3):
        raise ValueError(f'point count={count}, requires 2..{max_points} (closed >=3); split oversized sequences, no sampling')
    points = list(g.points())
    if order_attrib is not None:
        if not isinstance(order_attrib, str):
            raise ValueError('order_attrib must be a scalar unique numeric point attribute name')
        attrib = g.findPointAttrib(order_attrib)
        if attrib is None or attrib.size() != 1 or attrib.dataType() not in (hou.attribData.Int, hou.attribData.Float):
            raise ValueError('order_attrib must be a scalar unique numeric point attribute')
        keys = [p.attribValue(attrib) for p in points]
        if len(set(keys)) != count or not all(math.isfinite(float(k)) for k in keys):
            raise ValueError('order_attrib has duplicate or nonfinite values')
        points = [p for _, p in sorted(zip(keys, points), key=lambda pair: pair[0])]
    positions = [p.position() for p in points]
    if not all(math.isfinite(float(v)) for pos in positions for v in pos):
        raise ValueError('sequence contains nonfinite positions')
    pairs = [(i, (i + 1) % count) for i in range(count if closed else count - 1)]
    distances = [(positions[j] - positions[i]).length() for i, j in pairs]
    failed = [{'from_point': points[i].number(), 'to_point': points[j].number(),
               'distance': d, 'error': abs(d - expected)}
              for (i, j), d in zip(pairs, distances) if abs(d - expected) > tolerance]
    digest = hashlib.sha256()
    for p, pos in zip(points, positions):
        digest.update(struct.pack('<q3d', p.number(), *pos))
    return {'ok': not failed, 'status': 'pass' if not failed else 'fail', 'node': n.path(),
            'frame': float(hou.frame()), 'checked_at': time.time(), 'expected': expected,
            'tolerance': tolerance, 'closed': closed, 'order': order_attrib or 'point_number',
            'coordinate_space': 'SOP local', 'point_count': count, 'pair_count': len(pairs),
            'coverage': 'all_adjacent_pairs', 'min_distance': min(distances), 'max_distance': max(distances),
            'mean_distance': sum(distances) / len(distances), 'failure_count': len(failed),
            'failures': sorted(failed, key=lambda f: f['error'], reverse=True)[:16],
            'failures_truncated': len(failed) > 16, 'sequence_sha256': digest.hexdigest(),
            'semantic_status': 'unverified',
            'note': 'Only the specified point sequence/chord spacing is checked; not curve arc length or final surface/assembly correctness.'}


def verify_network(parent, output=None, nodes=None, limit: int = 512, require_valid: bool = True) -> dict:
    """Cook/check SOP children, not just OUT. No display/frame/selection changes.

    Default scope is all direct SOP children (not HDA internals). Explicit nodes
    restrict the scope; the report lists it. A limit overrun fails, never samples
    and reports healthy. Warnings, empty output and semantic verification differ.
    """
    import dsh_hou_helpers as h
    p = h._resolve(parent)
    if p.childTypeCategory() != hou.sopNodeTypeCategory():
        raise ValueError("verify_network currently accepts a SOP network parent only")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 2048:
        raise ValueError("limit must be an integer in 1..2048")
    if not isinstance(require_valid, bool):
        raise ValueError('require_valid must be bool')
    if output is None:
        candidates = [n.path() for n in p.children() if n.name().upper().startswith('OUT')][:12]
        raise ValueError(f'explicit output required; no display-node fallback. Call verify_network(parent, output=<deliverable SOP>); candidates={candidates}')
    if nodes is not None and not isinstance(nodes, (list, tuple)):
        raise ValueError('nodes must be a list of explicit SOP nodes/paths')
    selected = list(p.children()) if nodes is None else [h._resolve(n) for n in nodes]
    out = p.node(output) if isinstance(output, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', output) else h._resolve(output)
    if out is None or out.parent() != p:
        raise ValueError("output must be an explicit direct SOP child")
    if out not in selected:
        selected.append(out)
    selected = list(dict.fromkeys(selected))
    if len(selected) > limit:
        raise ValueError(f"verification scope has {len(selected)} nodes, exceeding limit={limit}; select a module")
    if any(n.parent() != p or n.type().category() != hou.sopNodeTypeCategory() for n in selected):
        raise ValueError("all nodes must be direct SOP children of parent")
    if hou.updateModeSetting() == hou.updateMode.Manual:
        result = {'ok':False, 'healthy':False, 'warning_free':None, 'parent':p.path(),
                  'output':out.path(), 'status':'not_evaluated_manual', 'update_mode':'manual',
                  'failure_reasons':['not_evaluated_manual'], 'geometry':None, 'nonempty':None,
                  'output_fingerprint':None, 'semantic_status':'unverified',
                  'frame':float(hou.frame()), 'checked_at':time.time(),
                  'scope':'direct_children' if nodes is None else 'explicit_nodes',
                  'scope_signature':hashlib.sha256('\n'.join(sorted(n.path() for n in selected)).encode()).hexdigest(),
                  'requested_nodes':[n.path() for n in selected], 'checked_nodes':[], 'node_count':0,
                  'error_nodes':[], 'warning_nodes':[], 'issues':[],
                  'next_action':'Manual mode: metadata inspection/editing only; explicitly authorize set_update_mode before evaluation. Geometry is unknown, not empty.'}
        if require_valid:
            raise h.CheckpointError(result['next_action'], result)
        return result
    reports = [h.cook_node(n) for n in selected]
    errors = [r['path'] for r in reports if not r['ok']]
    warnings = [r['path'] for r in reports if not r['warning_free']]
    output_cooked = next(r['ok'] for r in reports if r['path'] == out.path())
    # Never turn a failed/interrupted explicit cook into an unbounded implicit
    # retry through geometry()/geometryAtFrame(), or certify its stale cache.
    geometry = out.geometry() if output_cooked else None
    summary = h._geo_summary(geometry) if geometry is not None else None
    nonempty = bool(summary and (summary.get('points') or summary.get('prims'))) if output_cooked else None
    fingerprint = h._geometry_fingerprint(out, hou.frame()) if nonempty and not out.errors() else None
    reasons = (['cook_error'] if errors else []) + (['empty_output'] if output_cooked and not nonempty else [])
    result = {'ok': not reasons, 'output': out.path(), 'failure_reasons': reasons,
            'parent': p.path(), 'frame': float(hou.frame()),
            'checked_at': time.time(), 'scope': 'direct_children' if nodes is None else 'explicit_nodes',
            'scope_signature': hashlib.sha256('\n'.join(sorted(n.path() for n in selected)).encode()).hexdigest(),
            'checked_nodes': [n.path() for n in selected], 'node_count': len(selected),
            'warning_free': not warnings,
            'healthy': not errors and not warnings and nonempty, 'nonempty': nonempty,
            'error_nodes': errors, 'warning_nodes': warnings,
            'issues': [r for r in reports if not r['healthy']], 'geometry': summary,
            'geometry_status':'evaluated' if output_cooked else 'not_evaluated_cook_failed',
            'output_fingerprint': fingerprint, 'semantic_status': 'unverified',
            'next_action': ('Fix the explicit output/cook errors, then rerun this checkpoint; do not substitute a different output without revisiting the deliverable.' if reasons else
                            'Resolve or explicitly explain warning nodes before handoff.' if warnings else
                            'Cook/output checkpoint passed; relationship and visual acceptance remain separate.'),
            'note': 'Cook/geometry evidence only; no assertion of relationships, art quality or unsampled HDA internals.'}
    if reasons and require_valid:
        details = [{'path':r['path'],'errors':r['errors']} for r in reports if not r['ok']][:3]
        raise h.CheckpointError(f'verify_network failed: {reasons}; output={out.path()}; errors={errors}; cook_details={str(details)[:1800]}. {result["next_action"]}', result)
    return result


def _prepare_module(parent, nodes, output, dry_run, interfaces, required_outputs):
    """Read-only validation boundary: no creation, parameter edits or flag changes."""
    import dsh_hou_helpers as h
    if interfaces is not None:
        from dsh_quality_contracts import validate_interfaces
        validate_interfaces(interfaces)
    p = h._resolve(parent)
    if p.childTypeCategory() != hou.sopNodeTypeCategory():
        raise ValueError('build_module only creates SOP modules; use primitive verbs for other contexts')
    if not isinstance(dry_run, bool):
        raise ValueError('dry_run must be bool')
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 64:
        raise ValueError('nodes must contain 1..64 small-module specs')
    existing = {n.name(): n for n in p.children()}
    from dsh_operation_cards import decision_advisories
    specs, known, preflight_errors = [], set(existing), []
    advice_by_type = {}
    def problem(name, field, message, **details):
        preflight_errors.append({'node': name, 'field': field, 'message': message, **details})
    for spec in nodes:
        if not isinstance(spec, dict) or set(spec) - {'name', 'type', 'parms', 'inputs'}:
            raise ValueError('node spec supports only name/type/parms/inputs')
        name, typ = spec.get('name'), spec.get('type')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            raise ValueError('each new node needs a simple explicit name')
        if name in known:
            raise ValueError(f'node exists or duplicate name: {name}')
        if not isinstance(typ, str) or not typ:
            raise ValueError(f'{name}: missing type')
        card = h.node_info(p, typ, limit=256)
        if not card['visible']:
            raise ValueError(f'{name}: hidden/deprecated type {typ}; use search_tab_entries')
        # Do not misvalidate later parameters against a truncated card.
        if card['truncated']:
            raise ValueError(f'{name}: type interface exceeds static preflight budget; use primitive verbs')
        values, inputs = spec.get('parms', {}), spec.get('inputs', [])
        if not isinstance(values, dict) or not isinstance(inputs, list):
            raise ValueError(f'{name}: parms must be dict and inputs must be list')
        decisions = decision_advisories(card.get('operation_card', {}), values)
        if decisions:
            key = (card['type'], tuple(d['id'] for d in decisions),
                   tuple(tuple(tuple(m) for m in d['missing']) for d in decisions))
            if key not in advice_by_type:
                relevant = {n for d in decisions for option in d['alternatives'] for n in option}
                advice_by_type[key] = {'type': card['type'], 'nodes': [],
                                       'operation_card': card['operation_card']['id'],
                                       'decisions': decisions,
                                       'setting_cards': [p for p in card.get('operation_parameters', []) if p['name'] in relevant],
                                       'missing_runtime_parameters': card.get('operation_parameters_missing', [])}
            advice_by_type[key]['nodes'].append(name)
        # Actual numbered multiparm names must be validated against the declared
        # count (or the static default), not the uninstantiated '#' template.
        typ_obj = hou.nodeType(p.childTypeCategory(), card['type'])
        card['parameters'] = h._node_parameter_cards(typ_obj, values)
        allowed = {c['name'] for c in card['parameters']}
        allowed.update(k for c in card['parameters'] for k in c.get('components', []))
        unknown = set(values) - allowed
        if unknown:
            import difflib
            for field in sorted(unknown):
                similar = difflib.get_close_matches(field, sorted(allowed), n=5, cutoff=0.25)
                problem(name, field, f'unknown parameter(s) {field!r}; candidates={similar}; use node_info with a literal filter', candidates=similar)
        for parameter in card['parameters']:
            if parameter.get('type') in ('Float', 'Int') and not parameter.get('menu') and not parameter.get('menu_dynamic'):
                components = parameter.get('components', [])
                fields = ([parameter['name']] if parameter['name'] in values else [])
                fields += [c for c in components if c != parameter['name'] and c in values]
                for field in fields:
                    try:
                        h._validate_numeric_parameter_value(values[field], components if field == parameter['name'] else ())
                    except (ValueError, OverflowError) as error:
                        problem(name, field, str(error), components=components)
            if parameter['name'] in values and parameter.get('menu') and parameter.get('type') in ('Menu','Int') and not parameter.get('menu_dynamic'):
                value = values[parameter['name']]
                tokens = [item['token'] for item in parameter['menu']]
                if not isinstance(value, dict):
                    try: h._menu_setting(parameter['menu'], value)
                    except ValueError as error: problem(name, parameter['name'], str(error), tokens=tokens)
        if len(inputs) > card['max_inputs']:
            problem(name, 'inputs', f'too many input slots ({len(inputs)} > {card["max_inputs"]})')
        for source in inputs:
            if source is None:
                continue  # explicit empty input; e.g. Wrangle lookup on input 1
            if not isinstance(source, str) or source not in known:
                problem(name, 'inputs', f'input {source!r} must be an earlier spec or existing child name')
        known.add(name)
        count_names = [c['name'] for c in card['parameters'] if c.get('multiparm_count') and c['name'] in values]
        ordered_values = {k:values[k] for k in count_names}
        ordered_values.update(values)
        specs.append({**spec, 'type': card['type'], 'parms': ordered_values, 'inputs': inputs, '_counts':count_names})
    if output not in {s['name'] for s in specs}:
        raise ValueError('output must name one of the newly created nodes')
    if required_outputs is not None:
        if not isinstance(required_outputs, list) or not 1 <= len(required_outputs) <= 16 or any(not isinstance(n,str) for n in required_outputs) or len(set(required_outputs)) != len(required_outputs):
            raise ValueError('required_outputs must contain 1..16 unique new node names')
        if any(n not in {s['name'] for s in specs} for n in required_outputs):
            raise ValueError('required_outputs must name newly declared module nodes')
    advice = {'operation_advisories': list(advice_by_type.values())[:16],
              'operation_advisory_count': len(advice_by_type),
              'operation_advisories_truncated': len(advice_by_type) > 16,
              'operation_advisory_scope': 'Static explicit-field presence only; advisory, not a rejection or geometric/intent verification. No parameters are changed by this advice.'}
    if preflight_errors:
        error = h.PreflightError(preflight_errors)
        error.evidence.update(advice)
        raise error
    return p, existing, specs, advice


def build_module(parent, nodes: list, output: str, dry_run: bool = False, interfaces=None, *, required_outputs=None) -> dict:
    """Create a small SOP module after zero-write type/parameter/input preflight.

    Inputs reference earlier specs or existing direct children; None retains
    empty input slots. dry_run cannot prove VEX/cook/geometry. After creation
    starts, cleanup and transaction recovery keep their existing strict rules.
    """
    import dsh_hou_helpers as h
    try:
        p, existing, specs, advice = _prepare_module(parent, nodes, output, dry_run, interfaces, required_outputs)
    except h.PreflightError:
        raise
    except (ValueError, TypeError, hou.Error) as error:
        raise h.PreflightError([{'node':'module','field':'preflight','message':str(error)}]) from error
    if dry_run:
        return {'valid': True, 'dry_run': True, 'parent': p.path(), 'node_count': len(specs), **advice,
                'output': output, 'interface_status': 'unverified' if interfaces is not None else 'not_requested',
                'required_outputs': list(required_outputs or []),
                'note': 'Static preflight only; VEX, dynamic menus, cooking and interface geometry remain unverified.'}
    from dsh_cook_control import require_evaluation
    require_evaluation('build_module')
    baseline = set(p.children())
    provenance = dict(h._OWNED_NODE_SESSIONS)
    # renderNode() can fall back to displayNode() even without a render flag.
    # Snapshot flags themselves; restoring the effective node would add a flag.
    display_flags = {n for n in baseline if n.isDisplayFlagSet()}
    render_flags = {n for n in baseline if n.isRenderFlagSet()}
    created = {}
    try:
        for spec in specs:
            n = h.tab_create(p, spec['type'], name=spec['name'],
                             inputs=[None if s is None else created.get(s) or existing[s] for s in spec['inputs']])
            created[spec['name']] = n
            if spec['parms']:
                # Counts instantiate parameters. This remains inside the new-
                # module transaction; any later failure removes the whole batch.
                for count in spec['_counts']:
                    h.set_parm(n,count,spec['parms'][count])
                remaining={k:v for k,v in spec['parms'].items() if k not in spec['_counts']}
                if remaining:h.set_parms(n, remaining)
        validation = verify_network(p, output=created[output], nodes=list(created.values()))
        required_checks = []
        for name in required_outputs or []:
            node = created[name]
            geometry = node.geometry()
            required_checks.append({'output':node.path(), 'nonempty': bool(geometry is not None and (len(geometry.points()) or len(geometry.prims()))), 'errors':list(node.errors())})
        if any(not row['nonempty'] or row['errors'] for row in required_checks):
            raise h.CheckpointError('required module output is empty or has cook errors; newly created module removed',
                                    {**validation, 'ok':False, 'failure_reasons':['required_output'], 'required_outputs':required_checks})
        if required_checks: validation['required_outputs'] = required_checks
        if not validation['ok']:
            raise RuntimeError(f'module cook/output failed: {validation["issues"]}; nonempty={validation["nonempty"]}')
        interface_checks = h.geo_check_interfaces(created[output], interfaces) if interfaces is not None else None
        if interface_checks is not None and not interface_checks['ok']:
            raise h.CheckpointError('build_module interface contract failed/unverified; new module removed',
                                    {**validation,'ok':False,'failure_reasons':['interface_contract'],
                                     'interface_checks':interface_checks})
        return {'valid': True, 'dry_run': False, 'parent': p.path(), **advice,
                'created': {name: n.path() for name, n in created.items()}, 'validation': validation,
                **({'interface_checks':interface_checks} if interfaces is not None else {})}
    except BaseException as error:
        if isinstance(getattr(error, 'evidence', None), dict):
            error.evidence.update(advice)
        for n in reversed(p.children()):
            if n not in baseline:
                n.destroy()
        h._OWNED_NODE_SESSIONS.clear()
        h._OWNED_NODE_SESSIONS.update(provenance)
        raise
    finally:
        # Creation may auto-select a display node; existing flags stay user-owned.
        for n in p.children():
            if n.isDisplayFlagSet() and n not in display_flags:
                n.setDisplayFlag(False)
            if n.isRenderFlagSet() and n not in render_flags:
                n.setRenderFlag(False)
        for n in display_flags:
            n.setDisplayFlag(True)
        for n in render_flags:
            n.setRenderFlag(True)
