import assert from 'node:assert/strict'
import {Context} from '@deepseek-ai/cordis'
import {Session} from '@deepseek-ai/dsh-session'
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection'
import {ExecutorBindingBarrier,recordedExecutorIdentity} from '../../lib/executor-binding.js'
import {executorIdentityProjection,projectedExecutorBindingState,projectedExecutorIdentity,registerExecutorIdentityProjection}
  from '../../lib/executor-identity-projection.js'

const first='a'.repeat(32), second='b'.repeat(32)
const binding=id=>({type:'user/message',data:{source:{kind:'plugin',plugin:'dsh-houdini',
  sections:[{name:'dsh-houdini:executor-binding',text:'binding\n'+JSON.stringify({schema:1,kind:'executor_binding',executor_id:id})}]}}})
const call=(callId,name='houdini_exec',args={})=>({type:'tool/call',data:{callId,name,args}})
const result=(callId,id)=>({type:'tool/result',data:{message:{source:{callId}},
  meta:{canonical:{execution:{executor_id:id}}}}})
const malformed={type:'user/message',data:{source:{kind:'plugin',plugin:'dsh-houdini',
  sections:[{name:'dsh-houdini:executor-binding',text:'binding\n{broken'}]}}}

function oldOutcome(events) {
  try {return {identity:recordedExecutorIdentity(events)}}
  catch(error) {return {error:error.message}}
}
function projectedOutcome(events) {
  let state=executorIdentityProjection.init({},0)
  for(const event of events)state=executorIdentityProjection.apply(state,event)
  if(state.invalid)return {error:state.invalid}
  if(state.conflict)return {error:'Houdini task requires recovery: history contains more than one recorded executor identity. No live request sent. Cross-process recovery is not implemented: read retained results, preserve the saved/crash HIP and reconcile the project before any future recovery flow; do not start a new task to bypass this check or infer ownership from the HIP path.'}
  return {identity:state.identity??undefined}
}
const cases=[
  [],[binding(first)],[call('one'),result('one',first)],
  [call('one'),result('one',first),result('one',second)],
  [call('one'),call('one','houdini_query',{result_ref:'receipt'}),result('one',first)],
  [call('one','houdini_query',{source_ref:'source'}),result('one',first)],
  [call('one'),result('one',first),call('one'),result('one',second)],
  [binding(first),call('one'),result('one',first)],
  [binding(first),call('one'),result('one',second)],
  [binding(first),binding(second)],[call('one'),result('one','invalid')],
  [malformed],
]
for(const [index,events] of cases.entries())
  assert.deepEqual(projectedOutcome(events),oldOutcome(events),`identity history parity case ${index}`)
assert.equal(executorIdentityProjection.apply(executorIdentityProjection.init(),binding(first)).bindingRecorded,true)
let resultOnly=executorIdentityProjection.init()
for(const event of [call('one'),result('one',first)])resultOnly=executorIdentityProjection.apply(resultOnly,event)
assert.equal(resultOnly.bindingRecorded,false,'a tool result is identity evidence, not a binding record')

const ctx=new Context()
new SessionProjectionRegistry(ctx)
assert.throws(()=>projectedExecutorIdentity(ctx,Session.create('missing-key')),/projection unavailable/)
registerExecutorIdentityProjection(ctx)
const session=Session.create('identity-projection')
assert.equal(projectedExecutorIdentity(ctx,session),undefined)
session.append('tool/call',{turn:1,step:1,callId:'one',name:'houdini_exec',arguments:'{}'})
session.append('tool/result',{turn:1,step:1,message:{source:{callId:'one'}},
  meta:{canonical:{execution:{executor_id:first}}}},{surfaceOp:'append'})
assert.equal(projectedExecutorIdentity(ctx,session),first)
assert.equal(recordedExecutorIdentity(session.snapshotEvents()),first)
assert.equal(projectedExecutorBindingState(ctx,session).bindingRecorded,false)
const fresh=Session.create('projection-barrier'),barrier=new ExecutorBindingBarrier(async()=>true,
  current=>projectedExecutorBindingState(ctx,current))
await barrier.ensure(fresh,first)
assert.deepEqual(projectedExecutorBindingState(ctx,fresh),{identity:first,bindingRecorded:true})
assert.equal(fresh.snapshotEvents().filter(e=>e.type==='user/message').length,1)
await barrier.ensure(fresh,first)
assert.equal(fresh.snapshotEvents().filter(e=>e.type==='user/message').length,1)
await assert.rejects(barrier.ensure(fresh,second),/requires recovery/)
const noHistory={snapshotEvents(){throw new Error('full history read')},append(){throw new Error('unexpected append')}}
await new ExecutorBindingBarrier(async()=>true,()=>projectedExecutorBindingState(ctx,fresh)).ensure(noHistory,first)
const retry=Session.create('projection-flush-retry')
let flushes=0
const flaky=new ExecutorBindingBarrier(async()=>++flushes>1,
  current=>projectedExecutorBindingState(ctx,current))
await assert.rejects(flaky.ensure(retry,first),/no durable session backend/)
await flaky.ensure(retry,first)
assert.equal(flushes,2)
assert.equal(retry.snapshotEvents().filter(e=>e.type==='user/message').length,1)
fresh.append('tool/call',{turn:1,step:1,callId:'other',name:'houdini_exec',arguments:'{}'})
fresh.append('tool/result',{turn:1,step:1,message:{source:{callId:'other'}},
  meta:{canonical:{execution:{executor_id:second}}}},{surfaceOp:'append'})
await assert.rejects(barrier.ensure(fresh,first),/more than one recorded executor identity/)
console.log('executor identity projection: historical parity and registry materialization passed')
