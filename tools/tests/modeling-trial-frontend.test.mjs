import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import {generatedNodeDeliveryFactory} from '../gen-trace-client.mjs';
import {frontendArtifacts} from './modeling-trial-ui-artifacts.mjs';
import {attachImages} from '../../lib/image-output.js';

const events=[{type:'deliverables/presented',data:{files:[{path:'C:/task/model.hip'}]}}];
const nodes=[{path:'/obj/model',role:'node',label:'Model'}];
const options={cwd:'C:/task',sessionId:'trial'};
const files=paths=>frontendArtifacts([{type:'deliverables/presented',data:{files:paths.map(path=>({path}))}}],[],options).files;
const canonical={ok:true,result:{kind:'houdini/node-delivery-v1',nodes:nodes.map(node=>({...node,id:'c'.repeat(32),type:'geo'}))},
  execution:{executor_id:'a'.repeat(32),runtime_id:'b'.repeat(32),hip_path:'C:/task/model.hip',owner_session:'trial'}};
canonical.verbs=[{verb:'present_nodes',ok:true,result:canonical.result}];
canonical.result={entries:canonical.result};
const artifacts=frontendArtifacts(events,[{tool:'houdini_exec',canonical}],options);
assert.deepEqual(artifacts.files,[{path:'C:/task/model.hip',resolvedPath:'C:/task/model.hip',name:'model.hip',resourceAddress:'dsh-resource://file/session/trial/model.hip'}]);
assert.equal(files(['relative/model.hip'])[0].resolvedPath,'C:/task/relative/model.hip');
assert.deepEqual(artifacts.nodes,nodes);
assert.deepEqual(artifacts.uiCaptures,[]);
assert.deepEqual(frontendArtifacts([],[{tool:'houdini_exec',failed:true,canonical}]).nodes,[]);
const nodeFactory=vm.runInNewContext('('+generatedNodeDeliveryFactory()+')');
for(const value of [canonical,{...canonical,outcome:{operations:{failed:1}}},{...canonical,verbs:[{verb:'set_parms',ok:false}]}]){
  const projected=nodeFactory({},()=>value).definition.start(null,{event:{seq:2,type:'tool/ptc-dispatch',data:{name:'houdini_exec',subCallId:'node-call'}}});
  const collected=frontendArtifacts([],[{tool:'houdini_exec',canonical:value}],options);
  assert.equal(collected.nodes.length,projected.nodes.length,'artifact expectations and actual node-card projection must agree on failed operations');
}
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-trial-artifact-'));
try{
  const capturePath=path.join(temporary,'capture.png');
  const bytes=Buffer.from('controlled image transport bytes');fs.writeFileSync(capturePath,bytes);
  const attachment={attachmentId:'native-image',mediaType:'image/png',bytes:bytes.length,width:1,height:1,name:'capture.png'};
  const ctx={get:name=>name==='attachments'?{imageLimits:{maxImagesPerMessage:2,maxImageBytes:100,maxMessageImageBytes:100,mediaTypes:['image/png']},saveImage:async()=>attachment}:
    {resolveModelInfo:async()=>({inputModalities:['image']})}};
  const attached=await attachImages({ok:true,images:[capturePath],result:{path:capturePath,fresh:true,file_status:'passed'}},
    {route:{provider:'fixture',model:'fixture'},signal:new AbortController().signal},{fetchMedia:async()=>bytes},ctx);
  assert.equal(attached.imageAttachments[0].from,capturePath);
  assert.equal(attached.imageAttachments[0].path,undefined);
  assert.deepEqual(frontendArtifacts([],[{tool:'houdini_ui_screenshot',canonical:attached}],options).uiCaptures[0].attachment,attachment,
    'consume the real attachImages from/attachment shape');
  const alternateSpelling={...attached,result:{...attached.result,path:capturePath.replaceAll('\\','/')}};
  assert.deepEqual(frontendArtifacts([],[{tool:'houdini_ui_screenshot',canonical:alternateSpelling}],options).uiCaptures[0].attachment,attachment,
    'native Windows and slash-normalized receipt paths identify the same captured attachment');
}finally{
  assert.equal(path.dirname(path.resolve(temporary)),path.resolve(os.tmpdir()));
  assert(path.basename(temporary).startsWith('dsh-trial-artifact-'));
  fs.rmSync(temporary,{recursive:true,force:true});
}

