from pathlib import Path
import sys, subprocess, socket, tempfile, time, json, urllib.request, uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment
from dsh_web_auth import DshWebSession
from dsh_managed_runtime import spawn_frontend, stop_owned
node,cli,fixture,browser_module,hython_path=sys.argv[1:]
fixture=Path(fixture)
marker=json.loads((fixture/'shared-host-test.json').read_text(encoding='utf-8'))
assert marker=={'kind':'isolated-shared-host-test','plugin':str(ROOT)},'Only an explicitly prepared isolated fixture is accepted'
assert json.loads((Path(cli).parent.parent/'package.json').read_text(encoding='utf-8'))['name']=='@deepseek-ai/dsh'
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
env=isolated_environment(fixture/'env')
registry=fixture/('registry-'+uuid.uuid4().hex)
env.update(DSH_HOME=str(fixture/'home'),DSH_HOUDINI_EXECUTOR_REGISTRY=str(registry))
worker=None
worker_log=None
log=fixture/'frontend.log'
with log.open('wb') as stream:
    process=spawn_frontend([node,cli,'web','--patch',str(ROOT/'shared-host.cordis.yml'),'--port',str(port),'--no-open'],node=node,
        cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
try:
    base=f'http://127.0.0.1:{port}'
    auth=DshWebSession(base,str(log),str(fixture/'runtime.json'))
    deadline=time.monotonic()+45
    error=None
    connected=False
    while time.monotonic()<deadline:
        if process.poll() is not None: raise RuntimeError('Shared Host exited; inspect isolated log at '+str(log))
        try:
            auth.authorize(2)
            request=urllib.request.Request(base+'/api/houdiniTargets/list',data=json.dumps({
                'type':'client-request','rpcId':'shared-host-fixture','method':'houdiniTargets/list','payload':{'args':{}}}).encode(),
                headers={'Content-Type':'application/json'},method='POST')
            with auth.open(request,timeout=3) as response: result=json.load(response)
            assert result['result']['ok'],result
            assert result['result']['value']['candidates']==[],result
            connected=True
            print('PASS actual DSH Host boot, authenticated Connection/Gateway, shared target service; no model requests')
            task=str(uuid.uuid4())
            request=urllib.request.Request(base+'/api/session/create',data=json.dumps({
                'type':'client-request','rpcId':'create-fixture','method':'session/create','payload':{'args':{'request':{
                  'sessionId':task,'cwd':str(fixture),'agentPreset':'houdini'}}}}).encode(),headers={'Content-Type':'application/json'},method='POST')
            with auth.open(request,timeout=15) as response: created=json.load(response)
            assert created['result']['ok'],created
            hip=fixture/('test-'+uuid.uuid4().hex+'.hip')
            hip.write_bytes(b'isolated file identity fixture; never loaded')
            hython=Path(hython_path).resolve(strict=True)
            worker_log=(fixture/'worker.log').open('w',encoding='utf-8')
            worker=subprocess.Popen([str(hython),str(ROOT/'tools/tests/dsh-multi-executor.test.py'),'--worker',
                '--registry',str(registry),'--hip',str(hip),'--task',task],cwd=hython.parent,
                env=isolated_environment(fixture/('worker-'+uuid.uuid4().hex),executable=hython),stdin=subprocess.PIPE,
                stdout=worker_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            for _ in range(100):
                records=list((registry/'endpoints').glob('*.json')) if (registry/'endpoints').exists() else []
                if records:break
                if worker.poll() is not None:raise RuntimeError('fixture Houdini failed')
                time.sleep(.1)
            assert records,'worker registration timeout'
            endpoint=json.loads(records[0].read_text(encoding='utf-8'))
            select={'sessionId':task,'executorId':endpoint['executor_id'],'registrationId':endpoint['registration_id'],'expectedHip':str(fixture/'wrong-hip.hip')}
            request=urllib.request.Request(base+'/api/houdiniTargets/select',data=json.dumps({
                'type':'client-request','rpcId':'bind-fixture','method':'houdiniTargets/select','payload':{'args':{'input':select}}}).encode(),headers={'Content-Type':'application/json'},method='POST')
            with auth.open(request,timeout=15) as response: bound=json.load(response)
            assert not bound['result']['ok'],bound
            assert json.loads(records[0].read_text(encoding='utf-8'))['task_id'] is None
            result=subprocess.run([node,str(ROOT/'tools/tests/shared-picker-browser.mjs'),str(log),task,browser_module],
              cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
            print(result.stdout)
            if result.returncode: raise RuntimeError(result.stderr[-3000:])
            assert json.loads(records[0].read_text(encoding='utf-8'))['task_id']==task
            print('PASS actual browser confirmation -> DSH session -> real Houdini claim -> actual session flush')
            break
        except Exception as exc:
            if connected: raise
            error=type(exc).__name__+': '+str(exc)
            time.sleep(.25)
    else: raise RuntimeError('Shared Host readiness failed: '+str(error))
finally:
    if worker is not None:
        if worker.poll() is None:worker.kill()
        worker.communicate(timeout=10)
    if worker_log is not None:worker_log.close()
    stop_owned()
