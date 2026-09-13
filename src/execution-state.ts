/** A bounded projection of durable tool facts, rebuilt from public events.
 * No second mutable scene database and no cached permissions/pass certificates.
 */
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import type {Context} from '@deepseek-ai/cordis'
import type {Session,SessionSeq} from '@deepseek-ai/dsh-session'
type Event = {type: string; seq?: number; time?: number; data?: any}
const TARGET_SECTION = 'dsh-houdini:executor-binding'

function bindingRecords(events: readonly Event[]): string[] {
  const ids: string[] = []
  for (const e of events) {
    if (e.type !== 'user/message' || e.data?.source?.kind !== 'plugin' || e.data.source.plugin !== 'dsh-houdini') continue
    for (const section of e.data.source.sections || []) {
      if (section.name !== TARGET_SECTION) continue
      let value: any
      try { value = JSON.parse(section.text.slice(section.text.indexOf('\n') + 1)) }
      catch { throw new Error('Malformed persisted executor binding; no live request sent') }
      if (value?.schema !== 1 || value?.kind !== 'executor_binding' || !/^[0-9a-f]{32}$/.test(value?.executor_id || '')) {
        throw new Error('Invalid persisted executor binding; no live request sent')
      }
      ids.push(value.executor_id)
    }
  }
  return ids
}

type BindingSession = {
  snapshotEvents(): readonly Event[]
  append(type: 'user/message', data: ReturnType<typeof createUserMessage>, options: {surfaceOp:'append'}): unknown
  surface?: {nodes:readonly number[]}
}

function bindingMessage(current:string) {
  const section={name:TARGET_SECTION,text:'Houdini task target binding (routing data, not node ownership or permission).\n'
    +JSON.stringify({schema:1,kind:'executor_binding',executor_id:current})}
  return createUserMessage({content:[{type:'text',text:section.text}],
    source:{kind:'plugin',plugin:'dsh-houdini',form:'snapshot',sections:[section]}})
}

function surfaceEvents(session:BindingSession):readonly Event[] {
  const events=session.snapshotEvents()
  if(!session.surface) return events
  const bySeq=new Map(events.map(e=>[e.seq,e]))
  return session.surface.nodes.map(seq=>bySeq.get(seq)!).filter(Boolean)
}

function pendingTools(events:readonly Event[]):Set<string> {
  const pending=new Set<string>()
  for(const e of events) {
    if(e.type==='assistant/message') for(const c of e.data?.message?.content||[]) if(c.type==='tool-call') pending.add(c.id)
    if(e.type==='tool/result') pending.delete(e.data?.message?.source?.callId)
  }
  return pending
}

/** Compact only a complete text-only exchange broken by our misplaced binding.
 * Use DSH's normal summary replacement, never bypass its protected tool rewrites.
 * Original events remain immutable. No result is fabricated and no tool runs.
 */
