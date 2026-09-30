import assert from 'node:assert/strict'
import {projectExecutionState,projectExecutionNotice} from '../../lib/execution-state.js'
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
assert.equal(projectExecutionNotice(events).last_failure.error,'Unknown parameter')
result('correct','houdini_exec',observed(3))
assert.equal(projectExecutionNotice(events),null)
result('uncertain','houdini_exec',{ok:false,requestReceipt:{request_ref:'original',owner_call:'uncertain',status:'unknown_transport'}})
assert.deepEqual(projectExecutionNotice(events).unresolved_requests,[['original','unknown_transport']])
result('recovered','houdini_request',observed(4,{requestReceipt:{request_ref:'original',owner_call:'uncertain',status:'done'}}))
assert.deepEqual(projectExecutionState(events).unresolved_requests,[])
assert.equal(projectExecutionNotice(events),null)
result('job','houdini_job_submit',{jobId:'long',requestReceipt:{request_ref:'admission',status:'job_submitted'}})
assert.deepEqual(projectExecutionNotice(events).active_jobs,[['long','queued_or_unknown']])
result('done','houdini_job_status',{jobId:'long',status:'done',ok:true})
assert.equal(projectExecutionNotice(events),null)
result('late','houdini_request',{jobId:'long',requestReceipt:{request_ref:'admission',status:'job_submitted'}})
assert.equal(projectExecutionNotice(events),null,'late admission receipt does not revive a finished job')
result('domain-check','houdini_exec',observed(5,{evidence:[{verb:'geo_check_interfaces',status:'fail'}]}))
assert.equal(projectExecutionNotice(events),null,'domain results remain available to the author without a second acceptance interpreter')
result('failed-job','houdini_job_status',observed(6,{jobId:'failed-render',status:'failed',ok:false,error:'Renderer unavailable'}))
assert.equal(projectExecutionNotice(events).last_failure.error,'Renderer unavailable','a finished job keeps its actual execution error after foreground work')
for (const [code,unknown] of [['ABORTED',true],['ABORTED_BEFORE_DISPATCH',false]]) {
  const failure=[{type:'tool/call',seq:0,data:{callId:'cancel',name:'houdini_exec'}},
    {type:'tool/result',seq:1,data:{message:{isError:true,source:{callId:'cancel'}},error:{name:'ToolAborted',code}}}]
  const state=projectExecutionNotice(failure)
  assert.equal(state.last_failure.error.code,code)
  assert.equal(state.unresolved_calls.length,unknown?1:0,'DSH dispatch-stage codes determine whether cancellation leaves an unknown operation')
}
console.log('execution state: observations, actual errors, original-request recovery and terminal jobs passed')
