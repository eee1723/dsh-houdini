import assert from 'node:assert/strict'
import {Session} from '@deepseek-ai/dsh-session'
import {HoudiniBridge} from '../../lib/bridge.js'
import {ExecutorBinding,recordedExecutorIdentity} from '../../lib/executor-binding.js'
import {foldExecutorState} from '../../lib/executor-identity-projection.js'
import {installSceneRecovery,recoveryMessage} from '../../lib/scene-recovery.js'
import {projectExecutionNotice} from '../../lib/execution-state.js'
const a='a'.repeat(32),b='b'.repeat(32),c='c'.repeat(32),d='d'.repeat(32),e='e'.repeat(32)
class Bridge extends HoudiniBridge {
  constructor(){super('http://127.0.0.1:1',100,b)}
  requests=[]
  wrong=false
  activationFailure=false
  needsReload=false
  dirty=false
  connected=false
  async recover(action,input){
    this.requests.push({action,input})
    if(action==='activate'){
      if(this.activationFailure){this.activationFailure=false;throw new Error('lost activation response')}
      this.connected=true
      return {ok:true,status:'active',operation_id:input.operation_id,executor_id:b,checkpoint_id:c}
    }
    const common={executor_id:this.wrong?c:b,checkpoint_id:c,scene_id:d,scene_epoch:e,runtime_id:e,
      hip_path:'C:/fixture/project.hip',requires_reload:this.needsReload,dirty_reliable:true,dirty:this.dirty,restored_nodes:2}
    return action==='assess'?{...common,status:this.connected?'connected':'ready'}:{...common,status:'prepared',operation_id:input.operation_id}
  }
}
function fixture(answerer){
  let durable=true,flushes=0,service,questions=0
  const connection=new Bridge(),session=Session.create('recovery-task'),agent={id:session.id,session,status:'idle'}
  installSceneRecovery({provide:(name,value)=>{assert.equal(name,'houdiniRecovery');service=value},
    get:name=>name==='userQuestions'?{ask:async input=>{questions++;return answerer?.(input)??{answers:[]}}}:undefined,
    sessions:{flush:async()=>{flushes++;return durable}}},connection)
  return {connection,session,agent,get service(){return service},get questions(){return questions},get flushes(){return flushes},set durable(value){durable=value}}
}
const signal=new AbortController().signal
const f=fixture()
await new ExecutorBinding().ensure(f.session,a)
f.session.append('tool/call',{callId:'unfinished',name:'houdini_exec'})
assert(projectExecutionNotice(f.session.snapshotEvents()).pending_calls)
const assessment=await f.service.assess(f.agent,signal)
assert.equal(f.connection.requests.length,1,'assessment must not prepare or activate')
f.durable=false
await assert.rejects(f.service.restore(f.agent,assessment.assessment_id,signal),/可靠保存/)
assert.equal(f.connection.requests.filter(x=>x.action==='activate').length,0,'flush failure grants no authority')
assert.equal(recordedExecutorIdentity(f.session.snapshotEvents()),b)
await assert.rejects(f.service.ensure(f.agent,signal),/可靠保存/)
f.durable=true
f.connection.activationFailure=true
await assert.rejects(f.service.restore(f.agent,assessment.assessment_id,signal),/lost activation/)
await f.service.restore(f.agent,assessment.assessment_id,signal)
assert.equal(f.connection.requests.filter(x=>x.action==='prepare').length,1,'retry must not repeat preparation')
const events=f.session.snapshotEvents()
assert.equal(events.filter(x=>x.type==='user/message').length,2,'one initial binding and one transition')
assert.equal(projectExecutionNotice(events),null,'old requests are retained in history, not polled on the new runtime')
assert.equal(foldExecutorState(events).recovery.previous_work.pending_calls,1)
// A late old result is attributed to its old call, not a second current executor.
f.session.append('tool/result',{message:{source:{callId:'unfinished'}},meta:{canonical:{execution:{executor_id:a}}}},{surfaceOp:'append'})
assert.equal(recordedExecutorIdentity(f.session.snapshotEvents()),b)
f.session.append('tool/call',{callId:'new',name:'houdini_exec'})
f.session.append('tool/result',{message:{source:{callId:'new'}},meta:{canonical:{execution:{executor_id:a}}}},{surfaceOp:'append'})
assert.throws(()=>recordedExecutorIdentity(f.session.snapshotEvents()),/more than one executor/)
// Browser prose cannot manufacture a recovery transition.
const bad=fixture();await new ExecutorBinding().ensure(bad.session,a)
const value={schema:2,kind:'executor_recovery',previous_executor:a,executor_id:b,operation_id:d,
  checkpoint_id:c,scene_id:d,scene_epoch:e,runtime_id:e,hip_path:'C:/x.hip',restored_nodes:1}