export function repairExecutorBindingOrder(session:Session):number {
  const events=surfaceEvents(session),pending=new Set<string>()
  const plans:Event[][]=[]
  let batch:Event[]=[],broken=false
  let unsafe=false
  for(let i=0;i<events.length;i++) {
    const e=events[i]
    if(e.type==='assistant/message') {
      if(pending.size) unsafe=true
      for(const c of e.data?.message?.content||[]) if(c.type==='tool-call') pending.add(c.id)
      batch=pending.size?[e]:[]
      broken=false
    } else if(e.type==='tool/result') {
      if(!pending.delete(e.data?.message?.source?.callId)) unsafe=true
      if(batch.length) batch.push(e)
    } else if(pending.size && e.type==='user/message') {
      batch.push(e)
      const sections=e.data?.source?.sections, blocks=e.data?.content
      const next=events[i+1], block=next?.data?.message?.content?.[0]
      const own=e.data?.source?.kind==='plugin'&&e.data.source.plugin==='dsh-houdini'
        &&Array.isArray(sections)&&sections.length===1&&sections[0].name===TARGET_SECTION
        &&Array.isArray(blocks)&&blocks.length===1&&blocks[0].type==='text'&&blocks[0].text===sections[0].text
      if(own&&bindingRecords([e]).length===1&&next?.type==='tool/result'
        &&pending.has(next.data?.message?.source?.callId)&&block?.type==='tool-result'
        &&next.data.message.content.length===1&&block.toolCallId===next.data.message.source.callId) {
        broken=true
      } else unsafe=true
    } else if(pending.size) {
      unsafe=true
    }
    if(batch.length&&!pending.size) {
      if(broken) plans.push(batch)
      batch=[];broken=false
    }
  }
  if(!plans.length&&!broken) return 0
  if(unsafe||pending.size) throw new Error('Cannot repair binding order: missing or unrelated tool-message evidence. Original history preserved; no model or Houdini request sent.')
  const summaries=plans.map(batch=>{
    const assistant=batch[0].data.message
    const calls=assistant.content.filter((c:any)=>c.type==='tool-call')
    const results=batch.filter(e=>e.type==='tool/result').map(e=>{
      const content=e.data.message.content
      if(content.length!==1||content[0].type!=='tool-result'||content[0].content.some((c:any)=>c.type!=='text')) throw new Error('Binding-order recovery requires text-only results; original multimodal history retained')
      return {call_id:content[0].toolCallId,is_error:content[0].isError===true,text:content[0].content.map((c:any)=>c.text)}
    })
    const text='Recovered completed tool exchange after a plugin binding-order bug. Original result text is retained below; these are historical results, not new tool calls. This repair executed no tools. Original events remain in the session log.\n'
      +JSON.stringify({assistant_text:assistant.content.filter((c:any)=>c.type==='text').map((c:any)=>c.text),calls,results})
    if(text.length>200000) throw new Error('Binding-order recovery exceeds bounded summary size; original history preserved')
    return {batch,text}
  })
  for(const {batch,text} of summaries) {
    session.append('user/message',createUserMessage({content:[{type:'text',text}],
      source:{kind:'plugin',plugin:'dsh-houdini',form:'snapshot',sections:[{name:'dsh-houdini:binding-order-repair',text}]}}),{
      surfaceOp:{op:'replace',startSeq:batch[0].seq! as SessionSeq,endSeq:batch.at(-1)!.seq! as SessionSeq},
      sourceEventSeqs:batch.map(e=>e.seq! as SessionSeq),
    })
  }
  return plans.length
}

/** Pre-step messages use DSH's normal acceptance boundary, before model tool calls. */
export function installExecutorBinding(ctx:Context,current?:string):void {
  const repairFlushed=new WeakSet<Session>()
  ctx.on('agent/pre-step',async({agent,signal},next)=>{
    const decision=await next()
    signal.throwIfAborted()
    if(decision.kind==='reject') return decision
    const changed=repairExecutorBindingOrder(agent.session)
    const hasRepair=agent.session.snapshotEvents().some(e=>e.type==='user/message'&&e.data.source.kind==='plugin'
      &&e.data.source.plugin==='dsh-houdini'&&(e.data.source as any).sections?.some((s:any)=>s.name==='dsh-houdini:binding-order-repair'))
    if(changed||hasRepair&&!repairFlushed.has(agent.session)) {
      if(await ctx.sessions.flush(agent.session)!==true) throw new Error('Binding-order repair is not durable; no model request sent')
      repairFlushed.add(agent.session)
    }
    if(!current) return decision
    const events=agent.session.snapshotEvents()
    requireExecutorContinuity(events,current)
    const proposed=[...events,...decision.messages.map(data=>({type:'user/message',data}))]
    requireExecutorContinuity(proposed,current)
    if(bindingRecords(proposed).length) return decision
    if(!/^[0-9a-f]{32}$/.test(current)) throw new Error('Invalid executor identity')
    return {...decision,messages:[...decision.messages,bindingMessage(current)]}
  })
}

