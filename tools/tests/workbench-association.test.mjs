import assert from 'node:assert/strict'
import path from 'node:path'
import {Context} from '@deepseek-ai/cordis'
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection'
import {agentPresetProjectionDefinition} from '@deepseek-ai/dsh-agent-preset-registry'
import {ExecutorController} from '../../lib/executor-controller.js'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {registerExecutorIdentityProjection,foldExecutorState} from '../../lib/executor-identity-projection.js'
import {fixtureSession} from './fixture-session.mjs'
const ctx=new Context(),projections=new SessionProjectionRegistry(ctx)
projections.register(agentPresetProjectionDefinition);registerExecutorIdentityProjection(ctx)
const executor='a'.repeat(32),signal=new AbortController().signal,cwd=path.resolve('tools/out/original-files')
const record={executor_id:executor,registration_id:'b'.repeat(32),runtime_id:'c'.repeat(32),scene_epoch:'d'.repeat(32),scene_id:'e'.repeat(32),
  workbench:true,state:'registered',hip_path:path.resolve('tools/out/different-project/asset.hip'),hip_is_new:false,
  workspace_path:path.resolve('tools/out/different-project')}
const agents=new Map(),created=[],selected=[]
const old=fixtureSession('old-conversation',{agentPreset:'houdini',cwd})
old.append('tool/call',{callId:'already-executed',name:'houdini_exec',arguments:'{}'})
agents.set(old.id,{id:old.id,status:'idle',session:old})
ctx.provide('agents',{get:id=>agents.get(id)})
ctx.provide('workspaceRegistry',{list:()=>[{id:'old-workspace',path:cwd,title:'old',sessionIds:[old.id]}],archivedSessionIds:[],
  create:async directory=>({id:'new-workspace',path:directory,title:'new',sessionIds:[]}),
  relocateSession(){throw Error('target selection must not move cwd')}})
ctx.provide('sessions',{flush:async()=>true})
ctx.provide('sessionQuery',{readSession(){throw Error('Open Workspace must never scan conversation histories')}})
ctx.provide('sessionController',{resolveAgent:async id=>({agent:agents.get(id)}),create:async request=>{
  created.push(request);const session=fixtureSession(request.sessionId,{agentPreset:'houdini',cwd:record.workspace_path})
  agents.set(session.id,{id:session.id,status:'idle',session});return {sessionId:session.id}
}})
const binding=new ExecutorBinding()
const snapshot={executor_id:record.executor_id,registration_id:record.registration_id,runtime_id:record.runtime_id,
  scene_epoch:record.scene_epoch,scene_id:record.scene_id,hip_path:record.hip_path,hip_is_new:false,workspace_path:record.workspace_path}
const controller=new ExecutorController(ctx,{directory:{find:async()=>record},selectTarget:async agent=>{
  selected.push(agent.id);await binding.select(agent.session,snapshot);return snapshot
}},true)
const input={executorId:executor,registrationId:record.registration_id,expectedHip:record.hip_path,requestId:'f'.repeat(32)}
await assert.rejects(controller.openWorkspace({...input,registrationId:'0'.repeat(32)},signal),/发生变化/)
assert.equal(created.length,0,'a stale open must not create a native conversation')
const existing=await controller.openWorkspace({...input,sessionId:old.id},signal)
assert.equal(existing.sessionId,old.id)
assert.equal(existing.workspaceId,'old-workspace')
assert.equal(created.length,0)
assert.equal(old.header.cwd,cwd,'explicit existing conversation keeps its file workspace')
assert.equal(foldExecutorState(old.snapshotEvents()).selectedTarget.executor_id,executor)
const opened=await controller.openWorkspace(input,signal)
assert.equal(created.length,1)
assert.equal(opened.sessionId,input.requestId)
assert.equal(opened.workspaceId,'new-workspace')
assert.equal(created[0].agentPreset,'houdini')
assert.deepEqual(selected,[old.id,input.requestId])
assert.equal(old.header.cwd,cwd)
await ctx.fiber.dispose()
console.log('Open Workspace: exact executed conversation or native new draft, no history scan, writer, recovery or cwd migration')
