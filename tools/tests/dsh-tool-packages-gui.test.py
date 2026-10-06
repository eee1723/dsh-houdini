"""Direct source Package startup and native lifecycle in owned H21/H22 GUI workers."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, launch_directory, reexec_unpacked_test_cli

def shelf(name):
    return '<shelfDocument><tool name="' + name + '" label="Fixture" icon="SOP_box"><script scriptType="python"><![CDATA[import hou\nhou.session.dsh_native_clicked = getattr(hou.session, "dsh_native_clicked", 0) + 1\n]]></script></tool></shelfDocument>'

def prepare(fixture):
    import hou
    sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
    import dsh_tool_packages as packages
    resources = fixture / 'artist-source'
    for name in ('otls', 'toolbar', 'python_panels', 'python%d.%dlibs' % sys.version_info[:2]):
        (resources / name).mkdir(parents=True, exist_ok=True)
    (resources / ('python%d.%dlibs/dsh_native_fixture_module.py' % sys.version_info[:2])).write_text('VALUE = 73\n', encoding='utf-8')
    (resources / 'toolbar/main.shelf').write_text(shelf('dsh_native_fixture_action'), encoding='utf-8')
    (resources / 'python_panels/main.pypanel').write_text(r'''<pythonPanelDocument><interface name="dsh_native_fixture_panel" label="Fixture Panel" icon="SOP_box"><script><![CDATA[
from PySide6 import QtWidgets
def onCreateInterface():
    widget = QtWidgets.QLabel("\u5de5\u5177\u5305\u754c\u9762")
    widget.setObjectName("dsh_native_fixture_widget")
    return widget
]]></script><includeInPaneTabMenu menu_position="700" create_separator="false"/></interface></pythonPanelDocument>''', encoding='utf-8')
    geo = hou.node('/obj').createNode('geo')
    author = geo.createNode('subnet'); box = author.createNode('box')
    output = author.createNode('output'); output.setInput(0, box)
    library = resources / 'otls/main.hda'
    author.createDigitalAsset(name='dsh_fixture::direct_package::1.0', hda_file_name=str(library), min_num_inputs=0, max_num_inputs=0, create_backup=False)
    geo.destroy(); hou.hda.uninstallFile(str(library))
    result = packages.tool_package_create(str(resources), str(fixture / 'packages/ArtistTools.json'), houdini_versions=['%d.%d' % hou.applicationVersion()[:2]])
    assert not result['resource_files_copied'] and not result['loaded']
    conditional_root = fixture / 'condition-never-enabled'; conditional_root.mkdir()
    (fixture / 'packages/NeverEnabled.json').write_text(json.dumps({'enable': "houdini_version < '1.0'", 'env': [{'HOUDINI_PATH': str(conditional_root)}]}), encoding='utf-8')
    print('prepared direct source ' + hou.applicationVersionString())

def probe():
    import hou
    from PySide6 import QtCore, QtWidgets
    sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
    import dsh_tool_packages as packages
    from dsh_package_discovery import package_inspect
    fixture = Path(os.environ['DSH_TOOL_PACKAGE_FIXTURE'])
    config = fixture / 'packages/ArtistTools.json'
    source = fixture / 'artist-source'
    phase = os.environ['DSH_TOOL_PACKAGE_PHASE']
    original = config.read_bytes()
    def finish(result):
        Path(os.environ['DSH_TOOL_PACKAGE_REPORT']).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        hou.hipFile.clear(suppress_save_prompt=True)
        QtCore.QTimer.singleShot(100, hou.ui.mainQtWindow().close)
    def inspect():
        try:
            before = package_inspect(str(config))
            assert before['runtime']['package']['active'] is True and before['runtime_root_matches_config'] is True, before
            assert 'dsh_native_fixture_action' in hou.shelves.tools()
            assert 'dsh_native_fixture_panel' in hou.pypanel.interfaces()
            assert hou.nodeType(hou.sopNodeTypeCategory(), 'dsh_fixture::direct_package::1.0') is not None
            conditional = fixture / 'packages/NeverEnabled.json'
            conditional_original = conditional.read_bytes()
            conditional_state = package_inspect(str(conditional))['runtime']
            assert conditional_state['status'] == 'not_loaded' or conditional_state['package']['condition_enabled'] is False, conditional_state
            try:
                packages.tool_package_action(str(conditional), 'activate', dry_run=False)
                raise AssertionError('activation bypassed native false condition')
            except Exception as error:
                assert 'condition' in str(error) or 'not loaded' in str(error), str(error)
            assert conditional.read_bytes() == conditional_original
            geo = hou.node('/obj').createNode('geo', 'OriginalContent')
            original_node = geo.createNode('box', 'original_box'); original_node.parm('sizex').set(3.25)
            original_node.setSelected(True, clear_all_selected=True); hou.setFrame(13)
            snapshot = (original_node.sessionId(), original_node.parm('sizex').eval(), hou.frame(), tuple(node.path() for node in hou.selectedNodes()), tuple(original_node.geometry().boundingBox().sizevec()))
            asset = geo.createNode('dsh_fixture::direct_package::1.0', 'ToolInstance', exact_type_name=True)
            assert len(asset.geometry().points()) == 8
            library = source / 'otls/main.hda'; moved = library.with_suffix('.moved'); library.rename(moved)
            try:
                preview = packages.tool_package_action(str(config), 'deactivate')
                assert asset.path() in preview['affected_instances'], preview
                try:
                    packages.tool_package_action(str(config), 'deactivate', dry_run=False)
                    raise AssertionError('unloaded an in-use HDA')
                except Exception as error:
                    assert 'still used' in str(error), str(error)
            finally:
                moved.rename(library)
            assert asset.type().definition() is not None
            asset.destroy()
            alternate = fixture / 'alternate'; alternate.mkdir(exist_ok=True)
            changed = json.loads(original); changed['env'][0]['HOUDINI_PATH']['value'] = alternate.as_posix()
            config.write_text(json.dumps(changed), encoding='utf-8')
            try:
                try:
                    packages.tool_package_action(str(config), 'deactivate', dry_run=False)
                    raise AssertionError('config displaced native resource identity')
                except Exception as error:
                    assert 'differs from' in str(error), str(error)
            finally:
                config.write_bytes(original)
            panel = hou.ui.curDesktop().createFloatingPaneTab(hou.paneTabType.PythonPanel)
            panel.setActiveInterface(hou.pypanel.interfaces()['dsh_native_fixture_panel'])
            for _ in range(5):
                loop = QtCore.QEventLoop(); QtCore.QTimer.singleShot(20, loop.quit); loop.exec()
            assert not panel.activeInterfaceScriptErrors(), panel.activeInterfaceScriptErrors()
            root_widget = panel.activeInterfaceRootWidget()
            widget = root_widget if isinstance(root_widget, QtWidgets.QLabel) else root_widget.findChild(QtWidgets.QLabel, 'dsh_native_fixture_widget')
            assert widget is not None and widget.text() == '工具包界面'
            panel.close()
            action = 'dsh_native_extension_action' if phase == 'extension' else 'dsh_native_fixture_action'
            assert action in hou.shelves.tools(), 'fresh startup failed to discover added source resource'
            assert Path(hou.shelves.tool(action).filePath()).is_relative_to(source)
            hou.ui.paneTabOfType(hou.paneTabType.SceneViewer).runShelfTool(action)
            def after_shelf():
                try:
                    assert getattr(hou.session, 'dsh_native_clicked', None) == 1
                    import dsh_native_fixture_module
                    assert dsh_native_fixture_module.VALUE == 73
                    inactive = packages.tool_package_action(str(config), 'deactivate', dry_run=False)
                    assert inactive['runtime']['package']['active'] is False
                    assert inactive['restart_required_for_python_cache'] and 'dsh_native_fixture_module' in inactive['cached_python_modules']
                    assert 'dsh_native_fixture_action' not in hou.shelves.tools()
                    assert 'dsh_native_fixture_panel' not in hou.pypanel.interfaces()
                    active = packages.tool_package_action(str(config), 'activate', dry_run=False)
                    assert active['runtime']['package']['active'] is True
                    assert 'dsh_native_fixture_action' in hou.shelves.tools()
                    assert 'dsh_native_fixture_panel' in hou.pypanel.interfaces()
                    removed = packages.tool_package_action(str(config), 'unload', dry_run=False)
                    assert removed['runtime']['status'] == 'not_loaded'
                    assert config.read_bytes() == original and source.is_dir() and library.is_file()
                    after = (original_node.sessionId(), original_node.parm('sizex').eval(), hou.frame(), tuple(node.path() for node in hou.selectedNodes()), tuple(original_node.geometry().boundingBox().sizevec()))
                    assert after == snapshot and not original_node.errors(), (snapshot, after)
                    finish({'ok': True, 'houdini_version': hou.applicationVersionString(), 'phase': phase,
                            'direct_native_startup': True, 'hda_public_output': True, 'shelf_public_action': True,
                            'panel_real_widget': True, 'added_source_loaded_on_next_startup': phase == 'extension',
                            'native_deactivate_activate_unload': True, 'in_use_library_moved_refused': True,
                            'config_mismatch_refused': True, 'existing_content_unchanged': True,
                            'native_false_condition_activation_refused': True,
                            'json_unchanged': True, 'source_retained': True, 'python_cache_reported': True})
                except BaseException:
                    finish({'ok': False, 'error': traceback.format_exc(), 'native': json.loads(hou.ui.packageInfo())})
            QtCore.QTimer.singleShot(300, after_shelf)
            return
        except BaseException:
            finish({'ok': False, 'error': traceback.format_exc(), 'native': json.loads(hou.ui.packageInfo())})
    QtCore.QTimer.singleShot(2000, inspect)

def cli():
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--houdini', required=True, type=Path)
    parser.add_argument('--report-dir', type=Path)
    args = parser.parse_args()
    executable = args.houdini.resolve()
    with tempfile.TemporaryDirectory(prefix='dsh-direct-package-gui-') as temporary:
        fixture = Path(temporary)
        environment = isolated_environment(fixture, executable=executable, gui=True)
        environment['DSH_TOOL_PACKAGE_FIXTURE'] = str(fixture)
        prepared = subprocess.run([str(executable.with_name('hython.exe')), str(Path(__file__).resolve()), '--prepare', str(fixture)],
                                  cwd=launch_directory(executable), env=environment, capture_output=True, text=True, timeout=90)
        if prepared.returncode:
            raise RuntimeError(prepared.stdout + prepared.stderr)
        config = fixture / 'packages/ArtistTools.json'; original = config.read_bytes()
        source = fixture / 'artist-source'
        source_before = {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source.rglob('*') if path.is_file()}
        for version, python in [('21.0', '3.11'), ('22.0', '3.13')]:
            hook = Path(environment['HOUDINI_USER_PREF_DIR'].replace('__HVER__', version)) / ('python' + python + 'libs/uiready.py')
            hook.parent.mkdir(parents=True, exist_ok=True)
            hook.write_text('import runpy\nrunpy.run_path(' + repr(str(Path(__file__).resolve())) + ')["probe"]()\n', encoding='utf-8')
        results = []
        for phase in ('initial', 'extension'):
            if phase == 'extension':
                (source / 'toolbar/extension.shelf').write_text(shelf('dsh_native_extension_action'), encoding='utf-8')
            report = fixture / (phase + '.json')
            environment['DSH_TOOL_PACKAGE_REPORT'] = str(report)
            environment['DSH_TOOL_PACKAGE_PHASE'] = phase
            startup = subprocess.STARTUPINFO() if os.name == 'nt' else None
            if startup:
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startup.wShowWindow = 0
            log_file = fixture / (phase + '.log')
            with log_file.open('w', encoding='utf-8') as log:
                process = subprocess.Popen([str(executable), '-foreground', '-geometry=800x600+12000+12000'],
                                           cwd=launch_directory(executable), env=environment, stdout=log, stderr=log, startupinfo=startup)
                try:
                    process.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    pass
                finally:
                    if process.poll() is None:
                        process.kill(); process.wait()
            result = json.loads(report.read_text(encoding='utf-8')) if report.exists() else {'ok': False, 'error': 'no GUI report'}
            result['exit_code'] = process.returncode
            result['source_files_unchanged'] = all(hashlib.sha256((source / relative).read_bytes()).hexdigest() == digest for relative, digest in source_before.items())
            result['registration_unchanged_between_processes'] = config.read_bytes() == original
            results.append(result)
            if args.report_dir:
                args.report_dir.mkdir(parents=True, exist_ok=True)
                name = executable.parent.parent.name + '-' + phase
                (args.report_dir / (name + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                (args.report_dir / (name + '.log')).write_bytes(log_file.read_bytes())
            if not result['ok']:
                break
        print(json.dumps(results, ensure_ascii=False))
        return 0 if len(results) == 2 and all(result['ok'] and result['exit_code'] == 0 and result['source_files_unchanged'] and result['registration_unchanged_between_processes'] for result in results) else 1

if __name__ == '__main__':
    if '--prepare' in sys.argv:
        prepare(Path(sys.argv[sys.argv.index('--prepare') + 1]))
    else:
        sys.exit(cli())
