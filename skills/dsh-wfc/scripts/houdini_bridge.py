"""Thin resolved-WFC JSON to native Houdini instance-network adapter.

Import this module inside houdini_exec and pass api=globals(). All scene writes
use the injected DSH verbs; this module neither imports HOM nor solves WFC.
Prototype sources must be direct children of the destination SOP network.
"""
from __future__ import annotations

import json
from pathlib import Path
import re


_POINT_SOURCE = r'''import json
from pathlib import Path

path = Path(hou.pwd().parm("instances").evalAsString())
data = json.loads(path.read_text(encoding="utf-8"))
if data.get("schema_version") != 1 or data.get("status") != "resolved":
    raise ValueError("Expected resolved WFC schema_version 1: " + str(path))
rows = data.get("instances")
if not isinstance(rows, list) or not rows:
    raise ValueError("Resolved WFC contains no instances")
geo = hou.pwd().geometry()
vector = lambda name, default: geo.addAttrib(hou.attribType.Point, name, default)
vector("pivot", (0.0, 0.0, 0.0))
vector("scale", (1.0, 1.0, 1.0))
vector("orient", (0.0, 0.0, 0.0, 1.0))
strings = ("cell_id", "asset_key", "variant", "wfc_piece", "asset")
for name in strings:
    geo.addAttrib(hou.attribType.Point, name, "")
for row in rows:
    point = geo.createPoint()
    for name in ("P", "pivot", "scale", "orient"):
        point.setAttribValue(name, tuple(float(v) for v in row[name]))
    for name in strings:
        value = row["piece"] if name == "wfc_piece" else row[name]
        point.setAttribValue(name, str(value))
'''


def _read_instances(filename):
    path = Path(filename).resolve(strict=True)
    if not path.is_file():
        raise ValueError("Resolved WFC path is not a file: " + str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("status") != "resolved":
        raise ValueError("Expected resolved WFC schema_version 1")
    rows = data.get("instances")
    if not isinstance(rows, list) or not rows or data.get("cell_count") != len(rows):
        raise ValueError("Resolved WFC instance count is empty or inconsistent")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Every resolved WFC instance must be an object")
        for name in ("P", "pivot", "scale"):
            value = row.get(name)
            if not isinstance(value, list) or len(value) != 3:
                raise ValueError("Instance requires a three-component " + name)
        orient = row.get("orient")
        if not isinstance(orient, list) or len(orient) != 4:
            raise ValueError("Instance requires a four-component orient")
        for name in ("cell_id", "asset_key", "variant", "piece", "asset"):
            if not isinstance(row.get(name), str) or not row[name]:
                raise ValueError("Instance requires a nonempty " + name)
    return path, data


def _name(prefix, value):
    suffix = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return prefix + "_" + (suffix or "piece")


def build_instance_network(parent, instances_path, prototypes=None, *, api):
    """Build points, or native packed Copy to Points when prototypes are given.

    prototypes maps every selected ``piece`` to an existing direct-child SOP.
    The adapter adds name/pack nodes but does not import assets or change sources.
    Returns the actual node paths. Pass the houdini_exec namespace as ``api``.
    """
    if not isinstance(api, dict):
        raise ValueError("Pass the houdini_exec namespace with api=globals()")
    for verb in ("tab_create", "create_spare_parms", "set_parms", "verify_network", "sop_set_output"):
        if not callable(api.get(verb)):
            raise ValueError("Missing injected DSH verb: " + verb)
    create = api["tab_create"]
    path, data = _read_instances(instances_path)
    layout = create(parent, "python", "WFC_POINTS")
    api["create_spare_parms"](layout, spec=[{
        "type": "string", "name": "instances", "label": "Resolved WFC JSON",
        "default": path.as_posix(),
    }])
    api["set_parms"](layout, {"python": _POINT_SOURCE, "maintainstate": False})
    packed = []
    if prototypes is not None:
        if not isinstance(prototypes, dict):
            raise ValueError("prototypes must map piece IDs to direct-child SOPs")
        expected = {row["piece"] for row in data["instances"]}
        if set(prototypes) != expected:
            raise ValueError("Prototype IDs differ from resolved pieces: " +
                             repr({"missing": sorted(expected - set(prototypes)),
                                   "extra": sorted(set(prototypes) - expected)}))
        for piece in sorted(prototypes):
            identity = json.dumps(piece)
            tagged = create(parent, "attribwrangle", _name("PIECE", piece), inputs=[prototypes[piece]],
                            parms={"class": "primitive",
                                   "snippet": "s@name = {0}; s@wfc_piece = {0};".format(identity)})
            packed.append(create(parent, "pack", _name("PACK", piece), inputs=[tagged],
                                 parms={"nameattribute": "name", "transfer_attributes": "name wfc_piece"}))
        source = packed[0] if len(packed) == 1 else create(parent, "merge", "PROTOTYPES", inputs=packed)
        output = create(parent, "copytopoints", "OUT_WFC", inputs=[source, layout], parms={
            "useidattrib": True, "idattrib": "wfc_piece", "pack": False, "transform": True,
        })
    else:
        output = create(parent, "null", "OUT_WFC_POINTS", inputs=[layout])
    api["verify_network"](parent, output=output)
    api["sop_set_output"](output)
    return {"points": layout.path(), "output": output.path(), "instances": path.as_posix(),
            "prototypes": [node.path() for node in packed], "mode": "instances" if packed else "points"}
