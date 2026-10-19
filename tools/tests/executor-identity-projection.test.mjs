import assert from 'node:assert/strict'
import {Context} from '@deepseek-ai/cordis'
import {Session} from '@deepseek-ai/dsh-session'
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection'
import {ExecutorBinding,recordedExecutorIdentity} from '../../lib/executor-binding.js'
import {houdiniSnapshot,recordHoudiniContext,workspaceOpeningMessage} from '../../lib/dsh-adapter.js'
import {recoveryMessage} from '../../lib/scene-recovery.js'
import {executionHistory} from '../../lib/execution-history.js'
import {executorIdentityProjection as projection,foldExecutorState,projectedExecutorBindingState,projectedExecutorIdentity,registerExecutorIdentityProjection}
  from '../../lib/executor-identity-projection.js'
const first='a'.repeat(32),second='b'.repeat(32),ctx=new Context()
new SessionProjectionRegistry(ctx)
registerExecutorIdentityProjection(ctx)
const session=Session.create('identity-projection')
const binding=new ExecutorBinding(current=>projectedExecutorBindingState(ctx,current))
await binding.ensure(session,first)
assert.deepEqual(projectedExecutorBindingState(ctx,session),{identity:first,bindingRecorded:true})
assert.equal(recordedExecutorIdentity(session.snapshotEvents()),first)
const id='nested:ptc:1'
session.append('tool/ptc-dispatch-start',{rootCallId:'nested',parentCallId:'nested',subCallId:id,name:'houdini_inspect',arguments:{code:'hou.frame()'}})
session.append('tool/ptc-dispatch',{rootCallId:'nested',parentCallId:'nested',subCallId:id,name:'houdini_inspect',arguments:{code:'hou.frame()'},isError:false,
  content:[{type:'text',text:JSON.stringify({kind:'dsh-houdini/execution-v1',callId:id,tool:'houdini_inspect',value:{execution:{executor_id:first}}})}]})
assert.equal(projectedExecutorIdentity(ctx,session),first)
assert.equal(recordedExecutorIdentity(session.snapshotEvents()),first)
session.append('tool/call',{turn:1,step:1,callId:'native',name:'houdini_exec',arguments:'{}'})
session.append('tool/result',{turn:1,step:1,message:{role:'tool',source:{kind:'tool',callId:'native'},content:[]},meta:{canonical:{execution:{executor_id:second}}}},{surfaceOp:'append'})
assert.throws(()=>projectedExecutorIdentity(ctx,session),/more than one executor/)
assert.throws(()=>recordedExecutorIdentity(session.snapshotEvents()),/more than one executor/)
console.log('executor identity: shared fold covers native and declared nested facts passed')
const fresh=Session.create('queued-binding')
let injected
const freshAgent={session:fresh,inject:message=>{injected=message;fresh.append('agent/inbox/spliced',{target:'next-step',start:0,inserted:[message]})}}
await new ExecutorBinding(undefined,(_session,message)=>recordHoudiniContext(freshAgent,message)).ensure(fresh,first)
assert(fresh.snapshotEvents().every(event=>event.type!=='user/message'),'unseeded selection must not precede the protected system surface')
assert.equal(recordedExecutorIdentity(fresh.snapshotEvents()),first,'durable pending context is already the selected binding')
fresh.append('user/message',injected,{surfaceOp:'append'})
assert.equal(recordedExecutorIdentity(fresh.snapshotEvents()),first,'consuming the native inbox does not create a second binding')
const delayed=Session.create('delayed-binding')
let queuedMessage
await new ExecutorBinding(undefined,(_session,message)=>{
  queuedMessage=message
  delayed.append('agent/inbox/spliced',{target:'next-step',start:0,inserted:[message]})
}).ensure(delayed,first)
delayed.append('user/message',recoveryMessage({schema:2,kind:'executor_recovery',previous_executor:first,executor_id:second,
  operation_id:'c'.repeat(32),checkpoint_id:'d'.repeat(32),scene_id:'e'.repeat(32),scene_epoch:'f'.repeat(32),
  runtime_id:'1'.repeat(32),hip_path:'C:/fixture/project.hip',restored_nodes:1}),{surfaceOp:'append'})
