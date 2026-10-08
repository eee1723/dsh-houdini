"""Exercise image generation through the exact isolated DSH Host, without paid APIs.

Usage: python tools/tests/dsh-image-generation-smoke.test.py --runtime-cache <cache>
The owned HTTP fixture accepts real JSON/multipart requests. DSH settings,
credentials, sessions, native/PTC tools and attachment storage remain real.
"""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli
import dsh_managed_runtime as runtime


def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-cache', type=Path, required=True)
parser.add_argument('--houdini', type=Path, help='Optional isolated Houdini GUI to check the selected real task and all PNG previews')
args = parser.parse_args()
if args.houdini:
    reexec_unpacked_test_cli()
cache = args.runtime_cache.resolve(strict=True)
node = shutil.which('node')
assert node
preferred = json.loads((ROOT / 'dsh-runtime-compatibility.json').read_text())['preferredVersion']
assert json.loads((cache / 'node_modules/@deepseek-ai/dsh/package.json').read_text())['version'] == preferred
fixture = Path(tempfile.mkdtemp(prefix='dsh-image-generation-'))
workspace = fixture / 'workspace'
workspace.mkdir()
projects = {name: fixture / ('project-' + name) for name in ('B', 'C')}
for project in projects.values():
    project.mkdir()
print('Isolated evidence:', fixture, flush=True)
env = isolated_environment(fixture)
subprocess.run([node, str(ROOT / 'tools/tests/prepare-shared-host-fixture.mjs'),
    str(cache / 'node_modules/@deepseek-ai/dsh/lib/bin.js'), env['DSH_HOME'], str(ROOT)],
    cwd=ROOT, env=env, check=True, timeout=60, capture_output=True)
if args.houdini:
    (Path(env['DSH_HOME']) / 'profiles/web/cordis.patch.yml').write_text(
        '- id: locale\n  config:\n    preference: zh\n', encoding='utf-8')
api_port, host_port = unused_port(), unused_port()
env.update(DSH_HOUDINI_BRIDGE_URL=f'http://127.0.0.1:{api_port}',
           DSH_HOUDINI_EXECUTOR_ID=uuid.uuid4().hex,
           DSH_IMAGE_FIXTURE_OUT=str(fixture / 'result.json'),
           DSH_IMAGE_FIXTURE_WORKSPACE=str(workspace),
           DSH_IMAGE_FIXTURE_PROJECT_B=str(projects['B']),
           DSH_IMAGE_FIXTURE_PROJECT_C=str(projects['C']))
overlay = fixture / 'image-fixture.patch.yml'
# JSON is YAML: use structured values so paths/URLs never depend on shell quoting.
overlay.write_text(json.dumps([{'insert': [
    {'id': 'image-generation-fixture', 'name': (ROOT / 'tools/tests/dsh-image-generation-fixture.mjs').as_uri()},
]}]), encoding='utf-8')
log = fixture / 'host.log'


