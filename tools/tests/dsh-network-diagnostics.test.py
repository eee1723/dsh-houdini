"""Exact DSH startup consumes user .env; optional anonymous live-network check.

python tools/tests/dsh-network-diagnostics.test.py --runtime-bin <dsh/lib/bin.js>
  --proxy http://127.0.0.1:7897 --expect-fake-ip --output <evidence-dir>
All profiles, Hosts and loopback servers are owned isolated fixtures. No model calls.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from dsh_network_diagnostics import probe, update_home_proxy, DEFAULT_URL
import dsh_managed_runtime as owned

INSPECTOR = r"""
import fs from 'node:fs';
import http from 'node:http';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(process.env.DSH_NETWORK_TEST_CLI);
const {proxyRouteFor}=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-http-proxy')));
const {launchEnvironmentOf}=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-launch-environment')));
export const inject=['loader','web'];
export function apply(ctx){ctx.effect(()=>{
 queueMicrotask(async()=>{
  const report={};let server;
  try{
   await ctx.loader.await();
   const url=new URL(process.env.DSH_NETWORK_TEST_URL);
   report.proxied=proxyRouteFor(url).proxied;
   report.proxySource=launchEnvironmentOf(ctx).get('HTTPS_PROXY')?.source||null;
   try{const r=await ctx.web.fetch({url:url.href},AbortSignal.timeout(25000));
    report.fetch={status:r.statusCode,chars:r.body.content.length,truncated:r.truncated};}
   catch(e){report.fetch={code:e.code,message:e.message};}
   let hits=0;
   server=http.createServer((_q,s)=>{hits++;s.end('isolated-bridge-transport');});
   await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
   const local=new URL('http://127.0.0.1:'+server.address().port+'/health');
   const response=await fetch(local,{signal:AbortSignal.timeout(5000)});
   report.loopback={proxied:proxyRouteFor(local).proxied,status:response.status,text:await response.text()};
   try{await ctx.web.fetch({url:local.href},AbortSignal.timeout(5000));report.blockedLoopback='not_blocked';}
   catch(e){report.blockedLoopback=e.code;}
   report.loopback.hits=hits;
  }catch(e){report.error=String(e.stack||e);}
  finally{if(server)await new Promise(resolve=>server.close(resolve));
   fs.writeFileSync(process.env.DSH_NETWORK_TEST_RESULT,JSON.stringify(report,null,2));}
 });
});}
"""


def main():
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-bin', type=Path, required=True)
    parser.add_argument('--proxy')
    parser.add_argument('--expect-fake-ip', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    node = shutil.which('node')
    assert node and args.runtime_bin.is_file()
    results = {}
    with tempfile.TemporaryDirectory(prefix='dsh-network-runtime-') as raw:
        base = Path(raw)
        home, workspace = base / 'home', base / 'workspace'
        home.mkdir(); workspace.mkdir()
        env = isolated_environment(base / 'isolation')
        for key in list(env):
            if key.lower() in ('http_proxy', 'https_proxy', 'all_proxy', 'no_proxy', 'node_use_env_proxy'):
                env.pop(key)
        env['DSH_HOME'] = str(home)
        result = probe(node, args.runtime_bin, workspace, env=env, inspect_only=True)
        assert not result.get('error'), result
        assert not result['route']['proxied'] and not result['bridgeRoute']['proxied']
        assert result['search']['componentInstalled'] and not result['search']['tested']
        results['no_proxy_config'] = result
        update_home_proxy(home, {'http': 'http://lower:1000', 'https': 'http://user:private-fixture@127.0.0.1:7897'})
        result = probe(node, args.runtime_bin, workspace, env=env, inspect_only=True)
        assert result['route']['proxied'] and not result['bridgeRoute']['proxied'], result
        assert 'private-fixture' not in json.dumps(result) and 'user@' not in json.dumps(result)
        assert any(e['source'] == 'user-env' for e in result['proxyEntries'])
        results['redacted_user_proxy'] = result
        overridden = dict(env, HTTPS_PROXY='http://127.0.0.1:1234')
        result = probe(node, args.runtime_bin, workspace, env=overridden, inspect_only=True)
        assert result['route']['proxy'].rstrip('/') == 'http://127.0.0.1:1234', result
        assert any(e['source'] == 'process' for e in result['proxyEntries'])
        results['process_over_user'] = result
        # A project cannot choose a network route over the user's .env.
        (workspace / '.env').write_text('HTTPS_PROXY=http://127.0.0.1:1235\n', encoding='utf8')
        rejected = probe(node, args.runtime_bin, workspace, env=env, inspect_only=True)
        assert rejected.get('error'), rejected
        (workspace / '.env').unlink()
        results['project_proxy_rejected'] = rejected

        if args.proxy:
            # Actual CLI/profile boot, not just calling installProxyFromEnvironment.
            prepare = """
