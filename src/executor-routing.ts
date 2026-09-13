/** Shared Host routing candidate: no global 'current Houdini', no default target.
 * Registry records are hints; each selected endpoint must pass the Bridge header
 * guard and contract check. Selection never adopts node ownership or loads HIP.
 */
import fs from 'node:fs/promises'
import path from 'node:path'
import { HoudiniBridge } from './bridge.js'
import { ExecutorBindingBarrier, recordedExecutorIdentity, requireExecutorContinuity } from './execution-state.js'

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
}
type Session = Parameters<ExecutorBindingBarrier['ensure']>[0] & {id:string}
const ID=/^[0-9a-f]{32}$/
const canonical = (p:string) => process.platform==='win32' ? path.normalize(p).toLowerCase() : path.normalize(p)

export class ExecutorDirectory {
  constructor(private readonly root:string, private readonly installation:string) {
    if (!path.isAbsolute(root)||!path.isAbsolute(installation)) throw new Error('Executor registry and installation paths must be absolute')
  }
  requireRoot(root:string):void {
    if(!path.isAbsolute(root)||canonical(root)!==canonical(this.root)) throw new Error('Shared Houdini registry configuration differs from the Host service; no fallback to a different registry')
  }
  async list(): Promise<ExecutorRecord[]> {
    let files:string[]
    const directory=path.join(this.root,'endpoints')
    try { files=await fs.readdir(directory) }
    catch(error) { if((error as NodeJS.ErrnoException).code==='ENOENT') return [];throw error }
    files=files.filter(f=>f.endsWith('.json')).sort()
    if(files.length>256) throw new Error('Executor discovery budget exceeded')
    const expectedInstall=canonical(await fs.realpath(this.installation))
    const expectedDirectory=canonical(await fs.realpath(directory))
    const records:ExecutorRecord[]=[]
    for(const file of files) {
      if(!ID.test(file.slice(0,-5))) throw new Error('Invalid executor record filename')
      const filename=path.join(directory,file), stat=await fs.lstat(filename)
      if(!stat.isFile()||stat.isSymbolicLink()||stat.size>16384||canonical(path.dirname(await fs.realpath(filename)))!==expectedDirectory) throw new Error('Invalid executor record path/size')
      const text=await fs.readFile(filename,'utf8')
      if(Buffer.byteLength(text)>16384) throw new Error('Executor record exceeds read budget')
      const r=JSON.parse(text)
      if(!r||r.schema!==1||r.executor_id!==file.slice(0,-5)||!ID.test(r.registration_id)||!ID.test(r.runtime_id)
        ||typeof r.installation!=='string'||!path.isAbsolute(r.installation)
        ||typeof r.bridge_url!=='string'||!/^http:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(r.bridge_url)
        ||!Number.isInteger(r.pid)||r.pid<=0||!['registered','disconnected'].includes(r.state)
        ||typeof r.houdini_version!=='string'||!/^\d+\.\d+\.\d+$/.test(r.houdini_version)
        ||!(r.task_id===null||typeof r.task_id==='string'&&r.task_id.length>0)
        ||!(r.hip_path===null||typeof r.hip_path==='string'&&path.isAbsolute(r.hip_path))) throw new Error('Invalid executor record')
      const port=Number(new URL(r.bridge_url).port)
      if(port<1024||port>65535) throw new Error('Invalid registered Bridge port')
      // A missing foreign installation is not a reason to load or execute it.
      if(canonical(r.installation)!==expectedInstall) continue
      records.push(r)
    }
    return records
  }
  async find(id:string):Promise<ExecutorRecord> {
    if(!ID.test(id)) throw new Error('Invalid executor identity')
    const record=(await this.list()).find(r=>r.executor_id===id)
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
    private readonly binding:ExecutorBindingBarrier) {}

  private async verified(id:string, taskId:string, signal?:AbortSignal, requireWriter=true):Promise<HoudiniBridge> {
    signal=this.signal(signal)
    signal?.throwIfAborted()
    const record=await this.directory.find(id)
    // The Python registration currently grants writer leases. Until the live
    // claim endpoint/UI exists, refuse unclaimed or differently claimed targets.
    if((requireWriter&&record.task_id!==taskId)||!record.hip_path) throw new Error('Executor has no matching task/HIP writer reservation; select/claim it from the owning Houdini first')
    const bridge=new HoudiniBridge(record.bridge_url,this.timeoutMs,id,this.lifetime.signal)
    const health=await bridge.inspectExecutor(signal)
    if(health.runtimeId!==record.runtime_id||health.houVersion!==record.houdini_version) throw new Error('Executor generation changed; refresh the registry and reconcile pending operations')
    const after=await this.directory.find(id)
    if(JSON.stringify(record)!==JSON.stringify(after)) throw new Error('Executor registration changed during target verification')
    return bridge
  }

  async resolve(exec:{agent?:{id:string;session:Session};signal?:AbortSignal}):Promise<HoudiniBridge> {
    const signal=this.signal(exec.signal)
    const agent=exec.agent
    if(!agent||agent.session.id!==agent.id) throw new Error('Houdini routing requires the exact current agent session')
    const target=recordedExecutorIdentity(agent.session.snapshotEvents())
    if(!target) throw new Error('Choose a Houdini executor for this task before running live tools; no first/only/latest target is selected automatically')
    const bridge=await this.verified(target,agent.id,signal)
    await this.binding.ensure(agent.session,target,signal)
    return bridge
  }

  async sceneContextFor(session:Session,signal?:AbortSignal):Promise<unknown> {
    const target=recordedExecutorIdentity(session.snapshotEvents())
    if(!target) throw new Error('No Houdini target selected; ambient scene inspection is disabled')
    const deadline=AbortSignal.timeout(2000)
    const bounded=signal?AbortSignal.any([signal,deadline]):deadline
    return (await this.verified(target,session.id,bounded)).sceneContext(bounded)
  }

  /** Host/UI only. Initial bind, not a recovery/rebind or model-callable tool. */
  async selectInitial(agent:{id:string;status:string;session:Session}, id:string, registrationId:string, signal?:AbortSignal, expectedHip?:string):Promise<void> {
    signal=this.signal(signal)
    if(agent.status!=='idle'||agent.id!==agent.session.id) throw new Error('Select a target only for the exact idle agent')
    requireExecutorContinuity(agent.session.snapshotEvents(),id)
    const record=await this.directory.find(id)
    if(expectedHip!==undefined&&record.hip_path!==expectedHip) throw new Error('HIP changed after the selection was displayed; refresh and confirm again')
    if(record.registration_id!==registrationId) throw new Error('Target selection is stale; refresh before confirming')
    if(record.task_id!==null&&record.task_id!==agent.id) throw new Error('Executor already has another task writer reservation')
    const bridge=await this.verified(id,agent.id,signal,false)
    signal?.throwIfAborted()
    if(agent.status!=='idle') throw new Error('Agent started while selecting target; no new binding written')
    if(record.task_id===null) {
      await bridge.claimWriter(agent.id,registrationId,record.hip_path!,signal)
      await this.verified(id,agent.id,signal)
      if(agent.status!=='idle') throw new Error('Agent started during reservation; binding not written, reservation retained for inspection')
    }
    await this.binding.ensure(agent.session,id,signal)
  }
}
