/** Pure presentation of Bridge results. Domain conclusions come from the
 * Bridge; this layer renders them without inventing a second interpretation. */
import type { GenericResultView, ToolResult } from '@deepseek-ai/dsh-tools'
import type { ExecResult, JobHandle, JobStatus, JsonValue } from './bridge.js'
import { imageBlocks } from './image-output.js'
import {TextRetainer,formatRetentionNotice} from '@deepseek-ai/dsh-output-retention'
import {DETAIL_THRESHOLD,MAX_PRESENTATION_BYTES} from './result-policy.js'

const execOutputProperties = {
  job_id: {type:'string'},
  jobId: {type:'string'},
  status: {type:'string',enum:['queued','running','done','failed','cancelled']},
  ok: { type: 'boolean', required: true },
  stdout: { type: 'string', required: true },
  stderr: { type: 'string', required: true },
  result: { type: 'json' },
  verbs: { type: 'json' },
  outcome: { type: 'json' },
  error: { type: 'string' },
  rollback: { type: 'json' },
  transaction: { type: 'json' },
  rawUsage: { type: 'json' },
  advisory: { type: 'string' },
  images: { type: 'json' },
  imageAttachments: { type: 'json' },
  artifactCandidates: { type: 'json' },
  checks: { type: 'json' },
  evidence: { type: 'json' },
  execution: { type: 'json' },
  details: { type: 'json' },
  requestReceipt: { type: 'json' },
  script: { type: 'json' },
} as const

export const execOutputSchema = {
  type: 'object', properties: execOutputProperties, additionalProperties: false,
} as const

type PresentationMeta = Record<string, JsonValue>
const object = (value: unknown): PresentationMeta | undefined =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as PresentationMeta : undefined

export function codePresentationInput(args: { code?: string; script?:string; expected_sha256?:string; allow_raw?: string }): unknown {
  return args.allow_raw === undefined && args.script === undefined && args.expected_sha256 === undefined ? args.code : args
}

export const EXECUTION_FACT_PROJECTION = 'dsh-houdini/execution-facts-v1'
const pointerKey = (key: string) => key.replaceAll('~', '~0').replaceAll('/', '~1')

/** Keep complete values out of persistent browser facts even when archival
 * fails. Budgeting changes presentation only; omitted fields remain identified
 * by their pointer and the result's original-retention/recovery reference. */
export function boundedFact(value:any,pointer='',budget=MAX_PRESENTATION_BYTES):any {
  if(value===undefined)return value
  if(Buffer.byteLength(JSON.stringify(value))<=budget)return value
  const omitted={detail_pointer:pointer,value_omitted:true,...(Array.isArray(value)?{count:value.length}:{})}
  if(budget<512||Array.isArray(value)||value===null)return omitted
  if(typeof value==='string') {
    // JSON may escape every retained byte as six ASCII bytes. Reserve both
    // the exact omission notice and that worst-case encoding overhead.
    const cap=Math.max(0,Math.floor((budget-256)/12)),retainer=new TextRetainer({kind:'headTail',headBytes:cap,tailBytes:cap})
    retainer.push(value)
    const retained=retainer.finish()
    return retained.text+'\n['+formatRetentionNotice({scope:'result fact',strategy:'headTail',unit:'bytes',
      limit:{head:cap,tail:cap},kept:Buffer.byteLength(retained.text),omitted:retained.omittedBytes},()=>`Original field: ${pointer}. See result details/recovery.`)+']'
  }
  if(typeof value!=='object')return omitted
  const entries=Object.entries(value),result:Record<string,any>={}
  let used=2,index=0
  for(const [key,child] of entries) {
    const overhead=Buffer.byteLength(JSON.stringify(key))+2
    if(used+overhead+128>budget)break
    const allowance=Math.max(128,Math.floor((budget-used-overhead)/(entries.length-index)))
    const field=boundedFact(child,pointer+'/'+pointerKey(key),allowance)
    result[key]=field;used+=overhead+Buffer.byteLength(JSON.stringify(field)??'null');index++
  }
  if(index<entries.length)result.__dsh_omitted_fields={count:entries.length-index,detail_pointer:pointer}
  return Buffer.byteLength(JSON.stringify(result))<=budget?result:omitted
}

