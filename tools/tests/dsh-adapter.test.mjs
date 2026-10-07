import assert from 'node:assert/strict'
import fs from 'node:fs'
import {Context} from '@deepseek-ai/cordis'
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt'
import {ToolRuntime} from '@deepseek-ai/dsh-tools'
import {Session} from '@deepseek-ai/dsh-session'
import {createToolResultMessage} from '@deepseek-ai/dsh-llm'
import {validateStoredEvents} from '@deepseek-ai/dsh-session-persistence'
import {registerHoudiniTools} from '../../lib/tools.js'
import {executionHistory} from '../../lib/execution-history.js'
import {projectExecutionNotice} from '../../lib/execution-state.js'
import {installHoudiniExecutionLog} from '../../lib/dsh-adapter.js'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {apply as applySpillPolicy} from '@deepseek-ai/dsh-spill-policy'

const ctx=new Context()
const outcomeFixtures=process.env.DSH_OUTCOME_FIXTURE
  ? JSON.parse(fs.readFileSync(process.env.DSH_OUTCOME_FIXTURE,'utf8')) : null
new SystemPrompt(ctx,{})
const tools=new ToolRuntime(ctx,{mode:'both'})
installHoudiniExecutionLog(ctx)
const session=Session.create('dsh02-api'),agent={id:session.id,session,options:{provider:'fixture',model:'image'}}
if(outcomeFixtures) await new ExecutorBinding().ensure(session,outcomeFixtures.caught_read.execution.executor_id)
let savedImages=0
ctx.provide('llm',{async resolveModelInfo(){return {inputModalities:['text','image']}}})
ctx.provide('attachments',{imageLimits:{mediaTypes:['image/png'],maxImageBytes:100,maxMessageImageBytes:200,maxImagesPerMessage:4},
  async saveImage({data}){return {attachmentId:'image-'+(++savedImages),mediaType:'image/png',bytes:data.length,width:1,height:1}}})
let executed=0
let capturesExecuted=0
let bridgeReceipt
registerHoudiniTools(ctx,{targetExecutorId:outcomeFixtures?.caught_read?.execution?.executor_id,
  async fetchMedia(){return Buffer.from('image')},async exec(){executed++;if(bridgeReceipt)return structuredClone(bridgeReceipt);return {ok:true,stdout:'',stderr:'',result:{box:executed},images:['C:/fixture/output.png'],
  execution:{runtime_id:'runtime',sequence:executed,observed_at:executed}}},
  async captureUi(args,owner){capturesExecuted++;return {ok:true,stdout:'',stderr:'',
    result:{node:args.node,path:'C:/fixture/ui.png',scene_writes:0,semantic_status:'unverified',user_state_restored:true},
    images:['C:/fixture/ui.png'],evidence:[{operation:'ui_capture',scene_writes:0,semantic_status:'unverified'}],
    outcome:{batch:'completed',operations:{total:1,failed:0},checks:{failed:0,warning:0,unverified:0}},transaction:{status:'no_scene_change'},
    execution:{runtime_id:'capture-runtime',sequence:capturesExecuted,observed_at:10+capturesExecuted},
    requestReceipt:{request_ref:'ui-'+capturesExecuted,owner_call:owner.callId,status:'done'}}},
  async submitJob(){return {jobId:'a'.repeat(12),requestReceipt:{request_ref:'b'.repeat(32)+'.'+'c'.repeat(32),status:'job_submitted'}}},
  async cancelJob(){return {jobId:'a'.repeat(12),status:'cancelled',ok:false,stdout:'',stderr:''}}})
