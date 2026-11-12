/** Public tool registration and argument dispatch. HOM stays in the Bridge. */
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { readResource,recoverRequest } from './tool-query.js'
import { visualCapability } from './image-output.js'
import { HOUDINI_TOOLS } from './tool-catalog.js'
import { HoudiniToolRuntime, type HoudiniConnection } from './tool-runtime.js'
import {resolveExecutionSource} from './execution-source.js'
import {LiveJobs} from './live-jobs.js'
import {readHoudiniHelp} from './houdini-help.js'
import {MAX_MODEL_TEXT_BYTES} from './result-policy.js'
import {
  codePresentationInput, execOutputSchema, execPresentationMeta, genericResult,
  jobHandleMeta, jobResultTitle,
  renderExec, renderJobHandle, resultTitle,
} from './tool-output.js'

const ALLOW_RAW_PARAM = {
  type: 'string',
  description:
    'One-time exemption for LOW-LEVEL MUTATION with no matching verb, ONLY after the default-on '
    + 'raw-hou gate rejects it: re-issue that isolated low-level code with WHY no verb fits. '
    + 'This never exempts verb-covered calls such as createNode/parm.set/cook/destroy; use verbs '
    + 'for those and split them from the low-level batch. Exemptions are recorded in the trace.',
} as const

const MODEL_PRESENTATION_PARAM = {
  type:'string',enum:['full','compact'],
  description:'Model-facing text only; default full. compact bounds an archived result to 16 KiB and keeps detail pointers for selective reads. It does not change execution or canonical facts. Unarchived and unfamiliar results stay full.',
} as const

const EXECUTION_PARAMS = {
  code: {type:'string',description:'Python batch with hou and verbs. With script, optional invocation after its definitions (for example __result__ = build(parent)); otherwise the complete batch.'},
  script: {type:'string',description:'Absolute UTF-8 .py builder path. Host reads its actual source once through the current file policy; use this instead of exec(open(...).read()). This grants no extra mutation permission and does not replay, update or replace existing nodes automatically.'},
  expected_sha256: {type:'string',description:'Optional SHA-256 of the tested script bytes; requires script. A changed file fails before selecting or restoring the target scene.'},
  allow_raw: ALLOW_RAW_PARAM,
} as const

