import {foldExecutorBinding} from '../../lib/executor-identity-projection.js'
import assert from 'node:assert/strict'
import {projectExecutionState,projectExecutionNotice,executionNoticeFromFacts} from '../../lib/execution-state.js'
import {executionHistory} from '../../lib/execution-history.js'
import {Session} from '@deepseek-ai/dsh-session'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {fixtureProjectionContext} from './fixture-session.mjs'
import {projectedExecutionFacts} from '../../lib/executor-identity-projection.js'
const liveCtx=fixtureProjectionContext()
function assertLiveEquivalent(session) {
  assert.deepEqual(executionNoticeFromFacts(projectedExecutionFacts(liveCtx,session)),projectExecutionNotice(session.snapshotEvents()),
    'DSH live outstanding state matches cold native/nested history facts')
}
const events=[]
function result(id,name,value) {
  events.push({type:'tool/call',data:{callId:id,name}},
    {type:'tool/result',data:{message:{source:{callId:id}},meta:{canonical:value}}})
}
const observed=(sequence,extra={})=>({ok:true,execution:{runtime_id:'runtime',hip_path:'scene.hip',sequence,observed_at:sequence},...extra})
assert.equal(projectExecutionState([]),null)
result('read','houdini_inspect',observed(1))
assert.equal(projectExecutionState(events).last_sequence,1)
assert.equal(projectExecutionNotice(events),null,'ordinary observations do not create automatic acceptance work')
result('bad','houdini_exec',observed(2,{ok:false,error:'Unknown parameter'}))
assert.equal(projectExecutionState(events).last_failure.error,'Unknown parameter')
assert.equal(projectExecutionNotice(events),null,'settled failure stays in its result without duplicating the full runtime context')
result('correct','houdini_exec',observed(3))
assert.equal(projectExecutionNotice(events),null)
result('uncertain','houdini_exec',{ok:false,requestReceipt:{request_ref:'original',owner_call:'uncertain',status:'unknown_transport'}})
assert.deepEqual(projectExecutionNotice(events).unresolved_requests,[['original','unknown_transport']])
result('waiting','houdini_request',{ok:true,requestReceipt:{request_ref:'original',owner_call:'uncertain',status:'running'}})
const runningNotice=projectExecutionNotice(events)
assert.deepEqual(runningNotice.unresolved_requests,[['original','running']])
assert.deepEqual(runningNotice.unresolved_calls,['uncertain'],'status reads do not create additional unresolved executions')
result('waiting-again','houdini_request',{ok:true,requestReceipt:{request_ref:'original',owner_call:'uncertain',status:'running'}})
assert.deepEqual(projectExecutionNotice(events),runningNotice,'same running receipt does not churn dynamic context')
result('recovered','houdini_request',observed(4,{requestReceipt:{request_ref:'original',owner_call:'uncertain',status:'done'}}))
assert.deepEqual(projectExecutionState(events).unresolved_requests,[])
assert.equal(projectExecutionNotice(events),null)
result('job','houdini_job_submit',{jobId:'long',requestReceipt:{request_ref:'admission',status:'job_submitted'}})
assert.deepEqual(projectExecutionNotice(events).active_jobs,[['long','queued_or_unknown']])
const outstanding=projectExecutionNotice(events)
result('unrelated','houdini_inspect',observed(5))
assert.deepEqual(projectExecutionNotice(events),outstanding,'a new scene observation does not repeat unchanged outstanding work')
result('done','houdini_job_status',{jobId:'long',status:'done',ok:true})
assert.equal(projectExecutionNotice(events),null)
result('late','houdini_request',{jobId:'long',requestReceipt:{request_ref:'admission',status:'job_submitted'}})
assert.equal(projectExecutionNotice(events),null,'late admission receipt does not revive a finished job')
result('domain-check','houdini_exec',observed(6,{evidence:[{verb:'geo_check_interfaces',status:'fail'}]}))
assert.equal(projectExecutionNotice(events),null,'domain results remain available to the author without a second acceptance interpreter')
result('failed-job','houdini_job_status',observed(7,{jobId:'failed-render',status:'failed',ok:false,error:'Renderer unavailable'}))
assert.equal(projectExecutionNotice(events),null,'finished job errors are already delivered by their result')
for (const [code,unknown] of [['ABORTED',true],['ABORTED_BEFORE_DISPATCH',false],['TOOL_OUTCOME_UNKNOWN',true],['TOOL_NOT_STARTED',false]]) {
  const failure=[{type:'tool/call',seq:0,data:{callId:'cancel',name:'houdini_exec'}},
    {type:'tool/result',seq:1,data:{message:{isError:true,source:{callId:'cancel'}},error:{name:'ToolAborted',code}}}]
  const state=projectExecutionNotice(failure)
  assert.equal(projectExecutionState(failure).last_failure.error.code,code)
  if(unknown)assert.equal(state.unresolved_calls.length,1,'uncertain cancellation still needs recovery')
  else assert.equal(state,null,'a confirmed pre-dispatch refusal needs no additional context')
}
console.log('execution state: observations, actual errors, original-request recovery and terminal jobs passed')

