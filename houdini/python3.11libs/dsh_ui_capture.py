"""Native UI capture across Houdini's ordinary outer GUI event loop.

The Bridge owns request admission and all main-thread queue entries. This
state lives only in that one admitted request; it is not a capture registry.
Only an explicitly discovered, currently displayed surface can be captured.
Capture does not create, navigate, select, resize or close a user interface.
"""
from __future__ import annotations

import os
import threading
import base64
import json

import hou


def _require_uncovered_native_window(widget, area=None):
    """QScreen reads a screen region: refuse other-window pixels before use.

    Qt's grabWindow contract includes overlapping windows. This check is
    specific to the verified Windows native pane backend, not a desktop grab.
    """
    import ctypes
    from ctypes import wintypes as w
    from hutil.Qt import QtCore, QtWidgets
    origin_qt = widget.mapToGlobal(QtCore.QPoint(0, 0))
    # Custom tools may use ``self.size`` for a control. Read the actual Qt
    # geometry through its base accessor instead of the Python instance name.
    client_qt = QtCore.QRect(origin_qt, QtWidgets.QWidget.size(widget))
    area = client_qt if area is None else area
    if area.isEmpty() or not client_qt.contains(area):
        raise RuntimeError('UI surface bounds are not inside its existing parent window')
    if not widget.screen().geometry().contains(area):
        raise RuntimeError('selected UI surface extends outside its screen; no capture performed')
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.GetAncestor.argtypes = [w.HWND, w.UINT]; api.GetAncestor.restype = w.HWND
    api.GetWindow.argtypes = [w.HWND, w.UINT]; api.GetWindow.restype = w.HWND
    api.IsWindowVisible.argtypes = [w.HWND]; api.IsWindowVisible.restype = w.BOOL
    api.IsIconic.argtypes = [w.HWND]; api.IsIconic.restype = w.BOOL
    api.GetClientRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]; api.GetClientRect.restype = w.BOOL
    api.ClientToScreen.argtypes = [w.HWND, ctypes.POINTER(w.POINT)]; api.ClientToScreen.restype = w.BOOL
    api.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]; api.GetWindowRect.restype = w.BOOL
    # Const getter: discovery/capture must not create native widgets or activate
    # the user's main window as QWidget.winId() can do for alien child widgets.
    handle = int(widget.effectiveWinId())
    if not handle:
        raise RuntimeError('UI surface has no existing native parent window')
    client = w.RECT(); origin = w.POINT(0, 0)
    if not api.GetClientRect(handle, ctypes.byref(client)) or not api.ClientToScreen(handle, ctypes.byref(origin)):
        raise RuntimeError('selected native parent window bounds unavailable')
    ratio = float(widget.screen().devicePixelRatio())
    left = origin.x + round((area.x() - origin_qt.x()) * ratio)
    top = origin.y + round((area.y() - origin_qt.y()) * ratio)
    right, bottom = left + round(area.width() * ratio), top + round(area.height() * ratio)
    root = api.GetAncestor(handle, 2)  # GA_ROOT
    if not root or not api.IsWindowVisible(root) or api.IsIconic(root):
        raise RuntimeError('selected UI parent window is not natively displayed')
    above = api.GetWindow(root, 3)  # GW_HWNDPREV: windows above this one
    visited = set()
    while above:
        if above in visited or len(visited) >= 256:
            raise RuntimeError('native window stacking could not be observed consistently')
        visited.add(above)
        if api.IsWindowVisible(above) and not api.IsIconic(above):
            rect = w.RECT()
            if not api.GetWindowRect(above, ctypes.byref(rect)):
                raise RuntimeError('visible overlay bounds unavailable; no UI capture performed')
            if max(left, rect.left) < min(right, rect.right) and max(top, rect.top) < min(bottom, rect.bottom):
                raise RuntimeError('native UI window is covered by another window; no overlapping pixels captured')
        above = api.GetWindow(above, 3)
    return {'status': 'uncovered_before_capture', 'scope': 'selected surface rectangle and observed visible windows above its parent'}


def _rect_data(rect):
    return [rect.x(), rect.y(), rect.width(), rect.height()]


def _surface_target(kind, identity):
    import dsh_bridge
    value = json.dumps([dsh_bridge._RUNTIME_ID, kind, *identity], separators=(',', ':'), ensure_ascii=True)
    return 'ui:' + base64.urlsafe_b64encode(value.encode('ascii')).decode('ascii').rstrip('=')


