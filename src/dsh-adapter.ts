/** DSH 0.2 message producers and native/nested execution-log adapter. */
import type { Context } from '@deepseek-ai/cordis'
import type {Agent} from '@deepseek-ai/dsh-agent'
import {createUserMessage,type ContentBlock,type ContextFormed} from '@deepseek-ai/dsh-llm'
import {appendPluginRecord} from '@deepseek-ai/dsh-session'
import type {ExecResult,JsonValue} from './bridge.js'
import type { SessionEvent } from './execution-history.js'
import { houdiniToolKind } from './tool-catalog.js'
import {executionLogValue,renderJobObservation} from './tool-output.js'

declare module '@deepseek-ai/dsh-llm' {
  interface MessageSourceMap {
    'dsh-houdini': {readonly kind:'dsh-houdini'} & ContextFormed
  }
}

export const HOUDINI_SOURCE='dsh-houdini' as const
/** DSH's released V3-to-V4 converter names external producers plugin:<name>. */
export const isHoudiniSource=(source:any):boolean =>
  source?.kind===HOUDINI_SOURCE || source?.kind==='plugin:dsh-houdini'
export const isHoudiniTool=(name:unknown):name is string => typeof name==='string'
  &&houdiniToolKind(name)!==undefined

/** Traverse only producer-defined execution slots. A report read, request
 * receipt and a HOM execution are different objects even when nested together.
 * Consumers share these addresses; none recursively searches authored data. */
export function returnedExecutions(tool:string,value:any):{domain:'live'|'isolated';execution:any;archive?:string;runDirectory?:string}[] {
  if(tool==='houdini_isolated'){
    if(value?.kind!=='isolated-houdini')return []
    return [value.report?.result,value.progress].flatMap(report=>report?[
      {domain:'isolated' as const,execution:report.builder,archive:'builder.json',runDirectory:value.run_directory},
      ...(Array.isArray(report.checks)?report.checks.map((check:any)=>({domain:'isolated' as const,
        execution:check.execution,archive:`check-${check.id}.json`,runDirectory:value.run_directory})):[]),
    ].filter(row=>row.execution):[])
  }
  return (['python','receipt','ui'].includes(houdiniToolKind(tool)??'')||tool==='houdini_job_submit'&&value?.execution)
    &&value&&typeof value==='object'
    ?[{domain:'live',execution:value}]:[]
}

export const LIVE_JOB_KIND='houdini-live'
export const LIVE_JOB_RESULT='dsh-houdini/live-job-result-v1'
export const LIVE_JOB_OUTPUT_LIMIT_BYTES=16000
export const JOB_EXECUTION_RECORD='plugin:dsh-houdini/execution' as const
export interface JobExecutionRecord {
  schema:1;callId:string;sourceCallId:string;rootCallId:string;tool:'houdini_job_submit';canonical:JsonValue
}
declare module '@deepseek-ai/dsh-session/types' {
  interface PluginRecordMap {'plugin:dsh-houdini/execution':JobExecutionRecord}
}

/** The actual Bridge result enters its owning native Session once produced.
 * Generic jobs own observation and notifications, never the domain's result
 * metadata. This ignorable plugin fact has no model-visible surface. */
export function recordHoudiniJobExecution(exec:any,value:ExecResult):void {
  const ref=(value.requestReceipt as any)?.request_ref
  if(typeof ref!=='string'||!exec.agent?.session)throw Error('A completed Houdini job requires its original request and owning Session')
  const data:JobExecutionRecord={schema:1,callId:'bridge-job:'+ref,sourceCallId:exec.callId,
    rootCallId:exec.rootCallId??exec.callId,tool:'houdini_job_submit',canonical:executionLogValue(value)}
  // Execution envelopes may contain omitted undefined fields. Commit the same
  // JSON value that a native tool's metadata transport would persist.
  appendPluginRecord(exec.agent.session,JOB_EXECUTION_RECORD,JSON.parse(JSON.stringify(data)))
}

/** Validate only our declared record, never infer execution from job status or prose. */
export function recordedJobExecution(event:SessionEvent):JobExecutionRecord|undefined {
  if(event.type!==JOB_EXECUTION_RECORD||event.ignorable!==true)return
  const data=event.data,value=data?.canonical,ref=value?.requestReceipt?.request_ref
  if(data?.schema!==1||data.tool!=='houdini_job_submit'||typeof ref!=='string'
    ||! /^[0-9a-f]{32}\.[0-9a-f]{32}$/.test(ref)||data.callId!=='bridge-job:'+ref
    ||typeof data.sourceCallId!=='string'||!data.sourceCallId||typeof data.rootCallId!=='string'||!data.rootCallId
    ||!value||typeof value!=='object'||Array.isArray(value)||typeof value.ok!=='boolean'
    ||!['done','failed','cancelled'].includes(value.status))return
  return data
}
/** A generic DSH job read becomes a Houdini fact only through this exact producer envelope. */
export function liveJobResult(value:any):{job_id:string;value:any}|undefined {
  if(value?.job?.kind!==LIVE_JOB_KIND||typeof value.text!=='string')return
  let record:any
  try {record=JSON.parse(value.text)}catch{return}
  if(record?.kind!==LIVE_JOB_RESULT||record.job_id!==value.job.id
    ||!record.value||typeof record.value!=='object'||Array.isArray(record.value))return
  return record
}