const source=fs.readFileSync(new URL('./modeling-trial-frontend-probe.py',import.meta.url),'utf8');
const script=source.match(/SCRIPT=r"""([\s\S]*?)"""/)[1];
const dimensions=()=>({width:100,height:100});
function fixture(expected,{missingFiles=false,otherImage=false,shownFiles=expected.files,stalePreview=false,collapsedFiles=false}={}){
  let preview=null,opened=false,expanded=!collapsedFiles;
  const fileRows=missingFiles?[]:shownFiles.map(file=>({textContent:file.name,
    querySelector(selector){
      if(selector.includes('nyYjTG_fileName'))return {textContent:file.name};
      if(selector.includes('cardPreview'))return {getAttribute:name=>name==='title'?file.resolvedPath:null,click(){
        preview={getAttribute:()=>stalePreview?'dsh-resource://file/session/trial/other.png':file.resourceAddress,
          querySelector:()=>file.name.endsWith('.png')?{complete:true,naturalWidth:32,naturalHeight:16}:null};
      }};
      return null;
    }}));
  const nodeRows=expected.nodes.map(node=>({dataset:{houdiniNodeDelivery:node.role},
    querySelectorAll(){return [{textContent:node.path}]},
    querySelector(selector){
      if(selector==='.dsh-houdini-node-title')return {textContent:node.label};
      if(selector==='.dsh-houdini-node-open')return {click(){opened=true}};
      if(selector.includes('data-phase="opened"'))return opened?{}:null;
      return null;
    }}));
  const image={complete:true,naturalWidth:64,naturalHeight:64,getBoundingClientRect:dimensions,alt:'unrelated avatar'};
  const document={readyState:'complete',body:{textContent:'Current task',innerText:'Current task'},
    querySelectorAll(selector){
      if(selector==='[data-presented-file]')return expanded?fileRows:fileRows.slice(0,1);
      if(selector==='button[class*=nyYjTG_toggle][aria-expanded="false"]')return expanded?[]:[{click(){expanded=true}}];
      if(selector==='[data-textpreview-state="text"]')return preview?[preview]:[];
      if(selector==='.dsh-houdini-node-card')return nodeRows;
      if(selector==='img')return otherImage?[image]:[];
      return [];
    },
    querySelector(selector){
      return null;
    }};
  let now=0;
  const context={document,window:{__dshHoudiniSelection:()=>({sessionId:'trial',agentPreset:'houdini',cwd:'C:/task'})},
    Date:{now:()=>now+=1000},URL,location:{href:'http://localhost/'},performance:{getEntriesByType:()=>[]},
    setTimeout(callback){callback()}};
  return {context,run:()=>vm.runInNewContext(script.replace('__CONFIG__',JSON.stringify({sessionId:'trial',artifacts:expected})),context)};
}
const hipOnly=fixture(artifacts);
await hipOnly.run();
assert.equal(hipOnly.context.window.__dshPaidFrontendProbe.ok,true,'ordinary HIP delivery must not require source text or UI captures');
assert.equal(hipOnly.context.window.__dshPaidFrontendProbe.facts.textPreview,null);
assert.equal(hipOnly.context.window.__dshPaidFrontendProbe.facts.uiImageConsumerVerified,null);
const missing=fixture(artifacts,{missingFiles:true});
await missing.run();
assert.equal(missing.context.window.__dshPaidFrontendProbe.ok,false,'a native declared file missing from the frontend must fail');
const uiExpected={...artifacts,uiCaptures:[{path:'C:/task/ui.png',name:'ui.png'}]};
const unrelated=fixture(uiExpected,{otherImage:true});
await unrelated.run();
assert.equal(unrelated.context.window.__dshPaidFrontendProbe.ok,false,'an unrelated decoded image must not prove a canonical UI capture arrived');
const actualFiles={...artifacts,files:files(['C:/task/model.hip','C:/task/tool.py','C:/task/final.png'])};
const presented=fixture(actualFiles);
await presented.run();
assert.equal(presented.context.window.__dshPaidFrontendProbe.ok,true);
assert.equal(presented.context.window.__dshPaidFrontendProbe.facts.textPreview,true);
assert.equal(presented.context.window.__dshPaidFrontendProbe.facts.imagePreview.name,'final.png');
const uiFile=fixture({...uiExpected,files:files(['C:/task/model.hip','C:/task/tool.py','C:/task/final.png','C:/task/ui.png'])});
await uiFile.run();
assert.equal(uiFile.context.window.__dshPaidFrontendProbe.ok,true);
assert.equal(uiFile.context.window.__dshPaidFrontendProbe.facts.imagePreview.name,'ui.png','when a capture was presented, inspect that declared image rather than an unrelated earlier render');
const sameNames={...artifacts,files:files(['C:/task/one/model.hip','C:/task/two/model.hip'])};
const oneCard=fixture(sameNames,{shownFiles:[sameNames.files[0]]});
await oneCard.run();
assert.equal(oneCard.context.window.__dshPaidFrontendProbe.ok,false,'one filename card cannot satisfy two declared absolute paths');
const twoCards=fixture(sameNames);await twoCards.run();assert.equal(twoCards.context.window.__dshPaidFrontendProbe.ok,true);
const collapsed=fixture(sameNames,{collapsedFiles:true});await collapsed.run();
assert.equal(collapsed.context.window.__dshPaidFrontendProbe.ok,true,'expand the actual collapsed delivery list before checking declared cards');
const wrongUiImage=fixture({...uiExpected,files:files(['C:/task/other/ui.png'])});
await wrongUiImage.run();
assert.equal(wrongUiImage.context.window.__dshPaidFrontendProbe.ok,false,'same-basename image from another directory cannot certify the UI capture');
const stale=fixture({...artifacts,files:files(['C:/task/final.png'])},{stalePreview:true});
await stale.run();
assert.equal(stale.context.window.__dshPaidFrontendProbe.ok,false,'a decoded old preview must not certify the newly requested resource');
const empty=fixture({schemaVersion:1,files:[],nodes:[],uiCaptures:[]});
await empty.run();
assert.equal(empty.context.window.__dshPaidFrontendProbe.facts.deliveryVerification,'not_applicable');
console.log('Model-trial frontend expectations: native deliveries, optional surfaces and unrelated-image rejection passed; no GUI claim');
