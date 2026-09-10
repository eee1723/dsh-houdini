"""Bounded metadata observation. Main thread only; never cook or read geometry."""
import time
import threading
import hou


def _node(node):
    return {'path': node.path(), 'type': node.type().name()}


def scene_context(runtime_id, owner_thread):
    if threading.get_ident() != owner_thread:
        raise RuntimeError('scene_context must run on the Houdini owning thread')
    start = time.monotonic()
    ui = bool(hou.isUIAvailable())
    result = {
        'schema_version': 1, 'runtime_id': runtime_id,
        'observed_at': time.time(), 'version': hou.applicationVersionString(),
        'hip_path': hou.hipFile.path(), 'frame': float(hou.frame()),
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
