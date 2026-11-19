"""One-shot, read-only UE asset registry export; never imports or edits UE assets."""
import json
import shutil
from pathlib import Path

import unreal as ue


def export_dependencies(seeds, destination):
    project = Path(ue.Paths.convert_relative_path_to_full(ue.Paths.project_dir())).resolve()
    library = ue.EditorAssetLibrary
    registry = ue.AssetRegistryHelpers.get_asset_registry()
    registry.search_all_assets(True)
    options = ue.AssetRegistryDependencyOptions()
    options.include_hard_package_references = options.include_soft_package_references = True
    pending = list(seeds)
    visited = set()
    files = []
    mounts = set()
    if destination.resolve().is_relative_to(project):
        raise ValueError("export outside the source project")
    destination.mkdir(exist_ok=False)
    while pending:
        package = pending.pop()
        if package in visited:
            continue
        visited.add(package)
        if not package.startswith("/Game/"):
            mounts.add(package)
            continue
        if not library.does_asset_exist(package):
            raise ValueError("missing UE package " + package)
        stem = project / "Content" / package.removeprefix("/Game/")
        found = False
        for extension in (".uasset", ".umap", ".ubulk", ".uptnl", ".uexp"):
            source = stem.with_suffix(extension)
            if source.is_file():
                found |= extension in (".uasset", ".umap")
                relative = source.relative_to(project)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                files.append(relative.as_posix())
        if not found:
            raise ValueError("missing package on disk: " + package)
        pending.extend(str(item) for item in registry.get_dependencies(package, options) or [])
    return {"files": sorted(files), "external": sorted(mounts)}


def export_for_delivery(manifest, destination):
    data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    seeds = {ref.split(".")[0] for output in data["outputs"] for values in output["ue"].values()
             for ref in values if ref.startswith("/")}
    receipt = export_dependencies(seeds, Path(destination))
    (Path(destination) / "content-files.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt
