"""Historical v8 HTTP regression, excluded from the current test suite."""
from pathlib import Path
import json
import subprocess
import sys
import threading
import time
import tempfile
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import hou
import dsh_bridge as b

def reject(fn,match):
    try:fn()
    except Exception as e:assert match in str(e),str(e)
    else:raise AssertionError('expected rejection')

server=ThreadingHTTPServer(('127.0.0.1',0),b._Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
child=None
scratch=tempfile.TemporaryDirectory(prefix='dsh-delivery-http-')
try:
    hou.hipFile.save((Path(scratch.name)/'session.hip').as_posix())
    b._pump_active=True
    child=subprocess.Popen(['node',str(ROOT/'tools/tests/delivery-http-driver.mjs'),f'http://127.0.0.1:{server.server_port}'],
                           cwd=str(ROOT),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    deadline=time.monotonic()+60
    while child.poll() is None and time.monotonic()<deadline:
        b._pump();time.sleep(.01)
    if child.poll() is None:child.kill();raise AssertionError('integration timeout')
    output=child.communicate()[0]
    print(output)
    assert child.returncode==0,output
    reject(lambda:b.run_delivery({'request':{'action':'check'}}),'provenance')
    context={'runtime':b._RUNTIME_ID,'scene':b._SCENE_EPOCH,'hip':hou.hipFile.path()}
    b._scene_changed(hou.hipFileEventType.BeforeLoad)
    changed=b.run_delivery({'owner_session':'a','owner_call':'1','binding':context,'request':{'action':'check','contract':{}}})
    assert changed['reset_required'],changed
    with b._jobs_lock:b._jobs['pending']={'status':'queued'}
    blocked=b.run_delivery({'owner_session':'a','owner_call':'1','request':{'action':'check','contract':{}}})
    assert blocked['busy'],blocked
    with b._jobs_lock:b._jobs.clear()
    # Validation happens before cook: Python/solver/file/custom snippet isn't admitted.
    p=hou.node('/obj').createNode('geo','__unsupported_delivery')
    try:
        c=p.createNode('null','C');out=p.createNode('null','OUT');p.createNode('python','UNSUPPORTED')
        reject(lambda:b.run_delivery({'owner_session':'a','owner_call':'1','request':{'action':'inspect',
            'scope':{'parent':p.path(),'output':out.path(),'controller':c.path()}}}),'unsupported delivery node')
        assert not b._delivery_busy
    finally:p.destroy()
    errors=[]
    def worker():
        try:b.run_delivery({})
        except Exception as e:errors.append(str(e))
    w=threading.Thread(target=worker);w.start();w.join()
    assert errors and 'owning thread' in errors[0]
finally:
    b._pump_active=False
    if child is not None and child.poll() is None:child.kill();child.wait()
    server.shutdown();server.server_close();thread.join(3)
    with b._jobs_lock:b._jobs.clear();b._job_meta.clear()
    scratch.cleanup()
print('delivery service integration/lifecycle/thread/busy/unsupported passed')
