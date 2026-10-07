/** Public tool registration and argument dispatch. HOM stays in the Bridge. */
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { readResource,recoverRequest } from './tool-query.js'
import { visualCapability } from './image-output.js'
import { HOUDINI_TOOLS } from './tool-catalog.js'
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

/** One public tool per execution, observation, recovery or resource responsibility. */
export function registerHoudiniTools(ctx: Context, connection: HoudiniConnection): void {
  const runtime = new HoudiniToolRuntime(ctx, connection)
  ctx.tools.register(defineTool({
    name: 'houdini_exec',
    description: HOUDINI_TOOLS.houdini_exec.purpose+' Compose injected Python verbs; use __result__ for structured output. Inspect transaction/restoration after failure. Images arrive as native attachments.',
    parameters: {
      code: {type:'string',required:true,description:'Python batch, with hou and verbs available. Assign __result__ or print observations.'},
      allow_raw: ALLOW_RAW_PARAM,
    },
    output: {
      schema: execOutputSchema,
      render: (_args, value) => renderExec(value),
      presentationMeta: (_args, value) => execPresentationMeta(value),
    },
    presentCall: args=>({card:'generic',title:HOUDINI_TOOLS.houdini_exec.label,kind:'edit',rawInput:codePresentationInput(args)}),
    presentResult: (_args,result)=>genericResult(resultTitle(HOUDINI_TOOLS.houdini_exec.label,result),result),
    async execute(args,exec) {
      if(!args.code?.trim()) throw Error('Provide nonempty Python code')
      const {bridge,owner}=await runtime.target(exec)
      return runtime.result(await bridge.exec(args.code,owner,exec.signal,args.allow_raw),exec,bridge,true)
    },
  }))

  const readOutput={schema:execOutputSchema,render:(_args:unknown,value:any)=>renderExec(value),
    presentationMeta:(_args:unknown,value:any)=>execPresentationMeta(value)}
  ctx.tools.register(defineTool({
    name:'houdini_inspect',description:HOUDINI_TOOLS.houdini_inspect.purpose+' Run read-only Python, with hou and verbs available. Assign __result__ or print. Use exec for edits and control experiments.',
    parameters:{code:{type:'string',required:true,description:'Read-only Python code.'}},output:readOutput,
    presentCall:args=>({card:'generic',title:HOUDINI_TOOLS.houdini_inspect.label,kind:'read',rawInput:args.code}),
    presentResult:(_args,result)=>genericResult(resultTitle(HOUDINI_TOOLS.houdini_inspect.label,result),result),
    async execute(args,exec) {
      if(!args.code?.trim()) throw Error('Provide nonempty read-only Python code')
      const {bridge,owner}=await runtime.target(exec)
      return runtime.result(await bridge.exec(args.code,owner,exec.signal,undefined,true),exec,bridge,true)
    },
  }))
  ctx.tools.register(defineTool({
    name:'houdini_request',description:HOUDINI_TOOLS.houdini_request.purpose+' Receipt recovery reads the original execution; never resubmits code. Missing receipts mean unknown, not proof of no execution.',
    parameters:{request_ref:{type:'string',required:true,description:'Original request_ref, or index for current-session recent references.'}},output:readOutput,
    presentCall:args=>({card:'generic',title:HOUDINI_TOOLS.houdini_request.label,kind:'read',rawInput:args}),
    presentResult:(_args,result)=>genericResult(resultTitle(HOUDINI_TOOLS.houdini_request.label,result),result),
    execute:(args,exec)=>recoverRequest(args.request_ref,exec,runtime),
  }))
  ctx.tools.register(defineTool({
    name:'houdini_resource',description:HOUDINI_TOOLS.houdini_resource.purpose+' Host-only pagination; does not execute Houdini. Source originals and past results are historical material.',
    parameters:{kind:{type:'string',enum:['source','result'],required:true},ref:{type:'string',required:true,description:'source: index or listed hash; result: SHA-256 from details.'},
      pointer:{type:'string',description:'Result JSON Pointer, default root. Not used for sources.'},
      offset:{type:'number',description:'Character offset, default 0.'},limit:{type:'number',description:'Page characters 1..16000, default 6000.'}},output:readOutput,
    presentCall:args=>({card:'generic',title:args.kind==='source'?'读取任务资料':'读取完整操作结果',kind:'read',rawInput:args}),
    presentResult:(_args,result)=>genericResult(resultTitle(HOUDINI_TOOLS.houdini_resource.label,result),result),
    execute:async(args,exec)=>readResource(args,exec),
  }))
  ctx.tools.register(defineTool({
    name:'houdini_capabilities',description:HOUDINI_TOOLS.houdini_capabilities.purpose,
    parameters:{},output:readOutput,
    presentCall:()=>({card:'generic',title:HOUDINI_TOOLS.houdini_capabilities.label,kind:'read'}),
    presentResult:(_args,result)=>genericResult(resultTitle(HOUDINI_TOOLS.houdini_capabilities.label,result),result),
    execute:async(_args,exec)=>({ok:true,stdout:'',stderr:'',result:await visualCapability(exec,ctx)}),
  }))

  ctx.tools.register(defineTool({
    name:'houdini_ui_list',
    description:HOUDINI_TOOLS.houdini_ui_list.purpose+' Returns current runtime target references. Does not show, activate, resize or switch UI. Use returned supported targets with houdini_ui_screenshot.',
    parameters:{},output:readOutput,
    presentCall:()=>({card:'generic',title:HOUDINI_TOOLS.houdini_ui_list.label,kind:'read'}),
    presentResult:(_args,result)=>genericResult(resultTitle(HOUDINI_TOOLS.houdini_ui_list.label,result),result),
    async execute(_args,exec) {
      const {bridge,owner}=await runtime.target(exec)
      return runtime.result(await bridge.listUi(owner,exec.signal),exec,bridge,true)
    },
  }))

  ctx.tools.register(defineTool({
    name:'houdini_ui_screenshot',
    description:HOUDINI_TOOLS.houdini_ui_screenshot.purpose+' Use the exact target returned by houdini_ui_list. Captures its currently displayed contents without opening, navigating or resizing UI. Native attachment transport is not semantic visual verification.',
    parameters:{
      target:{type:'string',required:true,description:'Exact target reference returned by houdini_ui_list in this runtime.'},
      path:{type:'string',description:'Safe PNG basename for managed/delivery, or absolute temporary path for explicit.'},
      output_policy:{type:'string',enum:['managed','delivery','explicit'],description:'Default managed observation; explicit can capture an unnamed scene without Save As.'},
    },output:readOutput,
    presentCall:args=>({card:'generic',title:HOUDINI_TOOLS.houdini_ui_screenshot.label,kind:'read',rawInput:args}),
    presentResult:(_args,result)=>genericResult(resultTitle(HOUDINI_TOOLS.houdini_ui_screenshot.label,result),result),
    async execute(args,exec) {
      if(!args.target?.trim())throw Error('Provide the exact UI target reference returned by houdini_ui_list')
      const {bridge,owner}=await runtime.target(exec)
      return runtime.result(await bridge.captureUi(args,owner,exec.signal),exec,bridge,true)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'houdini_job_submit',
    description: HOUDINI_TOOLS.houdini_job_submit.purpose,
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
      title: HOUDINI_TOOLS.houdini_job_submit.label,
      kind: 'execute',
      rawInput: codePresentationInput(args),
    }),
    presentResult: (_args, result) => genericResult(jobResultTitle(HOUDINI_TOOLS.houdini_job_submit.label, result), result),
    async execute(args, exec) {
      const { bridge, owner } = await runtime.target(exec)
      return bridge.submitJob(args.code, owner, exec.signal, args.allow_raw)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'houdini_job_status',
    description: HOUDINI_TOOLS.houdini_job_status.purpose,
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
      title: `${HOUDINI_TOOLS.houdini_job_status.label} · ${args.jobId}`,
      kind: 'read',
      rawInput: args.wait === undefined ? args.jobId : { jobId: args.jobId, wait: args.wait },
    }),
    presentResult: (_args, result) => genericResult(jobResultTitle(HOUDINI_TOOLS.houdini_job_status.label, result), result),
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
    description: HOUDINI_TOOLS.houdini_job_cancel.purpose,
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
      title: `${HOUDINI_TOOLS.houdini_job_cancel.label} · ${args.jobId}`,
      kind: 'execute',
      rawInput: args.jobId,
    }),
    presentResult: (_args, result) => genericResult(jobResultTitle(HOUDINI_TOOLS.houdini_job_cancel.label, result), result),
    async execute(args, exec) {
      if (typeof args.jobId !== 'string' || !/^[0-9a-f]{12}$/.test(args.jobId))
        throw new Error('jobId must be the 12-character hexadecimal id returned by houdini_job_submit; placeholders are never sent to Houdini')
      const { bridge, owner } = await runtime.target(exec)
      return runtime.retain(await bridge.cancelJob(args.jobId, owner, exec.signal), exec)
    },
  }))
}
