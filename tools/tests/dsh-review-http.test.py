"""Real transport integration, isolated hython/server; no model calls or live runtime."""
from pathlib import Path
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import dsh_bridge as b
server=ThreadingHTTPServer(('127.0.0.1',0),b._Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
process=None
try:
    b._pump_active=True
    process=subprocess.Popen(['node',str(ROOT/'tools/tests/review-http-driver.mjs'),f'http://127.0.0.1:{server.server_port}'],
        cwd=str(ROOT),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    deadline=time.monotonic()+45
    while process.poll() is None and time.monotonic()<deadline:
        b._pump();time.sleep(.01)
    if process.poll() is None:process.kill();raise AssertionError('review HTTP integration timeout')
    output=process.communicate()[0];print(output)
    assert process.returncode==0,output
    assert not b._review_service.active() and not b._review_busy
finally:
    b._pump_active=False
    if process and process.poll() is None:process.kill();process.wait()
    server.shutdown();server.server_close();thread.join(3)
print('review HTTP integration passed')