/** Uses the public DSH log and durability barrier; never maintains a second binding file. */
export class ExecutorBindingBarrier {
  private readonly flushed = new WeakMap<BindingSession, Promise<void>>()
  constructor(private readonly flush: (session: BindingSession) => Promise<boolean>) {}

  async ensure(session: BindingSession, current?: string, signal?: AbortSignal, allowAppend=true): Promise<void> {
    signal?.throwIfAborted()
    const events = session.snapshotEvents()
    requireExecutorContinuity(events, current)
    if (!current) return // explicitly unbound legacy client, not a multi-executor route
    if (!/^[0-9a-f]{32}$/.test(current)) throw new Error('Invalid target executor identity')
    let pending = this.flushed.get(session)
    if (!pending) {
      if (!bindingRecords(events).length) {
        if(!allowAppend||pendingTools(surfaceEvents(session)).size) throw new Error('Executor binding must be accepted before model tool calls; no message inserted and no live request sent')
        session.append('user/message',bindingMessage(current),{surfaceOp:'append'})
      }
      // Schedule after publishing the shared promise so simultaneous calls share one flush.
      pending = Promise.resolve().then(async () => {
        if (await this.flush(session) !== true) throw new Error('Executor binding has no durable session backend; no live request sent')
      })
      this.flushed.set(session,pending)
      pending.catch(() => { if (this.flushed.get(session) === pending) this.flushed.delete(session) })
    }
    await pending
    signal?.throwIfAborted()
    requireExecutorContinuity(session.snapshotEvents(),current)
  }
}
const NAMES = new Set(['houdini_exec', 'houdini_query', 'houdini_job_submit', 'houdini_job_status', 'houdini_job_cancel'])
const CHECKS = new Set(['build_module', 'verify_network', 'test_controls', 'geo_check_interfaces', 'render_view', 'render_frame',
  'cop_layer_stats', 'cop_compare_layers', 'test_cop_controls'])
const RESOLVED_REQUESTS = new Set(['done', 'not_executed', 'job_submitted'])

/** Historical target continuity, not authority to adopt/rebind a new executor.
 * Only correlate original live calls with canonical tool results. A detail read,
 * source excerpt, receipt lookup or replay must not invent a target assignment.
 */
export function requireExecutorContinuity(events: readonly Event[], current?: string): void {
  const identity = recordedExecutorIdentity(events)
  if (identity && identity !== current) throw new Error('Houdini task requires recovery: recorded executor differs from the current target. No live request sent. Restore the original binding before any live operation.')
}

export function recordedExecutorIdentity(events: readonly Event[]): string | undefined {
  const calls = new Map<string, any>()
  const seen = new Set<string>()
  const identities = new Set<string>(bindingRecords(events))
  for (const event of events) {
    const d = event.data
    if (event.type === 'tool/call' && NAMES.has(d?.name)) calls.set(d.callId, d)
    if (event.type !== 'tool/result') continue
    const id = d?.message?.source?.callId
    const call = calls.get(id)
    if (!call || seen.has(id)) continue
    seen.add(id)
    if (call.name === 'houdini_query' && (call.args?.result_ref || call.args?.source_ref || call.args?.request_ref)) continue
    const value = d.meta?.canonical
    const identity = value?.execution?.executor_id ?? value?.requestReceipt?.executor_id
    if (identity === undefined) continue // old histories remain legacy, never infer identity from PID/path
    if (typeof identity !== 'string' || !/^[0-9a-f]{32}$/.test(identity)) {
      throw new Error('Invalid recorded Houdini executor identity; no live request sent. Inspect the original session evidence.')
    }
    identities.add(identity)
  }
  if (identities.size > 1) {
    throw new Error('Houdini task requires recovery: recorded executor differs from the current target. No live request sent. Read retained results and reconcile the saved project before explicitly restoring the binding; do not start a new task to bypass this check or infer ownership from the HIP path.')
  }
  return identities.values().next().value
}

