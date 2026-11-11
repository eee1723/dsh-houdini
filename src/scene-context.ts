/** One lightweight scene observation for each received user message. */
import type {HoudiniBridge} from './bridge.js'
import type {SessionEvent as Event} from './execution-history.js'
import {literalData as literal} from './prompt-data.js'
export type AgentView = { session: { snapshotEvents(): readonly Event[] } }
export type SceneBridge = Pick<HoudiniBridge,'sceneContext'> | {sceneContextFor(session:any,signal?:AbortSignal):Promise<unknown>}
type Observation={key:string;text:Promise<string>}
type Observations={pending:Map<string,Observation>;current?:Observation}
const messageKey=(message:any)=>String(message.id??JSON.stringify(message))
export class SceneContextProvider {
  // Only the inbox owns pending observations. Claiming moves one to the current
  // slot; older consumed messages already belong to DSH's durable history.
  private readonly observations = new WeakMap<object, Observations>()
  constructor(private readonly bridge: SceneBridge,
    private readonly observationOf:(agent:AgentView)=>{lastUserKey?:string;key?:string;text?:string}) {}

  receive(agent: AgentView, message: any): void {
    if (message?.source?.kind !== 'user')return
    const state=this.state(agent),key=messageKey(message)
    if(state.current?.key===key||state.pending.has(key))return
    state.pending.set(key,this.captureMessage(agent,key))
  }

  claim(agent: AgentView, message: any): void {
    if (message?.source?.kind !== 'user')return
    const state=this.state(agent),key=messageKey(message)
    const observation=state.pending.get(key)??(state.current?.key===key?state.current:this.recoveredMessage(agent,key))
    state.pending.delete(key)
    state.current=observation
  }

  discard(agent: object, message: any): void {
    if(message?.source?.kind==='user')this.observations.get(agent)?.pending.delete(messageKey(message))
  }

  async observe(agent: AgentView, signal?: AbortSignal): Promise<string> {
    // Inbox claims precede prompt assembly; the DSH projection supplies the
    // persisted message/observation association when this Host is reopened.
    const recorded=this.observationOf(agent),state=this.observations.get(agent)
    const current=state?.current??(recorded.lastUserKey?state?.pending.get(recorded.lastUserKey):undefined)
    const key=current?.key??recorded.lastUserKey
    if(!key)return ''
    signal?.throwIfAborted()
    // On host resume, reuse the original observation rather than capture the
    // user's later selection and bind it to an old message.
    if (!current) {
      return recorded.key===key?recorded.text??'':''
    }
    const text = await current.text
    signal?.throwIfAborted()
    return text
  }

  private state(agent:object):Observations {
    let state=this.observations.get(agent)
    if(!state){state={pending:new Map()};this.observations.set(agent,state)}
    return state
  }

  private captureMessage(agent:AgentView,key:string):Observation {
    const receivedAt = Date.now() / 1000
    return {key,text:this.capture(agent, key, receivedAt).catch(() =>
      'Houdini metadata observation unavailable for this user message. Query relevant state explicitly; no automatic retry.')}
  }

  private recoveredMessage(agent:AgentView,key:string):Observation {
    // DSH restores pending inbox entries without emitting a new insertion. A
    // later claim is not the original arrival: recapturing would bind the
    // user's current selection to an older request that never observed it.
    const recorded=this.observationOf(agent)
    const text=recorded.key===key&&typeof recorded.text==='string'?recorded.text:
      'Houdini metadata observation unavailable for this user message.\n'+literal(JSON.stringify({
        user_message_id:key,observation:{ok:false,status:'unavailable',
          reason:'The original arrival-time observation was not retained. Current selection was not sampled; inspect relevant state explicitly.'}}))
    return {key,text:Promise.resolve(text)}
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
      const result = reduced.observation.result
      for (const key of ['selection', 'selected_editor_items']) {
        while (data.length > 6000 && result?.[key]?.length) {
          result[key].pop()
          result[key + '_truncated'] = true
          data = JSON.stringify(reduced)
        }
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
