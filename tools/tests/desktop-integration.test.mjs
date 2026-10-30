import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {DesktopIntegration,DesktopIntents} from '../../lib/desktop-integration.js'
import {HoudiniBridge} from '../../lib/bridge.js'
import {HoudiniFrontend} from '../../lib/frontend-host.js'
import {processStarted} from '../../lib/desktop-process.js'
import {EXPECTED_EXECUTION_CONTRACT_VERSION,EXPECTED_VERB_CATALOG_HASH} from '../../lib/generated-verb-contract.js'

const home=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-desktop-integration-'))
const previous=process.env.DSH_HOME
process.env.DSH_HOME=home
const calls=[]
const targets={registry:path.join(home,'dsh-houdini/executors'),openWorkspace:async input=>{
  calls.push(input);await new Promise(resolve=>setTimeout(resolve,10))
  return {workspaceId:'native-workspace',sessionId:input.requestId,executorId:input.executorId}
}}
const ctx={logger:{warn:error=>{throw Error(error)}}}
const service=new DesktopIntegration(ctx,targets,async()=>[])
try {
  await service.start()
  const descriptor=JSON.parse(await fs.readFile(path.join(home,'dsh-houdini/desktop.json'),'utf8'))
  const base=`http://127.0.0.1:${descriptor.port}`
  assert.equal(descriptor.executorRegistry,targets.registry)
  const request=(route,body,headers={})=>fetch(base+route,{method:'POST',headers:{'content-type':'application/json',
    Authorization:'Bearer '+descriptor.token,...headers},body:JSON.stringify(body),signal:AbortSignal.timeout(3000)})
  assert.equal((await request('/status',{})).status,200)
  assert.equal((await request('/status',{}, {Authorization:'Bearer incorrect'})).status,401)
  assert.equal((await request('/status',{}, {Origin:'https://unrelated.example'})).status,401)
  for(const route of ['/exec','/api/session/create','/dialog','/shell'])assert.equal((await request(route,{})).status,400)
  const payload={executorId:'a'.repeat(32),registrationId:'b'.repeat(32),requestId:'c'.repeat(32),expectedHip:path.join(home,'scene.hip')}
  for(const body of [{...payload,code:'hou.hipFile.clear()'},{...payload,expectedHip:'relative.hip'},
    {...payload,requestId:'../../foreign'},{...payload,executorId:'other'}])assert.equal((await request('/open-workspace',body)).status,400)
  const responses=await Promise.all([request('/open-workspace',payload),request('/open-workspace',payload)])
  assert.ok(responses.every(response=>response.status===200))
  assert.equal(calls.length,1,'a retried menu request does not create another native session')
  assert.equal((await request('/open-workspace',{...payload,executorId:'d'.repeat(32)})).status,400)
  assert.equal(calls.length,1,'request identity cannot be reused for a different scene')
  const intent=await service.intent(0,new AbortController().signal)
  assert.equal(intent.selection.sessionId,payload.requestId)
  assert.equal(intent.selection.source,'menu')
  service.intents.acknowledge(intent.sequence-1)
  assert.ok((await service.intent(0,new AbortController().signal)).selection,'an old acknowledgement cannot consume a newer intent')
  service.intents.acknowledge(intent.sequence)
  const abort=new AbortController()
  const waiting=service.intent(intent.sequence,abort.signal)
  abort.abort(Error('fixture cancellation'))
  await assert.rejects(waiting,/fixture cancellation/)
  const duplicate=new DesktopIntegration(ctx,targets,async()=>[])
  await assert.rejects(duplicate.start(),/已有 Houdini 插件接入服务/)
  assert.deepEqual(JSON.parse(await fs.readFile(path.join(home,'dsh-houdini/desktop.json'),'utf8')),descriptor,
    'another Host cannot replace an active Desktop descriptor')
  await assert.rejects(service.project({action:'new',sessionId:'standard-session',hfs:home},new AbortController().signal))
  const record={schema:1,executor_id:'a'.repeat(32),registration_id:'b'.repeat(32),runtime_id:'c'.repeat(32),
    installation:home,bridge_url:'http://127.0.0.1:18765',houdini_version:'22.0.368',pid:process.pid,processStarted:await processStarted(process.pid),state:'registered',
    task_id:'session-a',hip_path:'E:/work/scene.hip',workbench:true,scene_id:'d'.repeat(32),scene_epoch:'e'.repeat(32),
    hip_is_new:false,workspace_path:'E:/work'}
  targets.getRouter=()=>({directory:{list:async()=>[record]}})
  const inspect=HoudiniBridge.prototype.observeExecutor
  try {
    HoudiniBridge.prototype.observeExecutor=async()=>({ok:true,executorId:record.executor_id,runtimeId:record.runtime_id,sceneEpoch:record.scene_epoch,
      activeRequests:2,activeJobs:1,executionContractVersion:117})
    const [observed]=await service.presence()
    assert.equal(observed.candidate,record,'the client receives the original registry candidate')
    assert.equal(observed.executorId,record.executor_id)
    assert.equal(observed.hipPath,record.hip_path)
    assert.equal(observed.ownerSessionId,'session-a')
    assert.ok(Number.isFinite(observed.observedAt),'each health observation has its own freshness')
    assert.equal(observed.activeRequests,2)
    assert.equal(observed.activeJobs,1)
    assert.equal(observed.busy,true)
  } finally {HoudiniBridge.prototype.observeExecutor=inspect}
  const mismatch=await HoudiniFrontend.prototype.projectPresence.call({desktop:()=>({presence:async()=>[
    {status:'online',contractVersion:1}]})},new AbortController().signal)
  assert.equal(mismatch[0].contractMismatch,true)
  assert.equal(mismatch[0].status,'unknown')
  const catalogMismatch=await HoudiniFrontend.prototype.projectPresence.call({desktop:()=>({presence:async()=>[
    {status:'online',contractVersion:EXPECTED_EXECUTION_CONTRACT_VERSION,verbCatalogHash:'old-catalog'},
    {status:'online',contractVersion:EXPECTED_EXECUTION_CONTRACT_VERSION,verbCatalogHash:EXPECTED_VERB_CATALOG_HASH}]})},new AbortController().signal)
  assert.equal(catalogMismatch[0].contractMismatch,true,'the UI rejects the same catalog mismatch as execution admission')
  assert.equal(catalogMismatch[1].contractMismatch,false)
  assert.equal(catalogMismatch[1].status,'online')
} finally {
  await service.dispose()
  assert.equal(await fs.stat(path.join(home,'dsh-houdini/desktop.json')).then(()=>true,()=>false),false)
  if(previous===undefined)delete process.env.DSH_HOME;else process.env.DSH_HOME=previous
}

