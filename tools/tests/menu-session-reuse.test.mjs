import assert from 'node:assert/strict'
import path from 'node:path'
import os from 'node:os'
import {Context} from '@deepseek-ai/cordis'
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection'
import {agentPresetProjectionDefinition} from '@deepseek-ai/dsh-agent-preset-registry'
import {ExecutorController} from '../../lib/executor-controller.js'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {foldExecutorBinding,registerExecutorIdentityProjection} from '../../lib/executor-identity-projection.js'
import {fixtureSession} from './fixture-session.mjs'

const ctx=new Context(),projections=new SessionProjectionRegistry(ctx)
projections.register(agentPresetProjectionDefinition);registerExecutorIdentityProjection(ctx)
const directory=path.join(os.tmpdir(),'menu-reuse-unit'),origin=fixtureSession('native-writer',{cwd:directory,agentPreset:'houdini'})
const agent={id:origin.id,session:origin,status:'running'}
const baseline={executor_id:'a'.repeat(32),registration_id:'b'.repeat(32),runtime_id:'c'.repeat(32),scene_id:'d'.repeat(32),
 scene_epoch:'e'.repeat(32),state:'registered',task_id:agent.id,hip_path:path.join(directory,'owned.hip'),
 workspace_path:directory,hip_is_new:false,workbench:true}
let record={...baseline},afterResolve=()=>{},duringVerify=async()=>{},resolveError=null,creates=0,selections=0
const archived=[],workspaces=[{id:'native-workspace',sessionIds:[agent.id],path:directory}],agents=new Map([[agent.id,agent]])
const binding=new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents()))
await binding.select(origin,baseline,new AbortController().signal)
ctx.provide('workspaceRegistry',{archivedSessionIds:archived,list:()=>workspaces,create:async directory=>{
 const value={id:'created-workspace',sessionIds:[],path:directory};workspaces.push(value);return value
}})
ctx.provide('sessionController',{
 resolveAgent:async id=>{await Promise.resolve();if(resolveError)throw resolveError;afterResolve();return agents.has(id)?{agent:agents.get(id)}:{error:{code:'session/not-found'}}},
 create:async()=>{const session=fixtureSession('created-'+(++creates),{cwd:directory,agentPreset:'houdini'});agents.set(session.id,{id:session.id,session,status:'idle'});return{sessionId:session.id}},
})
const router={directory:{find:async()=>({...record})},inspectSelectedTarget:async()=>{await duringVerify();return{...record}},
 selectTarget:async()=>{selections++;return{...record}}}
const controller=new ExecutorController(ctx,router,true)
const input=()=>({executorId:baseline.executor_id,registrationId:baseline.registration_id,expectedHip:baseline.hip_path,requestId:'f'.repeat(32)})
const open=()=>controller.openWorkspace(input(),new AbortController().signal)
try{
 const before=origin.seq
 const found=await open();assert.equal(found.sessionId,agent.id);assert.equal(found.workspaceId,'native-workspace')
 assert.equal(creates,0);assert.equal(selections,0);assert.equal(origin.seq,before,'busy navigation cannot change a binding or grant a writer')
 for(const [field,value] of [['registration_id','1'.repeat(32)],['runtime_id','2'.repeat(32)],['scene_epoch','3'.repeat(32)],
  ['scene_id','4'.repeat(32)],['task_id','other-writer'],['hip_path',path.join(directory,'moved.hip')]]){
  record={...baseline};afterResolve=()=>{record={...record,[field]:value}}
  await assert.rejects(open(),/接入期间已变化/);assert.equal(creates,0,'stale '+field+' cannot silently create another conversation')
 }
 record={...baseline};afterResolve=()=>archived.push(agent.id)
 await assert.rejects(open(),/接入期间已归档/);assert.equal(creates,0);archived.length=0;afterResolve=()=>{}
 resolveError=Error('native Session IO failure');await assert.rejects(open(),/native Session IO failure/);assert.equal(creates,0);resolveError=null
 duringVerify=async()=>{await binding.select(origin,null,new AbortController().signal)}
 await assert.rejects(open(),/接入期间已改选或归档/);assert.equal(creates,0)
 duringVerify=async()=>{};await binding.select(origin,baseline,new AbortController().signal)
 workspaces.length=0
 const ungrouped=await open();assert.equal(ungrouped.sessionId,agent.id);assert.equal(ungrouped.workspaceId,undefined);assert.equal(creates,0)
 archived.push(agent.id)
 const fallback=await open();assert.notEqual(fallback.sessionId,agent.id);assert.equal(creates,1,'an already archived exact source uses normal native creation')
 console.log('Menu Session reuse: exact busy/ungrouped native identity, no writes, stale endpoint/owner/HIP rejection, archive race and IO propagation passed')
}finally{await ctx.fiber.dispose()}
