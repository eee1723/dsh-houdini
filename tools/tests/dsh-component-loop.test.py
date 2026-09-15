"""Keyless real DSH composition with parent and two independently bound workers.

Arguments: node executable, patched DSH bin.js, hython executable.
Uses new data/registry/work directories and a deterministic adapter only.
"""
from pathlib import Path
import json
import queue
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
from houdini_test_environment import isolated_environment
from dsh_web_auth import DshWebSession
from dsh_managed_runtime import spawn_frontend, stop_owned

node, cli, hython = sys.argv[1:4]
# DSH workspace-write intentionally permits the platform temp area. Put author
# workspaces outside it so the negative test actually crosses a denied boundary.
fixture = Path(tempfile.mkdtemp(prefix='component-loop-', dir=ROOT / 'tools/out'))
print('Fixture:', fixture, flush=True)
registry = fixture / 'registry'
workers = fixture / 'parent/workspace/dsh-components'
configured_workers = fixture / 'configured-workers-unused'
outputs = fixture / 'results'
outputs.mkdir()
env = isolated_environment(fixture / 'environment')
env.update(DSH_HOME=str(fixture / 'home'), DSH_HOUDINI_EXECUTOR_REGISTRY=str(registry),
           DSH_COMPONENT_TEST_WORKERS=str(workers), DSH_COMPONENT_TEST_OUT=str(outputs))
negative = '--expect-cwd-rejection' in sys.argv
auto_release = '--expect-auto-release' in sys.argv
child_failure = '--expect-child-failure' in sys.argv
startup_failure = '--expect-startup-failure' in sys.argv
stop_failure = '--expect-stop-failure' in sys.argv
assert sum((negative, auto_release, child_failure, startup_failure, stop_failure)) <= 1
if auto_release:
    env['DSH_COMPONENT_EXPECT_AUTO_RELEASE'] = '1'
if negative:
    env['DSH_COMPONENT_EXPECT_REJECTION'] = '1'
if child_failure:
    env['DSH_COMPONENT_EXPECT_CHILD_FAILURE'] = '1'
if startup_failure:
    env['DSH_COMPONENT_EXPECT_STARTUP_FAILURE'] = '1'
if stop_failure:
    env['DSH_COMPONENT_EXPECT_STOP_FAILURE'] = '1'
