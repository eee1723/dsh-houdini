"""Real H21/H22 Qt page sends/stops/reconnects against an owned HTTP provider.

Reuses dsh-source-webview's GUI/Host harness; all scene edits use its real Bridge.
The provider is scripted: this verifies transport and public editing, not LLM
autonomy or semantic vision. Only authored temporary preferences and HIPs load.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, launch_directory, reexec_unpacked_test_cli
spec = importlib.util.spec_from_file_location('source_webview_harness', Path(__file__).with_name('dsh-source-webview.test.py'))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


PAGE = r"""
(() => {
  if(window.__dshSourceAcceptance)return;
  const config=CONFIG_JSON,stored=JSON.parse(sessionStorage.getItem('qt-loop-resume')||'null');
  const state=window.__dshSourceAcceptance={phase:'selection',done:false,facts:stored?.facts||{scriptedProvider:true,semanticVision:'unverified'}};
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const visible=element=>{if(!element||element.closest('[inert],[hidden],[aria-hidden="true"]'))return false;
    const box=element.getBoundingClientRect(),style=getComputedStyle(element);
    return box.width>0&&box.height>0&&style.visibility!=='hidden'&&style.display!=='none'};
  const wait=async(fn,label)=>{const end=Date.now()+40000;while(Date.now()<end){const value=fn();if(value)return value;await sleep(100)}throw Error('Timed out: '+label)};
  const check=(value,label)=>{if(!value)throw Error(label)};
  const button=name=>[...document.querySelectorAll('button')].find(element=>visible(element)&&(element.getAttribute('aria-label')===name||element.textContent.trim()===name));
  const normalized=value=>String(value||'').replace(/\\/g,'/').replace(/\/+$/,'').toLowerCase();
  async function rpc(method,args){const response=await fetch('/api/'+method,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({type:'client-request',rpcId:'qt-loop-'+Date.now(),method,payload:{args}})});const wire=await response.json();check(wire.result?.ok,'RPC '+method);return wire.result.value}
  async function command(action){const id=action+'-'+Date.now();state.command={id,action,sessionId:state.facts.selection.sessionId};
    const answer=await wait(()=>window.__dshSourceCommandResponse?.id===id?window.__dshSourceCommandResponse:null,action);check(answer.ok,answer.error);return answer.result}
  async function send(stage){state.phase='send-'+stage;
    const intro=button('继续');if(intro){intro.click();await sleep(200)}
    const editor=await wait(()=>{const found=document.querySelector('[data-composer-input][contenteditable="true"]');
      if(!visible(found)||found.closest('[inert]'))return null;found.focus();return document.activeElement===found?found:null},'focused native composer');
    const prompts={BUILD:'创建可调的立柱阵列，提供数量、高度、柱宽和间距控制，封装成 HDA 并保存工程。',
      STOP:'开始一段长回复，稍后我会点击停止。',UNKNOWN:'将示例立柱高度改为 1.4 并保存；回执未知时查回原请求。',
      RECONNECT:'继续讲解这个示例，在回复过程中我会重连页面。',AFTER:'读取当前示例控制和实际输出，确认重连后仍是同一工程。',
      IMAGE:'生成这个示例输出的检查图片，保留真实工具图片回执。'};
    const value=prompts[stage]+'\nGUI_CASE_'+stage,rect=editor.getBoundingClientRect(),id='input-'+stage+'-'+Date.now();
    state.input={id,text:value,x:rect.x+Math.min(100,rect.width/2),y:rect.y+Math.min(20,rect.height/2)};
    await wait(()=>window.__dshQtInput===id&&document.querySelector('[data-composer-input]')?.innerText.trim()===value,'actual native input');
    const action=await wait(()=>{const found=button('发送消息');return found&&!found.disabled?found:null},'enabled native send');action.click();
    await wait(()=>document.body.innerText.includes('GUI_'+stage+'_STREAM')||document.body.innerText.includes('GUI_'+stage+'_DONE'),stage+' real response');
  }
  async function settled(stage){await wait(()=>document.body.innerText.includes('GUI_'+stage+'_DONE'),stage+' completed text');
    await wait(()=>!button('停止生成'),'turn settled');await sleep(300)}
  async function screenshot(label){state.capture=label;await wait(()=>window.__dshQtCapture===label,'Qt capture '+label)}
  (async()=>{
    const selected=await wait(()=>window.__dshHoudiniSelection?.(),'native selected session');
    check(normalized(selected.cwd)===normalized(config.workspace),'workspace differs');check(selected.agentPreset==='houdini','preset differs');
    if(stored)check(selected.sessionId===stored.facts.selection.sessionId,'reload selected another task');else state.facts.selection=selected;
    await wait(()=>!new URL(location.href).searchParams.has('dsh-houdini-workspace'),'navigation consumed');
    const continueButton=button('继续');if(continueButton)continueButton.click();
    const later=button('稍后配置');if(later)later.click();
    if(!stored){
      await rpc('session/selectModel',{request:{sessionId:selected.sessionId,provider:config.provider,model:config.model}});
      await sleep(500);
      await send('BUILD');await settled('BUILD');
      const builtSnapshot=await command('snapshot');
      const buildResult=builtSnapshot.events.find(event=>event.type==='tool/result'&&event.data?.message?.source?.callId==='qt-build')?.data?.meta?.canonical;
      check(buildResult?.ok===true,buildResult?.error||'real authored build did not succeed');
      state.facts.build=true;await screenshot('qt-built-example');
      state.nativeCapture='houdini-post-array';await wait(()=>window.__dshNativeCapture===state.nativeCapture,'actual Houdini example screenshot');
      await send('IMAGE');await settled('IMAGE');
      const imageSnapshot=await command('snapshot');
      const imageEvent=imageSnapshot.events.find(event=>event.type==='tool/result'&&event.data?.message?.source?.callId==='qt-image');
      const imageResult=imageEvent?.data?.meta?.canonical;
      check(imageResult?.ok===true,imageResult?.error||'real image operation failed');
      const attached=imageResult.imageAttachments?.find(item=>item.attachment);
      check(attached,'real tool result has no native attachment');
      state.facts.imageAttachment={from:attached.from,attachment:attached.attachment,semanticVision:'unverified'};
      const turnProcess=document.querySelector('[data-turn-process="'+imageEvent.data.turn+'"][aria-expanded="false"]');
      if(turnProcess)turnProcess.click();await sleep(100);
      for(const process of document.querySelectorAll('[data-process-activity][aria-expanded="false"]'))if(visible(process))process.click();
      const imageTool=await wait(()=>[...document.querySelectorAll('[data-tool="houdini_exec"]')].find(element=>visible(element)&&element.textContent.includes('artist-guide-check.png')),'original visible tool image card');
      state.facts.imageConsumerSurface='standard DSH conversation tool result';
      const expand=imageTool.querySelector('[data-disclosure-row][aria-expanded="false"]');if(expand)expand.click();
      await wait(()=>imageTool.querySelector('[data-disclosure-row]')?.getAttribute('aria-expanded')==='true','native tool result expanded');
      imageTool.scrollIntoView({block:'center'});
      const shown=await wait(()=>[...imageTool.querySelectorAll('img')].find(image=>visible(image)&&image.complete&&image.naturalWidth===480&&image.naturalHeight===320),'native tool result image decode');
      state.facts.inlineImage={width:shown.naturalWidth,height:shown.naturalHeight,sourceScheme:new URL(shown.src,location.href).protocol,alt:shown.alt};
      await screenshot('qt-native-tool-image');
      [...document.querySelectorAll('[role=tab]')].find(element=>element.textContent.trim()==='对话').click();
      await send('STOP');await wait(()=>button('停止生成'),'native stop');button('停止生成').click();
      await wait(()=>!button('停止生成'),'stop settled');check(!document.body.innerText.includes('GUI_STOP_DONE'),'stop allowed scripted completion');
      state.facts.stop=true;await screenshot('qt-stopped-turn');
      await send('UNKNOWN');await settled('UNKNOWN');
      const trace=[...document.querySelectorAll('[role=tab]')].find(element=>element.textContent.trim()==='执行记录');
      check(trace,'Trace tab unavailable');trace.click();await wait(()=>visible(document.querySelector('.dsh-trace')),'real Trace');
      check(document.body.innerText.includes('结果未知')||document.body.innerText.includes('unknown_transport'),'lost response not presented');
      state.facts.unknownRecovered=true;await screenshot('qt-recovered-request');
      [...document.querySelectorAll('[role=tab]')].find(element=>element.textContent.trim()==='对话').click();
      await send('RECONNECT');
      state.phase='frontend-disconnect';state.facts.reconnectStarted=true;
      sessionStorage.setItem('qt-loop-resume',JSON.stringify({facts:state.facts}));location.reload();return;
    }
    await settled('RECONNECT');state.facts.reconnectedSameTask=true;
    await send('AFTER');await settled('AFTER');
    const snapshot=await command('snapshot'),events=snapshot.events;
    const calls=events.filter(event=>event.type==='tool/call').map(event=>event.data);
    const results=events.filter(event=>event.type==='tool/result').map(event=>event.data);
    check(calls.filter(call=>call.callId==='qt-build').length===1,'build executed more than once');
    check(calls.filter(call=>call.callId==='qt-unknown').length===1,'lost operation resubmitted');
    const unknown=results.find(result=>result.message?.source?.callId==='qt-unknown')?.meta?.canonical;
    const recovered=results.find(result=>result.message?.source?.callId==='qt-recover')?.meta?.canonical;
    check(unknown?.requestReceipt?.status==='unknown_transport','unknown result not retained');
    check(recovered?.ok===true&&recovered.requestReceipt?.retrieved===true&&recovered.requestReceipt?.status==='done','original result not recovered');
    check(unknown.requestReceipt.request_ref===recovered.requestReceipt.request_ref,'recovery changed request');
    const built=results.find(result=>result.message?.source?.callId==='qt-build')?.meta?.canonical;
    check(built?.ok===true&&built.execution?.owner_session===selected.sessionId,'real execution/task identity missing');
    state.facts.runtime={executor:built.execution.executor_id,runtime:built.execution.runtime_id,hip:built.execution.hip_path};
    state.facts.toolCalls=calls.map(call=>({id:call.callId,name:call.name}));
    state.facts.savedHeader=snapshot.header;state.facts.duplicateExecution=false;
    const listed=await rpc('session/list',{_request:{}});
    check(listed.items.filter(row=>normalized(row.cwd)===normalized(config.workspace)).length===1,'reconnect duplicated task');
    await screenshot('qt-reconnected-example');sessionStorage.removeItem('qt-loop-resume');state.phase='complete';state.done=true;state.ok=true;
  })().catch(error=>{state.done=true;state.ok=false;state.error=String(error.stack||error)});
})();
"""


def build_code(workspace):
    library = str(workspace / 'otls/post-array.hda')
    hip = str(workspace / 'artist-guide.hip')
    layout = [
        {'type':'int','name':'count','label':'数量','default':4,'min':2,'max':16},
        {'type':'float','name':'height','label':'高度','default':1.2,'min':.1,'max':3.},
        {'type':'float','name':'width','label':'柱宽','default':.18,'min':.02,'max':.5},
        {'type':'float','name':'spacing','label':'间距','default':.6,'min':.2,'max':1.5},
    ]
    return f"""g=tab_create('/obj','geo',name='artist_guide')
