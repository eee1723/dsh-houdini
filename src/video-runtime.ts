/** Tutorial workers use Houdini's Python and private, versioned media tools. */
import {existsSync} from 'node:fs'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import type {HoudiniBridge} from './bridge.js'

const PACKAGE=fileURLToPath(new URL('../',import.meta.url))
const execute=promisify(execFile)
export type RuntimeOptions={packageRoot?:string;environment?:NodeJS.ProcessEnv;exists?:(filename:string)=>boolean;
  bridge?:Pick<HoudiniBridge,'inspectExecutor'>;signal?:AbortSignal}
type PythonScope='explicit'|'selected-executor'|'host-launch'|'unavailable'

/** Without a task/executor context this only describes the Host launch environment. */
export function videoRuntime(pythonOverride='',options:RuntimeOptions={}) {
  const root=options.packageRoot??PACKAGE,env=options.environment??process.env,exists=options.exists??existsSync
  const override=pythonOverride.trim()
  if (override && !['python','python.exe'].includes(override.toLowerCase()) && !path.isAbsolute(override))
    throw Error('Python 自定义路径必须是完整的绝对路径；留空使用当前 Houdini 的 Python。')
  const explicit=Boolean(override && !['python','python.exe'].includes(override.toLowerCase()))
  const candidates=env.HFS ? ['python313','python311'].map(folder=>path.join(env.HFS!,folder,'python.exe')) : []
  const python=explicit ? override : candidates.find(exists)??''
  const media=path.join(root,'runtime','video','ffmpeg','bin')
  const managed=Boolean(env.DSH_HOUDINI_MANAGED_CONTEXT)
  const repair:Record<string,string>=managed ? {kind:'managed-version',label:'修复当前版本',
      detail:'在 Version & Updates → 高级设置中选择「修复当前版本」，重新安装当前版本的完整依赖；随后完整重开 Houdini。'}
      : {kind:'source-private',label:'准备源码私有依赖',
        detail:'源码开发在插件目录运行 tools/prepare-video-runtime.py；它只准备本目录的锁定依赖。Python 由 Houdini 提供。',
        script:path.join(root,'tools','prepare-video-runtime.py')}
  return {python,ffmpeg:path.join(media,'ffmpeg.exe'),ffprobe:path.join(media,'ffprobe.exe'),
    pythonSource:explicit?'explicit':python?'houdini':'unavailable',mediaSource:'private',
    pythonScope:(explicit?'explicit':python?'host-launch':'unavailable') as PythonScope,
    hfs:explicit?'':env.HFS??'',
    mode:managed?'managed':'source',repair}
}

/** Consume the already selected target; routing and session binding remain with
 * HoudiniToolRuntime. Selected targets never fall back to the Host's HFS/PATH. */
export async function resolveVideoRuntime(pythonOverride='',options:RuntimeOptions={}) {
  const base=videoRuntime(pythonOverride,{...options,
    ...(options.bridge?{environment:{...(options.environment??process.env),HFS:undefined}}:{})})
  if (base.pythonScope==='explicit' || !options.bridge) return base
  const health=await options.bridge.inspectExecutor(options.signal)
  const facts=health.runtime
  if (!facts || typeof facts.python!=='string' || !path.isAbsolute(facts.python)
      || typeof facts.hfs!=='string' || !path.isAbsolute(facts.hfs)
      || typeof facts.pythonVersion!=='string')
    throw Error('所选 Houdini 未提供 Python 运行时路径；请通过 Version & Updates → 高级设置 → 运行诊断修复并重启运行环境，或填写 Python 3.11+ 的完整路径。')
  const version=facts.pythonVersion.match(/^(\d+)\.(\d+)\.\d+$/)
  if (!version || Number(version[1])<3 || Number(version[1])===3 && Number(version[2])<11)
    throw Error(`所选 Houdini 的 Python 版本不受支持：${facts.pythonVersion}；需要 Python 3.11 或更新版本。`)
  if (!(options.exists??existsSync)(facts.python))
    throw Error(`所选 Houdini 的 Python 不存在：${facts.python}；请检查该 Houdini 安装，或填写 Python 3.11+ 的完整路径。`)
  return {...base,python:facts.python,pythonSource:'houdini',pythonScope:'selected-executor' as PythonScope,
    hfs:facts.hfs,pythonVersion:facts.pythonVersion,
    executorId:health.executorId??null,runtimeId:health.runtimeId??null,houVersion:health.houVersion??null}
}

/** Probe the exact commands used by workers; no cloud call or PATH fallback. */
export async function videoDiagnostics(pythonOverride='',options:RuntimeOptions={}) {
  const runtime=await resolveVideoRuntime(pythonOverride,options)
  const probes=[{name:'Python',command:runtime.python,args:['--version'],source:runtime.pythonSource},
    {name:'FFmpeg',command:runtime.ffmpeg,args:['-version'],source:runtime.mediaSource},
    {name:'ffprobe',command:runtime.ffprobe,args:['-version'],source:runtime.mediaSource}]
  const dependencies=await Promise.all(probes.map(async probe=>{
    const base={name:probe.name,path:probe.command,source:probe.source}
    if (!probe.command) return {...base,available:false,error:'此设置页没有当前任务执行器上下文，Host 启动环境也未提供 Houdini Python；在任务中选择 Houdini 后自动解析，或填写 Python 3.11+ 的完整路径。'}
    try {
      const {stdout,stderr}=await execute(probe.command,probe.args,{windowsHide:true,timeout:10_000,maxBuffer:128*1024})
      const version=(stdout || stderr).trim().split(/\r?\n/)[0]
      const python=probe.name==='Python' ? version.match(/^Python (\d+)\.(\d+)/) : null
      const available=probe.name!=='Python' || Boolean(python && (Number(python[1])>3 || Number(python[1])===3 && Number(python[2])>=11))
      return {...base,available,version,...(!available?{error:'需要 Python 3.11 或更新版本。'}:{})}
    } catch {
      return {...base,available:false,error:probe.name==='Python'?'无法运行所选 Python，请检查完整路径和 Houdini 安装。':
        '私有媒体依赖缺失或无法运行；'+runtime.repair.detail}
    }
  }))
  return {dependencies,runtime,repair:runtime.repair,cloud_request:false,
    note:(runtime.pythonScope==='selected-executor'?'Python 来自当前任务所选 Houdini 的健康信息。':
      runtime.pythonScope==='explicit'?'Python 使用显式配置的完整路径。':
      '此检查没有任务执行器上下文；Python 仅来自 Host 启动环境，不能证明当前任务所选 Houdini 的运行时。')
      +'仅检查 Python 和插件私有媒体依赖；不会安装全局程序或上传音频。转录服务需用实际音频短段验证。'}
}
