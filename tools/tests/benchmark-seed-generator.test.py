"""H21/H22 HOM regression for the generic benchmark seed generator."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "benchmark-seed-hython.py"
SPEC = importlib.util.spec_from_file_location("dsh_benchmark_seed_hython", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


SCENE = {
    "mode": "empty",
    "geometryPreset": "none",
    "clearExisting": True,
    "fps": 24,
    "frameRange": {"start": 1, "end": 120},
    "playbackRange": {"start": 1, "end": 96},
    "currentFrame": 1,
}


with tempfile.TemporaryDirectory(prefix="dsh-benchmark-seed-") as raw_root:
    root = Path(raw_root)
    first_path = root / "first" / "seed.hip"
    second_path = root / "second" / "seed.hip"
    first = MODULE.generate({"schemaVersion": 1, "outputPath": str(first_path), "scene": SCENE})
    second = MODULE.generate({"schemaVersion": 1, "outputPath": str(second_path), "scene": SCENE})

    assert first["ok"] is True and second["ok"] is True
    assert first_path.is_file() and first_path.stat().st_size > 0
    assert second_path.is_file() and second_path.stat().st_size > 0
    assert first["identity"] == second["identity"], "repeated generation must have the same structural identity"

    identity = first["identity"]
    assert identity["fps"] == 24.0
    assert identity["frameRange"] == [1.0, 120.0]
    assert identity["playbackRange"] == [1.0, 96.0]
    assert identity["currentFrame"] == 1.0
    assert all(item["path"].count("/") == 1 for item in identity["nodes"]), identity["nodes"]

    try:
        MODULE.generate({
            "schemaVersion": 1,
            "outputPath": str(root / "invalid.hip"),
            "scene": {**SCENE, "playbackRange": {"start": 0, "end": 96}},
        })
    except ValueError as error:
        assert "must stay inside" in str(error)
    else:
        raise AssertionError("generator accepted a playback range outside the frame range")

    fixed_scene = {**SCENE, "mode": "fixed-geometry", "geometryPreset": "shaderball"}
    fixed_first = MODULE.generate({
        "schemaVersion": 1,
        "outputPath": str(root / "fixed-first" / "seed.hip"),
        "scene": fixed_scene,
    })
    fixed_second = MODULE.generate({
        "schemaVersion": 1,
        "outputPath": str(root / "fixed-second" / "seed.hip"),
        "scene": fixed_scene,
    })
    assert fixed_first["identity"] == fixed_second["identity"]
    fixed_paths = [item["path"] for item in fixed_first["identity"]["nodes"]]
    assert "/obj/seed_geometry" in fixed_paths
    assert "/obj/seed_geometry/shaderball" in fixed_paths


print("benchmark seed generator HOM regression passed")