const intents=new DesktopIntents(),selection={workspaceId:'w',sessionId:'s',executorId:'e',source:'menu'}
let ignoredVersion='',settingsRevision=4,preferencesWritable=true
const preferences=[]
const availableUpdate={state:'available',title:'有可选更新',message:'可以继续使用当前版本。',update:{version:'0.1.4',urgency:'optional'}}
const preferenceStatus={...availableUpdate}
const preferenceHost={ctx:{get:name=>name==='settings'?{
  get writable(){return preferencesWritable},describe:()=>[{ns:'houdini-frontend',revision:settingsRevision}],
  update:async(ns,patch,revision)=>{assert.equal(ns,'houdini-frontend');assert.equal(revision,settingsRevision);preferences.push(patch);ignoredVersion=patch.ignoredPluginVersion;settingsRevision++},
}:null},updates:{read:async()=>preferenceStatus},config:{ignoredPluginVersion:{get:()=>ignoredVersion}}}
const preferenceCall=input=>HoudiniFrontend.prototype.pluginUpdates.call(preferenceHost,input,new AbortController().signal)
assert.equal((await preferenceCall({})).canIgnore,true)
assert.equal((await preferenceCall({ignoreVersion:'0.1.4'})).ignoredVersion,'0.1.4')
assert.deepEqual(preferences,[{ignoredPluginVersion:'0.1.4'}],'dismissal uses the native settings namespace, not browser-origin storage')
assert.equal((await HoudiniFrontend.prototype.pluginUpdates.call({...preferenceHost}, {},new AbortController().signal)).ignoredVersion,'0.1.4',
  'a replacement service reads the same saved profile preference')
preferenceStatus.update={...preferenceStatus.update,urgency:'required'}
assert.equal((await preferenceCall({})).canIgnore,false)
await assert.rejects(preferenceCall({ignoreVersion:'0.1.4'}),/信息已变化/)
preferenceStatus.update={...preferenceStatus.update,urgency:'optional'}
preferencesWritable=false;assert.equal((await preferenceCall({})).canIgnore,false)
await assert.rejects(preferenceCall({ignoreVersion:'0.1.4'}),/无法保存/)
assert.equal(preferences.length,1)
const sequence=intents.publish(selection)
const stop=new AbortController()
let delivered=false
const pending=intents.read(sequence,stop.signal).then(()=>{delivered=true},()=>{})
await new Promise(resolve=>setTimeout(resolve,25))
assert.equal(delivered,false,'a pending unacknowledged intent must not cause a polling busy loop')
stop.abort();await pending
console.log('Desktop integration: fixed authenticated routes, duplicate/stale requests, foreign origins, active Host isolation, navigation acknowledgement and cancellation passed')
