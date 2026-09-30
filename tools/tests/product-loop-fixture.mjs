// Deterministic local adapter for the actual DSH tool/result -> session -> model loop.
// No provider requests, Houdini process, or synthetic product receipt insertion.
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import {Session} from '@deepseek-ai/dsh-session'
import {productState,productCoverage} from '../../lib/product-definition.js'
import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'

export const inject=['llm','tools','sessions']
export function apply(ctx) {
  const normalized=new Map(),observations=[]
  const productMode=process.env.DSH_PRODUCT_FIXTURE_MODE==='1'
  let session,definition
  ctx.on('tools/result',(exec,result)=>{
    if(!exec.callId.startsWith('product-fixture-'))return
    session=exec.agent.session
    normalized.set(exec.callId,result)
  })
  const calls={source:'product-fixture-source',workflow:'product-fixture-workflow',invalid:'product-fixture-invalid',define:'product-fixture-define',read:'product-fixture-read',
    check:'product-fixture-check',bind:'product-fixture-bind',review:'product-fixture-review',final:'product-fixture-final'}
  function resultsOf(options) {
    const pending=new Set(),results=new Map()
    for(const message of options.messages) {
      const replies=message.content.filter(c=>c.type==='tool-result')
      assert(!pending.size||replies.length,'context must not interrupt an unresolved tool batch')
      for(const block of message.content) {
        if(block.type==='tool-call')pending.add(block.id)
        if(block.type==='tool-result') {
          assert(pending.delete(block.toolCallId),'result must match an actual call')
          assert(block.toolCallId===calls.invalid?block.isError:!block.isError,JSON.stringify(block))
          results.set(block.toolCallId,block.content.filter(c=>c.type==='text').map(c=>c.text).join('\n'))
        }
      }
    }
    assert.equal(pending.size,0)
    return results
  }
  function notice(options,name) {
    const sections=options.messages.filter(m=>m.source?.plugin==='dsh-houdini')
      .flatMap(m=>m.source.sections??[]).filter(s=>s.name===name)
    const last=sections.at(-1)
    return last?JSON.parse(last.text.slice(last.text.indexOf('\n')+1)):null
  }
  function* call(id,name,args) {
    yield {type:'block-start',index:0,blockType:'tool-call'}
    yield {type:'block-end',index:0,block:{type:'tool-call',id,name,arguments:JSON.stringify(args)}}
    yield {type:'finish',reason:{kind:'tool-calls'}}
  }
  function* stop(text) {
    yield {type:'block-start',index:0,blockType:'text'}
    yield {type:'block-end',index:0,block:{type:'text',text}}
    yield {type:'finish',reason:{kind:'stop'}}
  }
  class Fixture extends LlmAdapter {
    async resolveModel(provider,model) {
      return {provider,id:model,name:'Offline product loop fixture',inputModalities:['text'],context:{contextWindow:500000}}
    }
    async *stream(options) {
      if(options.purpose) {yield* stop('Offline product loop fixture');return}
      const results=resultsOf(options)
      const promptText=options.messages.flatMap(m=>m.content.filter(b=>b.type==='text').map(b=>b.text)).join('\n')
      assert(promptText.includes('houdini_product is an optional record')&&promptText.includes('Simple edits can proceed directly'),
        'the actual model input keeps product records optional')
      const visual=notice(options,'dsh-houdini:visual-capability')
      assert.equal(visual?.status,'unsupported','the first real model request must receive the text-only route preflight')
      assert.equal(visual.image_input,false)
      assert.equal(visual.semantic_status,'unverified')
      assert.equal(visual.provider,'product-fixture')
      const product=notice(options,'dsh-houdini:execution-state')?.product
      observations.push({results:results.size,visual:visual.status,product})
      if(productMode) assert(promptText.includes('Focus on editable product models'),
        'product focus contributes domain guidance to the same normal loop')
      for(const result of normalized.values()) assert(!Object.hasOwn(result.meta?.canonical??{},'admission'),
        'product focus must not add an execution admission layer')
      if(!results.has(calls.source)) {
        yield* call(calls.source,'houdini_query',{source_ref:'index'});return
      }
      if(!results.has(calls.workflow)) {
        yield* call(calls.workflow,'skill',{name:'houdini-sop-workflow'});return
      }
      if(!results.has(calls.invalid)) {
        yield* call(calls.invalid,'houdini_product',{action:'define',expected_revision:0,change_reason:'Deliberately malformed fixture',
          definition:{title:'Invalid',requirements:[{id:'invalid',kind:'invalid-kind',description:'Invalid schema'}]}});return
      }
      const invalidText=results.get(calls.invalid)
      assert(['subjects','state','checks'].every(key=>invalidText.includes(key)),'typed schema returns all missing requirement fields')
      assert(!normalized.get(calls.invalid).meta?.canonical?.product_definition,'invalid arguments never produce a canonical definition')
      if(!results.has(calls.define)) {
        assert.equal(product,undefined,'loading a skill or querying the schema does not create requirement reminders')
        const sourceText=results.get(calls.source)
        const sourceResult=JSON.parse(sourceText.slice(sourceText.indexOf('__result__:\n')+'__result__:\n'.length))
        const sources=JSON.parse(sourceResult.text)
        assert.equal(sources.length,1)
        assert.equal(sources[0].kind,'user_message')
        definition={title:'Fixture lid',output:'/obj/product_fixture/OUT',units:'meters',
          source_refs:[sources[0].source_ref],reviewed_through:sources[0].source_ref,assumptions:[],retired:[],requirements:[
            {id:'lid',kind:'part',description:'One lid in final output',subjects:['lid'],state:'default',members:{group:'lid',expected_components:1},checks:[]},
            {id:'rim',kind:'detail',description:'Visible detailed rim',subjects:['lid'],state:'default',checks:[]}]}
        yield* call(calls.define,'houdini_product',{action:'define',expected_revision:0,change_reason:'Record the source obligations',definition});return
      }
      assert.equal(product?.revision,results.has(calls.bind)?2:1,'definition must appear in the next real model input')
      assert(product.pending.some(r=>r.id==='rim'),'unmeasured detail must remain pending through every later step')
      if(!results.has(calls.read)) {
        const row=JSON.parse(results.get(calls.define)).product_definition
        assert.equal(row.revision,1)
        assert.equal(product.unresolved,2)
        assert.deepEqual(normalized.get(calls.define).meta.canonical.product_definition,row,
          'actual registry normalization must persist the same definition shown to the model')
        yield* call(calls.read,'houdini_product',{action:'read'});return
      }
      if(!results.has(calls.check)) {
        const read=JSON.parse(results.get(calls.read)).result
        assert.equal(read.current.revision,1)
        assert.equal(read.coverage.unresolved,2)
        yield* call(calls.check,'houdini_query',{code:'__result__ = "product_fixture_measurement"'});return
      }
      if(!results.has(calls.bind)) {
        const match=results.get(calls.check).match(/operation-evidence:\n([^\n]+)/)
        assert(match,'measurement evidence must be present in the actual model-facing result')
        const evidence=JSON.parse(match[1])[0]
        assert.equal(evidence.results[0].status,'pass')
        assert.equal(evidence.output,definition.output)
        definition={...definition,requirements:definition.requirements.map(r=>r.id==='lid'?{...r,checks:[{
          verb:'geo_check_interfaces',contract_sha256:evidence.contract_sha256,check_id:'lid_count'}]}:r)}
        yield* call(calls.bind,'houdini_product',{action:'define',expected_revision:1,change_reason:'Bind observed final-output count',definition});return
      }
      assert.equal(product.unresolved,1,'the measured part must clear without hiding the pending detail')
      if(!results.has(calls.review)) {
        yield* call(calls.review,'houdini_product',{action:'review'});return
      }
      const review=JSON.parse(results.get(calls.review)).result
      assert.equal(review.workflow.completion.status,'not_certified')
      assert.equal(review.workflow.stages.numerical_checks.status,'recorded')
      assert.equal(review.workflow.stages.detail_and_visual.status,'requires_semantic_review')
      assert.equal(review.workflow.persistence.status,'no_current_save_receipt')
      assert.equal(review.evidence_index.rows[0].binding.check_id,'lid_count')
      if(!results.has(calls.final)) {
        yield* call(calls.final,'houdini_product',{action:'read'});return
      }
      const read=JSON.parse(results.get(calls.final)).result
      assert.equal(read.current.revision,2)
      assert.deepEqual(read.coverage.requirements.map(r=>[r.id,r.status]),[['lid','measured'],['rim','missing']])
      const events=session.snapshotEvents()
      const definitions=events.filter(e=>e.type==='tool/result'&&e.data?.meta?.canonical?.product_definition)
      assert.equal(definitions.length,2,'real loop must write both canonical revision receipts')
      assert.equal(await ctx.get('sessions').flush(session),true,'fixture needs actual durable session persistence')
      // Reload a JSON-serialized copy into a new real DSH Session object. This
      // checks serialized canonical metadata, not a retained in-memory reference.
      const saved=path.join(path.dirname(process.env.DSH_PRODUCT_FIXTURE_OUT),'session-reload.json')
      fs.writeFileSync(saved,JSON.stringify(events))
      const restored=Session.create('product-fixture-reloaded',JSON.parse(fs.readFileSync(saved,'utf8')))
      assert.notEqual(restored,session)
      assert.deepEqual(productState(restored.snapshotEvents()),productState(events))
      assert.deepEqual(productCoverage(restored.snapshotEvents()),read.coverage)
      fs.writeFileSync(process.env.DSH_PRODUCT_FIXTURE_OUT,JSON.stringify({status:'passed',results:results.size,
        requests:observations.length,revision:read.current.revision,unresolved:read.coverage.unresolved,
        durable_flush:true,serialized_session_reload:true,session_id:options.sessionId,product_mode:productMode,observations}))
      yield* stop('Product definitions, measured coverage and pending detail survived the real loop and serialized session reload.')
    }
  }
  ctx.llm.registerAdapter(['product-fixture'],new Fixture())
}
