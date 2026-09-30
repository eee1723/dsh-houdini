import assert from 'node:assert/strict';
import {defineProduct,productState,productCoverage,productNotice,validateProductDefinition} from '../../lib/product-definition.js';
import {taskSources} from '../../lib/task-sources.js';
import {registerHoudiniTools} from '../../lib/tools.js';
import {installSceneContext} from '../../lib/context.js';

const events=[{type:'user/message',seq:1,data:{id:'request',source:{kind:'user'},content:[{type:'text',text:'Make an opening lid with a pin and a detailed rim.'}]}}];
const source=taskSources(events)[0].source_ref;
const hash='a'.repeat(64),output='/obj/product/OUT_ASSET';
const definition={title:'Lid',output,units:'meters',source_refs:[source],assumptions:[],retired:[],requirements:[
  {id:'pin',kind:'part',description:'One real pin',subjects:['pin'],state:'default',checks:[]},
  {id:'joint',kind:'relation',description:'Lid stays attached',subjects:['lid','base'],state:'default',checks:[{verb:'geo_check_interfaces',contract_sha256:hash,check_id:'join'}]},
  {id:'rim',kind:'detail',description:'Detailed rim',subjects:['lid'],state:'default',checks:[]},
]};
function recordDefinition(row,id='definition') {
  events.push({type:'tool/call',seq:events.length+1,data:{callId:id,name:'houdini_product'}});
  events.push({type:'tool/result',seq:events.length+1,data:{message:{source:{callId:id}},meta:{canonical:{product_definition:row}}}});
}
let sequence=0;
function measure({status='pass',path=output,method,contract=hash,impact,verb='geo_check_interfaces',rows}={}) {
  const id='measure-'+(++sequence);
  const evidence={verb,ledgerIndex:1,contract_sha256:contract,output:path,status,ok:status==='pass',restored:true,
    results:rows??[{id:'join',status,source_group:'lid_port',target_group:'base',...(method?{method}:{})}]};
  events.push({type:'tool/call',seq:events.length+1,data:{name:'houdini_exec',callId:id}});
  events.push({type:'tool/result',seq:events.length+1,data:{message:{source:{callId:id}},meta:{canonical:{ok:true,evidence:[evidence],verbs:[],transaction:{status:'committed'},
    execution:{runtime_id:'R',sequence,observed_at:sequence,hip_path:'C:/work/model.hip',impact:impact??{attempted:false,nodes:[]},outputs:[{ledger_index:1,identity:7,path}]}}}}});
}
assert.equal(productCoverage(events).status,'not_defined');
assert.equal(productNotice(events),null,'simple edits do not gain inferred obligations');
const discovered=[...events,{type:'tool/call',data:{name:'houdini_product',arguments:{action:'schema'}}}];
assert.equal(productNotice(discovered),null,'schema discovery creates no requirement obligations');
assert.equal(productNotice([...events,{type:'tool/call',data:{name:'houdini_product',arguments:JSON.stringify({action:'define'})}}]),null,'a failed definition is not recorded intent');
assert.equal(productNotice([...events,{type:'tool/call',data:{name:'houdini_product',args:{action:'read'}}}]),null);
assert.equal(productNotice([...events,{type:'tool/call',data:{name:'skill',arguments:{name:'houdini-sop-workflow'}}}]),null);
assert.equal(productNotice([...events,{type:'tool/call',data:{name:'skill',arguments:{name:'houdini-parameter-ui'}}}]),null,
  'unrelated workflow discovery does not imply product modeling');
const missingFields={...definition,retired:undefined,requirements:[{id:'incomplete',kind:'part',description:'A part'}]};
assert.throws(()=>validateProductDefinition(missingFields),error=>['definition.retired','requirements[0].subjects','requirements[0].state','requirements[0].checks'].every(s=>error.message.includes(s)),
  'all missing field paths must be returned together, not one full-definition retry per field');
const first=defineProduct(events,definition,0,'Initial source interpretation');
const badBindings=structuredClone(definition);
badBindings.requirements[0].checks=[{verb:'test_controls',contract_sha256:hash,check_id:'members'}];
badBindings.requirements[1].kind='control';
badBindings.requirements[1].checks=[{verb:'test_controls',contract_sha256:hash,check_id:'travel',case_id:'travel'}];
assert.throws(()=>validateProductDefinition(badBindings),e=>e.message.includes('pin:')&&e.message.includes('joint:')&&e.message.includes('evidence_index'),
  'Return all requirement-specific binding fixes together without recording a partial revision');
