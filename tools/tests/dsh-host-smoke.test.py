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
parser.add_argument('--browser', action='store_true', help='Verify the official browser and native mode/session navigation')
parser.add_argument('--context-loop', action='store_true', help='Run a scripted provider through the real DSH loop and local Bridge fixture')
parser.add_argument('--repetition-method', action='store_true', help='Also verify native/nested reference delivery to the scripted provider')
parser.add_argument('--surface-method', action='store_true', help='Verify surface/COP skills and native/nested reference delivery at the actual provider')
parser.add_argument('--outcome-fixture', type=Path, help='Exact receipts exported by isolated caught-failure HOM regression')
parser.add_argument('--catalog-fixture', type=Path, help='Exact receipt exported by isolated parameter-catalog HOM regression')
parser.add_argument('--hda-fixture', type=Path, help='Exact receipt exported by isolated HDA lifecycle regression')
parser.add_argument('--geometry-fixture', type=Path, help='Exact large-output control receipt exported by isolated HOM')
parser.add_argument('--script-fixture', type=Path, help='Exact script source, identity and complete receipt exported by isolated execution-runtime HOM')
parser.add_argument('--render-fixture', type=Path, help='Exact multi-product Bridge receipt exported by isolated camera-framing HOM')
args = parser.parse_args()
if args.repetition_method and not args.context_loop:
    parser.error('--repetition-method requires --context-loop')
if args.surface_method and not args.context_loop:
    parser.error('--surface-method requires --context-loop')
if args.script_fixture and not args.context_loop:
    parser.error('--script-fixture requires --context-loop')
if args.render_fixture and not args.context_loop:
    parser.error('--render-fixture requires --context-loop')
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
# An exact historical receipt must be consumed under its recorded executor;
# inventing another identity would create contradictory successful history.
# The local fixture still owns the HTTP endpoint and never contacts live HOM.
script_receipt = json.loads(args.script_fixture.resolve(strict=True).read_text(encoding='utf-8')) if args.script_fixture else None
render_receipt = json.loads(args.render_fixture.resolve(strict=True).read_text(encoding='utf-8')) if args.render_fixture else None
recorded_execution = (script_receipt['receipt']['execution'] if script_receipt else
                      render_receipt['execution'] if render_receipt else None)