export function projectExecutionState(events: readonly Event[]): Record<string, unknown> | null {
  const calls = new Map<string, any>()
  const seen = new Set<string>()
  const rows: any[] = []
  const uncertainRows: Array<{seq:number;ref?:string;callId:string}> = []
  const receipts = new Map<string,string>()
  const resolvedCalls = new Set<string>()
  const jobs = new Map<string, string>()
  for (const event of events) {
    const d = event.data
    if (event.type === 'tool/call' && NAMES.has(d?.name)) calls.set(d.callId, d)
    if (event.type !== 'tool/result') continue
    const id = d?.message?.source?.callId
    const call = calls.get(id)
    if (!call || seen.has(id)) continue
    seen.add(id)
    const value = d.meta?.canonical
    const receipt = value?.requestReceipt
    if (typeof receipt?.request_ref === 'string' && !RESOLVED_REQUESTS.has(receipts.get(receipt.request_ref) || '')) {
      // Receipt snapshots arrive out of order. Once history contains a terminal
      // outcome, an older poll or later Bridge retention expiry cannot erase it.
      receipts.set(receipt.request_ref,receipt.status)
    }
    if (typeof receipt?.owner_call === 'string' && RESOLVED_REQUESTS.has(receipt.status)) resolvedCalls.add(receipt.owner_call)
    const job = value?.jobId ?? receipt?.jobId ?? d.meta?.jobId
    if (typeof job === 'string') {
      const status=value?.status ?? d.meta?.status ?? 'queued_or_unknown'
      if (!['done','failed','cancelled'].includes(jobs.get(job) || '') || ['done','failed','cancelled'].includes(status)) jobs.set(job,status)
    }
    const e = value?.execution
    if (e && typeof e.runtime_id === 'string' && Number.isFinite(e.sequence) && Number.isFinite(e.observed_at)) {
      rows.push({eventSeq:event.seq ?? 0, callId:id, tool:call.name, value, e})
    } else if (call.name === 'houdini_exec' || (call.name === 'houdini_job_submit' && !job)
        || (['houdini_job_status','houdini_job_cancel'].includes(call.name) && ['failed','cancelled'].includes(value?.status ?? d.meta?.status))) {
      // Includes transport failures and historical runtimes without this schema.
      uncertainRows.push({seq:event.seq ?? 0,ref:receipt?.request_ref,callId:id})
    }
  }
  const unresolvedCalls = uncertainRows.filter(row=>!resolvedCalls.has(row.callId) && (!row.ref || !RESOLVED_REQUESTS.has(receipts.get(row.ref) || '')))
  const uncertain = unresolvedCalls.map(row=>row.seq)
  const activeRequests=[...receipts].filter(([,status])=>!RESOLVED_REQUESTS.has(status))
  const pendingCalls = [...calls].filter(([id, call]) => !seen.has(id) && !resolvedCalls.has(id) && ['houdini_exec','houdini_job_submit'].includes(call.name))
  const activeJobs = [...jobs].filter(([,status]) => !['done','failed','cancelled'].includes(status))
  if (!rows.length) return uncertain.length || activeJobs.length || pendingCalls.length || activeRequests.length
    ? {status:'execution_state_unknown', pending_calls:pendingCalls.length, active_jobs:activeJobs,
       unresolved_requests:activeRequests, unresolved_calls:unresolvedCalls.map(row=>row.callId),
       reason:'No ordered Bridge observation; inspect current outputs and in-flight work before retrying mutations.'} : null
  // Foreground results identify an observed runtime. A late poll for an old job
  // must not resurrect a previous runtime's node identities.
  const foreground = rows.filter(r => ['houdini_exec','houdini_query'].includes(r.tool))
  const anchor = (foreground.length ? foreground : rows).reduce((a,b) =>
    a.e.observed_at > b.e.observed_at || (a.e.observed_at === b.e.observed_at && a.e.sequence > b.e.sequence) ? a : b)
  const runtimeRows = rows.filter(r => r.e.runtime_id === anchor.e.runtime_id)
  const all = runtimeRows.filter(r => r.e.hip_path === anchor.e.hip_path)
  const unique = new Map<number, any>()
  for (const row of all) if (!unique.has(row.e.sequence)) unique.set(row.e.sequence, row)
  const ordered = [...unique.values()].sort((a,b) => a.e.sequence-b.e.sequence)
  const current = ordered.slice(-128)
  const nodes = new Map<number, any>()
  const checks = new Map<string, any>()
  const failures: any[] = []
  const inFlight = activeJobs.length > 0 || pendingCalls.length > 0 || activeRequests.length > 0
  for (const row of current) {
    const {value, e, eventSeq, callId} = row
    const impact = e.impact || {}
    const changed = new Set((impact.nodes || []).map((n:any)=>n.identity))
    const mayHaveEdited = impact.attempted === true && value.transaction?.status !== 'no_scene_change'
    if (mayHaveEdited) for (const check of checks.values()) {
      if (impact.global || impact.truncated || impact.unavailable || check.identity === null || changed.has(check.identity)
          || (check.dependency_identities || []).some((id:number) => changed.has(id))
          || check.verb.startsWith('render_')) {
        check.validity = 'stale_after_recorded_change'
        check.invalidated_by = callId
      }
    }
    for (const n of value.transaction?.nodes || []) if (Number.isFinite(n.identity)) {
      nodes.delete(n.identity)
      nodes.set(n.identity,{identity:n.identity,path:n.path ?? n.prior_path,
        last_observed_exists:n.exists,source_call:callId,sequence:e.sequence})
    }
    const byIndex = new Map((e.outputs || []).map((o:any)=>[o.ledger_index,o]))
    for (const item of value.evidence || []) {
      if (!CHECKS.has(item?.verb)) continue
      const binding:any = byIndex.get(item.ledgerIndex)
      const identity = binding?.identity ?? null
      const dependencyIdentities = (binding?.dependencies || []).map((d:any) => d.identity).filter(Number.isFinite)
      const checkStatus = item.ok === false || item.restored === false ? 'fail'
        : item.warning_free === false || item.healthy === false ? 'warning'
        : item.status ?? (item.ok === true ? 'observed_pass' : 'unverified')
      const rolledBack = value.transaction?.status === 'rolled_back' || value.transaction?.status === 'recovery_unverified'
      const supersededInCall = (impact.last_edit_ledger_index ?? 0) > item.ledgerIndex
      const unknownOrder = (value.rawUsage?.coveredMutations?.length || value.rawUsage?.suspectedMutations?.length) > 0
      const validity = rolledBack ? 'not_current_after_failed_transaction'
        : unknownOrder ? 'unverified_change_order_in_call'
        : supersededInCall ? 'stale_after_later_edit_in_same_call'
        : 'historical_observation_only'
      const portScope = item.verb === 'cop_compare_layers' ? JSON.stringify(binding?.dependencies || [])
        : item.verb === 'cop_layer_stats' ? item.output : item.verb === 'test_cop_controls' ? item.output_port : ''
      const key = `${item.verb}:${identity ?? binding?.path ?? item.output ?? item.node ?? item.ledgerIndex}:${portScope}`
      checks.delete(key)
      checks.set(key,{verb:item.verb,identity,output:binding?.path ?? item.output ?? item.node,
        ...(dependencyIdentities.length ? {dependency_identities:dependencyIdentities} : {}),
        status:checkStatus,validity,scope:item.scope ?? null,frame:item.frame ?? e.frame,
        source_call:callId,event_seq:eventSeq,sequence:e.sequence,
        ...(value.details?.stored ? {result_ref:value.details.sha256,pointer:`/evidence/${value.evidence.indexOf(item)}`} : {})})
    }
    if (value.ok === false) failures.push({call_id:callId,sequence:e.sequence,
      transaction:value.transaction?.status ?? 'unknown',reason:String(value.error ?? 'execution failed').slice(0,240)})
  }
  for (const check of checks.values()) if (inFlight || uncertain.some(seq => seq > check.event_seq)) {
    check.validity = 'unverified_after_unobserved_or_inflight_execution'
  }
  return {status:'recorded_execution_facts',runtime_id:anchor.e.runtime_id,
    hip_path:anchor.e.hip_path ?? null,
    last_sequence:current.at(-1)?.e.sequence,last_observed_at:current.at(-1)?.e.observed_at,
    frame:current.at(-1)?.e.frame,
    nodes:[...nodes.values()].slice(-12),checks:[...checks.values()].slice(-8),
    recent_failures:failures.slice(-2),active_jobs:activeJobs,pending_calls:pendingCalls.length,unresolved_requests:activeRequests,
    unresolved_calls:unresolvedCalls.map(row=>row.callId),
    coverage:{execution_records:current.length,older_records_omitted:ordered.length-current.length,
      other_runtime_records_excluded:rows.length-runtimeRows.length,
      other_hip_records_excluded:runtimeRows.length-all.length,nodes_omitted:Math.max(0,nodes.size-12),
      checks_omitted:Math.max(0,checks.size-8)},
    boundary:'Historical tool observations only, not current live state or permission. Native dependency hints exclude unobserved GUI edits, last-cook omissions and external/dynamic dependencies. Non-stale does not mean currently valid; recheck relevant state before relying on it.'}
}

