"""Thin resolved-WFC JSON to native Houdini instance-network adapter.

Import this module inside houdini_exec and pass api=globals(). All scene writes
use the injected DSH verbs; this module neither imports HOM nor solves WFC.
Prototype sources must be direct children of the destination SOP network.
"""
from __future__ import annotations

import json
import inspect
import math
from pathlib import Path
import re


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
    cells = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Every resolved WFC instance must be an object")
        for name, size in (("P", 3), ("pivot", 3), ("scale", 3), ("orient", 4)):
            value = row.get(name)
            if (not isinstance(value, list) or len(value) != size or
                    any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                        for v in value)):
                raise ValueError("Instance requires finite numeric components for " + name)
        if any(v <= 0 for v in row["scale"]):
            raise ValueError("Instance requires positive scale")
        if not math.isclose(sum(v * v for v in row["orient"]), 1.0, abs_tol=1e-6):
            raise ValueError("Instance requires a unit orient quaternion")
        for name in ("cell_id", "asset_key", "variant", "piece", "asset"):
            if not isinstance(row.get(name), str) or not row[name]:
                raise ValueError("Instance requires a nonempty " + name)
        if row["cell_id"] in cells:
            raise ValueError("Duplicate instance cell_id: " + row["cell_id"])
        cells.add(row["cell_id"])
    return path, data


# Embed the same reader in the HIP so recooks validate changed JSON and do not
# need this installed skill module on sys.path after reopening the project.
_POINT_SOURCE = "import json\nimport math\nfrom pathlib import Path\n\n" + inspect.getsource(_read_instances) + r'''
node = hou.pwd()
path, data = _read_instances(node.parm("instances").evalAsString())
rows = data["instances"]
inputs = node.inputs()
if inputs:
    sources = inputs[0].geometry()
    actual = set(sources.primStringAttribValues("wfc_piece")) if sources.findPrimAttrib("wfc_piece") else set()
    missing = {row["piece"] for row in rows} - actual
    if missing:
        raise ValueError("Missing or empty WFC prototypes: " + repr(sorted(missing)))
geo = node.geometry()
geo.clear()
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


def _name(prefix, value):
    suffix = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return prefix + "_" + (suffix or "piece")


def _instance_file(instances_path, project_root):
    """Read the source once and keep in-project file references movable with the HIP."""
    root = Path(project_root).resolve() if project_root else None
    source = Path(instances_path)
    if source.parts[:1] == ("$HIP",):
        if root is None:
            raise ValueError("$HIP requires a named project for the WFC instance file")
        source = root.joinpath(*source.parts[1:])
    path, data = _read_instances(source)
    relative = root is not None and path.is_relative_to(root)
    literal = (path.relative_to(root) if relative else path).as_posix()
    # Houdini expands dollar signs and backtick expressions when evaluating a file parm.
    literal = literal.replace("$", r"\$").replace("`", r"\`")
    return path, data, ("$HIP/" + literal if relative else literal)


def build_instance_network(parent, instances_path, prototypes=None, *, api):
    """Build points, or native packed Copy to Points when prototypes are given.

    prototypes maps every selected ``piece`` to an existing direct-child SOP;
    additional pieces may be prepared for later seed/style changes.
    The adapter adds piece/pack nodes but does not import assets or change sources.
    Returns the actual node paths. Pass the houdini_exec namespace as ``api``.
    """
    if not isinstance(api, dict):
        raise ValueError("Pass the houdini_exec namespace with api=globals()")
    for verb in ("scene_info", "tab_create", "create_spare_parms", "set_parms", "verify_network", "sop_set_output"):
        if not callable(api.get(verb)):
            raise ValueError("Missing injected DSH verb: " + verb)
    create = api["tab_create"]
    path, data, file_reference = _instance_file(instances_path, api["scene_info"]()["project_layout"]["project_root"])
    packed = []
    source = None
    if prototypes is not None:
        if not isinstance(prototypes, dict):
            raise ValueError("prototypes must map piece IDs to direct-child SOPs")
        expected = {row["piece"] for row in data["instances"]}
        missing = expected - set(prototypes)
        if missing:
            raise ValueError("Missing prototypes for resolved pieces: " + repr(sorted(missing)))
        for piece in sorted(prototypes):
            identity = json.dumps(piece)
            tagged = create(parent, "attribwrangle", _name("PIECE", piece), inputs=[prototypes[piece]],
                            parms={"class": "primitive",
                                   "snippet": "s@wfc_piece = {0};".format(identity)})
            packed.append(create(parent, "pack", _name("PACK", piece), inputs=[tagged],
                                 parms={"nameattribute": "wfc_piece", "transfer_attributes": "wfc_piece",
                                        "pivot": "origin"}))
        source = packed[0] if len(packed) == 1 else create(parent, "merge", "PROTOTYPES", inputs=packed)
    layout = create(parent, "python", "WFC_POINTS", inputs=[source] if source is not None else None)
    api["create_spare_parms"](layout, layout=[{
        "type": "string", "file": "any", "name": "instances", "label": "Resolved WFC JSON",
        "default": file_reference,
    }])
    api["set_parms"](layout, {"python": _POINT_SOURCE, "maintainstate": False})
    if source is not None:
        output = create(parent, "copytopoints", "OUT_WFC", inputs=[source, layout], parms={
            "useidattrib": True, "idattrib": "wfc_piece", "pack": False, "transform": True,
            "targetattribs": 1, "useapply1": True, "applyto1": "prims", "applymethod1": "copy",
            "applyattribs1": "cell_id asset_key variant asset",
        })
    else:
        output = create(parent, "null", "OUT_WFC_POINTS", inputs=[layout])
    api["verify_network"](parent, output=output)
    api["sop_set_output"](output)
    return {"points": layout.path(), "output": output.path(), "instances": path.as_posix(),
            "prototypes": [node.path() for node in packed], "mode": "instances" if packed else "points"}
