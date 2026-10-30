"""Shared atomic JSON and native lease primitives; no app/runtime installation."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_deployment as state

with tempfile.TemporaryDirectory(prefix='dsh-plugin-state-') as temporary:
    root = Path(temporary)
    # Installing/selecting a newer helper cannot rewrite facts held by an
    # already running process, even if maintenance reloads this module.
    helper = root / 'helpers' / ('a' * 16)
    library = helper / 'houdini/python3.11libs'
    library.mkdir(parents=True)
    module_file = library / 'dsh_deployment.py'
    module_file.write_bytes((ROOT / 'houdini/python3.11libs/dsh_deployment.py').read_bytes())
    manifest = helper / 'package.json'
    manifest.write_text(json.dumps({'name': 'dsh-houdini', 'version': '0.0.1-fixture'}), encoding='utf-8')
    spec = importlib.util.spec_from_file_location('loaded_helper_fixture', module_file)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    expected_helper = {'id': 'a' * 16, 'version': '0.0.1-fixture'}
    assert loaded.loaded_helper() == expected_helper
    manifest.write_text(json.dumps({'name': 'dsh-houdini', 'version': '0.0.2-fixture'}), encoding='utf-8')
    with patch.dict(os.environ, {'DSH_HOUDINI_PATH': str(root / 'helpers' / ('b' * 16) / 'houdini')}):
        spec.loader.exec_module(loaded)
        with patch.object(Path, 'open', side_effect=AssertionError('loaded facts read disk')):
            assert loaded.loaded_helper() == expected_helper
            loaded.loaded_helper()['id'] = 'b' * 16
            assert loaded.loaded_helper() == expected_helper
    assert state.loaded_helper() == {'id': None, 'version': None}, 'source checkout is not an installed helper'
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
