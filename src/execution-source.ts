/** Freeze a builder's exact source through DSH's filesystem before selecting a scene. */
import path from 'node:path'
import {createHash} from 'node:crypto'
import {TextDecoder} from 'node:util'
import {hostService} from './api-route.js'
import {workspaceOf} from './tool-runtime.js'
import type {ScriptSource} from './bridge.js'

export interface ExecutionSourceArgs {code?:string;script?:string;expected_sha256?:string}
export interface ExecutionSource {code:string;script?:ScriptSource}
// Whole-file transfer is bounded at the DSH filesystem seam, like isolated inputs.
const MAX_SOURCE_BYTES=4*1024*1024

export async function resolveExecutionSource(ctx:any,exec:any,args:ExecutionSourceArgs):Promise<ExecutionSource> {
  exec.signal?.throwIfAborted()
  if(args.code!==undefined&&typeof args.code!=='string')throw Error('code must be Python text')
  if(args.script===undefined){
    if(args.expected_sha256!==undefined)throw Error('expected_sha256 requires script')
    if(!args.code?.trim())throw Error('Provide nonempty Python code or an absolute UTF-8 .py script')
    return {code:args.code}
  }
  if(typeof args.script!=='string'||!path.isAbsolute(args.script)||path.extname(args.script).toLowerCase()!=='.py')
    throw Error('script must be an absolute UTF-8 .py path')
  if(args.expected_sha256!==undefined&&(typeof args.expected_sha256!=='string'||!/^[0-9a-f]{64}$/i.test(args.expected_sha256)))
    throw Error('expected_sha256 must be a 64-character SHA-256 hexadecimal digest')
  const filesystem=hostService(ctx,'fs'),policyService=hostService(ctx,'sandboxPolicy'),cwd=workspaceOf(exec)
  if(!filesystem||!policyService||!cwd)throw Error('Script execution requires the DSH workspace, filesystem and file policy')
  const target=await filesystem.resolve(args.script,{cwd,signal:exec.signal}),filename=filesystem.processPath(target)
  if(filesystem.processPathFromHostPath(filename)!==filename)throw Error('Script execution requires a local/shared Host filesystem')
  // The configured provider owns read policy. Do not reopen the path through node:fs.
  const bytes=Buffer.from(await filesystem.readBytes(target,exec.signal,MAX_SOURCE_BYTES))
  exec.signal?.throwIfAborted()
  const sha256=createHash('sha256').update(bytes).digest('hex')
  if(args.expected_sha256!==undefined&&sha256!==args.expected_sha256.toLowerCase())
    throw Error(`Script SHA-256 mismatch: expected ${args.expected_sha256.toLowerCase()}, read ${sha256}. The builder was not submitted.`)
  let code:string
  try {code=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes)}
  catch {throw Error('script must contain valid UTF-8 Python source')}
  return {code,script:{path:filename,sha256,bytes:bytes.length,...(args.code?.trim()?{entry:args.code}:{})}}
}
