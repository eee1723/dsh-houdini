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

console.log('Native delivery artifact expectations agree with the current node-card projection; no GUI claim');
