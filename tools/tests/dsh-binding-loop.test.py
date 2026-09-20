"""Explicit offline DSH agent-loop test. Args: Node executable, installed DSH bin.js.

Uses a local deterministic LLM adapter and a strict fake Bridge, never a paid
model, user home or Houdini scene. Persistent fixture logs remain for inspection.
"""
from pathlib import Path
import sys,json,subprocess,tempfile,threading,socket,time,uuid,re,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment
from dsh_web_auth import DshWebSession
from dsh_managed_runtime import spawn_frontend,stop_owned
node,cli=sys.argv[1:3]
legacy='--legacy' in sys.argv[3:]
attention='--attention' in sys.argv[3:]
flush_mode='false,false' if '--flush-false' in sys.argv[3:] else 'throw' if '--flush-throw' in sys.argv[3:] else ''
assert not flush_mode or attention, 'flush failures require --attention'
fixture=Path(tempfile.mkdtemp(prefix='dsh-binding-loop-'))
executor='a'*32;runtime='c'*32;executions=[]
generated=(ROOT/'src/generated-verb-contract.ts').read_text(encoding='utf-8')
version=int(re.search(r'EXPECTED_EXECUTION_CONTRACT_VERSION\s*=\s*(\d+)',generated)[1])
catalog=re.search(r"EXPECTED_VERB_CATALOG_HASH\s*=\s*['\"]([0-9a-f]+)",generated)[1]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path=='/requests/prepare':
            result={'ok':True,'executorId':executor,'runtimeId':runtime,'requestRef':runtime+'.'+uuid.uuid4().hex,
                    'executionContractVersion':version,'verbCatalog':{'hash':catalog}}
        elif self.path=='/exec':
            assert self.headers['X-DSH-Houdini-Executor']==executor
            allowed=[f'__result__={i}' for i in range(100 if attention else 2)]
            assert data['code'] in allowed and data.get('read_only','false')==('false' if attention else 'true'),data
            executions.append(data['code'])
            ordinal=int(data['code'].split('=')[1])+1
            result={'ok':True,'stdout':'','stderr':'','result':ordinal-1}
            if attention:
                result.update(transaction={'status':'committed','nodes':[]},
                    execution={'runtime_id':runtime,'executor_id':executor,'sequence':ordinal,
                        'observed_at':ordinal,'frame':1,'hip_path':str(fixture/'fixture.hip'),'hip_dir':str(fixture),
                        'read_only':False,'impact':{'attempted':True,'global':True,'nodes':[]},
                        'outputs':[{'ledger_index':1,'identity':1,'path':'/obj/fixture/OUT'}]},
                    evidence=[{'ledgerIndex':1,'verb':'verify_network','ok':True,'output':'/obj/fixture/OUT'}] if ordinal==1 else [])
        else: raise AssertionError('Unexpected endpoint '+self.path)
        raw=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
fake=ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=fake.serve_forever,daemon=True).start()
env=isolated_environment(fixture/'env')
env.update(DSH_HOME=str(fixture/'home'),DSH_HOUDINI_EXECUTOR_ID=executor,
    DSH_HOUDINI_BRIDGE_URL=f'http://127.0.0.1:{fake.server_port}',DSH_BINDING_FIXTURE_OUT=str(fixture/'passed.json'))
if legacy:env['DSH_BINDING_REPAIR_FIXTURE']='1'
if attention:env['DSH_ATTENTION_FIXTURE']='1'
if flush_mode:env['DSH_ATTENTION_FLUSH_FAILURES']=flush_mode
subprocess.run([node,str(ROOT/'tools/tests/prepare-shared-host-fixture.mjs'),cli,env['DSH_HOME'],str(ROOT)],
    cwd=ROOT,env=env,check=True,timeout=60,capture_output=True)
for name in ('houdini','houdini-dev'):
    file=fixture/'home/.agent-presets'/name/'agent.cordis.yml'
    file.write_text(file.read_text(encoding='utf-8').replace('bridgeUrl: http://127.0.0.1:8765',
        'bridgeUrl: '+env['DSH_HOUDINI_BRIDGE_URL']),encoding='utf-8')
overlay=fixture/'fixture.yml'
overlay.write_text('- insert:\n    - id: binding-fixture\n      name: '+(ROOT/'tools/tests/binding-loop-fixture.mjs').as_uri()+'\n',encoding='utf-8')
with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
log=fixture/'host.log'
with log.open('wb') as output:
    process=spawn_frontend([node,cli,'web','--patch',str(overlay),'--port',str(port),'--no-open'],node=node,
        cwd=fixture,env=env,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
try:
    auth=DshWebSession(f'http://127.0.0.1:{port}',str(log),str(fixture/'runtime.json'))
    def rpc(method,args):
        body={'type':'client-request','rpcId':str(uuid.uuid4()),'method':method,'payload':{'args':args}}
        request=urllib.request.Request(f'http://127.0.0.1:{port}/api/'+method,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
        with auth.open(request,timeout=10) as response:result=json.load(response)
        assert result['result']['ok'],result
        return result['result']['value']
    for _ in range(120):
        if process.poll() is not None:raise RuntimeError('Fixture Host failed; inspect '+str(log))
        try:auth.authorize(1);rpc('session/list',{'_request':{}});break
        except Exception:time.sleep(.25)
    else:raise RuntimeError('Fixture Host did not become ready')
    task=str(uuid.uuid4())
    rpc('session/create',{'request':{'sessionId':task,'cwd':str(fixture),'agentPreset':'houdini'}})
    rpc('session/selectModel',{'request':{'sessionId':task,'provider':'binding-fixture','model':'fixture'}})
    prompt='Run one hundred offline fixture changes.' if attention else 'Run the two read-only fixture queries.'
    rpc('session/prompt',{'request':{'sessionId':task,'requestId':str(uuid.uuid4()),'mode':'queue','content':[{'type':'text','text':prompt}]}})
    resumed_failures=0
    for _ in range(240):
        if (fixture/'passed.json').exists():break
        failure_file=fixture/'flush-failures.json'
        if flush_mode and failure_file.exists():
            failures=json.loads(failure_file.read_text(encoding='utf8'))
            assert all(not row.get('timeout') for row in failures),failures
            assert len({row['modelRequests'] for row in failures})==1,failures
            assert len({row['turn'] for row in failures})==len(failures), 'each failure must be a distinct retry'
            if len(failures)>resumed_failures:
                resumed_failures=len(failures)
                rpc('session/prompt',{'request':{'sessionId':task,'requestId':str(uuid.uuid4()),'mode':'queue',
                    'content':[{'type':'text','text':'Continue the offline fixture after persistence failure.'}]}})
        time.sleep(.25)
    else:raise RuntimeError('Agent loop did not reach the second valid request; inspect '+str(fixture))
    assert sorted(executions)==sorted(f'__result__={i}' for i in range(100 if attention else 2)),executions
    assert json.loads((fixture/'passed.json').read_text())['repaired'] is legacy
    if flush_mode:
        assert resumed_failures==len(flush_mode.split(',')),resumed_failures
        print('PASS persistence retry barriers:',flush_mode,'; zero additional model requests during failures')
    print('PASS real DSH loop: '+('100 changing execution notices bounded in actual adapter requests; original calls/results and user prompt retained' if attention else 'pre-step binding, scoped sessions.flush, two tool calls, complete results, valid next model request')+'; zero external model requests')
    print('Fixture:',fixture)
finally:
    stop_owned();fake.shutdown();fake.server_close()
