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
        if item.get("source") == "project":
            project_path = item.get("path")
            if project_path is not None and (
                not isinstance(project_path, str) or not project_path.strip()
            ):
                raise RuntimeError(f"plugin {name!r} has an invalid project path: {path}")
        elif not isinstance(item.get("spec"), str):
            raise RuntimeError(f"plugin {name!r} needs a spec: {path}")
    remove_plugins = data.get("removePlugins", [])
    if not isinstance(remove_plugins, list) or not all(
        isinstance(name, str) and name.strip() for name in remove_plugins
    ):
        raise RuntimeError(f"requirements removePlugins must be a string list: {path}")
    if len(remove_plugins) != len(set(remove_plugins)):
        raise RuntimeError(f"duplicate removePlugins entry: {path}")
    overlap = names.intersection(remove_plugins)
    if overlap:
        raise RuntimeError(f"plugins cannot be both required and removed: {sorted(overlap)}")
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


def _project_source(requirement: dict, project_root: Path) -> Path:
    relative = requirement.get("path", ".")
    source = (project_root / relative).resolve()
    try:
        source.relative_to(project_root.resolve())
    except ValueError as exc:
        raise RuntimeError(
            f"project plugin {requirement['name']!r} escapes project root: {relative!r}"
        ) from exc
    return source


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
                expected = _normalized_path(
                    str(_project_source(requirement, project_root)), root
                )
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

    obsolete = []
    for name in requirements.get("removePlugins", []):
        dependency = dependencies.get(name)
        package = _installed_manifest(root, name)
        bundle_count = bundles.count(name)
        if dependency is not None or package is not None or bundle_count:
            obsolete.append({
                "name": name,
                "dependency": dependency,
                "version": package.get("version") if package else None,
                "bundleCount": bundle_count,
            })

    return {
        "ok": not problems and not obsolete,
        "profile": profile,
        "profileDir": str(root),
        "plugins": installed,
        "problems": problems,
        "obsolete": obsolete,
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
            specs.append(str(_project_source(requirement, project_root)))
        else:
            specs.append(requirement["spec"])
    return specs


def required_remove_names(requirements: dict, status: dict) -> list[str]:
    """Return obsolete managed plugins that are still present in the profile."""
    present = {item["name"] for item in status.get("obsolete", [])}
    return [name for name in requirements.get("removePlugins", []) if name in present]


def _run_plugin_command(
    command_prefix: list[str] | str,
    args: list[str],
    *,
    use_shell: bool,
    project_root: Path,
    env: dict | None,
    timeout: int,
) -> str:
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
    return output


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
    removals = required_remove_names(requirements, before)
    outputs: list[str] = []
    if removals:
        outputs.append(_run_plugin_command(
            command_prefix,
            ["plugin", "--profile", requirements["profile"], "remove", *removals],
            use_shell=use_shell,
            project_root=project_root,
            env=env,
            timeout=timeout,
        ))

    current = inspect_profile(requirements, project_root=project_root, home=home)
    specs = required_install_specs(requirements, current, project_root=project_root)
    if not specs and not removals:
        versions = ", ".join(
            f"{item['name']}@{item['version'] or 'local'}" for item in before["plugins"]
        )
        return "profile plugins ok: " + versions

    if on_install is not None:
        on_install(specs)
    if specs:
        outputs.append(_run_plugin_command(
            command_prefix,
            ["plugin", "--profile", requirements["profile"], "add", *specs],
            use_shell=use_shell,
            project_root=project_root,
            env=env,
            timeout=timeout,
        ))

    after = inspect_profile(requirements, project_root=project_root, home=home)
    if not after["ok"]:
        raise RuntimeError(
            "DSH profile plugin synchronization did not satisfy the manifest:\n"
            + json.dumps({
                "problems": after["problems"],
                "obsolete": after.get("obsolete", []),
            }, ensure_ascii=False, indent=2)
            + (f"\ncommand output:\n{chr(10).join(outputs)[-8000:]}" if outputs else "")
        )
    actions = []
    if removals:
        actions.append("removed " + ", ".join(removals))
    if specs:
        actions.append("added " + ", ".join(specs))
    return "profile plugins synced: " + "; ".join(actions)