n=tab_create(g,'subnet',name='posts')
create_spare_parms(n,layout={layout!r})
shape=tab_create(n,'box',name='post_shape',parms={{'sizex':'ch("../width")','sizey':'ch("../height")','sizez':'ch("../width")','ty':'ch("../height")/2'}})
line=tab_create(n,'line',name='array_points',parms={{'dirx':1,'diry':0,'dirz':0,'points':'ch("../count")','dist':'(ch("../count")-1)*ch("../spacing")'}})
copies=tab_create(n,'copytopoints',name='repeat_posts',inputs=[shape,line])
outputs=[child for child in n.children() if child.type().name()=='output']
assert len(outputs)<=1,'new subnet has ambiguous native output ports'
if outputs:
    out=outputs[0]
    connect(copies,out)
else:
    out=tab_create(n,'output',name='output',inputs=[copies])
sop_set_output(out)
tests=test_controls(n,out,[
 {{'id':'count','values':{{'count':6}},'expectations':[{{'metric':'primitive_count','delta':[12,12]}},{{'metric':'bounds_size','axis':0,'delta':[1.199999,1.200001]}}]}},
 {{'id':'height','values':{{'height':1.5}},'expectations':[{{'metric':'bounds_size','axis':1,'delta':[.299999,.300001]}}]}},
 {{'id':'spacing','values':{{'spacing':.8}},'expectations':[{{'metric':'bounds_size','axis':0,'delta':[.599999,.600001]}}]}}
])
assert tests['control_summary']['status']=='pass',tests
verify_network(g,output=n)
created=hda_create(n,'artistguide::post_array::1.0',description='Post Array',hda_file={library!r})
n=hou.node(created['node'])
if n.isLockedHDA():
    plan=hda_edit(n,'unlock',dry_run=True)
    hda_edit(n,'unlock',expected_plan=plan['plan_sha256'])