/** DSH history needs recovery and delivery facts, not another copy of every
 * authored result. The immutable archive owns those complete payloads. */
export function executionLogValue(value: ExecResult): JsonValue {
  if(value.details===undefined&&JSON.stringify(value).length<DETAIL_THRESHOLD)return value as unknown as JsonValue
  const { result: _result, evidence: _evidence, stdout: _stdout, images: _images,
    artifactCandidates: _artifactCandidates, verbs, ...facts } = value as any
  const compactVerbs = Array.isArray(verbs) ? verbs.map((item: any) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return item
    const { args: _args, kwargs: _kwargs, result: _verbResult, summary: _summary, ...entry } = item
    return { ...entry, ...((item.verb === 'present_nodes' || item.ok === false) && item.result !== undefined
      ? { result: item.result } : {}) }
  }) : undefined
  const inventory = (rows: unknown, pointer: string) => Array.isArray(rows)
    ? { count: rows.length, detail_pointer: pointer } : rows
  const execution = object(value.execution), impact = object(execution?.impact)
  const transaction = object(value.transaction)
  const projected={ ...facts, ...(compactVerbs ? { verbs: compactVerbs } : {}),
    ...(execution ? { execution: { ...execution,
      ...(impact ? { impact: impact.nodes !== undefined
        ? { ...impact, nodes: inventory(impact.nodes, '/execution/impact/nodes') } : impact } : {}),
      ...(execution.outputs !== undefined ? { outputs: inventory(execution.outputs, '/execution/outputs') } : {}),
    } } : {}),
    ...(transaction ? { transaction: transaction.nodes !== undefined
      ? { ...transaction, nodes: inventory(transaction.nodes, '/transaction/nodes') } : transaction } : {}),
    details: {
      ...(value.details===undefined?{stored:false,storage:'unavailable',
        recovery:'The producer supplied no durable original reference. The immediate structured return is complete; use the original Bridge request if still retained. Do not resubmit scene code.'}:object(value.details)),
      projection: EXECUTION_FACT_PROJECTION,
      omitted: ['/result', '/evidence', '/stdout', '/images', '/artifactCandidates',
        '/execution/impact/nodes', '/execution/outputs', '/transaction/nodes',
        '/verbs/*/args', '/verbs/*/kwargs', '/verbs/*/result', '/verbs/*/summary'],
    } }
  // Put identity/recovery and actual execution verdicts before optional
  // diagnostics when a future or unusually large fact itself needs bounding.
  const {ok,job_id,jobId,status,requestReceipt,execution:observed,transaction:changed,outcome,details,error,stderr,...rest}=projected
  return boundedFact({ok,...(job_id?{job_id}:{}),...(jobId?{jobId}:{}),...(status?{status}:{}),
    ...(requestReceipt?{requestReceipt}:{}),...(observed?{execution:observed}:{}),...(changed?{transaction:changed}:{}),
    ...(outcome?{outcome}:{}),details,...(error?{error}:{}),...(stderr?{stderr}:{}),...rest},'',MAX_PRESENTATION_BYTES) as JsonValue
}

export function execPresentationMeta(value: ExecResult): PresentationMeta {
  return {
    ok: value.ok,
    verbCount: Array.isArray(value.verbs) ? value.verbs.length : 0,
    imageCount: Array.isArray(value.imageAttachments)
      ? value.imageAttachments.filter(item => object(item)?.attachment).length : 0,
    ...(Array.isArray(value.checks) && value.checks.length ? { checksPending: true } : {}),
    ...(value.outcome ? { outcome: boundedFact(value.outcome,'/outcome',4096) } : {}),
    canonical: executionLogValue(value),
  }
}

export function jobHandleMeta(value: JobHandle): PresentationMeta {
  return {
    ...(value.job_id ? { job_id: value.job_id } : {}),
    ...(value.jobId ? { jobId: value.jobId } : {}),
    canonical: value as unknown as JsonValue,
  }
}

