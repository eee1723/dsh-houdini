"""Actual Native Desktop plugin installation UI and tutorial credential consumer.

Only a new desktop profile/userData/cache/Documents tree is used. Ordinary
installation uses the native UI; source migration explicitly uses the official
CLI while that owned Desktop is closed, then the real native update button.
Chat inference uses owned loopback fixtures; distribution sources are explicit.
No real credential, Houdini, package publication or paid ASR is involved.
"""
import argparse
import base64
import hashlib
import http.server
import io
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
import urllib.request
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
parser.add_argument('--unpacked-app',type=Path,help='Unmodified official app extracted for development-carrier UI checks; excludes packaged protocol/update qualification')
parser.add_argument('--electron-carrier',type=Path,help='Official Electron copy with default_app.asar and no app.asar; requires --unpacked-app')
parser.add_argument('--update-from',type=Path,help='Actual public 0.1.6 tgz seeded disabled by the previous official CLI, then updated through the real native update button')
parser.add_argument('--previous-desktop-root',type=Path,default=Path('D:/dshdesktop'))
parser.add_argument('--migration-from',type=Path,help='Frozen compatible package seeded from a URL/file, migrated by the current official CLI at the same version, then updated by the native button to --artifact')
parser.add_argument('--migration-source',type=str.lower,choices=['url','file'],help='Original dependency source for --migration-from')
parser.add_argument('--migration-url',help='Actual HTTPS source tarball for a public-registry migration; absent with the owned loopback registry uses its exact frozen bytes')
parser.add_argument('--migration-cli-only',action='store_true',help='Probe same-version URL/file to registry migration with the official CLI, without starting a GUI or claiming session/UI validation')
parser.add_argument('--output-dir',type=Path,help='New evidence subdirectory allocated by the output manager; otherwise use a fresh temporary directory')
parser.add_argument('--expected-sha256')
parser.add_argument('--remote-only',action='store_true',help='Directly validate the owned HTTP/UI lifecycle after a fixture-only change')
parser.add_argument('--local-only',action='store_true',help='Verify the actual local Native UI/Agent/credential path after a UI-only change')
parser.add_argument('--remote-url',help='Install this actual HTTPS tarball URL through the native remote UI stage')
parser.add_argument('--npm',action='store_true',help='Install the frozen artifact name@version through the native package-name UI')
parser.add_argument('--registry',help='Use only this registry in the owned profile (requires --npm)')
parser.add_argument('--timeout',type=int,default=240)
args=parser.parse_args()
assert not (args.remote_only and args.local_only)
if args.update_from and (not args.unpacked_app or args.remote_only or args.local_only or args.npm or args.remote_url or args.registry or args.migration_from):
    parser.error('--update-from requires the unpacked carrier and its owned registry stage only')
if args.migration_from:
    if not args.migration_source or args.remote_only or args.local_only or args.npm or args.remote_url or args.update_from:
        parser.error('--migration-from requires --migration-source url|file and its dedicated migration stages')
    if args.registry and args.migration_source=='url' and not args.migration_url:
        parser.error('A public-registry URL migration requires the actual --migration-url; no loopback source may stand in for public HTTPS')
elif args.migration_source or args.migration_url or args.migration_cli_only:
    parser.error('Migration options require --migration-from')
if args.npm and (not args.remote_only or args.remote_url):
    parser.error('--npm requires --remote-only and cannot use --remote-url')
if args.registry:
    registry_source=urllib.parse.urlsplit(args.registry)
    if not (args.npm or args.migration_from) or registry_source.scheme!='https' or not registry_source.hostname:
        parser.error('--registry requires --npm or --migration-from and a complete HTTPS registry URL')
if args.migration_url:
    migration_url=urllib.parse.urlsplit(args.migration_url)
    if args.migration_source!='url' or migration_url.scheme!='https' or not migration_url.hostname:
        parser.error('--migration-url requires --migration-source url and a complete HTTPS tarball URL')
