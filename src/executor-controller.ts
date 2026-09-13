/** Authenticated DSH Remote surface, not a model tool or a separate web server. */
import type { Context } from '@deepseek-ai/cordis'
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol'
import type {} from '@deepseek-ai/dsh-agent'
import type { ExecutorRouter } from './executor-routing.js'
import {recordedExecutorIdentity} from './execution-state.js'

export class ExecutorController extends TypertRemoteService {
  constructor(ctx:Context,private readonly router:ExecutorRouter) { super(ctx,'houdiniTargets') }

  /** In-process consumer API, deliberately not exposed as a Remote method. */
  getRouter(registry:string):ExecutorRouter {
    this.router.directory.requireRoot(registry)
    return this.router
  }

  @Remote
  async list() {
    return {candidates:(await this.router.directory.list()).map(r=>{
      const agent=r.task_id?this.ctx.agents.get(r.task_id as Parameters<typeof this.ctx.agents.get>[0]):undefined
      return {...r,connection_status:'unverified',binding_status:agent&&recordedExecutorIdentity(agent.session.snapshotEvents())===r.executor_id?'bound':'not_confirmed'}
    }),
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
