"""Official DSH compatibility metadata and isolated development fixture lookup.

Desktop owns its runtime and update lifecycle. These helpers inspect exact
package metadata; they never patch DSH, install it, or activate a user profile.
"""
from __future__ import annotations

import hashlib
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
    if not isinstance(data, dict) or data.get("schemaVersion") != 1:
        raise RuntimeError(f"unsupported DSH compatibility schema: {path}")
    preferred, releases = data.get("preferredVersion"), data.get("releases")
    if not isinstance(preferred, str) or not _EXACT_VERSION.fullmatch(preferred):
        raise RuntimeError(f"preferredVersion must be an exact package version: {path}")
    if not isinstance(releases, list) or not releases:
        raise RuntimeError(f"releases must be a non-empty list: {path}")
    versions = []
    for release in releases:
        version = release.get("dshVersion") if isinstance(release, dict) else None
        if not isinstance(version, str) or not _EXACT_VERSION.fullmatch(version):
            raise RuntimeError(f"compatibility release has no exact dshVersion: {release!r}")
        versions.append(version)
    if len(versions) != len(set(versions)):
        raise RuntimeError(f"duplicate DSH compatibility release: {path}")
    if preferred not in versions:
        raise RuntimeError(f"preferredVersion {preferred!r} is not a verified release: {path}")
    return data


def verified_versions(path: Path = MANIFEST_PATH) -> set[str]:
    return {item["dshVersion"] for item in load_manifest(path)["releases"]}


def preferred_version(path: Path = MANIFEST_PATH) -> str:
    return load_manifest(path)["preferredVersion"]


def preferred_spec(path: Path = MANIFEST_PATH) -> str:
    return f"@deepseek-ai/dsh@{preferred_version(path)}"


def require_verified(version: str, path: Path = MANIFEST_PATH) -> None:
    if not isinstance(version, str) or version not in verified_versions(path):
        raise RuntimeError(f"DSH {version} is not declared compatible with this plugin. "
                           "Use a compatible plugin in Desktop; its serving runtime was not changed. "
                           f"Qualify the exact official package and Desktop integration before updating {path}.")


def _fixture_inputs(directory: Path) -> str:
    digest = hashlib.sha256()
    for name in ("package.json", "package-lock.json"):
        digest.update(name.encode("utf-8"))
        digest.update((directory / name).read_bytes())
    return digest.hexdigest()


def official_runtime_identity(binary: Path | str, path: Path = MANIFEST_PATH) -> dict:
    """Read supported package/fixture metadata, not live state or a file-integrity claim."""
    binary = Path(binary).resolve(strict=True)
    package = json.loads((binary.parent.parent / "package.json").read_text(encoding="utf-8"))
    if (not binary.is_file() or binary.name != "bin.js" or binary.parent.name != "lib"
            or not isinstance(package, dict) or package.get("name") != "@deepseek-ai/dsh"):
        raise RuntimeError("The fixture entry is not the official dsh package bin")
    version = package.get("version")
    require_verified(version, path)
    runtime = binary.parents[4]
    if (runtime / ".dsh-runtime-fixes.json").exists():
        raise RuntimeError("A private patched runtime is not an official Desktop compatibility fixture")
    marker = runtime / ".dsh-official-host.json"
    ownership = "official-package-metadata"
    if marker.is_file():
        record = json.loads(marker.read_text(encoding="utf-8"))
        if (not isinstance(record, dict) or record.get("schemaVersion") != 1 or record.get("runtimeOwnership") != "development-fixture"
                or record.get("dshVersion") != version or record.get("inputsSha256") != _fixture_inputs(runtime)):
            raise RuntimeError("Official Host fixture does not match its npm lock inputs; run npm run runtime:prepare")
        ownership = "development-fixture"
    return {"dshVersion": version, "runtimeOwnership": ownership, "binary": str(binary)}


def preferred_cached_bin(cache_root: Path | str, path: Path = MANIFEST_PATH) -> Path | None:
    """Find the prepared official fixture; do not choose arbitrary npx cache installs."""
    required = preferred_version(path)
    definition = path.parent / "deployment"
    expected = _fixture_inputs(definition) if all((definition / name).is_file()
                   for name in ("package.json", "package-lock.json")) else None
    for marker in sorted(Path(cache_root).glob(f"_npx/dsh-houdini-official-{required}-*/.dsh-official-host.json")):
        try:
            record = json.loads(marker.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                continue
            if expected is not None and record.get("inputsSha256") != expected:
                continue
            binary = marker.parent / "node_modules/@deepseek-ai/dsh/lib/bin.js"
            identity = official_runtime_identity(binary, path)
            if identity["dshVersion"] == required:
                return binary
        except (OSError, ValueError, RuntimeError, KeyError, TypeError):
            continue
    return None
