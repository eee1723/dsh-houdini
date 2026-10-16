import fs from 'node:fs'
import path from 'node:path'
import {randomUUID} from 'node:crypto'
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import {executionResult} from '../../lib/dsh-adapter.js'

export const inject=['sessionController','sessions','agentPresets','houdiniTargets','tools','llm','sessionTitle','workspaceRegistry']
export function apply(ctx) {
  const folder=process.env.DSH_WORKBENCH_TEST_ROOT
  if(!folder||!path.isAbsolute(folder))throw Error('Isolated workbench fixture root required')
  const scripts=new Map(),provider='workbench-fixture',model='scripted-local'
  const textChunks=text=>[{type:'block-start',index:0,blockType:'text'},
    {type:'block-end',index:0,block:{type:'text',text}},{type:'finish',reason:{kind:'stop'}}]
  class WorkbenchFixture extends LlmAdapter {
    async listModels(){return [{provider,id:model,name:'Isolated workbench fixture',inputModalities:['text']}]}
    async resolveModel(route,id){return {provider:route,id,name:'Isolated workbench fixture',inputModalities:['text'],context:{contextWindow:500000}}}
    async *stream(options){
      if(options.purpose){await new Promise(resolve=>setTimeout(resolve,350));yield* textChunks('Workbench fixture');return}
      const script=scripts.get(options.sessionId)
      if(!script)throw Error('Unrequested model turn in isolated fixture')
      if(script.tool===null){yield* textChunks('We are discussing the project before opening Houdini.');return}
      const events=ctx.sessions.get(options.sessionId).snapshotEvents()
      if(events.some(event=>event.type==='tool/result'&&event.data?.message?.source?.callId===script.id)) {
        yield* textChunks('Isolated workbench operation completed.');return
      }
      if(!options.tools.some(tool=>tool.name===script.tool))throw Error('Tool missing from actual request: '+script.tool)
      yield {type:'block-start',index:0,blockType:'tool-call'}
      yield {type:'block-end',index:0,block:{type:'tool-call',id:script.id,name:script.tool,arguments:JSON.stringify(script.args)}}
      yield {type:'finish',reason:{kind:'tool-calls'}}
    }
  }
  ctx.llm.registerAdapter([provider],new WorkbenchFixture())
  ctx.on('agent/created',({agent})=>{agent.ctx.tools.presentAs('both')})
  let active=false,handled
  ctx.effect(()=>{
    const timer=setInterval(async()=>{
      if(active||!fs.existsSync(path.join(folder,'command.json')))return
      const input=JSON.parse(fs.readFileSync(path.join(folder,'command.json'),'utf8'))
      if(input.id===handled)return
      active=true;handled=input.id
      let response
      try {
        const resolved=await ctx.sessionController.resolveAgent(input.sessionId)
        if(resolved.error)throw Error(JSON.stringify(resolved.error))
        const agent=resolved.agent,signal=AbortSignal.timeout(40000)
        const recovery=ctx.agentPresets.serviceFor(agent,'houdiniRecovery')
        if(input.action==='idle') {
          response={ok:true,idle:agent.status==='idle',started:agent.session.snapshotEvents().some(event=>event.type==='turn/start'),
            turns:agent.session.snapshotEvents().filter(event=>event.type==='turn/start').length,
            title:ctx.sessionTitle.get(agent.session)??null,
            workspaces:ctx.workspaceRegistry.list().map(workspace=>({id:workspace.id,path:workspace.path,sessionIds:workspace.sessionIds}))}
        } else if(input.action==='pinTitle') {
          ctx.sessionTitle.rename(agent.session,'旧工程标题.hip')
          response={ok:true}
        } else if(input.action==='beforeStep') {
          await recovery.followDirectory(agent,signal,true)
          await recovery.beforeStep(agent,signal)
          response={ok:true,cwd:agent.session.header.cwd,events:agent.session.snapshotEvents()}
        } else {
          scripts.set(agent.id,input)
          await ctx.sessionController.selectModel({sessionId:agent.id,provider,model})
          await ctx.sessionController.prompt({sessionId:agent.id,requestId:randomUUID(),mode:'queue',
            content:[{type:'text',text:'Perform the isolated workbench fixture operation.'}]},signal)
          await agent.whenIdle()
          const events=agent.session.snapshotEvents()
          if(input.tool===null) {
            scripts.delete(agent.id)
            response={ok:true,events}
          } else {
          const result=events.find(event=>event.type==='tool/result'&&event.data?.message?.source?.callId===input.id)
          if(!result)throw Error('The actual agent loop produced no expected tool receipt')
          const nested=input.tool==='run_code'?events.filter(event=>event.type==='tool/ptc-dispatch'
            &&event.data.subCallId.startsWith(input.id+':')).at(-1):undefined
          const observed=executionResult(nested??result)
          response={ok:true,value:observed?.value??{ok:false,error:observed?.error??result.data.message.content}}
          scripts.delete(agent.id)
          }
        }
        if(await ctx.sessions.flush(agent.session)!==true)throw Error('Fixture persistence did not flush')
      }catch(error){response={ok:false,error:String(error.stack||error)}}
      fs.writeFileSync(path.join(folder,'result.json'),JSON.stringify({id:input.id,...response}))
      active=false
    },80)
    return ()=>clearInterval(timer)
  })
}
