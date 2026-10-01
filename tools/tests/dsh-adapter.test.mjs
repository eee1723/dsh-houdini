import assert from 'node:assert/strict'
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

const ctx=new Context()
new SystemPrompt(ctx,{})
const tools=new ToolRuntime(ctx,{mode:'both'})
installHoudiniExecutionLog(ctx)
const session=Session.create('dsh02-api'),agent={id:session.id,session,options:{provider:'fixture',model:'image'}}
let savedImages=0
ctx.provide('llm',{async resolveModelInfo(){return {inputModalities:['text','image']}}})
ctx.provide('attachments',{imageLimits:{mediaTypes:['image/png'],maxImageBytes:100,maxMessageImageBytes:200,maxImagesPerMessage:4},
  async saveImage({data}){return {attachmentId:'image-'+(++savedImages),mediaType:'image/png',bytes:data.length,width:1,height:1}}})
let executed=0
registerHoudiniTools(ctx,{async fetchMedia(){return Buffer.from('image')},async exec(){executed++;return {ok:true,stdout:'',stderr:'',result:{box:executed},images:['C:/fixture/output.png'],
  execution:{runtime_id:'runtime',sequence:executed,observed_at:executed}}},
  async submitJob(){return {jobId:'a'.repeat(12),requestReceipt:{request_ref:'b'.repeat(32)+'.'+'c'.repeat(32),status:'job_submitted'}}},
  async cancelJob(){return {jobId:'a'.repeat(12),status:'cancelled',ok:false,stdout:'',stderr:''}}})
// The registry's real PTC bridge receives the provider's binding calls.
ctx.provide('ptcRuntime',{language:'typescript',resolve:request=>request,async run(request){
  const value=await request.bindings[0].functions.houdini_exec({code:'__result__ = "nested"'})
  return {value,logs:[]}
}})
const signal=new AbortController().signal
function logNative(callId,name,args,result) {
  session.append('tool/call',{turn:1,step:1,callId,name,arguments:JSON.stringify(args)})
  session.append('tool/result',{turn:1,step:1,message:createToolResultMessage({callId,content:result.content,isError:result.isError}),
    ...(result.meta===undefined?{}:{meta:result.meta})},{surfaceOp:'append'})
}
const native=await tools.execute({callId:'native',name:'houdini_exec',arguments:{code:'__result__ = "native"'},agent,signal})
assert.equal(native.isError,false)
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
console.log('DSH 0.2 API: real native and nested registry dispatch, one execution each, durable fact round-trip passed')
