"""Native registration, source isolation and truthful failure receipts; isolated hython."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import hou
import dsh_tool_packages as packages
import dsh_package_discovery as discovery
import dsh_hou_helpers as helpers

def fails(function, match, phase='package_action_preflight'):
    try:
        function()
        raise AssertionError('operation unexpectedly succeeded')
    except helpers.CheckpointError as error:
        assert match in str(error), str(error)
        assert error.evidence['phase'] == phase, error.evidence
        return error.evidence

with tempfile.TemporaryDirectory(prefix='dsh-native-packages-') as temporary:
    fixture = Path(temporary)
    source = fixture / 'artist-tools'
    (source / 'toolbar').mkdir(parents=True)
    (source / '.git').mkdir()
    (source / '.git/bad.shelf').write_text('never a resource', encoding='utf-8')
    other = source / ('python3.11libs' if sys.version_info[:2] != (3, 11) else 'python3.13libs')
    other.mkdir(); (other / 'hou.py').write_text('unused = True', encoding='utf-8')
    shelf = source / 'toolbar/artist.shelf'
    shelf.write_text('<shelfDocument><tool name="dsh_native_fixture" label="Fixture"><script scriptType="python">pass</script></tool></shelfDocument>', encoding='utf-8')
    before = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob('*') if p.is_file()}
    config = fixture / 'ArtistTools.json'
    created = packages.tool_package_create(str(source), str(config))
    parsed = json.loads(config.read_text(encoding='utf-8'))
    assert parsed == {'enable': True, 'env': [{'HOUDINI_PATH': {'value': source.as_posix(), 'method': 'append'}}]}, parsed
    assert created['resource_files_copied'] is False and created['loaded'] is False
    assert created['config_sha256'] == hashlib.sha256(config.read_bytes()).hexdigest()
    assert {str(p.relative_to(source)): p.read_bytes() for p in source.rglob('*') if p.is_file()} == before
    assert not any(path.suffix == '.zip' for path in fixture.rglob('*'))
    fails(lambda: packages.tool_package_create(str(source), str(config)), 'already exists', 'package_create_preflight')
    fails(lambda: packages.tool_package_create(str(source), str(fixture / 'missing/Tools.json')), 'existing directory', 'package_create_preflight')
    with patch.object(hou, 'getenv', side_effect=lambda name: str(fixture / 'official') if name == 'HFS' else None):
        official = fixture / 'official'; official.mkdir()
        fails(lambda: packages.tool_package_create(str(source), str(official / 'Tools.json')), '$HFS', 'package_create_preflight')
    versioned = packages.tool_package_create(str(source), str(fixture / 'versioned.json'), houdini_versions=['22.0', '21.0'])
    assert versioned['houdini_versions'] == ['21.0', '22.0'] and 'houdini_version' in versioned['enabled_in_config']
    assert packages.tool_package_create(str(source), str(fixture / 'disabled.json'), enable=False)['enabled_in_config'] is False

    competing = fixture / 'racing.json'
    original_link = os.link
    def race(source_file, target):
        Path(target).write_text('external registration', encoding='utf-8')
        return original_link(source_file, target)
    with patch.object(os, 'link', side_effect=race):
        evidence = fails(lambda: packages.tool_package_create(str(source), str(competing)), 'racing.json', 'package_create_failure')
    assert competing.read_text(encoding='utf-8') == 'external registration'
    assert evidence['registration_created'] is False and evidence['file_writes'] == [] and evidence['restored'] is True
    assert not list(fixture.glob('.racing.json-*.tmp'))
    original_fdopen = os.fdopen
    class PartialWrite:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): self.stream.__enter__(); return self
        def write(self, content): self.stream.write(content[:5]); raise OSError('fixture partial write')
        def __exit__(self, *args): return self.stream.__exit__(*args)
    with patch.object(os, 'fdopen', side_effect=lambda *args, **kwargs: PartialWrite(original_fdopen(*args, **kwargs))):
        evidence = fails(lambda: packages.tool_package_create(str(source), str(fixture / 'retry.json')), 'partial write', 'package_create_failure')
    assert evidence['restored'] is True and not (fixture / 'retry.json').exists()
    assert not list(fixture.glob('.retry.json-*.tmp'))
    packages.tool_package_create(str(source), str(fixture / 'retry.json'))

    current_python = source / ('python%d.%dlibs' % sys.version_info[:2]); current_python.mkdir()
    lazy = types.ModuleType('dsh_native_lazy_fixture')
    def forbidden_attribute(name):
        raise AssertionError('inspection executed lazy module code: ' + name)
    lazy.__getattr__ = forbidden_attribute
    sys.modules['dsh_native_lazy_fixture'] = lazy
    sys.modules['dsh_native_blocked_fixture'] = None
    (current_python / 'dsh_native_blocked_fixture.py').write_text('never_imported = True', encoding='utf-8')
    (current_python / 'json.pyd').write_bytes(b'not loaded by inspection')
    (current_python / 'json.backup.py').write_text('never imported either', encoding='utf-8')
    try:
        report = packages.resource_report([source])
        assert any(item['name'] == 'dsh_native_blocked_fixture' for item in report['conflicts']), report
        assert any(item['name'] == 'json' for item in report['conflicts']), report
        assert not any(item['file'].endswith('json.backup.py') for item in report['entries']), report
    finally:
        del sys.modules['dsh_native_lazy_fixture']; del sys.modules['dsh_native_blocked_fixture']
        for path in current_python.iterdir(): path.unlink()

    original = config.read_bytes()
    registry = {}
    def loaded(active=True, locations=None):
        return {'File path': str(config), 'Active': active, 'Environment Variables': locations or {'HOUDINI_PATH': str(source)}, 'Resources': {'Root folder': str(source)}}
    ui = MagicMock()
    ui.loadPackage.side_effect = lambda path: registry.update(ArtistTools=loaded())
    ui.deactivatePackage.side_effect = lambda path: registry.update(ArtistTools=loaded(False))
    ui.activatePackage.side_effect = lambda path: registry.update(ArtistTools=loaded())
    ui.unloadPackage.side_effect = lambda path: registry.clear()
    with patch.object(packages, '_require_gui', return_value=None), patch.object(hou, 'ui', ui, create=True), patch.object(discovery, '_loaded_package_metadata', side_effect=lambda: {'status': 'observed', 'packages': registry}):
        preview = packages.tool_package_action(str(config), 'load')
        assert preview['dry_run'] and not preview['applied'] and not preview['conflicts'] and not ui.loadPackage.called
        applied = packages.tool_package_action(str(config), 'load', dry_run=False, expected_sha256=created['config_sha256'])
        assert applied['applied'] and applied['runtime']['package']['active'] is True
        fails(lambda: packages.tool_package_action(str(config), 'load', dry_run=False), 'already loaded')
        assert ui.loadPackage.call_count == 1
        fails(lambda: packages.tool_package_action(str(config), 'deactivate', dry_run=False, expected_sha256='wrong'), 'changed since')
        packages.tool_package_action(str(config), 'deactivate', dry_run=False)
        assert registry['ArtistTools']['Active'] is False
        packages.tool_package_action(str(config), 'activate', dry_run=False)
        packages.tool_package_action(str(config), 'unload', dry_run=False)
        assert not registry and config.read_bytes() == original and shelf.is_file()
        fails(lambda: packages.tool_package_action(str(config), 'uninstall', dry_run=False), 'action must')
        config.write_text(json.dumps({'enable': "houdini_version < '1.0'", 'env': [{'HOUDINI_PATH': str(source)}]}), encoding='utf-8')
        registry['ArtistTools'] = {**loaded(False), 'enable': '0'}
        fails(lambda: packages.tool_package_action(str(config), 'activate', dry_run=False), 'condition is false')
        assert ui.activatePackage.call_count == 1
        config.write_bytes(original); registry.clear()

        python_root = fixture / 'python-source'; python_root.mkdir()
        (python_root / 'json.py').write_text('never = "imported"', encoding='utf-8')
        direct = fixture / 'direct.json'
        direct.write_text(json.dumps({'hpath': str(source), 'env': [{'PYTHONPATH': str(python_root)}]}), encoding='utf-8')
        conflict = packages.tool_package_action(str(direct), 'load')
        assert any(item['name'] == 'json' for item in conflict['conflicts']), conflict
        fails(lambda: packages.tool_package_action(str(direct), 'load', dry_run=False), 'conflict')
        assets = fixture / 'assets'; assets.mkdir()
        geo = hou.node('/obj').createNode('geo', 'native_package_fixture')
        subnet = geo.createNode('subnet'); box = subnet.createNode('box')
        output = subnet.createNode('output'); output.setInput(0, box)
        library = assets / 'foreign.hda'
        asset = subnet.createDigitalAsset(name='dsh_fixture::native_resource::1.0', hda_file_name=str(library), create_backup=False)
        config.write_text(json.dumps({'hpath': str(source), 'env': [{'HOUDINI_OTLSCAN_PATH': str(assets)}]}), encoding='utf-8')
        manual = packages.tool_package_action(str(config), 'load')
        assert asset.path() in manual['affected_instances'] and manual['blockers'], manual
        fails(lambda: packages.tool_package_action(str(config), 'load', dry_run=False), 'still used')
        registry['ArtistTools'] = loaded(locations={'HOUDINI_PATH': str(source), 'HOUDINI_OTLSCAN_PATH': str(assets)})
        moved = library.with_suffix('.moved'); library.rename(moved)
        try:
            preview = packages.tool_package_action(str(config), 'deactivate')
            assert asset.path() in preview['affected_instances'], preview
            fails(lambda: packages.tool_package_action(str(config), 'deactivate', dry_run=False), 'still used')
        finally:
            moved.rename(library); geo.destroy(); hou.hda.uninstallFile(str(library))
        config.write_bytes(original); registry.clear()

        def partial(path):
            registry['ArtistTools'] = loaded()
            raise RuntimeError('fixture native load failed after dispatch')
        ui.loadPackage.side_effect = partial
        evidence = fails(lambda: packages.tool_package_action(str(config), 'load', dry_run=False), 'failed after dispatch', 'package_action_failure')
        assert evidence['native_action_attempted'] is True and evidence['restored'] is False
        assert evidence['runtime']['status'] == 'observed' and evidence['scene_writes'] is None and config.read_bytes() == original
        registry.clear()
        with patch.object(packages, 'native_package_state', side_effect=ValueError('fixture readback unavailable')):
            evidence = fails(lambda: packages.tool_package_action(str(config), 'load', dry_run=False), 'failed after dispatch', 'package_action_failure')
            assert evidence['runtime']['status'] == 'unavailable' and 'readback unavailable' in evidence['runtime']['readback_error']
        registry.clear()
        ui.loadPackage.side_effect = lambda path: registry.update(ArtistTools=loaded(locations={'HOUDINI_PATH': str(fixture / 'unrelated')}))
        evidence = fails(lambda: packages.tool_package_action(str(config), 'load', dry_run=False), 'do not match', 'package_action_failure')
        assert evidence['restored'] is False

    import dsh_bridge
    bridge_config = fixture / 'bridge-partial.json'
    original_unlink = Path.unlink
    def denied_cleanup(path, *args, **kwargs):
        if path.name.startswith('.bridge-partial.json-'):
            raise PermissionError('fixture temporary cleanup denied')
        return original_unlink(path, *args, **kwargs)
    code = 'try:\n    tool_package_create(%r, %r)\nexcept Exception:\n    pass\n' % (str(source), str(bridge_config))
    code += "try:\n    tab_create('/obj', 'geo', name='after_package_failure')\nexcept Exception:\n    pass\n__result__={'incorrect_success':True}"
    with patch.object(Path, 'unlink', denied_cleanup):
        receipt = dsh_bridge.run_code(code, owner_session='native-package-failure-fixture')
    assert receipt['ok'] is False and hou.node('/obj/after_package_failure') is None, receipt
    assert receipt['verbs'][0]['summary']['restored'] is False and receipt['verbs'][1]['summary']['dispatched'] is False, receipt
    assert bridge_config.exists() and receipt['transaction']['status'] == 'recovery_unverified', receipt

print('PASS native Package registration and runtime boundaries ' + hou.applicationVersionString())
