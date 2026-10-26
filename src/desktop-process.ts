/** OS-only identity and lifetime exclusion for the Desktop plugin carrier. */
import fs from 'node:fs/promises'
import path from 'node:path'
import {createHash} from 'node:crypto'
import {createServer} from 'node:net'
import {extendWin32ProcessBindings,isNullPtr,type NativePtr} from '@deepseek-ai/dsh-win32-process'

type IdentityBindings={
  openProcess(access:number,inherit:number,pid:number):NativePtr|null
  getProcessTimes(process:NativePtr,created:Buffer,exited:Buffer,kernel:Buffer,user:Buffer):number
}
let identityBindings:ReturnType<typeof extendWin32ProcessBindings<IdentityBindings>>|undefined
function windowsIdentity() {
  return identityBindings??=extendWin32ProcessBindings(({kernel32,bind})=>({
    openProcess:bind(kernel32,'OpenProcess','void *',['uint32','int','uint32']) as IdentityBindings['openProcess'],
    getProcessTimes:bind(kernel32,'GetProcessTimes','int',['void *','void *','void *','void *','void *']) as IdentityBindings['getProcessTimes'],
  }))
}

/** Windows FILETIME birth identity, matching the helper's existing ctypes
 * representation. No Houdini interpreter, startup script or license is used.
 * Unreadable/exited identities and unsupported hosts return null; callers
 * separately distinguish confirmed exit from unknown observation. */
export async function processStarted(pid:number,_hfs?:string):Promise<string|null> {
  if(!Number.isInteger(pid)||pid<=0||pid>0xffffffff)throw new TypeError('Invalid process id')
  if(process.platform!=='win32')return null
  const api=windowsIdentity()
  const handle=api.openProcess(0x1000|0x100000,0,pid) // QUERY_LIMITED_INFORMATION | SYNCHRONIZE
  if(isNullPtr(handle))return null
  try {
    if(api.waitForSingleObject(handle,0)!==258)return null // Only WAIT_TIMEOUT proves it is still running.
    const created=Buffer.alloc(8),exited=Buffer.alloc(8),kernel=Buffer.alloc(8),user=Buffer.alloc(8)
    if(api.getProcessTimes(handle,created,exited,kernel,user)===0)return null
    return created.readBigUInt64LE().toString()
  }finally{api.closeHandle(handle)}
}

export interface DesktopLease {close():Promise<void>}

/** A canonical-root IPC bind is the lease itself. Windows pipes and Linux
 * abstract sockets disappear with their owner, including after a crash. The
 * endpoint exposes no request protocol and creates no stale PID lock file. */
export async function acquireDesktopLease(root:string):Promise<DesktopLease> {
  if(!path.isAbsolute(root))throw new TypeError('Desktop lease root must be absolute')
  if(process.platform!=='win32'&&process.platform!=='linux')throw new Error('Desktop lifetime lease is supported only on Windows and Linux')
  await fs.mkdir(root,{recursive:true})
  const real=await fs.realpath(root)
  const canonical=process.platform==='win32'?real.toLowerCase():real
  const name='dsh-houdini-desktop-'+createHash('sha256').update(canonical).digest('hex')
  const endpoint=process.platform==='win32'?'\\\\.\\pipe\\'+name:'\0'+name
  const server=createServer(socket=>socket.destroy())
  await new Promise<void>((resolve,reject)=>{
    server.once('error',(error:NodeJS.ErrnoException)=>{
      if(error.code==='EADDRINUSE') {
        const occupied=new Error('同一 DSH 数据根已有 Houdini 插件接入服务；未替换它。',{cause:error}) as NodeJS.ErrnoException
        occupied.code=error.code;reject(occupied)
      }else reject(error)
    })
    server.listen(endpoint,()=>{server.unref();resolve()})
  })
  let closing:Promise<void>|undefined
  return {close(){return closing??=new Promise<void>((resolve,reject)=>{
    server.close(error=>error?reject(error):resolve())
  })}}
}
