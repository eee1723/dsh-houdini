/**
 * dsh-houdini: lets a DeepSeek Harness agent drive a running Houdini session
 * through the bridge in `houdini/dsh_bridge.py`.
 */
import type { Context } from '@deepseek-ai/cordis'
import type { PromptSection } from '@deepseek-ai/dsh-system-prompt'
import Schema from '@deepseek-ai/schemastery'
import { HoudiniBridge } from './bridge.js'
import { registerHoudiniTools } from './tools.js'

export const name = 'dsh-houdini'
export const inject = ['tools', 'systemPrompt']

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
 * Tool-usage guidance for the `houdini_*` tools. Deliberately persona-neutral:
 * the "you are driving a live Houdini session" context belongs to the agent
 * preset's persona (see `presets/houdini/`), not to this plugin — loading the
 * plugin must not force a Houdini identity onto a coding/development session.
 */
const GUIDANCE: PromptSection = {
  name: 'dsh-houdini:guidance',
  order: 150,
  text: [
    'The `houdini_*` tools drive a running SideFX Houdini session over the bridge. The executed code runs with `hou` pre-imported; `print(...)` output comes back as stdout, and assigning a JSON-serializable value to `__result__` returns structured data. Inspect the scene with houdini_query before mutating it.',
    '',
    'A pre-imported verb vocabulary (plus raw `hou`) is available. Prefer the verbs over raw `hou` calls — they handle validation, latest-version resolution, and error correction:',
    '- `tab_create(parent, type_name, name=..., inputs=[...])` — create a node with full Tab-Menu initialization AND the latest version (prefer over raw createNode).',
    '- `search_tab_menu(category, query)` / `resolve_latest_type(category, base)` — look up node types; never guess type names (e.g. there is no `cone` SOP — use `tube` with top radius 0).',
    '- `find_nodes(pattern="*", category=, node_type=, root=)` — find existing nodes; `graph(node)` — topology (inputs/outputs/parm_refs); `describe(node)` — status + geometry + help URL.',
    '- `list_parms(node)` — parameter directory (names/types); `read_parms(node)` — changed/expression parameters with reference info; `set_parm(node, name, value)` — set a parameter (a string value on a numeric parm sets an expression; lists similar names on failure).',
    '- `connect(src, dst, index=0)` / `rename_node` / `delete_node` / `cook_node` — wire (reports the actual input used), rename, delete (reports expression refs), cook+report errors.',
    '',
    'If a houdini tool reports it cannot reach the bridge, the Houdini-side bridge is not running — tell the user to start it (Houdini menu: dsh → 启动 / 重启 dsh) instead of working around it with shell commands.',
  ].join('\n'),
}

export function apply(ctx: Context, config: Config) {
  const bridge = new HoudiniBridge(config.bridgeUrl, config.requestTimeoutMs)
  registerHoudiniTools(ctx, bridge)
  ctx.systemPrompt.section(GUIDANCE)
}
