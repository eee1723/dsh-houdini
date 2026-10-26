"""Exercise image generation through the exact isolated DSH Host, without paid APIs.

Usage: python tools/tests/dsh-image-generation-smoke.test.py --runtime-cache <cache>
The owned HTTP fixture accepts real JSON/multipart requests. DSH settings,
credentials, sessions, native/PTC tools and attachment storage remain real.
"""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli
import dsh_managed_runtime as runtime


def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-cache', type=Path, required=True)
args = parser.parse_args()
cache = args.runtime_cache.resolve(strict=True)
node = shutil.which('node')
assert node
preferred = json.loads((ROOT / 'dsh-runtime-compatibility.json').read_text())['preferredVersion']
assert json.loads((cache / 'node_modules/@deepseek-ai/dsh/package.json').read_text())['version'] == preferred
fixture = Path(tempfile.mkdtemp(prefix='dsh-image-generation-'))
workspace = fixture / 'workspace'
workspace.mkdir()
projects = {name: fixture / ('project-' + name) for name in ('B', 'C')}
for project in projects.values():
    project.mkdir()
print('Isolated evidence:', fixture, flush=True)
env = isolated_environment(fixture)
subprocess.run([node, str(ROOT / 'tools/tests/prepare-shared-host-fixture.mjs'),
    str(cache / 'node_modules/@deepseek-ai/dsh/lib/bin.js'), env['DSH_HOME'], str(ROOT)],
    cwd=ROOT, env=env, check=True, timeout=60, capture_output=True)
api_port, host_port = unused_port(), unused_port()
env.update(DSH_HOUDINI_BRIDGE_URL=f'http://127.0.0.1:{api_port}',
           DSH_HOUDINI_EXECUTOR_ID=uuid.uuid4().hex,
           DSH_IMAGE_FIXTURE_OUT=str(fixture / 'result.json'),
           DSH_IMAGE_FIXTURE_WORKSPACE=str(workspace),
           DSH_IMAGE_FIXTURE_PROJECT_B=str(projects['B']),
           DSH_IMAGE_FIXTURE_PROJECT_C=str(projects['C']))
overlay = fixture / 'image-fixture.patch.yml'
# JSON is YAML: use structured values so paths/URLs never depend on shell quoting.
overlay.write_text(json.dumps([{'insert': [
    {'id': 'image-generation-fixture', 'name': (ROOT / 'tools/tests/dsh-image-generation-fixture.mjs').as_uri()},
]}]), encoding='utf-8')
log = fixture / 'host.log'




with log.open('wb') as output:
    process = runtime.spawn_frontend([node, str(cache / 'node_modules/@deepseek-ai/dsh/lib/bin.js'),
        'web', '--patch', str(overlay), '--port', str(host_port), '--no-open'],
        node=node, cwd=fixture, env=env, stdout=output, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        deadline = time.monotonic() + 120
        result_file = fixture / 'result.json'
        while not result_file.exists():
            assert process.poll() is None, 'Host exited; inspect ' + str(log)
            assert time.monotonic() < deadline, 'Image loop timed out; inspect ' + str(log)
            time.sleep(.2)
        result = json.loads(result_file.read_text(encoding='utf-8'))
        assert result.get('ok') is True, result.get('error', result)
        print('Exact DSH image tools: live settings, real credentials, native generation, '
              'multipart PTC edit, project-root policy, in-flight Save As, offline explicit output, '
              'original/preview readback and actual-path present delivery passed', flush=True)
        print(json.dumps({key: result[key] for key in ('sessionId', 'checks', 'requests')}, ensure_ascii=False), flush=True)
    finally:
        runtime.stop_owned(process)
        process.wait(timeout=15)
