"""Shared atomic JSON and native lease primitives; no app/runtime installation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_deployment as state

with tempfile.TemporaryDirectory(prefix='dsh-plugin-state-') as temporary:
    root = Path(temporary)
    target = root / 'state.json'
    state.atomic_json(target, {'sequence': 0, 'payload': 'fixture' * 1000})
    failures = []
    def writer():
        try:
            for sequence in range(1, 30):
                state.atomic_json(target, {'sequence': sequence, 'payload': 'fixture' * 1000})
        except Exception as error:
            failures.append(error)
    thread = threading.Thread(target=writer)
    thread.start()
    while thread.is_alive():
        value = state.read_json(target)
        assert 0 <= value['sequence'] <= 29 and value['payload'] == 'fixture' * 1000
    thread.join()
    assert not failures, failures
    assert state.read_json(target)['sequence'] == 29
    try:
        state.read_json(target, limit=10)
    except ValueError:
        pass
    else:
        raise AssertionError('oversized state was accepted')
    lock = root / 'process.lock'
    command = [sys.executable, '-B', '-c',
               'import sys;sys.path.insert(0,sys.argv[1]);from dsh_deployment import FileLease;from pathlib import Path;FileLease(Path(sys.argv[2])).close()',
               str(ROOT / 'houdini/python3.11libs'), str(lock)]
    with state.FileLease(lock):
        assert subprocess.run(command, capture_output=True, timeout=15).returncode != 0
    assert subprocess.run(command, capture_output=True, timeout=15).returncode == 0
    if os.name == 'nt':
        assert state._process_started(os.getpid())

print('Atomic plugin state snapshots, bounded reads and cross-process lease exclusion passed')
