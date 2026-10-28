import {foldExecutorBinding} from '../../lib/executor-identity-projection.js'
import {fixtureProjectionContext} from './fixture-session.mjs'
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
      hip_path:'C:/fixture/project.hip',requires_reload:this.needsReload,dirty_reliable:true,dirty:this.dirty,owned_nodes:2,restored_nodes:2}
    return action==='assess'?{...common,status:this.assessmentStatus??(this.connected?'connected':'ready')}:{...common,status:'prepared',operation_id:input.operation_id}
  }
}
function fixture(answerer){
  let durable=true,flushes=0,service,questions=0,duringFlush
  const connection=new Bridge(),session=Session.create('recovery-task'),agent={id:session.id,session,status:'idle',inject:message=>session.append('agent/inbox/spliced',{target:'next-step',start:0,inserted:[message]})}
  installSceneRecovery(fixtureProjectionContext({provide:(name,value)=>{assert.equal(name,'houdiniRecovery');service=value},
    get:name=>name==='userQuestions'?{ask:async input=>{questions++;return answerer?.(input)??{answers:[]}}}:undefined,
    sessions:{flush:async()=>{flushes++;await duringFlush?.();return durable}}}),connection)
  return {connection,session,agent,get service(){return service},get questions(){return questions},get flushes(){return flushes},set durable(value){durable=value},set duringFlush(value){duringFlush=value}}
}
const signal=new AbortController().signal
const f=fixture()
await new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents())).ensure(f.session,a)
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
const bad=fixture();await new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents())).ensure(bad.session,a)
const value={schema:2,kind:'executor_recovery',previous_executor:a,executor_id:b,operation_id:d,
  checkpoint_id:c,scene_id:d,scene_epoch:e,runtime_id:e,hip_path:'C:/x.hip',restored_nodes:1}
