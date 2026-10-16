import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import {createUserMessage,createToolResultMessage} from '@deepseek-ai/dsh-llm'
import {houdiniSnapshot} from '../../lib/dsh-adapter.js'
import {ExecutorBinding} from '../../lib/executor-binding.js'

export const inject=['loader','sessions','sessionController','workspaceRegistry','houdiniFrontend','sessionPersistence']
export function apply(ctx) {
  ctx.effect(()=>{(async()=>{
    const folder=process.env.DSH_SUPPORT_TEST_ROOT
    const write=value=>fs.writeFileSync(path.join(folder,'ready.json'),JSON.stringify(value))
    try {
      const workspace=await ctx.workspaceRegistry.create(path.join(folder,'project'))
      for(const [sessionId,text] of [['support-selected','SELECTED_PRIVATE_CONTENT'],['support-other','OTHER_PRIVATE_CONTENT']]) {
        await ctx.sessionController.create({sessionId,workspaceId:workspace.id,agentPreset:'houdini'})
        const session=ctx.sessions.get(sessionId)
        if(sessionId==='support-selected')for(let index=0;index<2100;index++) {
          session.append('user/message',createUserMessage({content:[{type:'text',text:'older fixture event '+index}],source:{kind:'user'}}),{surfaceOp:'append'})
        }
        session.append('user/message',createUserMessage({content:[{type:'text',text}],source:{kind:'user'}}),{surfaceOp:'append'})
        await new ExecutorBinding().ensure(session,'a'.repeat(32))
        session.append('user/message',houdiniSnapshot({name:'dsh-houdini:recovery-required',text:'diagnostic\n'+JSON.stringify({
          executor_id:'b'.repeat(32),reason:'CHECKPOINT_UNAVAILABLE token=PRIVATE_LAUNCH_TOKEN'})}),{surfaceOp:'append'})
        assert(await ctx.sessions.flush(session))
      }
      const report=await ctx.houdiniFrontend.supportReport({sessionId:'support-selected',description:'DSH actual persistence',
        includeContent:false,includeLogs:false,includePrevious:false},AbortSignal.timeout(30000))
      const encoded=JSON.stringify(report.files)
      assert(encoded.includes('CHECKPOINT_UNAVAILABLE'))
      assert(!encoded.includes('PRIVATE_LAUNCH_TOKEN'))
      assert(!encoded.includes('SELECTED_PRIVATE_CONTENT'))
      assert(!encoded.includes('OTHER_PRIVATE_CONTENT'))
      const manifest=JSON.parse(report.files.find(file=>file.name==='manifest.json').text)
      assert(manifest.session.total_events>2100)
      assert(manifest.missing.includes('history_middle_omitted'))
      fs.writeFileSync(path.join(folder,'native-report.zip'),Buffer.from(report.archiveBase64,'base64'))
      write({ok:true,sessionId:'support-selected'})
    }catch(error){write({ok:false,error:String(error.stack||error)})}
  })()})
}
