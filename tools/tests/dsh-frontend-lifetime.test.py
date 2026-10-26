"""Owned Windows fixture process trees; no Desktop, DSH server, model, or HIP."""
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment
import dsh_managed_runtime as runtime

assert os.name == 'nt'
node = shutil.which('node')
assert node
identity = runtime.executor_identity()
importlib.reload(runtime)
assert identity == runtime.executor_identity()
with tempfile.TemporaryDirectory(prefix='dsh-owned-fixture-') as temporary:
    env = isolated_environment(Path(temporary) / 'env')
    process = runtime.spawn_frontend([node, '-e', 'setInterval(()=>{},1000)'], node=node,
                                    cwd=temporary, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        assert runtime.has_owned_frontend() and runtime.owns_pid(process.pid)
        assert not runtime.stop_owned(expected_process=None)
        assert not runtime.stop_owned(expected_process=object())
        try:
            runtime.spawn_frontend([node, '-e', 'throw Error("must not start")'], node=node, replace_existing=False)
        except RuntimeError:
            pass
        else:
            raise AssertionError('a fixture replaced an existing owned process')
        assert process.poll() is None
        assert runtime.stop_owned(expected_process=process)
        assert process.poll() is not None and not runtime.has_owned_frontend()
    finally:
        runtime.stop_owned()
print('Fixture-only Node ownership, identity retention and exact-handle shutdown passed')
