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
import { installFixedTargetContext } from './executor-binding.js'
import {installSceneRecovery} from './scene-recovery.js'
import {installHoudiniExecutionLog} from './dsh-adapter.js'
import {installNodeDeliveryNavigation} from './node-delivery.js'
import {registerImageTools} from './image-generation.js'
import {registerVideoTools} from './video-transcription.js'
import {registerIsolatedTool} from './isolated-execution.js'
import {registerExecutorIdentityProjection} from './executor-identity-projection.js'
import {desktopPaths} from './desktop-paths.js'

export const name = 'dsh-houdini'
export const inject = ['tools', 'systemPrompt', 'skills', 'sessions', 'sessionProjections']

export interface Config {
  /** Base URL of the Houdini-side bridge. */
  bridgeUrl?: string
  /** Per-request timeout for bridge calls; job submission returns long before this. */
  requestTimeoutMs: number
  automaticContext?: boolean
  /** Explicit target identity for agent-scoped routing; launcher provides the default. */
  executorId?: string
  /** Opt-in candidate shared-Host routing. No automatic target/default migration. */
  executorRegistry?: string
}

export const Config: Schema<Config> = Schema.object({
  bridgeUrl: Schema.string(),
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
    'Houdini tool routing:\nUse houdini_inspect for read-only scene/API queries, houdini_exec for batched edits and checks, and houdini_job_submit for long work tracked by DSH jobs. Use job_output/job_kill for those native jobs. Use houdini_request for the original execution, job result or interrupted observation, houdini_resource for retained material, and houdini_capabilities for image-channel metadata. Use houdini_ui_list, then houdini_ui_screenshot with an exact returned target. Live HOM uses one main-thread queue. The explicitly selected scene is the operation target; inspect it after a target change. Selecting a scene grants neither node ownership nor permission to replay earlier work.',
    '',
    'Execution and discovery:\nEdit by composing injected Python verbs through exec/job code or a file script; never hide source in exec/eval loaders. Read verb_help(name) for signatures, with detail="full" and a list of related names for input/output contracts and examples. Use node_info(parent, type_name) for types available in that parent. Batch related operations and name the actual output to check. Raw hou is a read/low-level escape hatch; Raw Gate and runtime ownership apply. Foreign edits require the user to identify the intended change. Use DSH file tools for source files and persistent render services for repeated render_view work.',
    '',
    `Current catalog: ${VERB_CATALOG_SUMMARY}`,
    '',
    'Results and recovery:\nExecution, checks, restoration and files are separate facts; unsupported or unobserved properties remain unverified. Read failed facts and retained details before deciding the next action. HTTP timeout neither cancels native work nor proves a crash. Recover an uncertain original request before retrying; houdini_request reads receipts without the HOM queue, while scene/UI queries share that queue. Undo covers only stated scene effects. Native image attachments and pixel checks do not establish visual understanding.',
    '',
    'Domain knowledge and independent work:\nLoad the applicable skill for SOP, COP, HDA/tools, controls, rigging, Solaris, tutorials or network handoff. DSH owns planning, teammates, files and jobs. The selected live scene has one active author; Team scopes and disjoint paths do not grant another session write access. For independent builders or saved-HIP computation, load houdini-isolated-execution and use houdini_isolated; the live author integrates and observes consumers. Independent success is scoped to its inputs and checks, not later edits or overall quality. Use actual HIP paths and returned artifacts; scene_info().project_layout discovers project directory roles. Do not migrate or clean directories implicitly.',
  ].join('\n'),
}

export function apply(ctx: Context, config: Config) {
  registerExecutorIdentityProjection(ctx)
  installHoudiniExecutionLog(ctx)
  const targets=ctx.get('houdiniTargets') as import('./executor-controller.js').ExecutorController|undefined
  const registry=config.executorRegistry||targets?.registry||desktopPaths().registry
  const fixedTarget=config.executorId??process.env.DSH_HOUDINI_EXECUTOR_ID
  // Only an explicit developer URL + identity may mount a fixed test target.
  // A missing/unloaded Desktop service never falls back to an ambient port.
  const explicitFixed=Boolean(config.bridgeUrl&&fixedTarget&&!targets&&!config.executorRegistry)
  if(explicitFixed)installFixedTargetContext(ctx,fixedTarget!)
  const connection = explicitFixed ? new HoudiniBridge(config.bridgeUrl!,config.requestTimeoutMs,fixedTarget)
    : sharedExecutorConnection(ctx,registry)
  installSceneRecovery(ctx,connection)
  registerHoudiniTools(ctx, connection)
  registerImageTools(ctx,connection)
  registerVideoTools(ctx,connection)
  registerIsolatedTool(ctx,connection)
  installNodeDeliveryNavigation(ctx,connection)
  registerBundledSkills(ctx)
  ctx.systemPrompt.section(GUIDANCE)
  if (config.automaticContext !== false) installSceneContext(ctx, connection)
}
