import {foldExecutorBinding} from '../../lib/executor-identity-projection.js'
import {fixtureProjectionContext} from './fixture-session.mjs'
import assert from 'node:assert/strict'
import {Session} from '@deepseek-ai/dsh-session'
import {HoudiniBridge} from '../../lib/bridge.js'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {installSceneRecovery} from '../../lib/scene-recovery.js'
const a='a'.repeat(32),b='b'.repeat(32),scene='d'.repeat(32),checkpoint='e'.repeat(32),epoch='f'.repeat(32)
const session=Session.create('original-task'),agent={id:session.id,session,status:'running'}
await new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents())).ensure(session,a)
session.append('tool/call',{callId:'old-save',name:'houdini_exec'})
session.append('tool/result',{message:{source:{callId:'old-save'}},meta:{canonical:{execution:{
  executor_id:a,runtime_id:a,sequence:1,observed_at:1,owner_session:agent.id,read_only:false,
  scene_recovery:{scene_id:scene,scene_epoch:a,checkpoint_id:checkpoint}}}}},{surfaceOp:'append'})
await new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents())).select(session,{executor_id:b,runtime_id:b,scene_epoch:epoch,scene_id:b,
  registration_id:b,hip_path:'C:/different.hip',hip_is_new:false})
let service,hook,questions=0;const requests=[]
class Bridge extends HoudiniBridge {
  constructor(){super('http://127.0.0.1:1',100,b)}
  async recover(action){requests.push(action);throw new Error('recovery must not be reached for a different scene')}
}
installSceneRecovery(fixtureProjectionContext({provide:(_name,value)=>{service=value},on:(event,callback)=>{assert.equal(event,'agent/pre-step');hook=callback},
  get:()=>({ask:async()=>{questions++;return {answers:[]}}}),sessions:{flush:async()=>true}}),new Bridge())
const signal=new AbortController().signal
await hook({agent,signal},async()=>({kind:'continue'}))
await service.beforeWrite(agent,signal)
assert.deepEqual(requests,[],'ordinary conversation and a newly selected scene do not locate/open/reload a historical project')
assert.equal(questions,0,'there is no implicit discard-unsaved question')
assert.equal(session.header.cwd,undefined,'selecting a project alone does not move the conversation directory')
console.log('original project preservation: current selection is respected without locate/open/replay or discard questions')
