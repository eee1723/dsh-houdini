import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {Context} from '@deepseek-ai/cordis'
import {Session} from '@deepseek-ai/dsh-session'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {HoudiniFrontend} from '../../lib/frontend-host.js'
import {workspaceOpeningMessage} from '../../lib/dsh-adapter.js'
import {EXPECTED_EXECUTION_CONTRACT_VERSION} from '../../lib/generated-verb-contract.js'

const directory=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-desktop-api-'))
const previous=process.env.DSH_HOUDINI_WORKBENCH_CONTEXT,originalFetch=globalThis.fetch
const context=new Context(),session=Session.create('original-project'),planning=Session.create('planning'),executor='a'.repeat(32)
const signal=new AbortController().signal
await new ExecutorBinding().ensure(session,executor)
session.append('user/message',workspaceOpeningMessage({executor_id:executor,scene_epoch:'b'.repeat(32),hip_path:path.join(directory,'saved.hip'),hip_is_new:false}),{surfaceOp:'append'})
context.provide('sessionQuery',{readSession:async id=>{assert([session.id,planning.id].includes(id));return {events:(id===session.id?session:planning).snapshotEvents()}}})
let active=false
context.provide('agents',{get:()=>({status:active?'running':'idle'})})
const frontend=new HoudiniFrontend(context,{})
const requests=[]
let generation='current-generation',result={accepted:true}
try {
  await fs.mkdir(path.join(directory,'workbench'))
  await fs.writeFile(path.join(directory,'context.json'),JSON.stringify({root:directory,workbench:true}))
  await fs.writeFile(path.join(directory,'workbench/desktop.json'),JSON.stringify({schema:1,controlPort:12345,token:'c'.repeat(64),generation}))
  process.env.DSH_HOUDINI_WORKBENCH_CONTEXT=path.join(directory,'context.json')
  globalThis.fetch=async(url,options)=>{
    assert.equal(options.headers.Authorization,'Bearer '+'c'.repeat(64))
    assert.equal(options.redirect,'error')
    requests.push({url,payload:JSON.parse(options.body)})
    return {ok:true,json:async()=>({ok:true,generation,result})}
  }
  await frontend.projectAction({action:'new'},signal)
  assert.deepEqual(requests.at(-1).payload,{action:'new'})
  await frontend.projectAction({action:'new',sessionId:session.id},signal)
  assert.deepEqual(requests.at(-1).payload,{action:'new'},'a bound conversation must not be repointed by New')
  await frontend.projectAction({action:'new',sessionId:planning.id},signal)
  assert.deepEqual(requests.at(-1).payload,{action:'new',bindSessionId:planning.id},'an unbound discussion keeps its context')
  active=true
  await assert.rejects(frontend.projectAction({action:'new',sessionId:planning.id},signal),/当前对话还在运行/)
  active=false
  await frontend.projectAction({action:'reopen',sessionId:session.id},signal)
  assert.deepEqual(requests.at(-1).payload,{action:'reopen',sessionId:session.id,executorId:executor,hip:path.join(directory,'saved.hip')})
  const count=requests.length
  await assert.rejects(frontend.projectAction({action:'open',hip:'C:/injected.hip'},signal),/请选择/)
  await assert.rejects(frontend.projectAction({action:'new',command:'execute anything'},signal),/请选择/)
  assert.equal(requests.length,count,'the browser cannot supply a command, executable or arbitrary file to the launch route')
  result=[{executorId:executor,status:'online',contractVersion:EXPECTED_EXECUTION_CONTRACT_VERSION}]
  assert.equal((await frontend.projectPresence(signal))[0].status,'online')
  result=[{executorId:executor,status:'online',contractVersion:-1}]
  assert.equal((await frontend.projectPresence(signal))[0].status,'unknown','incompatible Bridge must not be green')
  generation='stale-desktop'
  await assert.rejects(frontend.projectAction({action:'open'},signal),/没有完成/)
}finally {
  globalThis.fetch=originalFetch
  if(previous===undefined)delete process.env.DSH_HOUDINI_WORKBENCH_CONTEXT
  else process.env.DSH_HOUDINI_WORKBENCH_CONTEXT=previous
  await context.fiber.dispose()
  await fs.rm(directory,{recursive:true,force:true})
}
console.log('desktop API: actual scoped service lookup, fixed authenticated loopback route, original recorded HIP, no browser-supplied command/path, contract mismatch and stale generation passed')
