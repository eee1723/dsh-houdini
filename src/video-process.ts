/** Offline video/evidence operations use the same bundled CLI through DSH file policy.
 * No shell, credentials, arbitrary executable or alternative evidence ledger. */
import fs from 'node:fs/promises'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {spawn,execFile,type ChildProcess} from 'node:child_process'
import {promisify} from 'node:util'
import type {Context} from '@deepseek-ai/cordis'
import {defineTool} from '@deepseek-ai/dsh-tools'
import {hostService} from './api-route.js'
import {workspaceOf} from './tool-runtime.js'
import {VIDEO_TOOLS} from './tool-catalog.js'
import {videoRuntime} from './video-runtime.js'

export const VIDEO_LOCAL_OPERATIONS=['ingest','prepare','export','frames','scan','review','changes','context',
  'notes-init','check-notes','review-packet','index-init','index-link','check-index','read-index','read-transcript',
  'query-notes','export-brief'] as const
const READS=new Set(['check-index','read-index','read-transcript','query-notes'])
const PATHS=new Set(['input','video','audio','work','frames_dir','transcript','context','notes','index','font_file'])
const MEDIA=new Set(['ingest','prepare','frames','scan','review','changes','review-packet'])
const PROBE=new Set(['ingest','prepare','frames','scan','review','index-init'])
const SCRIPT=fileURLToPath(new URL('../skills/houdini-video-tutorial/scripts/video_tutorial.py',import.meta.url))
type Options=Record<string,string|number|boolean|(string|number)[]>
export interface LocalVideoArgs {operation:typeof VIDEO_LOCAL_OPERATIONS[number];options:Options}
export type LocalVideoRuntime=ReturnType<typeof videoRuntime>
export type LocalVideoRuntimeResolver=(exec:any)=>Promise<LocalVideoRuntime>
export interface LocalVideoProcessRequest {executable:string;args:string[];env:NodeJS.ProcessEnv;cwd:string;work?:string;signal?:AbortSignal}
export type LocalVideoRunner=(request:LocalVideoProcessRequest)=>Promise<{code:number|null;stdout:string;stderr:string;cancelled:boolean;termination_error?:string}>

/** A worker owns only the PID it wrote. A different worker's lock is never removed. */
export async function releaseVideoChildLock(work:string|undefined,pid:number|undefined){
  if(!work||!pid)return
  const filename=path.join(work,'.lock')
  try{
    if((await fs.lstat(filename)).isSymbolicLink())return
    if((await fs.readFile(filename,'utf8')).trim()===String(pid))await fs.unlink(filename)
  }catch{/* Missing/changed/unreadable lock is not authority to remove anything else. */}
}

async function terminateMediaTree(child:ChildProcess){
  if(!child.pid||child.exitCode!==null||child.signalCode!==null)return
  if(process.platform==='win32'){
    await promisify(execFile)(path.join(process.env.SystemRoot??'C:/Windows','System32','taskkill.exe'),
      ['/PID',String(child.pid),'/T','/F'],{windowsHide:true})
  }else process.kill(-child.pid,'SIGKILL')
}

export const runLocalVideoProcess:LocalVideoRunner=request=>new Promise((resolve,reject)=>{
  request.signal?.throwIfAborted()
  const child=spawn(request.executable,request.args,{cwd:request.cwd,env:request.env,shell:false,windowsHide:true,
    detached:process.platform!=='win32',stdio:['ignore','pipe','pipe']})
  let stdout='',stderr='',overflow=false,cancelled=false,termination:Promise<void>|undefined,terminationError:string|undefined
  const stop=()=>{termination??=terminateMediaTree(child).catch(()=>{terminationError='Could not confirm media process-tree termination';child.kill()})}
  const cancel=()=>{cancelled=true;stop()}
  request.signal?.addEventListener('abort',cancel,{once:true})
  child.stdout.setEncoding('utf8');child.stderr.setEncoding('utf8')
  child.stdout.on('data',(data:string)=>{if(stdout.length+data.length>1_000_000){overflow=true;stop()}else stdout+=data})
  child.stderr.on('data',(data:string)=>{if(stderr.length+data.length>64_000){overflow=true;stop()}else stderr+=data})
  child.once('error',error=>{request.signal?.removeEventListener('abort',cancel);reject(Error('Cannot start the selected tutorial runtime: '+(error as NodeJS.ErrnoException).code))})
  child.once('close',async code=>{
    request.signal?.removeEventListener('abort',cancel)
    await termination
    await releaseVideoChildLock(request.work,child.pid)
    resolve({code,stdout,stderr:overflow?'Local video output exceeded its budget; inspect retained files.':stderr,cancelled,
      ...(terminationError?{termination_error:terminationError}:{})})
  })
  if(request.signal?.aborted)cancel()
})

