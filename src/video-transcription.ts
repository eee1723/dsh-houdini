/** Tutorial ASR delegates evidence and attempt history to the bundled Python worker.
 * DSH owns route/credential settings; the child receives a per-operation secret only. */
import fs from 'node:fs/promises'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {spawn} from 'node:child_process'
import {randomUUID} from 'node:crypto'
import type {Context} from '@deepseek-ai/cordis'
import {defineTool} from '@deepseek-ai/dsh-tools'
import {apiCredential,apiEndpoint,configuredApiRoutes,configuredProviders,hostService} from './api-route.js'
import {HoudiniToolRuntime,workspaceOf,type HoudiniConnection} from './tool-runtime.js'
import {VIDEO_TOOLS} from './tool-catalog.js'
import {resolveVideoRuntime} from './video-runtime.js'
import {registerLocalVideoTool,releaseVideoChildLock} from './video-process.js'

const SCRIPT=fileURLToPath(new URL('../skills/houdini-video-tutorial/scripts/video_tutorial.py',import.meta.url))
const KEY_ENV='DSH_VIDEO_TRANSCRIPTION_KEY'
const SETTINGS={section:'houdini-video',model_section:'models'}
type VideoSelection={provider:string;model:string;python:string}

export function videoSelection(ctx:any):VideoSelection {
  const chosen=hostService(ctx,'houdiniFrontend')?.videoSelection?.()
  return {provider:chosen?.provider??'',model:chosen?.model??'',python:chosen?.python??''}
}

export function transcriptionProtocol(model:string) {
  if (/^qwen3-asr-flash(?:-\d{4}-\d{2}-\d{2})?$/.test(model)) return 'qwen-chat-asr'
  if (['qwen-audio-3.0-asr-flash','qwen-audio-3.1-asr-flash'].includes(model)) return 'dashscope-asr'
  if (/^qwen3-asr-flash-(?:filetrans|realtime|us)/.test(model) || /^qwen-audio-3\./.test(model))
    throw Error('此千问模型使用独立的 DashScope 接口；当前支持 qwen3-asr-flash 和 qwen-audio-3.0-asr-flash 本地切片转录，尚未接入此型号的异步文件转写或实时语音接口。')
  return 'openai-transcriptions'
}

function transcriptionEndpoint(profile:any,model='') {
  if (!profile || !['openai-completions','openai-responses'].includes(profile.api) || !profile.baseURL)
    throw Error('此供应商尚无可复用的 OpenAI 兼容音频 API 地址；请在「模型」设置配置支持语音转录的自定义 API。')
  const protocol=transcriptionProtocol(model)
  let endpoint
  if (protocol==='dashscope-asr') {
    const base=apiEndpoint(profile.baseURL,'','Transcription')
    if (!['/compatible-mode/v1/','/api/v1/'].includes(base.pathname))
      throw Error('Qwen-Audio 转录需要此供应商明确的 /compatible-mode/v1 或 /api/v1 基址；不能从其它网关路径推断原生接口。')
    endpoint=apiEndpoint(profile.baseURL,'/api/v1/services/aigc/multimodal-generation/generation','Transcription')
  } else endpoint=apiEndpoint(profile.baseURL,protocol==='qwen-chat-asr'?'chat/completions':'audio/transcriptions','Transcription')
  if (endpoint.protocol!=='https:' && !['127.0.0.1','[::1]','localhost'].includes(endpoint.hostname))
    throw Error('Cloud transcription requires HTTPS; HTTP is supported only for an explicit loopback test server')
  if (profile.headers && Object.keys(profile.headers).length)
    throw Error('This transcription route has custom headers that the audio worker does not support')
  return {endpoint,protocol}
}

