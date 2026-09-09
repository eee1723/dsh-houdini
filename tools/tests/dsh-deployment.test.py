"""Offline signed install/rollback/failure tests. All writes are isolated fixtures."""
from __future__ import annotations

import json
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
import dsh_deployment as d

NODE = shutil.which("node")
if not NODE:
    raise RuntimeError("Development regression needs Node to create independent RSA fixtures")

def rejects(call, match=None):
    try:
        call()
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        if match:
            assert match in str(exc), (match, exc)
        return
    raise AssertionError("unsafe operation accepted")

with tempfile.TemporaryDirectory(prefix="dsh-deployment-中文 空格-") as temporary:
    temp = Path(temporary)
    private, public = temp / "private.pem", temp / "trust.json"
    subprocess.run([NODE, str(ROOT / "tools/release-sign.mjs"), "keygen", str(private), str(public), "fixture"], check=True, capture_output=True)
    trust = d.read_json(public)
    env = dict(os.environ, DSH_RELEASE_SIGNING_KEY=str(private))
    serial = [0]
    def bundle(version="1.0.0", extra=(), channel="stable"):
        serial[0] += 1
        source = temp / f"bundle-{serial[0]}"
        source.mkdir()
        files = {
            "app/package-lock.json": b'{"lockfileVersion":3}',
            "app/node_modules/@deepseek-ai/dsh/package.json": b'{"version":"0.1.2-rc.1"}',
            "app/node_modules/dsh-houdini/package.json": json.dumps({"version": version}).encode(),
            "node/node.exe": b"fixture, never executed",
        }
        inventory = json.dumps({name: d.hashlib.sha256(raw).hexdigest() for name, raw in files.items()}).encode()
        name = f"dsh-houdini-{version}-win32-x64.zip"
        with zipfile.ZipFile(source / name, "w") as archive:
            for filename, raw in files.items():
                archive.writestr(filename, raw)
            archive.writestr("inventory.json", inventory)
            for filename, raw in extra:
                archive.writestr(filename, raw)
        manifest = {
            "schemaVersion": 1, "managerProtocol": 1, "version": version, "commit": "a" * 40,
            "channel": channel, "platform": "win32-x64", "nodeVersion": "24.17.0",
            "dshVersion": "0.1.2-rc.1", "houdini": ["21.0", "22.0"],
            "inventorySha256": d.hashlib.sha256(inventory).hexdigest(),
            "lockSha256": d.hashlib.sha256(files["app/package-lock.json"]).hexdigest(),
            "asset": {"name": name, "size": (source / name).stat().st_size, "sha256": d.digest(source / name)},
        }
        d.atomic_json(source / "release.json", manifest)
        subprocess.run([NODE, str(ROOT / "tools/release-sign.mjs"), "sign", str(source / "release.json"), str(source / "release.sig.json"), "fixture"], env=env, check=True)
        return source
    first, second = bundle(), bundle("1.1.0")
    store = d.Store(temp / "managed", trust)
    initial = store.state()
    # Online discovery still passes through the same signature/asset gates.
    # HTTP is mocked; these tests never publish a fixture or contact GitHub.
    manifest = d.read_json(first / "release.json")
    metadata = {"id": 42, "draft": False, "prerelease": False, "immutable": True,
                "published_at": "2026-09-09T00:00:00Z", "tag_name": "v1.0.0"}
    names = ["release.json", "release.sig.json", manifest["asset"]["name"]]
    metadata["assets"] = [{"name": name, "state": "uploaded", "size": (first / name).stat().st_size,
                           "browser_download_url": d.releases.RELEASES_URL + "/download/v1.0.0/" + name} for name in names]
    remote = {"id": 42, "version": "1.0.0"}
    copied = []
    def fetch_file(url, target, limit, progress):
        copied.append(target.name)
        assert url == d.releases.RELEASES_URL + "/download/v1.0.0/" + target.name
        shutil.copyfile(first / target.name, target)
    with patch.object(d.releases, "_read_json", return_value=metadata), patch.object(d, "download", fetch_file):
        downloaded = d.fetch_release(store, remote)
        assert d.load_signed(downloaded, trust) == manifest and copied == names
    for changed in ({"immutable": False}, {"id": 43}, {"assets": []}, {"draft": True}):
        with patch.object(d.releases, "_read_json", return_value={**metadata, **changed}):
            rejects(lambda: d.fetch_release(store, remote))
    wrong_assets = [dict(item) for item in metadata["assets"]]
    wrong_assets[0]["browser_download_url"] = "https://example.invalid/release.json"
    with patch.object(d.releases, "_read_json", return_value={**metadata, "assets": wrong_assets}):
        rejects(lambda: d.fetch_release(store, remote), "URL")
    redirect = d._ReleaseRedirect()
    request = d.urllib.request.Request("https://github.com/eee1723/dsh-houdini/releases")
    for url in ("http://github.com/file", "https://example.invalid/file", "file:///C:/file", "https://user:secret@github.com/file"):
        rejects(lambda: redirect.redirect_request(request, None, 302, "fixture", {}, url), "trusted HTTPS")
    class DownloadFixture:
        def open(self, *args, **kwargs):
            return io.BytesIO(b"too many bytes")
    with patch.object(d.urllib.request, "build_opener", return_value=DownloadFixture()):
        rejects(lambda: d.download("https://github.com/eee1723/dsh-houdini/file", temp / "oversized-download", 2), "size limit")
    # Signature/unknown-key/malformed metadata do not even create state.
    rejects(lambda: d.Store(temp / "unknown", {"schemaVersion": 1, "keys": []}).stage(first), "Unknown release signing key")
    signed_raw = (first / "release.json").read_bytes()
    signature = d.read_json(first / "release.sig.json")
    d.verify_signature(signed_raw, signature, trust)
    rejects(lambda: d.verify_signature(signed_raw + b" ", signature, trust), "signature mismatch")
    malformed = dict(signature, signature="AA==")
    rejects(lambda: d.verify_signature(signed_raw, malformed, trust), "invalid release signature")
    for field, value in (("managerProtocol", 99), ("platform", "linux-x64"), ("channel", "preview"),
                         ("version", "1.0.0-rc"), ("nodeVersion", "latest"), ("dshVersion", "^0.1.2"),
                         ("houdini", ["99.0"]), ("commit", "main")):
        rejects(lambda: d.validate_manifest({**d.read_json(first / "release.json"), field: value}))
    candidate = bundle(channel="candidate")
    rejects(lambda: store.stage(candidate), "stable")
    assert store.state() == initial

    for name in ("../escape", "/escape", "a\\b", "a:b", "CON", "nul.txt", "a.", "a /b", "app//x"):
        rejects(lambda: d.checked_path(temp, name))
    for extra in ([('../escape', b'x')], [('NODE/node.exe', b'x')], [('unlisted.txt', b'x')]):
        bad = bundle(extra=extra)
        rejects(lambda: store.stage(bad))
        assert store.state() == initial
        assert not (temp / "escape").exists()
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = (0o120777 << 16)
    bad = bundle(extra=[(link, b"../../elsewhere")])
    rejects(lambda: store.stage(bad), "links")
    with patch.object(d.shutil, "disk_usage", return_value=shutil._ntuple_diskusage(1, 1, 0)):
        rejects(lambda: store.stage(first), "disk space")
    def cancel(message):
        raise InterruptedError("fixture cancelled")
    rejects(lambda: store.stage(first, cancel), "cancelled")
    assert store.state() == initial
    with patch.object(d.os, "replace", side_effect=OSError("write failed")):
        rejects(lambda: store.stage(first), "write failed")
    assert store.state() == initial

    ident1 = store.stage(first)
    assert store.state()["pending"] == ident1 and store.state()["current"] is None
    # No system Node / npm is consulted by staging, hashing or selection.
    with patch.object(d.Store, "probe", staticmethod(lambda *args: None)):
        ctx1, lease1 = store.activate(ident1, "21.0")
        assert store.state()["current"] == ident1
        d.atomic_json(Path(ctx1["home"]) / "session.json", {"value": "old data"})
        d.atomic_json(Path(ctx1["home"]) / ".agent-presets/custom/agent.json", {"name": "user preset"})
        d.atomic_json(Path(ctx1["home"]) / ".agent-presets/houdini/agent.json", {"name": "old managed preset"})
        ident2 = store.stage(second)
        rejects(lambda: store.activate(ident2, "21.0"), "Another")
        assert store.state()["current"] == ident1
        lease1.close()
        rejects(lambda: store.activate(ident2, "99.0"), "support")
        rejects(lambda: store.activate(ident2, "22.0", prepare=lambda *a: (_ for _ in ()).throw(RuntimeError("profile failed"))), "profile failed")
        assert store.state()["current"] == ident1
        ctx2, lease2 = store.activate(ident2, "22.0")
        assert d.read_json(Path(ctx2["home"]) / "session.json")["value"] == "old data"
        assert d.read_json(Path(ctx2["home"]) / ".agent-presets/custom/agent.json")["name"] == "user preset"
        assert not (Path(ctx2["home"]) / ".agent-presets/houdini/agent.json").exists()
        d.atomic_json(Path(ctx2["home"]) / "session.json", {"value": "new data"})
        assert store.rollback() == ident1
        lease2.close()
        ctx_old, lease_old = store.activate(ident1, "21.0")
        assert d.read_json(Path(ctx_old["home"]) / "session.json")["value"] == "old data"
        assert d.read_json(Path(ctx2["home"]) / "session.json")["value"] == "new data"
        lease_old.close()
    assert store.installation(ident2).is_dir(), "rollback must not delete the newer installation"
    store.stage(second)
    store.cancel_pending()
    assert store.state()["pending"] is None and store.state()["current"] == ident1
    damaged = store.installation(ident1) / "node/node.exe"
    damaged.write_bytes(b"damaged")
    rejects(lambda: d.verify_inventory(store.installation(ident1), store.manifest(ident1)), "damaged")

    # Kernel-backed lock excludes a separate process and recovers after close.
    lock = temp / "process.lock"
    command = [sys.executable, "-c", "import sys;sys.path.insert(0,sys.argv[1]);from dsh_deployment import FileLease;from pathlib import Path;FileLease(Path(sys.argv[2])).close()", str(ROOT / "houdini/python3.11libs"), str(lock)]
    with d.FileLease(lock):
        assert subprocess.run(command, capture_output=True).returncode != 0
    assert subprocess.run(command, capture_output=True).returncode == 0

print("signed deployment: signature, traversal, cancellation, disk/write failures, exclusive activation, data snapshot and rollback passed")
