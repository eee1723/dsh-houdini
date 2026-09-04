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
    "dsh-houdini", "@anionex/dsh-vision-toolkit",
]
assert requirements["plugins"][1]["spec"] == "@anionex/dsh-vision-toolkit@0.1.40"
assert requirements["plugins"][1]["version"] == "0.1.40"
assert requirements["removePlugins"] == ["dsh-vision-router", "dsh-vision-fallback"]

with tempfile.TemporaryDirectory() as raw_home:
    home = Path(raw_home)
    profile = home / "profiles" / "web"
    profile.mkdir(parents=True)
    manifest = {
        "dependencies": {
            "dsh-houdini": f"link:{ROOT.as_posix()}",
            "@anionex/dsh-vision-toolkit": "0.1.40",
        },
        "dsh": {"profile": {"bundles": ["dsh-houdini", "@anionex/dsh-vision-toolkit"]}},
    }
    (profile / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    for name, version in (("dsh-houdini", "0.1.0"), ("@anionex/dsh-vision-toolkit", "0.1.40")):
        package_dir = profile / "node_modules" / name
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text(
            json.dumps({"name": name, "version": version}), encoding="utf-8",
        )

    status = sync.inspect_profile(requirements, project_root=ROOT, home=home)
    assert status["ok"], status
    assert sync.required_install_specs(requirements, status, project_root=ROOT) == []

    exposure = (
        profile / "node_modules" / "@anionex" / "dsh-vision-toolkit" / "lib" / "exposure.js"
    )
    exposure.parent.mkdir(parents=True)
    exposure.write_bytes(b"before\n" + sync._VISION_TOOLKIT_OLD_EVENTS_API + b"\nafter\n")
    repaired = sync.apply_profile_compatibility_repairs(requirements, home=home)
    assert repaired == ["vision-toolkit 0.1.40 session.snapshotEvents compatibility"]
    assert sync._VISION_TOOLKIT_OLD_EVENTS_API not in exposure.read_bytes()
    assert exposure.read_bytes().count(sync._VISION_TOOLKIT_NEW_EVENTS_API) == 1
    assert sync.apply_profile_compatibility_repairs(requirements, home=home) == []

    manifest["dsh"]["profile"]["bundles"].remove("@anionex/dsh-vision-toolkit")
    (profile / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    missing = sync.inspect_profile(requirements, project_root=ROOT, home=home)
    assert not missing["ok"]
    assert sync.required_install_specs(requirements, missing, project_root=ROOT) == [
        "@anionex/dsh-vision-toolkit@0.1.40",
    ]

    manifest["dsh"]["profile"]["bundles"].extend([
        "@anionex/dsh-vision-toolkit", "@anionex/dsh-vision-toolkit",
    ])
    (profile / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    duplicate = sync.inspect_profile(requirements, project_root=ROOT, home=home)
    assert not duplicate["ok"]
    assert duplicate["plugins"][1]["bundleCount"] == 2

    manifest["dependencies"]["dsh-vision-router"] = "1.6.0"
    manifest["dsh"]["profile"]["bundles"].append("dsh-vision-router")
    (profile / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    old_package = profile / "node_modules" / "dsh-vision-router"
    old_package.mkdir(parents=True)
    (old_package / "package.json").write_text(
        json.dumps({"name": "dsh-vision-router", "version": "1.6.0"}),
        encoding="utf-8",
    )
    manifest["dependencies"]["dsh-vision-fallback"] = "link:E:/retired/fallback"
    manifest["dsh"]["profile"]["bundles"].append("dsh-vision-fallback")
    (profile / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    fallback_package = profile / "node_modules" / "dsh-vision-fallback"
    fallback_package.mkdir(parents=True)
    (fallback_package / "package.json").write_text(
        json.dumps({"name": "dsh-vision-fallback", "version": "0.1.0"}),
        encoding="utf-8",
    )
    obsolete = sync.inspect_profile(requirements, project_root=ROOT, home=home)
    assert not obsolete["ok"]
    assert sync.required_remove_names(requirements, obsolete) == [
        "dsh-vision-router", "dsh-vision-fallback",
    ]

print("dsh profile sync tests passed")
