/** Exact installed SideFX references, read by an ordinary managed Python child. */
import fs from 'node:fs/promises'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {scrubbedParentEnv} from '@deepseek-ai/dsh-subprocess'
import type {Context} from '@deepseek-ai/cordis'
import type {ExecResult,HoudiniRuntimeFacts} from './bridge.js'
import type {HoudiniConnection} from './tool-runtime.js'
import {discoverHoudini} from './desktop-integration.js'

const WORKER=fileURLToPath(new URL('../tools/houdini-help.py',import.meta.url))
type Installation={hfs:string;version:string}
type HelpRuntime=Installation&{python:string;selection:'explicit-installation'|'selected-runtime'|'sole-installation'}
export type HelpArgs={ref:string;offset?:number;limit?:number;houdini_installation?:string;expected_sha256?:string}
const key=(value:string)=>process.platform==='win32'?path.normalize(value).toLowerCase():path.normalize(value)
const absolute=async(value:string)=>key(await fs.realpath(value))
const failure=(error:string,result?:ExecResult['result']):ExecResult=>({ok:false,stdout:'',stderr:'',error,...(result?{result}:{})})

/** Runtime records are read without health, scene selection or ownership. */
export async function resolveHelpInstallation(ctx:Context,connection:HoudiniConnection,exec:any,explicit?:string):Promise<HelpRuntime|{ambiguous:Installation[]}> {
  exec.signal?.throwIfAborted()
  // ctx.get is Cordis's public optional lookup. Do not fall through to
  // ctx[name]: an absent Desktop service is legitimate in fixed/dev Hosts.
  // Both those Hosts and Desktop consume the same installation discovery.
  const desktop=ctx.get('houdiniDesktop')
  const inventory:Installation[]=await (desktop?.listInstallations?.()??discoverHoudini())
  const installed:(Installation&{canonical:string})[]=[]
  for(const item of inventory) {
    if(!path.isAbsolute(item.hfs)||!/^2[12]\.0\.\d+$/.test(item.version))continue
    const canonical=await absolute(item.hfs)
    if(!installed.some(row=>row.canonical===canonical))installed.push({...item,canonical})
  }
  const target=explicit===undefined&&exec.agent?.session&&ctx.get('houdiniExecutorState')?.stateOf(exec.agent.session)?.selectedTarget
  let wanted=explicit,selected:{runtime:HoudiniRuntimeFacts;houdiniVersion:string}|undefined
  // An explicit reference installation does not rebind the scene. Otherwise a
  // selected scene's unavailable/stale installation never silently falls back.
  if(explicit===undefined&&target) {
    if(!('resolveRuntime' in connection)||!connection.resolveRuntime)throw Error('The selected scene has no recorded installation facts; choose an exact installed Houdini directory')
    selected=await connection.resolveRuntime(exec)
    wanted=selected.runtime.hfs
  }
  let chosen
  if(wanted!==undefined) {
    if(typeof wanted!=='string'||!path.isAbsolute(wanted))throw Error('houdini_installation must be an absolute directory from the installation inventory')
    const canonical=await absolute(wanted)
    chosen=installed.find(item=>item.canonical===canonical)
    if(!chosen)throw Error('The requested Houdini installation is not in the official installation inventory')
    if(selected&&selected.houdiniVersion!==chosen.version)throw Error('The selected Houdini installation changed build; choose the intended installed documentation explicitly')
  }else {
    if(installed.length!==1)return {ambiguous:installed.map(({hfs,version})=>({hfs,version}))}
    chosen=installed[0]
  }
  const hfs=await fs.realpath(chosen.hfs)
  // These are the ordinary bundled interpreters of the qualified H21/H22
  // installations; do not select a different Python from PATH or another HFS.
  const python=selected?.runtime.python??path.join(hfs,chosen.version.startsWith('21.')?'python311':'python313','python.exe')
  const pythonPath=await fs.realpath(python),relative=path.relative(hfs,pythonPath)
  if(relative.startsWith('..')||path.isAbsolute(relative)||!(await fs.stat(pythonPath)).isFile())
    throw Error('The help reader requires the ordinary Python inside the exact selected Houdini installation')
  return {hfs,version:chosen.version,python:pythonPath,selection:explicit!==undefined?'explicit-installation':selected?'selected-runtime':'sole-installation'}
}

export async function readHoudiniHelp(ctx:Context,connection:HoudiniConnection,args:HelpArgs,exec:any):Promise<ExecResult> {
  if(!Number.isSafeInteger(args.offset??0)||(args.offset??0)<0||!Number.isSafeInteger(args.limit??6000)||(args.limit??6000)<1||(args.limit??6000)>16000)
    throw Error('offset must be a nonnegative integer; limit must be 1..16000 characters')
  const runtime=await resolveHelpInstallation(ctx,connection,exec,args.houdini_installation)
  if('ambiguous' in runtime)return failure(runtime.ambiguous.length?'Several Houdini installations are available; name houdini_installation or select the intended scene':'No supported installed Houdini documentation source was found',
    {status:runtime.ambiguous.length?'ambiguous_installation':'installation_unavailable',installations:runtime.ambiguous})
  const subprocess=ctx.get('subprocess')
  if(!subprocess)throw Error('DSH subprocess service is unavailable; no help reader was started')
  const signal=AbortSignal.any([...(exec.signal?[exec.signal]:[]),AbortSignal.timeout(15000)])
  signal.throwIfAborted()
  const base=scrubbedParentEnv(),env:NodeJS.ProcessEnv={...base}
  for(const name of Object.keys(base))if(/^(PYTHON|QT_|QML|HOUDINI_|HFS$|HSITE$)/i.test(name))env[name]=undefined
  const child=subprocess.spawn({argv:[runtime.python,'-I','-S','-B','-X','utf8',WORKER],cwd:runtime.hfs,env,
    stdio:{stdin:{data:JSON.stringify({hfs:runtime.hfs,version:runtime.version,ref:args.ref,offset:args.offset??0,limit:args.limit??6000,
      ...(args.expected_sha256!==undefined?{expected_sha256:args.expected_sha256}:{})})},stdout:{maxBytes:128*1024},stderr:{maxBytes:8192}},
    graceMs:1000,signal})
  let outcome
  try{outcome=await child.done}
  finally{
    child.terminate()
    if(!await child.waitForExit(AbortSignal.timeout(5000)))throw Error('Help reader process termination is unconfirmed')
  }
  signal.throwIfAborted()
  const output=child.collected.stdout?.readFrom(0),stderr=child.collected.stderr?.readFrom(0)
  if(!output||output.lossy||stderr?.lossy)return failure('Help reader output exceeded its bounded protocol')
  let value
  try{value=JSON.parse(output.text)}catch{return failure('Help reader did not return a complete JSON result'+(stderr?.text?': '+stderr.text.slice(0,1000):''))}
  if(outcome.exitCode!==0||value.ok!==true)return failure(typeof value.error==='string'?value.error:'Help reader failed')
  return {ok:true,stdout:'',stderr:'',result:{...value.result,installation_selection:runtime.selection}}
}
