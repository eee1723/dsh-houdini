"""Real pinned DSH jobs and a disposable Houdini Bridge, including Host reopen.

No user runtime, HIP, model provider, registry or credentials are used. The
owned HTTP relay drops one admitted response to exercise receipt recovery.
"""
from pathlib import Path
import argparse
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment, launch_directory, reexec_unpacked_test_cli
from dsh_managed_runtime import spawn_frontend, stop_owned


def worker(config):
    import hou
    import dsh_bridge as bridge
    root = Path(config['directory'])
    # A tiny generated calibration image exercises receipt/media/attachment
    # transport only. No renderer or semantic visual-quality claim is made.
    def png_chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    pixels = b'\x00\xff\x00\x00\xff\x00\xff\x00\xff\x00\x00\x00\xff\xff\xff\xff\xff\xff'
    (root / 'reported-image.png').write_bytes(b'\x89PNG\r\n\x1a\n'
        + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 6, 0, 0, 0))
        + png_chunk(b'IDAT', zlib.compress(pixels)) + png_chunk(b'IEND', b''))
    hou.hipFile.setName(str(root / 'owned-fixture.hip'))
    server = bridge.start(0)
    bridge._pump_active = True
    calls = []
    dropped = set()

    class Relay(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def route(self):
            if self.path == '/fixture-metrics':
                value = json.dumps({'calls': calls, 'dropped': list(dropped)}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(value)))
                self.end_headers()
                self.wfile.write(value)
                return
            raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            body = json.loads(raw) if raw else {}
            calls.append({'method': self.command, 'path': self.path,
                          'code': body.get('code'), 'request_ref': body.get('request_ref'),
                          'owner_session': body.get('owner_session')})
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=40)
            try:
                connection.request(self.command, self.path, raw or None,
                                   {key: value for key, value in self.headers.items()
                                    if key.lower() not in ('host', 'connection', 'content-length')})
                response = connection.getresponse()
                value = response.read()
                lose = self.path == '/jobs' and 'TRANSPORT_LOST' in body.get('code', '')
                if lose and body['request_ref'] not in dropped:
                    dropped.add(body['request_ref'])
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                self.send_response(response.status)
                self.send_header('Content-Type', response.getheader('Content-Type', 'application/octet-stream'))
                self.send_header('Content-Length', str(len(value)))
                self.end_headers()
                self.wfile.write(value)
            finally:
                connection.close()

        do_GET = route
        do_POST = route

    relay = ThreadingHTTPServer(('127.0.0.1', 0), Relay)
    threading.Thread(target=relay.serve_forever, daemon=True).start()
    (root / 'ready.json').write_text(json.dumps({'executorId': bridge._EXECUTOR_ID,
        'runtimeId': bridge._RUNTIME_ID, 'houdiniVersion': hou.applicationVersionString(), 'port': relay.server_port,
        'contract': {'version': bridge._EXECUTION_CONTRACT_VERSION, 'hash': bridge._VERB_CATALOG_HASH}}))
    try:
        while not (root / 'stop').exists():
            if not (root / 'pause-pump').exists():
                bridge._pump()
            time.sleep(.01)
    finally:
        relay.shutdown()
        bridge.stop()


