/** DSH 0.2 message producers and native/nested execution-log adapter. */
import type { Context } from '@deepseek-ai/cordis'
import type {Agent} from '@deepseek-ai/dsh-agent'
import {createUserMessage,type ContentBlock,type ContextFormed} from '@deepseek-ai/dsh-llm'
import type { SessionEvent } from './execution-history.js'
import { HOUDINI_TOOLS } from './tool-catalog.js'
import {renderExec,renderJobStatus} from './tool-output.js'

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
  &&(Object.hasOwn(HOUDINI_TOOLS,name)||name==='houdini_job_status'||name==='houdini_job_cancel')

export const LIVE_JOB_KIND='houdini-live'
export const LIVE_JOB_RESULT='dsh-houdini/live-job-result-v1'
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
/** DSH owns native/PTC canonical metadata. Only project this producer's generic
 * job output for the model; never write another copy of the returned envelope. */
export function installHoudiniExecutionLog(ctx:Context):void {
  ctx.on('tools/post-execute',async(exec,result,next)=>{
    const decision=await next()
    if(decision.kind!=='accept'||decision.content||'value' in decision)return decision
    const value=result.isError?undefined:result.value
    const live=exec.name==='job_output'?liveJobResult(value):undefined
    if(!live||decision.kind!=='accept'||decision.content)return decision
    const native=value as any
    const blocks=live.value.status?renderJobStatus(live.value):renderExec(live.value)
    const ref=live.value.requestReceipt?.request_ref
    return {...decision,content:[{type:'text' as const,text:blocks.filter(b=>b.type==='text').map(b=>b.text).join('\n\n')
      +`\n\nDSH job ${live.job_id}: ${native.job.status}. Original images/result: houdini_request(request_ref=${JSON.stringify(ref)}).`}]}
  })
}

/** Read the declared canonical value, never infer facts from prose. */
export function executionResult(event:SessionEvent):{callId:string;tool?:string;producer?:'live-job';value:any;isError?:boolean;error?:any}|null {
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
