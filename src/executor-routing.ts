/** Shared Host routing candidate: no global 'current Houdini', no default target.
 * Registry records are hints; each selected endpoint must pass the Bridge header
 * guard and contract check. Selection never adopts node ownership or loads HIP.
 */
import fs from 'node:fs/promises'
import path from 'node:path'
import { HoudiniBridge } from './bridge.js'
import { ExecutorBinding } from './executor-binding.js'
import {foldExecutorState,targetSnapshotSchema,type TargetSnapshot} from './executor-identity-projection.js'
import {executionHistory} from './execution-history.js'
export type {TargetSnapshot} from './executor-identity-projection.js'

export interface ExecutorRecord {
  schema:1
  executor_id:string
  registration_id:string
  runtime_id:string
  installation:string
  bridge_url:string
  houdini_version:string
  pid:number
  state:'registered'|'disconnected'
  task_id:string|null
  hip_path:string|null
  workbench?:boolean
  scene_id?:string
  scene_epoch?:string
  hip_is_new?:boolean
  workspace_path?:string
}
type Session = Parameters<ExecutorBinding['ensure']>[0] & {id:string;header?:{cwd?:string}}
type Agent = {id:string;session:Session;status?:string}
export type ResolveOptions={write?:boolean}
const ID=/^[0-9a-f]{32}$/
const canonical = (p:string) => process.platform==='win32' ? path.normalize(p).toLowerCase() : path.normalize(p)
export class ExecutorUnavailableError extends Error {}

export class ExecutorDirectory {
  constructor(private readonly root:string, private readonly installation:string) {
    if (!path.isAbsolute(root)||!path.isAbsolute(installation)) throw new Error('Executor registry and installation paths must be absolute')
  }
  requireRoot(root:string):void {
    if(!path.isAbsolute(root)||canonical(root)!==canonical(this.root)) throw new Error('Shared Houdini registry configuration differs from the Host service; no fallback to a different registry')
  }
  private async read(id:string,expectedDirectory:string,expectedInstall:string):Promise<ExecutorRecord|undefined> {
    const filename=path.join(this.root,'endpoints',id+'.json')
    let stat
    try {stat=await fs.lstat(filename)}
    catch(error) {if((error as NodeJS.ErrnoException).code==='ENOENT')return undefined;throw error}
    if(!stat.isFile()||stat.isSymbolicLink()||stat.size>16384||canonical(path.dirname(await fs.realpath(filename)))!==expectedDirectory) throw new Error('Invalid executor record path/size')
    const text=await fs.readFile(filename,'utf8')
    if(Buffer.byteLength(text)>16384) throw new Error('Executor record exceeds read budget')
    const r=JSON.parse(text)
    if(!r||r.schema!==1||r.executor_id!==id||!ID.test(r.registration_id)||!ID.test(r.runtime_id)
      ||typeof r.installation!=='string'||!path.isAbsolute(r.installation)
      ||typeof r.bridge_url!=='string'||!/^http:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(r.bridge_url)
      ||!Number.isInteger(r.pid)||r.pid<=0||!['registered','disconnected'].includes(r.state)
      ||typeof r.houdini_version!=='string'||!/^\d+\.\d+\.\d+$/.test(r.houdini_version)
      ||!(r.task_id===null||typeof r.task_id==='string'&&r.task_id.length>0)
      ||!(r.hip_path===null||typeof r.hip_path==='string'&&path.isAbsolute(r.hip_path))) throw new Error('Invalid executor record')
    if(r.workbench===true&&(!ID.test(r.scene_id)||!ID.test(r.scene_epoch)||typeof r.hip_is_new!=='boolean'
      ||typeof r.workspace_path!=='string'||!path.isAbsolute(r.workspace_path)))throw new Error('Invalid workbench scene registration')
    const port=Number(new URL(r.bridge_url).port)
    if(port<1024||port>65535) throw new Error('Invalid registered Bridge port')
    // Accept the configured spelling or its resolved installation identity;
    // a foreign installation is never loaded to resolve an endpoint record.
    const recordedInstall=canonical(r.installation)
    if(recordedInstall!==canonical(this.installation)&&recordedInstall!==expectedInstall)return undefined
    return r
  }
  async list(): Promise<ExecutorRecord[]> {
    let files:string[]
    const directory=path.join(this.root,'endpoints')
    try { files=await fs.readdir(directory) }
    catch(error) { if((error as NodeJS.ErrnoException).code==='ENOENT') return [];throw error }
    files=files.filter(f=>f.endsWith('.json')).sort()
    const expectedInstall=canonical(await fs.realpath(this.installation))
    const expectedDirectory=canonical(await fs.realpath(directory))
    const records:ExecutorRecord[]=[]
    let registered=0
    for(const file of files) {
      if(!ID.test(file.slice(0,-5))) throw new Error('Invalid executor record filename')
      const record=await this.read(file.slice(0,-5),expectedDirectory,expectedInstall)
      if(!record)continue
      // Retired process evidence remains available to recovery diagnostics.
      // It does not consume the budget for this installation's registered targets.
      if(record.state==='registered'&&++registered>256)throw new Error('Registered executor discovery budget exceeded')
      records.push(record)
    }
    return records
  }
  async find(id:string):Promise<ExecutorRecord> {
    if(!ID.test(id)) throw new Error('Invalid executor identity')
    let record:ExecutorRecord|undefined
    try {
      record=await this.read(id,canonical(await fs.realpath(path.join(this.root,'endpoints'))),
        canonical(await fs.realpath(this.installation)))
    } catch(error) {if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error}
    if(!record||record.state!=='registered') throw new ExecutorUnavailableError('Bound Houdini is disconnected or absent; no automatic target substitution')
    return record
  }
}

