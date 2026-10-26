import {foldExecutorBinding} from '../../lib/executor-identity-projection.js'
import {fixtureProjectionContext} from './fixture-session.mjs'
import assert from 'node:assert/strict'
import path from 'node:path'
import {Session} from '@deepseek-ai/dsh-session'
import {ExecutorBinding,recordedExecutorIdentity} from '../../lib/executor-binding.js'
import {ExecutorRouter} from '../../lib/executor-routing.js'
import {HoudiniBridge} from '../../lib/bridge.js'
import {installSceneRecovery} from '../../lib/scene-recovery.js'
import {recordHoudiniContext} from '../../lib/dsh-adapter.js'
import {projectedExecutorState} from '../../lib/executor-identity-projection.js'

const identity='a'.repeat(32),signal=new AbortController().signal
const session=Session.create('durability-boundary')
await new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents())).ensure(session,identity)
const projectionCtx=fixtureProjectionContext()
let contacted=0
const router=new ExecutorRouter({find:async()=>{contacted++;throw Error('must not read endpoint')}},100,
  new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents())),value=>projectedExecutorState(projectionCtx,value),()=>true,async()=>false)
await assert.rejects(router.resolve({agent:{id:session.id,session},signal}),/尚未可靠保存/)
await assert.rejects(router.sceneContextFor(session,signal),/尚未可靠保存/)
assert.equal(contacted,0,'failed durability must precede endpoint verification or scene traffic')

async function chooseFixture(choice) {
  const source=Session.create('choose-project')
  const header={cwd:path.resolve('tools/out/before-choice')}
  let service,hook,questions=0
  const selected=path.resolve('tools/out/selected-project'),resolutions=[],traffic=[]
  const agent={id:source.id,status:'running',inject:message=>source.append('agent/inbox/spliced',{target:'next-step',start:0,inserted:[message]}),
    session:{id:source.id,header,get seq(){return source.seq},eventAt:(...args)=>source.eventAt(...args),snapshotEvents:()=>source.snapshotEvents(),append:(...args)=>source.append(...args)}}
  const target={executor_id:identity,runtime_id:identity,registration_id:'b'.repeat(32),scene_id:'c'.repeat(32),scene_epoch:'d'.repeat(32),
    hip_path:path.join(selected,'project.hip'),workspace_path:selected,hip_is_new:false}
  const bridge=new HoudiniBridge('http://127.0.0.1:1',100,identity)
  bridge.inspectExecutor=async()=>{traffic.push('health');return {executorId:identity}}
  bridge.recover=async()=>{throw Error('ordinary read or a fresh selected scene must not restore historical ownership')}
  installSceneRecovery(fixtureProjectionContext({provide:(_name,value)=>service=value,on:(event,callback)=>{assert.equal(event,'agent/pre-step');hook=callback},
    sessions:{flush:async()=>true},get:name=>name==='userQuestions'?{ask:async()=>{questions++;return {answers:[]}}}:undefined}),
    {registry:'fixture',resolve:async(exec,options)=>{assert.equal(exec.agent,agent);resolutions.push(options);return bridge}})
  await hook({agent,signal},async()=>({kind:'continue'}))
  assert.deepEqual(resolutions,[],'ordinary conversation resolves no endpoint')
  assert.deepEqual(traffic,[],'ordinary conversation probes or restores no scene')
  assert.equal(service.beforeStep,undefined)
  assert.equal(service.beforeTool,undefined)
  assert.equal(questions,0)
  if(choice==='select') {
    await new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents()),(_session,message)=>recordHoudiniContext(agent,message)).select(agent.session,target,signal)
    assert.deepEqual(resolutions,[],'explicit target selection itself makes no recovery call')
    assert.equal(recordedExecutorIdentity(source.snapshotEvents()),identity)
    assert.equal((await service.inspect(agent,signal)).status,'new_task')
    await service.beforeWrite(agent,signal)
    assert(resolutions.every(value=>value.write===false),'read routing and recovery checks never acquire the writer; tool write admission owns that step')
    assert.deepEqual(traffic,['health'])
  } else {
    assert.equal(recordedExecutorIdentity(source.snapshotEvents()),undefined,'free text and skipped selection confer no target')
  }
  assert.equal(header.cwd,path.resolve('tools/out/before-choice'),'target selection does not relocate a conversation')
}
await chooseFixture('select')
await chooseFixture('custom')
await chooseFixture('skip')
console.log('Desktop routing: durability before endpoint traffic, explicit read-only selection, no ordinary recovery traffic or cwd move, no binding from free text or skipped choice')
