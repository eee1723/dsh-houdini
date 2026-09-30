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
console.log('executor binding: one DSH message, target continuity and normal step admission passed')
