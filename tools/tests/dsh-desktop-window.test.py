"""Owned native Electron window/profile; optionally prove an owned Houdini survives normal quit/reopen.

Never invokes the system dsh: protocol. A native packaged app registers that protocol
at startup, so the test refuses to start unless its effective handler is already the
exact installed binary/command. The public Workspace documentsDirectory setting
keeps first-use default workspace creation inside the fixture as well.
"""
import argparse
import base64
import hashlib
import http.server
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import winreg

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from houdini_test_environment import isolated_environment,reexec_unpacked_test_cli
reexec_unpacked_test_cli()
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
from dsh_deployment import _process_started

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--artifact',required=True,type=Path)
parser.add_argument('--desktop-root',type=Path,default=Path('D:/dshdesktop'))
parser.add_argument('--lifetime-hfs',type=Path,help='Explicit installation for an empty disposable real GUI scene')
parser.add_argument('--pending-launch',action='store_true',help='Test-only native pythonrc barrier: quit before first Bridge admission')
parser.add_argument('--expected-integrity',help='Expected frozen package sha512 integrity')
parser.add_argument('--timeout',type=int,default=180)
parser.add_argument('--second-quit-timeout',type=int,default=20,help='Optional ready-state quit observation; does not replace required pending quit')
args=parser.parse_args()
assert not args.pending_launch or args.lifetime_hfs,'--pending-launch requires --lifetime-hfs'
artifact=args.artifact.resolve(strict=True)
desktop=args.desktop_root.resolve(strict=True)
electron=desktop/'DeepSeek Harness.exe'
cli=desktop/'resources/runtime/cli/bin/dsh.cmd'
fixture=Path(tempfile.mkdtemp(prefix='dsh-desktop-window-'))
env=isolated_environment(fixture,gui=True)
for name,relative in {'APPDATA':'appdata','LOCALAPPDATA':'localappdata','TEMP':'temp','TMP':'temp',
        'npm_config_cache':'npm-cache','npm_config_store_dir':'store','PNPM_HOME':'package-manager',
        'DSH_AGENTS_HOME':'agents'}.items():
    target=fixture/relative;target.mkdir(parents=True,exist_ok=True);env[name]=str(target)
for name in ['npm_config_userconfig','npm_config_globalconfig']:
    target=fixture/(name+'.npmrc');target.write_text('',encoding='utf-8');env[name]=str(target)
env['DSH_HOME']=str(fixture/'harness')
env['DSH_DESKTOP_OPEN_DEVTOOLS']='0'
env['DSH_DESKTOP_DIAGNOSTIC_FILE']=str(fixture/'desktop-startup-error.txt')
env['DSH_DESKTOP_UPDATE_JOURNAL_DIR']=str(fixture/'update-journal')
env['DSH_NATIVE_LIFETIME_CHAT_KEY']='owned-lifetime-chat-only'
home=Path(env['DSH_HOME'])
profile=home/'profiles/desktop'
user_data=fixture/'appdata/dsh-desktop'
state_file=fixture/'lifetime-state.json'
barrier_release=fixture/'startup-release'
barrier_blocked=fixture/'startup-blocked'
if args.pending_launch:
    startup=fixture/'owned-startup-barrier'
    source=('import os as _dsh_test_os, time as _dsh_test_time\nfrom pathlib import Path as _DshTestPath\n'
        '_dsh_test_blocked=_DshTestPath('+repr(str(barrier_blocked))+')\n'
        '_dsh_test_release=_DshTestPath('+repr(str(barrier_release))+')\n'
        '_dsh_test_blocked.write_text(str(_dsh_test_os.getpid()),encoding="ascii")\n'
        '_dsh_test_end=_dsh_test_time.monotonic()+180\n'
        'while not _dsh_test_release.exists() and _dsh_test_time.monotonic()<_dsh_test_end:\n    _dsh_test_time.sleep(.05)\n')
    for version in ['3.11','3.13']:
        directory=startup/('python'+version+'libs');directory.mkdir(parents=True)
        (directory/'pythonrc.py').write_text(source,encoding='utf-8')
    env['HOUDINI_PATH']=str(startup)+os.pathsep+'&'
node=shutil.which('node');assert node
print('Owned native Desktop evidence:',fixture,flush=True)
chat=None;chat_requests=0


