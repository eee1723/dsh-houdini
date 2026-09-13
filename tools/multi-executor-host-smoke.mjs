// Test-only shared Host against the two disposable Bridges created by the Python runner.
// Not a live connect/repair CLI. Uses fixture sessions and a fixture durability sink.
import fs from 'node:fs/promises'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import assert from 'node:assert/strict'
import {Session} from '@deepseek-ai/dsh-session'
import {ExecutorDirectory,ExecutorRouter} from '../lib/executor-routing.js'
import {ExecutorBindingBarrier} from '../lib/execution-state.js'
import {registerHoudiniTools} from '../lib/tools.js'

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
const registry=process.argv[2]
if(!registry||!path.isAbsolute(registry)) throw new Error('Fixture registry path required')
const directory=new ExecutorDirectory(registry,root)
const rows=await directory.list()
assert.equal(rows.length,2)
assert.deepEqual(rows.map(r=>r.task_id).sort(),['task-0','task-1'],'Only the isolated fixture is accepted')
const agents=rows.map(r=>({id:r.task_id,status:'idle',session:Session.create(r.task_id,[],{
  version:3,id:r.task_id,createdAt:1,isSeeded:false,agentPreset:'houdini'})}))
const flush=async session=>{
  await fs.writeFile(path.join(registry,session.id+'-session.json'),JSON.stringify(session.snapshotEvents()))
  return true
}
const router=new ExecutorRouter(directory,5000,new ExecutorBindingBarrier(flush))
for(let i=0;i<rows.length;i++) await router.selectInitial(agents[i],rows[i].executor_id,rows[i].registration_id)
const tools=new Map()
registerHoudiniTools({tools:{register:d=>tools.set(d.name,d)},sessions:{flush}},router)
const results=await Promise.all(agents.map((agent,i)=>tools.get('houdini_query').execute({
  code:'__result__=hou.applicationVersionString()'}, {agent,callId:'host-smoke-'+i})))
for(let i=0;i<results.length;i++) {
  assert.equal(results[i].result,rows[i].houdini_version)
  assert.equal(results[i].execution.executor_id,rows[i].executor_id)
  assert.equal(results[i].execution.owner_session,agents[i].id)
}
console.log('Shared Host tools -> two real Houdini main-thread Bridges passed')
