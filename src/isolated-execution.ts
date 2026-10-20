/** One-shot Houdini computation. DSH owns agents/jobs; the bundled checker owns run facts. */
import fs from 'node:fs/promises'
import {readFileSync} from 'node:fs'
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
import {visualCapability} from './image-output.js'
import {HOUDINI_TOOLS} from './tool-catalog.js'
import {executionStdout} from './tool-output.js'
import {projectDirectoryPath} from './project-paths.js'

const CHECKER=fileURLToPath(new URL('../tools/isolated-houdini-check.py',import.meta.url))
const SCOPE='Independent hython run only. Results describe the declared inputs and checks, not the current live scene or visual quality. Python/callback and external-file side effects are not a filesystem sandbox.'
const detailPolicy=JSON.parse(readFileSync(new URL('../houdini/result-detail-policy.json',import.meta.url),'utf8'))
if(detailPolicy.schemaVersion!==1||!Number.isSafeInteger(detailPolicy.maxArchiveBytes)||detailPolicy.maxArchiveBytes<=0)
  throw Error('Unsupported result detail policy')
const MAX_REPORT_BYTES:number=detailPolicy.maxArchiveBytes
const MAX_MANIFEST_BYTES=4*1024*1024
export interface IsolatedRuntime {python:string;hython:string;hfs:string;houdini?:string}
export interface IsolatedArgs {
  operation?:'run'|'read';manifest?:string;output_dir?:string;background?:boolean
  houdini_installation?:string
  timeout_seconds?:number;memory_mb?:number
}
export interface IsolatedProcessRequest {
  runtime:IsolatedRuntime;manifest:string;output:string;cancelFile:string;timeout:number;memory:number
  signal:AbortSignal;onOutput?:(text:string)=>void
}
export interface IsolatedProcessResult {exit_code:number|null;cancel_requested:boolean;stdout?:string;stderr:string;error?:string}
export interface IsolatedOptions {
  runtimeResolver?:(exec:any,args:IsolatedArgs)=>Promise<IsolatedRuntime>
  runner?:(request:IsolatedProcessRequest)=>Promise<IsolatedProcessResult>
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

/** Cancellation reaches the checker first; its Windows Job reaps the exact owned worker tree. */
export function runIsolatedProcess(request:IsolatedProcessRequest):Promise<IsolatedProcessResult> {
  request.signal.throwIfAborted()
  return new Promise((resolve,reject)=>{
    const env=localVideoEnvironment()
    for(const key of ['HOUDINI_LICENSE_SERVER','SESI_LMHOST'])if(process.env[key])env[key]=process.env[key]
    const child=spawn(request.runtime.python,[CHECKER,'--trusted','--manifest',request.manifest,
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
    const {verbs:_,...visible}=value
    return {...visible,stdout:executionStdout(value),...(!value.details?{details_pointer:pointer}:{})}
  }
  return {...report,worker:report.worker?{...report.worker,output:undefined}:undefined,
    result:result?{...result,builder:execution(result.builder,'/result/builder'),
      checks:result.checks?.map((check:any,index:number)=>({...check,
        execution:execution(check.execution,`/result/checks/${index}/execution`)}))}:undefined}
}

export async function readIsolatedRun(ctx:any,exec:any,output:string,attach=true) {
  const directory=await localPath(ctx,exec,output)
  const reportPath=path.join(directory.local,'report.json'),report=await readJson(ctx,exec,reportPath,MAX_REPORT_BYTES)
  let progress:any
  if(report.finished!==true){
    try {progress=await readJson(ctx,exec,path.join(directory.local,'worker-result.json'),MAX_REPORT_BYTES)}
    catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error}
    if(progress&&progress.run_id!==report.run_id)throw Error('Run progress identity does not match the report')
  }
  const value:any={kind:'isolated-houdini',run_directory:directory.local,report_path:reportPath,
    report:reportView(report),...(progress?{progress:reportView({result:progress}).result}:{}),scope:SCOPE}
  const attachments=hostService(ctx,'attachments'),images:any[]=[]
  const checks=(report.result??progress)?.checks??[]
  const candidates=checks.filter((row:any)=>row.status==='passed'&&row.artifact&&/\.(png|jpe?g|webp)$/i.test(row.artifact.file))
  if(attach&&candidates.length){
    const capability=await visualCapability(exec,ctx)
    let total=0
    for(const check of candidates){
      const artifact=check.artifact
      try {
        if(capability.status!=='available')throw Error(capability.reason??'Image input unavailable')
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
        total+=attachment.bytes;images.push({from:filename,attachment,semantic_status:'unverified'})
      }catch(error){images.push({from:artifact.file,error:String(error),semantic_status:'unverified'})}
    }
  }
  return {...value,imageAttachments:images}
}

export async function executeIsolated(ctx:any,exec:any,args:IsolatedArgs,runtimeResolver:(exec:any,args:IsolatedArgs)=>Promise<IsolatedRuntime>,
  runner:IsolatedOptions['runner']=runIsolatedProcess) {
  if((args.operation??'run')==='read'){
    if(!args.output_dir)throw Error('operation=read requires the original absolute output_dir')
    return readIsolatedRun(ctx,exec,args.output_dir)
  }
  const cwd=workspaceOf(exec)
  if(!cwd)throw Error('Isolated Houdini requires the DSH session workspace')
  const output=await localPath(ctx,exec,args.output_dir??path.join(projectDirectoryPath(cwd,'execution_run'),randomUUID()),true)
  if(await fs.lstat(output.local).catch((error:NodeJS.ErrnoException)=>{if(error.code!=='ENOENT')throw error;return null}))throw Error('Output directory already exists; read it or select a new run directory')
  const source=await localPath(ctx,exec,args.manifest??'')
  const manifest=await readJson(ctx,exec,source.local,MAX_MANIFEST_BYTES)
  if(!manifest||typeof manifest!=='object'||Array.isArray(manifest))throw Error('Manifest must be a JSON object')
  if(manifest.input_root!==undefined&&(typeof manifest.input_root!=='string'||!manifest.input_root.trim()))
    throw Error('input_root must name an absolute path or a path relative to the manifest')
  if(manifest.files!==undefined&&!Array.isArray(manifest.files))throw Error('Manifest files must be an array of relative input paths')
  const inputRoot=await localPath(ctx,exec,path.resolve(path.dirname(source.local),manifest.input_root??'.'))
  const inputs=[...(manifest.hip!==undefined?[manifest.hip]:[]),...(manifest.script!==undefined?[manifest.script]:[]),...(manifest.files??[])]
  for(const input of inputs){
    if(typeof input!=='string'||!input||path.isAbsolute(input)||/[\\<>:"|?*\x00-\x1f$%]/.test(input)||input.split('/').some(part=>!part||part==='.'||part==='..'))
      throw Error('Manifest inputs must be safe relative files within input_root, using / separators')
    const location=await localPath(ctx,exec,path.resolve(inputRoot.local,input))
    if(!location.filesystem.contains(inputRoot.target,location.target))throw Error('Manifest input resolves outside input_root')
    // Resolve through DSH's read policy before the checker copies declared inputs.
    await location.filesystem.stat(location.target,exec.signal)
  }
  const timeout=args.timeout_seconds??120,memory=args.memory_mb??4096
  if(!Number.isFinite(timeout)||timeout<=0||!Number.isSafeInteger(memory)||memory<=0)throw Error('timeout_seconds and memory_mb must be positive finite budgets')
  const runtime=await runtimeResolver(exec,args)
  for(const binary of [runtime.python,runtime.hython])if(!path.isAbsolute(binary)||(await fs.stat(binary)).isFile()!==true)throw Error('Selected Houdini runtime executable is missing: '+binary)
  const request={runtime,manifest:source.local,output:output.local,cancelFile:path.join(path.dirname(output.local),'.'+path.basename(output.local)+'.'+randomUUID()+'.cancel'),timeout,memory}
  const run=async(signal:AbortSignal,onOutput?:(text:string)=>void)=>{
    signal.throwIfAborted()
    // DSH admits a background job before this callback. The checker alone
    // creates the exclusive run directory; rejected admissions leave no run.
    await fs.mkdir(path.dirname(output.local),{recursive:true})
    const process=await runner!({...request,signal,onOutput})
    // A cancelled caller still receives its terminal facts after the owned tree exits.
    const resultExec={...exec,signal:undefined}
    try {
      const value=await readIsolatedRun(ctx,resultExec,output.local,!args.background)
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
      return {kind:'isolated-houdini',ok:false,run_directory:output.local,report_path:path.join(output.local,'report.json'),process,
        ...(preflight?{preflight}:{}),...(reportedStatus?{reported_status:reportedStatus}:{}),
        error:preflight?.error??reportedStatus?.error??process.error??(process.stderr.trim()||String(error)),report_error:String(error),scope:SCOPE}
    }
  }
  if(args.background){
    const jobs=hostService(ctx,'jobs')
    if(!jobs)throw Error('DSH background jobs are unavailable; run in the foreground')
    exec.signal?.throwIfAborted()
    const id=jobs.start({kind:'houdini',label:'独立 Houdini · '+path.basename(source.local),owner:exec.agent.id,
      toolCall:{callId:exec.callId,rootCallId:exec.rootCallId??exec.callId},outputLimitBytes:16000,
      run:(job:any)=>{
        const controller=new AbortController()
        const done:Promise<JobOutcome>=run(controller.signal).then(value=>({
          status:value.report?.worker?.status==='cancelled'||value.report?.worker?.status==='cancelled_before_start'?'killed':value.ok===true?'completed':'failed',
          result:JSON.stringify({run_directory:output.local,report_path:path.join(output.local,'report.json'),
            ok:value.ok??false,error:value.process?.error??value.report?.error??value.error??(value.process?.exit_code!==0?'Checker exit code: '+value.process?.exit_code:null),
            next_action:value.preflight?'Input was rejected before a run report was created. Correct the stated preflight error before a new run.':
              'Use houdini_isolated(operation="read", output_dir=...) for full results and native images.'}),
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
    ' Load houdini-isolated-execution for the manifest and examples. run starts a new headless Houdini with injected verbs; read retrieves the recorded run and native images without connecting to live. Background runs use DSH job_output/job_kill.',
    parameters:{operation:{type:'string',enum:['run','read'],description:'Default run; read only retrieves a prior output_dir.'},
      manifest:{type:'string',description:'Absolute JSON manifest with hip and/or script: a script after hip runs setup on that copied scene, then checks. Optional input_root is absolute or relative to the manifest; hip/script/files are safe relative names beneath it. Optional cook/cache/render checks; omitted checks only execute the declared input.'},
      output_dir:{type:'string',description:'Optional absolute NEW run directory for run; default unique execution_run directory under the current DSH workspace. read requires the exact directory returned by the original run. Existing or explicit paths are never moved.'},
      houdini_installation:{type:'string',description:'Optional explicit absolute Houdini installation directory (HFS). Otherwise use the selected scene\'s recorded installation even if live is offline; legacy fixed-Bridge connections obtain installation metadata online. No Host HFS or PATH fallback.'},
      background:{type:'boolean',description:'Default false. true returns a native DSH job_id immediately.'},
      timeout_seconds:{type:'number',description:'Positive worker time budget, default 120 seconds.'},
      memory_mb:{type:'number',description:'Positive integer process-tree committed-memory budget, default 4096 MiB; not GPU memory.'}},
    output:{schema:{type:'json'},render:(_args,value)=>{
      const data=value as any
      return [{type:'text',text:JSON.stringify(data)},...(data.imageAttachments??[]).filter((row:any)=>row.attachment)
        .map((row:any)=>({type:'image',attachment:row.attachment} as ContentBlock))]
    },presentationMeta:(_args,value)=>({canonical:value})},
    presentCall:args=>({card:'generic',title:args.operation==='read'?'读取独立执行结果':'独立 Houdini 执行',kind:args.operation==='read'?'read':'execute',rawInput:args}),
    presentResult:(_args,result)=>({card:'generic',title:'独立 Houdini 结果',content:result.content}),
    execute:async(args,exec)=>JSON.parse(JSON.stringify(await executeIsolated(ctx,exec,args as IsolatedArgs,runtimeResolver,options.runner)))}))
}
