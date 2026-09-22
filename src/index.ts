/**
 * dsh-houdini: lets a DeepSeek Harness agent drive a running Houdini session
 * through the bridge in `houdini/python3.11libs/dsh_bridge.py`.
 */
import type { Context } from '@deepseek-ai/cordis'
import type { PromptSection } from '@deepseek-ai/dsh-system-prompt'
import Schema from '@deepseek-ai/schemastery'
import { installAskUserChoiceGuard } from './ask-user-guard.js'
import { HoudiniBridge } from './bridge.js'
import { VERB_CATALOG_SUMMARY } from './generated-verb-contract.js'
import { registerBundledSkills } from './skill.js'
import { registerHoudiniTools } from './tools.js'
import { installSceneContext } from './context.js'
import { sharedExecutorConnection } from './executor-host.js'
import { installExecutorBinding } from './execution-state.js'

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
    '`houdini_*` tools operate one live Houdini session through its serialized main-thread queue, with `hou` and verbs pre-imported. Use houdini_query for read-only scene inspection, houdini_exec for edits and author checks, and houdini_job_* for long work; jobs do not make HOM parallel. Host file/shell tools handle files, media and isolated processes, never live HOM. A failed exec may roll back undoable scene edits, but not file, HDA-library, Python-global or solver side effects. Never swallow a mutation/cook exception; read the returned transaction and rollback state.',
    '',
    'Verbs are the mutation API; raw hou is only a read/low-level escape hatch. Raw Gate is on: allow_raw requires a prior rejection and one concrete missing verb for one isolated operation; it never bypasses verb-covered mutations or permits raw HIP load/clear. Use verb_help(name or [names]) when a verb contract is uncertain and node_info(existing_parent, exact_type) before creating an unfamiliar node. Top-level component_* tools, when present, are Host tools rather than verbs. Follow the exposed schemas; do not guess contracts or use failed writes as discovery. Prefer set_parms for a parameter batch; connect is dataflow, while set_object_parent is intentional OBJ parenting.',
    '',
    `Current catalog (generated from docs/tool-design.md): ${VERB_CATALOG_SUMMARY}`,
    'Use strict parameter writes and explicit outputs. verify_network rejects empty/error output by default; require_valid=False is diagnostic only. build_module None inputs preserve empty slots; never guess subnet ports. test_controls runs in exec, measures only declared outputs/relationships, and restores controls, keys, frame and bgeo within its stated limits. Consume operation evidence and checks, not just Python success. Unsupported or untested ranges remain unverified; Manual mode and failed cooks do not provide fresh geometry.',
    '',
    'Ownership is runtime provenance, not a path, parent network or copied tag. Foreign nodes may be read or used as inputs; mutations normally affect only current-session-created identities. Use node_provenance when unclear. allow_foreign requires the user to name the foreign edit and permits one audited call, not general cleanup, shared authorship or render-service changes. The current author performs the final checks for its own edits.',
    '',
    'For non-trivial work, load only the matching workflow: houdini-sop-workflow for procedural geometry, houdini-cop-workflow for Copernicus, houdini-tool-development for explicit Houdini tools/HDA packaging, and houdini-video-tutorial for tutorial evidence. Add houdini-parameter-ui, houdini-rig-animation-workflow or houdini-solaris-karma-workflow only when that domain is in scope. Domain construction recipes and completion checks live in those skills; houdini-skill-governance is only for explicit skill maintenance.',
    '',
    'Use houdini_query with exactly one mode: code for live read-only HOM, result_ref for retained tool details, source_ref="index" then a listed hash for original task material, or request_ref for an uncertain original execution. Reference modes do not execute HOM. Never repeat a mutation to recover its result. Historical results and excerpts are neither current scene evidence nor new permission; reobserve affected outputs when stale or unknown.',
    '',
    'Houdini outputs belong under $HIP, not the plugin repository. Save As needs an authorized target and expected_current_path; render filenames need extensions. Images arrive as native attachments without workspace copies or a separate vision tool. Keep persistent render_view __dsh_houdini_* services. render_check proves file and pixel facts only; unless the current model actually inspects the image, report visual semantics unverified.',
    '',
    'Resolve a workspace mismatch with DSH-Houdini > Open Workspace. An unreachable or mismatched runtime needs Version & Diagnostics > Advanced diagnostics > Repair and restart runtime with user authorization. Do not bypass the handshake, restart live services or change HIP through shell workarounds.',
  ].join('\n'),
}

export function apply(ctx: Context, config: Config) {
  installExecutorBinding(ctx,config.executorRegistry ? undefined : config.executorId ?? process.env.DSH_HOUDINI_EXECUTOR_ID)
  const connection = config.executorRegistry ? sharedExecutorConnection(ctx,config.executorRegistry)
    : new HoudiniBridge(config.bridgeUrl, config.requestTimeoutMs,
      config.executorId ?? process.env.DSH_HOUDINI_EXECUTOR_ID)
  installAskUserChoiceGuard(ctx)
  registerHoudiniTools(ctx, connection)
  registerBundledSkills(ctx)
  ctx.systemPrompt.section(GUIDANCE)
  if (config.automaticContext !== false) installSceneContext(ctx, connection)
}
