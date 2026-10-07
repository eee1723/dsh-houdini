"""Private native capture across Houdini's ordinary outer GUI event loop.

The Bridge owns request admission and all main-thread queue entries. This
state lives only in that one admitted request; it is not a capture registry.
"""
from __future__ import annotations

import os
import secrets
import threading

import hou


def _size(width, height):
    for name, value in (('width', width), ('height', height)):
        if type(value) is not int or not 1 <= value <= 4096:
            raise ValueError(f'{name} must be an integer in 1..4096 logical pixels')


def _require_uncovered_native_window(widget):
    """QScreen reads a screen region: refuse other-window pixels before use.

    Qt's grabWindow contract includes overlapping windows. This check is
    specific to the verified Windows native pane backend, not a desktop grab.
    """
    import ctypes
    from ctypes import wintypes as w
    from hutil.Qt import QtCore
    area = QtCore.QRect(widget.mapToGlobal(QtCore.QPoint(0, 0)), widget.size())
    if not widget.screen().geometry().contains(area):
        raise RuntimeError('native UI window extends outside its screen; request a smaller capture size')
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.GetAncestor.argtypes = [w.HWND, w.UINT]; api.GetAncestor.restype = w.HWND
    api.GetWindow.argtypes = [w.HWND, w.UINT]; api.GetWindow.restype = w.HWND
    api.IsWindowVisible.argtypes = [w.HWND]; api.IsWindowVisible.restype = w.BOOL
    api.IsIconic.argtypes = [w.HWND]; api.IsIconic.restype = w.BOOL
    api.GetClientRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]; api.GetClientRect.restype = w.BOOL
    api.ClientToScreen.argtypes = [w.HWND, ctypes.POINTER(w.POINT)]; api.ClientToScreen.restype = w.BOOL
    api.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]; api.GetWindowRect.restype = w.BOOL
    handle = int(widget.winId())
    client = w.RECT(); origin = w.POINT(0, 0)
    if not api.GetClientRect(handle, ctypes.byref(client)) or not api.ClientToScreen(handle, ctypes.byref(origin)):
        raise RuntimeError('owned native UI window bounds unavailable')
    left, top = origin.x, origin.y
    right, bottom = left + client.right, top + client.bottom
    root = api.GetAncestor(handle, 2)  # GA_ROOT
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
    return {'status': 'uncovered_before_capture', 'scope': 'owned client rectangle and observed visible windows above it'}


def _show_owned_window_without_activation(widget):
    """Present only the owned native window without activating it.

    Qt raise can activate the native RE window. The fixed native operation
    preserves position, size and activation, without touching other windows.
    """
    import ctypes
    from ctypes import wintypes as w
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT]
    api.SetWindowPos.restype = w.BOOL
    if not api.SetWindowPos(int(widget.winId()), None, 0, 0, 0, 0, 0x0013):  # NOSIZE | NOMOVE | NOACTIVATE
        raise RuntimeError('owned native capture window could not be presented without activation')


def _position_owned_window(widget):
    # H21's native creation already places the client correctly.
    if hou.applicationVersion()[0] == 21:
        return
    # Native creation can offset H22's client area by its window decoration.
    # Place the constructed, owned Qt window using its actual dimensions.
    available = widget.screen().availableGeometry()
    widget.move(available.right() + 1 - widget.width() - 20, available.y() + 40)


def _hscript_literal(value):
    """One literal native argument; no interpolation or line splitting."""
    if '\x00' in value or '\r' in value or '\n' in value:
        raise ValueError('native UI target cannot contain NUL or line breaks')
    escaped = value.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
    return '"' + escaped + '"'


def _gui():
    if not hou.isUIAvailable():
        raise ValueError('UI capture requires Houdini GUI; native parameter/network UI is unsupported in headless mode')
    from hutil.Qt import QtCore, QtGui, QtWidgets
    app = QtWidgets.QApplication.instance()
    if app is None or QtCore.QThread.currentThread() != app.thread():
        raise RuntimeError('UI capture must run on Houdini owning GUI thread')
    return app, QtCore, QtGui, QtWidgets


def _navigation():
    app, _, _, _ = _gui()
    selected = tuple(hou.selectedItems())
    panes = []
    for pane in hou.ui.paneTabs():
        if isinstance(pane, hou.PathBasedPaneTab):
            # Hidden native tabs from our completed capture may await deletion.
            if pane.name().startswith('__dsh_ui_capture_'):
                continue
            row = {'pane': pane, 'name': pane.name(), 'pwd': pane.pwd(),
                'current': pane.currentNode(), 'group': pane.linkGroup(), 'tab': pane.isCurrentTab()}
            if isinstance(pane, hou.ParameterEditor):
                row['scroll'] = pane.scrollPosition()
            if isinstance(pane, hou.NetworkEditor):
                row['bounds'] = pane.visibleBounds()
            panes.append(row)
    return {'selected': selected,
        'currents': tuple(n for n in selected if isinstance(n, hou.Node) and n.isCurrent()),
        'panes': panes, 'active': app.activeWindow(), 'focus': app.focusWidget()}


