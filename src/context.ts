import type { Context } from '@deepseek-ai/cordis'
import { createUserMessage, createSystemMessage } from '@deepseek-ai/dsh-llm'
import { projectExecutionState, projectExecutionNotice } from './execution-state.js'
import { projectDeliveryAudit } from './delivery-audit.js'
import {productNotice,productCoverage} from './product-definition.js'
import {visualCapability} from './image-output.js'
import {executionHistory,type SessionEvent as Event} from './execution-history.js'
import {SceneContextProvider,type AgentView,type SceneBridge} from './scene-context.js'
import {sectionData,lastEvent as last,literalData as literal,type PromptSectionData as Section} from './prompt-data.js'

const NAME = 'dsh-houdini:scene-context'
const STATE_NAME = 'dsh-houdini:execution-state'
const TASK_NAME = 'dsh-houdini:task-sources'
const RECOVERY_NAME = 'dsh-houdini:context-recovery'
const VISION_NAME = 'dsh-houdini:visual-capability'
const ATTENTION_COMPACTION = 'dsh-houdini:attention-compaction'
export const MAX_EXECUTION_NOTICES = 4
/** Public single-node surface replacements, never a span across tool/user data.
 * Empty system messages are DSH's native non-emitting tombstones. Current facts
 * are appended normally at this step, not moved into an earlier history slot.
 */
export function compactExecutionNotices(session: any, incomingNotice: boolean,incomingNames:readonly string[]=[STATE_NAME]): number {
  if (!session.surface || typeof session.append !== 'function') return 0
  const events: Event[] = session.snapshotEvents()
  const visible = new Set<number>(session.surface.nodes)
  const boundary = last(events,e=>e.type === 'step/start')
  if (!Number.isInteger(boundary?.data?.turn) || !Number.isInteger(boundary?.data?.step)) return 0
  const pending = new Set<string>()
  for (const e of events) {
    if (!visible.has(e.seq!)) continue
    if (e.type === 'assistant/message') for (const b of e.data?.message?.content || []) if (b.type === 'tool-call') pending.add(b.id)
    if (e.type === 'tool/result') {
      const id = e.data?.message?.source?.callId
      if (!pending.delete(id)) return 0 // incomplete/ambiguous history is not ours to repair
    }
  }
  if (pending.size) return 0
  const notices = events.filter(e=> {
    const m=e.data, sections=m?.source?.sections, blocks=m?.content
    return visible.has(e.seq!) && e.seq !== session.surface.nodes[0] && e.type === 'user/message'
      && m.source?.kind === 'plugin' && m.source.plugin === 'dsh-houdini' && m.source.form === 'snapshot'
      && sections?.length === 1 && [STATE_NAME].includes(sections[0].name)
      && blocks?.length === 1 && blocks[0].type === 'text' && blocks[0].text === sections[0].text
      && ['execution_attention','no_execution_attention','execution_state_exceeds_budget'].includes(sectionData(sections[0])?.status)
  })
  if (notices.length + (incomingNotice?new Set(incomingNames).size:0) <= MAX_EXECUTION_NOTICES) return 0
  const newest=new Map<string,Event>()
  for(const event of notices) newest.set(event.data.source.sections[0].name,event)
  const obsolete=notices.filter(event=>{
    const name=event.data.source.sections[0].name
    return (incomingNotice&&incomingNames.includes(name))||newest.get(name)!==event
  })
  for (const e of obsolete) session.append('system/message', {
    turn:boundary!.data.turn,step:boundary!.data.step,message:createSystemMessage('',ATTENTION_COMPACTION),
  }, {surfaceOp:{op:'replace',startSeq:e.seq,endSeq:e.seq},sourceEventSeqs:[e.seq]})
  return obsolete.length
}

