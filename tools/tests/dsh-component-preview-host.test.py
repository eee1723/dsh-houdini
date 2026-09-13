"""Exact source menu profile/owned Host/auth path, without a GUI or model call."""
from pathlib import Path
import json
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
sys.modules.setdefault('hou', types.SimpleNamespace())
import dsh_component_preview as preview
import dsh_managed_runtime as runtime

binary, houdini = (str(Path(value).resolve(strict=True)) for value in sys.argv[1:3])
root = Path(tempfile.mkdtemp(prefix='component-preview-host-', dir=ROOT / 'tools/out'))
run = root / 'run'
config = {'schema': 1, 'source': str(ROOT), 'bin': binary, 'python': sys.executable,
          'houdini': houdini, 'run': str(run),
          **{key: str(run / key) for key in ('home', 'workers', 'registry')}}
preview._validate_config(config, root)
process = None
try:
    preview._ensure_profile(config, root)
    assert preview._read_config(root) == config
    assert '"projectLocalWorkers":true' in (Path(config['home']) / 'component.cordis.yml').read_text(encoding='utf-8')
    process, session = preview._start_host(config, str(root), root)
    deadline = time.monotonic() + 90
    while not preview._check_ready(process, session):
        if time.monotonic() >= deadline:
            raise RuntimeError('isolated preview Host did not become ready; inspect fixture privately')
        time.sleep(.25)
    assert session.launch_url() and session.base_url.startswith('http://127.0.0.1:')
    assert runtime.owns_pid(process.pid)
    print('PASS source profile, dynamic owned Host and authenticated session/list; no model/HIP/GUI')
finally:
    if process is not None:
        runtime.stop_owned(expected_process=process)
