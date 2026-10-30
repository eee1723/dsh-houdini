/** Native Desktop plugin integration. The local channel accepts only Houdini
 * menu/launch receipts; it never exposes DSH owner credentials or generic RPC. */
import type {Context} from '@deepseek-ai/cordis'
import fs from 'node:fs/promises'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {createServer,type Server} from 'node:http'
import {randomBytes,randomUUID,timingSafeEqual} from 'node:crypto'
import {spawn,execFile,type ChildProcess} from 'node:child_process'
import {promisify} from 'node:util'
import {desktopPaths} from './desktop-paths.js'
import type {ExecutorController} from './executor-controller.js'
import {HoudiniBridge} from './bridge.js'
import {projectedExecutorState} from './executor-identity-projection.js'
import {targetMatchesRecord,targetSnapshot,type ExecutorRecord} from './executor-routing.js'
import {acquireDesktopLease,processStarted as systemProcessStarted} from './desktop-process.js'
import {ComponentInstallation,type ComponentUpdate} from './component-installation.js'

const execute=promisify(execFile)
const id=()=>randomUUID().replaceAll('-','')
const ID=/^[0-9a-f]{32}$/
const key=(value:string)=>process.platform==='win32'?path.resolve(value).toLowerCase():path.resolve(value)
async function sameInstallationPath(actual:string,expected:string):Promise<boolean> {
  if(key(actual)===key(expected))return true
  // Houdini can publish Windows 8.3 paths even when Desktop launched the long
  // path. Compare the actual installation without changing its reported facts.
  const [actualPath,expectedPath]=await Promise.all([fs.realpath(actual),fs.realpath(expected)])
  return key(actualPath)===key(expectedPath)
}
const pluginRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
export interface HoudiniInstallation {hfs:string;version:string;series:string;executable:string}
export interface DesktopSelection {workspaceId?:string;sessionId:string;executorId:string;source:'menu'|'launch';launchId?:string}
export interface HelperInstallResult {ok:true;helperId:string;helperRoot:string;requiresRestart:true;
  migration:{reportPath:string|null;disabledCount:number;reviewCount:number};message:string}
type LaunchStage='launching'|'capturing'|'registering'|'binding'
type LaunchReceipt={executorId:string;registrationId:string;expectedHip:string;runtimeId:string;sceneEpoch:string;sceneId:string|null}
type LaunchRuntime={child?:ChildProcess;probe?:Promise<string|null>;binding?:Promise<unknown>;abort?:AbortController;committed?:boolean;stopBeforeAdmission?:boolean}
type Ticket={id:string;generation:string;hfs:string;houdiniVersion:string;hip:string|null;workspace:string;pid?:number;processStarted?:string;
  selectionRevision:number;callback?:string;stage:LaunchStage;phase:'preparing'|'waiting'|'ready'|'error'|'detached';message?:string;sessionId:string;
  result?:DesktopSelection;createdAt:number;receipt?:LaunchReceipt;bootstrapRetired?:boolean}
type ProcessProbe=(pid:number,hfs:string)=>Promise<string|null>
type ProcessState='alive'|'exited'|'reused'|'unknown'
class LaunchRejected extends Error {}
class LaunchNotReady extends Error {}
function processObservation(pid:number|undefined,baseline:string|null|undefined,current:string|null):ProcessState {
  if(!pid)return 'unknown'
  if(baseline&&current!==null)return current===baseline?'alive':'reused'
  try {process.kill(pid,0)}catch(error){if((error as NodeJS.ErrnoException).code==='ESRCH')return 'exited'}
  return 'unknown'
}

function restoreTicket(value:any,identifier:string):Ticket {
  const absolute=(field:string)=>typeof value[field]==='string'&&path.isAbsolute(value[field])
  const phases=['preparing','waiting','ready','error','detached'],stages=['launching','capturing','registering','binding']
  if(!value||typeof value!=='object'||value.id!==identifier||!ID.test(identifier)||!ID.test(value.generation)
    ||!(value.schemaVersion===undefined||value.schemaVersion===1||value.schemaVersion===2)||!absolute('hfs')||!absolute('workspace')
    ||typeof value.houdiniVersion!=='string'||!/^2[12]\.0\.\d+$/.test(value.houdiniVersion)
    ||value.hip!==null&&(!absolute('hip')||!/^\.hip(?:lc|nc)?$/i.test(path.extname(value.hip)))
    ||value.pid!==undefined&&(!Number.isInteger(value.pid)||value.pid<=0)
    ||value.processStarted!==undefined&&(typeof value.processStarted!=='string'||!/^\d+$/.test(value.processStarted))
    ||!Number.isSafeInteger(value.selectionRevision)||value.selectionRevision<0
    ||!Number.isFinite(value.createdAt)||value.createdAt<=0||!phases.includes(value.phase)
    ||!stages.includes(value.stage||'launching')||typeof value.sessionId!=='string'||!value.sessionId||value.sessionId.length>256
    ||value.message!==undefined&&(typeof value.message!=='string'||value.message.length>4000))throw Error('Invalid Houdini launch ticket')
  if(value.phase==='ready'&&(!value.result||value.result.source!=='launch'||value.result.launchId!==identifier
    ||value.result.sessionId!==value.sessionId||!ID.test(value.result.executorId)))throw Error('Invalid completed Houdini launch ticket')
  const receipt=value.receipt
  if(receipt&&(!['executorId','registrationId','runtimeId','sceneEpoch'].every(field=>ID.test(receipt[field]))
    ||receipt.sceneId!==null&&!ID.test(receipt.sceneId)||typeof receipt.expectedHip!=='string'||!path.isAbsolute(receipt.expectedHip)))throw Error('Invalid Houdini launch receipt')
  return {id:identifier,generation:value.generation,hfs:value.hfs,houdiniVersion:value.houdiniVersion,hip:value.hip,
    workspace:value.workspace,pid:value.pid,processStarted:value.processStarted,selectionRevision:value.selectionRevision,
    callback:typeof value.callback==='string'?value.callback:undefined,receipt,stage:value.stage||'launching',phase:value.phase,
    message:value.message,sessionId:value.sessionId,result:value.result,createdAt:value.createdAt,bootstrapRetired:value.bootstrapRetired===true}
}