// Captures use the same request/execution facts; scene_writes=0 neither makes
// an unfinished capture disappear nor creates a scene mutation ledger.
for (const nested of [false,true]) {
  const captureEvents=[]
  const captureCall=(id)=>nested
    ? {type:'tool/ptc-dispatch-start',seq:captureEvents.length+1,data:{subCallId:id,parentCallId:'program',name:'houdini_ui_screenshot'}}
    : {type:'tool/call',seq:captureEvents.length+1,data:{callId:id,name:'houdini_ui_screenshot'}}
  const captureResult=(id,value)=>nested
    ? {type:'tool/ptc-dispatch',seq:captureEvents.length+1,data:{subCallId:id,parentCallId:'program',name:'houdini_ui_screenshot',
      content:[{type:'text',text:JSON.stringify({kind:'dsh-houdini/execution-v1',callId:id,tool:'houdini_ui_screenshot',value})}]}}
    : {type:'tool/result',seq:captureEvents.length+1,data:{message:{source:{callId:id}},meta:{canonical:value}}}
  captureEvents.push(captureCall('capture'))
  assert.equal(projectExecutionNotice(captureEvents).pending_calls,1)
  captureEvents.push(captureResult('capture',{ok:false,requestReceipt:{request_ref:'capture-ref',owner_call:'capture',status:'unknown_transport'}}))
  assert.deepEqual(projectExecutionNotice(captureEvents).unresolved_requests,[['capture-ref','unknown_transport']])
  captureEvents.push({type:'tool/call',seq:3,data:{callId:'recover-capture',name:'houdini_request'}},
    {type:'tool/result',seq:4,data:{message:{source:{callId:'recover-capture'}},meta:{canonical:observed(20,{
      result:{node:'/obj/asset/CTRL',path:'C:/capture.png',scene_writes:0,semantic_status:'unverified'},images:['C:/capture.png'],
      transaction:{status:'no_scene_change'},requestReceipt:{request_ref:'capture-ref',owner_call:'capture',status:'done',retrieved:true}})}}})
  assert.equal(projectExecutionNotice(captureEvents),null)
  assert.equal(executionHistory(captureEvents).rows.length,1,'recovery remains one canonical execution')
  assert.equal(executionHistory(captureEvents).rows[0].value.result.scene_writes,0)
  captureEvents.push(captureCall('fresh-capture'),captureResult('fresh-capture',observed(21,{
    result:{path:'C:/fresh.png',scene_writes:0,semantic_status:'unverified'},images:['C:/fresh.png'],transaction:{status:'no_scene_change'}})))
  assert.equal(executionHistory(captureEvents).foreground.at(-1).tool,'houdini_ui_screenshot')
  assert.equal(projectExecutionState(captureEvents).last_sequence,21)
  assert.equal(projectExecutionNotice(captureEvents),null)
}
for (const [code,unknown] of [['ABORTED',true],['ABORTED_BEFORE_DISPATCH',false],['TOOL_OUTCOME_UNKNOWN',true],['TOOL_NOT_STARTED',false]]) {
  const failure=[{type:'tool/call',seq:1,data:{callId:'capture-fail',name:'houdini_ui_screenshot'}},
    {type:'tool/result',seq:2,data:{message:{isError:true,source:{callId:'capture-fail'}},error:{code}}}]
  assert.equal(projectExecutionState(failure).last_failure.tool,'houdini_ui_screenshot')
  assert.equal(projectExecutionNotice(failure)?.unresolved_calls.length??0,Number(unknown))
}
console.log('UI capture execution facts: native/nested pending, unknown, recovery and scene-write-free observations passed')

