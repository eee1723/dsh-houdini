"""Explicit, HIP-persistent control entries and native network navigation.

The node's userData is the only persistent declaration. Names, node types,
Network Box colors and parameter counts never make a node a control entry.
"""
from __future__ import annotations

import contextlib
import math
import os
import re
import unicodedata
import uuid

import hou
from dsh_context import hip_file_state

CONTROL_KEY = 'dsh_houdini_control'
NODE_ID_KEY = 'dsh_houdini_node_delivery_id'
_ACTIVE_JOURNAL = None


def _resolve(value, parent=None):
    if isinstance(value, hou.Node):
        node = value
    elif isinstance(value, str) and value:
        node = parent.node(value) if parent is not None else hou.node(value)
    else:
        raise ValueError('control node must be an existing node or node path')
    if node is None:
        raise ValueError(f'control node does not exist: {value}')
    if parent is not None:
        root = parent.path().rstrip('/') + '/'
        if node != parent and not node.path().startswith(root):
            raise ValueError(f'{node.path()} is outside control scope {parent.path()}')
    return node


def _label(value):
    if (not isinstance(value, str) or not value.strip() or len(value) > 200
            or any(unicodedata.category(char) == 'Cc' for char in value)):
        raise ValueError('control label must be nonempty, at most 200 characters, without control characters')
    return value.strip()


def _asset_path(node):
    asset = node
    while asset.parent() is not None and asset.parent().parent() is not None:
        if asset.parent().parent().path() == '/':
            break
        asset = asset.parent()
    return asset.path()


def _entry(node, label):
    return {'path': node.path(), 'identity': int(node.sessionId()), 'label': label,
            'parent': node.parent().path() if node.parent() is not None else None,
            'asset': _asset_path(node)}


def list_controls(parent='/', recursive=True):
    """Read explicit node declarations without parameters, geometry or cooking."""
    root = _resolve(parent)
    if type(recursive) is not bool:
        raise ValueError('recursive must be a boolean')
    nodes = (root, *(root.allSubChildren(sync_delayed_definition=False) if recursive else root.children()))
    rows = []
    for node in nodes:
        label = node.userData(CONTROL_KEY)
        if isinstance(label, str) and label.strip():
            rows.append(_entry(node, label))
    return sorted(rows, key=lambda row: (row['asset'], row['path']))


def snapshot_controls(nodes):
    """Capture navigation metadata, keyed by current runtime node identity."""
    return [{'identity': int(node.sessionId()), 'path': node.path(),
             'label': node.userData(CONTROL_KEY), 'node_id': node.userData(NODE_ID_KEY)} for node in nodes]


def _write_control(node, label):
    if label is None:
        node.destroyUserData(CONTROL_KEY, must_exist=False)
    else:
        node.setUserData(CONTROL_KEY, label)


def _write_node_id(node, value):
    if value is None:
        node.destroyUserData(NODE_ID_KEY, must_exist=False)
    else:
        node.setUserData(NODE_ID_KEY, value)


def restore_controls(snapshot):
    """Restore surviving identities; never write a same-named replacement."""
    errors, missing, restored = [], [], []
    for row in reversed(snapshot):
        node = hou.nodeBySessionId(row['identity'])
        if node is None:
            missing.append(row['path'])
            continue
        try:
            if node.userData(CONTROL_KEY) != row['label']:
                _write_control(node, row['label'])
            if node.userData(CONTROL_KEY) != row['label']:
                raise RuntimeError('control declaration readback mismatch')
            if node.userData(NODE_ID_KEY) != row.get('node_id'):
                _write_node_id(node, row.get('node_id'))
            if node.userData(NODE_ID_KEY) != row.get('node_id'):
                raise RuntimeError('node reference identity readback mismatch')
            restored.append(node.path())
        except Exception as error:
            errors.append(f"{row['path']}: {error}")
    return {'ok': not errors, 'restored': restored, 'missing_nodes': missing,
            'errors': errors, 'scope': 'control declarations on surviving node identities only'}