recordDefinition(first);
assert.equal(productCoverage(events).unresolved,3,'missing obligations cannot be silently passed');
assert.throws(()=>defineProduct(events,definition,0,'stale'),/revision/);
assert.throws(()=>validateProductDefinition({...definition,pass:true}),/supports only/);
assert.throws(()=>defineProduct(events,{...definition,source_refs:['b'.repeat(64)]},1,'wrong source'),/current-session/);
assert.throws(()=>defineProduct(events,{...definition,requirements:definition.requirements.slice(1)},1,'remove pin'),/retirement/);
measure({path:'/obj/product/OUT_LOCAL'});
assert.equal(productCoverage(events).requirements[1].status,'unverified','local pass cannot cover final output');
measure({status:'fail'});
assert.equal(productCoverage(events).requirements[1].status,'fail');
measure();
assert.equal(productCoverage(events).requirements[1].status,'measured');
assert.equal(productCoverage(events).unresolved,2,'a measured join cannot hide a missing pin or rim');
// A known passing row remains measured even if another row in the batch fails.
measure({status:'fail',rows:[{id:'join',status:'pass',source_group:'lid_port',target_group:'base'},
  {id:'other',status:'fail',source_group:'other',target_group:'base'}]});
assert.equal(productCoverage(events).requirements[1].status,'measured');
assert.equal(productCoverage(events).requirements[1].evidence[0].contract_status,'fail');
// Exact ledger entry, not the first same-contract result in a single call.
measure();
const envelope=events.at(-1).data.meta.canonical;
const original=envelope.evidence[0];
envelope.evidence=[{...original,status:'fail',ok:false,results:[{...original.results[0],status:'fail'}]},
  {...original,ledgerIndex:3}];
envelope.execution.outputs.push({...envelope.execution.outputs[0],ledger_index:3});
envelope.execution.impact={attempted:true,nodes:[{identity:7}],last_edit_ledger_index:2};
assert.equal(productCoverage(events).requirements[1].status,'measured');
assert.equal(productCoverage(events).requirements[1].evidence[0].ledger_index,3);
// Started/aborted execution with no Bridge observation invalidates old checks.
events.push({type:'tool/call',seq:events.length+1,data:{name:'houdini_exec',callId:'aborted'}});
events.push({type:'tool/result',seq:events.length+1,data:{message:{source:{callId:'aborted'}},isError:true,error:{code:'ABORTED'}}});
assert.equal(productCoverage(events).requirements[1].status,'stale');
events.push({type:'tool/call',seq:events.length+1,data:{name:'houdini_query',callId:'recover-aborted'}});
events.push({type:'tool/result',seq:events.length+1,data:{message:{source:{callId:'recover-aborted'}},meta:{canonical:{
  requestReceipt:{request_ref:'recovered',owner_call:'aborted',status:'not_executed'}}}}});
assert.equal(productCoverage(events).requirements[1].status,'measured','authoritative no-execution receipt resolves uncertainty');
measure({method:'physical_extent',rows:[{id:'join',status:'pass',method:'physical_extent',target_group:'base'}]});
assert.equal(productCoverage(events).requirements[1].status,'unverified','dimension must not count as an assembly relation');
measure();
for(let i=0;i<20;i++) measure({contract:('0000000000000000000000000000000000000000000000000000000000000000'+i.toString(16)).slice(-64)});
assert.equal(productCoverage(events).requirements[1].status,'measured','full coverage must not inherit UI last-16 truncation');
measure({contract:'c'.repeat(64),impact:{attempted:true,nodes:[{identity:7}]}});
assert.equal(productCoverage(events).requirements[1].status,'stale');
measure();
events.push({type:'compaction/prune',seq:events.length+1,data:{}});
assert.equal(productState(events).current.revision,1,'compaction markers do not erase definition');
const next={...definition,requirements:definition.requirements.slice(1),retired:[{id:'pin',reason:'User approved an alternative connection',source_ref:source}]};
recordDefinition(defineProduct(events,next,1,'Revise declared scope; source interpretation still needs review'),'rev2');
assert.equal(productCoverage(events).retired[0].id,'pin');
assert.throws(()=>defineProduct(events,{...next,retired:[]},2,'forget history'),/retain retirement/);
events.push({type:'user/message',seq:events.length+1,data:{id:'correction',source:{kind:'user'},content:[{type:'text',text:'Also add two feet'}]}});
assert.equal(productCoverage(events).unreconciled_sources.length,1,'later source must remain visible until reconciled');
assert.equal(productNotice(events).pending.length,1);
const copied=structuredClone(events);
recordDefinition(first,'concurrent-stale');
assert.equal(productCoverage(events).status,'revision_conflict','concurrent/stale receipts cannot silently replace intent');
assert.throws(()=>defineProduct(events,next,2,'ignore conflict'),/conflicting/);
const resolved=defineProduct(events,next,2,'Merged conflicting definition; retained the pin retirement',['concurrent-stale']);
recordDefinition(resolved,'resolve-conflict');
assert.equal(productState(events).conflicts.length,0,'explicit merged revision resolves plan conflicts without editing history');
assert.equal(productState(events).current.revision,3);
events.splice(0,events.length,...copied);
// Supporting references and source-review range are separate in long chats.
for(let i=0;i<80;i++) events.push({type:'user/message',seq:events.length+1,data:{id:'continue-'+i,
  source:{kind:'user'},content:[{type:'text',text:'Continue '+i}]}});
