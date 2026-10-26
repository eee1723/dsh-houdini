"""Run the owned Node integration outside an inherited Store package identity.

This only changes the test process's desktop-app identity. It does not change
Windows tokens, the DSH sandbox, user profiles or installed Houdini files.
"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import reexec_unpacked_test_cli
from dsh_runtime_compat import official_runtime_identity

reexec_unpacked_test_cli()
if '--runtime-cache' in sys.argv:
    runtime = Path(sys.argv[sys.argv.index('--runtime-cache') + 1]).resolve()
    official_runtime_identity(runtime / 'node_modules/@deepseek-ai/dsh/lib/bin.js')
node = shutil.which('node')
if not node:
    raise RuntimeError('Node.js is required for the pinned DSH integration')
raise SystemExit(subprocess.call([node, str(Path(__file__).with_suffix('.mjs')), *sys.argv[1:]], cwd=ROOT))