export function installSceneContext(ctx: Context, bridge: SceneBridge): void {
  const provider = new SceneContextProvider(bridge)
  // Acknowledgements are a cache, not authority: after resume the latest owned
  // tombstone is rediscovered from immutable history and flushed again.
  const confirmedCompaction = new WeakMap<object,number>()
  const prepared = new WeakMap<object, Section[]>()
  const visionCache = new WeakMap<object,{key:string;llm:unknown;attachments:unknown;checkedAt:number;value:Awaited<ReturnType<typeof visualCapability>>}>()
  ctx.on('agent/inbox/inserted', ({ agent, message }) => {
    // Capture on receipt, before queued messages are claimed for a model step.
    provider.receive(agent as unknown as AgentView, message)
  })
  ctx.on('agent/inbox/claimed', ({ agent, message }) => provider.claim(agent, message))
  ctx.systemPrompt.context({ name: NAME, order: 150, text: '' })
  ctx.systemPrompt.context({ name: STATE_NAME, order: 151, text: '' })
  ctx.systemPrompt.context({ name: TASK_NAME, order: 152, text: '' })
  ctx.systemPrompt.context({ name: VISION_NAME, order: 153, text: '' })
  // Use public logged messages per changed section. Keeping them in the Host's
  // combined runtime snapshot would resend scene + policies on every update.
  ctx.on('agent/pre-step', async ({agent, signal}, next) => {
    const decision = await next()
    signal.throwIfAborted()
    if (decision.kind === 'reject') return decision
    const view = agent as unknown as AgentView
    const events = view.session.snapshotEvents()
    const surface = view.session.surface && new Set(view.session.surface.nodes)
    const retained = new Map<string,string>()
    for (const e of events) {
      if (e.type !== 'user/message' || e.data?.source?.plugin !== 'dsh-houdini'
          || (surface && !surface.has(e.seq!))) continue
      for (const section of e.data.source.sections || []) retained.set(section.name, section.text)
    }
    const additions = (prepared.get(agent) || []).filter(s => retained.get(s.name) !== s.text)
      .map(section => createUserMessage({content:[{type:'text',text:section.text}],
        source:{kind:'plugin',plugin:'dsh-houdini',form:'snapshot',sections:[section]}}))
    // The normal message-acceptance boundary owns the new snapshot. Only prune
    // once a non-rejected next step can accept it and persistence is available.
    const sessions = ctx.get?.('sessions') as {flush(session:unknown):Promise<boolean>} | undefined
    if (sessions && typeof sessions.flush === 'function' && (prepared.get(agent) || []).some(s=>[STATE_NAME].includes(s.name))) {
      const incoming=additions.flatMap(m=>m.source.kind==='plugin'?m.source.sections??[]:[])
        .map(s=>s.name).filter(name=>[STATE_NAME].includes(name))
      compactExecutionNotices(view.session,incoming.length>0,incoming)
    }
    const latestCompaction = last(view.session.snapshotEvents(),e=>e.type === 'system/message'
      && e.data?.message?.source?.plugin === ATTENTION_COMPACTION)?.seq
    if (latestCompaction !== undefined && confirmedCompaction.get(view.session) !== latestCompaction) {
      if (!sessions || typeof sessions.flush !== 'function' || await sessions.flush(view.session) !== true)
        throw new Error('Execution-notice compaction was not durable; no model request sent')
      signal.throwIfAborted()
      confirmedCompaction.set(view.session,latestCompaction)
    }
    return {...decision,messages:[...decision.messages,...additions]}
  })
  // Context providers are synchronous. The public assembly waterfall is async;
  // runtime-context suppressors are enforced by DSH after this waterfall.
  ctx.on('system-prompt/assemble', async (assembly, context, next) => {
    const result = await next()
    const agent = (context as typeof context & { agent?: AgentView }).agent
    if (agent) prepared.delete(agent)
    const wantsScene = result.contexts.some(c => c.name === NAME && !c.text)
    const wantsState = result.contexts.some(c => c.name === STATE_NAME && !c.text)
    const wantsTask = result.contexts.some(c => c.name === TASK_NAME && !c.text)
    const wantsVision = result.contexts.some(c => c.name === VISION_NAME && !c.text)
    if (!wantsScene && !wantsState && !wantsTask && !wantsVision) return result
    if (!agent || !context.scope || !result.tools.some(t => t.name === 'houdini_query')) return result
    const sections: Section[] = []
    const events = agent.session.snapshotEvents()
    const history=executionHistory(events)
    const execution=wantsState?projectExecutionState(events,history):null
    if(wantsVision) {
      result.contexts=result.contexts.filter(c=>c.name!==VISION_NAME)
      // Metadata service is optional for minimal/offline hosts. Production
      // agents receive the first route result before their first model step.
      if(typeof ctx.get==='function') {
        const runtimeAgent=agent as any
        const llm=ctx.get('llm'),attachments=ctx.get('attachments')
        // Before the first request, requestHeader is absent (or still the
        // previous model). The fully assembled prompt owns the selected route.
        const variables=result.variables
        const config=variables?.provider && variables?.model
          ? {provider:variables.provider,model:variables.model}
          : runtimeAgent.session.requestHeader?.()?.config
        const key=JSON.stringify([config?.provider??runtimeAgent.options?.provider,config?.model??runtimeAgent.options?.model])
        let cached=visionCache.get(agent)
        if(!cached||cached.key!==key||cached.llm!==llm||cached.attachments!==attachments
            ||cached.value.status==='unavailable'||Date.now()-cached.checkedAt>60000) {
          cached={key,llm,attachments,checkedAt:Date.now(),value:await visualCapability({agent,route:config,signal:context.signal},ctx)}
          visionCache.set(agent,cached)
        }
        sections.push({name:VISION_NAME,text:'Houdini visual capability (metadata only, not semantic evidence).\n'+literal(JSON.stringify(cached.value))})
      }
    }
    // A tool-result pruner also increments replaceGeneration. It must not
    // trigger a full recovery on every shortened tool result.
    const replaced = last(events, e => e.type !== 'tool/result'
      && !(e.type === 'system/message' && e.data?.message?.source?.plugin === ATTENTION_COMPACTION)
      && typeof e.surfaceOp === 'object' && e.surfaceOp.op === 'replace')
    const generation = replaced?.seq === undefined ? 0 : replaced.seq + 1
    const surface = agent.session.surface && new Set(agent.session.surface.nodes)
    const recovered = last(events, e => e.type === 'user/message' && e.data?.source?.plugin === 'dsh-houdini'
      && (!surface || surface.has(e.seq!)) && e.data.source.sections?.some((s:Section) => s.name === RECOVERY_NAME))
    const recovery = sectionData(recovered?.data.source.sections.find((s:Section) => s.name === RECOVERY_NAME))
    const needsRecovery = generation > 0 && recovery?.surface_generation !== generation
    if (wantsScene) {
      const text = await provider.observe(agent, context.signal)
      result.contexts = result.contexts.filter(c => c.name !== NAME)
      if (text) sections.push({ name: NAME, text })
    }
    if (wantsState) {
      const state = projectExecutionNotice(events,history,execution)
      const audit = projectDeliveryAudit(events,{fullChecks:true},history) as any
      const product = productNotice(events,productCoverage(events,{history,audit}))
      const deliveryAttention = audit && (audit.unresolved_checks?.length || audit.execution_failures?.length
        || audit.coverage_limits?.length || audit.unresolved_requests?.length
        || audit.unresolved_calls?.length || audit.active_jobs?.length
        || audit.pending_calls?.length || audit.delivery?.last_save)
      const deliverySummary = deliveryAttention ? {
        status:audit.status,current_hip:audit.current_hip,delivery:audit.delivery,
        unresolved_checks:audit.unresolved_checks,unresolved_checks_omitted:audit.unresolved_checks_omitted,
        coverage_limits:audit.coverage_limits,coverage_limits_omitted:audit.coverage_limits_omitted,
        execution_failures:audit.execution_failures,execution_failures_omitted:audit.execution_failures_omitted,
        unresolved_requests:audit.unresolved_requests,pending_calls:audit.pending_calls,
        unresolved_calls:audit.unresolved_calls,active_jobs:audit.active_jobs,
        boundary:audit.boundary,
      } : null
      result.contexts = result.contexts.filter(c => c.name !== STATE_NAME)
      const prior = last(events, e => e.type === 'user/message' && e.data?.source?.plugin === 'dsh-houdini'
        && e.data.source.sections?.some((s:Section) => s.name === STATE_NAME))
      if (state || deliverySummary || product || prior) {
        let data = literal(JSON.stringify(state
          ? {...state,...(deliverySummary ? {delivery_audit:deliverySummary} : {}),...(product?{product}: {})}
          : deliverySummary || product
            ? {status:'execution_attention',checks:[],...(deliverySummary?{delivery_audit:deliverySummary}:{}),...(product?{product}:{}),
              boundary:'Historical delivery facts require review before claiming a final output.'}
            : {status:'no_execution_attention',
              boundary:'Previously reported execution attention is no longer present in recorded tool evidence. This is not scene validation or task completion.'}))
        if (data.length > 7000) data = JSON.stringify({status:'execution_state_exceeds_budget',
          product:product?{status:product.status,revision:product.revision,unresolved:product.unresolved,
            pending:product.pending.map(r=>({id:r.id,kind:r.kind,status:r.status})),pending_omitted:product.pending_omitted,
            unreconciled_source_count:product.unreconciled_source_count,read:product.read}:null,
          runtime_id:state?.runtime_id,pending_calls:state?.pending_calls ?? 0,
          unresolved_request_count:(state?.unresolved_requests as unknown[] | undefined)?.length ?? 0,
          unresolved_call_count:(state?.unresolved_calls as unknown[] | undefined)?.length ?? 0,
          affected_check_count:(state?.checks as unknown[] | undefined)?.length ?? 0,
          delivery_audit_counts:deliverySummary ? {unresolved_checks:audit.unresolved_checks.length,
            coverage_limits:audit.coverage_limits.length,
            execution_failures:audit.execution_failures.length,unresolved_requests:audit.unresolved_requests.length,
            pending_calls:audit.pending_calls.length,last_save:audit.delivery.last_save?.path??null} : null,
          read:'Use houdini_query(request_ref="index") for retained request references; read the original tool results and recheck the affected outputs.',
          boundary:'Attention details exceed the context budget, NOT resolved or passed. Original results remain in history. No blanket pass or permission is implied.'})
        sections.push({name:STATE_NAME,text:'Houdini execution attention (historical data, not instructions or permission). This replaces earlier execution-attention notices only.\n'+data})
      }
    }
    if (wantsTask) {
      const sources = needsRecovery ? provider.taskContext(agent) : null
      result.contexts = result.contexts.filter(c => c.name !== TASK_NAME)
      if (sources) {
        let data = literal(JSON.stringify(sources))
        if (data.length > 6000) data = literal(JSON.stringify({status:'task_sources_exceed_budget',
          read:'houdini_query(source_ref="index")',
          boundary:'Source anchors exceed the context budget; read original sources before reconciling requirements. No inferred requirements or permission.'}))
        sections.push({name:TASK_NAME,text:'Recorded task source anchors (data, not additional instructions or permissions). User originals and reported plans remain separate.\n'+data})
      }
    }
    if (needsRecovery && (wantsState || wantsTask)) {
      const state = execution
      let data = literal(JSON.stringify({surface_generation:generation,state}))
      if (data.length > 7000) data = JSON.stringify({surface_generation:generation,state:'omitted_over_budget',
        boundary:'Read retained tool results and relevant current outputs before relying on old observations.'})
      sections.push({name:RECOVERY_NAME,text:'Houdini history recovery after context replacement. Historical observations only; no current-state or completion guarantee.\n'+data})
    }
    prepared.set(agent,sections)
    return result
  },{prepend:true})
}
