"""Single owner of native node identities and causal restoration records.

Only the serialized Bridge actor grants automatic mutation authority. Durable
userData, paths and parent networks are audit information, never ownership.
Consumers use scoped journals and detached snapshots; no other module writes
the registry. Native conversion and Undo reconciliation live beside that state.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
from types import MappingProxyType
from dataclasses import dataclass
import hou
import dsh_node_access
import dsh_service_constants


_TASK_OWNER_KEY = "dsh_houdini_task_owner"


_TASK_OWNER_CALL_KEY = "dsh_houdini_created_by_call"


_ACTIVE_OWNER_SESSION: str | None = None


_ACTIVE_OWNER_CALL: str | None = None


if globals().get('_OWNED_NODE_PID') != os.getpid():
    _OWNED_NODE_PID = os.getpid()
    _OWNED_NODE_SESSIONS: dict[int, dict] = {}


_CREATION_JOURNAL = None


def current_session():
    """Trusted actor for this serialized Bridge call, never a path-derived owner."""
    return _ACTIVE_OWNER_SESSION


def current_call():
    return _ACTIVE_OWNER_CALL


def records():
    """Detached diagnostic copy. Callers cannot mutate the identity registry."""
    return {identity: dict(entry) for identity, entry in _OWNED_NODE_SESSIONS.items()}


def clear_for_scene_load():
    """A native Open/New ends every runtime identity's causal scope."""
    _OWNED_NODE_SESSIONS.clear()


def restore_checkpoint(mapping, session, marker_key):
    """Only the recovery actor's verified load mapping may restore ownership."""
    checked = []
    for identity, row in mapping:
        node = hou.nodeBySessionId(identity)
        if (node is None or row['owner']['session'] != session
                or node.userData(marker_key) != row['node_id']
                or node.type().name() != row['type']
                or node.type().category().name() != row['category']
                or node.userData(dsh_service_constants._RENDER_OWNER_KEY) == dsh_service_constants._RENDER_OWNER_VALUE
                or (identity in _OWNED_NODE_SESSIONS and _OWNED_NODE_SESSIONS[identity] != row['owner'])):
            raise RuntimeError('Checkpoint node changed before ownership activation')
        checked.append((identity, dict(row['owner'])))
    _OWNED_NODE_SESSIONS.update(checked)


def forget(identity):
    """Retire an exact identity after its native destruction."""
    _OWNED_NODE_SESSIONS.pop(int(identity), None)


@dataclass(frozen=True)
class OwnershipSnapshot:
    """Immutable registry and causal live slots captured before an operation."""
    records: object
    alive: object


def snapshot(*, include_live=False):
    """Only the outer Undo boundary observes live paths, once per edit batch.

    Local creation cleanup needs registration alone; do not issue HOM lookups
    over every existing node each time a new node is constructed.
    """
    records = MappingProxyType({identity: MappingProxyType(dict(entry))
        for identity, entry in _OWNED_NODE_SESSIONS.items()})
    alive = {identity: (records[identity], node.path()) for identity in records
        if (node := hou.nodeBySessionId(identity)) is not None} if include_live else {}
    return OwnershipSnapshot(records, MappingProxyType(alive))


def restore(snapshot):
    """Restore registration only; does not claim that native scene Undo succeeded."""
    _OWNED_NODE_SESSIONS.clear()
    _OWNED_NODE_SESSIONS.update({identity: dict(entry) for identity, entry in snapshot.records.items()})


def restore_after_undo(snapshot, created, *, exclude_ids):
    """Reconcile one confirmed native Undo; preserve exact cleanup/adoption rules."""
    restore(snapshot)
    removed = _cleanup_failed_creations(created, snapshot.records)
    reconciled = _reconcile_undo_resurrected(snapshot.alive, exclude_ids=exclude_ids)
    return removed, reconciled


def capture_identity(node):
    """Immutable provenance captured before an explicit native type conversion."""
    identity = int(node.sessionId())
    entry = _OWNED_NODE_SESSIONS.get(identity)
    return identity, MappingProxyType(dict(entry)) if entry is not None else None


def transfer_identity(captured, node):
    """Transfer the captured root only. Foreign exemptions never adopt children."""
    source_identity, owner = captured
    if owner is None:
        return
    identity = int(node.sessionId())
    _OWNED_NODE_SESSIONS[identity] = dict(owner)
    if _CREATION_JOURNAL is not None and source_identity in _CREATION_JOURNAL:
        _CREATION_JOURNAL.add(identity)
    if hou.nodeBySessionId(source_identity) is None:
        forget(source_identity)


