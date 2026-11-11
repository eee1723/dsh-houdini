"""Actual HOM multi-frame numerical diagnostics; no GUI, model or live attachment."""
from pathlib import Path
import json
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge
import dsh_geometry_queries as query

parent = hou.node('/obj').createNode('geo', 'frame_diff_fixture', run_init_scripts=False)
source = '''
node = hou.pwd()
g = node.geometry()
g.clear()
f = node.evalParm('probe_frame')
mode = MODE
if mode == 'error' and f == 3:
    raise hou.NodeError('owned frame 3 cook failure')
if mode == 'baseline_error' and f == 1:
    raise hou.NodeError('owned baseline cook failure')
if mode == 'empty':
    pass
else:
    g.addAttrib(hou.attribType.Point, 'id', 0)
    if mode == 'missing' and f == 3:
        pass
    elif mode == 'type' and f == 3:
        g.addAttrib(hou.attribType.Point, 'measure', '')
    else:
        g.addAttrib(hou.attribType.Point, 'measure', 0.0)
    positions = [(0,0,0), (2,0,0), (2,1,0), (0,1,0)]
    order = list(range(4))
    if mode == 'topology' and f == 3:
        order = order[:3]
    if mode == 'reorder' and f == 3:
        order.reverse()
    points = {}
    for i in order:
        p = g.createPoint()
        pos = positions[i]
        p.setPosition((pos[0] + (f if mode == 'moving' else 0), pos[1], pos[2]))
        p.setAttribValue('id', i)
        attribute = g.findPointAttrib('measure')
        if attribute is not None:
            p.setAttribValue(attribute, 'x' if attribute.dataType() == hou.attribData.String else
                            float('nan') if mode == 'nonfinite' and f == 3 else float(i))
        points[i] = p
    polygon = g.createPolygon()
    for i in sorted(points):
        polygon.addVertex(points[i])
'''


def make(mode):
    node = parent.createNode('python', mode)
    node.addSpareParmTuple(hou.FloatParmTemplate('probe_frame', 'Probe Frame', 1))
    node.parm('probe_frame').setExpression('$FF', hou.exprLanguage.Hscript)
    node.parm('python').set(source.replace('MODE', repr(mode)))
    return node


nodes = {mode: make(mode) for mode in ('static', 'moving', 'topology', 'reorder', 'error', 'baseline_error', 'missing', 'type', 'empty', 'nonfinite')}
hou.setFrame(17.25)
original_frame = float(hou.frame())


def compare(node, targets, **kwargs):
    result = query.geo_frame_diff(node, 1, targets, **kwargs)
    assert float(hou.frame()) == original_frame, 'geometryAtFrame must not move the scene frame'
    return result


static = compare(nodes['static'], [2, 3, 4])
assert static['status'] == 'observed' and static['comparisons'] == {'compared': 3, 'not_comparable': 0, 'error': 0}
assert all(row['max_delta'] == 0 and row['unchanged_pct'] == 100 for row in static['results'])
assert static['semantic_status'] == 'unverified'
moving = compare(nodes['moving'], [2, 3, 4])
assert [row['max_delta'] for row in moving['results']] == [1, 2, 3]
assert [row['component_delta']['mean'] for row in moving['results']] == [[1, 0, 0], [2, 0, 0], [3, 0, 0]]
ordered = compare(nodes['moving'], (4.5, 2, 4.5))
assert ordered['frames_b'] == [4.5, 2, 4.5] and [row['max_delta'] for row in ordered['results']] == [3.5, 1, 3.5]

# Existing scalar consumers receive exactly the previous-shaped dictionaries.
for mode in ('static', 'moving', 'topology', 'type'):
    batch = compare(nodes[mode], [2, 3, 4])
    for row in batch['results']:
        scalar = compare(nodes[mode], row['frame_b'])
        assert {key: value for key, value in row.items() if key != 'status'} == scalar, (mode, row, scalar)

topology = compare(nodes['topology'], [2, 3, 4])
assert [row['status'] for row in topology['results']] == ['compared', 'not_comparable', 'compared']
assert topology['comparisons'] == {'compared': 2, 'not_comparable': 1, 'error': 0}
assert 'max_delta' not in topology['results'][1]
reordered = compare(nodes['reorder'], [2, 3])
assert reordered['results'][1]['comparable'] and reordered['results'][1]['max_delta'] > 0
assert reordered['correspondence'] == 'point_number' and 'stable' in reordered['scope']

