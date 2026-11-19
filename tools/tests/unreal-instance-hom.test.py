"""Run in an isolated hython process with an unused fixture directory."""
import json
from pathlib import Path
import runpy
import sys

import hou


root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=False)
collect = runpy.run_path(str(Path(__file__).resolve().parents[2] /
                             "skills/houdini-unreal-handoff/scripts/package-instance.py"))["collect"]
library = root / "fixture.hda"
instance = hou.node("/obj").createNode("geo", run_init_scripts=False)
geometry = instance.createNode("file")
model = root / "sample.gltf"
model.write_text(json.dumps({"buffers": [{"uri": "buffer.bin"}], "images": [{"uri": "color%20map.png"}]}))
geometry.parm("file").set(str(model))
(root / "buffer.bin").write_bytes(b"binary")
result = collect(instance, library)
assert result["unresolved"] == [{"reference": str(root / "color map.png"), "owner": "sample.gltf"}]
(root / "color map.png").write_bytes(b"fixture")
result = collect(instance, library)
assert not result["unresolved"]
assert result["files"] == ["buffer.bin", "color map.png", "sample.gltf"]
geometry.parm("file").set(str(root.parent / "outside.bgeo"))
assert collect(instance, library)["unresolved"][0]["owner"].endswith("/file")