@contextlib.contextmanager
def track_created_nodes():
    """Retain exact created identities across nested module/provenance cleanup."""
    global _CREATION_JOURNAL
    previous = _CREATION_JOURNAL
    created = set()
    _CREATION_JOURNAL = created
    try:
        yield created
    finally:
        _CREATION_JOURNAL = previous
        if previous is not None:
            previous.update(created)


def _cleanup_failed_creations(created, ownership_before):
    removed = []
    # Never infer ownership from paths or an agent-created parent. A partial
    # shelf/undo recovery can resurrect a registered identity after its registry
    # entry was removed; only identities recorded in this call are eligible.
    with hou.undos.disabler():
        for node_id in sorted(created - set(ownership_before), reverse=True):
            node = hou.nodeBySessionId(node_id)
            if node is None:continue
            descendants = node.allSubChildren()
            if any(n.sessionId() not in created for n in descendants):
                raise RuntimeError(f'rollback cleanup refused foreign descendants of {node.path()}')
            removed.append(node.path())
            node.destroy()
            _OWNED_NODE_SESSIONS.pop(node_id, None)
    return removed


def _reconcile_undo_resurrected(owned_at_start, *, exclude_ids=()):
    """Restore fresh native identities after this batch's own Undo.

    Candidates are owned identities alive at batch start, resolved at their
    batch-start path and type only after the original identity disappeared.
    exclude_ids contains every identity alive just before Undo, so an existing
    foreign replacement cannot be adopted. Undo can itself replace children
    that were still alive before rollback (not just resurrect deleted nodes).
    A registered live ancestor and an unconsumed record are also required.
    """
    restored = []
    for old_id, (entry, batch_start_path) in owned_at_start.items():
        if hou.nodeBySessionId(old_id) is not None:
            continue
        candidate = hou.node(batch_start_path) if isinstance(batch_start_path, str) else None
        if candidate is None or int(candidate.sessionId()) in _OWNED_NODE_SESSIONS or int(candidate.sessionId()) in exclude_ids:
            continue
        if entry.get('type') is not None and candidate.type().name() != entry['type']:
            continue
        ancestor = candidate.parent()
        while ancestor is not None and int(ancestor.sessionId()) not in _OWNED_NODE_SESSIONS:
            ancestor = ancestor.parent()
        if ancestor is None:
            continue
        _OWNED_NODE_SESSIONS[int(candidate.sessionId())] = dict(entry)
        # Consume the dead entry: ids are never reused, so after adoption the
        # old record must not linger as a stale candidate for later batches.
        _OWNED_NODE_SESSIONS.pop(int(old_id), None)
        if _CREATION_JOURNAL is not None:
            _CREATION_JOURNAL.add(int(candidate.sessionId()))
        candidate.setUserData(_TASK_OWNER_KEY, entry.get('session'))
        if entry.get('call'):
            candidate.setUserData(_TASK_OWNER_CALL_KEY, entry['call'])
        restored.append(candidate.path())
    return restored


def _set_execution_owner(session_id: str | None, call_id: str | None):
    """Install trusted host provenance for one serialized bridge execution."""
    global _ACTIVE_OWNER_SESSION, _ACTIVE_OWNER_CALL
    previous = (_ACTIVE_OWNER_SESSION, _ACTIVE_OWNER_CALL)
    _ACTIVE_OWNER_SESSION = str(session_id) if session_id else None
    _ACTIVE_OWNER_CALL = str(call_id) if call_id else None
    return previous


def _restore_execution_owner(previous) -> None:
    global _ACTIVE_OWNER_SESSION, _ACTIVE_OWNER_CALL
    _ACTIVE_OWNER_SESSION, _ACTIVE_OWNER_CALL = previous


@contextlib.contextmanager
def execution_owner(session_id: str | None, call_id: str | None):
    """Scope trusted host provenance to exactly one serialized execution."""
    previous = _set_execution_owner(session_id, call_id)
    try:
        yield
    finally:
        _restore_execution_owner(previous)


def register_owned_node(node, *, exclude_ids=()) -> None:
    """Record a verb-created subtree, excluding identities predating a replacement."""
    if node is None or _ACTIVE_OWNER_SESSION is None:
        return
    items = [node]
    try:
        # Materialize the newly created HDA's delayed definition NOW. Otherwise
        # its native children first appear on cook and incorrectly look foreign.
        # Never do this later to adopt arbitrary children of an owned parent.
        items.extend(node.allSubChildren(sync_delayed_definition=True))
    except Exception:
        pass
    for item in items:
        if int(item.sessionId()) in exclude_ids:
            continue
        entry = {
            "session": _ACTIVE_OWNER_SESSION,
            "call": _ACTIVE_OWNER_CALL,
            "path_at_creation": item.path(),
            "type": item.type().name(),
        }
        _OWNED_NODE_SESSIONS[int(item.sessionId())] = entry
        if _CREATION_JOURNAL is not None:
            _CREATION_JOURNAL.add(int(item.sessionId()))
        item.setUserData(_TASK_OWNER_KEY, _ACTIVE_OWNER_SESSION)
        if _ACTIVE_OWNER_CALL:
            item.setUserData(_TASK_OWNER_CALL_KEY, _ACTIVE_OWNER_CALL)


