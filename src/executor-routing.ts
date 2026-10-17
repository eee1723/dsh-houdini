/** Shared Host routing candidate: no global 'current Houdini', no default target.
 * Registry records are hints; each selected endpoint must pass the Bridge header
 * guard and contract check. Selection never adopts node ownership or loads HIP.
 */
import fs from 'node:fs/promises'
import path from 'node:path'
import { HoudiniBridge } from './bridge.js'
import { ExecutorBinding, requireExecutorContinuityIdentity } from './executor-binding.js'
import {foldExecutorState} from './executor-identity-projection.js'

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
type Session = Parameters<ExecutorBinding['ensure']>[0] & {id:string}
const ID=/^[0-9a-f]{32}$/
const canonical = (p:string) => process.platform==='win32' ? path.normalize(p).toLowerCase() : path.normalize(p)

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
    if(!record||record.state!=='registered') throw new Error('Bound Houdini is disconnected or absent; no automatic target substitution')
    return record
  }
}

export class ExecutorRouter {
  private readonly lifetime=new AbortController()
  dispose():void {this.lifetime.abort(new Error('Shared Houdini Host service was unloaded'))}
  private signal(signal?:AbortSignal):AbortSignal {
    return signal?AbortSignal.any([signal,this.lifetime.signal]):this.lifetime.signal
  }
  constructor(readonly directory:ExecutorDirectory, private readonly timeoutMs:number,
    private readonly binding:ExecutorBinding,
    private readonly identityOf:(session:Session)=>string|undefined,
    private readonly persist?: (session:Session)=>Promise<boolean>,
    private readonly chooseRecovery?: (taskId:string,candidates:readonly ExecutorRecord[],signal:AbortSignal)=>Promise<string|undefined>) {}

  private async checkpoint(session:Session):Promise<void> {
    if(this.persist&&await this.persist(session)!==true)throw new Error('对话记录尚未可靠保存，本次操作没有发送到 Houdini。')
  }

  private async verified(id:string, taskId:string, signal?:AbortSignal, requireWriter=true):Promise<HoudiniBridge> {
    signal=this.signal(signal)
    signal?.throwIfAborted()
    const record=await this.directory.find(id)
    // Verification never claims or steals a writer lease. An unclaimed or
    // differently claimed target is only usable after an explicit selection
    // (selectInitial / recoveryTarget); idle-ness alone is not ownership and
    // is decided Bridge-side on that explicit claim.
    if(!record.hip_path) throw new Error('当前工程没有可核对的位置，请从对应 Houdini 打开工作区。')
    if(requireWriter&&record.task_id!==taskId) throw new Error(record.task_id===null
      ? '这个工程还没有写入预留；请明确选择/确认要继续的工程后再执行。'
      : '这个工程的写入预留属于另一段对话；请明确选择/确认要继续的工程，没有自动接管。')
    const bridge=new HoudiniBridge(record.bridge_url,this.timeoutMs,id,this.lifetime.signal)
    const health=await bridge.inspectExecutor(signal)
    if(health.runtimeId!==record.runtime_id||health.houVersion!==record.houdini_version) throw new Error('Executor generation changed; refresh the registry and reconcile pending operations')
    const after=await this.directory.find(id)
    if(JSON.stringify(record)!==JSON.stringify(after)) throw new Error('Executor registration changed during target verification')
    return bridge
  }

  /** Explicit writer claim, used only by selectInitial and recoveryTarget.
   * registrationId/expectedHip carry what the user confirmed (or the verified
   * recovery window shows); the Bridge accepts or rejects the takeover. Every
   * successful claim is followed by writer verification. */
  private async claim(id:string, taskId:string, registrationId:string, expectedHip:string, signal?:AbortSignal):Promise<HoudiniBridge> {
    const bridge=await this.verified(id,taskId,signal,false)
    signal?.throwIfAborted()
    await bridge.claimWriter(taskId,registrationId,expectedHip,signal)
    return this.verified(id,taskId,signal)
  }

  async resolve(exec:{agent?:{id:string;session:Session};signal?:AbortSignal}):Promise<HoudiniBridge> {
    const signal=this.signal(exec.signal)
    const agent=exec.agent
    if(!agent||agent.session.id!==agent.id) throw new Error('Houdini routing requires the exact current agent session')
    const target=this.identityOf(agent.session)
    if(!target) throw new Error('Choose a Houdini executor for this task before running live tools; no first/only/latest target is selected automatically')
    await this.checkpoint(agent.session)
    const bridge=await this.verified(target,agent.id,signal)
    await this.binding.ensure(agent.session,target,signal)
    return bridge
  }

