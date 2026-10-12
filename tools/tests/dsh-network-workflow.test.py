import sys,pathlib,subprocess,json,socket,time,os,uuid,argparse,shutil
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment,reexec_unpacked_test_cli
from dsh_managed_runtime import spawn_frontend,stop_owned
from dsh_web_auth import DshWebSession
reexec_unpacked_test_cli()
parser=argparse.ArgumentParser();parser.add_argument('--runtime-cache',required=True,type=pathlib.Path);parser.add_argument('--proxy');parser.add_argument('--browser-module',type=pathlib.Path);args=parser.parse_args()
run=pathlib.Path('E:/tmp')/('dsh-network-chain-'+uuid.uuid4().hex[:8]);run.mkdir()
workspace=run/'workspace';workspace.mkdir();(run/'outside').mkdir()
(workspace/'references').mkdir();(workspace/'references'/'existing.txt').write_text('existing before sandbox initialization',encoding='utf8')
cache=args.runtime_cache.resolve();cli=cache/'node_modules/@deepseek-ai/dsh/lib/bin.js'
env=isolated_environment(run);env['DSH_HOME']=str(run/'home')
node=shutil.which('node');assert node
subprocess.run([node,str(ROOT/'tools/tests/prepare-shared-host-fixture.mjs'),str(cli),env['DSH_HOME'],str(ROOT)],env=env,cwd=ROOT,check=True,capture_output=True)
# Exact observed proxy; isolated home, no credentials or user settings copied.
for key in list(env):
 if key.lower() in ('http_proxy','https_proxy','all_proxy','no_proxy','node_use_env_proxy'):env.pop(key)
if args.proxy:(pathlib.Path(env['DSH_HOME'])/'.env').write_text('HTTP_PROXY='+json.dumps(args.proxy)+'\nHTTPS_PROXY='+json.dumps(args.proxy)+'\n',encoding='utf8')
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
env.update(DSH_FIX_CLI=str(cli),DSH_FIX_WORKSPACE=str(workspace),DSH_FIX_REPORT=str(run/'report.json'),DSH_HOUDINI_BRIDGE_URL='http://127.0.0.1:1')
patch=run/'test.patch.yml';patch.write_text(json.dumps([{'insert':[{'id':'network-fix-verification','name':(ROOT/'tools/tests/dsh-network-workflow-fixture.mjs').as_uri()}]}]),encoding='utf8')
(ROOT/'tools/out/network-repair/latest-run.json').write_text(json.dumps({'directory':str(run),'port':port,'runtime':str(cache)}),encoding='utf8')
with (run/'host.log').open('wb') as log:
 p=spawn_frontend([node,str(cli),'web','--patch',str(patch),'--port',str(port),'--no-open'],node=node,cwd=workspace,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
 try:
  deadline=time.monotonic()+180
  while not (run/'report.json').exists():
   if p.poll() is not None:raise RuntimeError('Host exited; '+str(run/'host.log'))
   if time.monotonic()>deadline:raise TimeoutError(str(run/'host.log'))
   time.sleep(.2)
  result=json.loads((run/'report.json').read_text(encoding='utf8'));print(json.dumps({k:v for k,v in result.items() if k not in ('events','ptcFirst')},ensure_ascii=True),flush=True)
  print('Evidence:',run,flush=True)
  if result.get('ok') and args.browser_module:
   auth=DshWebSession(f'http://127.0.0.1:{port}',str(run/'host.log'),str(run/'runtime.json'));auth.authorize(timeout=5)
   browser_config=run/'browser-config.json'
   browser_config.write_text(json.dumps({'base':f'http://127.0.0.1:{port}/','workspace':str(workspace),'sessionId':result['sessionId'],
    'output':str(run),'playwright':str(args.browser_module.resolve()),
    'cookies':[{'name':c.name,'value':c.value,'url':f'http://127.0.0.1:{port}/','httpOnly':True} for c in auth._cookies]}),encoding='utf8')
   try:subprocess.run([node,str(ROOT/'tools/tests/dsh-network-workflow-browser.mjs'),str(browser_config)],cwd=ROOT,check=True,timeout=65)
   finally:browser_config.unlink(missing_ok=True)
 finally:
  stop_owned(p);p.wait(timeout=20)
sys.exit(0 if result.get('ok') else 1)