/** Configuration and credential presence are facts, not an ASR capability test. */
export async function videoModels(ctx:any,query='',provider?:string,exec?:any,connection?:HoudiniConnection) {
  const selected=videoSelection(ctx),routes=[],diagnostics:string[]=[]
  const providers=configuredProviders(ctx)
  for (const route of providers.filter((row:any)=>!provider||row.provider===provider)) {
    const notes:string[]=[]
    let endpoint='',origin='',protocol='',credential:{configured:boolean;source?:string}={configured:false}
    if (route.error) notes.push(route.error)
    try {const value=transcriptionEndpoint(route.profile,selected.provider===route.provider?selected.model:'');endpoint=value.endpoint.href;origin=value.endpoint.origin;protocol=value.protocol}
    catch(error) {notes.push((error as Error).message)}
    if (!route.profile?.apiKeyEnv) notes.push('在模型设置中为供应商配置 API 凭据引用。')
    else {
      const credentials=hostService(ctx,'credentials')
      if (!credentials?.describe) notes.push('DSH 凭据状态服务不可用。')
      else {
        const info=await credentials.describe(route.profile.apiKeyEnv)
        credential={configured:info.configured===true,...(info.source?{source:info.source}:{})}
        if (!credential.configured) notes.push('服务商尚未配置可用凭据。')
      }
    }
    let models:{id:string;name:string}[]=[]
    try {models=(await hostService(ctx,'llm').listModels(route.provider))
      .filter((row:any)=>`${row.id} ${row.name??''}`.toLowerCase().includes(query.toLowerCase()))
      .map((row:any)=>({id:row.id,name:row.name??row.id}))}
    catch {notes.push('模型目录不可读；可通过「其他转录模型」填写供应商公布的准确模型 ID。')}
    routes.push({provider:route.provider,display_name:route.displayName,origin,endpoint,models,credential,
      protocol,support:endpoint?'unverified':'unsupported',diagnostics:notes})
  }
  if (!selected.provider || !selected.model) diagnostics.push('请在「教程视频」设置选择转录服务供应商和模型，或在本次调用显式指定。')
  if (selected.provider && !providers.some((row:any)=>row.provider===selected.provider))
    diagnostics.push('已选转录服务供应商不再存在，请检查模型设置。')
  if (!routes.length) diagnostics.push('请先在「模型」设置配置供应商、API 地址和凭据。')
  let runtime=null
  try {runtime={...await tutorialRuntime(ctx,selected.python,exec,connection),script:SCRIPT}}
  catch(error) {diagnostics.push((error as Error).message)}
  return {selected,routes,diagnostics,runtime,settings:SETTINGS,
    scope:'仅读取配置和凭据是否存在；未上传音频、未调用付费接口，模型目录不证明转录支持。'}
}

export interface VideoProcessRequest {
  executable:string;args:string[];env:NodeJS.ProcessEnv;cwd:string;work:string;signal?:AbortSignal
}
export interface VideoProcessResult {code:number|null;stdout:string;stderr:string;cancelled:boolean}
export type VideoProcessRunner=(request:VideoProcessRequest)=>Promise<VideoProcessResult>

/** The selected executor, rather than the shared Host's parent HFS, owns automatic Python discovery. */
async function tutorialRuntime(ctx:any,python:string,exec?:any,connection?:HoudiniConnection) {
  const explicit=python.trim()&&!['python','python.exe'].includes(python.trim().toLowerCase())
  if(explicit||!connection||!exec)return resolveVideoRuntime(python)
  const {bridge}=await new HoudiniToolRuntime(ctx,connection).target(exec)
  return resolveVideoRuntime(python,{bridge,signal:exec.signal})
}