for (const nested of [false,true]) {
  const history=[]
  const append=(id,name,value)=>history.push(...(nested?[
    {type:'tool/ptc-dispatch-start',data:{subCallId:id,name}},
    {type:'tool/ptc-dispatch',data:{subCallId:id,name,content:[{type:'text',text:JSON.stringify({kind:'dsh-houdini/execution-v1',callId:id,tool:name,value})}]}}
  ]:[{type:'tool/call',data:{callId:id,name}},{type:'tool/result',data:{message:{source:{callId:id}},meta:{canonical:value}}}]))
  const receipt={request_ref:'job-admission',owner_call:'submit',jobId:'retained-job',status:'job_submitted'}
  append('submit','houdini_job_submit',{jobId:receipt.jobId,requestReceipt:receipt})
  append('expired-admission','houdini_request',{ok:true,requestReceipt:{...receipt,status:'result_expired',job_finished:false,job_status:'running',job_result_available:false}})
  assert.deepEqual(projectExecutionNotice(history).active_jobs,[[receipt.jobId,'running']])
  assert.deepEqual(projectExecutionNotice(history).unavailable_results,[],'admission expiry does not mean a running job is finished')
  append('finished','houdini_request',{ok:true,requestReceipt:{...receipt,status:'result_expired',job_finished:true,job_status:'done',job_result_available:true}})
  assert.deepEqual(projectExecutionNotice(history).active_jobs,[[receipt.jobId,'finished_result_uncollected']])
  append('late-running','houdini_request',{ok:true,requestReceipt:{...receipt,job_finished:false,job_status:'running'}})
  assert.deepEqual(projectExecutionNotice(history).active_jobs,[[receipt.jobId,'finished_result_uncollected']],
    'an older running observation does not undo confirmed completion awaiting collection')
  append('pruned','houdini_request',{ok:true,requestReceipt:{...receipt,status:'result_expired',job_finished:true,job_result_available:false}})
  assert.deepEqual(projectExecutionNotice(history).active_jobs,[])
  assert.equal(projectExecutionNotice(history).unavailable_results[0].job_id,receipt.jobId)
  append('late-admission','houdini_request',{ok:true,requestReceipt:receipt})
  assert.equal(projectExecutionNotice(history).unavailable_results.length,1,'late admission cannot erase the unavailable outcome')
  append('actual-result','houdini_job_status',{ok:true,jobId:receipt.jobId,status:'done'})
  assert.equal(projectExecutionNotice(history),null,'a real collected result resolves the unavailable outcome')
  append('late-pruned','houdini_request',{ok:true,requestReceipt:{...receipt,status:'result_expired',job_finished:true,job_result_available:false}})
  assert.equal(projectExecutionNotice(history),null,'late expiry does not erase an already collected result')
}
console.log('Job recovery preserves admission expiry, uncollected results and terminal unavailable outcomes')

// A late lookup of a historical runtime is never current-scene state.
const selectedSession=Session.create('history-after-selection'),binding=new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents()))
const targetA={executor_id:'a'.repeat(32),runtime_id:'b'.repeat(32),scene_epoch:'c'.repeat(32),scene_id:'d'.repeat(32),
  registration_id:'e'.repeat(32),hip_path:'C:/project/a.hip',hip_is_new:false}
const targetB={...targetA,executor_id:'f'.repeat(32),runtime_id:'1'.repeat(32),scene_epoch:'2'.repeat(32),scene_id:'3'.repeat(32),hip_path:'C:/project/b.hip'}
const append=(id,name,value)=>{
 selectedSession.append('tool/call',{callId:id,name})
 selectedSession.append('tool/result',{message:{source:{callId:id}},meta:{canonical:value}},{surfaceOp:'append'})
}
const currentRead=(target,sequence)=>({ok:true,execution:{executor_id:target.executor_id,runtime_id:target.runtime_id,
 scene_epoch:target.scene_epoch,hip_path:target.hip_path,sequence,observed_at:sequence}})
await binding.select(selectedSession,targetA)
append('old-read','houdini_inspect',currentRead(targetA,1))
append('old-job','houdini_job_submit',{jobId:'a'.repeat(12),requestReceipt:{runtime_id:targetA.runtime_id,
 executor_id:targetA.executor_id,scene_epoch:targetA.scene_epoch,status:'job_submitted'}})
await binding.select(selectedSession,targetB)
append('current-read','houdini_inspect',currentRead(targetB,2))
append('late-receipt','houdini_request',{...currentRead(targetA,999),requestReceipt:{runtime_id:targetA.runtime_id,
 executor_id:targetA.executor_id,request_ref:targetA.runtime_id+'.'+'a'.repeat(32),status:'done'}})
append('late-job','houdini_job_status',{ok:true,jobId:'a'.repeat(12),status:'running'})
assert.equal(projectExecutionState(selectedSession.snapshotEvents()).runtime_id,targetB.runtime_id)
assert.equal(projectExecutionState(selectedSession.snapshotEvents()).last_sequence,2)
assert.deepEqual(executionHistory(selectedSession.snapshotEvents()).activeJobs,[],'old admission must not revive work in B')
assert(executionHistory(selectedSession.snapshotEvents(),{includeHistorical:true}).rows.some(row=>row.execution.runtime_id===targetA.runtime_id),
 'permission recovery and historical lookup retain original facts')
