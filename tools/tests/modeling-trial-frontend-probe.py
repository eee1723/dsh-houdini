"""Observe an actual isolated session in its owned Houdini QtWebEngine.

start() runs through Bridge once. Subsequent callbacks touch only cached Qt and
page objects, never HOM, sockets, processes or a nested Qt event loop.
"""
from pathlib import Path
import json,time,urllib.parse

SCRIPT=r"""(async()=>{
const config=__CONFIG__;
const expected=config.artifacts;
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
 const normalizedPath=path=>path.replace(/\\+/g,'/');
 const fileRows=()=>[...document.querySelectorAll('[data-presented-file]')];
 const fileName=e=>e.querySelector('[class*=nyYjTG_fileName]')?.textContent?.trim();
 const filePath=e=>e.querySelector('button[class*=cardPreview]')?.getAttribute('title');
 const matchesFile=(row,file)=>typeof filePath(row)==='string'&&normalizedPath(filePath(row))===normalizedPath(file.resolvedPath);
 const previewFor=file=>[...document.querySelectorAll('[data-textpreview-state="text"]')].find(e=>e.getAttribute('data-textpreview-url')===file.resourceAddress);
 const nodePath=e=>[...e.querySelectorAll('code')].map(x=>x.textContent).filter(x=>x.startsWith('/')).at(-1);
 if(expected.files.length||expected.nodes.length)await wait(()=>{
  for(const toggle of document.querySelectorAll('button[class*=nyYjTG_toggle][aria-expanded="false"]'))toggle.click();
  return expected.files.every(file=>fileRows().some(row=>matchesFile(row,file)))&&
  expected.nodes.every(node=>[...document.querySelectorAll('.dsh-houdini-node-card')].some(row=>nodePath(row)===node.path));},
  'actual declared delivery surfaces');
 facts.nodeCards=[...document.querySelectorAll('.dsh-houdini-node-card')].map(e=>({role:e.dataset.houdiniNodeDelivery,label:e.querySelector('.dsh-houdini-node-title')?.textContent,
   codes:[...e.querySelectorAll('code')].map(x=>x.textContent)}));
 facts.fileCards=fileRows().map(e=>({name:fileName(e),path:filePath(e),text:e.textContent}));
 const uiImagePaths=expected.uiCaptures.map(item=>normalizedPath(item.path));
 const imageTools=[...document.querySelectorAll('[data-tool="houdini_ui_screenshot"]')];
 if(uiImagePaths.length)for(const tool of imageTools){const expand=tool.querySelector('button[aria-expanded="false"]');if(expand)expand.click();}
 const decoded=()=>[...document.querySelectorAll('img')].filter(i=>visible(i)&&i.complete&&i.naturalWidth>0&&i.naturalHeight>0);
 await new Promise(r=>setTimeout(r,1500));
 const imageTool=imageTools.find(e=>uiImagePaths.some(path=>normalizedPath(e.textContent).includes(path)));
 facts.toolImages=imageTool?[...imageTool.querySelectorAll('img')].filter(i=>visible(i)&&i.complete&&i.naturalWidth>0).map(i=>({alt:i.alt,width:i.naturalWidth,height:i.naturalHeight})):[];
 facts.matchedUiImageReads=[...document.querySelectorAll('[data-tool="read_image"]')].filter(e=>uiImagePaths.some(path=>normalizedPath(e.textContent).includes(path))).flatMap(e=>[...e.querySelectorAll('img')].filter(i=>visible(i)&&i.complete&&i.naturalWidth>0).map(i=>({alt:i.alt,width:i.naturalWidth,height:i.naturalHeight})));
 facts.otherDecodedImages=decoded().filter(i=>!imageTool?.contains(i)).map(i=>({alt:i.alt,width:i.naturalWidth,height:i.naturalHeight}));
 const textFile=expected.files.find(file=>/\.(py|json|txt)$/i.test(file.name));
 const textRow=textFile&&fileRows().find(e=>matchesFile(e,textFile));
 if(textFile){const button=textRow?.querySelector('button[class*=cardPreview]');if(!button)throw Error('Missing declared text preview: '+textFile.name);button.click();
  await wait(()=>previewFor(textFile),'actual delivered source text preview');facts.textPreview=true;
 }else facts.textPreview=null;
 const imageFile=expected.files.find(file=>uiImagePaths.includes(normalizedPath(file.resolvedPath))&&/\.(png|jpe?g|gif|webp)$/i.test(file.name))??
  expected.files.find(file=>/\.(png|jpe?g|gif|webp)$/i.test(file.name));
 const imageRow=imageFile&&fileRows().find(e=>matchesFile(e,imageFile));
 if(imageFile){const button=imageRow?.querySelector('button[class*=cardPreview]');if(!button)throw Error('Missing declared image preview: '+imageFile.name);button.click();
  const image=await wait(()=>{const i=previewFor(imageFile)?.querySelector('[data-image-preview] img');return i&&i.complete&&i.naturalWidth>0&&i;},'actual delivered image preview');
  facts.imagePreview={name:imageFile.name,path:imageFile.resolvedPath,width:image.naturalWidth,height:image.naturalHeight,uiArtifactMatched:uiImagePaths.includes(normalizedPath(imageFile.resolvedPath))};
 }else facts.imagePreview=null;
 const node=expected.nodes.length?[...document.querySelectorAll('.dsh-houdini-node-card')].find(row=>expected.nodes.some(item=>nodePath(row)===item.path)):null;
 if(node){const codes=[...node.querySelectorAll('code')].map(e=>e.textContent);facts.clickedNode={role:node.dataset.houdiniNodeDelivery,label:node.querySelector('.dsh-houdini-node-title')?.textContent,
  path:codes.filter(x=>x.startsWith('/')).at(-1)};node.querySelector('.dsh-houdini-node-open').click();
  await wait(()=>node.querySelector('.dsh-houdini-node-action[data-phase="opened"]'),'actual node-card navigation');facts.nodeOpened=true;
 }else facts.nodeOpened=null;
 facts.modelButton=[...document.querySelectorAll('button')].find(b=>/^选择模型，当前 /.test(b.getAttribute('aria-label')??''))?.getAttribute('aria-label')??null;
 facts.uiImageConsumerVerified=expected.uiCaptures.length?
  facts.toolImages.length>0||facts.matchedUiImageReads.length>0||facts.imagePreview?.uiArtifactMatched===true:null;
 facts.imageConsumerVerified=imageFile?facts.imagePreview!==null:null;
 facts.fileConsumerVerified=expected.files.length?expected.files.every(file=>facts.fileCards.some(row=>typeof row.path==='string'&&normalizedPath(row.path)===normalizedPath(file.resolvedPath)))&&(!textFile||facts.textPreview):null;
 facts.navigationAndCardsVerified=!facts.tokenInUrl&&facts.selection.agentPreset==='houdini'&&(!expected.nodes.length||facts.nodeOpened);
 facts.expectedSurfaces={files:expected.files.map(file=>file.path),nodes:expected.nodes.map(node=>node.path),uiCaptures:expected.uiCaptures.map(image=>image.path)};
 facts.checkedPreviews={text:facts.textPreview?textFile.path:null,image:facts.imagePreview?imageFile.path:null,node:facts.clickedNode?.path??null};
 facts.deliveryVerification=expected.files.length||expected.nodes.length||expected.uiCaptures.length?'observed_declared_surfaces':'not_applicable';
 state.ok=facts.navigationAndCardsVerified&&[facts.uiImageConsumerVerified,facts.imageConsumerVerified,facts.fileConsumerVerified].every(value=>value!==false);
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
    artifact_file=Path(config_path).parent/'frontend-artifacts.json'
    artifacts=json.loads(artifact_file.read_text(encoding='utf-8'))
    output=Path(config['output'])
    if output.exists():raise RuntimeError('Frontend probe output already exists')
    webview.show_webview(session_id=config['sessionId'],authenticated_url=config['authenticatedUrl'],frontend_url=config['base'])
    page=webview._view.page()
    widget=webview._view
    timer=QtCore.QTimer(widget)
    state={'begun':False,'busy':False,'started':time.monotonic()}
    script=SCRIPT.replace('__CONFIG__',json.dumps({'sessionId':config['sessionId'],'artifacts':artifacts},ensure_ascii=True))
    def complete(report):
        if state.get('done'):return
        state['done']=True;timer.stop()
        report['scope']='actual owned Houdini QtWebEngine and selected real isolated DSH task; declared cards and representative text/image/node interactions as listed; physical mouse/keyboard and semantic quality not tested'
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