missing = compare(nodes['missing'], [2, 3, 4], attrib='measure')
assert [row['status'] for row in missing['results']] == ['compared', 'error', 'compared']
assert 'measure' in missing['results'][1]['error']
nonfinite = compare(nodes['nonfinite'], [2, 3, 4], attrib='measure')
assert [row['status'] for row in nonfinite['results']] == ['compared', 'error', 'compared']
assert 'nonfinite' in nonfinite['results'][1]['error']
empty = compare(nodes['empty'], [2])
assert empty['comparisons'] == {'compared': 0, 'not_comparable': 1, 'error': 0}
assert empty['results'][0]['reason'] == 'no points to compare' and 'unchanged_pct' not in empty['results'][0]

failed_frame = compare(nodes['error'], [2, 3, 4])
assert [row['status'] for row in failed_frame['results']] == ['compared', 'error', 'compared'], failed_frame
assert failed_frame['results'][1]['frame_b'] == 3 and failed_frame['results'][1]['error']
assert 'node_errors' not in failed_frame['results'][1], 'another frame\'s cached node errors are not this query\'s exception'
try:
    compare(nodes['baseline_error'], [2, 3])
except (hou.Error, ValueError) as error:
    assert '基线帧' in str(error) or 'baseline cook failure' in str(error)
else:
    raise AssertionError('A failed baseline was accepted')
assert float(hou.frame()) == original_frame

# The underlying HOM call remains real. Count only to prove that adding frames
# does not re-cook/re-read the baseline at every comparison.
resolved = query.dsh_node_access._resolve
class CountingNode:
    def __init__(self, node): self.node, self.frames = node, []
    def __getattr__(self, name): return getattr(self.node, name)
    def geometryAtFrame(self, frame):
        self.frames.append(frame)
        return self.node.geometryAtFrame(frame)
counted = CountingNode(nodes['moving'])
query.dsh_node_access._resolve = lambda _: counted
try:
    result = query.geo_frame_diff(counted, 1, [2, 3, 4])
    assert counted.frames == [1, 2, 3, 4] and result['results'][2]['max_delta'] == 3
    for bad in ([], list(range(17)), [2, math.nan], [math.inf]):
        before = list(counted.frames)
        try: query.geo_frame_diff(counted, 1, bad)
        except ValueError: pass
        else: raise AssertionError('Invalid target frames were accepted')
        assert counted.frames == before, 'Invalid input must not start geometry evaluation'
    for bad in (math.nan, math.inf, -1):
        before = list(counted.frames)
        try: query.geo_frame_diff(counted, 1, [2], tolerance=bad)
        except ValueError: pass
        else: raise AssertionError('Invalid tolerance was accepted')
        assert counted.frames == before
finally:
    query.dsh_node_access._resolve = resolved

def traced(node):
    result = bridge.run_code(f"__result__=geo_frame_diff({node.path()!r},1,[2,3,4])", owner_session='frame-diff-fixture', owner_call='observe')
    assert result['ok'], result
    return result, next(row for row in result['verbs'] if row['verb'] == 'geo_frame_diff')
successful, entry = traced(nodes['moving'])
assert 'check_status' not in entry and successful['result']['results'][2]['max_delta'] == 3
partial, entry = traced(nodes['topology'])
assert entry['check_status'] == 'unverified' and partial['result']['comparisons']['compared'] == 2
error, entry = traced(nodes['error'])
assert entry['check_status'] == 'failed' and error['result']['comparisons']['compared'] == 2
setup = bridge.run_code("g=tab_create('/obj','geo',name='frame_diff_owned')\nbox=tab_create(g,'box',name='shape')",
                        owner_session='frame-diff-fixture', owner_call='setup')
assert setup['ok'], setup
mixed = bridge.run_code(f"set_parm('/obj/frame_diff_owned/shape','sizex',2)\n__result__=geo_frame_diff({nodes['error'].path()!r},1,[2,3,4])",
                        owner_session='frame-diff-fixture', owner_call='mixed')
assert mixed['ok'] and mixed['result']['comparisons']['error'] == 1
assert hou.node('/obj/frame_diff_owned/shape').evalParm('sizex') == 2, 'partial read diagnostics must not roll back a valid earlier edit'
readonly = bridge.run_code(f"__result__=geo_frame_diff({nodes['moving'].path()!r},1,[2,3])",
                           owner_session='frame-diff-fixture', owner_call='inspect', read_only=True)
assert readonly['ok'] and readonly['result']['comparisons']['compared'] == 2
assert float(hou.frame()) == original_frame
print(json.dumps({'ok': True, 'houdini': hou.applicationVersionString(), 'scene_frame': original_frame,
    'baseline_reused': True, 'scalar_fields_preserved': True, 'static_and_moving': True,
    'topology_and_type_incomparability': True, 'failed_target_then_later_success': True,
    'point_number_reordering_not_certified': True, 'ledger_partial_scope': True}))
