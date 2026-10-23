"""Offline signed install/rollback/failure tests. All writes are isolated fixtures."""
from __future__ import annotations

import json
import io
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
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


def json_publication_cases(folder):
    record = folder / "publication.json"
    first = {"generation": "first", "text": "完整中文"}
    second = {"generation": "second", "text": "完整中文"}
    d.atomic_json(record, first)
    assert d.read_json(record) == first
    assert not list(folder.glob("publication.json.*.tmp"))
    with d._json_snapshot(record) as snapshot:
        # Publication while a reader is live is deterministic, not a stress
        # test that succeeds only when a scheduling race happens to be absent.
        d.atomic_json(record, second)
        assert json.load(snapshot) == first
        assert d.read_json(record) == second
    rejects(lambda: d.read_json(record, limit=4), "JSON too large")
    record.write_bytes(b"invalid JSON")
    rejects(lambda: d.read_json(record), "Expecting value")
    record.unlink()
    started = time.monotonic()
    try:
        d.read_json(record)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError('a genuinely absent record was replaced with default state')
    assert time.monotonic() - started < .5, 'a missing record caused an unbounded wait'

    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    # Only native publication-window errors retry, under one total deadline.
    for code in (2, 32, 33):
        with patch.object(d, '_json_snapshot', side_effect=[ctypes.WinError(code), io.BytesIO(json.dumps(first).encode())]), \
             patch.object(d.time, 'sleep') as delay:
            assert d.read_json(record) == first
            delay.assert_called_once_with(.002)
    denied = ctypes.WinError(5)
    with patch.object(d, '_json_snapshot', side_effect=denied) as reads, \
         patch.object(d.time, 'sleep', side_effect=AssertionError('permanent access denial retried')):
        rejects(lambda: d.read_json(record))
        reads.assert_called_once()
    with patch.object(d, '_json_snapshot', side_effect=ctypes.WinError(32)) as reads, \
         patch.object(d.time, 'monotonic', side_effect=[0, .01, .051]), patch.object(d.time, 'sleep') as delay:
        rejects(lambda: d.read_json(record))
        assert reads.call_count == 2 and delay.call_count == 1, 'retry deadline restarted or was ignored'

    # Shared-delete handles alone do not cover readers which open during the
    # actual ReplaceFileW window. Exercise both sides concurrently, retaining
    # complete data rather than translating a transient miss to offline state.
    concurrent = folder / 'concurrent-publication.json'
    d.atomic_json(concurrent, {'serial': -1, 'text': first['text']})
    done, errors = threading.Event(), []
    def publish():
        try:
            for serial in range(250):
                d.atomic_json(concurrent, {'serial': serial, 'text': first['text']})
        except Exception as error:
            errors.append(repr(error))
        finally:
            done.set()
    writer = threading.Thread(target=publish)
    writer.start()
    reads = 0
    try:
        while not done.is_set():
            value = d.read_json(concurrent)
            assert -1 <= value['serial'] < 250 and value['text'] == first['text'], value
            reads += 1
    finally:
        writer.join(10)
    assert reads and not errors and not writer.is_alive(), errors
    assert d.read_json(concurrent)['serial'] == 249

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    kernel.GetFileAttributesW.restype = wintypes.DWORD
    kernel.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel.SetFileAttributesW.restype = wintypes.BOOL
    d.atomic_json(record, first)
    attributes = kernel.GetFileAttributesW(str(record))
    try:
        assert kernel.SetFileAttributesW(str(record), attributes | 1)
        rejects(lambda: d.atomic_json(record, second))
        assert d.read_json(record) == first, "readonly publication changed the target"
    finally:
        assert kernel.SetFileAttributesW(str(record), attributes)

    # An unrelated reader that denies deletion is a real permission conflict.
    # The protocol must report it rather than retry, truncate or remove state.
    with record.open("rb") as denied_snapshot:
        rejects(lambda: d.atomic_json(record, second))
        assert json.load(denied_snapshot) == first
        assert d.read_json(record) == first

    # A distinct protected DACL must survive replacement rather than being
    # replaced by the temporary file's inherited permissions.
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    security.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.DWORD)]
    security.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPVOID]
    security.GetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    descriptor = wintypes.LPVOID()
    assert security.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        "D:P(A;;FA;;;SY)(A;;FA;;;OW)", 1, ctypes.byref(descriptor), None)
    try:
        assert security.SetFileSecurityW(str(record), 0x80000004, descriptor)
    finally:
        kernel.LocalFree(descriptor)
    def dacl():
        length = wintypes.DWORD()
        security.GetFileSecurityW(str(record), 4, None, 0, ctypes.byref(length))
        buffer = ctypes.create_string_buffer(length.value)
        assert security.GetFileSecurityW(str(record), 4, buffer, len(buffer), ctypes.byref(length))
        raw = buffer.raw[:length.value]
        # ReplaceFile may mark the new descriptor AUTO_INHERITED (0x400).
        # Preserve the actual ACEs and protection bit, not that bookkeeping.
        control = int.from_bytes(raw[2:4], "little") & ~0x400
        return raw[:2] + control.to_bytes(2, "little") + raw[4:]
    original_dacl = dacl()
    with d._json_snapshot(record) as snapshot:
        d.atomic_json(record, second)
        assert json.load(snapshot) == first
    assert dacl() == original_dacl, "atomic publication changed existing state permissions"
    assert d.read_json(record) == second

    # First creation may race another publisher; do not mistake a subsequent
    # real permission conflict for a missing file or claim that it succeeded.
    record.unlink()
    original_replace = d.os.replace
    held = []
    def concurrent_first_writer(source, destination):
        destination.write_text(json.dumps(first), encoding="utf8")
        held.append(destination.open("rb"))
        return original_replace(source, destination)
    try:
        with patch.object(d.os, "replace", side_effect=concurrent_first_writer):
            rejects(lambda: d.atomic_json(record, second))
        assert d.read_json(record) == first
    finally:
        for snapshot in held:
            snapshot.close()

