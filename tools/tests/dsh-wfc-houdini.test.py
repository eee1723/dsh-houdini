"""Run inside isolated H21/H22 hython; verify real final unpacked transforms."""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
sys.path.insert(0, str(ROOT / "skills/dsh-wfc/scripts"))
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
         "bounds_min": [-1.5, -0.25, -0.75], "bounds_max": [1.5, 0.25, 0.75]},
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
roof = tab_create(root, 'box', 'roof_source', parms={'sizex': 3.0, 'sizey': 0.5, 'sizez': 1.5})
built = houdini_bridge.build_instance_network(root, %r,
    prototypes={'wall::a': wall, 'roof::b': roof}, api=globals())
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
    for vertex in prim.vertices():
        point = vertex.point()
        by_piece.setdefault(piece, {})[point.number()] = tuple(point.position())
assert set(by_piece) == {'wall::a', 'roof::b'}, by_piece.keys()
__result__ = {'built': built, 'points_only': points_only,
              'by_piece': {key: list(values.values()) for key, values in by_piece.items()},
              'packed_count': len(hou.node(built['output']).geometry().prims()),
              'houdini': hou.applicationVersionString()}
''' % (str(instances), str(instances))
    result = bridge.run_code(code, owner_session="wfc-skill-development", owner_call="adapter-test")
    assert result.get("ok"), result
    facts = result["result"]
    assert facts["packed_count"] == 2, facts
    for row in rows:
        expected = expected_corners(row["bounds_min"], row["bounds_max"], row["pivot"],
                                    row["scale"], row["yaw"], row["P"])
        assert_points(facts["by_piece"][row["piece"]], expected, row["piece"])
    report = {"ok": True, "houdini": hou.applicationVersionString(),
              "scope": ["two distinct packed pieces", "90-degree quaternion", "nonuniform scale",
                        "nonzero source pivot", "points-only output", "final unpacked vertex positions"],
              "packed_primitives": facts["packed_count"], "unpacked_points": 16, "unpacked_primitives": 12}
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
