"""Build an offline Windows release with a frozen dependency tree and RSA signature.

Production builds require a clean version tag and a public key already in the
installer. --candidate is only for isolated tests and cannot be installed by the
normal manager. This command never creates or publishes a GitHub Release.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
import dsh_deployment as deployment


def run(args, *, cwd=ROOT, env=None, capture=False):
    result = subprocess.run([str(a) for a in args], cwd=cwd, env=env, check=True,
                            stdout=subprocess.PIPE if capture else None, text=True,
                            encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return result.stdout.strip() if capture else None


def zip_tree(source, target):
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(source.rglob("*")):
            if file.is_symlink() or getattr(file.lstat(), "st_file_attributes", 0) & 1024:
                raise ValueError("Release cannot contain symlinks/junctions: " + str(file))
            if file.is_file():
                relative = file.relative_to(source).as_posix()
                deployment.checked_path(source, relative)
                archive.write(file, relative)


def build(args):
    if os.name != "nt":
        raise RuntimeError("Build the win32-x64 release on Windows, including native dependencies")
    config = deployment.read_json(ROOT / "deployment/runtime.json")
    package = deployment.read_json(ROOT / "package.json")
    runtime_package = deployment.read_json(ROOT / "deployment/package.json")
    compat = deployment.read_json(ROOT / "dsh-runtime-compatibility.json")
    target_dsh = runtime_package["dependencies"]["@deepseek-ai/dsh"]
    if target_dsh != compat["preferredVersion"]:
        raise RuntimeError("Runtime lock target differs from plugin compatibility policy")
    if not args.candidate and not args.unsigned:
        raise RuntimeError("Production assembly must use --unsigned; sign in a separate trusted environment")
    if not args.unsigned and not os.environ.get("DSH_RELEASE_SIGNING_KEY"):
        raise RuntimeError("Set DSH_RELEASE_SIGNING_KEY to a private key outside the repository")
    trust = deployment.read_json(args.trust)
    if not any(k["id"] == args.key_id for k in trust["keys"]):
        raise RuntimeError("Signing key id is not in the installer trust store")
    commit = run(["git", "rev-parse", "HEAD"], capture=True)
    if not args.candidate:
        if run(["git", "diff", "--no-ext-diff", "HEAD", "--"], capture=True) or run(["git", "ls-files", "--others", "--exclude-standard"], capture=True):
            raise RuntimeError("Production release requires a clean checkout")
        if run(["git", "describe", "--tags", "--exact-match", "HEAD"], capture=True) != "v" + package["version"]:
            raise RuntimeError("Production release must be built from its exact version tag")
        if args.trust.resolve() != (ROOT / "installer/release-trust.json").resolve():
            raise RuntimeError("Production trust must be reviewed and committed in installer/release-trust.json")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError("Use a new empty output directory; existing release assets are immutable")
    output.mkdir(parents=True, exist_ok=True)
    scratch_parent = ROOT / "tools/out"
    scratch_parent.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="release-build-", dir=scratch_parent))
    print("Build workspace:", work, flush=True)
    archive = args.node_archive
    if archive is None:
        archive = work / "node.zip"
        url = f"https://nodejs.org/dist/v{config['nodeVersion']}/node-v{config['nodeVersion']}-win-x64.zip"
        print("Downloading pinned Node distribution", flush=True)
        with urllib.request.urlopen(url, timeout=45) as response, archive.open("xb") as target:
            size = 0
            while chunk := response.read(1024**2):
                size += len(chunk)
                if size > 150 * 1024**2:
                    raise ValueError("Node distribution exceeds size limit")
                target.write(chunk)
    if deployment.digest(archive) != config["nodeArchiveSha256"]:
        raise ValueError("Pinned Node archive checksum mismatch")
    with zipfile.ZipFile(archive) as nodezip:
        for entry in nodezip.infolist():
            destination = deployment.checked_path(work, entry.filename.rstrip("/"))
            if entry.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with nodezip.open(entry) as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target)
    node_home = work / f"node-v{config['nodeVersion']}-win-x64"
    node = node_home / "node.exe"
    npm = [node, node_home / "node_modules/npm/bin/npm-cli.js"]
    env = dict(os.environ, PATH=str(node_home) + os.pathsep + os.environ["PATH"])
    env.pop("NODE_OPTIONS", None)
    env.pop("NODE_PATH", None)
    for secret in ("DSH_RELEASE_SIGNING_KEY", "RELEASE_PRIVATE_PEM", "GH_TOKEN", "GITHUB_TOKEN", "NODE_AUTH_TOKEN", "NPM_TOKEN"):
        env.pop(secret, None)
    if run([node, "--version"], env=env, capture=True) != "v" + config["nodeVersion"]:
        raise RuntimeError("Node executable version mismatch")
    run([*npm, "run", "build"], env=env)
    files = json.loads(run([*npm, "pack", "--dry-run", "--ignore-scripts", "--json"], env=env, capture=True))[0]["files"]
    payload = work / "payload"
    app = payload / "app"
    app.mkdir(parents=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(ROOT / "deployment" / name, app / name)
    run([*npm, "ci", "--omit=dev", "--no-audit", "--no-fund"], cwd=app, env=env)
    plugin = app / "node_modules/dsh-houdini"
    for entry in files:
        name = entry["path"]
        if "__pycache__" in Path(name).parts or name.endswith(".pyc"):
            continue
        source = deployment.checked_path(ROOT, name)
        destination = deployment.checked_path(plugin, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    # Keep the runtime graph flat so Cordis/DSH peer modules have one identity.
    runtime_pkg = deployment.read_json(plugin / "package.json")
    runtime_pkg.pop("scripts", None)
    runtime_pkg.pop("devDependencies", None)
    deployment.atomic_json(plugin / "package.json", runtime_pkg)
    shutil.copyfile(ROOT / "tools/prepare-managed-profile.mjs", app / "prepare-profile.mjs")
    (payload / "node").mkdir()
    for name in ("node.exe", "LICENSE"):
        shutil.copyfile(node_home / name, payload / "node" / name)
    run([node, "--input-type=module", "-e", "await import('dsh-houdini')"], cwd=app, env=env)
    notices = []
    for file in sorted((app / "node_modules").rglob("package.json")):
        try:
            info = deployment.read_json(file)
            if info.get("name") and info.get("version"):
                notices.append({"name": info["name"], "version": info["version"], "license": info.get("license", "SEE PACKAGE LICENSE"), "path": file.parent.relative_to(payload).as_posix()})
        except (ValueError, AttributeError):
            pass
    deployment.atomic_json(payload / "third-party-notices.json", notices)
    inventory = {}
    for file in sorted(payload.rglob("*")):
        if file.is_file():
            inventory[file.relative_to(payload).as_posix()] = deployment.digest(file)
    deployment.atomic_json(payload / "inventory.json", inventory)
    name = f"dsh-houdini-{package['version']}-win32-x64.zip"
    print("Compressing the complete offline runtime", flush=True)
    zip_tree(payload, output / name)
    manifest = {
        "schemaVersion": 1, "managerProtocol": 1, "version": package["version"], "commit": commit,
        "channel": "candidate" if args.candidate else "stable", "platform": "win32-x64",
        "nodeVersion": config["nodeVersion"], "dshVersion": target_dsh, "houdini": config["houdini"],
        "inventorySha256": deployment.digest(payload / "inventory.json"),
        "lockSha256": deployment.digest(app / "package-lock.json"),
        "asset": {"name": name, "size": (output / name).stat().st_size, "sha256": deployment.digest(output / name)},
    }
    deployment.validate_manifest(manifest, allow_candidate=args.candidate)
    deployment.atomic_json(output / "release.json", manifest)
    if args.unsigned:
        print("Unsigned assembly built; transfer to the isolated signing environment", output, flush=True)
        return
    finalize(output, args.trust, args.key_id, node, candidate=True)


def finalize(output, trust_path, key_id, node, *, candidate=False):
    """No npm, imports from the payload, or payload execution on the signing host."""
    manifest = deployment.validate_manifest(deployment.read_json(output / "release.json"), allow_candidate=candidate)
    package = deployment.read_json(ROOT / "package.json")
    config = deployment.read_json(ROOT / "deployment/runtime.json")
    required = deployment.read_json(ROOT / "deployment/package.json")["dependencies"]["@deepseek-ai/dsh"]
    if (manifest["version"] != package["version"] or manifest["commit"] != run(["git", "rev-parse", "HEAD"], capture=True)
            or manifest["nodeVersion"] != config["nodeVersion"] or manifest["dshVersion"] != required):
        raise RuntimeError("Unsigned artifact identity does not match the checked-out release source")
    if not candidate:
        if run(["git", "describe", "--tags", "--exact-match", "HEAD"], capture=True) != "v" + manifest["version"]:
            raise RuntimeError("Signing requires the exact release tag")
        if trust_path.resolve() != (ROOT / "installer/release-trust.json").resolve():
            raise RuntimeError("Production signing must use the committed public trust store")
    trust = deployment.read_json(trust_path)
    name = manifest["asset"]["name"]
    if (output / name).stat().st_size != manifest["asset"]["size"] or deployment.digest(output / name) != manifest["asset"]["sha256"]:
        raise ValueError("Unsigned artifact checksum mismatch; refusing to sign")
    sign_env = dict(os.environ)
    sign_env.pop("RELEASE_PRIVATE_PEM", None)
    sign_env.pop("NODE_OPTIONS", None)
    sign_env.pop("NODE_PATH", None)
    run([node, ROOT / "tools/release-sign.mjs", "sign", output / "release.json", output / "release.sig.json", key_id], env=sign_env)
    deployment.load_signed(output, trust, allow_candidate=candidate)
    (ROOT / "tools/out").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="release-finalize-", dir=ROOT / "tools/out"))
    installer = work / "installer-bundle"
    (installer / "houdini/python3.11libs").mkdir(parents=True)
    shutil.copyfile(ROOT / "Install.cmd", installer / "Install.cmd")
    shutil.copytree(ROOT / "installer", installer / "installer")
    shutil.copyfile(trust_path, installer / "installer/release-trust.json")
    for filename in ("dsh_bootstrap.py", "dsh_install_ui.py", "dsh_deployment.py", "dsh_release_policy.py"):
        shutil.copyfile(ROOT / "houdini/python3.11libs" / filename, installer / "houdini/python3.11libs" / filename)
    zip_tree(installer, output / "dsh-houdini-installer.zip")
    # Offline wrapper: installer plus the exact signed payload, without recompression.
    with zipfile.ZipFile(output / f"dsh-houdini-{package['version']}-offline.zip", "x", compression=zipfile.ZIP_STORED) as offline:
        for file in sorted(installer.rglob("*")):
            if file.is_file():
                offline.write(file, file.relative_to(installer).as_posix())
        for filename in ("release.json", "release.sig.json", name):
            offline.write(output / filename, filename)
    print("Signed candidate built (not published)" if candidate else "Signed release built (not published)", output, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--trust", type=Path, default=ROOT / "installer/release-trust.json")
    parser.add_argument("--node-archive", type=Path)
    parser.add_argument("--candidate", action="store_true")
    parser.add_argument("--unsigned", action="store_true")
    build(parser.parse_args())
