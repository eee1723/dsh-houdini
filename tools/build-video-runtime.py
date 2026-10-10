"""Build the private Windows media runtime from locked, source-complete inputs.

This is a build-host tool, never a user install step. The shipped copy in sources/
can rebuild the libraries independently with Python 3.11+ and Git for Windows.
"""
from __future__ import annotations
import argparse
import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile

ALLOWED_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com",
                 "codeload.github.com", "distfiles.ariadne.space", "www.nasm.us"}


def digest(path):
    with Path(path).open("rb") as stream:
        result = hashlib.sha256()
        while block := stream.read(1024**2):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class SourceRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        check_url(url)
        return super().redirect_request(request, response, code, message, headers, url)


def check_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
        raise ValueError("Media build inputs must use the locked upstream HTTPS hosts")


def input_archive(spec, cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / spec["file"]
    if not target.exists():
        check_url(spec["url"])
        request = urllib.request.Request(spec["url"], headers={"User-Agent": "dsh-houdini-video-builder"})
        temporary = target.with_suffix(target.suffix + ".part")
        opener = urllib.request.build_opener(SourceRedirect())
        with opener.open(request, timeout=60) as response, temporary.open("wb") as output:
            size = 0
            while block := response.read(1024**2):
                size += len(block)
                if size > 250 * 1024**2:
                    raise ValueError("Media build input exceeds its archive size limit")
                output.write(block)
        temporary.replace(target)
    if digest(target) != spec["sha256"]:
        raise ValueError("Media build input checksum mismatch: " + target.name)
    return target


def archive_path(root, name):
    parts = PurePosixPath(name).parts
    if not parts or name.startswith(("/", "\\")) or "\\" in name or any(p in (".", "..") or ":" in p for p in parts):
        raise ValueError("Unsafe media source archive path")
    return Path(root).joinpath(*parts)


def expand(archive, spec, destination, *, reuse=False):
    destination = Path(destination)
    if destination.exists() and not reuse:
        raise ValueError("Media build extraction requires a new directory")
    destination.mkdir(parents=True, exist_ok=reuse)
    expected = spec["root"]
    if zipfile.is_zipfile(archive):
        links = []
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                name = member.filename.rstrip("/")
                if expected and name != expected and not name.startswith(expected + "/"):
                    raise ValueError("Unexpected media source archive root")
                target = archive_path(destination, name)
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    source_target = (target.parent / source.read(member).decode("utf-8")).resolve()
                    if not source_target.is_relative_to(destination.resolve()):
                        raise ValueError("Media source archive link escapes its extraction directory")
                    links.append((target, source_target))
                    continue
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(member) as data, target.open("wb" if reuse else "xb") as output:
                        shutil.copyfileobj(data, output)
                    timestamp = datetime.datetime(*member.date_time, tzinfo=datetime.timezone.utc).timestamp()
                    os.utime(target, (timestamp, timestamp))
        for target, source_target in links:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_target, target)
    else:
        links = []
        with tarfile.open(archive) as source:
            for member in source:
                name = member.name.rstrip("/")
                if expected and name != expected and not name.startswith(expected + "/"):
                    raise ValueError("Unexpected media source archive root")
                target = archive_path(destination, name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source.extractfile(member) as data, target.open("wb" if reuse else "xb") as output:
                        shutil.copyfileobj(data, output)
                    os.utime(target, (member.mtime, member.mtime))
                elif member.issym() or member.islnk():
                    source_target = (target.parent / member.linkname if member.issym()
                                     else destination / member.linkname).resolve()
                    if not source_target.is_relative_to(destination.resolve()):
                        raise ValueError("Media source archive link escapes its extraction directory")
                    links.append((target, source_target))
                else:
                    raise ValueError("Media build TAR must contain only regular files and directories")
        # Source distributions can contain documentation links. Materializing an
        # in-tree target keeps Windows builds independent of symlink privileges.
        for target, source_target in links:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_target, target)
    return destination / expected


def archive_members(archive, root, names):
    wanted = {root + "/" + name: name for name in names}
    found = {}
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            return {name: source.read(root + "/" + name) for name in names}
    with tarfile.open(archive, mode="r|*") as source:
        for member in source:
            if member.name in wanted:
                if not member.isfile():
                    raise ValueError("License is not a regular source file: " + member.name)
                found[wanted[member.name]] = source.extractfile(member).read()
                if len(found) == len(wanted):
                    break
    if len(found) != len(wanted):
        raise ValueError("Media source archive is missing its declared license files")
    return found