/** Only OS essentials reach this offline process; DSH provider credentials never do. */
export function localVideoEnvironment(environment:NodeJS.ProcessEnv=process.env):NodeJS.ProcessEnv {
  const allowed=new Set(['systemroot','windir','comspec','path','pathext','temp','tmp','localappdata','appdata','userprofile','home'])
  return {...Object.fromEntries(Object.entries(environment).filter(([name])=>allowed.has(name.toLowerCase()))),PYTHONUTF8:'1'}
}

export async function processLocalVideo(ctx:any,exec:any,args:LocalVideoArgs,
  resolveRuntime:LocalVideoRuntimeResolver,runner:LocalVideoRunner=runLocalVideoProcess) {
  if(!VIDEO_LOCAL_OPERATIONS.includes(args.operation))throw Error('Unsupported local video operation; cloud transcription uses video_transcribe')
  if(!args.options||typeof args.options!=='object'||Array.isArray(args.options)||Object.keys(args.options).length>32)
    throw Error('options must be a flat object of bundled CLI options')
  const filesystem=hostService(ctx,'fs'),policyService=hostService(ctx,'sandboxPolicy'),cwd=workspaceOf(exec)
  if(!cwd||!filesystem||!policyService)throw Error('Local video operations require a DSH workspace, filesystem and file policy')
  const policy=policyService.resolve({session:exec.agent.session}),readonly=READS.has(args.operation)
  if(!readonly&&policy.mode==='read-only')throw Error('Current DSH file policy is read-only; this operation writes tutorial evidence')
  if(!readonly&&(typeof args.options.output!=='string'||!path.isAbsolute(args.options.output)))
    throw Error('Use an absolute new output directory for this local video operation')
  if(readonly&&'output' in args.options)throw Error('Read operations return their result; they do not redirect files')
  const argv=[SCRIPT,args.operation],paths:{target:any;local:string;input:string}[]=[]
  for(const [key,value] of Object.entries(args.options)){
    if(!/^[a-z][a-z0-9_]*$/.test(key)||['ffmpeg','ffprobe','python','key_env','allow_upload','endpoint','protocol','model'].includes(key))
      throw Error('Runtime, cloud and executable options cannot be supplied to video_process')
    const flag='--'+key.replace(/_/g,'-')
    if(typeof value==='boolean') {if(value)argv.push(flag);continue}
    const values=Array.isArray(value)?value:[value]
    if(!values.length||values.length>100||values.some(v=>typeof v==='number'?!Number.isFinite(v):typeof v!=='string'||!v.length||v.startsWith('-')||v.includes('\0')))
      throw Error('Local video option values must be finite numbers or nonempty text; flags are supplied by name')
    if(PATHS.has(key)||key==='output'){
      if(typeof value!=='string'||!path.isAbsolute(value))throw Error(key+' must be an absolute path')
      const target=await filesystem.resolve(value,{cwd,signal:exec.signal}),local=filesystem.processPath(target)
      if(filesystem.processPathFromHostPath(local)!==local)throw Error('Local video requires a local/shared Host path')
      if(key==='output'||args.operation==='export'&&key==='work'){
        const root=await filesystem.resolve(policy.workspaceRoot,{signal:exec.signal})
        if(policy.mode!=='danger-full-access'&&!filesystem.contains(root,target))throw Error(key==='work'
          ?'Export creates a temporary input lock; work must be within the current writable workspace':'Video output is outside the current writable workspace')
      }
      if(key==='output'){
        // Existing directories belong to their current task; the CLI never overwrites them.
        try {await fs.lstat(local);throw Error('Video output directory already exists; use the existing evidence or a new directory')}
        catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error}
      }
      paths.push({target,local,input:value});argv.push(flag,local)
    } else if(key==='region'){
      for(const entry of values)argv.push(flag,String(entry))
    } else argv.push(flag,...values.map(String))
  }
  const runtime=await resolveRuntime(exec)
  if(!runtime.python)throw Error('Current selected Houdini Python is unavailable; inspect video_models runtime diagnostics')
  if(MEDIA.has(args.operation))argv.push('--ffmpeg',runtime.ffmpeg)
  if(PROBE.has(args.operation))argv.push('--ffprobe',runtime.ffprobe)
  // Re-resolve after runtime discovery, before launch; do not act on moved destinations.
  for(const item of paths){
    const current=await filesystem.resolve(item.input,{cwd,signal:exec.signal})
    if(current.targetKey!==item.target.targetKey)throw Error('Video path changed before execution')
  }
  exec.signal?.throwIfAborted()
  const facts={operation:args.operation,runtime,output:args.options.output??null,cloud_request:false,readonly}
  try{
    const result=await runner({executable:runtime.python,args:argv,env:localVideoEnvironment(),cwd,signal:exec.signal,
      ...(args.operation==='export'?{work:paths.find(item=>item.input===args.options.work)?.local}:{})})
    const rows=result.stdout.split(/\r?\n/).filter(Boolean).map(line=>{try{return JSON.parse(line)}catch{return null}}).filter(row=>row&&typeof row==='object')
    const ok=result.code===0&&!result.cancelled&&!result.termination_error&&rows.length>0
    return {...facts,ok,status:ok?'completed':result.cancelled?'cancelled':'worker_failed',exit_code:result.code,
      result:rows.at(-1)??null,progress:rows.slice(0,-1),...(!ok?{error:result.stderr.trim().slice(0,4000)||'Local video worker did not return a completed result.'}:{}),
      ...(result.termination_error?{termination_error:result.termination_error}:{}),
      scope:'Bundled offline media/evidence operation only. Facts, hashes and files remain owned by the Python script; no semantic certification or Houdini scene modification.'}
  }catch(error){return {...facts,ok:false,status:exec.signal?.aborted?'cancelled':'worker_not_started',error:(error as Error).message}}
}

