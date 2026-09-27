import assert from 'node:assert/strict';
import {projectDeliveryAudit} from '../../lib/delivery-audit.js';

const OLD='C:/work/checkpoint.hip', FINAL='C:/work/final.hip';
const contract='a'.repeat(64), otherContract='b'.repeat(64);
const events=[];
let sequence=0;
function record({hip=OLD,tool='houdini_exec',ok=true,evidence=[],outputs=[],verbs=[],
  impact={attempted:false,nodes:[]},error,transaction='committed'}={}) {
  const id=`call-${++sequence}`;
  events.push({seq:events.length+1,type:'tool/call',data:{callId:id,name:tool}});
  const canonical={ok,verbs,evidence,transaction:{status:transaction},
    ...(error?{error}:{}),execution:{runtime_id:'runtime-1',sequence,observed_at:sequence,
      hip_path:hip,impact,outputs}};
  events.push({seq:events.length+1,type:'tool/result',data:{message:{source:{callId:id}},meta:{canonical}}});
  return id;
}
const declared=(status,hash=contract,output='/obj/product/OUT_ASSET')=>({
  ledgerIndex:1,verb:'geo_check_interfaces',output,status,ok:status==='pass',contract_sha256:hash,
});
const binding=(identity=10,path='/obj/product/OUT_ASSET')=>({ledger_index:1,identity,path});
const save=(path,previous)=>({verb:previous?'scene_save_as':'scene_save',ok:true,
  result:{path,bytes:2048,mtime_ns:1,...(previous?{previous_path:previous}:{})}});

// An unrelated local success cannot erase a declared failure on the final output.
record({evidence:[declared('fail')],outputs:[binding()]});
record({evidence:[declared('pass',otherContract,'/obj/product/OUT_LOCAL')],
  outputs:[binding(11,'/obj/product/OUT_LOCAL')]});
assert.equal(projectDeliveryAudit(events).unresolved_checks.length,1);
assert.equal(projectDeliveryAudit(events).unresolved_checks[0].status,'fail');
events.splice(0);sequence=0;

// A passing check from before a related edit is historical, not acceptance.
record({evidence:[declared('pass')],outputs:[binding()]});
record({impact:{attempted:true,nodes:[{identity:10,path:'/obj/product/OUT_ASSET'}]}});
assert.equal(projectDeliveryAudit(events).unresolved_checks[0].validity,'stale_after_recorded_change');
events.splice(0);sequence=0;

// Successful Save As carries old failures forward only as pending rechecks.
record({evidence:[declared('fail')],outputs:[binding()]});
record({hip:FINAL,verbs:[save(FINAL,OLD)],impact:{attempted:true,global:true,nodes:[],last_edit_ledger_index:1}});
let audit=projectDeliveryAudit(events,{expectedFinalPath:FINAL});
assert.equal(audit.unresolved_checks[0].status,'fail');
assert.equal(audit.unresolved_checks[0].validity,'needs_recheck_after_save_as');
assert.equal(audit.unresolved_checks[0].hip_path,OLD.toLowerCase());
assert.equal(audit.delivery.status,'save_receipt_reopen_unverified');
record({hip:FINAL,evidence:[declared('pass')],outputs:[binding()]});
assert.equal(projectDeliveryAudit(events).unresolved_checks.length,0,
  'only a matching retest on the saved HIP clears the old declared failure');
events.splice(0);sequence=0;

// The audit reads immutable history beyond the execution notice's 128 rows.
record({evidence:[declared('unverified')],outputs:[binding()]});
for(let i=0;i<130;i++) record({tool:'houdini_query'});
audit=projectDeliveryAudit(events);
assert.equal(audit.unresolved_checks.length,1);
assert.equal(audit.unresolved_checks[0].status,'unverified');
events.splice(0);sequence=0;

// An unknown request invalidates prior acceptance until its original receipt is resolved.
record({evidence:[declared('pass')],outputs:[binding()]});
const unknown='c'.repeat(32)+'.'+'d'.repeat(32);
events.push({seq:events.length+1,type:'tool/call',data:{callId:'lost',name:'houdini_exec'}});
events.push({seq:events.length+1,type:'tool/result',data:{message:{source:{callId:'lost'}},
  meta:{canonical:{ok:false,requestReceipt:{request_ref:unknown,status:'unknown_transport'}}}}});
audit=projectDeliveryAudit(events);
assert.equal(audit.unresolved_requests[0].request_ref,unknown);
assert.equal(audit.unresolved_checks[0].validity,'unverified_after_unknown_execution');
events.splice(0);sequence=0;

// A checkpoint save is never inferred to be an explicitly requested final HIP.
record({verbs:[save(OLD)]});
audit=projectDeliveryAudit(events,{expectedFinalPath:FINAL});
assert.equal(audit.delivery.status,'final_not_saved');
assert.equal(audit.delivery.last_save,null);
assert.equal(audit.delivery.last_checkpoint.path,OLD);
events.splice(0);sequence=0;

// An execution failure still reaches the audit when no check verb ran.
record({ok:false,error:'Render process exited during execution',transaction:'recovery_unverified'});
audit=projectDeliveryAudit(events);
assert.equal(audit.execution_failures.length,1);
assert.match(audit.execution_failures[0].reason,/Render process exited/);
assert.equal(audit.status,'delivery_audit_attention');
const replay=structuredClone(events.at(-1));
replay.data.message.source.callId='recovered';
events.push({seq:events.length+1,type:'tool/call',data:{callId:'recovered',name:'houdini_query'}});
events.push({...replay,seq:events.length+1});
assert.equal(projectDeliveryAudit(events).execution_failures.length,1,
  'reading the original result again is not a second execution failure');

console.log('delivery audit: local pass, stale edit, Save As, long history, unknown request, checkpoint and unchecked failure passed');
