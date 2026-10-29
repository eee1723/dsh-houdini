"""Prepare the same locked private media tools used by an offline release.

Source development only. Writes runtime/video in this checkout; never installs
system programs, changes PATH or restarts Houdini. Release users repair their
complete installed version through Version & Updates instead.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dsh_release_builder", ROOT / "tools/build-release.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def prepare(args):
    with builder.temporary_staging("private-video-runtime-") as directory:
        work = Path(directory)
        config = json.loads((ROOT / "deployment/runtime.json").read_text(encoding="utf-8"))
        staged = work / "video"
        notice = builder.stage_video_runtime(staged, work / "build", config,
            cache=args.cache, prepared=args.runtime)
        destination = ROOT / "runtime/video"
        destination.parent.mkdir(parents=True, exist_ok=True)
        previous = destination.with_name("video.previous-" + uuid.uuid4().hex[:12]) if destination.exists() else None
        if previous:
            destination.rename(previous)
        try:
            staged.rename(destination)
        except OSError:
            if previous:
                previous.rename(destination)
            raise
    print("Prepared private FFmpeg / ffprobe:", destination)
    print("Version:", notice["version"])
    if previous:
        print("Previous private runtime retained:", previous)
    print("No global installation or PATH change. Python remains the current Houdini runtime.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, help="Reuse verified media source/compiler downloads")
    parser.add_argument("--runtime", type=Path, help="Reuse a complete source-built runtime after inventory/input verification")
    prepare(parser.parse_args())
