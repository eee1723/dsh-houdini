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
    'Houdini tool routing:\nUse houdini_inspect for live read-only scene and API information, houdini_exec for batched operations, houdini_job_* for long work, houdini_ui_list to discover visible native/Qt surfaces and houdini_ui_screenshot to observe an exact returned target. Opening nodes or changing UI layout is a separate explicit interaction. Use houdini_request to retrieve an uncertain original execution, houdini_resource for original task material and retained results, and houdini_capabilities for model image/attachment metadata. Live HOM runs through one main-thread queue. The explicitly selected scene is the current operation target; earlier targets remain history. After a target change, inspect the actual scene before relying on prior node paths. Selecting a scene does not grant ownership or authorize replaying earlier work.',
    '',
    'Execution boundary and discovery:\nCompose the injected Python verbs for edits. Raw hou is a read/low-level escape hatch; Raw Gate and runtime node ownership apply. Foreign edits require the user to identify the intended change. verb_help(name) reads signatures and brief purpose; detail="full" adds the needed input/output contract and examples. Pass a list as name for related verbs, without rereading unrelated full catalogs. node_info(parent, type_name) reads types available in an existing parent network. Batch related operations and specify the actual output being checked.',
    '',
    `Current catalog: ${VERB_CATALOG_SUMMARY}`,
    '',
    'Result and recovery contract:\nTool results report execution, checks, restoration and files separately. Read failed or unsupported facts and retained result details when needed. Recover uncertain execution by its original request reference before retrying. HTTP timeout does not cancel native work or establish a process crash. houdini_request reads receipts without the HOM queue; scene queries and UI discovery/capture share that queue and may wait behind running work. A shell process listing only describes what that shell can observe, not whether the bound Houdini executor has exited. Undo covers only its stated scene effects. Images use DSH native attachments; image delivery and pixel checks do not establish visual understanding. Report unavailable visual understanding accurately.',
    '',
    'Domain knowledge:\nLoad the applicable skill for SOP, COP, HDA/tools, controls, rigging, Solaris, tutorials or network handoff. Construction and presentation methods belong to those skills; tool contracts do not select a modeling strategy.',
    '',
    'Files and runtime:\nProject directory roles come from scene_info().project_layout, anchored to the actual named HIP; the DSH workspace may differ. Use directories.script for construction source and task scripts, with scratch probes in its scratch subdirectory. These share one artifact root with the other project roles; do not scatter new scripts at the project root. Use DSH file tools to write/edit source files, then execute needed Houdini operations through Bridge. Managed image generation selects reference or texture purpose and returns its actual path; explicit destinations keep DSH filesystem semantics and need no Houdini. Use the returned reference_downloaded directory when saving network reference images. Reusable tool resources and native Package JSON keep their chosen locations. Do not migrate or clean directories implicitly. Saving a scene to a new path requires the requested target and expected current HIP. Keep persistent render_view services. New conversations opened from Houdini use its project directory; choosing another scene keeps the existing conversation workspace; runtime repair and Houdini restart use the documented menu with user authorization.',
  ].join('\n'),
}

export function apply(ctx: Context, config: Config) {
  installHoudiniExecutionLog(ctx)
  const fixedTarget=config.executorId??process.env.DSH_HOUDINI_EXECUTOR_ID
  if(!config.executorRegistry&&fixedTarget)installFixedTargetContext(ctx,fixedTarget)
  const connection = config.executorRegistry ? sharedExecutorConnection(ctx,config.executorRegistry)
    : new HoudiniBridge(config.bridgeUrl, config.requestTimeoutMs,
      config.executorId ?? process.env.DSH_HOUDINI_EXECUTOR_ID)
  installSceneRecovery(ctx,connection)
  registerHoudiniTools(ctx, connection)
  registerImageTools(ctx,connection)
  registerVideoTools(ctx,connection)
  installNodeDeliveryNavigation(ctx,connection)
  registerBundledSkills(ctx)
  ctx.systemPrompt.section(GUIDANCE)
  if (config.automaticContext !== false) installSceneContext(ctx, connection)
}
