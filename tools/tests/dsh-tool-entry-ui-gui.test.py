"""Check authored Panel/Viewer State/Shelf resources in an owned Houdini GUI.

Only the staged resource package and vendor resources are loaded. This verifies
native entry loading and widget behavior, not arbitrary artistic workflows or
physical keyboard/mouse interaction with the viewer state.
"""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, launch_directory, reexec_unpacked_test_cli


def probe():
    import hou
    from PySide6 import QtCore, QtWidgets
    import dsh_artist_example_panel as source
    import dsh_artist_example_state as state_source
    output = Path(os.environ['DSH_ENTRY_UI_OUTPUT'])
    resources = Path(os.environ['DSH_ENTRY_UI_RESOURCES'])
    assert Path(source.__file__).is_relative_to(resources), source.__file__
    assert Path(state_source.__file__).is_relative_to(resources), state_source.__file__
    window = hou.qt.mainWindow()
    timer = QtCore.QTimer(window)
    state = {'step': 0}
    def snapshot():
        n = state['node']
        return {'nodes': [c.path() for c in hou.node('/obj').allSubChildren()],
            'selected': [c.path() for c in hou.selectedNodes()],
            'flags': [n.isDisplayFlagSet(), n.isRenderFlagSet()],
            'parms': [(p.name(), p.unexpandedString() if p.parmTemplate().type()==hou.parmTemplateType.String
                       else p.rawValue()) for p in n.parms()]}
    def finish(result):
        (output / 'entry-ui-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        timer.stop()
        hou.hipFile.save(str(output / 'entry-example.hip'))
        window.close()
    def advance():
        try:
            if state['step'] == 0:
                interface = hou.pypanel.interfaceByName('dsh_artist_example_reference')
                assert interface is not None, 'package did not discover .pypanel'
                assert hou.ui.isRegisteredViewerState(state_source.STATE_NAME), 'package did not register viewer state'
                assert hou.shelves.tool('dsh_artist_example_plane_inspect') is not None, 'package did not discover shelf tool'
                geo = hou.node('/obj').createNode('geo', 'entry_fixture')
                state['node'] = geo.createNode('null', 'reference')
                state['node'].setSelected(True)
                state['before'] = snapshot()
                pane = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
                state['panel'] = pane.pane().createTab(hou.paneTabType.PythonPanel)
                state['panel'].setActiveInterface(interface)
                window.showNormal(); window.move(30, 30); window.resize(1100, 800)
            elif state['step'] == 1:
                pane = state['panel']
                assert not pane.activeInterfaceScriptErrors(), pane.activeInterfaceScriptErrors()
                widget = pane.activeInterfaceRootWidget()
                assert widget is not None
                assert isinstance(widget.chooser, hou.qt.NodeChooserButton)
                # Public native chooser signal drives the widget's input route;
                # this does not claim a physical selection in the chooser dialog.
                widget.chooser.nodeSelected.emit(state['node'])
                assert widget.node_path == state['node'].path()
                count = widget.filtered.rowCount()
                assert count > 0
                widget.search.setText('copyinput')
                assert 0 < widget.filtered.rowCount() < count
                assert snapshot() == state['before']
                state['widget'] = widget
                pane.reloadActiveInterface()
            elif state['step'] == 2:
                widget = state['panel'].activeInterfaceRootWidget()
                assert widget is not None, 'reloaded panel has no root widget'
                assert widget is not state['widget'], 'reload did not replace panel root widget'
                assert not state['panel'].activeInterfaceScriptErrors()
                widget.set_node(state['node'])
                state['dialog'] = QtWidgets.QDialog(window)
                state['dialog'].setWindowTitle('参考节点 · 原生组件')
                # A second owned instance tests a narrow window without moving
                # the native pane's root widget out of its host.
                state['narrow'] = source.create_panel()
                state['narrow'].set_node(state['node'])
                QtWidgets.QVBoxLayout(state['dialog']).addWidget(state['narrow'])
                state['dialog'].resize(420, 480); state['dialog'].show()
                state['viewer'] = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
                state['viewer'].setPwd(state['node'].parent())
                state['viewer'].runShelfTool('dsh_artist_example_plane_inspect')
            elif state['step'] == 3:
                assert state['viewer'].currentState() == state_source.STATE_NAME, ('state after shelf',state['viewer'].currentState())
                assert state['dialog'].width() <= 500
                assert state['dialog'].screen().grabWindow(state['dialog'].winId()).save(str(output / 'entry-panel-narrow.png'))
                state['viewer'].setCurrentState('select')
                assert snapshot() == state['before']
                state['narrow'].set_node(None)
                assert state['narrow'].model.rowCount() == 0 and state['narrow'].node_path is None
                state['dialog'].close()
                finish({'ok': True, 'houdini': hou.applicationVersionString(),
                    'package_sources': [str(Path(source.__file__)), str(Path(state_source.__file__))],
                    'native_panel_entry': True, 'panel_reload': True, 'search': True,
                    'chooser_signal': True, 'narrow_width': state['dialog'].width(),
                    'shelf_enters_state': True, 'exit_preserves_scene': True,
                    'unverified': ['physical node-chooser selection', 'viewport mouse/keyboard events']})
                return
            state['step'] += 1
        except Exception as error:
            finish({'ok': False, 'error': str(error), 'step': state['step']})
    timer.timeout.connect(advance); timer.start(1200)


def main():
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--houdini', required=True, type=Path)
    parser.add_argument('--python-version', required=True, choices=('3.11', '3.13'))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT) or output.exists() and any(output.iterdir()):
        parser.error('--output must be an empty directory outside the repository')
    output.mkdir(parents=True, exist_ok=True)
    builder = runpy.run_path(str(ROOT / 'skills/houdini-tool-development/scripts/build-entry-examples.py'))
    resources = builder['build'](output / 'resources', args.python_version)
    with tempfile.TemporaryDirectory(prefix='dsh-entry-ui-') as temp:
        env = isolated_environment(temp, executable=args.houdini, gui=True)
        (Path(temp) / 'packages/artist-example.json').write_text(json.dumps({'path': resources.as_posix()}), encoding='utf-8')
        hook_script = f"import runpy\nrunpy.run_path({str(Path(__file__).resolve())!r})['probe']()\n"
        for major, version in (('21.0', '3.11'), ('22.0', '3.13')):
            prefs = Path(env['HOUDINI_USER_PREF_DIR'].replace('__HVER__', major))
            hook = prefs / f'python{version}libs/uiready.py'
            hook.parent.mkdir(parents=True); hook.write_text(hook_script, encoding='utf-8')
        env.update(DSH_ENTRY_UI_OUTPUT=str(output), DSH_ENTRY_UI_RESOURCES=str(resources))
        info = subprocess.STARTUPINFO(); info.dwFlags |= subprocess.STARTF_USESHOWWINDOW; info.wShowWindow = 0
        with (output / 'entry-ui-process.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([str(args.houdini.resolve()), '-foreground', '-geometry=1100x800+12000+12000'],
                cwd=launch_directory(args.houdini), env=env, stdout=log, stderr=log, startupinfo=info)
            try:
                process.wait(timeout=90)
            finally:
                if process.poll() is None:
                    process.kill(); process.wait(timeout=20)
        result_file = output / 'entry-ui-result.json'
        result = json.loads(result_file.read_text(encoding='utf-8')) if result_file.exists() else {'ok': False, 'error': 'no GUI report'}
        result['exit_code'] = process.returncode
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result['ok'] or process.returncode != 0:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
