// Historical v8 test, excluded from the current Node suite.
import assert from 'node:assert/strict'
import {DeliveryController} from '../../lib/delivery.js'
import {registerHoudiniTools} from '../../lib/tools.js'

const owner={sessionId:'a',callId:'1'}
const binding={runtime:'r1',scene:1,hip:'C:/task/a.hip'}
let revision='1', failure=null, resultBinding=binding, callback=null, calls=[]
const transport={mutationEpoch:0,pendingMutations:0,async delivery(request,who,expected){
  calls.push({request,who,expected})
  if(callback)await callback()
  if(failure)throw new Error(failure)
  if(expected && JSON.stringify(expected)!==JSON.stringify(resultBinding))return {ok:false,reset_required:true,error:'binding changed'}
  return {ok:true,binding:resultBinding,inspection:{controls:['length']},
    receipt:{revision,checks:[{id:'part',kind:'part',status:'pass'},{id:'length',kind:'control',status:'unverified'}]},
    test:request.action==='test_control'?{id:request.case_id,kind:'control',status:'pass'}:null}
}}
const controller=new DeliveryController(transport)
const register={action:'register',contract:{frozen:'original'}}
await assert.rejects(controller.execute({action:'check'},owner),/register/)
await assert.rejects(controller.execute(register,undefined),/trusted/)
await assert.rejects(controller.execute({action:'check',passed:true},owner),/do not submit/)
let r=await controller.execute(register,owner)
assert.equal(r.status,'unverified')
register.contract.frozen='changed externally'
r=await controller.execute({action:'test_control',case_id:'length'},owner)
assert.equal(calls.at(-1).request.contract.frozen,'original')
assert.equal(r.status,'pass')
assert.notEqual(r.delivery_status,'complete')
assert.equal(r.semantic_status,'unverified')
r.checks[1].status='fail' // result copy cannot poison cache
assert.equal((await controller.execute({action:'check'},owner)).status,'pass')
await assert.rejects(controller.execute({action:'check'},{sessionId:'other',callId:'2'}),/register/)
transport.mutationEpoch++
assert.equal(controller.summary('a').stale,true)
const invalidatedByMutation=await controller.execute({action:'check'},owner)
assert.equal(invalidatedByMutation.status,'unverified')
assert.deepEqual(invalidatedByMutation.invalidated_control_cases,['length'])
await controller.execute({action:'test_control',case_id:'length'},owner)
revision='2' // User/other Host changed parameters, same DSH mutation generation.
assert.equal((await controller.execute({action:'check'},owner)).status,'unverified')
await controller.execute({action:'test_control',case_id:'length'},owner)
transport.pendingMutations=1
await assert.rejects(controller.execute({action:'check'},owner),/pending/)
transport.pendingMutations=0
callback=async()=>{transport.mutationEpoch++}
await assert.rejects(controller.execute({action:'check'},owner),/overlapped/)
callback=null
assert.equal((await controller.execute({action:'check'},owner)).status,'unverified')
await controller.execute({action:'test_control',case_id:'length'},owner)
failure='timeout: execution unknown'
await assert.rejects(controller.execute({action:'check'},owner),/timeout/)
failure=null
assert.equal((await controller.execute({action:'check'},owner)).status,'unverified')
resultBinding={...binding,runtime:'restarted'}
await assert.rejects(controller.execute({action:'check'},owner),/binding changed/)
await assert.rejects(controller.execute({action:'check'},owner),/register/)
await controller.execute(register,owner)
resultBinding={...resultBinding,scene:2} // reload same HIP path
await assert.rejects(controller.execute({action:'check'},owner),/binding changed/)
await controller.execute(register,owner)
let release
callback=()=>new Promise(resolve=>{release=resolve})
const pending=controller.execute({action:'check'},owner)
await assert.rejects(controller.execute({action:'check'},owner),/already pending/)
release();await pending;callback=null
assert.equal(controller.summary('unknown'),undefined)
// A presentation request that starts and ends during a delivery call is still
// a race, even when it did not increment the numerical invalidation generation.
transport.activityEpoch=0
callback=async()=>{transport.activityEpoch++}
await assert.rejects(controller.execute({action:'check'},owner),/overlapped/)
callback=null
// Contract obligations cannot silently vanish or change validation method.
await controller.execute({action:'register',contract:{interfaces:[{id:'joint',source_group:'a',target_group:'b'}]}},owner)
const changed=await controller.execute({action:'register',contract:{topology:[{id:'joint',groups:['a','b']}]}},owner)
assert.deepEqual(changed.contract_changes.changed,['joint'])
const removed=await controller.execute({action:'register',contract:{topology:[]}},owner)
assert.deepEqual(removed.contract_changes.removed,['joint'])
const freshHost=new DeliveryController(transport)
await assert.rejects(freshHost.execute({action:'check'},owner),/register/)

// Existing five-tool surface: delivery is mutually exclusive with arbitrary code.
const definitions=new Map()
registerHoudiniTools({tools:{register(d){definitions.set(d.name,d)}}},transport)
const exec=definitions.get('houdini_exec')
assert.equal(definitions.size,5)
const context={agent:{id:'ui-session'},callId:'call'}
await assert.rejects(exec.execute({code:'pass',delivery:{action:'check'}},context),/cannot be mixed/)
await assert.rejects(exec.execute({allow_raw:'reason',delivery:{action:'check'}},context),/cannot be mixed/)
await assert.rejects(exec.execute({},context),/code or delivery/)
await assert.rejects(exec.execute({delivery:{action:'check',owner_session:'forged'}},context),/do not submit/)
const discovery=await exec.execute({delivery:{action:'inspect',scope:{parent:'/obj/a',output:'/obj/a/OUT',controller:'/obj/a/C'}}},context)
assert.equal(discovery.ok,true)
assert.equal(calls.at(-1).who.sessionId,'ui-session')
assert.equal(definitions.get('houdini_query').parameters.delivery,undefined)
console.log('Host delivery isolation/immutable contract/invalidation/race/timeout/restart/tool-branch passed')
