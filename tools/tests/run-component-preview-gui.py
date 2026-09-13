"""Isolated H21/H22 Qt WebView origin regression for the component menu."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, launch_directory

for executable in sys.argv[1:]:
    binary = Path(executable).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='dsh-component-preview-qt-') as folder:
        env = isolated_environment(Path(folder) / 'env', executable=binary)
        env['QT_QPA_PLATFORM'] = 'offscreen'
        result = subprocess.run([str(binary), str(ROOT / 'tools/tests/dsh-webview-navigation.test.py')],
                                cwd=launch_directory(binary), env=env, timeout=120, capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                creationflags=subprocess.CREATE_NO_WINDOW)
        print(binary.parent.parent.name, result.stdout,
              ('Qt backend diagnostics: ' + str(len(result.stderr.splitlines())) + ' lines' if result.stderr else ''), flush=True)
        if result.returncode:
            print(result.stderr[-3000:], flush=True)
            raise SystemExit(result.returncode)