export function targetSnapshot(record:ExecutorRecord):TargetSnapshot {
  return targetSnapshotSchema.parse({executor_id:record.executor_id,runtime_id:record.runtime_id,
    scene_epoch:record.scene_epoch,scene_id:record.scene_id??null,registration_id:record.registration_id,
    hip_path:record.hip_path,hip_is_new:record.hip_is_new===true,workspace_path:record.workspace_path})
}
export function targetMatchesRecord(target:TargetSnapshot,record:ExecutorRecord):boolean {
  return record.state==='registered'&&record.executor_id===target.executor_id&&record.runtime_id===target.runtime_id
    &&record.scene_epoch===target.scene_epoch&&record.scene_id===target.scene_id
}
function sameTargetIntent(left:TargetSnapshot,right:TargetSnapshot):boolean {
  return left.executor_id===right.executor_id&&left.runtime_id===right.runtime_id&&left.scene_epoch===right.scene_epoch
    &&left.scene_id===right.scene_id&&canonical(left.hip_path)===canonical(right.hip_path)
}

/** Selection is per conversation. Routing never chooses a replacement for a stale target. */
export class ExecutorRouter {
  private readonly lifetime=new AbortController()
  private readonly selections=new WeakMap<object,Promise<void>>()
  private readonly targetChanges=new WeakMap<object,Promise<unknown>>()
  dispose():void {this.lifetime.abort(new Error('Shared Houdini Host service was unloaded'))}
  private signal(signal?:AbortSignal):AbortSignal {
    return signal?AbortSignal.any([signal,this.lifetime.signal]):this.lifetime.signal
  }
  constructor(readonly directory:ExecutorDirectory,private readonly timeoutMs:number,
    private readonly binding:ExecutorBinding,
    private readonly identityOf:(session:Session)=>string|undefined,
    private readonly idleOwner:(taskId:string)=>boolean=()=>false,
    private readonly persist?:(session:Session)=>Promise<boolean>,
    private readonly chooseTarget?:(taskId:string,candidates:readonly ExecutorRecord[],signal:AbortSignal)=>Promise<string|undefined>) {}

  private async checkpoint(session:Session):Promise<void> {
    if(this.persist&&await this.persist(session)!==true)throw new Error('对话记录尚未可靠保存，本次操作没有发送到 Houdini。')
  }
  private state(session:Session) {
    // The registered DSH projection remains the authoritative live consumer.
    this.identityOf(session)
    return foldExecutorState(session.snapshotEvents())
  }
  private bridge(record:ExecutorRecord,expected:{runtimeId?:string;sceneEpoch?:string}) {
    return new HoudiniBridge(record.bridge_url,this.timeoutMs,record.executor_id,this.lifetime.signal,expected)
  }
  private async verified(target:TargetSnapshot,signal?:AbortSignal):Promise<{record:ExecutorRecord;bridge:HoudiniBridge}> {
    const bounded=this.signal(signal)
    bounded.throwIfAborted()
    const record=await this.directory.find(target.executor_id)
    if(!targetMatchesRecord(target,record))throw new Error('所选 Houdini 的场景或运行代际已变化，请重新选择目标；没有自动改用其他窗口。')
    const bridge=this.bridge(record,{runtimeId:target.runtime_id,sceneEpoch:target.scene_epoch})
    const health=await bridge.inspectExecutor(bounded)
    if(health.runtimeId!==target.runtime_id||health.houVersion!==record.houdini_version
      ||health.sceneEpoch!==target.scene_epoch)throw new Error('所选 Houdini 现场已变化，请重新选择目标。')
    const after=await this.directory.find(target.executor_id)
    if(!targetMatchesRecord(target,after)||after.registration_id!==record.registration_id)
      throw new Error('工程在核对期间发生变化，请重新选择目标。')
    return {record:after,bridge}
  }

