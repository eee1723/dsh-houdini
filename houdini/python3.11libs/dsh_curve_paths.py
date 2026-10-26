"""Structured native curve plans and bounded polyline envelope observations.

Plans contain ordinary Add/Curve/Resample nodes for build_module. Diagnostics
measure the actual selected Polygon line segments, never a sampled smooth curve
or a claim about a downstream Sweep mesh. Called on the Bridge owning thread.
"""
from __future__ import annotations

import math
import re


def _number(value, label, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + ' must be a finite number')
    value = float(value)
    if minimum is not None and value < minimum:
        raise ValueError(label + ' must be >= ' + str(minimum))
    return value


def _name(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value):
        raise ValueError(label + ' must be a direct child/parameter identifier')
    return value


CURVE_PATH_EXAMPLE = {
    'name': 'lead', 'controller': 'CTRL', 'segment_length': 0.005,
    'anchors': [
        {'name': 'plug', 'position': [{'parm': 'plug_x'}, 0.8, 0], 'handle': [0, 0, 0.08]},
        {'name': 'rest', 'position': [0.25, 0.79, 0.2], 'handle': [0.08, 0, 0]},
        {'name': 'probe', 'position': [0.5, 0.79, 0.15], 'handle': [0, 0, -0.04]},
    ],
}


def curve_path_plan(spec):
    """Plan one open C1 cubic Bezier path from named anchors and handle offsets."""
    if not isinstance(spec, dict) or set(spec) - {'name', 'controller', 'anchors', 'segment_length'}:
        raise ValueError('unsupported curve_path spec fields')
    name = _name(spec.get('name'), 'name')
    ctrl = _name(spec.get('controller', 'CTRL'), 'controller')
    anchors = spec.get('anchors')
    if not isinstance(anchors, list) or not 2 <= len(anchors) <= 32:
        raise ValueError('anchors requires 2..32 named anchors')

    def scalar(value, label):
        if isinstance(value, dict) and set(value) == {'parm'}:
            return 'ch("../%s/%s")' % (ctrl, _name(value['parm'], label))
        return _number(value, label)

    def vector(value, label):
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ValueError(label + ' requires three scalar components')
        return [scalar(v, label) for v in value]

    def value(a, b=0.0, sign=1):
        if isinstance(a, float) and isinstance(b, float):
            return a + sign * b
        return {'expression': '(%s)%s(%s)' % (a, '+' if sign == 1 else '-', b),
                'language': 'hscript'}

    parsed, seen = [], set()
    for item in anchors:
        if not isinstance(item, dict) or set(item) != {'name', 'position', 'handle'}:
            raise ValueError('each anchor requires exactly name, position, handle')
        key = _name(item['name'], 'anchor name')
        if key in seen:
            raise ValueError('anchor names must be unique')
        seen.add(key)
        parsed.append((key, vector(item['position'], 'position'), vector(item['handle'], 'handle')))
    length = scalar(spec.get('segment_length', 0.005), 'segment_length')
    if isinstance(length, float) and length <= 0:
        raise ValueError('segment_length must be positive')
    positions, mapping = [], []
    for index, (key, position, handle) in enumerate(parsed):
        row = {'name': key, 'anchor_point': len(positions)}
        positions.append([value(v) for v in position])
        if index < len(parsed) - 1:
            row['out_handle_point'] = len(positions)
            positions.append([value(v, h) for v, h in zip(position, handle)])
            next_position, next_handle = parsed[index + 1][1:]
            positions.append([value(v, h, -1) for v, h in zip(next_position, next_handle)])
        if index:
            row['in_handle_point'] = row['anchor_point'] - 1
        mapping.append(row)
    parms = {'points': len(positions), 'prims': 1, 'prim0': '0-%d' % (len(positions) - 1), 'closed0': False}
    for index, position in enumerate(positions):
        parms['usept%d' % index] = True
        for axis, component in zip('xyz', position):
            parms['pt%d%s' % (index, axis)] = component
    source, curve, sampled = (name + suffix for suffix in ('_CONTROLS', '_CURVE', '_SAMPLED'))
    nodes = [
        {'name': source, 'type': 'add', 'parms': parms},
        {'name': curve, 'type': 'curve::2.0', 'inputs': [source],
         'parms': {'outputtype': 'bezier', 'order': 4, 'convertcurves': True}},
        {'name': sampled, 'type': 'resample', 'inputs': [curve],
         'parms': {'length': length if isinstance(length, float) else {'expression': length, 'language': 'hscript'}}},
    ]
    return {'kind': 'curve_path', 'nodes': nodes, 'output': sampled,
            'required_outputs': [source, curve, sampled], 'anchors': mapping,
            'edit_nodes': {'control_points': source, 'native_curve': curve, 'polyline': sampled},
            'scope': 'Open cubic Bezier: shared anchor and symmetric handle offsets give C1 joins before native edits. '
                     'Handle is an outgoing control-point displacement in SOP local units, not a unit direction. '
                     'Zero handles have no regular tangent. Resample approximates the smooth path; no obstacle, '
                     'self-clearance, bend-radius, length or final Sweep certification. Numeric or {parm:name} '
                     'components reference one existing controller; no geometry projection or inferred anchors.'}


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


