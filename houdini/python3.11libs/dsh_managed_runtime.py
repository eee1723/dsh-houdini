"""Managed launcher paths/environment and owned Windows process lifetime."""
from __future__ import annotations

import json
import os
from pathlib import Path

_JOB = None
_PID = None


def context(project_root=None):
    filename = os.environ.get("DSH_HOUDINI_MANAGED_CONTEXT")
    if not filename:
        return None
    with open(filename, encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schemaVersion") != 1:
        raise RuntimeError("Unsupported managed runtime context")
    if project_root and Path(project_root).resolve() != (Path(data["install"]) / "app/node_modules/dsh-houdini").resolve():
        raise RuntimeError("Source and managed runtime paths are mixed; restart Houdini")
    return data


def environment():
    data = context()
    if data is None:
        return dict(os.environ)
    from dsh_deployment import runtime_env
    return runtime_env(data)


def stop_owned():
    global _JOB, _PID
    if _JOB is not None:
        import ctypes
        close = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
        close.argtypes = [ctypes.c_void_p]
        close(_JOB)
        _JOB = None
        _PID = None
        return True
    return False


def own_process(process):
    """Kill only this frontend tree on repair or Houdini exit, never by port."""
    global _JOB, _PID
    if os.name != "nt":
        raise RuntimeError("Managed releases currently require Windows")
    import ctypes
    from ctypes import wintypes
    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
    class Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    stop_owned()
    job = kernel.CreateJobObjectW(None, None)
    limits = Extended()
    limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle))):
        if job:
            kernel.CloseHandle(job)
        process.kill()
        raise RuntimeError("Could not establish owned frontend lifetime; no external service was stopped")
    _JOB, _PID = job, process.pid