export function resultTitle(label: string, result: ToolResult): string {
  const meta = object(result.meta)
  const receipt = object(object(meta?.canonical)?.requestReceipt)
  // A successful receipt lookup is not successful HOM execution. Use the
  // original receipt before the Host delivery flag, including lost transport.
  if (receipt && typeof receipt.status === 'string' && receipt.status !== 'done') {
    const state = receipt.jobId && receipt.job_finished === true
      ? receipt.job_result_available === false ? '后台任务已结束 · 结果不可用'
        : receipt.job_result_available === true ? '后台任务已结束 · 待收集结果' : undefined
      : receipt.jobId ? ({queued:'后台任务排队中',running:'后台任务执行中'} as Record<string,string>)[String(receipt.job_status)] : undefined
    const states: Record<string,string> = {
      queued:'请求已排队',running:'请求执行中',job_submitted:'后台任务已提交',not_executed:'未执行',
      unknown_transport:'结果未知 · 需要查回',unknown_runtime:'运行环境已变化 · 结果未知',unknown:'请求结果未知',
      result_expired:'已结束 · 结果已过期',result_unavailable:'已结束 · 结果不可用',index:'已读取请求索引',
    }
    return `${label} · ${state ?? states[receipt.status] ?? '请求状态已返回'}`
  }
  if (result.isError) return `${label} · 失败`
  const outcome = object(meta?.outcome)
  const operations = object(outcome?.operations)
  const failed = Number(operations?.failed)
  if (meta?.ok === true && failed > 0) {
    if (object(object(meta.canonical)?.execution)?.source_kind === 'structured_query' && failed === Number(operations?.total))
      return `${label} · 查询未取得结果`
    return `${label} · 批次完成，部分操作失败`
  }
  if (meta?.ok === true && meta?.checksPending) return `${label} · 已执行，检查需要关注`
  if (meta?.ok === true && object(object(meta.canonical)?.transaction)?.status === 'effects_unverified')
    return `${label} · 已执行，场景影响未核实`
  if (meta?.ok === true) return `${label} · 成功`
  if (meta?.ok === false) return `${label} · 失败`
  return `${label} · 已返回`
}

export function genericResult(title: string, result: ToolResult): GenericResultView {
  return { card: 'generic', title, content: result.content }
}

export function jobResultTitle(action: string, result: ToolResult): string {
  if (result.isError) return `${action} · 失败`
  const meta = object(result.meta)
  if (typeof meta?.job_id === 'string') return `${action} · ${meta.job_id}`
  if (typeof meta?.jobId === 'string' && meta.status === 'done')
    return resultTitle(`长任务 ${meta.jobId}`, result)
  const states: Record<string, string> = { queued: '排队中', running: '执行中', failed: '失败', cancelled: '已取消' }
  if (typeof meta?.jobId === 'string') return typeof meta.status === 'string'
    ? `长任务 ${meta.jobId} · ${states[meta.status] ?? meta.status}` : `${action} · ${meta.jobId}`
  return `${action} · 已返回`
}

// JSON object member order is not execution evidence. Compare values without
// changing the original payload, array order, or absent/explicit-null fields.
const comparisonKey = (value: unknown): string | undefined => JSON.stringify(value, (_key, item) =>
  item !== null && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item)

/** Identical JSON values have one addressable copy. Never truncate arbitrary
 * result text: a diagnostic at its end is as important as one at its start. */
