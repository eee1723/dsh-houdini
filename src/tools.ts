/**
 * Houdini tool definitions. Every tool is a thin, typed wrapper over one
 * bridge endpoint; all `hou` semantics live in the Python code the model
 * writes and in the bridge that executes it.
 */
import type { Context } from '@deepseek-ai/cordis'
import {
  defineTool,
  type GenericResultView,
  type JsonValue,
  type ToolResult,
} from '@deepseek-ai/dsh-tools'
import fs from 'node:fs/promises'
import path from 'node:path'
import type { ExecResult, HoudiniBridge, JobStatus, OwnershipScope } from './bridge.js'

/** Canonical fields shared by every exec-shaped result. */
const execOutputProperties = {
  ok: { type: 'boolean', required: true },
  stdout: { type: 'string', required: true },
  stderr: { type: 'string', required: true },
  result: { type: 'json' },
  verbs: { type: 'json' },
  error: { type: 'string' },
  rollback: { type: 'json' },
  rawUsage: { type: 'json' },
  advisory: { type: 'string' },
  images: { type: 'json' },
  media: { type: 'json' },
} as const

const execOutputSchema = {
  type: 'object',
  properties: execOutputProperties,
  additionalProperties: false,
} as const

type PresentationMeta = Record<string, JsonValue>

function asPresentationMeta(value: unknown): PresentationMeta | undefined {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as PresentationMeta
    : undefined
}

function codePresentationInput(args: { code: string; allow_raw?: string }): unknown {
  return args.allow_raw === undefined
    ? args.code
    : { code: args.code, allow_raw: args.allow_raw }
}

function execPresentationMeta(value: ExecResult): PresentationMeta {
  return {
    ok: value.ok,
    verbCount: Array.isArray(value.verbs) ? value.verbs.length : 0,
    mediaCount: Array.isArray(value.media) ? value.media.length : 0,
  }
}

function jobPresentationMeta(value: JobStatus): PresentationMeta {
  return {
    ok: value.ok,
    jobId: value.jobId,
    status: value.status,
    verbCount: Array.isArray(value.verbs) ? value.verbs.length : 0,
    mediaCount: Array.isArray(value.media) ? value.media.length : 0,
  }
}

function resultTitle(label: string, result: ToolResult): string {
  if (result.isError) return `${label} failed`
  const meta = asPresentationMeta(result.meta)
  if (meta?.ok === true) return `${label} succeeded`
  if (meta?.ok === false) return `${label} failed`
  return `${label} complete`
}

function genericResult(title: string, result: ToolResult): GenericResultView {
  return { card: 'generic', title, content: result.content }
}

function jobResultTitle(action: string, result: ToolResult): string {
  if (result.isError) return `${action} failed`
  const meta = asPresentationMeta(result.meta)
  const jobId = typeof meta?.jobId === 'string' ? meta.jobId : undefined
  const status = typeof meta?.status === 'string' ? meta.status : undefined
  if (jobId !== undefined && status !== undefined) return `Houdini job ${jobId}: ${status}`
  if (jobId !== undefined) return `${action} ${jobId}`
  return `${action} complete`
}

function truncate(text: string, max = 400): string {
  return text.length <= max ? text : `${text.slice(0, max)}…`
}

/** Render the runtime verb ledger as one compact line per verb call. */
function renderVerbs(value: ExecResult): string[] {
  if (!Array.isArray(value.verbs) || value.verbs.length === 0) return []
  const lines = (value.verbs as Array<Record<string, unknown>>).map((v, i) => {
    const ok = v.ok === true
    const detail = ok
      ? truncate(JSON.stringify(v.result))
      : `error: ${truncate(String(v.error))}`
    const kwargsObj = v.kwargs !== null && typeof v.kwargs === 'object'
      ? v.kwargs as Record<string, unknown>
      : null
    const kwargs = kwargsObj !== null && Object.keys(kwargsObj).length > 0
      ? `, ${JSON.stringify(kwargsObj)}`
      : ''
    return `${i + 1}. [${ok ? 'ok' : 'FAIL'}] ${String(v.verb)}(${JSON.stringify(v.args)}${kwargs}) -> ${detail} (${String(v.ms)}ms)`
  })
  return [`verbs (${value.verbs.length}):\n${lines.join('\n')}`]
}