/** One unacknowledged navigation intent, not a session/history database. */
export class DesktopIntents {
  private sequence=0
  private selection:DesktopSelection|null=null
  private readonly listeners=new Set<()=>void>()
  publish(value:DesktopSelection) {this.selection=value;this.sequence++;for(const wake of this.listeners)wake();return this.sequence}
  acknowledge(sequence:number) {if(sequence===this.sequence)this.selection=null}
  async read(after:number,signal:AbortSignal) {
    signal.throwIfAborted()
    if(after===this.sequence)await new Promise<void>((resolve,reject)=>{
      const complete=()=>{clearTimeout(timer);this.listeners.delete(complete);signal.removeEventListener('abort',abort);resolve()}
      const abort=()=>{complete();reject(signal.reason)}
      const timer=setTimeout(complete,25000)
      this.listeners.add(complete);signal.addEventListener('abort',abort,{once:true})
    })
    signal.throwIfAborted()
    return {sequence:this.sequence,selection:this.selection}
  }
}

export async function discoverHoudini():Promise<HoudiniInstallation[]> {
  if(process.platform!=='win32')return []
  const script=`$ErrorActionPreference='Stop'; $roots=@($env:HFS); foreach($view in @('Registry64','Registry32')) { try { $base=[Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine',$view); $top=$base.OpenSubKey('SOFTWARE\\Side Effects Software'); if($top) { foreach($n in $top.GetSubKeyNames()) { if($n -like 'Houdini *') { $child=$top.OpenSubKey($n); $roots+=$child.GetValue('InstallPath'); $child.Dispose() } }; $top.Dispose() }; $base.Dispose() } catch {} }; $standard=Join-Path $env:ProgramFiles 'Side Effects Software'; if(Test-Path -LiteralPath $standard) { $roots+=Get-ChildItem -LiteralPath $standard -Directory | Select-Object -ExpandProperty FullName }; $rows=@(); foreach($root in ($roots | Where-Object {$_} | Sort-Object -Unique)) { $exe=Join-Path $root 'bin/houdini.exe'; if(Test-Path -LiteralPath $exe -PathType Leaf) { $v=(Get-Item -LiteralPath $exe).VersionInfo; if($v.FileMajorPart -in 21,22 -and $v.FileMinorPart -eq 0) { $build=if($v.FileBuildPart){$v.FileBuildPart}else{$v.FilePrivatePart}; $rows+=@{hfs=[IO.Path]::GetFullPath($root);executable=$exe;series=\"$($v.FileMajorPart).$($v.FileMinorPart)\";version=\"$($v.FileMajorPart).$($v.FileMinorPart).$build\"} } } }; ConvertTo-Json -InputObject @($rows) -Compress`
  const result=await execute(path.join(process.env.SystemRoot||'C:/Windows','System32/WindowsPowerShell/v1.0/powershell.exe'),
    ['-NoProfile','-NonInteractive','-Command',script],{windowsHide:true,timeout:15000,maxBuffer:128000})
  const rows=JSON.parse(result.stdout.replace(/^\uFEFF/,''))
  if(!Array.isArray(rows))throw Error('Houdini 安装查询没有返回有效列表。')
  return rows.filter(row=>row&&['hfs','executable'].every(field=>typeof row[field]==='string'&&path.isAbsolute(row[field]))
    &&/^2[12]\.0\.\d+$/.test(row.version)).sort((a,b)=>b.version.localeCompare(a.version,undefined,{numeric:true}))
}

export class DesktopIntegration {
  readonly generation=id()
  readonly paths=desktopPaths()
  readonly intents=new DesktopIntents()
  private readonly token=randomBytes(32).toString('hex')
  private readonly lifetime=new AbortController()
  private readonly tickets=new Map<string,Ticket>()
  private readonly ticketWrites=new Map<string,Promise<void>>()
  private readonly runtime=new Map<string,LaunchRuntime>()
  private readonly requests=new Set<Promise<void>>()
  private projectTail:Promise<unknown>=Promise.resolve()
  private readonly menuRequests=new Map<string,{signature:string;promise:Promise<DesktopSelection>}>()
  private server?:Server
  private lease?:Awaited<ReturnType<typeof acquireDesktopLease>>
  private preparation?:Promise<HelperInstallResult>
  private readonly components=new ComponentInstallation(this.lifetime.signal)
  private port=0
  constructor(private readonly ctx:Context,private readonly targets:ExecutorController,
    private readonly installations=discoverHoudini,private readonly processStarted:ProcessProbe=systemProcessStarted,
    private readonly launchProcess:typeof spawn=spawn,private readonly helperInstaller?:()=>Promise<HelperInstallResult>) {
    if(targets.registry)this.paths.registry=targets.registry
  }