def run(args, cwd, env, log, commands):
    args = [str(value) for value in args]
    commands.append({"argv": args, "cwd": str(cwd)})
    with Path(log).open("a", encoding="utf-8") as output:
        output.write("\nDSH_BUILD_COMMAND " + json.dumps(commands[-1], ensure_ascii=False) + "\n")
        output.flush()
        subprocess.run(args, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                       check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def bash_path():
    git = shutil.which("git")
    if git:
        for root in (Path(git).parent.parent, Path(git).parent):
            candidate = root / "usr/bin/bash.exe"
            if candidate.is_file():
                return candidate
    raise RuntimeError("The media build host requires Git for Windows with its Bash shell")


def make_shell_path(bash):
    # Native GNU Make expands SHELL into unquoted nested Autotools recipes.
    # Use the actual Windows short path for Git's usual Program Files location.
    import ctypes
    output = ctypes.create_unicode_buffer(32768)
    function = ctypes.windll.kernel32.GetShortPathNameW
    function.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    function.restype = ctypes.c_uint32
    if not function(str(bash), output, len(output)):
        raise ctypes.WinError()
    return output.value.replace("\\", "/")


def patch_ffmpeg_windows_response_files(source):
    """The locked MinGW build must not send its 32K+ object list via Win32 argv."""
    source = Path(source)
    changes = {}
    filename = "ffbuild/library.mak"
    before = (source / filename).read_text(encoding="utf-8")
    after = before.replace("\t$(Q)echo $^ > $@.objs", "\t$(file >$@.objs,$^)")
    after = after.replace("\t$(SLIB_CREATE_DEF_CMD)", "\t$$(file >$$@.objs,$$(filter %.o,$$^))\n\t$(SLIB_CREATE_DEF_CMD)")
    after = after.replace("\t$(Q)echo $$(filter %.o,$$^) > $$@.objs", "\t$$(file >$$@.objs,$$(filter %.o,$$^))")
    after = "# DSH-Houdini build change: write object response files within GNU Make.\n" + after
    changes[filename] = (before, after)
    filename = "configure"
    before = (source / filename).read_text(encoding="utf-8")
    original = 'SLIB_CREATE_DEF_CMD=\'EXTERN_PREFIX="$(EXTERN_PREFIX)" AR="$(AR_CMD)" NM="$(NM_CMD)" $(SRC_PATH)/compat/windows/makedef $(SUBDIR)lib$(NAME).ver $(OBJS) > $$(@:$(SLIBSUF)=.def)\''
    replacement = original.replace("$(OBJS) >", "@$$@.objs >")
    if original not in before:
        raise ValueError("Locked FFmpeg configure no longer has the expected MinGW export rule")
    after = before.replace(original, replacement)
    after = after.replace("#!/bin/sh\n", "#!/bin/sh\n# DSH-Houdini build change: pass MinGW export objects by response file.\n", 1)
    changes[filename] = (before, after)
    filename = "compat/windows/makedef"
    before = (source / filename).read_text(encoding="utf-8")
    after = before.replace("shift\n", '''shift
response=""
if [ "$#" -eq 1 ] && [ "${1#@}" != "$1" ]; then
    response="${1#@}"
    set -- $(cat "$response")
fi
''', 1)
    after = after.replace('$AR rcs ${libname} $@ >/dev/null', '''if [ -n "$response" ]; then
        $AR rcs "${libname}" "@$response" >/dev/null
    else
        $AR rcs ${libname} $@ >/dev/null
    fi''')
    after = after.replace("#!/bin/sh\n", "#!/bin/sh\n# DSH-Houdini build change: llvm-ar consumes the complete object response file.\n", 1)
    changes[filename] = (before, after)
    patch = ""
    for filename, (before, after) in changes.items():
        if before == after:
            raise ValueError("FFmpeg Windows response patch did not apply")
        patch += "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                         fromfile="a/" + filename, tofile="b/" + filename))
        (source / filename).write_text(after, encoding="utf-8", newline="\n")
    return patch


def pe_imports(filename, readobj, env):
    result = subprocess.check_output([str(readobj), "--coff-imports", str(filename)], env=env,
        text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return sorted(set(re.findall(r"^\s+Name: (.+\.dll)\s*$", result, re.MULTILINE | re.IGNORECASE)), key=str.casefold)


def system_dll(name):
    return name.lower().startswith(("api-ms-win-", "ext-ms-win-")) or name.lower() in {
        "kernel32.dll", "user32.dll", "advapi32.dll", "gdi32.dll", "ole32.dll", "shell32.dll",
        "ws2_32.dll", "bcrypt.dll", "ntdll.dll", "msvcrt.dll", "ucrtbase.dll",
        "psapi.dll", "oleaut32.dll", "shlwapi.dll", "msvfw32.dll", "avicap32.dll"}


def collect_imports(binary_dir, toolchain, env):
    """Retain actual private runtime dependencies; never obtain them from PATH."""
    binary_dir, toolchain = Path(binary_dir), Path(toolchain)
    readobj = toolchain / "bin/llvm-readobj.exe"
    pending = list(binary_dir.glob("*.exe")) + list(binary_dir.glob("*.dll"))
    imports, supplied = {}, []
    while pending:
        file = pending.pop()
        if file.name in imports:
            continue
        observed = pe_imports(file, readobj, env)
        imports[file.name] = observed
        for name in observed:
            if system_dll(name):
                continue
            target = binary_dir / name
            if not target.is_file():
                source = toolchain / "x86_64-w64-mingw32/bin" / name
                if not source.is_file():
                    raise ValueError("Unprovided private media DLL dependency: " + name)
                shutil.copyfile(source, target)
                supplied.append(name)
            pending.append(target)
    return imports, sorted(supplied)


def package_sources(destination, spec, archives, toolchain, provenance):
    sources = destination / "sources"
    sources.mkdir()
    all_sources = {"ffmpeg": spec["source"], **spec["librarySources"]}
    for name, source in all_sources.items():
        shutil.copyfile(archives[name], sources / source["file"])
    shutil.copyfile(archives["recipeSource"], sources / spec["recipeSource"]["file"])
    shutil.copyfile(__file__, sources / "build-video-runtime.py")
    licenses = destination / "licenses"
    for name, source in all_sources.items():
        directory = licenses / name
        directory.mkdir(parents=True)
        for item, data in archive_members(archives[name], source["root"], source["licenseFiles"]).items():
            target = directory / item
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    # Keep the toolchain's complete delivered notice, including its LLVM exception.
    (licenses / "llvm/TOOLCHAIN-LICENSE.TXT").write_bytes((toolchain / "LICENSE.TXT").read_bytes())
    (destination / "ffmpeg/LICENSE.txt").write_bytes((licenses / "ffmpeg/COPYING.LGPLv2.1").read_bytes())
    shutil.copyfile(licenses / "ffmpeg/COPYING.LGPLv2.1", destination / "COPYING.LGPLv2.1")
    (destination / "SOURCE-NOTICE.txt").write_text(
        "This runtime uses FFmpeg under LGPL-2.1-or-later, FreeType under the FreeType License,\n"
        "HarfBuzz under its MIT-style license, dav1d under BSD-2-Clause, and zlib under the Zlib license.\n"
        "It is built from the exact archives in sources/.\n"
        "FreeType attribution: Portions of this software are copyright (c) The FreeType Project\n"
        "(www.freetype.org). All rights reserved.\n"
        "The corresponding MinGW-w64 and LLVM runtime sources and complete notices are also included.\n"
        "See licenses/ for the original terms, runtime.json for input hashes, and build-provenance.json\n"
        "for actual commands, compiler identity, DLL imports, output hashes and applied build patches.\n"
        "To rebuild on Windows: python sources/build-video-runtime.py --config runtime.json --output <new-dir>.\n"
        "The build host needs Python 3.11+ and Git for Windows; compiler/CMake/Ninja/Meson/NASM/pkgconf inputs are locked.\n"
        "The build downloads those inputs or reuses --cache; users running the plugin need none of those tools.\n"
        "Libraries are separate DLLs and may be replaced with ABI-compatible modified builds.\n"
        "Houdini Python and Windows system DLLs are provided by the user's licensed installations.\n",
        encoding="utf-8")
    write_json(destination / "runtime.json", provenance["runtime"])


def validate_prepared(directory, runtime):
    directory = Path(directory)
    observed = json.loads((directory / "runtime.json").read_text(encoding="utf-8"))
    provenance = json.loads((directory / "build-provenance.json").read_text(encoding="utf-8"))
    if observed != runtime or provenance["runtime"] != runtime:
        raise ValueError("Prepared media runtime differs from the locked inputs")
    recipe = directory / "sources/build-video-runtime.py"
    if digest(recipe) != digest(__file__):
        raise ValueError("Prepared media runtime uses a different build recipe")
    expected = provenance["files"]
    actual = {file.relative_to(directory).as_posix(): digest(file) for file in directory.rglob("*")
              if file.is_file() and file.name != "build-provenance.json"}
    if actual != expected:
        raise ValueError("Prepared media runtime file inventory differs from the build")
    for name, source in {"ffmpeg": runtime["ffmpeg"]["source"], **runtime["ffmpeg"]["librarySources"]}.items():
        if digest(directory / "sources" / source["file"]) != source["sha256"]:
            raise ValueError("Prepared media runtime lacks an exact corresponding source archive")
        for license_file in source["licenseFiles"]:
            if not (directory / "licenses" / name / license_file).is_file():
                raise ValueError("Prepared media runtime is missing a declared license file")
    recipe_source = runtime["ffmpeg"]["recipeSource"]
    if digest(directory / "sources" / recipe_source["file"]) != recipe_source["sha256"]:
        raise ValueError("Prepared media runtime lacks the exact toolchain build recipe")
    return provenance


def prepare(destination, work, runtime, *, cache=None, prepared=None, resume=False):
    destination, work = Path(destination).resolve(), Path(work).resolve()
    if prepared is not None:
        facts = validate_prepared(prepared, runtime)
        shutil.copytree(prepared, destination)
        return facts
    if os.name != "nt":
        raise RuntimeError("Build the media runtime on Windows x64")
    if destination.exists():
        raise ValueError("Use a new output directory for media runtime assembly")
    spec = runtime["ffmpeg"]
    work.mkdir(parents=True, exist_ok=True)
    cache = Path(cache).resolve() if cache is not None else work / "archives"
    inputs = {"ffmpeg": spec["source"], **spec["librarySources"], "recipeSource": spec["recipeSource"], **spec["buildTools"]}
    archives = {name: input_archive(item, cache) for name, item in inputs.items()}
    expanded = {name: expand(archives[name], inputs[name], work / name, reuse=resume)
                for name in ("toolchain", "cmake", "ninja", "meson", "nasm", "pkgconf", "zlib", "freetype", "harfbuzz", "dav1d", "ffmpeg")}
    toolchain, cmake, ninja = expanded["toolchain"], expanded["cmake"] / "bin/cmake.exe", expanded["ninja"]
    bash = bash_path()
    make_shell = make_shell_path(bash)
    env = dict(os.environ, PATH=os.pathsep.join([str(toolchain / "bin"), str(ninja), str(expanded["nasm"]), str(bash.parent),
                    str(Path(os.environ["SystemRoot"]) / "System32")]))
    env.update(CC="x86_64-w64-mingw32-gcc.exe", AR="llvm-ar.exe", RANLIB="llvm-ranlib.exe")
    make = toolchain / "bin/mingw32-make.exe"
    env["MAKE"] = make.as_posix()
    commands, log = [], work / "build.log"
    build_patch = patch_ffmpeg_windows_response_files(expanded["ffmpeg"])
    prefix = work / "prefix"
    common = ["-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_SYSTEM_NAME=Windows",
        "-DCMAKE_C_COMPILER=" + str(toolchain / "bin/x86_64-w64-mingw32-clang.exe"),
        "-DCMAKE_CXX_COMPILER=" + str(toolchain / "bin/x86_64-w64-mingw32-clang++.exe"),
        "-DCMAKE_INSTALL_PREFIX=" + str(prefix), "-DCMAKE_PREFIX_PATH=" + str(prefix), "-DBUILD_SHARED_LIBS=ON"]
    for name in ("zlib", "freetype", "harfbuzz"):
        output = work / (name + "-build")
        print("Building private media library:", name, flush=True)
        run([cmake, "-S", expanded[name], "-B", output, *common, *spec["cmakeOptions"][name]], work, env, log, commands)
        run([cmake, "--build", output, "--parallel", str(min(os.cpu_count() or 2, 8))], work, env, log, commands)
        run([cmake, "--install", output], work, env, log, commands)
    print("Building the locked AV1 software decoder", flush=True)
    meson = expanded["meson"] / "meson.py"
    dav1d_output = work / "dav1d-build"
    run([sys.executable, meson, "setup", dav1d_output, expanded["dav1d"], "--prefix=" + prefix.as_posix(),
         "--buildtype=release", "--default-library=shared", *spec["mesonOptions"]["dav1d"]], work, env, log, commands)
    run([sys.executable, meson, "compile", "-C", dav1d_output, "-j", "8"], work, env, log, commands)
    run([sys.executable, meson, "install", "-C", dav1d_output], work, env, log, commands)
    pkgconf = expanded["pkgconf"]
    print("Building the locked pkgconf build tool", flush=True)
    run([bash, "./configure", "--build=x86_64-w64-mingw32", "--host=x86_64-w64-mingw32",
         "--disable-shared", "--enable-static", "--disable-dependency-tracking",
         "--prefix=" + (work / "pkgconf-prefix").as_posix()], pkgconf, env, log, commands)
    run([make, "-j8", "SHELL=" + make_shell,
         "CPPFLAGS=-DPKGCONFIG_IS_STATIC"], pkgconf, env, log, commands)
    env["PKG_CONFIG_LIBDIR"] = (prefix / "lib/pkgconfig").as_posix()
    configure = [bash, "./configure", "--prefix=" + prefix.as_posix(), "--arch=x86_64", "--target-os=mingw32",
        "--cc=x86_64-w64-mingw32-clang", "--cxx=x86_64-w64-mingw32-clang++", "--ar=llvm-ar",
        "--ranlib=llvm-ranlib", "--nm=llvm-nm", "--pkg-config=" + (pkgconf / "pkgconf.exe").as_posix(),
        *spec["configureOptions"]]
    print("Building private FFmpeg and ffprobe from the locked source", flush=True)
    run(configure, expanded["ffmpeg"], env, log, commands)
    run([make, "-j8", "SHELL=" + make_shell], expanded["ffmpeg"], env, log, commands)
    run([make, "install", "SHELL=" + make_shell], expanded["ffmpeg"], env, log, commands)
    destination.mkdir(parents=True)
    shutil.copytree(prefix, destination / "ffmpeg")
    imports, supplied = collect_imports(destination / "ffmpeg/bin", toolchain, env)
    facts = {"schemaVersion": 1, "runtime": runtime, "commands": commands,
             "patches": [{"file": "ffmpeg-windows-response-files.patch", "scope": "Native Windows build object lists only"}],
             "incrementalBuild": resume, "dllImports": imports, "toolchainRuntimeDlls": supplied,
             "compiler": subprocess.check_output([str(toolchain / "bin/clang.exe"), "--version"], text=True, env=env),
             "recipeSha256": digest(__file__)}
    package_sources(destination, spec, archives, toolchain, facts)
    patch_path = destination / "sources/ffmpeg-windows-response-files.patch"
    patch_path.write_text(build_patch, encoding="utf-8", newline="\n")
    facts["patches"][0]["sha256"] = digest(patch_path)
    (destination / "build-configure.txt").write_text(subprocess.check_output(
        [str(destination / "ffmpeg/bin/ffmpeg.exe"), "-hide_banner", "-buildconf"], env=env, text=True), encoding="utf-8")
    shutil.copyfile(log, destination / "sources/build.log")
    facts["files"] = {file.relative_to(destination).as_posix(): digest(file) for file in destination.rglob("*") if file.is_file()}
    write_json(destination / "build-provenance.json", facts)
    validate_prepared(destination, runtime)
    return facts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--resume", action="store_true", help="Restore exact source inputs and reuse this build host's existing intermediate objects")
    args = parser.parse_args()
    raw = json.loads(args.config.read_text(encoding="utf-8"))
    runtime = raw.get("videoRuntime", raw)
    work = args.work or args.output.with_name(args.output.name + ".build")
    prepare(args.output, work, runtime, cache=args.cache, resume=args.resume)
    print("Source-complete private media runtime:", args.output, flush=True)
