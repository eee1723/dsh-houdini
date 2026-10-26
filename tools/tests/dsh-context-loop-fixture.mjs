import {fixturePresentation} from './fixture-presentation.mjs'
// Run the real mounted Houdini preset and DSH agent loop with a local scripted
// provider and an owned HTTP Bridge fixture. No model API or Houdini process.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {createHash,randomUUID} from 'node:crypto'
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import {normalizeTraceSteps} from '../normalized-trace-steps.mjs'
import {EXPECTED_EXECUTION_CONTRACT_VERSION, EXPECTED_VERB_CATALOG_HASH, EXPECTED_VERB_NAMES}
  from '../../lib/generated-verb-contract.js'

export const inject = ['loader', 'llm', 'sessions', 'agents', 'sessionController', 'jobs','workspaceRegistry','houdiniTargets']
const provider = 'houdini-context-fixture', model = 'scripted-local'
const defaultRuntimeId = 'a'.repeat(32), jobId = 'b'.repeat(12)
const largePayload = 'FIXTURE_BULK_BEGIN:' + 'x'.repeat(70000) + ':FIXTURE_BULK_END'
const nestedCanonical=event=>event?.data?.meta?.canonical??event?.data?.content
  ?.map(block=>{try{return JSON.parse(block.text)}catch{return null}})
  .find(value=>value?.kind==='dsh-houdini/execution-v1')?.value

