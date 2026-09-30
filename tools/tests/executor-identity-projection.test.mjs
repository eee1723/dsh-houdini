import assert from 'node:assert/strict'
import {Context} from '@deepseek-ai/cordis'
import {Session} from '@deepseek-ai/dsh-session'
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection'
import {ExecutorBinding,recordedExecutorIdentity} from '../../lib/executor-binding.js'
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
