/** One lightweight scene observation for each received user message. */
import type {HoudiniBridge} from './bridge.js'
import type {SessionEvent as Event} from './execution-history.js'
import {literalData as literal} from './prompt-data.js'
export type AgentView = { session: { snapshotEvents(): readonly Event[] } }
export type SceneBridge = Pick<HoudiniBridge,'sceneContext'> | {sceneContextFor(session:any,signal?:AbortSignal):Promise<unknown>}
type Observation={key:string;capturedAt:number;full:Promise<string>}
type Observations={pending:Map<string,Observation>;current?:Observation}
const messageKey=(message:any)=>String(message.id??JSON.stringify(message))
/** Compact historical summary budget; the full observation is persisted once. */
const COMPACT_BUDGET=1400
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
      if(recorded.key!==key||typeof recorded.text!=='string')return ''
      // The full observation already exists in persisted history; a resumed
      // assembly only needs the same historical summary later steps receive.
      return this.compact(key,this.capturedAtOf(recorded.text)??Date.now()/1000,recorded.text)
    }
    const full = await current.full
    signal?.throwIfAborted()
    // DSH materializes this contribution as a runtime-context snapshot. Once a
    // snapshot for exactly this user message is persisted, the full observation
    // is already in durable history; later assemblies (auto goal rounds, tool
    // follow-ups, inbox refreshes) only need an explicitly historical summary.
    // Keying on the persisted message identity also avoids an alternating
    // full/compact cycle when a later snapshot stores the compact text itself.
    if(recorded.key===key)return this.compact(key,current.capturedAt,full)
    return full
  }

  private state(agent:object):Observations {
    let state=this.observations.get(agent)
    if(!state){state={pending:new Map()};this.observations.set(agent,state)}
    return state
  }

  private captureMessage(agent:AgentView,key:string):Observation {
    const receivedAt = Date.now() / 1000
    const full=this.capture(agent, key, receivedAt).catch(() =>
      'Houdini metadata observation unavailable for this user message. Query relevant state explicitly; no automatic retry.')
    return {key,capturedAt:receivedAt,full}
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
    const capturedAt=this.capturedAtOf(text)??Date.now()/1000
    return {key,capturedAt,full:Promise.resolve(text)}
  }

  /** Recover the Host's request time, separate from Houdini's observed_at. */
  private capturedAtOf(text:string):number|undefined {
    try {
      const value=JSON.parse(text.slice(text.indexOf('\n')+1))
      const captured=Number(value?.capture_requested_at)
      return Number.isFinite(captured)&&captured>0?captured:undefined
    } catch { return undefined }
  }

  /** Bound the persisted observation to its decision-relevant historical facts. */
  private compact(key:string,capturedAt:number,full:string):string {
    // The summary must be byte-stable for one observation: DSH materializes
    // context snapshots over time, so a live-computed field (for example an
    // elapsed age) would make every snapshot differ and defeat deduplication.
    const head='Houdini historical scene observation. This only applies to its recorded user message. '
      +'When available, observed_at records when Houdini sampled the scene on its main thread. '
      +'Query scene_info/node_info/read_parms when current state matters.\n'
    let summary:Record<string,unknown>
    try {
      const value=JSON.parse(full.slice(full.indexOf('\n')+1))
      if(value?.historical===true&&value.user_message_id===key) {
        const retained=head+literal(JSON.stringify(value))
        if(retained.length<=COMPACT_BUDGET)return retained
      }
      const observation:any=value?.observation, result:any=observation?.result
      const paths=(rows:any):any=>Array.isArray(rows)
        ? {...(rows.length>12?{count:rows.length}:{}),
            paths:rows.slice(0,12).map((row:any)=>typeof row==='string'?row:({
              ...(row?.path?{path:row.path}:{}),...(row?.type?{type:row.type}:{}),
              ...(row?.parent?{parent:row.parent}:{}),
              ...(row?.name?{name:row.name}:{}),
              ...(row?.needs_cook!==undefined?{needs_cook:row.needs_cook}:{}),
              ...(Array.isArray(row?.errors)&&row.errors.length?{errors:row.errors.slice(0,1)}:{}),
              ...(Array.isArray(row?.warnings)&&row.warnings.length?{warnings:row.warnings.slice(0,1)}:{})}))}
        : null
      summary={user_message_id:value?.user_message_id??key,capture_requested_at:value?.capture_requested_at??capturedAt,
        historical:true,
        observation:{ok:observation?.ok??null,...(observation?.status?{status:observation.status}:{}),
          ...(observation?.reason?{reason:observation.reason}:{}),
          ...(result?{result:{
            ...(result.runtime_id?{runtime_id:result.runtime_id}:{}),
            ...(typeof result.observed_at==='number'?{observed_at:result.observed_at}:{}),
            ...(result.version?{version:result.version}:{}),
            ...(result.hip_path?{hip_path:result.hip_path}:{}),
            ...(result.hip_is_new!==undefined?{hip_is_new:result.hip_is_new}:{}),
            ...(result.hip_dir?{hip_dir:result.hip_dir}:{}),
            ...(result.has_named_path!==undefined?{has_named_path:result.has_named_path}:{}),
            ...(result.has_unsaved_changes!==undefined?{has_unsaved_changes:result.has_unsaved_changes}:{}),
            ...(result.frame!==undefined?{frame:result.frame}:{}),
            ...(result.update_mode?{update_mode:result.update_mode}:{}),
            ...(Array.isArray(result.selection)?{selection:paths(result.selection)}:{}),
            ...(Array.isArray(result.selected_editor_items)?{selected_editor_items:paths(result.selected_editor_items)}:{}),
            ...(typeof result.selection_count==='number'?{selection_count:result.selection_count}:{})
          }}:{})}}
    } catch {
      summary={user_message_id:key,capture_requested_at:capturedAt,historical:true,
        observation:{ok:false,status:'unavailable',reason:'The original full observation is not available; inspect relevant state explicitly.'}}
    }
    let text=head+literal(JSON.stringify(summary))
    if(text.length>COMPACT_BUDGET) {
      // Keep the historical marker and identity fields, drop optional arrays.
      const observation:any=(summary as any)?.observation,hint=observation?.result?{result:{
        observed_at:observation.result.observed_at,
        hip_path:observation.result.hip_path??null,has_unsaved_changes:observation.result.has_unsaved_changes??null,
        selection_truncated:true}}:{}
      summary={...summary,observation:{...observation,...hint}}
      text=head+literal(JSON.stringify(summary))
    }
    if(text.length>COMPACT_BUDGET)text=head+literal(JSON.stringify({user_message_id:key,capture_requested_at:capturedAt,
      historical:true,observation:{status:'details_omitted'}}))
    return text
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
    const text = 'Houdini metadata observation. A single sample was requested when this user message arrived. '
      + 'If this step includes several user messages, this applies only to the last one. Resolve the other messages’ scene references separately. '
      + 'When available, observed_at records when Houdini sampled the scene on its main thread. Geometry and selection can change before and after sampling. '
      + 'Query explicitly when current state is needed. Unavailable does not mean an empty scene.\n' + literal(data)
    return text
  }
}