export function apply(ctx) {
  const output = process.env.DSH_CONTEXT_FIXTURE_OUT
  const outcomeReceipts = process.env.DSH_OUTCOME_FIXTURE
    ? JSON.parse(fs.readFileSync(process.env.DSH_OUTCOME_FIXTURE,'utf8')) : null
  const expiryStart = outcomeReceipts ? 12 : 10
  const catalogReceipt = process.env.DSH_CATALOG_FIXTURE
    ? JSON.parse(fs.readFileSync(process.env.DSH_CATALOG_FIXTURE,'utf8')) : null
  const hdaReceipt = process.env.DSH_HDA_PRESENTATION_FIXTURE
    ? JSON.parse(fs.readFileSync(process.env.DSH_HDA_PRESENTATION_FIXTURE,'utf8')) : null
  const geometryReceipt = process.env.DSH_GEOMETRY_PRESENTATION_FIXTURE
    ? JSON.parse(fs.readFileSync(process.env.DSH_GEOMETRY_PRESENTATION_FIXTURE,'utf8')) : null
  const scriptFixture = process.env.DSH_SCRIPT_FIXTURE
    ? JSON.parse(fs.readFileSync(process.env.DSH_SCRIPT_FIXTURE,'utf8')) : null
  const renderReceipt = process.env.DSH_RENDER_FIXTURE
    ? JSON.parse(fs.readFileSync(process.env.DSH_RENDER_FIXTURE,'utf8')) : null
  // Replay an exact receipt under its recorded target identity. Introducing a
  // second executor here would correctly trigger production recovery before
  // the next step; this owned HTTP server never contacts that original process.
  const runtimeId=scriptFixture?.receipt?.execution?.runtime_id??renderReceipt?.execution?.runtime_id??defaultRuntimeId
  assert(process.env.DSH_HOME&&path.isAbsolute(process.env.DSH_HOME),'owned DSH_HOME is required')
  const executorId=process.env.DSH_HOUDINI_EXECUTOR_ID,registrationId=randomUUID().replaceAll('-','')
  const originalExecution=scriptFixture?.receipt?.execution??renderReceipt?.execution
  const sceneEpoch=originalExecution?.scene_epoch??'d'.repeat(32),sceneId=originalExecution?.scene_id??'e'.repeat(32)
  const hipPath=originalExecution?.hip_path&&path.isAbsolute(originalExecution.hip_path)?originalExecution.hip_path:path.join(path.dirname(output),'context-fixture.hip')
  const registry=path.join(process.env.DSH_HOME,'dsh-houdini','executors')
  assert.equal(path.resolve(ctx.houdiniTargets.registry),path.resolve(registry),'fixture uses the shared Desktop target registry')
  const endpoint=path.join(registry,'endpoints',executorId+'.json')
  const record={schema:1,executor_id:executorId,registration_id:registrationId,runtime_id:runtimeId,
    installation:fileURLToPath(new URL('../../',import.meta.url)),bridge_url:process.env.DSH_HOUDINI_BRIDGE_URL,
    houdini_version:'22.0.368',pid:process.pid,state:'registered',task_id:null,hip_path:hipPath,
    workbench:true,scene_id:sceneId,scene_epoch:sceneEpoch,hip_is_new:originalExecution?.hip_is_new??true,
    workspace_path:path.dirname(output)}
  const publish=()=>{fs.mkdirSync(path.dirname(endpoint),{recursive:true});fs.writeFileSync(endpoint+'.tmp',JSON.stringify(record));fs.renameSync(endpoint+'.tmp',endpoint)}
  if(scriptFixture){
    const {source,record,receipt}=scriptFixture,bytes=fs.readFileSync(record.path)
    assert.equal(typeof source,'string')
    assert.equal(bytes.toString('utf8'),source,'DSH must read the exact source used by the independent HOM regression')
    assert.equal(bytes.length,record.bytes)
    assert.equal(createHash('sha256').update(bytes).digest('hex'),record.sha256)
    assert.deepEqual(receipt.script,record,'the receipt and executable source must identify the same tested version')
  }
  // Exercise both official DSH transports only in this owned fixture scope;
  // production Houdini stays in its configured presentation mode.
  const presentation=fixturePresentation(ctx)
  const catalogStart = expiryStart + 4
  const repetitionMethod = process.env.DSH_REPETITION_METHOD_FIXTURE === '1'
  const repetitionStart = catalogStart + (catalogReceipt ? 6 : 0)
  const surfaceMethod = process.env.DSH_SURFACE_METHOD_FIXTURE === '1'
  const surfaceStart = repetitionStart + (repetitionMethod ? 2 : 0) + 1
  const surfaceResources = [
    ['skill','houdini-task-decomposition','houdini-task-decomposition/SKILL.md'],
    ['skill','houdini-isolated-execution','houdini-isolated-execution/SKILL.md'],
    ['nested',null,'houdini-sop-workflow/references/sop-patterns.md'],
    ['skill','houdini-surface-workflow','houdini-surface-workflow/SKILL.md'],
    ['read',null,'houdini-surface-workflow/references/appearance-and-sources.md'],
    ['read',null,'houdini-surface-workflow/references/generated-textures.md'],
    ['nested',null,'houdini-surface-workflow/references/sop-preview-and-uv.md'],
    ['skill','houdini-cop-workflow','houdini-cop-workflow/SKILL.md'],
    ['nested',null,'houdini-cop-workflow/references/pattern-design.md'],
    ['skill','houdini-parameter-ui','houdini-parameter-ui/SKILL.md'],
    ['nested',null,'houdini-parameter-ui/references/control-bindings.md'],
    ['skill','houdini-network-handoff','houdini-network-handoff/SKILL.md'],
    ['read',null,'houdini-network-handoff/references/network-layout.md'],
    ['nested',null,'houdini-network-handoff/references/file-delivery.md'],
    ['read',null,'houdini-sop-workflow/references/module-design-collaboration.md'],
    ['read',null,'houdini-sop-workflow/references/curves-and-routing.md'],
    ['skill','houdini-solaris-karma-workflow','houdini-solaris-karma-workflow/SKILL.md'],
    ['nested',null,'houdini-solaris-karma-workflow/references/karma-patterns.md'],
    ['read',null,'houdini-task-decomposition/references/reference-transfer.md'],
  ].map(([kind,name,relative])=>{
    const file=fileURLToPath(new URL('../../skills/'+relative,import.meta.url))
    const source=fs.readFileSync(file,'utf8').replaceAll('\r\n','\n')
    return {kind,name,file,body:kind==='skill'?source.replace(/^---\n[\s\S]*?\n---\n/,'').trim():source.trim()}
  })
  const geometryStart = surfaceStart + (surfaceMethod ? surfaceResources.length : 0)
  const hdaStart = geometryStart + (geometryReceipt ? 2 : 0)
  const scriptStart = hdaStart + (hdaReceipt ? 2 : 0)
  const renderStart = scriptStart + (scriptFixture ? 4 : 0)
  const receiptStart = renderStart + (renderReceipt ? 2 : 0)
  const nestedLargeStep=receiptStart+5
  const finalStep = nestedLargeStep+1
  const methodFile = fileURLToPath(new URL('../../skills/houdini-sop-workflow/references/modeling-methods.md',import.meta.url))
  const methodText = repetitionMethod ? fs.readFileSync(methodFile,'utf8').replaceAll('\r\n','\n') : ''
  const personaBody = fs.readFileSync(new URL('../../presets/houdini/persona.md',import.meta.url),'utf8')
    .replaceAll('\r\n','\n').trim().split('\n\n').slice(1)
  const skillBody = fs.readFileSync(new URL('../../skills/houdini-sop-workflow/SKILL.md',import.meta.url),'utf8')
    .replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/,'').trim().replaceAll('\r\n','\n')
  const decompositionBody = fs.readFileSync(new URL('../../skills/houdini-task-decomposition/SKILL.md',import.meta.url),'utf8')
    .replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/,'').trim().replaceAll('\r\n','\n')
  const requests = [], bridgeCalls = [], receipts = new Map()
  const scriptRejectedCalls=new Map()
  const scriptArgs=scriptFixture?{script:scriptFixture.record.path,expected_sha256:scriptFixture.record.sha256,
    ...(scriptFixture.record.entry!==undefined?{code:scriptFixture.record.entry}:{})}:null
  const scriptWrongArgs=scriptArgs?{...scriptArgs,expected_sha256:(scriptArgs.expected_sha256[0]==='0'?'1':'0')+scriptArgs.expected_sha256.slice(1)}:null
  let sequence = 0, expiryRef, busyRef, busyPolls=0, failure
  let jobState='running',expiryState='running'
  const jobWaiters=new Map()
  const releaseJob=id=>{for(const release of jobWaiters.get(id)??[])release();jobWaiters.delete(id)}
  const awaitJob=async(id,body)=>{
    if(!(body.wait>0))return
    await new Promise(resolve=>{
      const waiting=jobWaiters.get(id)??new Set();jobWaiters.set(id,waiting)
      const release=()=>{clearTimeout(timer);waiting.delete(release);resolve()}
      const timer=setTimeout(release,Math.min(body.wait,30)*1000);timer.unref()
      waiting.add(release)
    })
  }
  const expiredJob = 'c'.repeat(12)
  const writeReport = value => {
    fs.writeFileSync(output+'.tmp',JSON.stringify(value,null,2))
    fs.renameSync(output+'.tmp',output)
  }
  const fail = (error,failedProviderRequest) => {
    failure ??= String(error.stack || error)
    writeReport({error:failure, requests, bridgeCalls,
      ...(failedProviderRequest?{failedProviderRequest}:{})})
  }
  const health = () => ({ok:true, runtimeId, executorId:process.env.DSH_HOUDINI_EXECUTOR_ID,
    houVersion:record.houdini_version,sceneEpoch,
    executionContractVersion:EXPECTED_EXECUTION_CONTRACT_VERSION,
    verbCatalog:{hash:EXPECTED_VERB_CATALOG_HASH, names:EXPECTED_VERB_NAMES, count:EXPECTED_VERB_NAMES.length}})
  const observed = extra => ({ok:true, stdout:'', stderr:'', ...extra,
    execution:{...extra?.execution, runtime_id:runtimeId, executor_id:process.env.DSH_HOUDINI_EXECUTOR_ID,
      hip_path:hipPath,hip_is_new:record.hip_is_new,scene_id:sceneId,scene_epoch:sceneEpoch,sequence:++sequence, observed_at:sequence}})
  const server = http.createServer(async (req,res) => {
    try {
      let raw = ''
      for await (const chunk of req) raw += chunk
      assert.equal(req.headers['x-dsh-houdini-executor'],executorId,'all live requests must explicitly target this owned fixture')
      const body = raw ? JSON.parse(raw) : {}
      bridgeCalls.push({method:req.method, path:req.url, body})
      let value
      if (req.url === '/context') value = {ok:true, result:{hip_path:hipPath,hip_is_new:record.hip_is_new, frame:1,
        selection:[{path:'/obj/context_fixture',type:'geo'}], fixture_marker:'initial-scene-once'}}
      else if (req.url === '/health') value = health()
      else if(req.url==='/executor/claim') {
        assert.equal(body.registration_id,registrationId);assert.equal(body.expected_hip,hipPath)
        record.task_id=body.task_id;publish();value={ok:true}
      }
      else if (req.url === '/requests/prepare') {
        const requestRef = runtimeId + '.' + randomUUID().replaceAll('-','')
        receipts.set(requestRef,{owner_session:body.owner_session})
        value = {...health(), requestRef}
      } else if (req.url === '/exec') {
        const receipt = {request_ref:body.request_ref, owner_call:body.owner_call, runtime_id:runtimeId, status:'done'}
        receipts.set(body.request_ref, receipt)
        if (body.code === 'fixture_transport_unknown' || body.code === 'fixture_busy_receipt') {
          if(body.code==='fixture_busy_receipt')busyRef=body.request_ref
          res.writeHead(502, {'Content-Type':'application/json'})
          res.end(JSON.stringify({error:'fixture transport lost after admission'}))
          return
        }
        if(scriptFixture && body.script){
          assert.equal(body.code,scriptFixture.source,'the Host must transmit actual Python source, never an exec/open wrapper')
          assert.deepEqual(body.script,scriptFixture.record,'source version and invocation tail reach the actual HTTP consumer')
          assert.equal(req.headers['x-dsh-houdini-executor'],process.env.DSH_HOUDINI_EXECUTOR_ID,'HTTP routing stays pinned to the current fixture executor')
          assert.equal(typeof body.owner_session,'string');assert(body.owner_session.trim())
          assert.equal(typeof body.owner_call,'string');assert(body.owner_call.trim())
          // This is historical independent-HOM evidence. Do not overwrite its
          // source runtime/owner identity with this HTTP fixture's routing identity.
          value=scriptFixture.receipt
        }else value = renderReceipt && body.code === 'fixture_render'
          ? renderReceipt
          : geometryReceipt && body.code === 'fixture_geometry'
          ? observed({...geometryReceipt,requestReceipt:receipt})
          : hdaReceipt && body.code === 'fixture_hda'
          ? observed({...hdaReceipt,requestReceipt:receipt})
          : catalogReceipt && body.code === 'fixture_catalog'
          ? observed({...catalogReceipt,requestReceipt:receipt})
          : outcomeReceipts && body.code.startsWith('fixture_outcome_')
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
        value = body.request_ref===busyRef && ++busyPolls<4
          ? {ok:true,stdout:'',stderr:'',requestReceipt:{...receipts.get(body.request_ref),status:busyPolls===1?'queued':'running'}}
          : body.request_ref===expiryRef
          ? {ok:true,stdout:'',stderr:'',requestReceipt:{...receipts.get(body.request_ref),
              status:'result_expired',jobId:expiredJob,job_finished:expiryState==='unavailable',
              job_result_available:false,job_status:expiryState==='running'?'running':'done'}}
          : {ok:true,stdout:'',stderr:'',requestReceipt:{...receipts.get(body.request_ref),
              result:observed({result:{recovered:true}})}}
      } else if (req.url === '/jobs') {
        const submittedJob=body.code==='fixture_expiring_work'?expiredJob:jobId
        value = {jobId:submittedJob,requestReceipt:{request_ref:body.request_ref,owner_call:body.owner_call,
          runtime_id:runtimeId,status:'job_submitted',jobId:submittedJob}}
        receipts.set(body.request_ref,value.requestReceipt)
        if(submittedJob===expiredJob)expiryRef=body.request_ref
      } else if (req.url === '/jobs/' + jobId + '/status') {
        if(jobState==='running')await awaitJob(jobId,body)
        value = observed({jobId,status:jobState,result:{fixture:true}})
      } else if (req.url === '/jobs/' + expiredJob + '/status') {
        if(expiryState==='running')await awaitJob(expiredJob,body)
        if(expiryState==='unavailable'){
          res.writeHead(404,{'Content-Type':'application/json'});res.end(JSON.stringify({ok:false,error:'fixture result pruned'}));return
        }
        value=observed({jobId:expiredJob,status:'running'})
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
        const system = options.messages.filter(message => message.role === 'system')
          .flatMap(message => message.content.filter(block => block.type === 'text').map(block => block.text))
          .join('\n').replaceAll('\r\n','\n')
        for (const paragraph of personaBody) assert.equal(system.split(paragraph).length-1,1,
          'the actual provider must receive each maintained persona section exactly once')
        assert(!system.includes(skillBody),'domain methods must not be eagerly duplicated in System')
        assert(!system.includes(decompositionBody),'task decomposition must remain an on-demand skill')
        for(const resource of surfaceResources)assert(!system.includes(resource.body),'surface methods must remain on demand')
        if(surfaceMethod){
          assert(system.includes('houdini-surface-workflow'),'surface routing must reach the provider')
          for(const [index,resource] of surfaceResources.entries()){
            if(step<=surfaceStart+index)continue
            const message=options.messages.find(m=>m.role==='tool'&&m.toolCallId==='context-'+(surfaceStart+index))
            const raw=message?.content.filter(b=>b.type==='text').map(b=>b.text).join('\n')??''
            const visible=raw.replaceAll('\r\n','\n')
            // Native read is text; nested read may be JSON encoded. Preserve
            // literal backslash-n in code examples rather than unescaping all text.
            const missing=resource.body.split('\n').filter(line=>line.trim())
              .find(line=>!visible.includes(line)&&!visible.includes(JSON.stringify(line).slice(1,-1)))
            assert(!missing,`complete ${resource.kind} resource must reach the actual provider: ${resource.file}; missing: ${missing}`)
          }
        }
        if (step === finalStep) {
          const skillResult=options.messages.filter(message=>message.role==='tool')
            .flatMap(message=>message.content.filter(block=>block.type==='text').map(block=>block.text)).join('\n')
          assert(skillResult.replaceAll('\r\n','\n').includes(skillBody),'on-demand skill reaches the actual provider intact')
          assert(skillResult.replaceAll('\r\n','\n').includes(decompositionBody),'registered decomposition skill reaches the actual provider intact')
          const events=ctx.sessions.get(options.sessionId).snapshotEvents()
          const nativeJob=events.find(event=>event.type==='tool/result'&&event.data?.message?.source?.callId==='context-8')
          const jobCanonical=nativeJob?.data?.meta?.canonical
          assert.equal(jobCanonical?.job?.kind,'houdini-live','the official loop persists this producer\'s native job output metadata')
          const originalJob=JSON.parse(jobCanonical.text)
          assert.equal(originalJob.kind,'dsh-houdini/live-job-result-v1')
          assert.equal(originalJob.value.status,'done')
          assert.equal(originalJob.value.jobId,jobId)
          const visibleJob=options.messages.find(message=>message.role==='tool'&&message.toolCallId==='context-8')
            ?.content.filter(block=>block.type==='text').map(block=>block.text).join('\n')??''
          assert(visibleJob.includes('DSH job')&&visibleJob.includes('completed'),'the final provider retains the actual native job completion')
          const nestedLarge=events.find(event=>event.type==='tool/ptc-dispatch'&&event.data?.name==='houdini_exec'
            &&event.data?.parentCallId==='context-'+nestedLargeStep)
          const canonical=nestedCanonical(nestedLarge)
          assert.equal(canonical?.result?.payload,largePayload,'the real nested dispatch retains the complete large failure envelope')
          const nestedVisible=options.messages.find(message=>message.role==='tool'&&message.toolCallId==='context-'+nestedLargeStep)
            ?.content.filter(block=>block.type==='text').map(block=>block.text).join('\n')??''
          assert(nestedVisible.includes('FIXTURE_UNKNOWN_PARAMETER')&&nestedVisible.includes(canonical.details.sha256),
            'the final provider receives the nested actionable error and its exact original detail reference')
          const nativeLarge=events.find(event=>event.type==='tool/result'&&event.data?.message?.source?.callId==='context-0')
          assert.equal(nativeLarge?.data?.meta?.canonical?.result?.payload,largePayload,'later native and PTC steps preserve earlier full canonical values')
        }
        const snapshots = options.messages.map(message => message.content.filter(block => block.type === 'text')
          .map(block => block.text).join('\n')).filter(text => text.includes('Houdini metadata observation.'))
        if(geometryReceipt && step>geometryStart){
          for(let offset=0;offset<Math.min(2,step-geometryStart);offset++){
            const message=options.messages.find(m=>m.role==='tool'&&m.toolCallId==='context-'+(geometryStart+offset))
            const visible=message?.content.filter(b=>b.type==='text').map(b=>b.text).join('\n')??''
            for(const fact of ['selected_final_primitives','geometry_scope','full_output',geometryReceipt.result.results[0].geometry_restore.full_output.baseline.sha256])assert(visible.includes(fact),fact);
          }
          const canonical=ctx.sessions.get(options.sessionId).snapshotEvents().find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='context-'+geometryStart)?.data?.meta?.canonical
          assert.deepEqual(canonical?.result,geometryReceipt.result,'final-output selection and whole-output restoration stay canonical')
        }
        if(hdaReceipt && step>hdaStart){
          for(let offset=0;offset<Math.min(2,step-hdaStart);offset++){
            const message=options.messages.find(m=>m.role==='tool'&&m.toolCallId==='context-'+(hdaStart+offset))
            const visible=message?.content.filter(b=>b.type==='text').map(b=>b.text).join('\n')??''
            assert(visible.length<22000,'native and nested HDA results must reach the provider without a giant native inventory')
            for(const fact of [offset===0?'definition_rebuild_descendants':'editable_discarded_descendants',hdaReceipt.result.plan_sha256])assert(visible.includes(fact),fact)
            for(const [node] of hdaReceipt.result.editable_discarded_descendants)assert(visible.includes(node),'editable discard target stays visible')
          }
          const native=ctx.sessions.get(options.sessionId).snapshotEvents().find(e=>e.type==='tool/result'
            && e.data?.message?.source?.callId==='context-'+hdaStart)?.data?.meta?.canonical
          assert(native?.details?.stored,'full native receipt must be retained before projection')
          const archive=fs.readFileSync(native.details.path)
          assert.equal(createHash('sha256').update(archive).digest('hex'),native.details.sha256)
          assert.deepEqual(JSON.parse(archive).result,hdaReceipt.result,'HDA scope and identity facts survive archival')
          if(step>hdaStart+1){
            const nested=ctx.sessions.get(options.sessionId).snapshotEvents().find(e=>e.type==='tool/ptc-dispatch'
              &&e.data?.name==='houdini_exec'&&e.data?.parentCallId==='context-'+(hdaStart+1))
            const canonical=nestedCanonical(nested)
            assert.deepEqual(canonical?.result,hdaReceipt.result,'nested execution retains the same complete HDA facts')
          }
        }
        if(scriptFixture && step>scriptStart){
          const events=ctx.sessions.get(options.sessionId).snapshotEvents()
          const original=scriptFixture.receipt
          const preserve=value=>{
            for(const key of ['script','result','transaction','rawUsage','outcome','execution','verbs'])
              assert.deepEqual(value?.[key],original[key],`the actual DSH consumer preserves original independent HOM ${key}`)
          }
          const native=events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='context-'+scriptStart)
          assert.equal(native?.data?.message?.isError,false,'native script arguments must pass the actual mounted tool schema')
          preserve(native?.data?.meta?.canonical)
          const nativeMessage=options.messages.find(m=>m.role==='tool'&&m.toolCallId==='context-'+scriptStart)
          assert(nativeMessage?.content.some(b=>b.type==='text'&&b.text.includes(scriptFixture.record.sha256)),
            'the actual provider receives the exact native script fingerprint')
          const sent=bridgeCalls.filter(call=>call.path==='/exec'&&call.body.script)
          assert.equal(sent[0]?.body.owner_session,options.sessionId,'the native source is admitted with the real current DSH session')
          assert.equal(sent[0]?.body.owner_call,'context-'+scriptStart)
          if(step>scriptStart+1){
            const parent=events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='context-'+(scriptStart+1))
            assert.equal(parent?.data?.message?.isError,false,'the actual nested worker must run before checking its receipt: '
              +parent?.data?.message?.content.filter(b=>b.type==='text').map(b=>b.text).join('\n'))
            assert.equal(sent.length,2,'the successful nested program must dispatch exactly one script HTTP execution')
            const nested=events.find(e=>e.type==='tool/ptc-dispatch'&&e.data?.name==='houdini_exec'
              &&e.data?.subCallId===sent[1]?.body.owner_call)
            const canonical=nestedCanonical(nested)
            preserve(canonical)
            assert.equal(nested?.data?.isError,false,'nested script execution retains the original canonical envelope')
            assert.equal(nested?.data?.parentCallId,'context-'+(scriptStart+1),'the original script receipt is attached to the matching nested parent')
            assert.equal(sent[1]?.body.owner_session,options.sessionId,'nested source execution uses its actual DSH session')
            assert.notEqual(sent[1]?.body.owner_call,sent[0]?.body.owner_call,'the nested call retains its own tool invocation identity')
            const nestedMessage=options.messages.find(m=>m.role==='tool'&&m.toolCallId==='context-'+(scriptStart+1))
            assert(nestedMessage?.content.some(b=>b.type==='text'&&b.text.includes(scriptFixture.record.sha256)),
              'the actual provider receives script metadata selected by the nested program')
          }
          if(scriptRejectedCalls.has(step-1)){
            assert.equal(bridgeCalls.length,scriptRejectedCalls.get(step-1),'a wrong source hash must fail without any Bridge HTTP request')
            const message=options.messages.find(m=>m.role==='tool'&&m.toolCallId==='context-'+(step-1))
            assert(message?.content.some(b=>b.type==='text'&&b.text.includes('Script SHA-256 mismatch')),
              'native and nested model inputs receive the actual Host hash error')
          }
          if(step>=scriptStart+2)assert.equal(sent.length,2,'only the two version-matching calls reach HTTP execution')
        }
        if(renderReceipt && step>renderStart){
          const events=ctx.sessions.get(options.sessionId).snapshotEvents()
          for(let offset=0;offset<Math.min(2,step-renderStart);offset++){
            const callId='context-'+(renderStart+offset)
            const message=options.messages.find(m=>m.role==='tool'&&m.toolCallId===callId)
            const visible=message?.content.filter(b=>b.type==='text').map(b=>b.text).join('\n')??''
            // Native presentation exposes the execution-owned evidence; PTC
            // pretty-prints the selected JSON before its sandbox status footer.
            // Compare parsed provider values, not a compact serialization.
            let shown
            if(offset===0){
              const section=visible.split('\n\n').find(part=>part.startsWith('operation-evidence:\n'))
              assert(section,'native provider input includes operation evidence')
              shown=JSON.parse(section.slice('operation-evidence:\n'.length)).find(item=>item.verb==='render_frame')
            }else{
              const end=visible.lastIndexOf('}')+1
              assert(end>0&&visible.trimStart().startsWith('{'),'nested provider input includes the selected JSON object')
              shown=JSON.parse(visible.slice(0,end))
            }
            for(const key of ['output','outputs','fresh','inherited_products','scope'])assert.deepEqual(shown?.[key],renderReceipt.result[key],
              `actual provider receives original multi-product render ${key}, including file freshness and unverified products`)
            const event=offset===0
              ? events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId===callId)
              : events.find(e=>e.type==='tool/ptc-dispatch'&&e.data?.name==='houdini_exec'&&e.data?.parentCallId===callId)
            const canonical=offset===0?event?.data?.meta?.canonical:nestedCanonical(event)
            for(const [key,value] of Object.entries(renderReceipt))assert.deepEqual(canonical?.[key],value,
              `native/PTC render consumption preserves the original Bridge ${key}`)
          }
        }
        const current = snapshots.at(-1)
        if(!current)fs.writeFileSync(output+'.missing-context.json',JSON.stringify({messages:options.messages,
          events:ctx.sessions.get(options.sessionId).snapshotEvents()},null,2))
        assert(current, 'provider must receive the real scene context')
        assert(current.includes('initial-scene-once')&&current.includes('/obj/context_fixture'),
          'the provider must receive the explicitly selected fixture scene, not an unavailable or unrelated observation')
        assert(current.includes('Houdini image input capability'), 'provider must receive image capability')
        const runtimeEvents = ctx.sessions.get(options.sessionId).snapshotEvents()
          .filter(event => event.type === 'user/message' && event.data?.source?.kind === 'runtime-context')
        assert(runtimeEvents.length >= snapshots.length, 'snapshots must originate from the native loop events')
        const row = {step,sessionId:options.sessionId,snapshotCount:snapshots.length,
          runtimeEventCount:runtimeEvents.length,messages:options.messages}
        requests.push(row)
        fs.writeFileSync(output+'.requests.json',JSON.stringify(requests,null,2))
        if(step>=receiptStart+2){
          const expected=step===receiptStart+2?'queued':'running'
          if(step<=receiptStart+4)assert(current.includes(JSON.stringify([busyRef,expected])),
            'latest same-runtime receipt state reaches the real provider')
          for(let offset=1;offset<=Math.min(step-receiptStart-1,3);offset++){
            const message=options.messages.find(m=>m.role==='tool'&&m.toolCallId==='context-'+(receiptStart+offset))
            const visible=message?.content.filter(b=>b.type==='text').map(b=>b.text).join('\n')??''
            assert(visible.includes(offset===1?'not independent liveness probes':'HTTP timeout did not cancel'),
              'native and nested receipt values deliver the queue/recovery meaning')
          }
          if(step===receiptStart+4)assert.equal(snapshots.length,requests[receiptStart+3].snapshotCount,
            'repeating the same running receipt does not append a new context snapshot')
          if(step===finalStep){
            assert(!current.includes(busyRef),'completion retires this request without clearing unrelated facts')
            assert.equal(bridgeCalls.filter(c=>c.path==='/exec'&&c.body.code==='fixture_busy_receipt').length,1,
              'status recovery never resubmits the original operation')
          }
        }
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
          assert(current.includes(jobId) && current.includes('job_output'),'active jobs must stay observable through native jobs')
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
        if(step===expiryStart+2){
          assert(current.includes('running')&&current.includes(expiredJob),'admission expiry must retain genuinely running work')
          assert(current.includes('"unavailable_results":[]'),'running work is not an unavailable finished result')
        }
        if(step>=expiryStart+3){
          assert(current.includes('"active_jobs":[]')&&current.includes('finished_result_unavailable'),
            'the actual provider must receive terminal unavailable outcome without an active-job loop')
          assert(current.includes(expiredJob),'unavailable execution retains its job identity')
          const recoveredMessage=options.messages.find(m=>m.role==='tool'&&m.toolCallId==='context-'+(expiryStart+2))
          assert(recoveredMessage?.content.some(b=>b.type==='text'&&b.text.includes('Do not poll the missing job')),
            'the actual tool response must tell the provider not to poll or resubmit a pruned job')
          if(step===receiptStart)assert.equal(snapshots.length,requests[expiryStart+3].snapshotCount,'unrelated reads do not repeat expired-result context')
        }
        const currentEvents=ctx.sessions.get(options.sessionId).snapshotEvents()
        if(repetitionMethod && step>repetitionStart){
          const reference = options.messages.find(m=>m.role==='tool'&&m.toolCallId==='context-'+repetitionStart)
          const visible=reference?.content.filter(b=>b.type==='text').map(b=>b.text).join('\n').replaceAll('\r\n','\n')
          const section=methodText.split('### 重复规律与代码生成')[1].split('### 源构件与成形检查')[0]
          const relevant=section.split('\n').filter(line=>line.trim()&&!line.startsWith('```'))
          assert(relevant.every(line=>visible?.includes(line)), 'the actual provider must receive the shipped repetition method and exact VEX example')
          const componentSection=methodText.split('### 完整源组件与布局')[1].split('### 重复规律与代码生成')[0]
          assert(componentSection.split('\n').filter(line=>line.trim()).every(line=>visible?.includes(line)),
            'the actual provider must receive the complete component-source reference through the mounted read tool')
          const containerSection=methodText.split('### 逻辑模块与容器选择')[1].split('## 2. 选择先于倒角与局部操作')[0]
          assert(containerSection.split('\n').filter(line=>line.trim()).every(line=>visible?.includes(line)),
            'the actual provider receives the complete container and dependency guidance, not just its link')
        }
        if(repetitionMethod && step===finalStep){
          const events=normalizeTraceSteps(currentEvents).steps.filter(s=>s.tool==='read')
          assert.equal(events.length,2+(surfaceMethod?surfaceResources.filter(r=>r.kind!=='skill').length:0),'native and nested on-demand reference reads both execute')
          assert(events.every(s=>!s.failed),'reference delivery cannot be inferred from configuration')
        }
        const nativeCatalog=currentEvents.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='context-'+catalogStart)?.data?.meta?.canonical
        if(catalogReceipt && step>catalogStart){
          assert.deepEqual(nativeCatalog.result,catalogReceipt.result,'native provider result preserves the selected catalog fields')
          if(catalogReceipt.result.conditions){
            const conditions=nativeCatalog.result.conditions
            assert.deepEqual(conditions,catalogReceipt.result.conditions,'native conditionals and bit-field settings are execution facts')
            const materialParameters=conditions.static.parameters
            assert(materialParameters.some(p=>p.name==='elementscale'&&p.conditionals?.HideWhen),'native parameter enablement must remain visible')
          }
          assert.deepEqual(nativeCatalog.verbs[0].result,catalogReceipt.verbs[0].result,'native canonical catalog stays typed and complete')
          const message=options.messages.find(m=>m.role==='tool'&&m.toolCallId==='context-'+catalogStart)
          const visible=message?.content.filter(b=>b.type==='text').map(b=>b.text).join('\n')
          assert(visible.includes('resolutiony')&&visible.includes('parameter_catalog')&&visible.includes('/verbs/0/result'))
          if(catalogReceipt.result.conditions)assert(visible.includes('HideWhen')&&visible.includes('toggle_strip'),
            'actual provider text retains native parameter conditions and strip semantics')
          for(const card of Object.values(catalogReceipt.result.surface_cards??{})){
            assert(card.usage_notes.every(note=>visible.includes(note)),
              'actual provider receives the current native node operation knowledge')
            assert(visible.includes(card.operation_card.id),'native provider text retains the operation-card identity')
            assert(card.operation_parameters.every(parameter=>visible.includes(JSON.stringify(parameter.name))),
              'native provider text retains the critical operation parameter names')
          }
          if(catalogReceipt.result.interface_observation){
            assert(visible.includes('target_primitive_limit_exceeded')&&visible.includes('required_pairs')&&visible.includes('runtime_limits'),
              'actual provider receives capacity reasons and execution-owned limits without a fabricated geometric failure')
          }
          assert(!visible.includes('Full formatted result stored'),'selected catalog no longer triggers DSH spill')
          assert(visible.length<JSON.stringify(catalogReceipt.verbs[0].result).length/2,'full ledger does not undo Python selection')
        }
        if(catalogReceipt && step>catalogStart+1){
          const nested=currentEvents.find(e=>e.type==='tool/ptc-dispatch'&&e.data?.name==='houdini_inspect')
          const canonical=nestedCanonical(nested)
          assert.deepEqual(canonical?.result,catalogReceipt.result,'real PTC execution receives the selected result')
          assert.deepEqual(canonical?.verbs[0].result,catalogReceipt.verbs[0].result,'PTC durable catalog stays typed')
          const message=options.messages.find(m=>m.role==='tool'&&m.toolCallId==='context-'+(catalogStart+1))
          const visible=message?.content.filter(b=>b.type==='text').map(b=>b.text).join('\n')
          assert(visible.includes('resolutiony')&&!visible.includes('parameter_catalog'),'PTC returns only its selected value, not durable audit data')
          if(catalogReceipt.result.conditions)assert(visible.includes('HideWhen')&&visible.includes('toggle_strip'),
            'nested selected values retain parameter conditions and strip semantics at the actual provider')
          for(const card of Object.values(catalogReceipt.result.surface_cards??{})){
            assert(card.usage_notes.every(note=>visible.includes(note)),
              'nested selected values retain complete native node operation knowledge')
            assert(visible.includes(card.operation_card.id),'nested provider text retains the operation-card identity')
            assert(card.operation_parameters.every(parameter=>visible.includes(JSON.stringify(parameter.name))),
              'nested provider text retains the critical operation parameter names')
          }
          if(catalogReceipt.result.interface_observation){
            assert(visible.includes('target_primitive_limit_exceeded')&&visible.includes('Increasing max_pairs cannot remove'),
              'nested selected results preserve the supported recovery action')
          }
        }
        if(catalogReceipt && step>catalogStart+2){
          const read=currentEvents.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId==='context-'+(catalogStart+2))?.data?.meta?.canonical
          assert.equal(JSON.parse(read.result.text),catalogReceipt.verbs[0].result.at(-1).name,'real resource tool resolves a nested catalog leaf')
        }
        if(catalogReceipt && step>catalogStart+3){
          const read=currentEvents.filter(e=>e.type==='tool/ptc-dispatch'&&e.data?.name==='houdini_resource').at(-1)
          const canonical=nestedCanonical(read)
          assert.equal(JSON.parse(canonical.result.text),catalogReceipt.verbs[0].result.at(-1).name,'PTC resource read resolves the same typed leaf')
        }
        if(catalogReceipt && step===finalStep){
          const processes=normalizeTraceSteps(currentEvents).steps.filter(s=>s.tool==='pwsh')
          assert.equal(processes.length,2,'real native and PTC shell calls both returned')
          assert(processes.every(s=>!s.failed&&s.processOutcome?.exitCode===7&&s.processOutcome?.status==='failed'),
            'actual DSH native/nested process exits remain separate from successful tool delivery')
        }
        const uncertain = ctx.sessions.get(options.sessionId).snapshotEvents()
          .find(event => event.type === 'tool/result' && event.data?.message?.source?.callId === 'context-2')
        const ref = uncertain?.data?.meta?.canonical?.requestReceipt?.request_ref
        const submitted=ctx.sessions.get(options.sessionId).snapshotEvents().find(event=>event.type==='tool/result'
          &&event.data?.message?.source?.callId==='context-5')?.data?.meta?.canonical
        if(step===8){jobState='done';releaseJob(jobId)}
        if(step===expiryStart+2){expiryState='unavailable';releaseJob(expiredJob)}
        const calls = [
          ['houdini_exec',{code:'fixture_sync_failure'}], ['houdini_exec',{code:'fixture_sync_success'}],
          ['houdini_exec',{code:'fixture_transport_unknown'}], ['houdini_inspect',{code:'fixture_unknown_observation'}],
          ['houdini_request',{request_ref:ref}], ['houdini_job_submit',{code:'fixture_long_work'}],
          ['houdini_inspect',{code:'fixture_job_observation'}], ['houdini_request',{request_ref:submitted?.requestReceipt?.request_ref}],
          ['job_output',{job_id:submitted?.job_id,wait:true,timeout_ms:5000}],
          ...(outcomeReceipts ? [['houdini_inspect',{code:'fixture_outcome_caught_read'}],
            ['houdini_exec',{code:'fixture_outcome_failed_check'}]] : []),
          ['skill',{name:'houdini-sop-workflow'}],
          ['houdini_job_submit',{code:'fixture_expiring_work'}],
          ['houdini_request',{request_ref:expiryRef}],
          ['houdini_request',{request_ref:expiryRef}],
          ['houdini_inspect',{code:'fixture_after_expired_job'}],
          ...(catalogReceipt ? [
            ['houdini_inspect',{code:'fixture_catalog'}],
            ['run_code',{code:'const value = await tools.houdini_inspect({code:"fixture_catalog"}); return {selected:value.result};',description:'Inspect selected native parameter metadata'}],
            ['houdini_resource',{kind:'result',ref:nativeCatalog?.details?.sha256,pointer:'/verbs/0/result/'+(catalogReceipt.verbs[0].result.length-1)+'/name'}],
            ['run_code',{code:'const value = await tools.houdini_resource('+JSON.stringify({kind:'result',ref:nativeCatalog?.details?.sha256,pointer:'/verbs/0/result/'+(catalogReceipt.verbs[0].result.length-1)+'/name'})+'); return value.result;',description:'Read an archived parameter catalog leaf'}],
            ['pwsh',{command:"Write-Output 'process-outcome-fixture'; exit 7",description:'Exercise an isolated known process exit'}],
            ['run_code',{code:'return await tools.pwsh({command:"Write-Output \'process-outcome-fixture\'; exit 7",description:"Exercise nested known process exit"});',description:'Observe a shell process exit through PTC'}],
          ] : []),
          ...(repetitionMethod ? [
            ['read',{file_path:methodFile}],
            ['run_code',{code:'return await tools.read('+JSON.stringify({file_path:methodFile})+');',description:'Read the shipped repeated-layout method through the mounted tool'}],
          ] : []),
          ['skill',{name:'houdini-task-decomposition'}],
          ...(surfaceMethod ? surfaceResources.map(resource=>resource.kind==='skill'
            ? ['skill',{name:resource.name}]
            : resource.kind==='read' ? ['read',{file_path:resource.file}]
            : ['run_code',{code:'return await tools.read('+JSON.stringify({file_path:resource.file})+');',description:'Read the relevant Houdini method through the mounted tool'}]) : []),
          ...(geometryReceipt ? [
            ['houdini_exec',{code:'fixture_geometry'}],
            ['run_code',{code:'const v=await tools.houdini_exec({code:"fixture_geometry"}); return {control_summary:v.result.control_summary,geometry_scope:v.result.geometry_scope,restored:v.result.restored,full_output:v.result.results[0].geometry_restore.full_output};',description:'Read exact selection and complete restoration evidence'}],
          ] : []),
          ...(hdaReceipt ? [
            ['houdini_exec',{code:'fixture_hda'}],
            ['run_code',{code:'const v=await tools.houdini_exec({code:"fixture_hda"}); const r=v.result; return {node:r.node, plan_sha256:r.plan_sha256, applied:r.applied, affected_instances:r.affected_instances, descendant_count:r.descendant_count, editable_discarded_descendants:r.editable_discarded_descendants, details:v.details};',description:'Select the HDA lifecycle plan through the nested tool; canonical details stay complete'}],
          ] : []),
          ...(scriptFixture ? [
            ['houdini_exec',scriptArgs],
            ['run_code',{code:'const v=await tools.houdini_exec('+JSON.stringify(scriptArgs)+'); return {script:v.script,result:v.result,execution:v.execution};',
              description:'Read exact independent HOM script evidence through the nested tool; this HTTP fixture does not execute a new scene'}],
            ['houdini_exec',scriptWrongArgs],
            ['run_code',{code:'return await tools.houdini_exec('+JSON.stringify(scriptWrongArgs)+');',
              description:'Verify a changed builder version is rejected before any HTTP scene request'}],
          ] : []),
          ...(renderReceipt ? [
            ['houdini_exec',{code:'fixture_render'}],
            ['run_code',{code:'const v=await tools.houdini_exec({code:"fixture_render"}); const r=v.result; return {output:r.output,outputs:r.outputs,fresh:r.fresh,inherited_products:r.inherited_products,scope:r.scope};',
              description:'Read the exact historical multi-product render receipt; no new rendering or image inspection'}],
          ] : []),
          ['houdini_exec',{code:'fixture_busy_receipt'}],
          ['houdini_request',{request_ref:busyRef}],
          ['run_code',{code:'return await tools.houdini_request('+JSON.stringify({request_ref:busyRef})+');',description:'Read the same busy request through the nested tool'}],
          ['houdini_request',{request_ref:busyRef}],
          ['houdini_request',{request_ref:busyRef}],
          ['run_code',{code:'const value=await tools.houdini_exec({code:"fixture_sync_failure"}); return {ok:value.ok,error:value.error,details:value.details};',
            description:'Retain the complete nested failure envelope while returning only its error and original detail reference'}],
        ]
        if (step === finalStep) { yield* textChunks('Context fixture completed.'); return }
        const [name,args] = calls[step]
        if(scriptFixture&&(step===scriptStart+2||step===scriptStart+3))scriptRejectedCalls.set(step,bridgeCalls.length)
        presentation.after('context-'+step,calls[step+1]?.[0])
        assert(options.tools.some(tool => tool.name === name),'tool must come from the actual preset: '+name)
        if (name === 'houdini_request') assert(ref,'uncertain result must retain the original request reference')
        yield {type:'block-start',index:0,blockType:'tool-call'}
        yield {type:'block-end',index:0,block:{type:'tool-call',id:'context-'+step,name,arguments:JSON.stringify(args)}}
        yield {type:'finish',reason:{kind:'tool-calls'}}
      } catch(error) {fail(error,{step:requests.length,messages:options.messages}); throw error}
    }
  }
  ctx.llm.registerAdapter([provider],new ContextFixture())
  ctx.effect(() => {
    queueMicrotask(async () => {
      try {
        await ready
        publish()
        await ctx.loader.await()
        const workspace=await ctx.workspaceRegistry.create(path.dirname(output),'Owned context fixture')
        const {sessionId} = await ctx.sessionController.create({workspaceId:workspace.id,agentPreset:'houdini'})
        await ctx.houdiniTargets.select({sessionId,executorId,registrationId,expectedHip:hipPath,runtimeId,sceneEpoch},AbortSignal.timeout(5000))
        await ctx.sessionController.selectModel({sessionId,provider,model})
        await ctx.sessionController.prompt({sessionId,requestId:randomUUID(),mode:'queue',
          content:[{type:'text',text:'Run the isolated Houdini execution context fixture.'}]},AbortSignal.timeout(60000))
        const agent = ctx.agents.get(sessionId)
        await agent.whenIdle()
        assert(!failure,failure)
        assert.equal(requests.length,finalStep+1,'real loop must complete all scripted phases')
        assert.equal(bridgeCalls.filter(call => call.path === '/context').length,1,'capture one scene per user message')
        await ctx.sessions.flush(agent.session)
        writeReport({ok:true,sessionId,provider,model,consumer_checks:['explicit-shared-target','current-scene-context','settled-error-no-reprobe',
          'uncertain-original-request-recovery','native-jobs-result-in-final-model-input','native-and-PTC-lossless-canonical',
          'nested-actionable-error-and-detail-in-final-model-input'],requests:requests.map(({messages,...row})=>row),
          ...(scriptFixture?{script_consumption:{record:scriptFixture.record,original_execution:scriptFixture.receipt.execution,
            http_fixture_target:{runtime_id:runtimeId,executor_id:process.env.DSH_HOUDINI_EXECUTOR_ID},
            scope:'Actual mounted DSH native/PTC schema, file read, source HTTP body and original independent-HOM receipt consumption. The HTTP fixture does not execute or verify a new Houdini scene.'}}:{}),
          ...(renderReceipt?{render_consumption:{outputs:renderReceipt.result.outputs,
            unverified_products:renderReceipt.result.inherited_products.unverified_products,
            original_execution:renderReceipt.execution,
            scope:'Actual mounted DSH native/PTC provider inputs and unchanged original Bridge multi-product receipt. Historical mocked output files are not reopened; this does not verify Karma pixels or checkpoint/delegate completion.'}}:{}),
          bridgeCalls,events:agent.session.snapshotEvents()})
      } catch(error) {fail(error)}
    })
    return () => {for(const id of jobWaiters.keys())releaseJob(id);server.close()}
  })
}
