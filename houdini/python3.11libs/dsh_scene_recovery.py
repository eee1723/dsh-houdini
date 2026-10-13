"""Saved ownership checkpoints and task recovery on the Bridge actor.

HOM lives here and in dsh_ownership. File verification is worker-only. A
checkpoint restores only identities captured from a verified fresh HIP load.
No model code, replay, general file opener or workspace database is exposed.
"""
from __future__ import annotations
import copy
import os
import threading
import time
import uuid
import hou
import dsh_ownership
import dsh_recovery_store as store
from dsh_managed_runtime import executor_identity

CHECKPOINT_KEY = 'dsh_houdini_checkpoint'
SCENE_KEY = 'dsh_houdini_scene'
NODE_KEY = 'dsh_houdini_checkpoint_node'

if globals().get('_PID') != os.getpid():
    _PID = os.getpid()
    _MAIN = threading.get_ident()
    _EPOCH = uuid.uuid4().hex
    _SCENE = uuid.uuid4().hex
    _PREPARED = None
    _SAVED = None
    _LOADED = None
    _LOADED_STAMP = None
    _LOADED_NODES = {}
    _PROVEN = None
    _SAVE_SERIAL = 0
    _BINDINGS = {}
    _OPERATIONS = {}
    _STATUS = {'status': 'no_checkpoint'}
    _WORK = threading.RLock()
    _CALLBACK = None

# Runtime repair reloads modules in the same Houdini process. New optional
# evidence starts empty; the existing ownership and binding actor stays intact.
if '_PROVEN' not in globals():
    _PROVEN = None
if '_SAVE_SERIAL' not in globals():
    _SAVE_SERIAL = 0


def _main():
    if threading.get_ident() != _MAIN:
        raise RuntimeError('Scene recovery requires the Houdini owning thread')


def scene_epoch():
    """Immutable actor-published generation; worker reads never call HOM."""
    return _EPOCH


def _checkpoint():
    value = hou.node('/').userData(CHECKPOINT_KEY)
    try:
        return store.identity(value)
    except ValueError:
        return None


def _nodes():
    return hou.node('/').allSubChildren(sync_delayed_definition=False)


def facts():
    _main()
    return {'scene_epoch': _EPOCH, 'scene_id': _SCENE,
            'checkpoint_id': _checkpoint(), 'hip_path': hou.hipFile.path(),
            'loaded_checkpoint': _LOADED, 'dirty': bool(hou.hipFile.hasUnsavedChanges()),
            'loaded_stamp': _LOADED_STAMP,
            'successful_save': {'checkpoint_id': _SAVED[0], 'hip_path': _SAVED[1]} if _SAVED else None,
            'dirty_reliable': bool(hou.isUIAvailable()), 'checkpoint': dict(_STATUS)}


def before_save():
    """Preserve proven inactive creators without granting their authority."""
    global _PREPARED, _STATUS, _SAVE_SERIAL, _PROVEN
    _main()
    with _WORK:
        _SAVE_SERIAL += 1
        proven = _PROVEN if _PROVEN and _PROVEN['epoch'] == _EPOCH else None
    records = dsh_ownership.records()
    inherited, _ = _live_mapping(proven['record'], proven['nodes']) if proven else ([], [])
    inherited = dict(inherited)
    bound_here = any(binding['scene_epoch'] == _EPOCH for binding in _BINDINGS.values())
    if not records and not proven and (_LOADED or not bound_here):
        _PREPARED = None
        if _LOADED:
            _STATUS = {'status': 'checkpoint_unavailable',
                       'error': '原保存点尚未完成来源核对，本次保存没有自动继承节点归属。'}
        return
    checkpoint = uuid.uuid4().hex
    rows = []
    baseline = {}
    for identity in dict.fromkeys([*inherited, *records]):
        prior = inherited.get(identity)
        owner = records.get(identity) or prior['owner']
        node = hou.nodeBySessionId(identity)
        if node is None:
            continue
        if node.isInsideLockedHDA() and not node.isEditableInsideLockedHDA():
            # Definition-owned internals can be recreated without instance
            # userData on load. Their containing HDA remains the editable asset.
            continue
        # Copies can retain the old marker. Rotate only the exact known source
        # identity so the next load can distinguish it from every foreign copy.
        token = uuid.uuid4().hex
        try:
            node.setUserData(NODE_KEY, token)
        except hou.Error:
            continue  # Locked native members remain foreign after reopening.
        source = prior.get('source_executor', proven['record']['executor_id']) if prior and prior['owner'] == owner else executor_identity()
        rows.append({'node_id': token, 'path': node.path(), 'type': node.type().name(),
                     'category': node.type().category().name(), 'owner': dict(owner), 'source_executor': source})
        baseline[identity] = (token, node.type().category().name(), node.type().name())
    parent = _checkpoint()
    if _STATUS.get('status') == 'save_failed' and _PREPARED and parent == _PREPARED['checkpoint_id']:
        parent = _PREPARED['parent_checkpoint']  # A confirmed failed attempt is not a saved ancestor.
    hou.node('/').setUserData(SCENE_KEY, _SCENE)
    hou.node('/').setUserData(CHECKPOINT_KEY, checkpoint)
    _PREPARED = {'checkpoint_id': checkpoint, 'parent_checkpoint': parent, 'scene_id': _SCENE,
                 'executor_id': executor_identity(), 'hou_version': hou.applicationVersionString(),
                 'source_executors': sorted(set([executor_identity(), *(store.sources(proven['record']) if proven else [])])),
                 'saved_at': time.time(), 'nodes': rows, '_baseline': baseline, '_epoch': _EPOCH,
                 '_serial': _SAVE_SERIAL}
    if _LOADED and not proven:
        _PREPARED['unrestored_provenance'] = 'Loaded checkpoint provenance was unavailable before this save.'
    # Our marker writes preserve exact causal identities even if the upcoming
    # disk save fails. This is live provenance only: recovery still requires a
    # committed record and matching file bytes, and status stays "saving".
    with _WORK:
        _PROVEN = {'record': {key: value for key, value in _PREPARED.items() if not key.startswith('_')},
                   'nodes': baseline, 'epoch': _EPOCH}
    _STATUS = {'status': 'saving', 'checkpoint_id': checkpoint}


