"""Real official Host/tool execution -> writer receipt -> session-less menu.

The Bridge and one local busy LLM gate are controlled. No paid model/Houdini
process/user file is used. The browser consumes the real native Ungrouped intent.
"""
import argparse,json,os,shutil,socket,subprocess,sys,tempfile,time,urllib.request,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment,reexec_unpacked_test_cli
reexec_unpacked_test_cli()
from dsh_web_auth import DshWebSession
from dsh_managed_runtime import spawn_frontend,stop_owned
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--runtime-cache',type=Path,required=True);parser.add_argument('--browser',action='store_true');args=parser.parse_args()
binary=args.runtime_cache.resolve(strict=True)/'node_modules/@deepseek-ai/dsh/lib/bin.js';node=shutil.which('node');assert node
root=Path(tempfile.mkdtemp(prefix='dsh-menu-session-'));print('Owned menu session evidence:',root,flush=True)
env=isolated_environment(root,gui=True)
subprocess.run([node,str(ROOT/'tools/tests/prepare-shared-host-fixture.mjs'),str(binary),env['DSH_HOME'],str(ROOT)],cwd=ROOT,env=env,check=True,capture_output=True,timeout=90)
installed=json.loads((root/'shared-host-test.json').read_text(encoding='utf-8'))['plugin']
env.update(DSH_MENU_FIXTURE_ROOT=str(root),DSH_MENU_PLUGIN_ROOT=installed)
overlay=root/'fixture.yml';overlay.write_text('- insert:\n    - id: menu-session-fixture\n      name: '+(ROOT/'tools/tests/menu-session-fixture.mjs').as_uri()+'\n',encoding='utf-8')
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
log=root/'host.log'
with log.open('wb') as stream:
 process=spawn_frontend([node,str(binary),'web','--patch',str(overlay),'--port',str(port),'--no-open'],node=node,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
try:
 deadline=time.monotonic()+90
 while True:
  assert process.poll() is None,'Owned Host exited; inspect '+str(log)
  if (root/'result.json').exists():
   result=json.loads((root/'result.json').read_text(encoding='utf-8'));assert result['ok'],result;break
  assert time.monotonic()<deadline,'Menu session fixture timeout';time.sleep(.1)
 if args.browser:
  auth=DshWebSession('http://127.0.0.1:'+str(port),str(log),str(root/'auth.json'));auth.authorize(timeout=5)
  config={'base':auth.base_url+'/', 'output':str(root),'expectedSessionId':result['ungroupedSessionId'],
   'browser':'C:/Program Files/Google/Chrome/Application/chrome.exe','cookies':[{'name':cookie.name,'value':cookie.value,'url':auth.base_url+'/','httpOnly':True} for cookie in auth._cookies]}
  config_file=root/'browser-config.json';config_file.write_text(json.dumps(config),encoding='utf-8')
  subprocess.run([node,str(ROOT/'tools/tests/desktop-menu-browser.mjs'),str(config_file)],cwd=ROOT,env=env,check=True,timeout=90)
  deadline=time.monotonic()+10
  while not json.loads((root/'result.json').read_text(encoding='utf-8')).get('browserConfirmed'):
   assert time.monotonic()<deadline;time.sleep(.1)
 print('PASS official Host real writer tool -> exact menu Session, busy/changed/archive/other-mode guards and Ungrouped:',root,flush=True)
finally:
 stop_owned(process);process.wait(timeout=15)
