/** Read-only delivery facts reconstructed from immutable session events.
 * A save receipt is a file observation at that moment, not a reopened HIP or
 * permission to present it. Earlier checks remain historical after Save As.
 */
type Event = {type:string;seq?:number;data?:any}
type Row = {callId:string;eventSeq:number;value:any;execution:any}
type Check = {verb:string;identity:number|null;output:string|null;hip_path:string|null;
  contract_sha256:string|null;status:string;validity:string;source_call:string;
  sequence:number;event_seq:number;dependency_identities:number[];invalidated_by?:string;
  relationship_scope?:string;declared_interfaces?:number}

const DECLARED_CHECKS = new Set(['geo_check_interfaces','test_controls'])
const TERMINAL_RECEIPTS = new Set(['done','not_executed','job_submitted'])

function normalizedPath(path:unknown):string|null {
  return typeof path === 'string' && path.trim() ? path.replace(/\\/g,'/').replace(/\/+$/,'').toLowerCase() : null
}

function verbSave(value:any, name:'scene_save'|'scene_save_as') {
  if(value?.ok!==true) return []
  return (value?.verbs || []).map((verb:any,index:number)=>({verb,index:index+1}))
    .filter(({verb}:any)=>verb?.verb===name && verb.ok===true && typeof verb.result?.path==='string'
      && Number(verb.result?.bytes)>0)
}

function checkStatus(item:any):string {
  if (item.verb==='test_controls' && item.restored===false) return 'fail'
  if (item.status==='unverified') return 'unverified'
  if (item.status==='fail' || item.ok===false) return 'fail'
  return item.status==='pass' && item.ok===true ? 'pass' : 'unverified'
}

/** Optional expectedFinalPath is supplied by the task/evaluation harness.
 * Without it, the audit cannot infer that a checkpoint is the final deliverable.
 */
