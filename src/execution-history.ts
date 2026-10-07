/** Correlate native and nested calls, results and same-runtime receipts. */
import { executionCall,executionResult } from './dsh-adapter.js'
export type SessionEvent = {type:string;seq?:number;time?:number;data?:any;surfaceOp?:string|{op:string}}
export type ExecutionRow = {eventSeq:number;callId:string;tool:string;value:any;execution:any}

const LIVE_TOOLS = new Set(['houdini_exec','houdini_inspect','houdini_ui_list','houdini_ui_screenshot','houdini_request','houdini_job_submit','houdini_job_status','houdini_job_cancel'])
const RECOVERABLE_CALLS = new Set(['houdini_exec','houdini_ui_list','houdini_ui_screenshot','houdini_job_submit'])
const OBSERVED_REQUESTS = new Set(['done','not_executed','job_submitted'])
const UNAVAILABLE_RESULTS = new Set(['result_expired','result_unavailable'])
const TERMINAL_REQUESTS = new Set([...OBSERVED_REQUESTS,...UNAVAILABLE_RESULTS])
const TERMINAL_JOBS = new Set(['done','failed','cancelled'])

export function executionHistory(events:readonly SessionEvent[]) {
  const calls=new Map<string,any>(), results=new Map<string,any>()
  const rows:ExecutionRow[]=[], receipts=new Map<string,string>(), jobs=new Map<string,string>()
  const unavailableResults=new Map<string,{request_ref:string;owner_call:string|null;status:'finished_result_unavailable';retention_status:string;outcome:'unverified'}>()
  const resolvedCalls=new Set<string>()
  const uncertain:Array<{seq:number;callId:string;ref?:string}>=[]
  const failedCalls:Array<{seq:number;callId:string;tool:string;error:any}>=[]
  for (const event of events) {
    const call = executionCall(event)
    if (call) calls.set(call.callId,call)
    const outcome = executionResult(event)
    if (!outcome || results.has(outcome.callId)) continue
    const original = calls.get(outcome.callId)
    if (!original) continue
    const value=outcome.value, name=original.name
    results.set(outcome.callId,value)
    if (!LIVE_TOOLS.has(name)) continue
    if (outcome.isError) {
      failedCalls.push({seq:event.seq??0,callId:outcome.callId,tool:name,error:outcome.error??{code:'TOOL_FAILED'}})
      if (['ABORTED','TOOL_OUTCOME_UNKNOWN'].includes(outcome.error?.code) && RECOVERABLE_CALLS.has(name))
        uncertain.push({seq:event.seq??0,callId:outcome.callId})
    }
    if (!value) continue
    const receipt=value.requestReceipt
    if (typeof receipt?.request_ref==='string') {
      const prior=receipts.get(receipt.request_ref)||''
      if (!TERMINAL_REQUESTS.has(prior) || (!OBSERVED_REQUESTS.has(prior) && OBSERVED_REQUESTS.has(receipt.status)))
        receipts.set(receipt.request_ref,receipt.status)
      if (OBSERVED_REQUESTS.has(receipts.get(receipt.request_ref)||'')) unavailableResults.delete(receipt.request_ref)
      else if (UNAVAILABLE_RESULTS.has(receipt.status)) unavailableResults.set(receipt.request_ref,{
        request_ref:receipt.request_ref,owner_call:typeof receipt.owner_call==='string'?receipt.owner_call:null,
        status:'finished_result_unavailable',retention_status:receipt.status,outcome:'unverified',
      })
    }
    if (typeof receipt?.owner_call==='string' && TERMINAL_REQUESTS.has(receipt.status)) resolvedCalls.add(receipt.owner_call)
    const job=value.jobId??receipt?.jobId
    if (typeof job==='string') {
      const status=value.status??'queued_or_unknown'
      if (!TERMINAL_JOBS.has(jobs.get(job)||'') || TERMINAL_JOBS.has(status)) jobs.set(job,status)
    }
    const execution=value.execution
    if (execution && typeof execution.runtime_id==='string' && Number.isFinite(execution.sequence) && Number.isFinite(execution.observed_at))
      rows.push({eventSeq:event.seq??0,callId:outcome.callId,tool:name,value,execution})
    else if (receipt && !TERMINAL_REQUESTS.has(receipt.status))
      uncertain.push({seq:event.seq??0,callId:outcome.callId,ref:receipt.request_ref})
  }
  const unresolvedCalls=uncertain.filter(row=>!resolvedCalls.has(row.callId)&&(!row.ref||!TERMINAL_REQUESTS.has(receipts.get(row.ref)||'')))
  const pendingCalls=[...calls].filter(([id,call])=>!results.has(id)&&!resolvedCalls.has(id)&&RECOVERABLE_CALLS.has(call.name)).map(([id])=>id)
  const activeRequests=[...receipts].filter(([,status])=>!TERMINAL_REQUESTS.has(status))
  const activeJobs=[...jobs].filter(([,status])=>!TERMINAL_JOBS.has(status))
  const foreground=rows.filter(row=>['houdini_exec','houdini_inspect','houdini_ui_list','houdini_ui_screenshot'].includes(row.tool))
  const anchor=rows.reduce<ExecutionRow|undefined>((latest,row)=>!latest
    ||row.execution.observed_at>latest.execution.observed_at
    ||(row.execution.observed_at===latest.execution.observed_at&&row.execution.sequence>latest.execution.sequence)?row:latest,undefined)
  return {calls,results,rows,foreground,anchor,unresolvedCalls,pendingCalls,activeRequests,activeJobs,failedCalls,
    resolvedCalls,unavailableResults:[...unavailableResults.values()]}
}

export type ExecutionHistory = ReturnType<typeof executionHistory>
