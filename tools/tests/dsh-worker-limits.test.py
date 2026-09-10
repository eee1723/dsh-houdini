"""Owned worker deadline/cancel/memory tests using small disposable Python workers."""
from pathlib import Path
import os
import sys
import tempfile
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
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
print('owned worker deadline/cancel/committed-memory cap passed')
