"""Native Package disk/load separation, source relations and bounded reads.

Run in isolated hython; every path and registration belongs to this fixture.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import hou
import dsh_package_discovery as discovery


def reject(function, fragment):
    try:
        function()
    except ValueError as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError('accepted invalid Package request')


with tempfile.TemporaryDirectory(prefix='dsh-package-discovery-') as temporary:
    root = Path(temporary)
    pref, site, hfs, external = (root / name for name in ('prefs', 'site', 'installation', 'external'))
    version = '%d.%d' % hou.applicationVersion()[:2]
    package_dirs = [pref / 'packages', site / ('houdini' + version) / 'packages', hfs / 'packages', external]
    for directory in package_dirs:
        directory.mkdir(parents=True)
    assets, python, panels = (root / name for name in ('assets', 'python-source', 'panels'))
    (assets / 'toolbar').mkdir(parents=True)
    (assets / 'toolbar/main.shelf').write_text('<shelfDocument/>', encoding='utf-8')
    (assets / 'scripts/python').mkdir(parents=True)
    (assets / 'scripts/python/helper.py').write_text('raise RuntimeError("must not import")\n', encoding='utf-8')
    (assets / 'viewer_states').mkdir()
    for index in range(70):
        (assets / ('viewer_states/fixture_%02d.py' % index)).write_text('raise RuntimeError("must not import")\n', encoding='utf-8')
    python.mkdir()
    (python / 'entry.py').write_text('raise RuntimeError("must not import")\n', encoding='utf-8')
    panels.mkdir()
    outside = root / 'outside-source'
    outside.mkdir()
    (outside / 'outside.py').write_text('raise RuntimeError("never inspect")\n', encoding='utf-8')
    (panels / 'main.pypanel').write_text('<pythonPanelDocument/>', encoding='utf-8')
    user_configs = {
        'EEETools': {'env': [{'TOOLS_ROOT': str(assets)}, {'HOUDINI_PATH': {'value': '$TOOLS_ROOT', 'method': 'append'}}]},
        'vexManager': {'hpath': str(assets), 'enable': False},
        'houdini_renderman_denoise': {'env': [{'PYTHONPATH': {'value': str(python), 'method': 'append'}}, {'HOUDINI_PYTHON_PANEL_PATH': str(panels)}]},
        'dsh-houdini': {'path': str(assets)},
        'houdinimcp': {'env': [{'HOUDINI_PATH': '$ROOT_FROM_OTHER_PACKAGE'}]},
    }
    user_packages = package_dirs[0]
    for name, config in user_configs.items():
        (user_packages / (name + '.json')).write_text(json.dumps(config), encoding='utf-8')
    (user_packages / 'nested').mkdir()
    (user_packages / 'nested/hidden.json').write_text(json.dumps({'hpath': str(assets)}))
    (package_dirs[1] / 'site_tools.json').write_text(json.dumps({'hpath': str(assets)}))
    (package_dirs[2] / 'official_tools.json').write_text(json.dumps({'hpath': str(assets)}))
    (external / 'external_tools.json').write_text(json.dumps({'hpath': str(assets)}))
    (external / 'duplicate.json').write_text('{"enable":true,"enable":false}')
    missing_file = root / 'removed/previously_loaded.json'
    natives = {
        'EEETools': {'File path': str(user_packages / 'EEETools.json'), 'Active': True, 'enable': '1',
                     'Environment Variables': {'HOUDINI_PATH': [str(assets)], 'MY_API_TOKEN': ['native-never-return']},
                     'Resources': {'Root folder': str(assets), 'private_token': 'native-resource-secret'}},
        'mixed': {'File path': str(user_packages / 'houdini_renderman_denoise.json'), 'Active': True,
                  'Environment Variables': {'PYTHONPATH': [str(python)], 'HOUDINI_PYTHON_PANEL_PATH': [str(panels)]}},
        'missing': {'File path': str(missing_file), 'Active': True,
                    'Environment Variables': {'HOUDINI_PATH': [str(assets)]}},
    }
    variables = {'HOUDINI_USER_PREF_DIR': str(pref), 'HSITE': str(site), 'HFS': str(hfs),
                 'HOUDINI_PACKAGE_DIR': str(external), 'ROOT_FROM_OTHER_PACKAGE': str(assets)}
    ui = SimpleNamespace(packageInfo=lambda: json.dumps(natives))
    before_files = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob('*') if path.is_file()}
    before_scene = (hou.hipFile.path(), hou.hipFile.hasUnsavedChanges(), hou.frame(), tuple(hou.selectedNodes()))
    with patch.object(hou, 'getenv', side_effect=lambda name: variables.get(name)), \
         patch.object(hou, 'isUIAvailable', return_value=True), patch.object(hou, 'ui', ui, create=True):
        rows = discovery.package_catalog()
        assert rows['total'] == 10 and rows['runtime_status'] == 'observed', rows
        by_name = {row['name']: row for row in rows['entries']}
        assert not any(row['name'] == 'hidden' for row in rows['entries'])
        assert by_name['EEETools']['runtime']['package']['active'] is True
        assert by_name['EEETools']['runtime_root_matches_config'] is True
        assert by_name['EEETools']['runtime']['package']['condition_enabled'] is True
        assert by_name['vexManager']['enabled_in_config'] is False and by_name['vexManager']['runtime']['status'] == 'not_loaded'
        assert by_name['houdinimcp']['unresolved_paths'][0]['path'] is None
        assert by_name['previously_loaded']['config_status'] == 'missing' and by_name['previously_loaded']['runtime']['package']['active'] is True
        assert by_name['duplicate']['config_status'] == 'invalid'
        assert discovery.package_catalog(query='EEETools', limit=1)['total'] == 1
        assert discovery.package_catalog(limit=1)['truncated'] and discovery.package_catalog(offset=1, limit=1)['entries'] != rows['entries'][:1]
        all_text = json.dumps(rows)
        assert 'native-never-return' not in all_text and 'native-resource-secret' not in all_text
        mixed = discovery.package_inspect(str(user_packages / 'houdini_renderman_denoise.json'))
        assert mixed['runtime_root_matches_config'] is True
        assert {row['root'] for row in mixed['resource_folders']} == {str(python), str(panels)}
        relation = discovery.package_sources_for_path(str(python / 'entry.py'))
        assert relation['matches'][0]['name'] == 'mixed' and relation['matches'][0]['relation'] == 'source_under_native_search_path'
        assert discovery.package_sources_for_path(str(root / 'python-source-sibling/entry.py'))['matches'] == []
        if sys.platform == 'win32':
            assert discovery.package_sources_for_path(str(python / 'ENTRY.PY').upper())['matches'][0]['name'] == 'mixed'
        detail = discovery.package_inspect(str(user_packages / 'EEETools.json'), files=['toolbar/main.shelf'])
        assert detail['files'][0]['sha256'] == hashlib.sha256((assets / 'toolbar/main.shelf').read_bytes()).hexdigest()
        assert 'helper' not in sys.modules
        large_folder = next(folder for folder in detail['resource_folders'][0]['folders'] if Path(folder['path']).name == 'viewer_states')
        assert large_folder['truncated'] and large_folder['total'] is None and len(large_folder['children']) == 64
        reject(lambda: discovery.package_inspect(str(user_packages / 'EEETools.json'), files=['../outside.py']), 'inside')
        reject(lambda: discovery.package_inspect(str(user_packages / 'EEETools.json'), files=[str(root / 'outside.py')]), 'inside')
        link = assets / 'toolbar/linked-source'
        if os.name == 'nt':
            subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(outside)], check=True, capture_output=True)
        else:
            link.symlink_to(outside, target_is_directory=True)
        try:
            linked = discovery.package_inspect(str(user_packages / 'EEETools.json'))
            toolbar = next(folder for folder in linked['resource_folders'][0]['folders'] if Path(folder['path']).name == 'toolbar')
            assert next(item for item in toolbar['children'] if Path(item['path']) == link)['kind'] == 'link'
            reject(lambda: discovery.package_inspect(str(user_packages / 'EEETools.json'), files=['toolbar/linked-source/outside.py']), 'outside')
        finally:
            link.rmdir() if os.name == 'nt' else link.unlink()
        reject(lambda: discovery.read_package_config('$HOUDINI_USER_PREF_DIR/packages/EEETools.json'), 'absolute')
        for offset, limit in ((True, 1), (0, True), (0, 257)):
            reject(lambda: discovery.package_catalog(offset=offset, limit=limit), 'offset')
        original_iterdir = Path.iterdir
        def deny_toolbar(path):
            if path == assets / 'toolbar':
                raise PermissionError('fixture toolbar denied')
            return original_iterdir(path)
        with patch.object(Path, 'iterdir', deny_toolbar):
            denied = discovery.package_inspect(str(user_packages / 'EEETools.json'))
            assert denied['resource_folders'][0]['errors'][0]['path'] == str(assets / 'toolbar')
        conditional_file = external / 'conditional.json'
        conditional_file.write_text(json.dumps({'env': [{'ROOT': {'houdini_version >= 21.0': str(assets)}}, {'HOUDINI_PATH': '$ROOT'}]}))
        conditional = discovery.package_inspect(str(conditional_file))
        assert conditional['unresolved_paths'][0]['path'] is None
        standalone_file = external / 'standalone_hpath.json'
        standalone_file.write_text(json.dumps({'hpath': {'value': str(assets), 'method': 'append'}}))
        standalone = discovery.package_inspect(str(standalone_file))
        assert standalone['declared_resource_roots'] == [] and standalone['unresolved_paths'][0]['status'] == 'unresolved'
        array_file = external / 'array_hpath.json'
        array_file.write_text(json.dumps({'hpath': [{'value': str(assets), 'method': 'append'}]}))
        array = discovery.package_inspect(str(array_file))
        assert array['declared_resource_roots'] == [str(assets)] and not array['unresolved_paths']
        secret_file = external / 'secrets.json'
        secret_file.write_text(json.dumps({'hpath': str(assets), 'enable': "$API_TOKEN == 'enable-secret-literal'", 'private_api_token': 'top-secret-value',
                                          'unknown': {'credentials': ['nested-secret-value']},
                                          'requires': [{'password': 'known-field-secret'}],
                                          'env': [{'SIMPLE': 'innocent-name-secret'}, {'API_KEY': 'env-secret-value'},
                                                  {'HOUDINI_PATH': {"API_TOKEN == 'branch-secret'": str(assets)}}]}))
        secret_text = json.dumps(discovery.package_inspect(str(secret_file)))
        for secret in ('top-secret-value', 'nested-secret-value', 'known-field-secret', 'innocent-name-secret', 'env-secret-value', 'branch-secret', 'enable-secret-literal'):
            assert secret not in secret_text, secret_text
        raw_path, raw_data, _ = discovery.read_package_config(str(secret_file))
        assert raw_path == secret_file and raw_data['private_api_token'] == 'top-secret-value'
        same_root_file = external / 'same_root.json'
        same_root_file.write_text(json.dumps({'hpath': str(assets), 'env': [{'PYTHONPATH': str(assets)}]}))
        same_root = discovery.package_inspect(str(same_root_file), files=['toolbar/main.shelf'])
        assert {row['variable'] for row in same_root['resource_folders']} == {'PYTHONPATH', 'HOUDINI_PATH'} and len(same_root['files']) == 1
        same_root_file.unlink()
        # Internal edit reads are deliberate and separate from public discovery.
        conditional_file.unlink()
        standalone_file.unlink()
        array_file.unlink()
        secret_file.unlink()
    with patch.object(hou, 'isUIAvailable', return_value=False), patch.object(hou, 'getenv', side_effect=lambda name: variables.get(name)):
        unavailable = discovery.package_catalog(query='EEETools')
        assert unavailable['runtime_status'] == 'unavailable' and unavailable['entries'][0]['runtime']['status'] == 'unavailable'
    assert before_scene == (hou.hipFile.path(), hou.hipFile.hasUnsavedChanges(), hou.frame(), tuple(hou.selectedNodes()))
    assert before_files == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob('*') if path.is_file()}

print('PASS native Package discovery: disk/load separation, missing load facts, multiple roots, redaction, bounded reads and untouched fixtures ' + hou.applicationVersionString())
