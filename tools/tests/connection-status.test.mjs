import assert from 'node:assert/strict'
import {Session} from '@deepseek-ai/dsh-session'
import {createUserMessage} from '@deepseek-ai/dsh-llm'
import {HoudiniBridge} from '../../lib/bridge.js'
import {ExecutorBinding,installExecutorBinding} from '../../lib/executor-binding.js'
import {installSceneRecovery,recoveryMessage} from '../../lib/scene-recovery.js'
import {lastRecoveryNotice} from '../../lib/connection-status.js'

const first='a'.repeat(32),second='b'.repeat(32),checkpoint='c'.repeat(32),scene='d'.repeat(32),epoch='e'.repeat(32)
const signal=new AbortController().signal
const session=Session.create('connection-task')
await new ExecutorBinding().ensure(session,first)
const agent={id:session.id,session,status:'idle',ctx:{get:()=>service}}
let service
const requests=[]
class Bridge extends HoudiniBridge {
  constructor(){super('http://127.0.0.1:1',100,second)}
  replyId=second
  replyStatus='ready'
  async inspectExecutor(){return {executorId:second}}
  async recover(action,input){
    requests.push({action,input})
    return {status:action==='prepare'?'prepared':action==='activate'?'active':this.replyStatus,
      executor_id:this.replyId,runtime_id:second,scene_id:scene,scene_epoch:epoch,checkpoint_id:checkpoint,
      operation_id:input.operation_id,hip_path:'E:/fixture/original.hip',restored_nodes:1,requires_reload:false}
  }
}
const bridge=new Bridge()
installSceneRecovery({provide:(_key,value)=>service=value,get:()=>undefined,sessions:{flush:async()=>true}},bridge)
const prior=session.snapshotEvents().length
assert.equal((await service.inspect(agent,signal)).status,'ready')
assert.deepEqual(requests.map(row=>row.action),['assess'])
assert.equal(session.snapshotEvents().length,prior,'inspection never appends or prepares a recovery')
bridge.replyId=first
assert.equal((await service.inspect(agent,signal)).status,'unavailable','a changed executor after health cannot appear connected')
bridge.replyId=second;bridge.replyStatus='connected'
assert.equal((await service.inspect(agent,signal)).status,'unavailable','Bridge connected does not replace the persisted task binding')
bridge.replyStatus='ready'
const plan=await service.assess(agent,signal)
await service.inspect(agent,signal)
await service.restore(agent,plan.assessment_id,signal)
assert.equal(requests.filter(row=>row.action==='prepare').length,1,'inspection cannot replace the model step recovery plan')

const stale=Session.create('old-task')
await new ExecutorBinding().ensure(stale,first)
let hook,failure='恢复材料缺失，当前修改保留。'
const recovering={beforeStep:async()=>{if(failure)throw Error(failure)}}
installExecutorBinding({on:(_name,callback)=>hook=callback,get:()=>recovering},second)
const payload={agent:{session:stale},signal}
const user=createUserMessage({content:[{type:'text',text:'继续'}],source:{kind:'user'}})
async function step(messages){const value=await hook({...payload,messages},async()=>({kind:'enter',messages}));
  for(const message of value.messages)stale.append('user/message',message,{surfaceOp:'append'});return value}
await step([user])
assert.equal(lastRecoveryNotice(stale.snapshotEvents(),second).reason,failure)
await assert.rejects(new ExecutorBinding().ensure(stale,second),new RegExp(failure))
await step([])
assert.equal(lastRecoveryNotice(stale.snapshotEvents(),second).reason,failure,'model continuation must not replace the cause with a generic binding error')
stale.append('user/message',recoveryMessage({schema:2,kind:'executor_recovery',previous_executor:first,
  executor_id:second,operation_id:first,checkpoint_id:checkpoint,scene_id:scene,scene_epoch:epoch,runtime_id:second,
  hip_path:'E:/fixture/original.hip',restored_nodes:1}),{surfaceOp:'append'})
failure=null
await step([user])
assert.equal(lastRecoveryNotice(stale.snapshotEvents(),second),null)
failure='恢复材料缺失，当前修改保留。'
await step([user])
assert.equal(lastRecoveryNotice(stale.snapshotEvents(),second).reason,failure,'the same failure after success must be published again')
await step([])
assert.equal(lastRecoveryNotice(stale.snapshotEvents(),second).reason,failure,'same-process model continuation cannot clear an unresolved scene failure')
assert.equal(lastRecoveryNotice(stale.snapshotEvents(),first),null,'a different target cannot borrow the failure reason')
const beforeAbort=stale.snapshotEvents().length
await assert.rejects(hook({...payload,signal:AbortSignal.abort()},async()=>({kind:'enter',messages:[user]})),/abort/i)
assert.equal(stale.snapshotEvents().length,beforeAbort)
console.log('connection diagnostics: read-only inspection, plan isolation, identity checks, preserved cause, recovery-clear-recurrence and abort passed')