delayed.append('user/message',queuedMessage,{surfaceOp:'append'})
assert.equal(recordedExecutorIdentity(delayed.snapshotEvents()),second,'late consumption of an already recorded binding cannot undo a verified recovery')
const empty=Session.create('unexecuted-reselection'),pending=[]
const initial=new ExecutorBinding(undefined,(_session,message)=>{
  pending.push(message);empty.append('agent/inbox/spliced',{target:'next-step',start:pending.length-1,inserted:[message]})
})
await initial.ensure(empty,first)
await initial.select(empty,{executor_id:second,runtime_id:'1'.repeat(32),scene_epoch:'2'.repeat(32),scene_id:'3'.repeat(32),
  registration_id:'4'.repeat(32),hip_path:'C:/explicit/project.hip',hip_is_new:false})
assert.equal(recordedExecutorIdentity(empty.snapshotEvents()),second)
for(const message of pending)empty.append('user/message',message,{surfaceOp:'append'})
assert.equal(recordedExecutorIdentity(empty.snapshotEvents()),second)
empty.append('tool/call',{turn:1,step:1,callId:'started',name:'houdini_exec',arguments:'{}'})
await initial.select(empty,{executor_id:first,runtime_id:'1'.repeat(32),scene_epoch:'2'.repeat(32),scene_id:'3'.repeat(32),
  registration_id:'4'.repeat(32),hip_path:'C:/explicit/project.hip',hip_is_new:false})
assert.equal(recordedExecutorIdentity(empty.snapshotEvents()),first,'explicit target selection is allowed after recorded operations')

// Scene identity is not inheritable by file copy. An observation without
// scene_id carries facts only while the HIP path is unchanged; a path change
// must not inherit the previous file's identity and is marked for review.
let pstate=projection.init(),pseq=0
const pfold=(type,data)=>{pstate=projection.apply(pstate,{type,data,seq:++pseq,time:pseq*1000});return pstate}
pfold('user/message',houdiniSnapshot({name:'dsh-houdini:executor-binding',text:'binding\n'
  +JSON.stringify({schema:1,kind:'executor_binding',executor_id:first})}))
const scene='e'.repeat(32)
pfold('user/message',workspaceOpeningMessage({executor_id:first,scene_id:scene,scene_epoch:'f'.repeat(32),
  hip_path:'C:/projects/original.hip',hip_is_new:false}))
assert.equal(pstate.project.sceneId,scene)
assert.equal(pstate.project.needsReview,false)
const observation=(hip,extra)=>{
  const callId='obs-'+pseq
  pfold('tool/call',{turn:1,step:1,callId,name:'houdini_exec',arguments:'{}'})
  pfold('tool/result',{message:{source:{callId}},meta:{canonical:{execution:{
    executor_id:first,hip_path:hip,hip_is_new:false,observed_at:pseq+1,sequence:pseq,...extra}}}})
}
observation('C:/projects/copy.hip')
assert.equal(pstate.project.hipPath,'C:/projects/copy.hip')
assert.equal(pstate.project.sceneId,null,'a HIP path change without scene_id must not inherit the previous identity')
assert.equal(pstate.project.sceneEpoch,null)
assert.equal(pstate.project.needsReview,true,'path without observed identity needs review')
observation('C:/projects/copy.hip')
assert.equal(pstate.project.sceneId,null,'an unchanged path without scene_id still has no identity to inherit')
observation('C:/projects/copy.hip',{scene_recovery:{scene_id:scene,scene_epoch:'f'.repeat(32)}})
assert.equal(pstate.project.sceneId,scene)
assert.equal(pstate.project.needsReview,false)
observation('C:/projects/copy.hip')
assert.equal(pstate.project.sceneId,scene,'facts carry forward while the HIP path is unchanged')
assert.equal(pstate.project.needsReview,false)

// A spliced project message rewritten before consumption is detected exactly
// like a rewritten binding message; the queue never consumes forged facts.
const queued=workspaceOpeningMessage({executor_id:first,scene_id:scene,hip_path:'C:/projects/queued.hip',hip_is_new:false})
const qstate0=projection.init()
let qseq=0
const qfold=(state,type,data)=>projection.apply(state,{type,data,seq:++qseq,time:qseq*1000})
let qstate=qfold(qstate0,'user/message',houdiniSnapshot({name:'dsh-houdini:executor-binding',text:'binding\n'
  +JSON.stringify({schema:1,kind:'executor_binding',executor_id:first})}))
