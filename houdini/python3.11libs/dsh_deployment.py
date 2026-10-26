"""Atomic plugin JSON publication and OS lifetime leases for Houdini identities.

These shared primitives do not install a DSH runtime or own its user data.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import time
import uuid

def _json_snapshot(path: Path):
    """Readers retain a snapshot without blocking an atomic state publication."""
    if os.name != "nt":
        return path.open("rb")
    import ctypes
    from ctypes import wintypes
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    # GENERIC_READ, FILE_SHARE_READ|WRITE|DELETE, OPEN_EXISTING. Sharing permits
    # publication; the handle itself grants no write or delete access.
    handle = kernel.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        error = ctypes.WinError(ctypes.get_last_error())
        error.filename = str(path)
        raise error
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    try:
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def _publish_json(temp: Path, path: Path):
    if os.name != "nt":
        os.replace(temp, path)
        return
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.ReplaceFileW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
    kernel.ReplaceFileW.restype = wintypes.BOOL
    # State publication reproduced a MoveFileEx (os.replace) conflict despite
    # shared deletion. ReplaceFile supports the old reader snapshots while
    # retaining the existing state's access-control list.
    if kernel.ReplaceFileW(str(path), str(temp), None, 0, None, None):
        return
    code = ctypes.get_last_error()
    if code == 2:  # No existing destination: publish the first generation.
        os.replace(temp, path)
        return
    error = ctypes.WinError(code)
    error.filename, error.filename2 = str(temp), str(path)
    raise error


def read_json(path: Path, limit=8 * 1024**2):
    # ReplaceFileW can briefly reject a new reader (or hide the destination)
    # even when existing snapshots share deletion. Bound only these observed
    # publication races; missing files and real errors still propagate.
    deadline = time.monotonic() + .05
    while True:
        try:
            with _json_snapshot(path) as handle:
                raw = handle.read(limit + 1)
            break
        except OSError as error:
            if os.name != 'nt' or getattr(error, 'winerror', None) not in (2, 32, 33) or time.monotonic() >= deadline:
                raise
            time.sleep(.002)
    if len(raw) > limit:
        raise ValueError(f"JSON too large: {path.name}")
    return json.loads(raw)


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temp.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    _publish_json(temp, path)


def _process_started(pid):
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        code = wintypes.DWORD()
        times = [wintypes.FILETIME() for index in range(4)]
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
            return None
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
            return None
        return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
    finally:
        kernel.CloseHandle(handle)


class LeaseBusyError(RuntimeError):
    def __init__(self, message, path):
        super().__init__(message)
        self.path = Path(path)
        self.owner = None
        try:
            with Path(path).open('rb') as stream:
                stream.seek(1)
                raw = stream.read(8193)
            value = json.loads(raw) if len(raw) <= 8192 else None
            if isinstance(value, dict) and value.get('schema') == 1 and type(value.get('pid')) is int and 0 < value['pid'] <= 0xffffffff \
                    and value.get('process_started') and value['process_started'] == _process_started(value['pid']):
                self.owner = value
        except (OSError, ValueError, RecursionError):
            pass


class FileLease:
    """OS lifetime lock: crash/reboot releases it without deleting a stale lock."""
    def __init__(self, path: Path, *, busy_message="资源正在被其他操作使用，请稍后重试。"):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open("a+b")
        self.owner_recorded = False
        try:
            if os.fstat(self.handle.fileno()).st_size == 0:
                self.handle.write(b"0")
                self.handle.flush()
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            raise LeaseBusyError(busy_message, path) from exc

    def record_owner(self, value):
        identity = {'schema': 1, 'pid': os.getpid(), 'process_started': _process_started(os.getpid())}
        payload = json.dumps({**value, **identity}, ensure_ascii=False).encode('utf-8')
        if len(payload) > 8192:
            payload = json.dumps({**identity, 'details_unavailable': 'metadata_size_limit'}).encode('utf-8')
        self.handle.seek(1)
        self.handle.truncate()
        self.handle.write(payload)
        self.handle.flush()
        self.owner_recorded = True

    def close(self):
        if self.handle.closed:
            return
        try:
            if self.owner_recorded:
                self.handle.seek(1)
                self.handle.truncate()
                self.handle.flush()
        finally:
            self.handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