function retainedProjection(stored: boolean, verbs: JsonValue[] = []) {
  const seen = new Map<string, string>()
  // Only source-proven audit inventories can be abbreviated. Arbitrary selected
  // data and future schemas stay inline; full canonical values remain archived.
  const inventories = new Map<string, Record<string, unknown>>()
  if (stored) for (const item of verbs) {
    const verb = object(item), result = object(verb?.result)
    if (verb?.ok !== true || !result) continue
    const transfers = result.native_identity_transfers
    if (['hda_create', 'hda_fork'].includes(String(verb.verb)) && Array.isArray(transfers)
      && transfers.length > 8 && transfers.every(item => {
        const row = object(item)
        return row && Object.keys(row).length === 4 && typeof row.node === 'string'
          && ['previous_identity', 'identity', 'native_anchor_identity'].every(key => Number.isSafeInteger(row[key]))
      })) inventories.set(comparisonKey(transfers)!, {kind:'native_identity_transfers',count:transfers.length})
    const discarded = result.discarded_descendants, editable = result.editable_discarded_descendants
    const pair = (item:unknown) => Array.isArray(item) && item.length === 2
      && typeof item[0] === 'string' && Number.isSafeInteger(item[1])
    if (verb.verb === 'hda_edit' && result.ok === true && result.action === 'lock'
      && result.discard_changes === true && Array.isArray(discarded) && Array.isArray(editable)
      && discarded.length > 8 && discarded.length === result.descendant_count
      && editable.length === result.editable_descendant_count && discarded.every(pair) && editable.every(pair)) {
      const identities = new Set(discarded.map(item => comparisonKey(item)))
      if (editable.every(item => identities.has(comparisonKey(item)))) inventories.set(comparisonKey(discarded)!, {
        kind:'definition_rebuild_descendants',count:discarded.length,
        editable_descendants:editable,
        scope:'Editable boundaries shown in full; complete descendants including locked native internals are in details. All listed descendants are in the discard/rebuild scope.',
      })
    }
  }
  const duplicate = (prior: string, pointer: string) => ({
    duplicate_of: prior, ...(stored ? { detail_pointer: pointer } : {}),
  })
  const project = (value: unknown, pointer: string): unknown => {
    if (!stored && seen.size === 0) return value
    if (value === null || (typeof value !== 'object' && typeof value !== 'string')) return value
    const encoded = comparisonKey(value)!
    const inventory = inventories.get(encoded)
    if (inventory) return {...inventory, detail_pointer:pointer}
    if (encoded.length >= 256) {
      const prior = seen.get(encoded)
      if (prior !== undefined) return duplicate(prior, pointer)
      if (stored) seen.set(encoded, pointer)
    }
    if (typeof value === 'string') return value
    return Array.isArray(value)
      ? value.map((child, index) => project(child, `${pointer}/${index}`))
      : Object.fromEntries(Object.entries(value).map(([key, child]) =>
        [key, project(child, `${pointer}/${pointerKey(key)}`)]))
  }
  // Help stays immediately executable, including long docs and nested input
  // schemas. Remember the full value so __result__ cannot repeat the same help.
  const remember = (value: unknown, pointer: string): void => {
    const encoded = comparisonKey(value)
    if (encoded && encoded.length >= 256 && !seen.has(encoded)) seen.set(encoded, pointer)
    if (stored && value !== null && typeof value === 'object') Object.entries(value).forEach(([key, child]) =>
      remember(child, `${pointer}/${pointerKey(key)}`))
  }
  const help = (value: unknown, pointer: string): unknown => {
    const encoded = comparisonKey(value)
    if (encoded && encoded.length >= 256) {
      const prior = seen.get(encoded)
      if (prior !== undefined) return duplicate(prior, pointer)
    }
    remember(value, pointer)
    return value
  }
  return { project, help }
}