parent_log = (fixture / 'parent.log').open('wb')
parent = subprocess.Popen([sys.executable, str(ROOT / 'tools/component-worker.py'), '--executable', hython,
                           '--directory', str(fixture / 'parent'), '--registry', str(registry),
                           '--memory-mb', '4096', '--threads', '2', '--startup-timeout', '90'],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=parent_log, text=True,
                          env=env, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    lines = queue.Queue()
    threading.Thread(target=lambda: lines.put(parent.stdout.readline()), daemon=True).start()
    record = json.loads(lines.get(timeout=100))['record']
    subprocess.run([node, str(ROOT / 'tools/tests/prepare-shared-host-fixture.mjs'), cli, env['DSH_HOME'], str(ROOT)],
                   cwd=ROOT, env=env, check=True, timeout=120, capture_output=True)
    for name in ('houdini', 'houdini-dev'):
        preset = fixture / 'home/.agent-presets' / name / 'agent.cordis.yml'
        content = preset.read_text(encoding='utf-8')
        content = content.replace('bridgeUrl: http://127.0.0.1:8765',
                                  'bridgeUrl: ' + json.dumps(record['bridge_url']))
        preset.write_text(content, encoding='utf-8')
    overlay = fixture / 'component.yml'
    config = {'python': str(fixture / 'missing-python.exe') if startup_failure else sys.executable,
              'houdini': hython, 'workerRoot': str(configured_workers), 'executorRegistry': str(registry),
              'gui': False, 'memoryMb': 4096, 'threads': 2, 'startupTimeoutSeconds': 90, 'maxWorkers': 2,
              'projectLocalWorkers': True}
    overlay.write_text('- insert:\n'
                       '    - id: component-executors\n      name: dsh-houdini/executor-host\n      config: '
                       + json.dumps({'executorRegistry': str(registry), 'requestTimeoutMs': 30000}) + '\n'
                       '    - id: component-host\n      name: dsh-houdini/component-host\n      config: '
                       + json.dumps(config) + '\n'
                       '    - id: component-fixture\n      name: '
                       + (ROOT / 'tools/tests/component-loop-fixture.mjs').as_uri() + '\n', encoding='utf-8')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    log = fixture / 'host.log'
    with log.open('wb') as stream:
        host = spawn_frontend([node, cli, 'web', '--patch', str(overlay), '--port', str(port), '--no-open'],
                              node=node, cwd=fixture, env=env, stdout=stream, stderr=subprocess.STDOUT,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    auth = DshWebSession(f'http://127.0.0.1:{port}', str(log), str(fixture / 'runtime.json'))
    def rpc(method, args):
        req = urllib.request.Request(f'http://127.0.0.1:{port}/api/{method}',
            data=json.dumps({'type': 'client-request', 'rpcId': str(uuid.uuid4()), 'method': method, 'payload': {'args': args}}).encode(),
            headers={'Content-Type': 'application/json'})
        with auth.open(req, timeout=30) as response:
            result = json.load(response)
        assert result['result']['ok'], result
        return result['result']['value']
    deadline = time.monotonic() + 90
    last_error = None
    while True:
        if host.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError('Host startup failed: ' + str(last_error) + '; inspect ' + str(log))
        try:
            auth.authorize(1); rpc('session/list', {'_request': {}}); break
        except Exception as error:
            last_error = type(error).__name__ + ': ' + str(error)
            time.sleep(.25)
    task = str(uuid.uuid4())
    rpc('session/create', {'request': {'sessionId': task, 'cwd': str(fixture / 'parent/workspace'), 'agentPreset': 'houdini'}})
    rpc('session/selectModel', {'request': {'sessionId': task, 'provider': 'component-fixture', 'model': 'fixture'}})
    rpc('houdiniTargets/select', {'input': {'sessionId': task, 'executorId': record['executor_id'],
        'registrationId': record['registration_id'], 'expectedHip': record['hip_path']}})
    rpc('session/prompt', {'request': {'sessionId': task, 'requestId': str(uuid.uuid4()), 'mode': 'queue',
                                     'content': [{'type': 'text', 'text': 'Run the two independent component fixtures.'}]}})
    deadline = time.monotonic() + 180
    if stop_failure:
        while not (outputs / 'stop-ready.json').exists():
            if time.monotonic() > deadline:
                raise RuntimeError('Component stop fault setup incomplete; inspect ' + str(fixture))
            time.sleep(.25)
        ready = json.loads((outputs / 'stop-ready.json').read_text())
        (workers / ready['failedChild'] / 'stop').touch(exist_ok=False)
        # Allow the owned worker to exit before asking Host for its checkpoint.
        time.sleep(2)
        rpc('session/prompt', {'request': {'sessionId': task, 'requestId': str(uuid.uuid4()), 'mode': 'queue',
                                         'content': [{'type': 'text', 'text': 'Inspect the injected worker-stop failure.'}]}})
    outcome = ('rejected.json' if negative else 'blocked.json' if child_failure else
               'startup-blocked.json' if startup_failure else 'stop-unknown.json' if stop_failure else 'assembled.json')
    while not (outputs / outcome).exists():
        if time.monotonic() > deadline:
            raise RuntimeError('Component loop incomplete; inspect ' + str(fixture))
        time.sleep(.25)
    if negative:
        assert json.loads((outputs / 'rejected.json').read_text()) == {'rejected': True, 'childRequests': 0}
        assert not list(workers.glob('*/workspace/part.dshcomponent'))
        print('PASS unpatched DSH rejected before child model request or component build')
    elif child_failure:
        blocked = json.loads((outputs / 'blocked.json').read_text())
        assert blocked['assembly'] is False
        assert blocked['error'] == 'missing/ambiguous/unconnected public output 1'
        assert len(set(blocked['accepted'])) == 2
        assert {blocked['failedChild'], blocked['survivingChild']} == set(blocked['accepted'])
        failed = workers / blocked['failedChild'] / 'workspace'
        surviving = workers / blocked['survivingChild'] / 'workspace'
        assert (failed / 'component.hip').exists() and not (failed / 'part.dshcomponent').exists()
        assert (surviving / 'part.dshcomponent').exists()
        assert not (outputs / 'assembled.json').exists()
        print('PASS native child failure notice, concise parent block report, surviving artifact and saved failed HIP; no assembly or external model request')
    elif startup_failure:
        blocked = json.loads((outputs / 'startup-blocked.json').read_text())
        assert blocked['childRequests'] == 0 and blocked['assembly'] is False
        assert 'ENOENT' in blocked['error'] or 'not found' in blocked['error'].lower()
        assert not list(workers.glob('*/workspace/component.hip'))
        assert not (outputs / 'assembled.json').exists()
        print('PASS worker startup error surfaced to parent before child model or assembly; no external model request')
    elif stop_failure:
        result = json.loads((outputs / 'stop-unknown.json').read_text())
        assert result['assembly'] is False
        assert result['failed']['stopped'] is True and result['failed']['checkpoint'] == 'unknown'
        assert result['surviving']['ok'] is True and result['surviving']['checkpoint'] == 'saved'
        assert len(list(workers.glob('*/workspace/part.dshcomponent'))) == 2
        assert not (outputs / 'assembled.json').exists()
        print('PASS abnormal owned worker exit remains checkpoint-unknown, sibling saves cleanly, both artifacts retained; no assembly or external model request')
    else:
        results = [json.loads(p.read_text()) for p in outputs.glob('*.json') if p.name not in ('assembled.json', 'released.json')]
        assert len({r['cwd'] for r in results}) == 2 and all(r['passed'] for r in results)
        assert all(Path(r['cwd']).is_relative_to(workers) for r in results)
        assert not configured_workers.exists()
        if auto_release:
            # The first finished turn must go idle before the Host's bounded grace period starts.
            time.sleep(35)
            rpc('session/prompt', {'request': {'sessionId': task, 'requestId': str(uuid.uuid4()), 'mode': 'queue',
                                            'content': [{'type': 'text', 'text': 'Check idle worker release.'}]}})
            deadline = time.monotonic() + 30
            while not (outputs / 'released.json').exists():
                if time.monotonic() > deadline:
                    raise RuntimeError('Idle worker release incomplete; inspect ' + str(fixture))
                time.sleep(.25)
            print('PASS completed parent turn released two idle owned Houdini workers with saved checkpoints')
        else:
            print('PASS real DSH two component children, independent directories/targets, Bridge export/import, assembly shared control and recovery; no external model requests')
finally:
    stop_owned()
    if parent.poll() is None:
        parent.stdin.write('STOP\n'); parent.stdin.flush()
        parent.wait(timeout=30)
    parent.stdin.close(); parent.stdout.close(); parent_log.close()