qstate=qfold(qstate,'agent/inbox/spliced',{target:'next-step',start:0,inserted:[queued]})
assert.equal(qstate.project.hipPath,'C:/projects/queued.hip')
const rewritten={...queued,source:{...queued.source,sections:[{name:'dsh-houdini:workspace-open',
  text:'Explicit Open Workspace target.\n'+JSON.stringify({executor_id:first,scene_id:'f'.repeat(32),
    hip_path:'C:/projects/forged.hip',hip_is_new:false})}]}}
qstate=qfold(qstate,'user/message',rewritten)
assert.match(String(qstate.invalid),/project message changed before consumption/)

// A clean consume only releases the queue entry and never re-applies stale
// facts over newer observations.
const clean=workspaceOpeningMessage({executor_id:first,scene_id:scene,hip_path:'C:/projects/clean.hip',hip_is_new:false})
let cstate=projection.init()
let cseq=0
const cfold=(state,type,data)=>projection.apply(state,{type,data,seq:++cseq,time:cseq*1000})
cstate=cfold(cstate,'user/message',houdiniSnapshot({name:'dsh-houdini:executor-binding',text:'binding\n'
  +JSON.stringify({schema:1,kind:'executor_binding',executor_id:first})}))
cstate=cfold(cstate,'agent/inbox/spliced',{target:'next-step',start:0,inserted:[clean]})
assert.equal(cstate.project.hipPath,'C:/projects/clean.hip')
cstate=cfold(cstate,'tool/call',{turn:1,step:1,callId:'late',name:'houdini_exec',arguments:'{}'})
cstate=cfold(cstate,'tool/result',{message:{source:{callId:'late'}},meta:{canonical:{execution:{
  executor_id:first,hip_path:'C:/projects/saved.hip',hip_is_new:false,observed_at:4,sequence:4}}}})
assert.equal(cstate.project.hipPath,'C:/projects/saved.hip')
// The consume event timestamp is newer than the result observation; only the
// early release (never re-folding spliced facts at consume time) keeps it.
cstate=cfold(cstate,'user/message',clean)
assert.equal(cstate.project.hipPath,'C:/projects/saved.hip','consuming queued context must not revert a newer observation')
assert.equal(cstate.invalid,null)
console.log('executor identity: copy identity not inherited, needsReview without observed identity, queued project rewrite detected')

// New choices fence observations by both the selection revision and exact scene.
const selectionSession=Session.create('late-target-results'),select=new ExecutorBinding()
const snapshot=(id,runtime='5'.repeat(32),epoch='6'.repeat(32))=>({executor_id:id,runtime_id:runtime,
  scene_epoch:epoch,scene_id:'7'.repeat(32),registration_id:'8'.repeat(32),hip_path:'C:/selected/asset.hip',hip_is_new:false})
await select.select(selectionSession,snapshot(first))
selectionSession.append('tool/call',{callId:'old-scene',name:'houdini_inspect',arguments:'{}'})
await select.select(selectionSession,snapshot(second))
const selectionSeq=selectionSession.snapshotEvents().at(-1).seq
selectionSession.append('tool/result',{message:{source:{callId:'old-scene'}},meta:{canonical:{execution:{
  executor_id:first,runtime_id:'5'.repeat(32),scene_epoch:'6'.repeat(32),hip_path:'C:/late/wrong.hip',observed_at:Date.now()/1000+100,sequence:100}}}},{surfaceOp:'append'})
assert.equal(foldExecutorState(selectionSession.snapshotEvents()).selectedTarget.executor_id,second)
assert.equal(foldExecutorState(selectionSession.snapshotEvents()).project.hipPath,'C:/selected/asset.hip')
assert.equal(foldExecutorState(selectionSession.snapshotEvents()).recoverySeq,selectionSeq)
selectionSession.append('tool/call',{callId:'new-scene',name:'houdini_inspect',arguments:'{}'})
selectionSession.append('tool/result',{message:{source:{callId:'new-scene'}},meta:{canonical:{execution:{
  executor_id:second,runtime_id:'5'.repeat(32),scene_epoch:'6'.repeat(32),scene_id:'7'.repeat(32),
  hip_path:'C:/selected/renamed.hip',hip_is_new:false,observed_at:Date.now()/1000+101,sequence:101}}}},{surfaceOp:'append'})
