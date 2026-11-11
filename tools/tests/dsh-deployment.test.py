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
        import ctypes
        from ctypes import wintypes
        from types import SimpleNamespace
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        native_replace = kernel.ReplaceFileW
        native_replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR,
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
        native_replace.restype = wintypes.BOOL

        class Replacement:
            def __init__(self, code, failures=1):
                self.code, self.failures, self.calls = code, failures, []
            def __call__(self, destination, temporary, *rest):
                self.calls.append((destination, temporary))
                if self.failures is None or len(self.calls) <= self.failures:
                    ctypes.set_last_error(self.code)
                    return False
                return native_replace(destination, temporary, *rest)

        for code in (32, 33, 1175):
            replacement = Replacement(code)
            with patch.object(ctypes, 'WinDLL', return_value=SimpleNamespace(ReplaceFileW=replacement)):
                state.atomic_json(target, {'safe_retry': code})
            assert len(replacement.calls) == 2 and len(set(replacement.calls)) == 1
            assert state.read_json(target) == {'safe_retry': code}

        for code in (5, 1176, 1177):
            previous = target.read_bytes()
            replacement = Replacement(code, failures=None)
            with patch.object(ctypes, 'WinDLL', return_value=SimpleNamespace(ReplaceFileW=replacement)):
                try:
                    state.atomic_json(target, {'must_not_retry': code})
                except OSError as error:
                    assert error.winerror == code
                else:
                    raise AssertionError('A non-retryable publication error was hidden')
            assert len(replacement.calls) == 1 and target.read_bytes() == previous

        # A persistent sharing failure keeps the original error and has one
        # deadline, not a fresh budget per attempt. No wall-clock flakiness.
        clock = [0.0]
        replacement = Replacement(32, failures=None)
        previous = target.read_bytes()
        with patch.object(ctypes, 'WinDLL', return_value=SimpleNamespace(ReplaceFileW=replacement)), \
             patch.object(state.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(state.time, 'sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            try:
                state.atomic_json(target, {'blocked': True})
            except OSError as error:
                assert error.winerror == 32 and error.filename2 == str(target)
            else:
                raise AssertionError('Permanent publication failure was hidden')
        assert .05 <= clock[0] <= .051 and len(replacement.calls) > 1
        assert len(set(replacement.calls)) == 1 and target.read_bytes() == previous

        # Real Windows reader denies deletion. Release it only after the first
        # actual sharing failure, then require the same publication to finish.
        blocked = threading.Event()
        real_attempts = []
        def traced_replace(*arguments):
            result = native_replace(*arguments)
            code = ctypes.get_last_error()
            real_attempts.append(code if not result else 0)
            if not result and code in (32, 33, 1175):
                blocked.set()
            return result
        failures = []
        def publish_after_reader():
            try:
                state.atomic_json(target, {'reader_released': True})
            except BaseException as error:
                failures.append(error)
        with patch.object(ctypes, 'WinDLL', return_value=SimpleNamespace(ReplaceFileW=traced_replace)):
            reader = target.open('rb')
            thread = threading.Thread(target=publish_after_reader)
            try:
                thread.start()
                assert blocked.wait(2), 'The real reader did not exercise a sharing conflict'
            finally:
                reader.close()
                thread.join(timeout=2)
        assert not thread.is_alive() and not failures, failures
        assert real_attempts[0] in (32, 33, 1175) and real_attempts[-1] == 0
        assert state.read_json(target) == {'reader_released': True}
        print('Windows publication retries only safe name-preserving failures within one 50ms deadline')

print('Atomic plugin state snapshots, bounded reads and cross-process lease exclusion passed')
