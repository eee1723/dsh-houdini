// Local deterministic adapter: exercises the actual DSH agent loop without a provider request.
import {LlmAdapter,createUserMessage} from '@deepseek-ai/dsh-llm'
import fs from 'node:fs'
import assert from 'node:assert/strict'
export const inject=['llm','tools','sessions']
export function apply(ctx) {
  const attention=process.env.DSH_ATTENTION_FIXTURE==='1', observations=[]
  const failures=(process.env.DSH_ATTENTION_FLUSH_FAILURES||'').split(',').filter(Boolean)
  if(failures.length) {
    const sessions=ctx.get('sessions'), originalFlush=sessions.flush.bind(sessions), completed=[]
    let attempts=0
    sessions.flush=async session=> {
      const events=session.snapshotEvents(),tail=events.at(-1)
      const owned=e=>e?.type==='system/message'&&e.data?.message?.source?.plugin==='dsh-houdini:attention-compaction'
      // Inject at the production notice barrier only. Turn-end/inbox persistence
      // must keep working so the driver can observe and resume each failed turn.
      // No matching caller means the final expected-failure count fails the test.
      // Async ancestry can mention context.js during unrelated persistence.
      // Skip only the observed Cordis forwarding frame to find the direct caller;
      // do not match later async ancestry. A changed stack shape fails the final
      // injected-failure count rather than making this test pass vacuously.
      const frames=String(new Error().stack).split('\n')
      const caller=frames.slice(2).find(frame=>!frame.includes('/@deepseek-ai/cordis/'))||''
      const fromNoticeBarrier=caller.includes(new URL('../../lib/context.js',import.meta.url).href)
      if(attempts<failures.length && events.some(owned) && fromNoticeBarrier) {
        const outcome=failures[attempts++], boundary=tail.seq
        const turnStart=events.findLast(e=>e.type==='turn/start')
        const row={attempt:attempts,turn:turnStart.data.turn,turnStartSeq:turnStart.seq,modelRequests:observations.length,boundary}
        let polls=0
        const ended=()=> {
          const end=session.snapshotEvents().find(e=>e.seq>boundary&&e.type==='turn/end')
          if(end||polls++>=500) {
            completed.push({...row,timeout:!end,error:end?.data?.reason?.error?.message||null})
            const file=process.env.DSH_BINDING_FIXTURE_OUT.replace('passed.json','flush-failures.json')
            fs.writeFileSync(file+'.tmp',JSON.stringify(completed));fs.renameSync(file+'.tmp',file)
          } else setTimeout(ended,10)
        }
        setTimeout(ended,10)
        if(outcome==='throw')throw Error('injected persistence fault')
        return false
      }
      return originalFlush(session)
    }
  }
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
      if(attention) {
        const notices=options.messages.filter(m=>m.source?.plugin==='dsh-houdini'
          &&m.source.sections?.some(s=>s.name==='dsh-houdini:execution-state'))
        assert(notices.length<=4,'actual adapter request must contain at most four execution notices')
        assert(options.messages.some(m=>m.source?.kind==='user'&&m.content.some(c=>c.text==='Run one hundred offline fixture changes.')),
          'original user message must survive every consolidation')
        const system=options.messages.filter(m=>m.role==='system').flatMap(m=>m.content.map(c=>c.text||'')).join('\n')
        assert(system.includes('bounded low-cost visual verification'),'actual preset assembly exposes the new policy')
        assert(system.includes('Ordinary editable models default to node networks plus HIP'))
        assert(system.includes('Pure queries, renaming') && system.includes('Honor explicit no-render/budget constraints'))
        const catalog=options.messages.filter(m=>m.source?.kind==='skill-catalog').flatMap(m=>m.content.map(c=>c.text||'')).join('\n')
        assert(catalog.includes('普通可调模型、独立保存HIP不触发'),'actual skill catalog narrows HDA routing before skill loading')
        if(results>=2) {
          const current=JSON.parse(notices.at(-1).source.sections[0].text.split('\n').slice(1).join('\n'))
          assert.equal(current.checks[0].invalidated_by,'attention-call-'+(results-1),'latest stale evidence is not lost')
        }
        observations.push({results,notices:notices.length,noticeChars:notices.reduce((n,m)=>n+m.content[0].text.length,0)})
        if(results<100) {
          const block={type:'tool-call',id:'attention-call-'+results,name:'houdini_exec',arguments:JSON.stringify({code:'__result__='+results})}
          yield {type:'block-start',index:0,blockType:'tool-call'};yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:'tool-calls'}}
        } else {
          fs.writeFileSync(process.env.DSH_BINDING_FIXTURE_OUT,JSON.stringify({status:'passed',results,bindings,repaired:false,observations}))
          const block={type:'text',text:'One hundred results preserved; current attention bounded.'}
          yield {type:'block-start',index:0,blockType:'text'};yield {type:'block-end',index:0,block};yield {type:'finish',reason:{kind:'stop'}}
        }
        return
      }
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
