"""Test runners must not inherit another Houdini/DSH installation's state."""
from pathlib import Path
import os
import runpy
import json
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
contaminated = dict(os.environ, HOUDINI_PACKAGE_DIR='foreign-packages',
                    PYTHONPATH='foreign-python', PYTHONHOME='foreign-home',
                    HSITE='foreign-site', HFS='foreign-houdini',
                    QT_PLUGIN_PATH='foreign-qt', QTWEBENGINE_DISABLE_SANDBOX='1',
                    DSH_HOME='foreign-dsh', DSH_HOUDINI_MANAGED_CONTEXT='foreign-context',
                    NODE_OPTIONS='--require foreign.js', EXAMPLE_API_KEY='test-only-placeholder',
                    HOUDINI_LICENSE_SERVER='test-license-host')
calls = []
def record_run(args, **kwargs):
    calls.append(kwargs)
    return subprocess.CompletedProcess(args, 0, '', '')
with patch.dict(os.environ, contaminated, clear=True), \
     patch.object(sys, 'argv', ['run-deployment-tests.py']), \
     patch.object(subprocess, 'run', side_effect=record_run):
    runpy.run_path(str(ROOT / 'tools/run-deployment-tests.py'), run_name='__main__')
assert calls
for call in calls:
    env = call['env']
    for key in ('PYTHONPATH', 'PYTHONHOME', 'HSITE', 'HFS', 'QT_PLUGIN_PATH',
                'QTWEBENGINE_DISABLE_SANDBOX', 'DSH_HOUDINI_MANAGED_CONTEXT',
                'NODE_OPTIONS', 'EXAMPLE_API_KEY'):
        assert key not in env, f'test runner inherited {key}'
    assert env['HOUDINI_PACKAGE_DIR'] != 'foreign-packages'
    assert env['DSH_HOME'] != 'foreign-dsh'
    assert env['HOUDINI_LICENSE_SERVER'] == 'test-license-host'
print('deployment runner rejects inherited Houdini/Python/Qt/DSH configuration')