  async recoveryTarget(agent:{id:string;session:Session},signal:AbortSignal,preferredTarget?:string):Promise<HoudiniBridge> {
    await this.checkpoint(agent.session)
    const state=foldExecutorState(agent.session.snapshotEvents())
    if(!state.identity)throw new Error('请先从要操作的 Houdini 打开工作区，或在本轮选择工程。')
    const scene=state.project?.sceneId
    const hip=state.project?.hipPath??null
    if(!preferredTarget||preferredTarget===state.identity) {
      try {return await this.verified(state.identity,agent.id,signal)}
      catch(error) {
        signal.throwIfAborted()
        if(!scene)throw error
        // A scene change can drop this task's writer lease on its own recorded
        // window (observe() resets it on a scene+HIP change). Reclaim only an
        // unclaimed or still-ours window that still shows the recorded project:
        // a window that moved to another file must not be adopted, and another
        // task's reservation is never stolen. Reclamation is claimed through the
        // same helper; the Bridge accepts or rejects it.
        try {
          const record=await this.directory.find(state.identity)
          const sameWindow=record.task_id===null||record.task_id===agent.id
          const sameScene=Boolean(record.scene_id&&scene&&record.scene_id===scene)
          const sameHip=hip===null||Boolean(record.hip_path&&canonical(record.hip_path)===canonical(hip))
          if(record.hip_path&&sameWindow&&sameScene&&sameHip)
            return await this.claim(state.identity,agent.id,record.registration_id,record.hip_path,signal)
        } catch {signal.throwIfAborted()}
      }
    }
    if(!scene)throw new Error('原对话缺少可验证的工程身份，请明确选择工程；没有自动认领内容。')
    // scene_id alone is copyable with the HIP file. With a recorded path a
    // window must show that path to qualify; without one there is no auto-match,
    // only the explicit user choice below over scene-matched windows.
    const candidates=(await this.directory.list()).filter(record=>record.workbench&&record.state==='registered'
      &&record.executor_id!==state.identity&&record.scene_id===scene
      &&(hip===null||Boolean(record.hip_path&&canonical(record.hip_path)===canonical(hip))))
    const verified:ExecutorRecord[]=[]
    for(const record of candidates) {
      try {
        const candidate=await this.inspectRecovery(agent.session,record.executor_id,signal)
        if(candidate)verified.push(record)
      } catch {signal.throwIfAborted()}
    }
    if(!verified.length)throw new Error('原 Houdini 暂不可用，尚未找到可验证的原工程。请打开原工程后继续。')
    const selected=preferredTarget??(verified.length===1&&hip?verified[0].executor_id:await this.chooseRecovery?.(agent.id,verified,signal))
    if(!selected||!verified.some(record=>record.executor_id===selected))throw new Error('存在多份原工程，请在对话中选择要继续的窗口；本轮没有换绑。')
    if(!await this.inspectRecovery(agent.session,selected,signal))throw new Error('选择期间工程已变化，请重新选择。')
    // Explicit claim only after the chosen window re-verifies; windows that
    // failed inspectRecovery are never claimed.
    const record=verified.find(row=>row.executor_id===selected)!
    return this.claim(selected,agent.id,record.registration_id,record.hip_path!,signal)
  }

  async inspectRecovery(session:Pick<Session,'id'|'snapshotEvents'>,target:string,signal:AbortSignal):Promise<HoudiniBridge|undefined> {
    const state=foldExecutorState(session.snapshotEvents())
    const scene=state.project?.sceneId
    const hip=state.project?.hipPath
    if(!state.identity||!scene)return
    const candidate=await this.verified(target,session.id,signal,false)
    const value=await candidate.recover('assess',{session_id:session.id,previous_executor:state.identity,
      source_executors:state.executors,expected:{scene_id:scene}},signal)
    if(value.executor_id!==target||value.status!=='ready'||value.scene_id!==scene)return
    // A copy shares scene identity with its original; with a recorded HIP path
    // a window must also show that path to qualify. Without one nothing can be
    // auto-matched (recoveryTarget never auto-picks) and the user's explicit
    // window choice is the remaining authorization.
    if(hip&&(typeof value.hip_path!=='string'||canonical(value.hip_path)!==canonical(hip)))return
    return candidate
  }

  async sceneContextFor(session:Session,signal?:AbortSignal):Promise<unknown> {
    const target=this.identityOf(session)
    if(!target) throw new Error('No Houdini target selected; ambient scene inspection is disabled')
    await this.checkpoint(session)
    const deadline=AbortSignal.timeout(2000)
    const bounded=signal?AbortSignal.any([signal,deadline]):deadline
    return (await this.verified(target,session.id,bounded)).sceneContext(bounded)
  }

  /** Host/UI only. Initial bind, not a recovery/rebind or model-callable tool. */
  async selectInitial(agent:{id:string;status:string;session:Session}, id:string, registrationId:string, signal?:AbortSignal, expectedHip?:string,atStep=false,reselect=false):Promise<void> {
    signal=this.signal(signal)
    if((agent.status!=='idle'&&!atStep)||agent.id!==agent.session.id) throw new Error('Select a target only for the exact idle agent')
    if(reselect) {
      const state=foldExecutorState(agent.session.snapshotEvents())
      if(state.hasOperations||state.recovery)throw new Error('已有现场操作的对话不能直接换绑。')
    } else requireExecutorContinuityIdentity(this.identityOf(agent.session),id)
    const record=await this.directory.find(id)
    if(expectedHip!==undefined&&record.hip_path!==expectedHip) throw new Error('HIP changed after the selection was displayed; refresh and confirm again')
    if(record.registration_id!==registrationId) throw new Error('Target selection is stale; refresh before confirming')
    // No Host-side idle/ownership pre-reject: an explicit claim below is the
    // only takeover path and the Bridge accepts or rejects it. Verification
    // itself never claims.
    signal?.throwIfAborted()
    if(agent.status!=='idle'&&!atStep) throw new Error('Agent started while selecting target; no new binding written')
    if(record.task_id!==agent.id) await this.claim(id,agent.id,registrationId,record.hip_path!,signal)
    else await this.verified(id,agent.id,signal)
    // The writer reservation is already held; always finish the identity
    // write so a race cannot leave the agent claimed but unbound.
    if(reselect)await this.binding.reselectUnexecuted(agent.session,id,signal)
    else await this.binding.ensure(agent.session,id,signal)
    await this.checkpoint(agent.session)
  }
}
