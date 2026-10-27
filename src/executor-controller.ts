/** Authenticated DSH Remote surface, not a model tool or a separate web server. */
import type { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import type {} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-agent-preset-registry'
import {targetMatchesRecord,targetSnapshot,type ExecutorRouter} from './executor-routing.js'
import {projectedExecutorState,type TargetSnapshot} from './executor-identity-projection.js'
import type {} from '@deepseek-ai/dsh-api-session-controller'
import type {} from '@deepseek-ai/dsh-workspace'
import path from 'node:path'

export class ExecutorController extends TypertRemoteService {
  private readonly openings=new Map<string,Promise<unknown>>()
  private unnamedSerial=0
  constructor(ctx:Context,private readonly router:ExecutorRouter,readonly workbench=false,readonly registry='') { super(ctx,'houdiniTargets') }

  private async workspaceFor(directory:string,isNew:boolean) {
    const same=(value:string)=>process.platform==='win32'?path.resolve(value).toLowerCase()===path.resolve(directory).toLowerCase():path.resolve(value)===path.resolve(directory)
    const existing=this.ctx.workspaceRegistry.list().find(item=>same(item.path))
    if(existing)return existing
    let title:string|undefined
    if(isNew) {
      this.unnamedSerial=Math.max(this.unnamedSerial,...this.ctx.workspaceRegistry.list().map(item=>Number(/^(?:临时工作区|未保存工程) (\d+)$/.exec(item.title)?.[1]??0)))+1
      title='临时工作区 '+this.unnamedSerial
    }
    return this.ctx.workspaceRegistry.create(directory,title)
  }

  private async agentFor(sessionId:string) {
    if(this.ctx.workspaceRegistry?.archivedSessionIds.includes(sessionId as any))throw new Error('原对话已归档，未改变其现场目标。')
    const resolved=await this.ctx.sessionController.resolveAgent(sessionId as any)
    if('error' in resolved||!resolved.agent)throw new Error('无法载入指定对话。')
    const agent=resolved.agent
    if(this.ctx.get('sessionProjections')?.stateOf(agent.session,'agentPreset')!=='houdini')
      throw new Error('请选择 Houdini 模式的对话。')
    return agent
  }

  @Remote
  async openWorkspace(input:unknown,signal:AbortSignal,expectedSelectionRevision?:number,beforeCommit?:()=>void) {
    if(!this.workbench)throw new Error('此 Host 未启用 Houdini 现场接入。')
    const data=input as Record<string,string>
    if(!data||typeof data!=='object'||!['executorId,expectedHip,registrationId,requestId','executorId,expectedHip,registrationId,requestId,sessionId',
      'bindSessionId,executorId,expectedHip,registrationId,requestId'].includes(Object.keys(data).sort().join(','))
      ||!Object.values(data).every(value=>typeof value==='string'&&value.length>0&&value.length<=4096)
      ||!['executorId','registrationId','requestId'].every(key=>/^[0-9a-f]{32}$/.test(data[key])))throw new Error('工作区打开请求无效。')
    const previous=this.openings.get(data.executorId)
    const operation=(async()=>{
      if(previous)await previous.catch(()=>{})
      signal.throwIfAborted()
      const record=await this.router.directory.find(data.executorId)
      if(!record.workbench||!record.workspace_path)throw new Error('此 Houdini 尚未登记完整现场。请在目标 Houdini 中连接 Desktop。')
      const requested=data.sessionId??data.bindSessionId
      const key=(value:string)=>process.platform==='win32'?path.normalize(value).toLowerCase():path.normalize(value)
      if(!requested&&record.registration_id!==data.registrationId||!record.hip_path||key(record.hip_path)!==key(data.expectedHip))
        throw new Error('工程在打开期间发生变化，请从目标 Houdini 重新打开工作台。')
      // The registered writer is an exact native Session identity. A menu
      // reconnect may reveal that conversation, but never select a different
      // target, adopt ownership, or infer one from the HIP directory/history.
      if(!requested&&record.task_id&&!this.ctx.workspaceRegistry.archivedSessionIds.includes(record.task_id as any)) {
        const resolved=await this.ctx.sessionController.resolveAgent(record.task_id as any)
        const receiptTarget=targetSnapshot(record)
        const requireSameReceipt=(current:typeof record)=>{
          if(current.registration_id!==record.registration_id||current.task_id!==record.task_id
            ||!targetMatchesRecord(receiptTarget,current)
            ||!current.hip_path||key(current.hip_path)!==key(data.expectedHip))
            throw new Error('工程或原对话在接入期间已变化，请从当前 Houdini 重新打开。')
        }
        requireSameReceipt(await this.router.directory.find(record.executor_id))
        if(this.ctx.workspaceRegistry.archivedSessionIds.includes(record.task_id as any))
          throw new Error('原对话在接入期间已归档，请从当前 Houdini 重新打开。')
        if('error' in resolved) {
          if(resolved.error.code!=='session/not-found')throw resolved.error
        } else {
          const agent=resolved.agent
          const target=projectedExecutorState(this.ctx,agent.session).selectedTarget
          if(agent.id===record.task_id&&agent.session.id===agent.id
            &&this.ctx.get('sessionProjections')?.stateOf(agent.session,'agentPreset')==='houdini'
            &&target&&targetMatchesRecord(target,record)) {
            const verified=await this.router.inspectSelectedTarget(target,signal)
            requireSameReceipt(verified)
            const current=projectedExecutorState(this.ctx,agent.session).selectedTarget
            if(this.ctx.workspaceRegistry.archivedSessionIds.includes(agent.id)
              ||this.ctx.get('sessionProjections')?.stateOf(agent.session,'agentPreset')!=='houdini'
              ||!current||!targetMatchesRecord(current,verified))
              throw new Error('原对话在接入期间已改选或归档，请从当前 Houdini 重新打开。')
            const workspace=this.ctx.workspaceRegistry.list().find(item=>item.sessionIds.includes(agent.id))
            return {sessionId:agent.id,executorId:current.executor_id,selectedTarget:current,
              ...(workspace?{workspaceId:workspace.id}:{})}
          }
        }
      }
      signal.throwIfAborted()
      // Only default new conversations use the selected scene's directory.
      // An explicit existing conversation keeps its native workspace and history.
      let workspace:Awaited<ReturnType<ExecutorController['workspaceFor']>>|undefined
      let sessionId=requested
      if(!sessionId) {
        workspace=await this.workspaceFor(record.workspace_path,record.hip_is_new===true)
        const created=await this.ctx.sessionController.create({workspaceId:workspace.id,sessionId:data.requestId as any,agentPreset:'houdini'})
        sessionId=created.sessionId
      }
      const agent=await this.agentFor(sessionId)
      const selectedTarget=await this.router.selectTarget(agent,record.executor_id,data.registrationId,signal,data.expectedHip,false,
        expectedSelectionRevision===undefined?undefined:{selectionRevision:expectedSelectionRevision,beforeCommit})
      const ownerWorkspace=workspace??this.ctx.workspaceRegistry.list().find(item=>item.sessionIds.includes(agent.id))
      return {sessionId:agent.id,executorId:selectedTarget.executor_id,selectedTarget,
        ...(ownerWorkspace?{workspaceId:ownerWorkspace.id}:{})}
    })()
    this.openings.set(data.executorId,operation)
    try{return await operation}
    finally{if(this.openings.get(data.executorId)===operation)this.openings.delete(data.executorId)}
  }

  /** In-process consumer API, deliberately not exposed as a Remote method. */
  getRouter(registry:string):ExecutorRouter {
    this.router.directory.requireRoot(registry)
    return this.router
  }

  @Remote
  async list(input:unknown) {
    if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).join(',')!=='sessionId'
      ||typeof (input as Record<string,unknown>).sessionId!=='string'||!(input as Record<string,string>).sessionId.length)
      throw new Error('Expected the exact sessionId')
    const agent=await this.agentFor((input as Record<string,string>).sessionId)
    const records=await this.router.directory.list()
    let selectedTarget:TargetSnapshot|null=null,state:{status:string;message?:string}
    try {
      const binding=projectedExecutorState(this.ctx,agent.session)
      selectedTarget=binding.selectedTarget
      const record=selectedTarget?records.find(row=>row.executor_id===selectedTarget!.executor_id):undefined
      state=!selectedTarget?{status:'unbound',...(binding.selectionRecorded?{message:'已解除目标，请明确选择后再操作。'}:{})}
        :!record||record.state==='disconnected'?{status:'unavailable',message:'所选现场已断开，没有自动改用其他窗口。'}
        :targetMatchesRecord(selectedTarget,record)?{status:'selected'}:{status:'stale',message:'所选窗口的场景已变化，请重新选择。'}
    } catch(error) {state={status:'unbound',message:error instanceof Error?error.message:String(error)}}
    const cwd=agent.session.header.cwd
    const key=(value:string)=>process.platform==='win32'?path.resolve(value).toLowerCase():path.resolve(value)
    const candidates=records.filter(record=>record.workbench&&record.state==='registered').map(record=>{
      const owner=record.task_id?this.ctx.agents.get(record.task_id as any):undefined
      return {...record,connection_status:'pending',same_workspace:Boolean(cwd&&record.workspace_path&&key(cwd)===key(record.workspace_path)),
        activity:{ownerSessionId:record.task_id,ownerStatus:owner?(owner.status==='idle'?'idle':'running'):'unknown'}}
    }).sort((left,right)=>Number(right.same_workspace)-Number(left.same_workspace))
    return {selectedTarget,state,candidates,boundary:'Selection changes only the operation target. Presence remains pending; reading claims no writer and selecting grants no node ownership.'}
  }

  @Remote
  async select(input:unknown,signal:AbortSignal) {
    if(!input||typeof input!=='object'||Array.isArray(input))throw new Error('Expected a target selection')
    const data=input as Record<string,unknown>
    if(!['sessionId','executorId','registrationId','expectedHip'].every(key=>typeof data[key]==='string'&&Boolean(data[key]))
      ||Object.keys(data).some(key=>!['sessionId','executorId','registrationId','expectedHip','runtimeId','sceneEpoch'].includes(key))
      ||['runtimeId','sceneEpoch'].some(key=>data[key]!==undefined&&typeof data[key]!=='string'))throw new Error('Invalid target selection')
    const agent=await this.agentFor(data.sessionId as string)
    const selectedTarget=await this.router.selectTarget(agent,data.executorId as string,data.registrationId as string,signal,
      data.expectedHip as string,false,{runtimeId:data.runtimeId as string|undefined,sceneEpoch:data.sceneEpoch as string|undefined})
    return {sessionId:agent.id,executorId:selectedTarget.executor_id,selectedTarget,status:'selected'}
  }

  @Remote
  async clear(input:unknown,signal:AbortSignal) {
    if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).join(',')!=='sessionId'
      ||typeof (input as Record<string,unknown>).sessionId!=='string')throw new Error('Expected the exact sessionId')
    const agent=await this.agentFor((input as Record<string,string>).sessionId)
    await this.router.clear(agent,signal)
    return {sessionId:agent.id,selectedTarget:null,status:'unbound'}
  }
}
