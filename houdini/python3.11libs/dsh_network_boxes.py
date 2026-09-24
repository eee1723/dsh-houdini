"""Governed Houdini Network Box grouping, provenance and recovery."""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import uuid

import hou

from dsh_network_layout import Rect, contains, union


ROLE_COLORS = {
    'controls': (0.30, 0.48, 0.70),
    'component': (0.42, 0.46, 0.52),
    'placement': (0.27, 0.58, 0.55),
    'source': (0.68, 0.50, 0.25),
    'assembly': (0.56, 0.40, 0.65),
    'output': (0.39, 0.59, 0.31),
}
MAX_BOXES = 64
MAX_NODES = 512
SCHEMA = 2
RESERVED_SERVICE_NAMES = {'__dsh_houdini_render_service'}


class NetworkBoxOperationError(RuntimeError):
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = evidence


_PID = os.getpid()
if globals().get('_BOX_REGISTRY_PID') != _PID:
    _BOX_REGISTRY_PID = _PID
    _OWNED_BOXES = {}
    _SERVICE_BOXES = {}
    _BOX_GENERATION = uuid.uuid4().hex
_ACTIVE_JOURNAL = None


def _box_key(box):
    return ('network_box', int(box.parent().sessionId()), int(box.sessionId()))


def _box_by_identity(parent, identity):
    for box in parent.networkBoxes():
        if int(box.sessionId()) == int(identity):
            return box
    return None


def _parent_by_snapshot(snapshot):
    parent = hou.nodeBySessionId(snapshot['parent_identity'])
    return parent


def register_service_box(box):
    _SERVICE_BOXES[_box_key(box)] = box
    return box


def is_service_box(box):
    try: return _SERVICE_BOXES.get(_box_key(box)) == box
    except Exception: return False


def box_provenance(box, active_owner_session=None):
    key = _box_key(box)
    entry = _OWNED_BOXES.get(key)
    if entry is not None:
        try:
            if entry.get('native_object') != box: entry = None
        except Exception:
            entry = None
    if is_service_box(box):
        status = 'dsh_service'
    elif entry is None:
        status = 'foreign'
    elif entry.get('session') == active_owner_session:
        status = 'owned_current_session'
    else:
        status = 'owned_other_session'
    return {'kind': 'network_box', 'identity': int(box.sessionId()),
            'parent_identity': int(box.parent().sessionId()), 'name': box.name(),
            'status': status,
            'runtime_owner': ({key:value for key,value in entry.items()
                               if key != 'native_object'} if entry else None)}


def _live_owner(box):
    entry = _OWNED_BOXES.get(_box_key(box))
    if entry is None: return None
    try: return entry if entry.get('native_object') == box else None
    except Exception: return None


def _validate_allow_foreign(value):
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError('allow_foreign must be a nonempty explicit authorization reason string, or None')


def _require_box(box, operation, active_owner_session, allow_foreign):
    _validate_allow_foreign(allow_foreign)
    info = box_provenance(box, active_owner_session)
    if info['status'] == 'dsh_service':
        raise ValueError(f"{box.path()} belongs to the persistent dsh-houdini render service; {operation} is not allowed")
    if active_owner_session is None or info['status'] == 'owned_current_session':
        return
    if allow_foreign:
        print(f"[ownership] foreign-network-box exemption for {operation}: {box.path()} — {allow_foreign.strip()}")
        return
    raise ValueError(
        f"ownership guard: {operation} refused for foreign Network Box {box.path()}. "
        "Names, labels, colors, members and an owned parent do not establish ownership; "
        "retry only when the user explicitly authorized this box, with allow_foreign=\"<why>\"."
    )


def _service_node_or_ancestor(node):
    current = node
    while current is not None:
        try:
            if current.userData('dsh_houdini_owner') == 'render_view_v2':
                return current.path()
            current = current.parent()
        except Exception as error:
            raise RuntimeError(f'service ancestry inspection failed for {node}: {error}') from error
    return None


def _node_rect(node):
    position, size = node.position(), node.size()
    x, y = float(position.x()), float(position.y())
    return Rect(x, y, x + float(size.x()), y + float(size.y()))


def _box_rect(box):
    position, size = box.position(), box.size()
    x, y = float(position.x()), float(position.y())
    return Rect(x, y, x + float(size.x()), y + float(size.y()))


def _rect_close(left, right, tolerance=1e-5):
    return all(abs(a-b) <= tolerance for a,b in zip(left.as_list(), right.as_list()))


def _set_node_position(node,target): node.setPosition(hou.Vector2(*target))
def _set_box_bounds(box,target): box.setBounds(hou.BoundingRect(*target))


def _content_bounds(nodes=(), boxes=()):
    rectangles = [_node_rect(node) for node in nodes]
    rectangles.extend(_effective_box_rect(box) for box in boxes)
    if not rectangles:
        raise ValueError('Network Box needs at least one node or child box')
    combined = union(rectangles)
    width = max((rectangle.width for rectangle in rectangles), default=2.0)
    height = max((rectangle.height for rectangle in rectangles), default=1.0)
    return combined.padded(0.5 * width, 0.5 * width, 0.5 * height, 1.5 * height)


def _color(box):
    return [float(value) for value in box.color().rgb()]


def _box_items(box):
    return list(box.items(recurse=False))


def _unsupported_box_reason(box):
    if box.isMinimized(): return 'minimized box'
    if box.parentNetworkBox() is not None: return 'nested box'
    if box.networkBoxes(): return 'box contains nested boxes'
    unsupported = [item.path() for item in _box_items(box) if not isinstance(item, hou.Node)]
    return f'unsupported non-node items: {unsupported[:8]}' if unsupported else None


def _network_group_box_reason(box):
    """Reject unsupported editor items while permitting one governed nesting level."""
    if box.isMinimized(): return 'minimized box'
    unsupported = [item.path() for item in _box_items(box)
                   if not isinstance(item, (hou.Node, hou.NetworkBox))]
    if unsupported: return f'unsupported non-node/non-box items: {unsupported[:8]}'
    parent_box = box.parentNetworkBox()
    if parent_box is not None and parent_box.parentNetworkBox() is not None:
        return 'Network Box nesting deeper than one component container is unsupported'
    if box.networkBoxes() and parent_box is not None:
        return 'a component container cannot itself be nested'
    return None


def _state(box):
    items = _box_items(box)
    if any(not isinstance(item, (hou.Node, hou.NetworkBox)) for item in items):
        raise ValueError(f'{box.path()} contains unsupported editor items')
    owner = _live_owner(box)
    parent_box = box.parentNetworkBox()
    return {
        'identity': int(box.sessionId()), 'name': box.name(),
        'label': box.comment(), 'color': _color(box), 'alpha': float(box.alpha()),
        'auto_fit': bool(box.autoFit()), 'minimized': bool(box.isMinimized()),
        'bounds': _box_rect(box).as_list(), 'selected': bool(box.isSelected()),
        'members': [{'identity': int(item.sessionId()), 'path': item.path()}
                    for item in items if isinstance(item, hou.Node)],
        'nested_boxes': [{'identity': int(item.sessionId()), 'name': item.name()}
                         for item in box.networkBoxes()],
        'parent_box': ({'identity': int(parent_box.sessionId()), 'name': parent_box.name()}
                       if parent_box is not None else None),
        'owner': ({key:value for key,value in owner.items()
                   if key != 'native_object'} if owner is not None else None),
        'service': is_service_box(box),
    }


def _state_mismatches(expected, actual, *, check_identity=True):
    failures = []
    if check_identity and expected['identity'] != actual['identity']:
        failures.append('identity')
    for key in ('name','label','auto_fit','minimized','selected','service'):
        if expected[key] != actual[key]: failures.append(key)
    if expected['owner'] != actual['owner']: failures.append('owner')
    if {row['identity'] for row in expected['members']} != {row['identity'] for row in actual['members']}:
        failures.append('membership')
    if {row['identity'] for row in expected.get('nested_boxes',[])} != {row['identity'] for row in actual.get('nested_boxes',[])}:
        failures.append('nested_boxes')
    if expected.get('parent_box') != actual.get('parent_box'):
        failures.append('parent_box')
    if any(abs(a-b) > 1e-5 for a,b in zip(expected['color'],actual['color'])):
        failures.append('color')
    if abs(expected['alpha']-actual['alpha']) > 1e-5:
        failures.append('alpha')
    if not _rect_close(Rect(*expected['bounds']),Rect(*actual['bounds']),1e-4):
        failures.append('bounds')
    return failures


