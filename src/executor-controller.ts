/** Authenticated DSH Remote surface, not a model tool or a separate web server. */
import type { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import type {} from '@deepseek-ai/dsh-agent'
import type { ExecutorRecord, ExecutorRouter } from './executor-routing.js'
import {recordedExecutorIdentity} from './execution-state.js'

export function executorRecoveryStatus(recorded:string|undefined,records:readonly ExecutorRecord[],conflict?:unknown):Record<string,unknown> {
  if(conflict!==undefined)return {status:'history_conflict',message:'任务历史含冲突的执行端身份；未发送live请求。请保留HIP与历史证据，当前版本不能自动恢复或换绑。',
    detail:conflict instanceof Error?conflict.message:String(conflict)}
  const original=recorded?records.find(r=>r.executor_id===recorded):undefined
  if(!recorded)return {status:'unbound',message:'本任务尚未绑定Houdini；首次选择仍会核对HIP、代际和写入预留。'}
  if(!original)return {status:'bound_missing',executorId:recorded,
    message:'原Houdini执行端已不在登记目录；未发送live请求。跨进程恢复尚未实现，请保留已保存/崩溃HIP与任务历史。'}
  if(original.state==='disconnected')return {status:'bound_disconnected',executorId:recorded,hipPath:original.hip_path,
    message:'原Houdini执行端已断开；未发送live请求。新的Houdini不是原绑定，当前版本不能直接迁移此任务。'}
  return {status:'bound_available',executorId:recorded,hipPath:original.hip_path,
    message:'原任务执行端仍有登记；所有现场调用仍会重新核对进程代际、HIP和写入预留，登记本身不证明在线。'}
}

export class ExecutorController extends TypertRemoteService {
  constructor(ctx:Context,private readonly router:ExecutorRouter) { super(ctx,'houdiniTargets') }

  /** In-process consumer API, deliberately not exposed as a Remote method. */
  getRouter(registry:string):ExecutorRouter {
    this.router.directory.requireRoot(registry)
    return this.router
  }

  @Remote
  async list(input:unknown) {
    const records=await this.router.directory.list()
    let recovery:Record<string,unknown>|undefined
    if(input===undefined) {
      recovery={status:'session_required',message:'执行端发现可用；刷新客户端并从具体任务打开面板，才能核对该任务的持久绑定与恢复状态。'}
    } else {
      if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).join(',')!=='sessionId'
        ||typeof (input as Record<string,unknown>).sessionId!=='string'
        ||!(input as Record<string,string>).sessionId.length||(input as Record<string,string>).sessionId.length>256)
        throw new Error('Expected the exact open sessionId')
      const sessionId=(input as Record<string,string>).sessionId
      const task=this.ctx.agents.get(sessionId as Parameters<typeof this.ctx.agents.get>[0])
      if(!task)throw new Error('Open the intended task before inspecting its executor binding')
      let recorded:string|undefined
      try {recorded=recordedExecutorIdentity(task.session.snapshotEvents())}
      catch(error) {recovery=executorRecoveryStatus(undefined,records,error)}
      if(recovery===undefined)recovery=executorRecoveryStatus(recorded,records)
    }
    return {candidates:records.map(r=>{
      const owner=r.task_id?this.ctx.agents.get(r.task_id as Parameters<typeof this.ctx.agents.get>[0]):undefined
      let binding_status='not_confirmed'
      try {if(owner&&recordedExecutorIdentity(owner.session.snapshotEvents())===r.executor_id)binding_status='bound'}
      catch {binding_status='history_conflict'}
      return {...r,connection_status:'unverified',binding_status}
    }),recovery:recovery!,
      boundary:'Records are discovery hints, not online proof. Initial selection requires an idle task and a matching Houdini writer reservation.'}
  }

  @Remote
  async select(input:unknown,signal:AbortSignal) {
    if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).sort().join(',')!=='executorId,expectedHip,registrationId,sessionId') throw new Error('Expected sessionId, executorId, registrationId and expectedHip')
    const data=input as Record<string,unknown>
    if(!Object.entries(data).every(([k,v])=>typeof v==='string'&&v.length>0&&v.length<=(k==='expectedHip'?4096:256))) throw new Error('Invalid target selection')
    const agent=this.ctx.agents.get(data.sessionId as Parameters<typeof this.ctx.agents.get>[0])
    if(!agent) throw new Error('Open the intended task before selecting its executor; no task is resumed implicitly')
    let preset=agent.session.header.agentPreset
    for(const event of agent.session.snapshotEvents() as readonly {type:string;data?:{agentPreset?:string}}[]) {
      if(event.type==='agent-preset/selected') preset=event.data?.agentPreset
    }
    if(preset!=='houdini'&&preset!=='houdini-dev') throw new Error('Target selection is restricted to Houdini tasks')
    await this.router.selectInitial(agent,data.executorId as string,data.registrationId as string,signal,data.expectedHip as string)
    return {sessionId:agent.id,executorId:data.executorId,status:'bound',scene_verification:'not_performed'}
  }
}
