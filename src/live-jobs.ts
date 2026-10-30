/** DSH owns job lifecycle; the original Bridge owns HOM execution and receipts. */
import type {Context} from '@deepseek-ai/cordis'
import type {JobHandle as NativeJobHandle,JobOutcome} from '@deepseek-ai/dsh-jobs'
import type {HoudiniBridge,JobHandle,JobStatus,OwnershipScope,ExecResult} from './bridge.js'
import type {ExecutionSource} from './execution-source.js'
import {hostService} from './api-route.js'
import {HoudiniToolRuntime} from './tool-runtime.js'
import {LIVE_JOB_KIND,LIVE_JOB_RESULT,LIVE_JOB_OUTPUT_LIMIT_BYTES} from './dsh-adapter.js'
declare module '@deepseek-ai/dsh-jobs/view' {interface JobKindMap {'houdini-live':'houdini-live'}}

type Admission=JobHandle&{job_id:string}
const terminal=(status:unknown)=>['done','failed','cancelled'].includes(String(status))
const nextAction=(ref:unknown)=>typeof ref==='string'
  ?`Use houdini_request(request_ref=${JSON.stringify(ref)}) for the original result, images, or renewed observation. Never resubmit the scene code.`
  :'No Bridge receipt was obtained. Inspect the original request index before considering another submission.'

/** The map holds only active local observer handles, never a second execution ledger. */
export class LiveJobs {
  private readonly observing=new Map<string,string>()
  constructor(private readonly ctx:Context,private readonly runtime:HoudiniToolRuntime){}

  async submit(source:ExecutionSource,exec:any,bridge:HoudiniBridge,owner:OwnershipScope,allowRaw?:string):Promise<Admission> {
    return this.start(exec,bridge,owner,signal=>bridge.submitJob(source.code,owner,signal,allowRaw,source.script))
  }

  async observe(handle:JobHandle,exec:any,bridge:HoudiniBridge,owner:OwnershipScope):Promise<Admission> {
    const ref=(handle.requestReceipt as any)?.request_ref
    if(typeof ref!=='string')throw Error('Live job observation requires the original request receipt')
    const id=this.observing.get(ref)
    if(id)return {...handle,job_id:id}
    return this.start(exec,bridge,owner,async()=>handle,ref)
  }