assert.equal(foldExecutorState(selectionSession.snapshotEvents()).selectedTarget.hip_path,'C:/selected/renamed.hip','same-scene Save As facts can update the path')
await select.select(selectionSession,null)
selectionSession.append('tool/call',{callId:'after-clear',name:'houdini_inspect',arguments:'{}'})
selectionSession.append('tool/result',{message:{source:{callId:'after-clear'}},meta:{canonical:{execution:{executor_id:second}}}},{surfaceOp:'append'})
assert.equal(foldExecutorState(selectionSession.snapshotEvents()).selectedTarget,null,'receipts never bind a cleared conversation')
console.log('target projection: explicit selection fences old receipts, follows same-scene observations, and clear stays unbound')

const reordered=Session.create('same-scene-reordered-paths'),reorderedBinding=new ExecutorBinding()
await reorderedBinding.select(reordered,{...snapshot(first),workspace_path:'C:/before'})
for(const callId of ['earlier-observation','later-observation'])
  reordered.append('tool/call',{callId,name:'houdini_inspect',arguments:'{}'})
const observedTime=Date.now()/1000+200
const pathResult=(callId,directory,at,sequence)=>reordered.append('tool/result',{
  message:{source:{callId}},meta:{canonical:{ok:true,execution:{executor_id:first,runtime_id:'5'.repeat(32),
    scene_epoch:'6'.repeat(32),scene_id:'7'.repeat(32),hip_path:directory+'/asset.hip',hip_dir:directory,
    hip_is_new:false,observed_at:at,sequence}}}},{surfaceOp:'append'})
pathResult('later-observation','C:/after',observedTime+1,2)
pathResult('earlier-observation','C:/before',observedTime,1)
const reorderedState=foldExecutorState(reordered.snapshotEvents())
assert.equal(reorderedState.project.hipPath,'C:/after/asset.hip')
assert.equal(reorderedState.selectedTarget.hip_path,'C:/after/asset.hip')
assert.equal(reorderedState.selectedTarget.workspace_path,'C:/after','a rejected late observation cannot update the selected directory')
assert.equal(reorderedState.project.target.workspace_path,'C:/after','wire projection consumes the same accepted target snapshot')
console.log('target projection: reordered same-scene receipts keep the accepted HIP and workspace directory together')

// Restoring this scene's old node permissions is metadata inside the current
// tool request, not another target selection or a boundary that retires it.
const permissions=Session.create('ownership-metadata-current-request'),permissionBinding=new ExecutorBinding()
await permissionBinding.select(permissions,snapshot(first))
await permissionBinding.select(permissions,snapshot(second))
const boundary=foldExecutorState(permissions.snapshotEvents()).recoverySeq
permissions.append('tool/call',{callId:'first-write-after-reopen',name:'houdini_exec',arguments:'{}'})
const ownership=recoveryMessage({schema:2,kind:'executor_recovery',previous_executor:first,executor_id:second,
  operation_id:'9'.repeat(32),checkpoint_id:'a'.repeat(32),scene_id:'7'.repeat(32),scene_epoch:'6'.repeat(32),
  runtime_id:'5'.repeat(32),hip_path:'C:/selected/asset.hip',restored_nodes:2})
permissions.append('agent/inbox/spliced',{target:'next-step',start:0,inserted:[ownership]})
assert.equal(foldExecutorState(permissions.snapshotEvents()).recovery.operation_id,'9'.repeat(32))
assert.equal(foldExecutorState(permissions.snapshotEvents()).recoverySeq,boundary)
assert.deepEqual(executionHistory(permissions.snapshotEvents()).pendingCalls,['first-write-after-reopen'])
const requestRef='5'.repeat(32)+'.'+'b'.repeat(32)
permissions.append('tool/result',{message:{source:{callId:'first-write-after-reopen'}},meta:{canonical:{ok:false,
  requestReceipt:{request_ref:requestRef,runtime_id:'5'.repeat(32),executor_id:second,scene_epoch:'6'.repeat(32),
    status:'unknown_transport'}}}},{surfaceOp:'append'})
