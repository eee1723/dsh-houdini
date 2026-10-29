"""Actual Native Desktop plugin installation UI and tutorial credential consumer.

Only a new desktop profile/userData/cache/Documents tree is used. The package is
not installed by CLI. Chat inference uses owned loopback fixtures; the remote
tarball defaults to loopback or uses the explicit --remote-url HTTPS source.
No real credential, Houdini, npm publication or paid ASR is involved.
"""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.parse
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
parser.add_argument('--expected-sha256')
parser.add_argument('--remote-only',action='store_true',help='Directly validate the owned HTTP/UI lifecycle after a fixture-only change')
parser.add_argument('--local-only',action='store_true',help='Verify the actual local Native UI/Agent/credential path after a UI-only change')
parser.add_argument('--remote-url',help='Install this actual HTTPS tarball URL through the native remote UI stage')
parser.add_argument('--timeout',type=int,default=240)
args=parser.parse_args()
assert not (args.remote_only and args.local_only)
if args.remote_url:
    remote_source=urllib.parse.urlsplit(args.remote_url)
    if remote_source.scheme!='https' or not remote_source.hostname:
        parser.error('--remote-url requires a complete HTTPS URL')
    if args.local_only:parser.error('--remote-url requires a remote UI stage; remove --local-only')
artifact=args.artifact.resolve(strict=True)
desktop=args.desktop_root.resolve(strict=True)
electron=desktop/'DeepSeek Harness.exe'
fixture=Path(tempfile.mkdtemp(prefix='dsh-distribution-ui-'))
env={name.upper():value for name,value in isolated_environment(fixture,gui=True).items()}
for name,relative in {'APPDATA':'appdata','LOCALAPPDATA':'localappdata','TEMP':'temp','TMP':'temp',
        'npm_config_cache':'npm-cache','npm_config_store_dir':'store','PNPM_HOME':'package-manager','DSH_AGENTS_HOME':'agents'}.items():
    folder=fixture/relative;folder.mkdir(parents=True,exist_ok=True);env[name.upper()]=str(folder)
for name in ['npm_config_userconfig','npm_config_globalconfig']:
    file=fixture/(name+'.npmrc');file.write_text('',encoding='utf-8');env[name.upper()]=str(file)
env.update(DSH_HOME=str(fixture/'harness'),DSH_DESKTOP_OPEN_DEVTOOLS='0',
    DSH_DESKTOP_DIAGNOSTIC_FILE=str(fixture/'desktop-startup-error.txt'),
    DSH_DESKTOP_UPDATE_JOURNAL_DIR=str(fixture/'update-journal'),DSH_DIST_UI_CHAT_KEY='owned-loopback-chat-only')
home=Path(env['DSH_HOME']);profile=home/'profiles/desktop';user_data=fixture/'appdata/dsh-desktop'
sentinel='owned-native-asr-sentinel-not-a-real-key'
owned=[];process=None;output=None
server_facts={'chatRequests':0,'toolCalls':[],'tarballGets':0,'tarballTransfers':[],'asrRequests':0,'sentinelAbsentFromModel':True,'errors':[]}


def digest(file):
    with Path(file).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


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


def protocol_hash():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\dsh\UserChoice'):
            raise AssertionError('Refusing launch with a user-chosen dsh protocol handler')
    except FileNotFoundError:pass
    expected='"'+str(electron)+'" "%1"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Classes\dsh\shell\open\command') as key:
        assert winreg.QueryValueEx(key,'')[0]==expected,'Refusing launch without the same existing physical HKCU dsh registration'
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,r'dsh\shell\open\command') as key:
        assert winreg.QueryValueEx(key,'')[0]==expected,'Refusing launch with a different effective dsh handler'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Classes\dsh') as key:user=registry_tree(key)
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,'dsh') as key:effective=registry_tree(key)
    return hashlib.sha256(json.dumps({'user':user,'effective':effective},sort_keys=True).encode()).hexdigest()


def text_of(value):
    if isinstance(value,str):return value
    if isinstance(value,list):return '\n'.join(text_of(row) for row in value)
    if isinstance(value,dict):return str(value.get('text',''))
    return ''


