/** Correlate tool calls, results and receipts once for each session snapshot.
 * Consumers derive attention, delivery and requirement views from these facts.
 */
export type SessionEvent = {type:string;seq?:number;time?:number;data?:any;surfaceOp?:string|{op:string}}
export type ExecutionRow = {eventSeq:number;callId:string;tool:string;value:any;execution:any}

const LIVE_TOOLS = new Set(['houdini_exec','houdini_query','houdini_job_submit','houdini_job_status','houdini_job_cancel'])
const TERMINAL_REQUESTS = new Set(['done','not_executed','job_submitted'])
const TERMINAL_JOBS = new Set(['done','failed','cancelled'])

export function executionHistory(events:readonly SessionEvent[]) {
  const calls=new Map<string,any>(), results=new Map<string,any>()
  const rows:ExecutionRow[]=[], receipts=new Map<string,string>(), jobs=new Map<string,string>()
  const resolvedCalls=new Set<string>()
  const uncertain:Array<{seq:number;callId:string;ref?:string}>=[]
  for(const event of events) {
    const data=event.data
    if(event.type==='tool/call') calls.set(data?.callId,data)
    if(event.type!=='tool/result') continue
    const id=data?.message?.source?.callId, call=calls.get(id)
    if(!call||results.has(id)) continue
    const value=data?.meta?.canonical
    results.set(id,value)
    if(!LIVE_TOOLS.has(call.name)) continue
    const receipt=value?.requestReceipt
    if(typeof receipt?.request_ref==='string'&&!TERMINAL_REQUESTS.has(receipts.get(receipt.request_ref)||''))
      receipts.set(receipt.request_ref,receipt.status)
    if(typeof receipt?.owner_call==='string'&&TERMINAL_REQUESTS.has(receipt.status)) resolvedCalls.add(receipt.owner_call)
    const job=value?.jobId??receipt?.jobId??data?.meta?.jobId
    if(typeof job==='string') {
      const status=value?.status??data?.meta?.status??'queued_or_unknown'
      if(!TERMINAL_JOBS.has(jobs.get(job)||'')||TERMINAL_JOBS.has(status)) jobs.set(job,status)
    }
    const execution=value?.execution
    if(execution&&typeof execution.runtime_id==='string'&&Number.isFinite(execution.sequence)&&Number.isFinite(execution.observed_at))
      rows.push({eventSeq:event.seq??0,callId:id,tool:call.name,value,execution})
    else if(call.name==='houdini_exec'||(call.name==='houdini_job_submit'&&!job)
      ||(['houdini_job_status','houdini_job_cancel'].includes(call.name)&&['failed','cancelled'].includes(value?.status??data?.meta?.status)))
      uncertain.push({seq:event.seq??0,callId:id,ref:receipt?.request_ref})
  }
  const unresolvedCalls=uncertain.filter(row=>!resolvedCalls.has(row.callId)&&(!row.ref||!TERMINAL_REQUESTS.has(receipts.get(row.ref)||'')))
  const pendingCalls=[...calls].filter(([id,call])=>!results.has(id)&&!resolvedCalls.has(id)&&['houdini_exec','houdini_job_submit'].includes(call.name)).map(([id])=>id)
  const activeRequests=[...receipts].filter(([,status])=>!TERMINAL_REQUESTS.has(status))
  const activeJobs=[...jobs].filter(([,status])=>!TERMINAL_JOBS.has(status))
  const foreground=rows.filter(row=>['houdini_exec','houdini_query'].includes(row.tool))
  const candidates=foreground.length?foreground:rows
  const anchor=candidates.reduce<ExecutionRow|undefined>((latest,row)=>!latest
    ||row.execution.observed_at>latest.execution.observed_at
    ||(row.execution.observed_at===latest.execution.observed_at&&row.execution.sequence>latest.execution.sequence)?row:latest,undefined)
  return {calls,results,rows,foreground,anchor,unresolvedCalls,pendingCalls,activeRequests,activeJobs}
}

export type ExecutionHistory = ReturnType<typeof executionHistory>
