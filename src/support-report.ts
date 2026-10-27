import type {Context} from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-session-persistence'
import type {} from '@deepseek-ai/dsh-session'
import type {SessionHandle} from '@deepseek-ai/dsh-session-persistence'
import {spawn} from 'node:child_process'
import path from 'node:path'
import {scrubbedParentEnv} from '@deepseek-ai/dsh-subprocess'
import {fileURLToPath} from 'node:url'
import {videoRuntime,type RuntimeOptions} from './video-runtime.js'
import {executionCall,executionResult,houdiniSourceMessages} from './dsh-adapter.js'
import {sectionData} from './prompt-data.js'
import type {SessionEvent} from './execution-history.js'
import {EXPECTED_EXECUTION_CONTRACT_VERSION,EXPECTED_VERB_CATALOG_HASH} from './generated-verb-contract.js'

const MAX_BYTES=4*1024*1024
const MAX_EVENTS=2000
const ROOT=fileURLToPath(new URL('../',import.meta.url))
const SCRIPT=fileURLToPath(new URL('../houdini/python3.11libs/dsh_support_report.py',import.meta.url))
const KEYS=['schema','kind','executor_id','previous_executor','runtime_id','owner_session','owner_call','request_ref','request_id',
  'scene_id','scene_epoch','checkpoint_id','operation_id','status','ok','code','message','reason','error','cause','restored_nodes',
  'missing_nodes','hip_is_new','dirty','dirty_reliable','requires_reload','execution_contract','contract_version',
  'hou_version','houdini_version','scene_recovery','executionContractVersion','timestamp','stack','name','cleared']

function facts(value:any,depth=0):any {
  if(depth>5)return '[DEPTH LIMIT]'
  if(value===null||typeof value==='boolean'||typeof value==='number')return value
  if(typeof value==='string')return value.length<=16384?value:value.slice(0,16384)+'[TRUNCATED]'
  if(!value||typeof value!=='object')return undefined
  return Object.fromEntries(KEYS.filter(key=>Object.hasOwn(value,key)).map(key=>[key,facts(value[key],depth+1)]))
}

export function supportEvent(event:SessionEvent):Record<string,unknown>|null {
  const base={seq:event.seq,time:event.time,type:event.type}
  const call=executionCall(event)
  if(call)return {...base,callId:call.callId,tool:call.name}
  const result=executionResult(event)
  if(result) {
    const value=result.value
    const messageError=result.isError?(event.data?.message?.content??event.data?.content??[])
      .filter((block:any)=>block.type==='text').map((block:any)=>String(block.text).slice(0,16384)).join('\n'):undefined
    return {...base,callId:result.callId,tool:result.tool,isError:result.isError,error:facts(result.error??messageError),
      execution:facts(value?.execution),outcome:facts(value),
      verbs:Array.isArray(value?.verbs)?value.verbs.slice(0,100).map((verb:any)=>({verb:verb.verb,ok:verb.ok,error:facts(verb.error)})):undefined}
  }
  const messages=houdiniSourceMessages(event)
  if(messages.length) {
    const sections=messages.flatMap(message=>message.source.sections??[]).filter((section:any)=>
      ['dsh-houdini:executor-binding','dsh-houdini:recovery-required','dsh-houdini:workspace-directory','dsh-houdini:workspace-open','dsh-houdini:project-resume'].includes(section.name))
    if(sections.length)return {...base,sections:sections.map((section:any)=>({name:section.name,facts:facts(sectionData(section))}))}
  }
  if(['turn/start','turn/end','step/start','step/end'].includes(event.type))return base
  return null
}

export function supportOptions(input:unknown) {
  const value=input as Record<string,unknown>
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>
    !['sessionId','description','includeContent','includeLogs','includePrevious'].includes(key))
    ||typeof value.sessionId!=='string'||!value.sessionId.trim()||value.sessionId.length>256
    ||typeof value.description!=='string'||value.description.length>4000
    ||!['includeContent','includeLogs','includePrevious'].every(key=>typeof value[key]==='boolean'))
    throw new Error('请选择当前会话，并提供有效的诊断包选项。')
  return value as {sessionId:string;description:string;includeContent:boolean;includeLogs:boolean;includePrevious:boolean}
}

async function countEvents(handle:SessionHandle,signal:AbortSignal):Promise<number> {
  let lower=0,upper=MAX_EVENTS
  while(true) {
    signal.throwIfAborted()
    if(!(await handle.read(upper,1,{signal})).events.length)break
    lower=upper+1
    upper*=2
    if(!Number.isSafeInteger(upper))throw new Error('会话事件范围无法确定。')
  }
  while(lower<upper) {
    signal.throwIfAborted()
    const middle=Math.floor((lower+upper)/2)
    if((await handle.read(middle,1,{signal})).events.length)lower=middle+1
    else upper=middle
  }
  return lower
}

