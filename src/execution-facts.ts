/** Incremental execution facts owned by DSH's session projection.
 * Complete results stay in DSH's log. Pure transitions return a small delta so
 * offline readers can collect original rows in their own one-shot Maps. */
import {executionCall,executionResult} from './dsh-adapter.js'
import {HOUDINI_SCENE_TOOLS} from './tool-catalog.js'
import type {SessionEvent,ExecutionRow} from './execution-history.js'
import {z} from 'zod'
const RECOVERABLE=new Set(['houdini_exec','houdini_ui_list','houdini_ui_screenshot','houdini_job_submit'])
const OBSERVED=new Set(['done','not_executed','job_submitted'])
const UNAVAILABLE=new Set(['result_expired','result_unavailable'])
const TERMINAL_REQUESTS=new Set([...OBSERVED,...UNAVAILABLE])
const COLLECTED=new Set(['done','failed','cancelled'])
const TERMINAL_JOBS=new Set([...COLLECTED,'finished_result_unavailable'])
const LIVE_TOOLS=new Set([...HOUDINI_SCENE_TOOLS,'houdini_job_status','houdini_job_cancel'])
export type HistoricalExecutionOrigin={executorId?:string;runtimeId:string;sceneEpoch?:string}
type OriginIndex={origins:Record<string,HistoricalExecutionOrigin>;error?:string;jobId?:string}
type Unavailable={request_ref:string;owner_call:string|null;status:'finished_result_unavailable';retention_status:string;outcome:'unverified';job_id?:string}
type Uncertain={seq:number;callId:string;ref?:string}
type Failure={seq:number;callId:string;tool:string;error:any}
type Call={callId:string;name:string;returned?:boolean}
export type ExecutionScope={calls:Record<string,Call>;pending:Record<string,true>;uncertain:Record<string,Uncertain>;
  failures:Record<string,Failure>;activeRequests:Record<string,string>;activeJobs:Record<string,string>;
  unavailable:Record<string,Unavailable>;anchor?:ExecutionRow;saveAs?:ExecutionRow}
export type ExecutionFacts={current:ExecutionScope;requestOrigins:Record<string,OriginIndex>;jobOrigins:Record<string,OriginIndex>;
  checkpoints:Record<string,Record<string,ExecutionRow>>;inFlight:Record<string,string>}
export type ScopeDelta={callId:string;eventSeq:number;tool:string;row?:ExecutionRow;failure?:Failure;resolved?:string;
  request?:[string,string];job?:[string,string]}
/** Offline-only read faces; no complete history is stored in projection state. */
export type ScopeHistory={calls:ReadonlyMap<string,Call>;results:ReadonlyMap<string,unknown>;
  requestStatuses:ReadonlyMap<string,string>;jobStatuses:ReadonlyMap<string,string>}
const Row=z.object({eventSeq:z.number(),callId:z.string(),tool:z.string(),value:z.any(),execution:z.any(),producer:z.literal('live-job').optional()})
const FailureSchema=z.object({seq:z.number(),callId:z.string(),tool:z.string(),error:z.any()})
const Origin=z.object({runtimeId:z.string(),executorId:z.string().optional(),sceneEpoch:z.string().optional()})
const Index=z.object({origins:z.record(z.string(),Origin),error:z.string().optional(),jobId:z.string().optional()})
const Statuses=z.record(z.string(),z.string())
const Scope=z.object({calls:z.record(z.string(),z.object({callId:z.string(),name:z.string(),returned:z.boolean().optional()})),
  pending:z.record(z.string(),z.literal(true)),uncertain:z.record(z.string(),z.object({seq:z.number(),callId:z.string(),ref:z.string().optional()})),
  failures:z.record(z.string(),FailureSchema),activeRequests:Statuses,activeJobs:Statuses,
  unavailable:z.record(z.string(),z.object({request_ref:z.string(),owner_call:z.string().nullable(),status:z.literal('finished_result_unavailable'),
    retention_status:z.string(),outcome:z.literal('unverified'),job_id:z.string().optional()})),anchor:Row.optional(),saveAs:Row.optional()})
