import assert from 'node:assert/strict';
import {projectExecutionState,projectExecutionNotice} from '../../lib/execution-state.js';

const events=[];
function record(sequence, {tool='houdini_exec',runtime='R',nodes=[],networkBoxes,impact={},evidence=[],outputs=[],status='committed',ok=true,observed=sequence,jobId,jobStatus,details}={}) {
  const id='call-'+events.length;
  events.push({seq:events.length+1,type:'tool/call',data:{callId:id,name:tool}});
  const canonical={ok,transaction:{status,nodes,...(networkBoxes?{network_boxes:networkBoxes}:{})},evidence,
    ...(details?{details}:{}),
    execution:{runtime_id:runtime,sequence,observed_at:observed,frame:1,
      impact:{attempted:false,nodes:[],...impact},outputs},...(jobId?{jobId,status:jobStatus}:{})};
  events.push({seq:events.length+1,type:'tool/result',data:{meta:{canonical},message:{source:{callId:id},content:[]}}});
  return id;
}
const node=(identity,exists=true)=>({identity,path:'/obj/n'+identity,exists});
const check={ledgerIndex:1,verb:'verify_network',output:'/obj/n1',ok:true,scope:'explicit_nodes'};
const output={ledger_index:1,verb:'verify_network',identity:1,path:'/obj/n1',exists:true};
record(1,{nodes:[node(1)],evidence:[check],outputs:[output]});
record(2,{nodes:[node(2)],impact:{attempted:true,nodes:[node(2)]}});
assert.equal(projectExecutionState(events).checks[0].validity,'historical_observation_only','unrelated native edit does not falsely invalidate a known different branch');
record(3,{impact:{attempted:true,nodes:[node(10),node(1)]}});
assert.equal(projectExecutionState(events).checks[0].validity,'stale_after_recorded_change');
record(4,{tool:'houdini_query',status:'no_scene_change',nodes:[node(1,false)]});
assert.equal(projectExecutionState(events).nodes.find(n=>n.identity===1).last_observed_exists,false);
record(5,{evidence:[check],outputs:[output],impact:{attempted:true,last_edit_ledger_index:2,nodes:[node(1)]}});
assert.equal(projectExecutionState(events).checks[0].validity,'stale_after_later_edit_in_same_call');
record(6,{evidence:[check],outputs:[output],status:'rolled_back',ok:false});
assert.equal(projectExecutionState(events).checks[0].validity,'not_current_after_failed_transaction');
record(7,{evidence:[check],outputs:[output],status:'no_scene_change'});
const validityBeforePresentation=projectExecutionState(events).checks[0].validity;
record(8,{networkBoxes:{entry_count:1,box_count:2,node_count:4},impact:{attempted:false,nodes:[]}});
assert.equal(projectExecutionState(events).checks[0].validity,validityBeforePresentation,
  'typed Network Box presentation does not pollute node history or stale geometry evidence');
const duplicate=events.at(-1);events.push({...duplicate,seq:100});
assert.equal(projectExecutionState(events).coverage.execution_records,8,'result replay is not another execution');
events.push({seq:101,type:'tool/call',data:{name:'houdini_exec',callId:'timeout'}},
  {seq:102,type:'tool/result',data:{message:{source:{callId:'timeout'},content:[{isError:true}]}}});
assert.equal(projectExecutionState(events).checks[0].validity,'unverified_after_unobserved_or_inflight_execution');
// New runtime identities cannot revive old paths/pass results.
record(1,{runtime:'NEW',observed:1000,nodes:[node(9)]});
assert.equal(projectExecutionState(events).runtime_id,'NEW');
assert.equal(projectExecutionState(events).checks.length,0);
assert.deepEqual(projectExecutionState(events).nodes.map(n=>n.identity),[9]);
record(9,{tool:'houdini_job_status',runtime:'R',observed:9,jobId:'old',jobStatus:'done',evidence:[check],outputs:[output]});
assert.equal(projectExecutionState(events).runtime_id,'NEW','late old-runtime job result does not reset the active observation');
const fresh=[];
const earlier=events.splice(0);
record(2,{runtime:'NEW',observed:2,nodes:[node(2)]});
record(1,{runtime:'NEW',observed:1,nodes:[node(1)]});
assert.equal(projectExecutionState(events).last_sequence,2,'arrival order is not execution order');
events.push({seq:30,type:'tool/call',data:{name:'houdini_job_submit',callId:'job'}},
  {seq:31,type:'tool/result',data:{meta:{jobId:'J'},message:{source:{callId:'job'},content:[]}}});
