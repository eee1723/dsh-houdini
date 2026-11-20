"""预览当前源码的 Houdini Package，或用 --packages-dir 登记到指定的隔离开发目录。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

PACKAGE_ROOT = Path(__file__).resolve().parent  # houdini/


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages-dir", type=Path, help="当前隔离 Houdini profile 的 packages 目录")
    parser.add_argument("--print", action="store_true", help="只打印生成内容，不写文件")
    args = parser.parse_args()

    package = build_package()
    content = json.dumps(package, indent=2) + "\n"
    if args.print or args.packages_dir is None:
        print(content, end="")
        return 0

    directory = args.packages_dir
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "dsh-houdini.json"
    with tempfile.TemporaryDirectory(dir=directory) as staging:
        staged = Path(staging) / target.name
        staged.write_text(content, encoding="utf-8")
        try:
            if os.name == "nt":
                staged.rename(target)  # Windows rename never replaces an existing entry.
            else:
                os.link(staged, target)
        except FileExistsError:
            try:
                same = (not target.is_symlink() and target.is_file()
                        and json.loads(target.read_text(encoding="utf-8-sig")) == package)
            except (OSError, ValueError):
                same = False
            if not same:
                parser.error(f"已有其他登记，已保留 {target}。请选择隔离开发目录。")
    print(f"源码 Package 已登记至 {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
