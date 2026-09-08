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
import { createHash } from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import type { ExecResult, HoudiniBridge, JobStatus, OwnershipScope } from './bridge.js'
import { ReviewController } from './review.js'
import { readResultDetail, retainResult } from './result-details.js'

/** Canonical fields shared by every exec-shaped result. */
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
  media: { type: 'json' },
  checks: { type: 'json' },
  evidence: { type: 'json' },
  execution: { type: 'json' },
  details: { type: 'json' },
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
    ...(Array.isArray(value.checks) && value.checks.length ? { checksPending: true } : {}),
    ...(value.execution !== undefined || value.details !== undefined ? { canonical: value as unknown as JsonValue } : {}),
  }
}

function jobPresentationMeta(value: JobStatus): PresentationMeta {
  return {
    ok: value.ok,
    jobId: value.jobId,
    status: value.status,
    verbCount: Array.isArray(value.verbs) ? value.verbs.length : 0,
    mediaCount: Array.isArray(value.media) ? value.media.length : 0,
    ...(value.execution !== undefined || value.details !== undefined ? { canonical: value as unknown as JsonValue } : {}),
  }
}

function resultTitle(label: string, result: ToolResult): string {
  if (result.isError) return `${label} failed`
  const meta = asPresentationMeta(result.meta)
  if (meta?.ok === true && meta?.checksPending) return `${label} executed; checks need attention`
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
function hasCaution(value: unknown): boolean {
  if (value === null || typeof value !== 'object') return false
  const nonempty = (v:unknown) => Array.isArray(v) ? v.length > 0 : v && typeof v === 'object'
    ? Object.keys(v).length > 0 : v !== null && v !== undefined && v !== '' && v !== false && v !== 0
  for (const [key,v] of Object.entries(value)) {
    if (['ok','healthy','warning_free','restored','fresh'].includes(key) && v === false) return true
    if ((key === 'status' || key.endsWith('_status')) && typeof v === 'string'
        && !['passed','pass','ok','success','healthy','valid','committed','no_scene_change','done','restored'].includes(v)) return true
    if (/^(errors?|warnings?|failure_reasons|unsupported|restore_errors)$/.test(key) && nonempty(v)) return true
    if (hasCaution(v)) return true
  }
  return false
}

function renderVerbs(value: ExecResult): string[] {
  if (!Array.isArray(value.verbs) || value.verbs.length === 0) return []
  const lines = (value.verbs as Array<Record<string, unknown>>).map((v, i) => {
    const ok = v.ok === true
    let detail = ok
      ? truncate(JSON.stringify(v.result))
      : `error: ${truncate(String(v.error))}`
    const compact = (value.details as any)?.stored === true
    const caution = hasCaution(v.result) || ['failed','warning','unverified'].includes(String(v.check_status))
    if (compact && (caution || !ok)) detail = ok ? JSON.stringify(v.result) : `error: ${String(v.error)}`
    const kwargsObj = !compact && v.kwargs !== null && typeof v.kwargs === 'object'
      ? v.kwargs as Record<string, unknown>
      : null
    const kwargs = kwargsObj !== null && Object.keys(kwargsObj).length > 0
      ? `, ${JSON.stringify(kwargsObj)}`
      : ''
    const args = compact ? [] : v.args
    return `${i + 1}. [${ok ? 'ok' : 'FAIL'}] ${String(v.verb)}(${JSON.stringify(args)}${kwargs}) -> ${compact && ok && !caution ? JSON.stringify({ args_omitted:true, detail_pointer: `/verbs/${i}`, check_status: v.check_status ?? null, result_preview:detail }) : detail} (${String(v.ms)}ms)`
  })
  return [`verbs (${value.verbs.length}):\n${lines.join('\n')}`]
}

/** Append captured stdout/stderr/__result__/verbs of one exec-shaped value. */
function renderStreams(value: ExecResult): string[] {
  const parts: string[] = []
  const compact = (value.details as any)?.stored === true
  if (value.execution !== undefined) {
    const e:any = value.execution
    const observation = compact && Array.isArray(e.impact?.nodes) && e.impact.nodes.length > 16
      ? {...e,impact:{...e.impact,nodes:e.impact.nodes.slice(0,16),nodes_omitted:e.impact.nodes.length-16,detail_pointer:'/execution/impact/nodes'}} : e
    parts.push(`execution-observation:\n${JSON.stringify(observation)}`)
  }
  if (value.transaction !== undefined) parts.push(`transaction:\n${JSON.stringify(value.transaction)}`)
  if (Array.isArray(value.evidence)) {
    const summaries = value.evidence.flatMap(item => {
      if (item === null || typeof item !== 'object' || Array.isArray(item)
          || item.verb !== 'test_controls') return []
      const summary = item.control_summary
      return summary !== null && typeof summary === 'object' && !Array.isArray(summary)
        ? [{ ledgerIndex: item.ledgerIndex, ...summary }] : []
    })
    if (summaries.length) parts.push(`control-test-summary (not_run is not pass):\n${JSON.stringify(summaries)}`)
  }
  if (value.evidence !== undefined) {
    // Never summarize away failure/warning/unsupported evidence. For healthy
    // large records only repeated display payloads are eligible for omission.
    parts.push(`operation-evidence:\n${JSON.stringify(compact ? compactEvidence(value.evidence) : value.evidence)}`)
  }
  if (value.checks !== undefined) {
    parts.push(`CHECKS NEED ATTENTION (execution success is not validation success):\n${JSON.stringify(value.checks)}`)
  }
  if (value.stdout) {
    // The canonical ledger below already carries these tracer echoes, including errors.
    // Keep user stdout and the raw envelope; only remove duplicate model presentation.
    const output = Array.isArray(value.verbs) && value.verbs.length
      ? value.stdout.split('\n').filter(line => !line.startsWith('[verb] ')).join('\n').trim()
      : value.stdout
    if (output) parts.push(`stdout:\n${output}`)
  }
  if (value.stderr) parts.push(`stderr:\n${value.stderr}`)
  if (value.result !== undefined) {
    const result = JSON.stringify(value.result, null, 2)
    parts.push(`__result__:\n${compact && result.length > 4000 && !hasCaution(value.result) ? JSON.stringify({omitted:true,detail_pointer:'/result',chars:result.length,
      next_action:'Read the selected result fields through result_ref before relying on omitted values.'}) : result}`)
  }
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
  if (value.details !== undefined) parts.push(`result-details:\n${JSON.stringify(value.details)}`)
  return parts
}

function compactEvidence(evidence: unknown): unknown {
  if (!Array.isArray(evidence)) return evidence
  return evidence.map((item, i) => {
    if (!item || typeof item !== 'object' || JSON.stringify(item).length <= 2000) return item
    const text = JSON.stringify(item)
    if (hasCaution(item)) return item
    // Keep all scalar facts and all other fields; only omit named verbose
    // successful-detail arrays. Unknown schemas remain intact by default.
    const out = { ...item }
    for (const key of ['checked_nodes', 'cook_details', 'created', 'node_details']) {
      if (Array.isArray(out[key]) && JSON.stringify(out[key]).length > 1500) {
        out[key] = { omitted:true, count:out[key].length, detail_pointer:`/evidence/${i}/${key}` }
      }
    }
    return out
  })
}

/** Render an exec-shaped canonical value as model-facing text. */
function renderExec(value: ExecResult) {
  const parts: string[] = []
  if (value.ok) {
    parts.push(Array.isArray(value.checks) && value.checks.length
      ? 'Operation executed; checks failed or contain warnings/unverified results. Inspect checks before continuing.'
      : 'Executed successfully.')
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
export async function imageInspectionRoute(ctx: unknown, execInput: unknown): Promise<Record<string, unknown>> {
  const exec = execInput as any
  try {
    const config = exec.agent?.session.requestHeader?.()?.config
    const provider = config?.provider ?? exec.agent?.options?.provider
    const model = config?.model ?? exec.agent?.options?.model
    const llm = (ctx as any)?.get?.('llm')
    if (!provider || !model || !llm?.resolveModelInfo) throw new Error('route unavailable')
    const signal = exec.signal ? AbortSignal.any([exec.signal, AbortSignal.timeout(1500)]) : AbortSignal.timeout(1500)
    signal.throwIfAborted()
    let onAbort: () => void = () => {}
    const aborted = new Promise<never>((_, reject) => {
      onAbort = () => reject(new Error('image route lookup aborted'))
      signal.addEventListener('abort', onAbort, { once:true })
    })
    let info: any
    try { info = await Promise.race([llm.resolveModelInfo(provider, model, signal), aborted]) }
    finally { signal.removeEventListener('abort', onAbort) }
    const declared = Array.isArray(info.inputModalities) && info.inputModalities.includes('image')
    return { model, declared_image_input: declared, semantic_status:'unverified',
      next_action: declared ? 'Use read_image on the relayed path for semantic inspection.'
        : 'This route cannot use read_image. Use vision_toolkit_activate/vision_glance if available; otherwise report visual semantics unverified. Do not change model declarations based on the model name.' }
  } catch {
    return { declared_image_input:null, semantic_status:'unverified', next_action:'Image route could not be resolved; check available image inspection capability. Render transport does not establish semantic verification.' }
  }
}

async function relayMedia<T extends ExecResult>(value: T, execInput: unknown, bridge: HoudiniBridge, ctx?: Context): Promise<T> {
  const images = Array.isArray(value.images) ? value.images.filter((p): p is string => typeof p === 'string') : []
  if (!images.length) return value
  const cwd = workspaceOf(execInput)
  if (!cwd) return value
  const dir = path.join(cwd, '.dsh-houdini-media')
  const media: Array<Record<string, unknown>> = []
  const inspection = await imageInspectionRoute(ctx, execInput)
  for (const from of images) {
    try {
      const bytes = await bridge.fetchMedia(from)
      const contentId = createHash('sha256').update(bytes).digest('hex').slice(0, 12)
      const to = path.join(dir, `${contentId}-${path.basename(from.replace(/\\/g, '/'))}`)
      await fs.mkdir(dir, { recursive: true })
      await fs.writeFile(to, bytes)
      media.push({ from, to, bytes: bytes.length, inspection })
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
  const review = new ReviewController(bridge)
  ctx.tools.register(defineTool({
    name: 'houdini_exec',
    description:
      'Execute Python code inside the running Houdini session. The code runs with the `hou` '
      + 'module pre-imported and may modify the scene: create or edit nodes, set parameters, '
      + 'and cook. One call is one execution checkpoint: keep independently verifiable modules in separate calls, '
      + 'and unfamiliar read-only discovery in houdini_query before or after a committed module. '
      + 'When Houdini undo is enabled, a later failure rolls back earlier undoable edits in this same call; inspect transaction/rollback. '
      + 'Save an already named HIP with the `scene_save` verb; raw `hou.hipFile.save()` '
      + 'is verb-covered. Print what the agent needs to know; assign a JSON-serializable '
      + 'value to the variable `__result__` to return structured data. Alternatively review {parent,output,controller?} '
      + 'optionally delegates one quick issue review with current snapshot and prior tool facts; not a mandatory task stage. '
      + 'Wait for its report; no concurrent scene edits. Only that reviewer may use review_test for bounded '
      + 'batch control perturbations/preview captures with automatic restoration. No delivery registration or evidence cache.',
    parameters: {
      code: { type: 'string', description: 'Python source; mutually exclusive with review/review_test' },
      review: { type: 'json', description: 'Start one independent reviewer: {parent:absolute_SOP_network,output:absolute_final_SOP,controller?:absolute_CTRL}. Specify current-task owned nodes. Original user requirements are read by Host; do not submit a success story, contract, permissions or expected verdict.' },
      review_test: { type: 'json', description: 'Active reviewer only: {tests?:[{id,values:{numeric_spare_name:number},expectations?:[{group?,metric,axis?,delta:[min,max]}]}],views?:[iso|front|side|top],interfaces?:[...],topology?:[...],domain?:[...]}. Up to 3 targeted cases across this quick review; at most 2 views and 8 images including baseline. Empty tests captures baseline. Without expectations, responsive/unchanged is unverified, not correctness. Every case restores parameters/keys/frame; no new permission is granted by this argument.' },
      allow_raw: ALLOW_RAW_PARAM,
    },
    output: {
      schema: execOutputSchema,
      render: (_args, value) => renderExec(value),
      presentationMeta: (_args, value) => execPresentationMeta(value),
    },
    presentCall: (args) => !args.code && !args.review && !args.review_test ? undefined : ({
      card: 'generic',
      title: args.review ? 'Independent Houdini asset review' : args.review_test ? 'Houdini review experiment' : 'Execute Houdini Python',
      kind: 'edit',
      rawInput: args.review ?? args.review_test ?? codePresentationInput(args as {code:string;allow_raw?:string}),
    }),
    presentResult: (_args, result) => genericResult(resultTitle('Houdini execution', result), result),
    async execute(args, exec) {
      if([args.code,args.review,args.review_test].filter(v=>v!==undefined).length!==1) throw new Error('provide exactly one of code, review, review_test')
      if(args.review!==undefined || args.review_test!==undefined) {
        if(args.allow_raw!==undefined) throw new Error('review cannot be mixed with allow_raw')
        const result=args.review!==undefined
          ? await review.start(args.review,exec,ownershipScopeOf(exec))
          : await review.test(args.review_test,exec,ownershipScopeOf(exec))
        return retainResult(await relayMedia(result,exec,bridge,ctx),workspaceOf(exec))
      }
      await review.guard(exec,false)
      if(typeof args.code!=='string' || !args.code.trim())throw new Error('provide nonempty code')
      const result = await bridge.exec(args.code, exec.signal, args.allow_raw, ownershipScopeOf(exec))
      return retainResult(await withWorkspaceNote(await relayMedia(result, exec, bridge, ctx), exec, bridge), workspaceOf(exec))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'houdini_query',
    description:
      'Run read-only Python inspection code inside Houdini, with `hou` pre-imported. Use it to '
      + 'list nodes, read parameters, check for errors, and inspect scene state. It MUST NOT '
      + 'modify the scene; use houdini_exec for changes. Assign findings to `__result__` or print them. '
      + 'Alternatively read a retained historical result with result_ref (SHA-256), optional JSON pointer, offset and limit; this reads the workspace artifact without executing Houdini.',
    parameters: {
      code: { type: 'string', description: 'Read-only Python; mutually exclusive with result_ref' },
      result_ref: { type: 'string', description: 'SHA-256 returned in result-details; historical evidence, not live scene state' },
      pointer: { type: 'string', description: 'JSON Pointer into retained envelope, e.g. /verbs/0/args or /result; default root' },
      offset: { type: 'number', description: 'Character offset into selected JSON text; default 0' },
      limit: { type: 'number', description: 'Page characters 1..16000; default 6000' },
    },
    output: {
      schema: execOutputSchema,
      render: (_args, value) => renderExec(value),
      presentationMeta: (_args, value) => execPresentationMeta(value),
    },
    presentCall: (args) => ({
      card: 'generic',
      title: args.result_ref ? 'Read retained Houdini result' : 'Inspect Houdini scene',
      kind: 'read',
      rawInput: args.result_ref ? args : codePresentationInput(args as { code:string }),
    }),
    presentResult: (args, result) => genericResult(resultTitle(args.result_ref ? 'Houdini result detail' : 'Houdini inspection', result), result),
    async execute(args, exec) {
      await review.guard(exec,true)
      if ((args.code !== undefined) === (args.result_ref !== undefined)) throw new Error('provide exactly one of code or result_ref')
      if (args.result_ref !== undefined) return readResultDetail(workspaceOf(exec),args.result_ref,args.pointer,args.offset,args.limit)
      if ([args.pointer,args.offset,args.limit].some(v=>v!==undefined)) throw new Error('pointer/offset/limit require result_ref')
      if (typeof args.code !== 'string' || !args.code.trim()) throw new Error('provide nonempty read-only code')
      const result = await bridge.exec(args.code, exec.signal, undefined, ownershipScopeOf(exec), true)
      return retainResult(await withWorkspaceNote(await relayMedia(result, exec, bridge, ctx), exec, bridge), workspaceOf(exec))
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
      await review.guard(exec,false)
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
      return retainResult(await relayMedia(status, exec, bridge, ctx),workspaceOf(exec))
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
      return retainResult(await bridge.cancelJob(args.jobId, exec.signal),workspaceOf(exec))
    },
  }))
}
