import assert from 'node:assert/strict'
import {Context} from '@deepseek-ai/cordis'
import {Session} from '@deepseek-ai/dsh-session'
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection'
import {ExecutorBinding,recordedExecutorIdentity} from '../../lib/executor-binding.js'
import {recordHoudiniContext} from '../../lib/dsh-adapter.js'
import {recoveryMessage} from '../../lib/scene-recovery.js'
import {projectedExecutorBindingState,projectedExecutorIdentity,registerExecutorIdentityProjection}
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
