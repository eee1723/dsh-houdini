"""CLI consumers see every case even when native HDA inventories are large."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('delivery', ROOT / 'tools/hda-delivery-check.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

inventory = [{'path': f'/obj/case/native/internal_{i}', 'type': 'parameter',
              'source': 'Internal', 'library': None} for i in range(4500)]
report = {'ok': False, 'exit_code': 1, 'scope': 'declared geometry only', 'cases': [
    {'id': f'case-{i}', 'ok': i != 2, 'node_definitions': inventory,
     'geometry': {'points': 8, 'bounds_size': [1, 1, 1]},
     **({'error': 'late callback failure', 'cleanup_error': 'cleanup incomplete',
         'callback_diagnostics': 'native callback stderr',
         'future_diagnostic': {'unverified': ['unmeasured relation']}} if i == 2 else {})}
    for i in range(4)], 'worker': {'status': 'completed', 'returncode': 1,
                                  'released': True, 'output': 'worker diagnostic'}}
before = json.dumps(report)

with tempfile.TemporaryDirectory(prefix='dsh-hda-report-') as temporary:
    target = Path(temporary) / '完整 evidence.json'
    arguments = ['hda-delivery-check.py', '--manifest', str(Path(temporary) / 'manifest.json'),
                 '--hython', str(Path(temporary) / 'hython.exe'), '--output', str(target)]
    stdout = io.StringIO()
    with patch.object(sys, 'argv', arguments), patch.object(runner, 'check', return_value=report), contextlib.redirect_stdout(stdout):
        assert runner.main() == 1, 'a later failed case must retain the failing CLI exit'
    summary = json.loads(stdout.getvalue())
    assert len(stdout.getvalue()) < 6000, 'ordinary native inventories must not consume the stdout limit'
    assert json.loads(target.read_bytes()) == report
    assert summary['report']['sha256'] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert summary['report']['bytes'] == target.stat().st_size
    assert summary['report']['path'] == str(target.resolve())
    for index, (actual, expected) in enumerate(zip(summary['cases'], report['cases'])):
        pointer = actual['node_definitions']['detail_pointer']
        resolved = report
        for token in pointer.split('/')[1:]:
            resolved = resolved[int(token)] if isinstance(resolved, list) else resolved[token]
        assert resolved == inventory and actual['node_definitions']['count'] == len(resolved)
        assert {k: v for k, v in actual.items() if k != 'node_definitions'} == {
            k: v for k, v in expected.items() if k != 'node_definitions'}
    assert summary['worker'] == report['worker']
    assert json.loads(runner.write_report(report)) == report, 'no archive keeps full inline evidence'
    assert json.dumps(report) == before, 'projection must not mutate canonical results'
    failure = {'ok': False, 'error': 'worker produced no report',
               'worker': {'status': 'timed_out', 'returncode': 1, 'output': 'timeout diagnostic'}}
    projected = json.loads(runner.write_report(failure, target))
    assert {k: v for k, v in projected.items() if k != 'report'} == failure
    try:
        runner.write_report(report, Path(temporary))
    except OSError:
        pass
    else:
        raise AssertionError('archive failure must not publish an inaccessible inventory reference')

print('PASS HDA CLI summary: all cases, late failure, unknown diagnostics, archive hash/pointers and write failure')