bad.session.append('user/message',{...recoveryMessage(value),source:{kind:'user'}},{surfaceOp:'append'})
assert.equal(recordedExecutorIdentity(bad.session.snapshotEvents()),a)
bad.session.append('user/message',recoveryMessage({...value,previous_executor:c}),{surfaceOp:'append'})
assert.throws(()=>foldExecutorState(bad.session.snapshotEvents()),/Invalid Houdini recovery transition/)
// A wrong Bridge reply must not append a binding or activate anything.
const wrong=fixture();await new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents())).ensure(wrong.session,a)
const plan=await wrong.service.assess(wrong.agent,signal);wrong.connection.wrong=true
await assert.rejects(wrong.service.restore(wrong.agent,plan.assessment_id,signal),/身份不匹配/)
assert.equal(recordedExecutorIdentity(wrong.session.snapshotEvents()),a)
assert.equal(wrong.connection.requests.filter(x=>x.action==='activate').length,0)
wrong.agent.status='running'
await assert.rejects(wrong.service.restore(wrong.agent,plan.assessment_id,signal),/模型步骤边界/)
// Selecting or inspecting a target never restores ownership. Only a write to
// the exact previously saved scene can restore original nodes without reload.
async function selectedFixture({scene=d,reload=false,dirty=false,checkpoint=c,collector}={}) {
  const value=fixture();await new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents())).ensure(value.session,a)
  const execution={ok:true,execution:{
    executor_id:a,runtime_id:a,sequence:1,observed_at:1,owner_session:value.agent.id,read_only:false,
    hip_path:'C:/fixture/project.hip',scene_recovery:{scene_id:d,scene_epoch:a,checkpoint_id:checkpoint}}}
  if(collector) {
    const actual={...execution,jobId:'a'.repeat(12),status:'done',requestReceipt:{jobId:'a'.repeat(12),
      request_ref:a+'.'+'8'.repeat(32),runtime_id:a,executor_id:a,scene_epoch:a,status:'done',job_finished:true,job_result_available:true}}
    const tool=collector==='request-job'?'houdini_request':'job_output'
    const canonical=collector==='request-job'?actual:{job:{id:'native-saved-job',kind:'houdini-live'},
      text:JSON.stringify({kind:'dsh-houdini/live-job-result-v1',job_id:'native-saved-job',value:actual})}
    if(collector==='nested-job') {
      value.session.append('tool/ptc-dispatch-start',{subCallId:'saved',name:tool})
      value.session.append('tool/ptc-dispatch',{subCallId:'saved',name:tool,content:[{type:'text',text:JSON.stringify({
        kind:'dsh-houdini/execution-v1',callId:'saved',tool,value:canonical})}]})
    } else {
      value.session.append('tool/call',{callId:'saved',name:tool})
      value.session.append('tool/result',{message:{source:{callId:'saved'}},meta:{canonical}},{surfaceOp:'append'})
    }
  } else {
    value.session.append('tool/call',{callId:'saved',name:'houdini_exec'})
    value.session.append('tool/result',{message:{source:{callId:'saved'}},meta:{canonical:execution}},{surfaceOp:'append'})
  }
  await new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents())).select(value.session,{executor_id:b,runtime_id:e,scene_epoch:e,scene_id:scene,
    registration_id:b,hip_path:'C:/fixture/project.hip',hip_is_new:false})
  value.connection.needsReload=reload;value.connection.dirty=dirty;value.agent.status='running'
  return value
}
const direct=await selectedFixture()
await direct.service.beforeWrite(direct.agent,signal)
assert.deepEqual(direct.connection.requests.map(r=>r.action),['assess','prepare','activate'],'an explicit same-scene selection restores original ownership before its first write without needing a fresh read')
for(const collector of ['native-job','nested-job','request-job']) {
  const collected=await selectedFixture({collector})
  await collected.service.beforeWrite(collected.agent,signal)
  assert.deepEqual(collected.connection.requests.map(r=>r.action),['assess','prepare','activate'],
    collector+': original completed Bridge jobs retain their same-scene recovery provenance')
}
// The current tool protocol stays contiguous while ownership facts enter the
// durable native inbox. They are context, never a new user body in that pair.
const queued=await selectedFixture()
queued.session.append('tool/call',{callId:'current-write',name:'houdini_exec'})
const beforeQueue=queued.session.snapshotEvents().length
await queued.service.beforeWrite(queued.agent,signal)
const queuedEvents=queued.session.snapshotEvents().slice(beforeQueue)
assert.equal(queuedEvents.filter(event=>event.type==='user/message').length,0)
const metadata=queuedEvents.find(event=>event.type==='agent/inbox/spliced')?.data.inserted[0]
assert(metadata?.source.sections.some(section=>section.name==='dsh-houdini:executor-binding'))
assert(foldExecutorState(queued.session.snapshotEvents()).recovery,'native splice immediately supplies the single persisted recovery fact')
assert.equal(foldExecutorState(queued.session.snapshotEvents()).recovery.previous_work,undefined,'ownership metadata must not mislabel the current tool call as retired work')
// Transient checkpoint readiness must not disable restoration for this epoch.
const pending=await selectedFixture();pending.connection.assessmentStatus='unavailable'
await pending.service.beforeWrite(pending.agent,signal)
assert.deepEqual(pending.connection.requests.map(r=>r.action),['assess'])
pending.connection.assessmentStatus='ready'
await pending.service.beforeWrite(pending.agent,signal)
await pending.service.beforeWrite(pending.agent,signal)
assert.equal(pending.connection.requests.filter(r=>r.action==='assess').length,2,'the same target retries after pending material settles')
assert.equal(pending.connection.requests.filter(r=>r.action==='prepare').length,1,'successful retry does not repeat preparation')
const flushRetry=await selectedFixture();flushRetry.durable=false
await flushRetry.service.beforeWrite(flushRetry.agent,signal)
assert.equal(flushRetry.connection.requests.filter(r=>r.action==='activate').length,0,'queued facts grant no authority before durable flush')
flushRetry.durable=true
await flushRetry.service.beforeWrite(flushRetry.agent,signal)
assert.equal(flushRetry.connection.requests.filter(r=>r.action==='assess').length,1)
assert.equal(flushRetry.connection.requests.filter(r=>r.action==='prepare').length,1,'durability retry uses the same persisted operation')
assert.equal(flushRetry.connection.requests.filter(r=>r.action==='activate').length,1)
// A distinct user choice made while an explicit idle restoration flushes is
// not overwritten by the old activation transaction.
const choiceDuringFlush=await selectedFixture();choiceDuringFlush.agent.status='idle'
const beforeChoice=await choiceDuringFlush.service.assess(choiceDuringFlush.agent,signal)
choiceDuringFlush.duringFlush=async()=>{
  choiceDuringFlush.duringFlush=undefined
  await new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents())).select(choiceDuringFlush.session,null,signal)
}
await assert.rejects(choiceDuringFlush.service.restore(choiceDuringFlush.agent,beforeChoice.assessment_id,signal),/工程选择已变化/)
assert.equal(choiceDuringFlush.connection.requests.filter(r=>r.action==='activate').length,0)
assert.equal(foldExecutorState(choiceDuringFlush.session.snapshotEvents()).selectedTarget,null)
const automatic=await selectedFixture()
assert.equal(automatic.service.beforeStep,undefined,'ordinary steps have no restoration hook')
assert.equal(automatic.service.beforeTool,undefined,'read tools have no restoration hook')
assert.equal(automatic.connection.requests.length,0,'selection does not contact recovery')
// A fresh current read must not erase the old task's provenance.
automatic.session.append('tool/call',{callId:'read-current',name:'houdini_inspect'})
automatic.session.append('tool/result',{message:{source:{callId:'read-current'}},meta:{canonical:{ok:true,execution:{
  executor_id:b,runtime_id:e,sequence:1,observed_at:2,owner_session:automatic.agent.id,read_only:true,
  hip_path:'C:/fixture/project.hip',scene_recovery:{scene_id:d,scene_epoch:e,checkpoint_id:c}}}}},{surfaceOp:'append'})
await automatic.service.beforeWrite(automatic.agent,signal)
assert.deepEqual(automatic.connection.requests.map(r=>r.action),['assess','prepare','activate'])
assert.equal(automatic.questions,0)
assert.equal(automatic.connection.requests[1].input.reload_saved,false)
await automatic.service.beforeWrite(automatic.agent,signal)
assert.equal(automatic.connection.requests.filter(r=>r.action==='assess').length,1,'same-epoch retries do not hash the HIP again')
assert.equal(automatic.connection.requests.filter(r=>r.action==='prepare').length,1,'same mapping is activated idempotently')
const different=await selectedFixture({scene:c})
await different.service.beforeWrite(different.agent,signal)
assert.equal(different.connection.requests.length,0,'an explicitly selected new project needs no old checkpoint')
for(const dirty of [false,true]) {
  const reload=await selectedFixture({reload:true,dirty})
  await reload.service.beforeWrite(reload.agent,signal)
  await reload.service.beforeWrite(reload.agent,signal)
  assert.deepEqual(reload.connection.requests.map(r=>r.action),['assess'],'unverified load evidence is not auto-reloaded or repeatedly hashed')
  assert.equal(reload.questions,0,'write preflight does not ask to discard user content')
}
const changed=await selectedFixture({checkpoint:a})
await changed.service.beforeWrite(changed.agent,signal)
assert.deepEqual(changed.connection.requests.map(r=>r.action),['assess'],'different checkpoint never restores old ownership')
console.log('scene recovery: explicit durable restore and exact same-scene write-only ownership recovery passed')
