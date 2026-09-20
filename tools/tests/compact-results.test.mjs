import assert from 'node:assert/strict';
import {registerHoudiniTools} from '../../lib/tools.js';
const definitions=new Map();registerHoudiniTools({tools:{register:d=>(definitions.set(d.name,d),()=>{})}},{});
const render=value=>definitions.get('houdini_exec').output.render({},value).map(c=>c.text||'').join('\n');
const conditions=Array.from({length:24},(_,i)=>({id:'domain-'+i,status:'pass',condition:{id:'domain-'+i,left:'gain',op:'ge',right:0},left_value:2,right_value:0,scope:'declared only'}));
const state={ok:true,scope:'exact channels only',channels:Array.from({length:8},(_,i)=>({parameter:'/obj/a/p'+i,state_matches:true,expected_value:2,actual_value:2})),errors:[]};
const rows=Array.from({length:16},(_,i)=>({id:'case-'+i,status:'pass',values:{gain:i+3},restored:true,restore_errors:[],domain:conditions,parameter_restore:state,measurements:[{pass:true,baseline:2,measured:i+3,delta:i+1,expectation:{metric:'bounds_size',axis:0,delta:[i+1,i+1]}}]}));
// A risk in the MIDDLE must remain explicit, even with many later passes.
rows[8]={...rows[8],status:'fail',restored:false,restore_errors:['restoration-drift-middle'],parameter_restore:{...state,ok:false,channels:[{parameter:'/obj/a/locked',state_matches:false}],errors:['channel mismatch']}};
rows[9]={...rows[9],status:'not_run',reason:'dependent on failed recovery'};
const result={ok:false,status:'fail',restored:false,semantic_status:'unverified',scope:'declared checks only',results:rows,control_summary:{status:'fail',case_counts:{pass:14,fail:1,not_run:1},coverage:{relationship_scope:'not_checked'},failures:[{id:'case-8',reason:'restoration-drift-middle'}]}};
const raw={ok:true,stdout:'',stderr:'',transaction:{status:'committed'},evidence:[{ledgerIndex:1,verb:'test_controls',...result}],verbs:[{verb:'test_controls',ok:true,args:[],result,ms:1}]};
const retained={...raw,details:{stored:true,sha256:'a'.repeat(64),read:'houdini_query result_ref'}};
const original=JSON.stringify(raw);const text=render(retained);
for(const fact of ['case-8','case-9','restoration-drift-middle','channel mismatch','not_run','not_checked','unverified','"restored":false','detail_pointer','evidence_pointer'])assert(text.includes(fact),fact);
assert(text.length<render(raw).length*.6,[text.length,render(raw).length]);
assert(text.length<26000,'known bounded 16-case fixture should not spill into a 50k presentation');
assert.equal(JSON.stringify(raw),original,'formatting is pure');
const unknown={verb:'future_checker',domain:conditions,parameter_restore:state,novel_field:'must stay exact'};
const unknownText=render({...retained,evidence:[unknown],verbs:[]});assert(unknownText.includes(JSON.stringify(unknown)),'unknown schema retains all fields');
const help={items:[{name:'sample',signature:'sample(node, *, expected_plan=None)',call_mode:'exec',docstring:'Preview is zero-write. Application requires the exact expected plan. '+ 'bounded details '.repeat(400)}]};
const helpText=render({ok:true,stdout:'',stderr:'',details:{stored:true},verbs:[{verb:'verb_help',ok:true,result:help,args:['sample'],ms:1}],result:help});
assert(helpText.includes(help.items[0].signature));assert(helpText.includes(help.items[0].docstring));assert.equal(helpText.split(help.items[0].signature).length-1,1,'help rendered once with complete preconditions');
const fallback=render({...retained,details:{stored:false,error:'archive unavailable'}});assert(fallback.includes(JSON.stringify(raw.verbs[0].args)));assert(fallback.includes('restoration-drift-middle'));
const direct=render({...retained,result});
assert(direct.length<26000,'direct __result__ must not re-expand the same known control result');
assert(direct.includes('duplicate') && direct.includes('restoration-drift-middle'));
const wrapped=render({...retained,result:{controls:result,diagnostic:{warnings:['unique-wrapper-warning']}}});
assert(wrapped.length<27000 && wrapped.includes('unique-wrapper-warning'));
const differs=structuredClone(result);differs.results[8].restore_errors=['unique-top-level-failure'];
const differing=render({...retained,result:differs});
assert(differing.includes('unique-top-level-failure') && differing.includes('restoration-drift-middle'),
  'distinct top-level evidence must survive alongside the original failure');
assert(differing.length<30000,'unchanged subtrees may be shared without hiding differing fields');
const unknownTop={status:'unverified',unknown_payload:{novel:'unique future data'}};
assert(render({...retained,result:unknownTop}).includes(JSON.stringify(unknownTop,null,2)));
assert(render({...retained,result,details:{stored:false}}).includes(JSON.stringify(result,null,2)),
  'without a stored original, top-level data must retain the full fallback');
assert.equal(JSON.stringify(raw),original);
console.log(`risk-preserving compact results ${text.length}/${render(raw).length} chars; late failure, not-run, unknown schema, help and archive fallback passed`);

console.log(`top-level result projection: direct=${direct.length}, wrapped=${wrapped.length}, differing=${differing.length} chars`);
