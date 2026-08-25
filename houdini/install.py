"""dsh-houdini 安装脚本：生成本机 Houdini package 文件（每台机器跑一次）。

参照 EEEAgent / Edini 项目的验证做法：把仓库绝对路径直接写进生成的 package json，
不依赖提前 setx 环境变量（setx 需要新开进程才生效，容易踩空）。Houdini package
文件里的相对路径不是相对 package 文件位置解析，所以必须用绝对路径——这里经
`$DSH_HOUDINI_PATH` 展开。生成的 `dsh-houdini.json` 会被写进本机 Houdini packages
目录，供 Houdini 启动时加载（追加顶级 `dsh` 菜单、把 python3.11libs 加进 sys.path）。

用法（仅需标准库）：
    python houdini/install.py                # 装到本机所有已检测到的 Houdini 版本的 packages 目录
    python houdini/install.py --print        # 只打印生成内容，不写文件
    python houdini/install.py --packages-dir <dir>   # 覆盖安装目标目录

package 按用户 pref 目录隔离（H21 读 houdini21.0/packages、H22 读
houdini22.0/packages，互不可见），所以默认给每个检测到的版本各装一份；
新装了一个大版本的 Houdini 后重跑本脚本即可。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

PACKAGE_ROOT = Path(__file__).resolve().parent  # houdini/
PROJECT_ROOT = PACKAGE_ROOT.parent
PYTHON_LIB = PACKAGE_ROOT / "python3.11libs"
NPM_CACHE = PROJECT_ROOT / ".npm-cache"
DEFAULT_DSH_SPEC = "@deepseek-ai/dsh"


def dsh_command_prefix() -> tuple[list[str] | str, bool]:
    """Prefer an already cached/explicit CLI; use npx only for a cold install."""
    node = shutil.which("node")
    explicit = os.environ.get("DSH_HOUDINI_DSH_BIN", "").strip()
    if explicit:
        target = Path(explicit).expanduser().resolve()
        if not target.is_file():
            raise RuntimeError(f"DSH_HOUDINI_DSH_BIN does not point to a file: {target}")
        if not node:
            raise RuntimeError("Node.js is required to run DSH_HOUDINI_DSH_BIN")
        return [node, str(target)], False

    dsh_spec = os.environ.get("DSH_HOUDINI_DSH_SPEC", DEFAULT_DSH_SPEC)
    if dsh_spec == DEFAULT_DSH_SPEC and node:
        candidates = list(NPM_CACHE.glob(
            "_npx/*/node_modules/@deepseek-ai/dsh/lib/bin.js"
        ))
        if candidates:
            latest = max(candidates, key=lambda item: item.stat().st_mtime)
            return [node, str(latest)], False

    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError(
            "Node.js/npx 未安装；无法同步完整 DSH profile。"
            "安装 Node.js 后重跑，或显式使用 --skip-dsh-profile。"
        )
    if os.name == "nt":
        return subprocess.list2cmdline([npx, "--yes", dsh_spec]), True
    return [npx, "--yes", dsh_spec], False


def build_package() -> dict:
    """生成 package 定义（本机绝对路径已烘焙进去，各机器各自生成各自的）。

    sys.path 注入走 PYTHONPATH 而不是 pythonX.Ylibs 目录约定：Houdini 只会
    自动加载匹配自身 Python 版本的 pythonX.Ylibs（H21=3.11、H22=3.13），而
    本插件是纯 Python、与版本无关，PYTHONPATH 一条对两边都生效。
    """
    houdini_dir = PACKAGE_ROOT.as_posix()
    return {
        "env": [
            {"DSH_HOUDINI_PATH": houdini_dir},
            {"PYTHONPATH": "$DSH_HOUDINI_PATH/python3.11libs;$PYTHONPATH"},
        ],
        "path": "$DSH_HOUDINI_PATH",
    }


def default_packages_dirs() -> list[Path]:
    """本机所有 Houdini 版本的用户 package 目录（每个大版本各装一份）。

    HOUDINI_USER_PREF_DIR 优先（只装它一个）；否则扫描 Documents/houdini*
    全部命中——package 按 pref 目录隔离，H21 不读 houdini22.0 的、反之亦然。
    """
    pref = os.environ.get("HOUDINI_USER_PREF_DIR", "").strip()
    if pref:
        return [Path(pref) / "packages"]
    dirs = [d for d in Path.home().glob("Documents/houdini*") if d.is_dir()]
    if dirs:
        return [d / "packages" for d in sorted(dirs)]
    return [Path.home() / "Documents" / "houdini21.0" / "packages"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages-dir", type=Path, default=None, help="覆盖安装目标目录")
    parser.add_argument("--print", action="store_true", help="只打印生成内容，不写文件")
    parser.add_argument(
        "--skip-dsh-profile", action="store_true",
        help="只安装 Houdini package，不同步 DSH web profile 依赖",
    )
    args = parser.parse_args()

    package = build_package()
    if args.print:
        print(json.dumps(package, indent=2))
        return 0

    packages_dirs = [args.packages_dir] if args.packages_dir else default_packages_dirs()
    for packages_dir in packages_dirs:
        packages_dir.mkdir(parents=True, exist_ok=True)
        out = packages_dir / "dsh-houdini.json"
        out.write_text(json.dumps(package, indent=2), encoding="utf-8")
        print(f"已写入 {out}")

    if not args.skip_dsh_profile:
        sys.path.insert(0, str(PYTHON_LIB))
        import dsh_profile_sync

        prefix, use_shell = dsh_command_prefix()
        status = dsh_profile_sync.sync_profile_plugins(
            prefix,
            use_shell=use_shell,
            project_root=PROJECT_ROOT,
            env=dict(
                os.environ,
                NPM_CONFIG_CACHE=str(NPM_CACHE),
            ),
        )
        print(status)
    print(f"houdini 目录已烘焙：{PACKAGE_ROOT.as_posix()}")
    print("重开 Houdini 后，菜单栏应出现顶级菜单 dsh。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
