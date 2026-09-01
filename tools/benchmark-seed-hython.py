"""Generate a generic deterministic Houdini seed scene for benchmark setup.

This runner is evaluator infrastructure, not an agent-facing Houdini recipe. It
accepts only an empty-scene contract plus timeline settings, writes one HIP
below the caller-selected HIP root, and returns a normalized structural
identity. The Node orchestrator owns path containment, hashing, repeat checks,
and fixture-manifest generation.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import hou


def _require_object(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _require_exact_keys(value: dict, expected: set[str], label: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        parts = []
        if missing:
            parts.append("missing=" + ",".join(missing))
        if extra:
            parts.append("unsupported=" + ",".join(extra))
        raise ValueError(f"{label} fields are invalid ({'; '.join(parts)})")


def _require_number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    return float(value)


def _require_range(value, label: str) -> tuple[float, float]:
    item = _require_object(value, label)
    _require_exact_keys(item, {"start", "end"}, label)
    start = _require_number(item["start"], f"{label}.start")
    end = _require_number(item["end"], f"{label}.end")
    if start > end:
        raise ValueError(f"{label}.start must not exceed {label}.end")
    return start, end


def _node_identity(node: hou.Node) -> dict:
    node_type = node.type()
    return {
        "path": node.path(),
        "category": node_type.category().name(),
        "type": node_type.name(),
        "inputs": [item.path() if item is not None else None for item in node.inputs()],
    }


def structural_identity() -> dict:
    root = hou.node("/")
    nodes = sorted(root.allSubChildren(), key=lambda item: item.path()) if root is not None else []
    return {
        "schemaVersion": 1,
        "houdini": hou.applicationVersionString(),
        "fps": float(hou.fps()),
        "frameRange": [float(value) for value in hou.playbar.frameRange()],
        "playbackRange": [float(value) for value in hou.playbar.playbackRange()],
        "currentFrame": float(hou.frame()),
        "nodes": [_node_identity(node) for node in nodes],
    }


def generate(request: dict) -> dict:
    request = _require_object(request, "request")
    _require_exact_keys(request, {"schemaVersion", "outputPath", "scene"}, "request")
    if request["schemaVersion"] != 1:
        raise ValueError("request.schemaVersion must be 1")

    output_path = Path(request["outputPath"]).resolve()
    if output_path.suffix.lower() not in {".hip", ".hiplc", ".hipnc"}:
        raise ValueError("outputPath must name a .hip, .hiplc, or .hipnc file")

    scene = _require_object(request["scene"], "scene")
    _require_exact_keys(
        scene,
        {"mode", "geometryPreset", "clearExisting", "fps", "frameRange", "playbackRange", "currentFrame"},
        "scene",
    )
    if scene["mode"] not in {"empty", "fixed-geometry"}:
        raise ValueError("scene.mode must be 'empty' or 'fixed-geometry'")
    expected_preset = "none" if scene["mode"] == "empty" else "shaderball"
    if scene["geometryPreset"] != expected_preset:
        raise ValueError(
            f"scene.geometryPreset must be {expected_preset!r} when mode is {scene['mode']!r}"
        )
    if scene["clearExisting"] is not True:
        raise ValueError("scene.clearExisting must be true")

    fps = _require_number(scene["fps"], "scene.fps")
    if not 0 < fps <= 240:
        raise ValueError("scene.fps must be greater than 0 and at most 240")
    frame_range = _require_range(scene["frameRange"], "scene.frameRange")
    playback_range = _require_range(scene["playbackRange"], "scene.playbackRange")
    current_frame = _require_number(scene["currentFrame"], "scene.currentFrame")
    if not frame_range[0] <= playback_range[0] <= playback_range[1] <= frame_range[1]:
        raise ValueError("scene.playbackRange must stay inside scene.frameRange")
    if not frame_range[0] <= current_frame <= frame_range[1]:
        raise ValueError("scene.currentFrame must stay inside scene.frameRange")

    hou.hipFile.clear(suppress_save_prompt=True)
    hou.setFps(fps)
    hou.playbar.setFrameRange(*frame_range)
    hou.playbar.setPlaybackRange(*playback_range)
    hou.setFrame(current_frame)

    if scene["mode"] == "fixed-geometry":
        obj = hou.node("/obj")
        if obj is None:
            raise RuntimeError("Houdini scene has no /obj manager")
        container = obj.createNode("geo", "seed_geometry", run_init_scripts=False)
        shaderball = container.createNode("testgeometry_shaderball", "shaderball")
        shaderball.setDisplayFlag(True)
        shaderball.setRenderFlag(True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    hou.hipFile.save(file_name=str(output_path))

    return {
        "ok": True,
        "outputPath": str(output_path),
        "houdini": hou.applicationVersionString(),
        "identity": structural_identity(),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("usage: hython tools/benchmark-seed-hython.py <request.json>")
    request_file = Path(argv[1]).resolve()
    request = json.loads(request_file.read_text(encoding="utf-8"))
    result = generate(request)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
