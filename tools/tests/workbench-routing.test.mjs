import assert from 'node:assert/strict'
import path from 'node:path'
import {Session} from '@deepseek-ai/dsh-session'
import {ExecutorBinding,recordedExecutorIdentity} from '../../lib/executor-binding.js'
import {ExecutorRouter} from '../../lib/executor-routing.js'
import {HoudiniBridge} from '../../lib/bridge.js'
import {installSceneRecovery} from '../../lib/scene-recovery.js'
import {recordHoudiniContext} from '../../lib/dsh-adapter.js'
import {Context} from '@deepseek-ai/cordis'
import {ExecutorController} from '../../lib/executor-controller.js'

const identity='a'.repeat(32),signal=new AbortController().signal
const session=Session.create('durability-boundary')
await new ExecutorBinding().ensure(session,identity)
let contacted=0
const router=new ExecutorRouter({find:async()=>{contacted++;throw Error('must not read endpoint')}},100,
  new ExecutorBinding(),value=>recordedExecutorIdentity(value.snapshotEvents()),async()=>false)
await assert.rejects(router.resolve({agent:{id:session.id,session},signal}),/尚未可靠保存/)
await assert.rejects(router.sceneContextFor(session,signal),/尚未可靠保存/)
await assert.rejects(router.recoveryTarget({id:session.id,session},signal),/尚未可靠保存/)
assert.equal(contacted,0,'failed durability must precede endpoint verification or scene traffic')

async function chooseFixture(choice) {
  const source=Session.create('choose-project')
  let header={cwd:path.resolve('tools/out/before-choice')},service,questions=0,selections=0
  const selected=path.resolve('tools/out/selected-project')
  const agent={id:source.id,status:'running',inject:message=>source.append('agent/inbox/spliced',{target:'next-step',start:0,inserted:[message]}),
    session:{id:source.id,get header(){return header},snapshotEvents:()=>source.snapshotEvents(),append:(...args)=>source.append(...args)}}
  const record={executor_id:identity,registration_id:'b'.repeat(32),state:'registered',workbench:true,
    hip_path:path.join(selected,'project.hip'),workspace_path:selected,houdini_version:'21.0.440'}
  const bridge=new HoudiniBridge('http://127.0.0.1:1',100,identity)
  const targetRouter={directory:{list:async()=>[record]},selectInitial:async(selectedAgent,target,generation,actualSignal,hip,atStep)=>{
    assert.equal(selectedAgent,agent);assert.equal(generation,record.registration_id);assert.equal(hip,record.hip_path)
    assert.equal(atStep,true);actualSignal.throwIfAborted();selections++
    await new ExecutorBinding(undefined,(_session,message)=>recordHoudiniContext(agent,message)).ensure(agent.session,target,actualSignal)
  }}
  installSceneRecovery({provide:(_name,value)=>service=value,sessions:{flush:async()=>true},get:name=>
    name==='houdiniTargets'?{workbench:true,getRouter:registry=>{assert.equal(registry,'fixture');return targetRouter}}:
    name==='workspaceRegistry'?{relocateSession:async(id,directory)=>{assert.equal(id,agent.id);header={cwd:directory}}}:
    name==='userQuestions'?{ask:async({questions:items})=>{questions++;return {answers:[{id:items[0].id,
      selected:choice==='select'?[items[0].options[0].label]:[],custom:choice==='custom'?'please guess':undefined}]}}}:undefined},
    {registry:'fixture',resolve:async()=>bridge,recoveryTarget:async()=>bridge})
  if(choice==='select') {
    await service.beforeStep(agent,signal)
    assert.equal(questions,0,'ordinary conversation does not require choosing a Houdini')
    await Promise.all([service.beforeTool(agent,signal),service.beforeTool(agent,signal)])
    assert.equal(questions,1)
    assert.equal(selections,1)
    assert.equal(header.cwd,selected)
    assert.equal(recordedExecutorIdentity(source.snapshotEvents()),identity)
  } else {
    await assert.rejects(service.beforeTool(agent,signal),/只讨论/)
    assert.equal(selections,0)
    assert.equal(recordedExecutorIdentity(source.snapshotEvents()),undefined)
    assert.notEqual(header.cwd,selected)
  }
}
await chooseFixture('select')
await chooseFixture('custom')
await chooseFixture('skip')
const host=new Context()
let saved=true,jobs=true,flushes=0
host.provide('agents',{list:()=>[{id:session.id,status:'idle'}]})
host.provide('sessions',{list:()=>[session],flush:async()=>{flushes++;return saved}})
host.on('workspace/session-activity',async({sessionId},next)=>{
  assert.equal(sessionId,session.id)
  return [...await next(),...(jobs?[{kind:'job',items:[{id:'fixture-job'}]}]:[])]
})
const controller=new ExecutorController(host,router,true)
assert.equal((await controller.activity()).activeConversations,1,'native background activity matters even when the Agent is idle')
jobs=false
assert.deepEqual(await controller.activity(),{activeConversations:0,durable:true})
saved=false
await assert.rejects(controller.activity(),/尚未可靠保存/)
assert.equal(flushes,3)
console.log('workbench routing: durability before endpoint traffic, native explicit selection, selected directory, no repeated question, no binding from free text or skipped choice')
