"""Pin only one fresh Native Desktop fixture, using the real Host-parent OS boundary.
No Houdini, model requests, login, user profile, Desktop patch or system-protocol invocation.
"""
import argparse,base64,hashlib,http.server,json,os,re,shutil,subprocess,sys,tarfile,tempfile,threading,time,winreg
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from houdini_test_environment import isolated_environment,reexec_unpacked_test_cli
reexec_unpacked_test_cli()
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
from dsh_deployment import _process_started

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ui',action='store_true');parser.add_argument('--artifact',type=Path);parser.add_argument('--source-snapshot',action='store_true');parser.add_argument('--expected-integrity');args=parser.parse_args()
if args.artifact:assert args.ui,'--artifact is only used by --ui'
desktop=Path('D:/dshdesktop');electron=desktop/'DeepSeek Harness.exe'
fixture=Path(tempfile.mkdtemp(prefix='dsh-native-pin-'));print('Owned Native pin fixture:',fixture,flush=True)
env={key.upper():value for key,value in isolated_environment(fixture,gui=True).items()}
for key,name in {'APPDATA':'appdata','LOCALAPPDATA':'localappdata','TEMP':'temp','TMP':'temp','DSH_AGENTS_HOME':'agents','NPM_CONFIG_CACHE':'npm-cache','NPM_CONFIG_STORE_DIR':'store','PNPM_HOME':'package-manager'}.items():
    directory=fixture/name;directory.mkdir(parents=True,exist_ok=True);env[key]=str(directory)
for key in ['NPM_CONFIG_USERCONFIG','NPM_CONFIG_GLOBALCONFIG']:
    file=fixture/(key+'.npmrc');file.write_text('',encoding='utf-8');env[key]=str(file)
env.update(DSH_HOME=str(fixture/'harness'),DSH_DESKTOP_OPEN_DEVTOOLS='0',DSH_WINDOW_PIN_FIXTURE_KEY='owned-pin-configuration-only')
profile=Path(env['DSH_HOME'])/'profiles/desktop';user_data=fixture/'browser';plugin=fixture/'plugin';plugin.mkdir()
command=fixture/'commands';reply=fixture/'replies';command.mkdir();reply.mkdir();env['DSH_PIN_COMMAND']=str(command);env['DSH_PIN_REPLY']=str(reply)
env['DSH_PIN_ROOT']=str(fixture/'pin-state');env['DSH_PIN_META']=str(fixture/'host-meta.json')
report={'fixture':str(fixture),'nativeElectronWindowTested':False,'userProfileTouched':False,'modelRequests':0}
process=None;output=None;server=None;requests=0

def digest(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def tree(key):
    values={};children={};index=0
    while True:
        try:name,value,kind=winreg.EnumValue(key,index)
        except OSError:break
        values[name]=[kind,value];index+=1
    index=0
    while True:
        try:name=winreg.EnumKey(key,index)
        except OSError:break
        with winreg.OpenKey(key,name) as child:children[name]=tree(child)
        index+=1
    return {'values':values,'children':children}
def protocol():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\dsh\UserChoice') as key:choice=winreg.QueryValueEx(key,'ProgId')[0]
    except FileNotFoundError:choice=None
    assert choice is None,'Refusing launch with a user-chosen dsh protocol handler'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Classes\dsh\shell\open\command') as key:assert winreg.QueryValueEx(key,'')[0]=='"'+str(electron)+'" "%1"'
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,r'dsh\shell\open\command') as key:assert winreg.QueryValueEx(key,'')[0]=='"'+str(electron)+'" "%1"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Classes\dsh') as key:own=tree(key)
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,'dsh') as key:effective=tree(key)
    return hashlib.sha256(json.dumps([own,effective],sort_keys=True).encode()).hexdigest()
def run(argv,**kwargs):
    result=subprocess.run([str(value) for value in argv],cwd=kwargs.pop('cwd',fixture),env=env,capture_output=True,timeout=kwargs.pop('timeout',180),**kwargs)
    assert result.returncode==0,(result.stdout+result.stderr).decode('utf-8',errors='replace')
    return result
def wait(read,label,seconds=90):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        value=read()
        if value is not None:return value
        time.sleep(.1)
    raise AssertionError('Timed out: '+label)
