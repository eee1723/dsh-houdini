/** Correlate native and nested calls, results and same-runtime receipts. */
import { executionCall,executionResult } from './dsh-adapter.js'
import {foldExecutorState} from './executor-identity-projection.js'
import {HOUDINI_SCENE_TOOLS} from './tool-catalog.js'
export type SessionEvent = {type:string;seq?:number;time?:number;data?:any;surfaceOp?:string|{op:string}}
export type ExecutionRow = {eventSeq:number;callId:string;tool:string;value:any;execution:any}

const LIVE_TOOLS = HOUDINI_SCENE_TOOLS
const RECOVERABLE_CALLS = new Set(['houdini_exec','houdini_ui_list','houdini_ui_screenshot','houdini_job_submit'])
const OBSERVED_REQUESTS = new Set(['done','not_executed','job_submitted'])
const UNAVAILABLE_RESULTS = new Set(['result_expired','result_unavailable'])
const TERMINAL_REQUESTS = new Set([...OBSERVED_REQUESTS,...UNAVAILABLE_RESULTS])
const COLLECTED_JOBS = new Set(['done','failed','cancelled'])
const TERMINAL_JOBS = new Set([...COLLECTED_JOBS,'finished_result_unavailable'])

/** Receipt transitions are shared by live context and historical trace views. */
export function mergeRequestStatus(previous:string|undefined, observed:string):string {
  return !TERMINAL_REQUESTS.has(previous??'') || (!OBSERVED_REQUESTS.has(previous??'') && OBSERVED_REQUESTS.has(observed))
    ? observed : previous!
}
export const isPendingRequestStatus=(status:string):boolean => !TERMINAL_REQUESTS.has(status)

export function requestStatusGuidance(status:unknown):string|undefined {
  if(status==='running')return 'The same-runtime Bridge confirms this request is still executing. This is not a crash report or a progress estimate. HTTP timeout did not cancel the work. Scene queries and UI discovery/capture share its main-thread queue and may wait behind it; use this original request_ref for status, without resubmitting. An empty shell process listing does not override this receipt.'
  if(status==='queued')return 'The same-runtime Bridge confirms this request is admitted and waiting for main-thread dispatch. It has not started. Scene queries and UI discovery/capture also use that queue; they are not independent liveness probes. Read this original request_ref again to observe a later state; do not resubmit.'
}

export type HistoricalExecutionOrigin={executorId?:string;runtimeId:string;sceneEpoch?:string}
function resultOrigin(value:any):HistoricalExecutionOrigin|undefined {
  const receipt=value?.requestReceipt,execution=value?.execution??receipt?.result?.execution
  const runtimeId=receipt?.runtime_id??execution?.runtime_id
  if(typeof runtimeId!=='string'||!/^[0-9a-f]{32}$/.test(runtimeId))return
  const executorId=receipt?.executor_id??execution?.executor_id
  const sceneEpoch=receipt?.scene_epoch??execution?.scene_epoch??execution?.scene_recovery?.scene_epoch
  return {runtimeId,...(typeof executorId==='string'?{executorId}:{}),...(typeof sceneEpoch==='string'?{sceneEpoch}:{})}
}
function resultJob(value:any):string|undefined {
  const receipt=value?.requestReceipt
  const id=value?.jobId??receipt?.jobId??receipt?.result?.jobId??receipt?.result?.result?.jobId
  return typeof id==='string'?id:undefined
}
/** Original routing facts come from canonical native/nested receipts, never current selection. */
export function recordedExecutionOrigin(events:readonly SessionEvent[],reference:{requestRef:string}|{jobId:string}):HistoricalExecutionOrigin {
  const requestedRuntime='requestRef' in reference?reference.requestRef.split('.')[0]:undefined
  const candidates=new Map<string,HistoricalExecutionOrigin>()
  for(const event of events) {
    const value=executionResult(event)?.value
    const matches='requestRef' in reference?value?.requestReceipt?.request_ref===reference.requestRef:resultJob(value)===reference.jobId
    if(!matches)continue
    const origin=resultOrigin(value)
    if(!origin)continue
    if(requestedRuntime&&requestedRuntime!==origin.runtimeId)throw new Error('原请求记录的运行身份不一致，没有查询其他工程。')
    if(origin.executorId&&!/^[0-9a-f]{32}$/.test(origin.executorId))throw new Error('原请求的执行端记录无效，没有查询其他工程。')
    const previous=candidates.get(origin.runtimeId)
    if(previous?.executorId&&origin.executorId&&previous.executorId!==origin.executorId)
      throw new Error('原请求记录含多个执行端，没有猜测目标。')
    candidates.set(origin.runtimeId,{...previous,...origin})
  }
  if(!candidates.size&&requestedRuntime&&/^[0-9a-f]{32}$/.test(requestedRuntime))
    candidates.set(requestedRuntime,{runtimeId:requestedRuntime})
  if(candidates.size!==1)throw new Error('无法从本对话唯一确定原任务的 Houdini，请使用原请求回执核对；没有向当前工程查询或重发操作。')
  return [...candidates.values()][0]
}

