/** Public tool registration and argument dispatch. HOM stays in the Bridge. */
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { registerProductTool } from './product-definition.js'
import { executeQuery } from './tool-query.js'
import { HoudiniToolRuntime, type HoudiniConnection } from './tool-runtime.js'
import {
  codePresentationInput, execOutputSchema, execPresentationMeta, genericResult,
  jobHandleMeta, jobPresentationMeta, jobResultTitle, jobStatusOutputSchema,
  renderExec, renderJobHandle, renderJobStatus, resultTitle,
} from './tool-output.js'

const ALLOW_RAW_PARAM = {
  type: 'string',
  description:
    'One-time exemption for LOW-LEVEL MUTATION with no matching verb, ONLY after the default-on '
    + 'raw-hou gate rejects it: re-issue that isolated low-level code with WHY no verb fits. '
    + 'This never exempts verb-covered calls such as createNode/parm.set/cook/destroy; use verbs '
    + 'for those and split them from the low-level batch. Exemptions are recorded in the trace.',
} as const

/** Register public execution tools and the optional product requirements tool. */
export function registerHoudiniTools(ctx: Context, connection: HoudiniConnection): void {
  const runtime = new HoudiniToolRuntime(ctx, connection)
  ctx.tools.register(defineTool({
    name: 'houdini_exec',
    description:
      'Execute Python code inside the running Houdini session. The code runs with the `hou` '
      + 'module pre-imported and may modify the scene: create or edit nodes, set parameters, '
      + 'and cook. One call is one execution checkpoint. '
      + 'When Houdini undo is enabled, a later failure rolls back earlier undoable edits in this same call; inspect transaction/rollback. '
      + 'Use checkpoint={expected_path:...} for an isolated save, or checkpoint={path,expected_current_path,reason,overwrite?} for authorized Save As. Do not combine checkpoint with code/allow_raw. Save an already named HIP with the `scene_save` verb; raw `hou.hipFile.save()` '
      + 'is verb-covered. Print what the agent needs to know; assign a JSON-serializable '
      + 'value to the variable `__result__` to return structured data. Render/screenshot images are returned directly as native image attachments.',
    parameters: {
      code: { type: 'string', description: 'Python source; exactly one of code or checkpoint' },
      checkpoint:{oneOf:[
        {type:'object',additionalProperties:false,properties:{expected_path:{type:'string',required:true}}},
        {type:'object',additionalProperties:false,properties:{path:{type:'string',required:true},expected_current_path:{type:'string',required:true},
          reason:{type:'string',required:true},overwrite:{type:'boolean'}}},
      ],description:'Structured persistence only; no arbitrary code. Same scene_save/scene_save_as path, overwrite and authorization rules.'},
      allow_raw: ALLOW_RAW_PARAM,
    },
    output: {
      schema: execOutputSchema,
      render: (_args, value) => renderExec(value),
      presentationMeta: (_args, value) => execPresentationMeta(value),
    },
    presentCall: (args) => args.checkpoint?({card:'generic',title:'Save Houdini checkpoint',kind:'edit',rawInput:args.checkpoint}):!args.code ? undefined : ({
      card: 'generic',
      title: 'Execute Houdini Python',
      kind: 'edit',
      rawInput: codePresentationInput(args as {code:string;allow_raw?:string}),
    }),
    presentResult: (_args, result) => genericResult(resultTitle('Houdini execution', result), result),
    async execute(args, exec) {
      if((args.code!==undefined)===(args.checkpoint!==undefined)) throw new Error('provide exactly one of code or checkpoint')
      let code = args.code
      if (args.checkpoint !== undefined) {
        if (args.allow_raw !== undefined) throw new Error('checkpoint cannot include allow_raw')
        const save = args.checkpoint
        const existing = Object.hasOwn(save, 'expected_path')
        const required = existing ? ['expected_path'] : ['path', 'expected_current_path', 'reason']
        const allowed = existing ? required : [...required, 'overwrite']
        if (Object.keys(save).some(key => !allowed.includes(key))
          || required.some(key => typeof (save as any)[key] !== 'string' || !(save as any)[key].trim())
          || ('overwrite' in save && typeof save.overwrite !== 'boolean')) throw new Error('invalid structured checkpoint')
        code = `import json\n__dsh_checkpoint = json.loads(${JSON.stringify(JSON.stringify(save))})\n`
          + `__result__ = ${existing ? 'scene_save' : 'scene_save_as'}(**__dsh_checkpoint)`
      } else if (typeof code !== 'string' || !code.trim()) throw new Error('provide nonempty Python code')
      const { bridge, owner } = await runtime.target(exec)
      const result = await bridge.exec(code!, owner, exec.signal, args.allow_raw)
      return runtime.result(result, exec, bridge, true)
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
      + 'After an uncertain exec response, request_ref retrieves its same-runtime execution receipt without resubmitting code. Query capabilities="visual" before image-dependent work to inspect the current model route and native attachment channel without rendering. Exactly one query mode per call.',
    parameters: {
      code: { type: 'string', description: 'Read-only Python; exactly one of code, result_ref, source_ref, request_ref or capabilities' },
      capabilities: {type:'string',enum:['visual'],description:'Host-only current model image-input/channel preflight; no render or HOM. Exclusive query mode.'},
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
      title: args.capabilities ? 'Inspect visual capability' : args.request_ref ? 'Recover Houdini request' : args.source_ref ? 'Read task source' : args.result_ref ? 'Read retained Houdini result' : 'Inspect Houdini scene',
      kind: 'read',
      rawInput: args.capabilities || args.request_ref || args.result_ref || args.source_ref ? args : codePresentationInput(args as { code:string }),
    }),
    presentResult: (args, result) => genericResult(args.request_ref ? 'Houdini request recovery status' : resultTitle(args.source_ref ? 'Task source' : args.result_ref ? 'Houdini result detail' : 'Houdini inspection', result), result),
    execute: (args, exec) => executeQuery(args, exec, runtime, ctx),
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
      render: (_args, value) => renderJobHandle(value),
      presentationMeta: (_args, value) => jobHandleMeta(value),
    },
    presentCall: (args) => ({
      card: 'generic',
      title: 'Start Houdini background job',
      kind: 'execute',
      rawInput: codePresentationInput(args),
    }),
    presentResult: (_args, result) => genericResult(jobResultTitle('Started Houdini job', result), result),
    async execute(args, exec) {
      const { bridge, owner } = await runtime.target(exec)
      return bridge.submitJob(args.code, owner, exec.signal, args.allow_raw)
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
      render: (_args, value) => renderJobStatus(value),
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
      if (typeof args.jobId !== 'string' || !/^[0-9a-f]{12}$/.test(args.jobId))
        throw new Error('jobId must be the 12-character hexadecimal id returned by houdini_job_submit; placeholders are never sent to Houdini')
      const { bridge, owner } = await runtime.target(exec)
      const status = await bridge.jobStatus(args.jobId, owner, args.wait, exec.signal)
      return runtime.result(status, exec, bridge)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'houdini_job_cancel',
    description:
      'Cooperatively cancel a Houdini background job. A job still waiting in the queue is '
      + 'dropped before its code runs (no scene changes); a job already running cannot be '
      + 'killed and will run to completion. Collect the outcome with one houdini_job_status '
      + 'call using wait=<seconds>; do not poll in a loop.',
    parameters: {
      jobId: { type: 'string', required: true, description: 'Job id returned by houdini_job_submit' },
    },
    output: {
      schema: jobStatusOutputSchema,
      render: (_args, value) => renderJobStatus(value),
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
      if (typeof args.jobId !== 'string' || !/^[0-9a-f]{12}$/.test(args.jobId))
        throw new Error('jobId must be the 12-character hexadecimal id returned by houdini_job_submit; placeholders are never sent to Houdini')
      const { bridge, owner } = await runtime.target(exec)
      return runtime.retain(await bridge.cancelJob(args.jobId, owner, exec.signal), exec)
    },
  }))
  registerProductTool(ctx)
}