function renderFields(value: ExecResult): string[] {
  const parts: string[] = []
  if (value.job_id) parts.push(nativeJobActions(value.job_id))
  const retained = object(value.details)?.stored === true
  // Without an archive, only complete help values already shown in this reply
  // are shared. All other results keep their full inline fallback.
  const projection = retainedProjection(retained, Array.isArray(value.verbs) ? value.verbs : [])
  const project = projection.project
  const field = (label: string, key: keyof ExecResult, compact = true) => {
    if (value[key] !== undefined) parts.push(`${label}:\n${JSON.stringify(
      compact ? project(value[key], `/${key}`) : value[key])}`)
  }
  field('request-receipt', 'requestReceipt', false)
  field('script-source', 'script', false)
  field('execution-outcome', 'outcome', false)
  field('checks', 'checks', false)
  // The Host may spill large tool text. Put request, recovery and observation
  // facts before any unbounded selected payload, help, stdout or ledger.
  if (value.transaction !== undefined) {
    const transaction = object(value.transaction)
    parts.push(`transaction:\n${JSON.stringify(retained && transaction
      && ['committed', 'no_scene_change'].includes(String(transaction.status))
      ? auditNodes(transaction, '/transaction', project) : project(value.transaction, '/transaction'))}`)
  }
  field('rollback', 'rollback', false)
  field('raw-usage', 'rawUsage', false)
  const operationErrors = Array.isArray(value.verbs) ? value.verbs.flatMap((item, index) => {
    const verb = object(item)
    return verb?.ok === false ? [{ ledgerIndex: index + 1, verb: verb.verb, error: verb.error }] : []
  }) : []
  if (operationErrors.length) parts.push(`operation-errors:\n${JSON.stringify(operationErrors)}`)
  if (value.evidence !== undefined) {
    const evidence = retained && value.result !== undefined && object(value.execution)?.read_only === true
      && Array.isArray(value.evidence) ? value.evidence.map((item, index) =>
        selectedNodeCard(item, `/evidence/${index}`, project)) : project(value.evidence, '/evidence')
    parts.push(`operation-evidence:\n${JSON.stringify(evidence)}`)
  }
  if (value.execution !== undefined) {
    const execution = object(value.execution)
    const impact = object(execution?.impact)
    parts.push(`execution-observation:\n${JSON.stringify(retained && execution && impact
      ? Object.fromEntries(Object.entries(execution).map(([key, item]) => [key, key === 'impact'
        ? auditNodes(impact, '/execution/impact', project) : project(item, `/execution/${pointerKey(key)}`)]))
      : project(value.execution, '/execution'))}`)
  }
  if (value.stderr) parts.push(`stderr:\n${value.stderr}`)
  const verbs = Array.isArray(value.verbs) ? value.verbs : []
  const help = verbs.flatMap((item, index) => object(item)?.verb === 'verb_help'
    && object(item)?.ok === true ? [{ result: object(item)?.result, index }] : [])
  if (help.length) parts.push(`verb-help:\n${JSON.stringify(help.map((item, index) =>
    projection.help(item.result, retained ? `/verbs/${item.index}/result` : `verb-help[${index}]`)))}`)
  // The code author's selected output precedes routine ledger details, while
  // independent Bridge checks and recovery facts have already been shown.
  if (value.result !== undefined && !help.some(item =>
    comparisonKey(item.result) === comparisonKey(value.result))) field('__result__', 'result')
  if (value.stdout) {
    const stdout = executionStdout(value)
    if (stdout) parts.push(`stdout:\n${stdout}`)
  }
  if (verbs.length) {
    const ledger = verbs.map((item, index) => {
      const verb = object(item)
      if (!verb) return project(item, `/verbs/${index}`)
      if (!retained) return project(verb, `/verbs/${index}`)
      const { args, kwargs, result, summary, ...entry } = verb
      const evidenceIndex = Array.isArray(value.evidence) ? value.evidence.findIndex(item =>
        object(item)?.ledgerIndex === index + 1 && object(item)?.verb === verb.verb) : -1
      const evidence = evidenceIndex >= 0 ? object((value.evidence as JsonValue[])[evidenceIndex]) : undefined
      const { ledgerIndex: _ledgerIndex, verb: _verb, ...sourceSummary } = evidence ?? {}
      const sameSummary = summary !== undefined && evidence !== undefined
        && comparisonKey(summary) === comparisonKey(sourceSummary)
      const parameterCatalog = object(summary)?.kind === 'parameter_catalog'
      const hasSelectedResult = !parameterCatalog && value.result !== undefined && verb.ok === true && verb.check_status === 'passed'
      const needsAttention = verb.ok === false || ['failed', 'warning', 'unverified'].includes(String(verb.check_status))
        || (typeof result === 'string' && result.startsWith('[dsh-houdini: JSON value omitted:'))
      const summarizedResult = sameSummary && (!parameterCatalog
        || (verb.verb === 'list_parms' && verb.ok === true && verb.check_status === undefined
          && Array.isArray(result) && object(summary)?.parameter_count === result.length && value.result !== undefined))
      const largeRoutineResult = verb.ok === true && (verb.check_status === undefined || verb.check_status === 'passed')
        && !parameterCatalog && value.result !== undefined && JSON.stringify(result).length > 512
      return {
        ...entry, detail_pointer: `/verbs/${index}`,
        ...(summary !== undefined ? { summary: sameSummary
          ? { evidence_pointer: `/evidence/${evidenceIndex}`, detail_pointer: `/verbs/${index}/summary` }
          : project(summary, `/verbs/${index}/summary`) } : {}),
        ...(verb.verb !== 'verb_help' && result !== undefined
          ? { result: !needsAttention && (summarizedResult || hasSelectedResult || largeRoutineResult)
            ? { detail_pointer: `/verbs/${index}/result` }
            : project(result, `/verbs/${index}/result`) } : {}),
      }
    })
    parts.push(`verbs (${verbs.length}):\n${JSON.stringify(ledger)}`)
  }
  field('image-attachments', 'imageAttachments', false)
  if (Array.isArray(value.artifactCandidates) && value.artifactCandidates.length) {
    field('artifact-candidates (not delivered; verify requested final files, then call present)', 'artifactCandidates', false)
  }
  if (value.advisory) parts.push(`hint:\n${value.advisory}`)
  field('result-details', 'details', false)
  return parts
}

