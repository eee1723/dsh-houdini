"""Verify the installed DSH Web/preset contract without model calls or Houdini.

Usage: python tools/tests/dsh-host-smoke.test.py --runtime-cache <npm cache root>
The cache contains node_modules/@deepseek-ai/dsh. Each run owns a fresh profile,
reserved non-listening Bridge port, temporary Host and diagnostic output.
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
from houdini_test_environment import isolated_environment
from dsh_web_auth import DshWebSession
import dsh_managed_runtime as runtime

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-cache', type=Path, required=True)
parser.add_argument('--browser-module', type=Path)
parser.add_argument('--context-loop', action='store_true', help='Run a scripted provider through the real DSH loop and local Bridge fixture')
parser.add_argument('--outcome-fixture', type=Path, help='Exact receipts exported by isolated caught-failure HOM regression')
args = parser.parse_args()
cache = args.runtime_cache.resolve(strict=True)
node = shutil.which('node')
assert node
preferred = json.loads((ROOT / 'dsh-runtime-compatibility.json').read_text(encoding='utf-8'))['preferredVersion']
assert json.loads((cache / 'node_modules/@deepseek-ai/dsh/package.json').read_text())['version'] == preferred
fixture = Path(tempfile.mkdtemp(prefix='dsh-host-smoke-'))
print('Isolated evidence:', fixture, flush=True)
env = isolated_environment(fixture)
subprocess.run([node, str(ROOT / 'tools/tests/prepare-shared-host-fixture.mjs'),
    str(cache / 'node_modules/@deepseek-ai/dsh/lib/bin.js'), env['DSH_HOME'], str(ROOT)],
    cwd=ROOT, env=env, check=True, timeout=60, capture_output=True)
bridge_socket = socket.socket()
bridge_socket.bind(('127.0.0.1', 0))
env['DSH_HOUDINI_BRIDGE_URL'] = f'http://127.0.0.1:{bridge_socket.getsockname()[1]}'
env['DSH_HOUDINI_EXECUTOR_ID'] = uuid.uuid4().hex
context_output = fixture / 'context-loop.json'
if args.context_loop:
    # The fixture plugin owns this port and never opens or executes a real HIP.
    bridge_socket.close()
    env['DSH_CONTEXT_FIXTURE_OUT'] = str(context_output)
    if args.outcome_fixture:
        env['DSH_OUTCOME_FIXTURE'] = str(args.outcome_fixture.resolve(strict=True))
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
output_file = fixture / 'composition.json'
env['DSH_COMPOSITION_FIXTURE_OUT'] = str(output_file)
inspector = fixture / 'inspect.mjs'
inspector.write_text("""
import fs from 'node:fs';
export const inject=['loader','tools','agentPresets','clientModules','agents'];
export function apply(ctx) {
  ctx.effect(() => {
    let disposed=false;
    queueMicrotask(async () => {
      try {
        await ctx.loader.await();
        const roster=await ctx.agentPresets.remoteExportList();
        const lease=await ctx.agentPresets.acquireScope('houdini');
        try {
          const tools=ctx.tools.schemas(lease.key).map(tool=>tool.name);
          const graph=ctx.clientModules.graph();
          const rootEntries=[...ctx.loader.entries()].map(entry=>({name:entry.options.name,disabled:entry.disabled}));
          if(!disposed)fs.writeFileSync(process.env.DSH_COMPOSITION_FIXTURE_OUT,JSON.stringify({roster,tools,graph,rootEntries}));
        } finally {await lease[Symbol.asyncDispose]();}
      } catch(error) {
        if(!disposed)fs.writeFileSync(process.env.DSH_COMPOSITION_FIXTURE_OUT,JSON.stringify({error:String(error.stack||error)}));
      }
    });
    // Seed only the owned browser fixture's log, never inbox/run(). This makes
    // the official nonempty conversation surface visible without a model call.
    let seedDone=false;
    const seedFile=process.env.DSH_COMPOSITION_FIXTURE_OUT+'.seed';
    const seedTimer=setInterval(() => {
      if(seedDone||!fs.existsSync(seedFile))return;
      try {
        const id=fs.readFileSync(seedFile,'utf8').trim();
        const agent=ctx.agents.get(id);
        if(!agent)return;
        agent.session.append('user/message',{role:'user',source:{kind:'user'},
          content:[{type:'text',text:'Isolated UI fixture: inspect Trace and tool documentation.'}]},{surfaceOp:'append'});
        for (const [callId,name,args,result] of [
          ['ui-inspect','houdini_inspect',{code:'__result__ = scene_info()'},{ok:true,result:{objects:[]},execution:{hip_dir:null,hip_is_new:true}}],
          ['ui-create','houdini_exec',{code:'tab_create("/obj", "geo", "asset")'},{ok:true,verbs:[{verb:'tab_create',ms:5,args:['/obj','geo','asset'],ok:true,result:'/obj/asset'}],execution:{hip_dir:null,hip_is_new:true}}],
          ['ui-failure','houdini_exec',{code:'set_parms("/obj/asset", {unknown: 1})'},{ok:false,error:'参数不存在：unknown',verbs:[{verb:'set_parms',args:['/obj/asset',{unknown:1}],ms:1,ok:false,error:'参数不存在：unknown'}],execution:{hip_dir:null,hip_is_new:true}}],
          ['ui-warning','houdini_exec',{code:'verify_network("/obj/asset", output="/obj/asset/OUT")'},
            {ok:true,outcome:{batch:'completed',operations:{total:1,failed:0},checks:{failed:0,warning:1,unverified:0}},
             verbs:[{verb:'verify_network',ok:true,check_status:'warning',args:['/obj/asset'],ms:1,
               result:{output:'/obj/asset/OUT',warnings:['夹具：输出存在属性警告']}}],execution:{hip_dir:null,hip_is_new:true}}],
        ]) {
          agent.session.append('tool/call',{turn:1,step:1,callId,name,arguments:JSON.stringify(args)});
          agent.session.append('tool/result',{turn:1,step:1,message:{role:'tool',source:{kind:'tool',callId},
            content:[{type:'text',text:JSON.stringify(result)}],isError:!result.ok},meta:{canonical:result}},{surfaceOp:'append'});
        }
        seedDone=true;
        fs.writeFileSync(seedFile+'.done','ok');
      } catch(error) {fs.writeFileSync(seedFile+'.error',String(error.stack||error));}
    },100);
    return () => {disposed=true;clearInterval(seedTimer);};
  });
}
""", encoding='utf-8')
overlay = fixture / 'inspect.patch.yml'
overlay_text = '- insert:\n    - id: composition-inspector\n      name: ' + inspector.as_uri() + '\n'
if args.context_loop:
    overlay_text += '    - id: context-loop-fixture\n      name: ' + (ROOT / 'tools/tests/dsh-context-loop-fixture.mjs').as_uri() + '\n'
overlay.write_text(overlay_text, encoding='utf-8')
log = fixture / 'host.log'
auth = DshWebSession(f'http://127.0.0.1:{port}', str(log), str(fixture / 'runtime.json'))
def rpc(method, arguments):
    body=json.dumps({'type':'client-request','rpcId':uuid.uuid4().hex,'method':method,'payload':{'args':arguments}}).encode()
    request=urllib.request.Request(f'http://127.0.0.1:{port}/api/{method}', data=body,
        headers={'Content-Type':'application/json'}, method='POST')
    with auth.open(request, timeout=5) as response:
        result=json.load(response)['result']
        assert result['ok'], result
        return result['value']
with log.open('wb') as output:
    process=runtime.spawn_frontend([node,str(cache / 'node_modules/@deepseek-ai/dsh/lib/bin.js'),
        'web','--patch',str(overlay),'--port',str(port),'--no-open'], node=node, cwd=fixture, env=env,
        stdout=output, stderr=subprocess.STDOUT, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        deadline=time.monotonic()+60
        while not output_file.exists():
            assert process.poll() is None, 'Host exited; inspect ' + str(log)
            assert time.monotonic()<deadline, 'Host composition timed out; inspect ' + str(log)
            time.sleep(.25)
        facts=json.loads(output_file.read_text(encoding='utf-8'))
        assert 'error' not in facts, facts
        presets=facts['roster']['presets']
        assert len(presets)==1 and presets[0]['id']=='houdini' and presets[0]['isDefault'], facts
        assert 'broken' not in presets[0], facts
        expected={'houdini_inspect','houdini_exec','houdini_request','houdini_resource','houdini_capabilities',
            'houdini_job_submit','houdini_job_status','houdini_job_cancel'}
        assert {name for name in facts['tools'] if name.startswith('houdini_')} == expected, facts
        assert 'present' in facts['tools'] and 'skill' in facts['tools'], facts
        assert any(row['name'] == 'dsh-houdini' and not row['disabled']
                   for row in facts['rootEntries']), facts
        graph_rows = facts['graph'] if isinstance(facts['graph'], list) else facts['graph']['entries']
        assert sum(row['id'] == 'dsh-houdini' for row in graph_rows) == 1, [row['id'] for row in graph_rows]
        auth.authorize(timeout=5)
        assert rpc('agentPresets/list', {}) == facts['roster']
        created=rpc('session/create', {'request':{'sessionId':uuid.uuid4().hex,'cwd':str(fixture)}})
        assert created['agentPreset']=='houdini', created
        print('Exact DSH Web: browser module delivered, one Houdini preset, eight scoped tools and default session passed', flush=True)
        if args.context_loop:
            deadline=time.monotonic()+90
            while not context_output.exists():
                assert process.poll() is None, 'Host exited; inspect ' + str(log)
                assert time.monotonic()<deadline, 'Context loop timed out; inspect ' + str(log)
                time.sleep(.25)
            context_facts=json.loads(context_output.read_text(encoding='utf-8'))
            assert context_facts.get('ok') is True, context_facts.get('error', context_facts)
            print('Exact DSH loop: settled errors/repair do not repeat scene/vision; uncertain requests and active jobs retain recovery context', flush=True)
        if args.browser_module:
            first, second = fixture / 'test49', fixture / 'test51'
            first.mkdir(); second.mkdir()
            browser_config = fixture / 'browser-config.json'
            browser_config.write_text(json.dumps({'base': f'http://127.0.0.1:{port}/',
                'first': str(first), 'second': str(second), 'output': str(fixture),
                'seedFile': str(output_file)+'.seed',
                'browser': r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                'cookies': [{'name': cookie.name, 'value': cookie.value,
                    'url': f'http://127.0.0.1:{port}/', 'httpOnly': True} for cookie in auth._cookies]}), encoding='utf-8')
            subprocess.run([node, str(ROOT / 'tools/tests/dsh-client-navigation.mjs'),
                str(args.browser_module.resolve()), str(browser_config)], cwd=ROOT, env=env, check=True, timeout=90)
    finally:
        runtime.stop_owned(process)
        process.wait(timeout=15)
        bridge_socket.close()
