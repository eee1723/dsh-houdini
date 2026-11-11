/** One-shot Houdini computation. DSH owns agents/jobs; the bundled checker owns run facts. */
import fs from 'node:fs/promises'
import {readFileSync} from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {createHash,randomUUID} from 'node:crypto'
import {spawn,execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {fileURLToPath} from 'node:url'
import type {Context} from '@deepseek-ai/cordis'
import type {ContentBlock} from '@deepseek-ai/dsh-llm'
import type {JobOutcome} from '@deepseek-ai/dsh-jobs'
import {defineTool} from '@deepseek-ai/dsh-tools'
import {hostService} from './api-route.js'
import {HoudiniToolRuntime,workspaceOf,type HoudiniConnection} from './tool-runtime.js'
import {resolveVideoRuntime} from './video-runtime.js'
import {localVideoEnvironment} from './video-process.js'
import {visualCapability,imageAttachmentFacts} from './image-output.js'
import {HOUDINI_TOOLS} from './tool-catalog.js'
import {executionLogValue,executionStdout,boundedFact} from './tool-output.js'
import {MAX_MODEL_TEXT_BYTES,MAX_PRESENTATION_BYTES} from './result-policy.js'
import {pointerKeys,pointerValue} from './result-details.js'
import {TextRetainer} from '@deepseek-ai/dsh-output-retention'
import {projectDirectoryPath} from './project-paths.js'

const CHECKER=fileURLToPath(new URL('../tools/isolated-houdini-check.py',import.meta.url))
const SCOPE='Independent hython run only. Results describe the declared inputs and checks, not the current live scene or visual quality. Python/callback and external-file side effects are not a filesystem sandbox.'
const detailPolicy=JSON.parse(readFileSync(new URL('../houdini/result-detail-policy.json',import.meta.url),'utf8'))
if(detailPolicy.schemaVersion!==1||!Number.isSafeInteger(detailPolicy.maxArchiveBytes)||detailPolicy.maxArchiveBytes<=0)
  throw Error('Unsupported result detail policy')
const MAX_REPORT_BYTES:number=detailPolicy.maxArchiveBytes
const MAX_MANIFEST_BYTES=4*1024*1024
const inputPolicy=JSON.parse(readFileSync(new URL('../houdini/isolated-execution-policy.json',import.meta.url),'utf8'))
if(inputPolicy.schemaVersion!==1||['maxFiles','maxInputBytes','maxInlineCodeBytes','maxFrame','maxPadding'].some(key=>
  !Number.isSafeInteger(inputPolicy[key])||inputPolicy[key]<=0))throw Error('Unsupported isolated input policy')

export interface IsolatedRuntime {python:string;hython:string;hfs:string;houdini?:string}
/** Inline manifests are serialized once by the Host, then validated and
 * executed by the same checker contract a manifest file uses. */
export interface IsolatedManifest {
  script?:string;hip?:string;code?:string;input_root?:string;files?:unknown[];checks?:unknown[]
}
export interface IsolatedArgs {
  operation?:'run'|'read';manifest?:string|IsolatedManifest;output_dir?:string;background?:boolean
  houdini_installation?:string
  timeout_seconds?:number;memory_mb?:number
  pointer?:string;offset?:number;limit?:number;select?:string[]
  allow_undeclared_image_input?:boolean
}
export interface IsolatedProcessRequest {
  runtime:IsolatedRuntime;manifest:string;manifestSha256:string;output:string;cancelFile:string;timeout:number;memory:number
  manifestBase?:string;reserved?:boolean
  signal:AbortSignal;onOutput?:(text:string)=>void
}
export interface IsolatedProcessResult {exit_code:number|null;cancel_requested:boolean;stdout?:string;stderr:string;error?:string}
export interface IsolatedOptions {
  runtimeResolver?:(exec:any,args:IsolatedArgs)=>Promise<IsolatedRuntime>
  runner?:(request:IsolatedProcessRequest)=>Promise<IsolatedProcessResult>
  planner?:typeof planIsolatedManifest
}

/** Explicit HFS selection for unbound/legacy sessions. Enumerate the supplied
 * installation only; ambiguity never chooses a different interpreter version. */
export async function isolatedInstallationRuntime(hfs:string,signal?:AbortSignal):Promise<IsolatedRuntime> {
  signal?.throwIfAborted()
  if(typeof hfs!=='string'||!path.isAbsolute(hfs))throw Error('houdini_installation must be an absolute Houdini installation directory (HFS)')
  const names=await fs.readdir(hfs,{withFileTypes:true})
  const candidates=process.platform==='win32'
    ?names.filter(item=>item.isDirectory()&&/^python\d+$/.test(item.name)).map(item=>path.join(hfs,item.name,'python.exe'))
    :[path.join(hfs,'python/bin/python3')]
  const available=[]
  for(const filename of candidates)if(await fs.stat(filename).then(stat=>stat.isFile(),()=>false))available.push(filename)
  if(available.length!==1)throw Error('The explicit Houdini installation must contain exactly one bundled Python executable; found '+available.length)
  const python=available[0]
  const {stdout,stderr}=await promisify(execFile)(python,['--version'],{
    windowsHide:true,timeout:10000,maxBuffer:65536,env:localVideoEnvironment(),cwd:hfs,signal})
  const version=(stdout||stderr).trim().match(/^Python (\d+)\.(\d+)\.\d+$/)
  if(!version||Number(version[1])<3||Number(version[1])===3&&Number(version[2])<11)
    throw Error('The selected Houdini installation requires bundled Python 3.11 or newer')
  return {python,hfs,hython:path.join(hfs,'bin',process.platform==='win32'?'hython.exe':'hython')}
}

export interface IsolatedInputPlan {
  schema_version:1;manifest_sha256:string;input_root:string
  files:{path:string;max_bytes?:number}[];max_input_bytes:number
  budgets:{timeout_seconds:number;memory_mb:number}
}

/** The checker owns the manifest language. Planning is pure ordinary Python:
 * it receives only already-authorized bytes and never reads declared files. */
export function planIsolatedManifest(runtime:IsolatedRuntime,bytes:Buffer,signal?:AbortSignal,budgets={timeout:inputPolicy.defaultTimeoutSeconds,memory:inputPolicy.defaultMemoryMb}):Promise<IsolatedInputPlan> {
  signal?.throwIfAborted()
  return new Promise((resolve,reject)=>{
    const child=execFile(runtime.python,[CHECKER,'--plan','--timeout',String(budgets.timeout),'--memory-mb',String(budgets.memory)],{
      cwd:path.join(runtime.hfs,'bin'),windowsHide:true,env:localVideoEnvironment(),
      timeout:10000,maxBuffer:MAX_REPORT_BYTES,encoding:'utf8',signal,
    },(error,stdout,stderr)=>{
      if(signal?.aborted){reject(signal.reason);return}
      try {
        const response=JSON.parse(stdout)
        if(!response.ok)throw Error(response.error)
        if(error)throw error
        resolve(response.plan)
      }catch(failure){reject(stdout?failure:error??Error(stderr||'Isolated input planning returned no result'))}
    })
    child.stdin!.on('error',()=>{}) // Process completion/abort carries the actual cause.
    child.stdin!.end(bytes)
  })
}

/** Cancellation reaches the checker first; its Windows Job reaps the exact owned worker tree. */
export function runIsolatedProcess(request:IsolatedProcessRequest):Promise<IsolatedProcessResult> {
  request.signal.throwIfAborted()
  return new Promise((resolve,reject)=>{
    const env=localVideoEnvironment()
    for(const key of ['HOUDINI_LICENSE_SERVER','SESI_LMHOST'])if(process.env[key])env[key]=process.env[key]
    const child=spawn(request.runtime.python,[CHECKER,'--trusted','--manifest',request.manifest,'--manifest-sha256',request.manifestSha256,
      ...(request.manifestBase?['--manifest-base',request.manifestBase]:[]),
      ...(request.reserved?['--reserved-output']:[]),
      '--hython',request.runtime.hython,'--output-dir',request.output,'--cancel-file',request.cancelFile,
      '--timeout',String(request.timeout),'--memory-mb',String(request.memory)],{
      cwd:path.join(request.runtime.hfs,'bin'),env,shell:false,windowsHide:true,stdio:['ignore','pipe','pipe']})
    let stdout='',stderr='',cancelRequested=false,processError:Error|undefined,cancelWrite:Promise<void>|undefined
    const cancel=()=>{
      cancelRequested=true
      cancelWrite??=fs.writeFile(request.cancelFile,JSON.stringify({action:'cancel_owned_worker'}),{flag:'wx'})
        .catch(error=>{if(error.code!=='EEXIST')throw error})
      // Keep the rejection observed while the checker is stopping.
      void cancelWrite.catch(()=>{})
    }
    request.signal.addEventListener('abort',cancel,{once:true})
    child.stdout.setEncoding('utf8');child.stderr.setEncoding('utf8')
    child.stdout.on('data',(chunk:string)=>{stdout=(stdout+chunk).slice(-256*1024);request.onOutput?.(chunk)})
    child.stderr.on('data',(chunk:string)=>{stderr=(stderr+chunk).slice(-16000)})
    child.on('error',error=>{processError=error})
    child.once('close',async exit_code=>{
      request.signal.removeEventListener('abort',cancel)
      try {await cancelWrite}
      catch(error){resolve({exit_code,cancel_requested:cancelRequested,stdout,stderr,error:'Cancellation marker could not be written: '+String(error)});return}
      if(processError)reject(processError)
      else resolve({exit_code,cancel_requested:cancelRequested,stdout,stderr})
    })
    if(request.signal.aborted)cancel()
  })
}

async function localPath(ctx:any,exec:any,filename:string,write=false) {
  const filesystem=hostService(ctx,'fs'),policyService=hostService(ctx,'sandboxPolicy'),cwd=workspaceOf(exec)
  if(!filesystem||!policyService||!cwd)throw Error('Isolated Houdini requires the DSH workspace, filesystem and file policy')
  if(typeof filename!=='string'||!path.isAbsolute(filename))throw Error('Use an absolute local path')
  const target=await filesystem.resolve(filename,{cwd,signal:exec.signal}),local=filesystem.processPath(target)
  if(filesystem.processPathFromHostPath(local)!==local)throw Error('Isolated Houdini requires a local/shared Host filesystem')
  if(write){
    const policy=policyService.resolve({session:exec.agent.session})
    if(policy.mode==='read-only')throw Error('Current DSH file policy is read-only')
    const root=await filesystem.resolve(policy.workspaceRoot,{signal:exec.signal})
    if(policy.mode!=='danger-full-access'&&!filesystem.contains(root,target))throw Error('Output must be inside the current writable workspace')
  }
  return {filesystem,target,local}
}

async function readJson(ctx:any,exec:any,filename:string,maxBytes:number) {
  const {filesystem,target}=await localPath(ctx,exec,filename)
  return JSON.parse(Buffer.from(await filesystem.readBytes(target,exec.signal,maxBytes)).toString('utf8'))
}

/** Display the checker's own facts and detail references, including legacy full reports. */
function reportView(report:any) {
  const result=report.result
  const execution=(value:any,pointer:string)=>{
    if(!value)return undefined
    return {...value,stdout:executionStdout(value),...(!value.details?{details_pointer:pointer}:{})}
  }
  const worker=report.worker?Object.fromEntries(Object.entries(report.worker).filter(([key])=>key!=='output')):undefined
  const builder=execution(result?.builder,'/result/builder'),checks=result?.checks?.map((check:any,index:number)=>{
    const projected=execution(check.execution,`/result/checks/${index}/execution`)
    return {...check,...(projected?{execution:projected}:{})}
  })
  return {...report,...(worker?{worker}:{}),...(result?{result:{...result,
    ...(builder?{builder}:{}),...(checks?{checks}:{})}}:{})}
}

/** Keep large input inventories in the run report, not every model turn. */
function inputStatusCounts(rows:any[]=[]):Record<string,number> {
  const counts=rows.reduce((counts,row)=>{
    const status=String(row.status);counts[status]=(counts[status]??0)+1;return counts
  },{} as Record<string,number>)
  const entries=Object.entries(counts) as [string,number][]
  if(entries.length<=8)return counts
  return {...Object.fromEntries(entries.slice(0,8)),
    other_statuses:entries.slice(8).reduce((total,entry)=>total+entry[1],0)}
}

export function isolatedPresentation(value:any) {
  if(!value.report)return value
  const report=reportView(value.report)
  for(const field of ['inputs','input_observations']){
    const rows=report[field]
    if(!Array.isArray(rows)||rows.length<=16)continue
    const visible=field==='input_observations'?rows.filter((row:any)=>row.status!=='unchanged'):[]
    report[field]={count:rows.length,preview:visible.slice(0,16),omitted:rows.length-Math.min(16,visible.length),
      ...(field==='input_observations'?{status_counts:inputStatusCounts(rows)}:{}),
      details:{path:value.report_path,pointer:'/'+field},
      scope:'Presentation inventory summary only; complete original rows remain in the run report.'}
  }
  const process=value.process&&value.process.exit_code===0&&!value.process.error
    ?Object.fromEntries(Object.entries(value.process).filter(([key])=>key!=='stdout').concat(
      value.process.stdout?[['stdout_location','Original tool result /process/stdout; the recorded report is displayed once.']]:[]))
    :value.process
  return {...value,report,...(process?{process}:{}),...(value.progress?{progress:reportView({result:value.progress}).result}:{})}
}

/** Keep one report's aggregate projection bounded as well as its individual
 * executions. The original run and immediate native/PTC return stay complete. */
export function isolatedLogValue(value:any) {
  if(!value.report)return boundedIsolatedFacts(value,value)
  const presented=isolatedPresentation(value)
  const resultFacts=(result:any)=>{
    if(!result)return result
    return {...result,
      ...(result.builder?{builder:executionLogValue(result.builder)}:{}),
      ...(Array.isArray(result.checks)?{checks:result.checks.map((check:any)=>({...check,
        ...(check.execution?{execution:executionLogValue(check.execution)}:{})}))}:{})}
  }
  const process=value.process?Object.fromEntries(Object.entries(value.process).filter(([key])=>key!=='stdout').concat(
    value.process.stdout?[['stdout_location','Process stdout is not duplicated in session facts; use the run report and execution archives.']]:[])):undefined
  return boundedIsolatedFacts(value,{...presented,report:{...presented.report,...(presented.report.result?{result:resultFacts(presented.report.result)}:{})},
    ...(presented.progress?{progress:resultFacts(presented.progress)}:{}),...(process?{process}:{})})
}

function boundedIsolatedFacts(original:any,presented:any) {
  if(Buffer.byteLength(JSON.stringify(presented))<=MAX_PRESENTATION_BYTES)return presented
  return isolatedSummary(original)
}

function isolatedSummary(original:any) {
  const report=original.report,result=report?.result??original.progress
  return boundedFact(JSON.parse(JSON.stringify({kind:'isolated-houdini',run_directory:original.run_directory,
    report_path:original.report_path,read:typeof original.run_directory==='string'&&!original.preflight?{operation:'read',output_dir:original.run_directory}:undefined,
    ...(original.job_id?{job_id:original.job_id}:{}),...isolatedJobSummary(original),
    report_summary:report?{ok:report.ok,finished:report.finished,phase:report.phase,
      worker:report.worker?{status:report.worker.status,returncode:report.worker.returncode}:undefined}:undefined,
    builder_ok:result?.builder?.ok,
    checks:{count:result?.checks?.length??0,status_counts:inputStatusCounts(result?.checks)},
    presentation:{status:'summary',reason:'The aggregate report exceeded the model-text budget. Use operation="read" with a JSON Pointer such as "/result/builder/result" to retrieve only the needed field; absence from this summary is not evidence of absence.'}})))
}

function excerptText(value:unknown,maxChars=800) {
  if(typeof value!=='string')return value
  if(value.length<=maxChars)return value
  const retainer=new TextRetainer({kind:'headTail',headBytes:Math.max(64,Math.floor(maxChars*.75)),tailBytes:Math.max(32,Math.floor(maxChars*.25))})
  retainer.push(value)
  return retainer.finish().text+'\n[Excerpt; complete text remains in the run report]'
}

/** Model-facing projection of one run/read. Execution envelopes are the bulk of
 * the recorded report but almost never read inline in real workflows; they stay
 * in report.json and immutable archives and are addressed by pointer. The
 * projection keeps the facts decisions actually consume: builder __result__
 * (bounded), check facts, input versions and failure text. */
export function isolatedResultSummary(value:any) {
  const report=value.report, result=report?.result??value.progress
  const builder=result?.builder, checks=Array.isArray(result?.checks)?result.checks:[]
  const builderFacts=(()=>{
    if(!builder)return undefined
    const facts:any={ok:builder.ok}
    if(typeof builder.error==='string'&&builder.error)facts.error=excerptText(builder.error)
    if(builder.result!==undefined){
      const chars=JSON.stringify(builder.result)?.length??0
      facts.result=chars<=1200?builder.result:{detail_pointer:'/result/builder/result',omitted_chars:chars}
    }
    facts.detail_pointer='/result/builder'
    return facts
  })()
  const checkFacts=checks.map((check:any,index:number)=>({id:check.id,kind:check.kind,node:check.node,frame:check.frame,status:check.status,
    ...(check.geometry?{geometry:check.geometry}:{}),
    ...(check.artifact?{artifact:{file:check.artifact.file,bytes:check.artifact.bytes}}:{}),
    ...(check.error?{error:excerptText(check.error,200)}:{}),
    detail_pointer:'/result/checks/'+index+'/execution'}))
  const imageRows=Array.isArray(value.imageAttachments)?value.imageAttachments:[]
  const attachedImages=imageRows.filter((row:any)=>row.attachment),failedImages=imageRows.filter((row:any)=>!row.attachment)
  const inputs=Array.isArray(report?.inputs)?report.inputs:[]
  const observations=Array.isArray(report?.input_observations)?report.input_observations:[]
  const process=value.process
  const summary:any={kind:'isolated-houdini',run_directory:value.run_directory,report_path:value.report_path,
    ...(value.job_id?{job_id:value.job_id}:{}),
    ok:value.ok??report?.ok,finished:report?.finished??false,phase:report?.phase??result?.phase,
    ...(report?.worker?{worker:{status:report.worker.status,returncode:report.worker.returncode,
      ...(report.worker.error?{error:excerptText(report.worker.error,400)}:{})}}:{}),
    ...(builderFacts?{builder:builderFacts}:{}),
    checks:{count:checks.length,status_counts:inputStatusCounts(checkFacts),
      ...(checkFacts.length?{items:checkFacts}:{})},
    ...(report?{inputs_unchanged:report.inputs_unchanged,
      inputs:{count:inputs.length,...(inputs.length?{files:inputs.slice(0,12).map((row:any)=>row.file)}:{})},
      input_observations:{count:observations.length,status_counts:inputStatusCounts(observations),
        ...(observations.length?{detail_pointer:'/input_observations'}:{})}}:{}),
    ...(report?.inline_source?{inline_source:report.inline_source}:{}),
    ...(imageRows.length?{imageAttachments:{attached:attachedImages.length,failed:failedImages.length,
      ...(attachedImages.length?{images:attachedImages.slice(0,8).map((row:any)=>({from:path.basename(String(row.from??'')),...(row.image??{})}))}:{}),
      ...(failedImages.length?{failures:failedImages.slice(0,8).map((row:any)=>({from:path.basename(String(row.from??'')),error:excerptText(row.error,200)}))}:{}),
      scope:'Native attachments of this result, not a field of report.json; use these rows directly, not a read pointer.'}}:{}),
    ...(process&&(process.exit_code!==0||process.error)?{process:{exit_code:process.exit_code,
      ...(process.error?{error:excerptText(String(process.error),400)}:{})}}:{}),
    ...(report?.error??value.error?{error:excerptText(report?.error??value.error,1200)}:{}),
    ...(value.preflight?{preflight:value.preflight}:{}),
    ...(value.reported_status?{reported_status:value.reported_status}:{}),
    next_action:'Execution detail blocks are omitted here; read exact fields with operation="read" and select or pointer (for example "/result/builder/result", "/result/checks/0/execution"). Absence from this summary is not evidence of absence.'}
  if(Buffer.byteLength(JSON.stringify(summary))<=MAX_MODEL_TEXT_BYTES)return summary
  // Last-resort bound: drop values, never the addresses. Every remaining
  // pointer resolves against report.json; attachment rows are the only fact
  // that lives exclusively on the returned value.
  return {kind:summary.kind,run_directory:summary.run_directory,report_path:summary.report_path,
    ...(summary.job_id?{job_id:summary.job_id}:{}),ok:summary.ok,finished:summary.finished,phase:summary.phase,
    ...(summary.worker?{worker:summary.worker}:{}),
    ...(summary.builder?{builder:{ok:summary.builder.ok,...(summary.builder.error?{error:summary.builder.error}:{}),detail_pointer:'/result/builder'}}:{}),
    checks:{count:checks.length,status_counts:summary.checks.status_counts,detail_pointer:'/result/checks'},
    ...(report?{inputs_unchanged:summary.inputs_unchanged,inputs:summary.inputs,input_observations:summary.input_observations}:{}),
    ...(summary.imageAttachments?{imageAttachments:{attached:summary.imageAttachments.attached,
      failed:summary.imageAttachments.failed,scope:summary.imageAttachments.scope}}:{}),
    ...(summary.inline_source?{inline_source:summary.inline_source}:{}),
    ...(summary.error?{error:summary.error}:{}),
    presentation:{status:'summary',reason:'The compact receipt exceeded the model-text budget; counts and addresses are kept and no value is claimed absent.'},
    next_action:'Read exact fields with operation="read" and select or pointer; this summary omitted values, not facts.'}
}

/** One compact projection plus native images. Complete reports remain in the
 * run directory; pointer/select reads address any omitted field. */
export function renderIsolatedResult(value:any):ContentBlock[] {
  const blocks:ContentBlock[]=[{type:'text',
    text:JSON.stringify(value?.report||value?.progress?isolatedResultSummary(value):boundedFact(value,'',MAX_MODEL_TEXT_BYTES))}]
  blocks.push(...(value.imageAttachments??[]).filter((row:any)=>row.attachment)
    .map((row:any)=>({type:'image',attachment:row.attachment} as ContentBlock)))
  return blocks
}

/** Native jobs carry a locator and decision facts, never an unbounded copy of
 * the report. The same read operation supplies full canonical data and images. */
export function isolatedJobSummary(value:any) {
  const result=value.report?.result??value.progress
  const checkError=result?.checks?.find((check:any)=>check.error!=null||check.execution?.error!=null)
  const original=value.process?.error??value.report?.error??value.error??result?.builder?.error??
    checkError?.error??checkError?.execution?.error??
    (typeof value.process?.exit_code==='number'&&value.process.exit_code!==0?'Checker exit code: '+value.process.exit_code:null)
  let error=original
  if(typeof original==='string') {
    const retainer=new TextRetainer({kind:'headTail',headBytes:4096,tailBytes:2048});retainer.push(original)
    const retained=retainer.finish()
    if(retained.truncated)error=retained.text+(value.report?'\n[Error excerpt; full original in the run report]':'\n[Process error excerpt; no readable run report]')
  }
  return boundedFact(JSON.parse(JSON.stringify({run_directory:value.run_directory,report_path:value.report_path,ok:value.ok??(value.report?.finished===true?value.report.ok:undefined),error,
    inputs_unchanged:value.report?.inputs_unchanged??null,
    input_observations:{count:value.report?.input_observations?.length??0,
      status_counts:inputStatusCounts(value.report?.input_observations),pointer:'/input_observations'},
    next_action:value.preflight?'Input was rejected before a run report was created. Correct the stated preflight error before a new run.':
      'Use houdini_isolated(operation="read", output_dir=...) for the original report and native images. '
      +(value.report?.inputs_unchanged===false||value.report?.inputs_unchanged===null
        ?'Original input sources changed or could not be observed; read input_observations. Execution concerns the declared staged inputs; external effects are not restored.':'')})))
}

export async function readIsolatedRun(ctx:any,exec:any,output:string,attach=true,allowUndeclaredImageInput=false) {
  const directory=await localPath(ctx,exec,output)
  const reportPath=path.join(directory.local,'report.json'),report=await readJson(ctx,exec,reportPath,MAX_REPORT_BYTES)
  let progress:any
  if(report.finished!==true){
    try {progress=await readJson(ctx,exec,path.join(directory.local,'worker-result.json'),MAX_REPORT_BYTES)}
    catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error}
    if(progress&&progress.run_id!==report.run_id)throw Error('Run progress identity does not match the report')
  }
  const value:any={kind:'isolated-houdini',run_directory:directory.local,report_path:reportPath,
    report,...(progress?{progress}:{}),scope:SCOPE}
  const attachments=hostService(ctx,'attachments'),images:any[]=[]
  const result=report.result??progress,checks=result?.checks??[]
  const candidates=Array.isArray(result?.visual_artifacts)?result.visual_artifacts:
    checks.filter((row:any)=>row.status==='passed'&&row.artifact&&/\.(png|jpe?g|webp)$/i.test(row.artifact.file))
  if(attach&&candidates.length){
    const capability=await visualCapability(exec,ctx)
    let total=0
    for(const check of candidates){
      const artifact=check.artifact
      if(check.status!=='passed'){
        images.push({from:artifact?.file,error:check.error??'Image artifact was not retained',semantic_status:'unverified'})
        continue
      }
      try {
        if(capability.status==='unavailable'
            ||(capability.status==='unsupported'&&!allowUndeclaredImageInput))
          throw Error(capability.reason??'Image input unavailable')
        if(images.filter(row=>row.attachment).length>=attachments.imageLimits.maxImagesPerMessage)throw Error('Native image count limit reached')
        const filename=path.resolve(directory.local,artifact.file)
        if(!filename.startsWith(directory.local+path.sep))throw Error('Image artifact is outside its run directory')
        const {filesystem,target}=await localPath(ctx,exec,filename)
        const cap=Math.min(attachments.imageLimits.maxImageBytes,attachments.imageLimits.maxMessageImageBytes-total)
        if(cap<=0)throw Error('Native image byte limit reached')
        const data=Buffer.from(await filesystem.readBytes(target,exec.signal,cap))
        if(data.length!==artifact.bytes||createHash('sha256').update(data).digest('hex')!==artifact.sha256)throw Error('Image artifact differs from the recorded result')
        const mediaType=path.extname(filename).toLowerCase()==='.png'?'image/png':/\.webp$/i.test(filename)?'image/webp':'image/jpeg'
        const attachment=await attachments.saveImage({data,mediaType,name:path.basename(filename)})
        total+=attachment.bytes;images.push({from:filename,attachment,image:imageAttachmentFacts(attachment),semantic_status:'unverified',capability_status:capability.status})
      }catch(error){images.push({from:artifact.file,error:String(error),semantic_status:'unverified'})}
    }
  }
  return {...value,imageAttachments:images}
}

