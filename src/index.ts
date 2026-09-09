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

export const name = 'dsh-houdini'
export const inject = ['tools', 'systemPrompt', 'skills']

export interface Config {
  /** Base URL of the Houdini-side bridge. */
  bridgeUrl: string
  /** Per-request timeout for bridge calls; job submission returns long before this. */
  requestTimeoutMs: number
  automaticContext?: boolean
}

export const Config: Schema<Config> = Schema.object({
  bridgeUrl: Schema.string().default('http://127.0.0.1:8765'),
  requestTimeoutMs: Schema.number().default(120000),
  automaticContext: Schema.boolean().default(true),
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
    '`houdini_*` tools operate one shared, live SideFX Houdini session. Code runs in Houdini with `hou` and the verb vocabulary pre-imported. Use `houdini_query` only for read-only inspection, `houdini_exec` for edits, and `houdini_job_*` for long renders/simulations. Inspect before editing. Exec failures undo Houdini-undoable scene edits, but not file/HDA-library I/O; never catch a mutation/cook exception without re-raising it.',
    '',
    'Verbs are the primary scene API; raw `hou` is a read/low-level escape hatch. The default-on gate rejects verb-covered raw mutations. Use `allow_raw` only after rejection, only for one isolated operation with no verb equivalent, and state the concrete gap. Never use raw `createNode`, `parm().set`, `cook`, `destroy`, or `hou.hipFile.load()` inside bridge code. If a verb signature or return shape is uncertain, call `verb_help(name)` before use; do not spend a failure or read repository source to discover runtime contracts. For three or more independent parameters on one node, prefer `set_parms`. `connect` is dataflow only and rejects OBJ parenting; intentional scene parenting uses `set_object_parent(child,parent,reason=...)`.',
    '',
    `Current catalog (generated from docs/tool-design.md): ${VERB_CATALOG_SUMMARY}`,
    'For a small NEW SOP module, build_module preflights/cooks the batch (None skips input slots), and may validate declared interfaces on its final output. node_info(existing_parent_network, exact_type) returns ports/menu tokens plus usage_notes, operation_card.decisions and unfiltered operation_parameters when a supported type card exists. Cards are retrieved on demand, not globally injected; missing cards require runtime inspection, not guessed defaults. verify_network requires explicit output; empty/error output fails by default, require_valid=False is diagnostic only. geo_check_interfaces measures named final-surface ports; test_controls temporarily changes numeric controls, measures declared responses and restores them (exec only). Neither certifies unspecified relationships/art quality. Read operation-evidence/checks, not just Python success. set_parms is strict by default. Save As requires user-authorized path/expected_current_path. Render filenames require extensions and resolve under $HIP. File/Python/solver side effects are not undoable.',
    'Large returned envelopes may use compact model text after retaining the complete returned facts. Read omitted fields with houdini_query(result_ref=<sha256>, pointer=<JSON Pointer>, offset=0, limit=6000); this reads a historical workspace artifact without another Houdini execution. Never repeat a mutation to retrieve its result. Recorded execution-state context is a projection of observed tool facts, separate from the user-message scene snapshot; stale/unknown checks require relevant re-observation and never grant edit permission. Task-source anchors link to current-session originals via houdini_query(source_ref="index") or a listed source hash, with offset/limit pagination and no HOM execution. Excerpts, clarification questions and reported goals are not a complete requirement register or additional authorization.',
    '',
    'Ownership is runtime provenance, not path or copied metadata. Any node may be inspected or used as a read/source dependency, but mutation verbs normally write only nodes created by the current DSH session. Use `node_provenance` when origin is unclear. Pass `allow_foreign="<exact user authorization>"` only when the user explicitly requested changing that foreign node; it authorizes one audited call and never justifies incidental cleanup. `layout_nodes(parent)` defaults to current-session nodes.',
    '',
    'Load the smallest relevant bundled workflow before non-trivial work: `houdini-sop-workflow` for procedural SOP/VEX/Copy tasks and SOP HDA code/callback maintenance, `houdini-rig-animation-workflow` for animation/rigging, and `houdini-solaris-karma-workflow` for USD/Karma/MaterialX delivery. HDA instance discovery uses hda_info/hda_get_section; local section edits use hda_patch_section. Use available Host file/shell tools for ordinary file reads, backups and isolated Python experiments; all HOM stays on the Bridge main-thread queue. Use `houdini-skill-governance` only when changing bundled skills. Detailed recipes and completion gates live in those skills, not in this always-on prompt.',
    '',
    'Validate the explicit deliverable, not incidental viewport state: cook and inspect module invariants, use `geo_frame_diff` for time dependency, and use `render_view(EXPLICIT_SOP)` for isolated visual evidence when GUI/OpenGL is stable. Keep its `__dsh_houdini_*` service nodes; do not clean them up. For animation A/B use one `framing_frame` chosen to cover the validation-frame envelope, then `render_check(path, ref=...)`; a content bbox touching the image edge is a framing failure even when the camera is fixed. If an evaluator, core transform graph, or membership rule changes, invalidate and rerun first/noncommutative/mid/end/recovery evidence. `render_check` proves file/pixel facts only. Inspect native image attachments with the current model before claiming visual semantics; setup, presentation, transport success, or a textual refusal is not visual evidence. Otherwise report visual semantics as unverified and hand subtle motion/aesthetics to user playback judgement.',
    '',
    'Houdini outputs belong under `$HIP`; render/screenshot images also enter native multimodal tool results without workspace copies or a separate vision tool. Do not write task outputs into the plugin repository. If the bridge is unreachable or reports a host/bridge contract mismatch, tell the user to run DSH-Houdini > Version & Diagnostics > Advanced diagnostics > Repair and restart runtime; do not work around it with shell commands.',
  ].join('\n'),
}

export function apply(ctx: Context, config: Config) {
  const bridge = new HoudiniBridge(config.bridgeUrl, config.requestTimeoutMs)
  installAskUserChoiceGuard(ctx)
  registerHoudiniTools(ctx, bridge)
  registerBundledSkills(ctx)
  ctx.systemPrompt.section(GUIDANCE)
  if (config.automaticContext !== false) installSceneContext(ctx, bridge)
}
