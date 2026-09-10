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
with patch.dict(os.environ, contaminated, clear=True), \
     patch.object(sys, 'argv', ['run-deployment-tests.py']), \
     patch.object(subprocess, 'run', side_effect=lambda *a, **kw: calls.append(kw)):
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
