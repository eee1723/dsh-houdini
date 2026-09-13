"""Candidate executor discovery and cooperative HIP writer leases.

No hou, process termination, credentials or DSH account copies. Records are
discovery hints; the Host must still verify executor identity on every request.
All methods are worker-side file operations, not Houdini GUI callbacks.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import threading
import uuid

from dsh_deployment import FileLease, atomic_json

if '_ACTIVE' not in globals():
    _ACTIVE = None


def active_registration():
    if _ACTIVE is None:
        raise RuntimeError('Shared executor registration is not enabled')
    return _ACTIVE


def is_shared_executor():
    return _ACTIVE is not None and not _ACTIVE._closed


def activate(root, executor_id, *, installation, version, port, runtime_id, hip):
    """Explicit worker-side registration after the Bridge is listening."""
    global _ACTIVE
    if _ACTIVE is not None:
        raise RuntimeError('An executor registration is already active')
    item = ExecutorRegistration(root, executor_id, installation=installation, version=version)
    try:
        item.publish(port, runtime_id, hip=hip)
    except BaseException:
        item.close()
        raise
    _ACTIVE = item
    return item


def _identity(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError('invalid executor identity')
    return value


def _absolute(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError('absolute path required')
    return path.resolve()


def _hip_key(path):
    # Resolve case/symlink aliases; existing hard links share the filesystem ID.
    path = _absolute(path)
    if path.suffix.lower() not in ('.hip', '.hiplc', '.hipnc'):
        raise ValueError('expected a HIP path')
    canonical = os.path.normcase(str(path))
    keys = ['path:' + canonical]
    if path.exists():
        if not path.is_file():
            raise ValueError('HIP target is not a file')
        if os.name == 'nt':
            # Python 3.11/3.13 expose different Windows stat inode formats.
            # Use one native identity on both H21 and H22, including hard links.
            import ctypes
            from ctypes import wintypes
            import msvcrt
            class FileInfo(ctypes.Structure):
                _fields_ = [(name, wintypes.DWORD) for name in (
                    'attributes','creationLow','creationHigh','accessLow','accessHigh',
                    'writeLow','writeHigh','volume','sizeHigh','sizeLow','links','indexHigh','indexLow')]
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInfo)]
            info = FileInfo()
            with path.open('rb') as source:
                if not kernel.GetFileInformationByHandle(msvcrt.get_osfhandle(source.fileno()), ctypes.byref(info)):
                    raise OSError(ctypes.get_last_error(), 'Cannot establish HIP file identity')
            keys.append(f'file:{info.volume}:{info.indexHigh}:{info.indexLow}')
        else:
            info = path.stat()
            if not info.st_ino:
                raise ValueError('filesystem cannot establish HIP identity')
            keys.append(f'file:{info.st_dev}:{info.st_ino}')
    return path, [hashlib.sha256(k.encode('utf-8')).hexdigest() for k in sorted(keys)]


class ExecutorRegistration:
    """One executor's registration; its OS lease ends on process death.

    This is not a liveness oracle or automatic task recovery authority.
    A registration never adopts another process's existing record or writer.
    """
    def __init__(self, root, executor_id, *, installation, version):
        self.root = _absolute(root)
        self.executor_id = _identity(executor_id)
        self.installation = str(_absolute(installation))
        if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
            raise ValueError('expected exact Houdini version')
        self.version = version
        self._guard = threading.RLock()
        self._writers = []
        self._task = None
        self._hip = None
        self._closed = False
        self._lease = FileLease(self.root / 'leases' / (self.executor_id + '.lock'))
        self._file = self.root / 'endpoints' / (self.executor_id + '.json')
        if self._file.exists():
            self._lease.close()
            raise RuntimeError('executor identity already recorded; new processes require a fresh identity')
        self._generation = uuid.uuid4().hex
        self._port = None
        self._runtime_id = None
        self._observed_hip = None

    def _open(self):
        if self._closed:
            raise RuntimeError('executor registration is closed')

    def claim_writer(self, task_id, hip):
        """Acquire before enabling mutations. Never create/save/load the HIP.

        Only protects participating runtimes; GUI saves and arbitrary filesystem
        writes are not intercepted. Save As must acquire its new target first.
        """
        if not isinstance(task_id, str) or not task_id.strip() or len(task_id) > 256:
            raise ValueError('invalid task identity')
        target, keys = _hip_key(hip)
        with self._guard:
            self._open()
            if self._task is not None:
                if (self._task, self._hip) == (task_id, str(target)):
                    return
                raise RuntimeError('executor already has a scene author; release explicitly before changing task or HIP')
            leases = []
            try:
                for key in keys:
                    leases.append(FileLease(self.root / 'writers' / (key + '.lock')))
            except BaseException:
                for lease in reversed(leases):
                    lease.close()
                raise
            self._writers, self._task, self._hip = leases, task_id, str(target)

    def publish(self, port, runtime_id, *, hip=None):
        """Publish an already listening Bridge, never close-and-rebind a probe port."""
        _identity(runtime_id)
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError('invalid loopback port')
        with self._guard:
            self._open()
            if hip is not None:
                self._observed_hip = str(_absolute(hip))
            record = {'schema': 1, 'executor_id': self.executor_id,
                      'registration_id': self._generation, 'runtime_id': runtime_id,
                      'pid': os.getpid(), 'installation': self.installation, 'houdini_version': self.version,
                      'bridge_url': f'http://127.0.0.1:{port}', 'state': 'registered',
                      'task_id': self._task, 'hip_path': self._hip or self._observed_hip,
                      'boundary': 'Discovery only; verify executor header and task binding before any operation'}
            atomic_json(self._file, record)
            self._port, self._runtime_id = port, runtime_id
            return record

    def claim(self, task_id, registration_id, expected_hip, actual_hip):
        """Called after the Bridge main thread captures the actual current HIP."""
        with self._guard:
            self._open()
            if registration_id != self._generation or self._port is None:
                raise RuntimeError('Stale executor registration; refresh before selecting')
            expected = _absolute(expected_hip)
            if expected != _absolute(actual_hip) or str(expected) != self._observed_hip:
                raise RuntimeError('HIP changed after discovery; refresh and confirm the actual target')
            if not expected.is_file():
                raise RuntimeError('Save and name this HIP before binding a shared task')
            self.claim_writer(task_id, expected)
            # If publication fails, keep the acquired reservation. A retry by the
            # same task is safe; do not let a competing author take over unknown state.
            return self.publish(self._port, self._runtime_id)

    def require_writer(self, task_id, actual_hip):
        with self._guard:
            self._open()
            if self._task is None or self._task != task_id or os.path.normcase(self._hip) != os.path.normcase(os.path.abspath(actual_hip)):
                raise RuntimeError('Shared executor task/HIP reservation mismatch; no scene operation allowed')


    def close(self):
        with self._guard:
            if self._closed:
                return
            # Do not mark unknown executions completed. Retain evidence on disk.
            try:
                if self._file.exists():
                    value = json.loads(self._file.read_text(encoding='utf-8'))
                    if value.get('registration_id') != self._generation:
                        raise RuntimeError('registration changed; refusing to overwrite another generation')
                    atomic_json(self._file, {**value, 'state': 'disconnected'})
            finally:
                for lease in reversed(self._writers):
                    lease.close()
                self._writers = []
                self._lease.close()
                self._closed = True


def require_active_writer(task_id, actual_hip):
    if _ACTIVE is not None:
        _ACTIVE.require_writer(task_id, actual_hip)


def require_save_target(path):
    if _ACTIVE is not None and os.path.normcase(os.path.abspath(path)) != os.path.normcase(_ACTIVE._hip or ''):
        raise RuntimeError('Shared executor Save As requires a new writer reservation; use the explicit handoff flow, not this scene call')


def read_candidates(root, *, installation):
    """Read-only discovery. Stale records remain candidates, never 'connected'."""
    root, install = _absolute(root), str(_absolute(installation))
    folder = root / 'endpoints'
    if not folder.exists():
        return []
    files = sorted(folder.glob('*.json'))
    if len(files) > 256:
        raise ValueError('executor discovery exceeds 256 records; explicit maintenance required')
    rows = []
    for file in files:
        if file.is_symlink() or file.resolve().parent != folder.resolve() or file.stat().st_size > 16384:
            raise ValueError('invalid endpoint record path/size')
        value = json.loads(file.read_text(encoding='utf-8'))
        if (not isinstance(value, dict) or type(value.get('schema')) is not int or value.get('schema') != 1 or value.get('executor_id') != file.stem
                or not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{4,5}', value.get('bridge_url', ''))
                or value.get('state') not in ('registered', 'disconnected')):
            raise ValueError('invalid executor record')
        _identity(value['executor_id'])
        _identity(value.get('runtime_id'))
        _identity(value.get('registration_id'))
        if not 1024 <= int(value['bridge_url'].rsplit(':', 1)[1]) <= 65535:
            raise ValueError('invalid registered port')
        if value.get('installation') == install:
            rows.append({**value, 'connection_status': 'unverified'})
    return rows