export async function supportPayload(ctx:Context,input:unknown,signal:AbortSignal) {
  signal.throwIfAborted()
  const options=supportOptions(input),missing:string[]=[],timeline:Record<string,unknown>[]=[],content:SessionEvent[]=[]
  const persistence=ctx.get('sessionPersistence')
  if(!persistence)throw new Error('当前无法读取会话，未生成会话诊断包。可从 Houdini 的「DSH-Houdini → Version & Updates → 诊断」导出本端接入报告；该报告不含会话历史。')
  const sessionId=options.sessionId as Parameters<typeof persistence.open>[0]
  const sessions=ctx.get('sessions'),live=sessions?.get(sessionId)
  if(live) {
    try {if(await sessions!.flush(live)!==true)missing.push('session_flush_unconfirmed')}
    catch {signal.throwIfAborted();missing.push('session_flush_failed_reading_committed_history')}
  }
  signal.throwIfAborted()
  const handle=await persistence.open(sessionId,'read',{signal})
  let timelineBytes=0,contentBytes=0,scanned=0,omitted=0,contentOmitted=0
  try {
    if(handle.header.id!==sessionId)throw new Error('会话读取身份不一致，未生成诊断包。')
    const stat=await persistence.stat(sessionId,{signal})
    const count=stat?.eventCount??await countEvents(handle,signal)
    const ranges=count>MAX_EVENTS+64?[[0,64],[count-MAX_EVENTS,MAX_EVENTS]]:[[0,count]]
    if(count>MAX_EVENTS+64)missing.push('history_middle_omitted')
    for(const [start,length] of ranges) {
      for(let offset=start;offset<start+length;offset+=64) {
        signal.throwIfAborted()
        const read=await handle.read(offset,Math.min(64,start+length-offset),{signal})
        if(!read.events.length)break
        for(const event of read.events) {
          scanned++
          const row=supportEvent(event)
          if(row) {
            const encoded=JSON.stringify(row)
            timeline.push(row);timelineBytes+=Buffer.byteLength(encoded)
            while(timelineBytes>MAX_BYTES/2&&timeline.length) {
              timelineBytes-=Buffer.byteLength(JSON.stringify(timeline.shift()));omitted++
            }
          }
          if(options.includeContent) {
            const encoded=JSON.stringify(event)
            const size=Buffer.byteLength(encoded)
            if(size<=MAX_BYTES/2) {
              content.push(event);contentBytes+=size
              while(contentBytes>MAX_BYTES/2&&content.length) {
                contentBytes-=Buffer.byteLength(JSON.stringify(content.shift()));contentOmitted++
              }
            } else contentOmitted++
          }
        }
      }
    }
    if(omitted)missing.push('timeline_byte_limit:'+omitted)
    if(contentOmitted)missing.push('content_byte_limit:'+contentOmitted)
    return {options,session:{id:sessionId,format:handle.header.version,scanned_events:scanned,total_events:count},
      timeline,content:options.includeContent?content:undefined,missing,
      environment:{node:process.version,host_executor_id:process.env.DSH_HOUDINI_EXECUTOR_ID??null,
        expected_execution_contract:EXPECTED_EXECUTION_CONTRACT_VERSION,expected_verb_hash:EXPECTED_VERB_CATALOG_HASH,
        host_started_at:new Date(Date.now()-process.uptime()*1000).toISOString()}}
  } finally {await handle.close()}
}

/** Diagnostics need a local interpreter, not a live scene. Desktop owns no HFS
 * environment, so use its discovered installation's exact Python executable. */
export async function supportPython(ctx:Context,signal:AbortSignal,
  options:Pick<RuntimeOptions,'environment'|'exists'>={}):Promise<string> {
  signal.throwIfAborted()
  const desktop=ctx.get('houdiniDesktop')
  if(desktop) {
    for(const installation of await desktop.listInstallations()) {
      signal.throwIfAborted()
      const candidate=videoRuntime('',{...options,environment:{HFS:installation.hfs}}).python
      if(candidate)return candidate
    }
  }
  const candidate=videoRuntime('',options).python
  if(candidate)return candidate
  throw new Error('未找到 Houdini 安装内的 Python 3.11+；请检查本机 Houdini 安装后重新导出诊断包。此操作不要求连接或启动场景。')
}

export function collectSupport(payload:unknown,signal:AbortSignal,python:string) {
  if(!python||!path.isAbsolute(python))throw new Error('诊断收集需要 Houdini 安装内 Python 的完整路径。')
  signal.throwIfAborted()
  return new Promise<any>((resolve,reject)=>{
    const env=scrubbedParentEnv()
    const processHandle=spawn(python,[SCRIPT],{cwd:ROOT,env,windowsHide:true,stdio:['pipe','pipe','pipe'],signal})
    const chunks:Buffer[]=[]
    let size=0,overflow=false
    const timeout=setTimeout(()=>processHandle.kill(),30000)
    processHandle.stdout.on('data',(chunk:Buffer)=>{
      size+=chunk.length
      if(size>16*1024*1024){overflow=true;processHandle.kill()}
      else chunks.push(chunk)
    })
    processHandle.stderr.resume()
    processHandle.stdin.on('error',()=>{})
    processHandle.on('error',error=>{clearTimeout(timeout);reject(error.name==='AbortError'?error:new Error('诊断收集程序无法启动。'))})
    processHandle.on('close',code=>{
      clearTimeout(timeout)
      if(code!==0||overflow){reject(new Error('诊断收集未完成，未生成可分享文件。'));return}
      try {resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')))}catch {reject(new Error('诊断包返回格式无效。'))}
    })
    processHandle.stdin.end(JSON.stringify(payload))
  })
}

export async function createSupportReport(ctx:Context,input:unknown,signal:AbortSignal) {
  const payload=await supportPayload(ctx,input,signal)
  return collectSupport(payload,signal,await supportPython(ctx,signal))
}
