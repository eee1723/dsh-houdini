"""Explicit Network Editor notes, independent identity ownership and recovery."""
from __future__ import annotations

import contextlib
import math
import os
import re

import hou
from dsh_network_boxes import collect_editor_obstacles, _service_node_or_ancestor
from dsh_network_layout import Rect


class NetworkNoteOperationError(RuntimeError):
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = evidence


if globals().get('_NOTE_REGISTRY_PID') != os.getpid():
    _NOTE_REGISTRY_PID = os.getpid()
    _OWNED_NOTES = {}
_ACTIVE_JOURNAL = None
DEFAULT_SIZE = (6.0, 3.0)
DEFAULT_COLOR = (1.0, 0.97, 0.52)
SCOPE = 'explicit Sticky Note presentation only; no cooking, wiring or node changes'


def _key(note):
    return ('sticky_note', int(note.parent().sessionId()), int(note.sessionId()))


def _owner(note):
    entry = _OWNED_NOTES.get(_key(note))
    if entry is not None and entry['native_object'] == note:
        return entry
    return None


def note_provenance(note, active_owner_session=None):
    entry = _owner(note)
    status = ('owned_current_session' if entry and entry['session'] == active_owner_session
              else 'owned_other_session' if entry else 'foreign')
    return {'kind': 'sticky_note', 'identity': int(note.sessionId()),
            'parent_identity': int(note.parent().sessionId()), 'status': status,
            'runtime_owner': {k: v for k, v in entry.items() if k != 'native_object'} if entry else None}


def _require_note(note, active_owner_session, allow_foreign):
    service = _service_node_or_ancestor(note.parent())
    if service:
        raise ValueError(f'{service} belongs to the persistent render service; notes cannot be modified')
    if active_owner_session is None or note_provenance(note, active_owner_session)['status'] == 'owned_current_session':
        return
    if allow_foreign:
        print(f'[ownership] foreign-sticky-note exemption: {note.path()} — {allow_foreign.strip()}')
        return
    raise ValueError(f'ownership guard: network_notes refused for foreign Sticky Note {note.path()}; '
                     'names, text and parent ownership do not establish note ownership. '
                     'Use allow_foreign only for a user-authorized note change.')


def _by_identity(parent, identity):
    return next((note for note in parent.stickyNotes() if int(note.sessionId()) == identity), None)


def _state(note):
    entry = _owner(note)
    box = note.parentNetworkBox()
    return {'name': note.name(), 'identity': int(note.sessionId()), 'text': note.text(),
            'position': list(map(float, note.position())), 'size': list(map(float, note.size())),
            'color': list(map(float, note.color().rgb())),
            'text_color': list(map(float, note.textColor().rgb())), 'text_size': float(note.textSize()),
            'minimized': bool(note.isMinimized()), 'draw_background': bool(note.drawBackground()),
            'selected': bool(note.isSelected()),
            'parent_box': int(box.sessionId()) if box is not None else None,
            'owner': {k: v for k, v in entry.items() if k != 'native_object'} if entry else None}


def _row(note, active_owner_session):
    value = _state(note)
    return {k: value[k] for k in ('name', 'identity', 'text', 'position', 'size', 'color', 'minimized')} | {
        'path': note.path(), 'provenance': note_provenance(note, active_owner_session)}


def list_notes(parent, active_owner_session=None):
    return [_row(note, active_owner_session) for note in sorted(parent.stickyNotes(), key=lambda item: item.name())]


def _same(left, right):
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(abs(a - b) <= 1e-5 for a, b in zip(left, right))
    return left == right


def _set_value(note, field, value):
    if field == 'text': note.setText(value)
    elif field == 'position': note.setPosition(hou.Vector2(*value))
    elif field == 'size': note.setSize(hou.Vector2(*value))
    elif field == 'color': note.setColor(hou.Color(value))


