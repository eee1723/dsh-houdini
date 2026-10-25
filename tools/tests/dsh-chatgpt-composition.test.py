"""Real prepared DSH Host + source plugin + authenticated ChatGPT UI RPC.

Uses a fresh DSH home. Credentials are explicitly synthetic fixture inputs;
no browser authorization, model call, user account, Houdini or HIP is touched.
Provider protocol/JWT/revocation tests remain in the prepared native runtime.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment,reexec_unpacked_test_cli
from dsh_web_auth import DshWebSession
import dsh_managed_runtime as managed
from dsh_runtime_compat import runtime_fix_identity
from dsh_deployment import atomic_json,read_json

def write(filename,value):
    atomic_json(Path(filename),value)

def main():
    reexec_unpacked_test_cli()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-cache',type=Path,required=True)
    args=parser.parse_args()
    binary=args.runtime_cache.resolve(strict=True)/'node_modules/@deepseek-ai/dsh/lib/bin.js'
    runtime=runtime_fix_identity(binary,verify_files=True)
    node=shutil.which('node')
    assert node,'Node is required'
    folder=Path(tempfile.mkdtemp(prefix='dsh-chatgpt-composition-'))
    print('Real DSH ChatGPT composition evidence: '+str(folder),flush=True)
    env=isolated_environment(folder/'environment')
    home=Path(env['DSH_HOME'])
    subprocess.run([node,str(ROOT/'tools/tests/prepare-shared-host-fixture.mjs'),str(binary),str(home),str(ROOT)],
                   cwd=ROOT,env=env,check=True,capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    # A reserved, non-listening endpoint ensures this fixture cannot reach a live Houdini.
    bridge=socket.socket();bridge.bind(('127.0.0.1',0))
    env['DSH_HOUDINI_BRIDGE_URL']='http://127.0.0.1:'+str(bridge.getsockname()[1])
    env['DSH_HOUDINI_EXECUTOR_ID']=uuid.uuid4().hex
    with socket.socket() as port_probe:
        port_probe.bind(('127.0.0.1',0));port=port_probe.getsockname()[1]
    base='http://127.0.0.1:'+str(port)
    config={'home':str(home),'binary':str(binary),'ready':str(folder/'ready.json'),
            'command':str(folder/'command.json'),'response':str(folder/'response.json')}
    config_path=folder/'fixture.json';write(config_path,config)
    env['DSH_CHATGPT_COMPOSITION_CONFIG']=str(config_path)
    overlay=folder/'inspect.patch.yml'
    overlay.write_text('- insert:\n    - id: chatgpt-composition-inspector\n      name: '+(ROOT/'tools/tests/dsh-chatgpt-composition-fixture.mjs').as_uri()+'\n',encoding='utf-8')
    host=None;checks=[];report={'ok':False,'syntheticAccount':True,'noCloudRequests':True,'checks':checks,'runtime':runtime}
    def wait_file(filename,predicate=lambda value:True,timeout=35):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            assert host.poll() is None,'Owned Host exited before completing the fixture'
            try:
                value=read_json(Path(filename))
                if predicate(value):return value
            except FileNotFoundError:pass
            time.sleep(.05)
        raise AssertionError('Fixture response timed out: '+Path(filename).name)
    def command(action):
        ident=uuid.uuid4().hex;write(config['command'],{'id':ident,'action':action})
        value=wait_file(config['response']+'.'+ident,lambda value:value.get('id')==ident)
        assert value['ok'],value
        return value
    log=folder/'host.log'
    try:
        with log.open('wb') as stdout:
            host=managed.spawn_frontend([node,str(binary),'web','--patch',str(overlay),'--port',str(port),'--no-open'],
                node=node,cwd=folder,env=env,stdout=stdout,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            ready=wait_file(config['ready']);assert ready['ok'],ready
            assert ready['nativeService'] and sorted(ready['nativeMethods'])==['catalog','describe','disconnect','ensureInstallationId'],ready
            assert 'oauth' in ready['flow'],ready
            auth=DshWebSession(base,str(log),str(folder/'runtime.json'))
            deadline=time.monotonic()+15
            while auth.launch_url() is None:
                assert host.poll() is None and time.monotonic()<deadline,'Authenticated Host URL unavailable'
                time.sleep(.1)
            auth.authorize(timeout=10)
            def rpc(name,input=None,expect_error=False):
                method=name if '/' in name else 'houdiniFrontend/'+name
                body={'type':'client-request','rpcId':uuid.uuid4().hex,'method':method,'payload':{'args':{} if input is None else {'input':input}}}
                request=urllib.request.Request(base+'/api/'+method,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
                with auth.open(request,timeout=20) as response:result=json.load(response)['result']
                if expect_error:
                    assert result.get('ok') is False,'Expected a safe RPC refusal'
                    return result
                assert result.get('ok') is True,'Authenticated RPC failed: '+name
                return result['value']
            before=command('snapshot')
            blank=rpc('chatgptStatus');again=rpc('chatgptStatus')
            after=command('snapshot')
            assert blank['nativeFlowAvailable'] and blank['credential']['stored'] is False and blank['credential']['kind'] is None,blank
            assert not blank['route']['configured'] and not blank['route']['conflicts'],blank['route']
            assert blank['models']==[],'No subscription catalog is shown before sign-in'
            assert before['credentialDigest']==after['credentialDigest'] and before['patchDigest']==after['patchDigest']
            assert after['counts']['describe']>=before['counts']['describe']+2,'RPC must consume the already-loaded native account service'
            assert after['counts']['ensureInstallationId']==0 and after['counts']['disconnect']==0
            assert not after['blockedExternal']
            checks.extend(['actual-root-service-and-oauth-flow','authenticated-production-status-rpc','no-subscription-catalog-before-sign-in','signed-out-status-read-only-and-no-network','same-host-native-account-method'])
            seeded=command('seed-grant')
            signed=rpc('chatgptStatus')
            assert signed['credential']['stored'] and signed['credential']['kind']=='grant'
            assert 'account' not in signed,'Unverified synthetic legacy grant cannot invent a verified identity'
            assert not signed['route']['configured'],'Grant presence must not configure a model route'
            assert [row['id'] for row in signed['models']]==['gpt-6.1-sol','gpt-6-luna','future-fixture-model'],'Account visibility and order must own choices'
            assert signed['models'][0]['name']=='Account main model' and signed['models'][0]['description']=='Synthetic account description'
            assert signed['models'][-1]['supported'] is False,'New unknown models remain honest about missing metadata'
            model=next(row['id'] for row in signed['models'] if row['id'].startswith('gpt-'))
            selected=rpc('chatgptSelect',{'model':model})
            selection_state=command('snapshot')
            assert selected['route']['configured'] and selected['route']['registered']
            assert selected['defaultSelection']['provider']=='openai' and selected['defaultSelection']['model']==model
            assert selection_state['userProfile']=={'displayName':'ChatGPT'},selection_state['userProfile']
            assert [row['id'] for row in selected['models']]==[row['id'] for row in signed['models']],'Settings must preserve the account model catalog'
            assert selection_state['counts']['ensureInstallationId']==0,'Selecting a model must not start or migrate a login'
            assert not selection_state['blockedExternal']
            reasoning=next(row for row in selected['models'] if row.get('reasoning',{}).get('efforts'))
            effort=reasoning['reasoning']['efforts'][0]['id']
            picked=rpc('chatgptSelect',{'model':reasoning['id'],'reasoningEffort':effort})
            assert picked['defaultSelection']=={'provider':'openai','model':reasoning['id'],'reasoningEffort':effort}
            selection_state=command('snapshot')
            checks.extend(['synthetic-grant-has-no-unverified-identity','native-settings-mutate-preserves-catalog','native-default-model-selection-without-request'])
            picker=command('picker')
            assert [row['id'] for row in picker['models']]==['gpt-6.1-sol','gpt-6-luna'],'Conversation picker must use the same supported account choices'
            native_picker=rpc('session/modelCatalog')
            native_group=next(group for group in native_picker['groups'] if group['id']=='openai')
            assert [row['id'] for row in native_group['models']]==['gpt-6.1-sol','gpt-6-luna'],'Actual conversation catalog RPC must consume account choices'
            assert native_group['models'][0]['name']=='Account main model' and native_group['models'][0]['description']=='Synthetic account description'
            assert len(picker['catalogRequests'])==1,'Repeated status, selection and picker share one native catalog cache'
            command('catalog-failure')
            failed=rpc('chatgptStatus',{'refreshModels':True})
            assert failed['models']==[] and failed.get('catalogError'),'A failed refresh must not show the bundled historical catalog'
            assert 'synthetic-private-provider-body' not in json.dumps(failed),'Raw provider bodies cannot cross status RPC'
            command('catalog-recover')
            restored=rpc('chatgptStatus',{'refreshModels':True})
            assert [row['id'] for row in restored['models']]==[row['id'] for row in signed['models']]
            checks.extend(['same-account-catalog-in-native-picker','actual-native-conversation-catalog-rpc','account-catalog-cache-reuse','failed-catalog-no-historical-fallback','explicit-catalog-refresh-recovery'])
            disconnected=rpc('chatgptSignout')
            cleared=command('snapshot')
            assert disconnected['credential']['stored'] is False and disconnected['signout']['localCleared'] is True
            assert disconnected['signout']['revocation']=='unconfirmed','Synthetic legacy grant has no issued client registration to revoke'
            assert cleared['other']['configured'] is True and cleared['other']['kind']=='api-key'
            assert cleared['profile']==selection_state['profile'] and cleared['defaultSelection']==selection_state['defaultSelection']
            assert cleared['counts']['disconnect']==selection_state['counts']['disconnect']+1
            assert not cleared['blockedExternal']
            command('seed-api-key')
            refusal=rpc('chatgptSignout',expect_error=True)
            api=command('snapshot')
            assert api['credential']['configured'] is True and api['credential']['kind']=='api-key'
            assert api['counts']['disconnect']==cleared['counts']['disconnect'],'API-key refusal must precede native disconnect'
            assert not api['blockedExternal']
            checks.extend(['native-disconnect-exact-account','unconfirmed-revocation-honest','unrelated-record-and-model-settings-preserved','api-key-record-not-deleted'])
            report.update(ok=True,model=model,initialModelCount=len(blank['models']),accountModelCount=len(signed['models']),finalCounts=api['counts'],blockedExternal=api['blockedExternal'],
                          limitation='Synthetic grant and real native settings/RPC only; no real OAuth consent, model request, subscription entitlement or provider revocation is verified here.')
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        if host is not None:
            report['hostCleanup']=managed.stop_owned(expected_process=host)
            report['hostExited']=host.poll() is not None
        bridge.close()
        write(folder/'report.json',report)
        print(json.dumps({'ok':report['ok'],'checks':checks,'report':str(folder/'report.json'),'hostExited':report.get('hostExited')},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