def _surface_rows():
    """Read actual pane/window identities; never resolve a title or wrap a pointer.

    References carry only identity, not desktop coordinates. Every use repeats
    discovery; holding Qt/HOM objects between request stages also detects a
    destroyed/replaced surface. Nothing is registered or written on widgets.
    """
    app, QtCore, _, QtWidgets = _gui()
    from hutil.Qt import QtCompat
    rows, native_parents = [], set()
    main = hou.qt.mainWindow()
    for pane in hou.ui.paneTabs():
        widget = pane.qtParentWindow()
        if widget is None or not QtCompat.isValid(widget) or not widget.isVisible() or widget.isMinimized():
            continue
        native_parents.add(QtCompat.getCppPointer(widget))
        if not pane.isCurrentTab():
            continue
        area = pane.qtScreenGeometry()
        pane_type = str(pane.type()).split('.')[-1]
        node = None
        current_node = network_path = None
        if isinstance(pane, hou.PathBasedPaneTab):
            current, parent = pane.currentNode(), pane.pwd()
            current_node = current.path() if current is not None else None
            network_path = parent.path() if parent is not None else None
            node = network_path if isinstance(pane, hou.NetworkEditor) else current_node or network_path
        record = {'target': _surface_target('pane', [hash(pane), pane.name(), pane_type, QtCompat.getCppPointer(widget)]),
            'kind': 'pane', 'label': pane.name(), 'pane_type': pane_type, 'node': node,
            'current_node': current_node, 'network_path': network_path,
            'screen_geometry': _rect_data(area), 'modal': False,
            'scope': 'current displayed pane, including its native toolbars; adjacent panes excluded'}
        rows.append((record, pane, widget, area))
    for widget in app.topLevelWidgets():
        if not QtCompat.isValid(widget) or not widget.isVisible() or widget.isMinimized():
            continue
        pointer = QtCompat.getCppPointer(widget)
        if widget == main or pointer in native_parents:
            continue
        if widget.windowType() in (QtCore.Qt.Popup, QtCore.Qt.ToolTip, QtCore.Qt.SplashScreen):
            continue
        area = QtCore.QRect(widget.mapToGlobal(QtCore.QPoint(0, 0)), QtWidgets.QWidget.size(widget))
        if area.isEmpty():
            continue  # Qt bootstrap shells have no displayed client surface.
        modal = widget.windowModality() != QtCore.Qt.NonModal
        record = {'target': _surface_target('qt_window', [pointer, widget.metaObject().className(), widget.objectName()]),
            'kind': 'qt_window', 'label': widget.windowTitle() or widget.objectName() or widget.metaObject().className(),
            'qt_class': widget.metaObject().className(), 'object_name': widget.objectName(),
            'screen_geometry': _rect_data(area), 'modal': modal,
            'scope': 'existing Qt window client area; window decoration excluded'}
        rows.append((record, None, widget, area))
    # QDockWidget is a defined panel container, unlike arbitrarily named
    # buttons/labels. Include docks in the Houdini main window as well as
    # custom windows, without adding a whole-desktop screenshot target.
    for dock in app.allWidgets():
        if not isinstance(dock, QtWidgets.QDockWidget) or not QtCompat.isValid(dock) or dock.isWindow() or not dock.isVisible():
            continue
        widget = dock.window()
        if widget is None or not widget.isVisible() or widget.isMinimized():
            continue
        area = QtCore.QRect(dock.mapToGlobal(QtCore.QPoint(0, 0)), QtWidgets.QWidget.size(dock))
        if area.isEmpty():
            continue
        record = {'target': _surface_target('qt_panel', [QtCompat.getCppPointer(dock), QtCompat.getCppPointer(widget), dock.objectName()]),
            'kind': 'qt_panel', 'label': dock.windowTitle() or dock.objectName() or 'QDockWidget',
            'qt_class': dock.metaObject().className(), 'object_name': dock.objectName(),
            'screen_geometry': _rect_data(area), 'modal': widget.windowModality() != QtCore.Qt.NonModal,
            'scope': 'displayed Qt dock panel rectangle; adjacent content excluded'}
        rows.append((record, dock, widget, area))
    for record, _, widget, area in rows:
        reason = None
        if record['modal']:
            reason = 'modal dialog capture is currently unverified'
        elif os.name != 'nt':
            reason = 'existing native surface capture is currently verified on Windows only'
        else:
            try:
                _require_uncovered_native_window(widget, area)
            except RuntimeError as error:
                reason = str(error)
        record['supported'] = reason is None
        if reason:
            record['reason'] = reason
    return rows