_FULL_DOMAIN = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))


def _clip_domain(domain, coefficients):
    """Clip the (left_u,right_u) square by a linear >=0 half-plane."""
    if not domain:
        return []
    a, b, c = coefficients
    result = []
    previous = domain[-1]
    before = a * previous[0] + b * previous[1] + c
    for current in domain:
        after = a * current[0] + b * current[1] + c
        if (before < 0) != (after < 0):
            fraction = before / (before - after)
            result.append(tuple(x + fraction * (y - x) for x, y in zip(previous, current)))
        if after >= 0:
            result.append(current)
        previous, before = current, after
    return result


def _segment_distance(p, q, r, s, domain=_FULL_DOMAIN):
    """Closest points on finite nondegenerate segments, including parallel ones.

    Minimize the convex quadratic over a convex parameter-domain polygon:
    its interior stationary point when nonparallel, plus each boundary minimum.
    The domain may exclude truly local same-curve point pairs; it does not
    discard an entire long segment because just its nearest endpoints are local.
    """
    u, v, w = _sub(q, p), _sub(s, r), _sub(p, r)
    candidates = list(domain)
    for start, end in zip(domain, (*domain[1:], domain[0])):
        direction = (end[0] - start[0], end[1] - start[1])
        offset = tuple(wi + start[0] * ui - start[1] * vi for wi, ui, vi in zip(w, u, v))
        delta = tuple(direction[0] * ui - direction[1] * vi for ui, vi in zip(u, v))
        norm = _dot(delta, delta)
        fraction = max(0.0, min(1.0, -_dot(offset, delta) / norm)) if norm else 0.0
        candidates.append(tuple(x + fraction * dx for x, dx in zip(start, direction)))
    cross = _cross(u, v)
    determinant = _dot(cross, cross)
    area_twice = sum(start[0] * end[1] - start[1] * end[0]
                     for start, end in zip(domain, (*domain[1:], domain[0])))
    if determinant > 0.0 and area_twice > 0.0:
        # Cross products avoid the cancellation in a*c-b*b for near-parallel
        # crossing segments. Endpoints alone would miss their interior contact.
        t, z = -_dot(_cross(w, v), cross) / determinant, -_dot(_cross(w, u), cross) / determinant
        # All clipped polygons retain counterclockwise winding. A stationary
        # point outside the domain must not defeat the arc-distance exclusion.
        inside = 0 <= t <= 1 and 0 <= z <= 1 and all(
            (end[0] - start[0]) * (z - start[1]) - (end[1] - start[1]) * (t - start[0]) >= 0
            for start, end in zip(domain, (*domain[1:], domain[0])))
        if inside:
            candidates.append((t, z))
    best = None
    for t, z in candidates:
        left = tuple(x + t * dx for x, dx in zip(p, u))
        right = tuple(x + z * dx for x, dx in zip(r, v))
        distance = math.dist(left, right)
        if best is None or distance < best[0]:
            best = (distance, t, z, left, right)
    return best