@contextlib.contextmanager
def transaction_journal():
    """Collect declaration snapshots for the enclosing Bridge exec rollback."""
    global _ACTIVE_JOURNAL
    previous = _ACTIVE_JOURNAL
    journal = {'entries': []}
    _ACTIVE_JOURNAL = journal
    try:
        yield journal
    finally:
        _ACTIVE_JOURNAL = previous


def reconcile_transaction(journal):
    """Compensate metadata after a failed exec, including disabled native Undo."""
    errors, missing, restored = [], [], []
    for snapshot in reversed(journal.get('entries', [])):
        result = restore_controls(snapshot)
        errors.extend(result['errors'])
        missing.extend(result['missing_nodes'])
        restored.extend(result['restored'])
    return {'ok': not errors, 'entry_count': len(journal.get('entries', [])),
            'restored': sorted(set(restored)), 'missing_nodes': sorted(set(missing)),
            'errors': errors, 'scope': 'control declarations only; does not restore deleted nodes'}


def declare_controls(parent, controls=None, remove=None, require_owned=None, allow_foreign=None):
    """Preflight all explicit targets, then write and read back their labels."""
    root = _resolve(parent)
    controls = [] if controls is None else controls
    remove = [] if remove is None else remove
    if not isinstance(controls, (list, tuple)) or not isinstance(remove, (list, tuple)):
        raise ValueError('controls and remove must be lists')
    if require_owned is None:
        raise ValueError('control declaration requires an ownership checker')
    updates, ids = [], set()
    for row in controls:
        if not isinstance(row, dict) or set(row) != {'node', 'label'}:
            raise ValueError('each control declaration requires exactly node and label')
        node, label = _resolve(row['node'], root), _label(row['label'])
        identity = int(node.sessionId())
        if identity in ids:
            raise ValueError(f'duplicate control target: {node.path()}')
        ids.add(identity)
        updates.append((node, label))
    for value in remove:
        node = _resolve(value, root)
        identity = int(node.sessionId())
        if identity in ids:
            raise ValueError(f'duplicate or conflicting control target: {node.path()}')
        ids.add(identity)
        updates.append((node, None))
    for node, _ in updates:
        require_owned(node, 'network_controls', allow_foreign)
    snapshot = snapshot_controls([node for node, _ in updates])
    changed = [(node, label) for node, label in updates if node.userData(CONTROL_KEY) != label]
    if changed and _ACTIVE_JOURNAL is not None:
        _ACTIVE_JOURNAL['entries'].append(snapshot)
    writes = 0
    try:
        for node, label in changed:
            _write_control(node, label)
            writes += 1
            if node.userData(CONTROL_KEY) != label:
                raise RuntimeError(f'{node.path()}: control declaration readback mismatch')
    except Exception as error:
        recovery = restore_controls(snapshot)
        failure = RuntimeError(f'control declaration failed: {error}; restored={recovery["ok"]}')
        failure.evidence = {'ok': False, 'scene_writes': writes,
                            'restored': recovery['ok'], 'restore_errors': recovery['errors']}
        raise failure from error
    return {'ok': True, 'parent': root.path(), 'scene_writes': writes,
            'declared': [_entry(node, label) for node, label in updates if label is not None],
            'removed': [node.path() for node, label in updates if label is None],
            'controls': list_controls(root),
            'scope': 'explicit control entry declarations; no parameter or geometry verification'}


def _expand_control_boxes(node):
    """Reveal a control entry inside its actual minimized box ancestry."""
    boxes = []
    box = node.parentNetworkBox()
    while box is not None:
        boxes.append(box)
        box = box.parentNetworkBox()
    expanded = []
    for box in reversed(boxes):
        if box.isMinimized():
            box.setMinimized(False)
            if box.isMinimized():
                raise RuntimeError(f'无法展开控制节点所在框：{box.path()}')
            expanded.append({'path': box.path(), 'identity': int(box.sessionId())})
    return expanded