  /** First scene use only; ordinary chat and ambient context never call this chooser. */
  async selectFor(agent:Agent,signal:AbortSignal):Promise<void> {
    const state=this.state(agent.session)
    if(state.selectedTarget)return
    if(state.selectionRecorded)throw new Error('已解除此对话的现场目标；请明确选择后再操作，不会自动重新绑定。')
    if(state.identity&&!state.selectionRecorded)throw new Error('这段旧对话尚未选择当前现场，请从工程入口明确选择；历史归属没有改变。')
    const rows=(await this.directory.list()).filter(record=>record.workbench&&record.state==='registered')
    const cwd=agent.session.header?.cwd
    const scoped=rows.filter(record=>cwd&&record.workspace_path&&canonical(record.workspace_path)===canonical(cwd))
    const candidates=scoped.length?scoped:rows
    if(!candidates.length)throw new Error('目前没有可用的 Houdini 现场。请从目标 Houdini 打开工作台，或打开一份工程。')
    const selected=scoped.length===1?scoped[0].executor_id:await this.chooseTarget?.(agent.id,candidates,signal)
    const record=candidates.find(candidate=>candidate.executor_id===selected)
    if(!record)throw new Error('本轮没有选择 Houdini 现场，可以继续讨论；没有执行工程操作。')
    await this.selectTarget(agent,record.executor_id,record.registration_id,signal,record.hip_path!,true)
  }

  async resolve(exec:{agent?:Agent;signal?:AbortSignal},options:ResolveOptions={}):Promise<HoudiniBridge> {
    const signal=this.signal(exec.signal),agent=exec.agent
    if(!agent||agent.session.id!==agent.id)throw new Error('Houdini routing requires the exact current agent session')
    await this.checkpoint(agent.session)
    if(!this.state(agent.session).selectedTarget) {
      let selection=this.selections.get(agent.session)
      if(!selection){selection=this.selectFor(agent,signal);this.selections.set(agent.session,selection)}
      try {await selection}finally{if(this.selections.get(agent.session)===selection)this.selections.delete(agent.session)}
    }
    const target=this.state(agent.session).selectedTarget
    if(!target)throw new Error('请先选择要操作的 Houdini 现场。')
    const {record,bridge}=await this.verified(target,signal)
    if(options.write) {
      if(record.task_id&&record.task_id!==agent.id&&!this.idleOwner(record.task_id))
        throw new Error('这个工程的另一段对话仍在执行，请等待完成后再修改。')
      await bridge.claimWriter(agent.id,record.registration_id,record.hip_path!,signal)
      const after=this.state(agent.session).selectedTarget
      if(!after||after.executor_id!==target.executor_id||after.runtime_id!==target.runtime_id||after.scene_epoch!==target.scene_epoch)
        throw new Error('申请写入期间目标选择已变化，本次操作未发送。')
      await this.verified(target,signal)
    }
    return bridge
  }

  /** Read original request/job facts at their original runtime, never at the current default. */
  async resolveHistorical(exec:{agent?:Agent;signal?:AbortSignal},origin:{executorId?:string;runtimeId:string}):Promise<HoudiniBridge> {
    const signal=this.signal(exec.signal)
    if(!exec.agent||exec.agent.id!==exec.agent.session.id)throw new Error('Historical routing requires the exact current agent session')
    if(!ID.test(origin.runtimeId)||origin.executorId!==undefined&&!ID.test(origin.executorId))throw new Error('Invalid historical executor/runtime identity')
    let record:ExecutorRecord
    if(origin.executorId)record=await this.directory.find(origin.executorId)
    else {
      const rows=(await this.directory.list()).filter(row=>row.state==='registered'&&row.runtime_id===origin.runtimeId)
      if(rows.length!==1)throw new Error('原请求的 Houdini 运行端不可用或不唯一；结果保持未知，没有改用当前目标。')
      record=rows[0]
    }
    if(record.runtime_id!==origin.runtimeId)throw new Error('原请求所属的 Houdini 运行代际已结束；结果保持未知，没有改用当前目标。')
    const bridge=this.bridge(record,{runtimeId:origin.runtimeId})
    const health=await bridge.inspectExecutor(signal)
    if(health.runtimeId!==origin.runtimeId)throw new Error('原请求所属运行端已变化；结果保持未知。')
    return bridge
  }

  async sceneContextFor(session:Session,signal?:AbortSignal):Promise<unknown> {
    await this.checkpoint(session)
    const target=this.state(session).selectedTarget
    if(!target)throw new Error('No Houdini target selected; ambient scene inspection is disabled')
    const bounded=AbortSignal.any([this.signal(signal),AbortSignal.timeout(2000)])
    return (await this.verified(target,bounded)).bridge.sceneContext(bounded)
  }