export const executionFactsSchema:z.ZodType<ExecutionFacts>=z.object({current:Scope,requestOrigins:z.record(z.string(),Index),
  jobOrigins:z.record(z.string(),Index),checkpoints:z.record(z.string(),z.record(z.string(),Row)),inFlight:Statuses})
type Identity={identity:string|null;selectionRecorded:boolean;selectionRevision:number;recoverySeq:number;
  selectedTarget:{executor_id:string;runtime_id:string;scene_epoch:string;scene_id:string|null}|null}
const has=(record:object,key:string):boolean=>typeof key==='string'&&Object.hasOwn(record,key)
const own=<T>(record:Record<string,T>,key:string):T|undefined=>has(record,key)?record[key]:undefined
const put=<T>(record:Record<string,T>,key:string,value:T)=>({...record,[key]:value})
const without=<T>(record:Record<string,T>,key:string)=>{const next={...record};delete next[key];return next}
export const mergeRequestStatus=(previous:string|undefined,observed:string):string=>
  !TERMINAL_REQUESTS.has(previous??'')||!OBSERVED.has(previous??'')&&OBSERVED.has(observed)?observed:previous!
export const isPendingRequestStatus=(status:string)=>!TERMINAL_REQUESTS.has(status)
export function requestExecutionOrigin(ref:string):{runtimeId:string} {
  if(!/^[0-9a-f]{32}\.[0-9a-f]{32}$/.test(ref))throw new Error('原请求的运行身份无效，没有查询其他工程。')
  return {runtimeId:ref.split('.')[0]}
}
export const initExecutionScope=():ExecutionScope=>({calls:{},pending:{},uncertain:{},failures:{},activeRequests:{},activeJobs:{},unavailable:{}})
export function initExecutionFacts():ExecutionFacts {
  return {current:initExecutionScope(),requestOrigins:{},jobOrigins:{},checkpoints:{},inFlight:{}}
}
export function resultOrigin(value:any):HistoricalExecutionOrigin|undefined {
  const receipt=value?.requestReceipt,execution=value?.execution??receipt?.result?.execution
  const runtimeId=receipt?.runtime_id??execution?.runtime_id
  if(typeof runtimeId!=='string'||!/^[0-9a-f]{32}$/.test(runtimeId))return
  const executorId=receipt?.executor_id??execution?.executor_id,sceneEpoch=receipt?.scene_epoch??execution?.scene_epoch??execution?.scene_recovery?.scene_epoch
  return {runtimeId,...(typeof executorId==='string'?{executorId}:{}),...(typeof sceneEpoch==='string'?{sceneEpoch}:{})}
}
export function resultJob(value:any):string|undefined {
  const receipt=value?.requestReceipt,id=value?.jobId??receipt?.jobId??receipt?.result?.jobId??receipt?.result?.result?.jobId
  return typeof id==='string'?id:undefined
}
function addOrigin(index:OriginIndex|undefined,origin:HistoricalExecutionOrigin):OriginIndex {
  const previous=index&&own(index.origins,origin.runtimeId)
  const error=index?.error??(origin.executorId&&!/^[0-9a-f]{32}$/.test(origin.executorId)?'原请求的执行端记录无效，没有查询其他工程。'
    :previous?.executorId&&origin.executorId&&previous.executorId!==origin.executorId?'原请求记录含多个执行端，没有猜测目标。'
    :previous?.sceneEpoch&&origin.sceneEpoch&&previous.sceneEpoch!==origin.sceneEpoch?'原请求记录含多个场景代际，没有猜测目标。':undefined)
  return {origins:put(index?.origins??{},origin.runtimeId,{...previous,...origin}),...(error?{error}:{})}
}
function unique(index:OriginIndex|undefined):HistoricalExecutionOrigin|undefined {
  if(!index||index.error)return
  const values=Object.values(index.origins);return values.length===1?values[0]:undefined
}
const newer=(row:ExecutionRow,last:ExecutionRow|undefined)=>!last||row.execution.observed_at>last.execution.observed_at
  ||row.execution.observed_at===last.execution.observed_at&&row.execution.sequence>last.execution.sequence