/** Only facts requiring attention beyond an ordinary returned tool result.
 * No clocks, counters, healthy-node inventory or repeated error traceback.
 */
export function projectExecutionNotice(events: readonly Event[]): Record<string, unknown> | null {
  const state = projectExecutionState(events) as any
  if (!state) return null
  const checks = (state.checks || []).filter((check: any) =>
    check.validity.startsWith('stale_') || check.validity.startsWith('unverified_'))
    .map((check: any) => ({verb:check.verb,identity:check.identity,output:check.output,
      validity:check.validity,source_call:check.source_call,invalidated_by:check.invalidated_by}))
  // Compare observed foreground identities in execution order, never GUI selection.
  const calls = new Map<string, string>()
  const observations: any[] = []
  const seen = new Set<string>()
  for (const event of events) {
    const d = event.data
    if (event.type === 'tool/call') calls.set(d?.callId, d?.name)
    const id = d?.message?.source?.callId
    const e = d?.meta?.canonical?.execution
    if (event.type !== 'tool/result' || !e || seen.has(id)
        || !['houdini_exec','houdini_query'].includes(calls.get(id) || '')
        || !Number.isFinite(e.observed_at) || !Number.isFinite(e.sequence)) continue
    seen.add(id)
    observations.push({id, ...e})
  }
  observations.sort((a,b) => a.observed_at-b.observed_at || a.sequence-b.sequence)
  let changed: any = null
  for (let i=1;i<observations.length;i++) {
    const before=observations[i-1], after=observations[i]
    if (before.runtime_id !== after.runtime_id || before.hip_path !== after.hip_path) {
      changed={source_call:after.id,previous_runtime:before.runtime_id,runtime_id:after.runtime_id,
        previous_hip:before.hip_path ?? null,hip_path:after.hip_path ?? null}
    }
  }
  const requests = state.unresolved_requests || [], unresolved = state.unresolved_calls || []
  if (!checks.length && !requests.length && !unresolved.length && !state.pending_calls && !changed) return null
  return {status:'execution_attention',runtime_id:state.runtime_id ?? null,
    observed_scene_change:changed,checks,unresolved_requests:requests,unresolved_calls:unresolved,
    pending_calls:state.pending_calls || 0,
    boundary:'Historical tool evidence, not live state or permission. Resolve uncertain requests by their original reference before repeating mutations. Recheck affected outputs; passive GUI activity is not observed or a new user target.'}
}