const reviewed={...next,reviewed_through:taskSources(events).at(-1).source_ref};
recordDefinition(defineProduct(events,reviewed,2,'Reviewed all continuation messages without changing obligations'),'review-sources');
assert.equal(productCoverage(events).unreconciled_sources.length,0);
assert.equal(productState(events).current.definition.source_refs.length,1);

// Tool path is Host-only, session-scoped and preserved in canonical receipts.
let http=0;const defs=new Map();
registerHoudiniTools({tools:{register:d=>defs.set(d.name,d)}},{exec(){http++;throw Error('no HOM')}});
const product=defs.get('houdini_product'),exec={agent:{session:{snapshotEvents:()=>events}}};
const schema=await product.execute({action:'schema'},exec);
assert.match(schema.result.measurement_mapping.part,/component_count/);
assert.match(schema.result.measurement_mapping.control,/omit case_id/);
const read=await product.execute({action:'read'},exec);
assert.equal(read.result.coverage.unresolved,1);
assert.equal(product.output.presentationMeta({},read).canonical,read);
assert.equal((await product.execute({action:'read'},{agent:{session:{snapshotEvents:()=>[]}}})).result.coverage.status,'not_defined');
await assert.rejects(product.execute({action:'define',expected_revision:99,definition,change_reason:'stale'},exec),/revision/);
await assert.rejects(product.execute({action:'read',definition},exec),/require action/);
await assert.rejects(product.execute({action:'define',expected_revision:3,definition:reviewed,change_reason:'nested'},
  {...exec,parent:Symbol('ptc')}),/direct native/);
assert.equal(http,0);

// The actual pre-step projection exposes pending obligations, including after
// model-surface compaction, without creating another scene query.
const hooks={},contexts=[];
installSceneContext({systemPrompt:{context:c=>contexts.push(c)},on:(n,f)=>hooks[n]=f},{sceneContext(){throw Error('no scene query')}});
const agent={session:{snapshotEvents:()=>events,header:{},surface:{nodes:[],replaceGeneration:0}}};
const assembly={contexts:structuredClone(contexts),tools:[{name:'houdini_query'}]};
const signal=new AbortController().signal;
await hooks['system-prompt/assemble'](assembly,{agent,scope:{},signal},async()=>assembly);
const entered=await hooks['agent/pre-step']({agent,signal},async()=>({kind:'enter',messages:[]}));
assert(entered.messages.some(m=>m.content.some(b=>b.text?.includes('"product"')&&b.text.includes('"rim"'))));
console.log('product definitions: revision/source isolation, missing obligations, exact final-output evidence, stale checks, scope mismatch, full coverage and pre-step recovery passed');

