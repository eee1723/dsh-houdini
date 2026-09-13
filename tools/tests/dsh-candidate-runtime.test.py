"""Candidate composition/RPC smoke; independent home, no model calls or user HIP.

Install DSH and the packed plugin normally in --candidate before running, or
use --runtime-cache for a temporary read-only projection of a cached CLI plus source plugin.
This is not signed-package or GUI qualification and never promotes preferred.
"""
import argparse
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
from houdini_test_environment import isolated_environment
from dsh_web_auth import DshWebSession
import dsh_managed_runtime as runtime

parser = argparse.ArgumentParser(description=__doc__)
inputs = parser.add_mutually_exclusive_group(required=True)
inputs.add_argument('--candidate', type=Path)
inputs.add_argument('--runtime-cache', type=Path)
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
workspace = fixture / 'workspace'
workspace.mkdir()
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
                                'web', '--port', str(port), '--no-open'], node=node, cwd=workspace, env=env,
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
        for preset in ['houdini','houdini-dev']:
            request = {'workspaceId':first['workspaceId'], 'agentPreset':preset,
                       'sessionId':'dsh-houdini-'+uuid.uuid4().hex}
            created = rpc('session/create', {'request':request})
            repeated = rpc('session/create', {'request':request})  # Also covers an ignored/lost first response.
            assert created['sessionId'] == repeated['sessionId'] == request['sessionId']
            assert created['agentPreset'] == repeated['agentPreset'] == preset

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
