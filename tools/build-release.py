"""Build the standard Desktop plugin package; the artifact contains no DSH or Node runtime."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding='utf-8', errors='backslashreplace')

ROOT = Path(__file__).resolve().parents[1]
_video_spec = importlib.util.spec_from_file_location("dsh_video_builder", ROOT / "tools/build-video-runtime.py")
video_builder = importlib.util.module_from_spec(_video_spec)
_video_spec.loader.exec_module(video_builder)


def run(args, *, cwd=ROOT, env=None, capture=False):
    result = subprocess.run([str(value) for value in args], cwd=cwd, env=env, check=True,
                            stdout=subprocess.PIPE if capture else None, text=True,
                            encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return result.stdout.strip() if capture else None


def stage_video_runtime(destination, scratch, config, *, cache=None, prepared=None, distribution=False):
    """Clean-tag assembly builds locked sources; local reuse verifies the same full provision."""
    spec = config["videoRuntime"]["ffmpeg"]
    destination, scratch = Path(destination), Path(scratch)
    facts = video_builder.prepare(destination, scratch, config["videoRuntime"], cache=cache, prepared=prepared)
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        executable = destination / "ffmpeg/bin" / name
        if not executable.is_file():
            raise ValueError("Tutorial media runtime is missing " + name)
        version = run([executable, "-version"], capture=True).splitlines()[0]
        if spec["version"] not in version:
            raise ValueError("Tutorial media executable version mismatch: " + name)
    configuration = run([destination / "ffmpeg/bin/ffmpeg.exe", "-hide_banner", "-buildconf"], capture=True)
    if "--enable-gpl" in configuration or "--enable-nonfree" in configuration:
        raise ValueError("Tutorial media runtime must use the locked LGPL build")
    if distribution:
        distribute_media_sources(destination, config, facts)
    return {"name": "FFmpeg / ffprobe", "version": spec["version"], "license": spec["license"],
            "path": destination.as_posix(), "source": spec["source"]["url"],
            "libraries": [{"name": name, "version": item["version"], "license": item["license"],
                           "source": item["url"]} for name, item in spec["librarySources"].items()]}


def distribute_media_sources(directory, config, build_facts):
    """Derive the shipped inventory from a verified full build; binaries stay exact.

    The complete LLVM source archive is optional under its permissive license.
    This is release assembly only: build caches retain every locked input and
    their original provenance. FFmpeg source is always bundled.
    """
    directory = Path(directory)
    spec = config["videoRuntime"]["ffmpeg"]
    references = sorted(set(config.get("mediaDistribution", {}).get("sourceReferences", [])))
    if not references:
        return
    sources = {name: spec["librarySources"][name] for name in references}
    provenance_path = directory / "build-provenance.json"
    distribution = {"sourceReferences": references,
                    "sourceBuildProvenanceSha256": video_builder.digest(provenance_path),
                    "recipeSha256": video_builder.digest(__file__)}
    files = dict(build_facts["files"])
    for source in sources.values():
        relative = "sources/" + source["file"]
        (directory / relative).unlink()
        del files[relative]
    bundled = ["ffmpeg", *(name for name in spec["librarySources"] if name not in references)]
    notice = [
        "This package includes private FFmpeg/ffprobe and their runtime DLLs.",
        "FFmpeg is licensed under LGPL-2.1-or-later; all original license files and toolchain notices are in licenses/.",
        "Exact source archives bundled in sources/: " + ", ".join(bundled) + ".",
        "FreeType attribution: Portions of this software are copyright (c) The FreeType Project",
        "(www.freetype.org). All rights reserved.",
        "The following permissively licensed source archives are referenced, not bundled:",
    ]
    for name, source in sources.items():
        notice.extend([name + " " + source["version"] + " (" + source["license"] + ")",
                       "  " + source["url"], "  SHA256: " + source["sha256"]])
    notice.extend([
        "runtime.json records all exact build inputs, including referenced sources.",
        "build-provenance.json retains actual build commands, compiler, DLL imports and patches;",
        "its files map describes this shipped tree and distribution records the source build provenance digest.",
        "Only source archive delivery changed; executables, DLLs, licenses and build recipes are unchanged.",
        "To rebuild on Windows: python sources/build-video-runtime.py --config runtime.json --output <new-dir> --cache sources.",
        "The build host needs Python 3.11+ and Git for Windows; missing locked inputs are downloaded and verified.",
        "Users running the plugin need no build tools or source downloads.",
        "Libraries are separate DLLs and may be replaced with ABI-compatible modified builds.",
        "Houdini Python and Windows system DLLs are provided by the user's licensed installations.",
    ])
    notice_path = directory / "SOURCE-NOTICE.txt"
    notice_path.write_text("\n".join(notice) + "\n", encoding="utf-8")
    files["SOURCE-NOTICE.txt"] = video_builder.digest(notice_path)
    video_builder.write_json(provenance_path, {**build_facts, "distribution": distribution, "files": files})


def temporary_staging(prefix):
    """Own only one disposable build workspace, including on build failure."""
    scratch = ROOT / "tools/out/tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    if not scratch.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Build staging must remain inside this checkout")
    return tempfile.TemporaryDirectory(prefix=prefix, dir=scratch)



def build(args):
    """Package the plugin and its media tools; Desktop owns DSH and Node."""
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise RuntimeError("Plugin packaging requires npm")
    version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    artifact_tool = ["node", ROOT / "tools/output-artifacts.mjs"]
    if args.output is None:
        allocation = json.loads(run([*artifact_tool, "create", "--label", version,
                                     "--kind", "release", "--isolation", "unknown"], capture=True))
        output = Path(allocation['directory'])
    else:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
        run([*artifact_tool, "begin", output, "--label", "release-" + version,
             "--kind", "release", "--isolation", "unknown"])
    try:
        run([npm, "run", "build"])
        inventory = json.loads(run([npm, "pack", "--dry-run", "--ignore-scripts", "--json", "--cache", ROOT / ".npm-cache"], capture=True))[0]["files"]
        with temporary_staging("plugin-package-") as directory:
            result = package_staged(args, npm, output, inventory, Path(directory))
        run([*artifact_tool, "finish", output, "--status", "success"])
        return result
    except BaseException:
        try:
            run([*artifact_tool, "finish", output, "--status", "failed"])
        except BaseException as error:
            print("Unable to record failed release output: " + str(error), file=sys.stderr)
        raise


def package_staged(args, npm, output, inventory, work):
    """Assemble inside the caller-owned staging directory, preserving final output."""
    plugin = work / "package"
    plugin.mkdir()
    for entry in inventory:
        name = entry["path"]
        if "__pycache__" in Path(name).parts or name.endswith(".pyc") or name.startswith("runtime/video/"):
            continue
        source, destination = ROOT / name, plugin / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    package = json.loads((plugin / "package.json").read_text(encoding="utf-8"))
    # A built tarball installs without compiling source or resolving another copy
    # of the Host's dependencies. Peer requirements remain the Desktop contract.
    for name in ("scripts", "devDependencies", "overrides", "private"):
        package.pop(name, None)
    package["os"] = ["win32"]
    package["cpu"] = ["x64"]
    (plugin / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config = json.loads((ROOT / "deployment/runtime.json").read_text(encoding="utf-8"))
    print("Preparing verified tutorial media distribution", flush=True)
    media = stage_video_runtime(plugin / "runtime/video", work / "media", config,
                                cache=args.media_cache, prepared=args.media_runtime, distribution=True)
    packed = json.loads(run([npm, "pack", "--ignore-scripts", "--json", "--cache", ROOT / ".npm-cache", "--pack-destination", output], cwd=plugin, capture=True))[0]
    packed_files = {row["path"] for row in packed["files"]}
    if not {"runtime/video/ffmpeg/bin/ffmpeg.exe", "runtime/video/ffmpeg/bin/ffprobe.exe"}.issubset(packed_files):
        raise RuntimeError("Plugin package omitted the required tutorial media executables")
    artifact = output / packed["filename"]
    with artifact.open("rb") as stream:
        sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    update = json.loads((ROOT / "release-update.json").read_text(encoding="utf-8"))
    run(["node", "--input-type=module", "-e",
         "import {validReleaseUpdate} from './lib/plugin-updates.js'; "
         "if(!validReleaseUpdate(JSON.parse(process.argv[1]))) "
         "throw Error('Release advice needs a clear summary and valid affected version range');",
         json.dumps(update, ensure_ascii=False)])
    result = {"kind": "dsh-plugin-bundle", "version": package["version"],
              "requiresDsh": package["engines"]["dsh"], "runtimeOwnership": "host",
              "file": str(artifact), "integrity": packed["integrity"], "sha256": sha256,
              "installUrl": "https://github.com/eee1723/dsh-houdini/releases/download/v"
                  + package["version"] + "/" + packed["filename"],
              "platform": {"os": "win32", "cpu": "x64"}, "update": update,
              "mediaVersion": media["version"], "mediaLicense": media["license"]}
    (output / "release-manifest.json").write_text(json.dumps({**result, "file": artifact.name}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS.txt").write_text(sha256 + "  " + artifact.name + "\n", encoding="ascii")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Explicit output directory; default allocates a new versioned batch under tools/out/releases")
    parser.add_argument("--media-cache", type=Path, help="Reuse verified media source/compiler downloads")
    parser.add_argument("--media-runtime", type=Path, help="Reuse a source-complete media runtime after inventory/input verification")
    build(parser.parse_args())