def geo_curve_clearance(node, radius, *, group=None, clearance=0.0, self_exclusion=None,
                        max_segments=2048, max_pairs=500000, max_results=16):
    """Full segment-pair clearance of selected OPEN Polygon curves and radii.

    radius is a positive scalar or the name of a positive scalar primitive
    radius attribute (constant per curve). group is one exact primitive group.
    All selected primitives must be open Polygons; Bezier/NURBS/closed faces,
    packed and degenerate segments return unverified, never sampled or ignored.
    A geometric loop may repeat its first point; its seam is recognized only
    when the endpoint positions are exactly equal.

    Measures finite segment closest points and center distance minus both
    radii in SOP-local units. clearance is the required extra envelope gap.
    Same-curve POINT pairs within self_exclusion arc distance are omitted by
    clipping each segment pair's parameter domain; long adjacent/backtracking
    segments still have their nonlocal parts checked. None uses
    pi*(that_curve_radius+clearance/2), a half-circle arc at the envelope's
    effective radius. The returned exclusion/coverage is essential: no local curvature,
    knot, obstacle, downstream Sweep polygon or smooth-curve certification.
    Pair/segment budgets return unverified before measuring any pair; no
    sampling, mutations, native viewport edits or automatic rerouting.
    """
    import hou
    import dsh_node_access
    from dsh_cook_control import require_evaluation
    clearance = _number(clearance, 'clearance', minimum=0)
    if self_exclusion is not None:
        self_exclusion = _number(self_exclusion, 'self_exclusion', minimum=0)
    if group is not None and (not isinstance(group, str) or not group):
        raise ValueError('group must be one exact nonempty primitive group name')
    for key, val, maximum in [('max_segments', max_segments, 8192), ('max_pairs', max_pairs, 2000000), ('max_results', max_results, 64)]:
        if type(val) is not int or not 1 <= val <= maximum:
            raise ValueError(key + ' must be an integer in 1..' + str(maximum))
    attrib_name = radius if isinstance(radius, str) and radius else None
    if attrib_name is None:
        radius = _number(radius, 'radius')
        if radius <= 0:
            raise ValueError('radius must be positive')
    n = dsh_node_access._resolve(node)
    if n.type().category() != hou.sopNodeTypeCategory():
        raise ValueError('geo_curve_clearance requires a SOP output')
    require_evaluation('geo_curve_clearance')
    g = n.geometry()
    if g is None or n.errors():
        raise ValueError('geo_curve_clearance requires error-free SOP geometry')
    selection = g.findPrimGroup(group) if group is not None else None
    if group is not None and selection is None:
        raise ValueError('missing primitive group: ' + group)
    prims = selection.prims() if selection is not None else g.prims()
    base = {'node': n.path(), 'group': group, 'scope': 'selected actual open Polygon line segments and constant-per-curve radius envelopes; '
            'not smooth curves, final Sweep polygons, local bend validity or obstacle clearance',
            'source_primitives': len(g.prims()), 'selected_primitives': len(prims),
            'required_clearance': clearance, 'radius_source': {'primitive_attribute': attrib_name} if attrib_name else {'constant': radius}}

    def unknown(reason, **details):
        return {**base, 'status': 'unverified', 'ok': False, 'reason': reason, **details}

    if not prims:
        return unknown('empty_selection')
    attrib = g.findPrimAttrib(attrib_name) if attrib_name else None
    if attrib_name and (attrib is None or attrib.size() != 1 or attrib.dataType() not in (hou.attribData.Float, hou.attribData.Int)):
        raise ValueError('radius attribute must be a scalar numeric primitive attribute')
    segments, curves = [], []
    for prim in prims:
        if prim.type() != hou.primType.Polygon or prim.isClosed():
            return unknown('requires_open_polygon_curves', primitive=prim.number(), primitive_type=prim.type().name())
        if len(segments) + max(0, prim.numVertices() - 1) > max_segments:
            return unknown('segment_budget_exceeded', max_segments=max_segments,
                           observed_segments_at_least=len(segments) + max(0, prim.numVertices() - 1))
        points = [tuple(float(v) for v in pt.position()) for pt in prim.points()]
        if len(points) < 2 or not all(math.isfinite(v) for p in points for v in p):
            return unknown('invalid_curve_points', primitive=prim.number())
        rad = _number(prim.attribValue(attrib), 'radius attribute') if attrib else radius
        if rad <= 0:
            raise ValueError('radius attribute must be positive on every selected curve')
        length, first = 0.0, len(segments)
        for index, (p, q) in enumerate(zip(points, points[1:])):
            span = math.dist(p, q)
            if span == 0:
                return unknown('degenerate_segment', primitive=prim.number(), segment=index)
            segments.append({'primitive': prim.number(), 'segment': index, 'p': p, 'q': q,
                             'start': length, 'end': length + span, 'radius': rad})
            length += span
            if len(segments) > max_segments:
                return unknown('segment_budget_exceeded', max_segments=max_segments, observed_segments_at_least=len(segments))
        curves.append({'primitive': prim.number(), 'segments': len(segments) - first, 'length': length,
                       'geometric_loop': points[0] == points[-1], 'radius': rad,
                       'self_exclusion': self_exclusion if self_exclusion is not None else math.pi * (rad + clearance / 2)})
    by_prim = {c['primitive']: c for c in curves}

    def pair_domain(a, b):
        if a['primitive'] != b['primitive']:
            return _FULL_DOMAIN
        curve = by_prim[a['primitive']]
        length_a, length_b = a['end'] - a['start'], b['end'] - b['start']
        offset = b['start'] - a['start']
        # Arc separation is affine in (left segment u, right segment u).
        # Exclude local parameter regions, not whole coarse segment pairs.
        domain = _clip_domain(_FULL_DOMAIN, (-length_a, length_b, offset - curve['self_exclusion']))
        if curve['geometric_loop']:
            domain = _clip_domain(domain, (length_a, -length_b, curve['length'] - curve['self_exclusion'] - offset))
        return domain

    all_pairs = len(segments) * (len(segments) - 1) // 2
    coverage = {'segments': len(segments), 'all_pairs': all_pairs, 'excluded_local_self_pairs': None,
                'partially_clipped_self_pairs': None, 'eligible_pairs': None, 'curves': curves, 'measured_pairs': 0,
                'unverified_scope': ['excluded local self neighborhoods', 'unselected primitives', 'smooth input curve between samples',
                                     'downstream swept mesh', 'obstacles and connector contact']}
    # Bound even the exclusion scan. The budget counts candidate pairs before
    # local-neighborhood exclusion, not only the expensive distance queries.
    if all_pairs > max_pairs:
        return unknown('pair_budget_exceeded', coverage=coverage, max_pairs=max_pairs)
    worst, failures, measured, excluded_count, partial_count = [], 0, 0, 0, 0
    for i, a in enumerate(segments):
        for b in segments[i + 1:]:
            domain = pair_domain(a, b)
            if not domain:
                excluded_count += 1
                continue
            partial_count += tuple(domain) != _FULL_DOMAIN
            distance, t, u, left, right = _segment_distance(a['p'], a['q'], b['p'], b['q'], domain)
            measured += 1
            if not math.isfinite(distance):
                coverage['measured_pairs'] = measured
                return unknown('nonfinite_distance', coverage=coverage)
            gap = distance - a['radius'] - b['radius']
            # Only floating-point arithmetic roundoff, not a modeling tolerance.
            roundoff = 16 * math.ulp(max(distance, a['radius'] + b['radius'], clearance))
            failed = gap < clearance - roundoff
            failures += int(failed)
            row = {'left': {'primitive': a['primitive'], 'segment': a['segment'], 'segment_u': t, 'position': list(left),
                            'path_distance': a['start'] + t * (a['end'] - a['start'])},
                   'right': {'primitive': b['primitive'], 'segment': b['segment'], 'segment_u': u, 'position': list(right),
                             'path_distance': b['start'] + u * (b['end'] - b['start'])},
                   'centerline_distance': distance, 'envelope_gap': gap, 'roundoff_tolerance': roundoff,
                   'violates_clearance': failed}
            worst.append(row)
            if len(worst) > max_results:
                worst.sort(key=lambda r: r['envelope_gap'])
                worst.pop()
    worst.sort(key=lambda r: r['envelope_gap'])
    coverage.update({'measured_pairs': measured, 'eligible_pairs': measured,
                     'excluded_local_self_pairs': excluded_count, 'partially_clipped_self_pairs': partial_count})
    if not measured:
        return unknown('no_nonlocal_pairs', coverage=coverage)
    return {**base, 'status': 'fail' if failures else 'pass', 'ok': not failures, 'coverage': coverage,
            'min_envelope_gap': worst[0]['envelope_gap'], 'violation_pairs': failures,
            'worst_pairs': worst, 'truncated_results': measured > len(worst)}