@contextlib.contextmanager
def track_owned_definition_rebuilds(instances):
    """Attribute only fresh identities produced by this explicit native operation.

    An explicitly allowed foreign instance stays foreign. Existing identities,
    including user children moved during a callback, never become owned.
    Materialize delayed definitions inside this boundary, before later cooks.
    """
    owned = [n for n in instances if _ACTIVE_OWNER_SESSION is not None and
             _OWNED_NODE_SESSIONS.get(int(n.sessionId()), {}).get('session') == _ACTIVE_OWNER_SESSION]
    before = {int(n.sessionId()) for n in hou.node('/').allSubChildren()} if owned else set()
    descendants = {int(child.sessionId()) for n in owned for child in n.allSubChildren()}
    foreign_before = before - {identity for identity, entry in _OWNED_NODE_SESSIONS.items()
                               if entry.get('session') == _ACTIVE_OWNER_SESSION}
    try:
        yield
    finally:
        for n in owned:
            if hou.nodeBySessionId(int(n.sessionId())) is not None:
                blocked = set(before)
                for child in n.allSubChildren(sync_delayed_definition=True):
                    ancestor = child
                    while ancestor != n:
                        if int(ancestor.sessionId()) in foreign_before:
                            blocked.add(int(child.sessionId()))
                            break
                        ancestor = ancestor.parent()
                register_owned_node(n, exclude_ids=blocked)
        for identity in descendants:
            if hou.nodeBySessionId(identity) is None:
                _OWNED_NODE_SESSIONS.pop(identity, None)


def node_provenance(node) -> dict:
    """Report runtime ownership separately from durable, copyable audit tags."""
    n = dsh_node_access._resolve(node)
    if n.userData(dsh_service_constants._RENDER_OWNER_KEY) == dsh_service_constants._RENDER_OWNER_VALUE:
        status = "dsh_service"
        runtime_owner = None
    else:
        runtime_owner = _OWNED_NODE_SESSIONS.get(int(n.sessionId()))
        if runtime_owner is None:
            status = "foreign"
        elif runtime_owner.get("session") == _ACTIVE_OWNER_SESSION:
            status = "owned_current_session"
        else:
            status = "owned_other_session"
    return {
        "path": n.path(),
        "session_id": int(n.sessionId()),
        "status": status,
        "writable": status == "owned_current_session" or _ACTIVE_OWNER_SESSION is None,
        "runtime_owner": dict(runtime_owner) if runtime_owner else None,
        "audit_owner_session": n.userData(_TASK_OWNER_KEY),
        "audit_created_by_call": n.userData(_TASK_OWNER_CALL_KEY),
    }


def require_owned(node, operation: str, allow_foreign: str | None = None) -> None:
    """Guard one node mutation while preserving direct Python-shell workflows."""
    # Validate BEFORE the owned/direct-call fast paths. Python annotations are
    # not runtime checks: an accidental port number must never become authority.
    if allow_foreign is not None and (not isinstance(allow_foreign, str) or not allow_foreign.strip()):
        raise ValueError('allow_foreign must be a nonempty explicit authorization reason string, or None')
    if _ACTIVE_OWNER_SESSION is None:
        return
    info = node_provenance(node)
    if info["status"] == "owned_current_session":
        return
    if info["status"] == "dsh_service":
        raise ValueError(
            f"{info['path']} belongs to the persistent dsh-houdini service; "
            f"{operation} is not allowed"
        )
    reason = allow_foreign.strip() if allow_foreign is not None else ""
    if reason:
        print(
            f"[ownership] foreign-node exemption for {operation}: "
            f"{info['path']} — {reason}"
        )
        return
    raise ValueError(
        f"ownership guard: {operation} refused for foreign node {info['path']}. "
        "Nodes are not owned merely because they are inside an agent-created network. "
        "Read/inspect it freely; mutate it only when the user explicitly requested that "
        f"target, then retry with allow_foreign=\"<why the user authorized {operation}>\"."
    )


