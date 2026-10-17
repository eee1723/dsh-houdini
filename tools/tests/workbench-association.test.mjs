import assert from 'node:assert/strict'
import path from 'node:path'
import {Session} from '@deepseek-ai/dsh-session'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {executorIdentityProjection as projection,foldExecutorState} from '../../lib/executor-identity-projection.js'
import {workspaceOpeningMessage} from '../../lib/dsh-adapter.js'
import {ExecutorRouter} from '../../lib/executor-routing.js'
import {HoudiniBridge} from '../../lib/bridge.js'
import {installSceneRecovery} from '../../lib/scene-recovery.js'

const executor='a'.repeat(32),scene='b'.repeat(32),signal=new AbortController().signal
const session=Session.create('workbench-association')
const binding=new ExecutorBinding()
await binding.ensure(session,executor)
const recordedHip=path.resolve('tools/out/old/asset.hip')
session.append('user/message',workspaceOpeningMessage({executor_id:executor,scene_id:scene,scene_epoch:'c'.repeat(32),
  hip_path:recordedHip,hip_is_new:false}),{surfaceOp:'append'})
let events=[...session.snapshotEvents(),{type:'tool/call',data:{callId:'metadata',name:'houdini_capabilities'}}]
assert.equal(foldExecutorState(events).hasOperations,false,'model metadata never becomes scene work')
const reselected=[]
await binding.reselectUnexecuted({snapshotEvents:()=>events,append:(...args)=>reselected.push(args)},'d'.repeat(32))
assert.equal(reselected.length,1)
const observed={executor_id:executor,runtime_id:'e'.repeat(32),sequence:1,observed_at:Date.now()/1000+1,
  hip_path:path.resolve('tools/out/new/asset.hip'),hip_is_new:false,scene_recovery:{scene_id:scene,scene_epoch:'c'.repeat(32)}}
for(const tool of ['houdini_ui_list','houdini_ui_screenshot','houdini_request']) {
  const input=[...events,{type:'tool/call',data:{callId:tool,name:tool}},
    {type:'tool/result',data:{message:{source:{callId:tool}},meta:{canonical:{execution:observed}}}}]
  const state=foldExecutorState(input)
  assert.equal(state.project.sceneId,scene)
  assert.equal(state.project.hipPath,observed.hip_path)
}

// Multi-window choice rechecks the selected candidate. A same-path foreign
// scene is not even assessed; free text/cancel cannot become a target identity.
// A file copy shares scene_id: only the recorded HIP path qualifies a window.
const copyHip=path.resolve('tools/out/copy/asset.hip')
const candidates=['1','2'].map(char=>({executor_id:char.repeat(32),workbench:true,state:'registered',
  scene_id:scene,hip_path:recordedHip}))
const directory={find:async()=>{throw Error('original retired')},list:async()=>[...candidates,
  {executor_id:'3'.repeat(32),workbench:true,state:'registered',scene_id:'f'.repeat(32),hip_path:recordedHip},
  {executor_id:'4'.repeat(32),workbench:true,state:'registered',scene_id:scene,hip_path:copyHip}]}
let answer=candidates[1].executor_id,chosen=0,assessed=[],claims=[]
const router=new ExecutorRouter(directory,100,binding,()=>executor,async()=>true,
  async(_task,choices)=>{chosen++;assert.equal(choices.length,2);return answer})
