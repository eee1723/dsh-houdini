"""Explicit force repair: real disposable Windows Node listener, never live DSH/HIP."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
sys.modules.setdefault('hou', types.SimpleNamespace())
import dsh_launcher as launcher
import dsh_managed_runtime as runtime

def rejects(action, text):
    try:
        action()
    except RuntimeError as error:
        assert text in str(error), error
    else:
        raise AssertionError('Expected refusal: ' + text)

# Force bypasses DSH activity only, never another Bridge or running HOM.
with patch.object(launcher, '_port_open', return_value=True), \
     patch.object(launcher, '_port_pid', return_value=os.getpid()+1), \
     patch.object(launcher, '_force_frontend_repair', side_effect=AssertionError('foreign bridge caused shutdown')):
    rejects(lambda: launcher._service_preflight(force_frontend=True), 'bridge port conflict')
with patch.object(launcher, '_port_open', return_value=True), \
     patch.object(launcher, '_port_pid', return_value=os.getpid()), \
     patch.object(launcher, '_require_bridge_idle', side_effect=RuntimeError('active execution')), \
     patch.object(launcher, '_force_frontend_repair', side_effect=AssertionError('active HOM caused shutdown')):
    rejects(lambda: launcher._service_preflight(force_frontend=True), 'active execution')
order=[]
with patch.object(launcher, '_port_open', return_value=True), \
     patch.object(launcher, '_port_pid', return_value=os.getpid()), \
     patch.object(launcher, '_require_bridge_idle', side_effect=lambda: order.append('idle')), \
     patch.object(launcher, '_force_frontend_repair', side_effect=lambda: order.append('stop')), \
     patch.object(launcher, '_frontend_online', return_value=False):
    assert launcher._service_preflight(force_frontend=True)['bridge_online']
assert order==['idle','stop','idle'],order

# Parse real health responses: missing, boolean and negative counters are not idle.
class Response:
    def __init__(self, health): self.health=health
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self): return json.dumps(self.health).encode('utf-8')
for health in ({}, {'ok':True,'activeJobs':0},
               {'ok':True,'activeJobs':0,'activeRequests':False},
               {'ok':True,'activeJobs':-1,'activeRequests':0},
               {'ok':True,'activeJobs':1,'activeRequests':0},
               {'ok':True,'activeJobs':0,'activeRequests':1},
               {'ok':False,'activeJobs':0,'activeRequests':0}):
    with patch.object(launcher.urllib.request,'build_opener',return_value=types.SimpleNamespace(open=lambda *a,**k:Response(health))):
        rejects(launcher._require_bridge_idle,'active or unknown')
with patch.object(launcher.urllib.request,'build_opener',return_value=types.SimpleNamespace(
        open=lambda *a,**k:Response({'ok':True,'activeJobs':0,'activeRequests':0}))):
    launcher._require_bridge_idle()

# If a new request appears after DSH shutdown, report partial repair, not success.
with patch.object(launcher,'_port_open',return_value=True), \
     patch.object(launcher,'_port_pid',return_value=os.getpid()), \
     patch.object(launcher,'_require_bridge_idle',side_effect=[None,RuntimeError('late request')]), \
     patch.object(launcher,'_force_frontend_repair') as stopped:
    rejects(lambda:launcher._service_preflight(force_frontend=True),'late request')
    assert stopped.call_count==1

assert os.name=='nt'
with tempfile.TemporaryDirectory(prefix='dsh-force-repair-中文 空格-') as directory:
    root=Path(directory)
    cli=root/'.npm-cache/_npx/fixture/node_modules/@deepseek-ai/dsh/lib/bin.js'
    cli.parent.mkdir(parents=True)
    (cli.parent.parent/'package.json').write_text(json.dumps({'name':'@deepseek-ai/dsh'}),encoding='utf-8')
    cli.write_text("const net=require('node:net'); const port=Number(process.argv[process.argv.indexOf('--port')+1]); net.createServer(s=>s.end()).listen(port,'127.0.0.1',()=>console.log('ready'));",encoding='utf-8')
    with socket.socket() as temporary:
        temporary.bind(('127.0.0.1',0))
        port=temporary.getsockname()[1]
    argv=[launcher.NODE,str(cli),'web','--port',str(port),'--no-open']
    record={'ProcessId':999,'ExecutablePath':launcher.NODE}
    roots=[root/'.npm-cache/_npx']
    assert runtime._frontend_identity(record,argv,roots,port)['bin']==str(cli.resolve())
    rejects(lambda: runtime._frontend_identity(record,argv,[root/'other'],port),'exact DSH')
    rejects(lambda: runtime._frontend_identity(record,argv,roots,port+1),'exact DSH')
    rejects(lambda: runtime._frontend_identity(record,argv+['--other'],roots,port),'exact DSH')
    rejects(lambda: runtime._frontend_identity(record,[argv[0],'-e','unrelated_server()',*argv[1:]],roots,port),'exact DSH')
    assert runtime._frontend_identity(record,[argv[0],'--import',runtime._NODE_START_GATE,*argv[1:]],roots,port)['pid']==999
    rejects(lambda: runtime._frontend_identity({**record,'ExecutablePath':str(root/'houdini.exe')},argv,roots,port),'Node executable')
    process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        assert process.stdout.readline().strip()==b'ready'
        # Exact identity but listener changed: do not terminate even our fixture.
        rejects(lambda: runtime.stop_verified_frontend(process.pid,cli_roots=roots,port=port,
                  listener_pid=lambda: process.pid+1),'identity changed')
        assert process.poll() is None
        with patch.object(launcher,'_PROJECT_ROOT',str(root)), patch.object(launcher,'_MANAGED',None), \
             patch.object(launcher,'FRONTEND_PORT',port), \
             patch.object(launcher,'FRONTEND_RUNTIME_STATE',str(root/'runtime.json')), \
             patch.object(launcher,'_port_pid',return_value=process.pid):
            rejects(launcher._frontend_online,'frontend port conflict')
            assert process.poll() is None
            launcher._force_frontend_repair()
        assert process.wait(timeout=5) is not None
        assert not launcher._port_open('127.0.0.1',port)
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
print('force repair identity, isolation, guarded termination and port release passed')
