"""Run inside isolated H21/H22 hython; verify real final unpacked transforms."""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
sys.path.insert(0, str(ROOT / "skills/houdini-wfc-workflow/scripts"))
import hou
import dsh_bridge as bridge
import houdini_bridge


def expected_corners(bounds_min, bounds_max, anchor, scale, yaw, position):
    angle = math.radians(yaw)
    cosine, sine = math.cos(angle), math.sin(angle)
    result = []
    for corner in itertools.product(*zip(bounds_min, bounds_max)):
        local = [scale[i] * (corner[i] - anchor[i]) for i in range(3)]
        rotated = [cosine * local[0] + sine * local[2], local[1], -sine * local[0] + cosine * local[2]]
        result.append(tuple(position[i] + rotated[i] for i in range(3)))
    return result


def assert_points(actual, expected, label):
    assert len(actual) == len(expected), (label, len(actual), len(expected))
    remaining = list(actual)
    for target in expected:
        nearest = min(remaining, key=lambda value: sum((value[i] - target[i]) ** 2 for i in range(3)))
        error = math.sqrt(sum((nearest[i] - target[i]) ** 2 for i in range(3)))
        assert error < 2e-4, (label, target, nearest, error)
        remaining.remove(nearest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"cell_id": "wall_cell", "asset_key": "wall", "variant": "a", "piece": "wall::a",
         "asset": "native-box-wall", "P": [4.0, 3.0, 5.0], "pivot": [1.0, -0.5, 2.0],
         "scale": [1.25, 2.0, 0.75], "yaw": 90,
         "bounds_min": [-1.0, -0.5, -2.0], "bounds_max": [1.0, 0.5, 2.0]},
        {"cell_id": "roof_cell", "asset_key": "roof", "variant": "b", "piece": "roof::b",
         "asset": "native-box-roof", "P": [-3.0, 2.0, 1.0], "pivot": [0.0, -0.25, 0.0],
         "scale": [0.8, 1.4, 1.1], "yaw": 0,
         "bounds_min": [0.5, -0.25, 0.25], "bounds_max": [3.5, 0.25, 1.75]},
    ]
    for row in rows:
        angle = math.radians(row["yaw"])
        row["orient"] = [0.0, math.sin(angle / 2), 0.0, math.cos(angle / 2)]
    instances = output.parent / (output.stem + "-instances.json")
    instances.write_text(json.dumps({"schema_version": 1, "status": "resolved", "cell_count": 2,
                                     "instances": rows}), encoding="utf-8")
    code = '''
import houdini_bridge
root = tab_create('/obj', 'geo', 'wfc_adapter_test')
wall = tab_create(root, 'box', 'wall_source', parms={'sizex': 2.0, 'sizey': 1.0, 'sizez': 4.0})
roof = tab_create(root, 'box', 'roof_source', parms={'sizex': 3.0, 'sizey': 0.5, 'sizez': 1.5, 'tx': 2.0, 'tz': 1.0})
roof = tab_create(root, 'attribwrangle', 'roof_metadata', inputs=[roof], parms={'class': 'primitive',
    'snippet': 's@name="roof_panel"; s@shop_materialpath="/mat/roof";'})
roof_alt = tab_create(root, 'box', 'roof_alt_source', parms={'sizex': 3.0, 'sizey': 0.5, 'sizez': 2.5, 'tx': 2.0, 'tz': 1.0})
built = houdini_bridge.build_instance_network(root, %r,
    prototypes={'wall::a': wall, 'roof::b': roof, 'roof::c': roof_alt}, api=globals())
unpacked = tab_create(root, 'unpack', 'CHECK_FINAL_GEOMETRY', inputs=[built['output']])
verify_network(root, output=unpacked)
points_only_root = tab_create('/obj', 'geo', 'wfc_points_test')
points_only = houdini_bridge.build_instance_network(points_only_root, %r, api=globals())
points_geo = hou.node(points_only['output']).geometry()
assert len(points_geo.points()) == 2
assert points_geo.point(0).stringAttribValue('wfc_piece') == 'wall::a'
geo = unpacked.geometry()
debug = {}
for path in built['prototypes'] + [built['output'], unpacked.path()]:
    item = hou.node(path).geometry()
    debug[path] = {'points': len(item.points()), 'prims': len(item.prims()),
                   'prim_attribs': [a.name() for a in item.primAttribs()],
                   'names': [p.stringAttribValue('name') for p in item.prims()] if item.findPrimAttrib('name') else []}
assert len(geo.points()) == 16, debug
assert len(geo.prims()) == 12, debug
by_piece = {}
for prim in geo.prims():
    piece = prim.stringAttribValue('wfc_piece')
    if piece == 'roof::b':
        assert prim.stringAttribValue('name') == 'roof_panel'
        assert prim.stringAttribValue('shop_materialpath') == '/mat/roof'
    for vertex in prim.vertices():
        point = vertex.point()
        by_piece.setdefault(piece, {})[point.number()] = tuple(point.position())
assert set(by_piece) == {'wall::a', 'roof::b'}, by_piece.keys()
__result__ = {'built': built, 'points_only': points_only,
              'node_ids': [node.sessionId() for node in root.children()],
              'by_piece': {key: list(values.values()) for key, values in by_piece.items()},
              'identities': [{key: prim.stringAttribValue(key) for key in ('cell_id', 'asset_key', 'variant', 'asset')}
                             for prim in hou.node(built['output']).geometry().prims()],
              'packed_count': len(hou.node(built['output']).geometry().prims()),
              'houdini': hou.applicationVersionString()}
''' % (str(instances), str(instances))
    result = bridge.run_code(code, owner_session="wfc-skill-development", owner_call="adapter-test")
    assert result.get("ok"), result
    facts = result["result"]
    assert facts["packed_count"] == 2, facts
    assert len(facts['built']['prototypes']) == 3, facts
    assert {row["cell_id"]: row for row in facts["identities"]} == {
        row["cell_id"]: {key: row[key] for key in ("cell_id", "asset_key", "variant", "asset")}
        for row in rows}, facts["identities"]
    for row in rows:
        expected = expected_corners(row["bounds_min"], row["bounds_max"], row["pivot"],
                                    row["scale"], row["yaw"], row["P"])
        assert_points(facts["by_piece"][row["piece"]], expected, row["piece"])

    # A prepared library may contain variants unused by the first seed. A later
    # JSON can select one without rebuilding nodes or copying unused prototypes.
    alternate_rows = copy.deepcopy(rows)
    alternate_rows[1].update(piece='roof::c', variant='c', asset='native-box-roof-alt',
                             bounds_min=[0.5, -0.25, -0.25], bounds_max=[3.5, 0.25, 2.25])
    alternate_instances = output.parent / (output.stem + '-preloaded-variant.json')
    alternate_instances.write_text(json.dumps({'schema_version': 1, 'status': 'resolved', 'cell_count': 2,
                                               'instances': alternate_rows}), encoding='utf-8')
    alternate = bridge.run_code('''
set_parms(%r, {'instances': %r})
verify_network('/obj/wfc_adapter_test', output='/obj/wfc_adapter_test/CHECK_FINAL_GEOMETRY')
geo = hou.node('/obj/wfc_adapter_test/CHECK_FINAL_GEOMETRY').geometry()
vertices = {}
for prim in geo.prims():
    if prim.stringAttribValue('wfc_piece') == 'roof::c':
        for vertex in prim.vertices():
            point = vertex.point()
            vertices[point.number()] = tuple(point.position())
packed = hou.node(%r).geometry()
__result__ = {'vertices': list(vertices.values()), 'count': len(packed.prims()),
              'identities': {prim.stringAttribValue('cell_id'): prim.stringAttribValue('variant') for prim in packed.prims()},
              'node_ids': [node.sessionId() for node in hou.node('/obj/wfc_adapter_test').children()]}
''' % (facts['built']['points'], str(alternate_instances), facts['built']['output']),
                                owner_session='wfc-skill-development', owner_call='preloaded-variant')
    assert alternate.get('ok'), alternate
    assert alternate['result']['count'] == 2, alternate
    assert alternate['result']['node_ids'] == facts['node_ids'], alternate
    assert alternate['result']['identities'] == {'wall_cell': 'a', 'roof_cell': 'c'}, alternate
    alt = alternate_rows[1]
    assert_points(alternate['result']['vertices'], expected_corners(alt['bounds_min'], alt['bounds_max'],
                  alt['pivot'], alt['scale'], alt['yaw'], alt['P']), 'preloaded variant')

    # A source-origin change with its measured anchor change must preserve the
    # final installed geometry and stable cell IDs, not just its global bbox.
    changed_rows = copy.deepcopy(rows)
    changed_rows[1]["pivot"] = [2.0, -0.25, 1.0]
    changed_rows[1]["asset"] = "native-box-roof-other-style"
    changed_instances = output.parent / (output.stem + "-other-style.json")
    changed_instances.write_text(json.dumps({"schema_version": 1, "status": "resolved", "cell_count": 2,
                                             "instances": changed_rows}), encoding="utf-8")
    changed = bridge.run_code('''
set_parms('/obj/wfc_adapter_test/roof_source', {'tx': 4.0, 'tz': 2.0})
set_parms(%r, {'instances': %r})
verify_network('/obj/wfc_adapter_test', output='/obj/wfc_adapter_test/CHECK_FINAL_GEOMETRY')
geo = hou.node('/obj/wfc_adapter_test/CHECK_FINAL_GEOMETRY').geometry()
by_piece = {}
for prim in geo.prims():
    piece = prim.stringAttribValue('wfc_piece')
    for vertex in prim.vertices():
        point = vertex.point()
        by_piece.setdefault(piece, {})[point.number()] = tuple(point.position())
__result__ = {'by_piece': {key: list(values.values()) for key, values in by_piece.items()},
              'cells': hou.node(%r).geometry().primStringAttribValues('cell_id')}
''' % (facts['built']['points'], str(changed_instances), facts['built']['output']),
                              owner_session="wfc-skill-development", owner_call="style-change")
    assert changed.get("ok"), changed
    assert set(changed['result']['cells']) == {row['cell_id'] for row in rows}
    for piece in facts['by_piece']:
        assert_points(changed['result']['by_piece'][piece], facts['by_piece'][piece], "style change " + piece)

    # Native Copy to Points otherwise silently drops a newly selected piece.
    missing_rows = copy.deepcopy(rows)
    missing_rows[1]['piece'] = 'roof::not_imported'
    missing_instances = output.parent / (output.stem + "-missing-piece.json")
    missing_instances.write_text(json.dumps({"schema_version": 1, "status": "resolved", "cell_count": 2,
                                             "instances": missing_rows}), encoding="utf-8")
    missing = bridge.run_code('''
set_parms(%r, {'instances': %r})
verify_network('/obj/wfc_adapter_test', output=%r)
''' % (facts['built']['points'], str(missing_instances), facts['built']['output']),
                              owner_session="wfc-skill-development", owner_call="missing-piece")
    assert not missing.get('ok') and 'Missing or empty WFC prototypes' in missing.get('error', ''), missing

    # Validate source edits through the native input dependency, without an
    # external per-instance ledger or reliance on the initial build check.
    empty = bridge.run_code('''
set_parms(%r, {'instances': %r})
empty = tab_create('/obj/wfc_adapter_test', 'null', 'EMPTY_SOURCE')
connect(empty, '/obj/wfc_adapter_test/PIECE_roof_b')
verify_network('/obj/wfc_adapter_test', output=%r)
''' % (facts['built']['points'], str(changed_instances), facts['built']['output']),
                            owner_session="wfc-skill-development", owner_call="empty-source")
    assert not empty.get('ok') and 'Missing or empty WFC prototypes' in empty.get('error', ''), empty

    # Recooks use the same JSON reader as construction, including unique IDs.
    invalid_rows = copy.deepcopy(rows)
    invalid_rows[1]['cell_id'] = invalid_rows[0]['cell_id']
    invalid_instances = output.parent / (output.stem + "-duplicate-cell.json")
    invalid_instances.write_text(json.dumps({"schema_version": 1, "status": "resolved", "cell_count": 2,
                                             "instances": invalid_rows}), encoding="utf-8")
    invalid = bridge.run_code('''
set_parms(%r, {'instances': %r})
verify_network('/obj/wfc_points_test', output=%r)
''' % (facts['points_only']['points'], str(invalid_instances), facts['points_only']['output']),
                              owner_session="wfc-skill-development", owner_call="duplicate-cell")
    assert not invalid.get('ok') and 'Duplicate instance cell_id' in invalid.get('error', ''), invalid
    report = {"ok": True, "houdini": hou.applicationVersionString(),
              "scope": ["two distinct packed pieces", "90-degree quaternion", "nonuniform scale",
                        "nonzero source pivot", "off-center source bounds", "points-only output",
                        "final unpacked vertex positions", "packed cell identity metadata", "style/anchor change",
                        "source part names and material paths retained",
                        "preloaded unused variant selected without rebuilding",
                        "missing piece recook rejected", "emptied source recook rejected", "duplicate cell recook rejected"],
              "packed_primitives": facts["packed_count"], "unpacked_points": 16, "unpacked_primitives": 12}
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