def focus_control(node, *, expected_identity=None, expected_label=None):
    """Locate an actual declared node and show its parameters; model flags stay untouched."""
    if not hou.isUIAvailable():
        raise RuntimeError('control navigation requires the Houdini GUI')
    target = _resolve(node)
    label = target.userData(CONTROL_KEY)
    if not label or (expected_identity is not None and int(target.sessionId()) != expected_identity):
        raise ValueError('控制节点已改变，请刷新列表。')
    if expected_label is not None and label != expected_label:
        raise ValueError('控制声明已改变，请刷新列表。')
    return _focus_node(target, label)


def _focus_node(target, label):
    if not hou.isUIAvailable():
        raise RuntimeError('节点定位需要 Houdini 图形界面。')
    expanded_boxes = _expand_control_boxes(target)
    panes = list(hou.ui.curDesktop().paneTabs())
    networks = [pane for pane in panes if pane.type() == hou.paneTabType.NetworkEditor]
    matching = [pane for pane in networks if pane.pwd() == target.parent()]
    current = [pane for pane in networks if pane.isCurrentTab()]
    network = (matching or current or networks or [None])[0]
    if network is None:
        network = hou.ui.curDesktop().createFloatingPaneTab(hou.paneTabType.NetworkEditor)
    network.setPwd(target.parent())
    target.setCurrent(True, clear_all_selected=True)
    network.setCurrentNode(target)
    position, size = target.position(), target.size()
    x, y, width, height = (float(position.x()), float(position.y()),
                           float(size.x()), float(size.y()))
    if not all(math.isfinite(value) for value in (x, y, width, height)):
        raise ValueError('控制节点位置无法读取。')
    bounds = hou.BoundingRect(x - 3.0, y - 2.5, x + max(width, 1.0) + 3.0,
                              y + max(height, 0.5) + 2.5)
    network.setVisibleBounds(bounds)
    parameters = [pane for pane in panes if pane.type() == hou.paneTabType.Parm
                  and pane.linkGroup() != hou.paneLinkType.Pinned]
    current_parameters = [pane for pane in parameters if pane.isCurrentTab()]
    parameter = (current_parameters or parameters or [None])[0]
    if parameter is None:
        parameter = hou.ui.curDesktop().createFloatingPaneTab(hou.paneTabType.Parm)
    parameter.setCurrentNode(target)
    network.setIsCurrentTab()
    parameter.setIsCurrentTab()
    return {**_entry(target, label), 'network_parent': network.pwd().path(),
            'network_current': network.currentNode().path(),
            'parameter_current': parameter.currentNode().path(),
            'expanded_boxes': expanded_boxes,
            'scope': 'control box presentation and network/parameter pane navigation only'}


def _node_identifiers():
    result = {}
    for node in hou.node('/').allSubChildren(sync_delayed_definition=False):
        identifier = node.userData(NODE_ID_KEY)
        if identifier:
            result.setdefault(identifier, []).append(node)
    return result


