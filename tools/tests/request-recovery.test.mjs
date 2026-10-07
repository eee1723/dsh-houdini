import assert from 'node:assert/strict';
import http from 'node:http';
import {randomUUID} from 'node:crypto';
import {HoudiniBridge} from '../../lib/bridge.js';
import {registerHoudiniTools} from '../../lib/tools.js';
import {projectExecutionState} from '../../lib/execution-state.js';
import {normalizeTraceSteps} from '../normalized-trace-steps.mjs';
import {EXPECTED_EXECUTION_CONTRACT_VERSION as version,EXPECTED_VERB_CATALOG_HASH as hash} from '../../lib/generated-verb-contract.js';
const runtime='a'.repeat(32),records=new Map(),sourceCalls=new Map(),tickets=new Set();let edits=0,jobs=0,captures=0,preparations=0,mode='disconnect',ticketMode='valid';
let onExecAdmitted;
let onCaptureAdmitted;
const server=http.createServer((req,res)=>{
 res.setHeader('content-type','application/json');
 let text='';req.on('data',b=>text+=b);req.on('end',()=>{
  const body=JSON.parse(text);
  if(req.url==='/requests/prepare'){
   preparations++;
   assert.deepEqual(body,{owner_session:'owner'});
   const ref=runtime+'.'+randomUUID().replaceAll('-','');tickets.add(ref);
   res.end(JSON.stringify({ok:true,runtimeId:runtime,executionContractVersion:version,verbCatalog:{hash},
    ...(ticketMode==='missing'?{}:{requestRef:ticketMode==='wrong-runtime'?'b'.repeat(32)+'.'+ref.split('.')[1]:ref})}));return;
  }
  if(body.request_ref && body.owner_call)sourceCalls.set(body.request_ref,body.owner_call);
  if(req.url==='/exec'){
   assert(tickets.delete(body.request_ref),'Host must submit the prepared Bridge ticket exactly once');
   edits++;
   const value={ok:true,stdout:'executed once',stderr:'',result:edits,transaction:{status:'committed',nodes:[]},
    execution:{runtime_id:runtime,sequence:edits,observed_at:edits,impact:{attempted:true,global:true,nodes:[]}},
    requestReceipt:{request_ref:body.request_ref,runtime_id:runtime,status:'done'}};
   records.set(body.request_ref,value);
   onExecAdmitted?.();
   if(mode==='disconnect')req.socket.destroy();
   else if(mode==='bad-json')res.end('{broken');
   else if(mode==='delay')setTimeout(()=>res.end(JSON.stringify(value)),150);
   else {res.statusCode=500;res.end('response failed after mutation');}
  }else if(req.url==='/ui/capture'){
   assert.deepEqual(Object.keys(body).sort(),['node','view','owner_session','owner_call','expected_contract','request_ref'].sort(),
    'UI request has fixed UI fields and provenance, without Python code');
   assert.equal(body.node,'/obj/demo/CTRL');assert.equal(body.view,'parameters');
   assert.equal(body.owner_session,'owner');assert.equal(body.owner_call,'capture-call');
   assert.deepEqual(body.expected_contract,{version,hash});
   assert(tickets.delete(body.request_ref),'capture consumes the same-runtime prepared ticket once');
   captures++;
   const facts={node:body.node,view:body.view,path:'C:/fixture/layout-'+captures+'.png',scene_writes:0,semantic_status:'unverified',fresh:true};
   const value={ok:true,stdout:'',stderr:'',result:facts,evidence:[{operation:'ui_capture',...facts}],images:[facts.path],
    transaction:{status:'no_scene_change',nodes:[]},
    execution:{runtime_id:runtime,sequence:100+captures,observed_at:100+captures,impact:{attempted:false,global:false,nodes:[]}},
    requestReceipt:{request_ref:body.request_ref,runtime_id:runtime,status:'done'}};
   records.set(body.request_ref,value);onCaptureAdmitted?.();
   if(mode==='disconnect')req.socket.destroy();
   else if(mode==='bad-json')res.end('{broken');
   else if(mode==='delay')setTimeout(()=>res.end(JSON.stringify(value)),150);
   else{res.statusCode=500;res.end('response failed after capture');}
  }else if(req.url==='/jobs'){
   assert.equal(body.owner_session,'owner','job admission carries the session identity');
   assert.equal(body.owner_call,'lost-job-call','job admission carries the current callId');
   assert.deepEqual(body.expected_contract,{version,hash},'job admission carries the expected contract');
   assert(tickets.delete(body.request_ref));
   jobs++;records.set(body.request_ref,{jobId:'job-'+jobs});req.socket.destroy();
  }else if(req.url==='/requests/status'){
   res.end(JSON.stringify({ok:true,stdout:'',stderr:'',requestReceipt:body.request_ref==='index'
    ? {runtime_id:runtime,status:'index',requests:[...records.keys()].map(ref=>({request_ref:ref,owner_call:sourceCalls.get(ref)}))}
    : {request_ref:body.request_ref,owner_call:sourceCalls.get(body.request_ref),runtime_id:runtime,status:'done',result:records.get(body.request_ref)}}));
  }else{res.statusCode=404;res.end('{}');}
 });
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
try{
 const bridge=new HoudiniBridge(`http://127.0.0.1:${server.address().port}`,80);
 const owner={sessionId:'owner',callId:'call'};
 for(const invalid of ['missing','wrong-runtime']) {
  ticketMode=invalid;
  await assert.rejects(bridge.exec('must_not_submit()',owner),/valid same-runtime request ticket/);
  await assert.rejects(bridge.captureUi({node:'/obj/demo/CTRL',view:'parameters'},owner),/valid same-runtime request ticket/);
  assert.equal(edits,0,'invalid prepare response never submits scene code');
  assert.equal(captures,0,'invalid or wrong-runtime ticket never prepares a native pane');
 }
 ticketMode='valid';
 for(const failure of ['disconnect','bad-json','delay','http-error']){
  mode=failure;
  const unknown=await bridge.exec('mutate()',owner);
  assert.equal(unknown.requestReceipt.status,'unknown_transport');
  const before=edits,receipt=await bridge.requestStatus(unknown.requestReceipt.request_ref,owner);
  assert.equal(receipt.requestReceipt.status,'done');assert.equal(receipt.requestReceipt.result.result,before);
  assert.equal(edits,before,'recovery never repeats a mutation');
 }
 mode='delay';
 const cancellation=new AbortController();onExecAdmitted=()=>cancellation.abort();
 const cancelled=await bridge.exec('mutate_then_cancel()',owner,cancellation.signal);
 onExecAdmitted=undefined;
 assert.equal(cancelled.requestReceipt.status,'unknown_transport');
 const beforeRecovery=edits;
 assert.equal((await bridge.requestStatus(cancelled.requestReceipt.request_ref,owner)).requestReceipt.result.result,beforeRecovery);
 assert.equal(edits,beforeRecovery,'AbortSignal cancellation after dispatch must recover without executing again');
 const defs=new Map();registerHoudiniTools({tools:{register:d=>defs.set(d.name,d)}},bridge);
 const ref=[...records.keys()][0],ctx={agent:{id:'owner',session:{header:{}}},callId:'recover'};
 const recovered=await defs.get('houdini_request').execute({request_ref:ref},ctx);
 assert.equal(recovered.requestReceipt.retrieved,true);assert.equal(recovered.result,1);
 const events=[{seq:1,type:'tool/call',data:{name:'houdini_exec',callId:'unknown'}},
  {seq:2,type:'tool/result',data:{message:{source:{callId:'unknown'}},meta:{canonical:{ok:false,requestReceipt:{request_ref:ref,status:'unknown_transport'}}}}}];
 assert.equal(projectExecutionState(events).unresolved_requests.length,1);
 events.push({seq:3,type:'tool/call',data:{name:'houdini_request',callId:'recovered'}},
  {seq:4,type:'tool/result',data:{message:{source:{callId:'recovered'}},meta:{canonical:recovered}}});
 assert.equal(projectExecutionState(events).unresolved_requests.length,0);assert.equal(projectExecutionState(events).last_sequence,1);
 const lateReceiptEvents=[...events,
  {seq:5,type:'tool/call',data:{name:'houdini_request',callId:'late-status'}},
  {seq:6,type:'tool/result',data:{message:{source:{callId:'late-status'}},meta:{canonical:{ok:true,
   requestReceipt:{request_ref:ref,status:'running'}}}}}];
 assert.equal(projectExecutionState(lateReceiptEvents).unresolved_requests.length,0,
  'a delayed running snapshot must not undo an observed completion');
 const expiredAfterRecovery=[...events,
  {seq:5,type:'tool/call',data:{name:'houdini_request',callId:'expired-status'}},
  {seq:6,type:'tool/result',data:{message:{source:{callId:'expired-status'}},meta:{canonical:{ok:true,
   requestReceipt:{request_ref:ref,status:'result_expired'}}}}}];
 assert.equal(projectExecutionState(expiredAfterRecovery).unresolved_requests.length,0,
  'retention expiry cannot erase the original result already present in Host history');
 assert.deepEqual(projectExecutionState(expiredAfterRecovery).unavailable_results,[],
  'an already recorded original result stays available after Bridge retention expiry');
 for(const status of ['result_expired','result_unavailable']) {
  const finished=[{seq:1,type:'tool/call',data:{name:'houdini_exec',callId:'lost'}},
   {seq:2,type:'tool/result',data:{message:{isError:true,source:{callId:'lost'}},error:{code:'ABORTED'}}},
   {seq:3,type:'tool/call',data:{name:'houdini_request',callId:'finished'}},
   {seq:4,type:'tool/result',data:{message:{source:{callId:'finished'}},meta:{canonical:{ok:true,
    requestReceipt:{request_ref:ref,status,owner_call:'lost'}}}}}];
  const state=projectExecutionState(finished);
  assert.deepEqual(state.unresolved_requests,[]);
  assert.deepEqual(state.unresolved_calls,[]);
  assert.equal(state.last_failure,null,'a recovered completion supersedes the Host delivery cancellation');
  assert.deepEqual(state.unavailable_results,[{request_ref:ref,owner_call:'lost',status:'finished_result_unavailable',
   retention_status:status,outcome:'unverified'}]);
 }
 recovered.verbs=[{verb:'set_parm',ok:true,args:['/obj/a','tx',1],result:{value:1},ms:1}];
 const normalized=normalizeTraceSteps(events).steps;
 assert.equal(normalized.at(-1).verbs.length,0,'retrieving old execution does not count its verbs as executed again');
 assert.equal(normalized.at(-1).recoveredExecution,true);
 assert.equal(normalizeTraceSteps(events).uniqueExecutions.length,1);
 const replayEvents=[...events,{seq:5,type:'tool/call',data:{name:'houdini_job_status',callId:'repeat-result'}},
  {seq:6,type:'tool/result',data:{message:{source:{callId:'repeat-result'}},meta:{canonical:recovered}}}];
 assert.equal(normalizeTraceSteps(replayEvents).uniqueExecutions.length,1);
 assert.equal(normalizeTraceSteps(replayEvents).steps.at(-1).executionReplay,true);
 // The fixed UI endpoint has the same uncertain-response contract. Recovery
 // reads its original capture even though it made no scene parameter writes.
 for(const failure of ['disconnect','bad-json','delay','http-error']){
  mode=failure;
  const unknown=await defs.get('houdini_ui_screenshot').execute({node:'/obj/demo/CTRL',view:'parameters'},{...ctx,callId:'capture-call'});
  assert.equal(unknown.requestReceipt.status,'unknown_transport');
  assert.match(unknown.requestReceipt.next_action,/original reference[\s\S]*Do not start another capture/);
  const before=captures,preparedBefore=preparations;
  const restoredCapture=await defs.get('houdini_request').execute({request_ref:unknown.requestReceipt.request_ref},ctx);
  assert.equal(restoredCapture.requestReceipt.retrieved,true);assert.equal(restoredCapture.requestReceipt.status,'done');
  assert.equal(restoredCapture.result.scene_writes,0);assert.equal(restoredCapture.result.semantic_status,'unverified');
  assert.deepEqual(restoredCapture.images,['C:/fixture/layout-'+before+'.png']);
  assert.equal(restoredCapture.verbs,undefined,'receipt retrieval has no synthetic Python operation');
  assert.equal(captures,before);assert.equal(preparations,preparedBefore,'retrieval sends no prepare request or UI request');
  const captureEvents=[{seq:1,type:'tool/call',data:{name:'houdini_ui_screenshot',callId:'capture-call',arguments:{node:'/obj/demo/CTRL'}}},
   {seq:2,type:'tool/result',data:{message:{source:{callId:'capture-call'}},meta:{canonical:unknown}}}];
  assert.equal(projectExecutionState(captureEvents).unresolved_requests.length,1);
  captureEvents.push({seq:3,type:'tool/call',data:{name:'houdini_request',callId:'capture-recovered'}},
   {seq:4,type:'tool/result',data:{message:{source:{callId:'capture-recovered'}},meta:{canonical:restoredCapture}}});
  assert.equal(projectExecutionState(captureEvents).unresolved_requests.length,0);
  assert.equal(projectExecutionState(captureEvents).last_sequence,100+before);
  assert.equal(normalizeTraceSteps(captureEvents).uniqueExecutions.length,1);
 }
 mode='delay';
 const captureAbort=new AbortController();onCaptureAdmitted=()=>captureAbort.abort();
 const captureCancelled=await bridge.captureUi({node:'/obj/demo/CTRL',view:'parameters'},{...owner,callId:'capture-call'},captureAbort.signal);
 onCaptureAdmitted=undefined;
 assert.equal(captureCancelled.requestReceipt.status,'unknown_transport');
 const capturesBeforeRecovery=captures;
 const cancelledRecovered=await bridge.requestStatus(captureCancelled.requestReceipt.request_ref,owner);
 assert.equal(cancelledRecovered.requestReceipt.result.result.scene_writes,0);
 assert.equal(captures,capturesBeforeRecovery,'cancelled post-dispatch capture is recovered without another capture');
 const waiting=defs.get('houdini_request').output.render({}, {ok:true,stdout:'',stderr:'',requestReceipt:{status:'running',request_ref:ref}})[0].text;
 assert.ok(waiting.startsWith('Request receipt status: running'));
 assert.ok(!waiting.includes('Executed successfully.'));
 const lostJob=await defs.get('houdini_job_submit').execute({code:'long render'}, {...ctx,callId:'lost-job-call'});
 assert.equal(lostJob.jobId,undefined);assert.equal(lostJob.requestReceipt.status,'unknown_transport');
 const jobText=defs.get('houdini_job_submit').output.render({},lostJob)[0].text;
 assert.ok(!jobText.includes('Started Houdini job undefined'));
 // Simulate Host discarding the original tool result: only call event survives.
 const index=await defs.get('houdini_request').execute({request_ref:'index'},ctx);
 const discovered=index.requestReceipt.requests.find(r=>r.owner_call==='lost-job-call');
 const jobResult=await defs.get('houdini_request').execute({request_ref:discovered.request_ref},ctx);
 assert.equal(jobResult.result.jobId,'job-1');assert.equal(jobResult.requestReceipt.status,'job_submitted');assert.equal(jobs,1);
 const jobEvents=[{seq:1,type:'tool/call',data:{name:'houdini_job_submit',callId:'lost-job-call'}},
  {seq:2,type:'tool/call',data:{name:'houdini_request',callId:'recover-job'}},
  {seq:3,type:'tool/result',data:{message:{source:{callId:'recover-job'}},meta:{canonical:jobResult}}}];
 assert.equal(projectExecutionState(jobEvents).pending_calls,0);
 assert.equal(projectExecutionState(jobEvents).active_jobs[0][0],'job-1');
 jobEvents.push({seq:4,type:'tool/call',data:{name:'houdini_job_status',callId:'job-done'}},
  {seq:5,type:'tool/result',data:{message:{source:{callId:'job-done'}},meta:{canonical:{ok:true,jobId:'job-1',status:'done'}}}},
  {seq:6,type:'tool/call',data:{name:'houdini_request',callId:'late-admission'}},
  {seq:7,type:'tool/result',data:{message:{source:{callId:'late-admission'}},meta:{canonical:jobResult}}});
 assert.equal(projectExecutionState(jobEvents),null,'late admission recovery does not revive a terminal job');
 assert.equal(preparations,edits+jobs+captures+4,'one prepare per attempted call; recovery does not prepare or resubmit');
}finally{await new Promise(r=>server.close(r));}
console.log('exec/UI response disconnect/timeout/invalid JSON/HTTP failure recovery and state resolution passed');