/** Append captured stdout/stderr/__result__/verbs of one exec-shaped value. */
function renderStreams(value: ExecResult): string[] {
  const parts: string[] = []
  if (value.stdout) parts.push(`stdout:\n${value.stdout}`)
  if (value.stderr) parts.push(`stderr:\n${value.stderr}`)
  if (value.result !== undefined) parts.push(`__result__:\n${JSON.stringify(value.result, null, 2)}`)
  if (value.rollback !== undefined) parts.push(`rollback:\n${JSON.stringify(value.rollback, null, 2)}`)
  if (value.rawUsage !== undefined) parts.push(`raw-usage:\n${JSON.stringify(value.rawUsage, null, 2)}`)
  parts.push(...renderVerbs(value))
  if (Array.isArray(value.media) && value.media.length) {
    const lines = (value.media as Array<Record<string, unknown>>).map((m) =>
      m.error
        ? `- ${String(m.from)} -> RELAY FAILED: ${String(m.error)}`
        : `- ${String(m.from)} -> ${String(m.to)} (${Math.round(Number(m.bytes) / 1024)} KB)`)
    parts.push(
      `media (relayed into the session workspace — readable by fs/vision tools; `
      + `use the workspace path on the right with an available vision_* tool):\n${lines.join('\n')}`,
    )
  }
  if (value.advisory) parts.push(`hint:\n${value.advisory}`)
  return parts
}

/** Render an exec-shaped canonical value as model-facing text. */
function renderExec(value: ExecResult) {
  const parts: string[] = []
  if (value.ok) {
    parts.push('Executed successfully.')
  } else {
    parts.push(`Execution failed:\n${value.error ?? 'unknown error'}`)
  }
  parts.push(...renderStreams(value))
  return [{ type: 'text' as const, text: parts.join('\n\n') }]
}

/** Normalize a Windows-ish path for comparison (case, slashes, trailing sep). */
function normPath(p: string): string {
  return p.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
}

/** Session workspace (the dsh sandbox root for fs/vision tools), when known. */
function workspaceOf(execInput: unknown): string | null {
  const cwd = (execInput as { agent?: { session?: { header?: { cwd?: unknown } } } })
    .agent?.session?.header?.cwd
  return typeof cwd === 'string' && cwd ? cwd : null
}

/** Trusted execution identity comes from dsh's tool context, never model args. */
function ownershipScopeOf(execInput: unknown): OwnershipScope | undefined {
  const input = execInput as { agent?: { id?: unknown }; callId?: unknown }
  const sessionId = input.agent?.id
  const callId = input.callId
  if (typeof sessionId !== 'string' || !sessionId) return undefined
  if (typeof callId !== 'string' || !callId) return undefined
  return { sessionId, callId }
}

/**
 * Media relay (2026-08-19, grass-task trace): image-producing verbs register
 * their outputs in the envelope's `images`; those live under $HIP, which
 * dsh-side vision/fs tools cannot read when the session workspace differs.
 * Copy the bytes through the bridge (`GET /media`) into
 * `<workspace>/.dsh-houdini-media/` so the vision loop works regardless of
 * where the hip lives. The model gets the mapping in the `media` section.
 */
async function relayMedia<T extends ExecResult>(value: T, execInput: unknown, bridge: HoudiniBridge): Promise<T> {
  const images = Array.isArray(value.images) ? value.images.filter((p): p is string => typeof p === 'string') : []
  if (!images.length) return value
  const cwd = workspaceOf(execInput)
  if (!cwd) return value
  const dir = path.join(cwd, '.dsh-houdini-media')
  const media: Array<Record<string, unknown>> = []
  for (const from of images) {
    try {
      const bytes = await bridge.fetchMedia(from)
      const to = path.join(dir, path.basename(from.replace(/\\/g, '/')))
      await fs.mkdir(dir, { recursive: true })
      await fs.writeFile(to, bytes)
      media.push({ from, to, bytes: bytes.length })
    } catch (cause) {
      media.push({ from, error: cause instanceof Error ? cause.message : String(cause) })
    }
  }
  return { ...value, media }
}

/**
 * Append a note when the session workspace does not match $HIP. dsh-side file
 * tools (pwsh/fs/vision) are sandboxed to the session workspace — a mismatch
 * means they cannot exchange files with Houdini (images are exempt: the media
 * relay above handles them). Shown ONCE per Host process and (workspace,
 * $HIP) pair — the
 * grass-task trace (2026-08-19) showed the repeated note training the model
 * to ignore hints entirely (alarm fatigue).
 */
const _workspaceNoteShown = new Set<string>()