export function houdiniMessage(content:readonly ContentBlock[]) {
  return createUserMessage({content,source:{kind:HOUDINI_SOURCE}})
}

export function houdiniSnapshot(section:{name:string;text:string}) {
  return createUserMessage({content:[{type:'text',text:section.text}],
    source:{kind:HOUDINI_SOURCE,form:'snapshot',sections:[section]}})
}

export function workspaceOpeningMessage(record:{executor_id:string;scene_id?:string;scene_epoch?:string;hip_path:string|null;hip_is_new?:boolean;project_label?:string}) {
  return houdiniSnapshot({name:'dsh-houdini:workspace-open',text:
    'Explicit Open Workspace target; this is not node ownership or a saved checkpoint.\n'+JSON.stringify({
      executor_id:record.executor_id,scene_id:record.scene_id,scene_epoch:record.scene_epoch,
      hip_path:record.hip_path,hip_is_new:record.hip_is_new,project_label:record.project_label})})
}

export function houdiniSourceMessages(event:SessionEvent):any[] {
  const messages=event.type==='user/message'?[event.data]:event.type==='agent/inbox/spliced'?event.data?.inserted??[]:[]
  return messages.filter((message:any)=>isHoudiniSource(message?.source))
}

export function recordHoudiniContext(agent:Pick<Agent,'session'|'inject'>,message:ReturnType<typeof houdiniSnapshot>):void {
  agent.inject(message)
}

const LOG_KIND='dsh-houdini/execution-v1'
/** Render domain job summaries without copying or shadowing native controls.
 * Execution facts are already committed by the actual Bridge producer. */
export function installHoudiniExecutionLog(ctx:Context):void {
  ctx.on('tools/post-execute',async(exec,result,next)=>{
    const decision=await next()
    if(decision.kind!=='accept'||decision.content||'value' in decision)return decision
    const value=result.isError?undefined:result.value
    const live=exec.name==='job_output'?liveJobResult(value):undefined
    if(!live||decision.kind!=='accept'||decision.content)return decision
    const native=value as any
    const ref=live.value.requestReceipt?.request_ref
    const suffix=`\n\nDSH job ${live.job_id}: ${native.job.status}. Original images/result: houdini_request(request_ref=${JSON.stringify(ref)}).`
    return {...decision,content:[{type:'text' as const,text:
      renderJobObservation(live.value,LIVE_JOB_OUTPUT_LIMIT_BYTES-Buffer.byteLength(suffix))+suffix}]}
  })
}

/** Read the declared canonical value, never infer facts from prose. */
export function executionResult(event:SessionEvent):{callId:string;tool?:string;producer?:'live-job';recorded?:true;sourceCallId?:string;rootCallId?:string;value:any;isError?:boolean;error?:any}|null {
  const record=recordedJobExecution(event)
  if(record)return {callId:record.callId,tool:record.tool,producer:'live-job',recorded:true,
    sourceCallId:record.sourceCallId,rootCallId:record.rootCallId,value:record.canonical}
  const data=event.data
  if (event.type==='tool/result') {
    const value=data?.meta?.canonical,live=liveJobResult(value)
    return {callId:data?.message?.source?.callId,value:live?.value??value,
      ...(live?{tool:'houdini_request',producer:'live-job' as const}:{}),isError:data?.message?.isError,error:data?.error}
  }
  if (event.type!=='tool/ptc-dispatch' || !isHoudiniTool(data?.name)&&data?.name!=='job_output') return null
  if(data.meta&&Object.hasOwn(data.meta,'canonical')){
    const value=data.meta.canonical,live=data.name==='job_output'?liveJobResult(value):undefined
    return {callId:data.subCallId,tool:live?'houdini_request':data.name,
      ...(live?{producer:'live-job' as const}:{}),value:live?.value??value,isError:data.isError,error:data.error}
  }
  // Read previously committed wrappers; current producers write only DSH metadata.
  for (const block of data.content ?? []) {
    if (block.type!=='text') continue
    let record:any
    try {record=JSON.parse(block.text)} catch {continue}
    if (record?.kind===LOG_KIND && record.callId===data.subCallId && record.tool===data.name) {
      const live=record.tool==='job_output'?liveJobResult(record.value):undefined
      return {callId:record.callId,tool:live?'houdini_request':record.tool,...(live?{producer:'live-job' as const}:{}),value:live?.value??record.value,isError:data.isError,error:data.error}
    }
  }
  return {callId:data.subCallId,tool:data.name,value:undefined,isError:data.isError,error:data.error}
}

export function executionCall(event:SessionEvent):{callId:string;name:string}|null {
  if (event.type==='tool/call') return event.data
  if (event.type==='tool/ptc-dispatch-start') return {callId:event.data.subCallId,name:event.data.name}
  return null
}