def _verify_snapshot(snapshot, parent, remapped=()):
    errors = []
    remap_by_old = {row['old_identity']:row['new_identity'] for row in remapped}
    for expected in snapshot['boxes']:
        identity = remap_by_old.get(expected['identity'],expected['identity'])
        box = _box_by_identity(parent,identity)
        if box is None:
            errors.append(f"{expected['name']} missing after restore")
            continue
        adjusted = dict(expected)
        adjusted['nested_boxes'] = [{**row,'identity':remap_by_old.get(row['identity'],row['identity'])}
                                    for row in expected.get('nested_boxes',[])]
        if expected.get('parent_box') is not None:
            adjusted['parent_box'] = {**expected['parent_box'],
                'identity':remap_by_old.get(expected['parent_box']['identity'],expected['parent_box']['identity'])}
        try: failures = _state_mismatches(adjusted,_state(box),check_identity=expected['identity'] not in remap_by_old)
        except Exception as error:
            errors.append(f"{expected['name']} readback: {error}");continue
        if failures: errors.append(f"{expected['name']} restore mismatch: {failures}")
    for expected in snapshot['nodes']:
        node = hou.nodeBySessionId(expected['identity'])
        if node is None or node.path()!=expected['path']:
            errors.append(f"{expected['path']} missing after restore");continue
        if any(abs(a-b)>1e-6 for a,b in zip(expected['position'],node.position())):
            errors.append(f"{expected['path']} position mismatch")
        if bool(node.isSelected())!=expected['selected']:
            errors.append(f"{expected['path']} selection mismatch")
    return errors


def _snapshot(parent, boxes, nodes):
    return {
        'parent_identity': int(parent.sessionId()), 'parent_path': parent.path(),
        'boxes': [_state(box) for box in boxes],
        'nodes': [{'identity': int(node.sessionId()), 'path': node.path(),
                   'position': [float(value) for value in node.position()],
                   'selected': bool(node.isSelected())} for node in nodes],
        'created_box_identities': [], 'removed_box_identities': [],
        'affected_box_identities': [int(box.sessionId()) for box in boxes],
    }


def _restore(snapshot):
    errors, remapped = [], []
    parent = _parent_by_snapshot(snapshot)
    if parent is None:
        return ['parent identity was not restored'], remapped
    created = set(snapshot.get('created_box_identities') or [])
    for identity in created:
        box = _box_by_identity(parent, identity)
        if box is not None:
            try: box.destroy(destroy_contents=False)
            except Exception as error: errors.append(f'destroy created box {identity}: {error}')
        _OWNED_BOXES.pop(('network_box', int(parent.sessionId()), int(identity)), None)
        _SERVICE_BOXES.pop(('network_box', int(parent.sessionId()), int(identity)), None)

    restored = {}
    for state in snapshot['boxes']:
        box = _box_by_identity(parent, state['identity'])
        if box is None:
            same_name = parent.findNetworkBox(state['name'])
            if same_name is not None:
                errors.append(f"same-name replacement blocks recovery: {state['name']}")
                continue
            try:
                box = parent.createNetworkBox(state['name'])
                remapped.append({'old_identity': state['identity'], 'new_identity': int(box.sessionId()),
                                 'name': state['name']})
            except Exception as error:
                errors.append(f"recreate {state['name']}: {error}")
                continue
        restored[state['name']] = box

    # Remove extras first, then add captured nodes/boxes so cross-box moves compose.
    for state in snapshot['boxes']:
        box = restored.get(state['name'])
        if box is None: continue
        wanted = {item['identity'] for item in state['members']}
        for item in _box_items(box):
            if isinstance(item, hou.Node) and int(item.sessionId()) not in wanted:
                try: box.removeItem(item)
                except Exception as error: errors.append(f"{state['name']} remove extra {item.path()}: {error}")
        wanted_boxes = {item['identity'] for item in state.get('nested_boxes',[])}
        for child in list(box.networkBoxes()):
            if int(child.sessionId()) not in wanted_boxes:
                try: box.removeNetworkBox(child)
                except Exception as error: errors.append(f"{state['name']} remove extra box {child.name()}: {error}")
    for state in snapshot['boxes']:
        box = restored.get(state['name'])
        if box is None: continue
        try: box.setAutoFit(False)
        except Exception as error: errors.append(f"{state['name']} disable auto-fit: {error}")
        current = {int(item.sessionId()) for item in _box_items(box) if isinstance(item, hou.Node)}
        for member in state['members']:
            node = hou.nodeBySessionId(member['identity'])
            if node is None or node.path() != member['path']:
                errors.append(f"{state['name']} member identity missing: {member['path']}")
                continue
            if member['identity'] not in current:
                try: box.addItem(node)
                except Exception as error: errors.append(f"{state['name']} add {member['path']}: {error}")
        current_boxes = {int(item.sessionId()) for item in box.networkBoxes()}
        remap_by_old = {row['old_identity']:row['new_identity'] for row in remapped}
        for child_state in state.get('nested_boxes',[]):
            child_identity = remap_by_old.get(child_state['identity'],child_state['identity'])
            child = _box_by_identity(parent, child_identity)
            if child is None or child.name() != child_state['name']:
                errors.append(f"{state['name']} nested box identity missing: {child_state['name']}")
                continue
            if child_identity not in current_boxes:
                try: box.addNetworkBox(child)
                except Exception as error: errors.append(f"{state['name']} add box {child_state['name']}: {error}")
        for action, label in (
            (lambda: box.setComment(state['label']), 'label'),
            (lambda: box.setColor(hou.Color(tuple(state['color']))), 'color'),
            (lambda: box.setAlpha(state['alpha']), 'alpha'),
            (lambda: box.setBounds(hou.BoundingRect(*state['bounds'])), 'bounds'),
            (lambda: box.setMinimized(state['minimized']), 'minimized'),
            (lambda: box.setSelected(state['selected']), 'selection'),
            (lambda: box.setAutoFit(state['auto_fit']), 'auto-fit'),
        ):
            try: action()
            except Exception as error: errors.append(f"{state['name']} restore {label}: {error}")

    for node_state in snapshot['nodes']:
        node = hou.nodeBySessionId(node_state['identity'])
        if node is None or node.path() != node_state['path']:
            errors.append(f"node identity missing: {node_state['path']}")
            continue
        try: node.setPosition(hou.Vector2(*node_state['position']))
        except Exception as error: errors.append(f"{node_state['path']} position: {error}")
        try: node.setSelected(node_state['selected'])
        except Exception as error: errors.append(f"{node_state['path']} selection: {error}")

    # Clear affected live/dead entries, then restore prior classification.
    affected_ids = set(snapshot.get('affected_box_identities') or [])
    affected_ids.update(snapshot.get('created_box_identities') or [])
    affected_ids.update(snapshot.get('removed_box_identities') or [])
    affected_ids.update(item['new_identity'] for item in remapped)
    for key, entry in list(_OWNED_BOXES.items()):
        if key[1] == int(parent.sessionId()) and key[2] in affected_ids:
            _OWNED_BOXES.pop(key, None)
    for state in snapshot['boxes']:
        box = restored.get(state['name'])
        if box is None: continue
        if state['owner'] is not None:
            _OWNED_BOXES[_box_key(box)] = {**state['owner'], 'native_object': box}
        if state['service']:
            _SERVICE_BOXES[_box_key(box)] = box
    errors.extend(_verify_snapshot(snapshot,parent,remapped))
    return errors, remapped


@contextlib.contextmanager
def transaction_journal():
    global _ACTIVE_JOURNAL
    previous = _ACTIVE_JOURNAL
    journal = {'entries': [], 'boxes': 0, 'nodes': 0}
    _ACTIVE_JOURNAL = journal
    try: yield journal
    finally: _ACTIVE_JOURNAL = previous


def _check_journal_capacity(boxes, nodes):
    if _ACTIVE_JOURNAL is None: return
    if _ACTIVE_JOURNAL['boxes'] + boxes > MAX_BOXES or _ACTIVE_JOURNAL['nodes'] + nodes > MAX_NODES:
        raise ValueError('box transaction journal budget exceeded; split the exec before any writes')


def _journal(snapshot, kind):
    if _ACTIVE_JOURNAL is None: return
    _ACTIVE_JOURNAL['entries'].append({'kind': kind, 'snapshot': snapshot})
    existing = {state['identity'] for state in snapshot['boxes']}
    created = set(snapshot.get('created_box_identities') or []) - existing
    _ACTIVE_JOURNAL['boxes'] += len(existing | created)
    _ACTIVE_JOURNAL['nodes'] += len(snapshot['nodes'])


