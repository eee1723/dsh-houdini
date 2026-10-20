/** Host resource reads and recovery use distinct contracts, never live code. */
import type {ExecResult} from './bridge.js'
import {readResultDetail,recordedResultPath} from './result-details.js'
import {readTaskSource} from './task-sources.js'
import {HoudiniToolRuntime,workspaceOf} from './tool-runtime.js'
import {recordedLoadWarningPath} from './executor-identity-projection.js'
import {requestStatusGuidance} from './execution-history.js'
import type {LiveJobs} from './live-jobs.js'

export function readResource(args:{kind:'source'|'result';ref:string;pointer?:string;offset?:number;limit?:number},exec:any):Promise<ExecResult>|ExecResult {
  if(args.kind==='result') {
    const events=exec?.agent?.session?.snapshotEvents?.()??[]
    const retained=recordedResultPath(events,args.ref)??recordedLoadWarningPath(events,args.ref)
    return readResultDetail(workspaceOf(exec),args.ref,args.pointer,args.offset,args.limit,retained)
  }
  if(args.kind!=='source') throw Error('kind must be source or result')
  if(args.pointer!==undefined) throw Error('pointer is only used for result resources')
  const session=exec?.agent?.session
  if(!session?.snapshotEvents) throw Error('Task sources require a current agent session')
  return readTaskSource(session.snapshotEvents(),args.ref,args.offset,args.limit)
}

export async function recoverRequest(request_ref:string,exec:any,runtime:HoudiniToolRuntime,liveJobs:LiveJobs):Promise<ExecResult> {
    const { bridge, owner } = await runtime.historicalTarget(exec,{requestRef:request_ref})
    const receipt = await bridge.requestStatus(request_ref, owner, exec.signal)
    const recovered: any = receipt.requestReceipt
    const jobId = recovered?.jobId || (recovered?.status === 'done' && recovered.result?.jobId)
    if (jobId) {
      const {result:_admission,...facts}=recovered
      const unavailable=recovered.job_finished===true && recovered.job_result_available===false
      if(unavailable)return { ok: true, stdout: '', stderr: '', result: { jobId }, requestReceipt: {
        ...facts, owner_call: recovered.owner_call ?? null,
        status: recovered.status==='done' ? 'job_submitted' : recovered.status, jobId, retrieved: true,
        note:'Original job has finished and its execution result is no longer retained. Outcome unverified; inspect the scene. Do not poll the missing job or resubmit it.',
      } }
      const status=await bridge.jobStatus(jobId,owner,0,exec.signal)
      const active=['queued','running'].includes(status.status)
      const requestReceipt={...facts,status:'done',jobId,retrieved:true,
        job_status:status.status,job_finished:!active,job_result_available:!active}
      let observation
      if(active)try {observation=await liveJobs.observe({jobId,requestReceipt},exec,bridge,owner)}
      catch(error){status.advisory=[status.advisory,'DSH could not attach an observer; the original job is still '+status.status+'. '+String(error)].filter(Boolean).join('\n')}
      return runtime.result({...status,...(observation?.job_id?{job_id:observation.job_id}:{}),requestReceipt},exec,bridge)
    }
    if (recovered?.status === 'done' && recovered.result) return runtime.result({
      ...recovered.result, requestReceipt: {
        request_ref: recovered.request_ref, runtime_id: recovered.runtime_id,
        owner_call: recovered.owner_call ?? null, status: 'done', retrieved: true,
      },
    }, exec, bridge)
    const guidance=requestStatusGuidance(recovered?.status)
    return guidance ? {...receipt,requestReceipt:{...recovered,note:guidance}} : receipt
}
