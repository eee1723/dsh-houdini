"""Exact DSH runtime selection shared by installation, startup and repair.

``dsh-runtime-compatibility.json`` names the supported runtime and records
remaining live checks. Manifest admission describes the source combination;
it does not claim a running Houdini has loaded it.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import hashlib


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
            try:
                runtime_fix_identity(binary, path)
            except (OSError, ValueError, RuntimeError):
                continue
            return binary
    return None


def runtime_fix_identity(binary: Path | str, path: Path = MANIFEST_PATH, *, verify_files=False) -> dict | None:
    """Read revision metadata; only the startup worker requests full file verification."""
    location = load_manifest(path).get('runtimeFixes')
    if location is None:
        return None
    definition_path = path.parent / location
    definition = json.loads(definition_path.read_text(encoding='utf8'))
    expected_patch = definition['patchSha256']
    runtime_root = Path(binary).resolve().parents[4]
    applied = json.loads((runtime_root / '.dsh-runtime-fixes.json').read_text(encoding='utf8'))
    if (not isinstance(applied, dict) or applied.get('schemaVersion') != 1 or applied.get('revision') != definition['revision']
            or applied.get('dshVersion') != preferred_version(path) or applied.get('patchSha256') != expected_patch):
        raise RuntimeError('DSH runtime fixes do not match this plugin source; run npm run runtime:prepare')
    files = applied.get('files')
    if not isinstance(files, dict) or not files:
        raise RuntimeError('DSH runtime fix file inventory is missing')
    required = {f"node_modules/@deepseek-ai/dsh-{package['name']}/lib/{entry}.js"
                for package in definition['hostPackages'] for entry in package['entries']}
    required.update(f"node_modules/@deepseek-ai/dsh-{package['name']}/{asset}"
                    for package in definition['hostPackages'] for asset in package.get('assets', []))
    required.update(f"node_modules/@deepseek-ai/dsh-client-{name}/lib/client.js" for name in definition['clientPackages'])
    if not required.issubset(files):
        raise RuntimeError('DSH runtime fix inventory omits a required implementation or asset')
    if verify_files:
        for relative, expected in files.items():
            target = (runtime_root / relative).resolve()
            if not target.is_relative_to(runtime_root) or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise RuntimeError('DSH runtime fix file differs from its prepared inventory: ' + str(relative))
    return {'revision': applied['revision'], 'patchSha256': applied['patchSha256'], 'filesVerified': verify_files}


def require_verified(version: str, path: Path = MANIFEST_PATH) -> None:
    if version not in verified_versions(path):
        raise RuntimeError(
            f"DSH {version} is downloaded but not compatibility-verified; "
            f"the serving runtime was not changed. Qualify it across Host RPC, "
            "QtWebEngine, Houdini Trace, profile bundles, and workspace/session "
            f"lifecycle, then add the exact release to {path}."
        )