if args.remote_url:
    remote_source=urllib.parse.urlsplit(args.remote_url)
    if remote_source.scheme!='https' or not remote_source.hostname:
        parser.error('--remote-url requires a complete HTTPS URL')
    if args.local_only:parser.error('--remote-url requires a remote UI stage; remove --local-only')
artifact=args.artifact.resolve(strict=True)
with tarfile.open(artifact,'r:gz') as archive:
    package=json.load(archive.extractfile('package/package.json'))
npm_spec=package['name']+'@'+package['version'] if args.npm else None
previous_artifact=args.update_from.resolve(strict=True) if args.update_from else None
migration_artifact=args.migration_from.resolve(strict=True) if args.migration_from else None
if migration_artifact:
    with tarfile.open(migration_artifact,'r:gz') as archive:migration_package=json.load(archive.extractfile('package/package.json'))
    assert migration_package['name']==package['name']=='dsh-houdini'
    if not args.migration_cli_only:
        def stable_version(value):
            assert re.fullmatch(r'\d+\.\d+\.\d+',value),'Use genuine stable frozen releases for the migration/update path'
            return tuple(map(int,value.split('.')))
        assert stable_version(package['version'])>stable_version(migration_package['version']),'The actual native update needs a strictly newer frozen release'
if previous_artifact:
    with tarfile.open(previous_artifact,'r:gz') as archive:previous_package=json.load(archive.extractfile('package/package.json'))
    assert previous_package['name']==package['name']=='dsh-houdini' and previous_package['version']=='0.1.6'
    with previous_artifact.open('rb') as stream:
        previous_integrity='sha512-'+base64.b64encode(hashlib.file_digest(stream,'sha512').digest()).decode()
    assert previous_integrity=='sha512-d2BJMGCZEM6k+c8d4xJVdLeCNXj2zRNJ4+b+LjQF3CLnl90mtQkuCJAI8/Yy13fw8SDLH9SqNRegsIVmxVgLsQ==', (
        'Use the actual public npm 0.1.6 bytes, not a same-version local build')
desktop=args.desktop_root.resolve(strict=True)
electron=desktop/'DeepSeek Harness.exe'
unpacked=args.unpacked_app.resolve(strict=True) if args.unpacked_app else None
if bool(unpacked)!=bool(args.electron_carrier):parser.error('--unpacked-app and --electron-carrier must be supplied together')
carrier=args.electron_carrier.resolve(strict=True) if unpacked else electron
if unpacked:
    assert carrier.is_file() and (unpacked/'lib/main.js').is_file()
    # Electron's native Windows isPackaged getter is based on this basename,
    # not on whether app.asar exists. A renamed official application registers
    # dsh:// before a post-launch inspector could reject the wrong mode.
    assert carrier.name.lower()=='electron.exe','Unpacked tests require an Electron-named development carrier'
    assert not (carrier.parent/'resources/app.asar').exists(),'Development carrier must not boot a packaged app'
    assert (carrier.parent/'resources/default_app.asar').is_file()
app_package=unpacked/'package.json' if unpacked else desktop/'resources/app.asar/package.json'
dsh_package=unpacked/'dsh/node_modules/@deepseek-ai/dsh/package.json' if unpacked else desktop/'resources/app.asar/dsh/node_modules/@deepseek-ai/dsh/package.json'
fixture=args.output_dir.resolve() if args.output_dir else Path(tempfile.mkdtemp(prefix='dsh-distribution-ui-'))
if args.output_dir:fixture.mkdir(parents=True,exist_ok=False)
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
if unpacked:
    env.pop('ELECTRON_FORCE_IS_PACKAGED',None);env.pop('DSH_DESKTOP_DEV_APP',None)
    env.update(DSH_DESKTOP_DSH_DIR=str(unpacked/'dsh'),
        DSH_DESKTOP_PNPM_ENTRY=str(desktop/'resources/runtime/primary-runtime/dependencies/pnpm/bin/pnpm.mjs'),
        DSH_DESKTOP_PRIMARY_RUNTIME_DIR=str(desktop/'resources/runtime/primary-runtime'))