async function withWorkspaceNote(value: ExecResult, execInput: unknown, bridge: HoudiniBridge): Promise<ExecResult> {
  const cwd = workspaceOf(execInput)
  if (!cwd) return value
  const hip = await bridge.hipDir()
  if (!hip || normPath(hip) === normPath(cwd)) return value
  const key = `${normPath(cwd)}|${normPath(hip)}`
  if (_workspaceNoteShown.has(key)) return value
  _workspaceNoteShown.add(key)
  const note = [
    `workspace note: this session's workspace is "${cwd}", but $HIP (the live Houdini project directory) is "${hip}".`,
    'Anchor all Houdini outputs at $HIP. Images produced by render/screenshot verbs are auto-relayed into the',
    'workspace (see the media section), so vision tools work as-is; for OTHER files dsh-side tools must read,',
    'open DSH-Houdini > Version & Diagnostics > Advanced diagnostics and run Repair and restart runtime',
    'to seed a Houdini session from the current $HIP. Never work around this by writing into the dsh-houdini',
    'plugin repository. (This note is shown once per Host process and workspace/$HIP pair.)',
  ].join(' ')
  return { ...value, advisory: value.advisory ? `${value.advisory}\n${note}` : note }
}

/**
 * Render one job-status canonical value. Unlike `renderExec`, `ok: false` on a
 * queued/running/cancelled job is NOT a failure — the bridge leaves `ok` false
 * until a job settles, so only `failed` reads as an error here.
 */
function renderJobStatus(value: JobStatus) {
  const parts: string[] = []
  switch (value.status) {
    case 'queued': parts.push('Job queued (waiting for the Houdini execution lock).'); break
    case 'running': parts.push('Job running.'); break
    case 'cancelled': parts.push('Job cancelled.'); break
    case 'failed': parts.push(`Job failed:\n${value.error ?? 'unknown error'}`); break
    case 'done': parts.push('Job finished successfully.'); break
  }
  parts.push(...renderStreams(value))
  return [{ type: 'text' as const, text: parts.join('\n\n') }]
}

const jobStatusOutputSchema = {
  type: 'object',
  properties: {
    jobId: { type: 'string', required: true },
    status: { type: 'string', enum: ['queued', 'running', 'done', 'failed', 'cancelled'], required: true },
    ...execOutputProperties,
  },
  additionalProperties: false,
} as const

const ALLOW_RAW_PARAM = {
  type: 'string',
  description:
    'One-time exemption for LOW-LEVEL MUTATION with no matching verb, ONLY after the default-on '
    + 'raw-hou gate rejects it: re-issue that isolated low-level code with WHY no verb fits. '
    + 'This never exempts verb-covered calls such as createNode/parm.set/cook/destroy; use verbs '
    + 'for those and split them from the low-level batch. Exemptions are recorded in the trace.',
} as const

