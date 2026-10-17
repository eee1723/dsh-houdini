// Native DSH profile fixture: identity/history, metadata, permissions and real file tools.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import {randomUUID} from 'node:crypto'
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import {setSandboxMode} from '@deepseek-ai/dsh-sandbox-policy'
import {pruneScratchWorkspaces} from '../../lib/workbench-workspaces.js'
import {fixtureSession} from './fixture-session.mjs'
export const inject=['loader','llm','sessions','agents','sessionController','workspaceRegistry','sessionPersistence','sandboxPolicy']
export function apply(ctx){
 const root=process.env.DSH_WORKSPACE_TEST_ROOT,phase=process.env.DSH_WORKSPACE_TEST_PHASE,id=process.env.DSH_WORKSPACE_TEST_TASK
 const source=path.join(root,'original'),target=path.join(root,phase==='relocate'?'saved-as':'renamed-again')
 const same=(a,b)=>path.resolve(a).toLowerCase()===path.resolve(b).toLowerCase()
 const report=value=>fs.writeFileSync(path.join(root,phase+'-result.json'),JSON.stringify(value,null,2))
 let step=0,failure
 class Driver extends LlmAdapter{
  async listModels(){return [{provider:'workspace-fixture',id:'scripted',name:'Workspace fixture',inputModalities:['text']}]}
  async resolveModel(provider,id){return {provider,id,name:'Workspace fixture',inputModalities:['text'],context:{contextWindow:300000}}}
  async *stream(options){
   if(options.purpose){yield {type:'finish',reason:{kind:'stop'}};return}
   try{
    const session=ctx.sessions.get(id)
    assert(same(session.header.cwd,target))
    assert(same(ctx.sandboxPolicy.resolve({session}).workspaceRoot,target))
    if(step===0)await assert.rejects(ctx.sessions.relocate(session,source),/step boundary/)
    if(step++===0){
     assert(options.tools.some(t=>t.name==='write'))
     yield {type:'block-start',index:0,blockType:'tool-call'}
     yield {type:'block-end',index:0,block:{type:'tool-call',id:'write-'+phase,name:'write',arguments:JSON.stringify({file_path:phase+'.txt',content:'same conversation in new directory'})}}
     yield {type:'finish',reason:{kind:'tool-calls'}}
    }else{
     assert(fs.existsSync(path.join(target,phase+'.txt')))
     assert(!fs.existsSync(path.join(source,phase+'.txt')))
     yield {type:'block-start',index:0,blockType:'text'}
     yield {type:'block-end',index:0,block:{type:'text',text:'Workspace continuation verified.'}}
     yield {type:'finish',reason:{kind:'stop'}}
    }
   }catch(error){failure=String(error.stack||error);report({ok:false,error:failure});throw error}
  }
 }
 ctx.llm.registerAdapter(['workspace-fixture'],new Driver())
 ctx.on('agent/created',({agent})=>agent.ctx.tools.presentAs('both'))
 ctx.effect(()=>{queueMicrotask(async()=>{try{
  await ctx.loader.await()
  let before
  if(phase==='interrupted'){
   fs.mkdirSync(target,{recursive:true})
   await ctx.sessionController.resolveAgent(id)
   const relocate=ctx.sessions.relocate.bind(ctx.sessions)
   ctx.sessions.relocate=async(...args)=>{
    await relocate(...args)
    report({ok:true,phase,point:'metadata committed; workspace membership pending'})
    await new Promise(()=>{})
   }
   await ctx.workspaceRegistry.relocateSession(id,target)
   return
  }
  if(phase==='relocate'){
   fs.mkdirSync(source,{recursive:true});fs.mkdirSync(target,{recursive:true})
   await ctx.sessionController.create({sessionId:id,cwd:source})
   const session=ctx.sessions.get(id)
   fs.writeFileSync(path.join(source,'source-only.txt'),'source')
   fs.writeFileSync(path.join(target,'target-only.txt'),'target')
   const references=ctx.get('fileReferences'),agent=ctx.agents.get(id)
   assert(JSON.stringify(await references.list(agent,'source-only',AbortSignal.timeout(10000))).includes('source-only'))
   setSandboxMode(session,'workspace-write')
   await ctx.sessionController.selectModel({sessionId:id,provider:'workspace-fixture',model:'scripted'})
   await ctx.sessions.flush(session)
   before=session.snapshotEvents().map(event=>JSON.stringify(event))
   fs.writeFileSync(path.join(root,'prefix.json'),JSON.stringify(before))
   const createdAt=session.header.createdAt
   const replace=ctx.sessionPersistence.replaceHeader.bind(ctx.sessionPersistence)
   ctx.sessionPersistence.replaceHeader=async()=>{throw new Error('fixture metadata write failure')}
   await assert.rejects(ctx.workspaceRegistry.relocateSession(id,target),/fixture metadata write failure/)
   assert(same(session.header.cwd,source),'failed persistence must not publish a new live cwd')
   assert(same((await ctx.sessionPersistence.stat(id)).header.cwd,source),'failed persistence retains original durable cwd')
   ctx.sessionPersistence.replaceHeader=replace
   await ctx.workspaceRegistry.relocateSession(id,target)
   const candidates=JSON.stringify(await references.list(agent,'target-only',AbortSignal.timeout(10000)))
   assert(candidates.includes('target-only'),'file mention search must drop its old directory cache')
   assert.equal(ctx.sessions.get(id),session);assert.equal(session.header.createdAt,createdAt)
   assert.deepEqual(session.snapshotEvents().map(event=>JSON.stringify(event)),before)
   await ctx.workspaceRegistry.relocateSession(id,target)
   // An interrupted final frame must be repaired using its old byte offset.
   const tornId=randomUUID(),torn=fixtureSession(tornId,{createdAt:0,cwd:source,seed:undefined})
   const writer=await ctx.sessionPersistence.create(torn.header);await writer.flush();await writer.close()
   const store=ctx.sessionPersistence.root
   const physical=fs.readdirSync(store,{recursive:true}).find(name=>name.includes(torn.id)&&name.endsWith('.jsonl.zstd'))
   assert(physical)
   fs.appendFileSync(path.join(store,physical),Buffer.from([0x28,0xb5,0x2f,0xfd]))
   const repaired=await ctx.sessionPersistence.open(torn.id,'write')
   await repaired.relocate(target)
   torn.append('turn/start',{turn:1});await repaired.append(torn.snapshotEvents());await repaired.close()
   const read=await ctx.sessionPersistence.open(torn.id,'read')
   assert.equal((await read.read()).events.length,1);assert(same(read.header.cwd,target));await read.close()
   // Native conditional removal: only plugin scratch rows; all data stays put.
   const scratch=path.join(root,'scratch');fs.mkdirSync(scratch)
   const create=async(suffix,title)=>{
    const directory=path.join(scratch,'untitled-123-'+suffix);fs.mkdirSync(directory)
    return ctx.workspaceRegistry.create(directory,title??'未保存工程 7')
   }
   const empty=await create('empty'),files=await create('files'),active=await create('active'),renamed=await create('renamed','我保留的工作区')
   fs.writeFileSync(path.join(files.path,'keep.txt'),'user material')
   const archived=await create('archive'),archivedId=randomUUID()
   await ctx.sessionController.create({sessionId:archivedId,workspaceId:archived.id})
   await ctx.workspaceRegistry.archiveSession(archivedId)
   const racing=await create('racing'),racingId=randomUUID()
   await ctx.sessionController.create({sessionId:racingId,workspaceId:racing.id})
   assert.equal(await ctx.workspaceRegistry.deleteEmpty(racing.id,racing.path,racing.title),false)
   const retitled=await create('retitled'),originalTitle=retitled.title
   const titleWrite=retitled.setTitle('需要保留')
   const removal=ctx.workspaceRegistry.deleteEmpty(retitled.id,retitled.path,originalTitle)
   await titleWrite;assert.equal(await removal,false,'a queued user rename wins over cleanup')
   const removed=await pruneScratchWorkspaces(ctx,{list:async()=>[{state:'registered',workspace_path:active.path}]},[target],[scratch])
   assert.deepEqual(removed,[empty.id])
   assert(fs.existsSync(empty.path),'pruning never deletes the scratch directory')
   assert(!ctx.workspaceRegistry.list().some(item=>item.id===empty.id))
   for(const item of [files,active,renamed,archived,racing,retitled])assert(ctx.workspaceRegistry.list().some(value=>value.id===item.id))
   assert((await ctx.sessionPersistence.stat(archivedId)).header,'archived conversation is retained')
   fs.writeFileSync(path.join(root,'pruned-workspace.json'),JSON.stringify({id:empty.id,path:empty.path}))
  }else{
   const cold=(await ctx.sessionPersistence.stat(id)).header
   assert(same(cold.cwd,target),'cold metadata must follow the new directory')
   await ctx.sessionController.resolveAgent(id)
   before=JSON.parse(fs.readFileSync(path.join(root,'prefix.json'),'utf8'))
   assert.deepEqual(ctx.sessions.get(id).snapshotEvents().slice(0,before.length).map(event=>JSON.stringify(event)),before)
   const pruned=JSON.parse(fs.readFileSync(path.join(root,'pruned-workspace.json'),'utf8'))
   assert(!ctx.workspaceRegistry.list().some(item=>item.id===pruned.id),'empty registration stays removed after restart')
   assert(fs.existsSync(pruned.path))
  }
  const membership=ctx.workspaceRegistry.list().filter(w=>w.sessionIds.includes(id))
  assert.equal(membership.length,1);assert(same(membership[0].path,target))
  const items=(await ctx.sessionController.list({},AbortSignal.timeout(10000))).items
  assert(same(items.find(item=>item.id===id||item.sessionId===id).cwd,target),'actual API list must show new directory')
  await ctx.sessionController.prompt({sessionId:id,requestId:randomUUID(),mode:'queue',content:[{type:'text',text:'Continue in the saved-as project.'}]},AbortSignal.timeout(30000))
  await ctx.agents.get(id).whenIdle();assert(!failure,failure);assert.equal(step,2)
  await ctx.sessions.flush(ctx.sessions.get(id))
  report({ok:true,phase,sessionId:id,cwd:ctx.sessions.get(id).header.cwd,historyPreserved:before.length})
 }catch(error){report({ok:false,error:String(error.stack||error)})}})})
}