export function registerLocalVideoTool(ctx:Context,resolveRuntime:LocalVideoRuntimeResolver){
  ctx.tools.register(defineTool({name:'video_process',description:VIDEO_TOOLS.video_process.purpose+
    ' Runs only the bundled offline CLI without a shell or credentials. Use underscore option names and absolute paths from the tutorial skill; read operations return JSON directly, write operations use an explicit new workspace directory. No transcribe/network request, arbitrary executable, permission escalation or automatic retry.',
    parameters:{operation:{type:'string',required:true,enum:[...VIDEO_LOCAL_OPERATIONS],description:'Offline operation; source and evidence formats are documented in houdini-video-tutorial.'},
      options:{type:'object',required:true,description:'Flat CLI options using underscore names. Examples: review {video,output,start,duration,interval}; read-index {index,module,section,offset,limit,max_chars}; query-notes {index,subject,field,view}. Python validates the operation-specific options.',additionalProperties:true}},
    output:{schema:{type:'json'},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}],presentationMeta:(_args,value)=>({canonical:value})},
    presentCall:args=>({card:'generic',kind:READS.has(args.operation)?'read':'execute',title:VIDEO_TOOLS.video_process.label,rawInput:args}),
    execute:(args,exec)=>processLocalVideo(ctx,exec,args as LocalVideoArgs,resolveRuntime)}))
}
