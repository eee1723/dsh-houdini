"""Regression for fail-closed DSH runtime selection and activation."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

import dsh_runtime_compat as compat


manifest = compat.load_manifest()
assert manifest["preferredVersion"] == "0.1.2-rc.1"
assert compat.verified_versions() == {"0.1.2-rc.1"}
compat.require_verified("0.1.2-rc.1")
try:
    compat.require_verified("99.0.0-unseen")
except RuntimeError as exc:
    message = str(exc)
    assert "downloaded but not compatibility-verified" in message
    assert "serving runtime was not changed" in message
else:
    raise AssertionError("unverified DSH releases must fail closed")

with tempfile.TemporaryDirectory() as raw_dir:
    path = Path(raw_dir) / "compat.json"
    path.write_text(json.dumps({
        "schemaVersion": 1,
        "preferredVersion": "missing",
        "releases": [{"dshVersion": "verified"}],
    }), encoding="utf-8")
    try:
        compat.load_manifest(path)
    except RuntimeError as exc:
        assert "is not a verified release" in str(exc)
    else:
        raise AssertionError("preferred release must be present in releases")


print("dsh runtime compatibility policy tests passed")
