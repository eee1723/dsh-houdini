"""Isolated Houdini assembly registration through the new preview Host path."""
from pathlib import Path
import json
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import hou
import dsh_component_preview as preview
import dsh_managed_runtime as runtime
from dsh_shared_executor import prepare_registration, publish_registration

binary, python, houdini, folder = sys.argv[1:5]
root = Path(folder).resolve(strict=True)
run = root / 'run'
config = {'schema': 1, 'source': str(ROOT), 'bin': str(Path(binary).resolve(strict=True)),
          'python': str(Path(python).resolve(strict=True)),
          'houdini': str(Path(houdini).resolve(strict=True)), 'run': str(run),
          **{key: str(run / key) for key in ('home', 'workers', 'registry')}}
preview._validate_config(config, root)
hip = root / 'assembly.hip'
hou.hipFile.save(str(hip))  # New isolated fixture, never a user's scene.
facts = prepare_registration()
assert Path(facts['hip']).resolve() == hip
process = None
try:
    preview._ensure_profile(config, root)
    record = publish_registration(config['registry'], facts)
    process, session = preview._start_host(config, str(root), root)
    deadline = time.monotonic() + 90
    while not preview._check_ready(process, session):
        if time.monotonic() >= deadline:
            raise RuntimeError('Component Host did not become ready')
        time.sleep(.25)
    request = urllib.request.Request(session.base_url + '/api/houdiniTargets/list',
        data=json.dumps({'type': 'client-request', 'rpcId': 'component-preview-target',
                         'method': 'houdiniTargets/list', 'payload': {'args': {}}}).encode(),
        headers={'Content-Type': 'application/json'})
    with session.open(request, timeout=15) as response:
        result = json.load(response)
    assert result['result']['ok'], result
    assert any(item['executor_id'] == record['executor_id'] for item in result['result']['value']['candidates'])
    assert hip.is_file() and runtime.owns_pid(process.pid)
    print('PASS isolated assembly HIP registration, dynamic owned Host and target discovery; no model/GUI')
finally:
    if process is not None:
        runtime.stop_owned(expected_process=process)
