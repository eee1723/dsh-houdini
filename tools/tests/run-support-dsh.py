from pathlib import Path
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment,launch_directory,reexec_unpacked_test_cli
from dsh_managed_runtime import spawn_frontend,stop_owned


def main():
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser()
    parser.add_argument('--hython',type=Path,required=True)
    parser.add_argument('--runtime-cache',type=Path,required=True)
    parser.add_argument('--platform',choices=('windows','offscreen'),default='windows')
    args = parser.parse_args()
    folder = Path(tempfile.mkdtemp(prefix='support-dsh-',dir=ROOT/'tools/out'))
    (folder/'project').mkdir()
    env = isolated_environment(folder/'env',executable=args.hython,gui=True)
    env.update(DSH_SUPPORT_TEST_ROOT=str(folder),QT_QPA_PLATFORM=args.platform,HFS=str(args.hython.parent.parent))
    env.update(DSH_HOUDINI_BRIDGE_URL='http://127.0.0.1:1',DSH_HOUDINI_EXECUTOR_ID='b'*32)
    cli = args.runtime_cache.resolve()/'node_modules/@deepseek-ai/dsh/lib/bin.js'
    node = shutil.which('node')
    subprocess.run([node,str(ROOT/'tools/tests/prepare-shared-host-fixture.mjs'),str(cli),env['DSH_HOME'],str(ROOT)],
                   cwd=ROOT,env=env,check=True,timeout=60)
    overlay=folder/'fixture.json'
    overlay.write_text(json.dumps([{'insert':[{'id':'support-fixture','name':(ROOT/'tools/tests/support-report-dsh-fixture.mjs').as_uri()}]}]))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    (folder/'browser.json').write_text(json.dumps({'base':'http://127.0.0.1:'+str(port)}))
    runtime=folder/'runtime/123-abcdef01'
    runtime.mkdir(parents=True)
    (runtime/'frontend.log').write_text('fixture diagnostic line\n'*3000+'fixture diagnostic token=FIXTURE_RUNTIME_SECRET\n',encoding='utf-8')
    (runtime/'runtime.json').write_text(json.dumps({'version':'0.2.1-rc.2','source':'isolated-fixture'}))
    context=folder/'context.json'
    context.write_text(json.dumps({'schemaVersion':1,'root':str(folder),'runtimeDir':str(runtime),
                                   'install':str(folder/'unused-install'),'frontendPort':port,'bridgePort':1,'installId':'isolated-fixture'}))
    env['DSH_HOUDINI_MANAGED_CONTEXT']=str(context)
    with (folder/'host.log').open('wb') as log:
        host=spawn_frontend([node,str(cli),'web','--patch',str(overlay),'--port',str(port),'--no-open'],node=node,
                            cwd=folder,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+90
            while not (folder/'ready.json').exists() and host.poll() is None and time.monotonic()<deadline:
                time.sleep(.1)
            assert (folder/'ready.json').exists(),'Host fixture not ready: '+str(folder)
            result=json.loads((folder/'ready.json').read_text())
            assert result['ok'],result
            with (folder/'browser.log').open('wb') as output:
                browser=subprocess.run([str(args.hython),str(ROOT/'tools/tests/dsh-support-browser.test.py')],
                    cwd=launch_directory(args.hython),env=env,stdout=output,stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=120)
            print((folder/'browser.log').read_text(encoding='utf-8',errors='replace')[-5000:],flush=True)
            assert browser.returncode==0,'Browser fixture failed: '+str(folder)
            print('Actual DSH persistence, authenticated RPC, selected session, Qt support ZIP and native export passed: '+str(folder),flush=True)
        finally:
            stop_owned(host)


if __name__=='__main__':
    main()
