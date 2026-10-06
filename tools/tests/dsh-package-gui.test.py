"""Isolated native Package discovery; disk files and actual GUI load facts.

Run with ordinary Python --houdini EXE. Only newly created fixture processes
and files are changed; the user's preferences and live scene are never used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, launch_directory, reexec_unpacked_test_cli


def probe():
    import hou
    from PySide6 import QtCore

    def inspect():
        result = {}
        try:
            sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
            import dsh_bridge as bridge
            import dsh_package_discovery as discovery
            package_dir = Path(os.environ['DSH_PACKAGE_FIXTURE_DIR'])
            unchanged = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in package_dir.glob('*.json')}
            before = (hou.hipFile.path(), hou.hipFile.hasUnsavedChanges(), hou.frame(), tuple(hou.selectedNodes()))

            def query(code):
                receipt = bridge.run_code(code, owner_session='package-gui-test', read_only=True)
                assert receipt['ok'], receipt
                return receipt['result']

            first = query("__result__=package_catalog(query='fixture_')")
            second = query("__result__=package_catalog(query='fixture_')")
            assert first['runtime_status'] == 'observed' and first['entries'] == second['entries'], first
            by_name = {entry['name']: entry for entry in first['entries']}
            enabled = by_name['fixture_enabled']
            assert enabled['runtime']['package']['active'] is True, enabled
            assert enabled['runtime_root_matches_config'] is True, enabled
            disabled = by_name['fixture_disabled']
            assert disabled['enabled_in_config'] is False, disabled
            assert disabled['runtime']['status'] == 'not_loaded' or disabled['runtime']['package']['active'] is False, disabled
            array = by_name['fixture_array']
            assert array['runtime_root_matches_config'] is True, array
            standalone = by_name['fixture_standalone']
            assert standalone['declared_resource_roots'] == [] and standalone['unresolved_paths'], standalone
            assert standalone['runtime']['package']['search_roots'] == [], standalone
            multiple = query('__result__=package_inspect(' + repr(str(package_dir / 'fixture_multiple.json')) + ')')
            assert multiple['runtime']['package']['active'] is True and multiple['runtime_root_matches_config'] is True, multiple
            assert {row['variable'] for row in multiple['resource_locations']} == {'PYTHONPATH', 'HOUDINI_PYTHON_PANEL_PATH'}, multiple
            python_source = Path(os.environ['DSH_PACKAGE_PYTHON_SOURCE']) / 'fixture_discovery_module.py'
            assert 'fixture_discovery_module' not in sys.modules
            relation = discovery.package_sources_for_path(str(python_source))
            assert any(row['name'] == 'fixture_multiple' for row in relation['matches']), relation
            assert unchanged == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in package_dir.glob('*.json')}
            (package_dir / 'fixture_enabled.json').unlink()
            missing = query("__result__=package_catalog(query='fixture_enabled')")['entries'][0]
            assert missing['config_status'] == 'missing' and missing['runtime']['package']['active'] is True, missing
            assert before == (hou.hipFile.path(), hou.hipFile.hasUnsavedChanges(), hou.frame(), tuple(hou.selectedNodes()))
            native_metadata = discovery._loaded_package_metadata()
            native_facts = {name: {'keys': list(row), 'enable': discovery._public_value(row.get('enable')), 'expression_enable': discovery._public_value(row.get('expression enable'))}
                            for name, row in native_metadata['packages'].items() if name.startswith('fixture_')}
            result = {'ok': True, 'version': hou.applicationVersionString(), 'enabled': enabled, 'native_enable_observation': native_facts,
                      'disabled': disabled, 'array_path': array, 'unsupported_standalone_path': standalone,
                      'multiple': multiple, 'source_relation': relation,
                      'loaded_file_removed': missing, 'repeated_equal': True, 'scene_unchanged': True,
                      'source_not_imported': True}
        except Exception:
            import traceback
            result = {'ok': False, 'error': traceback.format_exc()}
        Path(os.environ['DSH_PACKAGE_REPORT']).write_text(json.dumps(result), encoding='utf-8')
        QtCore.QTimer.singleShot(100, hou.ui.mainQtWindow().close)

    QtCore.QTimer.singleShot(2000, inspect)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--houdini', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    reexec_unpacked_test_cli()
    executable = args.houdini.resolve()
    with tempfile.TemporaryDirectory(prefix='dsh-package-gui-') as temporary:
        root = Path(temporary)
        environment = isolated_environment(root, executable=executable, gui=True)
        resources, python, panels = (root / name for name in ('resources', 'python-source', 'panels'))
        (resources / 'toolbar').mkdir(parents=True)
        (resources / 'toolbar/fixture.shelf').write_text('<shelfDocument/>', encoding='utf-8')
        python.mkdir()
        (python / 'fixture_discovery_module.py').write_text('raise RuntimeError("discovery must not import")\n', encoding='utf-8')
        panels.mkdir()
        (root / 'packages/fixture_enabled.json').write_text(json.dumps({'hpath': str(resources)}))
        (root / 'packages/fixture_disabled.json').write_text(json.dumps({'enable': False, 'hpath': str(resources)}))
        (root / 'packages/fixture_array.json').write_text(json.dumps({'hpath': [{'value': str(resources), 'method': 'append'}]}))
        (root / 'packages/fixture_standalone.json').write_text(json.dumps({'hpath': {'value': str(resources), 'method': 'append'}}))
        (root / 'packages/fixture_multiple.json').write_text(json.dumps({'env': [
            {'var': 'PYTHONPATH', 'value': str(python), 'method': 'append'},
            {'HOUDINI_PYTHON_PANEL_PATH': {'value': str(panels), 'method': 'append'}}]}))
        for version, language in [('21.0', '3.11'), ('22.0', '3.13')]:
            hook = Path(environment['HOUDINI_USER_PREF_DIR'].replace('__HVER__', version)) / ('python' + language + 'libs/uiready.py')
            hook.parent.mkdir(parents=True)
            hook.write_text('import runpy\nrunpy.run_path(' + repr(str(Path(__file__).resolve())) + ')["probe"]()\n')
        report = root / 'report.json'
        environment.update(DSH_PACKAGE_REPORT=str(report), DSH_PACKAGE_FIXTURE_DIR=str(root / 'packages'),
                           DSH_PACKAGE_PYTHON_SOURCE=str(python))
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        with (root / 'process.log').open('w') as log:
            process = subprocess.Popen([str(executable), '-foreground', '-geometry=800x600+12000+12000'],
                                       cwd=launch_directory(executable), env=environment, stdout=log, stderr=log, startupinfo=startup)
            try:
                process.wait(timeout=100)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        result = json.loads(report.read_text()) if report.exists() else {'ok': False, 'error': 'no GUI report', 'log': (root / 'process.log').read_text(errors='replace')}
        result['exit_code'] = process.returncode
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0 if result['ok'] and process.returncode == 0 else 1)
