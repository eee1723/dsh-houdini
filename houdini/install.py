"""为 Houdini 开发环境登记当前源码。用 --print 预览，或用 --packages-dir 指定隔离目录。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent  # houdini/
SUPPORTED_SERIES = ('21.0', '22.0')


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

    HOUDINI_USER_PREF_DIR 优先，其次查找 Documents 下已有的 H21/H22 偏好目录。
    """
    pref = os.environ.get("HOUDINI_USER_PREF_DIR", "").strip()
    if pref:
        if "__HVER__" in pref:
            return [Path(pref.replace("__HVER__", version)) / "packages"
                    for version in SUPPORTED_SERIES]
        return [Path(pref) / "packages"]
    documents = Path.home() / "Documents"
    dirs = [documents / f"houdini{version}" for version in SUPPORTED_SERIES]
    dirs = [directory for directory in dirs if directory.is_dir()]
    if dirs:
        return [directory / "packages" for directory in dirs]
    return [documents / "houdini21.0" / "packages"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages-dir", type=Path, default=None, help="覆盖安装目标目录")
    parser.add_argument("--print", action="store_true", help="只打印生成内容，不写文件")
    args = parser.parse_args()

    package = build_package()
    if args.print:
        print(json.dumps(package, indent=2))
        return 0

    packages_dirs = [args.packages_dir] if args.packages_dir else default_packages_dirs()
    targets = []
    for directory in packages_dirs:
        out = directory / "dsh-houdini.json"
        if out.is_symlink() or out.exists():
            try:
                if not out.is_symlink() and out.is_file() and json.loads(out.read_text(encoding="utf-8-sig")) == package:
                    continue
            except (OSError, ValueError):
                pass
            parser.error(f"已有其他注册，已保留 {out}。请用 --packages-dir 选择隔离目录。")
        targets.append(out)

    for out in targets:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x", encoding="utf-8") as stream:
            json.dump(package, stream, indent=2)
        print(f"已写入 {out}")

    print("仅登记 Houdini 连接插件；请在官方 DSH Desktop 安装并启用 dsh-houdini。")
    print(f"houdini 目录已烘焙：{PACKAGE_ROOT.as_posix()}")
    print("重开 Houdini 后，菜单栏应出现 DSH-Houdini 菜单。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
