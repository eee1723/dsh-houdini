/** Windows-only pinning of this Host's Native Desktop parent. No Qt, title
 * matching, foreground-window selection, or arbitrary HWND RPC input. */
import fs from 'node:fs/promises'
import path from 'node:path'
import {randomUUID} from 'node:crypto'
import {createRequire} from 'node:module'
import {desktopPaths} from './desktop-paths.js'

export interface DesktopWindowIdentity {pid:number;started:string;executable:string;hwnd:string}
export interface DesktopWindowObservation extends DesktopWindowIdentity {pinned:boolean}
export interface DesktopWindowState {available:boolean;pinned?:boolean;reason?:string}
export interface DesktopWindowOS {
  readonly parentPid:number
  current():Promise<DesktopWindowObservation>
  set(window:DesktopWindowIdentity,pinned:boolean,commit?:()=>void):Promise<void>
  /** Restore only an already bound identity, including while hidden to tray.
   * A proved dead/reused process or destroyed/reused HWND needs no restore. */
  restore(window:DesktopWindowIdentity,pinned:boolean):Promise<void>
  dispose?():void|Promise<void>
}
type PinRecord={schema:1;owner:string;window:DesktopWindowIdentity;baseline:boolean}
type Active={owner:string;window:DesktopWindowIdentity;baseline:boolean;changed:boolean}
const OWNER=/^[a-f0-9]{32}$/
const canonical=(value:string)=>path.resolve(value).toLowerCase()
const same=(a:DesktopWindowIdentity,b:DesktopWindowIdentity)=>a.pid===b.pid&&a.started===b.started&&
  canonical(a.executable)===canonical(b.executable)&&a.hwnd===b.hwnd
export class DesktopWindowUnavailableError extends Error {}
function validateOwner(owner:string) {if(typeof owner!=='string'||!OWNER.test(owner))throw new TypeError('Invalid window scope')}
function parseRecord(value:any):PinRecord {
  const w=value?.window
  if(value?.schema!==1||!OWNER.test(value.owner)||typeof value.baseline!=='boolean'||!w||
    !Number.isInteger(w.pid)||w.pid<=0||typeof w.started!=='string'||!/^\d+$/.test(w.started)||
    typeof w.executable!=='string'||!path.isAbsolute(w.executable)||typeof w.hwnd!=='string'||!/^[1-9]\d*$/.test(w.hwnd))
    throw new Error('窗口置顶恢复记录无效，未改动窗口或覆盖记录。')
  return value as PinRecord
}