assert.equal(projectExecutionState(events).active_jobs[0][0],'J');
record(3,{runtime:'NEW',observed:3,nodes:[node(3)]});
events.at(-1).data.meta.canonical.execution.hip_path='new_project.hip';
assert.deepEqual(projectExecutionState(events).nodes.map(n=>n.identity),[3],'different observed HIP path cannot inherit prior scene identities');
assert.equal(projectExecutionState(events).hip_path,'new_project.hip');
assert.equal(projectExecutionState([]),null);
events.splice(0);
record(1,{evidence:[{ledgerIndex:1,verb:'cop_compare_layers',status:'pass',ok:true}],
  outputs:[{ledger_index:1,verb:'cop_compare_layers',identity:3,path:'/obj/n3',exists:true,
    dependencies:[{identity:1,node:'/obj/n1',output:0},{identity:3,node:'/obj/n3',output:0}]}]});
record(2,{impact:{attempted:true,nodes:[node(1)]}});
assert.equal(projectExecutionState(events).checks[0].validity,'stale_after_recorded_change',
  'independent before/delta operands invalidate a comparison even when after is unchanged');
record(3,{evidence:[{ledgerIndex:1,verb:'cop_layer_stats',node:'/obj/n3',output:0,status:'pass',ok:true},
                   {ledgerIndex:2,verb:'cop_layer_stats',node:'/obj/n3',output:1,status:'unverified',ok:true}],
  outputs:[{ledger_index:1,identity:3,path:'/obj/n3'},{ledger_index:2,identity:3,path:'/obj/n3'}]});
assert.equal(projectExecutionState(events).checks.filter(c=>c.verb==='cop_layer_stats').length,2,
  'different output ports cannot overwrite each other');
assert.equal(projectExecutionState(events).checks.at(-1).status,'unverified');
events.splice(0);
record(1,{evidence:[check],outputs:[output]});
const firstInvalidator=record(2,{impact:{attempted:true,nodes:[node(1)]}});
const firstAttention=projectExecutionNotice(events);
assert.equal(firstAttention.checks[0].invalidated_by,firstInvalidator);
record(3,{impact:{attempted:true,nodes:[node(1)]}});
assert.deepEqual(projectExecutionNotice(events),firstAttention,
  'a second edit must not rewrite an already-stale check and force another attention message');
events.splice(0);
const surfaceOutput={ledger_index:1,verb:'geo_piece_stats',identity:7,path:'/obj/n7',exists:true};
const surfaceRisk={ledgerIndex:1,verb:'geo_piece_stats',method:'bounded polygon surface integrity',
  node:'/obj/n7',status:'observed',group:null,risk_status:'needs_review',risk_reasons:['nonmanifold_edges'],
  boundary_edges:0,boundary_review_status:'none'};
record(1,{evidence:[surfaceRisk],outputs:[surfaceOutput]});
assert.equal(projectExecutionState(events).checks[0].status,'warning');
assert.equal(projectExecutionNotice(events).checks[0].risk_reasons[0],'nonmanifold_edges',
  'a scoped surface risk remains visible after the tool result');
record(2,{evidence:[{...surfaceRisk,risk_status:'no_detected_integrity_risk',risk_reasons:[]}],outputs:[surfaceOutput]});
assert.equal(projectExecutionState(events).checks[0].status,'no_detected_integrity_risk');
assert.equal(projectExecutionNotice(events),null,'a new clean check supersedes an old risk for the same output and group');
record(3,{evidence:[{...surfaceRisk,risk_status:'no_detected_integrity_risk',risk_reasons:[],
  boundary_edges:4,boundary_review_status:'open_boundary_unreviewed'}],outputs:[surfaceOutput]});
assert.equal(projectExecutionState(events).checks[0].status,'warning',
  'an open port needs review but is not automatically a broken surface');
assert.equal(projectExecutionNotice(events),null,
  'an intentional open-port candidate stays in the check record without becoming a persistent hard-risk reminder');
