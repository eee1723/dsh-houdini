"""Observe an actual isolated session in its owned Houdini QtWebEngine.

start() runs through Bridge once. Subsequent callbacks touch only cached Qt and
page objects, never HOM, sockets, processes or a nested Qt event loop.
"""
from pathlib import Path
import json,time,urllib.parse

SCRIPT=r"""(async()=>{
const config=__CONFIG__;
const facts={};
const state=window.__dshPaidFrontendProbe={done:false,facts};
const wait=async(check,label,ms=20000)=>{
 state.phase=label;
 const end=Date.now()+ms;
 while(Date.now()<end){const found=check();if(found)return found;await new Promise(r=>setTimeout(r,120));}
 throw Error('Timed out: '+label);
};
const visible=e=>e&&e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0;
try{
 await wait(()=>document.readyState==='complete','document ready',45000);
 for(let i=0;i<80;i++){
  if(document.body?.textContent?.includes('内测声明')){
   const check=[...document.querySelectorAll('[role=checkbox],input[type=checkbox]')].find(e=>visible(e)&&e.getAttribute('aria-checked')!=='true'&&!e.checked);if(check)check.click();
  }
  const next=[...document.querySelectorAll('button')].find(b=>visible(b)&&!b.disabled&&['继续','稍后配置','以后设置','Continue','Configure later','Set up later'].includes(b.textContent.trim()));
  if(next)next.click();
  if(window.__dshHoudiniSelection?.()?.sessionId===config.sessionId)break;
  await new Promise(r=>setTimeout(r,300));
 }
 const selection=await wait(()=>window.__dshHoudiniSelection?.()?.sessionId===config.sessionId&&window.__dshHoudiniSelection(),'selected actual trial session');
 facts.selection={sessionId:selection.sessionId,cwd:selection.cwd,agentPreset:selection.agentPreset};
 facts.tokenInUrl=new URL(location.href).searchParams.has('token');
 const conversation=[...document.querySelectorAll('[role=tab]')].find(b=>['对话','Chat','Conversation'].includes(b.textContent.trim()));
 if(conversation)conversation.click();
 await wait(()=>document.querySelector('.dsh-houdini-node-card')||document.querySelector('button[class*=cardPreview]'),'actual delivery surface');
 facts.nodeCards=[...document.querySelectorAll('.dsh-houdini-node-card')].map(e=>({role:e.dataset.houdiniNodeDelivery,label:e.querySelector('.dsh-houdini-node-title')?.textContent,
   codes:[...e.querySelectorAll('code')].map(x=>x.textContent)}));
 facts.fileCards=[...document.querySelectorAll('[class*=nyYjTG_file]')].filter(e=>e.querySelector('button[class*=cardPreview]')).map(e=>e.textContent);
 const imageTool=document.querySelector('[data-tool="houdini_ui_screenshot"]');
 if(imageTool){const expand=imageTool.querySelector('button[aria-expanded="false"]');if(expand)expand.click();}
 const decoded=()=>[...document.querySelectorAll('img')].filter(i=>visible(i)&&i.complete&&i.naturalWidth>0&&i.naturalHeight>0);
 await new Promise(r=>setTimeout(r,1500));
 facts.toolImages=imageTool?[...imageTool.querySelectorAll('img')].filter(i=>visible(i)&&i.complete&&i.naturalWidth>0).map(i=>({alt:i.alt,width:i.naturalWidth,height:i.naturalHeight})):[];
 facts.matchedUiImageReads=[...document.querySelectorAll('[data-tool="read_image"]')].filter(e=>config.uiImageNames.some(name=>e.textContent.includes(name))).flatMap(e=>[...e.querySelectorAll('img')].filter(i=>visible(i)&&i.complete&&i.naturalWidth>0).map(i=>({alt:i.alt,width:i.naturalWidth,height:i.naturalHeight})));
 facts.otherDecodedImages=decoded().filter(i=>!imageTool?.contains(i)).map(i=>({alt:i.alt,width:i.naturalWidth,height:i.naturalHeight}));
 const textRow=[...document.querySelectorAll('[class*=nyYjTG_file]')].find(e=>/\.(py|json|txt)$/i.test(e.querySelector('[class*=nyYjTG_fileName]')?.textContent?.trim()??'')&&e.querySelector('button[class*=cardPreview]'));
 if(textRow){textRow.querySelector('button[class*=cardPreview]').click();
  await wait(()=>document.querySelector('[data-textpreview-state="text"]'),'actual delivered source text preview');facts.textPreview=true;
 }else facts.textPreview=false;
 const imageRow=[...document.querySelectorAll('[class*=nyYjTG_file]')].find(e=>config.uiImageNames.some(name=>e.textContent.includes(name))&&e.querySelector('button[class*=cardPreview]'));
 if(imageRow){imageRow.querySelector('button[class*=cardPreview]').click();
  const image=await wait(()=>{const i=document.querySelector('[data-image-preview] img');return i&&i.complete&&i.naturalWidth>0&&i;},'actual delivered image preview');
  facts.imagePreview={width:image.naturalWidth,height:image.naturalHeight,uiArtifactMatched:true};
 }else facts.imagePreview=null;
 const node=document.querySelector('.dsh-houdini-node-card[data-houdini-node-delivery="control"]')??document.querySelector('.dsh-houdini-node-card');
 if(node){const codes=[...node.querySelectorAll('code')].map(e=>e.textContent);facts.clickedNode={role:node.dataset.houdiniNodeDelivery,label:node.querySelector('.dsh-houdini-node-title')?.textContent,
  path:codes.filter(x=>x.startsWith('/')).at(-1)};node.querySelector('.dsh-houdini-node-open').click();
  await wait(()=>node.querySelector('.dsh-houdini-node-action[data-phase="opened"]'),'actual node-card navigation');facts.nodeOpened=true;
 }else facts.nodeOpened=false;
 facts.modelButton=[...document.querySelectorAll('button')].find(b=>/^选择模型，当前 /.test(b.getAttribute('aria-label')??''))?.getAttribute('aria-label')??null;
 facts.imageConsumerVerified=facts.toolImages.length>0||facts.matchedUiImageReads.length>0||facts.imagePreview!==null;
 facts.fileConsumerVerified=facts.textPreview;
 facts.navigationAndCardsVerified=!facts.tokenInUrl&&facts.selection.agentPreset==='houdini'&&facts.nodeOpened&&facts.fileCards.length>0;
 state.ok=facts.navigationAndCardsVerified&&facts.imageConsumerVerified&&facts.fileConsumerVerified;
}catch(error){state.ok=false;state.error=error.message;facts.bootstrap={selectionType:typeof window.__dshHoudiniSelection,
 selection:window.__dshHoudiniSelection?.()??null,text:document.body?.innerText?.slice(0,5000),
 sessionHint:new URL(location.href).searchParams.get('dsh-houdini-session'),workspaceHint:new URL(location.href).searchParams.get('dsh-houdini-workspace'),navigationNotice:document.querySelector('#dsh-houdini-navigation')?.textContent??null,
 buttons:[...document.querySelectorAll('button')].map(b=>({text:b.textContent,disabled:b.disabled,label:b.getAttribute('aria-label')})).slice(-25),
 checkboxes:[...document.querySelectorAll('[role=checkbox],input[type=checkbox]')].map(e=>({role:e.getAttribute('role'),checked:e.getAttribute('aria-checked'),text:e.closest('label')?.textContent})),
 scripts:performance.getEntriesByType('resource').filter(r=>r.name.includes('/plugins/')).map(r=>new URL(r.name).pathname).slice(-12)};}
state.done=true;
})();"""