export class DesktopWindowController {
  readonly recordPath:string
  private readonly os:DesktopWindowOS
  private readonly platform:string
  private tail:Promise<unknown>=Promise.resolve()
  private recovered=false
  private active:Active|undefined
  private readonly retired=new Set<string>()
  private revision=0
  private closing=false
  private disposed:Promise<void>|undefined
  constructor(options:{root?:string;os?:DesktopWindowOS;platform?:string}={}) {
    this.platform=options.platform??process.platform
    this.os=options.os??createNativeDesktopWindowOS()
    this.recordPath=path.join(options.root??desktopPaths().root,'window-pins',String(this.os.parentPid)+'.json')
  }
  private enqueue<T>(run:()=>Promise<T>):Promise<T> {
    const operation=this.tail.catch(()=>{}).then(run);this.tail=operation;return operation
  }
  private async recover() {
    if(this.recovered||this.platform!=='win32')return
    let raw:string
    try {
      const info=await fs.lstat(this.recordPath)
      if(!info.isFile()||info.isSymbolicLink()||info.size>16384)throw new Error('窗口置顶恢复记录不可安全读取。')
      raw=await fs.readFile(this.recordPath,'utf8')
    }catch(error){if((error as NodeJS.ErrnoException).code==='ENOENT'){this.recovered=true;return}throw error}
    const record=parseRecord(JSON.parse(raw))
    if(record.window.pid!==this.os.parentPid)throw new Error('窗口置顶恢复记录不属于当前 Desktop，未改动它。')
    await this.os.restore(record.window,record.baseline)
    await fs.unlink(this.recordPath)
    this.recovered=true
  }
  /** Called when the root client service starts, even in Standard mode. With
   * no journal this completes before the Native Main window has been created. */
  start():Promise<void> {return this.enqueue(()=>this.recover())}
  private async state():Promise<DesktopWindowState> {
    if(this.platform!=='win32')return {available:false,reason:'窗口置顶目前仅支持 Windows Desktop。'}
    try {const window=await this.os.current();return {available:true,pinned:window.pinned}}
    catch(error){if(error instanceof DesktopWindowUnavailableError)return {available:false,reason:error.message};throw error}
  }
  read():Promise<DesktopWindowState> {return this.enqueue(async()=>{await this.recover();return this.state()})}
  activate(owner:string):Promise<DesktopWindowState> {
    validateOwner(owner)
    const revision=this.revision
    return this.enqueue(async()=>{
      if(this.closing||this.retired.has(owner)||revision!==this.revision)throw new Error('此置顶操作已结束，请重新进入 Houdini 模式。')
      await this.recover()
      if(this.platform!=='win32')return this.state()
      if(this.active?.owner===owner)return this.state()
      if(this.active){this.retired.add(this.active.owner);await this.restoreActive()}
      const window=await this.os.current()
      if(this.closing||this.retired.has(owner)||revision!==this.revision)throw new Error('此置顶操作已结束，未更改当前窗口。')
      const {pid,started,executable,hwnd}=window
      this.active={owner,window:{pid,started,executable,hwnd},baseline:window.pinned,changed:false}
      return {available:true,pinned:window.pinned}
    })
  }
  private async save(active:Active) {
    await fs.mkdir(path.dirname(this.recordPath),{recursive:true})
    const record:PinRecord={schema:1,owner:active.owner,window:active.window,baseline:active.baseline}
    const temporary=this.recordPath+'.'+randomUUID()+'.tmp'
    const handle=await fs.open(temporary,'wx',0o600)
    try {await handle.writeFile(JSON.stringify(record)+'\n');await handle.sync()}finally{await handle.close()}
    try {await fs.rename(temporary,this.recordPath)}finally{await fs.unlink(temporary).catch(error=>{if(error.code!=='ENOENT')throw error})}
    active.changed=true
  }
  set(owner:string,pinned:boolean):Promise<DesktopWindowState> {
    validateOwner(owner);if(typeof pinned!=='boolean')throw new TypeError('pinned must be boolean')
    const revision=this.revision
    return this.enqueue(async()=>{
      if(this.closing||this.retired.has(owner)||this.active?.owner!==owner)throw new Error('此置顶操作已结束，未更改当前窗口。')
      const active=this.active,window=await this.os.current()
      const commit=()=>{if(this.closing||this.retired.has(owner)||this.active!==active||revision!==this.revision)throw new Error('此置顶操作已结束，未更改当前窗口。')}
      commit()
      if(!same(active.window,window))throw new Error('Desktop 窗口已变化，未更改另一个窗口。')
      if(window.pinned!==pinned) {
        if(!active.changed)await this.save(active)
        await this.os.set(active.window,pinned,commit)
      }
      const actual=await this.os.current()
      if(!same(active.window,actual)||actual.pinned!==pinned)throw new Error('尚未确认窗口置顶结果，请重新查看状态。')
      if(active.changed&&actual.pinned===active.baseline){await fs.unlink(this.recordPath);active.changed=false}
      return {available:true,pinned:actual.pinned}
    })
  }
  private async restoreActive() {
    const active=this.active
    if(!active)return
    if(active.changed){await this.os.restore(active.window,active.baseline);await fs.unlink(this.recordPath)}
    this.active=undefined
  }
  release(owner:string):Promise<DesktopWindowState> {
    validateOwner(owner)
    // Retire before an older queued activate/set can start.
    this.retired.add(owner)
    return this.enqueue(async()=>{if(this.active?.owner===owner)await this.restoreActive();return this.state()})
  }
  /** Renderer reload/reconnect barrier. Keep the adapter alive, but retire
   * the previous page's scope before any in-flight native commit. */
  reset():Promise<DesktopWindowState> {
    this.revision++
    if(this.active)this.retired.add(this.active.owner)
    return this.enqueue(async()=>{
      if(this.active)this.retired.add(this.active.owner)
      await this.restoreActive()
      return this.state()
    })
  }
  dispose():Promise<void> {
    if(this.disposed)return this.disposed
    this.closing=true
    return this.disposed=this.enqueue(async()=>{try{await this.restoreActive()}finally{await this.os.dispose?.()}})
  }
}

