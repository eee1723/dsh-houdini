import assert from 'node:assert/strict'
import http from 'node:http'
import {HoudiniBridge} from '../../lib/bridge.js'
import {requireExecutorContinuity,ExecutorBindingBarrier,installExecutorBinding,repairExecutorBindingOrder} from '../../lib/execution-state.js'
import {Session} from '@deepseek-ai/dsh-session'
import {Context} from '@deepseek-ai/cordis'
import {createAssistantMessage,createToolResultMessage,createUserMessage} from '@deepseek-ai/dsh-llm'
import {inject as pluginInject} from '../../lib/index.js'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {registerHoudiniTools} from '../../lib/tools.js'
import {EXPECTED_EXECUTION_CONTRACT_VERSION as version, EXPECTED_VERB_CATALOG_HASH as hash} from '../../lib/generated-verb-contract.js'

const first='a'.repeat(32), second='b'.repeat(32)
function assistant(session) {
  session.append('assistant/message',{turn:1,step:1,stream:[],message:createAssistantMessage({
    content:[{type:'tool-call',id:'first-call',name:'houdini_query',arguments:'{}'},
      {type:'tool-call',id:'second-call',name:'ask_user_question',arguments:'{}'}],
    source:{kind:'model',provider:'fixture',model:'fixture'},
  })},{surfaceOp:'append'})
}
function result(session,id,text) {
  session.append('tool/result',{turn:1,step:1,message:createToolResultMessage({callId:id,
    content:[{type:'text',text}],isError:false})},{surfaceOp:'append'})
}
function protocolValid(session) {
  const pending=new Set()
  for(const m of session.deriveMessages()) {
    const results=m.content.filter(c=>c.type==='tool-result')
    if(pending.size&&!results.length) return false
    for(const c of m.content) {
      if(c.type==='tool-call') pending.add(c.id)
      if(c.type==='tool-result'&&!pending.delete(c.toolCallId)) return false
    }
  }
  return pending.size===0
}
const baseline=Session.create('legacy-binding')
await new ExecutorBindingBarrier(async()=>true).ensure(baseline,first)
const binding=baseline.snapshotEvents()[0].data
const broken=Session.create('broken-batch')
assistant(broken)
broken.append('user/message',binding,{surfaceOp:'append'})
result(broken,'first-call','Actual query failed before dispatch')
result(broken,'second-call','User selected metres')
assert.equal(protocolValid(broken),false)
const immutablePrefix=JSON.stringify(broken.snapshotEvents())
assert.equal(repairExecutorBindingOrder(broken),1)
assert.equal(protocolValid(broken),true)
assert.equal(JSON.stringify(broken.snapshotEvents().slice(0,JSON.parse(immutablePrefix).length)),immutablePrefix)
assert(broken.deriveMessages().at(-1).content[0].text.includes('User selected metres'))
assert.equal(repairExecutorBindingOrder(broken),0)
requireExecutorContinuity(broken.snapshotEvents(),first)
let retryHook,repairFlushes=0
installExecutorBinding({on:(_name,fn)=>retryHook=fn,sessions:{flush:async()=>{if(++repairFlushes===1)throw new Error('flush failed');return true}}},first)
await assert.rejects(retryHook({agent:{session:broken},signal:new AbortController().signal},async()=>({kind:'enter',messages:[]})),/flush failed/)
await retryHook({agent:{session:broken},signal:new AbortController().signal},async()=>({kind:'enter',messages:[]}))
assert.equal(repairFlushes,2,'a failed repair flush must not be skipped on the next step')
const userInterleaved=Session.create('user-interleaved')
assistant(userInterleaved)
userInterleaved.append('user/message',binding,{surfaceOp:'append'})
result(userInterleaved,'first-call','first')
userInterleaved.append('user/message',createUserMessage({content:[{type:'text',text:'Real user intervention'}],source:{kind:'user'}}),{surfaceOp:'append'})
result(userInterleaved,'second-call','second')
const userBefore=JSON.stringify(userInterleaved.snapshotEvents())
assert.throws(()=>repairExecutorBindingOrder(userInterleaved),/unrelated/)
assert.equal(JSON.stringify(userInterleaved.snapshotEvents()),userBefore,'never compact unrelated user input automatically')
const incomplete=Session.create('incomplete')
assistant(incomplete);incomplete.append('user/message',binding,{surfaceOp:'append'});result(incomplete,'first-call','only one result')
const incompleteBefore=JSON.stringify(incomplete.snapshotEvents())
assert.throws(()=>repairExecutorBindingOrder(incomplete),/missing or unrelated/)
assert.equal(JSON.stringify(incomplete.snapshotEvents()),incompleteBefore)
const busy=Session.create('busy')
assistant(busy)
const busyBefore=JSON.stringify(busy.snapshotEvents())
await assert.rejects(new ExecutorBindingBarrier(async()=>true).ensure(busy,first),/before model tool calls/)
assert.equal(JSON.stringify(busy.snapshotEvents()),busyBefore)

