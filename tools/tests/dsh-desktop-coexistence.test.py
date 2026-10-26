"""Issue #4: restart the official Host with existing third-party fixture bundles.

The three package names match the report, but their code is authored here and
only registers inert markers. No third-party package is downloaded or executed.
Every profile, Session, descriptor, package copy and child process is owned by
this fixture. No model, Houdini or installed user Desktop is used.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli
from dsh_web_auth import DshWebSession
from dsh_managed_runtime import spawn_frontend, stop_owned
from dsh_runtime_compat import official_runtime_identity
from dsh_deployment import read_json

THIRD_PARTY = ('@ace-zone/dsh-market', 'cc-safety-net', 'dsh-reverse-image-search')


def main():
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-cache', type=Path, required=True)
    args = parser.parse_args()
    binary = args.runtime_cache.resolve(strict=True) / 'node_modules/@deepseek-ai/dsh/lib/bin.js'
    identity = official_runtime_identity(binary)
    assert identity['dshVersion'] == '0.2.1-rc.3', identity
    node = shutil.which('node')
    assert node
    folder = Path(tempfile.mkdtemp(prefix='dsh-desktop-coexistence-')).resolve()
    print('Owned coexistence evidence: ' + str(folder), flush=True)
    env = isolated_environment(folder / 'environment')
    home = Path(env['DSH_HOME'])
    preparation = subprocess.run([node, str(ROOT / 'tools/tests/prepare-shared-host-fixture.mjs'), str(binary), str(home), str(ROOT)],
                   cwd=ROOT, env=env, capture_output=True, timeout=60,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (folder / 'prepare.log').write_bytes((preparation.stdout or b'') + b'\n' + (preparation.stderr or b''))
    assert preparation.returncode == 0, 'Fixture preparation exited ' + str(preparation.returncode) + '; inspect prepare.log'
    profile = home / 'profiles/web'
    manifest_path, patch_path = profile / 'package.json', profile / 'cordis.patch.yml'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    dependencies = manifest.setdefault('dependencies', {})
    bundles = manifest['dsh']['profile']['bundles']
    for index, name in enumerate(THIRD_PARTY):
        package = profile / 'node_modules' / name
        package.mkdir(parents=True)
        (package / 'package.json').write_text(json.dumps({
            'name': name, 'version': '0.0.0-fixture', 'private': True, 'type': 'module', 'main': 'marker.mjs',
            'exports': {'.': './marker.mjs', './package.json': './package.json'},
            'dsh': {'bundle': {'patch': './cordis.patch.yml'}}}), encoding='utf-8')
        (package / 'marker.mjs').write_text(
            'export function apply(ctx) { ctx.provide(' + json.dumps('issue4Fixture' + str(index))
            + ', ' + json.dumps({'packageName': name, 'inertFixture': True}) + '); }\n', encoding='utf-8')
        (package / 'cordis.patch.yml').write_text(json.dumps([{'insert': [{
            'id': 'issue4-fixture-' + str(index), 'name': (package / 'marker.mjs').as_uri()}]}]), encoding='utf-8')
        dependencies[name] = '0.0.0-fixture'
        bundles.append(name)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    patch_path.write_text('- id: ui-theme\n  config:\n    preference: dark\n', encoding='utf-8')
    profile_snapshot = manifest_path.read_bytes(), patch_path.read_bytes()
    workspace = folder / 'existing-project'
    workspace.mkdir()
    bridge_guard = socket.socket()
    bridge_guard.bind(('127.0.0.1', 0))
    env['DSH_HOUDINI_BRIDGE_URL'] = 'http://127.0.0.1:' + str(bridge_guard.getsockname()[1])
    env['DSH_HOUDINI_EXECUTOR_ID'] = uuid.uuid4().hex
    command_path, response_path = folder / 'fixture-command.json', folder / 'fixture-response.json'
    inspector = folder / 'coexistence-inspector.mjs'
    native_llm = binary.parents[2] / 'dsh-llm/lib/index.js'
    inspector.write_text('import {createUserMessage} from ' + json.dumps(native_llm.as_uri()) + ';\n' + r'''
import fs from 'node:fs';
const write=(path,value)=>{fs.writeFileSync(path+'.tmp',JSON.stringify(value));fs.renameSync(path+'.tmp',path)};
export const inject=['loader','agentPresets','sessions','agents'];
export function apply(ctx) {
  ctx.effect(()=>{
    let stopped=false,busy=false,lastId;
    queueMicrotask(async()=>{
      try {
        await ctx.loader.await();
        const roster=await ctx.agentPresets.remoteExportList();
        write(process.env.DSH_COEXIST_READY,{ok:true,roster,
          markers:[0,1,2].map(index=>ctx.get('issue4Fixture'+index))});
      } catch(error) {write(process.env.DSH_COEXIST_READY,{ok:false,error:String(error.stack||error)})}
    });
    const timer=setInterval(async()=>{
      if(stopped||busy||!fs.existsSync(process.env.DSH_COEXIST_COMMAND))return;
      const command=JSON.parse(fs.readFileSync(process.env.DSH_COEXIST_COMMAND,'utf8'));
      if(command.id===lastId)return;
      lastId=command.id;busy=true;
      try {
        if(command.action!=='seed')throw Error('Unsupported fixture action');
        const agent=ctx.agents.get(command.sessionId);
        if(!agent)throw Error('Fixture Session was not created by the native API');
        agent.session.append('turn/start',{turn:1});
        agent.session.append('user/message',createUserMessage({source:{kind:'user'},
          content:[{type:'text',text:command.text}]}),{surfaceOp:'append'});
        const terminal=agent.session.append('turn/end',{turn:1,reason:{kind:'completed'}});
        if(await ctx.sessions.flush(agent.session)!==true)throw Error('Native Session flush failed');
        write(process.env.DSH_COEXIST_RESPONSE,{id:command.id,ok:true,throughSeq:terminal.seq});
      } catch(error) {write(process.env.DSH_COEXIST_RESPONSE,{id:command.id,ok:false,error:String(error.stack||error)})}
      finally {busy=false}
    },50);
    return()=>{stopped=true;clearInterval(timer)};
  });
}
''', encoding='utf-8')
    overlay = folder / 'coexistence.patch.yml'
    overlay.write_text(json.dumps([{'insert': [{'id': 'coexistence-inspector', 'name': inspector.as_uri()}]}]), encoding='utf-8')
    env.update(DSH_COEXIST_COMMAND=str(command_path), DSH_COEXIST_RESPONSE=str(response_path))
    process = None
    report = {'ok': False, 'runtime': identity, 'thirdPartyPackages': list(THIRD_PARTY), 'runs': []}
    old_descriptor = None
    session_id, through_seq = None, None
    sentence = 'Issue #4: this native Session survives the second Host start.'

    def wait_json(filename, predicate=lambda value: True, timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            assert process is not None and process.poll() is None, 'Owned Host exited; inspect its fixture log'
            try:
                value = read_json(Path(filename))
                if predicate(value):
                    return value
            except FileNotFoundError:
                pass
            time.sleep(.05)
        raise AssertionError('Owned Host response timed out: ' + Path(filename).name)

    try:
        for run in (1, 2):
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            ready_file = folder / ('ready-' + str(run) + '.json')
            env['DSH_COEXIST_READY'] = str(ready_file)
            log = folder / ('host-' + str(run) + '.log')
            with log.open('wb') as output:
                process = spawn_frontend([node, str(binary), 'web', '--patch', str(overlay), '--port', str(port), '--no-open'],
                    node=node, cwd=folder, env=env, stdout=output, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            ready = wait_json(ready_file)
            assert ready['ok'], ready
            assert [item['packageName'] for item in ready['markers']] == list(THIRD_PARTY), ready
            assert all(item['inertFixture'] for item in ready['markers'])
            roster = ready['roster']['presets']
            assert next(row for row in roster if row['id'] == 'standard')['isDefault']
            assert not next(row for row in roster if row['id'] == 'houdini')['isDefault']
            assert {'standard', 'ptc', 'minimal', 'cordis', 'houdini'} <= {row['id'] for row in roster}
            auth = DshWebSession('http://127.0.0.1:' + str(port), str(log), str(folder / ('auth-' + str(run) + '.json')))
            deadline = time.monotonic() + 15
            while auth.launch_url() is None:
                assert process.poll() is None and time.monotonic() < deadline
                time.sleep(.05)
            auth.authorize(timeout=5)

            def rpc(method, arguments):
                data = {'type': 'client-request', 'rpcId': uuid.uuid4().hex, 'method': method, 'payload': {'args': arguments}}
                request = urllib.request.Request(auth.base_url + '/api/' + method, data=json.dumps(data).encode(),
                    headers={'Content-Type': 'application/json'}, method='POST')
                with auth.open(request, timeout=15) as response:
                    result = json.load(response)['result']
                assert result['ok'], result
                return result.get('value')

            inventory = rpc('pluginInventory/list', {})
            (folder / ('inventory-' + str(run) + '.json')).write_text(json.dumps([
                {key: row.get(key) for key in ('entryId', 'moduleName', 'enabled', 'fiberPhase')}
                for row in inventory['entries']], ensure_ascii=False, indent=2), encoding='utf-8')
            for index in range(3):
                module = (profile / 'node_modules' / THIRD_PARTY[index] / 'marker.mjs').as_uri()
                row = next(row for row in inventory['entries'] if row['moduleName'] == module)
                assert row['enabled'] and row['fiberPhase'] == 'active', row
            deadline = time.monotonic() + 10
            while not rpc('houdiniFrontend/capabilities', {})['desktop']:
                assert time.monotonic() < deadline, 'Standard plugin Desktop service did not activate'
                time.sleep(.05)
            descriptor = wait_json(home / 'dsh-houdini/desktop.json')
            if run == 1:
                created = rpc('session/create', {'request': {'sessionId': uuid.uuid4().hex, 'cwd': str(workspace)}})
                assert created['agentPreset'] == 'standard', created
                session_id = created['sessionId']
                command_id = uuid.uuid4().hex
                command_path.write_text(json.dumps({'id': command_id, 'action': 'seed', 'sessionId': session_id, 'text': sentence}), encoding='utf-8')
                seeded = wait_json(response_path, lambda value: value.get('id') == command_id)
                assert seeded['ok'], seeded
                through_seq = seeded['throughSeq']
                old_descriptor = descriptor
            else:
                assert descriptor['generation'] != old_descriptor['generation']
                assert descriptor['token'] != old_descriptor['token']
                request = urllib.request.Request('http://127.0.0.1:' + str(descriptor['port']) + '/status',
                    data=b'{}', headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + old_descriptor['token']}, method='POST')
                try:
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5):
                        raise AssertionError('The previous Host token was accepted')
                except urllib.error.HTTPError as error:
                    assert error.code == 401
                listed = rpc('session/list', {'_request': {}})
                assert any(item['sessionId'] == session_id for item in listed['items'])
            page = rpc('session/page', {'request': {'address': {'kind': 'session', 'sessionId': session_id},
                'throughSeq': through_seq, 'maxMessages': 20}})
            assert sentence in json.dumps(page, ensure_ascii=False), 'Native persisted Session content became unreadable'
            assert (manifest_path.read_bytes(), patch_path.read_bytes()) == profile_snapshot, 'Host changed existing dependencies or user settings'
            report['runs'].append({'run': run, 'nativeDefault': 'standard', 'thirdPartyActive': list(THIRD_PARTY),
                'desktop': True, 'descriptorGeneration': descriptor['generation'], 'sessionReadable': True,
                'profilePreserved': True, 'retiredTokenRefused': run == 2})
            stop_owned(expected_process=process)
            process.wait(timeout=15)
            process = None
        report['ok'] = True
        print('Official DSH rc.3: exact issue #4 fixture bundles active across two starts; native presets, existing Session/profile/settings preserved; new descriptor generation and old-token refusal passed', flush=True)
    finally:
        if process is not None:
            stop_owned(expected_process=process)
            process.wait(timeout=15)
        bridge_guard.close()
        (folder / 'coexistence-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
