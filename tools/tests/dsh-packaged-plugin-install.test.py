"""Install a release tgz using Desktop's public CLI in a fresh owned web profile.

Only Electron's Node mode is used. This does not launch the native application
window or initialize/bypass its reserved desktop profile. All mutable package
manager, Host, cache, store and preference paths are inside the test directory.
"""
import argparse
import hashlib
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
from dsh_deployment import _process_started

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--artifact',required=True,type=Path)
parser.add_argument('--desktop-root',type=Path,default=Path('D:/dshdesktop'))
parser.add_argument('--hfs',type=Path,help='Also verify the installed tarball with one owned real Houdini GUI')
parser.add_argument('--legacy-components',action='store_true',help='Seed owned legacy entry/data fixtures before automatic component preparation (requires --hfs)')
parser.add_argument('--timeout',type=int,default=600)
args=parser.parse_args()
if args.legacy_components and not args.hfs:parser.error('--legacy-components requires --hfs')
artifact=args.artifact.resolve(strict=True)
assert artifact.is_file() and artifact.suffix=='.tgz','Pass the actual release tarball'
desktop=args.desktop_root.resolve(strict=True)
cli=desktop/'resources/runtime/cli/bin/dsh.cmd'
electron=desktop/'DeepSeek Harness.exe'
assert cli.is_file() and electron.is_file()
entry=desktop/'resources/app.asar/dsh/node_modules/@deepseek-ai/dsh-desktop-host/lib/cli.js'
fixture=Path(tempfile.mkdtemp(prefix='dsh-packaged-plugin-'))
env=isolated_environment(fixture,gui=True)
for name,relative in {
    'TEMP':'temp','TMP':'temp','APPDATA':'appdata','LOCALAPPDATA':'localappdata',
    'XDG_CACHE_HOME':'cache','XDG_DATA_HOME':'data','XDG_STATE_HOME':'state',
    'PNPM_HOME':'package-manager','COREPACK_HOME':'corepack',
    'npm_config_cache':'npm-cache','npm_config_store_dir':'store',
}.items():
    target=fixture/relative;target.mkdir(parents=True,exist_ok=True);env[name]=str(target)
for name,relative in {'npm_config_userconfig':'user.npmrc','npm_config_globalconfig':'global.npmrc'}.items():
    target=fixture/relative;target.write_text('',encoding='utf-8');env[name]=str(target)
env['ELECTRON_RUN_AS_NODE']='1'
home=Path(env['DSH_HOME'])
assert not home.exists() and home.parent==fixture
print('Owned packaged-plugin evidence:',fixture,flush=True)

if args.hfs:
    # Real native menu code is used; only its system protocol activation is
    # stubbed so this fixture cannot activate the user's existing Desktop.
    hook=fixture/'menu-hook'
    menu_source='''import json,os
from pathlib import Path
import hou
from hutil.Qt import QtCore
_root=Path(os.environ['DSH_HOUDINI_TEST_MENU_ROOT'])
_request=_root/(str(os.getpid())+'.menu-request.json')
_result=_root/(str(os.getpid())+'.menu-result.json')
_timer=QtCore.QTimer(hou.qt.mainWindow())
def _save_result(value):
    temporary=_result.with_suffix('.tmp')
    temporary.write_text(json.dumps(value),encoding='utf-8')
    os.replace(temporary,_result)
def _check():
    if not _request.exists():return
    _timer.stop()
    import dsh_launcher,dsh_desktop_client
    dsh_desktop_client.activate_desktop=lambda:None
    original=dsh_desktop_client.request
    def capture(record,action,payload,**kwargs):
        try:
            value=original(record,action,payload,**kwargs)
            if action=='open-workspace':_save_result({'result':value})
            return value
        except Exception as error:
            _save_result({'error':str(error)});raise
    dsh_desktop_client.request=capture
    dsh_launcher.open_workspace()
_timer.timeout.connect(_check);_timer.start(100)
'''
    for python_version in ['3.11','3.13']:
        directory=hook/('python'+python_version+'libs');directory.mkdir(parents=True)
        (directory/'dsh_packaged_menu_fixture.py').write_text(menu_source,encoding='utf-8')
        (directory/'uiready.py').write_text('import dsh_packaged_menu_fixture\n',encoding='utf-8')
    env['HOUDINI_PATH']=str(hook)+os.pathsep+'&'
    env['DSH_HOUDINI_TEST_MENU_ROOT']=str(fixture)
    env['HOUDINI_ANONYMOUS_STATISTICS']='0'
    env['HOUDINI_NO_START_PAGE_SPLASH']='1'


