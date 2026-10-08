"""Source profile identity follows the installed directory, not only its manifest."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_profile_sync as sync


def link_directory(target, link):
    if os.name == 'nt':
        subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(target)],
                       check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        link.symlink_to(target, target_is_directory=True)


def unlink_directory(link):
    link.rmdir() if os.name == 'nt' else link.unlink()


requirements = sync.load_requirements()
assert [p['name'] for p in requirements['plugins']] == ['dsh-houdini']
with tempfile.TemporaryDirectory(prefix='dsh-profile-中文 空格-') as raw:
    base = Path(raw)
    project, stale = base / 'project', base / 'stale'
    for directory in (project, stale):
        directory.mkdir()
        (directory / 'package.json').write_text(json.dumps({'name': 'dsh-houdini', 'version': '0.0.2'}))
    (project / 'dsh-profile.requirements.json').write_text(json.dumps(requirements))
    home = base / 'home'
    profile = home / 'profiles/web'
    package = profile / 'node_modules/dsh-houdini'
    package.parent.mkdir(parents=True)
    alias = base / 'source-alias'
    link_directory(project, alias)
    link_directory(project, package)
    manifest = {'dependencies': {'dsh-houdini': f'link:{alias.as_posix()}'},
                'dsh': {'profile': {'bundles': ['dsh-houdini']}}}

    def save():
        (profile / 'package.json').write_text(json.dumps(manifest))

    def inspect():
        return sync.inspect_profile(requirements, project_root=project, home=home)

    def reconcile():
        return sync.sync_profile_plugins(['dsh'], project_root=project, home=home)

    try:
        save()
        # A declared alias and installed junction may both name the correct source.
        assert inspect()['ok'], inspect()
        with patch.object(sync, '_run_plugin_command') as command:
            assert reconcile().startswith('profile plugins ok:')
            command.assert_not_called()

        # Same package name/version cannot conceal a stale installed checkout.
        unlink_directory(package)
        link_directory(stale, package)
        status = inspect()
        assert not status['ok'] and 'installed project resolves to' in str(status['problems']), status
        assert sync.required_install_specs(requirements, status, project_root=project) == [str(project.resolve())]

        def repair(prefix, args, **kwargs):
            assert args == ['plugin', '--profile', 'web', 'add', str(project.resolve())]
            unlink_directory(package)
            link_directory(project, package)
            manifest['dependencies']['dsh-houdini'] = f'link:{project.as_posix()}'
            manifest['dsh']['profile']['bundles'] = ['dsh-houdini']
            save()
            return 'relinked through DSH'

        with patch.object(sync, '_run_plugin_command', side_effect=repair) as command:
            assert reconcile().startswith('profile plugins synced:')
            assert command.call_count == 1 and inspect()['ok']
            # Existing missing-dependency/bundle repair still uses the same path.
            manifest['dependencies'].clear()
            manifest['dsh']['profile']['bundles'].clear()
            save()
            assert not inspect()['ok']
            reconcile()
            assert command.call_count == 2 and inspect()['ok']
    finally:
        unlink_directory(package)
        unlink_directory(alias)
print('profile source identity, aliases, stale-link repair and idempotence passed')
