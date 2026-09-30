/** Attention views derived from ordered execution facts. */
import {executionHistory,type SessionEvent as Event} from './execution-history.js'
const CHECKS = new Set(['build_module', 'verify_network', 'test_controls', 'geo_check_interfaces', 'geo_piece_stats', 'render_view', 'render_frame',
  'cop_layer_stats', 'cop_compare_layers', 'test_cop_controls'])

function needsExecutionAttention(check: any): boolean {
  return check.validity.startsWith('stale_') || check.validity.startsWith('unverified_')
    || (check.verb === 'geo_check_interfaces' && ['fail','unverified'].includes(check.status))
    || (check.verb === 'test_controls' && ['fail','warning','unverified'].includes(check.status))
    || (check.verb === 'geo_piece_stats'
      && (check.status === 'unverified' || (check.risk_reasons || []).length > 0))
}

function isUnresolvedDeclaredCheck(check: any): boolean {
  return ['geo_check_interfaces','test_controls'].includes(check.verb)
    && ['fail','unverified'].includes(check.status)
}

export function projectExecutionState(events: readonly Event[], history=executionHistory(events)): Record<string, unknown> | null {
  const {rows,anchor,unresolvedCalls,pendingCalls,activeRequests,activeJobs}=history
  const uncertain=unresolvedCalls.map(row=>row.seq)
  if (!rows.length) return uncertain.length || activeJobs.length || pendingCalls.length || activeRequests.length
    ? {status:'execution_state_unknown', pending_calls:pendingCalls.length, active_jobs:activeJobs,
       unresolved_requests:activeRequests, unresolved_calls:unresolvedCalls.map(row=>row.callId),
       reason:'No ordered Bridge observation; inspect current outputs and in-flight work before retrying mutations.'} : null
  if (!anchor) return null
  const runtimeRows = rows.filter(r => r.execution.runtime_id === anchor.execution.runtime_id)
  const all = runtimeRows.filter(r => r.execution.hip_path === anchor.execution.hip_path)
  const unique = new Map<number, any>()
  for (const row of all) if (!unique.has(row.execution.sequence)) unique.set(row.execution.sequence, row)
  const ordered = [...unique.values()].sort((a,b) => a.execution.sequence-b.execution.sequence)
  const current = ordered.slice(-128)
  const nodes = new Map<number, any>()
  const checks = new Map<string, any>()
  const failures: any[] = []
  const inFlight = activeJobs.length > 0 || pendingCalls.length > 0 || activeRequests.length > 0
  for (const row of current) {
    const {value, execution:e, eventSeq, callId} = row
    const impact = e.impact || {}
    const changed = new Set((impact.nodes || []).map((n:any)=>n.identity))
    const mayHaveEdited = impact.attempted === true && value.transaction?.status !== 'no_scene_change'
    if (mayHaveEdited) for (const check of checks.values()) {
      if (impact.global || impact.truncated || impact.unavailable || check.identity === null || changed.has(check.identity)
          || (check.dependency_identities || []).some((id:number) => changed.has(id))
          || check.verb.startsWith('render_')) {
        // Once invalid, another edit cannot make this old check less valid.
        // Keep the first invalidator stable so unchanged attention is not
        // reinjected after every subsequent mutation.
        if (!check.validity.startsWith('stale_') && !check.validity.startsWith('unverified_')) {
          check.validity = 'stale_after_recorded_change'
          check.invalidated_by = callId
        }
      }
    }
    for (const n of value.transaction?.nodes || []) if (Number.isFinite(n.identity)) {
      nodes.delete(n.identity)
      nodes.set(n.identity,{identity:n.identity,path:n.path ?? n.prior_path,
        last_observed_exists:n.exists,source_call:callId,sequence:e.sequence})
    }
    const byIndex = new Map((e.outputs || []).map((o:any)=>[o.ledger_index,o]))
    for (const item of value.evidence || []) {
      if (!CHECKS.has(item?.verb)) continue
      if (item.verb === 'geo_piece_stats' && item.method !== 'bounded polygon surface integrity') continue
      const binding:any = byIndex.get(item.ledgerIndex)
      const identity = binding?.identity ?? null
      const dependencyIdentities = (binding?.dependencies || []).map((d:any) => d.identity).filter(Number.isFinite)
      const checkStatus = item.verb === 'geo_piece_stats'
        ? item.status === 'unverified' ? 'unverified'
          : item.risk_status === 'needs_review' || item.boundary_review_status === 'open_boundary_unreviewed' ? 'warning'
          : item.risk_status === 'no_detected_integrity_risk' ? 'no_detected_integrity_risk' : 'unverified'
        : item.verb === 'geo_check_interfaces' ? item.status === 'unverified' ? 'unverified'
          : item.status === 'fail' || item.ok === false ? 'fail'
          : item.status === 'pass' && item.ok === true ? 'pass' : 'unverified'
        : item.verb === 'test_controls' ? item.restored === false ? 'fail'
          : item.status === 'unverified' ? 'unverified'
          : item.status === 'fail' || item.ok === false ? 'fail'
          : item.status === 'pass' && item.ok === true ? 'pass' : 'unverified'
        : item.ok === false || item.restored === false ? 'fail'
        : item.warning_free === false || item.healthy === false ? 'warning'
        : item.status ?? (item.ok === true ? 'observed_pass' : 'unverified')
      const rolledBack = value.transaction?.status === 'rolled_back' || value.transaction?.status === 'recovery_unverified'
      const supersededInCall = (impact.last_edit_ledger_index ?? 0) > item.ledgerIndex
      const unknownOrder = (value.rawUsage?.coveredMutations?.length || value.rawUsage?.suspectedMutations?.length) > 0
      const validity = rolledBack ? 'not_current_after_failed_transaction'
        : unknownOrder ? 'unverified_change_order_in_call'
        : supersededInCall ? 'stale_after_later_edit_in_same_call'
        : 'historical_observation_only'
      const declaredContract = item.verb === 'geo_check_interfaces' || item.verb === 'test_controls'
      const contractHash = declaredContract && typeof item.contract_sha256 === 'string'
        && /^[0-9a-f]{64}$/i.test(item.contract_sha256) ? item.contract_sha256.toLowerCase() : null
      const portScope = declaredContract
        ? contractHash ?? `unknown_contract:${callId}:${item.ledgerIndex ?? value.evidence.indexOf(item)}`
        : item.verb === 'geo_piece_stats' ? JSON.stringify(item.group ?? null)
        : item.verb === 'cop_compare_layers' ? JSON.stringify(binding?.dependencies || [])
        : item.verb === 'cop_layer_stats' ? item.output : item.verb === 'test_cop_controls' ? item.output_port : ''
      const key = `${item.verb}:${identity ?? binding?.path ?? item.output ?? item.node ?? item.ledgerIndex}:${portScope}`
      checks.delete(key)
      checks.set(key,{verb:item.verb,identity,output:binding?.path ?? item.output ?? item.node,
        ...(dependencyIdentities.length ? {dependency_identities:dependencyIdentities} : {}),
        ...(item.verb === 'geo_piece_stats' ? {group:item.group ?? null,
          boundary_edges:item.boundary_edges ?? null,risk_reasons:item.risk_reasons ?? []} : {}),
        ...(declaredContract ? {contract_sha256:contractHash} : {}),
        status:checkStatus,validity,scope:item.scope ?? null,frame:item.frame ?? e.frame,
        source_call:callId,event_seq:eventSeq,sequence:e.sequence,
        ...(value.details?.stored ? {result_ref:value.details.sha256,pointer:`/evidence/${value.evidence.indexOf(item)}`} : {})})
    }
    if (value.ok === false) failures.push({call_id:callId,sequence:e.sequence,
      transaction:value.transaction?.status ?? 'unknown',reason:String(value.error ?? 'execution failed').slice(0,240)})
  }
  for (const check of checks.values()) if (inFlight || uncertain.some(seq => seq > check.event_seq)) {
    check.validity = 'unverified_after_unobserved_or_inflight_execution'
  }
  const allChecks = [...checks.values()]
  const attentionChecks = allChecks.filter(needsExecutionAttention)
  // A failed declared product relation must survive a later burst of stale
  // build/render checkpoints. The notice is still bounded and exposes overflow.
  const retainedChecks = new Set(attentionChecks.filter(isUnresolvedDeclaredCheck).slice(-8))
  for (let index=attentionChecks.length-1; index>=0 && retainedChecks.size<8; index--) {
    retainedChecks.add(attentionChecks[index])
  }
  for (let index=allChecks.length-1; index>=0 && retainedChecks.size<8; index--) retainedChecks.add(allChecks[index])
  const projectedChecks = allChecks.filter(check => retainedChecks.has(check))
  return {status:'recorded_execution_facts',runtime_id:anchor.execution.runtime_id,
    hip_path:anchor.execution.hip_path ?? null,
    last_sequence:current.at(-1)?.execution.sequence,last_observed_at:current.at(-1)?.execution.observed_at,
    frame:current.at(-1)?.execution.frame,
    nodes:[...nodes.values()].slice(-12),checks:projectedChecks,
    recent_failures:failures.slice(-2),active_jobs:activeJobs,pending_calls:pendingCalls.length,unresolved_requests:activeRequests,
    unresolved_calls:unresolvedCalls.map(row=>row.callId),
    coverage:{execution_records:current.length,older_records_omitted:ordered.length-current.length,
      other_runtime_records_excluded:rows.length-runtimeRows.length,
      other_hip_records_excluded:runtimeRows.length-all.length,nodes_omitted:Math.max(0,nodes.size-12),
      checks_omitted:allChecks.length-projectedChecks.length,
      attention_checks_omitted:attentionChecks.length-projectedChecks.filter(needsExecutionAttention).length},
    boundary:'Historical tool observations only, not current live state or permission. Native dependency hints exclude unobserved GUI edits, last-cook omissions and external/dynamic dependencies. Non-stale does not mean currently valid; recheck relevant state before relying on it.'}
}

