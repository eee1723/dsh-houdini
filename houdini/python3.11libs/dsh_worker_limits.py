"""Own one gated Windows worker tree. Never attaches to an existing live process."""
import ctypes
from ctypes import wintypes
import os
import math
from pathlib import Path
import subprocess
import tempfile
import time


class WorkerJob:
    def __init__(self, process, memory_mb):
        class Basic(ctypes.Structure):
            _fields_ = [('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),
                ('flags',wintypes.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),
                ('active',wintypes.DWORD),('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(str(i),ctypes.c_uint64) for i in range(6)]
        class Extended(ctypes.Structure):
            _fields_ = [('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),
                ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        k=self.kernel
        k.CreateJobObjectW.restype=wintypes.HANDLE
        k.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
        k.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        k.TerminateJobObject.argtypes=[wintypes.HANDLE,wintypes.UINT]
        k.CloseHandle.argtypes=[wintypes.HANDLE]
        self.handle=k.CreateJobObjectW(None,None)
        limits=Extended();limits.basic.flags=0x2000|0x200  # kill-on-close + aggregate committed-memory limit
        limits.job_memory=memory_mb*1024*1024
        if (not self.handle or not k.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits))
                or not k.AssignProcessToJobObject(self.handle,wintypes.HANDLE(int(process._handle)))):
            error=ctypes.get_last_error()
            self.close()
            raise OSError(error,'cannot establish worker job limits')

    def terminate(self):
        if not self.kernel.TerminateJobObject(self.handle,1):
            raise OSError(ctypes.get_last_error(),'cannot terminate owned worker tree')

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle);self.handle=None


def run_gated_worker(command, *, cwd, env, timeout=120, memory_mb=4096, cancel_file=None):
    """Worker must wait for a GO line before loading user assets or executing code.

    Job caps committed memory for this tree, not GPU allocations or the whole host.
    Allocation denial may raise/crash inside worker; it is not labeled a proved OOM.
    started means a process was created; released means GO was sent, not that the
    payload finished. Startup failures retain phase/error without releasing work.
    """
    if os.name!='nt':raise RuntimeError('worker limits currently require Windows')
    if type(memory_mb) is not int or not 128<=memory_mb<=65536:raise ValueError('memory_mb must be 128..65536')
    if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=86400:raise ValueError('timeout must be finite and in 0..86400 seconds')
    cancel=Path(cancel_file) if cancel_file else None
    if cancel and cancel.exists():
        return {'status':'cancelled_before_start','returncode':None,'output':'','started':False,
                'released':False,'phase':'spawn'}
    with tempfile.TemporaryFile() as log:
        process=None;job=None;status='failed';started=time.monotonic()
        phase='spawn';released=False;error=None
        try:
            process=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=log,stderr=log,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            phase='limits'
            job=WorkerJob(process,memory_mb)
            phase='release'
            # Recheck after process creation/assignment, before any user payload.
            if cancel and cancel.exists():
                status='cancelled';job.terminate()
            elif time.monotonic()-started>=timeout:
                status='timed_out';job.terminate()
            elif process.poll() is not None:
                raise RuntimeError('worker exited before GO')
            else:
                process.stdin.write(b'GO\n');process.stdin.flush()
                released=True;process.stdin.close();phase='run'
                while process.poll() is None:
                    if cancel and cancel.exists():status='cancelled';job.terminate();break
                    if time.monotonic()-started>=timeout:status='timed_out';job.terminate();break
                    time.sleep(.05)
            process.wait(timeout=15)
            if status=='failed' and released and process.returncode==0:status='completed'
        except (OSError, RuntimeError, subprocess.SubprocessError) as failure:
            status='failed';error=f'{type(failure).__name__}: {failure}'
        finally:
            if job:job.close()  # also removes descendants after normal parent exit
            if process is not None:
                if process.poll() is None:process.kill();process.wait(timeout=15)
                if process.stdin and not process.stdin.closed:
                    try:process.stdin.close()
                    except OSError:pass  # pipe may have broken before GO was flushed
        log.seek(0,2);size=log.tell();log.seek(max(0,size-12000))
        output=log.read().decode('utf-8',errors='replace')
        result={'status':status,'returncode':process.returncode if process is not None else None,
                'output':output,'started':process is not None,'released':released,'phase':phase,
                'memory_mb':memory_mb,'elapsed_seconds':round(time.monotonic()-started,3),
                'scope':'owned Windows process tree; committed-memory cap; no GPU or external-service limit'}
        if error:result['error']=error
        return result