plan=hda_edit(n,'promote',dry_run=True)
hda_edit(n,'promote',expected_plan=plan['plan_sha256'])
example=tab_create(g,'artistguide::post_array::1.0',name='post_array_example',parms={{'count':6,'height':1.5,'spacing':.7}})
sop_set_output(example)
layout_nodes(g)
verify_network(g,output=example)
__result__=present_nodes([{{'node':example.path(),'label':'阵列控制','role':'control','description':'调整数量、高度、柱宽和间距'}}])
scene_save(expected_path={hip!r})
"""


def start_gui_probe():
    import hou
    from hutil.Qt import QtCore
    config_path = Path(os.environ['DSH_SOURCE_GUI_CONFIG'])
    config = json.loads(config_path.read_text(encoding='utf-8'))
    sys.path.insert(0,str(ROOT / 'houdini/python3.11libs'))
    import dsh_bridge as bridge
    hou.hipFile.save(str(Path(config['workspace'])/'artist-guide.hip'))
    bridge.start(config['actualBridgePort'])
    base.atomic_json(config['bridgeReady'], {'executor':bridge._EXECUTOR_ID,'runtime':bridge._RUNTIME_ID})
    timer=QtCore.QTimer(hou.qt.mainWindow())
    def ready():
        if Path(config['authenticationFile']).exists():
            timer.stop()
            base.start_gui_probe()
    timer.timeout.connect(ready)
    timer.start(200)
    hou.session._dsh_interaction_bootstrap=timer


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0))
        return probe.getsockname()[1]


def reopen_example(executable, run, workspace):
    """New same-version interpreter opens only the HIP/HDA just authored here."""
    script=run/'reopen-example.py'
    result=run/'reopen-result.json'
    source_hip=workspace/'artist-guide.hip'
    project=Path(tempfile.mkdtemp(prefix='dsh-artist-guide-reopen-'))
    hip=project/'artist-guide.hip'
    updated=project/'artist-guide-reopened.hip'
    shutil.copyfile(source_hip,hip)
    source_library=workspace/'otls/post-array.hda'
    library=project/'otls/post-array.hda'
    library.parent.mkdir()
    shutil.copyfile(source_library,library)
    script.write_text(f"""import sys,json,hashlib,uuid