def _restore_navigation(snapshot):
    """Restore only native construction's temporary navigation before yielding."""
    app, _, _, QtWidgets = _gui()
    errors = []
    try:
        if tuple(hou.selectedItems()) != snapshot['selected']:
            for item in hou.selectedItems():
                item.setSelected(False)
            for item in snapshot['selected']:
                item.setSelected(True)
            for node in snapshot['currents']:
                node.setCurrent(True)
    except Exception as error:
        errors.append(f'selection restore failed: {error}')
    for row in snapshot['panes']:
        pane, current, pwd = row['pane'], row['current'], row['pwd']
        try:
            if (pane.currentNode(), pane.pwd()) != (current, pwd):
                if current is None:
                    command = 'pane -H ' + _hscript_literal(pwd.path().rstrip('/') + '/')
                else:
                    command = 'pane -h ' + _hscript_literal(pwd.path()) + ' -H ' + _hscript_literal(current.path())
                _, error = hou.hscript(command + ' ' + _hscript_literal(row['name']))
                if error:
                    raise RuntimeError(error)
            if pane.linkGroup() != row['group']:
                pane.setLinkGroup(row['group'])
            if row['tab'] and not pane.isCurrentTab():
                pane.setIsCurrentTab()
            if 'scroll' in row and pane.scrollPosition() != row['scroll']:
                pane.setScrollPosition(row['scroll'])
            if 'bounds' in row and pane.visibleBounds() != row['bounds']:
                pane.setVisibleBounds(row['bounds'])
            if (pane.currentNode(), pane.pwd(), pane.linkGroup(), pane.isCurrentTab()) != (current, pwd, row['group'], row['tab']):
                raise RuntimeError('navigation restore readback mismatch')
        except Exception as error:
            errors.append(f'pane restore failed ({row["name"]}): {error}')
    try:
        if app.activeWindow() != snapshot['active']:
            QtWidgets.QApplication.setActiveWindow(snapshot['active'])
        if snapshot['focus'] is not None and app.focusWidget() != snapshot['focus']:
            snapshot['focus'].setFocus()
        if tuple(hou.selectedItems()) != snapshot['selected']:
            raise RuntimeError('selection restore readback mismatch')
        if any(not n.isCurrent() for n in snapshot['currents']):
            raise RuntimeError('current-node restore readback mismatch')
    except Exception as error:
        errors.append(f'focus/selection restore failed: {error}')
    return errors


def _evidence(state, *, file_status='failed', fresh=False):
    return {'ok': False, 'node': state['node_path'], 'view': state['view'],
        'path': state['destination'], 'artifact': state['artifact'],
        'frame': state['frame'], 'fresh': fresh, 'file_status': file_status,
        'semantic_status': 'unverified', 'capture_unresolved': False,
        'scene_writes': 0, 'scope': 'private pinned native pane; native construction navigation restored before yielding; no parameter/frame edits'}


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
    """Close only this request's pane; native tab removal may be deferred."""
    from dsh_preview_paths import release_reservation
    app, _, _, _ = _gui()
    errors = []
    try:
        _clear_idle_signal(state)
    except Exception as error:
        errors.append(f'owned native idle callback cleanup failed: {error}')
    guard = state.pop('window_guard', None)
    if guard is not None:
        app.removeEventFilter(guard)
    panel = state.pop('panel', None)
    if panel is not None:
        try:
            widget = panel.qtParentWindow()
            if widget is not None:
                widget.hide()
                if widget.isVisible():
                    raise RuntimeError('owned UI window remains visible')
            # Closing the actual owned tab lets Houdini tear down its native
            # parameter/network dialog before disposing the floating shell.
            # H21 can retain a tab when only FloatingPanel.close is called.
            state['pane'].close()
        except Exception as error:
            errors.append(f'owned native pane close failed: {error}')
    errors.extend(release_reservation(state['artifact']))
    state['closed'] = True
    return errors