def _restore(snapshot):
    """Compensate explicit identities; recreation is reported, never silently adopted."""
    parent = hou.nodeBySessionId(snapshot['parent_identity'])
    if parent is None:
        if not snapshot['notes']:
            for identity in snapshot['created']:
                _OWNED_NOTES.pop(('sticky_note', snapshot['parent_identity'], identity), None)
            return {'ok': True, 'errors': [], 'identity_remaps': []}
        return {'ok': False, 'errors': ['note parent identity is missing'], 'identity_remaps': []}
    errors, remaps = [], []
    for identity in snapshot['created']:
        note = _by_identity(parent, identity)
        if note is not None:
            try: note.destroy()
            except Exception as error: errors.append(f'destroy created note {identity}: {error}')
        _OWNED_NOTES.pop(('sticky_note', int(parent.sessionId()), identity), None)
    for expected in snapshot['notes']:
        note = _by_identity(parent, expected['identity'])
        if note is None:
            if parent.findStickyNote(expected['name']) is not None:
                errors.append(f'same-name replacement blocks note recovery: {expected["name"]}')
                continue
            try:
                note = parent.createStickyNote(expected['name'])
                remaps.append({'old_identity': expected['identity'], 'new_identity': int(note.sessionId()),
                               'name': expected['name']})
            except Exception as error:
                errors.append(f'recreate {expected["name"]}: {error}')
                continue
        if note.name() != expected['name']:
            errors.append(f'note identity changed name: {expected["name"]}')
            continue
        setters = {'text': note.setText, 'position': lambda v: note.setPosition(hou.Vector2(*v)),
                   'size': lambda v: note.setSize(hou.Vector2(*v)), 'color': lambda v: note.setColor(hou.Color(v)),
                   'text_color': lambda v: note.setTextColor(hou.Color(v)), 'text_size': note.setTextSize,
                   'minimized': note.setMinimized, 'draw_background': note.setDrawBackground,
                   'selected': note.setSelected}
        try: actual = _state(note)
        except Exception as error:
            errors.append(f'{expected["name"]} restore readback: {error}')
            continue
        for field, setter in setters.items():
            if not _same(expected[field], actual[field]):
                try: setter(expected[field])
                except Exception as error: errors.append(f'{expected["name"]} restore {field}: {error}')
        _OWNED_NOTES.pop(('sticky_note', int(parent.sessionId()), expected['identity']), None)
        if expected['owner'] is not None:
            _OWNED_NOTES[_key(note)] = {**expected['owner'], 'native_object': note}
        else:
            _OWNED_NOTES.pop(_key(note), None)
        try:
            actual = _state(note)
            bad = [field for field in (*setters, 'parent_box', 'owner') if not _same(expected[field], actual[field])]
            if bad: errors.append(f'{expected["name"]} note restore mismatch: {bad}')
        except Exception as error: errors.append(f'{expected["name"]} restore readback: {error}')
    return {'ok': not errors, 'errors': errors, 'identity_remaps': remaps}


@contextlib.contextmanager
def transaction_journal():
    global _ACTIVE_JOURNAL
    previous = _ACTIVE_JOURNAL
    journal = {'entries': []}
    _ACTIVE_JOURNAL = journal
    try: yield journal
    finally: _ACTIVE_JOURNAL = previous


def reconcile_transaction(journal):
    """Merge first-touch baselines, then verify/compensate after this exec failed."""
    parents, created, baselines, local_remaps = {}, {}, {}, []
    for snapshot in journal.get('entries', []):
        parent_id = snapshot['parent_identity']
        parents[parent_id] = snapshot
        created.setdefault(parent_id, set())
        baselines.setdefault(parent_id, {})
        for state in snapshot['notes']:
            identity = state['identity']
            if identity not in created[parent_id]:
                baselines[parent_id].setdefault(identity, state)
        created[parent_id].update(snapshot['created'])
        for remap in snapshot.get('local_identity_remaps', []):
            created[parent_id].add(remap['new_identity'])
            local_remaps.append(remap)
    errors, remaps = [], []
    for parent_id, snapshot in parents.items():
        restored = _restore({'parent_identity': parent_id,
                             'notes': list(baselines[parent_id].values()),
                             'created': sorted(created[parent_id] - set(baselines[parent_id]))})
        errors.extend(restored['errors']); remaps.extend(restored['identity_remaps'])
    return {'ok': not errors, 'entry_count': len(journal.get('entries', [])), 'errors': errors,
            'identity_remaps': local_remaps + remaps,
            'scope': 'recorded Sticky Note presentation only; recreated notes have reported new identities'}


