"""Candidate composition/RPC smoke; independent home, no model calls or user HIP.

Install DSH and the packed plugin normally in --candidate before running, or
use --runtime-cache for a temporary read-only projection of a cached CLI plus source plugin.
This is not signed-package or GUI qualification and never promotes preferred.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment, launch_directory
from dsh_web_auth import DshWebSession
import dsh_managed_runtime as runtime

parser = argparse.ArgumentParser(description=__doc__)
inputs = parser.add_mutually_exclusive_group(required=True)
inputs.add_argument('--candidate', type=Path)
inputs.add_argument('--runtime-cache', type=Path)
parser.add_argument('--houdini', type=Path, action='append', default=[],
                    help='Optional isolated hython for actual DSH delivery card/Sidebar checks')
parser.add_argument('--houdini-gui', type=Path, action='append', default=[],
                    help='Optional isolated Houdini GUI WebView acceptance (no user HIP)')
parser.add_argument('--delivery-preset', choices=['houdini', 'standard'], default='houdini',
                    help='Diagnostic comparison for the actual Agent delivery turn')
parser.add_argument('--hold-seconds', type=int, default=0,
                    help='Keep only this isolated Host online briefly for browser inspection')
parser.add_argument('--preinit-webengine', action='store_true',
                    help='Diagnostic: initialize another WebEngine page before the DSH view')
args = parser.parse_args()
node = shutil.which('node')
assert node
fixture = Path(tempfile.mkdtemp(prefix='dsh-candidate-rpc-'))
print('Isolated evidence:', fixture, flush=True)
env = isolated_environment(fixture)
if args.runtime_cache:
    cache = args.runtime_cache.resolve(strict=True)
    assert (cache / 'node_modules/@deepseek-ai/dsh/package.json').is_file()
    candidate = fixture / 'candidate'
    # Junctions are created only in the new fixture, never inside the cache or source tree.
    projection = """