const current=productState(events).current;
const physical={...structuredClone(current.definition),requirements:[...structuredClone(current.definition.requirements),
  {id:'length',kind:'dimension',description:'Source length in meters',subjects:['base'],state:'default',
    dimension:{group:'base',axis:0,expected_m:.12,tolerance_m:.0001},
    checks:[{verb:'geo_check_interfaces',contract_sha256:'d'.repeat(64),check_id:'length'}]},
  {id:'end_support',kind:'relation',description:'Support at full travel',subjects:['slider','rail'],state:'travel=.07',
    control_values:{travel:.07},checks:[{verb:'test_controls',contract_sha256:'e'.repeat(64),case_id:'end',check_id:'join'}]},
]};
physical.requirements.find(r=>r.id==='rim').feature={family:'edge',purpose:'safe visible edge',attachment:'lid perimeter',
  controls:['wall_thickness'],construction:'local bevel',inspection:'close-up and width check'};
recordDefinition(defineProduct(events,physical,current.revision,'Register physical dimensions, states and feature design'),'physical-definition');
measure({contract:'d'.repeat(64),rows:[{id:'length',status:'pass',method:'physical_extent',target_group:'base',axis:0,expected_mm:120000,tolerance_mm:.1}]});
assert.equal(productCoverage(events).requirements.find(r=>r.id==='length').status,'unverified','a 1000x wrong expected quantity cannot satisfy a meter requirement');
measure({contract:'d'.repeat(64),rows:[{id:'length',status:'pass',method:'physical_extent',target_group:'base',axis:0,expected_mm:120,tolerance_mm:.1}]});
assert.equal(productCoverage(events).requirements.find(r=>r.id==='length').status,'measured');
measure({verb:'test_controls',contract:'e'.repeat(64),rows:[{id:'end',status:'pass',actual_values:{travel:.01},
  interfaces:{results:[{id:'join',status:'pass',source_group:'slider',target_group:'rail'}]}}]});
assert.equal(productCoverage(events).requirements.find(r=>r.id==='end_support').status,'unverified','another control state cannot cover the full-travel requirement');
measure({verb:'test_controls',contract:'e'.repeat(64),rows:[{id:'end',status:'pass',actual_values:{travel:.07},
  interfaces:{results:[{id:'join',status:'pass',source_group:'slider',target_group:'rail'}]}}]});
assert.equal(productCoverage(events).requirements.find(r=>r.id==='end_support').status,'measured');
assert.equal(productCoverage(events).detail_plan.with_design,1);
assert.equal(productCoverage(events).requirements.find(r=>r.id==='rim').status,'missing','a design plan never certifies a detail');
assert.throws(()=>validateProductDefinition({...physical,requirements:[{...physical.requirements.at(-1),control_values:{travel:'70'}}]}),/control_values/);

// Registered expectations survive a convenient but unrelated passing receipt.
const locked=structuredClone(productState(events).current.definition);
locked.requirements.push({id:'unplanned',kind:'part',description:'A required part without a numeric plan',subjects:['unplanned'],state:'default',checks:[]});
locked.requirements.push({id:'ribs',kind:'part',description:'Eight separate rib instances',subjects:['ribs'],state:'default',
  members:{group:'ribs',expected_components:8},checks:[{verb:'geo_check_interfaces',contract_sha256:'f'.repeat(64),check_id:'ribs'}]},
  {id:'seat',kind:'relation',description:'Actual seat vertices remain near base',subjects:['slider','base'],state:'default',
    contact:{source_group:'seat_vertices',target_group:'base',max_distance:.00005,expected_points:8},
    checks:[{verb:'geo_check_interfaces',contract_sha256:'f'.repeat(64),check_id:'seat'}]});
recordDefinition(defineProduct(events,locked,productState(events).current.revision,'Register independent expectations'),'locked-definition');
const resultFor=id=>productCoverage(events).requirements.find(r=>r.id===id);
measure({contract:'f'.repeat(64),rows:[
  {id:'ribs',status:'pass',method:'component_count',target_group:'ribs',expected_components:64,observed_components:64},
  {id:'seat',status:'pass',source_group:'seat_vertices',target_group:'base',expected_points:8,tolerance:.001}]});
assert.equal(resultFor('ribs').status,'unverified','64 overlapping copies cannot satisfy the registered 8 members');
assert.equal(resultFor('seat').status,'unverified','a looser contact tolerance cannot cover the registered gap');
measure({contract:'f'.repeat(64),rows:[
  {id:'ribs',status:'pass',method:'component_count',target_group:'unrelated',expected_components:8,observed_components:8},
  {id:'seat',status:'pass',method:'solid_overlap',source_group:'seat_vertices',target_group:'base',max_overlap_volume:0}]});