/** One public tool per execution, observation, recovery or resource responsibility. */
export function registerHoudiniTools(ctx: Context, connection: HoudiniConnection): void {
  const runtime = new HoudiniToolRuntime(ctx, connection)
  const liveJobs = new LiveJobs(ctx,runtime)
  ctx.tools.register(defineTool({
    name: 'houdini_exec',
    description: HOUDINI_TOOLS.houdini_exec.purpose+' Compose injected Python verbs; use __result__ for structured output. Inspect transaction/restoration after failure. Images arrive as native attachments.',
    parameters: {...EXECUTION_PARAMS,presentation:MODEL_PRESENTATION_PARAM},
    output: {
      schema: execOutputSchema,
      render: (args, value) => renderExec(value,args.presentation==='compact'
        &&value.details&&typeof value.details==='object'&&!Array.isArray(value.details)&&value.details.stored===true?MAX_MODEL_TEXT_BYTES:undefined),
      presentationMeta: (_args, value) => execPresentationMeta(value),
    },
    presentCall: args=>({card:'generic',title:HOUDINI_TOOLS.houdini_exec.label,kind:'edit',rawInput:codePresentationInput(args)}),
    presentResult: (_args,result)=>genericResult(resultTitle(HOUDINI_TOOLS.houdini_exec.label,result),result),
    async execute(args,exec) {
      const source=await resolveExecutionSource(ctx,exec,args)
      const {bridge,owner}=await runtime.target(exec,'write')
      return runtime.result(await bridge.exec(source.code,owner,exec.signal,args.allow_raw,false,source.script),exec,bridge,true)
    },
  }))

  const readOutput={schema:execOutputSchema,render:(args:any,value:any)=>renderExec(value,args.presentation==='compact'&&value.details?.stored===true?MAX_MODEL_TEXT_BYTES:undefined),
    presentationMeta:(_args:unknown,value:any)=>execPresentationMeta(value)}
  ctx.tools.register(defineTool({
    name:'houdini_inspect',description:HOUDINI_TOOLS.houdini_inspect.purpose+' Prefer data-only queries for common observations. Use either queries or code. Python is for observation only; known writes are refused and arbitrary effects are not verified. Use exec for edits and control experiments.',
    parameters:{
      queries:{type:'array',description:'1..16 data-only observations in order. Each row is independent; any read-only verb (query-capable with no scene effect) is accepted, e.g. scene_info, node_info, read_parms, node_provenance, graph, parameter_ui, geo_piece_stats, visible_objects, tool_catalog, usd_prim_info, verb_help, or selection.',
        items:{type:'object',additionalProperties:false,properties:{
          verb:{type:'string',required:true},id:{type:'string',description:'Optional label echoed in the result row.'},
          args:{type:'array',description:'Positional JSON arguments from the verb signature.'},
          kwargs:{type:'object',additionalProperties:true,description:'Named JSON arguments from the verb signature.'}
        }}},
      code:{type:'string',description:'Legacy Python observation code. Assign __result__ or print; code does not certify a read-only effect.'},
      presentation:MODEL_PRESENTATION_PARAM,
    },output:readOutput,
    presentCall:args=>({card:'generic',title:HOUDINI_TOOLS.houdini_inspect.label,kind:'read',rawInput:args.queries??args.code}),
    presentResult:(_args,result)=>genericResult(resultTitle(HOUDINI_TOOLS.houdini_inspect.label,result),result),
    async execute(args,exec) {
      if((args.code===undefined)===(args.queries===undefined))throw Error('Provide exactly one of code or queries')
      if(args.queries!==undefined&&(!args.queries.length||args.queries.length>16))throw Error('Provide 1..16 structured Houdini queries')
      if(args.code!==undefined&&!args.code.trim())throw Error('Provide nonempty Python observation code')
      const {bridge,owner}=await runtime.target(exec)
      const result=args.queries!==undefined
        ?await bridge.inspectQueries(args.queries,owner,exec.signal)
        :await bridge.exec(args.code!,owner,exec.signal,undefined,true)
      return runtime.result(result,exec,bridge,true)
    },
  }))
  ctx.tools.register(defineTool({
    name:'houdini_request',description:HOUDINI_TOOLS.houdini_request.purpose+' Receipt recovery reads the original execution; never resubmits code. Missing receipts mean unknown, not proof of no execution.',
    parameters:{request_ref:{type:'string',required:true,description:'Original request_ref, or index for current-session recent references.'}},output:readOutput,
    presentCall:args=>({card:'generic',title:HOUDINI_TOOLS.houdini_request.label,kind:'read',rawInput:args}),
    presentResult:(_args,result)=>genericResult(resultTitle(HOUDINI_TOOLS.houdini_request.label,result),result),
    execute:(args,exec)=>recoverRequest(args.request_ref,exec,runtime,liveJobs),
  }))
  ctx.tools.register(defineTool({
    name:'houdini_resource',description:HOUDINI_TOOLS.houdini_resource.purpose+' Host-only pagination; does not execute Houdini. Source originals and past results are historical material. Help reads one exact installed SideFX page without HOM, web search or temporary nodes.',
    parameters:{kind:{type:'string',enum:['source','result','help'],required:true},ref:{type:'string',required:true,description:'source: index or listed hash; result: SHA-256 from details; help: exact installed page such as hom/hou/Node, vex/functions/noise or nodes/sop/box.'},
      pointer:{type:'string',description:'Result JSON Pointer, default root. Not used for sources.'},
      select:{type:'array',items:{type:'string'},description:'Read 1..16 named result fields together as exact JSON values, e.g. ["/result/summary","/error"]. An empty array means no field selection: the default root page is returned. Missing/oversized fields are explicit; page oversized fields with pointer. Exclusive with pointer/offset; result only.'},
      offset:{type:'number',description:'Character offset, default 0; help uses Unicode code points.'},limit:{type:'number',description:'Page characters 1..16000, default 6000.'},
      houdini_installation:{type:'string',description:'Help only: exact HFS directory from the official installation inventory. Otherwise use the selected scene installation, or the sole installed version. Multiple unselected installations are reported, never guessed.'},
      expected_sha256:{type:'string',description:'Help only: original page SHA-256 from the preceding response. next supplies this value so a changed page cannot be silently joined to old text.'}},output:readOutput,
    presentCall:args=>({card:'generic',title:args.kind==='source'?'读取任务资料':args.kind==='help'?'读取 Houdini 官方帮助':'读取完整操作结果',kind:'read',rawInput:args}),
    presentResult:(_args,result)=>genericResult(resultTitle(HOUDINI_TOOLS.houdini_resource.label,result),result),
    execute:async(args,exec)=>{
      // Models commonly echo optional string parameters as empty strings; an
      // empty value carries no request and must not fail an otherwise valid read.
      const installation=typeof args.houdini_installation==='string'&&args.houdini_installation.trim()!==''?args.houdini_installation:undefined
      const expected=typeof args.expected_sha256==='string'&&args.expected_sha256.trim()!==''?args.expected_sha256:undefined
      const select=Array.isArray(args.select)&&args.select.length>0?args.select:undefined
      if(args.kind==='help') {
        if(args.pointer!==undefined||select!==undefined)throw Error('pointer/select are only used for result resources')
        return readHoudiniHelp(ctx,connection,{ref:args.ref,offset:args.offset,limit:args.limit,
          houdini_installation:installation,expected_sha256:expected},exec)
      }
      if(installation!==undefined||expected!==undefined)throw Error('houdini_installation/expected_sha256 are only used for help resources')
      return readResource({...args,kind:args.kind as 'source'|'result',select},exec)
    },
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
    parameters: EXECUTION_PARAMS,
    output: {
      schema: {
        type: 'object',
        properties: { job_id: {type:'string',required:true}, jobId: { type: 'string' }, requestReceipt: {type:'json'}, error: {type:'string'} },
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
      const source=await resolveExecutionSource(ctx,exec,args)
      const { bridge, owner } = await runtime.target(exec,'write')
      return liveJobs.submit(source,exec,bridge,owner,args.allow_raw)
    },
  }))

}
