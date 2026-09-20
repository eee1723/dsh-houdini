"""Keyless real DSH composition with parent and two independently bound workers.

Arguments: node executable, patched DSH bin.js, hython executable.
Uses new data/registry/work directories and a deterministic adapter only.
"""
from pathlib import Path
import ctypes
import json
import os
import queue
import re
import signal
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

probe_selftest_only = '--probe-selftest' in sys.argv

# Windows-safe process probe. os.kill(pid, 0) is NOT a probe on Windows (any
# signal other than 0 unconditionally terminates the target), and OpenProcess
# alone proves nothing: it succeeds while ANY handle to a terminated process
# remains open. The probe therefore opens the process ONCE with the
# permission that matches the wait (SYNCHRONIZE), KEEPS that same handle, and
# answers the liveness question with WaitForSingleObject(handle, 0):
# WAIT_OBJECT_0 means the process has exited (the handle is signaled),
# WAIT_TIMEOUT means it is still running. Every ctypes signature is declared
# explicitly and every failure is read through GetLastError
# (ctypes.get_last_error via use_last_error=True). A query failure is
# reported as 'unknown' - never as death, never as permission to kill.
if os.name == 'nt':
    from ctypes import wintypes
    _KERNEL32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _KERNEL32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _KERNEL32.OpenProcess.restype = wintypes.HANDLE
    _KERNEL32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _KERNEL32.WaitForSingleObject.restype = wintypes.DWORD
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _KERNEL32.CloseHandle.restype = wintypes.BOOL
    _PROCESS_SYNCHRONIZE = 0x00100000
    _WAIT_OBJECT_0 = 0x00000000
    _WAIT_TIMEOUT = 0x00000102

PROBE_METHOD = ('OpenProcess(SYNCHRONIZE) once + WaitForSingleObject(handle, 0) '
                'on the same held handle')

class WindowsPidProbe:
    def __init__(self, pid):
        self.pid = pid
        self.open_error = None
        self.handle = None
        if os.name == 'nt':
            self.handle = _KERNEL32.OpenProcess(_PROCESS_SYNCHRONIZE, False, int(pid))
            self.open_error = ctypes.get_last_error()

    def state(self):
        """Return (state, detail): state in {'alive', 'exited', 'unknown'};
        detail carries the actual wait code and the GetLastError value."""
        if os.name != 'nt':
            try:
                os.kill(self.pid, 0)
                return 'alive', {'method': 'posix kill(pid, 0)'}
            except ProcessLookupError:
                return 'exited', {'method': 'posix kill(pid, 0)'}
            except OSError as error:
                return 'unknown', {'method': 'posix kill(pid, 0)', 'reason': 'probe failed',
                                   'lastError': int(error.errno or 0)}
        if not self.handle:
            return 'unknown', {'method': PROBE_METHOD, 'reason': 'OpenProcess failed',
                               'openError': self.open_error}
        code = _KERNEL32.WaitForSingleObject(self.handle, 0)
        last_error = ctypes.get_last_error()
        if code == _WAIT_OBJECT_0:
            return 'exited', {'method': PROBE_METHOD, 'waitCode': code, 'lastError': last_error}
        if code == _WAIT_TIMEOUT:
            return 'alive', {'method': PROBE_METHOD, 'waitCode': code, 'lastError': last_error}
        return 'unknown', {'method': PROBE_METHOD, 'reason': 'WaitForSingleObject failed',
                           'waitCode': code, 'lastError': last_error}

    def close(self):
        if os.name == 'nt' and self.handle:
            _KERNEL32.CloseHandle(self.handle)
            self.handle = None

def probe_selftest():
    """Three-case self-test. The third case (query failure / invalid handle)
    must report 'unknown' - it must never produce passing evidence."""
    # Case 1: own child, running.
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    probe = WindowsPidProbe(child.pid)
    state, detail = probe.state()
    assert state == 'alive', ('self-test: the running child must read alive', detail)
    # Case 2: the child has exited while the test still holds the SAME handle
    # opened before the exit (the OpenProcess-only pitfall).
    child.terminate()
    child.wait(10)
    state, detail = probe.state()
    assert state == 'exited', ('self-test: the exited child must read exited even with the handle held', detail)
    probe.close()
    # Case 3a: OpenProcess on a pid that no process owns - must be 'unknown'
    # with the error recorded, never 'exited'.
    ghost = WindowsPidProbe(0xDEADBEE0)
    state, detail = ghost.state()
    assert state == 'unknown' and detail.get('reason') == 'OpenProcess failed', (state, detail)
    # Case 3b: invalid handle passed to the wait - WAIT_FAILED, must be
    # 'unknown' with GetLastError (6, ERROR_INVALID_HANDLE), never a pass.
    # INVALID_HANDLE_VALUE itself is special-cased by WaitForSingleObject
    # (it is treated as the current process and times out), so the failure
    # case uses a 4-byte-unaligned value that cannot name a real handle in
    # this process.
    broken = WindowsPidProbe.__new__(WindowsPidProbe)
    broken.pid = 0
    broken.handle = 0x0000DEAD
    broken.open_error = None
    state, detail = broken.state()
    assert state == 'unknown' and detail.get('reason') == 'WaitForSingleObject failed' \
        and detail.get('lastError') == 6, (state, detail)

