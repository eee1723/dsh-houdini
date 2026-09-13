// Local deterministic adapter: exercises the actual DSH agent loop without a provider request.
import {LlmAdapter,createUserMessage} from '@deepseek-ai/dsh-llm'
import fs from 'node:fs'
import assert from 'node:assert/strict'
export const inject=['llm','tools']
export function apply(ctx) {
  if(process.env.DSH_BINDING_REPAIR_FIXTURE==='1') {
    let inserted=false
    ctx.on('tools/pre-execute',async(exec,next)=>{
      if(!inserted&&exec.name==='houdini_query') {
        inserted=true
        const original=exec.agent.session.snapshotEvents().find(e=>e.type==='user/message'&&e.data.source?.plugin==='dsh-houdini'
          &&e.data.source.sections?.some(s=>s.name==='dsh-houdini:executor-binding')).data
        // Deliberately reproduce the retired bug in this isolated test only.
        exec.agent.session.append('user/message',createUserMessage({content:original.content,source:original.source}),{surfaceOp:'append'})
      }
      return next()
    })
  }
  class Fixture extends LlmAdapter {
    async resolveModel(provider,model) {return {provider,id:model,name:'Binding loop fixture',inputModalities:['text'],context:{contextWindow:500000}}}
    async *stream(options) {
      const pending=new Set();let results=0,bindings=0,repaired=false
      for(const message of options.messages) {
        const replies=message.content.filter(c=>c.type==='tool-result')
        assert(!pending.size||replies.length,'binding message interrupted a pending tool batch')
        for(const c of message.content) {
          if(c.type==='tool-call')pending.add(c.id)
          if(c.type==='tool-result') {assert(pending.delete(c.toolCallId));assert(!c.isError,JSON.stringify(c));results++}
        }
        if(message.source?.plugin==='dsh-houdini'&&message.source.sections?.some(s=>s.name==='dsh-houdini:executor-binding'))bindings++
        const recovery=message.source?.plugin==='dsh-houdini'&&message.source.sections?.find(s=>s.name==='dsh-houdini:binding-order-repair')
        if(recovery) {
          const original=JSON.parse(recovery.text.slice(recovery.text.indexOf('\n')+1))
          assert.equal(original.results.length,2)
          assert(original.results.every(r=>!r.is_error))
          results+=original.results.length;repaired=true
        }
      }
      assert.equal(pending.size,0)
      if(options.purpose) {
        const block={type:'text',text:'Binding fixture'}
        yield {type:'block-start',index:0,blockType:'text'};yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:'stop'}};return
      }
      assert.equal(bindings,1,'normal pre-step acceptance must deliver exactly one binding')
      if(results===0) {
        for(let index=0;index<2;index++) {
          const block={type:'tool-call',id:'fixture-call-'+index,name:'houdini_query',arguments:JSON.stringify({code:'__result__='+index})}
          yield {type:'block-start',index,blockType:'tool-call'}
          yield {type:'block-end',index,block}
        }
        yield {type:'finish',reason:{kind:'tool-calls'}}
      } else {
        assert.equal(results,2)
        assert.equal(repaired,process.env.DSH_BINDING_REPAIR_FIXTURE==='1')
        fs.writeFileSync(process.env.DSH_BINDING_FIXTURE_OUT,JSON.stringify({status:'passed',results,bindings,repaired,session:options.sessionId}))
        const block={type:'text',text:'Both query results received; protocol valid.'}
        yield {type:'block-start',index:0,blockType:'text'};yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:'stop'}}
      }
    }
  }
  ctx.llm.registerAdapter(['binding-fixture'],new Fixture())
}