/** Only facts requiring attention beyond an ordinary returned tool result.
 * No clocks, counters, healthy-node inventory or repeated error traceback.
 */
export function projectExecutionNotice(events: readonly Event[], history=executionHistory(events), state:any=projectExecutionState(events,history)): Record<string, unknown> | null {
  if (!state) return null
  const checks = (state.checks || []).filter(needsExecutionAttention)
    .map((check: any) => ({verb:check.verb,identity:check.identity,output:check.output,
      status:check.status,validity:check.validity,source_call:check.source_call,
      result_ref:check.result_ref,pointer:check.pointer,contract_sha256:check.contract_sha256,
      group:check.group,boundary_edges:check.boundary_edges,
      risk_reasons:check.risk_reasons,invalidated_by:check.invalidated_by}))
  const observations=history.foreground.map(row=>({id:row.callId,...row.execution}))
    .sort((a,b)=>a.observed_at-b.observed_at||a.sequence-b.sequence)
  let changed: any = null
  for (let i=1;i<observations.length;i++) {
    const before=observations[i-1], after=observations[i]
    if (before.runtime_id !== after.runtime_id || before.hip_path !== after.hip_path) {
      changed={source_call:after.id,previous_runtime:before.runtime_id,runtime_id:after.runtime_id,
        previous_hip:before.hip_path ?? null,hip_path:after.hip_path ?? null}
    }
  }
  const requests = state.unresolved_requests || [], unresolved = state.unresolved_calls || []
  if (!checks.length && !requests.length && !unresolved.length && !state.pending_calls && !changed) return null
  return {status:'execution_attention',runtime_id:state.runtime_id ?? null,
    observed_scene_change:changed,checks,attention_checks_omitted:state.coverage?.attention_checks_omitted ?? 0,
    unresolved_requests:requests,unresolved_calls:unresolved,
    pending_calls:state.pending_calls || 0,
    boundary:'Historical tool evidence, not live state or permission. A passing declared interface is not whole-product acceptance. Resolve uncertain requests by their original reference before repeating mutations. Recheck affected outputs; passive GUI activity is not observed or a new user target.'}
}
