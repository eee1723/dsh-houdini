"""Exercise the qualified native DSH profile twice, without touching user sessions."""
from pathlib import Path
import argparse,json,os,shutil,socket,subprocess,tempfile,time,uuid
ROOT=Path(__file__).resolve().parents[2]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-cache',required=True,type=Path)
    args=parser.parse_args();folder=Path(tempfile.mkdtemp(prefix='dsh-workspace-continuity-'))
    cli=args.runtime_cache.resolve()/'node_modules/@deepseek-ai/dsh/lib/bin.js'
    env=dict(os.environ,DSH_HOME=str(folder/'home'),DSH_WORKSPACE_TEST_ROOT=str(folder),DSH_WORKSPACE_TEST_TASK=str(uuid.uuid4()))
    subprocess.run([shutil.which('node'),str(ROOT/'tools/tests/prepare-shared-host-fixture.mjs'),str(cli),env['DSH_HOME'],str(ROOT)],env=env,check=True,capture_output=True,timeout=60)
    overlay=folder/'fixture.json';overlay.write_text(json.dumps([{'insert':[{'id':'workspace-fixture','name':(ROOT/'tools/tests/dsh-workspace-continuity-fixture.mjs').as_uri()}]}]),encoding='utf-8')
    for phase in ('relocate','interrupted','restart'):
        env['DSH_WORKSPACE_TEST_PHASE']=phase
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        with (folder/(phase+'-host.log')).open('wb') as log:
            process=subprocess.Popen([shutil.which('node'),str(cli),'web','--patch',str(overlay),'--port',str(port),'--no-open'],cwd=folder,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                result=folder/(phase+'-result.json');deadline=time.monotonic()+80
                while not result.exists():
                    assert process.poll() is None and time.monotonic()<deadline,str(folder)+' '+phase
                    time.sleep(.1)
                value=json.loads(result.read_text(encoding='utf-8'));assert value['ok'],(str(folder),value)
                print('PASS',phase,value,flush=True)
            finally:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                process.wait(timeout=20)
    print('PASS native workspace continuity:',folder)
if __name__=='__main__':main()
