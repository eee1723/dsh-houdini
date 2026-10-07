"""Native target UI capture and unchanged scene/UI in owned H21/H22 workers.

Images are evidence for human inspection, not an automatic artistic-quality
claim. No live Bridge, user HIP, desktop automation, or paid model is used.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import http.client
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, launch_directory, reexec_unpacked_test_cli


def probe():
    import hou
    from hutil.Qt import QtCore, QtGui, QtWidgets
    sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
    import dsh_ui_capture as capture
    import dsh_hou_helpers as helpers
    import dsh_bridge as bridge
    output = Path(os.environ['DSH_UI_CAPTURE_OUTPUT'])
    active_fixture = False  # Physical keyboard focus is outside this fixture.
    exposed_fixture = os.environ.get('DSH_UI_CAPTURE_EXPOSED') == '1'
    timer = QtCore.QTimer(hou.qt.mainWindow())
    state = {'step': 0, 'captures': [], 'failures': [], 'pending': 0, 'queued_shots': [], 'shot_running': False}
    import ctypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    foreground = user32.GetForegroundWindow
    foreground.argtypes = []; foreground.restype = ctypes.c_void_p

    def snapshot():
        pane_state = []
        for pane in hou.ui.paneTabs():
            # Native close is finalized when control returns to the outer GUI
            # loop; compare the user's preexisting panes, then verify private
            # pane disposal on the next timer tick below.
            if pane.name().startswith('__dsh_ui_capture_'):
                continue
            if isinstance(pane, hou.PathBasedPaneTab):
                pane_state.append((pane.name(), str(pane.type()), pane.isCurrentTab(),
                    pane.currentNode().path() if pane.currentNode() else None,
                    pane.pwd().path() if pane.pwd() else None, pane.isPin()))
        nodes = []
        for node in hou.node('/obj').allSubChildren():
            nodes.append((node.sessionId(), node.path(), tuple(node.position()), node.isSelected(), node.isCurrent(),
                node.parmTemplateGroup().asDialogScript(), node.userDataDict(),
                tuple((p.name(), p.rawValue(), tuple(k.asCode() for k in p.keyframes())) for p in node.parms())))
        boxes = [(b.name(), b.comment(), tuple(b.position()), tuple(b.size()),
                  tuple(item.name() for item in b.items())) for b in state['geo'].networkBoxes()]
        notes = [(n.name(), n.text(), tuple(n.position()), tuple(n.size())) for n in state['geo'].stickyNotes()]
        app = QtWidgets.QApplication.instance()
        return {'hip': hou.hipFile.path(), 'unsaved': hou.hipFile.hasUnsavedChanges(),
            'frame': float(hou.frame()), 'pwd': hou.pwd().path(), 'selection': tuple(n.path() for n in hou.selectedNodes()),
            'selected_items': tuple((i.parent().path(), i.name(), i.sessionId()) for i in hou.selectedItems()),
            'panes': pane_state, 'nodes': nodes, 'boxes': boxes, 'notes': notes,
            'active_window': app.activeWindow(), 'focus_widget': app.focusWidget(),
            'foreground_window': foreground(),
            'idle_callbacks': tuple(hou.ui.eventLoopCallbacks()) if hou.applicationVersion()[0] == 22 else ()}

    def shot(node, label, **kwargs):
        if os.environ.get('DSH_UI_CAPTURE_NARROW') == '1':
            kwargs['width'] = min(kwargs.get('width', 820), 420)
            kwargs['height'] = min(kwargs.get('height', 720), 720)
        state['queued_shots'].append((node, label, kwargs))
        state['pending'] += 1
        if not state['shot_running']:
            start_next_shot()

    def start_next_shot():
        node, label, kwargs = state['queued_shots'].pop(0)
        state['shot_running'] = True
        before = snapshot()
        try:
            prepared = capture.prepare_ui_capture(node, label + '.png', **kwargs)
        except BaseException:
            after = snapshot()
            differences = {key: {'before': repr(before[key]), 'after': repr(after[key])} for key in before if before[key] != after[key]}
            (output / (label + '-differences.json')).write_text(json.dumps(differences, ensure_ascii=False, indent=2), encoding='utf-8')
            raise
        deadline = time.monotonic() + 10
        bound = False
        def complete():
            nonlocal bound
            if not prepared['ready'].is_set() and time.monotonic() < deadline:
                QtCore.QTimer.singleShot(50, complete)
                return
            try:
                if not bound:
                    capture.refresh_ui_capture(prepared)
                    bound = True
                    QtCore.QTimer.singleShot(50, complete)
                    return
                result = capture.finish_ui_capture(prepared)
                assert result['ok'] and result['user_state_restored'], result
                after = snapshot()
                if after != before:
                    differences = {key: {'before': repr(before[key]), 'after': repr(after[key])} for key in before if before[key] != after[key]}
                    (output / (label + '-differences.json')).write_text(json.dumps(differences, ensure_ascii=False, indent=2), encoding='utf-8')
                    if active_fixture or set(differences) - {'active_window', 'focus_widget'}:
                        raise AssertionError('capture changed scene or existing panes: ' + ', '.join(differences))
                    state['inactive_qt_fallback'] = differences
                assert result['semantic_status'] == 'unverified' and result['scene_writes'] == 0
                assert all(abs(actual - requested) <= 2 for actual, requested in zip(result['actual_size'], result['requested_size'])), result
                assert not Path(result['path'] + '.reserve').exists(), 'capture reservation was not released'
                assert os.path.abspath(result['path']) in helpers._PRODUCED_IMAGES
                if result['view'] == 'parameters':
                    assert result['parameter_dialog_displayed'] and result['visible_parameter_count'] > 0, result
                if label == 'shape-detail-ramp':
                    assert 'detail_mode' in result['visible_parameter_names'] and 'profile_ramp' in result['visible_parameter_names'], result
                if label.startswith('artist-'):
                    expected = 'attribute_name' if label == 'artist-attribute-820' else 'amount'
                    assert expected in result['visible_parameter_names'], result
                state['captures'].append(result)
            except BaseException as error:
                finish({'ok': False, 'step': state['step'], 'error': str(error), 'traceback': traceback.format_exc(),
                    'captures': state['captures'], 'failures': state['failures']})
            finally:
                if prepared.get('closed'):
                    state['pending'] -= 1
                    state['shot_running'] = False
                    if state['queued_shots']:
                        state['shot_running'] = True
                        QtCore.QTimer.singleShot(0, start_next_shot)
        QtCore.QTimer.singleShot(250, complete)

    def failure(label, func):
        before = snapshot()
        try:
            func()
            raise AssertionError('invalid capture unexpectedly succeeded: ' + label)
        except (ValueError, helpers.CheckpointError) as error:
            state['failures'].append({'case': label, 'error': str(error), 'evidence': getattr(error, 'evidence', None)})
        after = snapshot()
        differences = {key: {'before': repr(before[key]), 'after': repr(after[key])} for key in before if before[key] != after[key]}
        if differences:
            (output / (label + '-differences.json')).write_text(json.dumps(differences, ensure_ascii=False, indent=2), encoding='utf-8')
            if active_fixture or set(differences) - {'active_window', 'focus_widget'}:
                raise AssertionError('failed capture changed scene or existing panes: ' + label + ': ' + ', '.join(differences))

    def finish(result):
        timer.stop()
        (output / 'ui-capture-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    def advance():
        try:
            if state['pending']:
                return
            if state['step'] == 0:
                spec = importlib.util.spec_from_file_location('capture_gallery', ROOT / 'skills/houdini-parameter-ui/scripts/build-ui-gallery.py')
                gallery = importlib.util.module_from_spec(spec); spec.loader.exec_module(gallery)
                state['gallery'] = gallery.build(output / 'gallery')
                state['artist'] = hou.node(state['gallery']['nodes']['artist_controls'])
                state['shape'] = hou.node(state['gallery']['nodes']['shape_controls'])
                state['geo'] = hou.node('/obj').createNode('geo', 'handoff_capture')
                original = state['geo'].createNode('box', 'original_box')
                original.parm('sizex').setKeyframe(hou.Keyframe(2.5, 1))
                original.parm('sizex').setKeyframe(hou.Keyframe(3.5, 24))
                result = state['geo'].createNode('null', 'OUT_result'); result.setInput(0, original)
                original.setPosition((0, 0)); result.setPosition((0, -2))
                box = state['geo'].createNetworkBox('delivery'); box.setComment('可编辑交付 / 操作入口')
                box.addItem(original); box.addItem(result); box.fitAroundContents()
                note = state['geo'].createStickyNote('usage'); note.setText('从 original_box 调整尺寸\nOUT_result 是最终输出')
                note.setPosition((3, 0)); note.setSize((4.5, 2))
                note.setTextSize(.25)
                original.setSelected(True, clear_all_selected=True); hou.setFrame(13)
                existing_parm = hou.ui.paneTabOfType(hou.paneTabType.Parm)
                existing_parm.setPin(True); existing_parm.setCurrentNode(original)
                existing_network = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
                existing_network.setPin(True); existing_network.setPwd(state['geo'])
                state['original'] = original
                string_probe = state['geo'].createNode('null', 'string_pixel_probe')
                string_probe.setPosition((-4, 0))
                string_probe.addSpareParmTuple(hou.StringParmTemplate(
                    'capture_text', 'Display Text', 1, default_value=('ALPHA_1111',)))
                state['string_probe'] = string_probe
                hou.hipFile.save(str(output / 'fixture.hip'))
                state['focus_dialog'] = QtWidgets.QDialog(hou.qt.mainWindow())
                if exposed_fixture:
                    main_window = hou.qt.mainWindow()
                    main_window.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
                    main_window.showNormal(); main_window.move(30, 30); main_window.resize(1100, 900)
                state['focus_dialog'].setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
                state['focus_dialog'].move(13000, 13000)
                state['focus_edit'] = QtWidgets.QLineEdit('original draft', state['focus_dialog'])
                QtWidgets.QVBoxLayout(state['focus_dialog']).addWidget(state['focus_edit'])
                state['focus_dialog'].show()
            elif state['step'] == 1:
                state['focus_edit'].clearFocus()
                QtWidgets.QApplication.setActiveWindow(None)
                shot(state['artist'], 'artist-820', width=820, height=1100)
                shot(state['artist'], 'artist-420', width=420, height=1100)
                assert state['artist'].parm('amount').isHidden() is False
                assert state['artist'].parm('attribute_name').isHidden() is True
                assert state['artist'].parm('texture_file').isHidden() is True
            elif state['step'] == 2:
                state['artist'].parm('value_source').set(1)
                state['artist'].parm('region_enabled1').set(0)
                state['artist'].updateParmStates()
                shot(state['artist'], 'artist-attribute-820', width=820, height=1100)
                assert state['artist'].parm('amount').isHidden()
                assert not state['artist'].parm('attribute_name').isHidden()
                assert state['artist'].parm('texture_file').isHidden()
                assert state['artist'].parm('region_weight1').isDisabled()
                shot(state['shape'], 'shape-general', width=820, height=920)
            elif state['step'] == 3:
                page = next(p for p in state['shape'].parms() if p.parmTemplate().type() == hou.parmTemplateType.FolderSet
                    and 'Detail' in p.parmTemplate().folderNames())
                page.set(1)
                state['shape'].parm('profile_enabled').set(1)
                state['shape'].updateParmStates()
                shot(state['shape'], 'shape-detail-ramp', width=820, height=1100)
                shot(state['geo'], 'network-820', view='network', width=820, height=720)
                shot(state['geo'], 'network-420', view='network', width=420, height=720)
            elif state['step'] == 4:
                failure('invalid_target', lambda: capture.prepare_ui_capture('/obj/no_capture_node'))
                failure('network_leaf', lambda: capture.prepare_ui_capture(state['original'], view='network'))
                failure('invalid_view', lambda: capture.prepare_ui_capture(state['original'], view='viewport'))
                failure('invalid_size', lambda: capture.prepare_ui_capture(state['original'], width=True))
                failure('repository_output', lambda: capture.prepare_ui_capture(state['original'], str(ROOT / 'capture.png'), output_policy='explicit'))
                failure('invalid_managed_path', lambda: capture.prepare_ui_capture(state['original'], '../capture.png'))
                failure('unsupported_format', lambda: capture.prepare_ui_capture(state['original'], 'capture.jpg'))
                old_restore = capture._restore_navigation
                # A post-pane-construction failure must close only the owned
                # pane and release its shared allocation reservation.
                def injected_failure(snapshot):
                    return old_restore(snapshot) + ['injected navigation recovery failure']
                capture._restore_navigation = injected_failure
                try:
                    failure('native_recovery_failure', lambda: capture.prepare_ui_capture(state['geo'], 'fail-widget.png', view='network'))
                finally:
                    capture._restore_navigation = old_restore
                assert not list((output / 'dsh-visual-checks').rglob('*.reserve'))
                # Native non-node selection must survive as well as nodes.
                note = state['geo'].stickyNotes()[0]; box = state['geo'].networkBoxes()[0]
                note.setSelected(True); box.setSelected(True)
                state['original'].setCurrent(True)
                shot(state['artist'], 'multi-item-selection', width=820, height=1100)
            elif state['step'] == 5:
                note = state['geo'].stickyNotes()[0]; box = state['geo'].networkBoxes()[0]
                assert note.isSelected() and box.isSelected() and state['original'].isCurrent()
                for item in hou.selectedItems():
                    item.setSelected(False)
                existing_parm = hou.ui.paneTabOfType(hou.paneTabType.Parm)
                error = hou.hscript('pane -H ' + capture._hscript_literal(state['geo'].path() + '/') + ' ' + capture._hscript_literal(existing_parm.name()))[1]
                assert not error, error
                empty_pane_current = existing_parm.currentNode()
                shot(state['artist'], 'no-selection', width=820, height=1100)
                state['empty_pane'] = existing_parm; state['empty_pane_current'] = empty_pane_current
            elif state['step'] == 6:
                existing_parm = state['empty_pane']; empty_pane_current = state['empty_pane_current']
                assert not hou.selectedItems() and existing_parm.currentNode() == empty_pane_current
                failure('premature_finish', lambda: capture.finish_ui_capture(capture.prepare_ui_capture(state['artist'], 'premature.png')))
                prepared = capture.prepare_ui_capture(state['artist'], 'aborted.png')
                aborted = capture.abort_ui_capture(prepared)
                assert aborted['phase'] == 'aborted' and not Path(prepared['destination']).exists()
                if hou.applicationVersion()[0] in (21, 22):
                    # QScreen samples a window's screen region. A different
                    # owned test window over that region must be rejected,
                    # without capturing or touching any external application.
                    covered = capture.prepare_ui_capture(state['artist'], 'covered.png')
                    target_window = covered['widget']
                    overlay = QtWidgets.QDialog(hou.qt.mainWindow())
                    overlay.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
                    overlay.resize(240, 160)
                    overlay.move(target_window.mapToGlobal(QtCore.QPoint(40, 80)))
                    overlay.show(); capture._show_owned_window_without_activation(overlay)
                    try:
                        try:
                            capture._require_uncovered_native_window(target_window)
                            raise AssertionError('native capture accepted an overlying window')
                        except RuntimeError as error:
                            assert 'covered by another window' in str(error), str(error)
                            state['failures'].append({'case': 'owned_overlay', 'error': str(error)})
                        assert not Path(covered['destination']).exists()
                    finally:
                        overlay.hide(); overlay.close(); overlay.deleteLater()
                        capture.abort_ui_capture(covered)
                assert not list((output / 'dsh-visual-checks').rglob('*.reserve'))
                state['post_capture'] = snapshot()
                server = bridge.start(port=0)
                port, node_path = server.server_port, state['shape'].path()
                state['http_response'] = None
                def http_worker():
                    def request(path, body=None):
                        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=20)
                        connection.request('GET' if body is None else 'POST', path,
                            body=None if body is None else json.dumps(body), headers={'Content-Type': 'application/json'})
                        response = connection.getresponse(); data = json.loads(response.read()); connection.close()
                        assert response.status == 200, data
                        return data
                    try:
                        owner = 'native-capture-http-fixture'
                        health = request('/health')
                        ticket = request('/requests/prepare', {'owner_session': owner})['requestRef']
                        body = {'node': node_path, 'path': 'http-detail.png',
                            'width': 420 if os.environ.get('DSH_UI_CAPTURE_NARROW') == '1' else 820,
                            'height': 720 if os.environ.get('DSH_UI_CAPTURE_NARROW') == '1' else 1100,
                            'owner_session': owner, 'owner_call': 'actual-queue-capture', 'request_ref': ticket,
                            'expected_contract': {'version': health['executionContractVersion'], 'hash': health['verbCatalog']['hash']}}
                        first = request('/ui/capture', body)
                        assert first['ok'], first.get('error')
                        repeat = request('/ui/capture', body)
                        assert repeat == first, 'repeating admitted ticket recaptured or changed original facts'
                        receipt = request('/requests/status', {'owner_session': owner, 'request_ref': ticket})['requestReceipt']
                        assert receipt['status'] == 'done' and receipt['result'] == first
                        state['http_response'] = first
                    except BaseException:
                        state['http_response'] = {'ok': False, 'error': traceback.format_exc()}
                state['http_thread'] = threading.Thread(target=http_worker, daemon=True)
                state['http_thread'].start()
            elif state['step'] == 7:
                if state['http_response'] is None:
                    return
                http_result = state['http_response']
                assert http_result['ok'], http_result.get('error')
                assert http_result['images'] == [os.path.abspath(http_result['result']['path'])], http_result
                assert http_result['artifactCandidates'][0]['source'] == 'ui_capture'
                assert http_result['result']['semantic_status'] == 'unverified'
                assert 'detail_mode' in http_result['result']['visible_parameter_names']
                assert 'profile_ramp' in http_result['result']['visible_parameter_names']
                bridge.stop()
            elif state['step'] == 8:
                parm = state['string_probe'].parm('capture_text')
                parm.set('ALPHA_1111')
                state['string_before_value'] = parm.evalAsString()
                state['string_other_parameters'] = {p.name(): p.rawValue() for p in state['string_probe'].parms() if p.name() != 'capture_text'}
                shot(state['string_probe'], 'string-value-A', width=420, height=420)
            elif state['step'] == 9:
                parm = state['string_probe'].parm('capture_text')
                assert parm.evalAsString() == 'ALPHA_1111'
                parm.set('OMEGA_8888')
                state['string_after_value'] = parm.evalAsString()
                assert {p.name(): p.rawValue() for p in state['string_probe'].parms() if p.name() != 'capture_text'} == state['string_other_parameters']
                shot(state['string_probe'], 'string-value-B', width=420, height=420)
            elif state['step'] == 10:
                result_a = next(c for c in state['captures'] if Path(c['path']).name.startswith('string-value-A_'))
                result_b = next(c for c in state['captures'] if Path(c['path']).name.startswith('string-value-B_'))
                image_a, image_b = QtGui.QImage(result_a['path']), QtGui.QImage(result_b['path'])
                assert not image_a.isNull() and not image_b.isNull()
                # The fixed node/interface/frame/layout are identical. Strip
                # the pane title/navigation/type bars; only the string value
                # changes in this parameter body, with no mode/hidden change.
                assert result_a['device_pixel_ratio'] == result_b['device_pixel_ratio']
                top = round(140 * result_a['device_pixel_ratio'])
                width = min(image_a.width(), image_b.width())
                height = min(image_a.height(), image_b.height())
                assert top < height
                changed = sum(image_a.pixel(x, y) != image_b.pixel(x, y)
                    for y in range(top, height) for x in range(width))
                check = {'before_value': state['string_before_value'], 'after_value': state['string_after_value'],
                    'before_path': result_a['path'], 'after_path': result_b['path'],
                    'node': state['string_probe'].path(), 'parameter': 'capture_text',
                    'body_region_pixels': [0, top, width, height - top], 'changed_pixels': changed,
                    'other_parameters_unchanged': True,
                    'scope': 'same native panel body; only one short string value changes; title/navigation excluded'}
                state['string_display_pixel_check'] = check
                (output / 'string-display-pixel-check.json').write_text(json.dumps(check, ensure_ascii=False, indent=2), encoding='utf-8')
                assert check['before_value'] == 'ALPHA_1111' and check['after_value'] == 'OMEGA_8888'
                assert changed >= 32, 'string display is stale: A/B parameter-body pixels did not change: ' + repr(check)
                state['post_capture'] = snapshot()
            else:
                after = snapshot()
                if after != state['post_capture']:
                    differences = {key: {'before': repr(state['post_capture'][key]), 'after': repr(after[key])} for key in after if state['post_capture'][key] != after[key]}
                    (output / 'outer-loop-differences.json').write_text(json.dumps(differences, ensure_ascii=False, indent=2), encoding='utf-8')
                    if active_fixture or set(differences) - {'active_window', 'focus_widget'}:
                        raise AssertionError('state changed after returning to outer GUI loop: ' + ', '.join(differences))
                    state['qt_close_fallback'] = differences['active_window']
                remaining = []
                for p in hou.ui.paneTabs():
                    if p.name().startswith('__dsh_ui_capture_'):
                        panel = p.floatingPanel(); widget = panel.qtParentWindow() if panel else None
                        remaining.append({'name': p.name(), 'window_visible': widget.isVisible() if widget else None})
                assert not remaining, 'owned native pane leaked after outer GUI tick: ' + repr(remaining)
                assert state['focus_edit'].text() == 'original draft'
                finish({'ok': True, 'houdini': hou.applicationVersionString(), 'captures': state['captures'],
                    'failures': state['failures'], 'focus_preserved': True if active_fixture else None, 'active_fixture': active_fixture,
                    'foreground_preserved': True, 'qt_active_window_native_close_fallback': state.get('qt_close_fallback'),
                    'inactive_qt_logical_fallback': state.get('inactive_qt_fallback'),
                    'http_result': state['http_response'], 'http_ticket_repeat_preserves_original_result': True,
                    'string_display_pixel_check': state['string_display_pixel_check'],
                    'private_panes_disposed_after_outer_loop': True,
                    'scope': 'staged main-thread capture across outer GUI loop; native rendering/target/files, frame/selection/parameters/panes/boxes/notes preserved',
                    'unverified': ['model semantic image interpretation', 'arbitrary UI design quality', 'physical mouse/key interactions']})
                return
            state['step'] += 1
        except BaseException as error:
            finish({'ok': False, 'step': state['step'], 'error': str(error), 'traceback': traceback.format_exc(),
                'captures': state['captures'], 'failures': state['failures']})
    timer.timeout.connect(advance); timer.start(1200)


def main():
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--houdini', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--exposed', action='store_true', help='initialize the owned native GUI visibly without requesting foreground')
    parser.add_argument('--narrow', action='store_true', help='use a 420px region when verifying a visible raster capture on a busy desktop')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT) or output.exists() and any(output.iterdir()):
        parser.error('--output must be an empty directory outside the repository')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dsh-capture-gui-') as temp:
        source_spec = importlib.util.spec_from_file_location('source_gui_job', ROOT / 'tools/tests/dsh-source-webview.test.py')
        source_gui = importlib.util.module_from_spec(source_spec); source_spec.loader.exec_module(source_gui)
        job = source_gui.GuiProcessJob()
        env = isolated_environment(temp, executable=args.houdini, gui=True)
        script = f"import runpy\nrunpy.run_path({str(Path(__file__).resolve())!r})['probe']()\n"
        for major, version in (('21.0', '3.11'), ('22.0', '3.13')):
            prefs = Path(env['HOUDINI_USER_PREF_DIR'].replace('__HVER__', major))
            hook = prefs / f'python{version}libs/uiready.py'; hook.parent.mkdir(parents=True)
            hook.write_text(script, encoding='utf-8')
        env['DSH_UI_CAPTURE_OUTPUT'] = str(output)
        env['DSH_UI_CAPTURE_EXPOSED'] = '1' if args.exposed else '0'
        env['DSH_UI_CAPTURE_NARROW'] = '1' if args.narrow else '0'
        info = subprocess.STARTUPINFO(); info.dwFlags |= subprocess.STARTF_USESHOWWINDOW; info.wShowWindow = 4 if args.exposed else 0
        with (output / 'gui-process.log').open('w', encoding='utf-8') as log:
            geometry = '-geometry=1100x900+30+30' if args.exposed else '-geometry=1100x900+12000+12000'
            process = subprocess.Popen([str(args.houdini.resolve()), '-foreground', geometry],
                cwd=launch_directory(args.houdini), env=env, stdout=log, stderr=log, startupinfo=info)
            job.assign(process)
            try:
                deadline = time.monotonic() + 120
                while process.poll() is None and not (output / 'ui-capture-result.json').exists() and time.monotonic() < deadline:
                    time.sleep(.2)
            finally:
                cleanup = job.close()
                process.wait(timeout=20)
        result_path = output / 'ui-capture-result.json'
        result = json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else {'ok': False, 'error': 'no GUI report'}
        result['gui_process_tree'] = cleanup
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'ok': result['ok'], 'houdini': result.get('houdini'), 'error': result.get('error'),
            'report': str(result_path), 'capture_count': len(result.get('captures', [])), 'exit_code': process.returncode}, ensure_ascii=False))
        if not result['ok']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
