/** Authenticated DSH Remote surface, not a model tool or a separate web server. */
import type { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import type {} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-agent-preset-registry'
import type { ExecutorRecord, ExecutorRouter } from './executor-routing.js'
import {projectedExecutorIdentity,foldExecutorState} from './executor-identity-projection.js'
import {workspaceOpeningMessage,recordHoudiniContext} from './dsh-adapter.js'
import {relocateDirectory} from './scene-recovery.js'
import type {} from '@deepseek-ai/dsh-api-session-controller'
import type {} from '@deepseek-ai/dsh-session-query'
import type {} from '@deepseek-ai/dsh-workspace'
import path from 'node:path'
import {pruneScratchWorkspaces} from './workbench-workspaces.js'

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
  private readonly openings=new Map<string,Promise<unknown>>()
  private unnamedSerial=0
  constructor(ctx:Context,private readonly router:ExecutorRouter,readonly workbench=false) { super(ctx,'houdiniTargets') }

  /** Host-only lifecycle; cleanup failure never changes a successful binding. */
  async pruneEmptyWorkspaces(keep:readonly string[]=[]) {
    if(!this.workbench)return
    try {await pruneScratchWorkspaces(this.ctx,this.router.directory,keep)}
    catch(error) {this.ctx.logger.warn('空工作区登记暂未清理：'+String(error))}
  }

  private async workspaceFor(directory:string,isNew:boolean) {
    const same=(value:string)=>process.platform==='win32'?path.resolve(value).toLowerCase()===path.resolve(directory).toLowerCase():path.resolve(value)===path.resolve(directory)
    const existing=this.ctx.workspaceRegistry.list().find(item=>same(item.path))
    if(existing)return existing
    let title:string|undefined
    if(isNew) {
      this.unnamedSerial=Math.max(this.unnamedSerial,...this.ctx.workspaceRegistry.list().map(item=>Number(/^未保存工程 (\d+)$/.exec(item.title)?.[1]??0)))+1
      title='未保存工程 '+this.unnamedSerial
    }
    return this.ctx.workspaceRegistry.create(directory,title)
  }

  @Remote
  async prepareWorkspace(input:unknown) {
    const data=input as {path:string;isNew:boolean;onlyIfEmpty?:boolean}
    if(!this.workbench||!data||typeof data!=='object'||!['isNew,path','isNew,onlyIfEmpty,path'].includes(Object.keys(data).sort().join(','))
      ||typeof data.path!=='string'||data.path.length>4096||!path.isAbsolute(data.path)||typeof data.isNew!=='boolean'
      ||data.onlyIfEmpty!==undefined&&typeof data.onlyIfEmpty!=='boolean')throw new Error('工作区准备请求无效。')
    await this.pruneEmptyWorkspaces([data.path])
    const existing=this.ctx.workspaceRegistry.list()[0]
    if(data.onlyIfEmpty&&existing)return {workspaceId:existing.id}
    const workspace=await this.workspaceFor(data.path,data.isNew)
    return {workspaceId:workspace.id}
  }

  @Remote
  async activity() {
    const agents=this.ctx.agents.list()
    const active=new Set(agents.filter(agent=>agent.status!=='idle').map(agent=>agent.id))
    const identifiers=new Set([...agents.map(agent=>agent.id),
      ...(this.ctx.get('workspaceRegistry')?.list().flatMap(workspace=>workspace.sessionIds)??[])])
    await Promise.all([...identifiers].map(async sessionId=>{
      const activity=await this.ctx.waterfall('workspace/session-activity',{sessionId},()=>Promise.resolve([]))
      if(activity.length)active.add(sessionId)
    }))
    const sessions=this.ctx.get('sessions')
    if(!sessions||!(await Promise.all(sessions.list().map(session=>sessions.flush(session)))).every(saved=>saved===true))
      throw new Error('最近对话尚未可靠保存，未确认可以安全退出工作台。')
    return {activeConversations:active.size,durable:true}
  }

  @Remote
  async openWorkspace(input:unknown,signal:AbortSignal) {
    if(!this.workbench)throw new Error('此 Host 未启用独立工作台。')
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
      const samePath=(left:string,right:string)=>process.platform==='win32'
        ?path.normalize(left).toLowerCase()===path.normalize(right).toLowerCase():path.normalize(left)===path.normalize(right)
      if(!record.workbench||record.registration_id!==data.registrationId||!record.hip_path||!samePath(record.hip_path,data.expectedHip)||!record.workspace_path)
        throw new Error('工程在打开过程中发生变化，请从对应 Houdini 重新打开工作区。')
      const workspace=await this.workspaceFor(record.workspace_path,record.hip_is_new===true)
      const openingMessage=()=>workspaceOpeningMessage({...record,project_label:record.hip_is_new?workspace.title:undefined})
      let selected:string|undefined
      if(data.bindSessionId) {
        if(this.ctx.workspaceRegistry.archivedSessionIds.includes(data.bindSessionId as any))throw new Error('原对话已归档，未改变它的工程。')
        const resolved=await this.ctx.sessionController.resolveAgent(data.bindSessionId as any)
        if('error' in resolved)throw new Error('无法载入原对话。')
        const state=foldExecutorState(resolved.agent.session.snapshotEvents())
        if(state.identity&&state.identity!==record.executor_id)throw new Error('原对话已关联另一份工程，没有覆盖它的绑定。')
        if(this.ctx.get('sessionProjections')?.stateOf(resolved.agent.session,'agentPreset')!=='houdini')throw new Error('请使用 Houdini 模式的对话连接工程。')
        await this.router.selectInitial(resolved.agent,record.executor_id,record.registration_id,signal,record.hip_path)
        recordHoudiniContext(resolved.agent,openingMessage())
        await relocateDirectory(this.ctx,resolved.agent,record.workspace_path,record.hip_path,signal,record.hip_is_new===true,record)
        if(await this.ctx.sessions.flush(resolved.agent.session)!==true)throw new Error('工程选择尚未可靠保存。')
        selected=resolved.agent.id
      }
      const candidates:{sessionId:(typeof workspace.sessionIds)[number];state:ReturnType<typeof foldExecutorState>}[]=[]
      const sessions=data.sessionId?[data.sessionId as (typeof workspace.sessionIds)[number]]:[...workspace.sessionIds]
      for(const sessionId of selected?[]:sessions) {
        if(this.ctx.workspaceRegistry.archivedSessionIds.includes(sessionId))continue
        const history=await this.ctx.sessionQuery.readSession(sessionId)
        if(history.session.agentPreset!=='houdini'||history.session.origin==='subagent')continue
        const state=foldExecutorState(history.events),identity=state.identity
        const project=state.project
        const explicitlyUnexecuted=data.sessionId===sessionId&&identity!==record.executor_id&&!state.hasOperations&&!state.recovery
          &&typeof project?.hipPath==='string'&&samePath(project.hipPath,record.hip_path)
        // scene_id is copyable with the HIP file; association also requires the
        // recorded path so a copy cannot capture the original conversation.
        const sameScene=record.scene_id&&project?.sceneId===record.scene_id
          &&typeof project?.hipPath==='string'&&samePath(project.hipPath,record.hip_path!)
        const sameLoadedScene=identity===record.executor_id&&record.scene_epoch&&project?.sceneEpoch===record.scene_epoch
          &&typeof project?.hipPath==='string'&&samePath(project.hipPath,record.hip_path!)
        if(identity&&(sameScene||sameLoadedScene||explicitlyUnexecuted))
          candidates.push({sessionId,state})
      }
      if(!selected&&candidates.length>1&&!data.sessionId) {
        const current=candidates.find(candidate=>candidate.sessionId===record.task_id&&candidate.state.identity===record.executor_id)
        if(current)selected=current.sessionId
        else throw new Error('这份工程关联多段对话。请先在左侧选择要继续的对话，再点「打开关联工程」；没有按历史顺序替你选择。')
      }
      if(!selected&&candidates.length===1) {
        const candidate=candidates[0]
        if(candidate.state.identity===record.executor_id)selected=candidate.sessionId
        else if(!candidate.state.hasOperations&&data.sessionId===candidate.sessionId) {
          // An explicit sidebar choice may re-select an unexecuted conversation;
          // an implicit scene match never re-points a different conversation.
          const resolved=await this.ctx.sessionController.resolveAgent(candidate.sessionId)
          if('error' in resolved)throw new Error('无法载入原对话。')
          await this.router.selectInitial(resolved.agent,record.executor_id,record.registration_id,signal,record.hip_path,false,true)
          recordHoudiniContext(resolved.agent,openingMessage())
          if(await this.ctx.sessions.flush(resolved.agent.session)!==true)throw new Error('工程选择尚未可靠保存。')
          selected=candidate.sessionId
        } else if(!candidate.state.hasOperations) {
          throw new Error('这份工程关联的对话已绑定其他工程。请在左侧选择要继续的对话，再点「打开关联工程」；没有自动换绑。')
        } else {
          const history=await this.ctx.sessionQuery.readSession(candidate.sessionId)
          const assessment=await this.router.inspectRecovery({id:candidate.sessionId,snapshotEvents:()=>history.events},record.executor_id,signal)
          signal.throwIfAborted()
          if(!assessment)throw new Error('已找到原对话，但当前工程尚未通过接续核对；没有创建替代对话或改变原绑定。')
          selected=candidate.sessionId
        }
      }
      if(!selected) {
        if(data.sessionId)throw new Error('已打开工程，但它与原对话的工程记录不匹配；原对话没有换绑。')
        const created=await this.ctx.sessionController.create({workspaceId:workspace.id,sessionId:data.requestId as any,agentPreset:'houdini'})
        const resolved=await this.ctx.sessionController.resolveAgent(created.sessionId)
        if('error' in resolved)throw new Error('无法载入新建对话。')
        await this.router.selectInitial(resolved.agent,record.executor_id,record.registration_id,signal,record.hip_path!)
        recordHoudiniContext(resolved.agent,openingMessage())
        if(await this.ctx.sessions.flush(resolved.agent.session)!==true)throw new Error('工作区对话尚未可靠保存，未确认打开成功。')
        selected=created.sessionId
      }
      // A conversation recorded against another executor needs the recovery
      // service first: that service verifies the checkpoint, takes the writer
      // reservation and writes the recovery binding. Claiming it through
      // selectInitial first would reject the identity change before recovery
      // could run, leaving a claimed but unbound conversation.
      {
        const resolved=await this.ctx.sessionController.resolveAgent(selected as any)
        if('error' in resolved)throw new Error('无法读取原对话。')
        if(foldExecutorState(resolved.agent.session.snapshotEvents()).identity!==record.executor_id) {
          if(resolved.agent.status!=='idle')throw new Error('原对话仍在运行，请等待当前任务结束后再接续。')
          const recovery=this.ctx.get('agentPresets')?.serviceFor(resolved.agent,'houdiniRecovery')
          if(!recovery)throw new Error('工程已打开，当前环境没有提供原对话接续能力。')
          const assessment=await recovery.assess(resolved.agent,signal,record.executor_id) as any
          if(assessment.status!=='ready'||typeof assessment.assessment_id!=='string')throw new Error('工程已打开，但原对话尚未通过保存点接续核对。')
          if(assessment.requires_reload&&!(assessment.dirty_reliable&&!assessment.dirty))
            throw new Error('工程已打开，但还有未保存的内容需要确认。请回到原对话继续；没有丢弃当前修改。')
          await recovery.restore(resolved.agent,assessment.assessment_id,signal,record.executor_id)
          await recovery.followDirectory(resolved.agent,signal,true)
          if(foldExecutorState(resolved.agent.session.snapshotEvents()).identity!==record.executor_id)throw new Error('工程已打开，但原对话尚未完成接续。')
        }
      }
      // Selecting a conversation is an explicit claim. Returning "bound" while
      // the Bridge lease still belongs to another task (or is unclaimed) would
      // make the next tool fail after the user was told the project opened.
      // Re-read the record after recovery: activation may have changed the
      // scene generation and its registration id.
      {
        const resolved=await this.ctx.sessionController.resolveAgent(selected as any)
        if('error' in resolved)throw new Error('无法读取原对话。')
        if(resolved.agent.status!=='idle')throw new Error('原对话仍在运行，请等待当前任务结束后再接续。')
        const current=await this.router.directory.find(record.executor_id)
        if(current.task_id!==selected) {
          await this.router.selectInitial(resolved.agent,record.executor_id,current.registration_id,signal,current.hip_path!)
          if(await this.ctx.sessions.flush(resolved.agent.session)!==true)throw new Error('工程选择尚未可靠保存。')
        }
      }
      signal.throwIfAborted()
      await this.pruneEmptyWorkspaces([record.workspace_path])
      return {sessionId:selected,executorId:record.executor_id,workspaceId:workspace.id}
    })()
    this.openings.set(data.executorId,operation)
    try {return await operation}
    finally {if(this.openings.get(data.executorId)===operation)this.openings.delete(data.executorId)}
  }

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
      try {recorded=projectedExecutorIdentity(this.ctx,task.session)}
      catch(error) {recovery=executorRecoveryStatus(undefined,records,error)}
      if(recovery===undefined)recovery=executorRecoveryStatus(recorded,records)
    }
    return {candidates:records.map(r=>{
      const owner=r.task_id?this.ctx.agents.get(r.task_id as Parameters<typeof this.ctx.agents.get>[0]):undefined
      let binding_status='not_confirmed'
      try {if(owner&&projectedExecutorIdentity(this.ctx,owner.session)===r.executor_id)binding_status='bound'}
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
    const projections=this.ctx.get('sessionProjections')
    if(!projections) throw new Error('Session preset projection unavailable; no live request sent')
    const preset=projections.stateOf(agent.session,'agentPreset')
    if(preset!=='houdini') throw new Error('Target selection is restricted to Houdini tasks')
    await this.router.selectInitial(agent,data.executorId as string,data.registrationId as string,signal,data.expectedHip as string)
    if(await this.ctx.get('sessions')?.flush(agent.session)!==true)throw new Error('工程选择尚未可靠保存，未确认连接成功。')
    return {sessionId:agent.id,executorId:data.executorId,status:'bound',scene_verification:'not_performed'}
  }
}
