import assert from 'node:assert/strict'
import path from 'node:path'
import {Session} from '@deepseek-ai/dsh-session'
import {HoudiniBridge} from '../../lib/bridge.js'
import {ExecutorBinding,recordedExecutorIdentity} from '../../lib/executor-binding.js'
import {installSceneRecovery,recoveryMessage} from '../../lib/scene-recovery.js'
const a='a'.repeat(32),b='b'.repeat(32),c='c'.repeat(32),scene='d'.repeat(32),checkpoint='e'.repeat(32),epoch='f'.repeat(32)
const hip=path.resolve('tools/out/original.hip'),other=path.resolve('tools/out/other.hip')
async function fixture(response='open'){
 const session=Session.create('original-task');await new ExecutorBinding().ensure(session,a)
 session.append('user/message',recoveryMessage({schema:2,kind:'executor_recovery',previous_executor:a,executor_id:b,
  operation_id:a,checkpoint_id:checkpoint,scene_id:scene,scene_epoch:epoch,runtime_id:b,hip_path:hip,restored_nodes:1}),{surfaceOp:'append'})
 const agent={id:session.id,session,status:'running'},requests=[];let opened=false,service,durable=true
 class Bridge extends HoudiniBridge{
  constructor(){super('http://127.0.0.1:1',100,c)}
  async recover(action,input){
   requests.push({action,input})
   const actual={executor_id:c,checkpoint_id:checkpoint,scene_id:scene,scene_epoch:epoch,runtime_id:c,hip_path:hip,requires_reload:false,restored_nodes:1}
   if(action==='locate')return {status:'located',executor_id:c,checkpoint_id:null,scene_id:a,scene_epoch:b,hip_path:other,
    dirty:true,dirty_reliable:true,candidates:[{scene_id:scene,checkpoint_id:checkpoint,hip_path:hip}],unavailable:[]}
   if(action==='open'){opened=true;return {...actual,status:'opened'}}
   if(action==='assess')return opened?{...actual,status:'ready'}:{status:'different_scene',message:'wrong project'}
   return {...actual,operation_id:input.operation_id,status:action==='activate'?'active':'prepared'}
  }
 }
 installSceneRecovery({provide:(_name,value)=>{service=value},sessions:{flush:async()=>durable},get:name=>name==='userQuestions'?{
  ask:async({questions:[q]})=>{
   assert(q.detail.includes(other)&&q.detail.includes(hip),'the native question must identify both actual files')
   if(response==='changed')session.append('user/message',recoveryMessage({schema:2,kind:'executor_recovery',previous_executor:b,executor_id:a,
    operation_id:a,checkpoint_id:checkpoint,scene_id:scene,scene_epoch:epoch,runtime_id:b,hip_path:hip,restored_nodes:1}),{surfaceOp:'append'})
   return {answers:[{id:q.id,selected:[q.options[response==='keep'?0:1].label],...(response==='custom'?{custom:'已确认恢复成功'}:{})}]}
  }}:undefined},new Bridge())
 return {session,requests,run:()=>service.beforeStep(agent,new AbortController().signal),set durable(value){durable=value}}
}
const open=await fixture();await open.run();assert.equal(recordedExecutorIdentity(open.session.snapshotEvents()),c)
assert.deepEqual(open.requests.map(r=>r.action),['assess','locate','open','assess','prepare','activate'])
assert.equal(open.requests.find(r=>r.action==='open').input.expected.discard_unsaved,true)
for(const response of ['keep','custom','changed']){
 const f=await fixture(response);await assert.rejects(f.run(),response==='changed'?/绑定已变化/:/已保留当前工程/)
 assert(!f.requests.some(r=>['open','prepare','activate'].includes(r.action)))
}
const disk=await fixture();disk.durable=false;await assert.rejects(disk.run(),/可靠保存/)
assert(!disk.requests.some(r=>r.action==='open'))
console.log('original project conversation: exact native choice, free text/keep/stale binding and failed persistence do not load')