import {createRequire} from 'node:module';import {pathToFileURL} from 'node:url';
const require=createRequire(process.argv[1]);
const boot=await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-app-boot')));
boot.initProfile(boot.resolveProfileDir('web'),boot.PROFILE_TEMPLATES.web.bundles);
"""
            subprocess.run([node, '--input-type=module', '-e', prepare, str(args.runtime_bin.resolve())],
                           env=env, cwd=workspace, capture_output=True, check=True, timeout=30,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            inspector = base / 'network-inspector.mjs'
            inspector.write_text(INSPECTOR, encoding='utf8')
            overlay = base / 'network.patch.yml'
            overlay.write_text('- insert:\n    - id: network-inspector\n      name: ' + inspector.as_uri() + '\n', encoding='utf8')
            for mode in ('no_proxy', 'home_proxy', 'process_override'):
                (home / '.env').write_text('# fixture user configuration\nUNRELATED=value\n', encoding='utf8')
                launch_env = dict(env)
                if mode == 'home_proxy':
                    update_home_proxy(home, {'http': args.proxy, 'https': args.proxy})
                elif mode == 'process_override':
                    update_home_proxy(home, {'http': 'http://127.0.0.1:1', 'https': 'http://127.0.0.1:1'})
                    launch_env.update(HTTP_PROXY=args.proxy, HTTPS_PROXY=args.proxy)
                report_file = base / (mode + '.json')
                launch_env.update(DSH_NETWORK_TEST_CLI=str(args.runtime_bin.resolve()),
                                  DSH_NETWORK_TEST_URL=DEFAULT_URL, DSH_NETWORK_TEST_RESULT=str(report_file))
                with socket.socket() as reservation:
                    reservation.bind(('127.0.0.1', 0)); port = reservation.getsockname()[1]
                log_file = base / (mode + '.log')
                process = None
                try:
                    with log_file.open('wb') as log:
                        command = [node, str(args.runtime_bin.resolve()), 'web', '--patch', str(overlay), '--port', str(port), '--no-open']
                        process = owned.spawn_frontend(command, node=node, replace_existing=False,
                            cwd=workspace, env=launch_env, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                        deadline = time.monotonic() + 75
                        while not report_file.exists():
                            assert process.poll() is None, 'Isolated Host exited: ' + str(log_file)
                            assert time.monotonic() < deadline, 'Isolated Host probe timed out'
                            time.sleep(.1)
                    result = json.loads(report_file.read_text(encoding='utf8'))
                    assert not result.get('error'), result
                    assert result['proxied'] == (mode != 'no_proxy'), result
                    assert result['loopback'] == {'proxied': False, 'status': 200,
                        'text': 'isolated-bridge-transport', 'hits': 1}, result
                    assert result['blockedLoopback'] == 'WEB_BLOCKED_URL', result
                    if mode != 'no_proxy':
                        assert result['fetch']['status'] == 200 and result['fetch']['chars'] > 0, result
                        assert result['proxySource'] == ('process' if mode == 'process_override' else 'user-env'), result
                    elif args.expect_fake_ip:
                        assert result['fetch']['code'] == 'WEB_BLOCKED_URL', result
                    results['host_' + mode] = result
                    print(mode, json.dumps(result), flush=True)
                finally:
                    if process is not None:
                        owned.stop_owned(process)
                        process.wait(timeout=15)
                    if args.output:
                        args.output.mkdir(parents=True, exist_ok=True)
                        # Host logs contain launch authentication tokens; do not export them.
                        if report_file.exists():
                            shutil.copyfile(report_file, args.output / report_file.name)
        if args.output:
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf8')
    print('Native DSH diagnostics/configuration checks passed; no live Host, HIP or model call', flush=True)


if __name__ == '__main__':
    main()