def journal_containing_boxes(nodes, kind='pre_position_boxes'):
    """Capture first-touch box state before another supported verb moves/deletes members."""
    if _ACTIVE_JOURNAL is None:return
    grouped={}
    for node in nodes:
        box=node.parentNetworkBox()
        while box is not None:
            grouped.setdefault(box.parent(),{})[int(box.sessionId())]=box
            box=box.parentNetworkBox()
    snapshots=[]
    for parent,by_id in grouped.items():
        box_rows=list(by_id.values())
        member_rows={int(item.sessionId()):item for box in box_rows for item in box.items(recurse=True)
                     if isinstance(item,hou.Node)}
        snapshots.append(_snapshot(parent,box_rows,list(member_rows.values())))
    box_count=sum(len(row['boxes']) for row in snapshots)
    node_count=sum(len(row['nodes']) for row in snapshots)
    if snapshots:_check_journal_capacity(box_count,node_count)
    for snapshot in snapshots:_journal(snapshot,kind)


def reconcile_transaction(journal):
    """Read-only post-undo verification plus exact typed-registry reconciliation."""
    entries = (journal or {}).get('entries') or []
    errors, baselines, parents, created_so_far, touched = [], {}, {}, set(), set()
    local_remaps = []
    for entry in entries:
        snapshot = entry['snapshot']
        parent_key = (snapshot['parent_identity'],snapshot['parent_path'])
        parents[parent_key] = snapshot
        for state in snapshot['boxes']:
            key = (snapshot['parent_identity'],state['identity'])
            touched.add(key)
            if key not in created_so_far and key not in baselines:
                baselines[key] = (snapshot,state)
        for identity in snapshot.get('created_box_identities') or []:
            key = (snapshot['parent_identity'],identity)
            created_so_far.add(key);touched.add(key)
        for identity in snapshot.get('removed_box_identities') or []:
            touched.add((snapshot['parent_identity'],identity))
        for remap in snapshot.get('local_identity_remaps') or []:
            touched.add((snapshot['parent_identity'],remap['new_identity']))
            local_remaps.append(remap)

    live_baselines = {}
    for key,(snapshot,expected) in baselines.items():
        parent = _parent_by_snapshot(snapshot)
        if parent is None:
            errors.append(f"parent not restored: {snapshot['parent_path']}");continue
        box = _box_by_identity(parent,expected['identity'])
        if box is None:
            errors.append(f"box identity not restored: {expected['name']}#{expected['identity']}");continue
        try:
            actual = _state(box)
            # Authority is reconciled below; compare native presentation only.
            actual['owner'],actual['service'] = expected['owner'],expected['service']
            failures = _state_mismatches(expected,actual)
            if failures: errors.append(f"{expected['name']} native undo mismatch: {failures}")
        except Exception as error:
            errors.append(f"{expected['name']} native undo readback: {error}")
        live_baselines[key] = box
    for parent_identity,identity in created_so_far-set(baselines):
        snapshot = next((item for item in parents.values() if item['parent_identity']==parent_identity),None)
        parent = _parent_by_snapshot(snapshot) if snapshot else None
        if parent is not None and _box_by_identity(parent,identity) is not None:
            errors.append(f'created box identity remained after native undo: {identity}')

    # Registry reconciliation is exact-identity only and creates no user undo.
    for parent_identity,identity in touched:
        key=('network_box',parent_identity,identity)
        _OWNED_BOXES.pop(key,None);_SERVICE_BOXES.pop(key,None)
    for key,(snapshot,expected) in baselines.items():
        box=live_baselines.get(key)
        if box is None:continue
        if expected['owner'] is not None:
            _OWNED_BOXES[_box_key(box)]={**expected['owner'],'native_object':box}
        if expected['service']:
            _SERVICE_BOXES[_box_key(box)]=box
    return {'ok': not errors, 'errors': errors, 'identity_remaps': local_remaps,
            'entry_count': len(entries), 'mode':'post_native_undo_readback'}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _hash(value): return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def _safe_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', value):
        raise ValueError('Network Box name must match [A-Za-z_][A-Za-z0-9_]{0,63}')
    return value


def _label(value):
    if (not isinstance(value, str) or not value.strip() or len(value) > 200
            or any(ord(char) < 32 and char not in '\n\t' for char in value)):
        raise ValueError('Network Box label must be nonempty, at most 200 characters, without control characters')
    return value