const reloaded={...targetA,scene_epoch:'4'.repeat(32)}
await binding.select(selectedSession,reloaded)
append('reload-read','houdini_inspect',currentRead(reloaded,3))
append('old-epoch-job','houdini_job_status',{ok:true,jobId:'a'.repeat(12),status:'running'})
assert.deepEqual(executionHistory(selectedSession.snapshotEvents()).activeJobs,[],'a job from a prior scene epoch is historical even in the same runtime')
await binding.select(selectedSession,null)
append('cleared-old-receipt','houdini_request',currentRead(targetA,1000))
assert.equal(projectExecutionState(selectedSession.snapshotEvents()),null,'an old receipt cannot give an unbound conversation a current scene')
assertLiveEquivalent(selectedSession)
console.log('execution scope: historical native/nested results and jobs do not contaminate the selected scene or explicit clear')

// Python RequestRegistry.status returns runtime/owner/ref, without repeating
// the admitted epoch. Match the original receipt even after same-process load.
for(const nested of [false,true])for(const change of ['reload','other','clear'])for(const status of ['unknown','running','done','result_expired']) {
  const session=Session.create(`old-request-${nested}-${change}-${status}`),selection=new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents()))
  const add=(id,name,value)=>{
    if(nested) {
      session.append('tool/ptc-dispatch-start',{subCallId:id,name})
      session.append('tool/ptc-dispatch',{subCallId:id,name,content:[{type:'text',text:JSON.stringify({
        kind:'dsh-houdini/execution-v1',callId:id,tool:name,value})}]})
    } else {
      session.append('tool/call',{callId:id,name})
      session.append('tool/result',{message:{source:{callId:id}},meta:{canonical:value}},{surfaceOp:'append'})
    }
  }
  const ref=targetA.runtime_id+'.'+'9'.repeat(32)
  await selection.select(session,targetA)
  add('original-call','houdini_exec',{ok:false,requestReceipt:{request_ref:ref,runtime_id:targetA.runtime_id,
    executor_id:targetA.executor_id,scene_epoch:targetA.scene_epoch,status:'unknown_transport'}})
  const target=change==='clear'?null:change==='other'?targetB:{...targetA,scene_epoch:'4'.repeat(32)}
  await selection.select(session,target)
  if(target)add('current-call','houdini_inspect',currentRead(target,2))
  add('historical-lookup','houdini_request',{ok:true,stdout:'',stderr:'',requestReceipt:{
    request_ref:ref,runtime_id:targetA.runtime_id,owner_call:'original-call',status}})
  assertLiveEquivalent(session)
  const current=executionHistory(session.snapshotEvents())
  assertLiveEquivalent(session)
  assert.deepEqual(current.activeRequests,[],`${change}: old ${status} is not current work`)
  assert.deepEqual(current.unavailableResults,[],'old retention expiry is not a current-scene outcome')
  assert.equal(current.resolvedCalls.has('original-call'),false,'old completion does not resolve current-scene calls')
  assert.equal(current.anchor?.execution.runtime_id,target?.runtime_id)
  const full=executionHistory(session.snapshotEvents(),{includeHistorical:true})
  assert.equal(full.results.get('historical-lookup').requestReceipt.status,status,'the original status response stays in raw history')
  if(status==='unknown'||status==='running')assert.deepEqual(full.activeRequests,[[ref,status]])
  else assert(full.resolvedCalls.has('original-call'))
}
console.log('request scope: original native/nested receipt epochs survive sparse status reads after reload, target change and clear')