/** Keep authored observations while omitting logger echoes already retained in the ledger. */
export function executionStdout(value:Pick<ExecResult,'stdout'|'verbs'>):string {
  const stdout=value.stdout??''
  return Array.isArray(value.verbs)&&value.verbs.length
    ?stdout.split('\n').filter(line=>!line.startsWith('[verb] ')).join('\n').trim():stdout
}

/** These two envelope lists contain audit identities, not operation results.
 * Keep incomplete/unusual rows and identity changes inline; only an ordinary
 * stable identity inventory can move behind the retained detail reference. */
function auditNodes(value: PresentationMeta, pointer: string,
  project: (value: unknown, pointer: string) => unknown): unknown {
  const nodes = value.nodes
  if (!Array.isArray(nodes) || nodes.length <= 8 || !nodes.every(item => {
    const row = object(item)
    return row && Object.keys(row).every(key => ['identity', 'prior_path', 'exists', 'path'].includes(key))
      && row.exists !== false && (row.prior_path == null || row.prior_path === row.path)
  })) return project(value, pointer)
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, key === 'nodes'
    ? { count: nodes.length, detail_pointer: `${pointer}/nodes` }
    : project(item, `${pointer}/${pointerKey(key)}`)]))
}

/** Static node-card metadata has an explicit discovery scope. When inspect
 * code selects __result__, do not append the complete parameter catalog again.
 * Keep type/version, usage/decision notes and scope; the two catalog arrays
 * remain individually readable. No execution/check evidence uses this shape. */
function selectedNodeCard(value: unknown, pointer: string,
  project: (value: unknown, pointer: string) => unknown): unknown {
  const card = object(value)
  if (!card || typeof card.operation_parameter_scope !== 'string' || typeof card.parameter_scope !== 'string'
      || !Array.isArray(card.setting_cards) || !Array.isArray(card.operation_parameters)) return project(value, pointer)
  return Object.fromEntries(Object.entries(card).map(([key, item]) => [key,
    ['setting_cards', 'operation_parameters'].includes(key) && Array.isArray(item) && JSON.stringify(item).length > 1000
      ? { count: item.length, detail_pointer: `${pointer}/${key}` }
      : project(item, `${pointer}/${pointerKey(key)}`)]))
}