export const runVideoProcess:VideoProcessRunner=request=>new Promise((resolve,reject)=>{
  request.signal?.throwIfAborted()
  const child=spawn(request.executable,request.args,{cwd:request.cwd,env:request.env,shell:false,
    windowsHide:true,stdio:['ignore','pipe','pipe']})
  let stdout='',stderr='',overflow=false,cancelled=false,spawnError:Error|undefined
  const cancel=()=>{cancelled=true;child.kill()}
  request.signal?.addEventListener('abort',cancel,{once:true})
  child.stdout.setEncoding('utf8');child.stderr.setEncoding('utf8')
  child.stdout.on('data',(data:string)=>{if (stdout.length+data.length>1_000_000){overflow=true;child.kill()}else stdout+=data})
  child.stderr.on('data',(data:string)=>{if (stderr.length+data.length>64_000){overflow=true;child.kill()}else stderr+=data})
  child.on('error',error=>{spawnError=error})
  child.on('close',async code=>{
    request.signal?.removeEventListener('abort',cancel)
    await releaseVideoChildLock(request.work,child.pid)
    if (spawnError) reject(Error(`Cannot start the configured Python interpreter (${(spawnError as NodeJS.ErrnoException).code??'process error'}); check Tutorial Video settings`))
    else resolve({code,stdout,stderr:overflow?'Python worker output exceeded its limit; existing ASR attempts are retained.':stderr,cancelled})
  })
  if (request.signal?.aborted) cancel()
})

export interface VideoTranscribeArgs {
  work:string;provider?:string;model?:string;allow_upload:boolean;max_chunks?:number;chunks?:string[]
  retry_failed?:boolean;max_retries?:number;concurrency?:number;requests_per_second?:number
  vocabulary?:{word:string;weight:number}[];speaker_diarization?:boolean
}

async function writableWork(ctx:any,exec:any,work:string) {
  const filesystem=hostService(ctx,'fs'),policyService=hostService(ctx,'sandboxPolicy'),cwd=workspaceOf(exec)
  if (!cwd || !filesystem || !policyService) throw Error('Transcription requires a DSH workspace, filesystem and file policy')
  const policy=policyService.resolve({session:exec.agent.session})
  if (policy.mode==='read-only') throw Error('Current DSH file policy is read-only; transcription saves evidence into its task directory')
  if (typeof work!=='string'||!path.isAbsolute(work)) throw Error('Use the absolute prepared video task directory')
  const target=await filesystem.resolve(work,{cwd,signal:exec.signal}),local=filesystem.processPath(target)
  if (filesystem.processPathFromHostPath(local)!==local) throw Error('Transcription requires a local/shared Host filesystem')
  if (policy.mode!=='danger-full-access') {
    const root=await filesystem.resolve(policy.workspaceRoot,{signal:exec.signal})
    if (!filesystem.contains(root,target)) throw Error('Prepared video task directory is outside the current writable workspace')
  }
  if (!(await fs.stat(local)).isDirectory()) throw Error('Prepared video task directory is missing')
  return {local,cwd}
}