  private async start(exec:any,bridge:HoudiniBridge,owner:OwnershipScope,
    admit:(signal:AbortSignal)=>Promise<JobHandle>,receiptKey?:string):Promise<Admission> {
    const jobs=hostService(this.ctx,'jobs')
    if(!jobs)throw Error('DSH native jobs are required for live background work')
    exec.signal?.throwIfAborted()
    let admitted!:(value:JobHandle)=>void
    const admission=new Promise<JobHandle>(resolve=>{admitted=resolve})
    // DSH checks the owner, controller and concurrency cap BEFORE run().
    const id=jobs.start({kind:LIVE_JOB_KIND,label:'Houdini · 工程长任务',owner:owner.sessionId,
      toolCall:{callId:exec.callId,rootCallId:exec.rootCallId??exec.callId},outputLimitBytes:LIVE_JOB_OUTPUT_LIMIT_BYTES,
      run:(job:NativeJobHandle)=>{
        if(receiptKey)this.observing.set(receiptKey,job.id)
        const controller=new AbortController()
        let handle:JobHandle={},original:HoudiniBridge|undefined,cancelRequested=false,cancelled=false,finished=false
        let cancellation:Promise<void>|undefined
        const detach=()=>{if(!finished)controller.abort(Error('Local observation closed; the original Houdini execution may continue'))}
        // Owner and producer teardown release this observer, never kill Houdini.
        const releaseOwner=exec.agent.ctx.effect(()=>detach,'Houdini live observer')
        const releaseProducer=this.ctx.effect(()=>detach,'Houdini live observer producer')
        const cancel=()=>{
          cancelRequested=true
          if(!handle.jobId||!original||cancellation)return
          cancellation=original.cancelJob(handle.jobId,owner,controller.signal).then(status=>{
            cancelled=status.status==='cancelled'
            job.updateProgress(cancelled?'排队任务已取消':'原生计算已运行，保留其实际结果，完成后通知')
          }).catch(error=>{
            if(!controller.signal.aborted)job.updateProgress('取消尚未确认；仍在观察原执行：'+String(error))
          })
        }
        const done:Promise<JobOutcome>=(async()=>{
          try {
            controller.signal.throwIfAborted()
            handle=await admit(controller.signal)
            const receipt=handle.requestReceipt as any
            if(receipt?.request_ref)this.observing.set(receipt.request_ref,job.id)
            admitted(handle)
            controller.signal.throwIfAborted()
            if(typeof receipt?.runtime_id!=='string')throw Error(handle.error??'No original Bridge runtime was returned')
            original=bridge.forRuntime(receipt.runtime_id)
            if(!handle.jobId&&typeof receipt.request_ref==='string'){
              const recovered=await original.requestStatus(receipt.request_ref,owner,controller.signal)
              const facts=recovered.requestReceipt as any
              const jobId=facts?.jobId??facts?.result?.jobId
              if(typeof jobId==='string')handle={jobId,requestReceipt:{...receipt,...facts,jobId},error:undefined}
            }
            if(!handle.jobId)throw Error(handle.error??'Original job admission could not be confirmed')
            if(cancelRequested)cancel()
            let status:JobStatus
            do {
              job.updateProgress(cancelRequested?'等待原计算的真实结果':'Houdini 主线程排队或计算中')
              status=await original.jobStatus(handle.jobId,owner,30,controller.signal)
            }while(!terminal(status.status))
            const value=await this.runtime.retain({...status,requestReceipt:{...(handle.requestReceipt as any),
              status:'done',jobId:handle.jobId,job_status:status.status,job_finished:true,job_result_available:true,
              result:undefined}},exec)
            return {status:status.status==='cancelled'?'killed':status.status==='failed'?'failed':'completed',
              detail:status.status==='cancelled'?'排队任务已取消':status.ok?'原执行已结束；检查与质量以回执为准':'Houdini 返回执行失败',
              result:JSON.stringify({kind:LIVE_JOB_RESULT,job_id:job.id,value,
                next_action:nextAction((handle.requestReceipt as any)?.request_ref)})}
          }catch(error){
            admitted(handle)
            // Native observer failure is never evidence that HOM failed/stopped.
            let value:ExecResult={ok:false,stdout:'',stderr:'',error:String(error),
              requestReceipt:{...(handle.requestReceipt as any),status:'unknown_transport',
                note:'Local job observation ended. The original execution outcome is unverified; no code was replayed.'}}
            const ref=(handle.requestReceipt as any)?.request_ref
            if(!controller.signal.aborted&&original&&ref)try {
              const recovered=await original.requestStatus(ref,owner,controller.signal)
              const facts=recovered.requestReceipt as any
              if(facts?.job_finished===true&&facts.job_result_available===false)value={...recovered,
                requestReceipt:{...facts,note:'Original execution finished but its result is no longer retained. Outcome unverified; inspect the scene. Do not resubmit.'}}
            }catch{/* The original receipt remains the only recovery route. */}
            return {status:cancelled?'killed':'failed',detail:'工程任务跟踪已断开；原执行结果须查回',
              result:JSON.stringify({kind:LIVE_JOB_RESULT,job_id:job.id,value,
                next_action:nextAction((handle.requestReceipt as any)?.request_ref)})}
          }finally{
            finished=true
            controller.abort()
            await cancellation
            const ref=(handle.requestReceipt as any)?.request_ref??receiptKey
            if(ref&&this.observing.get(ref)===job.id)this.observing.delete(ref)
            releaseOwner();releaseProducer()
          }
        })()
        return {done,cancel}
      }})
    return {...await admission,job_id:id}
  }
}
