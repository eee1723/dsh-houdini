import assert from 'node:assert/strict'
import http from 'node:http'
import {HoudiniBridge} from '../../lib/bridge.js'
import {HoudiniToolRuntime} from '../../lib/tool-runtime.js'
import {registerHoudiniTools} from '../../lib/tools.js'
import {EXPECTED_EXECUTION_CONTRACT_VERSION as version,EXPECTED_VERB_CATALOG_HASH as hash} from '../../lib/generated-verb-contract.js'
import {Context} from '@deepseek-ai/cordis'
import {createToolResultMessage} from '@deepseek-ai/dsh-llm'
import {fixtureProjectionContext,fixtureSession} from './fixture-session.mjs'
import {recordedExecutionOrigin} from '../../lib/execution-history.js'

const executorA='a'.repeat(32),executorB='b'.repeat(32),runtimeA='c'.repeat(32),runtimeB='d'.repeat(32)
const epochA='e'.repeat(32),epochB='f'.repeat(32),refA=runtimeA+'.'+'1'.repeat(32),job='2'.repeat(12)
const servers=[],requests=[]
let liveEpoch=epochA,edits=0
async function endpoint(executor,runtime) {
  const server=http.createServer(async(req,res)=>{
    const raw=await Array.fromAsync(req).then(chunks=>Buffer.concat(chunks).toString())
    const body=raw?JSON.parse(raw):{}
    requests.push({executor,path:req.url,body})
    res.setHeader('content-type','application/json')
    assert.equal(req.headers['x-dsh-houdini-executor'],executor)
    const health={ok:true,executorId:executor,runtimeId:runtime,sceneEpoch:liveEpoch,
      executionContractVersion:version,verbCatalog:{hash}}
    if(req.url==='/health')return res.end(JSON.stringify(health))
    if(req.url==='/requests/prepare') {
      if(body.scene_epoch&&body.scene_epoch!==liveEpoch){res.statusCode=409;return res.end(JSON.stringify({error:'scene changed'}))}
      return res.end(JSON.stringify({...health,requestRef:runtime+'.'+'3'.repeat(32)}))
    }
    if(req.url==='/requests/status')return res.end(JSON.stringify({ok:true,stdout:'',stderr:'',requestReceipt:{
      request_ref:body.request_ref,runtime_id:runtime,executor_id:executor,status:'running'}}))
    if(req.url===`/jobs/${job}/status`||req.url===`/jobs/${job}/cancel`)
      return res.end(JSON.stringify({ok:true,stdout:'',stderr:'',jobId:job,status:'done'}))
    if(req.url==='/exec'){edits++;return res.end(JSON.stringify({ok:true,stdout:'',stderr:''}))}
    if(req.url==='/ui/list'||req.url==='/ui/capture')return res.destroy() // admitted UI reply lost
    res.statusCode=404;res.end('{}')
  })
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));servers.push(server)
  return new HoudiniBridge('http://127.0.0.1:'+server.address().port,1000,executor,undefined,{runtimeId:runtime,sceneEpoch:epochA})
}
function event(value,seq=1){return{type:'tool/result',seq,time:seq,surfaceOp:'append',data:{message:createToolResultMessage({callId:'submit-'+seq,content:[],isError:false}),meta:{canonical:value}}}}
try {
  const a=await endpoint(executorA,runtimeA),b=await endpoint(executorB,runtimeB)
  let current=b,resolveCalls=0,historicalCalls=0
  const history=[event({jobId:job,requestReceipt:{request_ref:refA,runtime_id:runtimeA,executor_id:executorA,status:'job_submitted'}})]
  const session=fixtureSession('artist',{seed:history.map((event,seq)=>({...event,seq}))})
  const exec={agent:{id:'artist',session},callId:'lookup'}
  const connection={resolve:async()=>{resolveCalls++;return current},resolveHistorical:async(_exec,target)=>{
    historicalCalls++;assert.equal(target.runtimeId,runtimeA)
    assert.deepEqual(target,{runtimeId:runtimeA},'request references carry their original runtime without retaining a live per-job origin index')
    return a.forRuntime(target.runtimeId)
  }}
  const runtime=new HoudiniToolRuntime(fixtureProjectionContext(),connection)
  let origin=await runtime.historicalTarget(exec,{requestRef:refA})
  assert.equal((await origin.bridge.requestStatus(refA,origin.owner)).requestReceipt.executor_id,executorA)
  origin=await runtime.historicalTarget(exec,{requestRef:refA})
  assert.equal((await origin.bridge.jobStatus(job,origin.owner)).status,'done')
  assert.equal((await origin.bridge.cancelJob(job,origin.owner)).status,'done')
  assert.equal(resolveCalls,0,'historical controls must not resolve the new default scene')
  assert.equal(historicalCalls,2)
  assert(requests.every(row=>row.executor===executorA),'old requests and jobs must never be queried on B')
  for(const lookup of [()=>a.listUi(origin.owner),()=>a.captureUi({target:'ui:fixture'},origin.owner)]) {
    const lost=await lookup()
    assert.equal(lost.requestReceipt.status,'unknown_transport')
    assert.equal(lost.requestReceipt.scene_epoch,epochA,'lost UI receipts retain their admitted scene, so later status cannot become current after a reload')
    assert.equal(lost.requestReceipt.runtime_id,runtimeA)
    assert.equal(lost.requestReceipt.executor_id,executorA)
  }
  liveEpoch=epochB
  assert.equal((await origin.bridge.jobStatus(job,origin.owner)).status,'done','old runtime receipts remain queryable after its scene changes')
  const before=edits
  await assert.rejects(a.exec('never_run()',origin.owner),/scene changed|场景|工程/)
  assert.equal(edits,before,'a prepared call cannot silently adopt the currently loaded scene')
  const prepared=requests.findLast(row=>row.path==='/requests/prepare')
  assert.equal(prepared.body.scene_epoch,epochA)
  assert.equal(prepared.body.runtime_id,runtimeA)
  history.push(event({jobId:job,requestReceipt:{runtime_id:runtimeB,executor_id:executorB}},2))
  exec.agent.session=fixtureSession('artist',{seed:history.map((event,seq)=>({...event,seq}))})
  const count=requests.length
  assert.throws(()=>recordedExecutionOrigin(exec.agent.session.snapshotEvents(),{jobId:job}),/唯一确定/)
  assert.equal(requests.length,count,'a colliding short job id cannot guess between runtimes')
  history.pop()
  exec.agent.session=session
  servers[0].closeAllConnections();await new Promise(resolve=>servers[0].close(resolve))
  await assert.rejects((await runtime.historicalTarget(exec,{requestRef:refA})).bridge.requestStatus(refA,{sessionId:'artist',callId:'dead'}),/failed/)
  assert.equal(resolveCalls,0,'a dead original process must not fall back to the new selected target')

  // Real tool dispatch distinguishes reads, writes and historical controls.
  const definitions=new Map(),access=[],restored=[]
  const value={ok:true,stdout:'',stderr:'',result:{}}
  const fake={targetExecutorId:undefined,exec:async()=>value,listUi:async()=>value,captureUi:async()=>value,forRuntime(){return this},
    submitJob:async()=>({jobId:job,requestReceipt:{request_ref:refA,runtime_id:runtimeA}}),jobStatus:async()=>({...value,jobId:job,status:'done'})}
  const toolsContext=fixtureProjectionContext(new Context()),observers=[]
  toolsContext.provide('tools',{register:def=>definitions.set(def.name,def)})
  toolsContext.provide('houdiniRecovery',{beforeWrite:async agent=>restored.push(agent.id)})
  toolsContext.provide('jobs',{start(spec){const id='houdini-live-fixture';const hooks=spec.run({id,updateProgress(){},append(){}});observers.push(hooks.done);return id}})
  registerHoudiniTools(toolsContext,{resolve:async(_exec,options)=>{access.push(options.write);return fake}})
  const toolExec={agent:{id:'artist',ctx:toolsContext,session:fixtureSession('artist')},callId:'new-call'}
  for(const [name,args] of [['houdini_inspect',{code:'__result__=1'}],['houdini_ui_list',{}],['houdini_ui_screenshot',{target:'ui:fixture'}],
    ['houdini_exec',{code:'__result__=1'}],['houdini_job_submit',{code:'__result__=1'}]])await definitions.get(name).execute(args,toolExec)
  assert.deepEqual(access,[false,false,false,true,true])
  assert.deepEqual(restored,['artist','artist'],'only mutation admission may attempt saved node permission recovery')
  await Promise.all(observers)
  await toolsContext.fiber.dispose()
  console.log('target controls: explicit read/write separation, original-runtime request/job lookup, stale-scene rejection, collision/dead-target adversarial checks passed')
} finally {
  for(const server of servers)if(server.listening){server.closeAllConnections();await new Promise(resolve=>server.close(resolve))}
}
