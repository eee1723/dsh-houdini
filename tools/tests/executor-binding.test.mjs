import assert from 'node:assert/strict'
import {Session} from '@deepseek-ai/dsh-session'
import {ExecutorBinding,recordedExecutorIdentity,installFixedTargetContext} from '../../lib/executor-binding.js'
import {foldExecutorState} from '../../lib/executor-identity-projection.js'
const first='a'.repeat(32),second='b'.repeat(32)
const target=id=>({executor_id:id,runtime_id:'c'.repeat(32),scene_epoch:'d'.repeat(32),scene_id:'e'.repeat(32),
  registration_id:'f'.repeat(32),hip_path:'C:/project/scene.hip',hip_is_new:false,workspace_path:'C:/project'})
const session=Session.create('target-selection'),binding=new ExecutorBinding()
await binding.ensure(session,first)
assert.equal(recordedExecutorIdentity(session.snapshotEvents()),first,'legacy history remains readable')
session.append('tool/call',{callId:'executed',name:'houdini_exec',arguments:'{}'})
await binding.select(session,target(second))
assert.equal(recordedExecutorIdentity(session.snapshotEvents()),second,'an executed conversation can explicitly select a different target')
assert.deepEqual(foldExecutorState(session.snapshotEvents()).selectedTarget,target(second))
assert.equal(session.snapshotEvents().at(-1).data.source.kind,'dsh-houdini')
const before=session.snapshotEvents().length
await assert.rejects(binding.select(session,target(first),AbortSignal.abort()),/abort/i)
assert.equal(session.snapshotEvents().length,before)
await binding.select(session,null)
const cleared=foldExecutorState(session.snapshotEvents())
assert.equal(cleared.identity,null)
assert.equal(cleared.selectedTarget,null)
assert.equal(cleared.selectionRecorded,true,'explicit clear differs from a never-selected conversation')
let hook
installFixedTargetContext({on:(name,fn)=>{assert.equal(name,'agent/pre-step');hook=fn}},first)
const fixed=Session.create('fixed-composition')
const decision=await hook({agent:{session:fixed},signal:new AbortController().signal},async()=>({kind:'enter',messages:[]}))
assert.equal(decision.messages.length,1)
fixed.append('user/message',decision.messages[0],{surfaceOp:'append'})
assert.equal(recordedExecutorIdentity(fixed.snapshotEvents()),first)
assert.equal((await hook({agent:{session:fixed},signal:new AbortController().signal},async()=>({kind:'enter',messages:[]}))).messages.length,0)
assert.deepEqual(await hook({agent:{session:fixed},signal:new AbortController().signal},async()=>({kind:'reject'})),{kind:'reject'})
console.log('target binding: native explicit snapshots, executed reselect, explicit clear, abort and no ordinary-chat hooks passed')

const literalTarget={...target(first),hip_path:'C:/project/{{model}}.hip'}
await binding.select(session,literalTarget)
assert.equal(foldExecutorState(session.snapshotEvents()).selectedTarget.hip_path,literalTarget.hip_path)
assert(!session.snapshotEvents().at(-1).data.source.sections[0].text.includes('{{model}}'),
 'file names remain literal data before DSH expands template variables')