sentinel='owned-native-asr-sentinel-not-a-real-key'
owned=[];process=None;output=None
server_facts={'chatRequests':0,'toolCalls':[],'tarballGets':0,'tarballTransfers':[],'asrRequests':0,'sentinelAbsentFromModel':True,'errors':[]}
server_facts['registryRequests']=[]


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
    def tree(root,path):
        try:
            with winreg.OpenKey(root,path) as key:return registry_tree(key)
        except FileNotFoundError:return None
    choice=tree(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\dsh\UserChoice')
    user=tree(winreg.HKEY_CURRENT_USER,r'Software\Classes\dsh')
    effective=tree(winreg.HKEY_CLASSES_ROOT,'dsh')
    if not unpacked and not args.migration_cli_only:
        assert choice is None,'Refusing packaged launch with a user-chosen dsh protocol handler'
        expected='"'+str(electron)+'" "%1"'
        for root,path in [(winreg.HKEY_CURRENT_USER,r'Software\Classes\dsh\shell\open\command'),(winreg.HKEY_CLASSES_ROOT,r'dsh\shell\open\command')]:
            with winreg.OpenKey(root,path) as key:
                assert winreg.QueryValueEx(key,'')[0]==expected,'Refusing packaged launch with a different dsh handler'
    snapshot={'user':user,'effective':effective,'choice':choice}
    (fixture/'protocol-current.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
    return hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()


def text_of(value):
    if isinstance(value,str):return value
    if isinstance(value,list):return '\n'.join(text_of(row) for row in value)
    if isinstance(value,dict):return str(value.get('text',''))
    return ''


class FixtureServer(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*_):pass
    def do_HEAD(self):
        route=urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if route in registry_files:
            file=registry_files[route]
            self.send_response(200);self.send_header('Content-Type','application/octet-stream')
            self.send_header('Content-Length',str(file.stat().st_size));self.end_headers();return
        if self.path=='/dsh-houdini.tgz':
            server_facts['tarballTransfers'].append({'method':'HEAD','protocol':self.protocol_version,'contentLength':copied.stat().st_size,
                'contentType':'application/octet-stream','connectionHeader':None,'closeConnection':self.close_connection,'writtenBytes':0,'completed':True})
            self.send_response(200);self.send_header('Content-Type','application/octet-stream')
            self.send_header('Content-Length',str(copied.stat().st_size));self.end_headers();return
        self.send_response(404);self.send_header('Content-Length','0');self.end_headers()
    def do_GET(self):
        if previous_artifact or migration_artifact:
            route=urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
            server_facts['registryRequests'].append(route)
            if route in registry_files:
                file=registry_files[route]
                self.send_response(200);self.send_header('Content-Type','application/octet-stream')
                self.send_header('Content-Length',str(file.stat().st_size));self.end_headers()
                try:
                    with file.open('rb') as stream:shutil.copyfileobj(stream,self.wfile,128*1024)
                except (BrokenPipeError,ConnectionResetError):pass
                return
            if route=='/dsh-houdini' or route.startswith('/dsh-houdini/'):
                document=registry_document
                if route!='/dsh-houdini':document=registry_document['versions'].get(route.split('/')[-1])
                if document is None:self.send_response(404);self.send_header('Content-Length','0');self.end_headers();return
                data=json.dumps(document).encode();self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            # Public dependency metadata only; never forward local credentials,
            # arbitrary origins, or file paths from a request.
            try:
                target='https://registry.npmjs.org'+self.path
                with urllib.request.urlopen(target,timeout=60) as upstream:data=upstream.read()
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception as error:
                self.send_response(502);self.send_header('Content-Length','0');self.end_headers();server_facts['errors'].append('owned registry dependency: '+str(error))
            return
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
        self.send_response(404);self.send_header('Content-Length','0');self.end_headers()
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
    seed_desktop=args.previous_desktop_root.resolve(strict=True) if previous_artifact else desktop
    seed_electron=seed_desktop/'DeepSeek Harness.exe'
    seed_package=seed_desktop/'resources/app.asar/dsh/node_modules/@deepseek-ai/dsh/package.json' if previous_artifact else dsh_package
    script=fixture/'init-profile.mjs'
    templates="boot.PROFILE_TEMPLATES" if previous_artifact else "(await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-official-bundles')))).PROFILE_TEMPLATES"
    script.write_text("import {createRequire} from 'node:module';import {pathToFileURL} from 'node:url';"
        "const require=createRequire(process.argv[2]);const boot=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-app-boot')));"
        +("if(boot.getDshRuntimeVersion()!=='0.2.1-rc.5')throw Error('Seed only the verified previous official rc.5');" if previous_artifact else "")+
        ("if(boot.getDshRuntimeVersion()!=='0.2.2-rc.1')throw Error('Source migration requires the verified current official 0.2.2-rc.1');" if migration_artifact else "")+
        "boot.initProfile(process.argv[3],"+templates+".web.bundles);",encoding='utf-8')
    env['ELECTRON_RUN_AS_NODE']='1'
    run([seed_electron,script,seed_package,profile])
    if previous_artifact:
        entry=seed_desktop/'resources/app.asar/dsh/node_modules/@deepseek-ai/dsh-desktop-host/lib/cli.js'
        seeded=run([seed_electron,'--expose-internals',entry,'plugin','--profile','desktop','add',
            'dsh-houdini@'+previous_package['version'],'--registry',base,'--store-dir',Path(env['PNPM_HOME'])/'store'])
        (fixture/'previous-official-cli.log').write_bytes(seeded.stdout+seeded.stderr)
        disable=fixture/'disable-previous-official.mjs'
        disable.write_text("import fs from 'node:fs';import{createRequire}from'node:module';import{pathToFileURL}from'node:url';"
            "const r=createRequire(process.argv[2]);const boot=await import(pathToFileURL(r.resolve('@deepseek-ai/dsh-app-boot')));"
            "const dir=process.argv[3],manifest=JSON.parse(fs.readFileSync(dir+'/package.json','utf8'));"
            "const selected=manifest.dsh.profile.bundles;boot.writeProfileBundles(dir,manifest,selected.filter(name=>name!=='dsh-houdini'));",encoding='utf-8')
        run([seed_electron,disable,seed_package,profile])
    if migration_artifact:
        seeded=official_cli(['add',migration_source_spec,'--save-exact','--registry',migration_registry,
            '--store-dir',Path(env['PNPM_HOME'])/'store'])
        (stage/'source-official-cli.log').write_bytes(seeded.stdout+seeded.stderr)
        disable=fixture/'disable-migration-source.mjs'
        disable.write_text("import fs from 'node:fs';import{createRequire}from'node:module';import{pathToFileURL}from'node:url';"
            "const r=createRequire(process.argv[2]);const boot=await import(pathToFileURL(r.resolve('@deepseek-ai/dsh-app-boot')));"
            "const dir=process.argv[3],manifest=JSON.parse(fs.readFileSync(dir+'/package.json','utf8'));"
            "boot.writeProfileBundles(dir,manifest,manifest.dsh.profile.bundles.filter(name=>name!=='dsh-houdini'));",encoding='utf-8')
        run([electron,disable,dsh_package,profile])
    env.pop('ELECTRON_RUN_AS_NODE',None)
    manifest=json.loads((profile/'package.json').read_text(encoding='utf-8'))
    assert ('dsh-houdini' in manifest.get('dependencies',{}))==bool(previous_artifact or migration_artifact)
    assert 'dsh-houdini' not in manifest.get('dsh',{}).get('profile',{}).get('bundles',[])
    patch=('- id: workspace-controller\n  config:\n    documentsDirectory: '+json.dumps(str(fixture/'documents'))+'\n'
        '- id: llm-pi-ai\n  config:\n    providers:\n      owned-distribution-chat:\n'
        '        api: openai-completions\n        baseURL: '+json.dumps(base+'/v1/')+'\n'
        '        apiKeyEnv: DSH_DIST_UI_CHAT_KEY\n        models:\n          - id: scripted-chat\n            input: [text]\n')
    registry=migration_registry if migration_artifact else base if previous_artifact else args.registry
    if registry:
        patch+='- id: plugin-manager\n  config:\n    registry: '+json.dumps(registry)+'\n    fallbackRegistries: []\n'
        (profile/'.npmrc').write_text('registry='+registry+'\n'+
            ('store-dir='+str(Path(env['PNPM_HOME'])/'store')+'\n' if previous_artifact else ''),encoding='utf-8')
    (profile/'cordis.patch.yml').write_text(patch,encoding='utf-8')
    (fixture/'documents').mkdir(exist_ok=True)


def official_cli(arguments):
    """Current unmodified Desktop CLI; the caller only supplies owned env roots."""
    previous=env.get('ELECTRON_RUN_AS_NODE')
    env['ELECTRON_RUN_AS_NODE']='1'
    try:
        entry=desktop/'resources/app.asar/dsh/node_modules/@deepseek-ai/dsh-desktop-host/lib/cli.js'
        return run([electron,'--expose-internals',entry,'plugin','--profile','desktop',*arguments])
    finally:
        if previous is None:env.pop('ELECTRON_RUN_AS_NODE',None)
        else:env['ELECTRON_RUN_AS_NODE']=previous


def migrate_owned_profile():
    assert process is None or process.poll() is not None,'Official CLI migration requires the owned Desktop to have exited'
    manifest=json.loads((profile/'package.json').read_text(encoding='utf-8'))
    installed=json.loads((profile/'node_modules/dsh-houdini/package.json').read_text(encoding='utf-8'))
    source=manifest['dependencies']['dsh-houdini']
    assert installed['version']==migration_package['version']
    assert source.startswith('file:') if args.migration_source=='file' else source==migration_source_spec
    def frozen_files():
        hashes={}
        with tarfile.open(migration_artifact,'r:gz') as archive:
            for relative in ['package.json','client.js','lib/frontend-host.js','houdini/python3.11libs/dsh_bridge.py']:
                expected=hashlib.sha256(archive.extractfile('package/'+relative).read()).hexdigest()
                assert digest(profile/'node_modules/dsh-houdini'/relative)==expected,'Source migration did not retain the exact frozen release file: '+relative
                hashes[relative]=expected
        return hashes
    original_files=frozen_files()
    before_selection=manifest.get('dsh',{}).get('profile',{}).get('bundles',[])
    before_others={name:value for name,value in manifest['dependencies'].items() if name!='dsh-houdini'}
    preserved={str(file.relative_to(profile)):digest(file) for file in [profile/'cordis.patch.yml',profile/'.npmrc']}
    spec='dsh-houdini@'+migration_package['version']
    migrated=official_cli(['add',spec,'--save-exact','--registry',migration_registry,'--store-dir',Path(env['PNPM_HOME'])/'store'])
    (stage/'migration-official-cli.log').write_bytes(migrated.stdout+migrated.stderr)
    after=json.loads((profile/'package.json').read_text(encoding='utf-8'))
    actual=json.loads((profile/'node_modules/dsh-houdini/package.json').read_text(encoding='utf-8'))
    assert after['dependencies']['dsh-houdini']==migration_package['version'],'The official CLI did not write an exact registry dependency'
    assert actual['version']==migration_package['version'],'Source migration must preserve the installed release version'
    assert after.get('dsh',{}).get('profile',{}).get('bundles',[])==before_selection,'CLI source migration changed bundle selections'
    assert {name:value for name,value in after['dependencies'].items() if name!='dsh-houdini'}==before_others
    assert all(digest(profile/relative)==expected for relative,expected in preserved.items()),'CLI migration rewrote owned settings or registry configuration'
    assert frozen_files()==original_files
    return {'via':'official-desktop-cli','runtime':'0.2.2-rc.1','from':source,'to':spec,'version':actual['version'],
        'registry':migration_registry,'selectionPreserved':True,'otherDependenciesPreserved':True,'settingsSha256':preserved,
        'frozenPackageFilesSha256':original_files,
        'guiSessionPreservationTested':not args.migration_cli_only}


def endpoints():
    if unpacked:
        def inspector():
            assert process.poll() is None,'Owned development carrier exited before admission'
            text=log.read_text(encoding='utf-8',errors='replace')
            match=re.search(r'Debugger listening on (ws://127\.0\.0\.1:\d+/[^\s]+)',text)
            return match.group(1) if match else None
        main=wait_until(inspector,args.timeout,'paused official carrier inspector')
        configuration=log.parent/'carrier-admission-input.json'
        admission=log.parent/'carrier-admission.json'
        configuration.write_text(json.dumps({'main':main,'pid':process.pid,'executable':str(carrier),
            'appPackage':str(app_package),'output':str(admission)}),encoding='utf-8')
        checked=subprocess.run([shutil.which('node'),str(ROOT/'tools/tests/desktop-carrier-admission.mjs'),str(configuration)],
            cwd=fixture,env=env,capture_output=True,timeout=90)
        (log.parent/'carrier-admission.log').write_bytes(checked.stdout+checked.stderr)
        assert checked.returncode==0,'Official carrier was not admitted; no DSH main execution authorized'
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
registry_files={};registry_document={};broken_version=None
if previous_artifact or migration_artifact:
    seed_artifact=migration_artifact or previous_artifact
    seed_metadata=migration_package if migration_artifact else previous_package
    registry_files={'/old.tgz':seed_artifact,'/dsh-houdini.tgz':copied}
    versions={}
    entries=[(seed_metadata,'/old.tgz'),(package,'/dsh-houdini.tgz')]
if previous_artifact:
    major,minor,patch=package['version'].split('-')[0].split('.')
    broken_version=f'{major}.{minor}.{int(patch)+1}-rc.999999-fixture'
    broken=fixture/'owned-broken-update-fixture.tgz'
    broken_manifest={'name':'dsh-houdini','version':broken_version,'private':True,'type':'module',
        'main':'lib/broken.js','exports':{'.':'./lib/broken.js'},'engines':package['engines'],
        'dsh':{'bundle':{'patch':['./broken.patch.yml']}}}
    with tarfile.open(broken,'w:gz') as archive:
        for name,text in {'package.json':json.dumps(broken_manifest),'broken.patch.yml':'- insert:\n    - id: owned-update-failure\n      name: dsh-houdini\n',
                'lib/broken.js':'throw new Error("Owned update failure fixture; not a product release")\n'}.items():
            data=text.encode();info=tarfile.TarInfo('package/'+name);info.size=len(data);archive.addfile(info,io.BytesIO(data))
    registry_files['/broken-fixture.tgz']=broken
    entries.append((broken_manifest,'/broken-fixture.tgz'))
if previous_artifact or migration_artifact:
    for metadata,route in entries:
        with registry_files[route].open('rb') as stream:integrity=base64.b64encode(hashlib.file_digest(stream,'sha512').digest()).decode()
        versions[metadata['version']]={**metadata,'dist':{'tarball':base+route,'integrity':'sha512-'+integrity}}
    registry_document={'name':'dsh-houdini','dist-tags':{'latest':package['version']},'versions':versions}
migration_registry=(args.registry or base) if migration_artifact else None
migration_source_spec=(str(migration_artifact) if args.migration_source=='file' else args.migration_url or base+'/old.tgz') if migration_artifact else None
remote_spec=npm_spec or args.remote_url or base+'/dsh-houdini.tgz'
threading.Thread(target=server.serve_forever,daemon=True).start()
immutable={str(file):digest(file) for file in [electron,desktop/'resources/app.asar',desktop/'resources/runtime/versions.json']}
if previous_artifact:
    previous_desktop=args.previous_desktop_root.resolve(strict=True)
    immutable.update({str(file):digest(file) for file in [previous_desktop/'DeepSeek Harness.exe',
        previous_desktop/'resources/app.asar',previous_desktop/'resources/runtime/versions.json']})
report={'fixture':str(fixture),'artifactSha256':digest(copied),'nativeElectronWindowTested':False,'nativeProfile':'desktop',
    'installedByNativeUi':False,'cliPluginInstallUsed':False,'chatModel':'owned scripted loopback provider',
    'remoteDistribution':'published npm package installed by native UI' if args.npm else 'explicit HTTPS tarball installed by native UI' if args.remote_url else 'owned HTTP tarball mechanism only; no npm/GitHub publication claim',
    'remoteInstallSpec':remote_spec,'requestedRegistry':args.registry,'immutable':immutable}
report['carrierMode']='official-unpacked-development' if unpacked else 'official-packaged'
report['packagedProtocolAndUpdaterQualified']=False
if previous_artifact:
    report.update(seededByPreviousOfficialCli=True,cliPluginInstallUsed=True,previousArtifactSha256=digest(previous_artifact),
        remoteDistribution='owned loopback registry update and failure-recovery mechanism; no public publication claim')
if migration_artifact:
    report.update(cliPluginInstallUsed=True,migrationSource=args.migration_source,migrationSourceSpec=migration_source_spec,
        migrationArtifactSha256=digest(migration_artifact),migrationRegistry=migration_registry,
        remoteDistribution='explicit public registry source migration and update' if args.registry else 'owned loopback registry source migration mechanism; no public publication claim',
        cliOnly=args.migration_cli_only)
print('Owned Native distribution UI evidence:',fixture,flush=True)
try:
    baseline=protocol_hash();report['protocolSha256Before']=baseline
    shutil.copy2(fixture/'protocol-current.json',fixture/'protocol-before.json')
    report['ui']={}
    modes=(['migration-cli'] if args.migration_cli_only else ['migration-before','migration-after']) if migration_artifact else ['update'] if previous_artifact else ['remote'] if args.remote_only else ['local'] if args.local_only else ['local','remote']
    report['testedStages']=modes
    for mode in modes:
        stage=fixture/mode;stage.mkdir()
        storage=fixture/'migration-profile' if migration_artifact else stage
        storage.mkdir(exist_ok=True)
        env['APPDATA']=str(storage/'appdata');Path(env['APPDATA']).mkdir(exist_ok=True)
        for name,relative in {'NPM_CONFIG_CACHE':'npm-cache','NPM_CONFIG_STORE_DIR':'store','PNPM_HOME':'package-manager'}.items():
            directory=storage/relative;directory.mkdir(exist_ok=True);env[name]=str(directory)
        env['DSH_HOME']=str(storage/'harness');home=Path(env['DSH_HOME']);profile=home/'profiles/desktop'
        user_data=Path(env['APPDATA'])/'dsh-desktop'
        if mode!='migration-after':init_empty_profile()
        if mode in ['migration-cli','migration-after']:
            report['migrationCli']=migrate_owned_profile()
            if mode=='migration-cli':continue
            # The same owned userData retains the former renderer's endpoint.
            # Require this launch to publish its own port before observing it.
            (user_data/'DevToolsActivePort').unlink(missing_ok=True)
        log=stage/'desktop.log';output=log.open('wb')
        process=subprocess.Popen([str(carrier),*([str(unpacked)] if unpacked else []),
            '--inspect-brk=127.0.0.1:0' if unpacked else '--inspect=127.0.0.1:0',
            '--remote-debugging-port=0','--user-data-dir='+str(user_data)],
            cwd=fixture,env=env,stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
        birth=_process_started(process.pid);assert birth;owned.append((process.pid,birth))
        endpoint=endpoints();capture_children()
        settings={'artifact':str(copied),'remoteInstallSpec':remote_spec,'npmSpec':npm_spec,'expectedVersion':package['version'],'expectedRegistry':args.registry,
            'appPackage':str(app_package),'expectedPackaged':not bool(unpacked),
            'asrEndpoint':asr_endpoint,'sentinel':sentinel,
            'remoteOnly':mode in ['remote','update','migration-before','migration-after'],'expectedPid':process.pid,'timeoutMs':args.timeout*1000,'output':str(stage/'ui-result.json'),**endpoint}
        if previous_artifact:settings.update(updateFromVersion=previous_package['version'],updateRegistry=base,brokenVersion=broken_version)
        if migration_artifact:settings.update(migrationPhase='before' if mode=='migration-before' else 'after',
            migrationVersion=migration_package['version'],migrationSource=args.migration_source,migrationSourceSpec=migration_source_spec,
            migrationState=str(fixture/'migration-browser-state.json'),migrationWorkspace=str(fixture/'documents'),
            expectedRegistry=migration_registry,**({'updateFromVersion':migration_package['version'],'updateRegistry':migration_registry} if mode=='migration-after' else {}))
        config=stage/'probe-input.json';config.write_text(json.dumps(settings),encoding='utf-8')
        result=subprocess.run([shutil.which('node'),str(ROOT/'tools/tests/desktop-install-ui-probe.mjs'),str(config)],
            cwd=fixture,env=env,capture_output=True,timeout=args.timeout*3)
        (stage/'probe.log').write_bytes(result.stdout+result.stderr)
        assert result.returncode==0,'Native '+mode+' distribution UI failed; inspect '+str(stage/'ui-result.json')
        report['ui'][mode]=json.loads((stage/'ui-result.json').read_text(encoding='utf-8'))
        if mode in ['local','update','migration-after']:
            installed=(profile/'node_modules/dsh-houdini').resolve(strict=True)
            # --output-dir may live under the repository's managed tools/out.
            # The resolved package must still belong to this fresh fixture.
            assert installed.is_relative_to(fixture)
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
    report['nativeElectronWindowTested']=not args.migration_cli_only;report['installedByNativeUi']=not bool(previous_artifact or migration_artifact)
    report['updatedByNativeApi']=any(stage.get('updatedByNativeApi') is True for stage in report['ui'].values())
    report['updatedByNativeUi']=any(stage.get('updatedByNativeUi') is True for stage in report['ui'].values())
    if previous_artifact:assert report['updatedByNativeUi'],'The consumer did not observe the real Native update button path'
    if migration_artifact and not args.migration_cli_only:
        assert report['updatedByNativeUi'] and report['ui']['migration-after'].get('migrationStatePreserved') is True
    assert server_facts['asrRequests']==0 and not server_facts['errors'],server_facts
    if not (previous_artifact or migration_artifact) and not args.local_only and not args.remote_url and not args.npm:assert server_facts['tarballGets']>0,server_facts
    assert server_facts['sentinelAbsentFromModel'],server_facts
    if not args.remote_only and not migration_artifact:assert server_facts['chatRequests']==0 and not server_facts['toolCalls'],server_facts
    assert protocol_hash()==baseline and {file:digest(file) for file in immutable}==immutable
    report.update(ok=True,normalExitCode=process.returncode if process else None,loopback=server_facts,desktopInstallationAndProtocolUnchanged=True)
    remote_label='npm package' if args.npm else 'HTTPS tarball' if args.remote_url else 'HTTP tarball'
    print(('PASS official CLI same-version source migration only; GUI/session/update not tested' if args.migration_cli_only else 'PASS Native source eligibility, official CLI migration and real update button with original session/settings preserved' if migration_artifact else 'PASS Native update button from actual disabled registry 0.1.6 and API failed-fixture restoration' if previous_artifact else 'PASS Native local tarball UI + real Agent/credentials' if args.local_only else 'PASS Native '+remote_label+' UI install/disable/re-enable/uninstall' if args.remote_only else
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
            shutil.copy2(fixture/'protocol-current.json',fixture/'protocol-after.json')
            report['desktopInstallationUnchangedAfterCleanup']={file:digest(file) for file in immutable}==immutable
        except Exception as error:report['isolationVerificationError']=repr(error);report['ok']=False
    (fixture/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert 'isolationVerificationError' not in report,report.get('isolationVerificationError')
