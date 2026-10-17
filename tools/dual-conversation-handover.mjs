// Dual conversations on one workbench Bridge: writer reservation handover.
// Complements multi-executor-host-smoke (two non-workbench Bridges, steal refusal).
// Guarantees: a displaced conversation gets the explicit reservation refusal,
// the new author keeps the reservation, and nodes keep their creating session.
import assert from 'node:assert/strict'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {ExecutorDirectory,ExecutorRouter} from '../lib/executor-routing.js'
import {ExecutorBinding,recordedExecutorIdentity} from '../lib/executor-binding.js'
import {registerHoudiniTools} from '../lib/tools.js'
import {fixtureSession} from './tests/fixture-session.mjs'

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
const registry=process.argv[2]
if(!registry||!path.isAbsolute(registry)) throw new Error('Fixture registry path required')
const directory=new ExecutorDirectory(registry,root)
const rows=await directory.list()
assert.equal(rows.length,1,'dual-conversation fixture uses one workbench Bridge')
const record=rows[0]
const flush=async session=>true
const identityOf=session=>recordedExecutorIdentity(session.snapshotEvents())
const router=new ExecutorRouter(directory,5000,new ExecutorBinding(),identityOf,flush)
const tools=new Map()
registerHoudiniTools({on(){},get:()=>undefined,tools:{register:d=>tools.set(d.name,d)},sessions:{flush}},router)

const agentB={id:'task-b',status:'idle',session:fixtureSession('task-b',{agentPreset:'houdini'})}
const agentA={id:'task-a',status:'idle',session:fixtureSession('task-a',{agentPreset:'houdini'})}

// B is the original author and edits.
await router.selectInitial(agentB,record.executor_id,record.registration_id)
const created=await tools.get('houdini_exec').execute({
  code:"__result__=tab_create('/obj','geo',name='dual_b').path()"},{agent:agentB,callId:'dual-b-create'})
assert.equal(created.ok,true,created)
assert.equal(created.execution.owner_session,'task-b')

// A is unbound: tools cannot silently adopt the live window.
await assert.rejects(tools.get('houdini_inspect').execute(
  {code:'__result__=hou.applicationVersionString()'},{agent:agentA,callId:'dual-a-unbound'}),
  /Choose a Houdini|还没有写入预留|写入预留属于另一段对话/)

// A's explicit user selection is the designed idle handover.
await router.selectInitial(agentA,record.executor_id,record.registration_id)
let after=await directory.find(record.executor_id)
assert.equal(after.task_id,'task-a','explicit idle selection is the designed handover')
assert.equal(recordedExecutorIdentity(agentA.session.snapshotEvents()),record.executor_id)

// The displaced conversation gets the explicit refusal; the reservation is not
// stolen back by a rival operation.
await assert.rejects(tools.get('houdini_inspect').execute(
  {code:'__result__=hou.applicationVersionString()'},{agent:agentB,callId:'dual-b-after'}),
  /写入预留属于另一段对话/)
after=await directory.find(record.executor_id)
assert.equal(after.task_id,'task-a','a displaced conversation must not steal the reservation')

// The new author works; the old author's nodes stay fenced.
const edited=await tools.get('houdini_exec').execute({
  code:"__result__=tab_create('/obj','geo',name='dual_a').path()"},{agent:agentA,callId:'dual-a-create'})
assert.equal(edited.ok,true,edited)
assert.equal(edited.execution.owner_session,'task-a')
const foreign=await tools.get('houdini_exec').execute({
  code:"__result__=set_parms('/obj/dual_b',{'tx':2})"},{agent:agentA,callId:'dual-a-foreign'})
assert.equal(foreign.ok,false,'nodes keep their creating session after an explicit handover')
console.log('Dual conversation handover: displacement refusal, idle explicit transfer, new-author fence passed')