export async function transcribeVideo(ctx:any,exec:any,args:VideoTranscribeArgs,runner:VideoProcessRunner=runVideoProcess,connection?:HoudiniConnection) {
  if (args.allow_upload!==true) throw Error('Cloud audio upload requires the user’s authorization and allow_upload=true')
  const chosen=videoSelection(ctx),provider=args.provider??chosen.provider,model=args.model??chosen.model
  if (!provider || !model) throw Error('Select the transcription provider and exact model in Tutorial Video settings or this call')
  if (!/^[A-Za-z0-9_.:/-]{1,160}$/.test(model)) throw Error('Invalid transcription model identifier')
  const maximum=args.max_chunks??100,retries=args.max_retries??(args.retry_failed?1:0)
  const concurrency=args.concurrency??64,rate=args.requests_per_second??8
  if (!Number.isInteger(concurrency)||concurrency<1||concurrency>64) throw Error('concurrency must be 1..64')
  if (!Number.isFinite(rate)||rate<=0||rate>100) throw Error('requests_per_second must be greater than 0 and at most 100')
  if (!Number.isInteger(maximum)||maximum<1||maximum>100) throw Error('max_chunks must be 1..100')
  if (!Number.isInteger(retries)||retries<0||retries>100||(!args.retry_failed&&retries!==0)) throw Error('Retries require retry_failed=true and max_retries within 0..100')
  if (args.chunks!==undefined && (!Array.isArray(args.chunks)||!args.chunks.length||args.chunks.some(id=>!/^\d{5}$/.test(id))||new Set(args.chunks).size!==args.chunks.length))
    throw Error('chunks must contain unique five-digit chunk IDs from the manifest')
  const routes=configuredApiRoutes(ctx).filter((row:any)=>row.provider===provider)
  if (routes.length!==1) throw Error('Transcription provider is not an unambiguous configured API route; inspect video_models')
  const profile=routes[0].profile,route=transcriptionEndpoint(profile,model),endpoint=route.endpoint.href,protocol=route.protocol
  const options:Record<string,unknown>={}
  if (args.vocabulary!==undefined) {
    if (protocol!=='dashscope-asr'||!Array.isArray(args.vocabulary)||args.vocabulary.length>2000
      ||args.vocabulary.some(row=>!row||typeof row.word!=='string'||!row.word.trim()||!Number.isInteger(row.weight)||![1,2,3,4,5,50].includes(row.weight))
      ||new Set(args.vocabulary.map(row=>row.word)).size!==args.vocabulary.length||args.vocabulary.filter(row=>row.weight===50).length>50)
      throw Error('Native vocabulary must contain unique words and weights 1..5 or 50')
    options.vocabulary=Object.fromEntries(args.vocabulary.map(row=>[row.word,row.weight]))
  }
  if (args.speaker_diarization!==undefined) {
    if (model!=='qwen-audio-3.1-asr-flash'||typeof args.speaker_diarization!=='boolean') throw Error('speaker_diarization requires Qwen-Audio 3.1')
    options.speaker_diarization_enabled=args.speaker_diarization
  }
  const {local,cwd}=await writableWork(ctx,exec,args.work)
  exec.signal?.throwIfAborted()
  const runtime=await tutorialRuntime(ctx,chosen.python,exec,connection)
  if (!runtime.python) throw Error('未找到当前 Houdini 的 Python；从 Houdini 启动工作区，或在「教程视频」填写 Python 3.11+ 的完整路径。')
  const key=await apiCredential(ctx,profile,'Transcription')
  const argv=[SCRIPT,'transcribe','--work',local,'--model',model,'--endpoint',endpoint,'--protocol',protocol,'--key-env',KEY_ENV,
    '--allow-upload','--max-chunks',String(maximum),'--max-retries',String(retries),
    '--concurrency',String(concurrency),'--requests-per-second',String(rate)]
  let optionsFile:string|undefined
  if (Object.keys(options).length) {
    optionsFile=path.join(local,`request-options-${randomUUID()}.json`)
    await fs.writeFile(optionsFile,JSON.stringify(options),{flag:'wx'})
    argv.push('--asr-options-file',optionsFile)
  }
  if (args.retry_failed) argv.push('--retry-failed')
  if (args.chunks) argv.push('--chunks',...args.chunks)
  const facts={provider,model,endpoint,protocol,work:local,max_chunks:maximum,concurrency,requests_per_second:rate,settings:SETTINGS}
  const redact=(text:string)=>text.split(key).join('[redacted]')
  try {
    const run=await runner({executable:runtime.python,args:argv,env:{...process.env,[KEY_ENV]:key,PYTHONUTF8:'1'},cwd,work:local,signal:exec.signal})
    const rows=redact(run.stdout).split(/\r?\n/).filter(Boolean).map(line=>{
      try {return JSON.parse(line)} catch {return null}
    }).filter(row=>row&&typeof row==='object'&&!Array.isArray(row))
    const summary=[...rows].reverse().find(row=>Number.isInteger(row.submitted)&&Number.isInteger(row.remaining))??null
    const progress=rows.filter(row=>typeof row.chunk==='string'&&row.status==='saved')
    const ok=run.code===0&&summary!==null&&!run.cancelled
    return {...facts,ok,status:ok?'processed':run.cancelled?'cancelled':'worker_failed',progress,summary,
      ...(!ok?{error:redact(run.stderr.trim()).slice(0,4000)||'Python worker did not return a completed transcription result.'}:{}),
      retry:'Successful chunks are reused. Failed or unknown attempts stay in the same task directory; no automatic retry was made.',
      next_action:ok?'Use the video script export command to read transcript coverage and unresolved chunks.':'Inspect this task’s retained attempt/outcome files before explicitly authorizing a retry.'}
  } catch(error) {
    return {...facts,ok:false,status:exec.signal?.aborted?'cancelled':'worker_not_started',error:redact((error as Error).message),
      retry:'No automatic retry. Inspect the task directory before submitting again.'}
  } finally {
    if (optionsFile) await fs.unlink(optionsFile).catch(()=>{})
  }
}

