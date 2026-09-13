"""Two real disposable component workers; explicit IPC, no live or model calls."""
from pathlib import Path
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
                                    '--threads', '2', '--startup-timeout', '90'] + (['--gui'] if '--gui' in sys.argv else []),
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
    assert records[0]['bridge_url'] != records[1]['bridge_url']
    for record in records:
        health = request(record, '/health')
        assert health['executorId'] == record['executor_id']
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
