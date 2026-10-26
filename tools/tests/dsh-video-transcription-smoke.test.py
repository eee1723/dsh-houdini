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
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment,reexec_unpacked_test_cli
from dsh_web_auth import DshWebSession
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
credential_signal=fixture/'native-credential-request.json'
secret='fixture-only-'+uuid.uuid4().hex
env.update(DSH_VIDEO_FIXTURE_WORKSPACE=str(workspace),DSH_VIDEO_FIXTURE_PYTHON=sys.executable,
           DSH_VIDEO_FIXTURE_BASE=f'http://127.0.0.1:{api_port}',
           DSH_VIDEO_FIXTURE_CREDENTIAL_SIGNAL=str(credential_signal))
overlay = fixture / 'video-fixture.patch.yml'
overlay.write_text(json.dumps([{'id':'workspace-controller','config':{'documentsDirectory':str(fixture/'documents')}},
    {'insert': [{'id': 'video-transcription-fixture',
    'name': (ROOT / 'tools/tests/dsh-video-transcription-fixture.mjs').as_uri()}]}]), encoding='utf-8')
results = []
for phase in ('initial', 'restart'):
    result_path = fixture / (phase + '-result.json')
    env.update(DSH_VIDEO_FIXTURE_OUT=str(result_path), DSH_VIDEO_FIXTURE_PHASE=phase)
    log = fixture / (phase + '-host.log')
    auth=DshWebSession(f'http://127.0.0.1:{host_port}',str(log),str(fixture/(phase+'-runtime.json')))
    credential_written=False
    with log.open('wb') as output:
        process = runtime.spawn_frontend([node, str(cli), 'web', '--patch', str(overlay),
            '--port', str(host_port), '--no-open'], node=node, cwd=workspace, env=env,
            stdout=output, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            deadline = time.monotonic() + 150
            while not result_path.exists():
                assert process.poll() is None, 'Host exited; inspect ' + str(log)
                assert time.monotonic() < deadline, 'ASR loop timed out; inspect ' + str(log)
                if phase=='initial' and credential_signal.exists() and not credential_written:
                    signal=json.loads(credential_signal.read_text(encoding='utf-8'))
                    expected_endpoint=f'http://127.0.0.1:{api_port}/custom-asr'
                    expected_origin=f'http://127.0.0.1:{api_port}'
                    expected_ref='DSH_HOUDINI_ASR_'+__import__('hashlib').sha256(expected_origin.encode()).hexdigest()[:16].upper()+'_API_KEY'
                    assert signal['ref']==expected_ref and signal['endpoint']==expected_endpoint and signal['origin']==expected_origin
                    if auth.launch_url() is not None:
                        auth.authorize(timeout=5)
                        def rpc(method,arguments):
                            body=json.dumps({'type':'client-request','rpcId':uuid.uuid4().hex,'method':method,'payload':{'args':arguments}}).encode()
                            request=urllib.request.Request(f'http://127.0.0.1:{host_port}/api/'+method,data=body,headers={'content-type':'application/json'},method='POST')
                            with auth.open(request,timeout=10) as response:value=json.load(response)['result']
                            assert value['ok'],value
                            assert secret not in json.dumps(value)
                            return value.get('value')
                        rpc('credentials/set',{'ref':expected_ref,'value':secret})
                        assert rpc('credentials/describe',{'refs':[expected_ref]})[expected_ref]['configured']
                        credential_written=True
                time.sleep(.2)
            result = json.loads(result_path.read_text(encoding='utf-8'))
            assert result.get('ok'), result.get('error', result)
            assert secret not in json.dumps(result)
            if phase=='initial':
                assert credential_written,'Fixture must consume the native authenticated credential RPC'
                env['DSH_VIDEO_FIXTURE_SESSION']=result['sessionId']
            else:assert result['sessionId']==results[0]['sessionId'],'Restart must continue the original native Session'
            results.append(result)
        finally:
            runtime.stop_owned(process)
            process.wait(timeout=15)
    print(phase + ': ' + '; '.join(result['checks']), flush=True)
    assert secret not in log.read_text(encoding='utf-8',errors='replace'),'Secret must not be emitted in Host logs'
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
