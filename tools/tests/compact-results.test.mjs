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
for(const fact of ['case-8','case-9','restoration-drift-middle','channel mismatch','not_run','not_checked','unverified','"restored":false','detail_pointer','duplicate_of'])assert(text.includes(fact),fact);
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
assert(render({...retained,result:unknownTop}).includes(JSON.stringify(unknownTop)));
assert(render({...retained,result,details:{stored:false}}).includes(JSON.stringify(result)),
  'without a stored original, top-level data must retain the full fallback');
assert.equal(JSON.stringify(raw),original);
// __result__ is chosen by the executing code. Successful unselected ledger
// payloads are audit details; an independent failed check must remain visible.
const selected=render({ok:true,stdout:'',stderr:'',result:{output:'/obj/a/OUT'},details:{stored:true},
  verbs:[{verb:'set_parms',ok:true,check_status:'passed',result:{source:'unselected-source-'.repeat(1000)}},
    {verb:'cook_node',ok:true,check_status:'failed',result:{errors:['independent-cook-failure']}},
    {verb:'future_operation',ok:false,error:'caught-operation-failure'},
    {verb:'future_observer',ok:true,result:{novel:'unclassified-success-diagnostic'}}]});
assert(selected.includes('/obj/a/OUT') && !selected.includes('unselected-source-'));
assert(selected.includes('independent-cook-failure') && selected.includes('caught-operation-failure'));
assert(selected.includes('unclassified-success-diagnostic'),'unknown results remain visible without a Bridge summary or passed check');
assert(selected.includes('"detail_pointer":"/verbs/0/result"'));
// Arbitrary text cannot be clipped using a guessed diagnostic-field vocabulary.
const longDiagnostic='prefix '.repeat(1000)+'failure-at-the-very-end';
assert(render({ok:true,stdout:'',stderr:'',result:{novel:longDiagnostic},details:{stored:true}}).includes(longDiagnostic));
// DSH spills large tool text. Recovery/identity facts must precede large
// selected payloads and help, including when archive retention failed.
for(const stored of [true,false]){
  const large=render({ok:false,error:'operation-failed',stdout:'ordinary stdout',stderr:'native diagnostic',
    requestReceipt:{request_ref:'original-request',status:'done'},checks:[{verb:'build_module',status:'failed'}],
    transaction:{status:'rolled_back',nodes:[{identity:7,exists:false,prior_path:'/obj/rolled_back_node'}]},
    rollback:{applied:false,error:'recovery-not-confirmed'},rawUsage:{gateOutcome:'blocked'},
    evidence:[{ledgerIndex:1,verb:'build_module',ok:false,reason:'construction-failure',restored:false}],
    execution:{runtime_id:'original-runtime',sequence:9,impact:{unavailable:true}},
    result:{selected:'large-selected-payload '.repeat(6000)},details:{stored},
    verbs:[{verb:'verb_help',ok:true,result:{doc:'large-help '.repeat(6000)}}]});
  const bulky=Math.min(large.indexOf('verb-help:\n'),large.indexOf('__result__:\n'));
  for(const fact of ['original-request','"status":"failed"','rolled_back_node','recovery-not-confirmed',
    'construction-failure','original-runtime','"unavailable":true','"gateOutcome":"blocked"','native diagnostic']){
    const index=large.indexOf(fact);assert(index>=0&&index<bulky,fact+' must precede bulk output');
  }
}
const helpBatch=render({ok:true,stdout:'',stderr:'',details:{stored:true},
  verbs:[{verb:'verb_help',ok:true,result:help},{verb:'verb_help',ok:true,result:help}],
  result:{selected:[help,help]}});