from houdini_test_environment import isolated_environment, launch_directory
with tempfile.TemporaryDirectory(prefix='dsh-env-中文 空格-') as raw:
    fixture = Path(raw)
    inherited = {**contaminated, 'pythonpath': 'case-alias', 'dsh_home': 'case-alias',
                 'QT_QPA_PLATFORM': 'offscreen', 'QTWEBENGINE_CHROMIUM_FLAGS': '--no-sandbox',
                 'Path': 'fixture-path'}
    before = dict(inherited)
    env = isolated_environment(fixture / 'gui', executable=sys.executable, gui=True, base=inherited)
    assert inherited == before, 'must not mutate caller environment'
    assert env['HFS'] == str(Path(sys.executable).resolve().parent.parent)
    assert Path(env['HOUDINI_PACKAGE_DIR']).is_dir()
    assert env['HOUDINI_USER_PREF_DIR'].endswith('prefs__HVER__')
    assert 'QT_QPA_PLATFORM' not in env and 'QTWEBENGINE_CHROMIUM_FLAGS' not in env
    assert 'pythonpath' not in env and 'dsh_home' not in env
    assert sum(k.upper() == 'PATH' for k in env) == 1
    assert launch_directory(sys.executable) == Path(sys.executable).resolve().parent

    # Under licensed hython, verify actual startup, not only dictionary shape.
    if Path(sys.executable).stem.lower() == 'hython':
        poison = fixture / 'foreign'
        packages = poison / 'packages'
        packages.mkdir(parents=True)
        marker = fixture / 'foreign-startup-ran'
        for version in ('3.11', '3.13'):
            hook = poison / ('python' + version + 'libs/pythonrc.py')
            hook.parent.mkdir()
            hook.write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').touch()\n', encoding='utf-8')
        (packages / 'foreign.json').write_text(json.dumps({'path': str(poison)}), encoding='utf-8')
        base = {**os.environ, 'HOUDINI_PACKAGE_DIR': str(packages), 'HOUDINI_PATH': str(poison) + ';&',
                'PYTHONPATH': str(poison), 'HSITE': str(poison)}
        env = isolated_environment(fixture / 'real', executable=sys.executable, base=base)
        # Positive control: the authored package really is a startup hook. Use
        # a sanitized base and inject only our own fixture, never user paths.
        dirty = {**env, 'HOUDINI_PACKAGE_DIR': str(packages), 'HOUDINI_PATH': str(poison) + ';&'}
        control = subprocess.run([sys.executable, '-c', "import hou; print('FIXTURE_STARTUP')"],
                                 cwd=launch_directory(sys.executable), env=dirty, capture_output=True,
                                 text=True, encoding='utf-8', errors='replace', timeout=120,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert control.returncode == 0 and marker.exists(), control.stdout + control.stderr
        marker.unlink()  # this test's own disposable marker
        code = "import hou,sys; assert not any('foreign' in p for p in sys.path); print('ISOLATED_HOUDINI=' + hou.applicationVersionString())"
        result = subprocess.run([sys.executable, '-c', code], cwd=launch_directory(sys.executable),
                                env=env, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=120,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode == 0 and 'ISOLATED_HOUDINI=' in result.stdout, result.stdout + result.stderr
        assert not marker.exists(), 'inherited package executed before test startup'
        print(result.stdout.strip())
print('GUI policy, license preservation, caller immutability and explicit launch directory passed')

import houdini_test_environment as test_environment
with patch.object(test_environment, 'windows_package_name', return_value=None), \
     patch.object(test_environment, '_run_unpacked_test_cli', side_effect=AssertionError('ordinary CLI must stay in place')):
    test_environment.reexec_unpacked_test_cli()

if os.name == 'nt':
    import ctypes
    from ctypes import wintypes as w
    import time
    with tempfile.TemporaryDirectory(prefix='dsh-unpackaged-中文 空格-') as raw:
        folder = Path(raw)
        probe = folder / 'round trip.py'
        identity_log = folder / 'identities.jsonl'
        probe.write_text(
            "import sys,os,json\n"
            f"sys.path.insert(0,{str(ROOT / 'tools')!r})\n"
            "from houdini_test_environment import reexec_unpacked_test_cli,windows_package_name\n"
            "with open(sys.argv[1],'a',encoding='utf-8') as stream:\n"
            "    stream.write(json.dumps(windows_package_name())+'\\n')\n"
            "reexec_unpacked_test_cli()\n"
            "print('PAYLOAD '+json.dumps({'package':windows_package_name(),'input':sys.stdin.read(),"
            "'arguments':sys.argv[3:],'cwd':os.getcwd(),'marker':os.environ['DSH_TEST_STREAM_MARKER']},ensure_ascii=False),flush=True)\n"
            "print('STDERR 回显',file=sys.stderr,flush=True)\n"
            "raise SystemExit(int(sys.argv[2]))\n", encoding='utf-8')
        original_package = test_environment.windows_package_name()
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'DSH_TEST_STREAM_MARKER': '保留此变量'}
        values = ['中文 空格', 'quote"inside', 'ends-with-backslash\\', '']
        for code in (0, 37, -1073741515):  # Also preserve Windows NTSTATUS exit bits.
            identity_log.write_text('', encoding='utf-8')
            completed = subprocess.run([sys.executable, '-u', str(probe), str(identity_log), str(code), *values],
                                       input='stdin 中文\nsecond line\n', cwd=folder, env=env, capture_output=True,
                                       text=True, encoding='utf-8', errors='strict', timeout=60,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            assert completed.returncode & 0xffffffff == code & 0xffffffff, completed
            record = json.loads(next(line[8:] for line in completed.stdout.splitlines() if line.startswith('PAYLOAD ')))
            assert record == {'package': None, 'input': 'stdin 中文\nsecond line\n', 'arguments': values,
                              'cwd': str(folder), 'marker': '保留此变量'}, record
            assert completed.stderr == 'STDERR 回显\n', completed.stderr
            identities = [json.loads(line) for line in identity_log.read_text(encoding='utf-8').splitlines()]
            assert identities == ([original_package, None] if original_package else [None]), identities

        if original_package:
            # Terminating only our wrapper handle closes its Job, which must
            # reclaim its own re-executed CLI and descendants. Never kill a PID
            # discovered in system-wide process listings.
            cancellation = folder / 'cancel.py'
            ready = folder / 'ready.json'
            cancellation.write_text(
                "import sys,os,json,subprocess,time\n"
                f"sys.path.insert(0,{str(ROOT / 'tools')!r})\n"
                "from houdini_test_environment import reexec_unpacked_test_cli\n"
                "reexec_unpacked_test_cli()\n"
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],creationflags=subprocess.CREATE_NO_WINDOW)\n"
                "with open(sys.argv[1],'w',encoding='utf-8') as stream:\n"
                "    json.dump([os.getpid(),child.pid],stream)\n"
                "child.wait()\n", encoding='utf-8')
            wrapper = subprocess.Popen([sys.executable, str(cancellation), str(ready)], cwd=folder, env=env,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
            kernel.WaitForSingleObject.argtypes, kernel.WaitForSingleObject.restype = [w.HANDLE, w.DWORD], w.DWORD
            kernel.CloseHandle.argtypes = [w.HANDLE]
            handles = []
            try:
                deadline = time.monotonic() + 30
                while not ready.exists():
                    assert wrapper.poll() is None, wrapper.communicate()
                    assert time.monotonic() < deadline, 'owned cancellation fixture did not start'
                    time.sleep(.05)
                pids = json.loads(ready.read_text(encoding='utf-8'))
                handles = [kernel.OpenProcess(0x100000, False, pid) for pid in pids]
                assert all(handles), 'could not observe authored fixture processes'
                wrapper.kill()
                wrapper.wait(timeout=15)
                assert all(kernel.WaitForSingleObject(handle, 10000) == 0 for handle in handles), 'owned descendant survived wrapper exit'
            finally:
                if wrapper.poll() is None:
                    wrapper.kill()
                wrapper.communicate(timeout=15)
                for handle in handles:
                    if handle:
                        kernel.CloseHandle(handle)
    print('unpackaged CLI identity, exact argv/stdin/stdout/stderr/exit code and owned-tree cancellation passed')
