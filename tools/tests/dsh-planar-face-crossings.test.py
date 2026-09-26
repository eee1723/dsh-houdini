"""Bounded single-face crossing diagnostics; no general mesh-intersection claim."""
import json
import math
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_geometry_observation as o
import dsh_hou_helpers as h


def polygon(coords, indices=None, closed=True):
    geo = hou.Geometry()
    points = []
    for position in coords:
        point = geo.createPoint()
        point.setPosition(position)
        points.append(point)
    face = geo.createPolygon(is_closed=closed)
    for index in indices if indices is not None else range(len(points)):
        face.addVertex(points[index])
    return geo


def inspect(geo):
    return o.polygon_observation(geo, integrity_only=True)


def xz(coords):
    return [(x, 0, z) for x, z in coords]


start = time.perf_counter()
crossed = polygon(xz([(0, 0), (3, 2), (0, 2), (2, 0)]))
report = inspect(crossed)
check = report['planar_face_crossings']
assert check['crossed_faces'] == check['crossing_pairs'] == 1, check
assert check['samples'][0]['edge_indices'] == [0, 2], check
assert all(abs(a-b) < 1e-6 for a, b in zip(check['samples'][0]['position'], [1.2, 0, .8])), check
assert report['risk_status'] == 'needs_review' and 'planar_face_self_crossings' in report['risk_reasons'], report
assert o.polygon_observation(crossed)['planar_face_crossings'] == check
# The face's summed normal may cancel entirely; it still has a definable plane.
balanced = polygon(xz([(0, 0), (2, 2), (0, 2), (2, 0)]))
assert inspect(balanced)['planar_face_crossings']['crossed_faces'] == 1
# Normal direction, axis alignment and ordinary unit scale do not define scope.
for scale in (1e-5, 1, 1e5):
    tilted = polygon([(scale*(x+2*z), scale*(3*x-z), scale*(x+z))
                      for x, z in [(0, 0), (3, 2), (0, 2), (2, 0)]])
    assert inspect(tilted)['planar_face_crossings']['crossed_faces'] == 1

concave = polygon(xz([(0, 0), (3, 0), (3, 3), (1.5, 1), (0, 3)]))
assert inspect(concave)['planar_face_crossings']['crossed_faces'] == 0
# A repeated bridge to a real hole is legal and is not a strict interior crossing.
bridge = polygon(xz([(0, 0), (4, 0), (4, 4), (0, 4), (1, 1), (1, 3), (3, 3), (3, 1)]),
                 [0, 1, 2, 3, 0, 4, 5, 6, 7, 4])
bridge_report = inspect(bridge)
assert bridge_report['planar_face_crossings']['crossed_faces'] == 0, bridge_report
assert bridge_report['risk_status'] == 'no_detected_integrity_risk', bridge_report
assert bridge_report['shading_review_status'] == 'needs_visual_review', bridge_report
touch = polygon(xz([(0, 0), (2, 0), (1, 1), (2, 2), (0, 2), (1, 1)]))
assert inspect(touch)['planar_face_crossings']['crossed_faces'] == 0
line = polygon(xz([(0, 0), (3, 2), (0, 2), (2, 0)]), closed=False)
assert inspect(line)['status'] == 'unverified' and 'planar_face_crossings' not in inspect(line)
nonplanar = polygon([(0, 0, 0), (3, 0, 2), (0, 0, 2), (2, .2, 0)])
nonplanar_report = inspect(nonplanar)['planar_face_crossings']
assert nonplanar_report['crossed_faces'] == 0 and nonplanar_report['skipped_faces']['nonplanar'] == 1
collinear = polygon(xz([(0, 0), (1, 0), (2, 0), (3, 0)]))
assert inspect(collinear)['planar_face_crossings']['skipped_faces']['degenerate'] == 1
triangle = polygon(xz([(0, 0), (2, 0), (1, 1)]))
tri_report = o._planar_face_crossings(triangle.prims(), pair_budget=0)
assert tri_report['coverage'] == 'complete_within_scope' and tri_report['triangle_faces'] == 1
assert not any(tri_report['skipped_faces'].values())

