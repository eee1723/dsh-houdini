/** A bounded projection of durable tool facts, rebuilt from public events.
 * No second mutable scene database and no cached permissions/pass certificates.
 */
type Event = {type: string; seq?: number; time?: number; data?: any}
const NAMES = new Set(['houdini_exec', 'houdini_query', 'houdini_job_submit', 'houdini_job_status', 'houdini_job_cancel'])
const CHECKS = new Set(['build_module', 'verify_network', 'test_controls', 'geo_check_interfaces', 'render_view', 'render_frame'])

export function projectExecutionState(events: Event[]): Record<string, unknown> | null {
  const calls = new Map<string, any>()
  const seen = new Set<string>()
  const rows: any[] = []
  const uncertain: number[] = []
  const jobs = new Map<string, string>()
  for (const event of events) {
    const d = event.data
    if (event.type === 'tool/call' && NAMES.has(d?.name)) calls.set(d.callId, d)
    if (event.type !== 'tool/result') continue
    const id = d?.message?.source?.callId
    const call = calls.get(id)
    if (!call || seen.has(id)) continue
    seen.add(id)
    const value = d.meta?.canonical
    const job = value?.jobId ?? d.meta?.jobId
    if (typeof job === 'string') jobs.set(job, value?.status ?? d.meta?.status ?? 'queued_or_unknown')
    const e = value?.execution
    if (e && typeof e.runtime_id === 'string' && Number.isFinite(e.sequence) && Number.isFinite(e.observed_at)) {
      rows.push({eventSeq:event.seq ?? 0, callId:id, tool:call.name, value, e})
    } else if (call.name === 'houdini_exec' || (call.name === 'houdini_job_submit' && !job)
        || (['houdini_job_status','houdini_job_cancel'].includes(call.name) && ['failed','cancelled'].includes(value?.status ?? d.meta?.status))) {
      // Includes transport failures and historical runtimes without this schema.
      uncertain.push(event.seq ?? 0)
    }
  }
  const pendingCalls = [...calls].filter(([id, call]) => !seen.has(id) && ['houdini_exec','houdini_job_submit'].includes(call.name))
  const activeJobs = [...jobs].filter(([,status]) => !['done','failed','cancelled'].includes(status))
  if (!rows.length) return uncertain.length || activeJobs.length || pendingCalls.length
    ? {status:'execution_state_unknown', pending_calls:pendingCalls.length, active_jobs:activeJobs,
       reason:'No ordered Bridge observation; inspect current outputs and in-flight work before retrying mutations.'} : null
  // Foreground results identify an observed runtime. A late poll for an old job
  // must not resurrect a previous runtime's node identities.
  const foreground = rows.filter(r => ['houdini_exec','houdini_query'].includes(r.tool))
  const anchor = (foreground.length ? foreground : rows).reduce((a,b) =>
    a.e.observed_at > b.e.observed_at || (a.e.observed_at === b.e.observed_at && a.e.sequence > b.e.sequence) ? a : b)
  const runtimeRows = rows.filter(r => r.e.runtime_id === anchor.e.runtime_id)
  const all = runtimeRows.filter(r => r.e.hip_path === anchor.e.hip_path)
  const unique = new Map<number, any>()
  for (const row of all) if (!unique.has(row.e.sequence)) unique.set(row.e.sequence, row)
  const ordered = [...unique.values()].sort((a,b) => a.e.sequence-b.e.sequence)
  const current = ordered.slice(-128)
  const nodes = new Map<number, any>()
  const checks = new Map<string, any>()
  const failures: any[] = []
  const inFlight = activeJobs.length > 0 || pendingCalls.length > 0
  for (const row of current) {
    const {value, e, eventSeq, callId} = row
    const impact = e.impact || {}
    const changed = new Set((impact.nodes || []).map((n:any)=>n.identity))
    const mayHaveEdited = impact.attempted === true && value.transaction?.status !== 'no_scene_change'
    if (mayHaveEdited) for (const check of checks.values()) {
      if (impact.global || impact.truncated || impact.unavailable || check.identity === null || changed.has(check.identity)
          || check.verb.startsWith('render_')) {
        check.validity = 'stale_after_recorded_change'
        check.invalidated_by = callId
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
      const binding:any = byIndex.get(item.ledgerIndex)
      const identity = binding?.identity ?? null
      const checkStatus = item.ok === false || item.restored === false ? 'fail'
        : item.warning_free === false || item.healthy === false ? 'warning'
        : item.status ?? (item.ok === true ? 'observed_pass' : 'unverified')
      const rolledBack = value.transaction?.status === 'rolled_back' || value.transaction?.status === 'recovery_unverified'
      const supersededInCall = (impact.last_edit_ledger_index ?? 0) > item.ledgerIndex
      const unknownOrder = (value.rawUsage?.coveredMutations?.length || value.rawUsage?.suspectedMutations?.length) > 0
      const validity = rolledBack ? 'not_current_after_failed_transaction'
        : unknownOrder ? 'unverified_change_order_in_call'
        : supersededInCall ? 'stale_after_later_edit_in_same_call'
        : 'historical_observation_only'
      const key = `${item.verb}:${identity ?? binding?.path ?? item.output ?? item.node ?? item.ledgerIndex}`
      checks.delete(key)
      checks.set(key,{verb:item.verb,identity,output:binding?.path ?? item.output ?? item.node,
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
  return {status:'recorded_execution_facts',runtime_id:anchor.e.runtime_id,
    hip_path:anchor.e.hip_path ?? null,
    last_sequence:current.at(-1)?.e.sequence,last_observed_at:current.at(-1)?.e.observed_at,
    frame:current.at(-1)?.e.frame,
    nodes:[...nodes.values()].slice(-12),checks:[...checks.values()].slice(-8),
    recent_failures:failures.slice(-2),active_jobs:activeJobs,pending_calls:pendingCalls.length,
    coverage:{execution_records:current.length,older_records_omitted:ordered.length-current.length,
      other_runtime_records_excluded:rows.length-runtimeRows.length,
      other_hip_records_excluded:runtimeRows.length-all.length,nodes_omitted:Math.max(0,nodes.size-12),
      checks_omitted:Math.max(0,checks.size-8)},
    boundary:'Historical tool observations only, not current live state or permission. Native dependency hints exclude unobserved GUI edits, last-cook omissions and external/dynamic dependencies. Non-stale does not mean currently valid; recheck relevant state before relying on it.'}
}