assert.deepEqual(executionHistory(permissions.snapshotEvents()).activeRequests,[[requestRef,'unknown_transport']])
assert.equal(executionHistory(permissions.snapshotEvents()).unresolvedCalls[0].callId,'first-write-after-reopen')
permissions.append('user/message',ownership,{surfaceOp:'append'})
assert.equal(foldExecutorState(permissions.snapshotEvents()).recoverySeq,boundary,'queue consumption does not create a new target boundary')
assert.deepEqual(executionHistory(permissions.snapshotEvents()).activeRequests,[[requestRef,'unknown_transport']])
const legacyQueued=projection.apply(projection.init(),{type:'agent/inbox/spliced',seq:10,
  data:{target:'next-step',start:0,inserted:[ownership]}})
assert(legacyQueued.invalid,'legacy cross-target ownership recovery still requires a committed transition')
console.log('same-target ownership metadata preserves the in-flight request and unknown outcome through native queue consumption')

// DSH records the first tool call before its resolver chooses the sole scene.
// It is the one case where an unbound pending call belongs to the new choice.
for(const unknown of [false,true]) {
  const firstUse=Session.create('first-use-'+unknown),firstBinding=new ExecutorBinding(),callId='first-call'
  firstUse.append('tool/call',{callId,name:'houdini_exec',arguments:'{}'})
  assert.equal(foldExecutorState(firstUse.snapshotEvents()).pending[callId],null)
  await firstBinding.select(firstUse,snapshot(first))
  let firstState=foldExecutorState(firstUse.snapshotEvents())
  assert.equal(firstState.pending[callId],first)
  assert.equal(firstState.pendingSelections[callId],firstState.selectionRevision)
  const ref='5'.repeat(32)+'.'+'c'.repeat(32)
  const execution={executor_id:first,runtime_id:'5'.repeat(32),scene_epoch:'6'.repeat(32),scene_id:'7'.repeat(32),
    hip_path:'C:/selected/first-result.hip',hip_is_new:false,sequence:1,observed_at:Date.now()/1000+200}
  firstUse.append('tool/result',{message:{source:{callId}},meta:{canonical:unknown
    ?{ok:false,requestReceipt:{request_ref:ref,runtime_id:'5'.repeat(32),executor_id:first,scene_epoch:'6'.repeat(32),status:'unknown_transport'}}
    :{ok:true,execution,requestReceipt:{request_ref:ref,runtime_id:'5'.repeat(32),executor_id:first,scene_epoch:'6'.repeat(32),status:'done'}}}},
    {surfaceOp:'append'})
  firstState=foldExecutorState(firstUse.snapshotEvents())
  const current=executionHistory(firstUse.snapshotEvents())
  assert(current.calls.has(callId),'the first choice must retain its already-recorded tool call')
  if(unknown) {
    assert.deepEqual(current.activeRequests,[[ref,'unknown_transport']])
    assert.equal(current.unresolvedCalls[0].callId,callId)
  } else {
    assert.equal(firstState.project.hipPath,execution.hip_path,'the first actual result is a current observation')
    assert.equal(current.anchor.execution.hip_path,execution.hip_path)
  }
}
console.log('first-use selection adopts only genuinely unbound pending calls and preserves their actual or unknown results')
const afterClear=Session.create('cleared-call-must-not-follow'),afterClearBinding=new ExecutorBinding()
await afterClearBinding.select(afterClear,snapshot(first))
await afterClearBinding.select(afterClear,null)
afterClear.append('tool/call',{callId:'issued-while-cleared',name:'houdini_inspect',arguments:'{}'})
await afterClearBinding.select(afterClear,snapshot(second))
assert.equal(foldExecutorState(afterClear.snapshotEvents()).pending['issued-while-cleared'],null)
afterClear.append('tool/result',{message:{source:{callId:'issued-while-cleared'}},meta:{canonical:{ok:true,execution:{
  executor_id:second,runtime_id:'5'.repeat(32),scene_epoch:'6'.repeat(32),scene_id:'7'.repeat(32),
  hip_path:'C:/unbound-call-must-not-follow.hip',hip_is_new:false,sequence:1,observed_at:Date.now()/1000+300}}}},
  {surfaceOp:'append'})
assert.equal(foldExecutorState(afterClear.snapshotEvents()).project.hipPath,'C:/selected/asset.hip')
assert.equal(executionHistory(afterClear.snapshotEvents()).calls.has('issued-while-cleared'),false,
  'an explicit clear and later reselect keep the target-change boundary')
