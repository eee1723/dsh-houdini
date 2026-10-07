import assert from 'node:assert/strict'
import {projectExecutionState,projectExecutionNotice} from '../../lib/execution-state.js'
import {executionHistory} from '../../lib/execution-history.js'
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
