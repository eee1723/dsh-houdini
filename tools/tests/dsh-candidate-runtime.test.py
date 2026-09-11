"""Candidate composition/RPC smoke; independent home, no model calls or user HIP.

Install DSH and the packed plugin normally in --candidate before running.
This is not signed-package or GUI qualification and never promotes preferred.
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
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment
from dsh_web_auth import DshWebSession

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--candidate', type=Path, required=True)
args = parser.parse_args()
candidate = args.candidate.resolve(strict=True)
node = shutil.which('node')
assert node and (candidate / 'node_modules/dsh-houdini/package.json').is_file()
fixture = Path(tempfile.mkdtemp(prefix='dsh-candidate-rpc-'))
print('Isolated evidence:', fixture, flush=True)
env = isolated_environment(fixture)
install = fixture / 'install'
install.mkdir()
subprocess.run([node, '-e', "require('fs').symlinkSync(process.argv[1],process.argv[2],'junction')",
                str(candidate), str(install / 'app')], check=True, env=env)
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
context = fixture / 'context.json'
context.write_text(json.dumps({'home':env['DSH_HOME'], 'install':str(install), 'bridgePort':18765}), encoding='utf-8')
subprocess.run([node, str(ROOT / 'tools/prepare-managed-profile.mjs'), str(context)], check=True, env=env)
workspace = fixture / 'workspace'
workspace.mkdir()
log = fixture / 'frontend.log'
state = fixture / 'runtime.json'
base = f'http://127.0.0.1:{port}'
auth = DshWebSession(base, str(log), str(state))

def rpc(method, payload, authenticated=True):
    body = json.dumps({'type':'client-request', 'rpcId':'candidate-smoke', 'method':method,
                       'payload':{'args':payload}}).encode()
    request = urllib.request.Request(base+'/api/'+method, data=body,
                                     headers={'Content-Type':'application/json'}, method='POST')
    opener = auth if authenticated else urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=5) as response:
        result = json.load(response)['result']
        assert response.status == 200 and result['ok'], method + ' rejected'
        return result['value']

with log.open('wb') as output:
    process = subprocess.Popen([node, str(candidate/'node_modules/@deepseek-ai/dsh/lib/bin.js'),
                                'web', '--port', str(port), '--no-open'], cwd=workspace, env=env,
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
            created = rpc('session/create', {'request':{'workspaceId':first['workspaceId'], 'agentPreset':preset}})
            assert created['sessionId'] and created['agentPreset'] == preset
        print('Candidate boot, profile, 401/200 RPC, idempotent workspace and both presets passed', flush=True)
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=15)
