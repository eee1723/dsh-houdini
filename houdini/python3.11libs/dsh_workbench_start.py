"""Standalone workspace entry; never needs a running Houdini process."""
import argparse
import os
from pathlib import Path
import shutil

from dsh_houdini_installations import installation
from dsh_workbench import ensure, control, reject_legacy_frontend


def launch(hfs, source=None, root=None):
    selected = installation(hfs)
    if source:
        from dsh_profile_sync import dsh_home
        from dsh_runtime_compat import preferred_cached_bin
        source = Path(source).resolve()
        reject_legacy_frontend(source / '.dsh-runtime.json')
        binary = os.environ.get('DSH_HOUDINI_DSH_BIN') or preferred_cached_bin(source / '.npm-cache')
        node = shutil.which('node')
        if not binary or not node:
            raise RuntimeError('源码运行环境尚未准备，请先运行 npm run runtime:prepare。')
        config = {'root': str(dsh_home() / 'houdini-workbench'), 'installation': str(source), 'plugin': str(source),
                  'node': node, 'binary': str(binary), 'home': str(dsh_home())}
    else:
        from dsh_deployment import Store, read_json
        root = Path(root or Path(os.environ['LOCALAPPDATA']) / 'DSH-Houdini').resolve()
        trust = read_json(Path(__file__).resolve().parents[1] / 'release-trust.json')
        store = Store(root, trust)
        state = store.state()
        pinned = state['pending'] or state['current']
        if not pinned:
            raise RuntimeError('还没有准备好运行包，请先运行配套安装器 Install.cmd。')
        config = {'root': str(root), 'managed': True, 'installation': pinned, 'trustData': trust,
                  'houdiniVersion': selected['series']}
    config.update(hfs=selected['hfs'], python=selected['python'])
    desktop = ensure(config)
    control(desktop['record'], 'show')
    return desktop


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--hfs', required=True)
    parser.add_argument('--source-root')
    parser.add_argument('--root')
    args = parser.parse_args()
    try:
        launch(args.hfs, args.source_root, args.root)
    except Exception as error:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(error), 'DSH-Houdini · 无法打开工作台', 0x10)
        raise


if __name__ == '__main__':
    main()
