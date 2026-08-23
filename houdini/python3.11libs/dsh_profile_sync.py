"""Declarative DSH profile dependency inspection and synchronization.

This module deliberately has no ``hou`` dependency so both ``houdini/install.py``
and the in-Houdini launcher can use the same profile contract.  DSH remains the
only writer of profile manifests; this module only inspects them and invokes the
official ``dsh plugin`` command when reconciliation is required.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_FILE = PROJECT_ROOT / "dsh-profile.requirements.json"
SYNC_TIMEOUT_SECONDS = 600


def load_requirements(path: Path = REQUIREMENTS_FILE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1:
        raise RuntimeError(f"unsupported DSH profile requirements schema: {path}")
    profile = data.get("profile")
    plugins = data.get("plugins")
    if not isinstance(profile, str) or not profile.strip():
        raise RuntimeError(f"requirements profile must be a non-empty string: {path}")
    if not isinstance(plugins, list) or not plugins:
        raise RuntimeError(f"requirements plugins must be a non-empty list: {path}")
    names: set[str] = set()
    for item in plugins:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise RuntimeError(f"invalid plugin requirement in {path}: {item!r}")
        name = item["name"]
        if name in names:
            raise RuntimeError(f"duplicate plugin requirement {name!r}: {path}")
        names.add(name)
        if item.get("source") != "project" and not isinstance(item.get("spec"), str):
            raise RuntimeError(f"plugin {name!r} needs a spec: {path}")
    return data


def dsh_home() -> Path:
    configured = os.environ.get("DSH_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".dsh"


def profile_dir(profile: str, home: Path | None = None) -> Path:
    return (home or dsh_home()) / "profiles" / profile


def _normalized_path(value: str, anchor: Path) -> str:
    raw = value.replace("\\", "/")
    for prefix in ("link:", "file:"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = anchor / candidate
    return os.path.normcase(os.path.abspath(candidate)).replace("\\", "/").rstrip("/")


def _installed_manifest(root: Path, package_name: str) -> dict | None:
    manifest = root / "node_modules"
    for part in package_name.split("/"):
        manifest /= part
    manifest /= "package.json"
    try:
        return json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def inspect_profile(
    requirements: dict,
    *,
    project_root: Path = PROJECT_ROOT,
    home: Path | None = None,
) -> dict:
    """Return deterministic profile status without changing user state."""
    profile = requirements["profile"]
    root = profile_dir(profile, home)
    manifest_path = root / "package.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        manifest = {}
    except ValueError as exc:
        raise RuntimeError(f"invalid DSH profile manifest {manifest_path}: {exc}") from exc

    dependencies = manifest.get("dependencies") or {}
    bundles = ((manifest.get("dsh") or {}).get("profile") or {}).get("bundles") or []
    problems: list[dict] = []
    installed: list[dict] = []

    for requirement in requirements["plugins"]:
        name = requirement["name"]
        dependency = dependencies.get(name)
        package = _installed_manifest(root, name)
        package_version = package.get("version") if package else None
        bundle_count = bundles.count(name)
        reasons: list[str] = []
        if dependency is None:
            reasons.append("dependency missing")
        if bundle_count == 0:
            reasons.append("bundle not active")
        elif bundle_count > 1:
            reasons.append(f"bundle active {bundle_count} times")
        if package is None:
            reasons.append("package not installed")

        if requirement.get("source") == "project":
            if dependency is not None:
                actual = _normalized_path(str(dependency), root)
                expected = _normalized_path(str(project_root), root)
                if actual != expected:
                    reasons.append(f"project link points to {actual}")
        else:
            expected_version = requirement.get("version")
            if expected_version and package_version != expected_version:
                reasons.append(
                    f"installed version {package_version or '(unknown)'} != {expected_version}"
                )

        item = {
            "name": name,
            "dependency": dependency,
            "version": package_version,
            "active": bundle_count == 1,
            "bundleCount": bundle_count,
        }
        installed.append(item)
        if reasons:
            problems.append({"name": name, "reasons": reasons})

    return {
        "ok": not problems,
        "profile": profile,
        "profileDir": str(root),
        "plugins": installed,
        "problems": problems,
    }


def required_install_specs(
    requirements: dict,
    status: dict,
    *,
    project_root: Path = PROJECT_ROOT,
) -> list[str]:
    problem_names = {item["name"] for item in status["problems"]}
    specs = []
    for requirement in requirements["plugins"]:
        if requirement["name"] not in problem_names:
            continue
        if requirement.get("source") == "project":
            specs.append(str(project_root.resolve()))
        else:
            specs.append(requirement["spec"])
    return specs


def sync_profile_plugins(
    command_prefix: list[str] | str,
    *,
    use_shell: bool = False,
    project_root: Path = PROJECT_ROOT,
    home: Path | None = None,
    env: dict | None = None,
    timeout: int = SYNC_TIMEOUT_SECONDS,
    on_install: Callable[[list[str]], None] | None = None,
) -> str:
    """Reconcile required bundles through ``dsh plugin``, then verify them."""
    requirements = load_requirements(project_root / REQUIREMENTS_FILE.name)
    before = inspect_profile(requirements, project_root=project_root, home=home)
    specs = required_install_specs(requirements, before, project_root=project_root)
    if not specs:
        versions = ", ".join(
            f"{item['name']}@{item['version'] or 'local'}" for item in before["plugins"]
        )
        return "profile plugins ok: " + versions

    if on_install is not None:
        on_install(specs)
    args = ["plugin", "--profile", requirements["profile"], "add", *specs]
    if isinstance(command_prefix, str):
        command: list[str] | str = command_prefix + " " + subprocess.list2cmdline(args)
    else:
        command = [*command_prefix, *args]
    proc = subprocess.run(
        command,
        cwd=project_root,
        capture_output=True,
        timeout=timeout,
        shell=use_shell,
        env=env,
    )
    raw = (proc.stdout or b"") + b"\n" + (proc.stderr or b"")
    output = raw.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        raise RuntimeError(
            "DSH profile plugin synchronization failed"
            f" (exit {proc.returncode}):\n{output[-12000:]}"
        )

    after = inspect_profile(requirements, project_root=project_root, home=home)
    if not after["ok"]:
        raise RuntimeError(
            "DSH profile plugin synchronization did not satisfy the manifest:\n"
            + json.dumps(after["problems"], ensure_ascii=False, indent=2)
            + (f"\ncommand output:\n{output[-8000:]}" if output else "")
        )
    return "profile plugins synced: " + ", ".join(specs)
