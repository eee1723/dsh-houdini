/**
 * Houdini tool definitions. Every tool is a thin, typed wrapper over one
 * bridge endpoint; all `hou` semantics live in the Python code the model
 * writes and in the bridge that executes it.
 */
import type { Context } from '@deepseek-ai/cordis'
import {
  defineTool,
  type GenericResultView,
  type ToolResult,
} from '@deepseek-ai/dsh-tools'
import type { ExecResult, HoudiniBridge, JobStatus, OwnershipScope, JsonValue } from './bridge.js'
import { readResultDetail, retainResult } from './result-details.js'
import { readTaskSource } from './task-sources.js'
import { attachImages, imageBlocks } from './image-output.js'
import { ExecutorBindingBarrier } from './execution-state.js'

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
  imageAttachments: { type: 'json' },
  checks: { type: 'json' },
  evidence: { type: 'json' },
  execution: { type: 'json' },
  details: { type: 'json' },
  requestReceipt: { type: 'json' },
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
    imageCount: Array.isArray(value.imageAttachments) ? value.imageAttachments.filter((a: any) => a.attachment).length : 0,
    ...(Array.isArray(value.checks) && value.checks.length ? { checksPending: true } : {}),
    ...(value.execution !== undefined || value.details !== undefined || value.requestReceipt !== undefined ? { canonical: value as unknown as JsonValue } : {}),
  }
}