def _native_definition_identity(node, libraries):
    """Trust only an unchanged locked definition shipped inside this HFS."""
    definition = node.type().definition()
    if definition is None or not node.isLockedHDA() or not node.matchesCurrentDefinition():
        return None
    hfs = os.path.realpath(hou.expandString('$HFS'))
    library = os.path.realpath(definition.libraryFilePath())
    try:
        if os.path.commonpath([hfs, library]) != hfs or not os.path.isfile(library):
            return None
    except ValueError:
        return None
    if library not in libraries:
        size = os.path.getsize(library)
        if size > 32 * 1024 * 1024 or libraries.get('_bytes', 0) + size > 64 * 1024 * 1024:
            return None
        with open(library, 'rb') as stream:
            libraries[library] = hashlib.sha256(stream.read()).hexdigest()
        libraries['_bytes'] = libraries.get('_bytes', 0) + size
    return (node.type().category().name(), node.type().name(), library, libraries[library])


def snapshot_native_conversion(root):
    """Capture wholly owned, locked native subtrees BEFORE conversion.

    A path is only a slot within an unchanged native definition rooted at a
    surviving owned HOM identity, never independent proof of ownership.
    """
    owner = _OWNED_NODE_SESSIONS.get(int(root.sessionId()))
    if owner is None or owner['session'] != _ACTIVE_OWNER_SESSION:
        return []
    candidates = list(root.allSubChildren())
    if len(candidates) > 512:
        return []
    libraries, captured, covered = {}, [], set()
    for anchor in candidates:
        aid = int(anchor.sessionId())
        if aid in covered:
            continue
        entry = _OWNED_NODE_SESSIONS.get(aid)
        if not entry or entry['session'] != _ACTIVE_OWNER_SESSION:
            continue
        definition = _native_definition_identity(anchor, libraries)
        if definition is None:
            continue
        members = [anchor, *anchor.allSubChildren(sync_delayed_definition=True)]
        if any(not (e := _OWNED_NODE_SESSIONS.get(int(n.sessionId())))
               or e['session'] != _ACTIVE_OWNER_SESSION
               or n.userData(dsh_service_constants._RENDER_OWNER_KEY) == dsh_service_constants._RENDER_OWNER_VALUE for n in members):
            continue
        inventory = {anchor.relativePathTo(n): {
            'identity': int(n.sessionId()), 'type': (n.type().category().name(), n.type().name()),
            'owner': dict(_OWNED_NODE_SESSIONS[int(n.sessionId())])} for n in members[1:]}
        captured.append((aid, definition, inventory))
        covered.update(int(n.sessionId()) for n in members)
    return captured


def reconcile_native_conversion(captured):
    """Transfer only extinct identities in the exact captured native inventory."""
    libraries, materialized, transferred = {}, [], []
    for aid, definition, before in captured:
        anchor = hou.nodeBySessionId(aid)
        if anchor is None or _OWNED_NODE_SESSIONS.get(aid, {}).get('session') != _ACTIVE_OWNER_SESSION \
                or _native_definition_identity(anchor, libraries) != definition:
            continue
        anchor.allSubChildren(sync_delayed_definition=True)
        materialized.append((aid, definition, before))
    # Recheck actual definition bytes after ALL materialization, not a cached
    # pre-materialization digest. No further delayed loading during transfers.
    libraries = {}
    for aid, definition, before in materialized:
        anchor = hou.nodeBySessionId(aid)
        if anchor is None or _OWNED_NODE_SESSIONS.get(aid, {}).get('session') != _ACTIVE_OWNER_SESSION \
                or _native_definition_identity(anchor, libraries) != definition:
            continue
        after = {anchor.relativePathTo(n): n for n in anchor.allSubChildren()}
        if set(before) != set(after) or any(
                (n.type().category().name(), n.type().name()) != before[slot]['type']
                or n.userData(dsh_service_constants._RENDER_OWNER_KEY) == dsh_service_constants._RENDER_OWNER_VALUE for slot, n in after.items()):
            continue
        for slot, n in after.items():
            old = before[slot]
            new_id = int(n.sessionId())
            if old['owner']['session'] != _ACTIVE_OWNER_SESSION or old['identity'] == new_id or hou.nodeBySessionId(old['identity']) is not None:
                continue
            # Never overwrite a registered identity, even one with copied tags.
            if new_id in _OWNED_NODE_SESSIONS:
                continue
            _OWNED_NODE_SESSIONS[new_id] = dict(old['owner'])
            _OWNED_NODE_SESSIONS.pop(old['identity'], None)
            if _CREATION_JOURNAL is not None and old['identity'] in _CREATION_JOURNAL:
                _CREATION_JOURNAL.add(new_id)
            transferred.append({'node': n.path(), 'previous_identity': old['identity'],
                                'identity': new_id, 'native_anchor_identity': aid})
    return transferred