class FixtureServer(http.server.BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def do_HEAD(self):
        if self.path=='/dsh-houdini.tgz':
            server_facts['tarballTransfers'].append({'method':'HEAD','protocol':self.protocol_version,'contentLength':copied.stat().st_size,
                'contentType':'application/octet-stream','connectionHeader':None,'closeConnection':self.close_connection,'writtenBytes':0,'completed':True})
            self.send_response(200);self.send_header('Content-Type','application/octet-stream')
            self.send_header('Content-Length',str(copied.stat().st_size));self.end_headers();return
        self.send_response(404);self.end_headers()
    def do_GET(self):
        if self.path=='/dsh-houdini.tgz':
            server_facts['tarballGets']+=1
            transfer={'method':'GET','protocol':self.protocol_version,'expectedBytes':copied.stat().st_size,'contentLength':copied.stat().st_size,
                'contentType':'application/octet-stream','connectionHeader':None,'closeConnection':self.close_connection,'writtenBytes':0,'completed':False}
            server_facts['tarballTransfers'].append(transfer);checksum=hashlib.sha256()
            self.send_response(200);self.send_header('Content-Type','application/octet-stream')
            self.send_header('Content-Length',str(copied.stat().st_size));self.end_headers()
            try:
                with copied.open('rb') as stream:
                    while chunk:=stream.read(128*1024):
                        self.wfile.write(chunk);transfer['writtenBytes']+=len(chunk);checksum.update(chunk)
                self.wfile.flush();transfer['completed']=transfer['writtenBytes']==transfer['expectedBytes']
                transfer['sha256']=checksum.hexdigest()
            except Exception as error:
                transfer['error']=repr(error);server_facts['errors'].append('tarball stream: '+repr(error))
            return
        self.send_response(404);self.end_headers()
    def do_POST(self):
        raw=self.rfile.read(int(self.headers.get('Content-Length','0')))
        try:
            assert sentinel.encode() not in raw,'ASR secret appeared in a model request'
            if self.path!='/v1/chat/completions':
                server_facts['asrRequests']+=1
                raise AssertionError('Configuration verification must not upload audio')
            assert self.headers.get('Authorization')=='Bearer owned-loopback-chat-only'
            body=json.loads(raw);server_facts['chatRequests']+=1
            tools={row['function']['name'] for row in body.get('tools',[]) if row.get('type')=='function'}
            messages=body['messages']
            users=[index for index,row in enumerate(messages) if row.get('role')=='user' and '请帮我配置教程视频分析' in text_of(row.get('content'))]
            after_tool=bool(users and any(row.get('role')=='tool' for row in messages[users[-1]+1:]))
            call=None
            if users and not after_tool and tools:
                name='video_configure' if len(users)==1 else 'video_models'
                values={'endpoint':asr_endpoint,'protocol':'openai-transcriptions','model':'owned-asr-id',
                        'authentication':'bearer','concurrency':2,'requests_per_second':1} if name=='video_configure' else {}
                if name in tools:call=(name,values)
                elif 'run_code' in tools:call=('run_code',{'code':'return await tools.'+name+'('+json.dumps(values)+');','description':'Read or configure the owned tutorial fixture'})
                else:raise AssertionError('Native Agent did not expose tutorial configuration or run_code')
                server_facts['toolCalls'].append({'name':name,'transport':call[0]})
            delta={'role':'assistant'}
            if call:delta['tool_calls']=[{'index':0,'id':'owned-ui-'+str(len(server_facts['toolCalls'])),'type':'function','function':{'name':call[0],'arguments':json.dumps(call[1])}}]
            else:delta['content']='教程视频配置已检查。请在教程视频状态页安全录入密钥；本次没有上传音频。'
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            for value in [{'id':'owned-chat','object':'chat.completion.chunk','model':'scripted-chat','choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                          {'id':'owned-chat','object':'chat.completion.chunk','model':'scripted-chat','choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if call else 'stop'}]}]:
                self.wfile.write(('data: '+json.dumps(value,ensure_ascii=False)+'\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
        except Exception as error:
            if isinstance(error,(BrokenPipeError,ConnectionResetError)):return
            server_facts['sentinelAbsentFromModel']=False if sentinel.encode() in raw else server_facts['sentinelAbsentFromModel']
            server_facts['errors'].append(str(error))
            try:self.send_response(500);self.end_headers()
            except OSError:pass


def run(command,**kwargs):
    result=subprocess.run([str(value) for value in command],cwd=fixture,env=env,capture_output=True,timeout=args.timeout+120,**kwargs)
    if result.returncode:raise AssertionError((result.stdout+result.stderr).decode('utf-8',errors='replace'))
    return result


def wait_until(read,seconds,label):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        value=read()
        if value:return value
        time.sleep(.2)
    raise AssertionError('Timed out: '+label)


def init_empty_profile():
    script=fixture/'init-profile.mjs'
    script.write_text("import {createRequire} from 'node:module';import {pathToFileURL} from 'node:url';"
        "const require=createRequire(process.argv[2]);const boot=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-app-boot')));"
        "boot.initProfile(process.argv[3],boot.PROFILE_TEMPLATES.web.bundles);",encoding='utf-8')
    env['ELECTRON_RUN_AS_NODE']='1'
    run([electron,script,desktop/'resources/app.asar/dsh/node_modules/@deepseek-ai/dsh/package.json',profile])
    env.pop('ELECTRON_RUN_AS_NODE',None)
    manifest=json.loads((profile/'package.json').read_text(encoding='utf-8'))
    assert 'dsh-houdini' not in manifest.get('dependencies',{})
    assert 'dsh-houdini' not in manifest.get('dsh',{}).get('profile',{}).get('bundles',[])
    patch=('- id: workspace-controller\n  config:\n    documentsDirectory: '+json.dumps(str(fixture/'documents'))+'\n'
        '- id: llm-pi-ai\n  config:\n    providers:\n      owned-distribution-chat:\n'
        '        api: openai-completions\n        baseURL: '+json.dumps(base+'/v1/')+'\n'
        '        apiKeyEnv: DSH_DIST_UI_CHAT_KEY\n        models:\n          - id: scripted-chat\n            input: [text]\n')
    (profile/'cordis.patch.yml').write_text(patch,encoding='utf-8')


def endpoints():
    def read():
        assert process.poll() is None,'Owned Native Desktop exited before UI readiness'
        diagnostic=fixture/'desktop-startup-error.txt'
        if diagnostic.exists():raise AssertionError(diagnostic.read_text(encoding='utf-8'))
        text=log.read_text(encoding='utf-8',errors='replace')
        main=re.search(r'Debugger listening on (ws://127\.0\.0\.1:\d+/[^\s]+)',text)
        file=user_data/'DevToolsActivePort'
        if main and file.exists():return {'mainInspector':main.group(1),'port':int(file.read_text().splitlines()[0])}
    return wait_until(read,args.timeout,'owned Native inspectors')


def capture_children():
    roots={pid:birth for pid,birth in owned if _process_started(pid)==birth}
    if not roots:return
    command='ConvertTo-Json -Compress -InputObject @(Get-CimInstance Win32_Process | ForEach-Object { @{pid=[int]$_.ProcessId;parent=[int]$_.ParentProcessId} })'
    value=run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command])
    pending=json.loads(value.stdout.decode('utf-8-sig'))
    while pending:
        added=False
        for row in list(pending):
            parent=roots.get(row['parent'])
            if not parent:continue
            pending.remove(row)
            birth=_process_started(row['pid'])
            if not birth or int(birth)<int(parent) or _process_started(row['parent'])!=parent:continue
            roots[row['pid']]=birth;added=True
            if (row['pid'],birth) not in owned:owned.append((row['pid'],birth))
        if not added:break