record(4,{evidence:[{ledgerIndex:1,verb:'geo_piece_stats',method:'full selected polygon topology and point extents',
  node:'/obj/n7',status:'observed'}],outputs:[surfaceOutput]});
assert.equal(projectExecutionState(events).checks.length,1,
  'ordinary geometry observations do not overwrite an integrity risk');
events.splice(0);
const failedControl={ledgerIndex:1,verb:'test_controls',output:'/obj/n7',ok:false,status:'fail',restored:true,
  contract_sha256:'e'.repeat(64)};
const controlOutput={ledger_index:1,verb:'test_controls',identity:7,path:'/obj/n7',exists:true};
record(1,{evidence:[failedControl],outputs:[controlOutput]});
assert.equal(projectExecutionNotice(events).checks[0].status,'fail',
  'restoration does not turn a failed control verdict into a pass');
record(2,{impact:{attempted:true,nodes:[node(7)]}});
assert.equal(projectExecutionNotice(events).checks[0].status,'fail',
  'the original failed verdict remains explicit after a geometry edit makes it stale');
record(3,{evidence:[{...failedControl,ok:true,status:'pass',contract_sha256:'f'.repeat(64)}],
  outputs:[controlOutput]});
assert.equal(projectExecutionState(events).checks.length,2,
  'a narrower passing control test retains the failed contract on the same output');
assert.equal(projectExecutionNotice(events).checks[0].contract_sha256,failedControl.contract_sha256,
  'an unrelated passing control test cannot clear the failed control contract');
record(4,{evidence:[{...failedControl,ok:true,status:'pass'}],outputs:[controlOutput]});
assert.equal(projectExecutionNotice(events),null,'passing retest clears the old failed control check');
events.splice(0);
const unknownControl={...failedControl};delete unknownControl.contract_sha256;
record(1,{evidence:[unknownControl],outputs:[controlOutput]});
record(2,{evidence:[{...unknownControl,ok:true,status:'pass'}],outputs:[controlOutput]});
assert.equal(projectExecutionNotice(events).checks[0].status,'fail',
  'without a control contract hash, a later pass cannot prove it retested the failed declaration');
events.splice(0);
const unverifiedControl={...failedControl,status:'unverified',contract_sha256:'1'.repeat(64)};
record(1,{evidence:[unverifiedControl],outputs:[controlOutput]});
record(2,{evidence:[{...unverifiedControl,ok:true,status:'pass',contract_sha256:'2'.repeat(64)}],
  outputs:[controlOutput]});
assert.equal(projectExecutionNotice(events).checks[0].status,'unverified',
  'a different passing control contract cannot hide an unverified declaration');
record(3,{evidence:[{...unverifiedControl,ok:true,status:'pass'}],outputs:[controlOutput]});
assert.equal(projectExecutionNotice(events),null,'matching control retest clears unverified attention');
events.splice(0);
const interfaceOutput={ledger_index:1,verb:'geo_check_interfaces',identity:11,path:'/obj/asset/OUT_ASSET',exists:true};
const failedInterface={ledgerIndex:1,verb:'geo_check_interfaces',output:'/obj/asset/OUT_ASSET',
  ok:false,status:'fail',contract_sha256:'c'.repeat(64),scope:'declared interfaces only',
  results:[{id:'pin_span',status:'fail'}]};
const stored={stored:true,sha256:'a'.repeat(64)};
const failingCall=record(1,{evidence:[failedInterface],outputs:[interfaceOutput],details:stored});
const interfaceAttention=projectExecutionNotice(events);
assert.equal(interfaceAttention.checks[0].status,'fail','a failed final interface remains visible after its tool result');
assert.equal(interfaceAttention.checks[0].output,'/obj/asset/OUT_ASSET');
assert.equal(interfaceAttention.checks[0].source_call,failingCall);
assert.equal(interfaceAttention.checks[0].result_ref,stored.sha256);
assert.equal(interfaceAttention.checks[0].pointer,'/evidence/0');
assert.equal(interfaceAttention.checks[0].contract_sha256,failedInterface.contract_sha256);
assert.match(interfaceAttention.boundary,/not whole-product acceptance/);
record(2,{impact:{attempted:true,nodes:[node(99)]}});
assert.deepEqual(projectExecutionNotice(events),interfaceAttention,
  'an unrelated edit does not clear or rewrite a failed interface notice');