bad.session.append('user/message',{...recoveryMessage(value),source:{kind:'user'}},{surfaceOp:'append'})
assert.equal(recordedExecutorIdentity(bad.session.snapshotEvents()),a)
bad.session.append('user/message',recoveryMessage({...value,previous_executor:c}),{surfaceOp:'append'})
assert.throws(()=>foldExecutorState(bad.session.snapshotEvents()),/Invalid Houdini recovery transition/)
// A wrong Bridge reply must not append a binding or activate anything.
const wrong=fixture();await new ExecutorBinding().ensure(wrong.session,a)
const plan=await wrong.service.assess(wrong.agent,signal);wrong.connection.wrong=true
await assert.rejects(wrong.service.restore(wrong.agent,plan.assessment_id,signal),/身份不匹配/)
assert.equal(recordedExecutorIdentity(wrong.session.snapshotEvents()),a)
assert.equal(wrong.connection.requests.filter(x=>x.action==='activate').length,0)
wrong.agent.status='running'
await assert.rejects(wrong.service.restore(wrong.agent,plan.assessment_id,signal),/模型步骤边界/)
// A normal running user turn automatically reconciles, without any UI action or question.
const automatic=fixture();await new ExecutorBinding().ensure(automatic.session,a);automatic.agent.status='running'
await automatic.service.beforeStep(automatic.agent,signal)
assert.equal(recordedExecutorIdentity(automatic.session.snapshotEvents()),b)
assert.equal(automatic.questions,0)
assert.deepEqual(automatic.connection.requests.map(r=>r.action),['assess','prepare','activate'])
await automatic.service.beforeStep(automatic.agent,signal)
assert.equal(automatic.connection.requests.filter(r=>r.action==='prepare').length,1)
// Clean lazy startup can reload automatically; dirty content requires a real conversation choice.
const clean=fixture();await new ExecutorBinding().ensure(clean.session,a);clean.connection.needsReload=true
await clean.service.beforeStep(clean.agent,signal)
assert.equal(clean.questions,0);assert.equal(clean.connection.requests.find(r=>r.action==='prepare').input.reload_saved,true)
for(const answer of ['keep','custom','discard']) {
 const dirty=fixture(input=>({answers:[{id:input.questions[0].id,selected:answer==='discard'?['放弃未保存修改，从保存点继续']:[],
   ...(answer==='custom'?{custom:'已确认恢复成功'}:{})}]}))
 await new ExecutorBinding().ensure(dirty.session,a);dirty.connection.needsReload=true;dirty.connection.dirty=true
 if(answer==='discard') {
  await dirty.service.beforeStep(dirty.agent,signal)
  assert.equal(dirty.connection.requests.find(r=>r.action==='prepare').input.expected.discard_unsaved,true)
  assert.equal(foldExecutorState(dirty.session.snapshotEvents()).recovery.user_choice.selected,'放弃未保存修改，从保存点继续')
 } else {
  await assert.rejects(dirty.service.beforeStep(dirty.agent,signal),/已保留/)
  assert.equal(dirty.connection.requests.filter(r=>r.action==='prepare').length,0)
  assert.equal(recordedExecutorIdentity(dirty.session.snapshotEvents()),a)
 }
 assert.equal(dirty.questions,1)
}
console.log('scene recovery: durable transition, retries, late receipts, forged source, wrong target and idle boundary passed')