copied=fixture/'dsh-houdini.tgz';shutil.copy2(artifact,copied)
assert digest(copied)==digest(artifact)
if args.expected_sha256:assert digest(copied)==args.expected_sha256,'Frozen artifact SHA256 mismatch'
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),FixtureServer)
base='http://127.0.0.1:'+str(server.server_port);asr_endpoint=base+'/asr/audio/transcriptions'
remote_tarball=args.remote_url or base+'/dsh-houdini.tgz'
threading.Thread(target=server.serve_forever,daemon=True).start()
immutable={str(file):digest(file) for file in [electron,desktop/'resources/app.asar',desktop/'resources/runtime/versions.json']}
report={'fixture':str(fixture),'artifactSha256':digest(copied),'nativeElectronWindowTested':False,'nativeProfile':'desktop',
    'installedByNativeUi':False,'cliPluginInstallUsed':False,'chatModel':'owned scripted loopback provider',
    'remoteDistribution':'explicit HTTPS tarball installed by native UI' if args.remote_url else 'owned HTTP tarball mechanism only; no npm/GitHub publication claim',
    'remoteTarballUrl':remote_tarball,'immutable':immutable}
print('Owned Native distribution UI evidence:',fixture,flush=True)
try:
    baseline=protocol_hash();report['protocolSha256Before']=baseline
    report['ui']={}
    modes=['remote'] if args.remote_only else ['local'] if args.local_only else ['local','remote']
    report['testedStages']=modes
    for mode in modes:
        stage=fixture/mode;stage.mkdir()
        env['APPDATA']=str(stage/'appdata');Path(env['APPDATA']).mkdir()
        for name,relative in {'NPM_CONFIG_CACHE':'npm-cache','NPM_CONFIG_STORE_DIR':'store','PNPM_HOME':'package-manager'}.items():
            directory=stage/relative;directory.mkdir();env[name]=str(directory)
        env['DSH_HOME']=str(stage/'harness');home=Path(env['DSH_HOME']);profile=home/'profiles/desktop'
        user_data=Path(env['APPDATA'])/'dsh-desktop'
        init_empty_profile()
        log=stage/'desktop.log';output=log.open('wb')
        process=subprocess.Popen([str(electron),'--inspect=127.0.0.1:0','--remote-debugging-port=0','--user-data-dir='+str(user_data)],
            cwd=fixture,env=env,stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
        birth=_process_started(process.pid);assert birth;owned.append((process.pid,birth))
        endpoint=endpoints();capture_children()
        settings={'artifact':str(copied),'remoteTarball':remote_tarball,'asrEndpoint':asr_endpoint,'sentinel':sentinel,
            'remoteOnly':mode=='remote','expectedPid':process.pid,'timeoutMs':args.timeout*1000,'output':str(stage/'ui-result.json'),**endpoint}
        config=stage/'probe-input.json';config.write_text(json.dumps(settings),encoding='utf-8')
        result=subprocess.run([shutil.which('node'),str(ROOT/'tools/tests/desktop-install-ui-probe.mjs'),str(config)],
            cwd=fixture,env=env,capture_output=True,timeout=args.timeout*3)
        (stage/'probe.log').write_bytes(result.stdout+result.stderr)
        assert result.returncode==0,'Native '+mode+' distribution UI failed; inspect '+str(stage/'ui-result.json')
        report['ui'][mode]=json.loads((stage/'ui-result.json').read_text(encoding='utf-8'))
        if mode=='local':
            installed=(profile/'node_modules/dsh-houdini').resolve(strict=True)
            assert installed.is_relative_to(fixture) and not installed.is_relative_to(ROOT)
            hashes={}
            with tarfile.open(copied,'r:gz') as archive:
                for relative in ['client.js','lib/frontend-host.js','lib/video-configuration.js']:
                    expected=hashlib.sha256(archive.extractfile('package/'+relative).read()).hexdigest()
                    assert digest(installed/relative)==expected,'Native UI did not install the exact frozen bytes: '+relative
                    hashes[relative]=expected
            report['ui'][mode]['installedRoot']=str(installed)
            report['ui'][mode]['installedArtifactFilesSha256']=hashes
        capture_children()
        process.wait(timeout=30);assert process.returncode==0,'Owned Native normal quit did not complete'
        output.close();output=None
        report['ui'][mode]['normalExitCode']=process.returncode
        print('PASS Native '+mode+' UI stage',flush=True)
    report['nativeElectronWindowTested']=True;report['installedByNativeUi']=True
    assert server_facts['asrRequests']==0 and not server_facts['errors'],server_facts
    if not args.local_only and not args.remote_url:assert server_facts['tarballGets']>0,server_facts
    assert server_facts['sentinelAbsentFromModel'],server_facts
    if not args.remote_only:assert server_facts['chatRequests']==0 and not server_facts['toolCalls'],server_facts
    assert protocol_hash()==baseline and {file:digest(file) for file in immutable}==immutable
    report.update(ok=True,normalExitCode=process.returncode,loopback=server_facts,desktopInstallationAndProtocolUnchanged=True)
    remote_label='HTTPS' if args.remote_url else 'HTTP'
    print(('PASS Native local tarball UI + real Agent/credentials' if args.local_only else 'PASS Native '+remote_label+' tarball UI install/disable/re-enable/uninstall' if args.remote_only else
        'PASS Native UI local tgz + real tutorial Agent/credentials + '+remote_label+' distribution/lifecycle')+': '+str(fixture),flush=True)
except BaseException as error:
    report['error']=repr(error);raise
finally:
    if owned:
        try:capture_children()
        except Exception as error:report['childCaptureError']=repr(error)
    for pid,birth in reversed(owned):
        if _process_started(pid)==birth:
            subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/taskkill.exe'),'/PID',str(pid),'/F'],cwd=fixture,env=env,capture_output=True,timeout=15)
    if output:output.close()
    server.shutdown();server.server_close()
    report['loopback']=server_facts
    report['ownedProcessIdentitiesStopped']=all(_process_started(pid)!=birth for pid,birth in owned)
    if 'protocolSha256Before' in report:
        try:
            report['protocolUnchangedAfterCleanup']=protocol_hash()==baseline
            report['desktopInstallationUnchangedAfterCleanup']={file:digest(file) for file in immutable}==immutable
        except Exception as error:report['isolationVerificationError']=repr(error);report['ok']=False
    (fixture/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert 'isolationVerificationError' not in report,report.get('isolationVerificationError')