function executionSummary(value: ExecResult): string {
  if(value.status==='queued'||value.status==='running')return `Original Houdini job is ${value.status}. DSH observes it; use job_output for collection and job_kill to request cancellation. Running HOM completes normally.`
  if(value.status==='cancelled')return 'Original Houdini job was cancelled before it executed.'
  const receipt = object(value.requestReceipt)
  return receipt && receipt.status !== 'done'
    ? `Request receipt status: ${receipt.status}. This reports request recovery state, not successful scene completion.${value.error ? `\n${value.error}` : ''}`
    : !value.ok ? `Execution failed:\n${value.error ?? 'unknown error'}`
    : Number(object(object(value.outcome)?.operations)?.failed) > 0
      ? 'Batch completed; one or more operations raised errors. Any fallback result is separate from the failed operations; inspect operation-errors and checks.'
    : Array.isArray(value.checks) && value.checks.length
      ? 'Operation executed; checks failed or contain warnings/unverified results. Inspect checks before continuing.'
      : 'Executed successfully.'
}

export function renderExec(value: ExecResult, maxBytes = MAX_PRESENTATION_BYTES) {
  return [{ type: 'text' as const, text: observationText([executionSummary(value), ...renderFields(value)].join('\n\n'),maxBytes) }, ...imageBlocks(value)]
}

export function renderJobStatus(value: JobStatus) {
  const summary = {
    queued: 'Job queued (waiting for the Houdini execution lock).',
    running: 'Job running.',
    cancelled: 'Job cancelled.',
    failed: `Job failed:\n${value.error ?? 'unknown error'}`,
    done: executionSummary(value),
  }[value.status]
  return [{ type: 'text' as const, text: observationText([`job ${value.jobId}: ${value.status}`, summary,
    ...renderFields(value)].join('\n\n'),MAX_PRESENTATION_BYTES) }, ...imageBlocks(value)]
}

function observationText(full: string, maxBytes: number): string {
  if(Buffer.byteLength(full)<=maxBytes)return full
  const marker='\n\n… [middle omitted to fit the presentation budget; use original request/details references; omission is not evidence of absence] …\n\n'
  const available=Math.max(0,maxBytes-Buffer.byteLength(marker))
  const headBytes=Math.ceil(available*2/3)
  if(maxBytes<Buffer.byteLength(marker)) {
    const prefix=new TextRetainer({kind:'head',maxBytes});prefix.push(full);return prefix.finish().text
  }
  // Native retainers own both UTF-8 cuts. Encode once, and place the domain
  // notice between the retained ends rather than making them look contiguous.
  const bytes=Buffer.from(full)
  const head=new TextRetainer({kind:'head',maxBytes:headBytes}),tail=new TextRetainer({kind:'tail',maxBytes:available-headBytes})
  head.push(bytes);tail.push(bytes)
  return head.finish().text+marker+tail.finish().text
}

/** Preserve the renderer's prioritized head and recovery/detail tail. The
 * native finalizer keeps only a tail, so bound before returning through its
 * existing single-text contract; never maintain a second field interpreter. */
export function renderJobObservation(value: ExecResult, maxBytes: number): string {
  if(!Number.isSafeInteger(maxBytes)||maxBytes<0)throw Error('maxBytes must be a nonnegative safe integer')
  const full=(value.status?renderJobStatus(value as JobStatus):renderExec(value))
    .filter(block=>block.type==='text').map(block=>block.text).join('\n\n')
  return observationText(full,maxBytes)
}

export function renderJobHandle(value: JobHandle) {
  const requestRef=object(value.requestReceipt)?.request_ref
  const summary = (value.job_id ? nativeJobActions(value.job_id)+'\n' : '')
    +(value.jobId?'Houdini admission confirmed; this is not execution completion.':`Houdini admission is unconfirmed; do not resubmit. ${value.error||''}`)
  return [{ type: 'text' as const, text: summary
    +(typeof requestRef==='string'?`\nRecover the original execution with houdini_request(${JSON.stringify({request_ref:requestRef})}).`:'')
    +(value.requestReceipt?`\nThe receipt's jobId is a Bridge identifier, not a DSH job_id.\n\nrequest-receipt:\n${JSON.stringify(value.requestReceipt)}`:'') }]
}

function nativeJobActions(jobId: string): string {
  const args=JSON.stringify({job_id:jobId})
  return `DSH job_id: ${JSON.stringify(jobId)}. Wait/read with job_output(${args}); request cancellation with job_kill(${args}). Cancellation does not prove Houdini has stopped.`
}
