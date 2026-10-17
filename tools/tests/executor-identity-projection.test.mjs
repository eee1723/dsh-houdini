import assert from 'node:assert/strict'
import {Context} from '@deepseek-ai/cordis'
import {Session} from '@deepseek-ai/dsh-session'
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection'
import {ExecutorBinding,recordedExecutorIdentity} from '../../lib/executor-binding.js'
import {houdiniSnapshot,recordHoudiniContext,workspaceOpeningMessage} from '../../lib/dsh-adapter.js'
import {recoveryMessage} from '../../lib/scene-recovery.js'
import {executorIdentityProjection as projection,projectedExecutorBindingState,projectedExecutorIdentity,registerExecutorIdentityProjection}
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
await initial.reselectUnexecuted(empty,second)
assert.equal(recordedExecutorIdentity(empty.snapshotEvents()),second)
for(const message of pending)empty.append('user/message',message,{surfaceOp:'append'})
assert.equal(recordedExecutorIdentity(empty.snapshotEvents()),second)
empty.append('tool/call',{turn:1,step:1,callId:'started',name:'houdini_exec',arguments:'{}'})
await assert.rejects(initial.reselectUnexecuted(empty,first),/已有现场操作/)

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
