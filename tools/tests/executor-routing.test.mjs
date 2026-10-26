import {foldExecutorBinding} from '../../lib/executor-identity-projection.js'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'
import http from 'node:http'
import {spawn} from 'node:child_process'
import {once} from 'node:events'
import {fileURLToPath} from 'node:url'
import {Context} from '@deepseek-ai/cordis'
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection'
import {agentPresetProjectionDefinition} from '@deepseek-ai/dsh-agent-preset-registry'
import {remoteMethods} from '@deepseek-ai/dsh-typert-protocol'
import {ExecutorDirectory,ExecutorRouter} from '../../lib/executor-routing.js'
import {ExecutorController} from '../../lib/executor-controller.js'
import {registerExecutorIdentityProjection,foldExecutorState,projectedExecutorState} from '../../lib/executor-identity-projection.js'
import * as executorHost from '../../lib/executor-host.js'
import {ExecutorBinding,recordedExecutorIdentity} from '../../lib/executor-binding.js'
import {EXPECTED_EXECUTION_CONTRACT_VERSION as version,EXPECTED_VERB_CATALOG_HASH as hash} from '../../lib/generated-verb-contract.js'
import {fixtureSession} from './fixture-session.mjs'
import {executionHistory} from '../../lib/execution-history.js'

const directory=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-routing-'))
const endpoints=path.join(directory,'endpoints');await fs.mkdir(endpoints)
const installation=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..')
const servers=[],records=[],agents=[],claims=[],bodies=[],health=[]
const healthGates=[null,null]
const healthFailures=[false,false],children=[]
const requestIndexes=[new Map(),new Map()]
const gate=()=>{let enter,release;return {entered:new Promise(resolve=>enter=resolve),wait:new Promise(resolve=>release=resolve),
  enter:()=>enter(),release:()=>release()}}