function jobPresentationMeta(value: JobStatus): PresentationMeta {
  return {
    ok: value.ok,
    jobId: value.jobId,
    status: value.status,
    verbCount: Array.isArray(value.verbs) ? value.verbs.length : 0,
    imageCount: Array.isArray(value.imageAttachments) ? value.imageAttachments.filter((a: any) => a.attachment).length : 0,
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
  if (value.requestReceipt !== undefined) parts.push(`request-receipt:\n${JSON.stringify(value.requestReceipt)}`)
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
  if (Array.isArray(value.imageAttachments)) parts.push('image-attachments:\n' + JSON.stringify(value.imageAttachments));
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
  const receipt:any = value.requestReceipt
  if (receipt && receipt.status !== 'done') {
    parts.push(`Request receipt status: ${receipt.status}. This reports request recovery state, not successful scene completion.`)
    if (value.error) parts.push(`Transport detail:\n${value.error}`)
    parts.push(...renderStreams(value))
    return [{ type:'text' as const,text:parts.join('\n\n') }]
  }
  if (value.ok) {
    parts.push(Array.isArray(value.checks) && value.checks.length
      ? 'Operation executed; checks failed or contain warnings/unverified results. Inspect checks before continuing.'
      : 'Executed successfully.')
  } else {
    parts.push(`Execution failed:\n${value.error ?? 'unknown error'}`)
  }
  parts.push(...renderStreams(value))
  return [{ type: 'text' as const, text: parts.join('\n\n') }, ...imageBlocks(value)]
}

/** Normalize a Windows-ish path for comparison (case, slashes, trailing sep). */
function normPath(p: string): string {
  return p.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
}

/** Session workspace (the dsh sandbox root for filesystem tools), when known. */
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

/** Advice is a projection of this result, never another scene query after an edit. */
const workspaceNotes = new WeakMap<object, string>()

function withWorkspaceNote<T extends ExecResult>(value: T, execInput: unknown): T {
  const cwd = workspaceOf(execInput)
  const agent = (execInput as { agent?: object }).agent
  const hip = asPresentationMeta(value.execution)?.hip_dir
  if (!cwd || !agent || typeof hip !== 'string' || !hip) return value
  if (normPath(hip) === normPath(cwd)) {
    workspaceNotes.delete(agent)
    return value
  }
  const key = `${normPath(cwd)}|${normPath(hip)}`
  if (workspaceNotes.get(agent) === key) return value
  workspaceNotes.set(agent, key)
  const note = [
    `workspace note: this session's workspace is "${cwd}"; this operation observed $HIP at "${hip}".`,
    'Anchor all Houdini outputs at $HIP. Render/screenshot images arrive as native image attachments;',
    'use DSH-Houdini > Open Workspace to select the current HIP workspace for other file tools.',
    'Do not write task outputs into the plugin repository.',
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
  return [{ type: 'text' as const, text: parts.join('\n\n') }, ...imageBlocks(value)]
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
export function registerHoudiniTools(ctx: Context, connection: HoudiniBridge | {resolve(exec:any):Promise<HoudiniBridge>}): void {
  const resolveBridge = (exec:any):Promise<HoudiniBridge> => 'resolve' in connection ? connection.resolve(exec) : Promise.resolve(connection)
  const binding = new ExecutorBindingBarrier(async session => {
    if (!ctx.sessions?.flush) throw new Error('DSH session durability service unavailable; no live request sent')
    return ctx.sessions.flush(session as Parameters<typeof ctx.sessions.flush>[0])
  })
  async function requireTaskTarget(exec: any, bridge:HoudiniBridge): Promise<void> {
    const session = exec.agent?.session
    if (!session?.snapshotEvents) {
      if (bridge.targetExecutorId) throw new Error('Bound Houdini operations require a durable agent session')
      return
    }
    await binding.ensure(session,bridge.targetExecutorId,exec.signal,false)
  }
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
      + 'value to the variable `__result__` to return structured data. Render/screenshot images are returned directly as native image attachments.',
    parameters: {
      code: { type: 'string', required: true, description: 'Python source to execute' },
      allow_raw: ALLOW_RAW_PARAM,
    },
    output: {
      schema: execOutputSchema,
      render: (_args, value) => renderExec(value),
      presentationMeta: (_args, value) => execPresentationMeta(value),
    },
    presentCall: (args) => !args.code ? undefined : ({
      card: 'generic',
      title: 'Execute Houdini Python',
      kind: 'edit',
      rawInput: codePresentationInput(args as {code:string;allow_raw?:string}),
    }),
    presentResult: (_args, result) => genericResult(resultTitle('Houdini execution', result), result),
    async execute(args, exec) {
      if (typeof args.code !== 'string' || !args.code.trim()) throw new Error('provide nonempty Python code')
      const bridge = await resolveBridge(exec)
      await requireTaskTarget(exec,bridge)
      const result = await bridge.exec(args.code, exec.signal, args.allow_raw, ownershipScopeOf(exec))
      return retainResult(withWorkspaceNote(await attachImages(result, exec, bridge, ctx), exec), workspaceOf(exec))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'houdini_query',
    description:
      'Run read-only Python inspection code inside Houdini, with `hou` pre-imported. Use it to '
      + 'list nodes, read parameters, check for errors, and inspect scene state. It MUST NOT '
      + 'modify the scene; use houdini_exec for changes. Assign findings to `__result__` or print them. '
      + 'Alternatively read a retained historical result with result_ref (SHA-256), optional JSON pointer, offset and limit; this reads the workspace artifact without executing Houdini. '
      + 'Read original current-session task material with source_ref="index" or a source hash, offset and limit; no Houdini execution. Questions/plans are not user requirements or permission. '
      + 'After an uncertain exec response, request_ref retrieves its same-runtime execution receipt without resubmitting code. Exactly one query mode per call.',
    parameters: {
      code: { type: 'string', description: 'Read-only Python; exactly one of code, result_ref, source_ref or request_ref' },
      source_ref: { type: 'string', description: 'index lists current-session task sources; a listed SHA-256 reads original text with provenance. Nontext blocks are markers, not interpreted references.' },
      request_ref: { type: 'string', description: 'Exec/job receipt after uncertain response; index lists active then recent current-session references if Host discarded the response. No HOM or resubmission; match original owner_call, missing is unknown.' },
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
      title: args.request_ref ? 'Recover Houdini request' : args.source_ref ? 'Read task source' : args.result_ref ? 'Read retained Houdini result' : 'Inspect Houdini scene',
      kind: 'read',
      rawInput: args.request_ref || args.result_ref || args.source_ref ? args : codePresentationInput(args as { code:string }),
    }),
    presentResult: (args, result) => genericResult(args.request_ref ? 'Houdini request recovery status' : resultTitle(args.source_ref ? 'Task source' : args.result_ref ? 'Houdini result detail' : 'Houdini inspection', result), result),
    async execute(args, exec) {
      if ([args.code,args.result_ref,args.source_ref,args.request_ref].filter(v=>v!==undefined).length !== 1) throw new Error('provide exactly one of code, result_ref, source_ref or request_ref. For original user material use source_ref="index" then a listed source hash; for stored tool output use the SHA-256 from result-details as result_ref; for uncertain execution use request_ref. These references are not interchangeable; query them separately.')
      if (args.request_ref !== undefined) {
        if ([args.pointer,args.offset,args.limit].some(v=>v!==undefined)) throw new Error('request_ref does not accept pagination or pointer')
        const owner=ownershipScopeOf(exec)
        if (!owner) throw new Error('request_ref requires current Host session identity')
        const bridge = await resolveBridge(exec)
        const receipt=await bridge.requestStatus(args.request_ref,owner,exec.signal)
        const r:any=receipt.requestReceipt
        if (r?.jobId) return {ok:true,stdout:'',stderr:'',result:{jobId:r.jobId},
          requestReceipt:{request_ref:r.request_ref,runtime_id:r.runtime_id,owner_call:r.owner_call ?? null,status:'job_submitted',jobId:r.jobId,
            retrieved:true,note:'Original job admission recovered, not completed execution. Collect houdini_job_status(jobId).'}}
        if (r?.status==='done' && r.result) {
          if (r.result.jobId) return {ok:true,stdout:'',stderr:'',result:{jobId:r.result.jobId},
            requestReceipt:{request_ref:r.request_ref,runtime_id:r.runtime_id,owner_call:r.owner_call ?? null,status:'job_submitted',jobId:r.result.jobId,
              retrieved:true,note:'Original job admission recovered, not completed execution. Collect houdini_job_status(jobId).'}}
          return retainResult(await attachImages({...r.result,requestReceipt:{request_ref:r.request_ref,runtime_id:r.runtime_id,owner_call:r.owner_call ?? null,status:'done',retrieved:true}},exec,bridge,ctx),workspaceOf(exec))
        }
        return receipt
      }
      if (args.source_ref !== undefined) {
        if (args.pointer !== undefined) throw new Error('pointer requires result_ref; task sources use offset/limit')
        if (!exec.agent) throw new Error('task sources require a current agent session')
        const session = exec.agent.session as unknown as { snapshotEvents(): Array<{type:string;seq?:number;data?:any}> }
        return readTaskSource(session.snapshotEvents(),args.source_ref,args.offset,args.limit)
      }
      if (args.result_ref !== undefined) return readResultDetail(workspaceOf(exec),args.result_ref,args.pointer,args.offset,args.limit)
      if ([args.pointer,args.offset,args.limit].some(v=>v!==undefined)) throw new Error('pointer/offset/limit require result_ref')
      if (typeof args.code !== 'string' || !args.code.trim()) throw new Error('provide nonempty read-only code')
      const bridge = await resolveBridge(exec)
      await requireTaskTarget(exec,bridge)
      const result = await bridge.exec(args.code, exec.signal, undefined, ownershipScopeOf(exec), true)
      return retainResult(withWorkspaceNote(await attachImages(result, exec, bridge, ctx), exec), workspaceOf(exec))
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
        properties: { jobId: { type: 'string' }, requestReceipt: {type:'json'}, error: {type:'string'} },
        additionalProperties: false,
      },
      render: (_args, value) => [{ type: 'text' as const, text: value.jobId
        ? `Started Houdini job ${value.jobId}. Collect it with houdini_job_status(jobId, wait=<seconds>).` + (value.requestReceipt ? `\n\nrequest-receipt:\n${JSON.stringify(value.requestReceipt)}` : '')
        : `Job admission uncertain; do not resubmit.\n${value.error || ''}\n\nrequest-receipt:\n${JSON.stringify(value.requestReceipt)}` }],
      presentationMeta: (_args, value) => ({ ...(value.jobId ? {jobId:value.jobId}:{}),
        ...(value.requestReceipt ? {canonical:{...value,ok:!!value.jobId,stdout:'',stderr:''} as unknown as JsonValue}: {}) }),
    },
    presentCall: (args) => ({
      card: 'generic',
      title: 'Start Houdini background job',
      kind: 'execute',
      rawInput: codePresentationInput(args),
    }),
    presentResult: (_args, result) => genericResult(jobResultTitle('Started Houdini job', result), result),
    async execute(args, exec) {
      const bridge = await resolveBridge(exec)
      await requireTaskTarget(exec,bridge)
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
        return [{ type: 'text' as const, text: `job ${value.jobId}: ${value.status}` }, ...renderJobStatus(value)]
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
      const bridge = await resolveBridge(exec)
      await requireTaskTarget(exec,bridge)
      const status = await bridge.jobStatus(args.jobId, args.wait, exec.signal)
      return retainResult(await attachImages(status, exec, bridge, ctx),workspaceOf(exec))
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
        return [{ type: 'text' as const, text: `job ${value.jobId}: ${value.status}` }, ...renderJobStatus(value)]
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
      const bridge = await resolveBridge(exec)
      await requireTaskTarget(exec,bridge)
      return retainResult(await bridge.cancelJob(args.jobId, exec.signal),workspaceOf(exec))
    },
  }))
}
