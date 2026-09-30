/** One lightweight scene observation for each received user message. */
import type {HoudiniBridge} from './bridge.js'
import type {SessionEvent as Event} from './execution-history.js'
import {sectionData,lastEvent as last,literalData as literal} from './prompt-data.js'
import {isHoudiniSource} from './dsh-adapter.js'
const NAME='dsh-houdini:scene-context'
export type AgentView = { session: { snapshotEvents(): readonly Event[] } }
type Section = {name:string;text:string}
export type SceneBridge = Pick<HoudiniBridge,'sceneContext'> | {sceneContextFor(session:any,signal?:AbortSignal):Promise<unknown>}
export class SceneContextProvider {
  private readonly cache = new WeakMap<object, Map<string, Promise<string>>>()
  private readonly claimed = new WeakMap<object, any>()
  constructor(private readonly bridge: SceneBridge) {}

  receive(agent: AgentView, message: any): void {
    if (message?.source?.kind === 'user') void this.forMessage(agent, message)
  }

  claim(agent: object, message: any): void {
    if (message?.source?.kind === 'user') this.claimed.set(agent, message)
  }

  async observe(agent: AgentView, signal?: AbortSignal): Promise<string> {
    const events = agent.session.snapshotEvents()
    // Inbox claims precede prompt assembly; user/message is logged AFTER assembly.
    const recorded = last(events, e => e.type === 'user/message' && e.data?.source?.kind === 'user')
    const message = this.claimed.get(agent) ?? recorded?.data
    if (!message) return ''
    signal?.throwIfAborted()
    // On host resume, reuse the original observation rather than capture the
    // user's later selection and bind it to an old message.
    const key = String(message.id ?? recorded?.seq ?? JSON.stringify(message))
    if (!this.claimed.has(agent) && !this.cache.get(agent)?.has(key)) {
      const sections = events.flatMap(e => e.type === 'user/message'
        && (isHoudiniSource(e.data?.source) || e.data?.source?.kind==='runtime-context')
        ? e.data.source.sections || [] : [])
      return sections.filter((s: Section) => s.name === NAME && sectionData(s)?.user_message_id === key)
        .at(-1)?.text || ''
    }
    const text = await this.forMessage(agent, message, recorded?.seq)
    signal?.throwIfAborted()
    return text
  }

  private forMessage(agent: AgentView, message: any, seq?: number): Promise<string> {
    let messages = this.cache.get(agent)
    if (!messages) { messages = new Map(); this.cache.set(agent, messages) }
    const key = String(message.id ?? seq ?? JSON.stringify(message))
    const cached = messages.get(key)
    if (cached) return cached
    const receivedAt = Date.now() / 1000
    const promise = this.capture(agent, key, receivedAt).catch(() =>
      'Houdini metadata observation unavailable for this user message. Query relevant state explicitly; no automatic retry.')
    messages.set(key, promise)
    return promise
  }

  private async capture(agent: AgentView, messageKey: string, receivedAt: number): Promise<string> {
    let observation: unknown
    try { observation = await ('sceneContextFor' in this.bridge ? this.bridge.sceneContextFor(agent.session) : this.bridge.sceneContext()) }
    catch (error) {
      observation = { ok: false, status: 'unavailable', reason: String(error).slice(0, 300) }
    }
    // Do not substitute the newest display selection for a prior explicit user target.
    const binding = { user_message_id: messageKey, capture_requested_at: receivedAt }
    let data = JSON.stringify({ ...binding, observation })
    if (data.length > 6000) {
      const row: any = observation
      // Preserve scene identity and selected paths, dropping optional detail first.
      data = JSON.stringify({ ...binding, truncated: true,
        observation: { ok: row?.ok, status: row?.status, reason: row?.reason,
          result: row?.result && { ...row.result, selection: (row.result.selection || []).slice(0, 16)
            .map((n: any) => ({ path: n.path, type: n.type })), panes: [] } } })
      const reduced = JSON.parse(data)
      while (data.length > 6000 && reduced.observation.result?.selection?.length) {
        reduced.observation.result.selection.pop()
        reduced.observation.result.selection_truncated = true
        data = JSON.stringify(reduced)
      }
      if (data.length > 6000) data = JSON.stringify({ ...binding,
        observation: { ok: false, status: 'unavailable', reason: 'metadata exceeds observation budget; query the relevant target explicitly' } })
    }
    if (literal(data).length > 6000) data = JSON.stringify({ ...binding, observation:{ok:false,status:'unavailable',reason:'escaped metadata exceeds observation budget; query the relevant target explicitly'} })
    const text = 'Houdini metadata observation. '
      + 'Captured once for this user message; never refreshed by tools or elapsed time. '
      + 'Geometry/selection may change afterward; query explicitly when current state is needed. '
      + 'Unavailable does not mean an empty scene.\n' + literal(data)
    return text
  }
}
