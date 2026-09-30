/** Host resource reads and recovery use distinct contracts, never live code. */
import type {ExecResult} from './bridge.js'
import {readResultDetail} from './result-details.js'
import {readTaskSource} from './task-sources.js'
import {HoudiniToolRuntime,workspaceOf} from './tool-runtime.js'

export function readResource(args:{kind:'source'|'result';ref:string;pointer?:string;offset?:number;limit?:number},exec:any):Promise<ExecResult>|ExecResult {
  if(args.kind==='result') return readResultDetail(workspaceOf(exec),args.ref,args.pointer,args.offset,args.limit)
  if(args.kind!=='source') throw Error('kind must be source or result')
  if(args.pointer!==undefined) throw Error('pointer is only used for result resources')
  const session=exec?.agent?.session
  if(!session?.snapshotEvents) throw Error('Task sources require a current agent session')
  return readTaskSource(session.snapshotEvents(),args.ref,args.offset,args.limit)
}

export async function recoverRequest(request_ref:string,exec:any,runtime:HoudiniToolRuntime):Promise<ExecResult> {
    const { bridge, owner } = await runtime.target(exec, false)
    const receipt = await bridge.requestStatus(request_ref, owner, exec.signal)
    const recovered: any = receipt.requestReceipt
    const jobId = recovered?.jobId || (recovered?.status === 'done' && recovered.result?.jobId)
    if (jobId) return { ok: true, stdout: '', stderr: '', result: { jobId }, requestReceipt: {
      request_ref: recovered.request_ref, runtime_id: recovered.runtime_id,
      owner_call: recovered.owner_call ?? null, status: 'job_submitted', jobId, retrieved: true,
      note: 'Original job admission recovered, not completed execution. Collect houdini_job_status(jobId).',
    } }
    if (recovered?.status === 'done' && recovered.result) return runtime.result({
      ...recovered.result, requestReceipt: {
        request_ref: recovered.request_ref, runtime_id: recovered.runtime_id,
        owner_call: recovered.owner_call ?? null, status: 'done', retrieved: true,
      },
    }, exec, bridge)
    return receipt
}
