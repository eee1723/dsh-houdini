// Run the real mounted Houdini preset and DSH agent loop with a local scripted
// provider and an owned HTTP Bridge fixture. No model API or Houdini process.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import {createHash,randomUUID} from 'node:crypto'
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import {EXPECTED_EXECUTION_CONTRACT_VERSION, EXPECTED_VERB_CATALOG_HASH, EXPECTED_VERB_NAMES}
  from '../../lib/generated-verb-contract.js'

export const inject = ['loader', 'llm', 'sessions', 'agents', 'sessionController']
const provider = 'houdini-context-fixture', model = 'scripted-local'
const runtimeId = 'a'.repeat(32), jobId = 'b'.repeat(12)
const largePayload = 'FIXTURE_BULK_BEGIN:' + 'x'.repeat(70000) + ':FIXTURE_BULK_END'

export function apply(ctx) {
  const output = process.env.DSH_CONTEXT_FIXTURE_OUT
  const outcomeReceipts = process.env.DSH_OUTCOME_FIXTURE
    ? JSON.parse(fs.readFileSync(process.env.DSH_OUTCOME_FIXTURE,'utf8')) : null
  const finalStep = outcomeReceipts ? 11 : 9
  const requests = [], bridgeCalls = [], receipts = new Map()
  let sequence = 0, jobPolls = 0, failure
  const writeReport = value => {
    fs.writeFileSync(output+'.tmp',JSON.stringify(value,null,2))
    fs.renameSync(output+'.tmp',output)
  }
  const fail = error => {
    failure ??= String(error.stack || error)
    writeReport({error:failure, requests, bridgeCalls})
  }
  const health = () => ({ok:true, runtimeId, executorId:process.env.DSH_HOUDINI_EXECUTOR_ID,
    executionContractVersion:EXPECTED_EXECUTION_CONTRACT_VERSION,
    verbCatalog:{hash:EXPECTED_VERB_CATALOG_HASH, names:EXPECTED_VERB_NAMES, count:EXPECTED_VERB_NAMES.length}})
  const observed = extra => ({ok:true, stdout:'', stderr:'', ...extra,
    execution:{...extra?.execution, runtime_id:runtimeId, executor_id:process.env.DSH_HOUDINI_EXECUTOR_ID,
      hip_path:'context-fixture.hip', sequence:++sequence, observed_at:sequence}})
  const server = http.createServer(async (req,res) => {
    try {
      let raw = ''
      for await (const chunk of req) raw += chunk
      const body = raw ? JSON.parse(raw) : {}
      bridgeCalls.push({method:req.method, path:req.url, body})
      let value
      if (req.url === '/context') value = {ok:true, result:{hip_path:'context-fixture.hip', frame:1,
        selection:[{path:'/obj/context_fixture',type:'geo'}], fixture_marker:'initial-scene-once'}}
      else if (req.url === '/health') value = health()
      else if (req.url === '/requests/prepare') {
        const requestRef = runtimeId + '.' + randomUUID().replaceAll('-','')
        receipts.set(requestRef,{owner_session:body.owner_session})
        value = {...health(), requestRef}
      } else if (req.url === '/exec') {
        const receipt = {request_ref:body.request_ref, owner_call:body.owner_call, runtime_id:runtimeId, status:'done'}
        receipts.set(body.request_ref, receipt)
        if (body.code === 'fixture_transport_unknown') {
          res.writeHead(502, {'Content-Type':'application/json'})
          res.end(JSON.stringify({error:'fixture transport lost after admission'}))
          return
        }
        value = outcomeReceipts && body.code.startsWith('fixture_outcome_')
          ? observed({...outcomeReceipts[body.code.slice('fixture_outcome_'.length)],requestReceipt:receipt})
          : body.code === 'fixture_sync_failure'
          ? observed({ok:false,error:'FIXTURE_UNKNOWN_PARAMETER: expected angle tuple',
              result:{payload:largePayload},requestReceipt:receipt,
              transaction:{status:'rolled_back',parameter_state_restored:true},
              rollback:{success:true,scope:'FIXTURE_PARAMETER_VALUES_AND_KEYS_ONLY'},
              checks:[{verb:'set_parms',status:'unverified',reason:'FIXTURE_EFFECT_UNVERIFIED'}],
              evidence:[{verb:'set_parms',ok:false,restored:true,effect_status:'unverified',reason:'FIXTURE_GEOMETRY_UNVERIFIED'}]})
          : observed({result:{operation:body.code},requestReceipt:receipt})
      } else if (req.url === '/requests/status') {
        assert(receipts.has(body.request_ref), 'must retrieve an original reference')
        value = {ok:true,stdout:'',stderr:'',requestReceipt:{...receipts.get(body.request_ref),
          result:observed({result:{recovered:true}})}}
      } else if (req.url === '/jobs') {
        value = {jobId,requestReceipt:{request_ref:body.request_ref,owner_call:body.owner_call,
          runtime_id:runtimeId,status:'job_submitted',jobId}}
      } else if (req.url === '/jobs/' + jobId + '/status') {
        value = observed({jobId,status:++jobPolls === 1 ? 'running' : 'done',result:{fixture:true}})
      } else throw Error('Unexpected Bridge route: ' + req.url)
      res.writeHead(200, {'Content-Type':'application/json'})
      res.end(JSON.stringify(value))
    } catch (error) { fail(error); res.writeHead(500); res.end(String(error)) }
  })
  const port = Number(new URL(process.env.DSH_HOUDINI_BRIDGE_URL).port)
  const ready = new Promise((resolve,reject) => {server.once('error',reject);server.listen(port,'127.0.0.1',resolve)})
  const textChunks = text => [
    {type:'block-start',index:0,blockType:'text'},
    {type:'block-end',index:0,block:{type:'text',text}},
    {type:'finish',reason:{kind:'stop'}},
  ]
  class ContextFixture extends LlmAdapter {
    async listModels() { return [{provider,id:model,name:'Houdini context fixture',inputModalities:['text','image']}] }
    async resolveModel(route,id) {
      return {provider:route,id,name:'Houdini context fixture',inputModalities:['text','image'],context:{contextWindow:500000}}
    }
    async *stream(options) {
      if (options.purpose) { yield* textChunks('Context fixture'); return }
      try {
        assert(!failure, failure)
        const step = requests.length
        assert(step <= finalStep, 'fixture must converge within scripted requests')
        const snapshots = options.messages.map(message => message.content.filter(block => block.type === 'text')
          .map(block => block.text).join('\n')).filter(text => text.includes('Houdini metadata observation.'))
        const current = snapshots.at(-1)
        assert(current, 'provider must receive the real scene context')
        assert(current.includes('Houdini image input capability'), 'provider must receive image capability')
        const runtimeEvents = ctx.sessions.get(options.sessionId).snapshotEvents()
          .filter(event => event.type === 'user/message' && event.data?.source?.kind === 'runtime-context')
        assert(runtimeEvents.length >= snapshots.length, 'snapshots must originate from the native loop events')
        const row = {step,sessionId:options.sessionId,snapshotCount:snapshots.length,
          runtimeEventCount:runtimeEvents.length,messages:options.messages}
        requests.push(row)
        fs.writeFileSync(output+'.requests.json',JSON.stringify(requests,null,2))
        if (step === 1 || step === 2) {
          assert.equal(snapshots.length,requests[0].snapshotCount,'settled failure/repair must not append scene and vision again')
          const error = options.messages.find(message => message.role === 'tool' && message.toolCallId === 'context-0')
          const visible = error?.content.filter(block => block.type === 'text').map(block => block.text).join('\n')
          assert(error && visible.includes('FIXTURE_UNKNOWN_PARAMETER'),'original actionable tool error must remain visible')
          assert(visible.length < largePayload.length,'the real DSH consumer must truncate the oversized result')
          for (const marker of ['"status":"rolled_back"','"parameter_state_restored":true','"success":true',
            '"effect_status":"unverified"','FIXTURE_PARAMETER_VALUES_AND_KEYS_ONLY',
            'FIXTURE_EFFECT_UNVERIFIED','FIXTURE_GEOMETRY_UNVERIFIED','houdini_resource']) {
            assert(visible.includes(marker),'critical recovery/check/detail information must survive DSH truncation: '+marker)
          }
          const canonical = ctx.sessions.get(options.sessionId).snapshotEvents().find(event =>
            event.type === 'tool/result' && event.data?.message?.source?.callId === 'context-0')?.data?.meta?.canonical
          assert.equal(canonical?.result?.payload,largePayload,'canonical result must remain lossless')
          assert.equal(canonical?.details?.stored,true,'the real runtime must retain details')
          assert(visible.includes(canonical.details.sha256),'provider must receive the actual retained detail reference')
          const retained = fs.readFileSync(canonical.details.path)
          assert.equal(createHash('sha256').update(retained).digest('hex'),canonical.details.sha256)
          assert.equal(JSON.parse(retained).result.payload,largePayload)
        }
        if (step === 3 || step === 4) {
          assert(current.includes('unknown_transport') && current.includes('houdini_request'),'uncertain execution needs recovery context')
          if (step === 4) assert.equal(snapshots.length,requests[3].snapshotCount,'unrelated observation must not repeat an unresolved notice')
        }
        if (step === 5 || step === 9) {
          assert(!current.includes('Houdini recorded execution state.'),'completed recovery/job must clear outstanding context')
        }
        if (step === 6 || step === 7 || step === 8) {
          assert(current.includes(jobId) && current.includes('houdini_job_status'),'active jobs must stay observable')
          if (step === 7) assert.equal(snapshots.length,requests[6].snapshotCount,'unrelated observation must not repeat an active job notice')
          if (step === 8) assert(current.includes('running'),'job state transition must reach provider')
        }
        if (outcomeReceipts && (step === 10 || step === 11)) {
          const name=step===10?'caught_read':'failed_check'
          const callId='context-'+(step-1)
          const expected=outcomeReceipts[name]
          const message=options.messages.find(message=>message.role==='tool' && message.toolCallId===callId)
          const visible=message?.content.filter(block=>block.type==='text').map(block=>block.text).join('\n')
          assert(visible.includes(JSON.stringify(expected.outcome)),'actual model input receives the Python outcome')
          assert.match(visible,name==='caught_read'?/Batch completed; one or more operations raised errors/:/checks failed or contain warnings/)
          assert.doesNotMatch(visible,/Executed successfully/)
          const canonical=ctx.sessions.get(options.sessionId).snapshotEvents().find(event=>
            event.type==='tool/result' && event.data?.message?.source?.callId===callId)?.data?.meta?.canonical
          assert.deepEqual(canonical.outcome,expected.outcome)
          assert.deepEqual(canonical.result,expected.result,'fallback and scoped validation are preserved')
          assert.equal(snapshots.length,requests[9].snapshotCount,'caught read/returned validation adds no duplicate scene snapshot')
        }
        const uncertain = ctx.sessions.get(options.sessionId).snapshotEvents()
          .find(event => event.type === 'tool/result' && event.data?.message?.source?.callId === 'context-2')
        const ref = uncertain?.data?.meta?.canonical?.requestReceipt?.request_ref
        const calls = [
          ['houdini_exec',{code:'fixture_sync_failure'}], ['houdini_exec',{code:'fixture_sync_success'}],
          ['houdini_exec',{code:'fixture_transport_unknown'}], ['houdini_inspect',{code:'fixture_unknown_observation'}],
          ['houdini_request',{request_ref:ref}], ['houdini_job_submit',{code:'fixture_long_work'}],
          ['houdini_inspect',{code:'fixture_job_observation'}], ['houdini_job_status',{jobId}], ['houdini_job_status',{jobId}],
          ...(outcomeReceipts ? [['houdini_inspect',{code:'fixture_outcome_caught_read'}],
            ['houdini_exec',{code:'fixture_outcome_failed_check'}]] : []),
        ]
        if (step === finalStep) { yield* textChunks('Context fixture completed.'); return }
        const [name,args] = calls[step]
        assert(options.tools.some(tool => tool.name === name),'tool must come from the actual preset: '+name)
        if (name === 'houdini_request') assert(ref,'uncertain result must retain the original request reference')
        yield {type:'block-start',index:0,blockType:'tool-call'}
        yield {type:'block-end',index:0,block:{type:'tool-call',id:'context-'+step,name,arguments:JSON.stringify(args)}}
        yield {type:'finish',reason:{kind:'tool-calls'}}
      } catch(error) {fail(error); throw error}
    }
  }
  ctx.llm.registerAdapter([provider],new ContextFixture())
  ctx.effect(() => {
    queueMicrotask(async () => {
      try {
        await ready
        await ctx.loader.await()
        const {sessionId} = await ctx.sessionController.create({cwd:path.dirname(output),agentPreset:'houdini'})
        await ctx.sessionController.selectModel({sessionId,provider,model})
        await ctx.sessionController.prompt({sessionId,requestId:randomUUID(),mode:'queue',
          content:[{type:'text',text:'Run the isolated Houdini execution context fixture.'}]},AbortSignal.timeout(60000))
        const agent = ctx.agents.get(sessionId)
        await agent.whenIdle()
        assert(!failure,failure)
        assert.equal(requests.length,finalStep+1,'real loop must complete all scripted phases')
        assert.equal(bridgeCalls.filter(call => call.path === '/context').length,1,'capture one scene per user message')
        await ctx.sessions.flush(agent.session)
        writeReport({ok:true,sessionId,provider,model,requests:requests.map(({messages,...row})=>row),
          bridgeCalls,events:agent.session.snapshotEvents()})
      } catch(error) {fail(error)}
    })
    return () => server.close()
  })
}
