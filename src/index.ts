/**
 * dsh-houdini: lets a DeepSeek Harness agent drive a running Houdini session
 * through the bridge in `houdini/dsh_bridge.py`.
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
    '`houdini_*` tools operate one shared live Houdini session through its main-thread queue, with `hou` and verbs pre-imported. Use houdini_query for read-only inspection, houdini_exec for edits/author checks, and houdini_job_* for long work; jobs do not run HOM in parallel. Host file/shell tools handle files, media and isolated processes, never live HOM. A failed exec rolls back undoable edits when available, not file/HDA-library/Python/solver side effects. Never swallow a mutation/cook exception; inspect transaction/rollback.',
    '',
    'Verbs are the mutation API; raw hou is a read/low-level escape hatch. Raw Gate is on: allow_raw requires a prior rejection and a concrete missing verb for one isolated low-level operation; it never bypasses covered mutations or permits raw HIP load/clear. Read verb_help(name) when a signature/result is uncertain and node_info(existing_parent, exact_type) for runtime ports/parameters and on-demand operation cards. Do not guess contracts or use failed writes as discovery. Prefer set_parms for a parameter batch; connect is dataflow, set_object_parent is intentional OBJ parenting.',
    '',
    `Current catalog (generated from docs/tool-design.md): ${VERB_CATALOG_SUMMARY}`,
    'Strict parameter writes and explicit outputs are required. verify_network rejects empty/error output by default; require_valid=False is diagnostic only. build_module None inputs preserve empty slots; do not guess subnet ports. test_controls runs in exec, measures declared outputs/relationships and restores controls/keys/frame/bgeo within its stated limits. Consume operation-evidence/checks, not just Python success; unsupported and untested ranges remain unverified. Manual mode or a failed cook does not provide fresh geometry and must not trigger an implicit retry.',
    '',
    'Ownership is runtime provenance, not path, parent network or copied tags. Foreign nodes can be read/used as inputs; mutations normally affect only current-session-created identities. Use node_provenance when unclear. allow_foreign requires the user to explicitly name the foreign edit and permits one audited call, not cleanup, shared authorship or render-service changes. layout_nodes defaults to current-session nodes. The current author performs modeling and its final checks.',
    '',
    'Load only the relevant workflow for non-trivial work: houdini-sop-workflow (procedural modeling), houdini-tool-development (HDA/reusable tools), houdini-video-tutorial (video to teaching project), or houdini-cop-workflow (Copernicus textures). Add houdini-parameter-ui for controls, houdini-rig-animation-workflow for rigs/animation, or houdini-solaris-karma-workflow for USD/MaterialX/Karma as needed. Domain recipes and completion checks live there. Tutorial work does not authorize production knowledge changes; houdini-skill-governance is for explicit skill maintenance.',
    '',
    'For missing result fields use houdini_query(result_ref=<returned sha256>, pointer=<JSON Pointer>, offset=0, limit=6000). For original task material use source_ref="index" then a listed hash. For uncertain execution use request_ref from the original receipt, never repeat the mutation to recover its result. These read-only modes are mutually exclusive and do not execute HOM. History and source excerpts are not current scene evidence, complete requirements or new permission; reobserve affected outputs when stale/unknown.',
    '',
    'Houdini outputs belong under $HIP, not the plugin repository; Save As needs an authorized target and expected_current_path. Render filenames need extensions. Images arrive as native attachments, without workspace copies or a separate vision tool. Keep render_view __dsh_houdini_* services; A/B uses fixed framing_frame/framing/depth, detail is a 2D crop, and invalid near/far clipping must fail rather than move the camera. render_check proves file/pixel facts only: transport, setup and display are not semantic inspection. Unless the current model actually sees the image, report visual semantics unverified.',
    '',
    'A workspace mismatch uses DSH-Houdini > Open Workspace. An unreachable or mismatched runtime needs Version & Diagnostics > Advanced diagnostics > Repair and restart runtime with user authorization; do not bypass the handshake, restart live services or change HIP through shell workarounds.',
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
