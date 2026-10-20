"""Actual owned worker trees must exit before their runtime files are removed."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
sys.path.insert(0, str(ROOT/'houdini/python3.11libs'))

if len(sys.argv)>1 and sys.argv[1]=='--fixture':
    assert sys.stdin.readline().strip()=='GO'
    if sys.argv[2]=='descendant':
        child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
        print(json.dumps({'owned_child':child.pid}),flush=True)
    elif sys.argv[2]=='wait':
        print('OWNED_WORKER_RUNNING',flush=True)
        time.sleep(60)
    raise SystemExit(0)

from houdini_test_environment import reexec_unpacked_test_cli
reexec_unpacked_test_cli()
import dsh_worker_limits as limits
if os.name!='nt':
    print('SKIP Windows worker ownership checks')
    raise SystemExit(0)

def alive(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:
        assert ctypes.get_last_error()==87, ctypes.get_last_error()
        return False
    try:
        status=wintypes.DWORD()
        assert kernel.GetExitCodeProcess(handle,ctypes.byref(status))
        return status.value==259
    finally:
        kernel.CloseHandle(handle)

with tempfile.TemporaryDirectory(prefix='dsh-worker-lifecycle-') as raw:
    root=Path(raw)
    command=[sys.executable,str(Path(__file__).resolve()),'--fixture']
    def run(mode,**options):
        return limits.run_gated_worker(command+[mode],cwd=root,env=os.environ.copy(),
                                       timeout=options.pop('timeout',15),memory_mb=4096,**options)
    completed=run('descendant')
    assert completed['status']=='completed' and completed['returncode']==0,completed
    assert completed['released'] and completed['tree_reaped'],completed
    child=json.loads(completed['output'].strip())['owned_child']
    assert not alive(child),'normal parent exit must not leave its renderer child running'

    cancel=root/'cancel.request'
    cancel.write_text('cancel',encoding='utf-8')
    before=run('wait',cancel_file=cancel)
    assert not before['started'] and not before['released'] and before['tree_reaped'],before
    cancel.unlink()
    timer=threading.Timer(1,lambda:cancel.write_text('cancel',encoding='utf-8'))
    timer.start()
    try:
        stopped=run('wait',cancel_file=cancel)
    finally:
        timer.join()
    assert stopped['status']=='cancelled' and stopped['returncode']!=0 and stopped['tree_reaped'],stopped
    cancel.unlink()
    expired=run('wait',timeout=1)
    assert expired['status']=='timed_out' and expired['tree_reaped'],expired
    with patch.object(limits.WorkerJob,'reap',side_effect=TimeoutError('injected cleanup observation failure')):
        uncertain=run('descendant')
    assert uncertain['status']=='completed' and not uncertain['tree_reaped'],uncertain
    assert 'injected cleanup' in uncertain['cleanup_error'],uncertain
    missing=limits.run_gated_worker([str(root/'missing.exe')],cwd=root,env=os.environ.copy())
    assert not missing['started'] and missing['tree_reaped'] and missing['phase']=='spawn',missing
print('PASS worker lifecycle: owned descendants reaped; GO, execution and cleanup facts remain distinct')

# Existing deadline, admission and memory limits remain covered.
from dsh_worker_limits import run_gated_worker
with tempfile.TemporaryDirectory() as temp:
    def run(code,**options):
        script=Path(temp)/'worker.py'
        script.write_text('import sys\nassert sys.stdin.readline().strip()=="GO"\n'+code,encoding='utf-8')
        return run_gated_worker([sys.executable,str(script)],cwd=temp,env=dict(os.environ),memory_mb=128,**options)
    assert run('print("done")')['status']=='completed'
    r=run('import time\ntime.sleep(60)',timeout=.5)
    assert r['status']=='timed_out' and r['elapsed_seconds']<5,r
    cancel=Path(temp)/'cancel'
    timer=threading.Timer(.5,lambda:cancel.write_text('cancel'))
    timer.start()
    try:r=run('import time\ntime.sleep(60)',cancel_file=cancel)
    finally:timer.join()
    assert r['status']=='cancelled',r
    r=run('raise RuntimeError("must not start")',cancel_file=cancel)
    assert not r['started'] and r['status']=='cancelled_before_start',r
    r=run('try:\n x=bytearray(256*1024*1024)\nexcept MemoryError:\n print("allocation denied")\nelse:\n raise RuntimeError("memory cap failed")')
    assert r['status']=='completed' and 'allocation denied' in r['output'],r
    marker=Path(temp)/'escaped-child'
    child='import time;from pathlib import Path;time.sleep(2);Path('+repr(str(marker))+').write_text("alive")'
    r=run('import subprocess\nsubprocess.Popen([sys.executable,"-c",'+repr(child)+'])\nprint("parent done")')
    import time
    time.sleep(2.5)
    assert r['status']=='completed' and not marker.exists(),'descendant survived parent job close'

    # Admission failures must produce a recoverable result, not lose the report.
    r=run_gated_worker([str(Path(temp)/'missing-worker.exe')],cwd=temp,env=dict(os.environ))
    assert r['status']=='failed' and not r['started'] and not r['released'],r
    assert r['phase']=='spawn' and r['error'],r

    real_job=limits.WorkerJob
    processes=[]
    def rejected_job(process,memory_mb):
        processes.append(process)
        raise OSError('injected job assignment failure')
    with patch.object(limits,'WorkerJob',side_effect=rejected_job):
        r=run('raise RuntimeError("must never be released")')
    assert r['status']=='failed' and r['phase']=='limits' and not r['released'],r
    assert processes[-1].poll() is not None and processes[-1].stdin.closed

    cancel.unlink()
    def cancel_during_admission(process,memory_mb):
        job=real_job(process,memory_mb)
        cancel.write_text('cancel before GO')
        return job
    with patch.object(limits,'WorkerJob',side_effect=cancel_during_admission):
        r=run('raise RuntimeError("must never be released")',cancel_file=cancel)
    assert r['status']=='cancelled' and not r['released'],r

    # Model elapsed startup time without relying on machine speed.
    clock=[100.0]
    def slow_admission(process,memory_mb):
        job=real_job(process,memory_mb)
        clock[0]+=2
        return job
    with patch.object(limits,'WorkerJob',side_effect=slow_admission), patch.object(limits.time,'monotonic',side_effect=lambda:clock[0]):
        r=run('raise RuntimeError("expired work must never be released")',timeout=1)
    assert r['status']=='timed_out' and not r['released'],r

    # A worker may close stdin/exit while the parent establishes its job.
    def exited_during_admission(process,memory_mb):
        job=real_job(process,memory_mb)
        process.terminate();process.wait(timeout=5)
        return job
    with patch.object(limits,'WorkerJob',side_effect=exited_during_admission):
        r=run('raise RuntimeError("must never be released")')
    assert r['status']=='failed' and not r['released'] and r['phase']=='release',r

    # Failure in the GO pipe must not escape or flush a buffered GO at cleanup.
    def broken_go_pipe(process,memory_mb):
        job=real_job(process,memory_mb)
        processes.append(process)
        pipe=process.stdin
        class BrokenPipe:
            @property
            def closed(self):return pipe.closed
            def write(self,data):return pipe.write(data)
            def flush(self):raise BrokenPipeError('injected GO flush failure')
            def close(self):return pipe.close()
        process.stdin=BrokenPipe()
        return job
    with patch.object(limits,'WorkerJob',side_effect=broken_go_pipe):
        r=run('raise RuntimeError("must never be released")')
    assert r['status']=='failed' and not r['released'] and r['phase']=='release',r
    assert 'GO flush failure' in r['error'] and processes[-1].poll() is not None,r
    assert processes[-1].stdin.closed
print('owned worker deadline/cancel/committed-memory cap passed')