type Handle=bigint|null
type Main={pid:number;started:string;executable:string;handle:Handle}
let bindings:any
function native() {
  if(bindings)return bindings
  const koffi=createRequire(import.meta.url)('koffi') as typeof import('koffi')
  const kernel=koffi.load('kernel32.dll'),user=koffi.load('user32.dll')
  const bind=(lib:any,name:string,result:string,args:any[])=>lib.func('__stdcall',name,result,args)
  const enumerate=koffi.proto('__stdcall','DSH_HOUDINI_PIN_ENUMWINDOWS','int',['void *','intptr_t'])
  return bindings={
    open:bind(kernel,'OpenProcess','void *',['uint32','int','uint32']),close:bind(kernel,'CloseHandle','int',['void *']),
    wait:bind(kernel,'WaitForSingleObject','uint32',['void *','uint32']),error:bind(kernel,'GetLastError','uint32',[]),
    clearError:bind(kernel,'SetLastError','void',['uint32']),
    times:bind(kernel,'GetProcessTimes','int',['void *','void *','void *','void *','void *']),
    image:bind(kernel,'QueryFullProcessImageNameW','int',['void *','uint32','void *','void *']),
    windows:bind(user,'EnumWindows','int',[koffi.pointer(enumerate),'intptr_t']),
    pid:bind(user,'GetWindowThreadProcessId','uint32',['void *','void *']),
    visible:bind(user,'IsWindowVisible','int',['void *']),exists:bind(user,'IsWindow','int',['void *']),
    owner:bind(user,'GetWindow','void *',['void *','uint32']),long:bind(user,'GetWindowLongW','int32',['void *','int']),
    position:bind(user,'SetWindowPos','int',['void *','intptr_t','int','int','int','int','uint32']),
  }
}
function apiError(api:any,name:string):never {throw new Error(name+' failed (Win32 '+api.error()+')')}
function birth(api:any,handle:Handle) {
  const created=Buffer.alloc(8),exit=Buffer.alloc(8),kernel=Buffer.alloc(8),user=Buffer.alloc(8)
  if(!api.times(handle,created,exit,kernel,user))apiError(api,'GetProcessTimes')
  return created.readBigUInt64LE().toString()
}
function image(api:any,handle:Handle) {
  const buffer=Buffer.alloc(65536),size=Buffer.alloc(4);size.writeUInt32LE(buffer.length/2)
  if(!api.image(handle,0,buffer,size))apiError(api,'QueryFullProcessImageNameW')
  return buffer.subarray(0,size.readUInt32LE()*2).toString('utf16le')
}
function windowPid(api:any,hwnd:bigint) {const pid=Buffer.alloc(4);return api.pid(hwnd,pid)?pid.readUInt32LE():0}
function windowStyle(api:any,hwnd:bigint,index:number) {
  api.clearError(0);const value=api.long(hwnd,index)
  if(value===0&&api.error()!==0)apiError(api,'GetWindowLongW')
  return value
}
function mainWindow(api:any,hwnd:bigint,pid:number,visible:boolean) {
  return windowPid(api,hwnd)===pid&&(!visible||api.visible(hwnd)!==0)&&!api.owner(hwnd,4)&&
    !(windowStyle(api,hwnd,-20)&0x80)&&!(windowStyle(api,hwnd,-16)&0x40000000)
}
function pinned(api:any,hwnd:bigint) {return !!(windowStyle(api,hwnd,-20)&8)}