// The registry's real PTC bridge receives the provider's binding calls.
let ptcBindingValue
ctx.provide('ptcRuntime',{language:'typescript',resolve:request=>request,async run(request){
  const value=String(request.program).includes('houdini_ui_screenshot')
    ? await request.bindings[0].functions.houdini_ui_screenshot({node:'/obj/demo/CTRL',view:'parameters'})
    : await request.bindings[0].functions.houdini_exec({code:'__result__ = "nested"'})
  ptcBindingValue=value
  return {value,logs:[]}
}})
const signal=new AbortController().signal
function logNative(callId,name,args,result) {
  session.append('tool/call',{turn:1,step:1,callId,name,arguments:JSON.stringify(args)})
  session.append('tool/result',{turn:1,step:1,message:createToolResultMessage({callId,content:result.content,isError:result.isError}),
    ...(result.meta===undefined?{}:{meta:result.meta})},{surfaceOp:'append'})
}
const native=await tools.execute({callId:'native',name:'houdini_exec',arguments:{code:'__result__ = "native"'},agent,signal})
assert.equal(native.isError,false,JSON.stringify(native))
logNative('native','houdini_exec',{code:'__result__ = "native"'},native)
const nested=await tools.execute({callId:'program',name:'run_code',arguments:{code:'return await tools.houdini_exec({code:"nested"})',description:'Exercise nested Houdini execution'},agent,signal})
assert.equal(nested.isError,false,JSON.stringify(nested))
logNative('program','run_code',{},nested)
assert.equal(nested.additionalContexts.length,1,'nested images reach the model once through DSH')
assert.equal(nested.additionalContexts[0].content.filter(block=>block.type==='image').length,1)
assert.equal(executed,2,'log adaptation must not repeat either scene operation')
const before=executionHistory(session.snapshotEvents())
assert.equal(before.rows.length,2)
assert.deepEqual(before.rows.map(row=>row.value.result.box),[1,2])
const nestedEvent=session.snapshotEvents().find(event=>event.type==='tool/ptc-dispatch')
assert.equal(JSON.parse(nestedEvent.data.content[0].text).kind,'dsh-houdini/execution-v1')
assert(!nested.content[0].text.includes('dsh-houdini/execution-v1'),'the durable wrapper never enters the model summary')
const persisted=validateStoredEvents(session.header,JSON.parse(JSON.stringify(session.snapshotEvents())))
const restored=Session.create(session.id,persisted,session.header)
assert.deepEqual(executionHistory(restored.snapshotEvents()).rows.map(row=>row.value.result.box),[1,2])
const submit=await tools.execute({callId:'job-submit',name:'houdini_job_submit',arguments:{code:'pass'},agent,signal})
assert.equal(submit.isError,false)
assert.deepEqual(submit.meta.canonical,submit.value,'native admission stores the same value as nested dispatch, without invented execution success')
logNative('job-submit','houdini_job_submit',{code:'pass'},submit)
assert.equal(projectExecutionNotice(session.snapshotEvents()).active_jobs.length,1)
const cancel=await tools.execute({callId:'job-cancel',name:'houdini_job_cancel',arguments:{jobId:'a'.repeat(12)},agent,signal})
assert.equal(cancel.isError,false)
assert.deepEqual(cancel.meta.canonical,cancel.value,'queued cancellation is retained even without an execution observation')
logNative('job-cancel','houdini_job_cancel',{jobId:'a'.repeat(12)},cancel)
assert.equal(projectExecutionNotice(session.snapshotEvents()),null,'real DSH metadata clears the cancelled job from recorded active work')
const nativeCapture=await tools.execute({callId:'capture-native',name:'houdini_ui_screenshot',arguments:{node:'/obj/demo/CTRL'},agent,signal})
assert.equal(nativeCapture.isError,false,JSON.stringify(nativeCapture))
logNative('capture-native','houdini_ui_screenshot',{node:'/obj/demo/CTRL'},nativeCapture)
assert.equal(nativeCapture.meta.canonical.result.scene_writes,0)
assert.equal(nativeCapture.meta.canonical.result.semantic_status,'unverified')
assert.equal(nativeCapture.meta.canonical.verbs,undefined,'native UI observation has no fake Python ledger')
assert.equal(nativeCapture.content.filter(block=>block.type==='image').length,1)
const nestedCapture=await tools.execute({callId:'capture-program',name:'run_code',arguments:{
  code:'return await tools.houdini_ui_screenshot({node:"/obj/demo/CTRL"})',description:'Observe native parameter layout'},agent,signal})
assert.equal(nestedCapture.isError,false,JSON.stringify(nestedCapture))
logNative('capture-program','run_code',{},nestedCapture)
assert.equal(nestedCapture.additionalContexts.length,1)
assert.equal(nestedCapture.additionalContexts[0].content.filter(block=>block.type==='image').length,1)
assert.equal(capturesExecuted,2,'native/nested persistence cannot repeat a UI request')
assert.equal(executed,2,'UI captures do not execute Python scene operations')
const captureRows=executionHistory(session.snapshotEvents()).rows.filter(row=>row.tool==='houdini_ui_screenshot')
assert.equal(captureRows.length,2)
assert(captureRows.every(row=>row.value.verbs===undefined&&row.value.result.scene_writes===0))
assert(captureRows.every(row=>row.value.requestReceipt.status==='done'&&row.value.imageAttachments.length===1))
assert(captureRows.every(row=>row.value.evidence[0].operation==='ui_capture'&&row.value.outcome.checks.unverified===0),
  'semantic status remains in UI observation facts, not a fabricated Python check')
