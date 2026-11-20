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
import {desktopPaths} from './desktop-paths.js'

export const name = 'dsh-houdini'
export const inject = ['tools', 'systemPrompt', 'skills', 'sessions', 'houdiniExecutorState']

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
    'Operate on the explicitly selected scene. Use houdini_inspect queries for observations and houdini_exec for edits and checks. Live Houdini uses one main-thread queue and one active author. Other authors can use houdini_isolated with declared inputs. Reinspect the target after switching. Foreign edits require a user-identified target and change.',
    '',
    'Use known verbs directly. Discover unfamiliar signatures with verb_help(name) and available node types with node_info(parent, type_name). Batch related changes and name the output to check. Raw hou is for reads and low-level operations without a matching verb. For task scripts use the script directory returned by scene_info().project_layout when available, pass its actual path to collaborators, and execute through the script argument.',
    '',
    `Current catalog: ${VERB_CATALOG_SUMMARY}`,
    '',
    'Use houdini_job_submit for long live operations. DSH job_output observes the native job. job_kill requests cancellation and suppresses its automatic completion notice. Use job_output(wait=true) to collect the actual outcome. After a timeout, retrieve the original Bridge receipt with houdini_request before deciding whether any work remains. Queued or running operations may still execute. Undo covers only the stated scene effects.',
    '',
    'Use render_view on the explicit output SOP for an offscreen model preview. Use houdini_ui_list and houdini_ui_screenshot for questions about the existing visible interface. houdini_capabilities reports the image channel. Retrieve original live images with houdini_request and archived results or installed SideFX help with houdini_resource.',
  ].join('\n'),
}

export function apply(ctx: Context, config: Config) {
  installHoudiniExecutionLog(ctx)
  const targets=ctx.get('houdiniTargets') as import('./executor-controller.js').ExecutorController|undefined
  const registry=config.executorRegistry||targets?.registry||desktopPaths().registry
  const fixedTarget=config.executorId??process.env.DSH_HOUDINI_EXECUTOR_ID
  // Only an explicit developer URL + identity may mount a fixed test target.
  // A missing/unloaded Desktop service never falls back to an ambient port.
  const explicitFixed=Boolean(config.bridgeUrl&&fixedTarget&&!targets&&!config.executorRegistry)
  if(explicitFixed)installFixedTargetContext(ctx,fixedTarget!)
  const fixedToken=explicitFixed?process.env.DSH_HOUDINI_BRIDGE_TOKEN:undefined
  const connection = explicitFixed ? new HoudiniBridge(config.bridgeUrl!,config.requestTimeoutMs,fixedTarget,undefined,undefined,
    fixedToken?async()=>fixedToken:undefined)
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
