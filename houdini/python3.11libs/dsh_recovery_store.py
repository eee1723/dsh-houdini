"""Worker-only checkpoint files and executor lifetime leases; no HOM.

These records persist the ownership actor's save snapshot. HIP paths and copied
node tags do not create records. The store is outside task-writable workspaces.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import threading
from contextlib import ExitStack, contextmanager
from dsh_deployment import FileLease, atomic_json

if '_LOCK' not in globals():
    _LOCK = threading.RLock()
    _LEASES = {}


def root():
    explicit = os.environ.get('DSH_HOUDINI_RECOVERY_ROOT')
    if explicit:
        return Path(explicit)
    return Path(os.environ.get('DSH_HOUDINI_INSTALL_ROOT') or
                str(Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'DSH-Houdini')) / 'recovery'


def identity(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError('Invalid recovery identity')
    return value


def sources(record):
    """Trusted saved lineage, including creators preserved without activation."""
    return {identity(value) for value in record.get('source_executors', [record['executor_id']])}


def require_task_source(record, owner, executors):
    known = {identity(value) for value in executors}
    if not known.intersection(sources(record)):
        raise RuntimeError('保存点来自另一任务执行端，不能按目录或文件名恢复。')
    if any(row.get('source_executor', record['executor_id']) not in known
           for row in record['nodes'] if row['owner']['session'] == owner):
        raise RuntimeError('保存点中此任务的节点来源与对话记录不一致，未授予修改权。')


def retain_executor(executor):
    with _LOCK:
        key = (str(root()), identity(executor))
        if key not in _LEASES:
            _LEASES[key] = FileLease(root() / 'executors' / (executor + '.lock'))


def require_retired(executor):
    """Hold proof that a participating old executor is no longer active."""
    try:
        return FileLease(root() / 'executors' / (identity(executor) + '.lock'))
    except RuntimeError as error:
        raise RuntimeError('无法确认原 Houdini 已退出：原运行锁仍被占用或无法取得，未接管任务。') from error


@contextmanager
def retired_sources(previous, producer, current):
    """Keep the original task and checkpoint producer retired through one operation."""
    with ExitStack() as leases:
        for source in sorted({previous, producer} - {current}):
            leases.enter_context(require_retired(source))
        yield


def file_stamp(path):
    stat = os.stat(path)
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def file_digest(path, expected=None):
    before = file_stamp(path)
    if expected is not None and tuple(expected) != before:
        raise RuntimeError('HIP changed before recovery verification')
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    if file_stamp(path) != before:
        raise RuntimeError('HIP changed during recovery verification')
    return digest.hexdigest(), before


def commit(record, stamp):
    retain_executor(record['executor_id'])
    digest, _ = file_digest(record['hip_path'], stamp)
    saved = {**record, 'schema': 1, 'file_sha256': digest}
    atomic_json(root() / 'checkpoints' / (identity(record['checkpoint_id']) + '.json'), saved)
    return saved


def read(checkpoint):
    file = root() / 'checkpoints' / (identity(checkpoint) + '.json')
    if file.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Recovery record exceeds the supported size')
    value = json.loads(file.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schema') != 1 or value.get('checkpoint_id') != checkpoint:
        raise ValueError('Unsupported recovery record')
    return value


def locate(scene, owner, executors):
    """Find branch tips in existing trusted save records; never search project directories."""
    identity(scene)
    records = []
    for file in (root() / 'checkpoints').glob('*.json'):
        try:
            record = read(file.stem)
            if record.get('scene_id') != scene:
                continue
            require_task_source(record, owner, executors)
            records.append(record)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError):
            continue  # Unrelated or incomplete material cannot select a project.
    parents = {record.get('parent_checkpoint') for record in records}
    tips = sorted((record for record in records if record['checkpoint_id'] not in parents),
                  key=lambda record: (record['saved_at'], record['checkpoint_id']), reverse=True)
    found, unavailable = [], []
    for record in tips:
        candidate = {key: record[key] for key in ('checkpoint_id', 'scene_id', 'hip_path', 'saved_at', 'hou_version')}
        try:
            digest, _ = file_digest(record['hip_path'])
            if digest != record['file_sha256']:
                raise RuntimeError('保存文件已变化，不能确认仍是此保存点。')
            found.append(candidate)
        except (OSError, RuntimeError) as error:
            unavailable.append({**candidate, 'reason': str(error)})
    return {'candidates': found, 'unavailable': unavailable}
