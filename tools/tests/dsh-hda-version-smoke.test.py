"""Pinned DSH native/PTC to a real isolated Houdini Bridge and package reopen."""
from pathlib import Path
import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment, launch_directory
from dsh_managed_runtime import spawn_frontend, stop_owned

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-cache', required=True, type=Path)
parser.add_argument('--hython', required=True, type=Path)
args = parser.parse_args()
cli = args.runtime_cache.resolve() / 'node_modules/@deepseek-ai/dsh/lib/bin.js'
assert json.loads((cli.parent.parent/'package.json').read_text())['version'] == json.loads((ROOT/'dsh-runtime-compatibility.json').read_text())['preferredVersion']
run = Path(tempfile.mkdtemp(prefix='dsh-hda-version-smoke-'))
env = isolated_environment(run, executable=args.hython)
node = shutil.which('node')
subprocess.run([node, str(ROOT/'tools/tests/prepare-shared-host-fixture.mjs'), str(cli), env['DSH_HOME'], str(ROOT)], cwd=ROOT, env=env, check=True, capture_output=True, timeout=60)
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
library = run / 'package/otls/asset.hda'
library.parent.mkdir(parents=True)
(run/'packages/Fixture.json').write_text(json.dumps({'path': str(run/'package')}), encoding='utf8')
worker = run/'bridge.py'
worker.write_text(f"""
import sys,time,json
from pathlib import Path
sys.path.insert(0,{str(ROOT/'houdini/python3.11libs')!r})
import hou,dsh_bridge as b
n=hou.node('/obj').createNode('subnet','asset')
geo=n.createNode('geo','contents')
geo.createNode('box','shape')
n=n.createDigitalAsset('fixture::asset',{str(library)!r})
n.type().definition().addSection('PythonModule','VALUE = 1\\n')
n.matchCurrentDefinition()
hou.node('/obj').createNode('fixture::asset','peer',exact_type_name=True)
b.start({port});b._pump_active=True
Path({str(run/'ready.json')!r}).write_text(json.dumps({{'executorId':b._EXECUTOR_ID,'runtimeId':b._RUNTIME_ID}}))
while not Path({str(run/'stop')!r}).exists():
 b._pump();time.sleep(.02)
b.stop()
""", encoding='utf8')
with (run/'bridge.log').open('wb') as blog, (run/'host.log').open('wb') as hlog:
    bridge = subprocess.Popen([str(args.hython), str(worker)], cwd=launch_directory(args.hython), env=env, stdout=blog, stderr=subprocess.STDOUT, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    host = None
    try:
        deadline = time.monotonic()+40
        while not (run/'ready.json').exists():
            assert bridge.poll() is None and time.monotonic()<deadline, str(run)
            time.sleep(.1)
        identity = json.loads((run/'ready.json').read_text())
        env.update(DSH_HOUDINI_EXECUTOR_ID=identity['executorId'], DSH_HOUDINI_BRIDGE_URL=f'http://127.0.0.1:{port}', DSH_HDA_TEST_OUT=str(run/'result.json'))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); hostport=sock.getsockname()[1]
        patch=run/'fixture.patch.yml'
        patch.write_text(json.dumps([{'insert':[{'id':'hda-version-fixture','name':(ROOT/'tools/tests/dsh-hda-version-fixture.mjs').as_uri()}]}]),encoding='utf8')
        host=spawn_frontend([node,str(cli),'web','--patch',str(patch),'--port',str(hostport),'--no-open'],node=node,cwd=run,env=env,stdout=hlog,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+120
        while not (run/'result.json').exists():
            assert host.poll() is None and time.monotonic()<deadline, str(run)
            time.sleep(.2)
        result=json.loads((run/'result.json').read_text(encoding='utf8'))
        assert result['ok'], (str(run),result)
    finally:
        if host is not None: stop_owned(host)
        (run/'stop').touch()
        try: bridge.wait(timeout=10)
        except subprocess.TimeoutExpired: bridge.terminate();bridge.wait(timeout=10)

# A fresh process must discover both types through the existing package JSON.
reopen = run/'reopen.py'
reopen.write_text(f"""
import hou,os
for name,value in [('fixture::asset',1),('fixture::asset::1.1',2)]:
 n=hou.node('/obj').createNode(name,exact_type_name=True)
 assert n.hdaModule().VALUE==value
 assert os.path.samefile(n.type().definition().libraryFilePath(),{str(library)!r})
print('PASS package startup: both exact type versions and public module values')
""",encoding='utf8')
completed=subprocess.run([str(args.hython),str(reopen)],env=env,cwd=launch_directory(args.hython),capture_output=True,text=True,encoding='utf8',errors='replace',timeout=60)
assert completed.returncode==0,(completed.stdout,completed.stderr)
print(json.dumps({'ok':True,'evidence':str(run),'reopen':completed.stdout.strip(),'boundary':result['boundary']},ensure_ascii=False))