def _rgb(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError('color must be an RGB triple')
    result = [float(item) for item in value]
    if any(not math.isfinite(item) or item < 0 or item > 1 for item in result):
        raise ValueError('color components must be finite within [0,1]')
    return result


def _prepare(parent, groups, remove, dry_run, expected_plan, allow_foreign,
             active_owner_session, resolve_node, require_node_owned):
    _validate_allow_foreign(allow_foreign)
    if type(dry_run) is not bool:
        raise ValueError('dry_run must be boolean')
    if not isinstance(groups, (list, tuple)) or len(groups) > MAX_BOXES:
        raise ValueError(f'groups must contain at most {MAX_BOXES} entries')
    if remove is None: remove = []
    if not isinstance(remove, (list, tuple)) or len(remove) > MAX_BOXES:
        raise ValueError(f'remove must contain at most {MAX_BOXES} exact names')
    remove = [_safe_name(name) for name in remove]
    if len(set(remove)) != len(remove): raise ValueError('remove names must be unique')
    if not parent.isNetwork(): raise ValueError(f'{parent.path()} is not a network')
    protected_parent = _service_node_or_ancestor(parent)
    if protected_parent:
        raise ValueError(f'{parent.path()} is inside persistent render service {protected_parent}')
    try:
        if not parent.isEditable(): raise ValueError(f'{parent.path()} is not editable')
    except AttributeError:
        pass
    category = parent.childTypeCategory()
    if category is not None and 'apex' in category.name().lower():
        raise ValueError('APEX Network Boxes are unsupported in v1')

    existing = {box.name(): box for box in parent.networkBoxes()}
    declared_names = {_safe_name(group.get('name')) for group in groups if isinstance(group,dict)}
    if len(declared_names) != len(groups):
        raise ValueError('each group needs a unique valid name')
    normalized, all_nodes, all_child_boxes, target_names = [], {}, {}, set()
    allowed_keys = {'name', 'label', 'role', 'members', 'boxes', 'color'}
    for group in groups:
        if not isinstance(group, dict) or set(group) - allowed_keys or not {'name','label','role'} <= set(group):
            raise ValueError('each group must contain name,label,role and one of members/boxes; optional color only')
        name, label, role = _safe_name(group['name']), _label(group['label']), group['role']
        if name in RESERVED_SERVICE_NAMES:
            raise ValueError(f'{name} is reserved for the persistent render service')
        if name in target_names: raise ValueError(f'duplicate group name: {name}')
        target_names.add(name)
        if role not in ROLE_COLORS: raise ValueError(f'unknown Network Box role: {role}')
        members = group.get('members', [])
        box_names = group.get('boxes', [])
        if not isinstance(members, (list, tuple)) or not isinstance(box_names, (list, tuple)):
            raise ValueError(f'{name}: members/boxes must be lists')
        if bool(members) == bool(box_names):
            raise ValueError(f'{name}: provide exactly one nonempty members or boxes list')
        if role == 'component' and members:
            raise ValueError(f'{name}: component role requires boxes=[existing leaf boxes], not direct node members')
        if box_names and role != 'component':
            raise ValueError(f'{name}: boxes= requires role=component')
        resolved = []
        for item in members:
            node = resolve_node(item)
            if node.parent() != parent:
                raise ValueError(f'{node.path()} is not a direct child of {parent.path()}')
            protected = _service_node_or_ancestor(node)
            if protected:
                raise ValueError(f'{node.path()} belongs to persistent render service {protected}')
            require_node_owned(node, 'network_boxes member', allow_foreign)
            identity = int(node.sessionId())
            if identity in all_nodes:
                raise ValueError(f'{node.path()} appears in multiple groups')
            all_nodes[identity] = node; resolved.append(node)
        resolved_boxes = []
        for child_name in box_names:
            child_name = _safe_name(child_name)
            if child_name == name: raise ValueError(f'{name}: box cannot contain itself')
            if child_name in declared_names:
                raise ValueError(f'{name}: child boxes must already exist; create/layout leaf boxes before component containers')
            child = existing.get(child_name)
            if child is None: raise ValueError(f'{name}: child Network Box does not exist: {child_name}')
            reason = _network_group_box_reason(child)
            if reason: raise ValueError(f'{child.path()} unsupported: {reason}')
            if child.networkBoxes():
                raise ValueError(f'{name}: child {child_name} is already a component container')
            child_items=_box_items(child)
            if not child_items or any(not isinstance(item,hou.Node) for item in child_items):
                raise ValueError(f'{name}: child {child_name} must be a nonempty node-only leaf box')
            _require_box(child, 'network_boxes nested member', active_owner_session, allow_foreign)
            identity = int(child.sessionId())
            if identity in all_child_boxes:
                raise ValueError(f'{child.path()} appears in multiple component containers')
            all_child_boxes[identity] = child; resolved_boxes.append(child)
        color = _rgb(group['color']) if 'color' in group else None
        normalized.append({'name': name, 'label': label, 'role': role,
                           'members': resolved, 'boxes': resolved_boxes, 'color': color})
    if target_names & set(remove): raise ValueError('a box cannot be upserted and removed in one operation')
    for name in remove:
        if name in RESERVED_SERVICE_NAMES:
            raise ValueError(f'{name} is reserved for the persistent render service')
        if name not in existing: raise ValueError(f'Network Box to remove does not exist: {name}')

    affected = {}
    batch_names = target_names | set(remove)
    for group in normalized:
        box = existing.get(group['name'])
        if box is not None:
            reason = _network_group_box_reason(box)
            if reason: raise ValueError(f'{box.path()} unsupported: {reason}')
            _require_box(box, 'network_boxes upsert', active_owner_session, allow_foreign)
            affected[box.name()] = box
        elif parent.node(group['name']) is not None:
            raise ValueError(f"target box name is occupied by a node: {group['name']}")
    for name in remove:
        box = existing[name]
        reason = _network_group_box_reason(box)
        if reason: raise ValueError(f'{box.path()} unsupported: {reason}')
        _require_box(box, 'network_boxes remove', active_owner_session, allow_foreign)
        previous = box.parentNetworkBox()
        if previous is not None and previous.name() not in batch_names:
            raise ValueError(f'{box.path()} is nested in unmentioned component box {previous.name()}; include or remove the parent container')
        affected[name] = box

    for group in normalized:
        for node in group['members']:
            previous = node.parentNetworkBox()
            if previous is None or previous.name() == group['name']: continue
            if previous.name() not in batch_names:
                raise ValueError(f'{node.path()} currently belongs to unmentioned box {previous.name()}; include its complete final membership or remove it')
            reason = _network_group_box_reason(previous)
            if reason: raise ValueError(f'{previous.path()} unsupported: {reason}')
            _require_box(previous, 'network_boxes source membership', active_owner_session, allow_foreign)
            affected[previous.name()] = previous
    for group in normalized:
        for child in group['boxes']:
            previous = child.parentNetworkBox()
            if previous is None or previous.name() == group['name']: continue
            if previous.name() not in batch_names:
                raise ValueError(f'{child.path()} currently belongs to unmentioned component box {previous.name()}; include its complete final boxes list or remove it')
            reason = _network_group_box_reason(previous)
            if reason: raise ValueError(f'{previous.path()} unsupported: {reason}')
            _require_box(previous, 'network_boxes source nesting', active_owner_session, allow_foreign)
            affected[previous.name()] = previous
    if any(is_service_box(box) for box in affected.values()):
        raise ValueError('persistent render-service Network Boxes cannot be grouped, edited or removed')
    for node in all_nodes.values():
        if node.userData('dsh_houdini_owner') == 'render_view_v2':
            raise ValueError(f'{node.path()} belongs to the persistent render service')

    affected_nodes = dict(all_nodes)
    for child in all_child_boxes.values():
        affected[child.name()] = child
    nested_affected={}
    for box in list(affected.values()):
        for child in box.networkBoxes():
            if is_service_box(child):
                raise ValueError(f'{child.path()} belongs to the persistent render service')
            _require_box(child,'network_boxes affected nested member',active_owner_session,allow_foreign)
            nested_affected[child.name()]=child
    affected.update(nested_affected)
    for box in affected.values():
        if is_service_box(box):
            raise ValueError(f'{box.path()} belongs to the persistent render service')
        for item in box.items(recurse=True):
            if isinstance(item, hou.Node):
                protected = _service_node_or_ancestor(item)
                if protected:
                    raise ValueError(f'{item.path()} belongs to persistent render service {protected}')
                require_node_owned(item, 'network_boxes affected member', allow_foreign)
                affected_nodes[int(item.sessionId())] = item
    affected_box_count = len(affected) + len([g for g in normalized if g['name'] not in existing])
    if affected_box_count > MAX_BOXES:
        raise ValueError(f'operation affects more than {MAX_BOXES} boxes')
    if len(affected_nodes) > MAX_NODES:
        raise ValueError(f'operation affects more than {MAX_NODES} nodes')

    state_payload = {
        'schema': SCHEMA, 'generation': _BOX_GENERATION,
        'owner_session': active_owner_session,
        'parent': {'identity': int(parent.sessionId()), 'path': parent.path()},
        'intent': [{'name': row['name'], 'label': row['label'], 'role': row['role'],
                    'members': [int(node.sessionId()) for node in row['members']],
                    'boxes': [int(box.sessionId()) for box in row['boxes']], 'color': row['color']}
                   for row in normalized],
        'remove': remove,
        'boxes': [_state(box) for box in sorted(affected.values(), key=lambda item: item.name())],
        'nodes': [{'identity': identity, 'path': node.path(),
                   'position': [float(value) for value in node.position()],
                   'size': [float(value) for value in node.size()]}
                  for identity, node in sorted(affected_nodes.items())],
        'target_occupancy': {name: {'box': int(existing[name].sessionId()) if name in existing else None,
                                    'node': int(parent.node(name).sessionId()) if parent.node(name) is not None else None}
                             for name in sorted(target_names)},
    }
    plan_sha = _hash(state_payload)
    if not dry_run and expected_plan != plan_sha:
        raise ValueError('stale or missing Network Box plan; preview again with dry_run=True')
    return {'groups': normalized, 'remove': remove, 'existing': existing,
            'affected_boxes': list(affected.values()), 'affected_nodes': list(affected_nodes.values()),
            'affected_box_count':affected_box_count,
            'plan_sha256': plan_sha, 'state_payload': state_payload}


def _would_write(prepared):
    if prepared['remove']: return True
    for group in prepared['groups']:
        box=prepared['existing'].get(group['name'])
        if box is None:return True
        current={int(item.sessionId()) for item in _box_items(box) if isinstance(item,hou.Node)}
        desired={int(node.sessionId()) for node in group['members']}
        current_boxes={int(item.sessionId()) for item in box.networkBoxes()}
        desired_boxes={int(item.sessionId()) for item in group['boxes']}
        if current!=desired or current_boxes!=desired_boxes or box.comment()!=group['label']:return True
        if group['color'] is not None and any(abs(a-b)>1e-6 for a,b in zip(_color(box),group['color'])):
            return True
    return False


def apply_network_boxes(parent, groups, *, remove=None, dry_run=False,
                        expected_plan=None, allow_foreign=None,
                        active_owner_session=None, active_owner_call=None,
                        resolve_node=None, require_node_owned=None):
    try:
        prepared = _prepare(parent, groups, remove, dry_run, expected_plan, allow_foreign,
                            active_owner_session, resolve_node, require_node_owned)
    except BaseException as error:
        raise NetworkBoxOperationError(str(error), {
            'ok':False,'dry_run':bool(dry_run) if type(dry_run) is bool else None,
            'applied':False,'phase':'preflight','scene_writes':0,
            'parent':parent.path(),'restored':True,'restore_errors':[],
            'layout_status':'not_performed',
            'scope':'direct-child nodes plus one component-container Network Box level; preflight made zero scene writes'}) from error
    base = {'ok': True, 'dry_run': bool(dry_run), 'applied': False,
            'phase': 'preview' if dry_run else 'apply', 'scene_writes': 0,
            'plan_sha256': prepared['plan_sha256'], 'parent': parent.path(),
            'layout_status': 'not_performed',
            'scope': 'direct-child nodes plus one component-container Network Box level; grouping/presentation, no node movement or geometry evaluation'}
    if dry_run:
        planned_boxes = []
        for group in prepared['groups']:
            existing = prepared['existing'].get(group['name'])
            current_members = ({int(item.sessionId()) for item in _box_items(existing)
                                if isinstance(item, hou.Node)} if existing is not None else set())
            desired = {int(node.sessionId()) for node in group['members']}
            current_boxes = ({int(item.sessionId()) for item in existing.networkBoxes()}
                             if existing is not None else set())
            desired_boxes = {int(item.sessionId()) for item in group['boxes']}
            if existing is None:
                bounds = _content_bounds(group['members'],group['boxes'])
                color = list(group['color'] or ROLE_COLORS[group['role']])
                color_source = 'explicit' if group['color'] is not None else 'role_default'
            else:
                membership_changed = current_members != desired or current_boxes != desired_boxes
                bounds = (_box_rect(existing) if not membership_changed else
                          union([_box_rect(existing), _content_bounds(group['members'],group['boxes'])]))
                color = list(group['color']) if group['color'] is not None else _color(existing)
                color_source = 'explicit' if group['color'] is not None else 'preserved'
            planned_boxes.append({
                'kind':'network_box','identity':int(existing.sessionId()) if existing is not None else None,
                'name':group['name'],'label':group['label'],'role':group['role'],
                'color':color,'color_source':color_source,
                'members':[node.path() for node in group['members']],
                'boxes':[box.name() for box in group['boxes']],
                'bounds':bounds.as_list()})
        return {**base, 'boxes': planned_boxes,
                'created': [], 'updated': [], 'removed': [], 'unchanged': [],
                'protected_items': []}

    if _would_write(prepared):
        _check_journal_capacity(prepared['affected_box_count'],len(prepared['affected_nodes']))

    snapshot = _snapshot(parent, prepared['affected_boxes'], prepared['affected_nodes'])
    created, updated, removed, unchanged = [], [], [], []
    writes = 0; journaled = False
    try:
        boxes = dict(prepared['existing'])
        for group in prepared['groups']:
            box = boxes.get(group['name'])
            is_new = box is None
            if is_new:
                writes += 1
                box = parent.createNetworkBox(group['name'])
                snapshot['created_box_identities'].append(int(box.sessionId()))
                boxes[group['name']] = box
                if active_owner_session is not None:
                    _OWNED_BOXES[_box_key(box)] = {
                        'session': active_owner_session, 'call': active_owner_call,
                        'parent_identity': int(parent.sessionId()),
                        'name_at_creation': group['name'], 'role': group['role'],
                        'native_object': box}
                writes += 1; box.setAutoFit(False)
            current_members = {int(item.sessionId()): item for item in _box_items(box)
                               if isinstance(item, hou.Node)}
            desired = {int(node.sessionId()): node for node in group['members']}
            current_boxes = {int(item.sessionId()): item for item in box.networkBoxes()}
            desired_boxes = {int(item.sessionId()): item for item in group['boxes']}
            changed = is_new
            for identity, item in current_members.items():
                if identity not in desired:
                    writes += 1; box.removeItem(item); changed = True
            for identity, node in desired.items():
                if identity not in current_members:
                    writes += 1; box.addItem(node); changed = True
            for identity, child in current_boxes.items():
                if identity not in desired_boxes:
                    writes += 1; box.removeNetworkBox(child); changed = True
            for identity, child in desired_boxes.items():
                if identity not in current_boxes:
                    writes += 1; box.addNetworkBox(child); changed = True
            if box.comment() != group['label']:
                writes += 1; box.setComment(group['label']); changed = True
            color_source = 'preserved'
            requested_color = group['color']
            if is_new and requested_color is None:
                requested_color = list(ROLE_COLORS[group['role']]); color_source = 'role_default'
            elif requested_color is not None:
                color_source = 'explicit'
            if requested_color is not None and any(abs(a-b) > 1e-6 for a,b in zip(_color(box), requested_color)):
                writes += 1; box.setColor(hou.Color(tuple(requested_color))); changed = True
            if is_new or set(current_members) != set(desired) or set(current_boxes) != set(desired_boxes):
                target_bounds = _content_bounds(group['members'],group['boxes'])
                if not is_new: target_bounds = union([_box_rect(box), target_bounds])
                if not _rect_close(_box_rect(box), target_bounds):
                    writes += 1; box.setBounds(hou.BoundingRect(*target_bounds.as_list())); changed = True
            (created if is_new else updated if changed else unchanged).append(group['name'])

        for name in prepared['remove']:
            box = boxes[name]
            snapshot['removed_box_identities'].append(int(box.sessionId()))
            key = _box_key(box)
            writes += 1; box.destroy(destroy_contents=False)
            _OWNED_BOXES.pop(key, None); _SERVICE_BOXES.pop(key, None)
            removed.append(name)

        # Verify membership, node positions, and removals without cooking.
        before_positions = {row['identity']: row['position'] for row in snapshot['nodes']}
        before_box_state = {row['name']:row for row in snapshot['boxes']}
        for group in prepared['groups']:
            box = parent.findNetworkBox(group['name'])
            actual = {int(item.sessionId()) for item in _box_items(box) if isinstance(item, hou.Node)}
            expected = {int(node.sessionId()) for node in group['members']}
            if actual != expected: raise RuntimeError(f"membership readback mismatch: {group['name']}")
            actual_boxes = {int(item.sessionId()) for item in box.networkBoxes()}
            expected_boxes = {int(item.sessionId()) for item in group['boxes']}
            if actual_boxes != expected_boxes: raise RuntimeError(f"nested box readback mismatch: {group['name']}")
            if box.comment()!=group['label']:
                raise RuntimeError(f"label readback mismatch: {group['name']}")
            expected_color=(group['color'] if group['color'] is not None else
                            list(ROLE_COLORS[group['role']]) if group['name'] in created else
                            before_box_state[group['name']]['color'])
            if any(abs(a-b)>1e-5 for a,b in zip(_color(box),expected_color)):
                raise RuntimeError(f"color readback mismatch: {group['name']}")
            previous=before_box_state.get(group['name'])
            previous_members={row['identity'] for row in previous['members']} if previous else set()
            previous_boxes={row['identity'] for row in previous.get('nested_boxes',[])} if previous else set()
            expected_bounds=_content_bounds(group['members'],group['boxes'])
            if previous is not None and (previous_members!=expected or previous_boxes!=expected_boxes):
                expected_bounds=union([Rect(*previous['bounds']),expected_bounds])
            elif previous is not None:
                expected_bounds=Rect(*previous['bounds'])
            if not contains(_box_rect(box),expected_bounds,tolerance=1e-4):
                raise RuntimeError(f"bounds readback does not contain planned envelope: {group['name']}")
            if previous is not None and bool(box.isSelected())!=previous['selected']:
                raise RuntimeError(f"selection readback mismatch: {group['name']}")
            expected_status=('owned_current_session' if group['name'] in created and active_owner_session is not None
                             else box_provenance(box,active_owner_session)['status'])
            if group['name'] in created and box_provenance(box,active_owner_session)['status']!=expected_status:
                raise RuntimeError(f"ownership readback mismatch: {group['name']}")
        for name in prepared['remove']:
            if parent.findNetworkBox(name) is not None: raise RuntimeError(f'removal readback mismatch: {name}')
        for node in prepared['affected_nodes']:
            if [float(value) for value in node.position()] != before_positions[int(node.sessionId())]:
                raise RuntimeError(f'grouping moved member node: {node.path()}')
        final_boxes = []
        for group in prepared['groups']:
            box = parent.findNetworkBox(group['name'])
            state = _state(box)
            state['role'] = group['role']
            state['color_source'] = ('explicit' if group['color'] is not None else
                                     'role_default' if group['name'] in created else 'preserved')
            final_boxes.append(state)
        if writes:
            _journal(snapshot, 'network_boxes');journaled=True
        return {**base, 'applied': bool(writes), 'scene_writes': writes,
                'created': created, 'updated': updated, 'removed': removed,
                'unchanged': unchanged, 'boxes': final_boxes, 'protected_items': [],
                'current_state_preserved': True, 'restored': None, 'restore_errors': []}
    except BaseException as error:
        failures=[];remaps=[];restore_exception=None
        try:
            failures, remaps = _restore(snapshot)
        except BaseException as recovery_error:
            restore_exception=str(recovery_error)
            failures.append('recovery raised: '+restore_exception)
        snapshot['local_identity_remaps'] = list(remaps)
        if writes and not journaled:
            try:
                _journal(snapshot, 'network_boxes_failed_compensation');journaled=True
            except BaseException as journal_error:
                failures.append('recovery journal failed: '+str(journal_error))
        raise NetworkBoxOperationError(
            f'network_boxes failed during apply: {error}',
            {**base, 'ok': False, 'phase': 'apply_failure', 'scene_writes': writes,
             'restored': not failures, 'restore_errors': failures,
             'identity_remaps': remaps, 'original_error': str(error),
             'recovery_exception':restore_exception,
             'journaled':journaled}) from error


def _effective_box_rect(box):
    rectangles=[_box_rect(box)]
    rectangles.extend(_node_rect(item) for item in _box_items(box) if isinstance(item,hou.Node))
    rectangles.extend(_effective_box_rect(child) for child in box.networkBoxes())
    return union(rectangles)


def _presentation_item_rect(item, label, dot_footprint):
    """Read one native editor item's bounds; unknown/invalid bounds fail closed."""
    position=item.position();size=item.size();x,y=float(position.x()),float(position.y())
    width,height=float(size.x()),float(size.y())
    if label=='dot' and (width<=0 or height<=0):
        width,height=dot_footprint
        return Rect(x-width/2,y-height/2,x+width/2,y+height/2)
    values=(x,y,width,height)
    if not all(math.isfinite(value) for value in values) or width<0 or height<0:
        raise ValueError(f'invalid fixed {label} bounds')
    return Rect(x,y,x+width,y+height)


def collect_editor_obstacles(parent, *, excluded_node_ids=(), excluded_box_ids=(),
                             dot_footprint=(0.5,0.5)):
    """Enumerate all fixed editor items with complete, measurable bounds."""
    excluded_nodes={int(value) for value in excluded_node_ids}
    excluded_boxes={int(value) for value in excluded_box_ids}
    dot_width,dot_height=map(float,dot_footprint)
    if not all(math.isfinite(value) and value>0 for value in (dot_width,dot_height)):
        raise ValueError('dot footprint must be finite and positive')
    obstacles=[]
    for child in parent.children():
        identity=int(child.sessionId())
        if identity not in excluded_nodes:
            obstacles.append(['node:'+str(identity),_node_rect(child).as_list()])
    for box in parent.networkBoxes():
        identity=int(box.sessionId())
        if identity not in excluded_boxes:
            obstacles.append(['box:'+str(identity),_effective_box_rect(box).as_list()])
    for collection,label in ((parent.stickyNotes(),'note'),(parent.networkDots(),'dot')):
        for item in collection:
            try: rectangle=_presentation_item_rect(item,label,(dot_width,dot_height))
            except Exception as error:
                raise ValueError(f'cannot measure fixed {label}: {error}') from error
            obstacles.append([label+':'+str(int(item.sessionId())),rectangle.as_list()])
    return obstacles


def apply_handoff_layout(parent, box_refs, *, profile='comfortable', dry_run=False,
                         expected_plan=None, active_owner_session=None,
                         node_provenance=None, allow_foreign=None,
                         require_node_owned=None):
    try:
        _validate_allow_foreign(allow_foreign)
        if type(dry_run) is not bool:raise ValueError('dry_run must be boolean')
        if profile!='comfortable':raise ValueError("profile must be 'comfortable'")
        if not isinstance(box_refs,(list,tuple)) or not 1<=len(box_refs)<=MAX_BOXES:
            raise ValueError('boxes must contain 1..64 exact names or identities')
        selected=[]
        for ref in box_refs:
            box=(parent.findNetworkBox(ref) if isinstance(ref,str) else
                 _box_by_identity(parent,ref) if type(ref) is int else None)
            if box is None:raise ValueError(f'unknown Network Box: {ref!r}')
            if box in selected:raise ValueError('handoff boxes must be unique')
            reason=_unsupported_box_reason(box)
            if reason:raise ValueError(f'{box.path()} unsupported: {reason}')
            provenance=box_provenance(box,active_owner_session)
            if provenance['status']=='dsh_service':raise ValueError('render-service box is fixed')
            if active_owner_session is not None:
                _require_box(box,'handoff layout box',active_owner_session,allow_foreign)
            selected.append(box)
        movable_nodes={}
        for box in selected:
            for item in _box_items(box):
                if not isinstance(item,hou.Node):raise ValueError(f'{box.path()} contains unsupported item')
                if item.parent()!=parent:raise ValueError('handoff member must be a direct child')
                if item.parentNetworkBox()!=box:raise ValueError('handoff member belongs to another box')
                if active_owner_session is not None:
                    if require_node_owned is None:raise ValueError('handoff ownership guard unavailable')
                    require_node_owned(item,'handoff layout member',allow_foreign)
                movable_nodes[int(item.sessionId())]=item
        if not movable_nodes:raise ValueError('handoff boxes contain no movable nodes')
        if len(movable_nodes)>MAX_NODES:raise ValueError('handoff exceeds 512 movable nodes')
        node_group={int(item.sessionId()):box.name() for box in selected for item in _box_items(box) if isinstance(item,hou.Node)}
        node_rows=[{'key':str(identity),'group':node_group[identity],'rect':_node_rect(node).as_list()}
                   for identity,node in sorted(movable_nodes.items())]
        group_rows=[{'key':box.name(),'members':[str(int(item.sessionId())) for item in _box_items(box) if isinstance(item,hou.Node)],
                     'rect':_box_rect(box).as_list()} for box in selected]
        edges=[]
        for identity,node in movable_nodes.items():
            for source in node.inputs():
                if source is not None and int(source.sessionId()) in movable_nodes:
                    edges.append([str(int(source.sessionId())),str(identity)])
        skipped=[]
        selected_ids={int(box.sessionId()) for box in selected}
        max_width=max(_node_rect(node).width for node in movable_nodes.values())
        max_height=max(_node_rect(node).height for node in movable_nodes.values())
        dot_footprint=(max_width*.5,max_height)
        obstacles=collect_editor_obstacles(parent,excluded_node_ids=movable_nodes,
            excluded_box_ids=selected_ids,dot_footprint=dot_footprint)
        if len(obstacles)>MAX_NODES:raise ValueError('fixed obstacle budget exceeds 512')
        from dsh_network_layout import plan_handoff
        planned=plan_handoff(node_rows,group_rows,edges,obstacles)
        if not planned['ok']:
            return {'ok':False,'mode':'handoff','dry_run':dry_run,'applied':False,'scene_writes':0,
                    'layout_status':'blocked','reason':planned.get('reason'),'fixed_obstacles':obstacles,
                    'skipped_items':skipped,'restored':True,'restore_errors':[]}
        current={'generation':_BOX_GENERATION,'parent_identity':int(parent.sessionId()),
                 'boxes':[_state(box) for box in selected],'nodes':node_rows,'edges':sorted(edges),
                 'obstacles':sorted(obstacles),'profile':profile,'planned':planned}
        plan_sha=_hash(current)
        if not dry_run and expected_plan!=plan_sha:raise ValueError('stale or missing handoff layout plan; preview again')
    except BaseException as error:
        raise NetworkBoxOperationError(str(error),{'ok':False,'mode':'handoff','dry_run':bool(dry_run) if type(dry_run)is bool else None,
            'applied':False,'phase':'preflight','scene_writes':0,'layout_status':'blocked','restored':True,
            'restore_errors':[],'scope':'explicit owned or individually authorized flat boxes and complete fixed obstacles'}) from error
    planned_evidence={'node_overlap_count':len(planned['node_overlap_pairs']),
          'box_overlap_count':len(planned['box_overlap_pairs']),
          'obstacle_overlap_count':len(planned['obstacle_overlap_pairs']),
          'containment_failures':planned['containment_failures'],
          'clearance_failures':planned['clearance_failures'],
          'required_clearances':planned['required_clearances'],
          'achieved_clearances':planned['achieved_clearances'],
          'minimum_clearances':planned['achieved_clearances']}
    base={'ok':True,'mode':'handoff','dry_run':dry_run,'applied':False,'scene_writes':0,
          'plan_sha256':plan_sha,'profile':profile,'parent':parent.path(),'box_count':len(selected),
          'movable_node_count':len(movable_nodes),'fixed_obstacles':obstacles,'skipped_items':skipped,
          **planned_evidence,'scope':'owned or individually authorized flat boxes; presentation only; no wire crossing claim'}
    if dry_run:return {**base,'layout_status':'planned','node_positions':planned['node_positions'],'box_bounds':planned['box_bounds'],
                       'moved_nodes':[],'changed_boxes':[],'restored':None,'restore_errors':[]}
    will_write=(any(box.autoFit() or not _rect_close(_box_rect(box),Rect(*planned['box_bounds'][box.name()]),1e-4) for box in selected)
                or any(any(abs(a-b)>1e-6 for a,b in zip(node.position(),planned['node_positions'][str(identity)]))
                       for identity,node in movable_nodes.items()))
    if will_write:_check_journal_capacity(len(selected),len(movable_nodes))
    snapshot=_snapshot(parent,selected,list(movable_nodes.values()));writes=0;journaled=False
    moved=[];changed=[]
    try:
        for box in selected:
            if box.autoFit():writes+=1;box.setAutoFit(False)
        for identity,node in movable_nodes.items():
            target=planned['node_positions'][str(identity)]
            current_pos=[float(v) for v in node.position()]
            if any(abs(a-b)>1e-6 for a,b in zip(current_pos,target)):
                writes+=1;_set_node_position(node,target);moved.append(node.path())
        for box in selected:
            target=Rect(*planned['box_bounds'][box.name()])
            if not _rect_close(_box_rect(box),target):
                writes+=1;_set_box_bounds(box,target.as_list());changed.append(box.name())
        for identity,node in movable_nodes.items():
            target=planned['node_positions'][str(identity)]
            if any(abs(a-b)>1e-5 for a,b in zip(node.position(),target)):raise RuntimeError(f'node position readback mismatch: {node.path()}')
        for box in selected:
            target=Rect(*planned['box_bounds'][box.name()])
            if not _rect_close(_box_rect(box),target,1e-4):raise RuntimeError(f'box bounds readback mismatch: {box.name()}')
        actual_obstacles=collect_editor_obstacles(parent,excluded_node_ids=movable_nodes,
            excluded_box_ids=selected_ids,dot_footprint=dot_footprint)
        if _hash(sorted(actual_obstacles))!=_hash(sorted(obstacles)):
            raise RuntimeError('fixed obstacle state changed during handoff apply')
        from dsh_network_layout import evaluate_handoff
        actual=evaluate_handoff(
            {str(identity):_node_rect(node).as_list() for identity,node in movable_nodes.items()},
            {box.name():_box_rect(box).as_list() for box in selected},
            {str(identity):node_group[identity] for identity in movable_nodes},actual_obstacles,
            planned['required_clearances'])
        if not actual['ok']:raise RuntimeError('post-apply handoff evidence failed: '+str(actual['clearance_failures']))
        actual_evidence={'node_overlap_count':len(actual['node_overlap_pairs']),
            'box_overlap_count':len(actual['box_overlap_pairs']),
            'obstacle_overlap_count':len(actual['obstacle_overlap_pairs']),
            'containment_failures':actual['containment_failures'],
            'clearance_failures':actual['clearance_failures'],
            'required_clearances':actual['required_clearances'],
            'achieved_clearances':actual['achieved_clearances'],
            'minimum_clearances':actual['achieved_clearances']}
        if writes:_journal(snapshot,'handoff_layout');journaled=True
        return {**base,**actual_evidence,'fixed_obstacles':actual_obstacles,
                'applied':bool(writes),'scene_writes':writes,'layout_status':'passed','moved_nodes':moved,
                'moved_node_count':len(moved),'changed_boxes':changed,'changed_box_count':len(changed),
                'restored':None,'restore_errors':[]}
    except BaseException as error:
        failures=[];remaps=[]
        try:failures,remaps=_restore(snapshot)
        except BaseException as recovery:failures=['recovery raised: '+str(recovery)]
        snapshot['local_identity_remaps']=remaps
        if writes and not journaled:
            try:_journal(snapshot,'handoff_layout_failed');journaled=True
            except BaseException as journal_error:failures.append('journal failed: '+str(journal_error))
        raise NetworkBoxOperationError('handoff layout apply failed: '+str(error),{**base,'ok':False,'phase':'apply_failure',
            'scene_writes':writes,'layout_status':'restored_after_failure' if not failures else 'recovery_unverified',
            'restored':not failures,'restore_errors':failures,'journaled':journaled}) from error


def apply_component_layout(parent, box_refs, *, profile='comfortable', dry_run=False,
                           expected_plan=None, active_owner_session=None,
                           node_provenance=None, allow_foreign=None,
                           require_node_owned=None):
    """Lay out one-level component containers by moving leaf boxes as units."""
    try:
        _validate_allow_foreign(allow_foreign)
        if type(dry_run) is not bool:raise ValueError('dry_run must be boolean')
        if profile!='comfortable':raise ValueError("profile must be 'comfortable'")
        if not isinstance(box_refs,(list,tuple)) or not 1<=len(box_refs)<=MAX_BOXES:
            raise ValueError('boxes must contain 1..64 exact component container names or identities')
        selected=[];leaf_boxes={};movable_nodes={};leaf_group={}
        for ref in box_refs:
            outer=(parent.findNetworkBox(ref) if isinstance(ref,str) else
                   _box_by_identity(parent,ref) if type(ref) is int else None)
            if outer is None:raise ValueError(f'unknown component Network Box: {ref!r}')
            if outer in selected:raise ValueError('component boxes must be unique')
            reason=_network_group_box_reason(outer)
            if reason:raise ValueError(f'{outer.path()} unsupported: {reason}')
            if outer.parentNetworkBox() is not None:raise ValueError(f'{outer.path()} must be a top-level component container')
            if any(isinstance(item,hou.Node) for item in _box_items(outer)):
                raise ValueError(f'{outer.path()} component container must contain leaf boxes only')
            children=list(outer.networkBoxes())
            if not children:raise ValueError(f'{outer.path()} has no leaf role boxes')
            _require_box(outer,'component layout container',active_owner_session,allow_foreign)
            selected.append(outer)
            for leaf in children:
                if leaf.networkBoxes():raise ValueError(f'{leaf.path()} is not a leaf box')
                if leaf.isMinimized():raise ValueError(f'{leaf.path()} is minimized')
                if leaf.parentNetworkBox()!=outer:raise ValueError(f'{leaf.path()} has inconsistent component parent')
                _require_box(leaf,'component layout leaf',active_owner_session,allow_foreign)
                identity=int(leaf.sessionId())
                if identity in leaf_boxes:raise ValueError(f'{leaf.path()} appears in multiple component containers')
                nodes=[item for item in _box_items(leaf) if isinstance(item,hou.Node)]
                if len(nodes)!=len(_box_items(leaf)) or not nodes:
                    raise ValueError(f'{leaf.path()} must contain direct nodes only')
                leaf_boxes[identity]=leaf;leaf_group[identity]=outer.name()
                for node in nodes:
                    if node.parent()!=parent or node.parentNetworkBox()!=leaf:
                        raise ValueError(f'{node.path()} is not a direct member of {leaf.path()}')
                    if active_owner_session is not None:
                        if require_node_owned is None:raise ValueError('component layout ownership guard unavailable')
                        require_node_owned(node,'component layout member',allow_foreign)
                    node_identity=int(node.sessionId())
                    if node_identity in movable_nodes:raise ValueError(f'{node.path()} appears in multiple leaf boxes')
                    movable_nodes[node_identity]=node
        if len(movable_nodes)>MAX_NODES:raise ValueError('component layout exceeds 512 movable nodes')
        item_rows=[{'key':str(identity),'group':leaf_group[identity],'rect':_box_rect(leaf).as_list()}
                   for identity,leaf in sorted(leaf_boxes.items())]
        group_rows=[{'key':outer.name(),'members':[str(identity) for identity,leaf in sorted(leaf_boxes.items())
                                                  if leaf.parentNetworkBox()==outer],
                     'rect':_box_rect(outer).as_list()} for outer in selected]
        node_leaf={int(node.sessionId()):int(node.parentNetworkBox().sessionId()) for node in movable_nodes.values()}
        edges=set()
        for identity,node in movable_nodes.items():
            target_leaf=node_leaf[identity]
            for source in node.inputs():
                source_identity=int(source.sessionId()) if source is not None else None
                source_leaf=node_leaf.get(source_identity)
                if source_leaf is not None and source_leaf!=target_leaf:
                    edges.add((str(source_leaf),str(target_leaf)))
        selected_box_ids={int(box.sessionId()) for box in selected}|set(leaf_boxes)
        max_width=max(_box_rect(box).width for box in leaf_boxes.values())
        max_height=max(_box_rect(box).height for box in leaf_boxes.values())
        obstacles=collect_editor_obstacles(parent,excluded_node_ids=movable_nodes,
            excluded_box_ids=selected_box_ids,dot_footprint=(max_width*.25,max_height*.25))
        if len(obstacles)>MAX_NODES:raise ValueError('fixed obstacle budget exceeds 512')
        from dsh_network_layout import plan_handoff
        planned=plan_handoff(item_rows,group_rows,sorted(edges),obstacles)
        if not planned['ok']:
            return {'ok':False,'mode':'component','dry_run':dry_run,'applied':False,'scene_writes':0,
                    'layout_status':'blocked','reason':planned.get('reason'),'fixed_obstacles':obstacles,
                    'restored':True,'restore_errors':[]}
        current={'generation':_BOX_GENERATION,'parent_identity':int(parent.sessionId()),
                 'containers':[_state(box) for box in selected],
                 'leaves':[_state(box) for box in leaf_boxes.values()],
                 'nodes':[{'identity':identity,'path':node.path(),'position':[float(v) for v in node.position()]}
                          for identity,node in sorted(movable_nodes.items())],
                 'edges':sorted(edges),'obstacles':sorted(obstacles),'profile':profile,'planned':planned}
        plan_sha=_hash(current)
        if not dry_run and expected_plan!=plan_sha:raise ValueError('stale or missing component layout plan; preview again')
    except BaseException as error:
        raise NetworkBoxOperationError(str(error),{'ok':False,'mode':'component',
            'dry_run':bool(dry_run) if type(dry_run)is bool else None,'applied':False,'phase':'preflight',
            'scene_writes':0,'layout_status':'blocked','restored':True,'restore_errors':[],
            'scope':'explicit one-level component containers, their leaf boxes and complete fixed obstacles'}) from error
    planned_evidence={'leaf_box_overlap_count':len(planned['node_overlap_pairs']),
        'component_box_overlap_count':len(planned['box_overlap_pairs']),
        'obstacle_overlap_count':len(planned['obstacle_overlap_pairs']),
        'containment_failures':planned['containment_failures'],'clearance_failures':planned['clearance_failures'],
        'required_clearances':planned['required_clearances'],'achieved_clearances':planned['achieved_clearances'],
        'minimum_clearances':planned['achieved_clearances']}
    base={'ok':True,'mode':'component','dry_run':dry_run,'applied':False,'scene_writes':0,
        'plan_sha256':plan_sha,'profile':profile,'parent':parent.path(),'component_box_count':len(selected),
        'leaf_box_count':len(leaf_boxes),'movable_node_count':len(movable_nodes),'fixed_obstacles':obstacles,
        **planned_evidence,'scope':'one component-container level; moves leaf boxes and their nodes as units; presentation only'}
    if dry_run:
        return {**base,'layout_status':'planned','leaf_box_positions':planned['node_positions'],
                'component_box_bounds':planned['box_bounds'],'moved_nodes':[],'moved_leaf_boxes':[],
                'changed_component_boxes':[],'restored':None,'restore_errors':[]}
    will_write=(any(any(abs(a-b)>1e-6 for a,b in zip(_box_rect(leaf).as_list()[:2],planned['node_positions'][str(identity)]))
                    for identity,leaf in leaf_boxes.items())
                or any(not _rect_close(_box_rect(box),Rect(*planned['box_bounds'][box.name()]),1e-4) for box in selected))
    all_boxes=selected+list(leaf_boxes.values())
    if will_write:_check_journal_capacity(len(all_boxes),len(movable_nodes))
    snapshot=_snapshot(parent,all_boxes,list(movable_nodes.values()));writes=0;journaled=False
    moved_nodes=[];moved_leaves=[];changed_components=[]
    try:
        for identity,leaf in leaf_boxes.items():
            target=planned['node_positions'][str(identity)];current_rect=_box_rect(leaf)
            dx,dy=target[0]-current_rect.min_x,target[1]-current_rect.min_y
            if abs(dx)<=1e-6 and abs(dy)<=1e-6:continue
            for node in _box_items(leaf):
                position=node.position();writes+=1
                _set_node_position(node,[float(position.x())+dx,float(position.y())+dy]);moved_nodes.append(node.path())
            writes+=1;_set_box_bounds(leaf,current_rect.translated(dx,dy).as_list());moved_leaves.append(leaf.name())
        for outer in selected:
            target=Rect(*planned['box_bounds'][outer.name()])
            if not _rect_close(_box_rect(outer),target):
                writes+=1;_set_box_bounds(outer,target.as_list());changed_components.append(outer.name())
        for identity,leaf in leaf_boxes.items():
            target=planned['node_positions'][str(identity)]
            if any(abs(a-b)>1e-5 for a,b in zip(_box_rect(leaf).as_list()[:2],target)):
                raise RuntimeError(f'leaf box position readback mismatch: {leaf.name()}')
            if any(node.parentNetworkBox()!=leaf for node in _box_items(leaf)):
                raise RuntimeError(f'leaf membership changed: {leaf.name()}')
        for outer in selected:
            if not _rect_close(_box_rect(outer),Rect(*planned['box_bounds'][outer.name()]),1e-4):
                raise RuntimeError(f'component bounds readback mismatch: {outer.name()}')
        actual_obstacles=collect_editor_obstacles(parent,excluded_node_ids=movable_nodes,
            excluded_box_ids=selected_box_ids,dot_footprint=(max_width*.25,max_height*.25))
        if _hash(sorted(actual_obstacles))!=_hash(sorted(obstacles)):
            raise RuntimeError('fixed obstacle state changed during component layout apply')
        from dsh_network_layout import evaluate_handoff
        actual=evaluate_handoff(
            {str(identity):_box_rect(leaf).as_list() for identity,leaf in leaf_boxes.items()},
            {outer.name():_box_rect(outer).as_list() for outer in selected},
            {str(identity):leaf_group[identity] for identity in leaf_boxes},actual_obstacles,
            planned['required_clearances'])
        if not actual['ok']:raise RuntimeError('post-apply component layout failed: '+str(actual['clearance_failures']))
        actual_evidence={'leaf_box_overlap_count':len(actual['node_overlap_pairs']),
            'component_box_overlap_count':len(actual['box_overlap_pairs']),
            'obstacle_overlap_count':len(actual['obstacle_overlap_pairs']),
            'containment_failures':actual['containment_failures'],'clearance_failures':actual['clearance_failures'],
            'required_clearances':actual['required_clearances'],'achieved_clearances':actual['achieved_clearances'],
            'minimum_clearances':actual['achieved_clearances']}
        if writes:_journal(snapshot,'component_layout');journaled=True
        return {**base,**actual_evidence,'fixed_obstacles':actual_obstacles,'applied':bool(writes),
                'scene_writes':writes,'layout_status':'passed','moved_nodes':moved_nodes,
                'moved_node_count':len(moved_nodes),'moved_leaf_boxes':moved_leaves,
                'moved_leaf_box_count':len(moved_leaves),'changed_component_boxes':changed_components,
                'changed_component_box_count':len(changed_components),'restored':None,'restore_errors':[]}
    except BaseException as error:
        failures=[];remaps=[]
        try:failures,remaps=_restore(snapshot)
        except BaseException as recovery:failures=['recovery raised: '+str(recovery)]
        snapshot['local_identity_remaps']=remaps
        if writes and not journaled:
            try:_journal(snapshot,'component_layout_failed');journaled=True
            except BaseException as journal_error:failures.append('journal failed: '+str(journal_error))
        raise NetworkBoxOperationError('component layout apply failed: '+str(error),{**base,'ok':False,
            'phase':'apply_failure','scene_writes':writes,
            'layout_status':'restored_after_failure' if not failures else 'recovery_unverified',
            'restored':not failures,'restore_errors':failures,'journaled':journaled}) from error


def prepare_parent_deletion(node, *, active_owner_session, allow_foreign,
                            require_node_owned):
    boxes, nodes, seen, destroyed = [], [], set(), set()
    def include(box,will_destroy=False):
        key=_box_key(box)
        if key in seen:
            if will_destroy:destroyed.add(key)
            return
        seen.add(key)
        if will_destroy:destroyed.add(key)
        reason = _network_group_box_reason(box)
        if reason: raise ValueError(f'{box.path()} blocks deletion: {reason}')
        if is_service_box(box):
            raise ValueError(f'{box.path()} belongs to the persistent render service')
        _require_box(box, 'delete_node containing Network Box', active_owner_session, allow_foreign)
        for item in _box_items(box):
            if isinstance(item,hou.Node):
                protected=_service_node_or_ancestor(item)
                if protected:
                    raise ValueError(f'{item.path()} belongs to persistent render service {protected}')
                nodes.append(item)
        boxes.append(box)
    containing=node.parentNetworkBox()
    while containing is not None:
        include(containing,False)
        containing=containing.parentNetworkBox()
    networks = [node] if node.isNetwork() else []
    networks.extend(child for child in node.allSubChildren() if child.isNetwork())
    for parent in networks:
        current = list(parent.networkBoxes())
        for box in current:include(box,True)
    if not boxes: return None
    _check_journal_capacity(len(boxes), len({int(item.sessionId()) for item in nodes}))
    by_parent = {}
    for box in boxes: by_parent.setdefault(box.parent(), []).append(box)
    snapshots=[]
    for parent,rows in by_parent.items():
        snapshot=_snapshot(parent,rows,[item for item in nodes if item.parent()==parent])
        snapshot['delete_destroyed_box_identities']=[int(box.sessionId()) for box in rows if _box_key(box) in destroyed]
        snapshots.append(snapshot)
    return snapshots


def commit_parent_deletion(snapshots):
    for snapshot in snapshots or []:
        destroyed=set(snapshot.get('delete_destroyed_box_identities') or [])
        snapshot['removed_box_identities'] = list(destroyed)
        for state in snapshot['boxes']:
            if state['identity'] not in destroyed:continue
            key = ('network_box', snapshot['parent_identity'], state['identity'])
            _OWNED_BOXES.pop(key, None); _SERVICE_BOXES.pop(key, None)
        _journal(snapshot, 'delete_node_boxes')
