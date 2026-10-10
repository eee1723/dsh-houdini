/** Pure presentation of Bridge results. Domain conclusions come from the
 * Bridge; this layer renders them without inventing a second interpretation. */
import type { GenericResultView, ToolResult } from '@deepseek-ai/dsh-tools'
import type { ExecResult, JobHandle, JobStatus, JsonValue } from './bridge.js'
import { imageBlocks } from './image-output.js'

const execOutputProperties = {
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
} as const

export const execOutputSchema = {
  type: 'object', properties: execOutputProperties, additionalProperties: false,
} as const

export const jobStatusOutputSchema = {
  type: 'object',
  properties: {
    jobId: { type: 'string', required: true },
    status: { type: 'string', enum: ['queued', 'running', 'done', 'failed', 'cancelled'], required: true },
    ...execOutputProperties,
  },
  additionalProperties: false,
} as const

type PresentationMeta = Record<string, JsonValue>
const object = (value: unknown): PresentationMeta | undefined =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as PresentationMeta : undefined

export function codePresentationInput(args: { code: string; allow_raw?: string }): unknown {
  return args.allow_raw === undefined ? args.code : args
}

export function execPresentationMeta(value: ExecResult): PresentationMeta {
  return {
    ok: value.ok,
    verbCount: Array.isArray(value.verbs) ? value.verbs.length : 0,
    imageCount: Array.isArray(value.imageAttachments)
      ? value.imageAttachments.filter(item => object(item)?.attachment).length : 0,
    ...(Array.isArray(value.checks) && value.checks.length ? { checksPending: true } : {}),
    ...(value.outcome ? { outcome: value.outcome } : {}),
    canonical: value as unknown as JsonValue,
  }
}

export function jobPresentationMeta(value: JobStatus): PresentationMeta {
  return { ...execPresentationMeta(value), jobId: value.jobId, status: value.status }
}

export function jobHandleMeta(value: JobHandle): PresentationMeta {
  return {
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
  if (meta?.ok === true && Number(object(outcome?.operations)?.failed) > 0)
    return `${label} · 批次完成，部分操作失败`
  if (meta?.ok === true && meta?.checksPending) return `${label} · 已执行，检查需要关注`
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
  if (typeof meta?.jobId === 'string' && meta.status === 'done')
    return resultTitle(`长任务 ${meta.jobId}`, result)
  const states: Record<string, string> = { queued: '排队中', running: '执行中', failed: '失败', cancelled: '已取消' }
  if (typeof meta?.jobId === 'string') return typeof meta.status === 'string'
    ? `长任务 ${meta.jobId} · ${states[meta.status] ?? meta.status}` : `${action} · ${meta.jobId}`
  return `${action} · 已返回`
}

const pointerKey = (key: string) => key.replaceAll('~', '~0').replaceAll('/', '~1')

/** Identical JSON values have one addressable copy. Never truncate arbitrary
 * result text: a diagnostic at its end is as important as one at its start. */
function retainedProjection(stored: boolean) {
  const seen = new Map<string, string>()
  const duplicate = (prior: string, pointer: string) => ({
    duplicate_of: prior, ...(stored ? { detail_pointer: pointer } : {}),
  })
  const project = (value: unknown, pointer: string): unknown => {
    if (!stored && seen.size === 0) return value
    if (value === null || (typeof value !== 'object' && typeof value !== 'string')) return value
    const encoded = JSON.stringify(value)
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
    const encoded = JSON.stringify(value)
    if (encoded && encoded.length >= 256 && !seen.has(encoded)) seen.set(encoded, pointer)
    if (stored && value !== null && typeof value === 'object') Object.entries(value).forEach(([key, child]) =>
      remember(child, `${pointer}/${pointerKey(key)}`))
  }
  const help = (value: unknown, pointer: string): unknown => {
    const encoded = JSON.stringify(value)
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
  const retained = object(value.details)?.stored === true
  // Without an archive, only complete help values already shown in this reply
  // are shared. All other results keep their full inline fallback.
  const projection = retainedProjection(retained)
  const project = projection.project
  const field = (label: string, key: keyof ExecResult, compact = true) => {
    if (value[key] !== undefined) parts.push(`${label}:\n${JSON.stringify(
      compact ? project(value[key], `/${key}`) : value[key])}`)
  }
  field('request-receipt', 'requestReceipt', false)
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
    JSON.stringify(item.result) === JSON.stringify(value.result))) field('__result__', 'result')
  if (value.stdout) {
    const stdout = Array.isArray(value.verbs) && value.verbs.length
      ? value.stdout.split('\n').filter(line => !line.startsWith('[verb] ')).join('\n').trim()
      : value.stdout
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
        && JSON.stringify(summary) === JSON.stringify(sourceSummary)
      // An explicit Bridge summary or passed check supports focused output.
      // Unknown/unclassified results stay inline even when Python succeeded.
      const parameterCatalog = object(summary)?.kind === 'parameter_catalog'
      const hasSelectedResult = !parameterCatalog && value.result !== undefined && verb.ok === true && verb.check_status === 'passed'
      const needsAttention = verb.ok === false || ['failed', 'warning', 'unverified'].includes(String(verb.check_status))
        || (typeof result === 'string' && result.startsWith('[dsh-houdini: JSON value omitted:'))
      // A catalogue is discovery data, not a passed validation. With no
      // selected output its full contents are the answer; with __result__ the
      // caller's filtering wins and the typed catalogue stays in the archive.
      const summarizedResult = sameSummary && (!parameterCatalog
        || (verb.verb === 'list_parms' && verb.ok === true && verb.check_status === undefined
          && Array.isArray(result) && object(summary)?.parameter_count === result.length && value.result !== undefined))
      return {
        ...entry, detail_pointer: `/verbs/${index}`,
        ...(summary !== undefined ? { summary: sameSummary
          ? { evidence_pointer: `/evidence/${evidenceIndex}`, detail_pointer: `/verbs/${index}/summary` }
          : project(summary, `/verbs/${index}/summary`) } : {}),
        ...(verb.verb !== 'verb_help' && result !== undefined
          ? { result: !needsAttention && (summarizedResult || hasSelectedResult)
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

export function renderExec(value: ExecResult) {
  return [{ type: 'text' as const, text: [executionSummary(value), ...renderFields(value)].join('\n\n') }, ...imageBlocks(value)]
}

export function renderJobStatus(value: JobStatus) {
  const summary = {
    queued: 'Job queued (waiting for the Houdini execution lock).',
    running: 'Job running.',
    cancelled: 'Job cancelled.',
    failed: `Job failed:\n${value.error ?? 'unknown error'}`,
    done: executionSummary(value),
  }[value.status]
  return [{ type: 'text' as const, text: [`job ${value.jobId}: ${value.status}`, summary,
    ...renderFields(value)].join('\n\n') }, ...imageBlocks(value)]
}

export function renderJobHandle(value: JobHandle) {
  const summary = value.jobId
    ? `Started Houdini job ${value.jobId}. Collect it with houdini_job_status(jobId, wait=<seconds>).`
    : `Job admission uncertain; do not resubmit.\n${value.error || ''}`
  return [{ type: 'text' as const, text: summary + (value.requestReceipt
    ? `\n\nrequest-receipt:\n${JSON.stringify(value.requestReceipt)}` : '') }]
}