class FixtureChat(http.server.BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def do_POST(self):
        global chat_requests
        self.rfile.read(int(self.headers.get('Content-Length','0')));chat_requests+=1
        chunks=[{'id':'owned-lifetime','object':'chat.completion.chunk','model':'idle-fixture',
            'choices':[{'index':0,'delta':{'role':'assistant','content':'Owned lifetime fixture.'},'finish_reason':None}]},
            {'id':'owned-lifetime','object':'chat.completion.chunk','model':'idle-fixture','choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}]
        body=(''.join('data: '+json.dumps(row)+'\n\n' for row in chunks)+'data: [DONE]\n\n').encode()
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass


def digest(file):
    with file.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def registry_tree(key):
    values={};children={};index=0
    while True:
        try:name,value,kind=winreg.EnumValue(key,index)
        except OSError:break
        values[name]=[kind,value];index+=1
    index=0
    while True:
        try:name=winreg.EnumKey(key,index)
        except OSError:break
        with winreg.OpenKey(key,name) as child:children[name]=registry_tree(child)
        index+=1
    return {'values':values,'children':children}


def protocol_baseline():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\dsh\UserChoice') as key:
            choice=winreg.QueryValueEx(key,'ProgId')[0]
    except FileNotFoundError:choice=None
    assert choice is None,'Refusing native launch with a user-chosen dsh protocol handler'
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,r'dsh\shell\open\command') as key:command=winreg.QueryValueEx(key,'')[0]
    assert command=='"'+str(electron)+'" "%1"','Refusing to alter a different dsh protocol registration'
    # HKCR alone could hide a newly created HKCU override of an identical HKLM
    # handler. Require an existing physical per-user registration as well.
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Classes\dsh\shell\open\command') as key:user_command=winreg.QueryValueEx(key,'')[0]
    assert user_command==command,'Refusing native launch without the same existing per-user dsh command'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Classes\dsh') as key:user_tree=registry_tree(key)
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,'dsh') as key:effective_tree=registry_tree(key)
    return hashlib.sha256(json.dumps({'user':user_tree,'effective':effective_tree},sort_keys=True).encode()).hexdigest()


def run(command,**kwargs):
    result=subprocess.run([str(value) for value in command],cwd=fixture,env=env,capture_output=True,timeout=args.timeout+120,**kwargs)
    if result.returncode:raise AssertionError((result.stdout+result.stderr).decode('utf-8',errors='replace'))
    return result


def wait_until(read,timeout,label):
    deadline=time.monotonic()+timeout
    while True:
        value=read()
        if value is not None:return value
        assert time.monotonic()<deadline,'Timed out: '+label
        time.sleep(.2)


def start_desktop():
    (user_data/'DevToolsActivePort').unlink(missing_ok=True)
    log=fixture/('desktop-'+str(time.time_ns())+'.log');output=log.open('wb')
    process=subprocess.Popen([str(electron),'--inspect=127.0.0.1:0','--remote-debugging-port=0','--user-data-dir='+str(user_data)],cwd=fixture,env=env,
        stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
    owner_file=fixture/'desktop-owner-identities.json'
    owners=json.loads(owner_file.read_text(encoding='utf-8')) if owner_file.exists() else []
    owners.append({'pid':process.pid,'processStarted':wait_until(lambda:_process_started(process.pid),5,'owned native process birth'),
        'userData':str(user_data),'log':str(log)})
    owner_file.write_text(json.dumps(owners,indent=2),encoding='utf-8')
    return process,output,log


def debugging_endpoints(process,log):
    def read():
        assert process.poll() is None,'Owned Electron exited; inspect its fixture log'
        if (fixture/'desktop-startup-error.txt').exists():raise AssertionError((fixture/'desktop-startup-error.txt').read_text(encoding='utf-8'))
        text=log.read_text(encoding='utf-8',errors='replace')
        browser=re.search(r'DevTools listening on ws://127\.0\.0\.1:(\d+)/',text)
        main=re.search(r'Debugger listening on (ws://127\.0\.0\.1:\d+/[^\s]+)',text)
        port_file=user_data/'DevToolsActivePort'
        port=int(port_file.read_text().splitlines()[0]) if port_file.exists() else int(browser.group(1)) if browser else None
        if port and main:return {'port':port,'mainInspector':main.group(1)}
    return wait_until(read,args.timeout,'owned native Electron browser and main inspectors')


def install_plugin():
    init=fixture/'init-profile.mjs'
    init.write_text("import {createRequire} from 'node:module';import {pathToFileURL} from 'node:url';"
        "const require=createRequire(process.argv[2]);const boot=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-app-boot')));"
        "boot.initProfile(process.argv[3],boot.PROFILE_TEMPLATES.web.bundles);",encoding='utf-8')
    env['ELECTRON_RUN_AS_NODE']='1'
    anchor=desktop/'resources/app.asar/dsh/node_modules/@deepseek-ai/dsh/package.json'
    run([electron,init,anchor,profile])
    # Public first-use directory policy, only in this owned profile.
    (profile/'cordis.patch.yml').write_text('- id: workspace-controller\n  config:\n    documentsDirectory: '+json.dumps(str(fixture/'documents'))+'\n'
        '- id: llm-pi-ai\n  config:\n    providers:\n      owned-lifetime-chat:\n'
        '        api: openai-completions\n        baseURL: '+json.dumps('http://127.0.0.1:'+str(chat.server_port)+'/v1/')+'\n'
        '        apiKeyEnv: DSH_NATIVE_LIFETIME_CHAT_KEY\n        models:\n          - id: idle-fixture\n            input: [text]\n',encoding='utf-8')
    command=[os.environ.get('COMSPEC','C:/Windows/System32/cmd.exe'),'/d','/s','/c',
        subprocess.list2cmdline([str(cli),'plugin','--profile','desktop','add',str(artifact),'--store-dir',str(fixture/'store')])]
    result=run(command);(fixture/'plugin-install.log').write_bytes(result.stdout+result.stderr)
    manifest=json.loads((profile/'package.json').read_text(encoding='utf-8'))
    assert 'dsh-houdini' in manifest['dependencies'] and 'dsh-houdini' in manifest['dsh']['profile']['bundles'],manifest
    env.pop('ELECTRON_RUN_AS_NODE',None)


def probe(phase,**extra):
    config={'phase':phase,'output':str(fixture/(phase+'-result.json')),'stateFile':str(state_file),
            'conversation':str(fixture/'conversation'),'lifetimeHfs':str(args.lifetime_hfs.resolve(strict=True)) if args.lifetime_hfs else None,
            'timeoutMs':args.timeout*1000,'pendingLaunch':args.pending_launch,'barrierRelease':str(barrier_release),
            'launchesRoot':str(home/'dsh-houdini/launches'),**extra}
    file=fixture/(phase+'-input.json');file.write_text(json.dumps(config),encoding='utf-8')
    result=subprocess.run([node,str(ROOT/'tools/tests/desktop-window-probe.mjs'),str(file)],cwd=fixture,env=env,capture_output=True,timeout=args.timeout+90)
    (fixture/(phase+'-probe.log')).write_bytes(result.stdout+result.stderr)
    assert result.returncode==0,'Native '+phase+' probe failed; inspect '+phase+'-result.json'
    return json.loads(Path(config['output']).read_text(encoding='utf-8'))


def normal_quit(process,endpoint,timeout=None):
    result=probe('quit',mainInspector=endpoint['mainInspector'],expectedPid=process.pid)
    print('Native app.quit requested; only this owned PID/window may be confirmed: '+json.dumps(result['ownedMainWindows']),flush=True)
    owners=json.loads((fixture/'desktop-owner-identities.json').read_text(encoding='utf-8'))
    owner=next(row for row in owners if row['pid']==process.pid)
    observation={'pid':process.pid,'processStarted':owner['processStarted'],'ownedMainWindows':result['ownedMainWindows'],
        'status':'awaiting-native-exit','timeout':args.timeout if timeout is None else timeout}
    deadline=time.monotonic()+observation['timeout']
    while process.poll() is None:
        observation.update(liveFromOwnedPopenHandle=True,asOfUnixMs=time.time_ns()//1_000_000)
        (fixture/'quit-observation.json').write_text(json.dumps(observation,indent=2),encoding='utf-8')
        if time.monotonic()>=deadline:raise subprocess.TimeoutExpired(process.args,observation['timeout'])
        time.sleep(.5)
    code=process.poll()
    observation.update(status='exited',exitCode=code,liveFromOwnedPopenHandle=False,asOfUnixMs=time.time_ns()//1_000_000)
    (fixture/'quit-observation.json').write_text(json.dumps(observation,indent=2),encoding='utf-8')
    assert code==0,('Native app.quit failed',code)
    descriptor=home/'dsh-houdini/desktop.json'
    wait_until(lambda:True if not descriptor.exists() else None,10,'owned Desktop service descriptor release')


def host_identity():
    value=json.loads((home/'dsh-houdini/desktop.json').read_text(encoding='utf-8'))
    birth=_process_started(value['pid']);assert birth
    return {'pid':value['pid'],'processStarted':birth,'generation':value['generation']}


def owned_houdini_pids(hosts):
    # Exact parent carriers from this fixture, no foreign HFS/session inference.
    parents=','.join(str(host['pid']) for host in hosts)
    script="$parents=@("+parents+"); @{pids=@(Get-CimInstance Win32_Process -Filter \"Name='houdini.exe' OR Name='hython.exe'\" | Where-Object { $_.ParentProcessId -in $parents } | ForEach-Object { [int]$_.ProcessId })} | ConvertTo-Json -Compress"
    result=run([Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe','-NoProfile','-NonInteractive','-Command',script])
    return sorted(json.loads(result.stdout.decode('utf-8-sig').strip())['pids'])


immutable={str(file):digest(file) for file in [electron,desktop/'resources/app.asar',desktop/'resources/runtime/versions.json']}
report={'fixture':str(fixture),'artifact':str(artifact),'artifactSha256':digest(artifact),'nativeElectronWindowTested':False,
        'externalDesktopActivationStubbed':False,'nativeProfile':'desktop','fixtureDocumentsOverride':True,
        'isolatedDshHome':str(home),'isolatedUserData':str(user_data),'desktopInstallationSha256':immutable,
        'pendingLaunchWithOwnedStartupBarrier':args.pending_launch}
process=None;output=None
try:
    before_protocol=protocol_baseline()
    report['protocolSha256Before']=before_protocol
    with artifact.open('rb') as stream:report['artifactIntegrity']='sha512-'+base64.b64encode(hashlib.file_digest(stream,'sha512').digest()).decode('ascii')
    if args.expected_integrity:assert report['artifactIntegrity']==args.expected_integrity,'Frozen artifact integrity mismatch'
    chat=http.server.ThreadingHTTPServer(('127.0.0.1',0),FixtureChat)
    threading.Thread(target=chat.serve_forever,daemon=True).start()
    report['nativeModelSetup']='Owned public profile configuration + scripted loopback chat; real account/onboarding is not tested'
    install_plugin();(fixture/'conversation').mkdir()
    process,output,log=start_desktop();endpoint=debugging_endpoints(process,log)
    initial=probe('initial',expectedPid=process.pid,**endpoint);report['nativeElectronWindowTested']=True;report['initial']=initial
    report['firstHost']=host_identity()
    report['firstDesktopPid']=process.pid
    report['firstDesktopProcessStarted']=_process_started(process.pid)
    assert report['firstDesktopProcessStarted']
    if args.pending_launch:
        state=json.loads(state_file.read_text(encoding='utf-8'))
        wait_until(lambda:True if barrier_blocked.exists() else None,args.timeout,'owned Houdini startup barrier')
        assert int(barrier_blocked.read_text())==state['record']['pid']
        ticket_path=home/'dsh-houdini/launches'/(state['ticketId']+'.json')
        assert json.loads(ticket_path.read_text(encoding='utf-8'))['phase']=='waiting','Launch completed before native quit'
        report['houdiniBirthBeforeFirstQuit']=_process_started(state['record']['pid'])
        assert report['houdiniBirthBeforeFirstQuit']==state['record']['processStarted'],'Initial Houdini birth must match the issued ticket before quit'
        report['pendingBeforeQuit']=True
        print('Owned Houdini PID/birth reached native startup barrier; original ticket is waiting. Requesting native app.quit.',flush=True)
    normal_quit(process,endpoint);output.close();output=None
    assert _process_started(report['firstHost']['pid'])!=report['firstHost']['processStarted'],'Old native Host still alive after app.quit'
    report['firstDesktopQuitNormally']=True
    if args.lifetime_hfs:
        state=json.loads(state_file.read_text(encoding='utf-8'))
        report['houdiniBirthAfterFirstQuit']=_process_started(state['record']['pid'])
        assert report['houdiniBirthAfterFirstQuit']==state['record']['processStarted'],'Original Houdini died when native Desktop quit'
        if args.pending_launch:
            persisted=json.loads(ticket_path.read_text(encoding='utf-8'))
            assert persisted['phase']=='waiting' and persisted['pid']==state['record']['pid'] and persisted['processStarted']==state['record']['processStarted']
            report['pendingAfterOldHostQuit']=True
        else:report['afterFirstQuit']=probe('health')
        report['houdiniSurvivedNormalDesktopQuit']=True
        print('Native Desktop/old Host exited normally; same Houdini OS birth remains alive. Reopening same fixture.',flush=True)
        process,output,log=start_desktop();endpoint=debugging_endpoints(process,log)
        report['secondDesktopPid']=process.pid
        report['secondDesktopProcessStarted']=_process_started(process.pid)
        assert report['secondDesktopProcessStarted'] and (report['secondDesktopPid'],report['secondDesktopProcessStarted'])!=(report['firstDesktopPid'],report['firstDesktopProcessStarted'])
        report['reopen']=probe('reopen',expectedPid=process.pid,**endpoint)
        report['secondHost']=host_identity()
        assert report['secondHost']['generation']!=report['firstHost']['generation']
        state=json.loads(state_file.read_text(encoding='utf-8'))
        assert _process_started(state['record']['pid'])==state['record']['processStarted']
        report['ownedHoudiniPidsAfterReopen']=owned_houdini_pids([report['firstHost'],report['secondHost']])
        assert report['ownedHoudiniPidsAfterReopen']==[state['record']['pid']],'Additional Houdini/hython process was spawned by fixture carriers'
        assert sorted(file.stem for file in (home/'dsh-houdini/launches').glob('*.json'))==[state['ticketId']]
        report['corePendingResumePassed']=bool(args.pending_launch and report['pendingAfterOldHostQuit'] and report['reopen']['sameNativeSessionAndHoudini'])
        try:
            normal_quit(process,endpoint,timeout=args.second_quit_timeout);output.close();output=None
            assert _process_started(report['secondHost']['pid'])!=report['secondHost']['processStarted']
            report['afterSecondQuit']=probe('health');report['houdiniSurvivedSecondNormalQuit']=True
            report['secondQuitObservation']={'normalExitVerified':True,'exitCode':0}
        except Exception as error:
            report['secondQuitObservation']={'normalExitVerified':False,'error':repr(error),
                'inspectionOrNativeDialogReached':'Not observed; no quit-requested event alone cannot distinguish them.',
                'cleanup':'Only owned fixture processes will be terminated in finally; that is not a normal exit.'}
            print('Core resume passed; optional second normal quit was not completed. It will be recorded separately from exact fixture cleanup.',flush=True)
    assert protocol_baseline()==before_protocol,'Global dsh protocol values changed'
    assert {file:digest(Path(file)) for file in immutable}==immutable,'Official Desktop installation changed'
    report['desktopInstallationAndProtocolUnchanged']=True
    report['ok']=True
    print('PASS required native desktop assertions'+(' including original pending launch/session/process recovery' if args.pending_launch else '')+': '+str(fixture),flush=True)
except BaseException as error:
    report['error']=repr(error)
    raise
finally:
    barrier_release.write_text('release during owned test cleanup\n',encoding='utf-8')
    if process and process.poll() is None:
        process.terminate()
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
    if output:output.close()
    if chat:chat.shutdown();chat.server_close()
    report['fixtureChatRequests']=chat_requests
    # Only this new empty fixture Houdini, with the exact observed OS birth identity.
    # A partial launch can have its own PID before it reaches the ready callback.
    records=[]
    if state_file.exists():
        state=json.loads(state_file.read_text(encoding='utf-8'));records.append(state['record'])
    else:
        for ticket in (home/'dsh-houdini/launches').glob('*.json'):
            record=json.loads(ticket.read_text(encoding='utf-8'))
            if record.get('pid') and record.get('processStarted'):records.append(record)
    for record in records:
        if _process_started(record['pid'])==record['processStarted']:
            taskkill=Path(os.environ['SystemRoot'])/'System32/taskkill.exe'
            cleanup=subprocess.run([str(taskkill),'/PID',str(record['pid']),'/F'],cwd=fixture,env=env,capture_output=True,timeout=15)
            (fixture/'owned-houdini-cleanup.log').write_bytes(cleanup.stdout+cleanup.stderr)
    report['lastDesktopExitCode']=process.poll() if process else None
    if 'protocolSha256Before' in report:
        try:
            report['protocolUnchangedAfterCleanup']=protocol_baseline()==before_protocol
            report['desktopInstallationUnchangedAfterCleanup']={file:digest(Path(file)) for file in immutable}==immutable
        except Exception as error:report['isolationVerificationError']=repr(error)
    (fixture/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