function rowFor(event:SessionEvent,callId:string,tool:string,value:any,producer?:'live-job'):ExecutionRow|undefined {
  const execution=value?.execution
  if(!execution||typeof execution.runtime_id!=='string'||!Number.isFinite(execution.sequence)||!Number.isFinite(execution.observed_at))return
  const receipt=value.requestReceipt
  const actualJob=producer==='live-job'||typeof value.jobId==='string'&&value.jobId===receipt?.jobId
    &&COLLECTED.has(value.status)&&receipt.job_finished===true&&receipt.job_result_available===true
  return {eventSeq:event.seq??0,callId,tool,execution,value:{ok:value.ok,error:value.error,transaction:value.transaction},
    ...(actualJob?{producer:'live-job' as const}:{})}
}
/** One semantic transition, shared by live projection and offline collection. */
export function transitionExecutionScope(previous:ExecutionScope,event:SessionEvent,facts:ExecutionFacts,identity?:Identity,history?:ScopeHistory):{scope:ExecutionScope;delta?:ScopeDelta} {
  const call=executionCall(event)
  if(call&&(history||LIVE_TOOLS.has(call.name)||call.name==='job_output'))return {scope:{...previous,
    calls:put(previous.calls,call.callId,{callId:call.callId,name:call.name}),...(RECOVERABLE.has(call.name)?{pending:put(previous.pending,call.callId,true)}:{})}}
  const outcome=executionResult(event)
  if(!outcome||history?.results.has(outcome.callId))return {scope:previous}
  const original=own(previous.calls,outcome.callId)??history?.calls.get(outcome.callId)
  if(!original||original.returned&&!history)return {scope:previous}
  const finish=(state:ExecutionScope,delta?:ScopeDelta)=>{
    const calls=put(state.calls,outcome.callId,{...original,returned:true})
    const retained=Object.fromEntries(Object.entries(calls).filter(([id,row])=>!row.returned||has(state.uncertain,id)))
    const failure=Object.values(state.failures).at(-1)
    return {scope:{...state,calls:retained,failures:failure?{[failure.callId]:failure}:{}},...(delta?{delta}:{})}
  }
  let state={...previous,pending:without(previous.pending,outcome.callId)}
  const value=outcome.value,name=outcome.tool??original.name
  if(!LIVE_TOOLS.has(name))return finish(state)
  if(identity?.selectionRecorded&&value) {
    const job=resultJob(value),direct=resultOrigin(value),requestIndex=own(facts.requestOrigins,value.requestReceipt?.request_ref),request=unique(requestIndex)
    const jobIndex=job?own(facts.jobOrigins,job):undefined,origin=request?{...request,...direct}:direct??unique(jobIndex),selected=identity.selectedTarget
    const foreign=origin&&(!selected||origin.runtimeId!==selected.runtime_id||origin.executorId!==undefined&&origin.executorId!==selected.executor_id
      ||origin.sceneEpoch!==undefined&&origin.sceneEpoch!==selected.scene_epoch)
    if(foreign||requestIndex?.error||jobIndex?.error||jobIndex&&!unique(jobIndex)&&!direct
      ||name==='houdini_request'&&!origin?.sceneEpoch&&!has(state.calls,value.requestReceipt?.owner_call)&&!history?.calls.has(value.requestReceipt?.owner_call)
      ||job&&['houdini_job_status','houdini_job_cancel'].includes(name)&&!origin?.sceneEpoch&&!has(state.activeJobs,job))return finish(state)
  }
  const delta:ScopeDelta={callId:outcome.callId,eventSeq:event.seq??0,tool:name}
  if(outcome.isError) {
    delta.failure={seq:event.seq??0,callId:outcome.callId,tool:name,error:outcome.error??{code:'TOOL_FAILED'}}
    state.failures=put(state.failures,outcome.callId,delta.failure)
    if(['ABORTED','TOOL_OUTCOME_UNKNOWN'].includes(outcome.error?.code)&&RECOVERABLE.has(name))
      state.uncertain=put(state.uncertain,outcome.callId,{seq:event.seq??0,callId:outcome.callId})
  }
  if(!value)return finish(state,delta)
  const receipt=value.requestReceipt,job=resultJob(value),collecting=['houdini_request','houdini_job_status','houdini_job_cancel'].includes(name)
  const known=has(previous.activeRequests,receipt?.request_ref)||has(previous.unavailable,receipt?.request_ref)
    ||typeof receipt?.owner_call==='string'&&has(previous.calls,receipt.owner_call)
    ||typeof job==='string'&&(has(previous.activeJobs,job)||Object.values(previous.unavailable).some(row=>row.job_id===job))
  const collectStatus=Boolean(history)||!collecting||known
  const missing=typeof job==='string'&&receipt?.job_finished===true&&receipt?.job_result_available===false
  if(collectStatus&&typeof receipt?.request_ref==='string') {
    const ref=receipt.request_ref,status=mergeRequestStatus(history?.requestStatuses.get(ref)??own(state.activeRequests,ref)??own(state.unavailable,ref)?.retention_status,receipt.status)
    delta.request=[ref,status]
    state.activeRequests=TERMINAL_REQUESTS.has(status)?without(state.activeRequests,ref):put(state.activeRequests,ref,status)
    const previousJob=history?.jobStatuses.get(job!)??own(state.activeJobs,job!)
    if(missing&&!COLLECTED.has(previousJob??''))state.unavailable=put(state.unavailable,ref,{
      request_ref:ref,owner_call:typeof receipt.owner_call==='string'?receipt.owner_call:null,status:'finished_result_unavailable',retention_status:receipt.status,outcome:'unverified',job_id:job})
    else if(OBSERVED.has(status)&&(!own(state.unavailable,ref)?.job_id||COLLECTED.has(previousJob??'')))state.unavailable=without(state.unavailable,ref)
    else if(UNAVAILABLE.has(receipt.status)&&typeof job!=='string')state.unavailable=put(state.unavailable,ref,{
      request_ref:ref,owner_call:typeof receipt.owner_call==='string'?receipt.owner_call:null,status:'finished_result_unavailable',retention_status:receipt.status,outcome:'unverified'})
    if(TERMINAL_REQUESTS.has(status))for(const [id,uncertain] of Object.entries(state.uncertain))if(uncertain.ref===ref)state.uncertain=without(state.uncertain,id)
  }
  if(collectStatus&&typeof receipt?.owner_call==='string'&&TERMINAL_REQUESTS.has(receipt.status)) {
    const owner=receipt.owner_call;delta.resolved=owner
    state.pending=without(state.pending,owner);state.uncertain=without(state.uncertain,owner);state.failures=without(state.failures,owner)
    // Recovery can settle a lost original result. That original call must
    // stop counting as active even though its own tool/result never arrived.
    state.calls=without(state.calls,owner)
  }
  if(collectStatus&&typeof job==='string') {
    const observed=value.status??(missing?'finished_result_unavailable':COLLECTED.has(receipt?.job_status)?'finished_result_uncollected':receipt?.job_status??'queued_or_unknown')
    const previousStatus=history?.jobStatuses.get(job)??own(state.activeJobs,job)??(Object.values(state.unavailable).some(row=>row.job_id===job)?'finished_result_unavailable':'')
    const status=!COLLECTED.has(previousStatus)&&(previousStatus!=='finished_result_uncollected'||TERMINAL_JOBS.has(observed))
      &&(!TERMINAL_JOBS.has(previousStatus)||TERMINAL_JOBS.has(observed))?observed:previousStatus
    delta.job=[job,status]
    state.activeJobs=TERMINAL_JOBS.has(status)?without(state.activeJobs,job):put(state.activeJobs,job,status)
    if(COLLECTED.has(observed))for(const [ref,entry] of Object.entries(state.unavailable))if(entry.job_id===job)state.unavailable=without(state.unavailable,ref)
  }
  const row=rowFor(event,outcome.callId,name,value,outcome.producer)
  if(row) {
    delta.row=row
    if(newer(row,state.anchor))state.anchor=row
    if(Array.isArray(value.verbs)&&value.verbs.some((verb:any)=>verb?.verb==='scene_save_as'&&verb.ok===true))state.saveAs=row
  } else if(receipt&&name!=='houdini_request'&&!TERMINAL_REQUESTS.has(receipt.status))
    state.uncertain=put(state.uncertain,outcome.callId,{seq:event.seq??0,callId:outcome.callId,ref:receipt.request_ref})
  return finish(state,delta)
}
export function transitionExecutionFacts(previous:ExecutionFacts,event:SessionEvent,before:Identity,after:Identity):{facts:ExecutionFacts;delta?:ScopeDelta;reset?:{adopted:string[]}} {
  let facts=previous,reset:{adopted:string[]}|undefined
  const issued=executionCall(event)
  if(issued&&LIVE_TOOLS.has(issued.name))facts={...facts,inFlight:put(facts.inFlight,issued.callId,issued.name)}
  if(before.selectionRevision!==after.selectionRevision||before.recoverySeq!==after.recoverySeq) {
    const current=initExecutionScope(),adopted:string[]=[]
    if(after.selectedTarget&&!before.identity&&!before.selectionRecorded)for(const [id,call] of Object.entries(previous.current.calls))if(!call.returned) {
      current.calls=put(current.calls,id,call);adopted.push(id)
      if(has(previous.current.pending,id))current.pending[id]=true
    }
    facts={...facts,current,requestOrigins:{},jobOrigins:{}};reset={adopted}
  }
  const outcome=executionResult(event),value=outcome?.value,origin=resultOrigin(value),job=resultJob(value),ref=value?.requestReceipt?.request_ref
  if(origin) {
    if(typeof ref==='string')facts={...facts,requestOrigins:put(facts.requestOrigins,ref,{...addOrigin(own(facts.requestOrigins,ref),origin),...(job?{jobId:job}:{})})}
    if(job)facts={...facts,jobOrigins:put(facts.jobOrigins,job,addOrigin(own(facts.jobOrigins,job),origin))}
  }
  const transition=transitionExecutionScope(facts.current,event,facts,after)
  if(transition.scope!==facts.current)facts={...facts,current:transition.scope}
  const execution=value?.execution,saved=execution?.scene_recovery,tool=outcome&&(outcome.tool??own(facts.inFlight,outcome.callId))
  const row=outcome&&tool&&rowFor(event,outcome.callId,tool,value,outcome.producer)
  if(row&&(tool!=='houdini_request'||row.producer==='live-job')&&typeof execution.owner_session==='string'&&typeof saved?.scene_id==='string'&&typeof saved.checkpoint_id==='string') {
    const entries=own(facts.checkpoints,saved.scene_id)??{},key=[execution.executor_id,saved.scene_epoch,execution.owner_session].join(':')
    if(newer(row,own(entries,key)))facts={...facts,checkpoints:put(facts.checkpoints,saved.scene_id,put(entries,key,row))}
  }
  if(outcome) {
    const scope=facts.current
    facts={...facts,inFlight:without(facts.inFlight,outcome.callId),
      requestOrigins:Object.fromEntries(Object.entries(facts.requestOrigins).filter(([ref,index])=>has(scope.activeRequests,ref)||has(scope.unavailable,ref)||Boolean(index.jobId&&has(scope.activeJobs,index.jobId)))),
      jobOrigins:Object.fromEntries(Object.entries(facts.jobOrigins).filter(([id])=>has(scope.activeJobs,id)))}
  }
  return {facts,...(transition.delta?{delta:transition.delta}:{}),...(reset?{reset}:{})}
}
export function executionOutstanding(scope:ExecutionScope) {
  return {anchor:scope.anchor,saveAs:scope.saveAs,unresolvedCalls:Object.values(scope.uncertain),pendingCalls:Object.keys(scope.pending),
    activeRequests:Object.entries(scope.activeRequests),activeJobs:Object.entries(scope.activeJobs),failedCalls:Object.values(scope.failures),
    resolvedCalls:new Set<string>(),unavailableResults:Object.values(scope.unavailable)}
}
