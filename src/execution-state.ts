/** Runtime facts only. Geometry checks and task judgments remain tool results. */
import { executionHistory, type SessionEvent } from './execution-history.js'

export function projectExecutionState(events:readonly SessionEvent[],history=executionHistory(events)):Record<string,any>|null {
  const {anchor,unresolvedCalls,pendingCalls,activeRequests,activeJobs,failedCalls} = history
  const toolFailure=failedCalls.at(-1)
  if (!anchor && !unresolvedCalls.length && !pendingCalls.length && !activeRequests.length && !activeJobs.length && !toolFailure) return null
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
  }
}

/** Carry only unresolved work and the latest failed observation into context. */
export function projectExecutionNotice(events:readonly SessionEvent[],history=executionHistory(events)):Record<string,unknown>|null {
  const state = projectExecutionState(events,history)
  if (!state || (!state.last_failure && !state.active_jobs.length && !state.pending_calls
      && !state.unresolved_requests.length && !state.unresolved_calls.length)) return null
  return {...state,boundary:'Recorded request and execution facts. Recover an unknown request by its original request_ref before repeating the operation. Current scene and result quality can be inspected with Houdini tools.'}
}
