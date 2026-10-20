/** Offline history inspection; live consumers read the registered DSH projection. */
import {executorIdentityProjection,transitionExecutorState} from './executor-identity-projection.js'
import {executionCall,executionResult} from './dsh-adapter.js'
import {executionOutstanding,initExecutionScope,transitionExecutionScope,resultOrigin,resultJob,type ScopeDelta,type ExecutionScope,type HistoricalExecutionOrigin} from './execution-facts.js'
export {mergeRequestStatus,isPendingRequestStatus} from './execution-facts.js'
export type {HistoricalExecutionOrigin} from './execution-facts.js'
export type SessionEvent = {type:string;seq?:number;time?:number;data?:any;surfaceOp?:string|{op:string}}
export type ExecutionRow = {eventSeq:number;callId:string;tool:string;value:any;execution:any;producer?:'live-job'}

export function requestStatusGuidance(status:unknown):string|undefined {
  if(status==='running')return 'The same-runtime Bridge confirms this request is still executing. This is not a crash report or a progress estimate. HTTP timeout did not cancel the work. Scene queries and UI discovery/capture share its main-thread queue and may wait behind it; use this original request_ref for status, without resubmitting. An empty shell process listing does not override this receipt.'
  if(status==='queued')return 'The same-runtime Bridge confirms this request is admitted and waiting for main-thread dispatch. It has not started. Scene queries and UI discovery/capture also use that queue; they are not independent liveness probes. Read this original request_ref again to observe a later state; do not resubmit.'
}

/** Only this explicit cold lookup indexes old short job IDs. Live request
 * lookup routes by the runtime already encoded in its request reference. */
export function recordedExecutionOrigin(events:readonly SessionEvent[],reference:{requestRef:string}|{jobId:string}):HistoricalExecutionOrigin {
  const requested='requestRef' in reference?reference.requestRef.split('.')[0]:undefined,candidates=new Map<string,HistoricalExecutionOrigin>()
  for(const event of events) {
    const value=executionResult(event)?.value
    if('requestRef' in reference?value?.requestReceipt?.request_ref!==reference.requestRef:resultJob(value)!==reference.jobId)continue
    const origin=resultOrigin(value)
    if(!origin)continue
    if(requested&&requested!==origin.runtimeId)throw new Error('原请求记录的运行身份不一致，没有查询其他工程。')
    if(origin.executorId&&!/^[0-9a-f]{32}$/.test(origin.executorId))throw new Error('原请求的执行端记录无效，没有查询其他工程。')
    const previous=candidates.get(origin.runtimeId)
    if(previous?.executorId&&origin.executorId&&previous.executorId!==origin.executorId)throw new Error('原请求记录含多个执行端，没有猜测目标。')
    if(previous?.sceneEpoch&&origin.sceneEpoch&&previous.sceneEpoch!==origin.sceneEpoch)throw new Error('原请求记录含多个场景代际，没有猜测目标。')
    candidates.set(origin.runtimeId,{...previous,...origin})
  }
  if(!candidates.size&&requested&&/^[0-9a-f]{32}$/.test(requested))candidates.set(requested,{runtimeId:requested})
  if(candidates.size!==1)throw new Error('无法从本对话唯一确定原任务的 Houdini，请使用原请求回执核对；没有向当前工程查询或重发操作。')
  return [...candidates.values()][0]
}
function collector() {
  return {calls:new Map<string,any>(),callSeq:new Map<string,number>(),results:new Map<string,any>(),rows:[] as ExecutionRow[],
    failedCalls:[] as Array<{seq:number;callId:string;tool:string;error:any}>,resolvedCalls:new Set<string>(),
    requestStatuses:new Map<string,string>(),jobStatuses:new Map<string,string>()}
}
function collect(target:ReturnType<typeof collector>,event:SessionEvent,delta:ScopeDelta|undefined) {
  const call=executionCall(event)
  if(call){target.calls.set(call.callId,call);target.callSeq.set(call.callId,event.seq??0)}
  const result=executionResult(event)
  if(result&&target.calls.has(result.callId)&&!target.results.has(result.callId))target.results.set(result.callId,result.value)
  if(!delta)return
  if(delta.row)target.rows.push({...delta.row,value:result?.value})
  if(delta.failure)target.failedCalls.push(delta.failure)
  if(delta.resolved)target.resolvedCalls.add(delta.resolved)
  if(delta.request)target.requestStatuses.set(...delta.request)
  if(delta.job)target.jobStatuses.set(...delta.job)
}
/** One shot Maps collect originals; all status and scene-scope decisions still
 * come from the exact pure transition used by DSH's live projection. */
export function executionHistory(events:readonly SessionEvent[],options:{includeHistorical?:boolean}={}) {
  let state=executorIdentityProjection.init(),current=collector(),full=collector(),historical=initExecutionScope()
  for(const event of events) {
    const transition=transitionExecutorState(state,event)
    state=transition.state
    if(transition.reset) {
      const retained=collector(),seqs=transition.reset.adopted.map(id=>current.callSeq.get(id)).filter((seq):seq is number=>seq!==undefined)
      const cutoff=seqs.length?Math.min(...seqs):Infinity
      for(const [id,call] of current.calls)if((current.callSeq.get(id)??-Infinity)>=cutoff) {
        retained.calls.set(id,call);retained.callSeq.set(id,current.callSeq.get(id)!)
        if(current.results.has(id))retained.results.set(id,current.results.get(id))
      }
      current=retained
    }
    const all=transitionExecutionScope(historical,event,state.execution,undefined,full)
    historical=all.scope
    collect(full,event,all.delta);collect(current,event,transition.delta)
  }
  // An unfenced legacy trace has no recorded current-scene boundary. Its cold
  // reader must retain standalone receipts whose admission body was lost;
  // explicit selections and recovery boundaries still use the scoped facts.
  const useAll=options.includeHistorical||state.invalid||state.conflict||!state.selectionRecorded&&!state.recoverySeq
  const target=useAll?full:current,scope=useAll?historical:state.execution.current
  const summary=executionOutstanding(scope),withOriginal=(row:ExecutionRow|undefined)=>row?{...row,value:target.results.get(row.callId)}:undefined
  return {...summary,calls:target.calls,results:target.results,rows:target.rows,
    foreground:target.rows.filter(row=>['houdini_exec','houdini_inspect','houdini_ui_list','houdini_ui_screenshot'].includes(row.tool)),
    anchor:withOriginal(scope.anchor),saveAs:withOriginal(scope.saveAs),failedCalls:target.failedCalls,resolvedCalls:target.resolvedCalls}
}
export type ExecutionHistory=ReturnType<typeof executionHistory>
