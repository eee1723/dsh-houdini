import assert from 'node:assert/strict';
import http from 'node:http';
import {randomUUID} from 'node:crypto';
import {HoudiniBridge} from '../../lib/bridge.js';
import {registerHoudiniTools} from '../../lib/tools.js';
import {projectExecutionState} from '../../lib/execution-state.js';
import {normalizeTraceSteps} from '../normalized-trace-steps.mjs';
import {EXPECTED_EXECUTION_CONTRACT_VERSION as version,EXPECTED_VERB_CATALOG_HASH as hash} from '../../lib/generated-verb-contract.js';
const runtime='a'.repeat(32),records=new Map(),sourceCalls=new Map(),tickets=new Set();let edits=0,jobs=0,preparations=0,mode='disconnect',ticketMode='valid';
let onExecAdmitted;
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
  }else if(req.url==='/jobs'){
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
  await assert.rejects(bridge.exec('must_not_submit()',undefined,undefined,owner),/valid same-runtime request ticket/);
  assert.equal(edits,0,'invalid prepare response never submits scene code');
 }
 ticketMode='valid';
 for(const failure of ['disconnect','bad-json','delay','http-error']){
  mode=failure;
  const unknown=await bridge.exec('mutate()',undefined,undefined,owner);
  assert.equal(unknown.requestReceipt.status,'unknown_transport');
  const before=edits,receipt=await bridge.requestStatus(unknown.requestReceipt.request_ref,owner);
  assert.equal(receipt.requestReceipt.status,'done');assert.equal(receipt.requestReceipt.result.result,before);
  assert.equal(edits,before,'recovery never repeats a mutation');
 }
 mode='delay';
 const cancellation=new AbortController();onExecAdmitted=()=>cancellation.abort();
 const cancelled=await bridge.exec('mutate_then_cancel()',cancellation.signal,undefined,{sessionId:'owner',callId:'cancelled-call'});
 onExecAdmitted=undefined;
 assert.equal(cancelled.requestReceipt.status,'unknown_transport');
 const beforeRecovery=edits;
 assert.equal((await bridge.requestStatus(cancelled.requestReceipt.request_ref,owner)).requestReceipt.result.result,beforeRecovery);
 assert.equal(edits,beforeRecovery,'AbortSignal cancellation after dispatch must recover without executing again');
 const defs=new Map();registerHoudiniTools({tools:{register:d=>defs.set(d.name,d)}},bridge);
 const ref=[...records.keys()][0],ctx={agent:{id:'owner',session:{header:{}}},callId:'recover'};
 const recovered=await defs.get('houdini_query').execute({request_ref:ref},ctx);
 assert.equal(recovered.requestReceipt.retrieved,true);assert.equal(recovered.result,1);
 await assert.rejects(defs.get('houdini_query').execute({request_ref:ref,code:'x'},ctx),/exactly one/);
 await assert.rejects(defs.get('houdini_query').execute({request_ref:ref,offset:1},ctx),/does not accept/);
 const events=[{seq:1,type:'tool/call',data:{name:'houdini_exec',callId:'unknown'}},
  {seq:2,type:'tool/result',data:{message:{source:{callId:'unknown'}},meta:{canonical:{ok:false,requestReceipt:{request_ref:ref,status:'unknown_transport'}}}}}];
 assert.equal(projectExecutionState(events).unresolved_requests.length,1);
 events.push({seq:3,type:'tool/call',data:{name:'houdini_query',callId:'recovered'}},
  {seq:4,type:'tool/result',data:{message:{source:{callId:'recovered'}},meta:{canonical:recovered}}});
 assert.equal(projectExecutionState(events).unresolved_requests.length,0);assert.equal(projectExecutionState(events).last_sequence,1);
 const lateReceiptEvents=[...events,
  {seq:5,type:'tool/call',data:{name:'houdini_query',callId:'late-status'}},
  {seq:6,type:'tool/result',data:{message:{source:{callId:'late-status'}},meta:{canonical:{ok:true,
   requestReceipt:{request_ref:ref,status:'running'}}}}}];
 assert.equal(projectExecutionState(lateReceiptEvents).unresolved_requests.length,0,
  'a delayed running snapshot must not undo an observed completion');
 const expiredAfterRecovery=[...events,
  {seq:5,type:'tool/call',data:{name:'houdini_query',callId:'expired-status'}},
  {seq:6,type:'tool/result',data:{message:{source:{callId:'expired-status'}},meta:{canonical:{ok:true,
   requestReceipt:{request_ref:ref,status:'result_expired'}}}}}];
 assert.equal(projectExecutionState(expiredAfterRecovery).unresolved_requests.length,0,
  'retention expiry cannot erase the original result already present in Host history');
 recovered.verbs=[{verb:'set_parm',ok:true,args:['/obj/a','tx',1],result:{value:1},ms:1}];
 const normalized=normalizeTraceSteps(events).steps;
 assert.equal(normalized.at(-1).verbs.length,0,'retrieving old execution does not count its verbs as executed again');
 assert.equal(normalized.at(-1).recoveredExecution,true);
 assert.equal(normalizeTraceSteps(events).uniqueExecutions.length,1);
 const replayEvents=[...events,{seq:5,type:'tool/call',data:{name:'houdini_job_status',callId:'repeat-result'}},
  {seq:6,type:'tool/result',data:{message:{source:{callId:'repeat-result'}},meta:{canonical:recovered}}}];
 assert.equal(normalizeTraceSteps(replayEvents).uniqueExecutions.length,1);
 assert.equal(normalizeTraceSteps(replayEvents).steps.at(-1).executionReplay,true);
 const waiting=defs.get('houdini_query').output.render({}, {ok:true,stdout:'',stderr:'',requestReceipt:{status:'running',request_ref:ref}})[0].text;
 assert.ok(waiting.startsWith('Request receipt status: running'));
 assert.ok(!waiting.includes('Executed successfully.'));
 const lostJob=await defs.get('houdini_job_submit').execute({code:'long render'}, {...ctx,callId:'lost-job-call'});
 assert.equal(lostJob.jobId,undefined);assert.equal(lostJob.requestReceipt.status,'unknown_transport');
 const jobText=defs.get('houdini_job_submit').output.render({},lostJob)[0].text;
 assert.ok(!jobText.includes('Started Houdini job undefined'));
 // Simulate Host discarding the original tool result: only call event survives.
 const index=await defs.get('houdini_query').execute({request_ref:'index'},ctx);
 const discovered=index.requestReceipt.requests.find(r=>r.owner_call==='lost-job-call');
 const jobResult=await defs.get('houdini_query').execute({request_ref:discovered.request_ref},ctx);
 assert.equal(jobResult.result.jobId,'job-1');assert.equal(jobResult.requestReceipt.status,'job_submitted');assert.equal(jobs,1);
 const jobEvents=[{seq:1,type:'tool/call',data:{name:'houdini_job_submit',callId:'lost-job-call'}},
  {seq:2,type:'tool/call',data:{name:'houdini_query',callId:'recover-job'}},
  {seq:3,type:'tool/result',data:{message:{source:{callId:'recover-job'}},meta:{canonical:jobResult}}}];
 assert.equal(projectExecutionState(jobEvents).pending_calls,0);
 assert.equal(projectExecutionState(jobEvents).active_jobs[0][0],'job-1');
 jobEvents.push({seq:4,type:'tool/call',data:{name:'houdini_job_status',callId:'job-done'}},
  {seq:5,type:'tool/result',data:{message:{source:{callId:'job-done'}},meta:{canonical:{ok:true,jobId:'job-1',status:'done'}}}},
  {seq:6,type:'tool/call',data:{name:'houdini_query',callId:'late-admission'}},
  {seq:7,type:'tool/result',data:{message:{source:{callId:'late-admission'}},meta:{canonical:jobResult}}});
 assert.equal(projectExecutionState(jobEvents),null,'late admission recovery does not revive a terminal job');
 assert.equal(preparations,edits+jobs+2,'one prepare replaces health; recovery does not prepare or resubmit');
}finally{await new Promise(r=>server.close(r));}
console.log('exec response disconnect/timeout/invalid JSON/HTTP failure recovery and state resolution passed');
