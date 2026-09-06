// Developer replay of the saved rerun, not shipped in agent guidance or tool catalog.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import {HoudiniBridge} from '../../lib/bridge.js'
import {registerHoudiniTools} from '../../lib/tools.js'
const bridge=new HoudiniBridge(process.argv[2],15000),defs=new Map()
registerHoudiniTools({tools:{register(d){defs.set(d.name,d)}}},bridge)
let n=0
const context=()=>({agent:{id:'frozen-replay'},callId:`call-${++n}`})
const run=code=>defs.get('houdini_exec').execute({code},context())
const request=delivery=>defs.get('houdini_exec').execute({delivery},context())
const p='/obj/l_bracket'
const inspection=await request({action:'inspect',scope:{parent:p,output:`${p}/OUT`,controller:`${p}/CTRL`}})
const contract={parent:p,output:`${p}/OUT`,controller:`${p}/CTRL`,
 parts:[{id:'base',group:'base',min_prims:4},{id:'upright',group:'upright',min_prims:4}],interfaces:[],
 topology:[{id:'connection',groups:['base','upright'],require_closed:true}],
 domain:[{id:'positive_t',left:'thickness',op:'gt',right:0},{id:'t_h',left:'thickness',op:'lt',right:'height'},
         {id:'t_d',left:'thickness',op:'lt',right:'depth'}],
 controls:[{id:'w',parm:'width',value:9,expectations:[{metric:'bounds_size',axis:0,delta:[2.9,3.1]}]},
           {id:'h',parm:'height',value:12,expectations:[{metric:'bounds_size',axis:1,delta:[3.9,4.1]}]},
           {id:'t',parm:'thickness',value:2.5,expectations:[{metric:'bounds_size',group:'base',axis:1,delta:[1.4,1.6]}]},
           {id:'d',parm:'depth',value:6,expectations:[{metric:'bounds_size',axis:2,delta:[1.9,2.1]}]}]}
await request({action:'register',contract})
for(const case_id of ['w','h','t','d'])await request({action:'test_control',case_id})
const first=(await request({action:'check'})).result
assert.equal(first.status,'pass')
const reused=[]
for(const code of [`print(verb_help('render_view'))`,`layout_nodes('${p}')\nsop_set_output('${p}/OUT')`,`scene_save()`]){
  assert.equal((await run(code)).ok,true)
  const r=(await request({action:'check'})).result
  assert.equal(r.status,'pass')
  assert.equal(r.reused_control_cases.length,4)
  assert.equal(r.checks.find(c=>c.id==='connection').status,'pass')
  reused.push(r)
}
// Actual input change remains invalidating even if the geometry is still valid.
await run(`set_parms('${p}/CTRL',{'width':7})`)
const edited=(await request({action:'check'})).result
assert.equal(edited.status,'unverified');assert.equal(edited.invalidated_control_cases.length,4)
await run(`set_parms('${p}/CTRL',{'width':6})`)
assert.equal((await request({action:'check'})).result.status,'unverified')
for(const case_id of ['w','h','t','d'])await request({action:'test_control',case_id})
const final=(await request({action:'check'})).result
assert.equal(final.status,'pass');assert.equal(final.semantic_status,'unverified')
fs.writeFileSync(process.argv[3],JSON.stringify({source_sha256:process.argv[4],scope:'disposable clone; no source saves',
  inspection:inspection.result,contract,first,reused,edited,final,
  controls_rerun_for_three_successful_housekeeping_calls:0},null,2),{flag:'wx'})
console.log('frozen asset: connection retained, 4 proofs reused after each housekeeping call, real edits invalidated')
