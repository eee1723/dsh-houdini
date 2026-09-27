"""Two real disposable component workers; explicit IPC, no live or model calls."""
from pathlib import Path
import hashlib
import json
import queue
import subprocess
import sys
import tempfile
import threading
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment


def request(record, route, body=None):
    req = urllib.request.Request(record['bridge_url'] + route,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'X-DSH-Houdini-Executor': record['executor_id']})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


fixture = Path(tempfile.mkdtemp(prefix='dsh-component-workers-'))
processes = []
logs = []
try:
    records = []
    for index in range(2):
        log = (fixture / f'supervisor-{index}.log').open('wb')
        logs.append(log)
        process = subprocess.Popen([sys.executable, str(ROOT / 'tools/component-worker.py'),
                                    '--executable', sys.argv[1], '--directory', str(fixture / str(index)),
                                    '--registry', str(fixture / 'registry'), '--memory-mb', '4096',
                                    '--threads', '2', '--startup-timeout', '90',
                                    '--hip-name', 'component.hip' if index == 0 else 'final.hip']
                                   + (['--gui'] if '--gui' in sys.argv else []),
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True,
                                   env=isolated_environment(fixture / f'driver-{index}'),
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(process)
        lines = queue.Queue()
        threading.Thread(target=lambda p=process, q=lines: q.put(p.stdout.readline()), daemon=True).start()
        line = lines.get(timeout=100)
        assert line, 'supervisor exited; inspect ' + str(fixture)
        result = json.loads(line)
        assert result['ok']
        records.append(result['record'])
    assert records[0]['executor_id'] != records[1]['executor_id']
    assert records[0]['hip_path'] != records[1]['hip_path']
    assert Path(records[0]['hip_path']).name == 'component.hip'
    assert Path(records[1]['hip_path']).name == 'final.hip'
    assert records[0]['bridge_url'] != records[1]['bridge_url']
    for record in records:
        health = request(record, '/health')
        assert health['executorId'] == record['executor_id']
    final_record = records[1]
    initial_final_hash = hashlib.sha256(Path(final_record['hip_path']).read_bytes()).hexdigest()
    final_owner = 'final-hip-reservation-test'
    assert request(final_record, '/executor/claim', {'task_id': final_owner,
        'registration_id': final_record['registration_id'],
        'expected_hip': final_record['hip_path']})['ok']
    final_ticket = request(final_record, '/requests/prepare', {'owner_session': final_owner})
    final_code = ("g=tab_create('/obj','geo','final_probe')\n"
                  "b=tab_create(g,'box','shape')\n"
                  "__result__=scene_save(expected_path=" + repr(final_record['hip_path']) + ")")
    final_result = request(final_record, '/exec', {'owner_session': final_owner,
        'owner_call': 'save-final', 'request_ref': final_ticket['requestRef'],
        'expected_contract': {'version': final_ticket['executionContractVersion'],
                              'hash': final_ticket['verbCatalog']['hash']},
        'code': final_code})
    assert final_result['ok'], final_result.get('error')
    assert final_result['result']['path'] == final_record['hip_path']
    assert final_result['result']['bytes'] > 0, final_result
    assert Path(final_record['hip_path']).is_file()
    final_hash = hashlib.sha256(Path(final_record['hip_path']).read_bytes()).hexdigest()
    assert final_hash != initial_final_hash, 'explicit save did not replace the initial empty scene'
    wrong_target = str(Path(final_record['hip_path']).with_name('unreserved.hip'))
    wrong_ticket = request(final_record, '/requests/prepare', {'owner_session': final_owner})
    wrong_code = ("__result__=scene_save_as(path=" + repr(wrong_target)
                  + ",expected_current_path=" + repr(final_record['hip_path'])
                  + ",reason='isolated writer reservation negative test')")
    wrong_result = request(final_record, '/exec', {'owner_session': final_owner,
        'owner_call': 'reject-unreserved-save', 'request_ref': wrong_ticket['requestRef'],
        'expected_contract': {'version': wrong_ticket['executionContractVersion'],
                              'hash': wrong_ticket['verbCatalog']['hash']},
        'code': wrong_code})
    assert not wrong_result['ok'], wrong_result
    assert 'writer reservation' in wrong_result.get('error', '')
    assert not Path(wrong_target).exists()
    if '--gui' in sys.argv:
        record = records[0]
        owner = 'component-preview-test'
        assert request(record, '/executor/claim', {'task_id': owner,
            'registration_id': record['registration_id'], 'expected_hip': record['hip_path']})['ok']
        ticket = request(record, '/requests/prepare', {'owner_session': owner})
        result = request(record, '/exec', {'owner_session': owner, 'owner_call': 'preview',
            'request_ref': ticket['requestRef'], 'expected_contract': {'version': ticket['executionContractVersion'], 'hash': ticket['verbCatalog']['hash']},
            'code': "g=tab_create('/obj','geo','preview')\nb=tab_create(g,'box','shape')\n__result__=render_view(b,width=320,height=240)"})
        assert result['ok'], result.get('error')
        assert Path(result['result']['output']).is_file()
        print('PREVIEW:', result['result']['output'])
    processes[0].stdin.write('STOP\n'); processes[0].stdin.flush()
    assert processes[0].wait(timeout=25) == 0
    assert request(records[1], '/health')['executorId'] == records[1]['executor_id']
    assert Path(records[0]['hip_path']).is_file()
    processes[1].stdin.write('STOP\n'); processes[1].stdin.flush()
    assert processes[1].wait(timeout=25) == 0
    assert hashlib.sha256(Path(final_record['hip_path']).read_bytes()).hexdigest() == final_hash
    reopen_script = fixture / 'reopen-final.py'
    reopen_script.write_text(
        "import hou, sys\n"
        "hou.hipFile.load(sys.argv[1], suppress_save_prompt=True)\n"
        "shape = hou.node('/obj/final_probe/shape')\n"
        "assert shape is not None and shape.type().name() == 'box'\n"
        "print('REOPEN_OK')\n", encoding='utf-8')
    reopen_executable = (Path(sys.argv[1]).with_name('hython.exe')
                         if '--gui' in sys.argv else Path(sys.argv[1]))
    reopened = subprocess.run([str(reopen_executable), str(reopen_script), final_record['hip_path']],
                              env=isolated_environment(fixture / 'reopen-final'),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
    assert reopened.returncode == 0 and 'REOPEN_OK' in reopened.stdout, reopened.stdout
    assert hashlib.sha256(Path(final_record['hip_path']).read_bytes()).hexdigest() == final_hash
    print('PASS two component workers, unique HIP/identity/port, isolated stop; fixture:', fixture)
finally:
    for process in processes:
        if process.poll() is None:
            try:
                process.stdin.write('STOP\n'); process.stdin.flush()
            except OSError:
                pass  # supervisor closed its pipe during startup failure
            try:
                process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=15)
        if process.stdin:
            try:
                process.stdin.close()
            except OSError:
                pass  # already broken supervisor pipe
        if process.stdout:
            process.stdout.close()
    for log in logs:
        log.close()