def present_nodes(nodes, *, require_owned, allow_foreign=None):
    """Publish explicit, HIP-persistent node entry references in one execution result."""
    if hip_file_state()['hip_is_new']:
        raise ValueError('节点交付需要明确的工程文件，请先 Save As，再声明并保存节点入口。')
    if not isinstance(nodes, (list, tuple)) or not 1 <= len(nodes) <= 16:
        raise ValueError('nodes must contain 1..16 explicit node entries')
    existing = _node_identifiers()
    prepared, seen = [], set()
    for row in nodes:
        if not isinstance(row, dict) or 'node' not in row or set(row) - {'node', 'label', 'role', 'description', 'new_identity'}:
            raise ValueError('node entries require node; optional label,role,description,new_identity')
        node = _resolve(row['node'])
        if node.sessionId() in seen:
            raise ValueError('duplicate delivered node: ' + node.path())
        seen.add(node.sessionId())
        role = row.get('role', 'node')
        if role not in ('control', 'output', 'node'):
            raise ValueError('node role must be control, output or node')
        if type(row.get('new_identity', False)) is not bool:
            raise ValueError('new_identity must be boolean')
        label = _label(row.get('label', (node.userData(CONTROL_KEY) if role == 'control' else None) or node.name()))
        description = row.get('description')
        if description is not None:
            description = _label(description)
        identifier = node.userData(NODE_ID_KEY)
        valid_id = isinstance(identifier, str) and re.fullmatch('[0-9a-f]{32}', identifier)
        if valid_id and len(existing.get(identifier, [])) > 1 and not row.get('new_identity'):
            raise ValueError('节点标识因复制而重复；对复制品使用 new_identity=True 重新交付，不按路径猜目标。')
        identifier = identifier if valid_id and not row.get('new_identity') else uuid.uuid4().hex
        control_label = label if role == 'control' else node.userData(CONTROL_KEY)
        changes = identifier != node.userData(NODE_ID_KEY) or control_label != node.userData(CONTROL_KEY)
        if changes:
            require_owned(node, 'present_nodes', allow_foreign)
        prepared.append((node, identifier, label, role, control_label, changes, description))
    snapshot = snapshot_controls([row[0] for row in prepared])
    changed = any(row[5] for row in prepared)
    if changed and _ACTIVE_JOURNAL is not None:
        _ACTIVE_JOURNAL['entries'].append(snapshot)
    writes = 0
    try:
        for node, identifier, _label_value, _role, control_label, _changes, _description in prepared:
            if node.userData(NODE_ID_KEY) != identifier:
                _write_node_id(node, identifier); writes += 1
            if node.userData(CONTROL_KEY) != control_label:
                _write_control(node, control_label); writes += 1
            if node.userData(NODE_ID_KEY) != identifier or node.userData(CONTROL_KEY) != control_label:
                raise RuntimeError('node entry metadata readback mismatch')
    except Exception:
        recovery = restore_controls(snapshot)
        if not recovery['ok']:
            raise RuntimeError('node entry metadata restoration failed: ' + str(recovery['errors']))
        raise
    return {'kind': 'houdini/node-delivery-v1', 'scene_writes': writes,
            'nodes': [{'id': identifier, 'path': node.path(), 'label': label, 'role': role,
                       'type': node.type().name(), 'context': node.type().category().name(),
                       **({'description': description} if description is not None else {})}
                      for node, identifier, label, role, _control, _changes, description in prepared],
            'requires_save': changed,
            'scope': 'explicit node navigation entries only; save HIP after first declaration; no geometry or control verification'}


def resolve_reference(reference, expected_hip):
    """Resolve a saved entry in the current HIP; never fall back to its old path."""
    if not isinstance(reference, dict) or set(reference) != {'id'} or not isinstance(reference['id'], str) or not re.fullmatch('[0-9a-f]{32}', reference['id']):
        raise ValueError('node reference requires its persistent id')
    if not isinstance(expected_hip, str) or not expected_hip.strip():
        raise ValueError('expected_hip must be the original delivered HIP')
    normalize = lambda path: os.path.normcase(os.path.abspath(path))
    current = hip_file_state()
    if current['hip_is_new'] or normalize(current['hip_path']) != normalize(expected_hip):
        raise ValueError('当前工程与节点交付的工程不同，请先打开对应工程；定位不会加载或覆盖文件。')
    matches = _node_identifiers().get(reference['id'], [])
    if not matches:
        raise ValueError('工程中没有这个节点入口，可能尚未保存或节点已删除，请重新交付入口。')
    if len(matches) != 1:
        raise ValueError('节点入口标识重复，无法确定目标，请对复制品重新交付入口。')
    return matches[0]


def focus_reference(reference, *, expected_hip):
    target = resolve_reference(reference, expected_hip)
    label = target.userData(CONTROL_KEY) or target.name()
    return {**_focus_node(target, label), 'id': reference['id'], 'scene_writes': 0,
            'scope': 'explicit node navigation and box reveal only; no parameter, geometry, HIP load or save'}
