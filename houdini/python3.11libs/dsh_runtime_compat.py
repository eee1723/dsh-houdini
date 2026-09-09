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
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PROJECT_ROOT / "dsh-runtime-compatibility.json"
_EXACT_VERSION = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


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
    version = str(load_manifest(path)["preferredVersion"])
    if not _EXACT_VERSION.fullmatch(version):
        raise RuntimeError(f"preferredVersion must be an exact package version: {path}")
    return version


def preferred_spec(path: Path = MANIFEST_PATH) -> str:
    return f"@deepseek-ai/dsh@{preferred_version(path)}"


def preferred_cached_bin(cache_root: Path | str, path: Path = MANIFEST_PATH) -> Path | None:
    """Select only this plugin's required DSH, never cache recency or npm latest.

    This is a transitional source-install cache lookup, not a full dependency
    integrity check or the future managed release store.
    """
    required = preferred_version(path)
    for manifest in sorted(Path(cache_root).glob(
        "_npx/*/node_modules/@deepseek-ai/dsh/package.json"
    )):
        try:
            package = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(package, dict) or package.get("name") != "@deepseek-ai/dsh":
            continue
        binary = manifest.parent / "lib" / "bin.js"
        if package.get("version") == required and binary.is_file():
            return binary
    return None


def require_verified(version: str, path: Path = MANIFEST_PATH) -> None:
    if version not in verified_versions(path):
        raise RuntimeError(
            f"DSH {version} is downloaded but not compatibility-verified; "
            f"the serving runtime was not changed. Qualify it across Host RPC, "
            "QtWebEngine, Houdini Trace, profile bundles, and workspace/session "
            f"lifecycle, then add the exact release to {path}."
        )