def digest(file):
    value=hashlib.sha256()
    with file.open('rb') as source:
        for block in iter(lambda:source.read(1048576),b''):value.update(block)
    return value.hexdigest()


immutable=[desktop/'resources/app.asar',electron,desktop/'resources/runtime/versions.json']
baseline={str(file):digest(file) for file in immutable}
report={'nativeElectronWindowTested':False,'profile':'web','carrier':str(cli),
        'artifact':str(artifact),'artifactSha256':digest(artifact),'fixture':str(fixture),'fixtureDocumentsOverride':True}
command=[str(cli),'plugin','--profile','web','add',str(artifact),'--store-dir',str(fixture/'store')]
# Invoke the public carrier exactly as a user would. There is no direct pnpm,
# manually authored profile, compatibility exemption or source junction here.
native_command=[os.environ.get('COMSPEC','C:/Windows/System32/cmd.exe'),'/d','/s','/c',subprocess.list2cmdline(command)]
installer_wrapper=fixture/'run-native-cli.mjs'
installer_arguments=fixture/'native-cli-arguments.json'
installer_arguments.write_text(json.dumps(native_command),encoding='utf-8')
installer_wrapper.write_text("import fs from 'node:fs';import {spawn} from 'node:child_process';"
    "const [command,...args]=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));"
    "const child=spawn(command,args,{stdio:'inherit',env:process.env,windowsHide:true});"
    "child.once('error',error=>{console.error(error);process.exitCode=1});"
    "child.once('exit',code=>process.exitCode=code??1);",encoding='utf-8')