router.inspectRecovery=async(_session,id)=>{assessed.push(id);return new HoudiniBridge('http://127.0.0.1:1',100,id)}
const originalVerify=router.verified.bind(router)
const stubs=new Map()
const stub=(id)=>{
  if(!stubs.has(id))stubs.set(id,{targetExecutorId:id,claimWriter:async(taskId,registrationId,expectedHip)=>{
    claims.push({id,taskId,registrationId,expectedHip})}})
  return stubs.get(id)
}
router.verified=async(id,...args)=>id===executor?originalVerify(id,...args):stub(id)
const agent={id:session.id,session,status:'idle'}
assert.equal((await router.recoveryTarget(agent,signal)).targetExecutorId,answer)
assert.equal(chosen,1)
assert.deepEqual(assessed,[candidates[0].executor_id,candidates[1].executor_id,candidates[1].executor_id])
assert(!assessed.includes('4'.repeat(32)),'a copy sharing scene_id at another HIP path is never assessed or auto-matched')
assert.deepEqual(claims.map(claim=>claim.id),[candidates[1].executor_id],'the chosen window is explicitly claimed, never stolen inside verification')
assert.equal((await router.recoveryTarget(agent,signal,candidates[0].executor_id)).targetExecutorId,candidates[0].executor_id)
assert.equal(chosen,1,'an explicit native Open must not ask again or change its target')
assert.deepEqual(claims.map(claim=>claim.id),[candidates[1].executor_id,candidates[0].executor_id],'a preferred window is claimed only after it re-verifies')
answer=undefined
await assert.rejects(router.recoveryTarget(agent,signal),/选择/)
assert.equal(claims.length,2,'an unresolved window choice claims nothing')
answer=candidates[1].executor_id
let checks=0
router.inspectRecovery=async(_session,id)=>++checks>2?undefined:new HoudiniBridge('http://127.0.0.1:1',100,id)
await assert.rejects(router.recoveryTarget(agent,signal),/选择期间工程已变化/)
assert.equal(claims.length,2,'a window that failed the fresh recheck is never claimed')
assert.equal(foldExecutorState(session.snapshotEvents()).identity,executor)

// inspectRecovery itself binds scene_id + hip_path: the live reply must show
// the recorded path, not only the copyable scene identity.
const inspectRouter=new ExecutorRouter(directory,100,binding,()=>executor,async()=>true)
let replyHip=recordedHip
inspectRouter.verified=async id=>({recover:async()=>({executor_id:id,status:'ready',scene_id:scene,hip_path:replyHip})})
const inspectSession={id:session.id,snapshotEvents:()=>session.snapshotEvents()}
assert(await inspectRouter.inspectRecovery(inspectSession,candidates[0].executor_id,signal))
replyHip=copyHip
assert.equal(await inspectRouter.inspectRecovery(inspectSession,candidates[0].executor_id,signal),undefined,
  'same scene_id at another HIP path does not pass inspectRecovery')

// Failed Save As directory commit cannot disappear in the shared-workbench wrapper.
events=[...events,{type:'tool/call',data:{callId:'save',name:'houdini_exec'}},
  {type:'tool/result',data:{message:{source:{callId:'save'}},meta:{canonical:{execution:observed}}}}]
const checkpoint='9'.repeat(32),facts={status:'connected',executor_id:executor,checkpoint_id:checkpoint,hip_path:observed.hip_path,
  successful_save:{checkpoint_id:checkpoint,hip_path:observed.hip_path}}
const bridge=new HoudiniBridge('http://127.0.0.1:1',100,executor);bridge.recover=async()=>facts
let service,moves=0
const current={...agent,session:{id:session.id,header:{cwd:path.resolve('tools/out/old')},snapshotEvents:()=>events}}
installSceneRecovery({provide:(_name,value)=>service=value,sessions:{flush:async()=>true},get:name=>
  name==='houdiniTargets'?{workbench:true}:name==='workspaceRegistry'?{relocateSession:async()=>{moves++;throw Error('disk commit failed')}}:undefined},
  {resolve:async()=>bridge,recoveryTarget:async()=>bridge})
await assert.rejects(service.followDirectory(current,signal,true),/disk commit failed/)
assert.equal(moves,1)
assert.equal(projection.wire.view(foldExecutorState(events)).sceneId,scene)
console.log('workbench association: stable scene, Host-only metadata, UI/native receipts, explicit multi-window choice, fresh recheck, same-path exclusion and failed directory commit passed')
