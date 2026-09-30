/** DSH 0.2 message producers and native/nested execution-log adapter. */
import type { Context } from '@deepseek-ai/cordis'
import {createUserMessage,type ContentBlock,type ContextFormed} from '@deepseek-ai/dsh-llm'
import type { JsonValue } from '@deepseek-ai/dsh-util-values'
import type { SessionEvent } from './execution-history.js'
import { HOUDINI_TOOLS } from './tool-catalog.js'

declare module '@deepseek-ai/dsh-llm' {
  interface MessageSourceMap {
    'dsh-houdini': {readonly kind:'dsh-houdini'} & ContextFormed
  }
}

export const HOUDINI_SOURCE='dsh-houdini' as const
/** DSH's released V3-to-V4 converter names external producers plugin:<name>. */
export const isHoudiniSource=(source:any):boolean =>
  source?.kind===HOUDINI_SOURCE || source?.kind==='plugin:dsh-houdini'
export const isHoudiniTool=(name:unknown):name is keyof typeof HOUDINI_TOOLS =>
  typeof name==='string' && Object.hasOwn(HOUDINI_TOOLS,name)

export function houdiniMessage(content:readonly ContentBlock[]) {
  return createUserMessage({content,source:{kind:HOUDINI_SOURCE}})
}

export function houdiniSnapshot(section:{name:string;text:string}) {
  return createUserMessage({content:[{type:'text',text:section.text}],
    source:{kind:HOUDINI_SOURCE,form:'snapshot',sections:[section]}})
}

const LOG_KIND='dsh-houdini/execution-v1'
/** DSH preserves meta for native results but only content for PTC results.
 * Shape only that durable nested copy; the program value, model summary and
 * image contexts keep DSH's ordinary execution channel. */
export function installHoudiniExecutionLog(ctx:Context):void {
  const settled = new WeakMap<object,Map<string,JsonValue>>()
  ctx.on('tools/result',(exec,result)=>{
    if (!exec.agent || exec.parent === undefined || !isHoudiniTool(exec.name) || result.isError) return
    let calls = settled.get(exec.agent)
    if (!calls) {calls=new Map();settled.set(exec.agent,calls)}
    calls.set(exec.callId,result.value)
  })
  ctx.on('tools/ptc-dispatch-log',async(dispatch,next)=>{
    const content = await next()
    if (!dispatch.agent || !isHoudiniTool(dispatch.name)) return content
    const calls = settled.get(dispatch.agent)
    if (!calls?.has(dispatch.subCallId)) return content
    const value = calls.get(dispatch.subCallId)!
    calls.delete(dispatch.subCallId)
    return [{type:'text',text:JSON.stringify({kind:LOG_KIND,callId:dispatch.subCallId,tool:dispatch.name,value})}]
  })
}

/** Read the declared canonical value, never infer facts from prose. */
export function executionResult(event:SessionEvent):{callId:string;tool?:string;value:any;isError?:boolean;error?:any}|null {
  const data=event.data
  if (event.type==='tool/result') return {callId:data?.message?.source?.callId,value:data?.meta?.canonical,
    isError:data?.message?.isError,error:data?.error}
  if (event.type!=='tool/ptc-dispatch' || !isHoudiniTool(data?.name)) return null
  for (const block of data.content ?? []) {
    if (block.type!=='text') continue
    let record:any
    try {record=JSON.parse(block.text)} catch {continue}
    if (record?.kind===LOG_KIND && record.callId===data.subCallId && record.tool===data.name)
      return {callId:record.callId,tool:record.tool,value:record.value,isError:data.isError,error:data.error}
  }
  return {callId:data.subCallId,tool:data.name,value:undefined,isError:data.isError,error:data.error}
}

export function executionCall(event:SessionEvent):{callId:string;name:string}|null {
  if (event.type==='tool/call') return event.data
  if (event.type==='tool/ptc-dispatch-start') return {callId:event.data.subCallId,name:event.data.name}
  return null
}
