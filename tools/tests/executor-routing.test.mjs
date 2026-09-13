import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'
import http from 'node:http'
import {pathToFileURL,fileURLToPath} from 'node:url'
import {Context} from '@deepseek-ai/cordis'
import {Session} from '@deepseek-ai/dsh-session'
import {remoteMethods} from '@deepseek-ai/dsh-typert-protocol'
import {ExecutorDirectory,ExecutorRouter} from '../../lib/executor-routing.js'
import {ExecutorController} from '../../lib/executor-controller.js'
import * as executorHost from '../../lib/executor-host.js'
import {ExecutorBindingBarrier,recordedExecutorIdentity} from '../../lib/execution-state.js'
import {registerHoudiniTools} from '../../lib/tools.js'
import {EXPECTED_EXECUTION_CONTRACT_VERSION as version,EXPECTED_VERB_CATALOG_HASH as hash} from '../../lib/generated-verb-contract.js'

const directory=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-routing-'))
const endpoints=path.join(directory,'endpoints')
await fs.mkdir(endpoints)
const servers=[],records=[],agents=[],calls=[],flushed=[]
const write=r=>fs.writeFile(path.join(endpoints,r.executor_id+'.json'),JSON.stringify(r))
try {
  for(let i=0;i<2;i++) {
    const id=String(i+1).repeat(32),runtime=String(i+3).repeat(32),task='task-'+i
    const session=Session.create(task,[],{version:3,id:task,createdAt:1,isSeeded:false,agentPreset:'houdini'})
    agents.push({id:task,status:'idle',session})
    const server=http.createServer(async(req,res)=>{
      res.setHeader('content-type','application/json')
      if(req.headers['x-dsh-houdini-executor']!==id){res.writeHead(409);res.end('{}');return}
      let text='';for await(const chunk of req)text+=chunk
      const body=text?JSON.parse(text):{}
      if(req.url==='/health'||req.url==='/requests/prepare'){
        res.end(JSON.stringify({ok:true,executorId:id,houVersion:i?'22.0.368':'21.0.440',runtimeId:runtime,
          executionContractVersion:version,verbCatalog:{hash},requestRef:runtime+'.'+'a'.repeat(32)}));return
      }
      if(req.url==='/exec'||req.url==='/jobs') {
        assert(flushed.includes(task),'never execute before target durability')
        assert.equal(body.owner_session,task,'a shared tool instance sent the other task to this Bridge')
      }
      calls.push([task,req.url])
      // Force interleaving so a mutable global target would send the wrong task.
      await new Promise(resolve=>setTimeout(resolve,i?1:15))
      res.end(JSON.stringify({ok:true,stdout:'',stderr:'',result:{target:id},jobId:'job-'+i,status:'done',
        requestReceipt:{request_ref:runtime+'.'+'a'.repeat(32),runtime_id:runtime,status:'done'}}))
    })
    servers.push(server)
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
    const record={schema:1,executor_id:id,registration_id:String(i+5).repeat(32),runtime_id:runtime,
      installation:directory,bridge_url:`http://127.0.0.1:${server.address().port}`,
      houdini_version:i?'22.0.368':'21.0.440',pid:100+i,state:'registered',task_id:task,hip_path:path.join(directory,task+'.hip')}
    records.push(record);await write(record)
  }
  const flush=async s=>{flushed.push(s.id);return true}
  const router=new ExecutorRouter(new ExecutorDirectory(directory,directory),1000,new ExecutorBindingBarrier(flush))
  const ctx=new Context()
  ctx.provide('agents',{get:id=>agents.find(a=>a.id===id)})
  const controller=new ExecutorController(ctx,router)
  assert.deepEqual(remoteMethods(controller).map(m=>m.method),['list','select'])
  assert.equal(controller.typertRemote.namespace,'houdiniTargets')
  assert.equal((await controller.list()).candidates.length,2)
  let gateway
  if(process.env.DSH_TEST_GATEWAY_ROOT) {
    const modules=process.env.DSH_TEST_GATEWAY_ROOT
    const {default:Registry}=await import(pathToFileURL(path.join(modules,'dsh-typert-registry/lib/index.js')))
    const {default:Gateway}=await import(pathToFileURL(path.join(modules,'dsh-api-gateway/lib/index.js')))
    new Registry(ctx)
    gateway=new Gateway(ctx,{websocketHeartbeatIntervalMs:2000})
    assert.equal((await gateway.invoke({namespace:'houdiniTargets',method:'list',args:{}})).candidates.length,2)
  }
  const context=i=>({agent:agents[i],callId:'call-'+i})
  await assert.rejects(controller.select({sessionId:agents[0].id,executorId:records[0].executor_id,
    registrationId:records[0].registration_id,expectedHip:path.join(directory,'wrong.hip')},new AbortController().signal),/HIP changed/)
  await assert.rejects(router.resolve(context(0)),/Choose a Houdini/)
  await assert.rejects(router.sceneContextFor(agents[0].session),/No Houdini target/)
  await assert.rejects(router.selectInitial(agents[0],records[1].executor_id,records[1].registration_id),/writer reservation/)
  await assert.rejects(router.selectInitial(agents[0],records[0].executor_id,'stale'),/stale/)
  agents[0].status='running'
  await assert.rejects(router.selectInitial(agents[0],records[0].executor_id,records[0].registration_id),/idle/)
  agents[0].status='idle'
  for(let i=0;i<2;i++) {
    const input={sessionId:agents[i].id,executorId:records[i].executor_id,registrationId:records[i].registration_id,expectedHip:records[i].hip_path}
    if(gateway) await gateway.invoke({namespace:'houdiniTargets',method:'select',args:{input},signal:new AbortController().signal})
    else await controller.select(input,new AbortController().signal)
  }
  if(gateway) console.log('Real DSH Typert Gateway list/select dispatch passed')
  assert.equal(recordedExecutorIdentity(agents[0].session.snapshotEvents()),records[0].executor_id)
  await assert.rejects(router.selectInitial(agents[0],records[1].executor_id,records[1].registration_id),/recovery/)
  const defs=new Map()
  registerHoudiniTools({tools:{register:d=>defs.set(d.name,d)},sessions:{flush}},router)
  const values=await Promise.all([0,1].map(i=>defs.get('houdini_exec').execute({code:'pass'},context(i))))
  assert.deepEqual(values.map(v=>v.result.target),records.map(r=>r.executor_id))
  await Promise.all([0,1].map(i=>defs.get('houdini_job_submit').execute({code:'pass'},context(i))))
  await Promise.all([0,1].map(i=>defs.get('houdini_job_cancel').execute({jobId:'job-'+i},context(i))))
  assert(calls.some(c=>c[0]==='task-0'&&c[1]==='/jobs/job-0/cancel'))
  assert(calls.some(c=>c[0]==='task-1'&&c[1]==='/jobs/job-1/cancel'))
  const before=calls.length
  // One Host-plane controller survives removal of either preset consumer.
  const hostContext=new Context()
  hostContext.provide('agents',{get:id=>agents.find(a=>a.id===id)})
  hostContext.provide('sessions',{flush})
  // Fixture installation must be the actual candidate root used by Host apply.
  const candidateRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..')
  for(const record of records) await write({...record,installation:candidateRoot})
  let host=await hostContext.plugin(executorHost,{executorRegistry:directory,requestTimeoutMs:1000})
  const controller1=hostContext.get('houdiniTargets')
  assert(controller1)
  assert.throws(()=>executorHost.apply(hostContext,{executorRegistry:directory,requestTimeoutMs:1000}),/already mounted/)
  await assert.rejects(async()=>executorHost.sharedExecutorConnection(hostContext,path.join(directory,'other')).resolve(context(0)),/configuration differs/)
  let consumerA,consumerB
  const presetA=await hostContext.plugin({apply(c){consumerA=executorHost.sharedExecutorConnection(c,directory)}})
  const presetB=await hostContext.plugin({apply(c){consumerB=executorHost.sharedExecutorConnection(c,directory)}})
  const oldBridge=await consumerB.resolve(context(1))
  await presetA.dispose()
  assert.equal(hostContext.get('houdiniTargets').typertRemote.namespace,'houdiniTargets')
  await host.dispose()
  await assert.rejects(async()=>consumerB.resolve(context(1)),/unavailable/)
  await assert.rejects(oldBridge.exec('pass',undefined,undefined,{sessionId:agents[1].id,callId:'old'}),/unloaded|aborted/)
  assert.equal(calls.length,before,'unloaded service cannot dispatch through a retained Bridge')
  host=await hostContext.plugin(executorHost,{executorRegistry:directory,requestTimeoutMs:1000})
  assert.equal(hostContext.get('houdiniTargets').typertRemote.namespace,'houdiniTargets')
  await consumerB.resolve(context(1))
  await presetB.dispose();await host.dispose()
  for(const record of records) await write(record)
  await write({...records[0],state:'disconnected'})
  await assert.rejects(defs.get('houdini_exec').execute({code:'pass'},context(0)),/disconnected/)
  assert.equal(calls.length,before)
  assert.equal((await defs.get('houdini_exec').execute({code:'pass'},context(1))).result.target,records[1].executor_id)
  await write({...records[0],bridge_url:'http://example.com:8765'})
  await assert.rejects(router.directory.list(),/Invalid executor record/)
  await write({...records[0],runtime_id:'f'.repeat(32)})
  await assert.rejects(router.resolve(context(0)),/generation changed/)
  await write({...records[0],task_id:null,hip_path:null})
  await assert.rejects(router.resolve(context(0)),/writer reservation/)
  console.log('shared executor routing: explicit durable selection, concurrent tools, job isolation, disconnect and fail-closed discovery passed')
}finally{
  await Promise.all(servers.map(s=>new Promise(resolve=>s.close(resolve))))
  await fs.rm(directory,{recursive:true,force:true})
}
