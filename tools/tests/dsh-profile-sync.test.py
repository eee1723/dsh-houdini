"""Standard-library regression for the declarative DSH profile contract."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

import dsh_profile_sync as sync


requirements = sync.load_requirements(ROOT / "dsh-profile.requirements.json")
assert requirements["profile"] == "web"
assert [item["name"] for item in requirements["plugins"]] == [
    "dsh-houdini", "dsh-vision-router",
]

with tempfile.TemporaryDirectory() as raw_home:
    home = Path(raw_home)
    profile = home / "profiles" / "web"
    profile.mkdir(parents=True)
    manifest = {
        "dependencies": {
            "dsh-houdini": f"link:{ROOT.as_posix()}",
            "dsh-vision-router": "1.6.0",
        },
        "dsh": {"profile": {"bundles": ["dsh-houdini", "dsh-vision-router"]}},
    }
    (profile / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    for name, version in (("dsh-houdini", "0.1.0"), ("dsh-vision-router", "1.6.0")):
        package_dir = profile / "node_modules" / name
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text(
            json.dumps({"name": name, "version": version}), encoding="utf-8",
        )

    status = sync.inspect_profile(requirements, project_root=ROOT, home=home)
    assert status["ok"], status
    assert sync.required_install_specs(requirements, status, project_root=ROOT) == []

    manifest["dsh"]["profile"]["bundles"].remove("dsh-vision-router")
    (profile / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    missing = sync.inspect_profile(requirements, project_root=ROOT, home=home)
    assert not missing["ok"]
    assert sync.required_install_specs(requirements, missing, project_root=ROOT) == [
        "dsh-vision-router@1.6.0",
    ]

    manifest["dsh"]["profile"]["bundles"].extend([
        "dsh-vision-router", "dsh-vision-router",
    ])
    (profile / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    duplicate = sync.inspect_profile(requirements, project_root=ROOT, home=home)
    assert not duplicate["ok"]
    assert duplicate["plugins"][1]["bundleCount"] == 2

print("dsh profile sync tests passed")