// New binding is accepted in the pre-step message batch, not inserted during tools.
let hook
installExecutorBinding({on:(name,fn)=>{assert.equal(name,'agent/pre-step');hook=fn},sessions:{flush:async()=>true}},first)
const fresh=Session.create('fresh-batch')
const decision=await hook({agent:{session:fresh},signal:new AbortController().signal},async()=>({kind:'enter',messages:[
  createUserMessage({content:[{type:'text',text:'Inspect the scene'}],source:{kind:'user'}})]}))
assert.equal(fresh.snapshotEvents().length,0,'pre-step must not append behind the driver')
for(const m of decision.messages) fresh.append('user/message',m,{surfaceOp:'append'})
assistant(fresh)
let actualFlushes=0
const realContext=new Context(),defs=new Map()
realContext.provide('tools',{register:d=>defs.set(d.name,d)})
realContext.provide('systemPrompt',{})
realContext.provide('skills',{})
realContext.provide('sessions',{flush:async()=>{actualFlushes++;return true}})
let sends=0
const fiber=await realContext.plugin({inject:pluginInject,apply:ctx=>registerHoudiniTools(ctx,{
  targetExecutorId:first,exec:async()=>{sends++;return {ok:true,stdout:'',stderr:''}}})})
await defs.get('houdini_query').execute({code:'__result__=1'},{agent:{id:fresh.id,session:fresh},callId:'first-call'})
assert.equal(actualFlushes,1,'actual scoped Cordis access must declare sessions')
assert.equal(sends,1)
result(fresh,'first-call','query result');result(fresh,'second-call','answer')
assert.equal(protocolValid(fresh),true)
await fiber.dispose()
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-binding-durability-'))
try {
  const session=Session.create('binding-test')
  const file=path.join(directory,'events.json')
  let release, flushes=0
  const barrier=new ExecutorBindingBarrier(async s=>{
    flushes++
    await new Promise(resolve=>{release=resolve})
    fs.writeFileSync(file,JSON.stringify(s.snapshotEvents()))
    return true
  })
  let sent=false
  const one=barrier.ensure(session,first).then(()=>{sent=true})
  const two=barrier.ensure(session,first)
  await Promise.resolve()
  assert.equal(sent,false)
  assert.equal(flushes,1)
  assert.equal(session.snapshotEvents().length,1)
  release();await Promise.all([one,two])
  assert.equal(sent,true)
  // Real DSH session schema round-trip, without any tool/result ever arriving.
  const restored=Session.create('binding-restored',JSON.parse(fs.readFileSync(file,'utf8')))
  await assert.rejects(new ExecutorBindingBarrier(async()=>true).ensure(restored,second),/requires recovery/)
  await new ExecutorBindingBarrier(async()=>true).ensure(restored,first)
  assert.equal(restored.snapshotEvents().filter(e=>e.type==='user/message').length,1,'resume does not duplicate binding; DSH may add an end-seed marker')
  let attempts=0
  const failedSession=Session.create('binding-failed')
  const failing=new ExecutorBindingBarrier(async()=>{if(++attempts===1)throw new Error('disk full');return true})
  await assert.rejects(failing.ensure(failedSession,first),/disk full/)
  await failing.ensure(failedSession,first)
  assert.equal(attempts,2)
  assert.equal(failedSession.snapshotEvents().length,1,'failed flush retries same record')
  await assert.rejects(new ExecutorBindingBarrier(async()=>false).ensure(Session.create('no-backend'),first),/no durable/)
  const cancelled=Session.create('cancelled'), abort=new AbortController()
  const cancelBarrier=new ExecutorBindingBarrier(async()=>{abort.abort();return true})
  await assert.rejects(cancelBarrier.ensure(cancelled,first,abort.signal),/abort/i)
  requireExecutorContinuity(cancelled.snapshotEvents(),first)
  await assert.rejects(new ExecutorBindingBarrier(async()=>true).ensure(cancelled,second),/requires recovery/)
} finally {fs.rmSync(directory,{recursive:true,force:true})}
function history(identity, name='houdini_exec', args={code:'pass'}, id='call') {
  return [{type:'tool/call',data:{name,args,callId:id}},
    {type:'tool/result',data:{message:{source:{callId:id}},meta:{canonical:{execution:{executor_id:identity}}}}}]
}
const prior=history(first)
const jobHistory=[{type:'tool/call',data:{name:'houdini_job_submit',callId:'job'}},
  {type:'tool/result',data:{message:{source:{callId:'job'}},meta:{canonical:{requestReceipt:{executor_id:first,status:'unknown_transport'}}}}}]