def discover_ui_surfaces() -> dict:
    """List current displayed native panes and same-process Qt windows, read-only."""
    import dsh_bridge
    return {'ok': True, 'runtime_id': dsh_bridge._RUNTIME_ID,
        'surfaces': [row[0] for row in _surface_rows()], 'scene_writes': 0,
        'scope': 'Houdini current displayed panes, visible same-process Qt windows and their displayed dock panels; hidden tabs/popups excluded',
        'target_lifetime': 'current runtime and actual native object; rediscover after close, rename or replacement',
        'semantic_status': 'unverified'}


def _resolve_surface(target):
    if not isinstance(target, str) or not target.startswith('ui:') or len(target) > 2048:
        raise ValueError('target must be the exact reference returned by houdini_ui_list')
    matches = [row for row in _surface_rows() if row[0]['target'] == target]
    if len(matches) != 1:
        raise ValueError('UI target is no longer displayed or belongs to another runtime; run houdini_ui_list again')
    row = matches[0]
    if not row[0]['supported']:
        raise ValueError(row[0]['reason'])
    return row


def _gui():
    if not hou.isUIAvailable():
        raise ValueError('UI capture requires Houdini GUI; native parameter/network UI is unsupported in headless mode')
    from hutil.Qt import QtCore, QtGui, QtWidgets
    app = QtWidgets.QApplication.instance()
    if app is None or QtCore.QThread.currentThread() != app.thread():
        raise RuntimeError('UI capture must run on Houdini owning GUI thread')
    return app, QtCore, QtGui, QtWidgets


def _evidence(state, *, file_status='failed', fresh=False):
    result = {'ok': False, 'node': state['node_path'], 'view': state['view'],
        'path': state['destination'], 'artifact': state['artifact'],
        'frame': state['frame'], 'fresh': fresh, 'file_status': file_status,
        'semantic_status': 'unverified', 'capture_unresolved': False,
        'scene_writes': 0, 'target':state['surface']['target'], 'surface':state['surface'],
        'scope':'existing displayed surface; no navigation, resize, activation, show/hide, parameter or frame edits'}
    return result


def _clear_idle_signal(state):
    callback = state.pop('idle_signal', None)
    if callback is not None:
        hou.ui.removeEventLoopCallback(callback)


def _await_drawing(state):
    """Yield to native GUI drawing; callbacks only signal readiness.

    A zero Qt timer can run before native parameter value binding finishes.
    Registration and removal stay in the Bridge queue; the callback only
    signals the worker's Event and never touches the scene or UI.
    """
    _clear_idle_signal(state)
    state['ready'].clear()
    hou.ui.postRedrawFence()
    if hou.applicationVersion()[0] == 21:
        # H21's raster pane settles in the normal Qt loop; H22's native controls
        # use the idle signal below after their binding has been refreshed.
        from hutil.Qt import QtCore
        QtCore.QTimer.singleShot(0, state['ready'].set)
        return
    signal = state['ready'].set
    state['idle_signal'] = signal
    hou.ui.addEventLoopCallback(signal)


def _close(state):
    """Release only the request drawing signal and artifact allocation."""
    from dsh_preview_paths import release_reservation
    _gui()
    errors = []
    try:
        _clear_idle_signal(state)
    except Exception as error:
        errors.append(f'request drawing callback cleanup failed: {error}')
    errors.extend(release_reservation(state['artifact']))
    state['closed'] = True
    return errors


def prepare_ui_capture(target, path=None, *, output_policy='managed') -> dict:
    """Admit an exact displayed surface and yield to the ordinary GUI loop."""
    import dsh_hou_helpers as h
    _gui()
    surface, pane, widget, area = _resolve_surface(target)
    frame = float(hou.frame())
    destination, artifact, hip_path = h._preview_artifact(
        path, frame=frame, purpose='existing_ui', output_policy=output_policy,
        default_label='ui_' + surface['kind'], default_subdir='screenshots', allowed_extensions={'.png'})
    state = {'surface': surface, 'pane': pane, 'widget': widget,
        'node_path': surface.get('node'), 'view': 'existing',
        'width': area.width(), 'height': area.height(), 'destination': destination,
        'artifact': artifact, 'hip_path': hip_path, 'frame': frame,
        'ready': threading.Event(), 'closed': False}
    try:
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        _await_drawing(state)
        return state
    except BaseException as error:
        cleanup = _close(state)
        evidence = _evidence(state)
        evidence.update(user_state_restored=not cleanup, restore_errors=cleanup, errors=[str(error)] + cleanup)
        raise h.CheckpointError('existing UI preparation failed: ' + '; '.join(evidence['errors']), evidence) from error