with (fixture/'plugin-install.log').open('wb') as output:
    test_node=shutil.which('node');assert test_node
    installation=runtime.spawn_frontend([test_node,str(installer_wrapper),str(installer_arguments)],node=test_node,
        cwd=fixture,env=env,stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:exit_code=installation.wait(timeout=args.timeout)
    finally:runtime.stop_owned(installation)
assert exit_code==0,'Native plugin installation failed; inspect '+str(fixture/'plugin-install.log')
print('PASS native CLI installed the actual tgz into the owned profile',flush=True)
assert not (home/'profiles/desktop').exists(),'Test must not initialize the reserved desktop profile'
profile=home/'profiles/web'
assert (profile/'package.json').is_file(),'Native manager did not initialize its explicit owned profile'
profile_manifest=json.loads((profile/'package.json').read_text(encoding='utf-8'))
assert 'dsh-houdini' in profile_manifest.get('dependencies',{}),profile_manifest

facts_file=fixture/'installed-composition.json'
inspector=fixture/'inspect.mjs'
inspector.write_text("""
import fs from 'node:fs';import path from 'node:path';import {createRequire} from 'node:module';
export const inject=['loader','tools','agentPresets','clientModules','houdiniFrontend'];
export function apply(ctx) {
  ctx.effect(()=>{let disposed=false;queueMicrotask(async()=>{
    try {
      await ctx.loader.await();
      const require=createRequire(path.join(process.env.DSH_HOME,'profiles/web/package.json'));
      const file=require.resolve('dsh-houdini/package.json'),root=fs.realpathSync(path.dirname(file));
      const manifest=JSON.parse(fs.readFileSync(file,'utf8'));
      const roster=await ctx.agentPresets.remoteExportList();
      const modes={};
      for(const id of ['houdini','standard']){
        const lease=await ctx.agentPresets.acquireScope(id);
        try{modes[id]=ctx.tools.schemas(lease.key).map(row=>row.name)}finally{await lease[Symbol.asyncDispose]()}
      }
      const graph=ctx.clientModules.graph();
      const result={root,manifest,roster,modes,graph,
        prepareBridge:typeof ctx.get('houdiniFrontend').prepareBridge==='function',
        rootEntries:[...ctx.loader.entries()].map(row=>({name:row.options.name,disabled:row.disabled}))};
      if(!disposed)fs.writeFileSync(process.env.DSH_PACKAGED_TEST_FACTS,JSON.stringify(result,null,2));
    }catch(error){if(!disposed)fs.writeFileSync(process.env.DSH_PACKAGED_TEST_FACTS,JSON.stringify({error:String(error.stack||error)}))}
  });return()=>{disposed=true}})
}
""",encoding='utf-8')
overlay=fixture/'inspect.patch.yml'
overlay.write_text('- id: workspace-controller\n  config:\n    documentsDirectory: '+json.dumps(str(fixture/'documents'))+
    '\n- insert:\n    - id: packaged-plugin-inspector\n      name: '+inspector.as_uri()+'\n',encoding='utf-8')
env['DSH_PACKAGED_TEST_FACTS']=str(facts_file)
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
log=fixture/'host.log'
auth=DshWebSession('http://127.0.0.1:'+str(port),str(log),str(fixture/'runtime.json'))


def rpc(method,arguments,allow_error=False,timeout=15):
    request=urllib.request.Request('http://127.0.0.1:'+str(port)+'/api/'+method,
        data=json.dumps({'type':'client-request','rpcId':uuid.uuid4().hex,'method':method,'payload':{'args':arguments}}).encode(),
        headers={'Content-Type':'application/json'},method='POST')
    with auth.open(request,timeout=timeout) as response:result=json.load(response)['result']
    if allow_error:return result
    assert result['ok'],result
    return result['value']


def wait_until(probe,timeout,label):
    deadline=time.monotonic()+timeout
    while True:
        value=probe()
        if value is not None:return value
        assert time.monotonic()<deadline,'Timed out: '+label
        time.sleep(.2)


def verify_real_houdini(installed,workspace_id):
    hfs=args.hfs.resolve(strict=True)
    installations=rpc('houdiniFrontend/projectInstallations',{})
    selected=next(row for row in installations if Path(row['hfs']).samefile(hfs))
    install_root=Path(env['LOCALAPPDATA'])/'DSH-Houdini'
    package_path=Path(env['HOUDINI_PACKAGE_DIR'])/'dsh-houdini.json'
    assert install_root.is_relative_to(fixture) and package_path.is_relative_to(fixture)
    assert not package_path.exists(),'The project action must perform the first component installation'
    legacy_files={}
    legacy_packages={}
    legacy_bootstrap=None
    if args.legacy_components:
        legacy_bootstrap=install_root/'bootstrap/1234567890abcdef'
        # These files are never executed by this test. If an old Package still
        # reaches the real Houdini startup, its only action is an explicit error.
        for relative in ['python3.11libs/pythonrc.py','python3.13libs/pythonrc.py','python/dsh_bootstrap.py']:
            path=legacy_bootstrap/relative;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(b'raise RuntimeError("DSH_LEGACY_BOOTSTRAP_SENTINEL")\n')
            legacy_files[path]=digest(path)
        package_path.parent.mkdir(parents=True,exist_ok=True)
        old_package={'env':[{'DSH_HOUDINI_INSTALL_ROOT':install_root.as_posix()},
            {'PYTHONPATH':legacy_bootstrap.as_posix()+'/python;$PYTHONPATH'}],'path':legacy_bootstrap.as_posix()}
        for path in [package_path,package_path.with_name('copied-old-dsh.json')]:
            path.write_text(json.dumps(old_package,indent=2),encoding='utf-8')
            legacy_packages[path]=digest(path)
        for relative,data in {
            'releases/0.0.15/runtime.bin':b'old-runtime-fixture-never-execute',
            'data/old-install/sessions/fixture.jsonl':b'old-session-fixture-preserve',
            'data/old-install/credentials.bin':b'opaque-dummy-credentials-preserve',
            'DSH-Houdini.lnk':b'unknown-user-shortcut-fixture-preserve',
        }.items():
            path=install_root/relative;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data);legacy_files[path]=digest(path)
    session=rpc('session/create',{'request':{'sessionId':uuid.uuid4().hex,'workspaceId':workspace_id,'agentPreset':'houdini'}})
    # The real public action owns all preparation. Its 120s installer budget is
    # separate from the subsequent native Houdini startup wait.
    launched=rpc('houdiniFrontend/projectAction',{'input':{'action':'new','sessionId':session['sessionId'],'hfs':selected['hfs']}},timeout=150)
    assert launched.get('phase') in ('waiting','ready'),launched
    package=json.loads(package_path.read_text(encoding='utf-8-sig'))
    package_values={key:value for row in package['env'] for key,value in row.items()}
    assert Path(package_values['DSH_HOUDINI_INSTALL_ROOT']).samefile(install_root)
    helper_root=Path(package_values['DSH_HOUDINI_PATH']).parent.resolve(strict=True)
    assert helper_root.parent.samefile(install_root/'helpers') and not helper_root.samefile(installed)
    assert len(helper_root.name)==16 and all(char in '0123456789abcdef' for char in helper_root.name)
    assert (helper_root/'installer/uninstall.ps1').is_file() and (helper_root/'installer/legacy-migration.ps1').is_file()
    component_report=None
    if args.legacy_components:
        reports=list((install_root/'migrations').glob('*/report.json'))
        component_report=next(path for path in reports if json.loads(path.read_text(encoding='utf-8')).get('status')=='applied')
        migration=json.loads(component_report.read_text(encoding='utf-8'))
        retired={Path(action['path']):action for action in migration['actions'] if action['operation']=='disable' or action.get('retiredLegacy')}
        assert set(legacy_packages)<=set(retired),'Automatic preparation must retire both canonical and copied legacy registrations'
        for path,sha in legacy_packages.items():
            action=retired[path]
            assert action['beforeSha256']==sha and digest(component_report.parent/action['backup'])==sha
            if action['operation']=='disable':assert not path.exists() and digest(Path(action['disabledPath']))==sha
        assert any(Path(item['path'])==install_root/'DSH-Houdini.lnk' for item in migration['preserved'])
        assert all(path.is_file() and digest(path)==sha for path,sha in legacy_files.items())
    print('Waiting for real Houdini from the installed tarball:',selected['version'],flush=True)
    def status():
        value=rpc('houdiniFrontend/projectLaunchStatus',{'input':{'id':launched['id']}})
        if value['phase']=='waiting':return None
        assert value['phase']=='ready',value
        return value
    ready=wait_until(status,240,'installed tgz real Houdini launch')
    listing=rpc('houdiniTargets/list',{'input':{'sessionId':session['sessionId']}})
    target=listing['selectedTarget'];assert listing['state']['status']=='selected'
    record=next(row for row in listing['candidates'] if row['executor_id']==target['executor_id'])
    assert runtime.owns_pid(record['pid']),'Houdini must belong to this fixture Job'
    birth=_process_started(record['pid']);assert birth is not None
    assert ready['result']['sessionId']==session['sessionId']
    checker=fixture/'check-houdini.mjs'
    checker.write_text('import fs from "node:fs";import {HoudiniBridge} from '+json.dumps((installed/'lib/bridge.js').as_uri())+''';
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),signal=AbortSignal.timeout(45000);
const bridge=new HoudiniBridge(input.record.bridge_url,45000,input.target.executor_id,undefined,{runtimeId:input.target.runtime_id,sceneEpoch:input.target.scene_epoch});
await bridge.claimWriter(input.sessionId,input.record.registration_id,input.record.hip_path,signal);
const code="import os,sys,threading,dsh_bridge,dsh_launcher,dsh_desktop_client,dsh_workbench_entry\\n__result__={'version':hou.applicationVersionString(),'hip':hou.hipFile.path(),'new':hou.hipFile.isNewFile(),'hfs':hou.getenv('HFS'),'pid':os.getpid(),'mainThread':threading.get_ident()==dsh_bridge._HOU_THREAD_ID,'bridgeFile':dsh_bridge.__file__,'pythonPath':list(sys.path),'loadedFiles':{'launcher':dsh_launcher.__file__,'desktopClient':dsh_desktop_client.__file__,'entry':dsh_workbench_entry.__file__}}";
const value=await bridge.exec(code,{sessionId:input.sessionId,callId:'packaged-real-houdini-read'},signal,undefined,true);
fs.writeFileSync(process.argv[3],JSON.stringify(value));if(value.ok!==true)process.exitCode=1;
''',encoding='utf-8')
    inputs=fixture/'hom-input.json';inputs.write_text(json.dumps({'record':record,'target':target,'sessionId':session['sessionId']}),encoding='utf-8')
    hom_file=fixture/'hom-result.json'
    checked=subprocess.run([shutil.which('node'),str(checker),str(inputs),str(hom_file)],cwd=fixture,env=env,
        capture_output=True,timeout=65,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (fixture/'hom-check.log').write_bytes(checked.stdout+checked.stderr)
    assert checked.returncode==0,'Installed Bridge GUI check failed; inspect hom-check.log'
    facts=json.loads(hom_file.read_text(encoding='utf-8'))['result']
    assert facts['mainThread'] and facts['new'] and facts['pid']==record['pid'] and facts['version']==selected['version'],facts
    assert Path(facts['hfs']).samefile(hfs) and Path(facts['bridgeFile']).resolve().is_relative_to(helper_root),facts
    assert all(filename and Path(filename).resolve().is_relative_to(helper_root) for filename in facts['loadedFiles'].values()),facts['loadedFiles']
    if args.legacy_components:
        legacy_prefix=os.path.normcase(str(legacy_bootstrap.resolve()))
        assert not any(os.path.normcase(os.path.abspath(path)).startswith(legacy_prefix) for path in facts['pythonPath'] if path)
        launch_log=home/'dsh-houdini/launches'/(launched['id']+'.log')
        assert b'DSH_LEGACY_BOOTSTRAP_SENTINEL' not in launch_log.read_bytes(),'Retired legacy startup code ran in the new Houdini'
        assert all(path.is_file() and digest(path)==sha for path,sha in legacy_files.items())
    (fixture/(str(record['pid'])+'.menu-request.json')).write_text('{}',encoding='utf-8')
    menu_file=fixture/(str(record['pid'])+'.menu-result.json')
    menu=wait_until(lambda:json.loads(menu_file.read_text(encoding='utf-8')) if menu_file.exists() else None,30,'installed native menu worker')
    assert 'error' not in menu,menu
    assert menu['result']['sessionId']==session['sessionId'],'Native menu must return the exact registered writer conversation'
    assert menu['result']['executorId']==target['executor_id'],menu
    print('PASS installed helper GUI, main-thread HOM and exact native-menu conversation',flush=True)
    return {**facts,'releaseTarballUsed':True,'automaticComponentPreparation':True,'helperRoot':str(helper_root),
        'componentInstallRoot':str(install_root),'legacyComponents':args.legacy_components,
        'migrationReport':str(component_report) if component_report else None,
        'legacyFilesRetained':len(legacy_files),'legacyEntryCount':len(legacy_packages),'sessionId':session['sessionId'],
        'menuSessionId':menu['result']['sessionId'],'writerClaimed':True,'processStarted':birth,'externalDesktopActivationStubbed':True}


with log.open('wb') as output:
    # Same immutable Desktop Host carrier as dsh.cmd. The public `web` command
    # is used, and the start gate establishes our Job before any child spawns.
    process=runtime.spawn_frontend([str(electron),'--expose-internals',str(entry),'web','--patch',str(overlay),
        '--port',str(port),'--no-open'],node=str(electron),cwd=fixture,env=env,
        stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        deadline=time.monotonic()+90
        while not facts_file.exists():
            assert process.poll() is None,'Packaged Host exited; inspect '+str(log)
            assert time.monotonic()<deadline,'Packaged Host composition timeout; inspect '+str(log)
            time.sleep(.2)
        facts=json.loads(facts_file.read_text(encoding='utf-8'))
        assert 'error' not in facts,facts
        installed=Path(facts['root']).resolve(strict=True)
        assert installed.is_relative_to(fixture),'Plugin must be installed into the owned data/store tree'
        assert not installed.is_relative_to(ROOT),'Formal tgz test cannot resolve to the checkout'
        manifest=facts['manifest']
        assert manifest['name']=='dsh-houdini' and manifest['engines']['dsh']=='0.2.1-rc.3',manifest
        presets=facts['roster']['presets'];houdini=next(row for row in presets if row['id']=='houdini');standard=next(row for row in presets if row['id']=='standard')
        assert standard['isDefault'] and not houdini['isDefault'] and len(presets)>=5 and 'broken' not in houdini,presets
        assert {'houdini_exec','houdini_inspect','houdini_isolated'}<=set(facts['modes']['houdini'])
        assert not any(name.startswith('houdini_') for name in facts['modes']['standard'])
        entries=facts['graph'].get('entries',facts['graph']) if isinstance(facts['graph'],dict) else facts['graph']
        assert sum(row['id']=='dsh-houdini' for row in entries)==1
        assert facts['prepareBridge'] is True
        for relative in ['Install.cmd','Uninstall.cmd','Open Workspace.cmd','installer/install.ps1','installer/uninstall.ps1','installer/legacy-migration.ps1',
                         'installer/open-desktop.ps1','houdini/MainMenuCommon.xml','lib/frontend-host.js','client.js',
                         'locale/en.json','locale/zh.json','assets/dsh-houdini-plugin.png']:
            assert (installed/relative).is_file(),'Release installation omitted '+relative
        assert (installed/'assets/dsh-houdini-plugin.png').stat().st_size<=256*1024,'Installed icon exceeds the official limit'
        auth.authorize(timeout=5)
        deadline=time.monotonic()+15
        while not rpc('houdiniFrontend/capabilities',{})['desktop']:
            assert time.monotonic()<deadline,'Installed Desktop integration never became available'
            time.sleep(.1)
        assert rpc('agentPresets/list',{})==facts['roster']
        print('PASS packaged official Host modes, scoped tools and root client',flush=True)
        descriptor=json.loads((home/'dsh-houdini/desktop.json').read_text(encoding='utf-8'))
        assert Path(descriptor['pluginRoot']).samefile(installed)
        workspace=fixture/'conversation';workspace.mkdir()
        workspace_id=rpc('workspace/create',{'request':{'path':str(workspace)}})['workspace']['workspaceId']
        ordinary=rpc('session/create',{'request':{'sessionId':uuid.uuid4().hex,'workspaceId':workspace_id}})
        assert ordinary['agentPreset']=='standard'
        refused=rpc('houdiniFrontend/prepareBridge',{'input':{'sessionId':ordinary['sessionId']}},allow_error=True)
        assert refused['ok'] is False,'Component preparation must refuse other modes before touching any Houdini preferences'
        if args.hfs:report['houdiniGui']=verify_real_houdini(installed,workspace_id)
        media=installed/'runtime/video'
        for relative in ['runtime.json','build-provenance.json','SOURCE-NOTICE.txt','COPYING.LGPLv2.1','build-configure.txt',
                         'ffmpeg/bin/ffmpeg.exe','ffmpeg/bin/ffprobe.exe']:
            assert (media/relative).is_file(),'Installed release is missing media '+relative
        metadata=json.loads((media/'runtime.json').read_text(encoding='utf-8'))
        provenance=json.loads((media/'build-provenance.json').read_text(encoding='utf-8'))
        assert isinstance(provenance.get('files'),dict) and provenance['files']
        for relative,expected_hash in provenance['files'].items():
            member=(media/relative).resolve(strict=True)
            assert member.is_relative_to(media.resolve()) and digest(member)==expected_hash,'Installed media inventory mismatch: '+relative
        probes={}
        for name in ['ffmpeg','ffprobe']:
            result=subprocess.run([str(media/'ffmpeg/bin'/(name+'.exe')),'-version'],cwd=media/'ffmpeg/bin',env=env,
                capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            assert result.returncode==0,name+' failed from the installed tarball'
            probes[name]=(result.stdout+result.stderr).decode('utf-8',errors='replace').splitlines()[0]
        assert not (home/'profiles/desktop').exists()
        report.update(ok=True,version=manifest['version'],engine=manifest['engines']['dsh'],installedRoot=str(installed),
            modeIds=[row['id'] for row in presets],rootClientCount=1,prepareBridgeOtherModeRefused=True,
            mediaRoot=str(media),mediaVersion=metadata['ffmpeg']['version'],mediaProbes=probes,
            mediaInventoryFiles=len(provenance['files']),
            runtimeRelease=facts['graph'].get('release') if isinstance(facts['graph'],dict) else None)
    finally:
        runtime.stop_owned(process);process.wait(timeout=15)
assert {str(file):digest(file) for file in immutable}==baseline,'Native Desktop immutable installation changed'
if report.get('houdiniGui'):
    gui=report['houdiniGui']
    wait_until(lambda:True if _process_started(gui['pid'])!=gui['processStarted'] else None,15,'owned Houdini process exit')
    gui['ownedProcessExited']=True
report['desktopImmutableFilesUnchanged']=True
(fixture/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS native Desktop CLI tgz installation + exact packaged Node-mode Host:',fixture,flush=True)
