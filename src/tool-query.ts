/** Query dispatch keeps local sources and history reads independent of HOM. */
import type { Context } from '@deepseek-ai/cordis'
import type { ExecResult } from './bridge.js'
import { visualCapability } from './image-output.js'
import { readResultDetail } from './result-details.js'
import { readTaskSource } from './task-sources.js'
import { HoudiniToolRuntime, workspaceOf } from './tool-runtime.js'

export interface HoudiniQuery {
  code?: string
  capabilities?: string
  source_ref?: string
  request_ref?: string
  result_ref?: string
  pointer?: string
  offset?: number
  limit?: number
}

export async function executeQuery(args: HoudiniQuery, exec: any,
  runtime: HoudiniToolRuntime, ctx: Context): Promise<ExecResult> {
  if ([args.code, args.result_ref, args.source_ref, args.request_ref, args.capabilities]
    .filter(value => value !== undefined).length !== 1) {
    throw new Error('provide exactly one of code, result_ref, source_ref, request_ref or capabilities')
  }
  const paginated = [args.pointer, args.offset, args.limit].some(value => value !== undefined)
  if (args.capabilities !== undefined) {
    if (args.capabilities !== 'visual' || paginated) throw new Error('capabilities requires visual, without pagination/pointer')
    return { ok: true, stdout: '', stderr: '', result: await visualCapability(exec, ctx) }
  }
  if (args.source_ref !== undefined) {
    if (args.pointer !== undefined) throw new Error('pointer requires result_ref; task sources use offset/limit')
    if (!exec?.agent) throw new Error('task sources require a current agent session')
    return readTaskSource(exec.agent.session.snapshotEvents(), args.source_ref, args.offset, args.limit)
  }
  if (args.result_ref !== undefined) return readResultDetail(
    workspaceOf(exec), args.result_ref, args.pointer, args.offset, args.limit)
  if (args.request_ref !== undefined) {
    if (paginated) throw new Error('request_ref does not accept pagination or pointer')
    const { bridge, owner } = await runtime.target(exec, false)
    const receipt = await bridge.requestStatus(args.request_ref, owner, exec.signal)
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
  if (paginated) throw new Error('pointer/offset/limit require result_ref')
  if (typeof args.code !== 'string' || !args.code.trim()) throw new Error('provide nonempty read-only code')
  const { bridge, owner } = await runtime.target(exec)
  return runtime.result(await bridge.exec(args.code, owner, exec.signal, undefined, true), exec, bridge, true)
}