  async start() {
    await fs.mkdir(this.paths.root,{recursive:true,mode:0o700})
    this.lease=await acquireDesktopLease(this.paths.root)
    try {await this.restoreTickets()}catch(error){await this.dispose();throw error}
    try {
      this.server=createServer((request,response)=>{
        const work=(async()=>{
          response.setHeader('content-type','application/json; charset=utf-8')
          const expected=Buffer.from('Bearer '+this.token),actual=Buffer.from(request.headers.authorization||'')
          if(request.method!=='POST'||request.headers.origin||actual.length!==expected.length||!timingSafeEqual(actual,expected)) {
            response.writeHead(401);response.end(JSON.stringify({ok:false,error:'Unauthorized Houdini menu request'}));return
          }
          if(request.headers.host!==`127.0.0.1:${this.port}`)throw Error('Invalid local Host')
          let bytes=0,text=''
          for await(const chunk of request){bytes+=chunk.length;if(bytes>16384)throw Error('Menu request is too large');text+=chunk.toString()}
          const payload=JSON.parse(text||'{}')
          let value:unknown
          if(request.url==='/status'&&Object.keys(payload).length===0)value={generation:this.generation}
          else if(request.url==='/open-workspace')value=await this.menu(payload)
          else if(request.url==='/launch-attached')value=await this.attached(payload)
          else if(request.url==='/launch-failed')value=await this.failed(payload)
          else if(request.url==='/launch-progress')value=await this.launchProgress(payload)
          else if(request.url==='/ticket-current')value=await this.ticketCurrent(payload)
          else throw Error('Unsupported Houdini menu action')
          response.end(JSON.stringify({ok:true,value}))
        })().catch(error=>{response.statusCode=error instanceof LaunchNotReady?503:400;response.end(JSON.stringify({ok:false,error:String(error.message||error)}))})
        this.requests.add(work)
        void work.finally(()=>this.requests.delete(work)).catch(error=>this.ctx.logger.warn(String(error)))
      })
      await new Promise<void>((resolve,reject)=>{this.server!.once('error',reject);this.server!.listen(0,'127.0.0.1',resolve)})
      this.port=(this.server.address() as {port:number}).port
      const temporary=this.paths.descriptor+'.'+this.generation+'.tmp'
      await fs.writeFile(temporary,JSON.stringify({schemaVersion:1,pid:process.pid,generation:this.generation,port:this.port,
        token:this.token,pluginRoot,executorRegistry:this.paths.registry,launchesRoot:this.paths.launches}),{mode:0o600,flag:'wx'})
      await fs.rename(temporary,this.paths.descriptor)
    }catch(error){await this.dispose();throw error}
  }
  async dispose() {
    this.lifetime.abort(Error('Houdini Desktop plugin unloaded'))
    for(const runtime of this.runtime.values())runtime.abort?.abort(Error('Houdini Desktop plugin unloaded'))
    if(this.server){this.server.closeAllConnections();await new Promise<void>(resolve=>this.server!.close(()=>resolve()))}
    await Promise.allSettled([...this.requests])
    await this.projectTail.catch(()=>{})
    await this.preparation?.catch(()=>{})
    await Promise.allSettled([...this.runtime.values()].map(runtime=>runtime.binding).filter(Boolean))
    await Promise.allSettled([...this.ticketWrites.values()])
    try {const descriptor=JSON.parse(await fs.readFile(this.paths.descriptor,'utf8'));if(descriptor.generation===this.generation)await fs.unlink(this.paths.descriptor)}catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')this.ctx.logger.warn(String(error))}
    if(this.lease){await this.lease.close();this.lease=undefined}
  }
  private live(ticket:Ticket):LaunchRuntime {
    let runtime=this.runtime.get(ticket.id)
    if(!runtime){runtime={};this.runtime.set(ticket.id,runtime)}
    return runtime
  }
  private ticketIdentity(ticket:Ticket):Promise<string|null> {
    const runtime=this.live(ticket)
    if(!ticket.pid||!ticket.processStarted&&!runtime.child)return Promise.resolve(null)
    if(runtime.probe)return runtime.probe
    const probe=(async()=>{
      try {
        const value=await this.processStarted(ticket.pid!,ticket.hfs)
        if(value!==null&&!/^\d+$/.test(value))throw Error('Invalid Houdini process birth fact')
        // Only a child still held by this Host can acquire its first baseline.
        // A restored PID without a baseline is deliberately never adopted.
        if(value!==null&&!ticket.processStarted&&runtime.child?.exitCode===null&&!this.lifetime.signal.aborted) {
          ticket.processStarted=value;await this.saveTicket(ticket)
        }
        return value
      }catch(error){this.ctx.logger.warn('Houdini process identity unavailable: '+String(error));return null}
    })()
    runtime.probe=probe
    void probe.finally(()=>{if(runtime.probe===probe)runtime.probe=undefined})
    return probe
  }
  private async ticketProcessState(ticket:Ticket):Promise<ProcessState> {
    const runtime=this.live(ticket)
    if(runtime.child&&runtime.child.exitCode!==null)return 'exited'
    if(runtime.child&&!ticket.processStarted)await this.ticketIdentity(ticket)
    const started=ticket.processStarted?await this.ticketIdentity(ticket):null
    return processObservation(ticket.pid,ticket.processStarted,started)
  }
  private async registeredProcessState(record:ExecutorRecord):Promise<ProcessState> {
    let current:string|null=null
    if(record.processStarted)try {current=await this.processStarted(record.pid,record.runtime?.hfs??'')}
    catch(error){this.ctx.logger.warn('Houdini process identity unavailable: '+String(error))}
    return processObservation(record.pid,record.processStarted,current)
  }
  private async retireTicket(ticket:Ticket) {
    await this.ticketWrites.get(ticket.id)?.catch(()=>{})
    if(this.lifetime.signal.aborted)return
    const root=await fs.lstat(this.paths.launches).catch(()=>null)
    if(!root?.isDirectory()||root.isSymbolicLink())return
    if(ticket.bootstrapRetired)return
    if(ticket.phase!=='ready') {
      ticket.phase='error';ticket.message='原启动进程已结束，此请求不会再次创建窗口。'
      await this.saveTicket(ticket)
    }
    this.runtime.delete(ticket.id)
    const startup=path.join(this.paths.launches,ticket.id)
    const source='from dsh_workbench_entry import after_ui_ready\nafter_ui_ready()\n'
    try {
      const top=await fs.lstat(startup)
      if(!top.isDirectory()||top.isSymbolicLink())return
      for(const version of ['3.11','3.13']) {
        const directory=path.join(startup,'python'+version+'libs'),file=path.join(directory,'uiready.py')
        const stat=await fs.lstat(directory).catch(()=>null)
        if(!stat?.isDirectory()||stat.isSymbolicLink())continue
        const hook=await fs.lstat(file).catch(()=>null)
        if(hook?.isFile()&&!hook.isSymbolicLink()&&await fs.readFile(file,'utf8')===source)await fs.unlink(file)
        await fs.rmdir(directory).catch(()=>{})
      }
      await fs.rmdir(startup).catch(()=>{})
    }catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')this.ctx.logger.warn(String(error))}
    // A small terminal receipt preserves request idempotence across reloads;
    // only the expendable bootstrap is retired, never the operation's identity.
    ticket.bootstrapRetired=true;await this.saveTicket(ticket)
  }
  private async restoreTickets() {
    let files:string[]
    try {files=await fs.readdir(this.paths.launches)}catch(error){if((error as NodeJS.ErrnoException).code==='ENOENT')return;throw error}
    const tickets:Ticket[]=[]
    for(const file of files.filter(file=>ID.test(file.slice(0,-5))&&file.endsWith('.json')).sort()) {
      try {
        const filename=path.join(this.paths.launches,file),stat=await fs.lstat(filename)
        if(!stat.isFile()||stat.isSymbolicLink()||stat.size>32768)throw Error('Invalid Houdini launch ticket file')
        const text=await fs.readFile(filename,'utf8'),ticket=restoreTicket(JSON.parse(text),file.slice(0,-5))
        tickets.push(ticket)
      }catch(error){this.ctx.logger.warn('Preserve unread Houdini launch ticket '+file+': '+String(error))}
    }
    for(const ticket of tickets)this.tickets.set(ticket.id,ticket)
    // Loading the plugin never waits for every old process or performs HOM.
    // Only confirmed ended operations have their own small bootstrap retired.
    void (async()=>{
      for(const ticket of tickets) {
        if(this.lifetime.signal.aborted)return
        if(ticket.bootstrapRetired)continue
        const state=await this.ticketProcessState(ticket)
        if(state==='exited'||state==='reused')await this.retireTicket(ticket)
      }
    })().catch(error=>this.ctx.logger.warn(String(error)))
  }
  private async ticketCurrent(input:unknown) {
    const data=input as any
    if(!data||Object.keys(data).sort().join(',')!=='hfs,hipIsNew,hipPath,id,pid,processStarted'||!ID.test(data.id)
      ||!Number.isSafeInteger(data.pid)||data.pid<=0||typeof data.processStarted!=='string'||!/^\d+$/.test(data.processStarted)
      ||typeof data.hfs!=='string'||!path.isAbsolute(data.hfs)||typeof data.hipPath!=='string'||!path.isAbsolute(data.hipPath)
      ||typeof data.hipIsNew!=='boolean')throw Error('无效的启动接入身份。')
    const ticket=this.requireTicket({id:data.id})
    if(ticket.phase==='error')throw Error(ticket.message||'原启动已结束，未接管此窗口。')
    const process=await this.ticketProcessState(ticket)
    if(process==='unknown'&&this.live(ticket).child)throw new LaunchNotReady('原启动进程身份正在确认，请稍后重试。')
    if(process!=='alive'||ticket.pid!==data.pid||ticket.processStarted!==data.processStarted
      ||!(await sameInstallationPath(data.hfs,ticket.hfs))||(ticket.hip?(data.hipIsNew||key(ticket.hip)!==key(data.hipPath)):!data.hipIsNew))
      throw Error('当前 Houdini 与原启动身份或工程不一致，未接管。')
    return {id:ticket.id,phase:ticket.phase,workspace:ticket.workspace,hfs:ticket.hfs,hip:ticket.hip}
  }
  private async launchProgress(input:unknown) {
    const data=input as any
    if(!data||Object.keys(data).sort().join(',')!=='id,stage'||!ID.test(data.id)
      ||!['capturing','registering','binding'].includes(data.stage))throw Error('无效的启动进度回执。')
    const ticket=this.tickets.get(data.id)
    if(!ticket||!['waiting','detached'].includes(ticket.phase)||await this.ticketProcessState(ticket)!=='alive')throw Error('无法确认原启动进程，未更新启动状态。')
    const stages=['launching','capturing','registering','binding']
    if(stages.indexOf(data.stage)<stages.indexOf(ticket.stage))return {}
    ticket.stage=data.stage as LaunchStage
    await this.saveTicket(ticket)
    return {}
  }
  private async menu(input:unknown):Promise<DesktopSelection> {
    const data=input as any
    if(!data||Object.keys(data).sort().join(',')!=='executorId,expectedHip,registrationId,requestId'
      ||![data.executorId,data.registrationId,data.requestId].every(value=>typeof value==='string'&&ID.test(value))
      ||typeof data.expectedHip!=='string'||!path.isAbsolute(data.expectedHip))throw Error('无效的 Houdini 菜单请求。')
    const signature=JSON.stringify([data.executorId,data.registrationId,key(data.expectedHip)])
    const existing=this.menuRequests.get(data.requestId)
    if(existing){if(existing.signature!==signature)throw Error('同一个菜单请求标识不能指向另一个工程。');return existing.promise}
    const pending=(async()=>{const result=await this.targets.openWorkspace(data,this.lifetime.signal) as Omit<DesktopSelection,'source'>
      const selection={...result,source:'menu' as const};this.intents.publish(selection);return selection})()
    this.menuRequests.set(data.requestId,{signature,promise:pending})
    // Bounded transport-retry receipts; no durable mirror of native sessions.
    if(this.menuRequests.size>64)this.menuRequests.delete(this.menuRequests.keys().next().value!)
    try{return await pending}catch(error){this.menuRequests.delete(data.requestId);throw error}
  }
  async presence() {
    const records=await this.targets.getRouter(this.paths.registry).directory.list()
    const observe=async(record:typeof records[number])=>{
      let status='offline',contractVersion:number|undefined,verbCatalogHash:string|undefined,activeRequests=0,activeJobs=0,
        componentUpdate:ComponentUpdate|undefined
      const process=record.state==='registered'?await this.registeredProcessState(record):'exited'
      if(record.state==='registered'&&process!=='exited'&&process!=='reused')try {
        const bridge=new HoudiniBridge(record.bridge_url,3000,record.executor_id,this.lifetime.signal)
        const health=await bridge.observeExecutor(AbortSignal.any([this.lifetime.signal,AbortSignal.timeout(3000)]))
        status=health.runtimeId===record.runtime_id&&health.sceneEpoch===record.scene_epoch?'online':'changed'
        contractVersion=health.executionContractVersion
        verbCatalogHash=health.verbCatalog?.hash
        if(status==='online')componentUpdate=await this.components.observe(health,record.installation)
        activeRequests=health.activeRequests??0;activeJobs=health.activeJobs??0
      }catch{status='unknown'}
      return {executorId:record.executor_id,runtimeId:record.runtime_id,sceneEpoch:record.scene_epoch,
        sceneId:record.scene_id,hipPath:record.hip_path,status,observedAt:Date.now(),candidate:record,
        ownerSessionId:record.task_id,activeRequests,activeJobs,busy:Boolean(activeRequests||activeJobs),contractVersion,verbCatalogHash,componentUpdate}
    }
    const observed=[]
    for(let offset=0;offset<records.length;offset+=8) {
      this.lifetime.signal.throwIfAborted()
      observed.push(...await Promise.all(records.slice(offset,offset+8).map(observe)))
    }
    return observed
  }
  async listInstallations(){return this.installations()}
  private installHelper():Promise<HelperInstallResult> {
    if(this.preparation)return this.preparation
    const pending=(async()=>{
      this.lifetime.signal.throwIfAborted()
      if(this.helperInstaller)return this.helperInstaller()
      if(process.platform!=='win32')throw Error('当前本端安装器支持 Windows Houdini 21/22。')
      const installer=path.join(pluginRoot,'installer/install.ps1');await fs.access(installer)
      const {stdout}=await execute(path.join(process.env.SystemRoot||'C:/Windows','System32/WindowsPowerShell/v1.0/powershell.exe'),
        ['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',installer],
        {windowsHide:true,timeout:120000,maxBuffer:128000,signal:this.lifetime.signal})
      const marker='DSH_HOUDINI_INSTALL_RESULT=',line=stdout.split(/\r?\n/).reverse().find(value=>value.startsWith(marker))
      if(!line)throw Error('本机组件安装未返回可核对结果；没有启动 Houdini，请查看安装器诊断。')
      const result=JSON.parse(line.slice(marker.length)) as HelperInstallResult
      if(result.ok!==true||!path.isAbsolute(result.helperRoot)||!/^[0-9a-f]{16}$/.test(result.helperId)||typeof result.message!=='string'
        ||!result.migration||!Number.isSafeInteger(result.migration.disabledCount)||!Number.isSafeInteger(result.migration.reviewCount))
        throw Error('本机组件安装回执无效，没有启动 Houdini。')
      return result
    })()
    this.preparation=pending
    void pending.finally(()=>{if(this.preparation===pending)this.preparation=undefined}).catch(()=>{})
    return pending
  }
  async prepareBridge(input:unknown) {
    const data=input as {sessionId?:string}
    if(!data||Object.keys(data).join(',')!=='sessionId'||typeof data.sessionId!=='string')throw Error('请选择 Houdini 模式的对话。')
    await this.houdiniSession(data.sessionId)
    try{return await this.installHelper()}finally{this.components.invalidate()}
  }
  intent(after:number,signal:AbortSignal){return this.intents.read(after,AbortSignal.any([signal,this.lifetime.signal]))}
  private async houdiniSession(sessionId:string) {
    const resolved=await this.ctx.sessionController.resolveAgent(sessionId as any)
    if('error' in resolved||this.ctx.sessionProjections.stateOf(resolved.agent.session,'agentPreset')!=='houdini')throw Error('请选择 Houdini 模式的对话。')
    if(resolved.agent.status!=='idle')throw Error('请在当前对话完成后打开或新建工程。')
    return resolved.agent
  }
  project(input:unknown,signal:AbortSignal) {
    const requestId=(input as {requestId?:unknown})?.requestId
    if(typeof requestId==='string'&&ID.test(requestId)&&!this.runtime.has(requestId))this.runtime.set(requestId,{})
    const bounded=AbortSignal.any([signal,this.lifetime.signal])
    const operation=this.projectTail.catch(()=>{}).then(()=>{bounded.throwIfAborted();return this.openProject(input,bounded)})
    this.projectTail=operation
    void operation.finally(()=>{if(typeof requestId==='string'&&!this.tickets.has(requestId))this.runtime.delete(requestId)}).catch(()=>{})
    return operation
  }
  private async openProject(input:unknown,signal:AbortSignal) {
    const data=input as any
    if(!data||Object.keys(data).some(field=>!['action','sessionId','hfs','hip','requestId'].includes(field))
      ||!['open','new','reopen'].includes(data.action)||typeof data.sessionId!=='string'
      ||data.requestId!==undefined&&(typeof data.requestId!=='string'||!ID.test(data.requestId)))throw Error('请选择 Houdini 对话和工程操作。')
    const agent=await this.houdiniSession(data.sessionId)
    const state=projectedExecutorState(this.ctx,agent.session)
    let hip=data.hip
    if(data.action==='reopen') {
      hip=state.project?.hipPath
      if(!hip||state.project?.hipIsNew!==false)throw Error('这段对话没有已保存的工程。')
    }
    if(data.action!=='new') {
      if(typeof hip!=='string'||!path.isAbsolute(hip)||!/^\.hip(?:lc|nc)?$/i.test(path.extname(hip))||!(await fs.stat(hip)).isFile())throw Error('请选择现有 HIP 文件的完整路径。')
      hip=await fs.realpath(hip)
    }else hip=null
    const available=await this.installations()
    const selected=available.find(item=>typeof data.hfs==='string'&&key(item.hfs)===key(data.hfs))
    if(!selected)throw Error('请选择已发现的受支持 Houdini 安装。')
    signal.throwIfAborted()
    const sameIntent=(ticket:Ticket)=>ticket.sessionId===agent.id&&ticket.houdiniVersion===selected.version&&key(ticket.hfs)===key(selected.hfs)
      &&(ticket.hip===null?hip===null:hip!==null&&key(ticket.hip)===key(hip))
    const retried=data.requestId&&this.tickets.get(data.requestId)
    if(retried) {
      if(!sameIntent(retried))throw Error('同一个启动请求标识不能用于另一个对话、安装或工程。')
      return this.status({id:retried.id})
    }
    for(const ticket of this.tickets.values()) {
      if(!['preparing','waiting','detached'].includes(ticket.phase))continue
      const same=sameIntent(ticket)&&ticket.selectionRevision===state.selectionRevision
      if(same) {
        const observed=await this.status({id:ticket.id})
        if(observed.phase!=='error'||!ticket.bootstrapRetired)return observed
        continue
      }
      if(hip&&ticket.hip&&key(ticket.hip)===key(hip)) {
        const process=await this.ticketProcessState(ticket)
        if(process==='alive'||process==='unknown')throw Error('该工程已有启动请求，请继续原请求或从对应窗口接入；未重复打开。')
      }
    }
    const records=await this.targets.getRouter(this.paths.registry).directory.list()
    let existing:ExecutorRecord|undefined
    if(hip) {
      const matches:ExecutorRecord[]=[]
      for(const record of records.filter(record=>record.state==='registered'&&record.hip_path&&key(record.hip_path)===key(hip))) {
        const process=await this.registeredProcessState(record)
        if(process!=='exited'&&process!=='reused')matches.push(record)
      }
      if(matches.length>1)throw Error('该工程已在多个 Houdini 窗口中打开，请选择要绑定的窗口。')
      if(matches.length) {
        const record=matches[0]
        if(record.houdini_version!==selected.version)throw Error('该工程已在其他 Houdini 版本打开，请选择原版本或从原窗口接入。')
        existing=record
      }
    }
    const identifier=data.requestId??id(),workspace=hip?path.dirname(hip):path.join(this.paths.root,'workspaces','unsaved-'+identifier)
    const ticket:Ticket={id:identifier,generation:this.generation,hfs:selected.hfs,houdiniVersion:selected.version,hip,workspace,
      phase:this.runtime.get(identifier)?.stopBeforeAdmission?'detached':'preparing',stage:'launching',sessionId:agent.id,selectionRevision:state.selectionRevision,createdAt:Date.now()}
    this.tickets.set(identifier,ticket)
    delete this.live(ticket).stopBeforeAdmission
    const filename=path.join(this.paths.launches,identifier+'.json')
    let output:fs.FileHandle|undefined
    try {
      await fs.mkdir(workspace,{recursive:true})
      await fs.mkdir(this.paths.launches,{recursive:true,mode:0o700})
      await this.saveTicket(ticket)
      if(existing) {
        ticket.pid=existing.pid;ticket.processStarted=existing.processStarted??undefined
        if(ticket.phase==='preparing')ticket.phase='waiting'
        ticket.stage='binding'
        ticket.receipt=await this.validateRecord(ticket,existing)
        await this.saveTicket(ticket)
        await this.complete(ticket)
        return this.status({id:ticket.id})
      }
      ticket.message='正在准备 Houdini 连接组件…'
      await this.saveTicket(ticket)
      const preparation=await this.installHelper()
      signal.throwIfAborted()
      ticket.message='正在打开 Houdini…'
      const startup=path.join(this.paths.launches,identifier)
      for(const version of ['3.11','3.13']) {
        const directory=path.join(startup,'python'+version+'libs');await fs.mkdir(directory,{recursive:true})
        await fs.writeFile(path.join(directory,'uiready.py'),'from dsh_workbench_entry import after_ui_ready\nafter_ui_ready()\n')
      }
      const environment={...process.env}
      for(const field of Object.keys(environment))if(/^(QT_|QTWEBENGINE_|QML|PYSIDE|SHIBOKEN)/i.test(field)
        ||['PYTHONHOME','PYTHONPATH','NODE_OPTIONS','NODE_PATH','DSH_HOUDINI_MANAGED_CONTEXT','DSH_HOUDINI_WORKBENCH_CONTEXT','DSH_HOUDINI_EXECUTOR_ID','DSH_HOUDINI_BRIDGE_URL'].includes(field))delete environment[field]
      environment.HFS=selected.hfs
      environment.HOUDINI_PATH=[startup,path.join(pluginRoot,'houdini'),process.env.HOUDINI_PATH||'&'].join(path.delimiter)
      environment.PYTHONPATH=path.join(pluginRoot,'houdini/python3.11libs')
      environment.DSH_HOUDINI_DESKTOP_DESCRIPTOR=this.paths.descriptor
      environment.DSH_HOUDINI_LAUNCH_TICKET=filename
      environment.DSH_HOUDINI_EXECUTOR_REGISTRY=this.paths.registry
      environment.PYTHONDONTWRITEBYTECODE='1'
      output=await fs.open(path.join(this.paths.launches,identifier+'.log'),'a')
      signal.throwIfAborted()
      const child=this.launchProcess(selected.executable,['-foreground',...(hip?[hip]:[])],{cwd:path.join(selected.hfs,'bin'),env:environment,
        detached:true,windowsHide:true,stdio:['ignore',output.fd,output.fd]})
      // Houdini is an independent application; closing Desktop must not keep
      // its Host alive or terminate the artist's newly opened scene.
      child.unref()
      this.live(ticket).child=child;ticket.pid=child.pid
      if(ticket.pid&&ticket.phase==='preparing')ticket.phase='waiting'
      child.once('error',error=>{ticket.phase='error';ticket.message=error.message;void this.saveTicket(ticket).catch(failure=>this.ctx.logger.warn(String(failure)))})
      child.once('exit',code=>{if(ticket.phase==='waiting'){ticket.phase='error';ticket.message='Houdini 在接入完成前退出：'+String(code);void this.saveTicket(ticket).catch(failure=>this.ctx.logger.warn(String(failure)))}})
      await this.ticketIdentity(ticket)
      await this.saveTicket(ticket)
    }catch(error) {
      // This call knows submission never reached a child when no PID/handle
      // exists. Such failures must not poison the conversation's next action.
      ticket.phase='error';ticket.message=String((error as Error).message||error).slice(0,4000)
      await this.saveTicket(ticket).catch(failure=>this.ctx.logger.warn(String(failure)))
      throw error
    }finally{await output?.close()}
    return this.status({id:identifier})
  }
  private saveTicket(ticket:Ticket):Promise<void> {
    const pending=(async()=>{
      await this.ticketWrites.get(ticket.id)?.catch(()=>{})
      if(ticket.bootstrapRetired&&ticket.phase!=='ready'&&ticket.phase!=='error')throw Error('Retired launch cannot be resubmitted')
      const filename=path.join(this.paths.launches,ticket.id+'.json'),temporary=filename+'.'+id()+'.tmp'
      await fs.writeFile(temporary,JSON.stringify({schemaVersion:2,...ticket}),{mode:0o600,flag:'wx'})
      await fs.rename(temporary,filename)
    })()
    this.ticketWrites.set(ticket.id,pending)
    void pending.finally(()=>{if(this.ticketWrites.get(ticket.id)===pending)this.ticketWrites.delete(ticket.id)}).catch(()=>{})
    return pending
  }
  private requireTicket(input:unknown):Ticket {
    const data=input as any
    if(!data||Object.keys(data).join(',')!=='id'||!ID.test(data.id))throw Error('无效的启动请求。')
    const ticket=this.tickets.get(data.id)
    if(!ticket)throw Error('未找到原启动请求；请从对应 Houdini 的 Open Workspace 接入，未自动换绑。')
    return ticket
  }
  private signature(receipt:Pick<LaunchReceipt,'executorId'|'registrationId'|'expectedHip'>) {
    return JSON.stringify({executorId:receipt.executorId,registrationId:receipt.registrationId,expectedHip:key(receipt.expectedHip)})
  }
  private async validateRecord(ticket:Ticket,record:ExecutorRecord):Promise<LaunchReceipt> {
    const process=await this.ticketProcessState(ticket)
    if(process==='unknown')throw new LaunchNotReady('原 Houdini 进程身份暂时无法确认，未绑定。')
    if(process!=='alive')throw new LaunchRejected('原 Houdini 已结束或 PID 已被复用，未绑定。')
    if(record.pid!==ticket.pid||record.processStarted!==ticket.processStarted||record.houdini_version!==ticket.houdiniVersion
      ||!record.runtime||!(await sameInstallationPath(record.runtime.hfs,ticket.hfs))
      ||!(await sameInstallationPath(record.runtime.executable,path.join(ticket.hfs,'bin/houdini.exe')))
      ||!record.hip_path||(ticket.hip?key(ticket.hip)!==key(record.hip_path):record.hip_is_new!==true)
      ||!record.scene_epoch||!ID.test(record.scene_epoch))throw new LaunchRejected('启动回执与原进程、版本或工程不一致，未绑定。')
    const receipt={executorId:record.executor_id,registrationId:record.registration_id,expectedHip:record.hip_path,
      runtimeId:record.runtime_id,sceneEpoch:record.scene_epoch,sceneId:record.scene_id??null}
    if(ticket.receipt&&(this.signature(ticket.receipt)!==this.signature(receipt)||ticket.receipt.runtimeId!==receipt.runtimeId
      ||ticket.receipt.sceneEpoch!==receipt.sceneEpoch||ticket.receipt.sceneId!==receipt.sceneId))throw new LaunchRejected('原启动的工程已重开或切换，未改用后来打开的工程。')
    return receipt
  }
  private async observeReceipt(ticket:Ticket):Promise<LaunchReceipt|undefined> {
    const directory=this.targets.getRouter(this.paths.registry).directory
    let record:ExecutorRecord|undefined
    if(ticket.receipt)record=await directory.find(ticket.receipt.executorId)
    else {
      // This is one explicitly pending launch, not a history/scene guess: the
      // original OS process and installation must match before we inspect it.
      const records=await directory.list()
      const matches:ExecutorRecord[]=[]
      for(const row of records) {
        if(row.pid!==ticket.pid||row.processStarted!==ticket.processStarted||!row.runtime)continue
        if(await sameInstallationPath(row.runtime.hfs,ticket.hfs))matches.push(row)
      }
      if(matches.length>1)throw Error('原启动进程有多个登记，尚未自动绑定。')
      record=matches[0]
    }
    if(!record)return
    const receipt=await this.validateRecord(ticket,record)
    ticket.receipt=receipt;await this.saveTicket(ticket)
    return receipt
  }
  private complete(ticket:Ticket):Promise<any> {
    if(ticket.phase==='ready')return Promise.resolve(ticket.result)
    if(ticket.phase==='detached')return Promise.resolve({phase:'detached'})
    const runtime=this.live(ticket)
    if(runtime.binding)return runtime.binding
    const abort=new AbortController();runtime.abort=abort;runtime.committed=false
    const signal=AbortSignal.any([abort.signal,this.lifetime.signal])
    const pending=(async()=>{
      try {
        signal.throwIfAborted()
        const receipt=await this.observeReceipt(ticket)
        signal.throwIfAborted()
        if(!receipt)return {phase:'waiting'}
        const resolved=await this.ctx.sessionController.resolveAgent(ticket.sessionId as any)
        signal.throwIfAborted()
        if('error' in resolved||this.ctx.sessionProjections.stateOf(resolved.agent.session,'agentPreset')!=='houdini'
          ||this.ctx.workspaceRegistry?.archivedSessionIds.includes(ticket.sessionId as any))throw new LaunchRejected('原对话已不可用、改为其他模式或归档，未改用另一段对话。')
        const agent=resolved.agent,state=projectedExecutorState(this.ctx,agent.session)
        let result:Omit<DesktopSelection,'source'>
        if(state.selectionRevision!==ticket.selectionRevision) {
          const selected=state.selectedTarget
          if(!selected||selected.executor_id!==receipt.executorId||selected.runtime_id!==receipt.runtimeId
            ||selected.scene_epoch!==receipt.sceneEpoch||selected.scene_id!==receipt.sceneId)
            throw new LaunchRejected('等待启动时用户已更改工程，本次迟到回执未覆盖新选择。')
          // The exact scene is already selected in the native Session (e.g.
          // commit succeeded just before Host exit). Observe it; never rebind.
          await this.targets.getRouter(this.paths.registry).inspectSelectedTarget(selected,signal)
          const workspace=this.ctx.workspaceRegistry?.list().find(item=>item.sessionIds.includes(agent.id))
          result={sessionId:agent.id,executorId:selected.executor_id,...(workspace?{workspaceId:workspace.id}:{})}
          runtime.committed=true
        }else {
          if(agent.status!=='idle') {
            ticket.phase='detached';ticket.message='原对话正在执行，已保留原窗口。对话完成后可继续连接。'
            await this.saveTicket(ticket);return {phase:'detached',message:ticket.message}
          }
          ticket.stage='binding'
          result=await this.targets.openWorkspace({executorId:receipt.executorId,registrationId:receipt.registrationId,
            expectedHip:receipt.expectedHip,requestId:ticket.id,bindSessionId:ticket.sessionId},signal,ticket.selectionRevision,()=>{
              signal.throwIfAborted()
              if(ticket.phase!=='waiting')throw Error('已停止等待，未提交工程选择。')
              runtime.committed=true
            }) as Omit<DesktopSelection,'source'>
        }
        ticket.result={...result,source:'launch',launchId:ticket.id};ticket.phase='ready';ticket.callback=this.signature(receipt)
        ticket.message=undefined
        await this.saveTicket(ticket)
        this.intents.publish(ticket.result)
        return ticket.result
      }catch(error) {
        if(ticket.phase==='detached')return {phase:'detached'}
        if(this.lifetime.signal.aborted)throw error
        ticket.message=String((error as Error).message||error).slice(0,4000)
        if(error instanceof LaunchRejected)ticket.phase='error'
        await this.saveTicket(ticket)
        if(error instanceof LaunchRejected)throw error
        return {phase:'waiting',message:ticket.message}
      }
    })()
    runtime.binding=pending
    void pending.finally(()=>{if(runtime.binding===pending){runtime.binding=undefined;runtime.abort=undefined}}).catch(()=>{})
    return pending
  }
  async status(input:unknown) {
    this.lifetime.signal.throwIfAborted()
    const ticket=this.requireTicket(input)
    let process:ProcessState|undefined,message=ticket.message
    if(ticket.pid&&(ticket.phase==='preparing'||ticket.phase==='waiting'||ticket.phase==='detached')) {
      process=await this.ticketProcessState(ticket)
      this.lifetime.signal.throwIfAborted()
      if(process==='exited'||process==='reused') {
        ticket.phase='error';message=process==='reused'?'原 Houdini 已退出，当前 PID 属于另一个进程；未绑定。':'原 Houdini 已退出，未绑定其他窗口。'
        ticket.message=message
        const result={id:ticket.id,phase:ticket.phase,message,result:ticket.result,stage:ticket.stage,process,createdAt:ticket.createdAt,elapsedMs:Math.max(0,Date.now()-ticket.createdAt)}
        await this.saveTicket(ticket);await this.retireTicket(ticket)
        return result
      }
      if(process==='unknown')message='暂时无法确认原 Houdini 的进程身份，尚未自动绑定。可从原窗口 Open Workspace 接入。'
      if(process==='alive'&&ticket.phase==='waiting') {
        await this.complete(ticket).catch(()=>{})
        message=ticket.message
      }
    }
    return {id:ticket.id,phase:ticket.phase,message,result:ticket.result,stage:ticket.stage,process,
      createdAt:ticket.createdAt,elapsedMs:Math.max(0,Date.now()-ticket.createdAt)}
  }
  async detach(input:unknown) {
    this.lifetime.signal.throwIfAborted()
    const data=input as {id?:string}
    if(data&&Object.keys(data).join(',')==='id'&&typeof data.id==='string'&&ID.test(data.id)&&!this.tickets.has(data.id)) {
      const admitted=this.runtime.get(data.id)
      if(admitted){admitted.stopBeforeAdmission=true;return {id:data.id,phase:'detached' as const}}
    }
    const ticket=this.requireTicket(input),runtime=this.live(ticket)
    if(runtime.committed&&runtime.binding){await runtime.binding.catch(()=>{});return this.status(input)}
    if(ticket.phase==='waiting'||ticket.phase==='preparing')ticket.phase='detached'
    runtime.abort?.abort(Error('已停止等待原启动请求。'))
    await this.saveTicket(ticket)
    return this.status(input)
  }
  async resume(input:unknown) {
    this.lifetime.signal.throwIfAborted()
    const ticket=this.requireTicket(input)
    await this.live(ticket).binding?.catch(()=>{})
    if(ticket.phase==='ready'||ticket.phase==='error')return this.status(input)
    await this.houdiniSession(ticket.sessionId)
    if(await this.ticketProcessState(ticket)!=='alive')return this.status(input)
    this.lifetime.signal.throwIfAborted()
    ticket.phase='waiting';ticket.message=undefined
    await this.saveTicket(ticket)
    await this.complete(ticket).catch(()=>{})
    return this.status(input)
  }
  private async attached(input:unknown) {
    const data=input as any
    if(!data||Object.keys(data).sort().join(',')!=='executorId,expectedHip,id,registrationId'
      ||![data.id,data.executorId,data.registrationId].every(value=>typeof value==='string'&&ID.test(value))
      ||typeof data.expectedHip!=='string'||!path.isAbsolute(data.expectedHip))throw Error('无效的启动回执。')
    const ticket=this.tickets.get(data.id)
    if(!ticket)throw Error('未找到原启动请求，未自动绑定其他工程。')
    const callback=this.signature(data)
    if(ticket.phase==='ready'){if(ticket.callback!==callback)throw Error('启动回执与已完成的工程不一致。');return ticket.result}
    const record=await this.targets.getRouter(this.paths.registry).directory.find(data.executorId)
    if(record.registration_id!==data.registrationId||!record.hip_path||key(record.hip_path)!==key(data.expectedHip))throw Error('启动回执与工程登记不一致。')
    ticket.receipt=await this.validateRecord(ticket,record)
    await this.saveTicket(ticket)
    if(ticket.phase==='detached')return {phase:'detached'}
    if(ticket.phase!=='waiting')throw Error('启动请求已失败。')
    return this.complete(ticket)
  }
  private async failed(input:unknown){const data=input as any;if(!data||Object.keys(data).sort().join(',')!=='error,id'||!ID.test(data.id)||typeof data.error!=='string')throw Error('无效的启动失败回执。')
    const ticket=this.tickets.get(data.id)
    if(ticket&&ticket.phase==='waiting') {
      if(await this.ticketProcessState(ticket)!=='alive')throw Error('无法确认失败回执属于原启动进程，未改变原请求。')
      ticket.phase='error';ticket.message=data.error.slice(0,4000);await this.saveTicket(ticket)
    }
    return {}
  }
}

declare module '@deepseek-ai/cordis' {interface Context {houdiniDesktop:DesktopIntegration}}
