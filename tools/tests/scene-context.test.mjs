import {fixtureProjectionContext} from './fixture-session.mjs'
import {projectedExecutorState} from '../../lib/executor-identity-projection.js'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {installSceneContext} from '../../lib/context.js'
import {SceneContextProvider} from '../../lib/scene-context.js'
import {Session,SessionStore} from '@deepseek-ai/dsh-session'
import {Context} from '@deepseek-ai/cordis'
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt'
import {AgentRegistry} from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import ToolsService from '@deepseek-ai/dsh-tools'
import {NativeToolExecutor} from '@deepseek-ai/dsh-tool-executor-native'
import * as JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
const SCENE='dsh-houdini:scene-context',STATE='dsh-houdini:execution-state'
const user=(id,text)=>({id,role:'user',source:{kind:'user'},content:[{type:'text',text}]})
const data=section=>JSON.parse(section.text.slice(section.text.indexOf('\n')+1))
let calls=0,frame=1
const selectedEditorItems=[{type:'sticky_note',parent:'/obj/example',name:'READ_ME'}]
const bridge={async sceneContext(){calls++;return {ok:true,result:{frame,hip_path:'{{scene}}.hip',
  selection:[{path:'/obj/selected'}],selected_editor_items:selectedEditorItems}}}}
const hooks={},registered=[]
const projectionCtx=await fixtureProjectionContext({tools:{get:(_name,_scope,toolSet)=>toolSet?.enabled===false?undefined:({name:'houdini_inspect'})},systemPrompt:{context:c=>registered.push(c)},on:(n,f)=>hooks[n]=f})
installSceneContext(projectionCtx,bridge)
const session=Session.create('scene-native-context'),agent={session,model:{current:()=>undefined}}
const promptContext=new Context()
new SystemPrompt(promptContext,{})
for(const section of registered)promptContext.systemPrompt.context(section)
async function assemble(message,contexts=registered.map(c=>({name:c.name,text:c.text({agent})})),tools=[{name:'houdini_inspect'}],toolSet) {
  if (message) {hooks['agent/inbox/inserted']({agent,message});hooks['agent/inbox/claimed']({agent,message})}
  const assembly={contexts,tools,variables:{}}
  await hooks['system-prompt/assemble'](assembly,{scope:agent,agent,toolSet},async()=>assembly)
  return promptContext.systemPrompt.refreshContext(assembly,{scope:{},agent}).contexts.filter(c=>c.text)
}
assert.equal((await assemble(user('greeting','你好'))).filter(section=>section.name===SCENE).length,1)
const first=await assemble(user('selected','检查选中节点'))
assert.equal(data(first[0]).observation.result.frame,1)
assert.deepEqual(data(first[0]).observation.result.selected_editor_items,selectedEditorItems)
assert(!first[0].text.includes('{{'),'scene strings cannot interpolate prompt variables')
frame=20
assert.equal((await assemble())[0].text,first[0].text)
assert.equal(calls,2,'one observation is tied to one received user message')
assert.equal((await assemble(undefined,undefined,[{name:'run_code'}]))[0].text,first[0].text,
  'PTC presentation retains the same registered Houdini context at request admission')
assert.deepEqual(await assemble(undefined,undefined,[],{enabled:false}),[],
  'a step without admitted Houdini tools cannot retain the previous scene context')
assert.equal((await assemble())[0].text,first[0].text,'an admitted later step can recover its same observation')
assert.equal(hooks['agent/pre-step'],undefined,'DSH owns context acceptance, compression and persistence')
session.append('user/message',user('selected','检查选中节点'),{surfaceOp:'append'})
session.append('user/message',{role:'user',content:[{type:'text',text:first[0].text}],
  source:{kind:'runtime-context',form:'snapshot',sections:first}},{surfaceOp:'append'})