  /** An explicit choice may replace any idle conversation's target, with no writer or ownership side effect. */
  async selectTarget(agent:Agent,id:string,registrationId:string,signal?:AbortSignal,expectedHip?:string,atStep=false,
    expected?:{runtimeId?:string;sceneEpoch?:string}):Promise<TargetSnapshot> {
    const bounded=this.signal(signal)
    return this.changeTarget(agent.session,bounded,()=>this.selectNow(agent,id,registrationId,bounded,expectedHip,atStep,expected))
  }
  private changeTarget<T>(session:Session,signal:AbortSignal,operation:()=>Promise<T>):Promise<T> {
    const previous=this.targetChanges.get(session)??Promise.resolve()
    const result=previous.catch(()=>{}).then(()=>{signal.throwIfAborted();return operation()})
    this.targetChanges.set(session,result)
    return result.finally(()=>{if(this.targetChanges.get(session)===result)this.targetChanges.delete(session)})
  }
  private async selectNow(agent:Agent,id:string,registrationId:string,bounded:AbortSignal,expectedHip?:string,atStep=false,
    expected?:{runtimeId?:string;sceneEpoch?:string}):Promise<TargetSnapshot> {
    if((agent.status!==undefined&&agent.status!=='idle'&&!atStep)||agent.id!==agent.session.id)
      throw new Error('Select a target only for the exact idle agent')
    const record=await this.directory.find(id)
    const target=targetSnapshot(record)
    let selected:TargetSnapshot|null=null
    try {selected=foldExecutorState(agent.session.snapshotEvents()).selectedTarget}catch{ /* Explicit choice can replace legacy invalid routing. */ }
    const unchanged=selected!==null&&sameTargetIntent(selected,target)
    if(record.registration_id!==registrationId&&!unchanged||expectedHip!==undefined&&canonical(record.hip_path??'')!==canonical(expectedHip)
      ||expected?.runtimeId!==undefined&&record.runtime_id!==expected.runtimeId
      ||expected?.sceneEpoch!==undefined&&record.scene_epoch!==expected.sceneEpoch)
      throw new Error('工程选择已过期，请重新选择目标。')
    await this.assertCanChange(agent,target,bounded)
    await this.verified(target,bounded)
    bounded.throwIfAborted()
    if(agent.status!==undefined&&agent.status!=='idle'&&!atStep)throw new Error('Agent started while selecting target')
    if(unchanged) {
      // Registration is a discovery generation, not another user intention.
      // Reconfirming the same scene must not retire active request/job facts.
      await this.checkpoint(agent.session)
      return selected!
    }
    await this.binding.select(agent.session,target,bounded)
    await this.checkpoint(agent.session)
    return target
  }
  async clear(agent:Agent,signal?:AbortSignal):Promise<void> {
    const bounded=this.signal(signal)
    return this.changeTarget(agent.session,bounded,async()=>{
      if(agent.id!==agent.session.id||agent.status!==undefined&&agent.status!=='idle')throw new Error('Clear a target only for the exact idle agent')
      await this.assertCanChange(agent,null,bounded)
      if(agent.status!==undefined&&agent.status!=='idle')throw new Error('Agent started while clearing target; selection was retained')
      await this.binding.select(agent.session,null,bounded)
      await this.checkpoint(agent.session)
    })
  }
  private async assertCanChange(agent:Agent,next:TargetSnapshot|null,signal:AbortSignal):Promise<void> {
    let old:TargetSnapshot|null
    try {old=foldExecutorState(agent.session.snapshotEvents()).selectedTarget}catch{return}
    if(!old||next&&sameTargetIntent(old,next))return
    const history=executionHistory(agent.session.snapshotEvents())
    if(!history.activeJobs.length&&!history.activeRequests.length&&!history.pendingCalls.length&&!history.unresolvedCalls.length)return
    let record:ExecutorRecord
    try {record=await this.directory.find(old.executor_id)}
    catch(error){if(error instanceof ExecutorUnavailableError)return;throw error}
    if(record.runtime_id!==old.runtime_id)return
    let health
    try {health=await this.bridge(record,{runtimeId:old.runtime_id}).inspectExecutor(signal)}
    catch(error){
      signal.throwIfAborted()
      // A crashed process may leave a registered discovery row. Only the OS's
      // explicit ESRCH proves retirement; timeouts and access errors do not.
      try {process.kill(record.pid,0)}
      catch(probe){if((probe as NodeJS.ErrnoException).code==='ESRCH')return}
      throw new Error('无法确认原目标是否仍有后台操作，暂未切换；请结束原操作后重试。',{cause:error})
    }
    if((health.activeJobs??0)>0||(health.activeRequests??0)>0)
      throw new Error('这段对话在原目标仍有请求或后台任务执行，完成后才能切换或解除目标。')
  }
}