assert.equal(helpBatch.split(help.items[0].signature).length-1,1,'batch help has one complete copy');
// test58 #3: an unstored reply repeated the same complete help in verb-help,
// __result__.help and the verb ledger. Its inline copy must be usable without
// a result_ref archive; arbitrary selected diagnostics and stdout stay exact.
for(const details of [undefined,{stored:false},{stored:false,error:'archive unavailable'}]){
  const inlineRaw={ok:true,stdout:'printed diagnostic\n'+longDiagnostic,stderr:'',details,
    result:{help,diagnostic:{novel:longDiagnostic}},
    verbs:[{verb:'future_observer',ok:true,args:['keep arguments'],result:{novel:longDiagnostic}},
      {verb:'verb_help',ok:true,result:help,args:['sample'],ms:1},
      {verb:'verb_help',ok:true,result:help,args:['sample'],ms:1}]};
  const before=JSON.stringify(inlineRaw);
  const inline=render(inlineRaw);
  const section=label=>JSON.parse(inline.split(label+':\n')[1].split('\n\n')[0]);
  const inlineHelp=section('verb-help');
  assert.deepEqual(inlineHelp[0],help,'the first help copy keeps every precondition and schema inline');
  assert.equal(inline.split(help.items[0].signature).length-1,1,'unstored help is rendered once');
  const resolve=value=>{
    assert.deepEqual(Object.keys(value),['duplicate_of'],'an inline reference cannot require an archive');
    const match=/^verb-help\[(\d+)\]$/.exec(value.duplicate_of);
    assert(match,'help reference names an addressable section in this reply');
    return inlineHelp[Number(match[1])];
  };
  assert.deepEqual(resolve(inlineHelp[1]),help);
  assert.deepEqual(resolve(section('__result__').help),help);
  const ledger=section('verbs (3)');
  assert.deepEqual(resolve(ledger[1].result),help);
  assert.deepEqual(resolve(ledger[2].result),help);
  assert.deepEqual(ledger[0],inlineRaw.verbs[0],'unknown results and arguments keep their complete fallback');
  assert.deepEqual(section('__result__').diagnostic,inlineRaw.result.diagnostic);
  assert(inline.includes('stdout:\n'+inlineRaw.stdout),'arbitrary printed diagnostics are not deduplicated');
  assert(!inline.includes('detail_pointer'),'unstored results never invent archive pointers');
  assert.equal(JSON.stringify(inlineRaw),before,'canonical audit data is unchanged');
}
const inventory=Array.from({length:104},(_,identity)=>({identity,path:'/obj/inventory/node'+identity}));
const observation={runtime_id:'runtime',sequence:10,impact:{nodes:inventory,truncated:true,unavailable:false,scope:'bounded only'}};
const transaction={status:'committed',nodes:inventory.map(item=>({...item,prior_path:item.path,exists:true})),nodes_truncated:true,coverage:'observed only'};
const inventoryText=render({ok:true,stdout:'',stderr:'',execution:observation,transaction,details:{stored:true}});
assert(inventoryText.includes('"count":104') && !inventoryText.includes('/obj/inventory/node103'));
for(const fact of ['bounded only','"truncated":true','"nodes_truncated":true','observed only','/transaction/nodes','/execution/impact/nodes'])assert(inventoryText.includes(fact));
const unusual=structuredClone(transaction);unusual.nodes[103].error='late-identity-failure';
assert(render({ok:true,stdout:'',stderr:'',transaction:unusual,details:{stored:true}}).includes('late-identity-failure'));
const remapped=structuredClone(transaction);remapped.nodes[103].path='/obj/renamed';
assert(render({ok:true,stdout:'',stderr:'',transaction:remapped,details:{stored:true}}).includes('/obj/renamed'));
assert(render({ok:false,stdout:'',stderr:'',transaction:{...transaction,status:'rollback_failed'},details:{stored:true}}).includes('/obj/inventory/node103'));
assert(render({ok:true,stdout:'',stderr:'',execution:observation,transaction,details:{stored:false}}).includes('/obj/inventory/node103'));
const cards=Array.from({length:24},(_,index)=>({name:'parameter'+index,type:'Float',components:['parameter'+index],default:[0],menu:[]}));
const nodeCard={ledgerIndex:1,verb:'node_info',parent:'/obj/a',type:'example::2.0',version:'21.0',
  operation_parameter_scope:'unfiltered static templates',parameter_scope:'returned filtered parameter card only',
  setting_cards:cards,operation_parameters:cards,operation_card:{decisions:['choose axis']},
  novel_diagnostic:'future-scope-warning'};
const chosenCard={ok:true,stdout:'',stderr:'',execution:{read_only:true},result:{selected:cards[0]},
  evidence:[nodeCard],details:{stored:true}};
const cardText=render(chosenCard);
assert(cardText.includes('parameter0') && !cardText.includes('parameter23'));
for(const fact of ['example::2.0','choose axis','future-scope-warning','/evidence/0/setting_cards','unfiltered static templates'])assert(cardText.includes(fact));
assert(render({...chosenCard,result:undefined}).includes('parameter23'),'a caller requesting the full card still receives the full card');
assert(render({...chosenCard,details:{stored:false}}).includes('parameter23'),'card selection requires accessible full details');
const differentSummary=render({ok:true,stdout:'',stderr:'',details:{stored:true},evidence:[{ledgerIndex:1,verb:'future',ok:true}],
  verbs:[{verb:'future',ok:true,summary:{ok:true,novel:'unmatched-summary-fact'},result:{scope:'full result'}}]});
assert(differentSummary.includes('unmatched-summary-fact'),'only the exact Bridge summary can be replaced by its evidence pointer');
console.log(`risk-preserving compact results ${text.length}/${render(raw).length} chars; late failure, not-run, unknown schema, help and archive fallback passed`);

console.log(`top-level result projection: direct=${direct.length}, wrapped=${wrapped.length}, differing=${differing.length} chars`);
