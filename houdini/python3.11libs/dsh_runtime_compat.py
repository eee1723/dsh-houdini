"""Fail-closed DSH host compatibility release policy.

Downloading a DSH package does not authorize activating it.  The default
launcher selects only an exact release recorded in
``dsh-runtime-compatibility.json`` after Host RPC, browser, QtWebEngine,
client-view, third-party bundle, and workspace/session checks have passed.
Explicit developer bin/spec overrides remain available for qualifying a new
candidate without changing the normal user's serving runtime.
"""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PROJECT_ROOT / "dsh-runtime-compatibility.json"


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1:
        raise RuntimeError(f"unsupported DSH compatibility schema: {path}")
    preferred = data.get("preferredVersion")
    releases = data.get("releases")
    if not isinstance(preferred, str) or not preferred:
        raise RuntimeError(f"preferredVersion must be a non-empty string: {path}")
    if not isinstance(releases, list) or not releases:
        raise RuntimeError(f"releases must be a non-empty list: {path}")
    versions = []
    for release in releases:
        if not isinstance(release, dict):
            raise RuntimeError(f"invalid DSH compatibility release: {release!r}")
        version = release.get("dshVersion")
        if not isinstance(version, str) or not version:
            raise RuntimeError(f"compatibility release has no dshVersion: {release!r}")
        versions.append(version)
    if len(versions) != len(set(versions)):
        raise RuntimeError(f"duplicate DSH compatibility release: {path}")
    if preferred not in versions:
        raise RuntimeError(f"preferredVersion {preferred!r} is not a verified release: {path}")
    return data


def verified_versions(path: Path = MANIFEST_PATH) -> set[str]:
    return {str(item["dshVersion"]) for item in load_manifest(path)["releases"]}


def preferred_version(path: Path = MANIFEST_PATH) -> str:
    return str(load_manifest(path)["preferredVersion"])


def require_verified(version: str, path: Path = MANIFEST_PATH) -> None:
    if version not in verified_versions(path):
        raise RuntimeError(
            f"DSH {version} is downloaded but not compatibility-verified; "
            f"the serving runtime was not changed. Qualify it across Host RPC, "
            "QtWebEngine, Houdini Trace, profile bundles, and workspace/session "
            f"lifecycle, then add the exact release to {path}."
        )