def after_save(path, success):
    """Called by native afterscenesave.py and the explicit save verbs."""
    global _SAVED, _STATUS
    _main()
    pending = _PREPARED
    if not pending or pending['checkpoint_id'] != _checkpoint():
        return
    if not success:
        _STATUS = {'status': 'save_failed', 'checkpoint_id': pending['checkpoint_id']}
        return
    path = os.path.abspath(path)
    key = (pending['checkpoint_id'], path)
    if _SAVED == key:
        return
    try:
        stamp = store.file_stamp(path)
        if stamp[2] <= 0:
            raise OSError('保存的 HIP 为空，未建立恢复点。')
    except OSError as error:
        _STATUS = {'status': 'checkpoint_unavailable', 'error': str(error)}
        return
    _SAVED = key
    record = {key: copy.deepcopy(value) for key, value in pending.items() if not key.startswith('_')}
    record['hip_path'] = path
    _STATUS = {'status': 'checkpoint_pending', 'checkpoint_id': key[0]}
    def persist():
        global _STATUS, _PROVEN
        try:
            saved = store.commit(record, stamp)
            result = {'status': 'checkpoint_saved', 'checkpoint_id': key[0], 'hip_path': path}
            if saved.get('unrestored_provenance'):
                result['unrestored_provenance'] = saved['unrestored_provenance']
        except Exception as error:
            saved = None
            result = {'status': 'checkpoint_unavailable', 'checkpoint_id': key[0], 'error': str(error)}
        with _WORK:
            if _SAVED == key and _SAVE_SERIAL == pending['_serial']:
                _STATUS = result
                if saved and pending['_epoch'] == _EPOCH:
                    _PROVEN = {'record': saved, 'nodes': pending['_baseline'], 'epoch': _EPOCH}
    threading.Thread(target=persist, daemon=True, name='dsh-checkpoint').start()


def save_unverified(reason):
    global _STATUS
    _main()
    _STATUS = {'status': 'checkpoint_unavailable', 'error': reason}


def invalidate():
    global _EPOCH, _SCENE, _LOADED, _LOADED_STAMP, _LOADED_NODES, _PREPARED, _SAVED, _STATUS, _PROVEN
    _main()
    _EPOCH, _SCENE = uuid.uuid4().hex, uuid.uuid4().hex
    _LOADED, _LOADED_NODES, _PREPARED, _SAVED = None, {}, None, None
    _LOADED_STAMP = None
    _PROVEN = None
    _STATUS = {'status': 'not_observed'}
    _OPERATIONS.clear()
    # Keep task expectations so an old task cannot silently adopt the new HIP.
    dsh_ownership.clear_for_scene_load()