with tempfile.TemporaryDirectory(prefix="dsh-deployment-中文 空格-") as temporary:
    temp = Path(temporary)
    json_publication_cases(temp)
    # A browser carrier can import successfully while the scoped agent is
    # missing. Exercise the actual Node resolver used before stage publication.
    probe_install = temp / "preflight"
    probe_plugin = probe_install / "app/node_modules/dsh-houdini"
    probe_plugin.mkdir(parents=True)
    d.atomic_json(probe_plugin / "package.json", {"name": "dsh-houdini", "type": "module",
        "exports": {".": "./frontend.js", "./agent": "./agent.js"}})
    (probe_plugin / "frontend.js").write_text("export function apply() {}", encoding="utf-8")
    probe_cli = probe_install / "app/node_modules/@deepseek-ai/dsh/lib/bin.js"
    probe_cli.parent.mkdir(parents=True)
    probe_cli.write_text("console.log('0.2.1-rc.2')", encoding="utf-8")
    node_version = subprocess.run([NODE, "--version"], check=True, capture_output=True,
                                  text=True).stdout.strip()[1:]
    probe_context = {"install": str(probe_install), "home": str(temp / "probe-home"),
                     "root": str(temp), "nodeVersion": node_version, "dshVersion": "0.2.1-rc.2"}
    actual_run = subprocess.run
    def run_probe(args, **kwargs):
        return actual_run([NODE, *args[1:]], **kwargs)
    with patch.object(d.subprocess, "run", run_probe):
        rejects(lambda: d.Store.probe(probe_context), "agent.js")
        d.atomic_json(probe_plugin / "package.json", {"name": "dsh-houdini", "type": "module",
            "exports": {".": "./frontend.js"}})
        d.Store.probe(probe_context)
        d.atomic_json(probe_plugin / "package.json", {"name": "dsh-houdini", "type": "module",
            "exports": {".": "./frontend.js", "./agent": "./agent.js"}})
        rejects(lambda: d.Store.probe(probe_context), "agent.js")
        (probe_plugin / "agent.js").write_text("export function apply() {}", encoding="utf-8")
        d.Store.probe(probe_context)
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
            "app/node_modules/@deepseek-ai/dsh/package.json": b'{"version":"0.1.6-alpha.2"}',
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
            "dshVersion": "0.1.6-alpha.2", "houdini": ["21.0", "22.0"],
            "inventorySha256": d.hashlib.sha256(inventory).hexdigest(),
            "lockSha256": d.hashlib.sha256(files["app/package-lock.json"]).hexdigest(),
            "asset": {"name": name, "size": (source / name).stat().st_size, "sha256": d.digest(source / name)},
        }
        d.atomic_json(source / "release.json", manifest)
        subprocess.run([NODE, str(ROOT / "tools/release-sign.mjs"), "sign", str(source / "release.json"), str(source / "release.sig.json"), "fixture"], env=env, check=True)
        return source
    first, second = bundle(), bundle("1.1.0")
    # The signed archive fixtures deliberately contain inert Node bytes. The
    # real bundled-runtime probe above is independent of these archive tests.
    fixture_probe = patch.object(d.Store, "probe", return_value=None)
    staged_probe = fixture_probe.start()
    # Finalization builds the bootstrap/installer from the signing checkout.
    # A correct unsigned artifact and tag cannot authorize dirty installer files.
    builder_spec = importlib.util.spec_from_file_location("release_builder_fixture", ROOT / "tools/build-release.py")
    builder = importlib.util.module_from_spec(builder_spec)
    builder_spec.loader.exec_module(builder)
    signing_source = temp / "signing-source"
    d.atomic_json(signing_source / "package.json", {"version": "1.0.0"})
    d.atomic_json(signing_source / "deployment/runtime.json", {"nodeVersion": "24.17.0"})
    d.atomic_json(signing_source / "deployment/package.json", {"dependencies": {"@deepseek-ai/dsh": "0.1.6-alpha.2"}})
    signing_trust = signing_source / "installer/release-trust.json"
    d.atomic_json(signing_trust, trust)
    for dirty_kind in ("tracked", "untracked"):
        commands = []
        def signing_command(args, **kwargs):
            commands.append(args)
            assert args[0] == "git", "a dirty signing checkout must never invoke the signer"
            if args[1] == "rev-parse":
                return "a" * 40
            if args[1] == "diff":
                return "changed installer" if dirty_kind == "tracked" else ""
            if args[1] == "ls-files":
                return "installer/unreviewed.py"
            if args[1] == "describe":
                return "v1.0.0"
            raise AssertionError(args)
        with patch.object(builder, "ROOT", signing_source), patch.object(builder, "run", signing_command):
            rejects(lambda: builder.finalize(first, signing_trust, "fixture", NODE), "clean checkout")
            assert any(command[1] == "diff" for command in commands)
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

    with patch.object(d.Store, "probe", side_effect=RuntimeError("bundled runtime cannot load")):
        rejects(lambda: store.stage(first), "cannot load")
    assert store.state() == initial, "failed runtime validation published an installation"
    staged_probe.reset_mock()
    ident1 = store.stage(first)
    staged_probe.assert_called_once()
    staged_context = staged_probe.call_args.args[0]
    assert Path(staged_context["install"]).parent == store.root / "staging"
    assert not Path(staged_context["home"]).exists(), "disposable probe data was retained"
    assert store.state()["pending"] == ident1 and store.state()["current"] is None
    # Ordinary activation consumes the stage transaction, without a second
    # payload walk or Node probe. Both first and repeated cold starts use it.
    with patch.object(d, "verify_inventory", side_effect=AssertionError("startup scanned the payload")), \
         patch.object(d.Store, "probe", side_effect=AssertionError("startup spawned a preflight")):
        ctx1, lease1 = store.activate(ident1, "21.0")
        lease1.close()
        ctx1, lease1 = store.activate(ident1, "21.0")
    # No system Node / npm is consulted by hashing or activation.
    with patch.object(d.Store, "probe", staticmethod(lambda *args: None)):
        assert store.state()["current"] == ident1
        d.atomic_json(Path(ctx1["home"]) / "session.json", {"value": "old data"})
        d.atomic_json(Path(ctx1["home"]) / ".agent-presets/custom/agent.json", {"name": "user preset"})
        d.atomic_json(Path(ctx1["home"]) / ".agent-presets/houdini/agent.json", {"name": "old managed preset"})
        d.atomic_json(Path(ctx1["home"]) / ".agent-presets/houdini-product/agent.json", {"name": "old product preset"})
        ident2 = store.stage(second)
        rejects(lambda: store.activate(ident2, "21.0"), "退出那个 Houdini 后重试")
        assert store.state()["current"] == ident1
        lease1.close()
        rejects(lambda: store.activate(ident2, "99.0"), "support")
        rejects(lambda: store.activate(ident2, "22.0", prepare=lambda *a: (_ for _ in ()).throw(RuntimeError("profile failed"))), "profile failed")
        assert store.state()["current"] == ident1
        ctx2, lease2 = store.activate(ident2, "22.0")
        assert d.read_json(Path(ctx2["home"]) / "session.json")["value"] == "old data"
        assert d.read_json(Path(ctx2["home"]) / ".agent-presets/custom/agent.json")["name"] == "user preset"
        assert not (Path(ctx2["home"]) / ".agent-presets/houdini/agent.json").exists()
        assert not (Path(ctx2["home"]) / ".agent-presets/houdini-product/agent.json").exists()
        d.atomic_json(Path(ctx2["home"]) / "session.json", {"value": "new data"})
        before_rollback = store.state()
        def cancel_rollback(message):
            if "Preparing rollback" in message:
                raise InterruptedError("rollback cancelled after verification")
        rejects(lambda: store.rollback(cancel_rollback), "rollback cancelled")
        assert store.state() == before_rollback, "cancellation before selection commit cannot prepare a rollback"
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

    lockfile = store.installation(ident1) / "app/package-lock.json"
    original_lock = lockfile.read_bytes()
    lockfile.write_bytes(b"changed lock")
    rejects(lambda: store.activate(ident1, "21.0"), "lock mismatch")
    lockfile.write_bytes(original_lock)
    package_file = store.installation(ident1) / "app/node_modules/@deepseek-ai/dsh/package.json"
    original_package = package_file.read_bytes()
    d.atomic_json(package_file, {"version": "99.0.0"})
    rejects(lambda: store.activate(ident1, "21.0"), "versions do not match")
    package_file.write_bytes(original_package)
    signed_file = store.installation(ident1) / "release.json"
    original_signed = signed_file.read_bytes()
    signed_file.write_bytes(original_signed + b" ")
    rejects(lambda: store.activate(ident1, "21.0"), "signature mismatch")
    signed_file.write_bytes(original_signed)
    fixture_probe.stop()

    # Kernel-backed lock excludes a separate process and recovers after close.
    lock = temp / "process.lock"
    command = [sys.executable, "-c", "import sys;sys.path.insert(0,sys.argv[1]);from dsh_deployment import FileLease;from pathlib import Path;FileLease(Path(sys.argv[2])).close()", str(ROOT / "houdini/python3.11libs"), str(lock)]
    with d.FileLease(lock):
        assert subprocess.run(command, capture_output=True).returncode != 0
    assert subprocess.run(command, capture_output=True).returncode == 0
    with d.FileLease(store.root / "install.lock"):
        rejects(store.cancel_pending, "另一项安装操作正在进行")

print("signed deployment: signature, traversal, cancellation, disk/write failures, exclusive activation, data snapshot and rollback passed")