export function executionHistory(events:readonly SessionEvent[],options:{includeHistorical?:boolean}={}) {
  let recoverySeq=0,selected:ReturnType<typeof foldExecutorState>['selectedTarget']=null,selectionRecorded=false
  try {const state=foldExecutorState(events);recoverySeq=state.recoverySeq;selected=state.selectedTarget;selectionRecorded=state.selectionRecorded}
  catch { /* Invalid bindings retire no evidence; live admission reports the conflict. */ }
  // Status reads may omit the admitted scene epoch. Correlate their original
  // native/nested receipts before filtering, so loading another scene in the
  // same runtime cannot make an old request or job current work again.
  const requestOrigins=new Map<string,HistoricalExecutionOrigin>()
  const jobOrigins=new Map<string,HistoricalExecutionOrigin|null>()
  if(selectionRecorded&&!options.includeHistorical)for(const event of events) {
    const value=executionResult(event)?.value,id=resultJob(value),origin=resultOrigin(value)
    if(!origin)continue
    const ref=value?.requestReceipt?.request_ref
    if(typeof ref==='string')requestOrigins.set(ref,{...origin,...requestOrigins.get(ref)})
    if(!id)continue
    const previous=jobOrigins.get(id)
    jobOrigins.set(id,previous===null||previous&&previous.runtimeId!==origin.runtimeId?null:{...previous,...origin})
  }
  if(recoverySeq&&!options.includeHistorical) {
    let cutoff=recoverySeq
    // The very first scene choice can be answered inside the first live tool.
    // Keep that still-pending call, while later explicit target changes retire
    // their previous scope. This reads the same projection, not a second ledger.
    if(selected) {
      const prior=foldExecutorState(events.filter(event=>(event.seq??0)<recoverySeq))
      if(!prior.identity&&!prior.selectionRecorded) {
        for(const event of events) {
          const call=executionCall(event)
          if(call&&Object.hasOwn(prior.pending,call.callId)&&Number.isFinite(event.seq))cutoff=Math.min(cutoff,event.seq!-1)
        }
      }
    }
    events=events.filter(event=>(event.seq??0)>cutoff)
  }
  const calls=new Map<string,any>(), results=new Map<string,any>()
  const rows:ExecutionRow[]=[], receipts=new Map<string,string>(), jobs=new Map<string,string>()
  const unavailableResults=new Map<string,{request_ref:string;owner_call:string|null;status:'finished_result_unavailable';retention_status:string;outcome:'unverified';job_id?:string}>()
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
    if(selectionRecorded&&!options.includeHistorical&&value) {
      const job=resultJob(value),direct=resultOrigin(value),request=requestOrigins.get(value.requestReceipt?.request_ref)
      const origin=request?{...request,...direct}:direct??(job?jobOrigins.get(job):undefined)
      const foreign=origin&&(!selected||origin.runtimeId!==selected.runtime_id
        ||origin.executorId!==undefined&&origin.executorId!==selected.executor_id
        ||origin.sceneEpoch!==undefined&&origin.sceneEpoch!==selected.scene_epoch)
      // A wholly lost original result leaves no receipt epoch to correlate.
      // Only a named call retained in this selected scope can make that sparse
      // status current; a lookup of older/unknown work remains historical data.
      // Sparse job controls likewise update only a job already admitted here.
      if(foreign||job&&jobOrigins.get(job)===null&&!direct
        ||name==='houdini_request'&&!origin?.sceneEpoch&&!calls.has(value.requestReceipt?.owner_call)
        ||job&&['houdini_job_status','houdini_job_cancel'].includes(name)&&!origin?.sceneEpoch&&!jobs.has(job))continue
    }
    if (outcome.isError) {
      failedCalls.push({seq:event.seq??0,callId:outcome.callId,tool:name,error:outcome.error??{code:'TOOL_FAILED'}})
      if (['ABORTED','TOOL_OUTCOME_UNKNOWN'].includes(outcome.error?.code) && RECOVERABLE_CALLS.has(name))
        uncertain.push({seq:event.seq??0,callId:outcome.callId})
    }
    if (!value) continue
    const receipt=value.requestReceipt
    const job=value.jobId??receipt?.jobId
    const missingJobResult=typeof job==='string' && receipt?.job_finished===true && receipt?.job_result_available===false
    if (typeof receipt?.request_ref==='string') {
      receipts.set(receipt.request_ref,mergeRequestStatus(receipts.get(receipt.request_ref),receipt.status))
      if (missingJobResult && !COLLECTED_JOBS.has(jobs.get(job)||'')) unavailableResults.set(receipt.request_ref,{
        request_ref:receipt.request_ref,owner_call:typeof receipt.owner_call==='string'?receipt.owner_call:null,
        status:'finished_result_unavailable',retention_status:receipt.status,outcome:'unverified',job_id:job,
      })
      else if (OBSERVED_REQUESTS.has(receipts.get(receipt.request_ref)||'')
        && (!unavailableResults.get(receipt.request_ref)?.job_id || COLLECTED_JOBS.has(jobs.get(job)||''))) unavailableResults.delete(receipt.request_ref)
      else if (UNAVAILABLE_RESULTS.has(receipt.status) && typeof job!=='string') unavailableResults.set(receipt.request_ref,{
        request_ref:receipt.request_ref,owner_call:typeof receipt.owner_call==='string'?receipt.owner_call:null,
        status:'finished_result_unavailable',retention_status:receipt.status,outcome:'unverified',
      })
    }
    if (typeof receipt?.owner_call==='string' && TERMINAL_REQUESTS.has(receipt.status)) resolvedCalls.add(receipt.owner_call)
    if (typeof job==='string') {
      const status=value.status??(missingJobResult?'finished_result_unavailable'
        : COLLECTED_JOBS.has(receipt?.job_status)?'finished_result_uncollected':receipt?.job_status??'queued_or_unknown')
      const previous=jobs.get(job)||''
      if (!COLLECTED_JOBS.has(previous)
        && (previous!=='finished_result_uncollected' || TERMINAL_JOBS.has(status))
        && (!TERMINAL_JOBS.has(previous) || TERMINAL_JOBS.has(status))) jobs.set(job,status)
      if (COLLECTED_JOBS.has(status)) for (const [ref,entry] of unavailableResults)
        if (entry.job_id===job) unavailableResults.delete(ref)
    }
    const execution=value.execution
    if (execution && typeof execution.runtime_id==='string' && Number.isFinite(execution.sequence) && Number.isFinite(execution.observed_at))
      rows.push({eventSeq:event.seq??0,callId:outcome.callId,tool:name,value,execution})
    else if (receipt && name!=='houdini_request' && !TERMINAL_REQUESTS.has(receipt.status))
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