def prepare_ui_capture(node, path=None, *, view='parameters', width=820,
                       height=720, output_policy='managed') -> dict:
    """Prepare a private target pane; Bridge must yield before finishing.

    State includes a threading.Event signalled by an outer GUI callback
    which never calls HOM. Bridge waits off the GUI thread, then queues finish
    through its ordinary FIFO. No nested event processing or synthetic UI.
    """
    import dsh_hou_helpers as h
    app, QtCore, _, _ = _gui()
    if view not in ('parameters', 'network'):
        raise ValueError("view must be 'parameters' or 'network'")
    _size(width, height)
    target = h._resolve(node)
    if view == 'network' and not target.isNetwork():
        raise ValueError('network view requires a parent network; pass the network whose contents should be shown')
    frame = float(hou.frame())
    navigation = _navigation()
    destination, artifact, hip_path = h._preview_artifact(
        path, frame=frame, purpose=f'{view}_ui', output_policy=output_policy,
        default_label=f'{target.name()}_{view}', default_subdir='screenshots',
        allowed_extensions={'.png'})
    state = {'node_path': target.path(), 'identity': target.sessionId(), 'view': view,
        'width': width, 'height': height, 'destination': destination,
        'artifact': artifact, 'hip_path': hip_path, 'frame': frame,
        'ready': threading.Event(), 'closed': False, 'in_prepare': True, 'widget': None}
    try:
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        kind = hou.paneTabType.Parm if view == 'parameters' else hou.paneTabType.NetworkEditor
        screen = hou.qt.mainWindow().screen()
        visible = screen.availableGeometry()
        top = visible.y() + 20
        # Houdini's native panel position uses a bottom-origin desktop Y.
        native_y = screen.geometry().bottom() + 1 - top - height
        position = (visible.right() + 1 - width - 20, native_y)
        panel = hou.ui.curDesktop().createFloatingPanel(kind,
            position=position, size=(width, height), immediate=False)
        state['panel'] = panel
        pane = panel.paneTabs()[0]
        state['pane'] = pane
        pane.setName('__dsh_ui_capture_' + secrets.token_hex(8))
        pane.setPin(True)

        class OwnedWindowGuard(QtCore.QObject):
            def eventFilter(self, watched, event):
                if event.type() in (QtCore.QEvent.Polish, QtCore.QEvent.Show, QtCore.QEvent.WinIdChange):
                    owned = state['widget']
                    if owned is None and state['in_prepare'] and panel is not None:
                        owned = panel.qtParentWindow()
                        state['widget'] = owned
                    if owned is not None and watched == owned:
                        # Does not rebuild the native window or invalidate
                        # Houdini's initial native parameter dialog.
                        owned.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
                return False
        guard = OwnedWindowGuard()
        state['window_guard'] = guard
        app.installEventFilter(guard)
        if view == 'parameters':
            pane.setCurrentNode(target)
            target.updateParmStates()
            if pane.currentNode() != target:
                raise RuntimeError('native parameter pane did not resolve requested target')
        else:
            pane.setPwd(target)
            if pane.pwd() != target:
                raise RuntimeError('native network pane did not resolve requested parent')
        if state['widget'] is None:
            state['widget'] = panel.qtParentWindow()
        if state['widget'] is None:
            raise RuntimeError('native pane construction is deferred before its Qt window can be configured')
        _position_owned_window(state['widget'])
        _show_owned_window_without_activation(state['widget'])
        restored = _restore_navigation(navigation)
        if restored:
            raise RuntimeError('; '.join(restored))
        state['in_prepare'] = False
        _await_drawing(state)
        return state
    except BaseException as error:
        cleanup = _restore_navigation(navigation) + _close(state)
        evidence = _evidence(state)
        evidence.update(user_state_restored=not cleanup, restore_errors=cleanup,
                        errors=[str(error)] + cleanup)
        raise h.CheckpointError('native UI preparation failed: ' + '; '.join(evidence['errors']), evidence) from error


def refresh_ui_capture(state) -> None:
    """Bind constructed controls and frame their private view, then yield.

    Native dialog construction precedes its scalar/string display updates;
    capture must not recreate that binding immediately before grabbing pixels.
    """
    _gui()
    target = hou.nodeBySessionId(state['identity'])
    if target is None or state.get('closed'):
        raise RuntimeError('requested UI target no longer exists')
    pane, widget = state['pane'], state['widget']
    modern = hou.applicationVersion()[0] != 21
    if modern:
        widget.resize(state['width'], state['height'])
        _position_owned_window(widget)
        widget.ensurePolished()
    if state['view'] == 'parameters':
        # H21 binds the requested native raster controls during construction.
        # H22 constructs controls first and then binds their current values.
        if modern:
            pane.setCurrentNode(target, pick_node=False)
            target.updateParmStates()
    else:
        rectangles = [pane.itemRect(item, adjusted=False) for item in target.allItems()]
        state['item_count'] = len(rectangles)
        content = None
        if rectangles:
            content = hou.BoundingRect(min(float(r.min()[0]) for r in rectangles), min(float(r.min()[1]) for r in rectangles),
                max(float(r.max()[0]) for r in rectangles), max(float(r.max()[1]) for r in rectangles))
            pane.setVisibleBounds(hou.BoundingRect(content.min()[0] - 2, content.min()[1] - 2,
                content.max()[0] + 2, content.max()[1] + 2))
        else:
            pane.setVisibleBounds(hou.BoundingRect(-5, -4, 5, 4))
        state['content'] = content
        pane.redraw()
    _await_drawing(state)