export async function executeIsolated(ctx:any,exec:any,args:IsolatedArgs,runtimeResolver:(exec:any,args:IsolatedArgs)=>Promise<IsolatedRuntime>,
  runner:IsolatedOptions['runner']=runIsolatedProcess,planner:typeof planIsolatedManifest=planIsolatedManifest) {
  if((args.operation??'run')==='read'){
    if(!args.output_dir)throw Error('operation=read requires the original absolute output_dir')
    const directory=await localPath(ctx,exec,args.output_dir)
    const reportPath=path.join(directory.local,'report.json')
    if(args.select!==undefined){
      if(args.pointer!==undefined||args.offset!==undefined)throw Error('select cannot be combined with pointer or offset; page an oversized selection separately')
      if(!Array.isArray(args.select)||args.select.length<1||args.select.length>16
        ||args.select.some(pointer=>typeof pointer!=='string')||new Set(args.select).size!==args.select.length)
        throw Error('select must contain 1..16 unique JSON Pointers')
      const limit=args.limit??6000
      if(!Number.isSafeInteger(limit)||limit<1||limit>16000)throw Error('limit must be 1..16000 characters')
      const report=await readJson(ctx,exec,reportPath,MAX_REPORT_BYTES)
      let remaining=limit
      const items=args.select.map(pointer=>{
        let value:unknown
        try {value=pointerValue(report,pointerKeys(pointer))}
        catch {return {pointer,status:'missing',error:'JSON Pointer field not found'}}
        const chars=JSON.stringify(value)?.length??0
        if(chars>remaining)return {pointer,status:'requires_pagination',total_chars:chars,read:{pointer,offset:0,limit}}
        remaining-=chars
        return {pointer,status:'available',value}
      })
      return {kind:'isolated-houdini-report-selection',run_directory:directory.local,report_path:reportPath,
        format:'json_selection',items,selected_value_chars:limit-remaining,scope:SCOPE,imageAttachments:[]}
    }
    if(args.pointer!==undefined||args.offset!==undefined||args.limit!==undefined){
      const pointer=args.pointer??'',offset=args.offset??0,limit=args.limit??6000
      if(!Number.isSafeInteger(offset)||offset<0||!Number.isSafeInteger(limit)||limit<1||limit>16000)
        throw Error('offset must be a nonnegative integer; limit must be 1..16000 characters')
      const report=await readJson(ctx,exec,reportPath,MAX_REPORT_BYTES)
      const text=JSON.stringify(pointerValue(report,pointerKeys(pointer)),null,2)
      if(offset>text.length)throw Error('offset exceeds selected JSON text length')
      const end=Math.min(offset+limit,text.length)
      return {kind:'isolated-houdini-report-page',run_directory:directory.local,report_path:reportPath,
        pointer,offset,total_chars:text.length,next_offset:end<text.length?end:null,
        format:'json_text_page',text:text.slice(offset,end),scope:SCOPE,imageAttachments:[]}
    }
    return readIsolatedRun(ctx,exec,args.output_dir,true,args.allow_undeclared_image_input===true)
  }
  const cwd=workspaceOf(exec)
  if(!cwd)throw Error('Isolated Houdini requires the DSH session workspace')
  const output=await localPath(ctx,exec,args.output_dir??path.join(projectDirectoryPath(cwd,'execution_run'),randomUUID()),true)
  let manifestBytes:Buffer,manifestBase:string,sourcePath:string|undefined
  if(typeof args.manifest==='string'){
    const source=await localPath(ctx,exec,args.manifest)
    manifestBytes=Buffer.from(await source.filesystem.readBytes(source.target,exec.signal,MAX_MANIFEST_BYTES))
    manifestBase=path.dirname(source.local);sourcePath=source.local
  }else{
    if(args.manifest===null||typeof args.manifest!=='object'||Array.isArray(args.manifest))
      throw Error('operation=run requires manifest as an absolute JSON manifest path or an inline manifest object')
    manifestBytes=Buffer.from(JSON.stringify(args.manifest))
    if(manifestBytes.length>MAX_MANIFEST_BYTES)throw Error('Inline manifest exceeds '+MAX_MANIFEST_BYTES+' bytes')
    // Inline manifests have no source folder: relative input paths anchor at
    // the DSH workspace, exactly as workflow/tool callers already resolve.
    manifestBase=cwd
  }
  const timeout=args.timeout_seconds??inputPolicy.defaultTimeoutSeconds,memory=args.memory_mb??inputPolicy.defaultMemoryMb
  if(!Number.isFinite(timeout)||timeout<=0||!Number.isSafeInteger(memory)||memory<=0)throw Error('timeout_seconds and memory_mb must be positive finite budgets')
  const runtime=await runtimeResolver(exec,args)
  for(const binary of [runtime.python,runtime.hython])if(!path.isAbsolute(binary)||(await fs.stat(binary)).isFile()!==true)throw Error('Selected Houdini runtime executable is missing: '+binary)
  let plan:IsolatedInputPlan
  try {plan=await planner(runtime,manifestBytes,exec.signal,{timeout,memory})}
  catch(error){
    exec.signal?.throwIfAborted()
    return {kind:'isolated-houdini',ok:false,phase:'preflight',error:String(error),
      preflight:{phase:'preflight',error:String(error)},scope:SCOPE}
  }
  const inputRoot=await localPath(ctx,exec,path.resolve(manifestBase,plan.input_root))
  let inputBytes=0
  for(const input of plan.files){
    const location=await localPath(ctx,exec,path.resolve(inputRoot.local,input.path))
    if(!location.filesystem.contains(inputRoot.target,location.target))throw Error('Manifest input resolves outside input_root')
    const stat=await location.filesystem.stat(location.target,exec.signal)
    if(!stat||stat.type!=='file')throw Error('Declared input is not a regular file: '+input.path)
    if(input.max_bytes!==undefined&&stat.size!==undefined&&stat.size>input.max_bytes)
      throw Error('Declared input exceeds '+input.max_bytes+' bytes: '+input.path)
    inputBytes+=stat.size??0
    if(inputBytes>plan.max_input_bytes)throw Error('Declared inputs exceed '+plan.max_input_bytes+' bytes')
  }
  const request={runtime,manifestSha256:plan.manifest_sha256,
    output:output.local,cancelFile:path.join(path.dirname(output.local),'.'+path.basename(output.local)+'.'+randomUUID()+'.cancel'),
    timeout:plan.budgets.timeout_seconds,memory:plan.budgets.memory_mb}
  // Only a reservation this invocation created is discarded; any directory with
  // evidence in it stays exactly as recorded.
  const discardEmptyReservation=async()=>{
    try {if((await fs.readdir(output.local)).length===0)await fs.rmdir(output.local)}catch{}
  }
  const run=async(signal:AbortSignal,onOutput?:(text:string)=>void)=>{
    signal.throwIfAborted()
    // DSH admits a background job before this callback. The Host reserves the
    // exact run directory atomically here, so two calls cannot both proceed to
    // the same destination; rejected admissions leave no run behind.
    await fs.mkdir(path.dirname(output.local),{recursive:true})
    try {await fs.mkdir(output.local)}
    catch(error){
      if((error as NodeJS.ErrnoException).code==='EEXIST')
        throw Error('Output directory already exists; read it with operation="read" or select a new run directory')
      throw error
    }
    let staging:string|undefined,process:IsolatedProcessResult
    try {
      let manifestPath:string
      if(sourcePath!==undefined)manifestPath=sourcePath
      else {
        // The checker re-verifies these exact Host-authorized bytes before it
        // stages inputs, then records the manifest (including inline code) in
        // request.json. The temporary copy is never execution evidence.
        staging=path.join(os.tmpdir(),'dsh-isolated-manifest-'+randomUUID()+'.json')
        try {await fs.writeFile(staging,manifestBytes,{mode:0o600})}
        catch(error){await discardEmptyReservation();throw error}
        manifestPath=staging
      }
      try {process=await runner!({...request,manifest:manifestPath,manifestBase,reserved:true,signal,onOutput})}
      catch(error){await discardEmptyReservation();throw error}
      // A cancelled caller still receives its terminal facts after the owned tree exits.
      const resultExec={...exec,signal:undefined}
      try {
        const value=await readIsolatedRun(ctx,resultExec,output.local,!args.background,args.allow_undeclared_image_input===true)
        return {...value,ok:value.report?.ok===true&&process.exit_code===0&&!process.error,process}
      }
      catch(error){
        const lines=(process.stdout??'').split(/\r?\n/).filter(Boolean)
        let preflight:any,reportedStatus:any
        for(const line of lines.reverse())try {
          const value=JSON.parse(line)
          if(value?.phase==='preflight'&&value.ok===false){preflight=value;break}
          if(typeof value?.run_id==='string'&&typeof value?.report==='string'
            &&path.resolve(value.report)===path.resolve(output.local,'report.json')){reportedStatus=value;break}
        }catch{}
        await discardEmptyReservation()
        return {kind:'isolated-houdini',ok:false,run_directory:output.local,report_path:path.join(output.local,'report.json'),process,
          ...(preflight?{preflight}:{}),...(reportedStatus?{reported_status:reportedStatus}:{}),
          error:preflight?.error??reportedStatus?.error??process.error??(process.stderr.trim()||String(error)),report_error:String(error),scope:SCOPE}
      }
    } finally {
      if(staging!==undefined)await fs.rm(staging,{force:true}).catch(()=>{})
    }
  }
  if(args.background){
    const jobs=hostService(ctx,'jobs')
    if(!jobs)throw Error('DSH background jobs are unavailable; run in the foreground')
    exec.signal?.throwIfAborted()
    const id=jobs.start({kind:'houdini',label:'独立 Houdini · '+(sourcePath?path.basename(sourcePath):'inline manifest'),owner:exec.agent.id,
      toolCall:{callId:exec.callId,rootCallId:exec.rootCallId??exec.callId},outputLimitBytes:16000,
      run:(job:any)=>{
        const controller=new AbortController()
        const done:Promise<JobOutcome>=run(controller.signal).then(value=>({
          status:value.report?.worker?.status==='cancelled'||value.report?.worker?.status==='cancelled_before_start'?'killed':value.ok===true?'completed':'failed',
          result:JSON.stringify(isolatedJobSummary(value)),
        }),error=>({status:'failed',detail:String(error)}))
        job.updateProgress('独立 hython 执行中')
        return {done,cancel:()=>controller.abort()}
      }})
    return {kind:'isolated-houdini',job_id:id,run_directory:output.local,report_path:path.join(output.local,'report.json'),
      next_action:'DSH job_output waits/collects; job_kill cancels this owned run. Then use operation=read for the report and native images.',scope:SCOPE}
  }
  return run(exec.signal??new AbortController().signal)
}

