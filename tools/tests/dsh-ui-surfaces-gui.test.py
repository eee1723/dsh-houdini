"""Existing pane/window discovery and precise capture in disposable GUI workers.

Each native pane shares a parent with other panes: image dimensions and native
rectangle identity must match the selected pane, not the whole parent. Qt
dialog text is changed between captures to detect stale framebuffers. Tests
never connect to or alter a user's Houdini process.
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
import time
import traceback
import threading
import http.client

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, launch_directory, reexec_unpacked_test_cli


def present_owned_fixture_window(widget):
    """Fixture setup only: expose its own window without foreground activation."""
    import ctypes
    from ctypes import wintypes as w
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.SetWindowPos.argtypes = [w.HWND,w.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.UINT]
    api.SetWindowPos.restype = w.BOOL
    assert api.SetWindowPos(int(widget.effectiveWinId()),None,0,0,0,0,0x0013)


def dismiss_owned_startup_dialogs():
    """Fixture setup: ordinarily close only this worker's native welcome UI."""
    import ctypes
    from ctypes import wintypes as w
    api=ctypes.WinDLL('user32',use_last_error=True)
    callback_type=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    api.EnumWindows.argtypes=[callback_type,w.LPARAM]; api.EnumWindows.restype=w.BOOL
    api.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]; api.GetWindowThreadProcessId.restype=w.DWORD
    api.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]; api.GetWindowTextW.restype=ctypes.c_int
    api.IsWindowVisible.argtypes=[w.HWND]; api.IsWindowVisible.restype=w.BOOL
    api.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]; api.PostMessageW.restype=w.BOOL
    dismissed,errors=[],[]
    def visit(handle,_):
        pid=w.DWORD(); api.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        if pid.value != os.getpid() or not api.IsWindowVisible(handle):
            return True
        title=ctypes.create_unicode_buffer(512); api.GetWindowTextW(handle,title,512)
        if title.value == 'Python Callback Error':
            errors.append('owned worker has a native Python Callback Error; fixture must not hide it')
        elif title.value in ('Start Here','Anonymous Usage Statistics'):
            if api.PostMessageW(handle,0x0010,0,0):  # WM_CLOSE, no prefs/permission choice.
                dismissed.append(title.value)
            else:
                errors.append('owned startup window did not accept normal close')
        return True
    callback=callback_type(visit)
    if not api.EnumWindows(callback,0):
        raise RuntimeError('owned startup window enumeration failed')
    if errors:
        raise RuntimeError('; '.join(errors))
    return dismissed


