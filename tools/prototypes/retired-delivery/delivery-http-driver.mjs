// Historical v8 driver, excluded from the current test suite.
import assert from 'node:assert/strict'
import {HoudiniBridge} from '../../lib/bridge.js'
import {registerHoudiniTools} from '../../lib/tools.js'
const bridge=new HoudiniBridge(process.argv[2],15000)
const definitions=new Map()
registerHoudiniTools({tools:{register(d){definitions.set(d.name,d)}}},bridge)
let id=0
const context=()=>({agent:{id:'delivery-http-test'},callId:String(++id)})
const run=code=>definitions.get('houdini_exec').execute({code},context())
const request=delivery=>definitions.get('houdini_exec').execute({delivery},context())
const created=await run(`p=tab_create('/obj','geo',name='__delivery_http')
c=tab_create(p,'null',name='CTRL')
create_spare_parms(c,spec=[{'name':'length','type':'float','default':1},{'name':'height','type':'float','default':1}])
spec=[
 {'name':'a','type':'box','parms':{'sizex':"ch('../CTRL/length')",'tx':"ch('../CTRL/length')/2"}},
 {'name':'port','type':'groupcreate','inputs':['a'],'parms':{'groupname':'a_port','grouptype':'point','basegroup':'@P.x>0.99'}},
 {'name':'tag_a','type':'groupcreate','inputs':['port'],'parms':{'groupname':'a_part'}},
 {'name':'b','type':'box','parms':{'tx':"ch('../CTRL/length')+0.5"}},
 {'name':'tag_b','type':'groupcreate','inputs':['b'],'parms':{'groupname':'b_part'}},
 {'name':'merge','type':'merge','inputs':['tag_a','tag_b']},
 {'name':'OUT','type':'null','inputs':['merge']}]
build_module(p,spec,output='OUT')
__result__=p.path()`)
assert.equal(created.ok,true,created.error)
const parent=created.result
const scope={parent,output:`${parent}/OUT`,controller:`${parent}/CTRL`}
const contract={...scope,parts:[{id:'a',group:'a_part',min_prims:6},{id:'b',group:'b_part',min_prims:6}],
 controls:[{id:'length',parm:'length',value:1.2,expectations:[{group:'b_part',metric:'bounds_center',axis:0,delta:[.199,.201]}]},
           {id:'height',parm:'height',value:2,expectations:[{group:'b_part',metric:'bounds_size',axis:1,delta:[.999,1.001]}]}],
 interfaces:[{id:'joint',source_group:'a_port',target_group:'b_part',expected_points:4,max_distance:.001}]}
const inspect=await request({action:'inspect',scope})
assert.equal(inspect.result.inspection.controls.length,2)
assert.equal((await request({action:'register',contract})).result.status,'unverified')
const row=(r,id)=>r.result.checks.find(r=>r.id===id)
assert.equal(row(await request({action:'test_control',case_id:'length'}),'length').status,'pass')
assert.equal(row(await request({action:'test_control',case_id:'height'}),'height').status,'fail')
const repair=await run(`set_parm('${parent}/b','sizey',"ch('../CTRL/height')")`)
assert.match(repair.advisory,/invalidated/)
assert.equal(row(await request({action:'check'}),'length').status,'unverified')
await request({action:'test_control',case_id:'length'})
await request({action:'test_control',case_id:'height'})
const passed=await request({action:'check'})
assert.equal(passed.result.status,'pass')
assert.equal(passed.result.semantic_status,'unverified')
await run(`disconnect_input('${parent}/merge',index=1)`)
assert.equal(row(await request({action:'check'}),'b').status,'fail')
await run(`connect('${parent}/tag_b','${parent}/merge',index=1)`)
assert.equal(row(await request({action:'check'}),'length').status,'unverified')
// A different session cannot reuse state or acquire authority through register.
await assert.rejects(definitions.get('houdini_exec').execute({delivery:{action:'check'}},
 {agent:{id:'other'},callId:'1'}),/register/)
await definitions.get('houdini_exec').execute({delivery:{action:'register',contract}}, {agent:{id:'other'},callId:'2'})
await assert.rejects(definitions.get('houdini_exec').execute({delivery:{action:'test_control',case_id:'length'}},
 {agent:{id:'other'},callId:'3'}),/ownership/)