for(const nested of [false,true])for(const status of ['unknown','running','not_executed','done','result_expired']) {
  const session=Session.create(`lost-original-${nested}-${status}`),selection=new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents()))
  const call=(id,name)=>session.append(nested?'tool/ptc-dispatch-start':'tool/call',nested?{subCallId:id,name}:{callId:id,name})
  const result=(id,name,value)=>nested
    ?session.append('tool/ptc-dispatch',{subCallId:id,name,content:[{type:'text',text:JSON.stringify({
      kind:'dsh-houdini/execution-v1',callId:id,tool:name,value})}]})
    :session.append('tool/result',{message:{source:{callId:id}},meta:{canonical:value}},{surfaceOp:'append'})
  const lookup=(id,ref,owner)=>{
    call(id,'houdini_request')
    result(id,'houdini_request',{ok:true,requestReceipt:{request_ref:ref,runtime_id:targetA.runtime_id,status,
      ...(owner?{owner_call:owner}:{})}})
  }
  await selection.select(session,targetA)
  call('old-result-lost','houdini_exec')
  await selection.select(session,{...targetA,scene_epoch:'4'.repeat(32)})
  const oldRef=targetA.runtime_id+'.'+'8'.repeat(32),unattributedRef=targetA.runtime_id+'.'+'7'.repeat(32)
  lookup('old-ref-lookup',oldRef,'old-result-lost')
  lookup('no-owner-lookup',unattributedRef)
  const historicalOnly=executionHistory(session.snapshotEvents())
  assert.deepEqual(historicalOnly.activeRequests,[],'an old owner or no owner cannot assign a sparse receipt to the selected scene')
  assert.deepEqual(historicalOnly.unavailableResults,[])
  assert.equal(historicalOnly.resolvedCalls.has('old-result-lost'),false)
  assert.equal(historicalOnly.results.get('old-ref-lookup').requestReceipt.status,status,'sparse historical responses remain retrievable')
  call('current-result-lost','houdini_exec')
  const currentRef=targetA.runtime_id+'.'+'6'.repeat(32)
  lookup('current-ref-lookup',currentRef,'current-result-lost')
  const current=executionHistory(session.snapshotEvents())
  const terminal=['not_executed','done','result_expired'].includes(status)
  assert.deepEqual(current.pendingCalls,terminal?[]:['current-result-lost'],'current lost results can settle through their original owner_call')
  assert.equal(current.resolvedCalls.has('current-result-lost'),terminal)
  assert.deepEqual(current.activeRequests,terminal?[]:[[currentRef,status]])
  assert.equal(current.unavailableResults.length,Number(status==='result_expired'))
}
console.log('request scope: sparse receipts resolve current lost results without adopting old or unattributed requests')

for(const nested of [false,true])for(const [control,status] of [['houdini_job_status','running'],['houdini_job_cancel','cancelled']]) {
  const session=Session.create(`lost-job-${nested}-${control}`),selection=new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents()))
  const call=(id,name)=>session.append(nested?'tool/ptc-dispatch-start':'tool/call',nested?{subCallId:id,name}:{callId:id,name})
  const result=(id,name,value)=>nested
    ?session.append('tool/ptc-dispatch',{subCallId:id,name,content:[{type:'text',text:JSON.stringify({
      kind:'dsh-houdini/execution-v1',callId:id,tool:name,value})}]})
    :session.append('tool/result',{message:{source:{callId:id}},meta:{canonical:value}},{surfaceOp:'append'})
  const add=(id,name,value)=>{call(id,name);result(id,name,value)}
  const recoverJob=(id,jobId,owner)=>add(id,'houdini_request',{ok:true,result:{jobId},requestReceipt:{jobId,
    request_ref:targetA.runtime_id+'.'+(owner==='old-job-lost'?'8':'9').repeat(32),
    runtime_id:targetA.runtime_id,owner_call:owner,status:'job_submitted'}})
  const oldJob='7'.repeat(12),currentJob='6'.repeat(12)
  await selection.select(session,targetA)
  call('old-job-lost','houdini_job_submit')
  await selection.select(session,{...targetA,scene_epoch:'4'.repeat(32)})
  recoverJob('recover-old-job',oldJob,'old-job-lost')
  add('old-job-control',control,{ok:true,jobId:oldJob,status})
  assert.deepEqual(executionHistory(session.snapshotEvents()).activeJobs,[],'an unscoped recovered old admission cannot make later job controls current')
  call('current-job-lost','houdini_job_submit')
  recoverJob('recover-current-job',currentJob,'current-job-lost')
  assertLiveEquivalent(session)
  let current=executionHistory(session.snapshotEvents())
  assert.deepEqual(current.pendingCalls,[],'current admission recovery settles the lost submit call')
  assert.deepEqual(current.activeJobs,[[currentJob,'queued_or_unknown']],'current owner_call can establish the recovered job in this scope')
  add('current-job-control',control,{ok:true,jobId:currentJob,status})
  current=executionHistory(session.snapshotEvents())
  assert.deepEqual(current.activeJobs,status==='running'?[[currentJob,status]]:[],'sparse controls can update a job already admitted in the current scope')
  assert.equal(current.results.get('old-job-control').status,status,'old job control responses remain in raw results')
}
console.log('job scope: lost historical admissions stay historical while current lost submissions can be recovered and controlled')