def probe():
    import hou
    from hutil.Qt import QtCore, QtGui, QtWidgets, QtCompat
    sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
    import dsh_ui_capture as capture
    import dsh_hou_helpers as helpers
    import dsh_bridge as bridge
    output = Path(os.environ['DSH_UI_SURFACES_OUTPUT'])
    app = QtWidgets.QApplication.instance()
    state = {'step': 0, 'captures': [], 'failures': [], 'busy': False}
    only_size_shadow = os.environ.get('DSH_UI_SURFACES_SIZE_SHADOW_ONLY') == '1'
    timer = QtCore.QTimer(hou.qt.mainWindow())
    import ctypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    foreground = user32.GetForegroundWindow
    foreground.argtypes = []; foreground.restype = ctypes.c_void_p

    def snapshot():
        pane_state = [(p.name(), str(p.type()), p.isCurrentTab(), _node(p.currentNode()), _node(p.pwd()), p.isPin())
            for p in hou.ui.paneTabs() if isinstance(p, hou.PathBasedPaneTab)]
        window_state = sorted((QtCompat.getCppPointer(w), w.isVisible(), _rect(w.geometry()), int(w.windowFlags())) for w in app.topLevelWidgets())
        return (hou.hipFile.path(), hou.hipFile.hasUnsavedChanges(), hou.frame(),
            tuple(n.path() for n in hou.selectedNodes()), pane_state, window_state,
            app.activeWindow(), app.focusWidget(), foreground(),
            state['edit'].text() if QtCompat.isValid(state['edit']) else '<closed>', state['geo'].asCode())

    def _node(n):
        return n.path() if n is not None else None

    def _rect(r):
        return [r.x(), r.y(), r.width(), r.height()]

    def finish(result):
        timer.stop()
        (output / 'ui-surfaces-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    def list_surfaces():
        before = snapshot()
        result = capture.discover_ui_surfaces()
        after = snapshot()
        assert before == after, 'discovery changed scene or UI: ' + repr([(i, repr(a), repr(b)) for i,(a,b) in enumerate(zip(before,after)) if a != b])
        assert result['runtime_id'] == bridge._RUNTIME_ID and result['scene_writes'] == 0
        (output / ('surfaces-%d.json' % state['step'])).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return result['surfaces']

    def row_for_pane(pane):
        rows = [r for r in list_surfaces() if r.get('label') == pane.name() and r['kind'] == 'pane']
        assert len(rows) == 1, (pane.name(), rows)
        return rows[0]

    def shot(row, label, callback=None):
        assert row['supported'], row
        before = snapshot()
        prepared = capture.prepare_ui_capture(target=row['target'], path=label + '.png')
        state['busy'] = True
        bound = False
        deadline = time.monotonic() + 10
        def complete():
            nonlocal bound
            try:
                if not prepared['ready'].is_set():
                    assert time.monotonic() < deadline, 'drawing did not settle'
                    QtCore.QTimer.singleShot(50, complete)
                    return
                if not bound:
                    capture.refresh_ui_capture(prepared)
                    bound = True
                    QtCore.QTimer.singleShot(100, complete)
                    return
                result = capture.finish_ui_capture(prepared)
                assert result['ok'] and result['view'] == 'existing' and result['capture_method'] == 'native_surface_region', result
                assert result['surface']['target'] == row['target'] and result['semantic_status'] == 'unverified'
                assert result['actual_size'] == row['screen_geometry'][2:], result
                assert result['cleanup_pending'] is False and not Path(result['path'] + '.reserve').exists()
                assert os.path.abspath(result['path']) in helpers._PRODUCED_IMAGES
                after = snapshot()
                if before != after:
                    raise AssertionError('borrowed capture changed UI/scene: ' + repr([(i, repr(a), repr(b)) for i, (a,b) in enumerate(zip(before,after)) if a != b]))
                if QtCompat.isValid(state['dialog']):
                    assert state['dialog'].isVisible() and state['dialog'].isEnabled()
                state['captures'].append(result)
                if callback:
                    callback(result)
                state['busy'] = False
            except BaseException as error:
                if not prepared.get('closed'):
                    capture.abort_ui_capture(prepared)
                finish({'ok': False, 'step': state['step'], 'error': str(error), 'traceback': traceback.format_exc(),
                    'captures': state['captures'], 'failures': state['failures']})
        QtCore.QTimer.singleShot(150, complete)

    def expect_failure(label, func, phrase):
        before = snapshot()
        try:
            func()
            raise AssertionError('accepted invalid UI target: ' + label)
        except (ValueError, RuntimeError, helpers.CheckpointError) as error:
            assert phrase in str(error), (label, str(error))
            state['failures'].append({'case': label, 'error': str(error)})
        assert before == snapshot(), 'invalid target changed UI/scene: ' + label

    def advance():
        if state['busy']:
            return
        try:
            if state['step'] == 0:
                main = hou.qt.mainWindow()
                main.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
                main.showNormal(); main.move(20, 20); main.resize(1000, 800)
                present_owned_fixture_window(main)
                geo = hou.node('/obj').createNode('geo', 'existing_surface_fixture')
                box = geo.createNode('box', 'Box_Edit_Here'); box.parm('sizex').set(3.25)
                box.setSelected(True, clear_all_selected=True); hou.setFrame(13)
                parm = hou.ui.paneTabOfType(hou.paneTabType.Parm); parm.setPin(True); parm.setCurrentNode(box)
                net = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor); net.setPin(True); net.setPwd(geo)
                state.update(geo=geo, box=box, parm=parm, net=net,
                    scene=hou.ui.paneTabOfType(hou.paneTabType.SceneViewer))
                dialog = QtWidgets.QDialog(main); dialog.setObjectName('dsh_capture_dialog_fixture')
                dialog.setWindowTitle('Surface Fixture'); dialog.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
                layout = QtWidgets.QVBoxLayout(dialog)
                layout.addWidget(QtWidgets.QLabel('Editable Batch Tool / 可编辑工具'))
                edit = QtWidgets.QLineEdit('ALPHA_1111'); edit.setObjectName('draft'); layout.addWidget(edit)
                layout.addWidget(QtWidgets.QPushButton('Apply to Selected Nodes'))
                # Real authoring boundary: an instance control named ``size``
                # shadows QWidget.size without changing its native geometry.
                dialog.size = QtWidgets.QDoubleSpinBox(dialog)
                dialog.size.setObjectName('size_control_shadow')
                layout.addWidget(dialog.size)
                dialog.resize(430, 220); dialog.move(1260, 40); dialog.show()
                present_owned_fixture_window(dialog)
                state.update(dialog=dialog, edit=edit)
                state['parent_window_size'] = [main.width(), main.height()]
                # H21's GUI event marshalling parses Windows backslashes in
                # callback kwargs as Python escapes. Use HOM's portable path.
                hou.hipFile.save((output / 'fixture.hip').as_posix())
            elif state['step'] == 1:
                # H22's native pane owner may differ from hou.qt.mainWindow's
                # wrapper. Present only this fixture's actual native window.
                native_parent = state['parm'].qtParentWindow()
                dismissed=dismiss_owned_startup_dialogs()
                if dismissed:
                    state.setdefault('startup_dismissed_titles',[]).extend(dismissed)
                    return  # Process ordinary own-window closes at the outer GUI loop.
                present_owned_fixture_window(native_parent)
                (output / 'parent-identities.json').write_text(json.dumps({
                    'main': QtCompat.getCppPointer(hou.qt.mainWindow()),
                    'pane_parent': QtCompat.getCppPointer(native_parent),
                    'main_rect': _rect(hou.qt.mainWindow().geometry()),
                    'parent_rect': _rect(native_parent.geometry())}, indent=2), encoding='utf-8')
                surfaces = list_surfaces()
                if only_size_shadow:
                    row=next(r for r in surfaces if r.get('object_name') == 'dsh_capture_dialog_fixture')
                    assert isinstance(state['dialog'].size, QtWidgets.QDoubleSpinBox)
                    actual=QtWidgets.QWidget.size(state['dialog'])
                    assert row['screen_geometry'][2:] == [actual.width(),actual.height()]
                    def finish_shadow(result):
                        finish({'ok':True,'houdini':hou.applicationVersionString(),'captures':state['captures'],
                            'qt_size_attribute_shadow_preserves_native_geometry':True,
                            'scope':'one observed Qt size attribute shadow: discovery and capture use native QWidget geometry; scene/UI/foreground preserved by snapshot',
                            'unverified':['model semantic image interpretation']})
                    shot(row,'qt-size-shadow',finish_shadow)
                    return
                assert not any(r['kind'] == 'qt_window' and r['label'] == hou.qt.mainWindow().windowTitle() for r in surfaces)
                row = row_for_pane(state['parm']); state['parm_ref'] = row['target']
                assert row['screen_geometry'][2:] != state['parent_window_size']
                assert row['node'] == state['box'].path()
                shot(row, 'existing-parameters')
            elif state['step'] == 2:
                shot(row_for_pane(state['net']), 'existing-network')
            elif state['step'] == 3:
                shot(row_for_pane(state['scene']), 'existing-scene')
            elif state['step'] == 4:
                # Replace only our fixture network tab with a native spreadsheet.
                name = state['net'].name()
                state['net'].setType(hou.paneTabType.DetailsView)
                state['details'] = hou.ui.findPaneTab(name)
                state['details'].setCurrentNode(state['box'])
            elif state['step'] == 5:
                row = row_for_pane(state['details'])
                assert row['pane_type'] == 'DetailsView', row
                shot(row, 'existing-spreadsheet')
            elif state['step'] == 6:
                rows = [r for r in list_surfaces() if r.get('object_name') == 'dsh_capture_dialog_fixture']
                assert len(rows) == 1 and rows[0]['kind'] == 'qt_window', rows
                assert isinstance(state['dialog'].size, QtWidgets.QDoubleSpinBox)
                actual = QtWidgets.QWidget.size(state['dialog'])
                assert rows[0]['screen_geometry'][2:] == [actual.width(), actual.height()]
                state['dialog_ref'] = rows[0]['target']
                shot(rows[0], 'existing-qt-A')
            elif state['step'] == 7:
                state['edit'].setText('OMEGA_8888')
            elif state['step'] == 8:
                row = next(r for r in list_surfaces() if r['target'] == state['dialog_ref'])
                shot(row, 'existing-qt-B')
            elif state['step'] == 9:
                a, b = state['captures'][-2:]
                ia, ib = QtGui.QImage(a['path']), QtGui.QImage(b['path'])
                assert ia.size() == ib.size()
                # Crop the text field only: cursor and window title are excluded.
                origin = state['edit'].mapTo(state['dialog'], QtCore.QPoint(0, 0))
                ratio = a['device_pixel_ratio']; rect = state['edit'].rect()
                top = round((origin.y() + 3) * ratio); left = round((origin.x() + 4) * ratio)
                right = min(round((origin.x() + rect.width() - 10) * ratio), ia.width())
                bottom = min(round((origin.y() + rect.height() - 3) * ratio), ia.height())
                changed = sum(ia.pixel(x,y) != ib.pixel(x,y) for y in range(top,bottom) for x in range(left,right))
                assert changed >= 32, ('dialog stale pixels', changed)
                state['changed_text_pixels'] = changed
                expect_failure('forged_ref', lambda: capture.prepare_ui_capture(target='ui:invented'), 'no longer displayed')
                original_runtime = bridge._RUNTIME_ID
                bridge._RUNTIME_ID = original_runtime + '-new-fixture-runtime'
                try:
                    expect_failure('stale_runtime', lambda: capture.prepare_ui_capture(target=state['dialog_ref']), 'another runtime')
                finally:
                    bridge._RUNTIME_ID = original_runtime
                modal = QtWidgets.QDialog(hou.qt.mainWindow()); modal.setWindowTitle('Modal Fixture')
                modal.setObjectName('capture_modal_fixture'); modal.setModal(True)
                modal.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True); modal.move(1600, 40); modal.resize(200,100); modal.show()
                state['modal'] = modal
            elif state['step'] == 10:
                row = next(r for r in list_surfaces() if r.get('object_name') == 'capture_modal_fixture')
                assert not row['supported'] and row['modal'], row
                expect_failure('modal_unsupported', lambda: capture.prepare_ui_capture(target=row['target']), 'unverified')
                state['modal'].close(); state['modal'].deleteLater()
                hidden = state['parm'].pane().createTab(hou.paneTabType.NetworkEditor)
                state['hidden_replacement'] = hidden
            elif state['step'] == 11:
                assert not state['parm'].isCurrentTab()
                assert not any(r['target'] == state['parm_ref'] for r in list_surfaces())
                expect_failure('hidden_tab', lambda: capture.prepare_ui_capture(target=state['parm_ref']), 'no longer displayed')
                state['parm'].setIsCurrentTab()
                state['dialog'].hide()
            elif state['step'] == 12:
                expect_failure('hidden_window', lambda: capture.prepare_ui_capture(target=state['dialog_ref']), 'no longer displayed')
                state['dialog'].show(); present_owned_fixture_window(state['dialog'])
                overlay = QtWidgets.QDialog(hou.qt.mainWindow()); overlay.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
                overlay.setWindowTitle('Overlay Fixture'); overlay.resize(100,80)
                overlay.move(state['dialog'].mapToGlobal(QtCore.QPoint(40,60))); overlay.show()
                present_owned_fixture_window(overlay); state['overlay'] = overlay
            elif state['step'] == 13:
                row = next(r for r in list_surfaces() if r['target'] == state['dialog_ref'])
                assert not row['supported'] and 'covered' in row['reason'], row
                expect_failure('covered_window', lambda: capture.prepare_ui_capture(target=state['dialog_ref']), 'covered')
                state['overlay'].hide(); state['overlay'].close(); state['overlay'].deleteLater()
                # Reject a surface destroyed after request admission without
                # closing or otherwise changing any surviving user surface.
                state['deletion_prepared'] = capture.prepare_ui_capture(target=state['dialog_ref'], path='deleted.png')
                state['dialog'].close(); state['dialog'].deleteLater()
            elif state['step'] == 14:
                prepared = state['deletion_prepared']
                try:
                    capture.refresh_ui_capture(prepared)
                    raise AssertionError('deleted Qt surface was accepted')
                except ValueError as error:
                    assert 'closed' in str(error) or 'no longer' in str(error), str(error)
                    state['failures'].append({'case':'deleted_surface','error':str(error)})
                capture.abort_ui_capture(prepared)
                assert not Path(prepared['destination']).exists()
                assert not list((output / 'dsh-visual-checks').rglob('*.reserve'))
                name = state['details'].name()
                state['details'].setType(hou.paneTabType.PythonPanel)
                state['python_panel'] = hou.ui.findPaneTab(name)
                state['python_panel'].setActiveInterface(hou.pypanel.interfaces()['dsh_capture_python_panel'])
            elif state['step'] == 15:
                assert not state['python_panel'].activeInterfaceScriptErrors(), state['python_panel'].activeInterfaceScriptErrors()
                row = row_for_pane(state['python_panel'])
                assert row['pane_type'] == 'PythonPanel', row
                shot(row, 'existing-python-panel')
            elif state['step'] == 16:
                window = QtWidgets.QMainWindow(hou.qt.mainWindow(), QtCore.Qt.Window)
                window.setObjectName('capture_dock_window'); window.setWindowTitle('Dock Tool Fixture')
                window.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
                center = QtWidgets.QLabel('UNRELATED CENTER SHOULD NOT ENTER DOCK CAPTURE')
                center.setStyleSheet('background: #13776c; color: white;')
                window.setCentralWidget(center)
                dock = QtWidgets.QDockWidget('Batch Controls', window); dock.setObjectName('capture_dock_panel')
                controls = QtWidgets.QWidget(); controls.setStyleSheet('background: #fff2b3; color: black;')
                layout = QtWidgets.QVBoxLayout(controls); layout.addWidget(QtWidgets.QLabel('Selected Nodes / 当前选择'))
                layout.addWidget(QtWidgets.QPushButton('Preview Changes')); dock.setWidget(controls)
                window.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
                window.resize(560, 420); window.move(1260, 400); window.show()
                present_owned_fixture_window(window)
                # A valid blank custom panel is not a failed native bootstrap.
                blank = QtWidgets.QWidget(hou.qt.mainWindow(), QtCore.Qt.Window)
                blank.setObjectName('capture_blank_panel'); blank.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
                blank.setStyleSheet('background: #314159;'); blank.resize(120, 100); blank.move(1700, 40); blank.show()
                present_owned_fixture_window(blank)
                state.update(dock_window=window, dock=dock, blank=blank)
            elif state['step'] == 17:
                row = next(r for r in list_surfaces() if r.get('object_name') == 'capture_dock_panel')
                assert row['kind'] == 'qt_panel' and row['screen_geometry'][2:] != [state['dock_window'].width(),state['dock_window'].height()]
                shot(row, 'existing-qt-dock')
            elif state['step'] == 18:
                row = next(r for r in list_surfaces() if r.get('object_name') == 'capture_blank_panel')
                shot(row, 'existing-qt-blank')
            elif state['step'] == 19:
                dock_image = QtGui.QImage(next(c['path'] for c in state['captures'] if Path(c['path']).name.startswith('existing-qt-dock_')))
                center_color = QtGui.QColor('#13776c').rgb()
                assert not any(dock_image.pixel(x,y) == center_color for y in range(dock_image.height()) for x in range(dock_image.width())), 'dock capture includes unrelated central content'
                server = bridge.start(port=0)
                state['http_result'] = None
                state['before_http'] = snapshot()
                port = server.server_port
                def worker():
                    def request(path, body=None):
                        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=20)
                        try:
                            connection.request('GET' if body is None else 'POST', path,
                                body=json.dumps(body) if body is not None else None,
                                headers={'Content-Type':'application/json'})
                            response = connection.getresponse()
                            data = json.loads(response.read().decode('utf-8'))
                            assert response.status == 200, data
                            return data
                        finally:
                            connection.close()
                    try:
                        health = request('/health')
                        common = {'owner_session':'existing-ui-http-fixture',
                            'expected_contract':{'version':health['executionContractVersion'], 'hash':health['verbCatalog']['hash']}}
                        list_ticket = request('/requests/prepare', {'owner_session':common['owner_session']})['requestRef']
                        listing_body = {**common, 'owner_call':'discover', 'request_ref':list_ticket}
                        listing = request('/ui/list', listing_body)
                        (output / 'http-list.json').write_text(json.dumps(listing, ensure_ascii=False, indent=2), encoding='utf-8')
                        assert listing['ok'] and listing.get('images', []) == [], listing
                        assert request('/ui/list', listing_body) == listing
                        target = next(r['target'] for r in listing['result']['surfaces'] if r.get('object_name') == 'capture_dock_panel')
                        capture_ticket = request('/requests/prepare', {'owner_session':common['owner_session']})['requestRef']
                        body = {**common, 'target':target, 'path':'http-dock.png',
                            'owner_call':'observe', 'request_ref':capture_ticket}
                        result = request('/ui/capture', body)
                        (output / 'http-capture.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                        assert result['ok'], result
                        assert request('/ui/capture', body) == result, 'ticket repeat recaptured pixels'
                        receipt = request('/requests/status', {'owner_session':common['owner_session'], 'request_ref':body['request_ref']})['requestReceipt']
                        assert receipt['status'] == 'done' and receipt['result'] == result
                        state['http_result'] = {'listing':listing, 'capture':result, 'receipt':receipt}
                    except BaseException:
                        state['http_result'] = {'ok':False,'error':traceback.format_exc()}
                state['http_thread'] = threading.Thread(target=worker, daemon=True); state['http_thread'].start()
            else:
                if state['http_result'] is None:
                    return
                result = state['http_result']
                assert 'error' not in result, result
                assert state['before_http'] == snapshot(), 'HTTP observation changed user UI/scene'
                assert result['capture']['images'] == [os.path.abspath(result['capture']['result']['path'])]
                assert result['capture']['result']['capture_method'] == 'native_surface_region'
                bridge.stop()
                finish({'ok': True, 'houdini': hou.applicationVersionString(), 'captures': state['captures'],
                    'failures': state['failures'], 'changed_text_pixels': state['changed_text_pixels'],
                    'http_result': result, 'http_ticket_repeat_preserves_original_result': True, 'foreground_preserved': True,
                    'qt_size_attribute_shadow_preserves_native_geometry':True,
                    'fixture_setup': 'ordinary owned windows shown without activation; only own native Start Here/Anonymous Usage Statistics startup windows ordinarily dismissed before snapshots',
                    'own_startup_windows_dismissed':bool(state.get('startup_dismissed_titles')),
                    'own_startup_dismissed_titles':state.get('startup_dismissed_titles',[]),
                    'scope': 'existing parameter/network/SceneViewer/spreadsheet/PythonPanel, nonmodal Qt client/dock/blank; no borrowed UI mutation',
                    'unverified': ['model semantic interpretation', 'physical input', 'modal/native file chooser', 'arbitrary third-party GL widgets']})
                return
            state['step'] += 1
        except BaseException as error:
            finish({'ok': False, 'step': state['step'], 'error': str(error), 'traceback': traceback.format_exc(),
                'captures': state['captures'], 'failures': state['failures']})
    timer.timeout.connect(advance); timer.start(1000)


def main():
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--houdini', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--only-size-shadow',action='store_true',help='run the real observed QWidget.size attribute shadow regression only')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT) or output.exists() and any(output.iterdir()):
        parser.error('--output must be an empty directory outside the repository')
    output.mkdir(parents=True, exist_ok=True)
    source_spec = importlib.util.spec_from_file_location('source_gui_job', ROOT / 'tools/tests/dsh-source-webview.test.py')
    source_gui = importlib.util.module_from_spec(source_spec); source_spec.loader.exec_module(source_gui)
    with tempfile.TemporaryDirectory(prefix='dsh-ui-surfaces-') as temp:
        job = source_gui.GuiProcessJob()
        env = isolated_environment(temp, executable=args.houdini, gui=True)
        script = 'import runpy\nrunpy.run_path(%r)["probe"]()\n' % str(Path(__file__).resolve())
        for major, version in (('21.0', '3.11'), ('22.0', '3.13')):
            prefs = Path(env['HOUDINI_USER_PREF_DIR'].replace('__HVER__', major))
            hook = prefs / ('python%slibs/uiready.py' % version); hook.parent.mkdir(parents=True)
            hook.write_text(script, encoding='utf-8')
            panels = prefs / 'python_panels'; panels.mkdir()
            (panels / 'capture_fixture.pypanel').write_text('''<pythonPanelDocument><interface name="dsh_capture_python_panel" label="Capture Python Panel"><script><![CDATA[
from hutil.Qt import QtWidgets
def onCreateInterface():
    widget = QtWidgets.QWidget()
    widget.setObjectName("capture_python_panel_root")
    layout = QtWidgets.QVBoxLayout(widget)
    layout.addWidget(QtWidgets.QLabel("PYTHON PANEL / Editable Batch Tool"))
    layout.addWidget(QtWidgets.QPushButton("Preview Selected Nodes"))
    return widget
]]></script><includeInPaneTabMenu menu_position="700" create_separator="false"/></interface></pythonPanelDocument>''', encoding='utf-8')
        env['DSH_UI_SURFACES_OUTPUT'] = str(output)
        env['DSH_UI_SURFACES_SIZE_SHADOW_ONLY'] = '1' if args.only_size_shadow else '0'
        info = subprocess.STARTUPINFO(); info.dwFlags |= subprocess.STARTF_USESHOWWINDOW; info.wShowWindow = 4
        with (output / 'gui-process.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([str(args.houdini.resolve()), '-foreground', '-geometry=1000x800+20+20'],
                cwd=launch_directory(args.houdini), env=env, stdout=log, stderr=log, startupinfo=info)
            job.assign(process)
            try:
                deadline = time.monotonic() + 120
                while process.poll() is None and not (output / 'ui-surfaces-result.json').exists() and time.monotonic() < deadline:
                    time.sleep(.2)
            finally:
                cleanup = job.close(); process.wait(timeout=20)
        report = output / 'ui-surfaces-result.json'
        result = json.loads(report.read_text(encoding='utf-8')) if report.exists() else {'ok':False, 'error':'no GUI report'}
        result['gui_process_tree'] = cleanup
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'ok':result['ok'], 'houdini':result.get('houdini'), 'error':result.get('error'), 'report':str(report)}, ensure_ascii=False))
        if not result['ok']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