env['DSH_HOUDINI_EXECUTOR_ID'] = recorded_execution['executor_id'] if recorded_execution else uuid.uuid4().hex
context_output = fixture / 'context-loop.json'
if args.context_loop:
    # The fixture plugin owns this port and never opens or executes a real HIP.
    bridge_socket.close()
    env['DSH_CONTEXT_FIXTURE_OUT'] = str(context_output)
    if args.repetition_method:
        env['DSH_REPETITION_METHOD_FIXTURE'] = '1'
    if args.surface_method:
        env['DSH_SURFACE_METHOD_FIXTURE'] = '1'
    if args.outcome_fixture:
        env['DSH_OUTCOME_FIXTURE'] = str(args.outcome_fixture.resolve(strict=True))
    if args.catalog_fixture:
        env['DSH_CATALOG_FIXTURE'] = str(args.catalog_fixture.resolve(strict=True))
    if args.hda_fixture:
        env['DSH_HDA_PRESENTATION_FIXTURE'] = str(args.hda_fixture.resolve(strict=True))
    if args.geometry_fixture:
        env['DSH_GEOMETRY_PRESENTATION_FIXTURE'] = str(args.geometry_fixture.resolve(strict=True))
    if args.script_fixture:
        env['DSH_SCRIPT_FIXTURE'] = str(args.script_fixture.resolve(strict=True))
    if args.render_fixture:
        env['DSH_RENDER_FIXTURE'] = str(args.render_fixture.resolve(strict=True))
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
output_file = fixture / 'composition.json'
env['DSH_COMPOSITION_FIXTURE_OUT'] = str(output_file)
inspector = fixture / 'inspect.mjs'
inspector.write_text("import {createUserMessage,createToolResultMessage} from "
    +json.dumps((cache / 'node_modules/@deepseek-ai/dsh-llm/lib/index.js').as_uri())+";\n"
    +"import {auditStartupEntries} from "+json.dumps((cache / 'node_modules/@deepseek-ai/dsh-app-boot/lib/index.js').as_uri())+";\n"+"""
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
          const activation=await auditStartupEntries(ctx,'owned-smoke',()=>{});
          const services={workspaceRegistry:ctx.get('workspaceRegistry')!==undefined,workspaceController:ctx.get('workspaceController')!==undefined,
            houdiniTargets:ctx.get('houdiniTargets')!==undefined,houdiniFrontend:ctx.get('houdiniFrontend')!==undefined};
          if(!disposed)fs.writeFileSync(process.env.DSH_COMPOSITION_FIXTURE_OUT,JSON.stringify({roster,tools,graph,rootEntries,activation,services}));
        } finally {await lease[Symbol.asyncDispose]();}
      } catch(error) {
        if(!disposed)fs.writeFileSync(process.env.DSH_COMPOSITION_FIXTURE_OUT,JSON.stringify({error:String(error.stack||error)}));
      }
    });
    // Seed only the owned browser fixture's log, never inbox/run(). This makes
    // the official nonempty conversation surface visible without a model call.
    let seedDone=false;
    const seedFile=process.env.DSH_COMPOSITION_FIXTURE_OUT+'.seed';
    const seedTimer=setInterval(async () => {
      const sidebarFile=process.env.DSH_COMPOSITION_FIXTURE_OUT+'.sidebar';
      if(fs.existsSync(sidebarFile)) {
        const ids=JSON.parse(fs.readFileSync(sidebarFile,'utf8'));
        if(ids.every(id=>ctx.agents.get(id))) {
          for(const id of ids) {
            const session=ctx.agents.get(id).session;
            session.append('turn/start',{turn:1});
            session.append('user/message',createUserMessage({source:{kind:'user'},
              content:[{type:'text',text:'Owned mode fixture '+id}]}),{surfaceOp:'append'});
            session.append('turn/end',{turn:1,reason:{kind:'completed'}});
          }
          fs.unlinkSync(sidebarFile);
        }
      }
      if(seedDone||!fs.existsSync(seedFile))return;
      try {
        const id=fs.readFileSync(seedFile,'utf8').trim();
        const agent=ctx.agents.get(id);
        if(!agent)return;
        agent.session.append('turn/start',{turn:2});
        agent.session.append('user/message',createUserMessage({source:{kind:'user'},
          content:[{type:'text',text:'Isolated UI fixture: inspect Trace and tool documentation.'}]}),{surfaceOp:'append'});
        for (const [callId,name,args,result] of [
          ['ui-inspect','houdini_inspect',{code:'__result__ = scene_info()'},{ok:true,result:{objects:[]},execution:{hip_dir:null,hip_is_new:true}}],
          ['ui-create','houdini_exec',{code:'tab_create("/obj", "geo", "asset")'},{ok:true,verbs:[{verb:'tab_create',ms:5,args:['/obj','geo','asset'],ok:true,result:'/obj/asset'}],execution:{hip_dir:null,hip_is_new:true}}],
          ['ui-failure','houdini_exec',{code:'set_parms("/obj/asset", {unknown: 1})'},{ok:false,error:'参数不存在：unknown',verbs:[{verb:'set_parms',args:['/obj/asset',{unknown:1}],ms:1,ok:false,error:'参数不存在：unknown'}],execution:{hip_dir:null,hip_is_new:true}}],
          ['ui-warning','houdini_exec',{code:'verify_network("/obj/asset", output="/obj/asset/OUT")'},
            {ok:true,outcome:{batch:'completed',operations:{total:1,failed:0},checks:{failed:0,warning:1,unverified:0}},
             verbs:[{verb:'verify_network',ok:true,check_status:'warning',args:['/obj/asset'],ms:1,
               result:{output:'/obj/asset/OUT',warnings:['夹具：输出存在属性警告']}}],execution:{hip_dir:null,hip_is_new:true}}],
        ]) {
          agent.session.append('tool/call',{turn:2,step:1,callId,name,arguments:JSON.stringify(args)});
          agent.session.append('tool/result',{turn:2,step:1,message:createToolResultMessage({callId,
            content:[{type:'text',text:JSON.stringify(result)}],isError:!result.ok}),meta:{canonical:result}},{surfaceOp:'append'});
        }
        agent.session.append('turn/end',{turn:2,reason:{kind:'completed'}});
        seedDone=true;
        await ctx.get('sessions').flush(agent.session);
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
        houdini = next(row for row in presets if row['id'] == 'houdini')
        standard = next(row for row in presets if row['id'] == 'standard')
        assert standard['isDefault'] and not houdini['isDefault'], facts
        assert 'broken' not in houdini and 'broken' not in standard, facts
        assert len(presets) >= 4, facts
        expected={'houdini_inspect','houdini_exec','houdini_ui_list','houdini_ui_screenshot','houdini_request','houdini_resource','houdini_capabilities',
            'houdini_job_submit','houdini_isolated'}
        assert {name for name in facts['tools'] if name.startswith('houdini_')} == expected, facts
        assert 'present' in facts['tools'] and 'skill' in facts['tools'], facts
        assert any(row['name'] == 'dsh-houdini' and not row['disabled']
                   for row in facts['rootEntries']), facts
        graph_rows = facts['graph'] if isinstance(facts['graph'], list) else facts['graph']['entries']
        assert sum(row['id'] == 'dsh-houdini' for row in graph_rows) == 1, [row['id'] for row in graph_rows]
        auth.authorize(timeout=5)
        assert rpc('agentPresets/list', {}) == facts['roster']
        default_workspace=rpc('workspace/create', {'request': {'path': str(fixture)}})['workspace']
        default=rpc('session/create', {'request':{'sessionId':uuid.uuid4().hex,'workspaceId':default_workspace['workspaceId']}})
        assert default['agentPreset']=='standard', default
        created=rpc('session/create', {'request':{'sessionId':uuid.uuid4().hex,'cwd':str(fixture),'agentPreset':'houdini'}})
        assert created['agentPreset']=='houdini', created
        print('Official DSH Web: native default/other presets preserved, additive Houdini preset, scoped tools and explicit session passed', flush=True)
        if args.context_loop:
            deadline=time.monotonic()+90
            while not context_output.exists():
                assert process.poll() is None, 'Host exited; inspect ' + str(log)
                assert time.monotonic()<deadline, 'Context loop timed out; inspect ' + str(log)
                time.sleep(.25)
            context_facts=json.loads(context_output.read_text(encoding='utf-8'))
            assert context_facts.get('ok') is True, context_facts.get('error', context_facts)
            print('Exact DSH loop: settled errors/repair do not repeat scene/vision; uncertain requests and active jobs retain recovery context', flush=True)
            if args.script_fixture:
                assert context_facts.get('script_consumption', {}).get('record'), context_facts
                print('Exact DSH script consumer: native/PTC source bytes, version rejection, current Host ownership and original independent-HOM canonical receipt passed; HTTP fixture executes no new scene', flush=True)
            if args.render_fixture:
                assert context_facts.get('render_consumption', {}).get('outputs') == render_receipt['result']['outputs'], (
                    'Original render output values changed in the DSH report; inspect ' + str(context_output))
                print('Exact DSH render consumer: native/PTC multi-product paths, freshness and unverified checkpoint/delegate facts preserved; historical mock receipt does not verify Karma pixels', flush=True)
        desktop_deadline=time.monotonic()+10
        while not rpc('houdiniFrontend/capabilities', {})['desktop']:
            assert time.monotonic()<desktop_deadline, 'Root plugin Desktop integration did not become available'
            time.sleep(.1)
        if args.browser_module or args.browser:
            first, second = fixture / 'test49', fixture / 'test51'
            first.mkdir(); second.mkdir()
            browser_sessions = []
            for directory in [first, second]:
                workspace = rpc('workspace/create', {'request': {'path': str(directory)}})['workspace']
                browser_session=rpc('session/create', {'request': {'sessionId': uuid.uuid4().hex,
                    'workspaceId': workspace['workspaceId'], 'agentPreset': 'houdini'}})
                assert browser_session['agentPreset']=='houdini', browser_session
                browser_sessions.append(browser_session['sessionId'])
            Path(str(output_file)+'.sidebar').write_text(json.dumps([default['sessionId'],*browser_sessions]), encoding='utf-8')
            browser_config = fixture / 'browser-config.json'
            browser_config.write_text(json.dumps({'base': f'http://127.0.0.1:{port}/',
                'first': str(first), 'second': str(second), 'output': str(fixture),
                'firstSession': browser_sessions[0], 'secondSession': browser_sessions[1], 'standardSession': default['sessionId'],
                'seedFile': str(output_file)+'.seed',
                'browser': r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                'cookies': [{'name': cookie.name, 'value': cookie.value,
                    'url': f'http://127.0.0.1:{port}/', 'httpOnly': True} for cookie in auth._cookies]}), encoding='utf-8')
            subprocess.run([node, str(ROOT / 'tools/tests/dsh-client-navigation.mjs'),
                str(browser_config)], cwd=ROOT, env=env, check=True, timeout=120)
    finally:
        runtime.stop_owned(process)
        process.wait(timeout=15)
        bridge_socket.close()
