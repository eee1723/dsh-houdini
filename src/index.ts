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

export const name = 'dsh-houdini'
export const inject = ['tools', 'systemPrompt', 'skills', 'sessions']

export interface Config {
  /** Base URL of the Houdini-side bridge. */
  bridgeUrl: string
  /** Per-request timeout for bridge calls; job submission returns long before this. */
  requestTimeoutMs: number
  automaticContext?: boolean
  /** Optional physical-product focus; never an execution gate. */
  productMode?: boolean
  /** Explicit target identity for agent-scoped routing; launcher provides the default. */
  executorId?: string
  /** Opt-in candidate shared-Host routing. No automatic target/default migration. */
  executorRegistry?: string
}

export const Config: Schema<Config> = Schema.object({
  bridgeUrl: Schema.string().default('http://127.0.0.1:8765'),
  requestTimeoutMs: Schema.number().default(120000),
  automaticContext: Schema.boolean().default(true),
  productMode: Schema.boolean().default(false),
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
    'Houdini tools address one live scene through its main-thread queue. Use houdini_query for read-only inspection, houdini_exec for edits and checks, and houdini_job_* for long work. Host shell/file tools operate outside live HOM. An uncertain request is recovered by request_ref, never by repeating the edit.',
    '',
    'Compose the injected Python verbs for edits. Raw hou is a read/low-level escape hatch; Raw Gate and runtime node ownership apply. Foreign edits require the user to identify the intended change. Query verb_help for uncertain signatures and node_info for unfamiliar node types. Batch related operations and specify the actual output being checked.',
    '',
    `Current catalog: ${VERB_CATALOG_SUMMARY}`,
    '',
    'Tool results report execution, checks, restoration and files separately. Read failed or unsupported facts and retained result details when needed. Undo covers only its stated scene effects. Images use DSH native attachments; inspect them with the current model and report unavailable visual understanding accurately.',
    '',
    'Load domain skills as needed for SOP, COP, HDA/tools, controls, rigging, Solaris or tutorials. houdini_product is an optional requirement record and measurement view; it grants no scene permissions and never blocks construction.',
    '',
    'Outputs belong under $HIP. Saving to a new path requires the requested target and expected current HIP. Keep persistent render_view services. Open Workspace aligns the task directory; runtime repair and Houdini restart use the documented menu with user authorization.',
  ].join('\n'),
}

export function apply(ctx: Context, config: Config) {
  installExecutorBinding(ctx,config.executorRegistry ? undefined : config.executorId ?? process.env.DSH_HOUDINI_EXECUTOR_ID)
  const connection = config.executorRegistry ? sharedExecutorConnection(ctx,config.executorRegistry)
    : new HoudiniBridge(config.bridgeUrl, config.requestTimeoutMs,
      config.executorId ?? process.env.DSH_HOUDINI_EXECUTOR_ID)
  registerHoudiniTools(ctx, connection)
  registerBundledSkills(ctx)
  ctx.systemPrompt.section(GUIDANCE)
  if(config.productMode) ctx.systemPrompt.section({name:'dsh-houdini:product-mode',order:149,text:
    'Focus on editable product models, useful controls and visible detail. Record complex requirements with houdini_product when helpful, choose the construction method freely, and compare the actual result with the user goal.'})
  if (config.automaticContext !== false) installSceneContext(ctx, connection)
}
