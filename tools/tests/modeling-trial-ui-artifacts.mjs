// Resolve frontend expectations from the real native session. A modeling task
// does not owe a source-text file or UI capture unless it actually produced one.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {loadSessionEvents} from '../trace-session-lib.mjs';
import {nodeDeliveryRows} from '../../lib/node-delivery-record.js';
import {normalizeTraceSteps} from '../normalized-trace-steps.mjs';
import {pathToFileURL} from 'node:url';
import {fileAddressFor,resolveWorkspacePath} from '@deepseek-ai/dsh-util-workspace-path';

export function frontendArtifacts(events,steps,{cwd,sessionId}={}){
  const uiCaptures=[],files=new Map(),nodes=new Map();
  for(const event of events){
    if(event.type!=='deliverables/presented')continue;
    for(const file of event.data?.files??[]){
      if(typeof file.path!=='string')continue;
      const resolvedPath=resolveWorkspacePath(cwd,file.path);
      files.set(resolvedPath,{path:file.path,resolvedPath,name:path.basename(file.path.replaceAll('\\','/')),
        ...(sessionId?{resourceAddress:fileAddressFor(sessionId,cwd,file.path)}:{})});
    }
  }
  for(const step of steps){
    // Match the successful-batch boundary used by client/node-delivery.js and
    // the Host's recordedNodeDelivery; Python success cannot hide failed verbs.
    if(step.failed||step.canonical?.ok!==true||Number(step.canonical.outcome?.operations?.failed)>0||
      Array.isArray(step.canonical.verbs)&&step.canonical.verbs.some(verb=>verb?.ok===false))continue;
    const result=step.canonical.result;
    for(const node of nodeDeliveryRows(step.canonical))if(typeof node?.path==='string')nodes.set(node.path,{path:node.path,role:node.role,label:node.label});
    if(step.tool!=='houdini_ui_screenshot')continue;
    const capture=result;
    if(capture?.fresh!==true||capture.file_status!=='passed'||typeof capture.path!=='string')continue;
    if(!fs.statSync(capture.path).isFile())continue;
    uiCaptures.push({path:capture.path,name:path.basename(capture.path),
      sha256:createHash('sha256').update(fs.readFileSync(capture.path)).digest('hex'),
      callId:step.callId,requestRef:step.canonical.requestReceipt?.request_ref,
      runtimeId:step.canonical.execution?.runtime_id,target:capture.target??null,
      attachment:step.canonical.imageAttachments?.find(a=>typeof a.from==='string'
        && path.normalize(resolveWorkspacePath(cwd,a.from))===path.normalize(resolveWorkspacePath(cwd,capture.path)))?.attachment??null});
  }
  return {schemaVersion:1,uiCaptures,files:[...files.values()],nodes:[...nodes.values()]};
}

if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){
  const [session,output,cwd,sessionId]=process.argv.slice(2);
  if(!session||!output||!cwd||!sessionId)throw Error('Explicit owned session, artifact output, workspace and sessionId required');
  const loaded=loadSessionEvents(session);
  if(loaded.frameErrors.length||loaded.lineErrors.length)throw Error('Incomplete native session read; no frontend artifact certification');
  const {steps}=normalizeTraceSteps(loaded.events);
  const artifacts=frontendArtifacts(loaded.events,steps,{cwd,sessionId});
  fs.writeFileSync(output,JSON.stringify(artifacts,null,2));
  console.log(JSON.stringify({uiArtifacts:artifacts.uiCaptures.length,files:artifacts.files.length,nodes:artifacts.nodes.length,
    source:'native presented files and successful canonical Houdini receipts'}));
}