const resumed=new SceneContextProvider(bridge,agent=>projectedExecutorState(projectionCtx,agent.session).sceneObservation)
assert.equal(await resumed.observe({session}),first[0].text)
assert.equal(calls,2,'resume reuses the original selection observation')
const reclaimed={session}
resumed.claim(reclaimed,user('selected','检查选中节点'))
assert.equal(await resumed.observe(reclaimed),first[0].text,
  'a claim without a new insertion reuses an exactly matching persisted observation')
assert.equal(calls,2,'reclaiming a persisted observation never samples the new live selection')
session.append('tool/call',{turn:1,step:1,callId:'bad',name:'houdini_exec',arguments:'{}'})
session.append('tool/result',{turn:1,step:1,message:{role:'tool',source:{kind:'tool',callId:'bad'},content:[]},meta:{canonical:{ok:false,error:'Bad parm',execution:{runtime_id:'r',sequence:1,observed_at:1}}}},{surfaceOp:'append'})
const notice=(await assemble()).find(c=>c.name===STATE)
assert.equal(notice,undefined,'settled failure does not append the same scene and capability again')
assert.equal((await assemble())[0].text,first[0].text)
session.append('tool/call',{turn:1,step:2,callId:'unknown',name:'houdini_exec',arguments:'{}'})
session.append('tool/result',{turn:1,step:2,message:{role:'tool',source:{kind:'tool',callId:'unknown'},content:[]},meta:{canonical:{ok:false,requestReceipt:{request_ref:'r.request',status:'unknown_transport'}}}},{surfaceOp:'append'})
const recovery=(await assemble()).find(c=>c.name===STATE)
assert.deepEqual(data(recovery).unresolved_requests,[['r.request','unknown_transport']])
assert.deepEqual(await assemble(undefined,[]),[],'runtime context suppression remains DSH-owned')
const override={name:SCENE,text:'Scoped observation override'}
// The plugin preserves an accepted scoped override; the real registry also
// needs that scoped provider, otherwise admission correctly refreshes it.
const overrideAssembly={contexts:[override],tools:[{name:'houdini_inspect'}],variables:{}}
await hooks['system-prompt/assemble'](overrideAssembly,{scope:{},agent},async()=>overrideAssembly)
assert.deepEqual(overrideAssembly.contexts,[override])
const removed=user('removed-and-replaced','queued selection')
frame=30
hooks['agent/inbox/inserted']({agent,message:removed})
hooks['agent/inbox/discarded']({agent,message:removed})
frame=40
const replaced=await assemble({...removed,content:[{type:'text',text:'replacement selection'}]})
assert.equal(data(replaced.find(c=>c.name===SCENE)).observation.result.frame,40,
  'the installed context consumer releases native discarded messages before replacement')
console.log('scene context: message-time observation, resume, native DSH context and actual errors passed')

// A queued message keeps the selection observed at arrival, even when newer
// messages arrive and their captures complete first. Discarding one pending
// message must not change the current observation or the other queued inputs.
const completions=[]
const queueAgent={session:Session.create('scene-observation-queue')}
const queued=new SceneContextProvider({sceneContext(){
  return new Promise(resolve=>completions.push(resolve))
}},()=>({}))
const qa=user('queued-a','first selection'),qb=user('queued-b','second selection'),qc=user('queued-c','cancel this')
queued.receive(queueAgent,qa);queued.receive(queueAgent,qb);queued.receive(queueAgent,qc)
queued.receive(queueAgent,qa)
assert.equal(completions.length,3,'duplicate delivery shares the same original capture')
queued.claim(queueAgent,qb)
completions[1]({ok:true,result:{frame:22}})
const second=await queued.observe(queueAgent)
assert.equal(data({text:second}).observation.result.frame,22)
queued.discard(queueAgent,qc)
completions[2]({ok:true,result:{frame:33}})
completions[0]({ok:true,result:{frame:11}})
assert.equal(await queued.observe(queueAgent),second,'late old or discarded results do not replace the current one')
queued.claim(queueAgent,qa)
assert.equal(data({text:await queued.observe(queueAgent)}).observation.result.frame,11,
  'claiming an earlier queued message preserves its arrival-time selection')
