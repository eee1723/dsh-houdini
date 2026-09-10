"""Owned worker deadline/cancel/memory tests using small disposable Python workers."""
from pathlib import Path
import os
import sys
import tempfile
import threading
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import dsh_worker_limits as limits
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