def main():
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-cache', type=Path)
    parser.add_argument('--hython', type=Path)
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(json.loads(args.worker.read_text(encoding='utf8')))
        return
    if not args.runtime_cache or not args.hython:
        parser.error('--runtime-cache and --hython are required')
    cli = args.runtime_cache.resolve(strict=True) / 'node_modules/@deepseek-ai/dsh/lib/bin.js'
    preferred = json.loads((ROOT / 'dsh-runtime-compatibility.json').read_text())['preferredVersion']
    assert json.loads((cli.parent.parent / 'package.json').read_text())['version'] == preferred
    hython = args.hython.resolve(strict=True)
    directory = Path(tempfile.mkdtemp(prefix='dsh-live-job-loop-'))
    print('Real live-job integration evidence:', directory, flush=True)
    def build_digest():
        digest = hashlib.sha256()
        files = sorted((ROOT / 'lib').rglob('*.js'))
        assert files, 'Build the plugin before running its real DSH fixture'
        for filename in files:
            digest.update(filename.relative_to(ROOT).as_posix().encode())
            digest.update(b'\0')
            digest.update(hashlib.sha256(filename.read_bytes()).digest())
        return digest.hexdigest()
    expected_build = build_digest()
    def check_build(stage, result_path=None):
        observed = build_digest()
        if observed == expected_build:
            return
        failure = {'ok': False, 'classification': 'test_environment_changed', 'stage': stage,
                   'expected_lib_sha256': expected_build, 'observed_lib_sha256': observed,
                   'error': 'Plugin build output changed during the fixture; this run cannot certify product behavior.'}
        if result_path and result_path.exists():
            result_path.rename(result_path.with_name(result_path.stem + '-uncertified.json'))
            result_path.write_text(json.dumps(failure, indent=2), encoding='utf8')
        (directory / 'environment-failure.json').write_text(json.dumps(failure, indent=2), encoding='utf8')
        raise RuntimeError(failure['error'] + ' ' + str(directory))
    env = isolated_environment(directory, executable=hython)
    node = shutil.which('node')
    assert node
    subprocess.run([node, str(ROOT / 'tools/tests/prepare-shared-host-fixture.mjs'), str(cli),
                    env['DSH_HOME'], str(ROOT)], cwd=ROOT, env=env,
                   check=True, capture_output=True, timeout=60)
    config_path = directory / 'fixture.json'
    config = {'directory': str(directory), 'phase': 'initial', 'lib_sha256': expected_build}
    config_path.write_text(json.dumps(config), encoding='utf8')
    patch = directory / 'fixture.patch.json'
    patch.write_text(json.dumps([{'id': 'session-title-llm', 'disabled': True},
        {'insert': [{'id': 'live-job-fixture',
                     'name': (ROOT / 'tools/tests/dsh-live-job-loop-fixture.mjs').as_uri()}]}]), encoding='utf8')
    env['DSH_LIVE_JOB_FIXTURE'] = str(config_path)
    with (directory / 'bridge.log').open('wb') as blog:
        bridge = subprocess.Popen([str(hython), str(Path(__file__).resolve()), '--worker', str(config_path)],
            cwd=launch_directory(hython), env=env, stdout=blog, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        host = None
        try:
            deadline = time.monotonic() + 45
            while not (directory / 'ready.json').exists():
                assert bridge.poll() is None and time.monotonic() < deadline, str(directory)
                time.sleep(.1)
            ready = json.loads((directory / 'ready.json').read_text())
            env.update(DSH_HOUDINI_EXECUTOR_ID=ready['executorId'],
                       DSH_HOUDINI_BRIDGE_URL=f"http://127.0.0.1:{ready['port']}")
            for phase in ('initial', 'restart'):
                check_build('before ' + phase)
                config['phase'] = phase
                config_path.write_text(json.dumps(config), encoding='utf8')
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0))
                    port = sock.getsockname()[1]
                with (directory / (phase + '-host.log')).open('wb') as log:
                    host = spawn_frontend([node, str(cli), 'web', '--patch', str(patch),
                        '--port', str(port), '--no-open'], node=node, cwd=directory,
                        env=env, stdout=log, stderr=subprocess.STDOUT)
                    result_path = directory / (phase + '-result.json')
                    deadline = time.monotonic() + 150
                    while not result_path.exists():
                        assert host.poll() is None and time.monotonic() < deadline, str(directory) + ' ' + phase
                        time.sleep(.1)
                    check_build('after ' + phase, result_path)
                    result = json.loads(result_path.read_text(encoding='utf8'))
                    assert result['ok'], (str(directory), result)
                    print('PASS', phase, json.dumps(result['checks'], ensure_ascii=False), flush=True)
                    stop_owned(host)
                    host = None
                assert bridge.poll() is None, 'Host shutdown must not stop the separate Houdini process'
        finally:
            if host is not None:
                stop_owned(host)
            (directory / 'pause-pump').unlink(missing_ok=True)
            for name in ('native', 'running', 'lost', 'restart'):
                (directory / ('release-' + name)).touch()
            (directory / 'stop').touch()
            try:
                bridge.wait(timeout=10)
            except subprocess.TimeoutExpired:
                bridge.terminate()
                bridge.wait(timeout=10)
    check_build('completed')
    print(json.dumps({'ok': True, 'evidence': str(directory), 'lib_sha256': expected_build,
        'houdini_version': ready['houdiniVersion'], 'boundary':
        'Real pinned DSH native/PTC jobs, completion delivery and independent HOM main-thread Bridge; scripted planning, no user live/GUI or visual-quality claim.'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
