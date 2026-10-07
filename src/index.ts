/**
 * dsh-houdini: lets a DeepSeek Harness agent drive a running Houdini session
 * through the bridge in `houdini/python3.11libs/dsh_bridge.py`.
 */
import type { Context } from '@deepseek-ai/cordis'
import type { PromptSection } from '@deepseek-ai/dsh-system-prompt'
import Schema from '@deepseek-ai/schemastery'
import { HoudiniBridge } from './bridge.js'
import { VERB_CATALOG_SUMMARY } from './generated-verb-contract.js'
import { registerBundledSkills } from './skill.js'
import { registerHoudiniTools } from './tools.js'
import { installSceneContext } from './context.js'
import { sharedExecutorConnection } from './executor-host.js'
import { installExecutorBinding } from './executor-binding.js'
import {installHoudiniExecutionLog} from './dsh-adapter.js'
import {installNodeDeliveryNavigation} from './node-delivery.js'

export const name = 'dsh-houdini'
export const inject = ['tools', 'systemPrompt', 'skills', 'sessions']

export interface Config {
  /** Base URL of the Houdini-side bridge. */
  bridgeUrl: string
  /** Per-request timeout for bridge calls; job submission returns long before this. */
  requestTimeoutMs: number
  automaticContext?: boolean
  /** Explicit target identity for agent-scoped routing; launcher provides the default. */
  executorId?: string
  /** Opt-in candidate shared-Host routing. No automatic target/default migration. */
  executorRegistry?: string
}

export const Config: Schema<Config> = Schema.object({
  bridgeUrl: Schema.string().default('http://127.0.0.1:8765'),
  requestTimeoutMs: Schema.number().default(120000),
  automaticContext: Schema.boolean().default(true),
  executorId: Schema.string(),
  executorRegistry: Schema.string(),
})

/**
 * Stable tool contract only. Persona and domain-specific recipes belong to
 * presets and bundled skills; the catalog summary is generated from the
 * tool-design source of truth so this section cannot silently list stale verbs.
 */
const GUIDANCE: PromptSection = {
  name: 'dsh-houdini:guidance',
  order: 150,
  text: [
    'Houdini tool routing:\nUse houdini_inspect for live read-only scene and API information, houdini_exec for batched operations, houdini_job_* for long work, houdini_ui_screenshot for a named native parameter pane or parent network after normal GUI refresh, houdini_request to retrieve an uncertain original execution, houdini_resource for original task material and retained results, and houdini_capabilities for model image/attachment metadata. Live HOM runs through one main-thread queue.',
    '',
    'Execution boundary and discovery:\nCompose the injected Python verbs for edits. Raw hou is a read/low-level escape hatch; Raw Gate and runtime node ownership apply. Foreign edits require the user to identify the intended change. verb_help(name) reads signatures and brief purpose; detail="full" adds the needed input/output contract and examples. Pass a list as name for related verbs, without rereading unrelated full catalogs. node_info(parent, type_name) reads types available in an existing parent network. Batch related operations and specify the actual output being checked.',
    '',
    `Current catalog: ${VERB_CATALOG_SUMMARY}`,
    '',
    'Result and recovery contract:\nTool results report execution, checks, restoration and files separately. Read failed or unsupported facts and retained result details when needed. Recover uncertain execution by its original request reference before retrying. Undo covers only its stated scene effects. Images use DSH native attachments; image delivery and pixel checks do not establish visual understanding. Report unavailable visual understanding accurately.',
    '',
    'Domain knowledge:\nLoad the applicable skill for SOP, COP, HDA/tools, controls, rigging, Solaris, tutorials or network handoff. Construction and presentation methods belong to those skills; tool contracts do not select a modeling strategy.',
    '',
    'Files and runtime:\nTask outputs anchor under $HIP; reusable tool resources and native Package JSON use the explicitly chosen source and registration locations. Preserve existing resources and conditions. Saving a scene to a new path requires the requested target and expected current HIP. Keep persistent render_view services. Open Workspace aligns the task directory; runtime repair and Houdini restart use the documented menu with user authorization.',
  ].join('\n'),
}

export function apply(ctx: Context, config: Config) {
  installHoudiniExecutionLog(ctx)
  installExecutorBinding(ctx,config.executorRegistry ? undefined : config.executorId ?? process.env.DSH_HOUDINI_EXECUTOR_ID)
  const connection = config.executorRegistry ? sharedExecutorConnection(ctx,config.executorRegistry)
    : new HoudiniBridge(config.bridgeUrl, config.requestTimeoutMs,
      config.executorId ?? process.env.DSH_HOUDINI_EXECUTOR_ID)
  registerHoudiniTools(ctx, connection)
  installNodeDeliveryNavigation(ctx,connection)
  registerBundledSkills(ctx)
  ctx.systemPrompt.section(GUIDANCE)
  if (config.automaticContext !== false) installSceneContext(ctx, connection)
}