def capture_loaded():
    global _SCENE, _LOADED, _LOADED_STAMP, _LOADED_NODES, _PROVEN
    _main()
    _LOADED = _checkpoint()
    try:
        _SCENE = store.identity(hou.node('/').userData(SCENE_KEY))
    except ValueError:
        _SCENE = uuid.uuid4().hex
    try:
        _LOADED_STAMP = store.file_stamp(hou.hipFile.path())
    except OSError:
        _LOADED_STAMP = None
    _LOADED_NODES = {int(node.sessionId()): (node.userData(NODE_KEY), node.type().category().name(),
                                            node.type().name()) for node in _nodes()}
    _PROVEN = None
    checkpoint, stamp, path, epoch, serial = _LOADED, _LOADED_STAMP, hou.hipFile.path(), _EPOCH, _SAVE_SERIAL
    baseline = dict(_LOADED_NODES)
    if not checkpoint or not stamp:
        return
    def verify():
        global _PROVEN
        try:
            record = store.read(checkpoint)
            digest, _ = store.file_digest(path, stamp)
            if digest != record['file_sha256']:
                return
        except (OSError, ValueError, RuntimeError, KeyError):
            return
        with _WORK:
            if epoch == _EPOCH and checkpoint == _LOADED and serial == _SAVE_SERIAL:
                _PROVEN = {'record': record, 'nodes': baseline, 'epoch': epoch}
    threading.Thread(target=verify, daemon=True, name='dsh-load-checkpoint').start()


def install():
    global _CALLBACK
    _main()
    if _CALLBACK is not None:
        try:
            hou.hipFile.removeEventCallback(_CALLBACK)
        except hou.Error:
            pass
    def changed(kind, **kwargs):
        if kind == hou.hipFileEventType.BeforeSave:
            before_save()
        elif kind in (hou.hipFileEventType.BeforeLoad, hou.hipFileEventType.BeforeClear):
            invalidate()
        elif kind == hou.hipFileEventType.AfterLoad:
            capture_loaded()
        # AfterSave has no success flag and is broken for some H21 backslash
        # paths. Native afterscenesave.py is the authoritative success hook.
    _CALLBACK = changed
    hou.hipFile.addEventCallback(changed)


def task_target(owner):
    """Actor-side scene fence, captured once even before the first saved HIP."""
    _main()
    expected = _BINDINGS.get(owner)
    if expected is None:
        _BINDINGS[owner] = {'scene_epoch': _EPOCH, 'binding_id': None}
    elif expected['scene_epoch'] != _EPOCH:
        raise RuntimeError('当前打开的工程已变化，需要先核对任务与当前工程的接续关系。')
    return _EPOCH


def connected(owner):
    _main()
    return _BINDINGS.get(owner, {}).get('scene_epoch') == _EPOCH


def status(owner):
    """Cheap actor facts, without disk hashing or a new task binding."""
    _main()
    binding = _BINDINGS.get(owner)
    return {**facts(), 'task_bound': binding is not None, 'connected': connected(owner),
            'binding_id': binding.get('binding_id') if binding else None}


def require_target(owner, epoch):
    _main()
    if epoch != _EPOCH:
        raise RuntimeError('Scene changed after request preparation; no operation dispatched')
    task_target(owner)


def preview(record, owner, previous, expected_scene=None):
    """Main-thread projection; byte verification and old-process check happen outside."""
    _main()
    current = status(owner)
    if record['checkpoint_id'] != current['checkpoint_id']:
        raise RuntimeError('当前工程与保存点不匹配；请打开原任务对应的 HIP。')
    owned = [row for row in record['nodes'] if row['owner']['session'] == owner]
    if expected_scene is not None and record['scene_id'] != expected_scene:
        raise RuntimeError('当前工程身份与原对话不一致；需要通过对话确认要继续的工程。')
    if not owned and expected_scene != record['scene_id']:
        raise RuntimeError('此保存点没有任务节点，且缺少原对话的工程身份，无法自动确认接续关系。')
    verified = _PROVEN and _PROVEN['epoch'] == _EPOCH and _PROVEN['record']['checkpoint_id'] == record['checkpoint_id']
    return {**current, 'scene_id': record['scene_id'], 'saved_at': record['saved_at'],
            'saved_hip': record['hip_path'], 'saved_version': record['hou_version'],
            'owned_nodes': len(owned), 'requires_reload': not verified and _LOADED != current['checkpoint_id'],
            'unrestored_provenance': record.get('unrestored_provenance')}


def _live_mapping(record, baseline, owner=None):
    """Surviving observed HOM identities prove lineage; copied tags never do."""
    _main()
    origins = {}
    for identity, signature in baseline.items():
        origins.setdefault(signature, []).append(identity)
    mapping, missing, surviving_ancestors = [], [], {}
    for row in record['nodes']:
        signature = (row['node_id'], row['category'], row['type'])
        identities = origins.get(signature, [])
        identity = identities[0] if len(identities) == 1 else None
        node = hou.nodeBySessionId(identity) if identity is not None else None
        survives = node is not None and (node.userData(NODE_KEY), node.type().category().name(), node.type().name()) == signature
        if survives:
            surviving_ancestors[row['path']] = node
        if owner is not None and row['owner']['session'] != owner:
            continue
        if not survives:
            missing.append({'path': row['path'], 'reason': 'original_node_missing_or_changed'})
        else:
            mapping.append((identity, row))
    for item in missing:
        parent = item['path'].rsplit('/', 1)[0]
        while parent:
            ancestor = surviving_ancestors.get(parent)
            if ancestor is not None and ancestor.isLockedHDA():
                item['reason'] = 'native_definition_member_unverified'
                break
            parent = parent.rsplit('/', 1)[0]
    return mapping, missing