const fs=require('fs'),path=require('path');
const [cache,app,plugin]=process.argv.slice(1), nm=path.join(app,'node_modules');
fs.mkdirSync(nm,{recursive:true});
for(const entry of fs.readdirSync(path.join(cache,'node_modules'),{withFileTypes:true})) {
  if(entry.isDirectory() && entry.name!=='dsh-houdini')
    fs.symlinkSync(path.join(cache,'node_modules',entry.name),path.join(nm,entry.name),'junction');
}
fs.symlinkSync(plugin,path.join(nm,'dsh-houdini'),'junction');
"""
    subprocess.run([node,'-e',projection,str(cache),str(candidate),str(ROOT)],check=True,env=env,
                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
else:
    candidate = args.candidate.resolve(strict=True)
assert (candidate / 'node_modules/dsh-houdini/package.json').is_file()
install = fixture / 'install'
install.mkdir()
subprocess.run([node, '-e', "require('fs').symlinkSync(process.argv[1],process.argv[2],'junction')",
                str(candidate), str(install / 'app')], check=True, env=env)
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
bridge_socket = socket.socket()
bridge_socket.bind(('127.0.0.1',0))  # Reserve a non-listening fixture port, never point tools at live Houdini.
bridge_port = bridge_socket.getsockname()[1]
env['DSH_HOUDINI_BRIDGE_URL'] = f'http://127.0.0.1:{bridge_port}'
context = fixture / 'context.json'
context.write_text(json.dumps({'home':env['DSH_HOME'], 'install':str(install), 'bridgePort':bridge_port}), encoding='utf-8')
subprocess.run([node, str(ROOT / 'tools/prepare-managed-profile.mjs'), str(context)], check=True, env=env)
for preset_name in ('houdini', 'houdini-dev'):
    synced = (Path(env['DSH_HOME']) / '.agent-presets' / preset_name / 'agent.cordis.yml').read_text(encoding='utf-8')
    assert "- id: present\n  name: '@deepseek-ai/dsh-tool-present'" in synced.replace('\r\n', '\n'), (
        f'{preset_name} lost standard file delivery during managed preset synchronization')
workspace = fixture / 'workspace'
workspace.mkdir()
text_file = workspace / '说明 空格.txt'
text_file.write_text('Houdini delivery path\n', encoding='utf-8')
plain_file = workspace / 'plain.txt'
plain_file.write_text('ASCII delivery preview\n', encoding='utf-8')
image_file = workspace / '最终 图片.png'
image_bytes = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lXcAAAAASUVORK5CYII=')
image_file.write_bytes(image_bytes)
outside = fixture / 'outside 中文 空格'
outside.mkdir()
outside_file = outside / 'final.txt'
outside_file.write_text('outside HIP workspace\n', encoding='utf-8')
hip_files = []
for gui_executable in args.houdini_gui:
    gui_executable = gui_executable.resolve(strict=True)
    hython = gui_executable.with_name('hython.exe')
    hip = outside / (gui_executable.parent.parent.name + ' 空白场景.hip')
    hip_env = isolated_environment(fixture / ('hip-' + gui_executable.parent.parent.name), executable=hython)
    saved = subprocess.run([str(hython), '-c', 'import hou,sys; hou.hipFile.save(sys.argv[1])', str(hip)],
                           cwd=launch_directory(hython), env=hip_env, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=60)
    if saved.returncode or not hip.is_file():
        raise RuntimeError('isolated Houdini HIP save failed: ' + (saved.stdout + saved.stderr)[-2000:])
    hip_files.append(hip)
delivery_files = [
    {'path': str(image_file), 'description': 'Final PNG'},
    {'path': str(text_file), 'description': 'Final text'},
    {'path': str(plain_file), 'description': 'Plain text control'},
    {'path': str(outside_file), 'description': 'External final output'},
    *({'path': str(hip), 'description': 'Saved Houdini scene'} for hip in hip_files),
]
env['DSH_PRESENT_FIXTURE_FILES'] = json.dumps(delivery_files, ensure_ascii=False)
delivery_output = fixture / 'presented.json'
env['DSH_PRESENT_FIXTURE_OUT'] = str(delivery_output)
overlay = fixture / 'present-overlay.yml'
overlay.write_text('- insert:\n    - id: present-fixture\n      name: '
                   + (ROOT / 'tools/tests/dsh-present-loop-fixture.mjs').as_uri() + '\n', encoding='utf-8')
present_check = subprocess.run([node, str(ROOT / 'tools/tests/dsh-present-candidate.mjs'),
                                str(candidate), str(workspace), str(outside_file)],
                               check=True, env=env, capture_output=True, text=True,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
print(present_check.stdout.strip(), flush=True)
log = fixture / 'frontend.log'
state = fixture / 'runtime.json'
base = f'http://127.0.0.1:{port}'
auth = DshWebSession(base, str(log), str(state))

def rpc(method, payload, authenticated=True, *, expected_ok=True, client=None):
    body = json.dumps({'type':'client-request', 'rpcId':'candidate-'+uuid.uuid4().hex, 'method':method,
                       'payload':{'args':payload}}).encode()
    request = urllib.request.Request(base+'/api/'+method, data=body,
                                     headers={'Content-Type':'application/json'}, method='POST')
    opener = (client or auth) if authenticated else urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=5) as response:
        result = json.load(response)['result']
        assert response.status == 200 and result['ok'] is expected_ok, method + ': ' + str(result)
        return result['value'] if expected_ok else result['error']

with log.open('wb') as output:
    process = runtime.spawn_frontend([node, str(candidate/'node_modules/@deepseek-ai/dsh/lib/bin.js'),
                                'web', '--patch', str(overlay), '--port', str(port), '--no-open'], node=node, cwd=workspace, env=env,
                               stdout=output, stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        state.write_text(json.dumps({'pid':process.pid,'authLogOffset':0}), encoding='utf-8')
        deadline = time.monotonic()+90
        while time.monotonic()<deadline:
            assert process.poll() is None, 'candidate exited; inspect isolated frontend.log'
            try:
                auth.authorize(timeout=3)
                assert isinstance(rpc('session/list', {'_request':{}})['items'], list)
                break
            except (OSError, RuntimeError):
                time.sleep(.3)
        else:
            raise AssertionError('candidate readiness timed out; inspect isolated frontend.log')
        try:
            rpc('session/list', {'_request':{}}, authenticated=False)
        except urllib.error.HTTPError as error:
            assert error.code == 401
        else:
            raise AssertionError('unauthenticated RPC accepted')
        first = rpc('workspace/create', {'request':{'path':str(workspace)}})['workspace']
        second = rpc('workspace/create', {'request':{'path':str(workspace)}})['workspace']
        assert first['workspaceId'] == second['workspaceId']
        sessions = {}
        for preset in ['houdini','houdini-dev']:
            request = {'workspaceId':first['workspaceId'], 'agentPreset':preset,
                       'sessionId':'dsh-houdini-'+uuid.uuid4().hex}
            created = rpc('session/create', {'request':request})
            repeated = rpc('session/create', {'request':request})  # Also covers an ignored/lost first response.
            assert created['sessionId'] == repeated['sessionId'] == request['sessionId']
            assert created['agentPreset'] == repeated['agentPreset'] == preset
            sessions[preset] = created['sessionId']

        # These are the authenticated read routes used by Sidebar previews.
        # Houdini's absolute output may live outside the Session file tree.
        file_scope = sessions['houdini']
        def file_args(path, **extra):
            return {'workspaceFileScopeId':file_scope, 'path':str(path), **extra}
        image_stat = rpc('workspaceFiles/stat', file_args(image_file))
        assert Path(image_stat['absolutePath']).resolve() == image_file.resolve()
        assert image_stat['bytes'] == len(image_bytes)
        image_read = rpc('workspaceFiles/readAll', file_args(image_file))
        assert base64.b64decode(image_read['data']) == image_bytes and image_read['eof']
        text_read = rpc('workspaceFiles/read', file_args(text_file, range={'offset':1,'limit':2}))
        assert text_read['text'].strip() == 'Houdini delivery path', text_read
        external_stat = rpc('workspaceFiles/stat', file_args(outside_file))
        assert Path(external_stat['absolutePath']).resolve() == outside_file.resolve()
        for hip in hip_files:
            hip_stat = rpc('workspaceFiles/stat', file_args(hip))
            assert Path(hip_stat['absolutePath']).resolve() == hip.resolve() and hip_stat['bytes'] > 0
        for invalid in (workspace, workspace / 'missing.txt'):
            error = rpc('workspaceFiles/stat', file_args(invalid), expected_ok=False)
            assert error, f'non-file path unexpectedly accepted: {invalid}'
        for link in (workspace / 'file-link.txt', workspace / 'directory-junction'):
            if link.is_symlink() or link.exists():
                error = rpc('workspaceFiles/stat', file_args(link), expected_ok=False)
                assert error, f'final link unexpectedly accepted: {link}'
        print('Candidate Sidebar file routes: PNG bytes, Unicode text and outside-workspace absolute path passed', flush=True)

        # The mounted Houdini preset must execute present in an actual Agent
        # turn, then persist the event. The adapter is local and deterministic.
        present_id = 'dsh-houdini-'+uuid.uuid4().hex
        rpc('session/create', {'request':{'workspaceId':first['workspaceId'],
            'agentPreset':args.delivery_preset,'sessionId':present_id}})
        rpc('session/selectModel', {'request':{'sessionId':present_id,
            'provider':'present-fixture','model':'fixture'}})
        rpc('session/prompt', {'request':{'sessionId':present_id,'requestId':uuid.uuid4().hex,
            'mode':'queue','content':[{'type':'text','text':'Deliver the temporary fixture files.'}]}})
        for _ in range(120):
            if delivery_output.exists():
                break
            assert process.poll() is None, 'candidate exited before present tool result'
            time.sleep(.25)
        else:
            raise AssertionError('mounted present tool did not publish a delivery; inspect isolated frontend.log')
        delivered = json.loads(delivery_output.read_text(encoding='utf-8'))
        assert delivered['sessionId'] == present_id and delivered['files'] == delivery_files
        assert isinstance(delivered['seq'], int)
        print('Candidate Agent turn: mounted present emitted a persisted delivery event without a model request', flush=True)
        if args.hold_seconds:
            assert 1 <= args.hold_seconds <= 600
            (fixture / 'launch.url').write_text(auth.launch_url(), encoding='utf-8')
            (fixture / 'delivery-session.txt').write_text(present_id, encoding='utf-8')
            print('Isolated browser inspection ready:', fixture, flush=True)
            until = time.monotonic() + args.hold_seconds
            while time.monotonic() < until and not (fixture / 'continue.flag').exists():
                assert process.poll() is None
                time.sleep(.5)
        for executable in [*args.houdini, *args.houdini_gui]:
            executable = executable.resolve(strict=True)
            gui = executable in [p.resolve(strict=True) for p in args.houdini_gui]
            browser_fixture = fixture / (('gui-' if gui else 'webview-') + executable.parent.parent.name)
            browser_env = isolated_environment(browser_fixture, executable=executable, gui=gui)
            browser_result = browser_fixture / 'present-webview.json'
            browser_env.update(DSH_PRESENT_WEBVIEW_URL=auth.launch_url(),
                               DSH_PRESENT_WEBVIEW_SESSION_ID=present_id,
                               DSH_PRESENT_WEBVIEW_RESULT=str(browser_result))
            command = [str(executable), str(ROOT / 'tools/tests/dsh-present-webview-probe.py')]
            if gui:
                browser_env['DSH_PRESENT_WEBVIEW_GUI'] = '1'
                if args.preinit_webengine:
                    browser_env['DSH_PRESENT_WEBVIEW_PREINIT'] = '1'
                hook_source = (
                    'import os, runpy, traceback\n'
                    'from pathlib import Path\n'
                    'from PySide6.QtCore import QTimer\n'
                    'import hou\n'
                    'def run_probe():\n'
                    '  if os.environ.get("DSH_PRESENT_WEBVIEW_PREINIT") == "1":\n'
                    '    from PySide6.QtWebEngineCore import QWebEnginePage\n'
                    '    prior = QWebEnginePage(hou.qt.mainWindow())\n'
                    '  try: runpy.run_path(' + repr(str(ROOT / 'tools/tests/dsh-present-webview-probe.py')) + ')\n'
                    '  except BaseException:\n'
                    '    Path(os.environ["DSH_PRESENT_WEBVIEW_RESULT"]).write_text('
                    'traceback.format_exc(), encoding="utf-8")\n'
                    '  finally: QTimer.singleShot(100, hou.qt.mainWindow().close)\n'
                    'QTimer.singleShot(1500, run_probe)\n'
                )
                for version, python in [('21.0', '3.11'), ('22.0', '3.13')]:
                    hook = Path(browser_env['HOUDINI_USER_PREF_DIR'].replace('__HVER__', version)) / f'python{python}libs/uiready.py'
                    hook.parent.mkdir(parents=True, exist_ok=True)
                    hook.write_text(hook_source, encoding='utf-8')
                command = [str(executable), '-foreground', '-geometry=800x600+12000+12000']
            probe = subprocess.run(command, cwd=launch_directory(executable), env=browser_env,
                                   capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=150)
            if probe.returncode:
                (browser_fixture / 'probe.log').write_text(probe.stdout + probe.stderr, encoding='utf-8')
                detail = browser_result.read_text(encoding='utf-8') if browser_result.exists() else '(no probe result)'
                raise RuntimeError(f'{executable} delivery WebView failed: {detail[:2500]}; inspect {browser_fixture}')
            result = json.loads(browser_result.read_text(encoding='utf-8'))
            assert (result['ok'] and result['textPreview'] and result['imagePreview']
                    and result['externalPreview'] and len(result['cards']) >= 4)
            print(executable.parent.parent.name, 'isolated GUI' if gui else 'Qt WebView',
                  'delivery cards and Sidebar preview passed', flush=True)

        # Real published-but-unattached state; retrying the same id must adopt
        # and attach it, not create another session or change the preset.
        detached_id = 'dsh-houdini-'+uuid.uuid4().hex
        rpc('session/create', {'request':{'cwd':str(workspace),'agentPreset':'houdini','sessionId':detached_id}})
        before = rpc('workspace/create', {'request':{'path':str(workspace)}})['workspace']
        assert detached_id not in before['sessionIds'], 'fixture is not genuinely unattached'
        adopted = rpc('session/create', {'request':{'workspaceId':first['workspaceId'],
                      'agentPreset':'houdini','sessionId':detached_id}})
        after = rpc('workspace/create', {'request':{'path':str(workspace)}})['workspace']
        assert adopted['sessionId'] == detached_id and adopted['agentPreset'] == 'houdini'
        assert after['sessionIds'].count(detached_id) == 1

        failed_id = 'dsh-houdini-'+uuid.uuid4().hex
        rpc('session/create', {'request':{'workspaceId':first['workspaceId'],
            'agentPreset':'missing-navigation-fixture','sessionId':failed_id}}, expected_ok=False)
        fixed = rpc('session/create', {'request':{'workspaceId':first['workspaceId'],
            'agentPreset':'houdini','sessionId':failed_id}})
        assert fixed['sessionId'] == failed_id and fixed['agentPreset'] == 'houdini'

        # Separate authenticated clients exercise overlapping same-ID creates,
        # not a transport lock or a repeated rpcId masking duplicate execution.
        peers = [DshWebSession(base,str(log),str(state)) for _ in range(2)]
        for peer in peers:
            peer.authorize(timeout=3)
        concurrent_id = 'dsh-houdini-'+uuid.uuid4().hex
        def create_same(peer):
            return rpc('session/create', {'request':{'workspaceId':first['workspaceId'],
                       'agentPreset':'houdini','sessionId':concurrent_id}},client=peer)
        with ThreadPoolExecutor(max_workers=2) as executor:
            values = list(executor.map(create_same,peers))
        assert all(value['sessionId'] == concurrent_id and value['agentPreset'] == 'houdini' for value in values)

        archived = rpc('workspace/archiveSession', {'request':{'sessionId':detached_id}})
        assert detached_id in archived['archivedSessionIds']
        accounted = rpc('workspace/create', {'request':{'path':str(workspace)}})['workspace']
        assert detached_id in accounted['sessionIds'], 'archive state is separate from workspace membership'
        items = rpc('session/list', {'_request':{}})['items']
        for identity in (detached_id, failed_id, concurrent_id):
            matches = [row for row in items if row['sessionId'] == identity]
            assert len(matches) == 1 and matches[0]['projections']['values']['agentPreset'] == 'houdini'
        print('Candidate native RPC: both presets, caller-owned IDs, repeat/concurrent adoption, unattached retry and independent archive state passed', flush=True)
    finally:
        runtime.stop_owned()
        process.wait(timeout=15)
        bridge_socket.close()
