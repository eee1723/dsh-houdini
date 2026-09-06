"""Actual Host/HTTP replay on a temporary clone of the saved e8c90d2b artifact.

Usage: hython tools/prototypes/replay_delivery_reuse.py SOURCE_HIP NEW_REPORT.json
Original bytes never saved or edited. Fixture provenance is installed only in the
disposable process; this does not change the live session's ownership boundary.
"""
from pathlib import Path
from http.server import ThreadingHTTPServer
import hashlib,subprocess,sys,tempfile,threading,time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
source=Path(sys.argv[1]).resolve(strict=True);report=Path(sys.argv[2]).resolve()
if hou.isUIAvailable():raise RuntimeError('disposable hython only')
if report.exists() or report.suffix.lower()!='.json':raise ValueError('new JSON report required')
sha=hashlib.sha256(source.read_bytes()).hexdigest()
if sha!='63f833ded74897f3d0cdf8c37df05d600c0033595b9a0bdb1c7a7bc64f5b61af':raise ValueError('unexpected frozen source bytes')
hou.hipFile.load(source.as_posix(),suppress_save_prompt=True,ignore_load_warnings=True)
with tempfile.TemporaryDirectory(prefix='dsh-frozen-replay-') as tmp:
    clone=Path(tmp)/'clone.hip';hou.hipFile.save(clone.as_posix())
    assert Path(hou.hipFile.path()).resolve()==clone.resolve()
    with b.dsh_hou_helpers._execution_owner('frozen-replay','fixture'):
        b.dsh_hou_helpers._register_owned_node(hou.node('/obj/l_bracket'))
    server=ThreadingHTTPServer(('127.0.0.1',0),b._Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    child=None
    try:
        b._pump_active=True
        child=subprocess.Popen(['node',str(ROOT/'tools/prototypes/replay_delivery_reuse.mjs'),
             f'http://127.0.0.1:{server.server_port}',str(report),sha],cwd=str(ROOT),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        end=time.monotonic()+60
        while child.poll() is None and time.monotonic()<end:b._pump();time.sleep(.01)
        if child.poll() is None:child.kill();raise AssertionError('replay timed out')
        output=child.communicate()[0];print(output)
        assert child.returncode==0,output
    finally:
        b._pump_active=False
        if child is not None and child.poll() is None:child.kill();child.wait()
        server.shutdown();server.server_close();worker.join(3)
assert hashlib.sha256(source.read_bytes()).hexdigest()==sha
print('source HIP unchanged:',sha)
