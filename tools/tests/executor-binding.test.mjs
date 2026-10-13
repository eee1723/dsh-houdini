import assert from 'node:assert/strict'
import {Session} from '@deepseek-ai/dsh-session'
import {ExecutorBinding,recordedExecutorIdentity,installExecutorBinding} from '../../lib/executor-binding.js'
const first='a'.repeat(32),second='b'.repeat(32)
const session=Session.create('executor-binding')
const binding=new ExecutorBinding()
await binding.ensure(session,first)
await binding.ensure(session,first)
assert.equal(session.snapshotEvents().length,1)
assert.equal(session.snapshotEvents()[0].data.source.kind,'dsh-houdini')
assert.equal(recordedExecutorIdentity(session.snapshotEvents()),first)
const migrated=structuredClone(session.snapshotEvents())
migrated[0].data.source.kind='plugin:dsh-houdini'
assert.equal(recordedExecutorIdentity(migrated),first,'released DSH V3-to-V4 source conversion retains the original binding')
await assert.rejects(binding.ensure(session,second),/recorded executor differs/)
const before=session.snapshotEvents().length
await assert.rejects(binding.ensure(session,first,AbortSignal.abort()),/abort/i)
assert.equal(session.snapshotEvents().length,before)
const fresh=Session.create('binding-step')
let hook
installExecutorBinding({on:(name,fn)=>{assert.equal(name,'agent/pre-step');hook=fn}},first)
const decision=await hook({agent:{session:fresh},signal:new AbortController().signal},async()=>({kind:'enter',messages:[]}))
assert.equal(decision.messages.length,1)
fresh.append('user/message',decision.messages[0],{surfaceOp:'append'})
assert.equal((await hook({agent:{session:fresh},signal:new AbortController().signal},async()=>({kind:'enter',messages:[]}))).messages.length,0)
await assert.rejects(binding.ensure(Session.create('binding-missing'),first,undefined,false),/selected before model tool/)
let continued
installExecutorBinding({on:(_name,fn)=>continued=fn},second)
const unavailable=await continued({agent:{session},signal:new AbortController().signal},async()=>({kind:'enter',messages:[]}))
assert.equal(unavailable.kind,'enter','a missing Houdini must not disable conversation or historical work')
assert.equal(unavailable.messages[0].source.sections[0].name,'dsh-houdini:recovery-required')
session.append('user/message',unavailable.messages[0],{surfaceOp:'append'})
assert.equal((await continued({agent:{session},signal:new AbortController().signal},async()=>({kind:'enter',messages:[]}))).messages.length,0)
assert.equal(recordedExecutorIdentity(session.snapshotEvents()),first,'a recovery notice must never rebind the task')
await assert.rejects(binding.ensure(session,second),/recorded executor differs/)
let automaticStep,assessments=0
installExecutorBinding({on:(_name,fn)=>automaticStep=fn,get:()=>({beforeStep:async()=>{assessments++;throw new Error('kept unsaved content')}})},second)
const userMessage={source:{kind:'user'},content:[{type:'text',text:'继续'}]}
const payload={agent:{session},signal:new AbortController().signal}
assert.deepEqual(await automaticStep(payload,async()=>({kind:'reject'})),{kind:'reject'})
assert.equal(assessments,0,'a rejected DSH step must not inspect, reload, ask or append recovery')
await automaticStep(payload,async()=>({kind:'enter',messages:[userMessage]}))
assert.equal(assessments,1)
await automaticStep(payload,async()=>({kind:'enter',messages:[]}))
assert.equal(assessments,1,'model/tool continuations without new human input must not ask again')
console.log('executor binding: one DSH message, target continuity and normal step admission passed')