def act(action,**data):
    import uuid
    identifier=uuid.uuid4().hex;temporary=command/(identifier+'.tmp');target=reply/(identifier+'.json')
    temporary.write_text(json.dumps({'id':identifier,'action':action,**data}),encoding='utf-8');temporary.replace(command/(identifier+'.json'))
    def read():
        if not target.exists():return
        try:value=json.loads(target.read_text(encoding='utf-8'))
        except (ValueError,OSError):return
        if value.get('id')==identifier:return value
    value=wait(read,'owned Host '+action,20)
    assert value.get('ok'),value
    return value['value']

try:
    baseline_protocol=protocol();immutable={str(p):digest(p) for p in [electron,desktop/'resources/app.asar']}
    class Loopback(http.server.BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_GET(self):
            global requests
            requests+=1;self.send_response(400);self.end_headers()
        def do_POST(self):
            global requests
            if not args.ui:return self.do_GET()
            self.rfile.read(int(self.headers.get('Content-Length','0')));requests+=1
            rows=[{'id':'pin-ui','object':'chat.completion.chunk','model':'idle-fixture','choices':[{'index':0,'delta':{'role':'assistant','content':'Owned pin fixture ready.'},'finish_reason':None}]},
                {'id':'pin-ui','object':'chat.completion.chunk','model':'idle-fixture','choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}]
            body=(''.join('data: '+json.dumps(row)+'\n\n' for row in rows)+'data: [DONE]\n\n').encode()
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Loopback)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    # Copy installed code, not a junction to the development worktree.
    if not args.ui:
        for name in ['desktop-window.js','desktop-paths.js']:shutil.copy2(ROOT/'lib'/name,plugin/name)
    (plugin/'package.json').write_text('{"type":"module"}',encoding='utf-8')
    for name in ['koffi','@koromix/koffi-win32-x64','@deepseek-ai/dsh-home-paths']:
        shutil.copytree(ROOT/'node_modules'/name,plugin/'node_modules'/name)
    if not args.ui:report['moduleSha256']=digest(plugin/'desktop-window.js')
    inspector=plugin/'index.mjs'
    inspector.write_text(r'''import fs from 'node:fs/promises';import {createRequire} from 'node:module';
import {DesktopWindowController,createNativeDesktopWindowOS} from './desktop-window.js';
export async function apply(ctx){const boundary=createNativeDesktopWindowOS(),controller=new DesktopWindowController({root:process.env.DSH_PIN_ROOT,os:boundary});
const koffi=createRequire(import.meta.url)('koffi'),user=koffi.load('user32.dll'),kernel=koffi.load('kernel32.dll');
const self=kernel.func('__stdcall','GetCurrentProcess','void *',[]),times=kernel.func('__stdcall','GetProcessTimes','int',['void *','void *','void *','void *','void *']);const born=Buffer.alloc(8);if(!times(self(),born,Buffer.alloc(8),Buffer.alloc(8),Buffer.alloc(8)))throw Error('Own Host birth unavailable');
const meta=process.env.DSH_PIN_META;await fs.writeFile(meta+'.tmp',JSON.stringify({pid:process.pid,parentPid:process.ppid,birth:born.readBigUInt64LE().toString()}));await fs.rename(meta+'.tmp',meta);
const rect=user.func('__stdcall','GetWindowRect','int',['void *','void *']);const foreground=user.func('__stdcall','GetForegroundWindow','void *',[]);
let stopped=false,busy=false,last;const ready=controller.start();
ctx.effect(()=>{const timer=setInterval(async()=>{if(stopped||busy)return;busy=true;try{
 const file=(await fs.readdir(process.env.DSH_PIN_COMMAND)).find(name=>name.endsWith('.json'));if(!file)return;const source=process.env.DSH_PIN_COMMAND+'/'+file;const request=JSON.parse(await fs.readFile(source,'utf8'));await fs.unlink(source);if(request.id===last)return;last=request.id;
 let value;try{await ready;
 if(request.action==='read')value=await controller.read();
 else if(request.action==='activate')value=await controller.activate(request.owner);
 else if(request.action==='set')value=await controller.set(request.owner,request.pinned);
 else if(request.action==='release')value=await controller.release(request.owner);
 else if(request.action==='snapshot'){const window=await boundary.current(),buffer=Buffer.alloc(16);if(!rect(BigInt(window.hwnd),buffer))throw Error('GetWindowRect failed');value={window,rect:[0,4,8,12].map(offset=>buffer.readInt32LE(offset)),foreground:foreground()?.toString()??null,hostPid:process.pid,parentPid:process.ppid,recordPath:controller.recordPath};}
 else throw Error('Unexpected fixture action');
 const file=process.env.DSH_PIN_REPLY+'/'+request.id+'.tmp';await fs.writeFile(file,JSON.stringify({id:request.id,ok:true,value}));await fs.rename(file,process.env.DSH_PIN_REPLY+'/'+request.id+'.json');
 }catch(error){await fs.writeFile(process.env.DSH_PIN_REPLY+'/'+request.id+'.json',JSON.stringify({id:request.id,ok:false,error:String(error.stack||error)}));}
 }catch(error){if(error.code!=='ENOENT'&&!(error instanceof SyntaxError))ctx.logger.error(error);}finally{busy=false}},50);timer.unref();return async()=>{stopped=true;clearInterval(timer);await controller.dispose()}})}
''',encoding='utf-8')
    if args.ui:
        # Metadata only: the real package owns the sole production controller.
        inspector.write_text('''import fs from 'node:fs/promises';import {createRequire} from 'node:module';
export async function apply(){const k=createRequire(import.meta.url)('koffi'),kernel=k.load('kernel32.dll');const self=kernel.func('__stdcall','GetCurrentProcess','void *',[]),times=kernel.func('__stdcall','GetProcessTimes','int',['void *','void *','void *','void *','void *']),born=Buffer.alloc(8);if(!times(self(),born,Buffer.alloc(8),Buffer.alloc(8),Buffer.alloc(8)))throw Error('Own birth unavailable');const file=process.env.DSH_PIN_META;const facts={pid:process.pid,parentPid:process.ppid,birth:born.readBigUInt64LE().toString()};
try{const anchored=createRequire(await fs.realpath(process.env.DSH_PIN_INSTALLED_PACKAGE));facts.koffiModule=anchored.resolve('koffi');facts.koffiVersion=anchored('koffi').version;}catch(error){facts.peerResolutionError=String(error.message||error)}
await fs.writeFile(file+'.tmp',JSON.stringify(facts));await fs.rename(file+'.tmp',file)}
''',encoding='utf-8')
    init=fixture/'init.mjs'
    init.write_text("import{createRequire}from'node:module';import{pathToFileURL}from'node:url';const r=createRequire(process.argv[2]);const b=await import(pathToFileURL(r.resolve('@deepseek-ai/dsh-app-boot')));b.initProfile(process.argv[3],b.PROFILE_TEMPLATES.web.bundles);",encoding='utf-8')
    env['ELECTRON_RUN_AS_NODE']='1';run([electron,'--expose-internals',init,desktop/'resources/app.asar/dsh/node_modules/@deepseek-ai/dsh/package.json',profile]);env.pop('ELECTRON_RUN_AS_NODE',None)
    (profile/'cordis.patch.yml').write_text('- id: workspace-controller\n  config:\n    documentsDirectory: '+json.dumps(str(fixture/'documents'))+'\n'
        '- id: llm-pi-ai\n  config:\n    providers:\n      owned-pin-chat:\n        api: openai-completions\n        baseURL: '+json.dumps('http://127.0.0.1:'+str(server.server_port)+'/v1/')+'\n        apiKeyEnv: DSH_WINDOW_PIN_FIXTURE_KEY\n        models:\n          - id: idle-fixture\n            input: [text]\n'
        '- insert:\n    - id: owned-window-pin-fixture\n      name: '+inspector.as_uri()+'\n',encoding='utf-8')
    if args.ui:
        if args.artifact:
            artifact=args.artifact.resolve(strict=True);report['explicitArtifactSpecified']=True
            if args.source_snapshot:report['sourceSnapshotForTest']=True
        else:
            npm=shutil.which('npm.cmd') or shutil.which('npm');assert npm
            npm_cli=Path(npm).parent/'node_modules/npm/bin/npm-cli.js';assert npm_cli.is_file()
            packed=run([shutil.which('node'),npm_cli,'pack','--ignore-scripts','--json','--pack-destination',fixture],cwd=ROOT,timeout=180)
            artifact=fixture/json.loads(packed.stdout.decode('utf-8'))[0]['filename'];report['sourceSnapshotForTest']=True
        report['artifactSha256']=digest(artifact)
        with artifact.open('rb') as stream:report['artifactIntegrity']='sha512-'+base64.b64encode(hashlib.file_digest(stream,'sha512').digest()).decode('ascii')
        if args.expected_integrity:assert report['artifactIntegrity']==args.expected_integrity,'Frozen artifact integrity mismatch'
        with tarfile.open(artifact,'r:gz') as package:
            manifest=json.load(package.extractfile('package/package.json'))
            expected_client=hashlib.sha256(package.extractfile('package/client.js').read()).hexdigest()
            expected_window=hashlib.sha256(package.extractfile('package/lib/desktop-window.js').read()).hexdigest()
        report['artifactVersion']=manifest['version']
        report['koffiDeclaration']={'peer':manifest.get('peerDependencies',{}).get('koffi'),'direct':manifest.get('dependencies',{}).get('koffi')}
        assert report['koffiDeclaration']=={'peer':'3.1.1','direct':None},'Expected frozen standard peer declaration'
        env['ELECTRON_RUN_AS_NODE']='1'
        install=run([electron,'--expose-internals',desktop/'resources/app.asar/dsh/node_modules/@deepseek-ai/dsh-desktop-host/lib/cli.js','plugin','--profile','desktop','add',artifact,'--store-dir',fixture/'package-manager/store'],timeout=240)
        report['buildApprovalRequested']=b'ERR_PNPM_IGNORED_BUILDS' in install.stdout+install.stderr
        assert not report['buildApprovalRequested']
        env.pop('ELECTRON_RUN_AS_NODE',None)
        installed=profile/'node_modules/dsh-houdini'
        report['installedClientSha256']=digest(installed/'client.js');report['installedWindowSha256']=digest(installed/'lib/desktop-window.js')
        assert report['installedClientSha256']==expected_client and report['installedWindowSha256']==expected_window
        report['moduleSha256']=report['installedWindowSha256']
        if not args.artifact:
            assert expected_client==digest(ROOT/'client.js') and expected_window==digest(ROOT/'lib/desktop-window.js')
        report['nativeCliPluginInstallUsed']=True
        env['DSH_PIN_INSTALLED_PACKAGE']=str(installed/'package.json')
    probe=fixture/'main-probe.mjs'
    probe.write_text(r'''import fs from 'node:fs/promises';const c=JSON.parse(await fs.readFile(process.argv[2],'utf8'));const socket=new WebSocket(c.url);await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})});let id=0;const pending=new Map();socket.addEventListener('message',event=>{const value=JSON.parse(event.data);if(value.id)pending.get(value.id)(value)});async function call(method,params){const request=++id;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Main inspector timeout')),10000);pending.set(request,value=>{clearTimeout(timer);pending.delete(request);value.error?reject(Error(JSON.stringify(value.error))):resolve(value.result)});socket.send(JSON.stringify({id:request,method,params}))})}
const body=`(()=>{if(process.pid!==${c.pid})throw Error('Foreign Main');const e=process.getBuiltinModule('module').createRequire(process.resourcesPath+'/app.asar/package.json')('electron');const windows=e.BrowserWindow.getAllWindows().filter(w=>w.webContents.getURL().startsWith('dsh-app://app/'));if(windows.length!==1)throw Error('No unique own Native app window');const w=windows[0];${c.action==='show'?'w.show();w.focus();':''}${c.action==='hide'?'w.hide();':''}${c.action==='extra'?'globalThis.__pinExtra=new e.BrowserWindow({show:true,width:180,height:120});':''}${c.action==='remove-extra'?'globalThis.__pinExtra.destroy();delete globalThis.__pinExtra;':''}${c.action==='quit'?'setTimeout(()=>e.app.quit(),30);':''}return{pid:process.pid,hwnd:w.getNativeWindowHandle().readBigUInt64LE().toString(),pinned:w.isAlwaysOnTop(),visible:w.isVisible(),bounds:w.getBounds()}})()`;
try{const value=await call('Runtime.evaluate',{expression:body,returnByValue:true});if(value.exceptionDetails)throw Error(JSON.stringify(value.exceptionDetails));await fs.writeFile(c.output,JSON.stringify(value.result.value));}finally{socket.close()}
''',encoding='utf-8')
    log=fixture/'native.log';output=log.open('wb')
    process=subprocess.Popen([str(electron),'--inspect=127.0.0.1:0','--remote-debugging-port=0','--user-data-dir='+str(user_data)],cwd=fixture,env=env,stdout=output,stderr=subprocess.STDOUT)
    birth=wait(lambda:_process_started(process.pid),'own Main birth',8);report.update(mainPid=process.pid,mainBirth=birth)
    def endpoint():
        assert process.poll() is None,'Own Native Main exited before readiness'
        match=re.search(r'Debugger listening on (ws://127\.0\.0\.1:\d+/[^\s]+)',log.read_text(encoding='utf-8',errors='replace'))
        return match.group(1) if match else None
    url=wait(endpoint,'own Main inspector')
    def oracle(action):
        config=fixture/'probe.json';target=fixture/'probe-result.json';config.write_text(json.dumps({'url':url,'pid':process.pid,'action':action,'output':str(target)}),encoding='utf-8')
        run([shutil.which('node'),probe,config]);return json.loads(target.read_text(encoding='utf-8'))
    # The exact own Main is shown before measurement; it is never selected by a
    # title, foreground handle, or guessed process list in the production code.
    def show():
        if not (user_data/'DevToolsActivePort').exists():return
        try:return oracle('show')
        except AssertionError as error:
            if 'No unique own Native app window' in str(error):return
            raise
    host_meta=wait(lambda:json.loads((fixture/'host-meta.json').read_text()) if (fixture/'host-meta.json').exists() else None,'own plugin Host metadata')
    report['hostPid']=host_meta['pid'];report['hostBirth']=host_meta['birth'];report['koffiPeer']={key:value for key,value in host_meta.items() if key.startswith('koffi') or key=='peerResolutionError'};assert _process_started(host_meta['pid'])==host_meta['birth'] and host_meta['parentPid']==process.pid
    initial=wait(show,'own native app window');report['nativeElectronWindowTested']=True
    if args.ui:
        # Root's actual client and actual frontend service own all pin actions.
        def browser_port():
            f=user_data/'DevToolsActivePort'
            return int(f.read_text().splitlines()[0]) if f.exists() else None
        port=wait(browser_port,'own renderer CDP')
        (fixture/'conversation').mkdir()
        ui_input=fixture/'ui-input.json';ui_output=fixture/'ui-result.json'
        ui_input.write_text(json.dumps({'port':port,'mainInspector':url,'mainPid':process.pid,'pluginPackage':str(plugin/'package.json'),'recordPath':str(Path(env['DSH_HOME'])/'dsh-houdini/window-pins'/(str(process.pid)+'.json')),'conversation':str(fixture/'conversation'),'output':str(ui_output)}),encoding='utf-8')
        ui_run=subprocess.run([shutil.which('node'),str(ROOT/'tools/tests/desktop-window-pin-ui-probe.mjs'),str(ui_input)],cwd=fixture,env=env,capture_output=True,timeout=240)
        if ui_output.exists():report['ui']=json.loads(ui_output.read_text(encoding='utf-8'))
        assert ui_run.returncode==0,(ui_run.stdout+ui_run.stderr).decode('utf-8',errors='replace')
        report['nativeElectronWindowTested']=True
        assert report['koffiPeer'].get('koffiVersion')=='3.1.1' and str(desktop).lower() in report['koffiPeer'].get('koffiModule','').lower(),'Actual peer must come from the official installation'
    else:
        available=wait(lambda:act('read') if command.parent.exists() else None,'owned Host boundary')
        assert available['available'],available
        report['nativeElectronWindowTested']=True
        A='a'*32;B='b'*32
        act('activate',owner=A);before=act('snapshot');report['before']=before
        assert before['parentPid']==process.pid and before['window']['pid']==process.pid and before['window']['hwnd']==initial['hwnd']
        assert before['window']['started']==birth
        report['hostPid']=before['hostPid'];report['hostBirth']=_process_started(before['hostPid'])
        target=not before['window']['pinned'];act('set',owner=A,pinned=target);after=act('snapshot')
        assert after['window']['pinned']==target and after['rect']==before['rect'] and after['foreground']==before['foreground']
        act('release',owner=A);released=act('snapshot');assert released['window']['pinned']==before['window']['pinned']
        assert released['rect']==before['rect'] and released['foreground']==before['foreground'];assert not Path(before['recordPath']).exists()
        report.update(after=after,released=released,geometryAndFocusPreserved=True,baselineRestored=True)
        act('activate',owner=B);act('set',owner=B,pinned=target);oracle('hide');act('release',owner=B)
        hidden=oracle('read');assert not hidden['visible'] and hidden['pinned']==before['window']['pinned'];assert not Path(before['recordPath']).exists()
        report['hiddenLeaseRestoredWithoutShowing']=True
        oracle('show');oracle('extra');ambiguous=act('read');assert not ambiguous['available'] and '多个' in ambiguous['reason'];oracle('remove-extra')
        report['ambiguousMainWindowsRejected']=True
    oracle('quit');assert process.wait(timeout=30)==0;output.close();output=None
    if args.ui and args.artifact and not args.source_snapshot:
        # Honour Native manager's restart-required outcome and consume the
        # resulting profile again; this is a new owned Main, never a user one.
        report['firstMainNormalExitCode']=0;report['firstMainPid']=report['mainPid'];report['firstMainBirth']=report['mainBirth'];report['firstHostPid']=report['hostPid'];report['firstHostBirth']=report['hostBirth'];report['hostPid']=None;report['hostBirth']=None
        (fixture/'host-meta.json').unlink(missing_ok=True);(user_data/'DevToolsActivePort').unlink(missing_ok=True)
        log=fixture/'native-reopen.log';output=log.open('wb')
        process=subprocess.Popen([str(electron),'--inspect=127.0.0.1:0','--remote-debugging-port=0','--user-data-dir='+str(user_data)],cwd=fixture,env=env,stdout=output,stderr=subprocess.STDOUT)
        report['reopenMainPid']=process.pid;report['reopenMainBirth']=wait(lambda:_process_started(process.pid),'reopened own Main birth',8);report['mainPid']=process.pid;report['mainBirth']=report['reopenMainBirth']
        url=wait(endpoint,'reopened Main inspector');wait(show,'reopened own app window')
        meta=wait(lambda:json.loads((fixture/'host-meta.json').read_text()) if (fixture/'host-meta.json').exists() else None,'reopened own Host identity')
        assert meta['parentPid']==process.pid;report['hostPid']=meta['pid'];report['hostBirth']=meta['birth']
        config=json.loads(ui_input.read_text(encoding='utf-8'));config.update(phase='reopen',port=wait(browser_port,'reopened renderer'),mainInspector=url,mainPid=process.pid,standardSessionId=report['ui']['sessions']['standard'],output=str(fixture/'reopen-ui-result.json'))
        ui_input.write_text(json.dumps(config),encoding='utf-8')
        check=run([shutil.which('node'),ROOT/'tools/tests/desktop-window-pin-ui-probe.mjs',ui_input],timeout=90)
        report['reopenUi']=json.loads((fixture/'reopen-ui-result.json').read_text(encoding='utf-8'))
        assert report['reopenUi']['ok'];oracle('quit');assert process.wait(timeout=30)==0;output.close();output=None
        report['sameProfileRestartConfirmedUninstalled']=True
    assert protocol()==baseline_protocol and {file:digest(Path(file)) for file in immutable}==immutable
    assert (requests>=1 if args.ui else requests==0),'Only the explicit UI history test may call the owned loopback model'
    report.update(ok=True,normalExitCode=0,officialDesktopAndProtocolUnchanged=True)
    print('PASS actual Native Desktop '+('Pin UI lifecycle' if args.ui else 'pin identity/topmost/geometry/focus/release/hidden restore/ambiguity')+':',fixture,flush=True)
except BaseException as error:
    report['error']=repr(error);raise
finally:
    if process and process.poll() is None:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
    if output:output.close()
    if not report.get('hostBirth') and (fixture/'host-meta.json').exists():
        try:meta=json.loads((fixture/'host-meta.json').read_text(encoding='utf-8'))
        except ValueError:meta={}
        if meta.get('parentPid')==report.get('mainPid') and meta.get('birth'):report['hostPid']=meta['pid'];report['hostBirth']=meta['birth']
    if report.get('hostBirth') and _process_started(report['hostPid'])==report['hostBirth']:
        subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/taskkill.exe'),'/PID',str(report['hostPid']),'/F'],capture_output=True,timeout=15)
    if server:server.shutdown();server.server_close()
    report['modelRequests']=requests
    (fixture/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Native pin evidence:',fixture,flush=True)
