"""Retired review transport cannot grant scene or parameter capabilities."""
from pathlib import Path
import sys, threading, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import dsh_bridge as b
import dsh_hou_helpers as h
assert not hasattr(b,'run_review') and not hasattr(b,'_review_service')
assert not hasattr(h,'_review_parameter_access')
server=ThreadingHTTPServer(('127.0.0.1',0),b._Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
 request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/review',data=b'{}',headers={'Content-Type':'application/json'})
 try: urllib.request.urlopen(request,timeout=3)
 except urllib.error.HTTPError as error: assert error.code==404,error.code
 else:raise AssertionError('retired review route still active')
finally:server.shutdown();server.server_close();thread.join(3)
print('retired review HTTP endpoint rejected')