from pathlib import Path
sys.path.insert(0,{str(ROOT/'houdini/python3.11libs')!r})
import hou,dsh_bridge as bridge
library=Path({str(library)!r})
original_hash=hashlib.sha256(library.read_bytes()).hexdigest()
hou.hda.installFile(str(library))
hou.hipFile.load({str(hip)!r},suppress_save_prompt=True)
example=hou.node('/obj/artist_guide/post_array_example')
assert example and example.type().name()=='artistguide::post_array::1.0'
before={{'count':example.parm('count').eval(),'height':example.parm('height').eval(),'spacing':example.parm('spacing').eval(),
        'primitives':example.geometry().intrinsicValue('primitivecount'),'bbox':list(example.geometry().boundingBox().sizevec())}}
assert before['count']==6 and abs(before['height']-1.4)<1e-6 and before['primitives']==36,before
code="set_parms('/obj/artist_guide/post_array_example',{{'count':8,'height':1.6,'spacing':.65}},allow_foreign='User explicitly requested changing this isolated saved example after reopening')\\nverify_network('/obj/artist_guide',output='/obj/artist_guide/post_array_example')\\nscene_save_as("+repr({str(updated)!r})+",expected_current_path="+repr({str(hip)!r})+",reason='Authorized independent reopen and continuation of the authored example')"
outcome=bridge.run_code(code,owner_session='isolated-reopen-'+uuid.uuid4().hex,owner_call=uuid.uuid4().hex)
assert outcome['ok'],outcome
after={{'count':example.parm('count').eval(),'height':example.parm('height').eval(),'spacing':example.parm('spacing').eval(),
       'primitives':example.geometry().intrinsicValue('primitivecount'),'bbox':list(example.geometry().boundingBox().sizevec())}}
