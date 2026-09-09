"""Signed, side-by-side Windows deployments. No hou/Qt/Node bootstrap dependency.

All expensive functions are worker/CLI only. Publication metadata is never
installation authority: a locally trusted signing key must bind every payload.
No operation deletes an installation or the user's data.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
import zipfile

import dsh_release_policy as releases

PROTOCOL = 1
PLATFORM = "win32-x64"
MAX_ARCHIVE = 2 * 1024**3
MAX_UNPACKED = 6 * 1024**3
MAX_FILES = 100000
SHA256 = re.compile(r"[0-9a-f]{64}")
INSTALL_ID = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+-[0-9a-f]{12}-[0-9a-f]{8}")
_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def read_json(path: Path, limit=8 * 1024**2):
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"JSON too large: {path.name}")
    return json.loads(raw)


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temp.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def digest(path: Path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024**2), b""):
            result.update(chunk)
    return result.hexdigest()


def _payload_parts(relative: str):
    """Lexical validation shared by new empty extraction trees and readback."""
    if not isinstance(relative, str) or not relative or len(relative) > 220:
        raise ValueError("invalid payload path")
    parts = PurePosixPath(relative).parts
    if (relative != "/".join(parts) or not parts or "\\" in relative
            or any(p in (".", "..") or not p or p[-1] in " ." for p in parts)
            or any(ord(c) < 32 or c in ':*?"<>|' for c in relative)
            or relative.startswith("/")):
        raise ValueError(f"unsafe payload path: {relative!r}")
    if any(re.fullmatch(r"(?i)(?:con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?", p) for p in parts):
        raise ValueError("reserved Windows filename")
    return parts


def checked_path(root: Path, relative: str) -> Path:
    """Windows-safe portable path; reject traversal, ADS, aliases and links."""
    parts = _payload_parts(relative)
    root = root.resolve()
    target = root.joinpath(*parts)
    cursor = root
    for part in parts:
        cursor /= part
        if cursor.is_symlink() or (cursor.exists() and getattr(cursor.lstat(), "st_file_attributes", 0) & 1024):
            raise ValueError("reparse points are not allowed in installation paths")
    if not target.resolve().is_relative_to(root):
        raise ValueError("path escapes installation root")
    return target


def verify_signature(raw: bytes, signature: dict, trust: dict):
    """Strict RSASSA-PKCS1-v1_5 SHA-256 verification of public data (RFC 8017).

    Full encoded-block equality, no permissive ASN.1 parsing. Signing is done
    by Node's crypto library, never here; known-good/bad vectors cross-check it.
    """
    if trust.get("schemaVersion") != 1 or not isinstance(trust.get("keys"), list):
        raise ValueError("unsupported trust store")
    keys = [k for k in trust["keys"] if k.get("id") == signature.get("keyId")]
    if len(keys) != 1:
        raise ValueError("Unknown release signing key. Install a trusted newer installer; no code was installed.")
    key = keys[0]
    def integer(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("invalid RSA public key")
        return int.from_bytes(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)), "big")
    n, e = integer(key["n"]), integer(key["e"])
    if not 3072 <= n.bit_length() <= 4096 or e != 65537:
        raise ValueError("unsupported RSA signing key")
    sig = base64.b64decode(signature["signature"], validate=True)
    size = (n.bit_length() + 7) // 8
    if len(sig) != size or int.from_bytes(sig, "big") >= n:
        raise ValueError("invalid release signature")
    actual = pow(int.from_bytes(sig, "big"), e, n).to_bytes(size, "big")
    suffix = _DIGEST_INFO + hashlib.sha256(raw).digest()
    expected = b"\x00\x01" + b"\xff" * (size - len(suffix) - 3) + b"\x00" + suffix
    if actual != expected:
        raise ValueError("Release signature mismatch; no code was installed")


def validate_manifest(data, *, allow_candidate=False):
    fields = {"schemaVersion", "managerProtocol", "version", "commit", "channel", "platform",
              "nodeVersion", "dshVersion", "houdini", "inventorySha256", "lockSha256", "asset"}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError("unsupported release manifest fields")
    if (type(data["schemaVersion"]) is not int or data["schemaVersion"] != 1
            or type(data["managerProtocol"]) is not int or data["managerProtocol"] != PROTOCOL):
        raise ValueError("This release needs a newer installer")
    releases.stable_version(data["version"])
    if data["channel"] != "stable" and not (allow_candidate and data["channel"] == "candidate"):
        raise ValueError("Only signed stable releases can be installed")
    if data["platform"] != PLATFORM:
        raise ValueError("Release is not for Windows x64")
    if not isinstance(data["commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", data["commit"]):
        raise ValueError("release needs an exact source commit")
    for field in ("inventorySha256", "lockSha256"):
        if not isinstance(data[field], str) or not SHA256.fullmatch(data[field]):
            raise ValueError(f"invalid {field}")
    releases.stable_version(data["nodeVersion"])
    if not isinstance(data["dshVersion"], str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", data["dshVersion"]):
        raise ValueError("DSH version must be exact")
    if (not isinstance(data["houdini"], list) or not data["houdini"]
            or len(set(data["houdini"])) != len(data["houdini"])
            or any(v not in ("21.0", "22.0") for v in data["houdini"])):
        raise ValueError("unsupported Houdini compatibility list")
    asset = data["asset"]
    expected_name = f"dsh-houdini-{data['version']}-{PLATFORM}.zip"
    if (not isinstance(asset, dict) or set(asset) != {"name", "size", "sha256"}
            or asset["name"] != expected_name or type(asset["size"]) is not int
            or not 0 < asset["size"] <= MAX_ARCHIVE
            or not isinstance(asset["sha256"], str) or not SHA256.fullmatch(asset["sha256"])):
        raise ValueError("invalid release asset")
    return data


def load_signed(directory: Path, trust: dict, *, allow_candidate=False):
    manifest = directory / "release.json"
    if manifest.stat().st_size > 65536:
        raise ValueError("release manifest too large")
    raw = manifest.read_bytes()
    verify_signature(raw, read_json(directory / "release.sig.json", 8192), trust)
    return validate_manifest(json.loads(raw), allow_candidate=allow_candidate)


def extract_payload(archive: Path, dest: Path, manifest: dict, progress=lambda s: None):
    asset = manifest["asset"]
    if archive.stat().st_size != asset["size"] or digest(archive) != asset["sha256"]:
        raise ValueError("Downloaded/local package checksum does not match the signed manifest")
    if dest.is_symlink() or getattr(dest.lstat(), "st_file_attributes", 0) & 1024 or any(dest.iterdir()):
        raise ValueError("Extraction requires a new empty non-linked staging directory")
    with zipfile.ZipFile(archive) as payload:
        infos = payload.infolist()
        if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_UNPACKED:
            raise ValueError("payload exceeds extraction limits")
        seen = set()
        for entry in infos:
            name = entry.filename[:-1] if entry.is_dir() else entry.filename
            _payload_parts(name)
            if name.casefold() in seen:
                raise ValueError("duplicate/case-colliding archive path")
            seen.add(name.casefold())
            mode = entry.external_attr >> 16
            if entry.flag_bits & 1 or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError("links/special/encrypted archive entries are not supported")
        required = sum(i.file_size for i in infos) + archive.stat().st_size + 64 * 1024**2
        if shutil.disk_usage(dest.parent).free < required:
            raise ValueError("Not enough disk space; the current installation is unchanged")
        for index, entry in enumerate(infos):
            # The staging directory started empty and this extractor cannot
            # create links. Avoid re-resolving every ancestor for every file.
            target = dest.joinpath(*_payload_parts(entry.filename.rstrip("/")))
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with payload.open(entry) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, 1024**2)
            if index % 250 == 0:
                progress(f"Extracting files · {index + 1}/{len(infos)}")
    verify_inventory(dest, manifest, progress)


def verify_inventory(root: Path, manifest: dict, progress=lambda s: None):
    inventory_path = checked_path(root, "inventory.json")
    if digest(inventory_path) != manifest["inventorySha256"]:
        raise ValueError("file inventory checksum mismatch")
    inventory = read_json(inventory_path, 32 * 1024**2)
    if not isinstance(inventory, dict) or not 1 <= len(inventory) <= MAX_FILES:
        raise ValueError("invalid file inventory")
    actual = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in dirs + files:
            item = base / name
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 1024:
                raise ValueError("unexpected link in installation")
            if name in files and not stat.S_ISREG(info.st_mode):
                raise ValueError("unexpected special file in installation")
        for name in files:
            file = base / name
            relative = file.relative_to(root).as_posix()
            _payload_parts(relative)
            if relative in ("inventory.json", "release.json", "release.sig.json"):
                continue
            key = relative.casefold()
            if key in actual:
                raise ValueError("case-colliding installed file")
            actual[key] = file
            if len(actual) > MAX_FILES:
                raise ValueError("installation exceeds file count limit")
    expected = set()
    for index, (name, sha) in enumerate(inventory.items()):
        _payload_parts(name)
        if name.casefold() in expected or not isinstance(sha, str) or not SHA256.fullmatch(sha):
            raise ValueError("invalid inventory entry")
        expected.add(name.casefold())
        file = actual.get(name.casefold())
        if file is None or digest(file) != sha:
            raise ValueError(f"Missing or damaged file: {name}. Use Install / repair.")
        if index % 500 == 0:
            progress(f"Checking files · {index + 1}/{len(inventory)}")
    if set(actual) != expected:
        raise ValueError("unlisted files in installation")
    if digest(root / "app/package-lock.json") != manifest["lockSha256"]:
        raise ValueError("runtime dependency lock mismatch")
    dsh = read_json(root / "app/node_modules/@deepseek-ai/dsh/package.json")
    plugin = read_json(root / "app/node_modules/dsh-houdini/package.json")
    if dsh["version"] != manifest["dshVersion"] or plugin["version"] != manifest["version"]:
        raise ValueError("installed package versions do not match the release")
    return inventory


class FileLease:
    """OS lifetime lock: crash/reboot releases it without deleting a stale lock."""
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open("a+b")
        try:
            self.handle.seek(0)
            if self.handle.read(1) == b"":
                self.handle.write(b"0")
                self.handle.flush()
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            raise RuntimeError("Another install/runtime operation is active. Close the other managed Houdini workspace and retry.") from exc

    def close(self):
        self.handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def empty_state():
    return {"schemaVersion": 1, "current": None, "previous": None, "pending": None}


class Store:
    def __init__(self, root: Path | str, trust: dict, *, allow_candidate=False):
        self.root = Path(root).resolve()
        if self.root == self.root.parent or self.root == Path.home().resolve():
            raise ValueError("installation root must be a dedicated directory")
        self.trust = trust
        self.allow_candidate = allow_candidate

    def state(self):
        path = self.root / "state.json"
        state = read_json(path) if path.exists() else empty_state()
        if not isinstance(state, dict) or set(state) != set(empty_state()) or state["schemaVersion"] != 1:
            raise ValueError("Installation state is damaged. Preserve this folder for data recovery and choose a new installation root; reinstalling program files cannot recover the selection.")
        for field in ("current", "previous", "pending"):
            if state[field] is not None:
                self.installation(state[field])
        return state

    def installation(self, install_id):
        if not isinstance(install_id, str) or not INSTALL_ID.fullmatch(install_id):
            raise ValueError("invalid installation identity")
        return checked_path(self.root, "releases/" + install_id)

    def manifest(self, install_id):
        return load_signed(self.installation(install_id), self.trust, allow_candidate=self.allow_candidate)

    def stage(self, directory: Path, progress=lambda s: None):
        """Never overwrite the serving directory; interruption leaves only staging."""
        manifest = load_signed(directory, self.trust, allow_candidate=self.allow_candidate)
        with FileLease(self.root / "install.lock"):
            state = self.state()
            progress("Verifying the signed package")
            staging = self.root / "staging"
            staging.mkdir(parents=True, exist_ok=True)
            temp = Path(tempfile.mkdtemp(prefix="install-", dir=staging))
            extract_payload(directory / manifest["asset"]["name"], temp, manifest, progress)
            shutil.copyfile(directory / "release.json", temp / "release.json")
            shutil.copyfile(directory / "release.sig.json", temp / "release.sig.json")
            install_id = f"{manifest['version']}-{manifest['asset']['sha256'][:12]}-{uuid.uuid4().hex[:8]}"
            destination = self.installation(install_id)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp.rename(destination)
            progress("Preparing this verified package for the next Houdini start")
            state["pending"] = install_id
            atomic_json(self.root / "state.json", state)
            return install_id

    def rollback(self):
        with FileLease(self.root / "install.lock"):
            state = self.state()
            if not state["previous"]:
                raise ValueError("No previous installation is available")
            manifest = self.manifest(state["previous"])
            verify_inventory(self.installation(state["previous"]), manifest)
            state["pending"] = state["previous"]
            atomic_json(self.root / "state.json", state)
        return state["pending"]

    def cancel_pending(self):
        with FileLease(self.root / "install.lock"):
            state = self.state()
            state["pending"] = None
            atomic_json(self.root / "state.json", state)

    def activate(self, pinned_id, houdini_version, progress=lambda s: None, prepare=None):
        """Worker only, called for the selection captured at Houdini startup.

        Returns a lifetime runtime lease; keep it alive until Houdini exits.
        Runtime is exclusive across managed Houdini instances, but staging is not.
        """
        lease = FileLease(self.root / "runtime.lock")
        try:
            with FileLease(self.root / "install.lock"):
                state = self.state()
                if pinned_id not in (state["current"], state["pending"]) or not pinned_id:
                    raise ValueError("Installation selection changed. Restart Houdini before opening the workspace.")
                manifest = self.manifest(pinned_id)
                if houdini_version not in manifest["houdini"]:
                    raise ValueError("This release does not support this Houdini version")
                install = self.installation(pinned_id)
                verify_inventory(install, manifest, progress)
                home = checked_path(self.root, "data/" + pinned_id)
                if home.exists() and pinned_id not in (state["current"], state["previous"]):
                    # A failed activation's snapshot must not later hide newer
                    # changes made in the still-serving version. Retain it for
                    # recovery and take a fresh snapshot, never merge or delete.
                    retained = checked_path(self.root, "data/incomplete-" + uuid.uuid4().hex)
                    home.rename(retained)
                if not home.exists():
                    data_root = self.root / "data"
                    data_root.mkdir(exist_ok=True)
                    data_temp = Path(tempfile.mkdtemp(prefix="snapshot-", dir=data_root))
                    previous = state["current"]
                    if previous and previous != pinned_id:
                        source = checked_path(self.root, "data/" + previous)
                        if source.exists():
                            progress("Copying a version-isolated snapshot of your DSH data")
                            self._copy_data(source, data_temp)
                    data_temp.rename(home)
                context = {
                    "schemaVersion": 1, "root": str(self.root), "installId": pinned_id,
                    "install": str(install), "home": str(home), "version": manifest["version"],
                    "nodeVersion": manifest["nodeVersion"], "dshVersion": manifest["dshVersion"],
                }
                self.probe(context, progress)
                if prepare is not None:
                    prepare(context, progress)
                if pinned_id == state["pending"]:
                    state["previous"] = state["current"]
                    state["current"] = pinned_id
                    state["pending"] = None
                    atomic_json(self.root / "state.json", state)
                return context, lease
        except BaseException:
            lease.close()
            raise

    @staticmethod
    def _copy_data(source: Path, destination: Path):
        # Profiles hold machine-specific fallback junctions. Preserve regular
        # config files, never follow these links into installed dependencies.
        ignored = {"node_modules", ".dsh-module-fallback"}
        for directory, dirs, files in os.walk(source, followlinks=False):
            base = Path(directory)
            dirs[:] = [name for name in dirs if name not in ignored and not (base / name).is_symlink()
                       and not getattr((base / name).lstat(), "st_file_attributes", 0) & 1024]
            if base.relative_to(source).parts == (".agent-presets",):
                # Regenerate only product-owned presets; user-created presets
                # are data and must survive updates along with their sessions.
                dirs[:] = [name for name in dirs if name not in ("houdini", "houdini-dev")]
            target = destination / base.relative_to(source)
            target.mkdir(parents=True, exist_ok=True)
            for name in files:
                item = base / name
                if not item.is_symlink() and not getattr(item.lstat(), "st_file_attributes", 0) & 1024:
                    shutil.copy2(item, target / name)

    @staticmethod
    def probe(context, progress=lambda s: None):
        install = Path(context["install"])
        node = install / "node/node.exe"
        env = runtime_env(context)
        for args, cwd, expected in (
            ([str(node), "--version"], install, "v" + context["nodeVersion"]),
            ([str(node), str(install / "app/node_modules/@deepseek-ai/dsh/lib/bin.js"), "--version"], install, context["dshVersion"]),
            ([str(node), "--input-type=module", "-e", "await import('dsh-houdini')"], install / "app", None),
        ):
            progress("Checking the bundled Node, DSH and plugin")
            result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=90, creationflags=_NO_WINDOW)
            if result.returncode or (expected is not None and result.stdout.strip() != expected):
                raise RuntimeError("Bundled runtime preflight failed: " + (result.stderr or result.stdout)[-3000:])


def runtime_env(context):
    env = dict(os.environ)
    install = Path(context["install"])
    env.update(DSH_HOME=context["home"], NODE_ENV="production",
               NPM_CONFIG_CACHE=str(Path(context["root"]) / "cache"),
               PYTHONDONTWRITEBYTECODE="1")
    env.pop("NODE_OPTIONS", None)
    env.pop("NODE_PATH", None)
    env.pop("PSModulePath", None)
    env.pop("DSH_HOUDINI_BRIDGE_URL", None)
    if "bridgePort" in context:
        if type(context["bridgePort"]) is not int or not 1024 <= context["bridgePort"] <= 65535:
            raise ValueError("invalid managed bridge port")
        env["DSH_HOUDINI_BRIDGE_URL"] = f"http://127.0.0.1:{context['bridgePort']}"
    env["PATH"] = str(install / "node") + os.pathsep + env.get("PATH", "")
    return env


class _ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in (
            "github.com", "api.github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"
        ) or parsed.username or parsed.password:
            raise ValueError("release download redirected outside the trusted HTTPS hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, target: Path, limit, progress=lambda s: None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password:
        raise ValueError("release downloads must originate on GitHub HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "dsh-houdini-installer"})
    total = 0
    opener = urllib.request.build_opener(_ReleaseRedirect())
    with opener.open(request, timeout=30) as response, target.open("xb") as output:
        while True:
            chunk = response.read(1024**2)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ValueError("download exceeds the signed/metadata size limit")
            output.write(chunk)
            progress(f"Downloading {target.name} · {total // 1024**2} MiB")


def fetch_release(store: Store, release: dict, progress=lambda s: None):
    metadata = releases._read_json(f"{releases.REPOSITORY_API}/releases/{int(release['id'])}")
    checked = releases.validate_published_release(metadata)
    if checked["id"] != release["id"] or checked["version"] != release["version"]:
        raise ValueError("Published release changed; refresh before installing")
    if metadata.get("immutable") is not True:
        raise ValueError("The publisher must enable immutable GitHub Releases before in-app installation")
    names = {"release.json": 65536, "release.sig.json": 8192}
    base = f"{releases.RELEASES_URL}/download/{checked['tag']}/"
    assets = metadata.get("assets", [])
    def asset_url(name, limit):
        matching = [a for a in assets if a.get("name") == name and a.get("state") == "uploaded"]
        if len(matching) != 1 or type(matching[0].get("size")) is not int or not 0 < matching[0]["size"] <= limit:
            raise ValueError("Release assets are missing or invalid: " + name)
        url = base + name
        if matching[0].get("browser_download_url") != url:
            raise ValueError("Release asset URL does not belong to this publication")
        return url
    downloads = store.root / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    dest = Path(tempfile.mkdtemp(prefix="release-", dir=downloads))
    for name, limit in names.items():
        download(asset_url(name, limit), dest / name, limit, progress)
    manifest = load_signed(dest, store.trust)
    if manifest["version"] != checked["version"]:
        raise ValueError("Signed version does not match the GitHub release tag")
    asset = manifest["asset"]
    download(asset_url(asset["name"], asset["size"]), dest / asset["name"], asset["size"], progress)
    return dest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "status", "rollback", "cancel"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--trust", type=Path, required=True)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--allow-candidate", action="store_true", help="explicit isolated developer tests only")
    args = parser.parse_args()
    store = Store(args.root, read_json(args.trust), allow_candidate=args.allow_candidate)
    if args.action == "stage":
        if args.directory is None:
            parser.error("stage requires --directory")
        print(store.stage(args.directory, print))
    elif args.action == "rollback":
        print(store.rollback())
    elif args.action == "cancel":
        store.cancel_pending()
    else:
        print(json.dumps(store.state(), indent=2))