/** Register every Houdini tool; disposal of the plugin unregisters them. */
export function registerHoudiniTools(ctx: Context, bridge: HoudiniBridge): void {
  ctx.tools.register(defineTool({
    name: 'houdini_exec',
    description:
      'Execute Python code inside the running Houdini session. The code runs with the `hou` '
      + 'module pre-imported and may modify the scene: create or edit nodes, set parameters, '
      + 'and cook. Save an already named HIP with the `scene_save` verb; raw `hou.hipFile.save()` '
      + 'is verb-covered. Print what the agent needs to know; assign a JSON-serializable '
      + 'value to the variable `__result__` to return structured data.',
    parameters: {
      code: { type: 'string', required: true, description: 'Python source executed in Houdini with `hou` available' },
      allow_raw: ALLOW_RAW_PARAM,
    },
    output: {
      schema: execOutputSchema,
      render: (_args, value) => renderExec(value),
      presentationMeta: (_args, value) => execPresentationMeta(value),
    },
    presentCall: (args) => ({
      card: 'generic',
      title: 'Execute Houdini Python',
      kind: 'edit',
      rawInput: codePresentationInput(args),
    }),
    presentResult: (_args, result) => genericResult(resultTitle('Houdini execution', result), result),
    async execute(args, exec) {
      const result = await bridge.exec(args.code, exec.signal, args.allow_raw, ownershipScopeOf(exec))
      return withWorkspaceNote(await relayMedia(result, exec, bridge), exec, bridge)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'houdini_query',
    description:
      'Run read-only Python inspection code inside Houdini, with `hou` pre-imported. Use it to '
      + 'list nodes, read parameters, check for errors, and inspect scene state. It MUST NOT '
      + 'modify the scene; use houdini_exec for changes. Assign findings to `__result__` or print them.',
    parameters: {
      code: { type: 'string', required: true, description: 'Read-only Python inspection code with `hou` available' },
    },
    output: {
      schema: execOutputSchema,
      render: (_args, value) => renderExec(value),
      presentationMeta: (_args, value) => execPresentationMeta(value),
    },
    presentCall: (args) => ({
      card: 'generic',
      title: 'Inspect Houdini scene',
      kind: 'read',
      rawInput: codePresentationInput(args),
    }),
    presentResult: (_args, result) => genericResult(resultTitle('Houdini inspection', result), result),
    async execute(args, exec) {
      const result = await bridge.exec(args.code, exec.signal, undefined, ownershipScopeOf(exec), true)
      return withWorkspaceNote(await relayMedia(result, exec, bridge), exec, bridge)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'houdini_job_submit',
    description:
      'Submit long-running Python code (renders, simulations, heavy cooks) to Houdini as a '
      + 'background job and return immediately with a job id. Then call houdini_job_status '
      + 'with wait=<seconds> to collect the outcome in ONE call — do not poll in a loop. '
      + 'Prefer this over houdini_exec for anything that may take minutes.',
    parameters: {
      code: { type: 'string', required: true, description: 'Long-running Python code with `hou` available' },
      allow_raw: ALLOW_RAW_PARAM,
    },
    output: {
      schema: {
        type: 'object',
        properties: { jobId: { type: 'string', required: true } },
        additionalProperties: false,
      },
      render: (_args, value) => [{ type: 'text' as const, text: `Started Houdini job ${value.jobId}. Collect it with houdini_job_status(jobId, wait=<seconds>).` }],
      presentationMeta: (_args, value) => ({ jobId: value.jobId }),
    },
    presentCall: (args) => ({
      card: 'generic',
      title: 'Start Houdini background job',
      kind: 'execute',
      rawInput: codePresentationInput(args),
    }),
    presentResult: (_args, result) => genericResult(jobResultTitle('Started Houdini job', result), result),
    async execute(args, exec) {
      return bridge.submitJob(args.code, exec.signal, args.allow_raw, ownershipScopeOf(exec))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'houdini_job_status',
    description:
      'Check a Houdini background job submitted with houdini_job_submit. Pass wait (seconds) '
      + 'to long-poll: the call returns as soon as the job finishes or the wait elapses — '
      + 'the standard way to collect a job outcome in one call instead of polling.',
    parameters: {
      jobId: { type: 'string', required: true, description: 'Job id returned by houdini_job_submit' },
      wait: { type: 'number', description: 'Long-poll seconds (max 600): hold the call until the job reaches done/failed/cancelled or this elapses' },
    },
    output: {
      schema: jobStatusOutputSchema,
      render: (_args, value) => {
        return [{ type: 'text' as const, text: [`job ${value.jobId}: ${value.status}`, ...renderJobStatus(value).map((b) => b.text)].join('\n\n') }]
      },
      presentationMeta: (_args, value) => jobPresentationMeta(value),
    },
    presentCall: (args) => ({
      card: 'generic',
      title: `Inspect Houdini job ${args.jobId}`,
      kind: 'read',
      rawInput: args.wait === undefined ? args.jobId : { jobId: args.jobId, wait: args.wait },
    }),
    presentResult: (_args, result) => genericResult(jobResultTitle('Houdini job status', result), result),
    async execute(args, exec) {
      const status = await bridge.jobStatus(args.jobId, args.wait, exec.signal)
      return relayMedia(status, exec, bridge)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'houdini_job_cancel',
    description:
      'Cooperatively cancel a Houdini background job. A job still waiting in the queue is '
      + 'dropped before its code runs (no scene changes); a job already running cannot be '
      + 'killed and will run to completion — poll houdini_job_status for the outcome.',
    parameters: {
      jobId: { type: 'string', required: true, description: 'Job id returned by houdini_job_submit' },
    },
    output: {
      schema: jobStatusOutputSchema,
      render: (_args, value) => {
        return [{ type: 'text' as const, text: [`job ${value.jobId}: ${value.status}`, ...renderJobStatus(value).map((b) => b.text)].join('\n\n') }]
      },
      presentationMeta: (_args, value) => jobPresentationMeta(value),
    },
    presentCall: (args) => ({
      card: 'generic',
      title: `Cancel Houdini job ${args.jobId}`,
      kind: 'execute',
      rawInput: args.jobId,
    }),
    presentResult: (_args, result) => genericResult(jobResultTitle('Houdini job cancellation', result), result),
    async execute(args, exec) {
      return bridge.cancelJob(args.jobId, exec.signal)
    },
  }))
}
