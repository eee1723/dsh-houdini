// Real DSH native/nested tools and a real isolated HOM Bridge; only the model is scripted.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import {randomUUID} from 'node:crypto'
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import {setSandboxMode} from '@deepseek-ai/dsh-sandbox-policy'

export const inject=['loader','llm','sessions','agents','sessionController','sandboxPolicy']
export function apply(ctx) {
  const output=process.env.DSH_HDA_TEST_OUT, workspace=path.dirname(output)
  const library=path.join(workspace,'package','otls','asset.hda')
  let steps=0, failure
  const receipts=[]
  const report=value=>fs.writeFileSync(output,JSON.stringify(value,null,2))
  const text=value=>[{type:'block-start',index:0,blockType:'text'},
    {type:'block-end',index:0,block:{type:'text',text:value}},{type:'finish',reason:{kind:'stop'}}]
  const auth="allow_foreign='Fixture user explicitly authorized this library and selected instance'"
  const calls=[
    ['houdini_inspect',{code:"__result__=verb_help(['hda_version','hda_switch_version'],detail='full')"}],
    ['houdini_exec',{code:`__result__=hda_version('/obj/asset','1.1',${auth})`}],
    ['run_code',{code:'const value = await tools.houdini_exec('+JSON.stringify({code:`hda_switch_version('/obj/asset','fixture::asset::1.1',${auth})\nhda_set_section('/obj/asset','PythonModule','VALUE = 2\\n',${auth})\n__result__=hou.node('/obj/asset').type().name()`})+'); return value;',description:'Switch selected fixture to its native version and edit it'}],
    ['houdini_inspect',{code:"__result__={'selected_type':hou.node('/obj/asset').type().name(),'selected_value':hou.node('/obj/asset').hdaModule().VALUE,'peer_type':hou.node('/obj/peer').type().name(),'peer_value':hou.node('/obj/peer').hdaModule().VALUE,'tool':tool_inspect('node_type','fixture::asset::1.1',category='Object')}"}],
  ]
  class Driver extends LlmAdapter {
    async listModels(){return [{provider:'hda-fixture',id:'scripted',name:'HDA version fixture',inputModalities:['text']}]}
    async resolveModel(provider,id){return {provider,id,name:'HDA version fixture',inputModalities:['text'],context:{contextWindow:300000}}}
    async *stream(options){
      if(options.purpose){yield*text('HDA fixture');return}
      try {
        const step=steps++
        const events=ctx.sessions.get(options.sessionId).snapshotEvents()
        const native=id=>events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId===id)?.data?.meta?.canonical
        if(step>0){
          const message=events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='hda-'+(step-1))
          assert(message && !message.data.message.isError,JSON.stringify(message))
        }
        if(step===2){const r=native('hda-1');assert(r.ok,r.error);assert(r.result.applied);assert.equal(r.result.type,'fixture::asset::1.1');assert.equal(path.resolve(r.result.hda_file),library);receipts.push(r)}
        if(step===3){
          const dispatch=events.find(e=>e.type==='tool/ptc-dispatch'&&e.data?.name==='houdini_exec')
          assert(dispatch&&!dispatch.data.isError,JSON.stringify(dispatch))
          const r=dispatch.data.content.map(b=>{try{return JSON.parse(b.text)}catch{return null}}).find(v=>v?.kind==='dsh-houdini/execution-v1')?.value
          assert(r?.ok,JSON.stringify(dispatch));assert.equal(r.result,'fixture::asset::1.1');receipts.push(r)
        }
        if(step===4){
          const r=native('hda-3');assert.equal(r.result.selected_value,2);assert.equal(r.result.peer_value,1)
          assert.equal(r.result.peer_type,'fixture::asset');assert.equal(r.result.tool.type_version,'1.1')
          assert.equal(r.result.tool.type_versions.length,2);receipts.push(r)
          const ids=new Set(receipts.map(r=>r.execution.executor_id));assert.deepEqual([...ids],[process.env.DSH_HOUDINI_EXECUTOR_ID])
          assert(receipts.every(r=>r.execution.owner_session===options.sessionId))
          yield*text('Native versions verified through the selected Houdini session.');return
        }
        const [name,args]=calls[step];assert(options.tools.some(t=>t.name===name))
        yield {type:'block-start',index:0,blockType:'tool-call'}
        yield {type:'block-end',index:0,block:{type:'tool-call',id:'hda-'+step,name,arguments:JSON.stringify(args)}}
        yield {type:'finish',reason:{kind:'tool-calls'}}
      } catch(error){failure=String(error.stack||error);report({ok:false,error:failure,steps,receipts});throw error}
    }
  }
  ctx.llm.registerAdapter(['hda-fixture'],new Driver())
  ctx.on('agent/created',({agent})=>agent.ctx.tools.presentAs('both'))
  ctx.effect(()=>{queueMicrotask(async()=>{
    try {
      await ctx.loader.await()
      const {sessionId}=await ctx.sessionController.create({cwd:workspace,agentPreset:'houdini'})
      setSandboxMode(ctx.sessions.get(sessionId),'workspace-write')
      await ctx.sessionController.selectModel({sessionId,provider:'hda-fixture',model:'scripted'})
      await ctx.sessionController.prompt({sessionId,requestId:randomUUID(),mode:'queue',content:[{type:'text',text:'Upgrade the fixture asset in its original package library and preserve its peer.'}]},AbortSignal.timeout(90000))
      const agent=ctx.agents.get(sessionId);await agent.whenIdle();assert(!failure,failure);assert.equal(steps,5)
      await ctx.sessions.flush(agent.session)
      report({ok:true,sessionId,steps,receipts,boundary:'Real pinned DSH native/PTC and HOM main-thread Bridge. Scripted model; no GUI/version-menu claim.'})
    } catch(error){report({ok:false,error:String(error.stack||error),steps,receipts})}
  })})
}