const captureStored=validateStoredEvents(session.header,JSON.parse(JSON.stringify(session.snapshotEvents())))
assert.deepEqual(executionHistory(Session.create(session.id,captureStored,session.header).snapshotEvents()).rows.filter(row=>row.tool==='houdini_ui_screenshot').map(row=>row.value),captureRows.map(row=>row.value))
assert.equal(projectExecutionNotice(session.snapshotEvents()),null)
console.log('UI captures: real native/PTC registry, image attachments, durable exact facts and one request each passed')
// Optional exact receipts from the isolated HOM caught-failure regression:
// same bytes reach real native and PTC registry paths, with no hand-built
// outcome oracle standing in for the Python producer.
if (outcomeFixtures) {
  for (const [name,receipt] of Object.entries(outcomeFixtures)) {
    bridgeReceipt=receipt
    const callId='outcome-'+name
    const direct=await tools.execute({callId,name:'houdini_exec',arguments:{code:'fixture'},agent,signal})
    assert.equal(direct.isError,false,'caught reads and returned checks do not fail Python execution')
    assert.deepEqual(direct.meta.canonical.outcome,receipt.outcome)
    assert.deepEqual(direct.value.result,receipt.result,'fallback/check result remains available')
    const text=direct.content.filter(b=>b.type==='text').map(b=>b.text).join('\n')
    assert.match(text,name==='caught_read'?/Batch completed; one or more operations raised errors/:/checks failed or contain warnings/)
    assert.doesNotMatch(text,/Executed successfully/)
    logNative(callId,'houdini_exec',{code:'fixture'},direct)
    const ptcId=callId+'-ptc'
    const ptc=await tools.execute({callId:ptcId,name:'run_code',arguments:{code:'return await tools.houdini_exec({code:"fixture"})',description:'Read exact Houdini outcome'},agent,signal})
    assert.equal(ptc.isError,false,JSON.stringify(ptc))
    assert.deepEqual(ptcBindingValue.outcome,receipt.outcome,'PTC code consumes the same wire outcome')
    assert.deepEqual(ptcBindingValue.result,receipt.result)
    logNative(ptcId,'run_code',{},ptc)
    const rows=executionHistory(session.snapshotEvents()).rows.filter(row=>row.value.outcome)
    assert.deepEqual(rows.at(-1).value.outcome,receipt.outcome,'PTC persists the same outcome as native dispatch')
    assert.deepEqual(rows.at(-1).value.result,receipt.result)
  }
  console.log('Exact Houdini receipts: caught read/fallback and failed validation survive native/PTC dispatch')
}
// Use the released middleware, not a hand-written truncator. A display spill
// must never cut the PTC audit JSON in its middle or lose later failure facts.
const spillCtx=new Context()
new SystemPrompt(spillCtx,{})
const spillRuntime=new ToolRuntime(spillCtx,{mode:'both'})
const spillCopies=[]
spillCtx.provide('spillStore',{async saveText(input){spillCopies.push(input.content);return {
  locator:'fixture:retained',retrievalHint:'Read the retained fixture',bytes:Buffer.byteLength(input.content)}}})
applySpillPolicy(spillCtx,{maxInlineTokens:1000})
installHoudiniExecutionLog(spillCtx)
const spillSession=Session.create('dsh02-spill-audit')
const spillAgent={id:spillSession.id,session:spillSession,options:{provider:'fixture',model:'text'}}
const largeReceipt={ok:false,stdout:'large process log '.repeat(12000),stderr:'',error:'FINAL_WRITE_FAILED',
  result:{kind:'houdini/node-delivery-v1',nodes:[]},outcome:{batch:'failed',operations:{failed:1}},
  execution:{owner_session:spillSession.id,executor_id:'a'.repeat(32),runtime_id:'b'.repeat(32),sequence:1,observed_at:1,hip_path:'fixture.hip'},
  verbs:[{verb:'tool_package_create',ok:false,error:'FINAL_WRITE_FAILED',summary:{restored:false,package_exists:true}}]}
let spillExecuted=0
registerHoudiniTools(spillCtx,{async exec(){spillExecuted++;return structuredClone(largeReceipt)}})
spillCtx.provide('ptcRuntime',{language:'typescript',resolve:request=>request,async run(request){
  return {value:await request.bindings[0].functions.houdini_exec({code:'fixture'}),logs:[]}
}})
spillSession.append('tool/call',{turn:1,step:1,callId:'large-program',name:'run_code',arguments:JSON.stringify({code:'fixture'})})
const spilled=await spillRuntime.execute({callId:'large-program',name:'run_code',
  arguments:{code:'return await tools.houdini_exec({code:"fixture"})',description:'Retain original audit facts'},agent:spillAgent,signal})
assert.equal(spilled.isError,false)
assert(spillCopies.length>0&&spilled.content[0].text.includes('Full formatted result stored at:'),'the actual model display policy remains active')
assert(!spilled.content[0].text.includes('dsh-houdini/execution-v1'),'audit framing is not model-facing text')
assert.equal(spillExecuted,1,'retention never retries a scene operation')
const durable=spillSession.snapshotEvents().find(e=>e.type==='tool/ptc-dispatch')
const durableValue=JSON.parse(durable.data.content[0].text).value
assert.deepEqual(durableValue,largeReceipt,'large PTC audit JSON remains valid and complete after the released spill policy')
const spillStored=validateStoredEvents(spillSession.header,JSON.parse(JSON.stringify(spillSession.snapshotEvents())))
assert.deepEqual(executionHistory(Session.create(spillSession.id,spillStored,spillSession.header).snapshotEvents()).rows[0].value,largeReceipt)
console.log('DSH 0.2 API: native/nested dispatch, durable replay, exact large receipts with real display spill, one execution each passed')