assert.equal(completions.length,3,'out-of-order claim does not recapture an earlier message')
const cancelled=new AbortController();cancelled.abort()
await assert.rejects(queued.observe(queueAgent,cancelled.signal),error=>error.name==='AbortError')
assert.equal(completions.length,3,'aborted assembly does not retry the scene query')
const qd=user('claimed-slow','slow current capture'),qe=user('claimed-new','new current capture')
queued.receive(queueAgent,qd);queued.claim(queueAgent,qd)
const slowAssembly=queued.observe(queueAgent)
queued.receive(queueAgent,qe);queued.claim(queueAgent,qe)
completions[4]({ok:true,result:{frame:55}})
const newest=await queued.observe(queueAgent)
completions[3]({ok:true,result:{frame:44}})
assert.equal(data({text:await slowAssembly}).user_message_id,qd.id,
  'an in-flight reader retains the observation it requested')
assert.equal(await queued.observe(queueAgent),newest,
  'late completion of a formerly current capture never backfills the new current slot')

// Exercise the released DSH Inbox rather than simulate its replacement/clear
// notifications. Only scene observation and model work are substituted: every
// consumed message goes through a real Agent turn and native claim lifecycle.
const inboxContext=new Context()
new SessionStore(inboxContext)
await fixtureProjectionContext(inboxContext)
new SystemPrompt(inboxContext,{})
const inboxTools=new ToolsService(inboxContext,{})
inboxTools.setExecutor(new NativeToolExecutor(inboxContext))
inboxContext.provide('llm',{})
await inboxContext.plugin(AgentRegistry).await()
await inboxContext.plugin(AgentLoop,{agents:[]}).await()
let arrival=0,lastObserved
const liveProvider=new SceneContextProvider({async sceneContext(){
  return {ok:true,result:{frame:++arrival}}
}},agent=>projectedExecutorState(inboxContext,agent.session).sceneObservation)
inboxContext.on('agent/inbox/inserted',({agent,message})=>liveProvider.receive(agent,message))
inboxContext.on('agent/inbox/claimed',({agent,message})=>liveProvider.claim(agent,message))
inboxContext.on('agent/inbox/discarded',({agent,message})=>liveProvider.discard(agent,message))
inboxContext.on('agent/pre-step',async({agent})=>{
  lastObserved=await liveProvider.observe(agent)
  return {kind:'reject'} // no model call, filesystem, network or HOM
})
const handle=await inboxContext.agents.create({sessionId:'scene-native-inbox',
  agentOptions:{provider:'scene-context-fixture',model:'not-called'}})
