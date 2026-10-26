"""Owned official Host + real H21/H22 GUI launch/menu/Bridge validation.

No model request, user HIP, Desktop process or shared preference is touched.
The menu worker runs unchanged except its external dsh:// activation is stubbed
inside the owned GUI. The test validates the real local authenticated callback.
"""
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
from houdini_test_environment import isolated_environment,reexec_unpacked_test_cli
reexec_unpacked_test_cli()
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
from dsh_web_auth import DshWebSession
import dsh_managed_runtime as runtime

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-cache',required=True,type=Path)
parser.add_argument('--hfs',action='append',type=Path)
parser.add_argument('--action',action='append',choices=['new','open'])
parser.add_argument('--helper-package',action='store_true',help='Install the immutable helper Package separately from the Host package')
parser.add_argument('--timeout',type=int,default=240)
args=parser.parse_args()
cache=args.runtime_cache.resolve(strict=True)
node=shutil.which('node')
assert node
bin_file=cache/'node_modules/@deepseek-ai/dsh/lib/bin.js'
hfss=[item.resolve(strict=True) for item in (args.hfs or [Path('D:/houdini'),Path('D:/Houdini22')])]
fixture=Path(tempfile.mkdtemp(prefix='dsh-desktop-live-'))
print('Owned live evidence:',fixture,flush=True)
report={'officialBackendVersion':json.loads((cache/'node_modules/@deepseek-ai/dsh/package.json').read_text())['version'],
        'nativeElectronTested':False,'externalDesktopActivationStubbed':True,'scenarios':[]}


def wait_until(read,timeout,label):
    deadline=time.monotonic()+timeout
    announced=time.monotonic()
    while True:
        value=read()
        if value is not None:return value
        assert time.monotonic()<deadline,'Timeout '+label
        if time.monotonic()-announced>30:
            print('Waiting:',label,flush=True);announced=time.monotonic()
        time.sleep(.2)


def menu_hook(directory):
    code="""
import json,os
from pathlib import Path
from hutil.Qt import QtCore
import hou
_root=Path(os.environ['DSH_HOUDINI_TEST_MENU_ROOT'])
_trigger=_root/(str(os.getpid())+'.menu-request.json')
_result=_root/(str(os.getpid())+'.menu-result.json')
_timer=QtCore.QTimer(hou.qt.mainWindow())
def _check():
    if not _trigger.exists():return
    _timer.stop();_trigger.unlink()
    import dsh_desktop_client,dsh_launcher
    # Exercise capture, worker, registration and authenticated local request.
    # The independent fixture must never focus the user's real Desktop.
    dsh_desktop_client.activate_desktop=lambda:None
    _request=dsh_desktop_client.request
    def _record(record,action,payload,**kwargs):
        try:
            value=_request(record,action,payload,**kwargs)
            if action=='open-workspace':_result.write_text(json.dumps({'payload':payload,'result':value}),encoding='utf-8')
            return value
        except Exception as error:
            _result.write_text(json.dumps({'error':str(error)}),encoding='utf-8');raise
    dsh_desktop_client.request=_record
    dsh_launcher.open_workspace()
_timer.timeout.connect(_check);_timer.start(100)
"""
    for version in ['3.11','3.13']:
        target=directory/('python'+version+'libs');target.mkdir(parents=True)
        (target/'dsh_live_menu_fixture.py').write_text(code,encoding='utf-8')
        (target/'uiready.py').write_text('import dsh_live_menu_fixture\n',encoding='utf-8')


def setup_hip(hfs,directory):
    executable=hfs/'bin/hython.exe'
    env=isolated_environment(directory/'hython',executable=executable)
    target=directory/'fixture-empty.hip'
    script=directory/'make-hip.py'
    script.write_text('import hou,json\nhou.hipFile.save('+repr(str(target))+')\nprint("DSH_TEST_HIP="+json.dumps({"hip":hou.hipFile.path(),"version":hou.applicationVersionString()}))\n',encoding='utf-8')
    result=subprocess.run([str(executable),str(script)],cwd=executable.parent,env=env,capture_output=True,timeout=120)
    (directory/'hython-setup.log').write_bytes(result.stdout+result.stderr)
    assert result.returncode==0,'Owned hython setup failed; see '+str(directory/'hython-setup.log')
    values=[json.loads(line.split('=',1)[1]) for line in result.stdout.decode('utf-8',errors='replace').splitlines() if line.startswith('DSH_TEST_HIP=')]
    assert values and Path(values[-1]['hip']).is_file(),values
    return values[-1]['hip']