assert after['count']==8 and after['primitives']==48 and abs(after['bbox'][0]-4.73)<1e-5 and abs(after['bbox'][1]-1.6)<1e-5,after
source=hou.node('/obj/artist_guide/posts')
assert source.parm('count').eval()==4 and source.parm('height').eval()==1.2,'other instance changed'
assert hashlib.sha256(library.read_bytes()).hexdigest()==original_hash,'instance edit modified HDA definition'
Path({str(result)!r}).write_text(json.dumps({{'ok':True,'houdini':hou.applicationVersionString(),'before':before,'after':after,
    'definitionUnchanged':True,'otherInstanceUnchanged':True,'hip':{str(hip)!r},'updatedHip':{str(updated)!r},'hda':str(library),
    'execution':outcome['execution'],'verbs':outcome['verbs']}},ensure_ascii=True,indent=2),encoding='utf-8')
print('Saved HIP/HDA independently reopened and controls modified with other instance/definition preserved')
""",encoding='utf-8')
    hython=executable.with_name('hython.exe')
    process=subprocess.run([str(hython),str(script)],cwd=launch_directory(hython),
        env=isolated_environment(run/'reopen',executable=hython),capture_output=True,text=True,encoding='utf-8',errors='replace',
        timeout=80,creationflags=subprocess.CREATE_NO_WINDOW)
    (run/'reopen.log').write_text(process.stdout+'\n'+process.stderr,encoding='utf-8')
    assert process.returncode==0 and result.exists(),process.stdout+'\n'+process.stderr
    facts=json.loads(result.read_text(encoding='utf-8'))
    evidence_hip=workspace/'artist-guide-reopened.hip'
    shutil.copyfile(updated,evidence_hip)
    facts.update(evidenceSourceHip=str(source_hip),evidenceUpdatedHip=str(evidence_hip))
    base.atomic_json(result,facts)
    return facts


def main():
    reexec_unpacked_test_cli()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-cache',type=Path,required=True)
    parser.add_argument('--houdini',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'tools/out/artist-guide/evidence')
    parser.add_argument('--timeout',type=int,default=300)
    args=parser.parse_args()
    sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
    import dsh_managed_runtime as managed
    from dsh_web_auth import DshWebSession
    binary=args.runtime_cache.resolve(strict=True)/'node_modules/@deepseek-ai/dsh/lib/bin.js'
    preferred=json.loads((ROOT/'dsh-runtime-compatibility.json').read_text(encoding='utf-8'))['preferredVersion']
    assert json.loads((binary.parent.parent/'package.json').read_text(encoding='utf-8'))['version']==preferred
    node=shutil.which('node');assert node
    fixture=args.output.resolve()/('qt-interaction-'+uuid.uuid4().hex[:8]);fixture.mkdir(parents=True)
    print('Owned GUI interaction evidence:',fixture,flush=True)
    for executable in args.houdini:
        executable=executable.resolve(strict=True)
        run=fixture/executable.parent.parent.name;run.mkdir()
        version_probe=subprocess.run([str(executable.with_name('hython.exe')),'-c',"import hou;print('DSH_VERSION='+'.'.join(map(str,hou.applicationVersion()[:2])))"],
            cwd=launch_directory(executable),env=isolated_environment(run/'version',executable=executable),capture_output=True,text=True,
            encoding='utf-8',errors='replace',check=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
        version=re.search(r'DSH_VERSION=(21\.0|22\.0)',version_probe.stdout)[1]
        workspace=Path(tempfile.mkdtemp(prefix='dsh-artist-guide-gui-'))
        host_env=isolated_environment(run/'host')
        subprocess.run([node,str(ROOT/'tools/tests/prepare-shared-host-fixture.mjs'),str(binary),host_env['DSH_HOME'],str(ROOT)],
            cwd=ROOT,env=host_env,capture_output=True,check=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
        provider_port,actual_bridge,proxy_port,host_port=[free_port() for _ in range(4)]
        provider,model='qt-owned-fixture','qt-scripted'
        key='local-fixture-'+uuid.uuid4().hex
        profile=Path(host_env['DSH_HOME'])/'profiles/web/cordis.patch.yml'
        profile.write_text('- id: locale\n  config:\n    preference: zh\n- id: llm-pi-ai\n  config:\n    providers:\n      '+provider+':\n'
            '        api: openai-completions\n        baseURL: http://127.0.0.1:'+str(provider_port)+'/v1\n'
            '        apiKeyEnv: DSH_QT_FIXTURE_KEY\n        models:\n          - id: '+model+'\n            name: Qt loopback fixture\n'
            '            input: [text, image]\n            contextWindow: 500000\n            maxTokens: 4096\n',encoding='utf-8')
        hip=str(workspace/'artist-guide.hip')
        config={'base':'http://127.0.0.1:'+str(host_port),'workspace':str(workspace),'assistantText':'scripted integration fixture',
            'provider':provider,'model':model,'providerPort':provider_port,'fixtureKey':key,
            'actualBridge':'http://127.0.0.1:'+str(actual_bridge),'actualBridgePort':actual_bridge,'bridgeProxyPort':proxy_port,
            'providerEvidence':str(run/'provider.json'),'bridgeReady':str(run/'bridge-ready.json'),
            'authenticationFile':str(run/'authenticated-url.json'),
            'toolCatalogUrl':(ROOT/'lib/tool-catalog.js').as_uri(),'composition':str(run/'composition.json'),
            'command':str(run/'command.json'),'response':str(run/'response.json'),'history':str(run/'session-history.json'),
            'output':str(run/'result.json'),'timeout':args.timeout,'fixtureHipChanges':True,'buildCode':build_code(workspace),
            'imageCode':f"__result__=render_view('/obj/artist_guide/post_array_example',width=480,height=320,picture='artist-guide-check.png')\nscene_save(expected_path={hip!r})",
            'unknownCode':f"__gui_unknown_transport__=True\nset_parms('/obj/artist_guide/post_array_example',{{'height':1.4}})\nscene_save(expected_path={hip!r})\n__result__={{'height':hou.node('/obj/artist_guide/post_array_example').parm('height').eval()}}",
            'inspectCode':"n=hou.node('/obj/artist_guide/post_array_example')\n__result__={'height':n.parm('height').eval(),'count':n.parm('count').eval(),'primitives':n.geometry().intrinsicValue('primitivecount')}"}
        acceptance=run/'page-acceptance.js';acceptance.write_text(PAGE,encoding='utf-8');config['acceptanceScript']=str(acceptance)
        config_path=run/'config.json';base.atomic_json(config_path,config)
        host_env.update(DSH_SOURCE_GUI_CONFIG=str(config_path),DSH_SOURCE_RUNTIME_BIN=str(binary),DSH_QT_FIXTURE_KEY=key,
            DSH_HOUDINI_BRIDGE_URL='http://127.0.0.1:'+str(proxy_port))
        gui_env=isolated_environment(run/'gui',executable=executable,gui=True)
        gui_env['DSH_SOURCE_GUI_CONFIG']=str(config_path)
        prefs=Path(gui_env['HOUDINI_USER_PREF_DIR'].replace('__HVER__',version))
        hook=prefs/('python3.11libs' if version=='21.0' else 'python3.13libs')/'uiready.py';hook.parent.mkdir(parents=True,exist_ok=True)
        hook.write_text("import importlib.util,traceback\ns=importlib.util.spec_from_file_location('interaction_probe',"+repr(str(Path(__file__).resolve()))+")\nm=importlib.util.module_from_spec(s)\ns.loader.exec_module(m)\ntry:\n m.start_gui_probe()\nexcept Exception:\n m.base.atomic_json("+repr(config['output'])+",{'ok':False,'error':traceback.format_exc()})\n",encoding='utf-8')
        inspector=run/'inspect.mjs';inspector.write_text(base.HOST_FIXTURE,encoding='utf-8')
        overlay=run/'inspect.patch.yml';overlay.write_text('- insert:\n    - id: source-gui-inspector\n      name: '+inspector.as_uri()+'\n'
            '    - id: source-gui-http-provider\n      name: '+Path(__file__).with_name('dsh-source-webview-provider.mjs').as_uri()+'\n',encoding='utf-8')
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
        gui_job=base.GuiProcessJob();host=None;gui=None
        try:
            with (run/'houdini.log').open('wb') as log:
                gui=subprocess.Popen([str(executable),'-foreground','-geometry=1440x1000+12000+12000'],cwd=launch_directory(executable),
                    env=gui_env,stdout=log,stderr=subprocess.STDOUT,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
                gui_job.assign(gui)
            deadline=time.monotonic()+80
            while not Path(config['bridgeReady']).exists():
                assert gui.poll() is None and time.monotonic()<deadline,'GUI Bridge bootstrap failed: '+str(run)
                if Path(config['output']).exists():raise AssertionError(Path(config['output']).read_text())
                time.sleep(.2)
            identity=json.loads(Path(config['bridgeReady']).read_text());host_env['DSH_HOUDINI_EXECUTOR_ID']=identity['executor']
            with (run/'host.log').open('wb') as log:
                host=managed.spawn_frontend([node,str(binary),'web','--patch',str(overlay),'--port',str(host_port),'--no-open'],node=node,
                    cwd=run,env=host_env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            auth=DshWebSession(config['base'],str(run/'host.log'),str(run/'runtime.json'))
            deadline=time.monotonic()+60
            while auth.launch_url() is None:
                assert host.poll() is None and time.monotonic()<deadline,'Host failed: '+str(run)
                time.sleep(.2)
            auth.authorize(timeout=10);base.atomic_json(config['authenticationFile'],{'authenticatedUrl':auth.launch_url()})
            deadline=time.monotonic()+args.timeout+40;last=None
            while not Path(config['output']).exists():
                assert gui.poll() is None and host.poll() is None and time.monotonic()<deadline,'GUI loop failed/timed out: '+str(run)
                progress=Path(config['output']).with_suffix('.progress.json')
                if progress.exists() and progress.read_text()!=last:last=progress.read_text();print(version,last,flush=True)
                time.sleep(.25)
            result=json.loads(Path(config['output']).read_text(encoding='utf-8'))
            print(version,json.dumps({'ok':result['ok'],'phase':result['phase'],'detail':result['detail'],
                'loads':result['loads'],'renderer':result['renderer'],'console':result['console']},ensure_ascii=True),flush=True)
            assert result['ok'],result
            assert result['fixtureHipChanges'] and result['offTheRecord'] and not result['renderer'],result
            assert gui.wait(timeout=30)==0
            provider_facts=json.loads(Path(config['providerEvidence']).read_text(encoding='utf-8'))
            assert len(provider_facts['lost'])==1 and provider_facts['lost'][0]['applied']
            assert any(row.get('stage')=='STOP' and row.get('closedBeforeFinish') for row in provider_facts['requests'])
            assert all(row.get('authorizationMatched',True) for row in provider_facts['requests'])
            assert any(image.get('transport')=='base64' and image.get('width')==480 and image.get('height')==320
                       for row in provider_facts['requests'] for image in row.get('imageEvidence',[])), 'actual provider did not receive the rendered image pixels'
        finally:
            tree=gui_job.close()
            if Path(config['output']).exists():
                result=json.loads(Path(config['output']).read_text());result['guiProcessTree']=tree;base.atomic_json(config['output'],result)
            if gui is not None:gui.wait(timeout=20)
            if host is not None:managed.stop_owned(host);host.wait(timeout=20)
        reopened=reopen_example(executable,run,workspace)
        copied_workspace=run/'workspace'
        shutil.copytree(workspace,copied_workspace)
        summary={'houdini':version,'sourceWorkspace':str(workspace),'evidenceWorkspace':str(copied_workspace),
                 'guiResult':str(run/'result.json'),'reopenResult':str(run/'reopen-result.json'),
                 'imageProviderEvidence':str(run/'provider.json'),'semanticVision':'unverified'}
        base.atomic_json(run/'summary.json',summary)
        print(version,'Independent HIP/HDA reopen and continued public controls:',json.dumps(reopened['after']),flush=True)
    print('Real Qt send/stop/frontend-reconnect and actual Bridge/HDA execution passed; scripted provider, semantic vision unverified',flush=True)


if __name__=='__main__':main()