def refresh_ui_capture(state) -> None:
    """Verify the same displayed surface, then allow normal GUI drawing."""
    _gui()
    _current_borrowed_surface(state)
    _await_drawing(state)


def _current_borrowed_surface(state):
    from hutil.Qt import QtCompat
    if state.get('closed') or not QtCompat.isValid(state['widget']):
        raise ValueError('selected UI surface was closed; run houdini_ui_list again')
    surface, pane, widget, area = _resolve_surface(state['surface']['target'])
    if widget != state['widget'] or pane != state['pane']:
        raise ValueError('selected UI surface was replaced; run houdini_ui_list again')
    return surface, pane, widget, area


def _grab_surface(widget, area):
    from hutil.Qt import QtCore
    visibility = _require_uncovered_native_window(widget, area)
    local = area.topLeft() - widget.mapToGlobal(QtCore.QPoint(0, 0))
    pixmap = widget.screen().grabWindow(widget.effectiveWinId(), local.x(), local.y(), area.width(), area.height())
    _require_uncovered_native_window(widget, area)
    return pixmap, visibility


def finish_ui_capture(state) -> dict:
    """Capture the exact current native surface without changing its UI."""
    import dsh_hou_helpers as h
    from dsh_preview_paths import with_actual_path
    _, QtCore, QtGui, _ = _gui()
    if state.get('closed'):
        raise ValueError('native capture state is already closed')
    result = None
    capture_error = None
    try:
        if not state['ready'].is_set():
            raise RuntimeError('native UI has not returned to its outer event loop')
        surface, pane, widget, area = _current_borrowed_surface(state)
        state['surface'] = surface
        state['node_path'] = surface.get('node')
        # Native H21 QWidget grabs can be black; H22 offscreen grabs can reuse
        # another pane's framebuffer or stale field values. Read only this
        # request's visible, uncovered native window, never a widget framebuffer.
        pixmap, visibility = _grab_surface(widget, area)
        if pixmap.isNull() or pixmap.width() <= 0 or pixmap.height() <= 0:
            raise RuntimeError('selected native UI surface returned no pixels')
        if not pixmap.save(state['destination'], 'PNG'):
            raise RuntimeError('native UI image could not be saved')
        image = QtGui.QImage(state['destination'])
        if image.isNull() or image.size() != pixmap.size() or not os.path.getsize(state['destination']):
            raise RuntimeError('saved native UI image is unreadable or incomplete')
        frame = float(hou.frame())
        artifact = with_actual_path(state['artifact'], state['destination'], state['hip_path'])
        artifact['frame'] = frame
        result = _evidence(state, file_status='passed', fresh=True)
        result.update(ok=True, node=state['node_path'], artifact=artifact, frame=frame,
            initial_size=[state['width'], state['height']], actual_size=[area.width(), area.height()],
            image_size=[image.width(), image.height()], device_pixel_ratio=float(pixmap.devicePixelRatio()),
            screen_geometry=_rect_data(area), capture_method='native_surface_region', visibility=visibility,
            presentation_scope='current displayed surface captured inside its existing parent window; no UI presentation changes',
            bytes=int(os.path.getsize(state['destination'])), cleanup_pending=False,
            cleanup_scope='only request drawing signal and artifact reservation released; selected surface remains open')
    except BaseException as error:
        capture_error = error
    finally:
        cleanup = _close(state)
    if result is not None:
        h.report_image(state['destination'])
        result.update(user_state_restored=not cleanup, restore_errors=cleanup)
    if capture_error is not None or cleanup:
        evidence = result or _evidence(state)
        evidence.update(ok=False, user_state_restored=not cleanup, restore_errors=cleanup,
                        errors=([str(capture_error)] if capture_error is not None else []) + cleanup)
        raise h.CheckpointError('native UI screenshot failed: ' + '; '.join(evidence['errors']), evidence) from capture_error
    return result


def abort_ui_capture(state) -> dict:
    """Release this request's signal/allocation; leave its selected surface alone."""
    _gui()
    errors = [] if state.get('closed') else _close(state)
    evidence = _evidence(state)
    evidence.update(phase='aborted', user_state_restored=not errors, restore_errors=errors,
        cleanup_pending=False, cleanup_scope='only request drawing signal and artifact reservation released; selected surface remains open')
    return evidence