def prepare(record, owner, previous, operation, expected, reload_saved=False, expected_scene=None):
    """Freeze one verified load's exact identities. Does not grant ownership."""
    _main()
    store.identity(operation)
    existing = _OPERATIONS.get(operation)
    if existing is not None:
        if (existing['owner'] != owner or existing['record']['checkpoint_id'] != record['checkpoint_id']
                or existing['epoch'] != _EPOCH or existing['previous'] != previous):
            raise RuntimeError('Recovery operation conflicts with its original preparation')
        return public_prepared(existing)
    current = preview(record, owner, previous, expected_scene)
    if (current['scene_epoch'] != expected['scene_epoch'] or current['hip_path'] != expected['hip_path']
            or current['checkpoint_id'] != expected['checkpoint_id']):
        raise RuntimeError('工程已在检查后切换，请重新检查。')
    if current['requires_reload']:
        discard = expected.get('discard_unsaved') is True
        if not reload_saved or not current['dirty_reliable'] or (current['dirty'] and not discard):
            raise RuntimeError('接续需要重新打开当前 HIP；未保存修改须先保留，或由用户在对话中明确选择放弃。')
        hou.hipFile.load(current['hip_path'].replace('\\', '/'), suppress_save_prompt=True)
        capture_loaded()
    proven = _PROVEN if _PROVEN and _PROVEN['epoch'] == _EPOCH and _PROVEN['record']['checkpoint_id'] == record['checkpoint_id'] else None
    if not proven and _LOADED != record['checkpoint_id']:
        raise RuntimeError('No observed load of the verified checkpoint')
    mapping, missing = _live_mapping(record, proven['nodes'] if proven else _LOADED_NODES, owner)
    value = {'owner': owner, 'previous': previous, 'operation': operation,
             'record': record, 'epoch': _EPOCH, 'mapping': mapping, 'missing': missing, 'active': False}
    _OPERATIONS[operation] = value
    return public_prepared(value)


def open_original(record, owner, expected):
    """Load the verified recorded path after a native conversation choice; grant no ownership."""
    _main()
    current = status(owner)
    if any(current[key] != expected.get(key) for key in ('scene_epoch', 'hip_path', 'checkpoint_id')):
        raise RuntimeError('回答期间当前工程已切换，未将旧选择应用到新工程。')
    if expected.get('open_original') is not True:
        raise RuntimeError('切换到原工程需要用户在对话中明确选择。')
    if not current['dirty_reliable'] or (current['dirty'] and expected.get('discard_unsaved') is not True):
        raise RuntimeError('当前工程存在未确认的未保存内容，未切换工程。')
    hou.hipFile.load(record['hip_path'].replace('\\', '/'), suppress_save_prompt=True)
    capture_loaded()
    if _LOADED != record['checkpoint_id'] or _SCENE != record['scene_id']:
        raise RuntimeError('打开后的工程身份与保存点不符，未恢复修改权。')
    return {**status(owner), 'status': 'opened'}


def public_prepared(value):
    return {'operation_id': value['operation'], 'scene_epoch': value['epoch'],
            'checkpoint_id': value['record']['checkpoint_id'], 'scene_id': value['record']['scene_id'],
            'executor_id': executor_identity(), 'previous_executor': value['previous'],
            'restored_nodes': len(value['mapping']), 'unrestored_nodes': value.get('missing', []),
            'status': 'active' if value['active'] else 'prepared'}


def discard_prepared(operation, owner):
    """A failed final disk check cannot leave a reusable unchecked mapping."""
    _main()
    value = _OPERATIONS.get(operation)
    if value and value['owner'] == owner and not value['active']:
        del _OPERATIONS[operation]


def activate(operation, owner):
    global _SCENE
    _main()
    value = _OPERATIONS.get(operation)
    if value is None or value['owner'] != owner or value['epoch'] != _EPOCH:
        raise RuntimeError('Recovery preparation is absent or the scene changed')
    if not value['active']:
        dsh_ownership.restore_checkpoint(value['mapping'], owner, NODE_KEY)
        _SCENE = value['record']['scene_id']
        _BINDINGS[owner] = {'scene_epoch': _EPOCH, 'binding_id': operation}
        value['active'] = True
    return public_prepared(value)