def prepare_parent_deletion(node, *, active_owner_session, allow_foreign):
    """Node deletion destroys editor items too; parent authority does not own them."""
    networks = [node] if node.isNetwork() else []
    networks.extend(child for child in node.allSubChildren() if child.isNetwork())
    snapshots = []
    for parent in networks:
        current = list(parent.stickyNotes())
        for note in current:
            _require_note(note, active_owner_session, allow_foreign)
        if current:
            snapshots.append({'parent_identity': int(parent.sessionId()), 'parent_path': parent.path(),
                              'notes': [_state(note) for note in current], 'created': [],
                              'deleted_with_parent': True})
    return snapshots


def commit_parent_deletion(snapshots):
    for snapshot in snapshots or []:
        for state in snapshot['notes']:
            _OWNED_NOTES.pop(('sticky_note', snapshot['parent_identity'], state['identity']), None)
        if _ACTIVE_JOURNAL is not None:
            _ACTIVE_JOURNAL['entries'].append(snapshot)


def _vector(value, length, label, *, positive=False, color=False):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError(f'{label} must contain {length} numbers')
    result = [float(item) for item in value]
    if any(not math.isfinite(item) for item in result):
        raise ValueError(f'{label} must contain finite numbers')
    if positive and any(item <= 0 for item in result):
        raise ValueError(f'{label} must be positive')
    if color and any(not 0 <= item <= 1 for item in result):
        raise ValueError(f'{label} RGB must be between 0 and 1')
    return result


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', value):
        raise ValueError('note name must be a nonempty native ASCII item name')
    return value


