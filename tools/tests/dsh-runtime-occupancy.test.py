from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import dsh_deployment as deployment


def blocked(path):
    try:
        lease=deployment.FileLease(path)
    except deployment.LeaseBusyError as error:
        return error
    else:
        lease.close()
        raise AssertionError('concurrent process acquired the runtime')


if len(sys.argv)>1:
    lock=Path(sys.argv[1])
    lease=deployment.FileLease(lock)
    lease.record_owner({'hip_path':'E:/artist/中文工程.hip','hip_is_new':False,'houdini_version':'21.0.440','pid':999})
    (lock.parent/'ready').write_text('ready')
    while not (lock.parent/'release').exists():
        time.sleep(.03)
    lease.close()
else:
    with tempfile.TemporaryDirectory(prefix='dsh-occupancy-') as temporary:
        folder=Path(temporary)
        lock=folder/'runtime.lock'
        process=subprocess.Popen([sys.executable,__file__,str(lock)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            deadline=time.monotonic()+10
            while not (folder/'ready').exists():
                assert process.poll() is None and time.monotonic()<deadline
                time.sleep(.03)
            error=blocked(lock)
            assert error.owner and error.owner['pid']==process.pid, error.owner
            assert error.owner['hip_path'].endswith('中文工程.hip')
            with patch.object(deployment,'_process_started',return_value='different-process-birth'):
                assert blocked(lock).owner is None,'reused PID or stale identity cannot name the occupant'
            (folder/'release').touch()
            assert process.wait(timeout=10)==0
            assert lock.read_bytes()==b'0','normal release clears stale occupant metadata'
            with deployment.FileLease(lock) as next_lease:
                next_lease.record_owner({'hip_is_new':True,'houdini_version':'22.0.368'})
                error=blocked(lock)
                assert error.owner['pid']==os.getpid()
                assert error.owner['hip_is_new'] is True
                next_lease.record_owner({'hip_path':'字'*9000})
                oversized=blocked(lock)
                assert oversized.owner['pid']==os.getpid() and oversized.owner['details_unavailable']=='metadata_size_limit'
            (folder/'ready').unlink()
            (folder/'release').unlink()
            process=subprocess.Popen([sys.executable,__file__,str(lock)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            deadline=time.monotonic()+10
            while not (folder/'ready').exists():
                assert process.poll() is None and time.monotonic()<deadline
                time.sleep(.03)
            process.kill();process.wait(timeout=10)
            with deployment.FileLease(lock) as next_lease:
                assert blocked(lock).owner is None,'dead owner record is not the new lock holder'
                next_lease.record_owner({'hip_path':'E:/new.hip','hip_is_new':False})
                assert blocked(lock).owner['hip_path']=='E:/new.hip'
            lock.write_bytes(b'0{damaged')
            with deployment.FileLease(lock):
                assert blocked(lock).owner is None
        finally:
            if process.poll() is None:
                process.kill();process.wait(timeout=10)
    print('runtime occupancy: real competing processes, exact occupant, PID reuse, normal release, crash, stale and damaged metadata passed')