assert.throws(()=>requireExecutorContinuity(jobHistory,second),/requires recovery/)
requireExecutorContinuity(jobHistory,first)
requireExecutorContinuity(prior,first)
requireExecutorContinuity([],second)
requireExecutorContinuity(history(undefined),second)
assert.throws(()=>requireExecutorContinuity(prior,second),/requires recovery/)
assert.throws(()=>requireExecutorContinuity(prior),/requires recovery/)
assert.throws(()=>requireExecutorContinuity([...prior,...history(second,'houdini_exec',{},'other')],second),/requires recovery/)
requireExecutorContinuity(history(first,'houdini_query',{result_ref:'retained'}),second)
requireExecutorContinuity([...prior,...history(second).slice(1)],first) // replay cannot rebind
assert.throws(()=>requireExecutorContinuity(history('malformed'),first),/Invalid recorded/)
const definitions=new Map()
registerHoudiniTools({tools:{register(d){definitions.set(d.name,d)}}}, {targetExecutorId:second})
const context={agent:{id:'task',session:{snapshotEvents:()=>prior}},callId:'now'}
for(const name of ['houdini_exec','houdini_query','houdini_job_submit','houdini_job_status','houdini_job_cancel']){
  await assert.rejects(definitions.get(name).execute({code:'pass',jobId:'j'},context),/requires recovery/)
}
// Source material remains inspectable without calling any Bridge method.
const sourceContext={...context,agent:{...context.agent,session:{snapshotEvents:()=>[
  ...prior,{type:'user/message',seq:3,data:{source:{kind:'user'},content:[{type:'text',text:'Recreate the reference'}]}}]}}}
const sourceResult=await definitions.get('houdini_query').execute({source_ref:'index'},sourceContext)
assert.equal(sourceResult.ok,true)
let target=first, replaceAfterPrepare=false, dispatched=[]
const server=http.createServer(async(req,res)=>{
  res.setHeader('content-type','application/json')
  const expected=req.headers['x-dsh-houdini-executor']
  if(expected!==target){res.writeHead(409);res.end(JSON.stringify({error:'executor_mismatch'}));return}
  let text='';for await(const chunk of req) text+=chunk
  if(req.url==='/requests/prepare'||req.url==='/health'){
    res.end(JSON.stringify({ok:true,executorId:target,runtimeId:'c'.repeat(32),requestRef:'c'.repeat(32)+'.'+'d'.repeat(32),
      executionContractVersion:version,verbCatalog:{hash}}))
    if(replaceAfterPrepare)target=second
    return
  }
  dispatched.push(req.url)
  if(req.url==='/media?path=x.png'){res.end(Buffer.from([1,2]));return}
  res.end(JSON.stringify({ok:true,stdout:'',stderr:'',jobId:'j',status:'done'}))
})
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
try{
  const url=`http://127.0.0.1:${server.address().port}`,owner={sessionId:'task',callId:'call'}
  assert.throws(()=>new HoudiniBridge(url,1000,'bad'),'invalid identity')
  const a=new HoudiniBridge(url,1000,first),b=new HoudiniBridge(url,1000,second)
  await a.exec('pass',undefined,undefined,owner)
  await a.sceneContext();await a.jobStatus('j');await a.cancelJob('j')
  await a.requestStatus('index',owner);await a.fetchMedia('x.png')
  assert.equal(dispatched.length,6)
  await assert.rejects(b.exec('pass',undefined,undefined,owner),/409/)
  assert.equal(dispatched.length,6)
  replaceAfterPrepare=true
  const unknown=await a.exec('must not reach replacement',undefined,undefined,owner)
  assert.equal(unknown.requestReceipt.status,'unknown_transport')
  assert.equal(unknown.requestReceipt.executor_id,first)
  assert.equal(dispatched.length,6,'target changed after handshake must reject actual request')
  for(const action of [()=>a.exec('pass',undefined,undefined,owner),()=>a.submitJob('pass',undefined,undefined,owner),
    ()=>a.sceneContext(),()=>a.jobStatus('j'),()=>a.cancelJob('j'),()=>a.requestStatus('index',owner),()=>a.fetchMedia('x.png')]){
    await assert.rejects(action,/409/)
  }
  assert.equal(dispatched.length,6,'reads, media and job control cannot cross target either')
  replaceAfterPrepare=false
  await b.exec('pass',undefined,undefined,owner)
  assert.equal(dispatched.length,7)
}finally{await new Promise(resolve=>server.close(resolve))}
console.log('executor binding: all routes, target mismatch and post-handshake replacement passed')