const unfinished=(agent,index,callId)=>{
  const record=records[index]
  agent.session.append('tool/call',{callId,name:'houdini_exec',arguments:'{}'})
  agent.session.append('tool/result',{message:{source:{callId}},meta:{canonical:{ok:false,requestReceipt:{
    request_ref:record.runtime_id+'.'+'f'.repeat(32),runtime_id:record.runtime_id,executor_id:record.executor_id,
    scene_epoch:record.scene_epoch,status:'unknown_transport'}}}},{surfaceOp:'append'})
  assert.equal(executionHistory(agent.session.snapshotEvents()).unresolvedCalls.length,1)
}
const write=record=>fs.writeFile(path.join(endpoints,record.executor_id+'.json'),JSON.stringify(record))
const signal=new AbortController().signal
try {
  for(let i=0;i<2;i++) {
    const session=fixtureSession('task-'+i,{agentPreset:'houdini'})
    agents.push({id:session.id,status:'idle',session})
    health.push({activeRequests:0,activeJobs:0})
    const server=http.createServer(async(req,res)=>{
      const record=records[i]
      res.setHeader('content-type','application/json')
      if(req.headers['x-dsh-houdini-executor']!==record.executor_id){res.writeHead(409);res.end('{}');return}
      let text='';for await(const chunk of req)text+=chunk
      const body=text?JSON.parse(text):{}
      bodies.push({executor:record.executor_id,route:req.url,body})
      if(req.url==='/health'||req.url==='/requests/prepare') {
        if(req.url==='/health'&&healthFailures[i]){res.statusCode=503;res.end(JSON.stringify({error:'fixture endpoint unavailable'}));return}
        const pending=healthGates[i]
        if(pending){healthGates[i]=null;pending.enter();await pending.wait}
        res.end(JSON.stringify({ok:true,executorId:record.executor_id,houVersion:record.houdini_version,
          runtimeId:record.runtime_id,sceneEpoch:record.scene_epoch,...health[i],executionContractVersion:version,
          verbCatalog:{hash},requestRef:record.runtime_id+'.'+'a'.repeat(32)}));return
      }
      if(req.url==='/executor/claim') {
        claims.push({executor:record.executor_id,...body})
        record.task_id=body.task_id;await write(record)
        res.end(JSON.stringify({ok:true}));return
      }
      if(req.url==='/requests/status') {
        assert.equal(body.request_ref,'index')
        res.end(JSON.stringify({ok:true,stdout:'',stderr:'',requestReceipt:{status:'index',runtime_id:record.runtime_id,
          requests:requestIndexes[i].get(body.owner_session)??[],omitted:0}}));return
      }
      await new Promise(resolve=>setTimeout(resolve,i?1:15))
      res.end(JSON.stringify({ok:true,stdout:'',stderr:'',result:{target:record.executor_id}}))
    })
    servers.push(server);await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
    const record={schema:1,executor_id:String(i+1).repeat(32),registration_id:String(i+5).repeat(32),runtime_id:String(i+3).repeat(32),
      installation,bridge_url:`http://127.0.0.1:${server.address().port}`,houdini_version:i?'22.0.368':'21.0.440',pid:100+i,
      state:'registered',task_id:null,workbench:true,scene_id:String(i+7).repeat(32),scene_epoch:(i?'a':'9').repeat(32),hip_is_new:false,
      hip_path:path.join(directory,'project-'+i,'asset.hip'),workspace_path:path.join(directory,'project-'+i)}
    record.runtime={hfs:path.join(directory,'H'+i),python:path.join(directory,'H'+i,'python.exe'),
      pythonVersion:i?'3.13.7':'3.11.7',executable:path.join(directory,'H'+i,'houdini.exe')}
    records.push(record);await write(record)
  }
  const identityOf=session=>projectedExecutorState(ctx,session)
  let durable=true,questions=0,answer=records[1].executor_id
  const router=new ExecutorRouter(new ExecutorDirectory(directory,installation),1000,new ExecutorBinding(session=>foldExecutorBinding(session.snapshotEvents())),identityOf,
    id=>!agents.find(agent=>agent.id===id)||agents.find(agent=>agent.id===id).status==='idle',async()=>durable,
    async(_task,candidates)=>{questions++;return candidates.find(record=>record.executor_id===answer)?.executor_id})
  const ctx=new Context(),projections=new SessionProjectionRegistry(ctx)
  projections.register(agentPresetProjectionDefinition);registerExecutorIdentityProjection(ctx)
  ctx.provide('agents',{get:id=>agents.find(agent=>agent.id===id)})
  ctx.provide('sessions',{flush:async()=>durable})
  ctx.provide('sessionController',{resolveAgent:async id=>({agent:agents.find(agent=>agent.id===id)})})
  const controller=new ExecutorController(ctx,router)
  assert.deepEqual(remoteMethods(controller).map(method=>method.method),['openWorkspace','list','select','clear'])
  const input=(agent,record)=>({sessionId:agent.id,executorId:record.executor_id,registrationId:record.registration_id,expectedHip:record.hip_path,
    runtimeId:record.runtime_id,sceneEpoch:record.scene_epoch})
  const context=index=>({agent:agents[index],signal})
  const initial=await controller.list({sessionId:agents[0].id})
  assert.equal(initial.state.status,'unbound')
  assert(initial.candidates.every(record=>record.connection_status==='pending'))
  assert.equal(claims.length,0)
  await assert.rejects(router.resolveRuntime(context(0)),/houdini_installation/)
  assert.equal(questions,0,'independent work cannot silently choose a live scene by workspace')
  await controller.select(input(agents[0],records[0]),signal)
  await controller.select(input(agents[1],records[1]),signal)
  const requestsBeforeRuntime=bodies.length,questionsBeforeRuntime=questions
  healthFailures.fill(true)
  records[0].state='disconnected';await write(records[0])
  const runtimes=await Promise.all([router.resolveRuntime(context(0)),router.resolveRuntime(context(1))])
  assert.deepEqual(runtimes.map(value=>value.runtime),records.map(record=>record.runtime),
    'independent runs use each session\'s exact selected installation, including disconnected records')
  assert.equal(bodies.length,requestsBeforeRuntime,'installation resolution sends no request to unavailable live endpoints')
  assert.equal(questions,questionsBeforeRuntime,'independent runtime selection cannot open a scene chooser')
  const recordedRuntime=records[0].runtime;delete records[0].runtime;await write(records[0])
  await assert.rejects(router.resolveRuntime(context(0)),/houdini_installation/,'old records require an explicit installation, never another target or Host HFS')
  records[0].runtime=recordedRuntime;await write(records[0])
  const invalidRuntime={...records[0],runtime:{...recordedRuntime,python:'python.exe'}};await write(invalidRuntime)
  await assert.rejects(router.resolveRuntime(context(0)),/Invalid registered Houdini installation runtime/)
  await write(records[0])
  await assert.rejects(router.resolve(context(0)),/disconnected/,'offline runtime metadata cannot grant live access')
  records[0].state='registered';await write(records[0]);healthFailures.fill(false)
  assert.equal(claims.length,0,'select does not acquire a writer')
  assert.equal((await controller.list({sessionId:agents[0].id})).state.status,'selected')
  const bridges=await Promise.all([router.resolve(context(0)),router.resolve(context(1))])
  const results=await Promise.all(bridges.map((bridge,index)=>bridge.exec('pass',{sessionId:agents[index].id,callId:'read-'+index},signal,undefined,true)))
  assert.deepEqual(results.map(result=>result.result.target),records.map(record=>record.executor_id),'interleaved calls retain their own target')
  assert.equal(claims.length,0,'read calls never claim a writer')
  for(const request of bodies.filter(row=>row.route==='/requests/prepare')) {
    const record=records.find(row=>row.executor_id===request.executor)
    assert.equal(request.body.runtime_id,record.runtime_id)
    assert.equal(request.body.scene_epoch,record.scene_epoch)
  }
  await router.resolve(context(0),{write:true})
  assert.equal(claims.length,1)
  assert.equal(claims[0].runtime_id,records[0].runtime_id)
  assert.equal(claims[0].scene_epoch,records[0].scene_epoch)

  // Many conversations may select one scene. Only actual writes contend.
  await controller.select(input(agents[1],records[0]),signal)
  agents[0].status='running'
  await router.resolve(context(1))
  await assert.rejects(router.resolve(context(1),{write:true}),/另一段对话仍在执行/)
  agents[0].status='idle'
  await router.resolve(context(1),{write:true})
  agents[1].session.append('tool/call',{callId:'finished-work',name:'houdini_inspect',arguments:'{}'})
  await controller.select(input(agents[1],records[1]),signal)
  assert.equal(foldExecutorState(agents[1].session.snapshotEvents()).selectedTarget.executor_id,records[1].executor_id,
    'executed conversation selection does not require a checkpoint')

  // A live original job/request prevents changing or clearing its task target.
  unfinished(agents[0],0,'original-unknown-request')
  records[0].task_id=agents[0].id;await write(records[0]);health[0].activeJobs=1
  requestIndexes[0].set(agents[0].id,[{status:'done',active:true}])
  await assert.rejects(controller.select(input(agents[0],records[1]),signal),/后台任务执行/)
  await assert.rejects(controller.clear({sessionId:agents[0].id},signal),/后台任务执行/)
  health[0].activeJobs=0
  requestIndexes[0].set(agents[0].id,[{status:'done',active:false}])
  await controller.clear({sessionId:agents[0].id},signal)
  assert.equal((await controller.list({sessionId:agents[0].id})).selectedTarget,null)
  const asked=questions
  await assert.rejects(router.resolve(context(0)),/解除/)
  assert.equal(questions,asked,'clear never auto-binds a later request')

  const firstUse=fixtureSession('first-use',{agentPreset:'houdini',cwd:records[0].workspace_path})
  await router.resolve({agent:{id:firstUse.id,status:'running',session:firstUse},signal})
  assert.equal(questions,asked+1,'a matching workspace never substitutes for an explicit user target choice')
  assert.equal(foldExecutorState(firstUse.snapshotEvents()).selectedTarget.executor_id,records[1].executor_id,
    'the user can choose another scene even when the workspace has exactly one matching candidate')
  const ambiguous=fixtureSession('choose-use',{agentPreset:'houdini',cwd:directory})
  await router.resolve({agent:{id:ambiguous.id,status:'running',session:ambiguous},signal})
  assert.equal(questions,asked+2)
  assert.equal(foldExecutorState(ambiguous.snapshotEvents()).selectedTarget.executor_id,records[1].executor_id)
  answer=undefined
  const skipped=fixtureSession('skip-use',{agentPreset:'houdini',cwd:directory})
  await assert.rejects(router.resolve({agent:{id:skipped.id,status:'running',session:skipped},signal}),/没有选择/)
  assert.equal(foldExecutorState(skipped.snapshotEvents()).selectedTarget,null)

  // Actual delayed HTTP health responses prove choices execute in invocation
  // order, rather than whichever endpoint happens to answer first.
  const makeAgent=id=>{const session=fixtureSession(id,{agentPreset:'houdini'});return {id,session,status:'idle'}}
  const choose=(agent,index,signal)=>router.selectTarget(agent,records[index].executor_id,records[index].registration_id,signal,records[index].hip_path)
  const settledWhileOtherWorks=makeAgent('settled-while-other-works');await choose(settledWhileOtherWorks,0)
  unfinished(settledWhileOtherWorks,0,'settled-original-with-stale-history')
  requestIndexes[0].set(settledWhileOtherWorks.id,[{status:'done',active:false}])
  records[0].task_id=agents[1].id;await write(records[0]);health[0].activeJobs=1
  await choose(settledWhileOtherWorks,1)
  assert.equal(foldExecutorState(settledWhileOtherWorks.session.snapshotEvents()).selectedTarget.executor_id,records[1].executor_id,
    'another conversation job must not stop a settled conversation leaving its old target')
  health[0].activeJobs=0
  for(const status of ['queued','running']) {
    const current=makeAgent('own-'+status);await choose(current,0)
    unfinished(current,0,'original-'+status)
    requestIndexes[0].set(current.id,[{status,active:true}]);health[0].activeRequests=1
    await assert.rejects(choose(current,1),/后台任务执行/)
    await assert.rejects(router.clear(current),/后台任务执行/)
    requestIndexes[0].set(current.id,[]);health[0].activeRequests=0
  }
  const sameTarget=makeAgent('same-target-job');await choose(sameTarget,0)
  const selected=foldExecutorState(sameTarget.session.snapshotEvents()).selectedTarget,jobId='b'.repeat(12)
  sameTarget.session.append('tool/call',{callId:'active-submit',name:'houdini_job_submit',arguments:'{}'})
  sameTarget.session.append('tool/result',{message:{source:{callId:'active-submit'}},meta:{canonical:{jobId,
    requestReceipt:{jobId,runtime_id:records[0].runtime_id,executor_id:records[0].executor_id,status:'job_submitted'}}}},{surfaceOp:'append'})
  const activeBoundary=foldExecutorState(sameTarget.session.snapshotEvents()).recoverySeq
  const oldGeneration=records[0].registration_id,oldTask=records[0].task_id
  records[0].task_id=sameTarget.id;records[0].registration_id='d'.repeat(32);await write(records[0]);health[0].activeJobs=1
  requestIndexes[0].set(sameTarget.id,[{status:'done',active:true}])
  assert.equal(executionHistory(sameTarget.session.snapshotEvents()).activeJobs.length,1)
  await router.selectTarget(sameTarget,records[0].executor_id,selected.registration_id,signal,records[0].hip_path)
  assert.equal(foldExecutorState(sameTarget.session.snapshotEvents()).recoverySeq,activeBoundary)
  assert.deepEqual(executionHistory(sameTarget.session.snapshotEvents()).activeJobs,[[jobId,'queued_or_unknown']],
    'same-scene reselect keeps the live background job visible despite a discovery-generation change')
  await assert.rejects(router.clear(sameTarget),/后台任务执行/)
  health[0].activeJobs=0;records[0].registration_id=oldGeneration;records[0].task_id=oldTask;await write(records[0])
  requestIndexes[0].set(sameTarget.id,[])
  const fifoClear=makeAgent('fifo-select-clear'),slow=gate();healthGates[0]=slow
  const firstChoice=choose(fifoClear,0);await slow.entered
  let clearCompleted=false
  const laterClear=router.clear(fifoClear).then(()=>{clearCompleted=true})
  await new Promise(resolve=>setImmediate(resolve));assert.equal(clearCompleted,false)
  slow.release();await Promise.all([firstChoice,laterClear])
  assert.equal(foldExecutorState(fifoClear.session.snapshotEvents()).selectedTarget,null,'a later clear wins over an earlier slow choice')
  const fifoTwo=makeAgent('fifo-select-select'),twoGate=gate();healthGates[0]=twoGate
  const chooseA=choose(fifoTwo,0);await twoGate.entered
  const chooseB=choose(fifoTwo,1);twoGate.release();await Promise.all([chooseA,chooseB])
  assert.equal(foldExecutorState(fifoTwo.session.snapshotEvents()).selectedTarget.executor_id,records[1].executor_id)
  const fifoAbort=makeAgent('fifo-clear-select-abort');await choose(fifoAbort,0)
  unfinished(fifoAbort,0,'pending-before-queued-choice')
  const clearGate=gate();healthGates[0]=clearGate
  const clearing=router.clear(fifoAbort);await clearGate.entered
  const cancellation=new AbortController()
  const cancelled=assert.rejects(choose(fifoAbort,1,cancellation.signal),/abort/i)
  cancellation.abort();clearGate.release();await Promise.all([clearing,cancelled])
  assert.equal(foldExecutorState(fifoAbort.session.snapshotEvents()).selectedTarget,null,'an aborted queued choice cannot undo clear')
  await choose(fifoAbort,1)
  assert.equal(foldExecutorState(fifoAbort.session.snapshotEvents()).selectedTarget.executor_id,records[1].executor_id)
  const queuedStale=makeAgent('fifo-registration-recheck'),registrationGate=gate();healthGates[0]=registrationGate
  const beforeRegistration=choose(queuedStale,0);await registrationGate.entered
  const staleChoice=assert.rejects(choose(queuedStale,1),/选择已过期/)
  const oldRegistration=records[1].registration_id
  records[1].registration_id='e'.repeat(32);await write(records[1])
  registrationGate.release();await Promise.all([beforeRegistration,staleChoice])
  assert.equal(foldExecutorState(queuedStale.session.snapshotEvents()).selectedTarget.executor_id,records[0].executor_id)
  records[1].registration_id=oldRegistration;await write(records[1])
  const clearStarted=makeAgent('clear-agent-recheck');await choose(clearStarted,0)
  unfinished(clearStarted,0,'pending-before-clear-recheck')
  const idleGate=gate();healthGates[0]=idleGate
  const retainedClear=assert.rejects(router.clear(clearStarted),/Agent started/);await idleGate.entered
  clearStarted.status='running';idleGate.release();await retainedClear
  assert.equal(foldExecutorState(clearStarted.session.snapshotEvents()).selectedTarget.executor_id,records[0].executor_id)

  // A dead participating process can leave its discovery row registered.
  // A living but unresponsive process remains unknown, never inferred dead.
  const liveUnknown=makeAgent('live-unresponsive'),oldPid=records[0].pid
  await choose(liveUnknown,0)
  unfinished(liveUnknown,0,'real-unresolved-live-request')
  const settledClear=makeAgent('settled-clear-offline'),settledSelect=makeAgent('settled-select-offline')
  await choose(settledClear,0);await choose(settledSelect,0)
  records[0].pid=process.pid;await write(records[0]);healthFailures[0]=true
  const oldProbes=bodies.filter(row=>row.executor===records[0].executor_id&&row.route==='/health').length
  await router.clear(settledClear);await choose(settledSelect,1)
  assert.equal(foldExecutorState(settledClear.session.snapshotEvents()).selectedTarget,null)
  assert.equal(foldExecutorState(settledSelect.session.snapshotEvents()).selectedTarget.executor_id,records[1].executor_id)
  assert.equal(bodies.filter(row=>row.executor===records[0].executor_id&&row.route==='/health').length,oldProbes,
    'settled conversations can explicitly leave an unavailable old endpoint without probing it')
  await assert.rejects(router.clear(liveUnknown),/无法确认原目标/)
  await assert.rejects(choose(liveUnknown,1),/无法确认原目标/)
  healthFailures[0]=false
  const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:'ignore',windowsHide:true});children.push(child)
  await once(child,'spawn')
  records[0].pid=child.pid;await write(records[0])
  const deadClear=makeAgent('dead-clear'),deadSelect=makeAgent('dead-select')
  await choose(deadClear,0);await choose(deadSelect,0)
  unfinished(deadClear,0,'dead-original-request-clear');unfinished(deadSelect,0,'dead-original-request-select')
  const exited=once(child,'exit');child.kill();await exited
  healthFailures[0]=true
  await router.clear(deadClear)
  await choose(deadSelect,1)
  assert.equal(foldExecutorState(deadClear.session.snapshotEvents()).selectedTarget,null)
  assert.equal(foldExecutorState(deadSelect.session.snapshotEvents()).selectedTarget.executor_id,records[1].executor_id)
  assert.equal((await router.directory.find(records[0].executor_id)).state,'registered','dead-process clear does not fabricate a registry rewrite')
  healthFailures[0]=false;records[0].pid=oldPid;await write(records[0])

  await controller.select(input(agents[0],records[0]),signal)
  const originalEpoch=records[0].scene_epoch
  records[0].scene_epoch='f'.repeat(32);await write(records[0])
  await assert.rejects(router.resolve(context(0)),/代际已变化/)
  assert.equal((await controller.list({sessionId:agents[0].id})).state.status,'stale')
  const historical=await router.resolveHistorical(context(0),{executorId:records[0].executor_id,runtimeId:records[0].runtime_id})
  assert.equal(historical.targetExecutorId,records[0].executor_id,'historical requests remain readable after scene changes')
  assert.equal((await router.resolveHistorical(context(1),{runtimeId:records[0].runtime_id})).targetExecutorId,records[0].executor_id)
  await assert.rejects(router.resolveHistorical(context(0),{executorId:records[1].executor_id,runtimeId:records[0].runtime_id}),/运行代际已结束/)
  records[0].scene_epoch=originalEpoch;await write(records[0])
  durable=false
  const before=bodies.length
  await assert.rejects(router.resolve(context(0)),/尚未可靠保存/)
  assert.equal(bodies.length,before)
  durable=true
  const retained=await router.resolve(context(0))
  router.dispose()
  await assert.rejects(retained.inspectExecutor(signal),/unloaded|aborted/)
  // Normal process retirement preserves recovery evidence without exhausting
  // discovery or making each bound tool enumerate the entire registry history.
  const retired=Array.from({length:256},(_,index)=>({...records[1],
    executor_id:index.toString(16).padStart(32,'0'),state:'disconnected'}))
  await Promise.all(retired.map(write))
  const withHistory=await router.directory.list()
  assert.equal(withHistory.length,258)
  assert.equal(withHistory.filter(r=>r.state==='disconnected').length,256)
  assert.equal((await router.directory.find(records[1].executor_id)).executor_id,records[1].executor_id)
  await assert.rejects(router.directory.find(retired[0].executor_id),/disconnected/)
  const foreign={...records[1],executor_id:'e'.repeat(32),installation:path.join(directory,'other-install')}
  await write(foreign)
  await assert.rejects(router.directory.find(foreign.executor_id),/disconnected or absent/)
  assert.equal((await router.directory.list()).length,258)
  const malformed='f'.repeat(32)
  const malformedFile=path.join(endpoints,malformed+'.json')
  await fs.writeFile(malformedFile,'{}')
  assert.equal((await router.directory.find(records[1].executor_id)).executor_id,records[1].executor_id,
    'unrelated malformed history cannot redirect or block an already bound target')
  await assert.rejects(router.directory.find(malformed),/Invalid executor record/)
  await assert.rejects(router.directory.list(),/Invalid executor record/)
  await fs.unlink(malformedFile)
  await assert.rejects(router.directory.find('../outside'),/Invalid executor identity/)
  await fs.symlink(directory,malformedFile,process.platform==='win32'?'junction':'dir')
  await assert.rejects(router.directory.find(malformed),/Invalid executor record path\/size/)
  await fs.unlink(malformedFile)
  await Promise.all(retired.map(record=>write({...record,state:'registered'})))
  await assert.rejects(router.directory.list(),/Registered executor discovery budget exceeded/)
  assert.equal((await router.directory.find(records[1].executor_id)).executor_id,records[1].executor_id,
    'discovery capacity cannot block an existing bound identity')
  console.log('executor routing: read/write separation, explicit reselect/clear, first-use choice, stale fencing, original-runtime queries and registry boundaries passed')
}finally{
  for(const child of children)if(child.exitCode===null&&child.signalCode===null)child.kill()
  await Promise.all(servers.map(server=>new Promise(resolve=>server.close(resolve))))
  await fs.rm(directory,{recursive:true,force:true})
}
