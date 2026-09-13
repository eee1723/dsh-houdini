"""Run the preview menu's assembly/Host data path in isolated H21/H22 hython."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, launch_directory

binary = str(Path(sys.argv[1]).resolve(strict=True))
for executable in sys.argv[2:]:
    hython = Path(executable).resolve(strict=True)
    houdini = hython.with_name('houdini.exe')
    root = Path(tempfile.mkdtemp(prefix='component-preview-registration-', dir=ROOT / 'tools/out'))
    result = subprocess.run([str(hython), str(ROOT / 'tools/tests/dsh-component-preview-registration.test.py'),
                             binary, sys.executable, str(houdini), str(root)],
                            cwd=launch_directory(hython), env=isolated_environment(root / 'environment', executable=hython),
                            timeout=180, capture_output=True, text=True, encoding='utf-8', errors='replace',
                            creationflags=subprocess.CREATE_NO_WINDOW)
    print(hython.parent.parent.name, result.stdout, flush=True)
    if result.returncode:
        print(result.stderr[-3000:], flush=True)
        raise SystemExit(result.returncode)
