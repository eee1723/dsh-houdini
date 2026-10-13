// Real persisted DSH session, ordinary browser prompt and native/nested tools. Scripted model only.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import {randomUUID} from 'node:crypto'
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import {setSandboxMode} from '@deepseek-ai/dsh-sandbox-policy'
export const inject=['loader','llm','sessions','agents','sessionController','sandboxPolicy','workspaceRegistry']
export function apply(ctx){
 const folder=process.env.DSH_RECOVERY_TEST_ROOT,phase=process.env.DSH_RECOVERY_PHASE,sessionId=process.env.DSH_RECOVERY_TASK
 const dirtyChoice=phase==='resume'?process.env.DSH_RECOVERY_DIRTY_CHOICE:''
 const originalChoice=phase==='resume'?process.env.DSH_RECOVERY_ORIGINAL_CHOICE:'',keepDirty=dirtyChoice==='keep'||originalChoice==='keep'
 const saveAs=process.env.DSH_RECOVERY_SAVE_AS==='1',cwd=saveAs?path.join(folder,'original'):folder
 const file=path.join(folder,saveAs?'saved-as/project.hip':'project.hip').replaceAll('\\','/'),output=path.join(folder,phase+'-result.json')
 const report=value=>fs.writeFileSync(output,JSON.stringify(value,null,2));let step=0,failure,modelStarted=false
 const text=function*(value){yield {type:'block-start',index:0,blockType:'text'};yield {type:'block-end',index:0,block:{type:'text',text:value}};yield {type:'finish',reason:{kind:'stop'}}}
 const calls=phase==='save'?[
  ['houdini_exec',{code:`p=tab_create('/obj','geo',name='asset')\nn=tab_create(p,'box',name='source')\n__result__=scene_save_as(${JSON.stringify(file)},scene_info()['hip_path'],'User requested this isolated fixture destination')`}],
  ...(saveAs?[['write',{file_path:'continuation.txt',content:'The same conversation follows Save As.'}]]:[]),
  ['houdini_exec',{code:"set_parms('/obj/asset/source',{'sizex':3})\n__result__=hou.node('/obj/asset/source').parm('sizex').eval()"}],
 ]:[
  ['houdini_inspect',{code:"__result__={'size':hou.node('/obj/asset/source').parm('sizex').eval(),'owner':node_provenance('/obj/asset/source')}"}],
  ['run_code',{code:'return await tools.houdini_exec('+JSON.stringify({code:"set_parms('/obj/asset/source',{'sizex':2.5})\n__result__={'size':hou.node('/obj/asset/source').parm('sizex').eval(),'saved':scene_save()}"})+');',description:'Continue the recovered saved scene through a nested tool'}],
 ]
 class Driver extends LlmAdapter{
  async listModels(){return [{provider:'recovery-fixture',id:'scripted',name:'Recovery fixture',inputModalities:['text']}]}
  async resolveModel(provider,id){return {provider,id,name:'Recovery fixture',inputModalities:['text'],context:{contextWindow:300000}}}
  async *stream(options){
   if(options.purpose){yield*text('Recovery fixture');return}
   try{
    modelStarted=true
    const events=ctx.sessions.get(sessionId).snapshotEvents()
    if(saveAs&&(phase==='resume'||step>0)){
     assert.equal(path.resolve(ctx.sessions.get(sessionId).header.cwd).toLowerCase(),path.resolve(path.dirname(file)).toLowerCase(),'actual session cwd follows the saved HIP')
     if(phase==='save'&&step===1)assert(JSON.stringify(options).includes('Saved-as workspace fixture instructions.'),'next model request receives the new workspace instructions')
     const runtime=events.filter(e=>e.type==='user/message'&&e.data.source?.kind==='runtime-context').at(-1)
     const policy=runtime?.data.source.sections?.find(section=>section.name==='sandbox-policy')
     assert(JSON.stringify(policy??runtime).toLowerCase().includes('saved-as'),'model runtime context must use the relocated file policy immediately')
    }
    if(phase==='resume'&&step===0){
     assert(events.some(e=>e.type==='user/message'&&e.data.source?.kind==='user'
       &&e.data.content?.some(part=>part.type==='text'&&part.text==='继续')),
       'the resumed turn must originate from the actual browser composer')
     if(keepDirty){
      assert(!events.some(e=>e.type==='user/message'&&e.data.source?.sections?.some(s=>s.text.includes('"kind":"executor_recovery"'))),
        'keeping unsaved edits must not rebind or reload the scene')
      assert(events.some(e=>e.type==='user/message'&&e.data.source?.sections?.some(s=>s.name==='dsh-houdini:recovery-required'
        &&s.text.includes(originalChoice?'已保留当前工程':'已保留当前未保存内容'))),'the native keep choice must reach the model as the actual recovery outcome')
      yield*text('Fixture kept the unsaved scene and continued the conversation without live tools.');return
     }
     assert(events.some(e=>e.type==='user/message'&&e.data.source?.sections?.some(s=>s.name==='dsh-houdini:executor-binding'
       &&s.text.includes('"kind":"executor_recovery"'))),
       'automatic recovery must commit before the first model tool call')
    }
    if(step){
     const result=events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId===phase+'-'+(step-1))
     assert(result&&!result.data.message.isError,JSON.stringify(result))
     if(phase==='resume'&&step===1){
      const value=result.data.meta.canonical;assert(value.ok,JSON.stringify(value));assert.equal(value.result.size,1,'unsaved old progress must not masquerade as saved')
      assert.equal(value.result.owner.status,'owned_current_session');assert.equal(value.execution.executor_id,process.env.DSH_HOUDINI_EXECUTOR_ID)
     }
    }
    if(step===calls.length){yield*text(phase==='resume'?'Fixture resumed through the normal conversation.':'Fixture complete');return}
    const [name,args]=calls[step],id=phase+'-'+step++
    assert(options.tools.some(t=>t.name===name),name)
    yield {type:'block-start',index:0,blockType:'tool-call'}
    yield {type:'block-end',index:0,block:{type:'tool-call',id,name,arguments:JSON.stringify(args)}}
    yield {type:'finish',reason:{kind:'tool-calls'}}
   }catch(error){failure=String(error.stack||error);report({ok:false,error:failure});throw error}
  }
 }
 ctx.llm.registerAdapter(['recovery-fixture'],new Driver())
 ctx.on('agent/created',({agent})=>agent.ctx.tools.presentAs('both'))
 ctx.effect(()=>{queueMicrotask(async()=>{
  try{
   await ctx.loader.await()
   if(phase==='save'){
    const workspace=await ctx.workspaceRegistry.create(cwd)
    await ctx.sessionController.create({sessionId,workspaceId:workspace.id,agentPreset:'houdini'})
    setSandboxMode(ctx.sessions.get(sessionId),'workspace-write')
    await ctx.sessionController.selectModel({sessionId,provider:'recovery-fixture',model:'scripted'})
    if(saveAs){
     fs.writeFileSync(path.join(folder,'save-ready.json'),JSON.stringify({sessionId}))
     const deadline=Date.now()+90000
     while(!modelStarted&&!failure){assert(Date.now()<deadline,'Save As browser prompt timeout');await new Promise(r=>setTimeout(r,100))}
    }
   }else{
    await ctx.sessionController.resolveAgent(sessionId)
    assert.equal(step,0,'opening a saved task must not run a model turn')
    fs.writeFileSync(path.join(folder,'resume-ready.json'),JSON.stringify({sessionId}))
    const deadline=Date.now()+90000
    while(!modelStarted&&!failure){assert(Date.now()<deadline,'ordinary browser prompt timeout');await new Promise(r=>setTimeout(r,100))}
   }
   if(phase==='save'&&!saveAs)await ctx.sessionController.prompt({sessionId,requestId:randomUUID(),mode:'queue',content:[{type:'text',text:'Build, save, then make an unsaved fixture change.'}]},AbortSignal.timeout(90000))
   const agent=ctx.agents.get(sessionId);await agent.whenIdle();assert(!failure,failure);assert.equal(step,keepDirty?0:calls.length)
   if(saveAs){assert(fs.existsSync(path.join(path.dirname(file),'continuation.txt')));assert(!fs.existsSync(path.join(cwd,'continuation.txt')))}
   assert(await ctx.sessions.flush(agent.session))
   const events=agent.session.snapshotEvents()
   const receipts=events.filter(e=>e.type==='tool/result').map(e=>e.data.meta?.canonical).filter(Boolean)
   if(keepDirty){
    assert.equal(events.filter(e=>e.type==='tool/call'&&e.data.callId.startsWith('resume-')).length,0)
    assert.equal(events.filter(e=>e.type==='user/message'&&e.data.source?.sections?.some(s=>s.text.includes('"kind":"executor_recovery"'))).length,0)
   }else if(phase==='resume'){
    const nested=events.filter(e=>e.type==='tool/ptc-dispatch'&&e.data.name==='houdini_exec').at(-1)
    const result=nested?.data.content.map(x=>{try{return JSON.parse(x.text)}catch{return null}}).find(x=>x?.kind==='dsh-houdini/execution-v1')?.value
    assert(result?.ok,JSON.stringify(nested));assert.equal(result.result.size,2.5)
    assert.equal(result.execution.owner_session,sessionId);assert.equal(result.execution.executor_id,process.env.DSH_HOUDINI_EXECUTOR_ID)
    assert.equal(events.filter(e=>e.type==='user/message'&&e.data.source?.sections?.some(s=>s.text.includes('"kind":"executor_recovery"'))).length,1)
   }
   report({ok:true,sessionId,phase,dirtyChoice,receipts,boundary:'Real persisted DSH, ordinary browser continuation, automatic recovery or native conversation choice, real HOM; scripted model, no autonomous quality claim.'})
  }catch(error){report({ok:false,error:String(error.stack||error)})}
 })})
}
