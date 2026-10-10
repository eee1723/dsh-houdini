"""Pinned, source-complete private media staging; no downloads or native builds."""
from __future__ import annotations
import importlib.util
import io
from pathlib import Path
import shutil
import tempfile
import tarfile
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("release_builder", ROOT / "tools/build-release.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
media = builder.video_builder


def rejects(callback, match):
    try:
        callback()
    except (ValueError, FileNotFoundError) as error:
        assert match in str(error), (match, error)
    else:
        raise AssertionError("Invalid media provision accepted")


with tempfile.TemporaryDirectory(prefix="dsh-private-media-package-") as temporary:
    root = Path(temporary)
    cache = root / "cache"
    cache.mkdir()
    source = cache / "ffmpeg-source.zip"
    recipe = cache / "toolchain-source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("source/COPYING.LGPLv2.1", "LGPL fixture")
        archive.writestr("source/example.c", "complete corresponding fixture source")
    with zipfile.ZipFile(recipe, "w") as archive:
        archive.writestr("recipe/build.sh", "pinned toolchain recipe")
    source_spec = {"url": "https://github.com/test/source.zip", "sha256": media.digest(source),
        "root": "source", "file": source.name, "licenseFiles": ["COPYING.LGPLv2.1"]}
    recipe_spec = {"url": "https://github.com/test/recipe.zip", "sha256": media.digest(recipe),
        "root": "recipe", "file": recipe.name}
    runtime = {"python": "current-houdini-3.11+", "ffmpeg": {"version": "fixture-version",
        "license": "LGPL-2.1-or-later", "source": source_spec, "librarySources": {}, "recipeSource": recipe_spec}}
    with patch.object(media.urllib.request, "build_opener", side_effect=AssertionError("no network")):
        assert media.input_archive(source_spec, cache) == source
        rejects(lambda: media.input_archive({**source_spec, "sha256": "0" * 64}, cache), "checksum")
    rejects(lambda: media.check_url("https://example.invalid/source.zip"), "upstream HTTPS")
    request = media.urllib.request.Request("https://github.com/FFmpeg/FFmpeg/archive/pinned.zip")
    assert media.SourceRedirect().redirect_request(request, None, 302, "fixture", {},
        "https://codeload.github.com/FFmpeg/FFmpeg/zip/pinned").full_url.startswith("https://codeload.github.com/")
    extracted = media.expand(source, source_spec, root / "extract")
    assert (extracted / "example.c").is_file()
    assert media.archive_members(source, "source", ["COPYING.LGPLv2.1"])["COPYING.LGPLv2.1"] == b"LGPL fixture"
    for index, member in enumerate(("source/../escape", "other/file")):
        unsafe = cache / (str(index) + ".zip")
        with zipfile.ZipFile(unsafe, "w") as archive:
            archive.writestr(member, b"unsafe")
        rejects(lambda: media.expand(unsafe, source_spec, root / ("unsafe-" + str(index))),
            "Unsafe" if ".." in member else "root")

    # Distribution timestamps must survive extraction: writing configure.ac
    # later must not spuriously trigger an unavailable Autotools regeneration.
    tar_source = cache / "source.tar"
    with tarfile.open(tar_source, "w") as archive:
        for name, timestamp in (("configure", 1700000100), ("configure.ac", 1700000000), ("notes.md", 1700000000)):
            item = tarfile.TarInfo("source/" + name)
            item.size, item.mtime = len(b"source fixture"), timestamp
            archive.addfile(item, io.BytesIO(b"source fixture"))
        link = tarfile.TarInfo("source/documentation.md")
        link.type, link.linkname = tarfile.SYMTYPE, "notes.md"
        archive.addfile(link)
    tar_tree = media.expand(tar_source, source_spec, root / "tar-extract")
    assert (tar_tree / "configure").stat().st_mtime > (tar_tree / "configure.ac").stat().st_mtime
    assert (tar_tree / "documentation.md").read_bytes() == (tar_tree / "notes.md").read_bytes()
    assert not (tar_tree / "documentation.md").is_symlink()

    prepared = root / "prepared"
    (prepared / "sources").mkdir(parents=True)
    (prepared / "licenses/ffmpeg").mkdir(parents=True)
    (prepared / "ffmpeg/bin").mkdir(parents=True)
    for name in ("ffmpeg.exe", "ffprobe.exe", "avcodec-62.dll"):
        (prepared / "ffmpeg/bin" / name).write_bytes(b"fixture, never executed")
    shutil.copyfile(source, prepared / "sources" / source.name)
    shutil.copyfile(recipe, prepared / "sources" / recipe.name)
    shutil.copyfile(ROOT / "tools/build-video-runtime.py", prepared / "sources/build-video-runtime.py")
    (prepared / "licenses/ffmpeg/COPYING.LGPLv2.1").write_bytes(b"LGPL fixture")
    media.write_json(prepared / "runtime.json", runtime)
    def record():
        files = {file.relative_to(prepared).as_posix(): media.digest(file) for file in prepared.rglob("*")
                 if file.is_file() and file.name != "build-provenance.json"}
        media.write_json(prepared / "build-provenance.json", {"runtime": runtime, "files": files})
    record()
    destination = root / "runtime/video"
    commands = []
    def fake_run(args, **kwargs):
        commands.append(args)
        return "ffmpeg fixture-version" if args[-1] == "-version" else "--enable-shared --disable-autodetect"
    with patch.object(builder, "run", fake_run), patch.object(media.urllib.request, "build_opener", side_effect=AssertionError("no network")):
        builder.stage_video_runtime(destination, root / "scratch", {"videoRuntime": runtime}, prepared=prepared)
    assert commands[0][0] == destination / "ffmpeg/bin/ffmpeg.exe"
    assert commands[1][0] == destination / "ffmpeg/bin/ffprobe.exe"
    assert (destination / "ffmpeg/bin/avcodec-62.dll").is_file()
    assert (destination / "sources" / source.name).read_bytes() == source.read_bytes()
    (prepared / "ffmpeg/bin/ffmpeg.exe").write_bytes(b"changed executable")
    rejects(lambda: media.validate_prepared(prepared, runtime), "inventory")
    record()
    (prepared / "licenses/ffmpeg/COPYING.LGPLv2.1").unlink()
    record()
    rejects(lambda: media.validate_prepared(prepared, runtime), "license")

print("pinned source-complete private tutorial runtime staging tests passed")