def scenario(hfs,action):
    directory=fixture/(hfs.name+'-'+action);directory.mkdir()
    hook=directory/'menu-hook';menu_hook(hook)
    env=isolated_environment(directory,gui=True)
    for name,relative in {'LOCALAPPDATA':'localappdata','APPDATA':'appdata'}.items():
        target=directory/relative;target.mkdir(parents=True,exist_ok=True);env[name]=str(target)
    # hconfig documents 0 as disabling collection. A fresh preference tree
    # otherwise blocks native uiready on the first-use statistics question.
    env['HOUDINI_ANONYMOUS_STATISTICS']='0'
    env['HOUDINI_NO_START_PAGE_SPLASH']='1'
    env['HOUDINI_PATH']=str(hook)+os.pathsep+'&'
    env['DSH_HOUDINI_TEST_MENU_ROOT']=str(directory)
    subprocess.run([node,str(ROOT/'tools/tests/prepare-shared-host-fixture.mjs'),str(bin_file),env['DSH_HOME'],str(ROOT)],
                   cwd=ROOT,env=env,check=True,timeout=90,capture_output=True)
    installed=directory/'installed/dsh-houdini'
    expected_helper=installed
    if args.helper_package:
        installer=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
            str(installed/'installer/install.ps1'),'-Root',str(directory/'helper-install'),'-PackagesDir',env['HOUDINI_PACKAGE_DIR']],
            cwd=directory,env=env,capture_output=True,timeout=90)
        (directory/'helper-install.log').write_bytes(installer.stdout+installer.stderr)
        assert installer.returncode==0,'Owned immutable helper installation failed; see helper-install.log'
        package=json.loads((Path(env['HOUDINI_PACKAGE_DIR'])/'dsh-houdini.json').read_text(encoding='utf-8-sig'))
        path=next(row['DSH_HOUDINI_PATH'] for row in package['env'] if 'DSH_HOUDINI_PATH' in row)
        expected_helper=Path(path).parent.resolve(strict=True)
        assert expected_helper.is_relative_to(directory/'helper-install/helpers') and not expected_helper.samefile(installed)
    hip=setup_hip(hfs,directory) if action=='open' else None
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    log=directory/'host.log';auth=DshWebSession('http://127.0.0.1:'+str(port),str(log),str(directory/'runtime.json'))
    def rpc(method,arguments,timeout=30):
        body=json.dumps({'type':'client-request','rpcId':uuid.uuid4().hex,'method':method,'payload':{'args':arguments}}).encode()
        request=urllib.request.Request('http://127.0.0.1:'+str(port)+'/api/'+method,data=body,
                    headers={'Content-Type':'application/json'},method='POST')
        with auth.open(request,timeout=timeout) as response:value=json.load(response)['result']
        assert value['ok'],value
        return value['value']
    started=time.monotonic()
    with log.open('wb') as output:
        process=runtime.spawn_frontend([node,str(bin_file),'web','--port',str(port),'--no-open'],node=node,cwd=directory,env=env,
                        stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            def authorize():
                assert process.poll() is None,'Owned Host exited; inspect '+str(log)
                if auth.launch_url() is None:return None
                auth.authorize(timeout=5);return True
            wait_until(authorize,60,'official Host authentication')
            wait_until(lambda:True if rpc('houdiniFrontend/capabilities',{})['desktop'] else None,15,'Desktop plugin service')
            installations=rpc('houdiniFrontend/projectInstallations',{})
            installation=next(item for item in installations if Path(item['hfs']).samefile(hfs))
            workspace=directory/'conversation';workspace.mkdir()
            workspace_id=rpc('workspace/create',{'request':{'path':str(workspace)}})['workspace']['workspaceId']
            session=rpc('session/create',{'request':{'sessionId':uuid.uuid4().hex,'workspaceId':workspace_id,'agentPreset':'houdini'}})
            assert session['agentPreset']=='houdini',session
            submit={'action':action,'sessionId':session['sessionId'],'hfs':installation['hfs']}
            if hip:submit['hip']=hip
            ticket=rpc('houdiniFrontend/projectAction',{'input':submit})
            assert ticket['phase']=='waiting' and ticket['id'],ticket
            def status():
                assert process.poll() is None,'Owned Host exited'
                value=rpc('houdiniFrontend/projectLaunchStatus',{'input':{'id':ticket['id']}})
                if value['phase']=='waiting':return None
                assert value['phase']=='ready',value
                return value
            ready=wait_until(status,args.timeout,str(hfs)+' '+action+' actual GUI callback')
            listing=rpc('houdiniTargets/list',{'input':{'sessionId':session['sessionId']}})
            assert listing['state']['status']=='selected',listing
            target=listing['selectedTarget'];assert target['executor_id']==ready['result']['executorId'],(target,ready)
            record=next(item for item in listing['candidates'] if item['executor_id']==target['executor_id'])
            assert runtime.owns_pid(record['pid']),'GUI must belong to the fixture Host Job'
            assert Path(record['runtime']['hfs']).samefile(hfs),(record,installation)
            presence=rpc('houdiniFrontend/projectPresence',{})
            observed=next(item for item in presence if item['executorId']==target['executor_id'])
            assert observed['status']=='online' and observed['contractMismatch'] is False,observed
            assert observed['candidate']['executor_id']==record['executor_id'],observed
            assert observed['ownerSessionId'] is None,'explicit target selection must not claim scene authorship'
            assert isinstance(observed['observedAt'],(int,float)),observed
            assert isinstance(observed['activeRequests'],int) and isinstance(observed['activeJobs'],int),observed
            assert observed['busy']==bool(observed['activeRequests'] or observed['activeJobs']),observed
            source=directory/'bridge-check.mjs'
            source.write_text('import fs from "node:fs";import {HoudiniBridge} from '+json.dumps((installed/'lib/bridge.js').as_uri())+''';
const config=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const bridge=new HoudiniBridge(config.record.bridge_url,45000,config.target.executor_id,undefined,{runtimeId:config.target.runtime_id,sceneEpoch:config.target.scene_epoch});
const code="import os,threading,dsh_bridge\\n__result__={'version':hou.applicationVersionString(),'hip':hou.hipFile.path(),'new':hou.hipFile.isNewFile(),'ui':hou.isUIAvailable(),'hfs':hou.getenv('HFS'),'pid':os.getpid(),'main_thread':threading.get_ident()==dsh_bridge._HOU_THREAD_ID,'bridge_file':dsh_bridge.__file__}";
const result=await bridge.exec(code,{sessionId:config.sessionId,callId:'desktop-live-read'},AbortSignal.timeout(45000),undefined,true);
fs.writeFileSync(process.argv[3],JSON.stringify(result,null,2));if(result.ok!==true)process.exitCode=1;
''',encoding='utf-8')
            read_config=directory/'bridge-input.json';read_config.write_text(json.dumps({'record':record,'target':target,'sessionId':session['sessionId']}),encoding='utf-8')
            subprocess.run([node,str(source),str(read_config),str(directory/'hom-read.json')],cwd=directory,env=env,check=True,timeout=60,capture_output=True)
            receipt=json.loads((directory/'hom-read.json').read_text(encoding='utf-8'));facts=receipt['result']
            assert facts['main_thread'] and facts['ui'] and facts['pid']==record['pid'],facts
            assert Path(facts['hfs']).samefile(hfs) and facts['version']==installation['version'],facts
            assert Path(facts['bridge_file']).resolve().is_relative_to(expected_helper),facts
            if hip:assert Path(facts['hip']).samefile(hip) and not facts['new'],facts
            else:assert facts['new'],facts
            launch_intent=rpc('houdiniFrontend/desktopIntent',{'input':{'after':0}})
            assert launch_intent['selection']['source']=='launch' and launch_intent['selection']['sessionId']==session['sessionId'],launch_intent
            rpc('houdiniFrontend/desktopIntentAck',{'input':{'sequence':launch_intent['sequence']}})
            (directory/(str(record['pid'])+'.menu-request.json')).write_text('{}',encoding='utf-8')
            menu_file=directory/(str(record['pid'])+'.menu-result.json')
            menu=wait_until(lambda:json.loads(menu_file.read_text(encoding='utf-8')) if menu_file.exists() else None,30,'actual Houdini menu worker')
            assert 'error' not in menu,menu
            assert menu['result']['executorId']==record['executor_id'],menu
            descriptor=json.loads((Path(env['DSH_HOME'])/'dsh-houdini/desktop.json').read_text(encoding='utf-8'))
            request=urllib.request.Request('http://127.0.0.1:'+str(descriptor['port'])+'/open-workspace',
                data=json.dumps(menu['payload']).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+descriptor['token']},method='POST')
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=20) as response:repeated=json.load(response)
            assert repeated['ok'] and repeated['value']==menu['result'],'same menu transport retry is idempotent'
            intent=rpc('houdiniFrontend/desktopIntent',{'input':{'after':launch_intent['sequence']}})
            assert intent['selection']['source']=='menu' and intent['selection']['sessionId']==menu['result']['sessionId'],intent
            rpc('houdiniFrontend/desktopIntentAck',{'input':{'sequence':intent['sequence']}})
            menu_target=rpc('houdiniTargets/list',{'input':{'sessionId':menu['result']['sessionId']}})['selectedTarget']
            assert menu_target['runtime_id']==target['runtime_id'] and menu_target['scene_epoch']==target['scene_epoch'],menu_target
            evidence={'hfs':str(hfs),'version':facts['version'],'action':action,'pid':facts['pid'],'executorId':record['executor_id'],
                'sessionId':session['sessionId'],'hip':facts['hip'],'mainThread':True,'pluginCopy':str(installed),
                'helperPackageInstalled':args.helper_package,'helperRoot':str(expected_helper),
                'menuSessionId':menu['result']['sessionId'],'menuIdempotent':True,'intent':intent['sequence'],'elapsedSeconds':round(time.monotonic()-started,2)}
            (directory/'result.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
            print('PASS real GUI:',facts['version'],action,'PID',facts['pid'],'main-thread read + menu callback',flush=True)
            return evidence
        finally:
            runtime.stop_owned(process);process.wait(timeout=15)


try:
    for hfs in hfss:
        for action in args.action or ['new','open']:
            report['scenarios'].append(scenario(hfs,action))
            (fixture/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
except BaseException as error:
    report['error']=str(error)
    (fixture/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    raise
print('PASS all owned Desktop integration live scenarios:',fixture,flush=True)
