/** Runtime facts only. Geometry checks and task judgments remain tool results. */
import { executionHistory, type SessionEvent } from './execution-history.js'

export function projectExecutionState(events:readonly SessionEvent[],history=executionHistory(events)):Record<string,any>|null {
  const {anchor,unresolvedCalls,pendingCalls,activeRequests,activeJobs,failedCalls,resolvedCalls,unavailableResults} = history
  const toolFailure=failedCalls.filter(row=>!resolvedCalls.has(row.callId)).at(-1)
  if (!anchor && !unresolvedCalls.length && !pendingCalls.length && !activeRequests.length && !activeJobs.length && !toolFailure && !unavailableResults.length) return null
  const last = anchor?.execution
  const failure = toolFailure && toolFailure.seq > (anchor?.eventSeq??-1)
    ? {call_id:toolFailure.callId,tool:toolFailure.tool,error:toolFailure.error}
    : anchor?.value.ok === false ? {
    call_id:anchor.callId, error:anchor.value.error ?? 'execution failed',
    transaction:anchor.value.transaction?.status ?? null,
  } : null
  return {
    status:last ? 'recorded_execution_facts' : 'execution_state_unknown',
    runtime_id:last?.runtime_id ?? null,hip_path:last?.hip_path ?? null,
    last_sequence:last?.sequence ?? null,last_observed_at:last?.observed_at ?? null,
    last_failure:failure,active_jobs:activeJobs,pending_calls:pendingCalls.length,
    unresolved_requests:activeRequests,unresolved_calls:unresolvedCalls.map(row => row.callId),
    unavailable_results:unavailableResults,
  }
}

/** Carry only work that still needs recovery/collection into dynamic context.
 * A settled synchronous failure is already in its tool result. Repeating it
 * here makes DSH append an entire context snapshot after both failure and repair.
 * Keep this projection stable across unrelated observations, including their
 * changing execution sequence, paths and timestamps. */
export function projectExecutionNotice(events:readonly SessionEvent[],history=executionHistory(events)):Record<string,unknown>|null {
  const {activeJobs,pendingCalls,activeRequests,unresolvedCalls,unavailableResults}=history
  if (!activeJobs.length && !pendingCalls.length && !activeRequests.length
      && !unresolvedCalls.length && !unavailableResults.length) return null
  return {
    active_jobs:activeJobs,pending_calls:pendingCalls.length,
    unresolved_requests:activeRequests,unresolved_calls:unresolvedCalls.map(row=>row.callId),
    unavailable_results:unavailableResults,
    boundary:'Recorded outstanding work, not current scene state. Recover uncertain operations with houdini_request using the original request_ref (or its index when the reference is missing) before repeating them. Collect active jobs with houdini_job_status. A finished_result_unavailable receipt confirms completion but not the outcome; inspect the scene rather than polling the expired result or repeating the operation.',
  }
}
