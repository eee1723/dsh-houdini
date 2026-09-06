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
    out = h._resolve(output)
    if out is None or out.parent() != p:
        raise ValueError("output must be an explicit direct SOP child")
    if out not in selected:
        selected.append(out)
    selected = list(dict.fromkeys(selected))
    if len(selected) > limit:
        raise ValueError(f"verification scope has {len(selected)} nodes, exceeding limit={limit}; select a module")
    if any(n.parent() != p or n.type().category() != hou.sopNodeTypeCategory() for n in selected):
        raise ValueError("all nodes must be direct SOP children of parent")
    reports = [h.cook_node(n) for n in selected]
    errors = [r['path'] for r in reports if not r['ok']]
    warnings = [r['path'] for r in reports if not r['warning_free']]
    geometry = out.geometry()
    summary = h._geo_summary(geometry) if geometry is not None else None
    nonempty = bool(summary and (summary.get('points') or summary.get('prims')))
    fingerprint = h._geometry_fingerprint(out, hou.frame()) if nonempty and not out.errors() else None
    reasons = (['cook_error'] if errors else []) + ([] if nonempty else ['empty_output'])
    result = {'ok': not reasons, 'output': out.path(), 'failure_reasons': reasons,
            'parent': p.path(), 'frame': float(hou.frame()),
            'checked_at': time.time(), 'scope': 'direct_children' if nodes is None else 'explicit_nodes',
            'scope_signature': hashlib.sha256('\n'.join(sorted(n.path() for n in selected)).encode()).hexdigest(),
            'checked_nodes': [n.path() for n in selected], 'node_count': len(selected),
            'ok': not errors and nonempty, 'warning_free': not warnings,
            'healthy': not errors and not warnings and nonempty, 'nonempty': nonempty,
            'error_nodes': errors, 'warning_nodes': warnings,
            'issues': [r for r in reports if not r['healthy']], 'geometry': summary,
            'output_fingerprint': fingerprint, 'semantic_status': 'unverified',
            'next_action': ('Fix the explicit output/cook errors, then rerun this checkpoint; do not substitute a different output without revisiting the deliverable.' if reasons else
                            'Resolve or explicitly explain warning nodes before handoff.' if warnings else
                            'Cook/output checkpoint passed; relationship and visual acceptance remain separate.'),
            'note': 'Cook/geometry evidence only; no assertion of relationships, art quality or unsampled HDA internals.'}
    if reasons and require_valid:
        raise h.CheckpointError(f'verify_network failed: {reasons}; output={out.path()}; errors={errors}. {result["next_action"]}', result)
    return result


def build_module(parent, nodes: list, output: str, dry_run: bool = False, interfaces=None) -> dict:
    """Create a small new SOP module; never overwrite existing nodes or flags.

    Specs: {name, type, parms?, inputs?}. Inputs reference earlier specs or
    existing direct children. Exact input indices follow list order. Static
    type/parm/input preflight runs before creation; dry_run does not create a
    scratch node and cannot prove dynamic menus/VEX/cook. On failure only newly
    created nodes are removed, including headless (external I/O not reversible).
    """
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
    specs, known = [], set(existing)
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
        allowed = {c['name'] for c in card['parameters']}
        allowed.update(k for c in card['parameters'] for k in c.get('components', []))
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f'{name}: unknown parameter(s) {sorted(unknown)}; available parameters={sorted(allowed)}; use node_info(parent,type,parm_filter=...)')
        for parameter in card['parameters']:
            if parameter['name'] in values and parameter.get('menu') and not parameter.get('menu_dynamic'):
                value = values[parameter['name']]
                tokens = [item['token'] for item in parameter['menu']]
                if not isinstance(value, dict) and not (isinstance(value, str) and value in tokens) and not (type(value) is int and 0 <= value < len(tokens)):
                    raise ValueError(f'{name}/{parameter["name"]}: invalid menu value {value!r}; tokens={tokens}')
        if len(inputs) > card['max_inputs']:
            raise ValueError(f'{name}: too many input slots ({len(inputs)} > {card["max_inputs"]})')
        for source in inputs:
            if source is None:
                continue  # explicit empty input; e.g. Wrangle lookup on input 1
            if not isinstance(source, str) or source not in known:
                raise ValueError(f'{name}: input {source!r} must be an earlier spec or existing child name')
        known.add(name)
        specs.append({**spec, 'type': card['type'], 'parms': values, 'inputs': inputs})
    if output not in {s['name'] for s in specs}:
        raise ValueError('output must name one of the newly created nodes')
    if dry_run:
        return {'valid': True, 'dry_run': True, 'parent': p.path(), 'node_count': len(specs),
                'output': output, 'interface_status': 'unverified' if interfaces is not None else 'not_requested',
                'note': 'Static preflight only; VEX, dynamic menus, cooking and interface geometry remain unverified.'}
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
                h.set_parms(n, spec['parms'])
        validation = verify_network(p, output=created[output], nodes=list(created.values()))
        if not validation['ok']:
            raise RuntimeError(f'module cook/output failed: {validation["issues"]}; nonempty={validation["nonempty"]}')
        interface_checks = h.geo_check_interfaces(created[output], interfaces) if interfaces is not None else None
        if interface_checks is not None and not interface_checks['ok']:
            raise h.CheckpointError('build_module interface contract failed/unverified; new module removed',
                                    {**validation,'ok':False,'failure_reasons':['interface_contract'],
                                     'interface_checks':interface_checks})
        return {'valid': True, 'dry_run': False, 'parent': p.path(),
                'created': {name: n.path() for name, n in created.items()}, 'validation': validation,
                **({'interface_checks':interface_checks} if interfaces is not None else {})}
    except BaseException:
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
