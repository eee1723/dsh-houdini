/** Read the installer's own read-only plan. Do not duplicate its file identity
 * algorithm or invent an active-version pointer alongside Houdini Packages. */
import fs from 'node:fs/promises'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import type {BridgeHealth} from './bridge.js'

const execute=promisify(execFile)
const pluginRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
const key=(p:string)=>process.platform==='win32'?path.resolve(p).toLowerCase():path.resolve(p)
type Plan={helper:string;targets:string[];package:{env:Record<string,string>[]};migration:{conflicts:unknown[]}}
export type ComponentUpdate={state:'install'|'restart'|'unknown'|'current';loadedHelperId?:string;installedHelperId?:string}

/** A loaded build difference is advisory; only the execution contract determines
 * whether the scene tools are available. */
export function componentUpdate(health:BridgeHealth,expectedId:string,installed:boolean|null,sameInstallation=true):ComponentUpdate {
  const loaded=health.helper?.id??undefined
  const details={...(loaded?{loadedHelperId:loaded}:{}),...(installed?{installedHelperId:expectedId}:{})}
  if(loaded===expectedId)return {state:'current',...details}
  if(installed===true&&loaded&&sameInstallation)return {state:'restart',...details}
  if(!sameInstallation)return {state:'unknown',...details}
  if(installed===false)return {state:'install',...details}
  return {state:'unknown',...details}
}

export class ComponentInstallation {
  private snapshot?:{at:number;promise:Promise<{expectedId:string;installed:boolean|null;root:string}>;value?:{expectedId:string;installed:boolean|null;root:string}}
  constructor(private readonly lifetime?:AbortSignal){}
  invalidate(){this.snapshot=undefined}
  private plan() {
    if(this.snapshot&&Date.now()-this.snapshot.at<30000)return this.snapshot.promise
    const promise=(async()=>{
      if(process.platform!=='win32')throw Error('尚未确认组件安装位置。')
      const {stdout}=await execute(path.join(process.env.SystemRoot||'C:/Windows','System32/WindowsPowerShell/v1.0/powershell.exe'),
        ['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',path.join(pluginRoot,'installer/install.ps1'),'-PrintOnly'],
        {windowsHide:true,timeout:15000,maxBuffer:256000,signal:this.lifetime})
      const plan=JSON.parse(stdout.replace(/^\uFEFF/,'')) as Plan
      const expectedId=path.basename(plan.helper)
      if(!/^[0-9a-f]{16}$/.test(expectedId)||!Array.isArray(plan.targets)||!plan.targets.length)throw Error('尚未确认组件安装位置。')
      const root=key(path.resolve(plan.helper,'../..'))
      if(plan.migration?.conflicts?.length)return {expectedId,installed:null,root}
      const expectedPath=key(path.join(plan.helper,'houdini'))
      let installed=true
      for(const directory of plan.targets) {
        try {
          const pkg=JSON.parse(await fs.readFile(path.join(directory,'dsh-houdini.json'),'utf8'))
          const componentPath=Array.isArray(pkg.env)?pkg.env.find((entry:any)=>entry?.DSH_HOUDINI_PATH)?.DSH_HOUDINI_PATH:undefined
          if(typeof componentPath!=='string'||key(componentPath)!==expectedPath)installed=false
        }catch(error){if((error as NodeJS.ErrnoException).code==='ENOENT')installed=false;else return {expectedId,installed:null,root}}
      }
      // A Package referring to a removed directory is not a completed install.
      if(installed)try{await fs.access(path.join(plan.helper,'houdini/python3.11libs/dsh_bridge.py'))}catch{installed=false}
      return {expectedId,installed,root}
    })()
    const snapshot={at:Date.now(),promise,value:this.snapshot?.value}
    this.snapshot=snapshot
    void promise.then(value=>{snapshot.value=value},()=>{snapshot.value=undefined})
    return promise
  }
  async observe(health:BridgeHealth,installation:string):Promise<ComponentUpdate> {
    // Disk inspection runs independently of live health. A slow filesystem or
    // PowerShell start must never turn a reachable scene into a timeout.
    void this.plan().catch(()=>{})
    const plan=this.snapshot?.value
    const sameInstallation=plan&&/^[0-9a-f]{16}$/.test(path.basename(installation))
      &&path.basename(path.dirname(installation)).toLowerCase()==='helpers'&&key(path.resolve(installation,'../..'))===plan.root
    return plan?componentUpdate(health,plan.expectedId,plan.installed,!!sameInstallation):
      {state:'unknown',...(health.helper?.id?{loadedHelperId:health.helper.id}:{})}
  }
}
