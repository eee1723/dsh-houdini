"""Exact DSH + real video worker + owned HTTP ASR; no cloud calls or Houdini.

Usage: python tools/tests/dsh-video-transcription-smoke.test.py --runtime-cache <cache>
Creates 30 seconds of synthetic media, prepares genuine audio manifests, and
restarts the same isolated Host profile to verify persisted service selection.
"""
import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment,reexec_unpacked_test_cli
import dsh_managed_runtime as runtime
reexec_unpacked_test_cli()


def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def command(values, env):
    return subprocess.run(values, cwd=ROOT, env=env, check=True, timeout=90,
                          capture_output=True, text=True, encoding='utf-8',
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-cache', required=True, type=Path)
args = parser.parse_args()
cache = args.runtime_cache.resolve(strict=True)
node=shutil.which('node')
ffmpeg,ffprobe=(str(ROOT/'runtime/video/ffmpeg/bin'/name) for name in ('ffmpeg.exe','ffprobe.exe'))
assert node and Path(ffmpeg).is_file() and Path(ffprobe).is_file(), 'Node and private media tools are required'
preferred = json.loads((ROOT / 'dsh-runtime-compatibility.json').read_text())['preferredVersion']
assert json.loads((cache / 'node_modules/@deepseek-ai/dsh/package.json').read_text())['version'] == preferred
fixture = Path(tempfile.mkdtemp(prefix='dsh-video-transcription-'))
workspace = fixture / 'workspace'
workspace.mkdir()
env = isolated_environment(fixture)
env['PYTHONUTF8'] = '1'
print('Isolated evidence:', fixture, flush=True)
source = workspace / 'synthetic.mp4'
command([ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
         '-f', 'lavfi', '-i', 'color=c=green:s=160x90:r=5',
         '-f', 'lavfi', '-i', 'aevalsrc=0.1*sin(2*PI*(200*t+5*t*t)):s=16000',
         '-t', '30', '-c:v', 'mpeg4', '-q:v', '10', '-c:a', 'aac', str(source)], env)
script = ROOT / 'skills/houdini-video-tutorial/scripts/video_tutorial.py'
for name in ('prepared-a', 'prepared-b'):
    command([sys.executable, str(script), 'prepare', '--video', str(source),
             '--output', str(workspace / name), '--start', '0', '--duration', '30',
             '--chunk', '12', '--overlap', '2', '--ffmpeg', ffmpeg, '--ffprobe', ffprobe], env)
    manifest = json.loads((workspace / name / 'manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['chunks']) == 3
    assert len({row['sha256'] for row in manifest['chunks']}) == 3, 'Synthetic chunks must be distinguishable'
cli = cache / 'node_modules/@deepseek-ai/dsh/lib/bin.js'
command([node, str(ROOT / 'tools/tests/prepare-shared-host-fixture.mjs'),
         str(cli), env['DSH_HOME'], str(ROOT)], env)
api_port, host_port = unused_port(), unused_port()
env.update(DSH_VIDEO_FIXTURE_WORKSPACE=str(workspace), DSH_VIDEO_FIXTURE_PYTHON=sys.executable,
           DSH_VIDEO_FIXTURE_PYTHON_VERSION='.'.join(map(str,sys.version_info[:3])),
           DSH_VIDEO_FIXTURE_BASE=f'http://127.0.0.1:{api_port}',
           DSH_HOUDINI_BRIDGE_URL=f'http://127.0.0.1:{api_port}',
           DSH_HOUDINI_EXECUTOR_ID='a' * 32)
overlay = fixture / 'video-fixture.patch.yml'
overlay.write_text(json.dumps([{'insert': [{'id': 'video-transcription-fixture',
    'name': (ROOT / 'tools/tests/dsh-video-transcription-fixture.mjs').as_uri()}]}]), encoding='utf-8')
results = []
for phase in ('initial', 'restart'):
    result_path = fixture / (phase + '-result.json')
    env.update(DSH_VIDEO_FIXTURE_OUT=str(result_path), DSH_VIDEO_FIXTURE_PHASE=phase)
    log = fixture / (phase + '-host.log')
    with log.open('wb') as output:
        process = runtime.spawn_frontend([node, str(cli), 'web', '--patch', str(overlay),
            '--port', str(host_port), '--no-open'], node=node, cwd=workspace, env=env,
            stdout=output, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            deadline = time.monotonic() + 150
            while not result_path.exists():
                assert process.poll() is None, 'Host exited; inspect ' + str(log)
                assert time.monotonic() < deadline, 'ASR loop timed out; inspect ' + str(log)
                time.sleep(.2)
            result = json.loads(result_path.read_text(encoding='utf-8'))
            assert result.get('ok'), result.get('error', result)
            results.append(result)
        finally:
            runtime.stop_owned(process)
            process.wait(timeout=15)
    print(phase + ': ' + '; '.join(result['checks']), flush=True)
assert len(results[0]['requests']) == 4 and not results[1]['requests']
for name, expected in [('prepared-a', 1), ('prepared-b', 3)]:
    work = workspace / name
    assert len(list(work.glob('attempt-*.json'))) == expected
    assert len(list(work.glob('outcome-*.json'))) == expected
    assert not (work / '.lock').exists()
command([sys.executable, str(script), 'export', '--work', str(workspace / 'prepared-b'),
         '--output', str(workspace / 'exported')], env)
transcript = json.loads((workspace / 'exported/transcript.json').read_text(encoding='utf-8'))
assert len(transcript['chunks']) == 3
print('Exact DSH ASR: actual Python media/attempt history, native + PTC transport, live root '
      'selection, durable settings and restart resume passed; no paid provider or GUI claim.', flush=True)
