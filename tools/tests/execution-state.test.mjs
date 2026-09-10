import assert from 'node:assert/strict';
import {projectExecutionState} from '../../lib/execution-state.js';

const events=[];
function record(sequence, {tool='houdini_exec',runtime='R',nodes=[],impact={},evidence=[],outputs=[],status='committed',ok=true,observed=sequence,jobId,jobStatus}={}) {
  const id='call-'+events.length;
  events.push({seq:events.length+1,type:'tool/call',data:{callId:id,name:tool}});
  const canonical={ok,transaction:{status,nodes},evidence,
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
const duplicate=events.at(-1);events.push({...duplicate,seq:100});
assert.equal(projectExecutionState(events).coverage.execution_records,7,'result replay is not another execution');
events.push({seq:101,type:'tool/call',data:{name:'houdini_exec',callId:'timeout'}},
  {seq:102,type:'tool/result',data:{message:{source:{callId:'timeout'},content:[{isError:true}]}}});
assert.equal(projectExecutionState(events).checks[0].validity,'unverified_after_unobserved_or_inflight_execution');
// New runtime identities cannot revive old paths/pass results.
record(1,{runtime:'NEW',observed:1000,nodes:[node(9)]});
assert.equal(projectExecutionState(events).runtime_id,'NEW');
assert.equal(projectExecutionState(events).checks.length,0);
assert.deepEqual(projectExecutionState(events).nodes.map(n=>n.identity),[9]);
record(8,{tool:'houdini_job_status',runtime:'R',observed:8,jobId:'old',jobStatus:'done',evidence:[check],outputs:[output]});
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
console.log('execution-state projection: dependency invalidation, deleted identities, same-call edits, rollback, replay, timeout, runtime change, out-of-order jobs and pending jobs passed');
