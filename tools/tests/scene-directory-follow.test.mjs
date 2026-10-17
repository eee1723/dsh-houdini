import assert from 'node:assert/strict'
import path from 'node:path'
import {Session} from '@deepseek-ai/dsh-session'
import {HoudiniBridge} from '../../lib/bridge.js'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {installSceneRecovery} from '../../lib/scene-recovery.js'
import {foldExecutorState} from '../../lib/executor-identity-projection.js'
const executor='a'.repeat(32),checkpoint='c'.repeat(32),signal=new AbortController().signal
const old=path.resolve('tools/out/follow-old'),file=path.resolve('tools/out/follow-new/project.hip')
const scene='d'.repeat(32),epoch='e'.repeat(32)
const original={status:'connected',executor_id:executor,checkpoint_id:checkpoint,hip_path:file,scene_id:scene,scene_epoch:epoch,
 successful_save:{checkpoint_id:checkpoint,hip_path:file}}
async function fixture(value,available=true){
 const base=Session.create('follow-test'),moves=[]
 await new ExecutorBinding().ensure(base,executor)
 const session={id:base.id,header:{cwd:old},snapshotEvents:()=>base.snapshotEvents(),append:(...args)=>base.append(...args)}
 const agent={id:base.id,session,status:'idle',inject:message=>base.append('agent/inbox/spliced',{target:'next-step',start:0,inserted:[message]})},bridge=new HoudiniBridge('http://127.0.0.1:1',100,executor)
 bridge.recover=async()=>value
 let service
 installSceneRecovery({provide:(_name,value)=>{service=value},sessions:{flush:async()=>true},get:name=>
  name==='workspaceRegistry'&&available?{relocateSession:async(id,cwd)=>{moves.push({id,cwd});session.header={cwd}}}:undefined},bridge)
 return {moves,session,run:()=>service.followDirectory(agent,signal,true)}
}
for(const value of [
 {...original,successful_save:null},
 {...original,successful_save:{checkpoint_id:'d'.repeat(32),hip_path:file}},
 {...original,successful_save:{checkpoint_id:checkpoint,hip_path:path.resolve('tools/out/backup/project.hip')}},
 {...original,status:'different_scene'},
 {...original,executor_id:'b'.repeat(32)},
 {...original,hip_path:'relative.hip'},
]){const f=await fixture(value);await f.run();assert.equal(f.moves.length,0,'unverified paths must not relocate the conversation')}
const valid=await fixture(original);await valid.run();await valid.run()
assert.deepEqual(valid.moves,[{id:'follow-test',cwd:path.dirname(file)}],'one durable move, then an idempotent no-op')
const followed=foldExecutorState(valid.session.snapshotEvents()).project
assert.equal(followed.sceneId,scene,'a verified Save As keeps the observed scene identity')
assert.equal(followed.sceneEpoch,epoch)
assert.equal(followed.needsReview,false,'the plugin move is not an unobserved file replacement')
const unavailable=await fixture(original,false)
await assert.rejects(unavailable.run(),/尚未加载会话目录接续能力/)
assert.equal(unavailable.session.header.cwd,old)
console.log('scene directory follow: saved facts only, unrelated/failed/backup paths refused, original identity retained')