# The diagnostic reports bounded coverage rather than inventing a pass from skips.
limited = o._planar_face_crossings(crossed.prims(), pair_budget=1)
assert limited['status'] == 'unverified' and limited['coverage'] == 'partial'
assert limited['tested_edge_pairs'] == 0 and limited['skipped_faces']['pair_budget'] == 1
large_face = polygon(xz([(math.cos(i*math.tau/257), math.sin(i*math.tau/257)) for i in range(257)]))
limited = inspect(large_face)['planar_face_crossings']
assert limited['coverage'] == 'partial' and limited['skipped_faces']['face_vertex_budget'] == 1
dense_face = polygon(xz([(math.cos(i*math.tau/256), math.sin(i*math.tau/256)) for i in range(256)]))
dense = hou.Geometry()
for _ in range(8):
    dense.merge(dense_face)
limited = inspect(dense)['planar_face_crossings']
assert limited['coverage'] == 'partial' and limited['skipped_faces']['pair_budget'] > 0, limited
assert 0 < limited['tested_edge_pairs'] <= 250000 and limited['crossed_faces'] == 0, limited
repeated = hou.Geometry()
for _ in range(10):
    repeated.merge(crossed)
sampled = inspect(repeated)['planar_face_crossings']
assert sampled['crossed_faces'] == 10 and len(sampled['samples']) == 8 and sampled['samples_truncated']

root = h.tab_create('/obj', 'geo', 'planar_face_crossing_fixture')
try:
    with tempfile.TemporaryDirectory(prefix='dsh-planar-faces-') as scratch:
        path = str(pathlib.Path(scratch)/'crossed.bgeo.sc')
        crossed.saveToFile(path)
        source = root.createNode('file', 'source')
        source.parm('file').set(path)
        out = root.createNode('null', 'OUT_ASSET')
        out.setInput(0, source)
        packet = b.run_code(f'__result__=geo_piece_stats({out.path()!r},inspect=True,integrity_only=True)')
        evidence = next(item for item in packet['evidence'] if item.get('verb') == 'geo_piece_stats')
        assert evidence['planar_face_crossings']['crossed_faces'] == 1, evidence
        checkpoint = h.verify_network(root, output=out)
        assert checkpoint['ok'] and checkpoint['healthy'], checkpoint
        assert checkpoint['surface_integrity']['planar_face_crossings']['crossed_faces'] == 1, checkpoint
        assert checkpoint['surface_integrity']['risk_status'] == 'needs_review', checkpoint
        packet = b.run_code(f'__result__=verify_network({root.path()!r},output={out.path()!r})')
        evidence = next(item for item in packet['evidence'] if item.get('verb') == 'verify_network')
        assert evidence['surface_integrity']['planar_face_crossings']['crossed_faces'] == 1, evidence
        assert evidence['ok'] and evidence['healthy'], evidence
    # Typical large quad surface remains inside the edge-pair budget.
    grid = root.createNode('grid')
    grid.parm('rows').set(152)
    grid.parm('cols').set(152)
    grid_start = time.perf_counter()
    grid_report = h.geo_piece_stats(grid, inspect=True, integrity_only=True)
    grid_seconds = time.perf_counter()-grid_start
    assert grid_report['planar_face_crossings']['checked_faces'] == 151*151, grid_report
    assert grid_report['planar_face_crossings']['coverage'] == 'complete_within_scope', grid_report
    assert grid_report['risk_status'] == 'no_detected_integrity_risk', grid_report
finally:
    root.destroy()

print(json.dumps({'version': hou.applicationVersionString(), 'result': 'passed',
                  'quad_faces': 151*151, 'quad_integrity_seconds': grid_seconds,
                  'total_seconds': time.perf_counter()-start}, indent=2))