/** The parent PID is captured from this Host, never supplied by an RPC caller. */
export function createNativeDesktopWindowOS():DesktopWindowOS {
  const parentPid=process.ppid,carrier=process.execPath
  let parent:Promise<Main>|undefined,closed=false
  async function main():Promise<Main> {
    if(process.platform!=='win32')throw new DesktopWindowUnavailableError('窗口置顶目前仅支持 Windows Desktop。')
    if(closed)throw new DesktopWindowUnavailableError('窗口置顶服务已结束。')
    if(!parent)parent=(async()=>{
      const api=native(),handle=api.open(0x1000|0x100000,0,parentPid) as Handle
      if(!handle)throw new DesktopWindowUnavailableError('无法确认所属的 Desktop 主进程。')
      try {
        if(api.wait(handle,0)!==258)throw new DesktopWindowUnavailableError('所属的 Desktop 主进程已结束。')
        const executable=await fs.realpath(image(api,handle)),expected=await fs.realpath(carrier)
        if(canonical(executable)!==canonical(expected))throw new DesktopWindowUnavailableError('当前不是官方 Native Desktop 的直属 Host。')
        return {pid:parentPid,started:birth(api,handle),executable,handle}
      }catch(error){api.close(handle);throw error}
    })().catch(error=>{parent=undefined;throw error})
    const value=await parent
    if(native().wait(value.handle,0)!==258)throw new DesktopWindowUnavailableError('所属的 Desktop 主进程已结束。')
    return value
  }
  async function current():Promise<DesktopWindowObservation> {
    const owner=await main(),api=native(),matches:bigint[]=[];let failure:unknown
    const ok=api.windows((hwnd:bigint)=>{try{if(mainWindow(api,hwnd,owner.pid,true))matches.push(hwnd);return 1}catch(error){failure=error;return 0}},0)
    if(failure)throw failure
    if(!ok)apiError(api,'EnumWindows')
    if(matches.length!==1)throw new DesktopWindowUnavailableError(matches.length?'存在多个可能的 Desktop 主窗口，未猜测置顶对象。':'尚未找到可见的 Desktop 主窗口。')
    if(api.wait(owner.handle,0)!==258)throw new DesktopWindowUnavailableError('所属的 Desktop 主进程已结束。')
    return {pid:owner.pid,started:owner.started,executable:owner.executable,hwnd:matches[0].toString(),pinned:pinned(api,matches[0])}
  }
  function write(owner:Main,window:DesktopWindowIdentity,value:boolean,visible:boolean) {
    const api=native(),hwnd=BigInt(window.hwnd)
    if(api.wait(owner.handle,0)!==258||!mainWindow(api,hwnd,owner.pid,visible))throw new DesktopWindowUnavailableError('已绑定的 Desktop 窗口不可确认，未更改其他窗口。')
    if(pinned(api,hwnd)!==value&&!api.position(hwnd,value?-1n:-2n,0,0,0,0,0x213))apiError(api,'SetWindowPos')
    if(windowPid(api,hwnd)!==owner.pid||pinned(api,hwnd)!==value)throw new Error('尚未确认窗口置顶结果。')
  }
  return {
    parentPid, current,
    async set(window,value,commit) {const actual=await current();if(!same(window,actual))throw new DesktopWindowUnavailableError('Desktop 窗口已变化。');const owner=await main();commit?.();write(owner,window,value,true)},
    async restore(window,value) {
      const owner=await main(),api=native()
      if(owner.pid!==window.pid)throw new DesktopWindowUnavailableError('恢复记录不属于当前 Desktop，未改动它。')
      if(owner.started!==window.started)return // Parent PID was reused; the old Main and its HWND are gone.
      if(canonical(owner.executable)!==canonical(window.executable))throw new DesktopWindowUnavailableError('恢复记录与当前 Desktop 安装不一致，未改动窗口。')
      const hwnd=BigInt(window.hwnd)
      if(!api.exists(hwnd)||windowPid(api,hwnd)!==owner.pid)return
      write(owner,window,value,false)
    },
    async dispose() {closed=true;if(parent){const owner=await parent.catch(()=>undefined);if(owner)native().close(owner.handle)}},
  }
}
