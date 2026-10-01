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
  if (result.isError) return `${label} failed`
  const meta = object(result.meta)
  if (meta?.ok === true && meta?.checksPending) return `${label} executed; checks need attention`
  if (meta?.ok === true) return `${label} succeeded`
  if (meta?.ok === false) return `${label} failed`
  return `${label} complete`
}

export function genericResult(title: string, result: ToolResult): GenericResultView {
  return { card: 'generic', title, content: result.content }
}

export function jobResultTitle(action: string, result: ToolResult): string {
  if (result.isError) return `${action} failed`
  const meta = object(result.meta)
  if (typeof meta?.jobId === 'string') return typeof meta.status === 'string'
    ? `Houdini job ${meta.jobId}: ${meta.status}` : `${action} ${meta.jobId}`
  return `${action} complete`
}

const pointerKey = (key: string) => key.replaceAll('~', '~0').replaceAll('/', '~1')

/** Repeated JSON values and long text have one addressable copy. No verb
 * schema, status vocabulary or geometry heuristic participates in projection. */
function retainedProjection() {
  const seen = new Map<string, string>()
  const project = (value: unknown, pointer: string, diagnostic = false): unknown => {
    if (!diagnostic && typeof value === 'string' && value.length > 2000) return {
      preview: value.slice(0, 400), chars: value.length, detail_pointer: pointer,
    }
    if (value === null || typeof value !== 'object') return value
    const encoded = JSON.stringify(value)
    if (encoded.length >= 256) {
      const prior = seen.get(encoded)
      if (prior !== undefined) return { duplicate_of: prior, detail_pointer: pointer }
      seen.set(encoded, pointer)
    }
    return Array.isArray(value)
      ? value.map((child, index) => project(child, `${pointer}/${index}`, diagnostic))
      : Object.fromEntries(Object.entries(value).map(([key, child]) =>
        [key, project(child, `${pointer}/${pointerKey(key)}`, diagnostic
          || /^(errors?|warnings?|unsupported|restore_errors|failure_reasons|reason)$/.test(key))]))
  }
  return project
}

function renderFields(value: ExecResult): string[] {
  const parts: string[] = []
  const retained = object(value.details)?.stored === true
  const project = retained ? retainedProjection() : (item: unknown) => item
  const field = (label: string, key: keyof ExecResult, compact = true) => {
    if (value[key] !== undefined) parts.push(`${label}:\n${JSON.stringify(
      compact ? project(value[key], `/${key}`) : value[key])}`)
  }
  field('request-receipt', 'requestReceipt', false)
  field('checks', 'checks', false)
  field('operation-evidence', 'evidence')
  field('execution-observation', 'execution')
  field('transaction', 'transaction')
  if (value.stdout) {
    const stdout = Array.isArray(value.verbs) && value.verbs.length
      ? value.stdout.split('\n').filter(line => !line.startsWith('[verb] ')).join('\n').trim()
      : value.stdout
    if (stdout) parts.push(`stdout:\n${stdout}`)
  }
  if (value.stderr) parts.push(`stderr:\n${value.stderr}`)
  // Help is executable interface documentation and remains immediately usable.
  const help = Array.isArray(value.verbs) ? value.verbs.filter(item =>
    object(item)?.verb === 'verb_help' && object(item)?.ok === true) : []
  if (help.length) parts.push(`verb-help:\n${JSON.stringify(help.map(item => object(item)?.result))}`)
  if (value.result !== undefined && !help.some(item =>
    JSON.stringify(object(item)?.result) === JSON.stringify(value.result))) field('__result__', 'result')
  field('rollback', 'rollback', false)
  field('raw-usage', 'rawUsage', false)
  if (Array.isArray(value.verbs) && value.verbs.length) {
    const ledger = value.verbs.map((item, index) => {
      const verb = object(item)
      if (!verb) return project(item, `/verbs/${index}`)
      if (!retained) return verb
      const { args, kwargs, result, ...entry } = verb
      return {
        ...entry, detail_pointer: `/verbs/${index}`,
        ...(verb.verb !== 'verb_help' && result !== undefined
          ? { result: project(result, `/verbs/${index}/result`) } : {}),
      }
    })
    parts.push(`verbs (${value.verbs.length}):\n${JSON.stringify(ledger)}`)
  }
  field('image-attachments', 'imageAttachments', false)
  if (Array.isArray(value.artifactCandidates) && value.artifactCandidates.length) {
    field('artifact-candidates (not delivered; verify requested final files, then call present)', 'artifactCandidates', false)
  }
  if (value.advisory) parts.push(`hint:\n${value.advisory}`)
  field('result-details', 'details', false)
  return parts
}

export function renderExec(value: ExecResult) {
  const receipt = object(value.requestReceipt)
  const summary = receipt && receipt.status !== 'done'
    ? `Request receipt status: ${receipt.status}. This reports request recovery state, not successful scene completion.${value.error ? `\n${value.error}` : ''}`
    : !value.ok ? `Execution failed:\n${value.error ?? 'unknown error'}`
    : Array.isArray(value.checks) && value.checks.length
      ? 'Operation executed; checks failed or contain warnings/unverified results. Inspect checks before continuing.'
      : 'Executed successfully.'
  return [{ type: 'text' as const, text: [summary, ...renderFields(value)].join('\n\n') }, ...imageBlocks(value)]
}

export function renderJobStatus(value: JobStatus) {
  const summary = {
    queued: 'Job queued (waiting for the Houdini execution lock).',
    running: 'Job running.',
    cancelled: 'Job cancelled.',
    failed: `Job failed:\n${value.error ?? 'unknown error'}`,
    done: 'Job finished successfully.',
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
