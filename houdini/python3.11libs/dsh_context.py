"""Bounded metadata observation. Main thread only; never cook or read geometry."""
import time
import threading
import re
import os
import hou
from dsh_project_paths import project_layout


def _node(node):
    return {'path': node.path(), 'type': node.type().name()}


def hip_file_identity():
    """Capture native HIP identity without filesystem I/O in the GUI.

    A named scene is not proof that its file/server is currently accessible.
    Only headless HOM's ambiguous new-file flag needs a disk observation.
    """
    path = hou.hipFile.path()
    is_new = bool(hou.hipFile.isNewFile())
    file_exists = None
    # HOM reports a loaded/saved default-name HIP as new in hython. In a GUI
    # its native flag is authoritative, including .hiplc and .hipnc scenes.
    if not hou.isUIAvailable() and is_new:
        file_exists = os.path.isfile(path)
        if file_exists:
            is_new = False
    return {'hip_path': path, 'hip_is_new': is_new,
            'hip_dir': None if is_new else os.path.dirname(path),
            'has_named_path': not is_new, 'file_exists': file_exists}


def hip_file_state():
    """Explicit disk observation, separate from native GUI identity capture."""
    identity = hip_file_identity()
    if identity['file_exists'] is None:
        identity['file_exists'] = os.path.isfile(identity['hip_path'])
    return {**identity,
            'project_layout': project_layout(identity['hip_path'], has_named_path=identity['has_named_path'])}


def unit_length_meters():
    """Read the HIP unit length without changing the scene or evaluating geometry."""
    try:
        output, error = hou.hscript('unitlength')
        if error:
            return None
        match = re.search(r'Unit Length:\s*([+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s+meters\b', output)
        value = float(match.group(1)) if match else None
        return value if value is not None and value > 0 else None
    except (AttributeError, ValueError, hou.Error):
        return None


def scene_context(runtime_id, owner_thread):
    if threading.get_ident() != owner_thread:
        raise RuntimeError('scene_context must run on the Houdini owning thread')
    start = time.monotonic()
    ui = bool(hou.isUIAvailable())
    hip = hip_file_identity()
    result = {
        'schema_version': 1, 'runtime_id': runtime_id,
        'observed_at': time.time(), 'version': hou.applicationVersionString(),
        **hip, 'project_layout': project_layout(hip['hip_path'], has_named_path=hip['has_named_path']),
        'frame': float(hou.frame()),
        'unit_length_meters': unit_length_meters(),
        'update_mode': {hou.updateMode.AutoUpdate:'auto', hou.updateMode.Manual:'manual', hou.updateMode.OnMouseUp:'on_mouse_up'}[hou.updateModeSetting()],
        'ui_available': ui, 'dirty_reliable': ui,
        'has_unsaved_changes': bool(hou.hipFile.hasUnsavedChanges()) if ui else None,
        'selection': [], 'selection_count': 0, 'panes': [],
        'focus': 'unknown', 'geometry_selection': {'status': 'not_observed',
            'reason': 'metadata snapshot does not evaluate geometry or enter viewer selection'},
        'scope': 'metadata only; observation is not a scene lock or mutation authorization',
    }
    if ui:
        selected = hou.selectedNodes()
        result['selection_count'] = len(selected)
        result['selection_truncated'] = len(selected) > 16
        for n in selected[:16]:
            row = _node(n)
            row['needs_cook'] = bool(n.needsToCook())
            row['errors'] = [str(v)[:240] for v in n.errors()[:2]]
            row['warnings'] = [str(v)[:240] for v in n.warnings()[:2]]
            result['selection'].append(row)
        result['playing'] = bool(hou.playbar.isPlaying())
        # No reliable active-pane claim when several panes can show different networks.
        panes = [p for p in hou.ui.paneTabs() if p.type() in
                 (hou.paneTabType.NetworkEditor, hou.paneTabType.SceneViewer)]
        result['panes_truncated'] = len(panes) > 4
        for pane in panes[:4]:
            try:
                parent = pane.pwd()
                row = {'kind': str(pane.type()), 'path': parent.path()}
                current = pane.currentNode()
                row['current'] = _node(current) if current else None
                if parent.childTypeCategory() == hou.sopNodeTypeCategory():
                    display, render = parent.displayNode(), parent.renderNode()
                    row['display'] = display.path() if display else None
                    row['render'] = render.path() if render else None
                result['panes'].append(row)
            except (hou.Error, AttributeError) as exc:
                result['panes'].append({'kind': str(pane.type()), 'status': 'unavailable',
                                        'reason': str(exc)[:160]})
    result['elapsed_ms'] = round((time.monotonic() - start) * 1000, 2)
    return result