# The self-test runs in every invocation (cheap, self-contained evidence) and
# standalone via --probe-selftest, which exits after printing the result.
SELFTEST = probe_selftest()
print('probe self-test: OK (running child reads alive; exited child reads exited '
      'with the same held handle; OpenProcess failure reads unknown with its error; '
      'invalid handle reads unknown with GetLastError 6)', flush=True)
if probe_selftest_only:
    raise SystemExit(0)

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
    if built_exit:
        # R6 built-exit drill, driver-driven. The fixture parks the built
        # child at a synchronous hold point (built, saved, NOT exported, NOT
        # ended) and records the idle parent turn from real session events.
        # THIS driver - outside any model turn - verifies preconditions for
        # the real target AND for a completed-child counterexample, writes an
        # immutable arm record, kills, and only then writes the outcome.
        def atomic_write_json(path, doc):
            tmp = str(path) + '.tmp-' + str(os.getpid())
            with open(tmp, 'w', encoding='utf-8') as stream:
                json.dump(doc, stream, indent=1)
            os.replace(tmp, str(path))

        class PreconditionRejected(Exception):
            pass

        def session_items():
            return rpc('session/list', {'_request': {}}).get('items', [])

        def event_notices():
            snapshot = json.loads((outputs / 'built-exit-events.json').read_text(encoding='utf-8'))
            return [entry['notice'] for entry in snapshot if entry.get('notice')]

        def built_exit_preconditions(candidate_child, items, snap_notices, records):
            """One verifier for the real kill and the counterexample alike:
            every rejection names its reason, so the counterexample proves the
            gate is real instead of an assertion passing vacuously."""
            parent_item = next((i for i in items if i.get('sessionId') == task), None)
            if parent_item is None or parent_item.get('running') is not False:
                raise PreconditionRejected('the parent task must be observed idle at kill time')
            terminal = [n for n in snap_notices
                        if n.get('kind') == 'native' and n.get('childId') == candidate_child]
            if terminal:
                raise PreconditionRejected('the candidate child already has a terminal notice: '
                                           + json.dumps(terminal[0]))
            item = next((i for i in items if i.get('sessionId') == candidate_child), None)
            if item is None:
                raise PreconditionRejected('no session item for ' + candidate_child)
            if item.get('running') is not True:
                raise PreconditionRejected('the candidate child session is not running (already ended): '
                                           + json.dumps(item)[:240])
            record = next((r for r in records if r.get('task_id') == candidate_child), None)
            if not record or record.get('pid', 0) <= 0:
                raise PreconditionRejected('no registry record with a real pid for ' + candidate_child)
            if record.get('hip_path') != str(workers / candidate_child / 'workspace' / 'component.hip'):
                raise PreconditionRejected('registry hip_path does not match the built workspace: '
                                           + json.dumps(record))
            return record, item

        while not ((outputs / 'built-exit-idle.json').exists() and (outputs / 'built-hold.json').exists()):
            if time.monotonic() > deadline:
                raise RuntimeError('built-exit sync point never reached; inspect ' + str(fixture))
            time.sleep(.25)
        idle_doc = json.loads((outputs / 'built-exit-idle.json').read_text(encoding='utf-8'))
        assert idle_doc['endedTextOnly'] is True and idle_doc['outstandingSyntheticCalls'] is False, idle_doc
        assert idle_doc.get('idleTurn') is not None, 'the idle turn must come from a real turn/start event'
        hold_doc = json.loads((outputs / 'built-hold.json').read_text(encoding='utf-8'))
        built_child = hold_doc['child']
        assert not (outputs / (built_child + '.json')).exists(), 'the built child must not have published a record'
        # The counterexample needs the survivor's terminal notice in the
        # session event snapshot: wait for the survivor's published record and
        # its settlement to be on the record.
        survivor_child = None
        while survivor_child is None:
            if time.monotonic() > deadline:
                raise RuntimeError('the survivor never published; inspect ' + str(fixture))
            published = [p for p in outputs.glob('*.json') if re.fullmatch(r'[0-9a-f-]{36}', p.stem)]
            if len(published) == 1:
                candidate = published[0].stem
                try:
                    notices = event_notices()
                except FileNotFoundError:
                    notices = []
                if any(n.get('childId') == candidate and n.get('outcome') == 'finished and will do no further work'
                       for n in notices):
                    survivor_child = candidate
            time.sleep(.25)
        assert survivor_child != built_child, (survivor_child, built_child)
        # Observe the sessions: the parent task idle, the target child STILL
        # running at its hold point.
        while True:
            items = session_items()
            parent_item = next((i for i in items if i.get('sessionId') == task), None)
            child_item = next((i for i in items if i.get('sessionId') == built_child), None)
            if (parent_item is not None and parent_item.get('running') is False
                    and child_item is not None and child_item.get('running') is True):
                break
            if time.monotonic() > deadline:
                raise RuntimeError('the parent never settled idle or the child left its hold; inspect ' + str(fixture))
            time.sleep(.25)
        snap_notices = event_notices()
        assert not any(n.get('childId') == built_child for n in snap_notices), \
            'the target child must have no terminal event before the kill: ' + json.dumps(snap_notices)[:400]
        # Registry-bound identity for the REAL target, through the shared
        # verifier.
        records = [json.loads(p.read_text(encoding='utf-8')) for p in (registry / 'endpoints').glob('*.json')]
        worker_record, child_item = built_exit_preconditions(built_child, items, snap_notices, records)
        pid = worker_record['pid']
        # The kill authorization rests on a CONFIRMED-alive probe. The same
        # handle stays open from this precondition through the post-kill
        # polls; a query failure ('unknown') never authorizes the kill.
        probe = WindowsPidProbe(pid)
        pre_state, pre_detail = probe.state()
        if pre_state != 'alive':
            probe.close()
            raise RuntimeError('the worker pid must read alive through the '
                               + PROBE_METHOD + ' before any kill; got '
                               + json.dumps({'state': pre_state, **pre_detail}))
        # Counterexample: the SAME verifier must REJECT the completed child
        # (the survivor has settled) instead of passing vacuously.
        try:
            built_exit_preconditions(survivor_child, items, snap_notices, records)
            raise AssertionError('the completed-child counterexample must be rejected by the preconditions')
        except PreconditionRejected as rejection:
            counterexample_reason = str(rejection)
        # Immutable arm record, written atomically BEFORE the kill.
        arm_doc = {
            'armedAt': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'killBy': 'test-driver: os.kill(SIGTERM) outside any model turn',
            'killAuthorized': True,
            'target': {'builtChild': built_child, 'pid': pid,
                       'record': {key: worker_record.get(key) for key in
                                  ('task_id', 'pid', 'hip_path', 'executor_id', 'registration_id')}},
            'preconditions': {
                'parentSession': {'sessionId': task, 'running': parent_item.get('running')},
                'childSession': {'sessionId': built_child, 'running': child_item.get('running')},
                'terminalEventsForChildCount': 0,
                'idleMarker': idle_doc,
                'pidProbe': {'method': PROBE_METHOD, 'state': pre_state, 'detail': pre_detail,
                             'handleHeldThroughKill': True}},
            'negativeControl': {'input': survivor_child,
                                'inputClass': 'target child task already completed (settled)',
                                'rejected': True, 'reason': counterexample_reason}}
        atomic_write_json(outputs / 'built-exit-arm.json', arm_doc)
        # The kill, outside any model turn.
        kill_error = None
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as error:
            kill_error = str(error)
        # Poll the SAME held handle after the kill. Only WAIT_OBJECT_0
        # (state 'exited') confirms death; an 'unknown' poll is recorded as
        # unknown and never counted as a death confirmation.
        polls = []
        final_state = None
        for _ in range(60):
            state, detail = probe.state()
            polls.append({'state': state, **detail})
            if state != 'unknown':
                final_state = state
                if state == 'exited':
                    break
            time.sleep(.1)
        probe.close()
        # Separate outcome record, written AFTER the kill, carrying the
        # actual probe method, the returned states and the error codes.
        outcome_doc = {'pidDead': final_state == 'exited', 'killError': kill_error,
                       'probe': {'method': PROBE_METHOD, 'handleHeldThroughKill': True,
                                 'finalState': final_state, 'polls': polls},
                       'confirmedAt': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
        atomic_write_json(outputs / 'built-exit-outcome.json', outcome_doc)
        assert kill_error is None and final_state == 'exited', (kill_error, outcome_doc)
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
        arm_doc = json.loads((outputs / 'built-exit-arm.json').read_text(encoding='utf-8'))
        outcome_doc = json.loads((outputs / 'built-exit-outcome.json').read_text(encoding='utf-8'))
        # Driver-owned fault control: immutable arm before the kill, separate
        # outcome after it, and the report carries both verbatim.
        assert arm_doc['killBy'].startswith('test-driver'), arm_doc
        assert arm_doc['killAuthorized'] is True, arm_doc
        assert arm_doc['target']['record']['task_id'] == arm_doc['target']['builtChild'], arm_doc
        assert arm_doc['preconditions']['parentSession']['running'] is False, arm_doc['preconditions']
        assert arm_doc['preconditions']['childSession']['running'] is True, arm_doc['preconditions']
        assert arm_doc['preconditions']['terminalEventsForChildCount'] == 0, arm_doc['preconditions']
        assert arm_doc['negativeControl']['rejected'] is True, arm_doc['negativeControl']
        assert arm_doc['negativeControl']['input'] != arm_doc['target']['builtChild'], arm_doc['negativeControl']
        assert 'terminal notice' in arm_doc['negativeControl']['reason'], arm_doc['negativeControl']
        assert outcome_doc['pidDead'] is True and outcome_doc['killError'] is None, outcome_doc
        assert report['arm'] == arm_doc and report['outcome'] == outcome_doc, report
        assert report['builtChild'] == arm_doc['target']['builtChild'], report
        assert report['pid'] == arm_doc['target']['pid'], report
        # Real event identity: the idle turn from a real turn/start event, the
        # status turn from the exact built-exit-status call event, real seq,
        # time and callId; array positions only ever labeled index.
        assert isinstance(report['idleTurn'], int) and isinstance(report['statusTurn'], int), report
        assert report['statusTurn'] > report['idleTurn'], ('the checkpoint inspection must run in a later real turn', report)
        assert report['statusCall']['callId'] and isinstance(report['statusCall']['seq'], int), report['statusCall']
        # The notices keep childId and outcome, and BOTH kinds are on the
        # record with their persistent seq/time.
        notices = report['noticesByReportTime']
        infra = [n for n in notices if n['kind'] == 'infrastructure' and n['childId'] == report['builtChild']]
        native = [n for n in notices if n['kind'] == 'native' and n['childId'] == report['builtChild']]
        assert infra and all(isinstance(n['seq'], int) and n['time'] for n in infra), notices
        assert native and native[0]['outcome'] == 'failed before it finished', notices
        assert report['statusCall']['seq'] > min(n['seq'] for n in notices), \
            'the checkpoint inspection must follow the first notice in the persistent event order'
        assert 'unique cause' in report['wakePathNote'], report['wakePathNote']
        assert report['status']['failed']['workerStatus'] == 'stopped'
        assert report['status']['failed']['checkpoint'] == 'unknown'
        assert report['status']['surviving']['workerStatus'] == 'ready'
        assert report['artifacts'] == {'builtHip': True, 'builtMarker': True, 'failedArtifact': False, 'survivorArtifact': True}, report
        assert report['delegateCalls'] == 2 and report['assembly'] is False, report
        for entry in report['eventOrder']:
            assert isinstance(entry['index'], int) and isinstance(entry['seq'], int) and entry['time'], entry
        sessions = rpc('session/list', {'_request': {}})
        child_sessions = [item for item in sessions.get('items', []) if item.get('origin') == 'subagent']
        assert len(child_sessions) == 2,             'no replacement dispatch may follow the built-exit kill: ' + str(len(child_sessions))
        assert not (outputs / 'assembled.json').exists()
        print('PASS real worker exit while built-not-exported, driver-driven with real-event forensics:')
        print('     the driver observed the idle parent (running=false) and the target child still')
        print('     running with no terminal event, verified the registry identity and REJECTED the')
        print('     completed-child counterexample through the same verifier before killing outside')
        print('     any model turn; the notices (Host infrastructure + native child failure) are on')
        print('     the record with childId, outcome, persistent seq and time; the checkpoint')
        print('     inspection is attributed to its exact call event (seq %s, callId %s, turn %s,' % (
            report['statusCall']['seq'], report['statusCall']['callId'], report['statusTurn']))
        print('     idle turn %s); failed stopped/unknown vs ready survivor, nothing exported, no' % report['idleTurn'])
        print('     re-dispatch, no assembly - sequential appearance reported, not claimed as a unique cause')
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
        results = [json.loads(p.read_text(encoding='utf-8')) for p in outputs.glob('*.json') if p.name not in ('assembled.json', 'released.json', 'parent-turns.json', 'module-source.json', 'rejection-reason.json', 'adapter-throw.json', 'process-exit.json', 'process-exit-kill.json', 'built-exit.json', 'built-exit-arm.json', 'built-exit-outcome.json', 'built-exit-idle.json', 'built-exit-events.json', 'built-exit-trace.jsonl', 'built-exit-error.json', 'built-exit-kill.json', 'built-exit-armed.json', 'built-hold.json', 'built-exit-event-sample.json', 'parent-idle.json', 'process-exit-error.json', 'process-exit-debug.json')]
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
