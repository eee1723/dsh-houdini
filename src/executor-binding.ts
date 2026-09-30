/** Task target routing and its durable session binding. */
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import type {Context} from '@deepseek-ai/cordis'
type Event = {type: string; seq?: number; time?: number; data?: any}
const NAMES = new Set(['houdini_exec','houdini_query','houdini_job_submit','houdini_job_status','houdini_job_cancel'])
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

/** Pre-step messages use DSH's normal acceptance boundary, before model tool calls. */
export function installExecutorBinding(ctx:Context,current?:string):void {
  ctx.on('agent/pre-step',async({agent,signal},next)=>{
    const decision=await next()
    signal.throwIfAborted()
    if(decision.kind==='reject') return decision
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

/** Uses the public DSH projection in shared Host and the event log in single-target mode.
 * Both routes require a durable flush before dispatch and never maintain a second binding file.
 */
export class ExecutorBindingBarrier {
  private readonly flushed = new WeakMap<BindingSession, Promise<void>>()
  constructor(private readonly flush: (session: BindingSession) => Promise<boolean>,
    private readonly stateOf?: (session: BindingSession) => {identity:string|undefined;bindingRecorded:boolean}) {}

  private read(session:BindingSession):{identity:string|undefined;bindingRecorded:boolean} {
    if(this.stateOf)return this.stateOf(session)
    const events=session.snapshotEvents()
    return {identity:recordedExecutorIdentity(events),bindingRecorded:bindingRecords(events).length>0}
  }

  async ensure(session: BindingSession, current?: string, signal?: AbortSignal, allowAppend=true): Promise<void> {
    signal?.throwIfAborted()
    const state=this.read(session)
    requireExecutorContinuityIdentity(state.identity,current)
    if (!current) return // explicitly unbound single-executor route
    if (!/^[0-9a-f]{32}$/.test(current)) throw new Error('Invalid target executor identity')
    let pending = this.flushed.get(session)
    if (!pending) {
      if (!state.bindingRecorded) {
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
    const durable=this.read(session)
    requireExecutorContinuityIdentity(durable.identity,current)
    if(!durable.bindingRecorded)throw new Error('Executor binding is absent after the durability barrier; no live request sent')
  }
}
/** Historical target continuity, not authority to adopt/rebind a new executor.
 * Only correlate original live calls with canonical tool results. A detail read,
 * source excerpt, receipt lookup or replay must not invent a target assignment.
 */
export function requireExecutorContinuity(events: readonly Event[], current?: string): void {
  requireExecutorContinuityIdentity(recordedExecutorIdentity(events),current)
}

/** Same fail-closed continuity rule for callers with a current Session projection. */
export function requireExecutorContinuityIdentity(identity:string|undefined,current?:string):void {
  if (identity && identity !== current) throw new Error('Houdini task requires recovery: recorded executor differs from the current target. No live request sent. If the original Houdini process is gone, cross-process recovery is not implemented: preserve the saved/crash HIP and inspect retained results; do not start a new task or select another target to bypass ownership. Restore the original binding only when that exact process is still available.')
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
    if (identity === undefined) continue // an unbound history never gains identity from PID/path
    if (typeof identity !== 'string' || !/^[0-9a-f]{32}$/.test(identity)) {
      throw new Error('Invalid recorded Houdini executor identity; no live request sent. Inspect the original session evidence.')
    }
    identities.add(identity)
  }
  if (identities.size > 1) {
    throw new Error('Houdini task requires recovery: history contains more than one recorded executor identity. No live request sent. Cross-process recovery is not implemented: read retained results, preserve the saved/crash HIP and reconcile the project before any future recovery flow; do not start a new task to bypass this check or infer ownership from the HIP path.')
  }
  return identities.values().next().value
}
