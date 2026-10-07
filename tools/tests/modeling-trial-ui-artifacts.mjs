// Resolve only successful UI-capture artifacts from the real native session.
// Frontend image verification must match these paths, not an unrelated PNG.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {loadSessionEvents} from '../trace-session-lib.mjs';
import {normalizeTraceSteps} from '../normalized-trace-steps.mjs';
const [session,output]=process.argv.slice(2);
if(!session||!output)throw Error('Explicit owned session and artifact output required');
const loaded=loadSessionEvents(session);
if(loaded.frameErrors.length||loaded.lineErrors.length)throw Error('Incomplete native session read; no UI artifact certification');
const {steps}=normalizeTraceSteps(loaded.events);
const artifacts=[];
for(const step of steps){
  if(step.tool!=='houdini_ui_screenshot'||step.failed)continue;
  const capture=step.canonical?.result;
  if(capture?.fresh!==true||capture.file_status!=='passed'||typeof capture.path!=='string')continue;
  if(!fs.statSync(capture.path).isFile())continue;
  artifacts.push({path:capture.path,name:path.basename(capture.path),
    sha256:createHash('sha256').update(fs.readFileSync(capture.path)).digest('hex'),
    callId:step.callId,requestRef:step.canonical.requestReceipt?.request_ref,
    runtimeId:step.canonical.execution?.runtime_id,target:capture.target??null,
    attachment:step.canonical.imageAttachments?.find(a=>a.path===capture.path)?.attachment??null});
}
fs.writeFileSync(output,JSON.stringify(artifacts,null,2));
console.log(JSON.stringify({uiArtifacts:artifacts.length,source:'successful canonical native UI capture receipts'}));
