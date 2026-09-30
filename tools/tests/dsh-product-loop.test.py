"""Offline real DSH loop. Args: Node executable, exact installed DSH bin.js.

Uses an isolated DSH_HOME, local deterministic adapter and strict fake Bridge.
No credentials, external model requests or Houdini process are used.
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
product_mode='--product-mode' in sys.argv[3:]
fixture=Path(tempfile.mkdtemp(prefix='dsh-product-loop-'))
executor='a'*32;runtime='c'*32;executions=[];errors=[]
generated=(ROOT/'src/generated-verb-contract.ts').read_text(encoding='utf-8')
version=int(re.search(r'EXPECTED_EXECUTION_CONTRACT_VERSION\s*=\s*(\d+)',generated)[1])
catalog=re.search(r"EXPECTED_VERB_CATALOG_HASH\s*=\s*['\"]([0-9a-f]+)",generated)[1]

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        try:
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/requests/prepare':
                result={'ok':True,'executorId':executor,'runtimeId':runtime,'requestRef':runtime+'.'+uuid.uuid4().hex,
                        'executionContractVersion':version,'verbCatalog':{'hash':catalog}}
            elif self.path=='/exec':
                assert self.headers['X-DSH-Houdini-Executor']==executor
                measurement=data['code']=='__result__ = "product_fixture_measurement"'
                assert measurement,data['code']
                assert (data.get('read_only')=='true') is measurement,data
                executions.append(data['code'])
                output='/obj/product_fixture/OUT'
                result={'ok':True,'stdout':'','stderr':'','result':{'measured':True},
                    'transaction':{'status':'no_scene_change','nodes':[]},
                    'execution':{'runtime_id':runtime,'executor_id':executor,'sequence':len(executions),'observed_at':len(executions),
                        'frame':1,'hip_path':str(fixture/'fixture.hip'),'hip_dir':str(fixture),'read_only':measurement,
                        'impact':{'attempted':False,'nodes':[]},
                        'outputs':[{'ledger_index':1,'identity':7,'path':output}]},
                    'evidence':[{'ledgerIndex':1,'verb':'geo_check_interfaces','ok':True,'status':'pass',
                        'output':output,'contract_sha256':'a'*64,'results':[{'id':'lid_count','status':'pass',
                            'method':'component_count','target_group':'lid','expected_components':1,'observed_components':1}]}]}
            else:
                raise AssertionError('Unexpected endpoint '+self.path)
            raw=json.dumps(result).encode()
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        except Exception as error:
            errors.append(repr(error));self.send_error(500)

fake=ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=fake.serve_forever,daemon=True).start()
env=isolated_environment(fixture/'env')
env.update(DSH_HOME=str(fixture/'home'),DSH_HOUDINI_EXECUTOR_ID=executor,
    DSH_HOUDINI_BRIDGE_URL=f'http://127.0.0.1:{fake.server_port}',DSH_PRODUCT_FIXTURE_OUT=str(fixture/'passed.json'))
if product_mode:env['DSH_PRODUCT_FIXTURE_MODE']='1'
try:
    subprocess.run([node,str(ROOT/'tools/tests/prepare-shared-host-fixture.mjs'),cli,env['DSH_HOME'],str(ROOT)],
        cwd=ROOT,env=env,check=True,timeout=60,capture_output=True)
    for name in ('houdini','houdini-dev','houdini-product'):
        file=fixture/'home/.agent-presets'/name/'agent.cordis.yml'
        file.write_text(file.read_text(encoding='utf-8').replace('bridgeUrl: http://127.0.0.1:8765',
            'bridgeUrl: '+env['DSH_HOUDINI_BRIDGE_URL']),encoding='utf-8')
    overlay=fixture/'fixture.yml'
    overlay.write_text('- insert:\n    - id: product-fixture\n      name: '+(ROOT/'tools/tests/product-loop-fixture.mjs').as_uri()+'\n',encoding='utf-8')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    log=fixture/'host.log'
    with log.open('wb') as output:
        process=spawn_frontend([node,cli,'web','--patch',str(overlay),'--port',str(port),'--no-open'],node=node,
            cwd=fixture,env=env,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    auth=DshWebSession(f'http://127.0.0.1:{port}',str(log),str(fixture/'runtime.json'))
    def rpc(method,args):
        body={'type':'client-request','rpcId':str(uuid.uuid4()),'method':method,'payload':{'args':args}}
        request=urllib.request.Request(f'http://127.0.0.1:{port}/api/'+method,data=json.dumps(body).encode(),
            headers={'Content-Type':'application/json'},method='POST')
        with auth.open(request,timeout=10) as response: result=json.load(response)
        assert result['result']['ok'],result
        return result['result']['value']
    for _ in range(120):
        if process.poll() is not None: raise RuntimeError('Fixture Host failed; inspect '+str(log))
        try:
            auth.authorize(1);rpc('session/list',{'_request':{}});break
        except Exception:time.sleep(.25)
    else:raise RuntimeError('Fixture Host did not become ready; inspect '+str(fixture))
    task=str(uuid.uuid4())
    rpc('session/create',{'request':{'sessionId':task,'cwd':str(fixture),'agentPreset':'houdini-product' if product_mode else 'houdini'}})
    rpc('session/selectModel',{'request':{'sessionId':task,'provider':'product-fixture','model':'fixture'}})
    rpc('session/prompt',{'request':{'sessionId':task,'requestId':str(uuid.uuid4()),'mode':'queue',
        'content':[{'type':'text','text':'Define an editable lid with one part and a visible detailed rim; verify the declared count.'}]}})
    for _ in range(240):
        if errors:raise AssertionError(errors)
        if process.poll() is not None:raise RuntimeError('Fixture Host exited; inspect '+str(log))
        if (fixture/'passed.json').exists():break
        time.sleep(.25)
    else:raise RuntimeError('Product loop did not complete; inspect '+str(fixture))
    result=json.loads((fixture/'passed.json').read_text(encoding='utf-8'))
    assert result['status']=='passed' and result['revision']==2 and result['unresolved']==1,result
    assert result['results']==9 and result['requests']==10,result
    assert result['durable_flush'] and result['serialized_session_reload'],result
    assert result['product_mode'] is product_mode,result
    assert executions==['__result__ = "product_fixture_measurement"'],executions
    print('PASS real DSH optional product loop'+(' with product focus' if product_mode else '')
          +': no requirement reminder before definition; source index; two canonical revisions; '
          'pending detail; measured final-output binding; durable flush and serialized Session reload; zero external model requests')
    print('Fixture:',fixture)
finally:
    stop_owned();fake.shutdown();fake.server_close()