export function projectDeliveryAudit(events:readonly Event[], options:{expectedFinalPath?:string}={}):Record<string,unknown>|null {
  const calls=new Map<string,any>(), seen=new Set<string>(), rows:Row[]=[]
  const receipts=new Map<string,string>(), resolvedCalls=new Set<string>()
  for(const event of events) {
    const data=event.data
    if(event.type==='tool/call' && typeof data?.callId==='string') calls.set(data.callId,data)
    if(event.type!=='tool/result') continue
    const id=data?.message?.source?.callId
    if(typeof id!=='string' || seen.has(id) || !calls.has(id)) continue
    seen.add(id)
    const value=data?.meta?.canonical
    const receipt=value?.requestReceipt
    if(typeof receipt?.request_ref==='string'
        && !TERMINAL_RECEIPTS.has(receipts.get(receipt.request_ref)||'')) {
      receipts.set(receipt.request_ref,receipt.status)
    }
    if(typeof receipt?.owner_call==='string' && TERMINAL_RECEIPTS.has(receipt.status)) resolvedCalls.add(receipt.owner_call)
    const execution=value?.execution
    if(execution && typeof execution.runtime_id==='string' && Number.isFinite(execution.sequence)
        && Number.isFinite(execution.observed_at)) {
      rows.push({callId:id,eventSeq:event.seq??0,value,execution})
    }
  }
  const unresolvedRequests=[...receipts].filter(([,status])=>!TERMINAL_RECEIPTS.has(status))
    .map(([request_ref,status])=>({request_ref,status}))
  const pendingCalls=[...calls].filter(([id,call])=>!seen.has(id) && !resolvedCalls.has(id)
    && ['houdini_exec','houdini_job_submit'].includes(call.name)).map(([id])=>id)
  if(!rows.length) return unresolvedRequests.length || pendingCalls.length
    ? {status:'delivery_audit_attention',current_hip:null,delivery:{status:'unverified_no_observed_execution'},
      checks:[],unresolved_checks:[],execution_failures:[],unresolved_requests:unresolvedRequests,pending_calls:pendingCalls,
      boundary:'Historical receipts only; missing execution evidence cannot prove that scene code did not run.'}
    : null

  // A late job poll must not move the task back to an older runtime.
  const foreground=rows.filter(row=>['houdini_exec','houdini_query'].includes(calls.get(row.callId)?.name))
  const anchor=(foreground.length?foreground:rows).reduce((a,b)=>
    a.execution.observed_at>b.execution.observed_at
      || (a.execution.observed_at===b.execution.observed_at && a.execution.sequence>b.execution.sequence)?a:b)
  const runtime=anchor.execution.runtime_id
  const currentHip=normalizedPath(anchor.execution.hip_path)
  const runtimeRowsRaw=rows.filter(row=>row.execution.runtime_id===runtime)
    .sort((a,b)=>a.execution.sequence-b.execution.sequence)
  const unique=new Map<number,Row>()
  for(const row of runtimeRowsRaw) if(!unique.has(row.execution.sequence)) unique.set(row.execution.sequence,row)
  const runtimeRows=[...unique.values()]
  const transitions=runtimeRows.flatMap(row=>verbSave(row.value,'scene_save_as').flatMap(({verb}:any)=> {
    const from=normalizedPath(verb.result?.previous_path),to=normalizedPath(verb.result?.path)
    return from && to && to===normalizedPath(row.execution.hip_path)
      ? [{from,to,sequence:row.execution.sequence}] : []
  }))
  const lineage=new Set<string|null>([currentHip])
  for(let i=transitions.length-1;i>=0;i--) if(lineage.has(transitions[i].to)) lineage.add(transitions[i].from)
  const ordered=runtimeRows.filter(row=>lineage.has(normalizedPath(row.execution.hip_path)))
  const checks=new Map<string,Check>(), failures:any[]=[], saves:any[]=[]
  let lastEditSequence=0
  for(const row of ordered) {
    const {callId,eventSeq,value,execution}=row
    const path=normalizedPath(execution.hip_path)
    const saveAs=verbSave(value,'scene_save_as')
    for(const {verb} of saveAs) {
      const from=normalizedPath(verb.result.previous_path),to=normalizedPath(verb.result.path)
      if(from && to===path) for(const check of checks.values()) if(check.hip_path===from)
        check.validity='needs_recheck_after_save_as'
    }
    const impact=execution.impact||{}
    const mayHaveEdited=impact.attempted===true && value.transaction?.status!=='no_scene_change'
    if(mayHaveEdited) {
      const changed=new Set((impact.nodes||[]).map((node:any)=>node.identity))
      for(const check of checks.values()) {
        if(check.validity!=='historical_observation_only') continue
        if(impact.global || impact.truncated || impact.unavailable || check.identity===null || changed.has(check.identity)
            || check.dependency_identities.some(identity=>changed.has(identity))) {
          check.validity='stale_after_recorded_change'
          check.invalidated_by=callId
        }
      }
      // Save As itself is a global operation, but it does not dirty the newly
      // saved target unless a later verb in the same call changes the scene.
      lastEditSequence=execution.sequence
    }
    const outputs=new Map((execution.outputs||[]).map((output:any)=>[output.ledger_index,output]))
    for(const item of value.evidence||[]) {
      if(!DECLARED_CHECKS.has(item?.verb)) continue
      const binding:any=outputs.get(item.ledgerIndex)
      const identity=Number.isFinite(binding?.identity)?binding.identity:null
      const dependencyIdentities=(binding?.dependencies||[]).map((dependency:any)=>dependency.identity)
        .filter(Number.isFinite)
      const output=typeof binding?.path==='string'?binding.path
        :typeof item.output==='string'?item.output:null
      const contract=typeof item.contract_sha256==='string' && /^[0-9a-f]{64}$/i.test(item.contract_sha256)
        ? item.contract_sha256.toLowerCase():null
      // An unlabelled declaration cannot silently clear an earlier failure.
      const scope=contract??`unknown:${callId}:${item.ledgerIndex}`
      const key=`${item.verb}:${identity??output??item.ledgerIndex}:${scope}`
      const status=checkStatus(item)
      const sameCallEdit=(impact.last_edit_ledger_index??0)>item.ledgerIndex
      const validity=value.transaction?.status==='rolled_back' || value.transaction?.status==='recovery_unverified'
        ? 'not_current_after_failed_transaction'
        :value.rawUsage?.coveredMutations?.length || value.rawUsage?.suspectedMutations?.length
          ? 'unverified_change_order_in_call'
        :sameCallEdit?'stale_after_later_edit_in_same_call':'historical_observation_only'
      checks.delete(key)
      checks.set(key,{verb:item.verb,identity,output,hip_path:path,contract_sha256:contract,
        status,validity,source_call:callId,sequence:execution.sequence,event_seq:eventSeq,
        dependency_identities:dependencyIdentities,
        ...(item.verb==='test_controls' ? {
          relationship_scope:item.control_summary?.coverage?.relationship_scope ?? 'unknown',
          declared_interfaces:Number.isFinite(item.control_summary?.coverage?.declared_interfaces)
            ? item.control_summary.coverage.declared_interfaces : 0,
        } : {})})
    }
    const callName=calls.get(callId)?.name
    if(value.ok===false && (callName==='houdini_exec'
        || (callName==='houdini_job_status' && value.status==='failed'))) failures.push({source_call:callId,hip_path:path,sequence:execution.sequence,
      transaction:value.transaction?.status??'unknown',reason:String(value.error??'execution failed').slice(0,200)})
    for(const {verb,index} of [...verbSave(value,'scene_save'),...verbSave(value,'scene_save_as')]
      .sort((a,b)=>a.index-b.index)) {
      const savedPath=normalizedPath(verb.result.path)
      saves.push({path:verb.result.path,normalized_path:savedPath,source_call:callId,
        sequence:execution.sequence,bytes:verb.result.bytes,mtime_ns:verb.result.mtime_ns??null,
        kind:verb.verb,edit_after_save_in_call:(impact.last_edit_ledger_index??0)>index})
    }
  }
  if(unresolvedRequests.length || pendingCalls.length) for(const check of checks.values())
    check.validity='unverified_after_unknown_execution'
  const expected=normalizedPath(options.expectedFinalPath)
  const matchingSaves=saves.filter(save=>save.normalized_path===(expected??currentHip))
  const lastSave=matchingSaves.at(-1)??null
  const savedBeforeEdit=!!lastSave && (lastSave.edit_after_save_in_call || lastEditSequence>lastSave.sequence)
  const deliveryStatus=expected && !lastSave?'final_not_saved'
    :!lastSave?'no_current_save_receipt'
    :savedBeforeEdit?'save_precedes_recorded_edit'
    :expected?'save_receipt_reopen_unverified':'candidate_save_reopen_unverified'
  const allChecks=[...checks.values()]
  const attention=allChecks.filter(check=>check.status!=='pass' || check.validity!=='historical_observation_only')
  // A passing measurement-only control test cannot certify the mechanical
  // relations absent from its declaration. This is a coverage warning, not a
  // failed test or proof that a particular product relation is wrong.
  const coverageLimits=allChecks.filter(check=>check.verb==='test_controls'
      && check.status==='pass' && check.relationship_scope==='not_checked')
    .map(check=>({kind:'control_relationships_not_checked',output:check.output,
      source_call:check.source_call,contract_sha256:check.contract_sha256,
      validity:check.validity,declared_interfaces:check.declared_interfaces}))
  const result={status:attention.length || failures.length || unresolvedRequests.length || pendingCalls.length
      || coverageLimits.length || deliveryStatus==='final_not_saved' || deliveryStatus==='save_precedes_recorded_edit'
      ? 'delivery_audit_attention':'delivery_audit_observed',
    runtime_id:runtime,current_hip:anchor.execution.hip_path??null,
    delivery:{status:deliveryStatus,expected_final_path:options.expectedFinalPath??null,
      last_save:lastSave?{path:lastSave.path,source_call:lastSave.source_call,sequence:lastSave.sequence,
        bytes:lastSave.bytes,mtime_ns:lastSave.mtime_ns,kind:lastSave.kind}:null,
      last_checkpoint:saves.at(-1)?{path:saves.at(-1).path,source_call:saves.at(-1).source_call}:null,
      boundary:'A save receipt confirms a nonempty file at save time. Final delivery and independent reopen remain unverified.'},
    checks:allChecks.slice(-16),checks_omitted:Math.max(0,allChecks.length-16),
    unresolved_checks:attention.slice(-12),unresolved_checks_omitted:Math.max(0,attention.length-12),
    coverage_limits:coverageLimits.slice(-8),coverage_limits_omitted:Math.max(0,coverageLimits.length-8),
    execution_failures:failures.slice(-5),execution_failures_omitted:Math.max(0,failures.length-5),
    unresolved_requests:unresolvedRequests,pending_calls:pendingCalls,
    boundary:'Historical event audit only. A pass covers only declared measurements; missing relationship checks are not proof of failure or whole-product acceptance. Save As preserves prior failures as needing recheck. Unobserved GUI or external edits are outside this record.'}
  return result
}