export function registerIsolatedTool(ctx:Context,connection:HoudiniConnection,options:IsolatedOptions={}) {
  const runtimeResolver=options.runtimeResolver??(async(exec:any,args:IsolatedArgs)=>{
    if(args.houdini_installation!==undefined)return isolatedInstallationRuntime(args.houdini_installation,exec.signal)
    if('resolve' in connection){
      if(!connection.resolveRuntime)throw Error('This Houdini connection has no recorded installation; specify houdini_installation')
      const {runtime,houdiniVersion}=await connection.resolveRuntime(exec)
      const version=runtime.pythonVersion.match(/^(\d+)\.(\d+)\.\d+$/)
      if(!version||Number(version[1])<3||Number(version[1])===3&&Number(version[2])<11)
        throw Error('The selected Houdini installation requires bundled Python 3.11 or newer')
      return {python:runtime.python,hfs:runtime.hfs,hython:path.join(runtime.hfs,'bin',process.platform==='win32'?'hython.exe':'hython'),houdini:houdiniVersion}
    }
    // Legacy fixed-Bridge configuration has no registry. Its ordinary online
    // metadata route remains available; explicit HFS above needs no live endpoint.
    const {bridge}=await new HoudiniToolRuntime(ctx,connection).target(exec,'read')
    const runtime=await resolveVideoRuntime('',{bridge,signal:exec.signal})
    return {python:runtime.python,hfs:runtime.hfs,hython:path.join(runtime.hfs,'bin',process.platform==='win32'?'hython.exe':'hython'),houdini:('houVersion'in runtime?String(runtime.houVersion):undefined)}
  })
  ctx.tools.register(defineTool({name:'houdini_isolated',description:HOUDINI_TOOLS.houdini_isolated.purpose+
    ' Load houdini-isolated-execution for the manifest and examples. run starts a new headless Houdini with injected verbs; read retrieves the recorded run and native images without connecting to live, returning a compact summary unless pointer/select asks for exact fields. manifest accepts an absolute path or an inline object whose code is executed directly, so a small experiment needs no manifest file. run reserves output_dir exclusively; read requires the exact directory returned earlier. Background runs use DSH job_output/job_kill.',
    parameters:{operation:{type:'string',enum:['run','read'],description:'Default run; read only retrieves a prior output_dir.'},
      manifest:{oneOf:[
        {type:'string',description:'Absolute JSON manifest path. Use a file when the saved manifest itself is reused across runs; otherwise the inline object avoids a separate write.'},
        {type:'object',description:'Inline manifest: the Host serializes these exact bytes, the same checker validates and stages them, and the run records them in request.json. Relative paths (including a relative input_root) resolve against the current DSH workspace.',
          properties:{
            hip:{type:'string',description:'Saved HIP copied into this run (relative to input_root); the script may prepare the copy.'},
            script:{type:'string',description:'Builder .py path at input_root; executed after an optional hip loads. Not combinable with code.'},
            code:{type:'string',description:'Inline Python builder executed in the injected verb environment after an optional hip loads; up to '+inputPolicy.maxInlineCodeBytes+' UTF-8 bytes. Staged as a generated .py input and recorded in request.json. Cannot combine with script.'},
            input_root:{type:'string',description:'Directory for hip/script/files; absolute or relative to the current DSH workspace for an inline manifest.'},
            files:{type:'array',description:'Additional inputs: safe relative names or {pattern:"cache/points.$F4.bgeo.sc",start:1,end:240,step:1} sequences; every expanded file is required and checked through DSH policy.'},
            checks:{type:'array',description:'Optional cook/cache/render checks with unique id, kind, node and frame; expect accepts points/primitives counts. Omitted checks only execute declared input.'}},
          additionalProperties:false}]},
      output_dir:{type:'string',description:'Optional absolute NEW run directory for run; default unique execution_run directory under the current DSH workspace. Reserved exclusively by this call: an existing or concurrently reserved directory is rejected, never moved or reused. read requires the exact directory returned by the original run.'},
      houdini_installation:{type:'string',description:'Optional explicit absolute Houdini installation directory (HFS). Otherwise use the selected scene\'s recorded installation even if live is offline; legacy fixed-Bridge connections obtain installation metadata online. No Host HFS or PATH fallback.'},
      background:{type:'boolean',description:'Default false. true returns a native DSH job_id immediately.'},
      allow_undeclared_image_input:{type:'boolean',description:'Only when the user explicitly confirms this exact route accepts images: attach images despite missing metadata and let the real model response decide. Not a bypass for an observed provider rejection.'},
      pointer:{type:'string',description:'Read only: JSON Pointer into report.json, for example /result/builder/result. Returns a bounded JSON text page without image attachments.'},
      offset:{type:'number',description:'Read only: zero-based character offset into the selected JSON text; default 0. Use next_offset for continuation.'},
      limit:{type:'number',description:'Read only: selected JSON text characters per page, 1..16000; default 6000.'},
      select:{type:'array',items:{type:'string'},description:'Read only: 1..16 unique JSON Pointers into report.json, for example "/result/builder/result" or "/result/checks/0/execution". Returns bounded exact values without image attachments; not combinable with pointer/offset.'},
      timeout_seconds:{type:'number',description:`Worker time budget in (0, ${inputPolicy.maxTimeoutSeconds}] seconds; default ${inputPolicy.defaultTimeoutSeconds}. Validated before job admission.`},
      memory_mb:{type:'number',description:`Integer process-tree memory budget ${inputPolicy.minMemoryMb}..${inputPolicy.maxMemoryMb} MiB; default ${inputPolicy.defaultMemoryMb}. Not GPU memory; validated before job admission.`}},
    output:{schema:{type:'json'},render:(_args,value)=>renderIsolatedResult(value),presentationMeta:(_args,value)=>({canonical:isolatedLogValue(value)})},
    presentCall:args=>({card:'generic',title:args.operation==='read'?'读取独立执行结果':'独立 Houdini 执行',kind:args.operation==='read'?'read':'execute',rawInput:args}),
    presentResult:(_args,result)=>{
      const value=(result.meta as any)?.canonical,report=value?.report??value?.report_summary
      const status=result.isError||value?.ok===false||report?.ok===false&&report?.finished?'失败'
        :value?.job_id?'已提交':report?.finished?'已完成':report?'执行中':'已返回'
      return {card:'generic',title:'独立 Houdini · '+status,content:result.content}
    },
    execute:async(args,exec)=>JSON.parse(JSON.stringify(await executeIsolated(ctx,exec,args as IsolatedArgs,runtimeResolver,options.runner,options.planner)))}))
}
