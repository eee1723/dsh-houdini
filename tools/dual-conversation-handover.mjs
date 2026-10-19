// One workbench Bridge, two conversations: selection/read and writer handover
// are distinct. This runs only against the Python runner's disposable scene.
import assert from 'node:assert/strict'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {ExecutorDirectory,ExecutorRouter} from '../lib/executor-routing.js'
import {ExecutorBinding,recordedExecutorIdentity} from '../lib/executor-binding.js'
import {registerHoudiniTools} from '../lib/tools.js'
import {fixtureSession} from './tests/fixture-session.mjs'

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
const registry=process.argv[2]
if(!registry||!path.isAbsolute(registry))throw new Error('Fixture registry path required')
const directory=new ExecutorDirectory(registry,root),rows=await directory.list()
assert.equal(rows.length,1,'dual-conversation fixture uses one workbench Bridge')
const record=rows[0],flush=async()=>true
const agentB={id:'task-b',status:'idle',session:fixtureSession('task-b',{agentPreset:'houdini'})}
const agentA={id:'task-a',status:'idle',session:fixtureSession('task-a',{agentPreset:'houdini'})}
const agents=[agentA,agentB]
const router=new ExecutorRouter(directory,5000,new ExecutorBinding(),session=>recordedExecutorIdentity(session.snapshotEvents()),
  id=>agents.find(agent=>agent.id===id)?.status==='idle',flush)
const tools=new Map()
registerHoudiniTools({on(){},get:()=>undefined,tools:{register:definition=>tools.set(definition.name,definition)},sessions:{flush}},router)
const exec=(agent,code,callId)=>tools.get('houdini_exec').execute({code},{agent,callId})
const inspect=(agent,code,callId)=>tools.get('houdini_inspect').execute({code},{agent,callId})
const select=agent=>router.selectTarget(agent,record.executor_id,record.registration_id,undefined,record.hip_path)

await select(agentB)
assert.equal((await directory.find(record.executor_id)).task_id,null,'selection alone never acquires the writer')
const created=await exec(agentB,"__result__=tab_create('/obj','geo',name='dual_b').path()",'dual-b-create')
assert.equal(created.ok,true,created)
assert.equal(created.execution.owner_session,'task-b')
await assert.rejects(inspect(agentA,'__result__=hou.applicationVersionString()','dual-a-unbound'),/本轮没有选择|请选择|还没有/)

await select(agentA)
assert.equal(recordedExecutorIdentity(agentA.session.snapshotEvents()),record.executor_id)
assert.equal((await directory.find(record.executor_id)).task_id,'task-b','selecting another chat does not transfer a writer')
for(const agent of agents)assert.equal((await inspect(agent,'__result__=hou.applicationVersionString()',agent.id+'-read')).ok,true)
agentB.status='running'
await assert.rejects(exec(agentA,"tab_create('/obj','geo',name='must_not_steal')",'dual-a-busy'),/仍在执行|等待完成/)
assert.equal((await directory.find(record.executor_id)).task_id,'task-b','a running author cannot be displaced while HOM is temporarily idle')
agentB.status='idle'
const edited=await exec(agentA,"__result__=tab_create('/obj','geo',name='dual_a').path()",'dual-a-create')
assert.equal(edited.ok,true,edited)
assert.equal(edited.execution.owner_session,'task-a')
assert.equal((await directory.find(record.executor_id)).task_id,'task-a','the first actual write performs an idle handover')
assert.equal((await inspect(agentB,'__result__=hou.applicationVersionString()','dual-b-read-after')).ok,true,'the previous author can still observe')
assert.equal((await directory.find(record.executor_id)).task_id,'task-a','read-only observation does not steal the writer back')
const foreign=await exec(agentA,"__result__=set_parms('/obj/dual_b',{'tx':2})",'dual-a-foreign')
assert.equal(foreign.ok,false,'the former author nodes remain foreign after a writer handover')
console.log('Dual conversation handover: selection/read without writer, busy-author refusal, write-only idle transfer and original-node ownership fence passed')