def start(config_path):
    from hutil.Qt import QtCore
    import dsh_webview as webview
    config=json.loads(Path(config_path).read_text(encoding='utf-8'))
    # UI observations carry their facts in the native session, independently
    # of exec result spooling. Consume the verifier's canonical manifest.
    artifact_file=Path(config_path).parent/'ui-capture-artifacts.json'
    artifacts=json.loads(artifact_file.read_text(encoding='utf-8')) if artifact_file.exists() else []
    config['uiImageNames']=[item['name'] for item in artifacts]
    output=Path(config['output'])
    if output.exists():raise RuntimeError('Frontend probe output already exists')
    webview.show_webview(session_id=config['sessionId'],authenticated_url=config['authenticatedUrl'],frontend_url=config['base'])
    page=webview._view.page()
    widget=webview._view
    timer=QtCore.QTimer(widget)
    state={'begun':False,'busy':False,'started':time.monotonic()}
    script=SCRIPT.replace('__CONFIG__',json.dumps({'sessionId':config['sessionId'],'uiImageNames':config.get('uiImageNames',[])},ensure_ascii=True))
    def complete(report):
        if state.get('done'):return
        state['done']=True;timer.stop()
        report['scope']='actual owned Houdini QtWebEngine, selected real isolated DSH task; node UI action uses real Host/Bridge; physical mouse/keyboard not tested'
        report['modelRunKind']=config.get('modelRunKind','unspecified')
        widget.grab().save(str(output.with_suffix('.png')))
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        QtCore.QTimer.singleShot(0,webview._dispose_webview)
    def received(encoded):
        state['busy']=False
        if not encoded:return
        result=json.loads(urllib.parse.unquote(encoded))
        state['last']=result
        if not state['begun'] and result.get('ready')=='complete' and result.get('origin')==config['base'] and result.get('hasBody'):
            state['begun']=True;page.runJavaScript(script,0);return
        if state['begun'] and result.get('ready') and not result.get('done'):
            state['begun']=False
        if result.get('done'):complete(result)
    def tick():
        if time.monotonic()-state['started']>110:
            complete({'ok':False,'error':'Native frontend probe time limit','lastObservation':state.get('last')});return
        if state['busy']:return
        state['busy']=True
        page.runJavaScript('encodeURIComponent(JSON.stringify(window.__dshPaidFrontendProbe??{ready:document.readyState,origin:location.origin,hasBody:!!document.body?.textContent,selectionReady:typeof window.__dshHoudiniSelection==="function",text:document.body?.innerText?.slice(0,1500)}))',0,received)
    timer.timeout.connect(tick);timer.start(250)
    return {'started':True,'output':str(output),'sessionId':config['sessionId']}