let coldHandle,coldStorage
const coldRoot=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-scene-context-cold-'))
try {
  const agent=handle.agent
  const pending=()=>liveProvider.observations.get(agent)?.pending.size??0
  const saved=user('saved-selection','keep until consumed')
  agent.inbox.append('next-turn',saved)
  const savedArrival=arrival
  agent.inbox.append('next-step',user('replaced','old queued text'))
  const beforeReplacement=arrival
  assert(agent.inbox.replace('replaced',user('replacement','new queued text')))
  assert.equal(arrival,beforeReplacement+1,'native replacement gets its own arrival observation')
  assert.equal(pending(),2,'replaced message releases its observation')
  assert(agent.inbox.remove('replacement'))
  assert.equal(pending(),1)
  agent.inbox.prepend('next-turn',user('front','first turn'))
  const frontArrival=arrival
  agent.steer(user('steering','wake and consume steering'))
  await agent.whenIdle()
  assert.equal(pending(),1,'a rejected native step leaves later queued turns and their observations pending')
  assert.equal(agent.inbox.nextTurn[0].id,saved.id)
  agent.steer(user('next-steering','wake the saved follow-up'))
  await agent.whenIdle()
  assert.equal(pending(),0,'all native claimed observations leave the pending store')
  assert.equal(data({text:lastObserved}).user_message_id,saved.id)
  assert.equal(data({text:lastObserved}).observation.result.frame,savedArrival,
    'a queued follow-up retains its original observation after newer steering and turns')
  assert(frontArrival>savedArrival)

  for(let i=0;i<1000;i++) {
    agent.inbox.append('next-turn',user('discard-'+i,'discarded pending input'))
    agent.inbox.clear()
  }
  assert.equal(pending(),0,'clearing native queued input does not accumulate observations')
  for(let i=0;i<1000;i++) {
    const message=user('long-'+i,'consume one more turn')
    agent.followup(message)
    await agent.whenIdle()
    assert.equal(data({text:lastObserved}).user_message_id,message.id)
    assert.equal(pending(),agent.inbox.nextTurn.length+agent.inbox.nextStep.length,
      'retained pending observations follow the live inbox, not total history')
  }
  assert.equal(liveProvider.observations.get(agent).current.key,'long-999')
  assert.equal(pending(),0,'the long-lived agent retains only its current consumed observation')
  const captured=arrival
  assert.equal(await liveProvider.observe(agent),lastObserved)
  assert.equal(arrival,captured,'later steps reuse the last claimed observation')

  // A stored pending Inbox is reconstructed without inserted notifications.
  // The new Host cannot pretend its current selection was observed before the
  // old Host ended. Exercise the actual JSONL read and Agent.resume contract.
  coldStorage=inboxContext.plugin(JsonlSessionPersistence,{root:coldRoot,compression:'none'})
  await coldStorage.await()
  const cold=Session.create('scene-cold-pending')
  cold.append('user/message',user('selected','earlier already observed message'),{surfaceOp:'append'})
  cold.append('user/message',{id:'cold-original-observation',role:'user',content:[{type:'text',text:first[0].text}],
    source:{kind:'runtime-context',form:'snapshot',sections:first}},{surfaceOp:'append'})
  const oldPending=user('old-pending','change what I selected before the Host closed')
  cold.append('agent/inbox/spliced',{target:'next-turn',start:0,inserted:[oldPending]})
  const stored=await inboxContext.sessionPersistence.create(cold.header)
  await stored.append(cold.snapshotEvents());await stored.flush();await stored.close()
  const beforeResume=arrival
  coldHandle=await inboxContext.agents.resume({resumeSessionId:cold.id,
    agentOptions:{provider:'scene-context-fixture',model:'not-called'}})
  assert.equal(coldHandle.agent.inbox.nextTurn[0].id,oldPending.id)
  assert.equal(arrival,beforeResume,'native cold resume does not fabricate an insertion observation')
  coldHandle.agent.send({...user('wake-cold','resume pending work'),source:{kind:'dsh-houdini'}},'next-step',true)
  await coldHandle.agent.whenIdle()
  const unavailable=data({text:lastObserved})
  assert.equal(unavailable.user_message_id,oldPending.id)
  assert.equal(unavailable.observation.status,'unavailable')
  assert.equal(unavailable.observation.ok,false)
  assert.match(unavailable.observation.reason,/arrival-time observation was not retained/)
  assert.equal(unavailable.observation.result,undefined,'another message snapshot cannot stand in for the missing one')
  assert.equal(arrival,beforeResume,'claiming old pending input never captures today\'s selection')
}finally {
  await coldHandle?.dispose()
  await handle.dispose()
  await coldStorage?.dispose()
  await inboxContext.fiber.dispose()
  fs.rmSync(coldRoot,{recursive:true,force:true})
}
console.log('scene context: native Inbox replacement/clear, 1000 consumed turns and cold pending resume keep bounded, message-exact observations')