def inspect_frontend(host, result):
    from dsh_web_auth import DshWebSession
    worker = None
    paths = [Path(artifact['actual_path']) for artifact in result['artifacts']]
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    evidence = {'ok': False, 'pngBefore': before}
    try:
        session_file = next((Path(env['DSH_HOME']) / 'sessions').glob(
            '*/' + result['sessionId'] + '/session.v4.jsonl.zstd'))
        subprocess.run([node, str(ROOT / 'tools/tests/modeling-trial-ui-artifacts.mjs'),
            str(session_file), str(fixture / 'frontend-artifacts.json'), str(workspace), result['sessionId']],
            cwd=ROOT, env=env, capture_output=True, check=True, timeout=30)
        auth = DshWebSession(f'http://127.0.0.1:{host_port}', str(log), str(fixture / 'runtime.json'))
        auth.authorize(timeout=10)
        config = {'base': f'http://127.0.0.1:{host_port}', 'authenticatedUrl': auth.launch_url(),
            'sessionId': result['sessionId'], 'output': str(fixture / 'frontend-probe-result.json'),
            'modelRunKind': 'local-image-http-fixture', 'previewAllImages': True, 'imageDimensions': [16, 16]}
        config_path = fixture / 'frontend-probe-config.json'
        config_path.write_text(json.dumps(config), encoding='utf-8')
        with (fixture / 'gui-supervisor.log').open('wb') as worker_log:
            worker = subprocess.Popen([sys.executable, str(ROOT / 'tools/isolated-worker.py'),
                '--executable', str(args.houdini.resolve(strict=True)), '--directory', str(fixture / 'gui-worker'),
                '--registry', str(fixture / 'gui-registry'), '--gui', '--memory-mb', '8192', '--threads', '2',
                '--startup-timeout', '120'], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=worker_log, text=True, env=isolated_environment(fixture / 'gui-driver'),
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            ready = queue.Queue()
            threading.Thread(target=lambda: ready.put(worker.stdout.readline()), daemon=True).start()
            info = json.loads(ready.get(timeout=135))
            assert info['ok'], info
            record = info['record']

            def bridge(route, payload):
                request = urllib.request.Request(record['bridge_url'] + route, data=json.dumps(payload).encode(),
                    headers={'Content-Type': 'application/json', 'X-DSH-Houdini-Executor': record['executor_id']})
                with urllib.request.urlopen(request, timeout=45) as response:
                    return json.load(response)

            claimed = bridge('/executor/claim', {'task_id': result['sessionId'],
                'registration_id': record['registration_id'], 'expected_hip': record['hip_path']})
            assert claimed.get('ok'), claimed
            ticket = bridge('/requests/prepare', {'owner_session': result['sessionId']})
            code = ('import runpy\n__result__=runpy.run_path(' + repr(str(ROOT / 'tools/tests/modeling-trial-frontend-probe.py'))
                    + ')["start"](' + repr(str(config_path)) + ')\nimport dsh_webview\ndsh_webview._window.move(12000,12000)')
            admission = bridge('/exec', {'owner_session': result['sessionId'], 'owner_call': 'image-frontend-probe',
                'request_ref': ticket['requestRef'], 'expected_contract': {'version': ticket['executionContractVersion'],
                'hash': ticket['verbCatalog']['hash']}, 'code': code,
                'allow_raw': 'Move only the self-owned test Qt WebView offscreen for painting and capture; no Houdini verb covers QWidget positioning, and no scene geometry is changed.'})
            assert admission.get('ok'), admission
            deadline = time.monotonic() + 125
            while not Path(config['output']).exists():
                assert worker.poll() is None and host.poll() is None, 'owned process exited during Qt probe'
                assert time.monotonic() < deadline, 'Qt image probe timed out'
                time.sleep(.25)
            frontend = json.loads(Path(config['output']).read_text(encoding='utf-8'))
            evidence['frontend'] = frontend
            assert frontend['ok'], frontend
            facts = frontend['facts']
            assert facts['selection']['sessionId'] == result['sessionId']
            assert facts['fileConsumerVerified'] and facts['imageConsumerVerified']
            assert {image['name'] for image in facts['imagePreviews']} == {path.name for path in paths}
            assert all((image['width'], image['height']) == (16, 16) for image in facts['imagePreviews'])
            evidence['pngAfter'] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
            assert evidence['pngAfter'] == before, 'UI inspection modified generated pixels'
            evidence['ok'] = True
            print('Houdini Qt: selected real fixture task, all actual-path delivery previews decoded 16 x 16, source hashes unchanged', flush=True)
    finally:
        if worker is not None and worker.poll() is None:
            worker.stdin.write('STOP\n')
            worker.stdin.flush()
            try:
                evidence['workerExitCode'] = worker.wait(timeout=35)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=10)
                evidence['supervisorKilledAfterTimeout'] = True
        (fixture / 'frontend-result.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    assert evidence.get('workerExitCode') == 0, evidence


with log.open('wb') as output:
    process = runtime.spawn_frontend([node, str(cache / 'node_modules/@deepseek-ai/dsh/lib/bin.js'),
        'web', '--patch', str(overlay), '--port', str(host_port), '--no-open'],
        node=node, cwd=fixture, env=env, stdout=output, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        deadline = time.monotonic() + 120
        result_file = fixture / 'result.json'
        while not result_file.exists():
            assert process.poll() is None, 'Host exited; inspect ' + str(log)
            assert time.monotonic() < deadline, 'Image loop timed out; inspect ' + str(log)
            time.sleep(.2)
        result = json.loads(result_file.read_text(encoding='utf-8'))
        assert result.get('ok') is True, result.get('error', result)
        print('Exact DSH image tools: live settings, real credentials, native generation, '
              'multipart PTC edit, project-root policy, in-flight Save As, offline explicit output, '
              'original/preview readback and actual-path present delivery passed', flush=True)
        print(json.dumps({key: result[key] for key in ('sessionId', 'checks', 'requests')}, ensure_ascii=False), flush=True)
        if args.houdini:
            inspect_frontend(process, result)
    finally:
        runtime.stop_owned(process)
        process.wait(timeout=15)
