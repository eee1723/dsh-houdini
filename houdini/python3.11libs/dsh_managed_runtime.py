"""Houdini process identity and owned test-driver process trees; no Desktop ownership."""
from __future__ import annotations

import os
import base64
import subprocess
import threading
import uuid

# Process identity is not a Bridge generation, PID, file path or node ownership.
# Never inherit it from the environment: a relaunched Houdini is a new executor.
if '_EXECUTOR_PID' not in globals() or _EXECUTOR_PID != os.getpid():
    _EXECUTOR_PID = os.getpid()
    _EXECUTOR_ID = uuid.uuid4().hex


def executor_identity():
    return _EXECUTOR_ID


def has_owned_frontend():
    with _JOB_LOCK:
        return _PROCESS is not None and _PROCESS.poll() is None

# Repair reloads implementation, but must retain the live native ownership handle.
if '_JOB_LOCK' not in globals():
    _JOB = None
    _PROCESS = None
    _JOB_LOCK = threading.RLock()
    _STOP_CURRENT = object()

# Wait before importing the CLI or spawning its npx shell. Otherwise cmd.exe can
# create descendants before AssignProcessToJobObject establishes inheritance.
_NODE_START_GATE = "data:text/javascript;base64," + base64.b64encode(b"""
import { readSync } from 'node:fs';
const gate = Buffer.alloc(1);
if (readSync(0, gate, 0, 1, null) !== 1 || gate[0] !== 71) process.exit(1);
// Do not make future DSH fork/worker children inherit this one-use startup gate.
const option = process.execArgv.indexOf(import.meta.url);
if (option > 0 && process.execArgv[option - 1] === '--import') process.execArgv.splice(option - 1, 2);
""").decode("ascii")

_NODE_SHELL_ENTRY = """
const child = require('node:child_process').spawn(process.argv[1], {
  shell: true, stdio: ['ignore', 'inherit', 'inherit'], windowsHide: true
});
child.on('error', error => { console.error(error); process.exit(1); });
child.on('exit', code => process.exit(code ?? 1));
"""






def stop_owned(expected_process=_STOP_CURRENT):
    """Stop our Job, optionally only the exact launch attempt; None never matches."""
    global _JOB, _PROCESS
    with _JOB_LOCK:
        if (_JOB is None or expected_process is None
                or expected_process is not _STOP_CURRENT and expected_process is not _PROCESS):
            return False
        import ctypes
        close = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
        close.argtypes = [ctypes.c_void_p]
        if not close(_JOB):
            raise OSError(ctypes.get_last_error(), "Could not close the owned frontend Job")
        process = _PROCESS
        _JOB = None
        _PROCESS = None
        if process is not None:
            process.wait(timeout=10)
        return True


def owns_pid(pid):
    """Read Job membership only; never adopt a listener from its PID or marker."""
    with _JOB_LOCK:
        if _JOB is None or pid is None:
            return False
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        process = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not process:
            return False
        try:
            belongs = wintypes.BOOL()
            return bool(kernel.IsProcessInJob(process, _JOB, ctypes.byref(belongs)) and belongs.value)
        finally:
            kernel.CloseHandle(process)












def spawn_frontend(command, *, node, shell=False, replace_existing=True, **kwargs):
    """Create a Node CLI/npx tree, establish ownership, then release its entrypoint."""
    with _JOB_LOCK:
        if not replace_existing and _PROCESS is not None and _PROCESS.poll() is None:
            raise RuntimeError('Another owned frontend is active; component preview cannot replace it')
        # Native Node entry keeps import.meta.main, argv and CLI exit semantics.
        args = [node, "--import", _NODE_START_GATE]
        args.extend(["-e", _NODE_SHELL_ENTRY, command] if shell else command[1:])
        process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE, shell=False, **kwargs,
        )
        try:
            own_process(process)
            process.stdin.write(b"G")
            process.stdin.close()
            process.stdin = None
            return process
        except Exception:
            # This handle was just created here. No port/PID discovery authorizes cleanup.
            if _PROCESS is process:
                stop_owned()
            elif process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            process.stdin.close()
            raise


def own_process(process):
    """Kill only this frontend tree on repair or Houdini exit, never by port."""
    global _JOB, _PROCESS
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
    with _JOB_LOCK:
        stop_owned()
        job = kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle))):
            if job:
                kernel.CloseHandle(job)
            process.kill()
            raise RuntimeError("Could not establish owned frontend lifetime; no external service was stopped")
        _JOB, _PROCESS = job, process
