"""Pinned DSH native/nested local media and evidence calls; no paid provider or HOM."""
from pathlib import Path
import argparse,json,os,socket,subprocess,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment,reexec_unpacked_test_cli
from dsh_managed_runtime import spawn_frontend,stop_owned
reexec_unpacked_test_cli()
parser=argparse.ArgumentParser();parser.add_argument('--runtime-cache',required=True,type=Path);args=parser.parse_args()
cache=args.runtime_cache.resolve(strict=True);cli=cache/'node_modules/@deepseek-ai/dsh/lib/bin.js'
assert json.loads((cli.parent.parent/'package.json').read_text())['version']==json.loads((ROOT/'dsh-runtime-compatibility.json').read_text())['preferredVersion']
run=Path(tempfile.mkdtemp(prefix='dsh-local-video-smoke-'));workspace=run/'workspace';workspace.mkdir()
env=isolated_environment(run);env['PYTHONUTF8']='1';env.pop('HFS',None)
node=Path('C:/Program Files/nodejs/node.exe');ffmpeg=ROOT/'runtime/video/ffmpeg/bin/ffmpeg.exe'
def command(values):return subprocess.run([str(x) for x in values],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',check=True,timeout=90)
command([ffmpeg,'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=size=96x64:rate=10:duration=2','-c:v','mpeg4',workspace/'source.mp4'])
command([node,ROOT/'tools/tests/prepare-shared-host-fixture.mjs',cli,env['DSH_HOME'],ROOT])
with socket.socket() as s:s.bind(('127.0.0.1',0));bridgeport=s.getsockname()[1]
with socket.socket() as s:s.bind(('127.0.0.1',0));hostport=s.getsockname()[1]
output=run/'result.json'
env.update(DSH_LOCAL_VIDEO_WORKSPACE=str(workspace),DSH_LOCAL_VIDEO_RESULT=str(output),DSH_LOCAL_VIDEO_PYTHON=sys.executable,
 DSH_LOCAL_VIDEO_PYTHON_VERSION='.'.join(map(str,sys.version_info[:3])),DSH_LOCAL_VIDEO_HFS=str(Path(sys.executable).parent.parent),
 DSH_HOUDINI_EXECUTOR_ID='a'*32,DSH_HOUDINI_BRIDGE_URL=f'http://127.0.0.1:{bridgeport}')
patch=run/'fixture.patch.yml';patch.write_text(json.dumps([{'insert':[{'id':'local-video-fixture','name':(ROOT/'tools/tests/dsh-video-process-fixture.mjs').as_uri()}]}]),encoding='utf-8')
with (run/'host.log').open('wb') as log:
 host=spawn_frontend([str(node),str(cli),'web','--patch',str(patch),'--port',str(hostport),'--no-open'],node=str(node),cwd=workspace,env=env,stdout=log,stderr=subprocess.STDOUT)
 try:
  deadline=time.monotonic()+120
  while not output.exists():
   assert host.poll() is None,'Host exited: '+str(run)
   assert time.monotonic()<deadline,'Fixture timed out: '+str(run)
   time.sleep(.2)
  result=json.loads(output.read_text());assert result['ok'],result
 finally:stop_owned(host)
print(json.dumps({'ok':True,'evidence':str(run),'checks':result['checks'],'boundary':result['boundary']},ensure_ascii=False,indent=2))
