"""Exact official compatibility and owned fixture lookup; no user installation changes."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
import dsh_runtime_compat as compat

manifest = compat.load_manifest()
required = manifest["preferredVersion"]
declared = {row["dshVersion"] for row in manifest["releases"]}
assert compat.verified_versions() == declared
assert compat.preferred_spec() == "@deepseek-ai/dsh@" + required
for version in declared:
    compat.require_verified(version)
package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
fixture = json.loads((ROOT / "deployment/package.json").read_text(encoding="utf-8"))
assert package["engines"]["dsh"] == " || ".join(row["dshVersion"] for row in manifest["releases"])
assert fixture["dependencies"]["@deepseek-ai/dsh"] == required
assert manifest["runtimeOwnership"] == "host" and "runtimeFixes" not in manifest
try:
    compat.require_verified("99.0.0-unseen")
except RuntimeError as error:
    assert "not declared compatible" in str(error) and "runtime was not changed" in str(error)
else:
    raise AssertionError("unknown versions must be refused without replacing Desktop")

with tempfile.TemporaryDirectory(prefix="dsh-official-compat-") as raw:
    directory = Path(raw)
    policy = directory / "compat.json"
    policy.write_text(json.dumps({"schemaVersion": 1, "preferredVersion": required,
        "releases": [{"dshVersion": required}]}), encoding="utf-8")
    def fixture_at(name, version=required, marker=True):
        target = directory / "_npx" / name
        binary = target / "node_modules/@deepseek-ai/dsh/lib/bin.js"
        binary.parent.mkdir(parents=True)
        binary.write_text("// inert fixture; never executed", encoding="utf-8")
        (binary.parent.parent / "package.json").write_text(json.dumps({"name": "@deepseek-ai/dsh", "version": version}), encoding="utf-8")
        (target / "package.json").write_text('{"private":true}', encoding="utf-8")
        (target / "package-lock.json").write_text('{"lockfileVersion":3}', encoding="utf-8")
        digest = hashlib.sha256()
        for filename in ("package.json", "package-lock.json"):
            digest.update(filename.encode("utf-8")); digest.update((target / filename).read_bytes())
        if marker:
            (target / ".dsh-official-host.json").write_text(json.dumps({"schemaVersion": 1,
                "runtimeOwnership": "development-fixture", "dshVersion": version,
                "inputsSha256": digest.hexdigest()}), encoding="utf-8")
        return target, binary
    fixture_at("arbitrary-npx-same-version", marker=False)
    fixture_at("dsh-houdini-official-99.0.0-unseen-stale", "99.0.0-unseen")
    assert compat.preferred_cached_bin(directory, policy) is None
    target, binary = fixture_at("dsh-houdini-official-" + required + "-owned")
    assert compat.preferred_cached_bin(directory, policy) == binary
    assert compat.official_runtime_identity(binary, policy)["runtimeOwnership"] == "development-fixture"
    # An old patched artifact is never selected merely because its package
    # version equals the official package target.
    marker = target / ".dsh-runtime-fixes.json"
    marker.write_text("{}", encoding="utf-8")
    assert compat.preferred_cached_bin(directory, policy) is None
    marker.unlink()
    (target / "package-lock.json").write_text('{"lockfileVersion":3,"changed":true}', encoding="utf-8")
    assert compat.preferred_cached_bin(directory, policy) is None
    policy.write_text(json.dumps({"schemaVersion": 1, "preferredVersion": required,
        "releases": [{"dshVersion": "0.0.1-unrelated"}]}), encoding="utf-8")
    try:
        compat.load_manifest(policy)
    except RuntimeError as error:
        assert "is not a verified release" in str(error)
    else:
        raise AssertionError("the preferred target must be explicitly declared")

print("official DSH exact compatibility and isolated fixture selection passed")