export function registerVideoTools(ctx:Context,connection?:HoudiniConnection) {
  registerLocalVideoTool(ctx,exec=>tutorialRuntime(ctx,videoSelection(ctx).python,exec,connection))
  const output={schema:{type:'json' as const},render:(_args:unknown,value:any)=>[{type:'text' as const,text:JSON.stringify(value)}],
    presentationMeta:(_args:unknown,value:any)=>({canonical:value})}
  ctx.tools.register(defineTool({name:'video_models',description:VIDEO_TOOLS.video_models.purpose,
    parameters:{query:{type:'string',description:'Optional model ID/name substring; empty lists all configured model suggestions.'},provider:{type:'string'}},
    output,presentCall:()=>({card:'generic',kind:'read',title:VIDEO_TOOLS.video_models.label}),
    execute:(args,exec)=>videoModels(ctx,args.query,args.provider,exec,connection)}))
  ctx.tools.register(defineTool({name:'video_transcribe',description:VIDEO_TOOLS.video_transcribe.purpose+
    ' Reads prepared audio through the bundled video script, whose original attempt/outcome files own resumability. Defaults to 64 concurrent requests, lowering to 32 then 16 after overload/server or transport failures; in-flight results are saved before new chunks continue within the submission budget. Authentication, model/response validation and local failures stop dispatch. Failed/unknown chunks are never automatically retried. No HOM or provider substitution. Upload authorization must already cover this service and audio.',
    parameters:{work:{type:'string',required:true,description:'Absolute task directory created by video_tutorial.py prepare.'},
      provider:{type:'string',description:'DSH configured API route; omitted uses Tutorial Video settings.'},
      model:{type:'string',description:'Exact ASR model ID; omitted uses Tutorial Video settings. It need not be a chat model.'},
      allow_upload:{type:'boolean',required:true,description:'True only when the user authorized this cloud audio upload.'},
      max_chunks:{type:'number',description:'Maximum total submissions this call including explicitly authorized retries, default 100, range 1..100.'},
      concurrency:{type:'number',description:'Maximum in-flight audio requests, default 64, range 1..64. Overload/server or transport failure drains in-flight requests then lowers to 32/16 for untouched chunks; 16 or below stops on further failure. Separate from the provider request rate.'},
      requests_per_second:{type:'number',description:'Dispatch rate, default 8 requests/second. Range >0..100; provider account limits still apply.'},
      vocabulary:{type:'array',items:{type:'object',properties:{word:{type:'string',required:true},weight:{type:'number',required:true}},additionalProperties:false},description:'Native Qwen-Audio only: explicit domain words with weights 1..5 (or 50); preserved in task configuration.'},
      speaker_diarization:{type:'boolean',description:'Qwen-Audio 3.1 only; true requests its provider sentence collection and is saved in the transcription configuration.'},
      chunks:{type:'array',items:{type:'string'},description:'Optional exact chunk IDs from the existing manifest.'},
      retry_failed:{type:'boolean',description:'Explicit authorization to resubmit failed/unknown chunks; default false.'},
      max_retries:{type:'number',description:'Retry request budget this call; default 0 (or 1 with retry_failed).'}},
    output,presentCall:args=>({card:'generic',kind:'execute',title:VIDEO_TOOLS.video_transcribe.label,rawInput:args}),
    execute:(args,exec)=>transcribeVideo(ctx,exec,args,runVideoProcess,connection)}))
}