def apply_network_notes(parent, notes=None, *, remove=None, active_owner_session=None,
                        active_owner_call=None, allow_foreign=None):
    """List or locally upsert/remove exact notes; no implicit Network Box membership."""
    writes = 0
    try:
        if not isinstance(parent, hou.Node) or not parent.isNetwork():
            raise ValueError('parent must be an existing network node')
        if allow_foreign is not None and (not isinstance(allow_foreign, str) or not allow_foreign.strip()):
            raise ValueError('allow_foreign must be a nonempty explicit authorization reason or None')
        if notes is None and remove is None:
            return {'ok': True, 'parent': parent.path(), 'scene_writes': 0,
                    'notes': list_notes(parent, active_owner_session), 'scope': SCOPE}
        if _service_node_or_ancestor(parent):
            raise ValueError('network_notes cannot modify the persistent render service or its descendants')
        notes = [] if notes is None else notes
        remove = [] if remove is None else remove
        if not isinstance(notes, (list, tuple)) or not isinstance(remove, (list, tuple)):
            raise ValueError('notes and remove must be lists')
        if len(notes) + len(remove) > 64:
            raise ValueError('a batch supports at most 64 explicit note targets')
        existing = {note.name(): note for note in parent.stickyNotes()}
        prepared, names, touched = [], set(), []
        obstacles = [Rect(*bounds) for _name_value, bounds in collect_editor_obstacles(parent)]
        for row in notes:
            if not isinstance(row, dict) or not {'name', 'text'} <= set(row) or set(row) - {'name','text','position','size','color'}:
                raise ValueError('note entries require name/text and optional position/size/color')
            name = _name(row['name'])
            if name in names: raise ValueError(f'duplicate note target: {name}')
            names.add(name)
            text = row['text']
            if not isinstance(text, str) or not text.strip() or len(text) > 4096 or '\x00' in text:
                raise ValueError('note text must be nonempty, at most 4096 characters, without NUL')
            note = existing.get(name)
            if note is not None:
                _require_note(note, active_owner_session, allow_foreign)
                if note.parentNetworkBox() is not None:
                    raise ValueError(f'{name} is inside a Network Box; this note operation does not restore box membership/bounds')
                touched.append(note)
                values = _state(note)
            else:
                if parent.item(name) is not None:
                    raise ValueError(f'native item name is already in use: {name}')
                values = {'size': list(DEFAULT_SIZE), 'color': list(DEFAULT_COLOR)}
            values = {field: values[field] for field in ('position', 'size', 'color') if field in values}
            values['text'] = text
            for field, length in (('position', 2), ('size', 2), ('color', 3)):
                if field in row:
                    values[field] = _vector(row[field], length, field, positive=field == 'size', color=field == 'color')
            if 'position' not in values:
                x = max((obstacle.max_x for obstacle in obstacles), default=-1.0) + 1.0
                y = max((obstacle.max_y for obstacle in obstacles), default=values['size'][1]) - values['size'][1]
                values['position'] = [x, y]
            x, y = values['position']; width, height = values['size']
            obstacles.append(Rect(x, y, x + width, y + height))
            prepared.append((name, note, values))
        removed_notes = []
        for name in remove:
            name = _name(name)
            if name in names: raise ValueError(f'duplicate or conflicting note target: {name}')
            names.add(name)
            note = existing.get(name)
            if note is None: raise ValueError(f'note does not exist: {name}')
            _require_note(note, active_owner_session, allow_foreign)
            if note.parentNetworkBox() is not None:
                raise ValueError(f'{name} is inside a Network Box; note removal does not restore box membership/bounds')
            removed_notes.append(note); touched.append(note)
        snapshot = {'parent_identity': int(parent.sessionId()), 'parent_path': parent.path(),
                    'notes': [_state(note) for note in touched], 'created': []}
    except Exception as error:
        raise NetworkNoteOperationError(str(error), {'ok': False, 'phase': 'preflight', 'scene_writes': 0,
                                                    'scope': SCOPE}) from error
    created, updated, unchanged, removed = [], [], [], []
    try:
        for name, note, values in prepared:
            is_new = note is None
            if is_new:
                writes += 1
                note = parent.createStickyNote(name)
                snapshot['created'].append(int(note.sessionId()))
                if active_owner_session is not None:
                    _OWNED_NOTES[_key(note)] = {'session': active_owner_session, 'call': active_owner_call,
                                               'name_at_creation': name, 'native_object': note}
                created.append(name)
            current = _state(note)
            changed = False
            for field, value in values.items():
                if not _same(current[field], value):
                    writes += 1; _set_value(note, field, value); changed = True
            actual = _state(note)
            if any(not _same(actual[field], value) for field, value in values.items()):
                raise RuntimeError(f'{name} note write readback mismatch')
            if not is_new: (updated if changed else unchanged).append(name)
        for note in removed_notes:
            name = note.name(); key = _key(note)
            writes += 1; note.destroy(); _OWNED_NOTES.pop(key, None); removed.append(name)
        if writes and _ACTIVE_JOURNAL is not None:
            _ACTIVE_JOURNAL['entries'].append(snapshot)
        return {'ok': True, 'parent': parent.path(), 'scene_writes': writes,
                'created': created, 'updated': updated, 'removed': removed, 'unchanged': unchanged,
                'notes': list_notes(parent, active_owner_session), 'scope': SCOPE}
    except Exception as error:
        recovery = _restore(snapshot)
        if recovery['identity_remaps']: snapshot['local_identity_remaps'] = recovery['identity_remaps']
        if writes and _ACTIVE_JOURNAL is not None:
            _ACTIVE_JOURNAL['entries'].append(snapshot)
        raise NetworkNoteOperationError(f'network_notes failed: {error}; restored={recovery["ok"]}',
            {'ok': False, 'phase': 'apply', 'scene_writes': writes, 'restored': recovery['ok'],
             'restore_errors': recovery['errors'], 'identity_remaps': recovery['identity_remaps'], 'scope': SCOPE}) from error