// Scheduled scene work must be observed settled, not turned into cached pass.
const job=await bridge.submitJob("__result__=1",undefined,undefined,{sessionId:'delivery-http-test',callId:'job'})
await bridge.jobStatus(job.jobId,5)
assert.equal(row(await request({action:'check'}),'length').status,'unverified')
await run(`delete_node('${parent}')`)
// Boolean fusion plus a coupled size domain, the natural path missed by v6.
const fused=await run(`p=tab_create('/obj','geo',name='__delivery_union')
c=tab_create(p,'null',name='C')
create_spare_parms(c,spec=[{'name':'w','type':'float','default':4},{'name':'h','type':'float','default':6},{'name':'t','type':'float','default':1}])
build_module(p,[
 {'name':'a','type':'box','parms':{'sizex':"ch('../C/w')",'sizez':"ch('../C/w')",'sizey':"ch('../C/t')",'ty':"ch('../C/t')/2"}},
 {'name':'b','type':'box','parms':{'sizex':"ch('../C/t')",'sizez':"ch('../C/w')",'sizey':"ch('../C/h')",'tx':"(ch('../C/w')-ch('../C/t'))/2",'ty':"ch('../C/h')/2"}},
 {'name':'ga','type':'groupcreate','inputs':['a'],'parms':{'groupname':'base'}},
 {'name':'gb','type':'groupcreate','inputs':['b'],'parms':{'groupname':'upright'}},
 {'name':'union','type':'boolean','inputs':['ga','gb'],'parms':{'booleanop':'union'}},
 {'name':'OUT','type':'null','inputs':['union']}],output='OUT')
__result__=p.path()`)
assert.equal(fused.ok,true,fused.error)
const p2=fused.result
const c2={parent:p2,output:`${p2}/OUT`,controller:`${p2}/C`,
 parts:[{id:'base',group:'base',min_prims:1},{id:'upright',group:'upright',min_prims:1}],interfaces:[],
 topology:[{id:'fused_join',groups:['base','upright'],require_closed:true}],
 controls:[{id:'w-test',parm:'w',value:6,expectations:[{metric:'bounds_size',axis:0,delta:[1.99,2.01]}]},
           {id:'h-test',parm:'h',value:8,expectations:[{metric:'bounds_size',axis:1,delta:[1.99,2.01]}]},
           {id:'t-test',parm:'t',value:1.5,expectations:[{metric:'bounds_size',axis:1,group:'base',delta:[.49,.51]}]}],
 domain:[{id:'positive',left:'t',op:'gt',right:0},{id:'thin_w',left:'t',op:'lt',right:'w'},{id:'thin_h',left:'t',op:'lt',right:'h'}]}
const inspected=await request({action:'inspect',scope:{parent:p2,output:`${p2}/OUT`,controller:`${p2}/C`}})
assert.ok(inspected.result.inspection.control_metrics.includes('bounds_center'))
assert.equal(inspected.result.inspection.verification_suggestions[0].method,'topology')
await request({action:'register',contract:c2})
for(const case_id of ['w-test','h-test','t-test'])await request({action:'test_control',case_id})
assert.equal((await request({action:'check'})).result.status,'pass')
// Successful presentation/housekeeping doesn't need to rerun registered tests.
for(const code of [`print(verb_help('render_view'))`,`layout_nodes('${p2}')\nsop_set_output('${p2}/OUT')`,`scene_save()`]){
  const result=await run(code);assert.equal(result.ok,true,result.error)
  const receipt=await request({action:'check'})
  assert.equal(receipt.result.status,'pass')
  assert.deepEqual(new Set(receipt.result.reused_control_cases),new Set(['w-test','h-test','t-test']))
  assert.equal(row(receipt,'fused_join').status,'pass')
}
// Unknown programs, even harmless ones, still discard current control proofs.
await run("import math\n__result__=math.sqrt(1)")
assert.equal((await request({action:'check'})).result.status,'unverified')
for(const case_id of ['w-test','h-test','t-test'])await request({action:'test_control',case_id})
// Another client changes the scene: this Host has no local mutation notification.
const external=new HoudiniBridge(process.argv[2],15000)
const externalEdit=await external.exec(`set_parms('${p2}/C',{'w':7.6,'t':7})`,undefined,undefined,{sessionId:'delivery-http-test',callId:'external'})
assert.equal(externalEdit.ok,true,externalEdit.error)
const outside=await request({action:'check'})
assert.equal(row(outside,'thin_h').status,'fail')
assert.equal(row(outside,'upright').status,'fail')
assert.equal(row(outside,'w-test').status,'unverified')
await external.exec(`set_parm('${p2}/C','t',1)`,undefined,undefined,{sessionId:'delivery-http-test',callId:'restore'})
assert.equal((await request({action:'check'})).result.status,'unverified')
const bad=structuredClone(c2);bad.controls[2].value=7
await request({action:'register',contract:bad})
const prevented=await request({action:'test_control',case_id:'t-test'})
assert.equal(row(prevented,'t-test').evidence.results[0].parameter_writes,0)
assert.equal(row(prevented,'t-test').status,'fail')
await run(`delete_node('${p2}')`)
console.log('real Node tool -> HTTP -> owning-thread delivery -> Host merge passed')