record(3,{evidence:[{...failedInterface,status:'unverified',results:[{id:'pin_span',status:'unverified'}]}],
  outputs:[interfaceOutput],details:{stored:true,sha256:'b'.repeat(64)}});
assert.equal(projectExecutionState(events).checks[0].status,'unverified',
  'interface unverified must not collapse to fail merely because ok is false');
assert.equal(projectExecutionNotice(events).checks[0].status,'unverified');
record(4,{evidence:[{...failedInterface,ok:true,status:'pass',results:[{id:'pin_span',status:'pass'}]}],
  outputs:[interfaceOutput]});
assert.equal(projectExecutionState(events).checks[0].status,'pass');
assert.equal(projectExecutionNotice(events),null,
  'a passing retest clears the scoped attention, without asserting whole-product acceptance');
events.splice(0);
record(1,{evidence:[failedInterface],outputs:[interfaceOutput]});
record(2,{evidence:[{...failedInterface,ok:true,status:'pass',contract_sha256:'d'.repeat(64)}],
  outputs:[interfaceOutput]});
assert.equal(projectExecutionState(events).checks.length,2,'distinct contracts on one final output remain distinct');
assert.equal(projectExecutionNotice(events).checks[0].contract_sha256,failedInterface.contract_sha256,
  'a changed contract is not a repair of the old failing contract');
record(3,{evidence:[{...failedInterface,ok:true,status:'pass'}],outputs:[interfaceOutput]});
assert.equal(projectExecutionNotice(events),null,'only a retest of the original contract clears its failure');
events.splice(0);
const unknownContract={...failedInterface};delete unknownContract.contract_sha256;
record(1,{evidence:[unknownContract],outputs:[interfaceOutput]});
record(2,{evidence:[{...unknownContract,ok:true,status:'pass'}],outputs:[interfaceOutput]});
assert.equal(projectExecutionNotice(events).checks[0].status,'fail',
  'without a contract hash, an apparent pass cannot prove it retested the same declaration');
events.splice(0);
record(1,{evidence:[failedInterface],outputs:[interfaceOutput]});
for(let i=0;i<10;i++) {
  const id=100+i;
  record(2+i,{evidence:[{ledgerIndex:1,verb:'verify_network',output:'/obj/n'+id,ok:true}],
    outputs:[{ledger_index:1,verb:'verify_network',identity:id,path:'/obj/n'+id,exists:true}]});
}
assert.equal(projectExecutionState(events).checks.length,8,'check projection stays bounded');
assert.equal(projectExecutionState(events).coverage.attention_checks_omitted,0);
assert.equal(projectExecutionNotice(events).checks[0].contract_sha256,failedInterface.contract_sha256,
  'unrelated successful checks cannot evict an unresolved interface failure');
for(let i=0;i<10;i++) {
  const id=200+i;
  record(12+i,{evidence:[{ledgerIndex:1,verb:'build_module',output:'/obj/n'+id,ok:true}],
    outputs:[{ledger_index:1,verb:'build_module',identity:id,path:'/obj/n'+id,exists:true}],
    impact:{attempted:true,last_edit_ledger_index:2,nodes:[node(id)]}});
}
assert.equal(projectExecutionNotice(events).checks.some(c=>c.contract_sha256===failedInterface.contract_sha256),true,
  'a burst of stale build checkpoints cannot evict a failed declared relation');
events.splice(0);
for(let i=0;i<10;i++) {
  const id=100+i;
  record(i+1,{evidence:[{...failedInterface,contract_sha256:i.toString(16).padStart(64,'0'),
    output:'/obj/n'+id}],outputs:[{ledger_index:1,verb:'geo_check_interfaces',identity:id,
    path:'/obj/n'+id,exists:true}]});
}
assert.equal(projectExecutionNotice(events).checks.length,8);
assert.equal(projectExecutionNotice(events).attention_checks_omitted,2,
  'overflow is explicit rather than silently implying all unresolved contracts fit the notice');
console.log('execution-state projection: dependency invalidation, deleted identities, same-call edits, rollback, replay, timeout, runtime change, out-of-order jobs and pending jobs passed');
