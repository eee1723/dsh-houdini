/** Host provenance, executor routing and result attachment for tool calls. */
import type { Context } from '@deepseek-ai/cordis'
import type { ExecResult, HoudiniBridge, OwnershipScope } from './bridge.js'
import { ExecutorBinding } from './executor-binding.js'
import { attachImages } from './image-output.js'
import { retainResult } from './result-details.js'

export type HoudiniConnection = HoudiniBridge | { resolve(exec: any): Promise<HoudiniBridge> }

export function workspaceOf(exec: any): string | null {
  const cwd = exec?.agent?.session?.header?.cwd
  return typeof cwd === 'string' && cwd ? cwd : null
}

function ownershipScopeOf(exec: any): OwnershipScope {
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
    this.binding = new ExecutorBinding()
  }

  /** Validate trusted provenance before resolving or contacting an executor. */
  async target(exec: any, bind = true): Promise<{ bridge: HoudiniBridge; owner: OwnershipScope }> {
    const owner = ownershipScopeOf(exec)
    const bridge = 'resolve' in this.connection ? await this.connection.resolve(exec) : this.connection
    if (bind) {
      const session = exec?.agent?.session
      if (session?.snapshotEvents) await this.binding.ensure(session, bridge.targetExecutorId, exec.signal, false)
      else if (bridge.targetExecutorId) throw new Error('Bound Houdini operations require a durable agent session')
    }
    return { bridge, owner }
  }

  /** Uses this result's observation; presentation never adds a scene query. */
  async result<T extends ExecResult>(value: T, exec: any, bridge: HoudiniBridge, workspaceNote = false): Promise<T> {
    let attached = await attachImages(value, exec, bridge, this.ctx)
    if (workspaceNote) attached = this.withWorkspaceNote(attached, exec)
    return retainResult(attached, workspaceOf(exec))
  }

  async retain<T extends ExecResult>(value: T, exec: any): Promise<T> {
    return retainResult(value, workspaceOf(exec))
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
      + 'use DSH-Houdini > Open Workspace to select the current HIP workspace for other file tools. '
      + 'Do not write task outputs into the plugin repository.'
    return { ...value, advisory: value.advisory ? `${value.advisory}\n${note}` : note }
  }
}
