/**
 * Houdini tool definitions. Every tool is a thin, typed wrapper over one
 * bridge endpoint; all `hou` semantics live in the Python code the model
 * writes and in the bridge that executes it.
 */
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { ExecResult, HoudiniBridge, JobStatus } from './bridge.js'

/** Canonical value shared by the exec-shaped tools. */
const execOutputSchema = {
  type: 'object',
  properties: {
    ok: { type: 'boolean', required: true },
    stdout: { type: 'string', required: true },
    stderr: { type: 'string', required: true },
    result: { type: 'json' },
    verbs: { type: 'json' },
    error: { type: 'string' },
    advisory: { type: 'string' },
  },
  additionalProperties: false,
} as const

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
  parts.push(...renderVerbs(value))
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
    ok: { type: 'boolean', required: true },
    stdout: { type: 'string', required: true },
    stderr: { type: 'string', required: true },
    result: { type: 'json' },
    verbs: { type: 'json' },
    error: { type: 'string' },
    advisory: { type: 'string' },
  },
  additionalProperties: false,
} as const

/** Register every Houdini tool; disposal of the plugin unregisters them. */
export function registerHoudiniTools(ctx: Context, bridge: HoudiniBridge): void {
  ctx.tools.register(defineTool({
    name: 'houdini_exec',
    description:
      'Execute Python code inside the running Houdini session. The code runs with the `hou` '
      + 'module pre-imported and may modify the scene: create or edit nodes, set parameters, '
      + 'cook, save the hip file. Print what the agent needs to know; assign a JSON-serializable '
      + 'value to the variable `__result__` to return structured data.',
    parameters: {
      code: { type: 'string', required: true, description: 'Python source executed in Houdini with `hou` available' },
    },
    output: { schema: execOutputSchema, render: (_args, value) => renderExec(value) },
    async execute(args, exec) {
      return bridge.exec(args.code, exec.signal)
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
    output: { schema: execOutputSchema, render: (_args, value) => renderExec(value) },
    async execute(args, exec) {
      return bridge.exec(args.code, exec.signal)
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
    },
    output: {
      schema: {
        type: 'object',
        properties: { jobId: { type: 'string', required: true } },
        additionalProperties: false,
      },
      render: (_args, value) => [{ type: 'text' as const, text: `Started Houdini job ${value.jobId}. Collect it with houdini_job_status(jobId, wait=<seconds>).` }],
    },
    async execute(args, exec) {
      return bridge.submitJob(args.code, exec.signal)
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
    },
    async execute(args, exec) {
      return bridge.jobStatus(args.jobId, args.wait, exec.signal)
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
    },
    async execute(args, exec) {
      return bridge.cancelJob(args.jobId, exec.signal)
    },
  }))
}
