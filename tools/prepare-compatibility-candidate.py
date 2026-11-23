"""Prepare release notes from the frozen candidate and real Desktop qualification reports."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def read_report(path, digest):
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("artifactSha256") != digest or report.get("ok") is not True:
        raise ValueError(f"{path}: need a passing report for candidate SHA256 {digest}")
    return report


def prepare(args):
    artifact = args.artifact.resolve(strict=True)
    with artifact.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = json.loads((artifact.parent / "release-manifest.json").read_text(encoding="utf-8"))
    if manifest["sha256"] != digest or manifest["file"] != artifact.name:
        raise ValueError("Frozen tarball and release-manifest.json differ")
    with tarfile.open(artifact, "r:gz") as archive:
        package = json.load(archive.extractfile("package/package.json"))
        policy = json.load(archive.extractfile("package/dsh-runtime-compatibility.json"))
    version = package["version"]
    hosts = [row["dshVersion"] for row in policy["releases"]]
    if (package["name"] != "dsh-houdini" or manifest["version"] != version
            or manifest["requiresDsh"] != package["engines"]["dsh"]
            or package["engines"]["dsh"] != " || ".join(hosts)):
        raise ValueError("Packaged version or compatibility declaration differs from the release manifest")
    targets = set(args.target)
    if targets.difference(hosts):
        raise ValueError(f"Requested targets outside the candidate declaration: {sorted(targets.difference(hosts))}")

    builds = {}
    for path in args.install_report:
        report = read_report(path, digest)
        host = (report.get("runtimeRelease") or {}).get("version")
        gui = report.get("houdiniGui") or {}
        if (host not in hosts or report.get("version") != version or not gui.get("mainThread")
                or not gui.get("editorSmoke") or not gui.get("registeredInspect")):
            raise ValueError(f"{path}: need installed Host identity, main-thread editor and registered-tool evidence")
        series = ".".join(gui["version"].split(".")[:2])
        builds[(host, series)] = gui["version"]
    missing = [f"DSH {host} / Houdini {hfs}" for host in hosts for hfs in ("21.0", "22.0") if (host, hfs) not in builds]
    if missing:
        raise ValueError("Missing same-tarball Desktop checks: " + ", ".join(missing))

    upgrades = {}
    for path in args.update_report:
        report = read_report(path, digest)
        host = report.get("candidateCompatibility", {}).get("runtime")
        update = report.get("ui", {}).get("update", {})
        button = update.get("nativeRegistryUpdate", {}).get("update", {})
        if (host not in hosts or not report.get("updatedByNativeUi") or not update.get("updateStatePreserved")
                or button.get("to") != version or not button.get("from")):
            raise ValueError(f"{path}: need a successful native version update with preserved session")
        upgrades[host] = button["from"]
    if not targets.issubset(upgrades):
        raise ValueError(f"Missing native update for DSH {sorted(targets.difference(upgrades))}")

    lines = [f"# dsh-houdini {version}", "", "## 适用版本", "",
             "Windows x64。下面各组合使用同一份安装包。", "",
             "| DSH Desktop | 已验证的 Houdini 构建 |", "|---|---|"]
    lines += [f"| {host} | {builds[host, '21.0']} / {builds[host, '22.0']} |" for host in hosts]
    lines += ["", "## 本次变化", ""]
    lines += [f"- 已适配 DSH {host}，已验证从插件 {upgrades[host]} 经详情页更新并保留会话。" for host in sorted(targets)]
    lines += ["- " + note for note in args.note]
    lines += ["", "## 安装与更新", "", "启用「自定义插件索引」，在「发现 → 添加索引源」粘贴以下地址，安装推荐版本并启用。", "",
              "```text", "https://raw.githubusercontent.com/eee1723/dsh-houdini/main/market/index.json", "```",
              "", "已通过包名安装的用户可在详情页检查更新。直接安装时，待所选渠道上架后使用对应入口。", "",
              "```text", f"dsh-houdini@{version}", "```", "", "```text", manifest["installUrl"], "```",
              "", "保存工程后重开需要加载新版组件的 Houdini 窗口。", "", f"安装包 SHA-256 为 `{digest}`。", ""]
    notes = args.notes or artifact.parent / "release-notes.md"
    content = "\n".join(lines)
    # Rerunning a check may reuse an identical draft. Preserve subsequent editorial changes.
    if notes.exists():
        if notes.read_text(encoding="utf-8") != content:
            raise ValueError(f"Draft already exists with different text: {notes}. Select a new --notes path.")
    else:
        with notes.open("x", encoding="utf-8", newline="\n") as output:
            output.write(content)
    print(json.dumps({"artifact": str(artifact), "sha256": digest, "hosts": hosts, "notes": str(notes.resolve())}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--target", required=True, action="append", help="New DSH version, repeat for multiple targets")
    parser.add_argument("--install-report", required=True, type=Path, action="append")
    parser.add_argument("--update-report", required=True, type=Path, action="append")
    parser.add_argument("--note", action="append", default=[], help="Additional verified user-visible change")
    parser.add_argument("--notes", type=Path, help="Default: release-notes.md next to the frozen tgz")
    try:
        prepare(parser.parse_args())
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        parser.exit(1, f"Candidate qualification: {error}\n")