def finish_ui_capture(state) -> dict:
    """Grab the settled private native pane, then hide/close it on GUI thread."""
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
        target = hou.nodeBySessionId(state['identity'])
        if target is None:
            raise RuntimeError('requested capture node was deleted before drawing')
        pane = state['pane']
        resolved = pane.currentNode() if state['view'] == 'parameters' else pane.pwd()
        if resolved != target:
            raise RuntimeError('native pane target changed before capture')
        widget = state['widget']
        if widget is None:
            raise RuntimeError('native UI window did not finish construction')
        widget.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        content = state.get('content')
        widget.repaint()
        # Native H21 QWidget grabs can be black; H22 offscreen grabs can reuse
        # another pane's framebuffer or stale field values. Read only this
        # request's visible, uncovered native window, never a widget framebuffer.
        visibility = _require_uncovered_native_window(widget)
        pixmap = widget.screen().grabWindow(widget.winId())
        _require_uncovered_native_window(widget)
        capture_method = 'native_window'
        if pixmap.isNull() or pixmap.width() <= 0 or pixmap.height() <= 0:
            raise RuntimeError('native pane returned no pixels')
        if not pixmap.save(state['destination'], 'PNG'):
            raise RuntimeError('native UI image could not be saved')
        image = QtGui.QImage(state['destination'])
        if image.isNull() or image.size() != pixmap.size() or not os.path.getsize(state['destination']):
            raise RuntimeError('saved native UI image is unreadable or incomplete')
        # Observed H21 never-exposed GUI workers can return a valid but wholly
        # uniform GL image. This is a capture/bootstrap failure, not semantic
        # validation of the design. Native pane chrome guarantees variation.
        samples = {image.pixel(x, y) for y in range(0, image.height(), max(1, image.height() // 64))
                   for x in range(0, image.width(), max(1, image.width() // 64))}
        if len(samples) < 2:
            raise RuntimeError('native UI produced uniform pixels; no rendered parameter/network pane was captured')
        frame = float(hou.frame())
        artifact = with_actual_path(state['artifact'], state['destination'], state['hip_path'])
        artifact['frame'] = frame
        result = _evidence(state, file_status='passed', fresh=True)
        result.update(ok=True, node=target.path(), artifact=artifact, frame=frame,
            requested_size=[state['width'], state['height']], actual_size=[widget.width(), widget.height()],
            image_size=[image.width(), image.height()], device_pixel_ratio=float(pixmap.devicePixelRatio()),
            capture_method=capture_method, visibility=visibility,
            presentation_scope='temporary owned native pane may be visible; shown without activation; image contains only its native surface',
            bytes=int(os.path.getsize(state['destination'])), cleanup_pending=True,
            cleanup_scope='owned widget hidden immediately; native tab removal finalizes at outer GUI loop; Qt logical activeWindow may fall back to main window')
        if state['view'] == 'network':
            bounds = pane.visibleBounds()
            result.update(visible_bounds=list(bounds.min()) + list(bounds.max()),
                content_bounds=list(content.min()) + list(content.max()) if content is not None else None,
                item_count=state.get('item_count', 0),
                framing_scope='all native item bodies plus two network units margin; labels/decorations may extend beyond bodies')
        else:
            result.update(parameter_dialog_displayed=bool(pane.isShowingParmDialog()),
                visible_parameter_names=[parm.name() for parm in pane.visibleParms()][:128],
                parameter_scope='native visibleParms metadata may include other tab contents; visual design interpretation remains unverified')
            result['visible_parameter_count'] = len(pane.visibleParms())
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
    """Release the admitted request's private pane/allocation without a capture."""
    _gui()
    errors = [] if state.get('closed') else _close(state)
    evidence = _evidence(state)
    evidence.update(phase='aborted', user_state_restored=not errors, restore_errors=errors,
        cleanup_pending=True, cleanup_scope='owned widget hidden; native tab removal finalizes at outer GUI loop')
    return evidence