assert.equal(resultFor('ribs').status,'unverified');assert.equal(resultFor('seat').status,'unverified','no overlap is not contact');
measure({contract:'f'.repeat(64),rows:[
  {id:'ribs',status:'pass',method:'component_count',target_group:'ribs',expected_components:8,observed_components:8},
  {id:'seat',status:'fail',source_group:'seat_vertices',target_group:'base',expected_points:8,tolerance:.00005}]});
assert.equal(resultFor('ribs').status,'measured');assert.equal(resultFor('seat').status,'fail');
const loosened=structuredClone(locked);loosened.requirements.find(r=>r.id==='seat').contact.max_distance=.001;
recordDefinition(defineProduct(events,loosened,productState(events).current.revision,'Revise a prototype assumption'),'loosened-definition');
let stage=productCoverage(events).workflow;
assert(stage.expectation_changes.some(x=>x.id==='seat'&&x.fields.includes('contact')),'expectation changes stay visible');
recordDefinition(defineProduct(events,loosened,productState(events).current.revision,'No further expectation changes'),'unchanged-definition');
assert.equal(productCoverage(events).workflow.expectation_changes.length,stage.expectation_changes.length);
const reordered=structuredClone(loosened);
reordered.requirements.find(r=>r.id==='ribs').members={expected_components:8,group:'ribs'};
recordDefinition(defineProduct(events,reordered,productState(events).current.revision,'Equivalent object key order'),'reordered-definition');
assert.equal(productState(events).expectation_changes.length,stage.expectation_changes.length,'object key order is not an expectation change');
measure();const saved=events.at(-1).data.meta.canonical;
saved.evidence=[];saved.verbs=[{verb:'scene_save',ok:true,result:{path:'C:/work/model.hip',bytes:200}}];
stage=(await product.execute({action:'review'},exec)).result.workflow;
assert.equal(stage.persistence.last_save.bytes,200);
assert.equal(stage.completion.status,'not_certified','a valid save does not certify the product');
assert.equal(stage.stages.numerical_checks.status,'incomplete');
assert(stage.stages.expectation_plan.gaps.some(x=>x.id==='unplanned'&&x.missing==='members'));
assert.equal(http,0,'review and expectation binding remain Host-only');
const recent=(await product.execute({action:'review'},exec)).result.evidence_index;
assert(recent.rows.some(r=>r.binding.check_id==='seat'&&r.source_group==='seat_vertices'));
assert(recent.rows.length<=32);
assert.throws(()=>validateProductDefinition({...locked,requirements:[{...locked.requirements.at(-2),members:{group:'ribs',expected_components:0}}]}),/members/);
assert.throws(()=>validateProductDefinition({...locked,requirements:[{...locked.requirements.at(-1),contact:{source_group:'s',target_group:'b',expected_points:0,max_distance:.1}}]}),/contact/);
console.log('registered member/contact expectations, revision disclosure and persistence/acceptance separation passed');
// Optional requirements never gate execution or checkpoint persistence.
{
const defs=new Map(),sent=[];
registerHoudiniTools({tools:{register:d=>defs.set(d.name,d)}},{
  exec:async(code,_timeout,_args,_raw,readOnly)=>{sent.push({code,readOnly});return {ok:true,stdout:'',stderr:''};},
  submitJob:async(code)=>{sent.push({code});return {jobId:'012345abcdef'};},
});
const plain={agent:{id:'author',session:{snapshotEvents:()=>[]}},callId:'call',signal:new AbortController().signal};
await defs.get('houdini_exec').execute({code:'__result__=1'},plain);
await defs.get('houdini_job_submit').execute({code:'__result__=2'},plain);
assert.equal(sent.length,2,'a product definition is optional for all construction');
for(const checkpoint of [{expected_path:'C:/work/model.hip'},
  {path:'C:/work/new.hip',expected_current_path:'C:/work/old.hip',reason:'User specified Save As',overwrite:false}]) {
  await defs.get('houdini_exec').execute({checkpoint},plain);
  assert.match(sent.at(-1).code,/__result__ = scene_save(?:_as)?\(\*\*__dsh_checkpoint\)$/);
}
const before=sent.length;
await assert.rejects(defs.get('houdini_exec').execute({checkpoint:{expected_path:'C:/x.hip'},code:'anything'},plain),/exactly one/);
assert.equal(sent.length,before);
console.log('optional product records and checkpoint persistence passed');

}
