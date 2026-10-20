/** Host provenance, executor routing and result attachment for tool calls. */
import type { Context } from '@deepseek-ai/cordis'
import type { ExecResult, HoudiniBridge, OwnershipScope,HoudiniRuntimeFacts } from './bridge.js'
import { ExecutorBinding } from './executor-binding.js'
import { attachImages } from './image-output.js'
import { retainResult } from './result-details.js'
import {projectedExecutorBindingState} from './executor-identity-projection.js'
import {requestExecutionOrigin} from './execution-facts.js'
import {hostService} from './api-route.js'

export type HistoricalTarget={executorId?:string;runtimeId:string}
export type HoudiniConnection = HoudiniBridge | { resolve(exec:any,options?:{write?:boolean}):Promise<HoudiniBridge>;
  registry?:string;
  resolveRuntime?(exec:any):Promise<{runtime:HoudiniRuntimeFacts;houdiniVersion:string}>;
  resolveHistorical?(exec:any,target:HistoricalTarget):Promise<HoudiniBridge> }

export function workspaceOf(exec: any): string | null {
  const cwd = exec?.agent?.session?.header?.cwd
  return typeof cwd === 'string' && cwd ? cwd : null
}

export function ownershipScopeOf(exec: any): OwnershipScope {
  const sessionId = exec?.agent?.id
  const callId = exec?.callId
  const nonempty = (value: unknown): value is string => typeof value === 'string' && value.trim() !== ''
  if (!nonempty(sessionId) || !nonempty(callId)) {
    throw new Error('Houdini execution requires the current Host session identity (agent.id and callId); '
      + 'missing, blank or mistyped identity is rejected before any executor resolution or request')
  }
  return { sessionId, callId }
}

const normPath = (value: string) => value.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()

export class HoudiniToolRuntime {
  private readonly binding: ExecutorBinding
  private readonly workspaceNotes = new WeakMap<object, string>()

  constructor(private readonly ctx: Context, private readonly connection: HoudiniConnection) {
    this.binding = new ExecutorBinding(session=>projectedExecutorBindingState(ctx,session as any))
  }

  /** Resolve a selected scene; read access never claims an author or restores nodes. */
  async target(exec:any,access:'read'|'write'='read'):Promise<{bridge:HoudiniBridge;owner:OwnershipScope}> {
    const owner=ownershipScopeOf(exec)
    const bridge='resolve' in this.connection?await this.connection.resolve(exec,{write:access==='write'}):this.connection
    const session=exec?.agent?.session
    if(session?.snapshotEvents)await this.binding.ensure(session,bridge.targetExecutorId,exec.signal,false)
    else if(bridge.targetExecutorId)throw new Error('Bound Houdini operations require a durable agent session')
    if(access==='write'&&exec.agent)await this.ctx.get?.('houdiniRecovery')?.beforeWrite?.(exec.agent,exec.signal)
    return {bridge,owner}
  }

  /** Receipt/job lookup keeps its original runtime even after the default target changes. */
  async historicalTarget(exec:any,reference:{requestRef:string}):Promise<{bridge:HoudiniBridge;owner:OwnershipScope}> {
    const owner=ownershipScopeOf(exec)
    if('requestRef' in reference&&reference.requestRef==='index')return this.target(exec,'read')
    const target=requestExecutionOrigin(reference.requestRef)
    const bridge='resolve' in this.connection
      ?await (this.connection.resolveHistorical?.(exec,target)??Promise.reject(new Error('当前连接没有提供原运行实例查询，未向其他工程发送请求。')))
      :this.connection.forRuntime(target.runtimeId)
    return {bridge,owner}
  }

  /** Uses this result's observation; presentation never adds a scene query. */
  async result<T extends ExecResult>(value: T, exec: any, bridge: HoudiniBridge, workspaceNote = false): Promise<T> {
    let attached = await attachImages(value, exec, bridge, this.ctx)
    if (workspaceNote) attached = this.withWorkspaceNote(attached, exec)
    return this.retain(attached, exec)
  }

  async retain<T extends ExecResult>(value: T, exec: any): Promise<T> {
    return retainResult(value, workspaceOf(exec), () =>
      hostService(this.ctx,'sandboxPolicy')?.resolve({session:exec?.agent?.session})?.mode)
  }

  private withWorkspaceNote<T extends ExecResult>(value: T, exec: any): T {
    const cwd = workspaceOf(exec)
    const agent = exec?.agent
    const observation = value.execution !== null && typeof value.execution === 'object'
      && !Array.isArray(value.execution) ? value.execution : undefined
    const hip = observation?.hip_dir
    if (!cwd || !agent) return value
    if (observation?.hip_is_new === true || typeof hip !== 'string' || !hip) {
      if (observation && ('hip_dir' in observation || observation.hip_is_new === true)) this.workspaceNotes.delete(agent)
      return value
    }
    if (normPath(hip) === normPath(cwd)) {
      this.workspaceNotes.delete(agent)
      return value
    }
    const key = `${normPath(cwd)}|${normPath(hip)}`
    if (this.workspaceNotes.get(agent) === key) return value
    this.workspaceNotes.set(agent, key)
    const note = `workspace note: this session's workspace is "${cwd}"; this operation observed $HIP at "${hip}". `
      + 'Anchor all Houdini outputs at $HIP. Render/screenshot images arrive as native image attachments; '
      + 'A successful Save As performed by this conversation through scene_save_as follows the project directory at the next model step; selecting a scene or reading another save does not move the workspace. '
      + 'Do not write task outputs into the plugin repository.'
    return { ...value, advisory: value.advisory ? `${value.advisory}\n${note}` : note }
  }
}
