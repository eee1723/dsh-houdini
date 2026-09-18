"""Keyless real DSH composition with parent and two independently bound workers.

Arguments: node executable, patched DSH bin.js, hython executable.
Uses new data/registry/work directories and a deterministic adapter only.
"""
from pathlib import Path
import json
import queue
import re
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
adapter_throw = '--expect-adapter-throw' in sys.argv
process_exit = '--expect-worker-process-exit' in sys.argv
built_exit = '--expect-built-exit' in sys.argv
assert sum((negative, auto_release, child_failure, startup_failure, stop_failure, adapter_throw, process_exit, built_exit)) <= 1
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
if adapter_throw:
    env['DSH_COMPONENT_EXPECT_ADAPTER_THROW'] = '1'
if process_exit:
    env['DSH_COMPONENT_EXPECT_WORKER_PROCESS_EXIT'] = '1'
if built_exit:
    env['DSH_COMPONENT_EXPECT_BUILT_EXIT'] = '1'
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
        ready = json.loads((outputs / 'stop-ready.json').read_text(encoding='utf-8'))
        (workers / ready['failedChild'] / 'stop').touch(exist_ok=False)
        # Allow the owned worker to exit before asking Host for its checkpoint.
        time.sleep(2)
        rpc('session/prompt', {'request': {'sessionId': task, 'requestId': str(uuid.uuid4()), 'mode': 'queue',
                                         'content': [{'type': 'text', 'text': 'Inspect the injected worker-stop failure.'}]}})
    outcome = ('rejected.json' if negative else 'blocked.json' if child_failure else
               'startup-blocked.json' if startup_failure else 'stop-unknown.json' if stop_failure else
               'adapter-throw.json' if adapter_throw else
               'process-exit.json' if process_exit else
               'built-exit.json' if built_exit else 'assembled.json')
    while not (outputs / outcome).exists():
        if time.monotonic() > deadline:
            raise RuntimeError('Component loop incomplete; inspect ' + str(fixture))
        time.sleep(.25)
    if negative:
        rejected_doc = json.loads((outputs / 'rejected.json').read_text(encoding='utf-8'))
        assert rejected_doc['rejected'] is True and rejected_doc['childRequests'] == 0, rejected_doc
        # R6: pin the PRECISE cause. The official runtime admits the continuable
        # descriptor but refuses the delegation at child admission because the
        # candidate component-host pre-step never bound the child executor.
        turn_error = [e['detail'] for e in rejected_doc['events'] if '"kind":"error"' in e['detail']]
        assert any('no executor binding' in detail for detail in turn_error), turn_error
        assert not list(workers.glob('*/workspace/part.dshcomponent'))
        source_doc = json.loads((outputs / 'module-source.json').read_text(encoding='utf-8'))
        sessions = rpc('session/list', {'_request': {}})
        reason_doc = {'reason': json.dumps(sessions)[:1500], 'childRequests': 0}
        print('PASS unpatched DSH rejected before child model request or component build')
        print('rejection reason:', reason_doc['reason'][:300])
        print('loaded module source:', json.dumps(source_doc)[:300])
    elif adapter_throw:
        report = json.loads((outputs / 'adapter-throw.json').read_text(encoding='utf-8'))
        assert report['outcome'] in ('failed before it finished', 'ended abnormally'), report
        assert report['assembled'] is False, report
        assert report['sessionEvents'], 'the throw must surface as an actual session event'
        # childId-bound acceptance: the notice names the exact child; ITS
        # finished authoring work (built HIP + exported artifact) is retained
        # because the throw hit the model boundary only, the OTHER child owns
        # its artifact too, and the failed child's worker process is alive.
        failed_workspace = workers / report['failedChild'] / 'workspace'
        survivor_workspace = workers / report['survivorChild'] / 'workspace'
        assert (failed_workspace / 'component.hip').exists(), report
        assert (failed_workspace / 'part.dshcomponent').exists(), report
        assert (survivor_workspace / 'part.dshcomponent').exists(), report
        assert report['workerStillAlive'] is True,             'an adapter throw must not stop the worker process: ' + str(report)
        sessions = rpc('session/list', {'_request': {}})
        child_sessions = [item for item in sessions.get('items', []) if item.get('origin') == 'subagent']
        assert len(child_sessions) == 2,             'exactly the two dispatched children may exist; no replacement dispatch after the adapter throw: ' + str(len(child_sessions))
        artifacts = list(workers.glob('*/workspace/part.dshcomponent'))
        assert len(artifacts) == 2,             'both children finished authoring; both artifacts are retained: ' + str(artifacts)
        print('PASS injected child model-adapter throw after authoring, bound to the failed childId:')
        print('     the parent received the native failure notice, the failed child keeps its')
        print('     built HIP and retained artifact (the throw hit the model boundary only),')
        print('     its worker process stays alive, the surviving child owns its artifact, and')
        print('     exactly two child sessions existed (no replacement dispatch); assembly never ran')
    elif process_exit:
        report = json.loads((outputs / 'process-exit.json').read_text(encoding='utf-8'))
        kill_doc = json.loads((outputs / 'process-exit-kill.json').read_text(encoding='utf-8'))
        assert report['pid'] == kill_doc['pid'] and report['failedChild'] == kill_doc['failedChild'], report
        assert report['survivorPid'] == kill_doc['survivorPid'], report
        assert report['infraEvent'] and report['infraEvent']['source'].get('plugin') == 'dsh-houdini', report
        assert 'blocked' in report['infraEvent']['text'] and report['failedChild'] in report['infraEvent']['text'], report['infraEvent']
        assert report['status']['failed']['workerStatus'] == 'stopped'
        assert report['status']['failed']['checkpoint'] == 'unknown'
        assert report['status']['surviving']['workerStatus'] == 'ready'
        assert report['artifacts'] == {'failed': True, 'surviving': True}, report
        assert report['delegateCalls'] == 2 and report['assembly'] is False, report
        sessions = rpc('session/list', {'_request': {}})
        child_sessions = [item for item in sessions.get('items', []) if item.get('origin') == 'subagent']
        assert len(child_sessions) == 2,             'no replacement dispatch may follow a real worker process exit: ' + str(len(child_sessions))
        assert not (outputs / 'assembled.json').exists()
        print('PASS real worker process exit by registry-bound pid: the parent session holds the')
        print('     dsh-houdini infrastructure notice for the exact childId, the childId-bound')
        print('     status snapshot reports stopped/unknown while the survivor stays ready, and')
        print('     both artifacts are retained; no replacement dispatch, assembly never ran')
    elif built_exit:
        report = json.loads((outputs / 'built-exit.json').read_text(encoding='utf-8'))
        kill_doc = json.loads((outputs / 'built-exit-kill.json').read_text(encoding='utf-8'))
        assert report['builtChild'] == kill_doc['builtChild'] and report['pid'] == kill_doc['pid'], report
        assert kill_doc['killError'] is None and kill_doc['pidDead'] is True and kill_doc['parentIdleAtKill'] is True, kill_doc
        assert report['wake']['prevTurnTextOnly'] is True, report
        assert report['wake']['statusCallIndex'] > report['wake']['noticeEventIndex'] >= 0, report
        assert report['status']['failed']['workerStatus'] == 'stopped'
        assert report['status']['failed']['checkpoint'] == 'unknown'
        assert report['status']['surviving']['workerStatus'] == 'ready'
        assert report['artifacts'] == {'builtHip': True, 'builtMarker': True, 'failedArtifact': False, 'survivorArtifact': True}, report
        assert report['delegateCalls'] == 2 and report['assembly'] is False, report
        sessions = rpc('session/list', {'_request': {}})
        child_sessions = [item for item in sessions.get('items', []) if item.get('origin') == 'subagent']
        assert len(child_sessions) == 2,             'no replacement dispatch may follow the built-exit kill: ' + str(len(child_sessions))
        assert not (outputs / 'assembled.json').exists()
        print('PASS real worker exit while built-not-exported with the parent idle: the kill by')
        print('     registry-bound pid succeeded, the dsh-houdini infrastructure notice woke the')
        print('     idle parent as an actual session event before the childId-bound checkpoint')
        print('     inspection (stopped/unknown vs ready survivor), the built HIP and marker are')
        print('     retained with no artifact; no replacement dispatch, assembly never ran')
    elif child_failure:
        blocked = json.loads((outputs / 'blocked.json').read_text(encoding='utf-8'))
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
        blocked = json.loads((outputs / 'startup-blocked.json').read_text(encoding='utf-8'))
        assert blocked['childRequests'] == 0 and blocked['assembly'] is False
        assert 'ENOENT' in blocked['error'] or 'not found' in blocked['error'].lower()
        assert not list(workers.glob('*/workspace/component.hip'))
        assert not (outputs / 'assembled.json').exists()
        print('PASS worker startup error surfaced to parent before child model or assembly; no external model request')
    elif stop_failure:
        result = json.loads((outputs / 'stop-unknown.json').read_text(encoding='utf-8'))
        assert result['assembly'] is False
        assert result['failed']['stopped'] is True and result['failed']['checkpoint'] == 'unknown'
        assert result['surviving']['ok'] is True and result['surviving']['checkpoint'] == 'saved'
        assert len(list(workers.glob('*/workspace/part.dshcomponent'))) == 2
        assert not (outputs / 'assembled.json').exists()
        print('PASS abnormal owned worker exit remains checkpoint-unknown, sibling saves cleanly, both artifacts retained; no assembly or external model request')
    else:
        results = [json.loads(p.read_text(encoding='utf-8')) for p in outputs.glob('*.json') if p.name not in ('assembled.json', 'released.json', 'parent-turns.json', 'module-source.json', 'rejection-reason.json', 'adapter-throw.json', 'process-exit.json', 'process-exit-kill.json', 'built-exit.json', 'built-exit-kill.json', 'built-exit-armed.json', 'built-exit-error.json', 'process-exit-error.json', 'process-exit-debug.json')]
        assert len({r['cwd'] for r in results}) == 2 and all(r['passed'] for r in results)
        assert all(Path(r['cwd']).is_relative_to(workers) for r in results)
        assert not configured_workers.exists()
        # 54/54 pairing evidence: the Host the CLI actually loaded (resolved in
        # the fresh isolated profile) must carry the same execution-contract
        # version as the Bridge that ran the composition.
        source_doc = json.loads((outputs / 'module-source.json').read_text(encoding='utf-8'))
        bridge_version = int(re.search(r'_EXECUTION_CONTRACT_VERSION\s*=\s*(\d+)',
                                       (ROOT / 'houdini/python3.11libs/dsh_bridge.py').read_text(encoding='utf-8')).group(1))
        assert source_doc.get('host', {}).get('hostContractVersion') == bridge_version, \
            ('host/bridge contract mismatch', source_doc.get('host'), bridge_version)
        print('pairing: host contract %s == bridge contract %s (plugin %s, subagent %s)' % (
            source_doc['host']['hostContractVersion'], bridge_version,
            source_doc['host'].get('package'), source_doc.get('version')))
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
