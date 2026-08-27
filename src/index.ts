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

export const name = 'dsh-houdini'
export const inject = ['tools', 'systemPrompt', 'skills']

export interface Config {
  /** Base URL of the Houdini-side bridge. */
  bridgeUrl: string
  /** Per-request timeout for bridge calls; job submission returns long before this. */
  requestTimeoutMs: number
}

export const Config: Schema<Config> = Schema.object({
  bridgeUrl: Schema.string().default('http://127.0.0.1:8765'),
  requestTimeoutMs: Schema.number().default(120000),
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
    'Verbs are the primary scene API; raw `hou` is a read/low-level escape hatch. The default-on gate rejects verb-covered raw mutations. Use `allow_raw` only after rejection, only for one isolated operation with no verb equivalent, and state the concrete gap. Never use raw `createNode`, `parm().set`, `cook`, `destroy`, or `hou.hipFile.load()` inside bridge code. If a verb signature or return shape is uncertain, call `verb_help(name)` before use; do not spend a failure or read repository source to discover runtime contracts. For three or more independent parameters on one node, prefer `set_parms`.',
    '',
    `Current catalog (generated from docs/tool-design.md): ${VERB_CATALOG_SUMMARY}`,
    '',
    'Ownership is runtime provenance, not path or copied metadata. Any node may be inspected or used as a read/source dependency, but mutation verbs normally write only nodes created by the current DSH session. Use `node_provenance` when origin is unclear. Pass `allow_foreign="<exact user authorization>"` only when the user explicitly requested changing that foreign node; it authorizes one audited call and never justifies incidental cleanup. `layout_nodes(parent)` defaults to current-session nodes.',
    '',
    'Load the smallest relevant bundled workflow before non-trivial work: `houdini-sop-workflow` for procedural SOP/VEX/Copy tasks, `houdini-rig-animation-workflow` for animation/rigging, and `houdini-solaris-karma-workflow` for USD/Karma/MaterialX delivery. Use `houdini-skill-governance` only when changing bundled skills. Detailed recipes and completion gates live in those skills, not in this always-on prompt.',
    '',
    'Validate the explicit deliverable, not incidental viewport state: cook and inspect module invariants, use `geo_frame_diff` for time dependency, and use `render_view(EXPLICIT_SOP)` for isolated visual evidence when GUI/OpenGL is stable. Keep its `__dsh_houdini_*` service nodes; do not clean them up. For animation A/B use one `framing_frame` chosen to cover the validation-frame envelope, then `render_check(path, ref=...)`; a content bbox touching the image edge is a framing failure even when the camera is fixed. If an evaluator, core transform graph, or membership rule changes, invalidate and rerun first/noncommutative/mid/end/recovery evidence. `render_check` proves file/pixel facts only. Claim visual semantics only after a vision inspection actually accessed the relayed image; setup, presentation, transport success, or a textual refusal is not visual evidence. Otherwise report visual semantics as unverified and hand subtle motion/aesthetics to user playback judgement.',
    '',
    'Houdini outputs belong under `$HIP`; relayed images are the exception and appear under the session workspace in the tool result `media` mapping. Do not write task outputs into the plugin repository. If the bridge is unreachable or reports a host/bridge contract mismatch, tell the user to run DSH-Houdini > Version & Diagnostics > Advanced diagnostics > Repair and restart runtime; do not work around it with shell commands.',
  ].join('\n'),
}

export function apply(ctx: Context, config: Config) {
  const bridge = new HoudiniBridge(config.bridgeUrl, config.requestTimeoutMs)
  installAskUserChoiceGuard(ctx)
  registerHoudiniTools(ctx, bridge)
  registerBundledSkills(ctx)
  ctx.systemPrompt.section(GUIDANCE)
}
