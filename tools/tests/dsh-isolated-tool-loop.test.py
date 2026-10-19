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
from houdini_test_environment import reexec_unpacked_test_cli

reexec_unpacked_test_cli()
node = shutil.which('node')
if not node:
    raise RuntimeError('Node.js is required for the pinned DSH integration')
raise SystemExit(subprocess.call([node, str(Path(__file__).with_suffix('.mjs')), *sys.argv[1:]], cwd=ROOT))
