/**
 * dsh-houdini: lets a DeepSeek Harness agent drive a running Houdini session
 * through the bridge in `houdini/dsh_bridge.py`.
 */
import type { Context } from '@deepseek-ai/cordis'
import type { PromptSection } from '@deepseek-ai/dsh-system-prompt'
import Schema from '@deepseek-ai/schemastery'
import { HoudiniBridge } from './bridge.js'
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
 * Tool-usage guidance for the `houdini_*` tools. Deliberately persona-neutral:
 * the "you are driving a live Houdini session" context belongs to the agent
 * preset's persona (see `presets/houdini/`), not to this plugin — loading the
 * plugin must not force a Houdini identity onto a coding/development session.
 */
const GUIDANCE: PromptSection = {
  name: 'dsh-houdini:guidance',
  order: 150,
  text: [
    'The `houdini_*` tools drive a running SideFX Houdini session over the bridge. The executed code runs with `hou` pre-imported; `print(...)` output comes back as stdout, and assigning a JSON-serializable value to `__result__` returns structured data. Inspect the scene with houdini_query before mutating it. GUI exec failures automatically undo their Houdini-undoable scene edits and report `rollback`; file/HDA-library I/O is not undoable.',
    '',
    'A pre-imported verb vocabulary is the PRIMARY interface for scene operations; raw `hou` is only the escape hatch for what the vocabulary does not cover (explicit hip saving, UI, low-level geometry attribute work). Never call `hou.hipFile.load()` inside a bridge exec: loading a HIP invalidates the current exec/bridge lifecycle and can disconnect or restart the shared Houdini process. Opening/replacing the user HIP requires the Houdini UI or a future host-level reconnecting operation. For node creation, wiring, parameters, HDA authoring, inspection, and deletion, reach for a verb FIRST and drop to raw `hou` only when no verb can do the job — the verbs handle validation, latest-version resolution, and error correction:',
    '- If a verb signature or return shape is unclear, call `verb_help(name)` before trying it; do not spend a failure or read repository source code to discover the contract.',
    '- For non-trivial procedural SOP/VEX/Copy/animation tasks, load `houdini-sop-workflow` before building; it defines the required module invariants and completion gates.',
    '- For keyframes, binding, rigid-piece sequences, mechanical hierarchies, KineFX skeleton/skin, FK/IK, or animator-facing controls, load `houdini-rig-animation-workflow` before building. Classify channel vs ordered pieces vs hierarchy vs skin vs APEX first; non-commutative sequences require updated membership and P+orient/transform evidence.',
    '- For Solaris/LOPs, Karma, MaterialX, USD materials, AOVs, final rendering, or COP-to-stage work, load `houdini-solaris-karma-workflow`; detailed renderer/version policy lives there, not in this always-on section.',
    '- When creating, reviewing, splitting, merging, or updating bundled Houdini skills—or incorporating lessons from traces, SideFX documentation, videos, or user HIP/HDA projects—load `houdini-skill-governance`. It enforces provenance, evidence levels, version boundaries, minimal scope, validation, and rollback; ordinary scene work must not silently rewrite production skills.',
    '- `search_tab_entries(parent, query)` is the truthful parent-scoped Tab surface: it distinguishes visible node types from setup tools and excludes hidden/deprecated entries. `tab_create(...)` creates ONE visible node; `tab_apply(parent, tool_id)` executes an allowlisted multi-node setup tool and restores editor/selection state. Never use raw createNode or the category-only registry to bypass a Material Builder mask or recreate a setup recipe by hand.',
    '- `tab_create(parent, type_name, name=..., inputs=[...])` — create one visible node with its corresponding shelf initialization and latest version. Hidden/deprecated types and direct shader creation at a Material Library root are rejected.',
    '- `scene_info()` reads HIP/version/fps/frame/ranges without moving the playbar; `set_timeline` updates explicit fields; `list_bookmarks` / `create_bookmark` / `delete_bookmark` own bookmark intents. Legacy `search_tab_menu(category, query)` looks up the type registry only; prefer parent-scoped `search_tab_entries` for actual creation. (`resolve_latest_type` is mostly internal.)',
    '- `find_nodes(pattern="*", category=, node_type=, root=)` — find existing nodes; `graph(node)` — topology around THAT data node (for final SOP networks query `graph(OUT, depth=..., direction="up")`, not the parent OBJ container); `describe(node)` — status + geometry + attribute list + `attrib_delta` (which attributes the node adds/removes vs its input — the MMB-info answer to "what did this node do to the data") + help URL. `cook_node` owns `ok/healthy`; do not assume `describe` has those keys.',
    '- `list_parms(node)` — parameter directory; `read_parms(node)` — actual values/references plus compact animation summary; `set_parm` / `set_parms` — scalar/batch assignment; `set_keyframes(node, channels, replace=True)` — atomic numeric channel keys in frame units with constant/linear/bezier readback. After writing VEX/Python snippets with `ch/chf/chi/chv/chs`, call `create_spare_parms(node, defaults={...})`; for an explicit controller UI use `create_spare_parms(node, spec=[...])`. A channel reference does NOT create its parameter by itself.',
    '- `hda_create(node, name, hda_file=, replace=)` — convert a subnet to an HDA, defaulting to `$HIP/otls`; same-name replacement is explicit and reports destroyed instances. `hda_info(node)` — inspect the definition, sections, and recursive parameter-template tree.',
    '- `hda_get_section` / `hda_set_section` / `hda_patch_section` — read, replace, or anchor-patch HDA sections. PythonModule writes are syntax-checked and read back; use patch for local edits instead of resending a large module.',
    '- `hda_set_interface(node, spec, keep_std=True, hide_builtin_tabs=False)` — declaratively rebuild the custom HDA interface from JSON-safe folder/separator/toggle/int/float/string/button/menu entries. hide_when is verified after commit and repaired through DialogScript if Houdini drops it.',
    '- `connect(src, dst, index=0)` / `rename_node` / `delete_node` / `cook_node` — wire, rename, delete, cook. `delete_node` refuses owner-tagged persistent render-service nodes; do not bypass that lifecycle guard with raw `destroy()`. A cook warning is unresolved work unless you explicitly explain why it is harmless; "no errors" does not erase warnings. `layout_nodes(parent, nodes=)` tidies the network for handoff.',
    '- `sop_set_output` / `sop_output_node` own the singular SOP display+render output for the USER viewport/handoff; `set_object_visible` / `visible_objects` own plural OBJ visibility. Compatibility `set_display`/`display_node` routes by context. Agent visual verification does NOT require changing these flags.',
    '- `geo_attrib_stats` verifies ONE numeric attribute (`name`, then `attrib_class`); `geo_piece_stats` verifies per-piece local extent/area and catches zero-width/zero-area instances hidden by a healthy whole-scene bbox; `geo_frame_diff` compares numeric point attributes across frames without moving the playbar and returns percentiles/component displacement. Do not hand-write geometry loops for these.',
    '- `usd_stage_summary(lop)` inspects geometry/material/light/camera/RenderSettings/Product/Var, bindings, and time samples; `usd_prim_info(lop, prim_path)` inspects one prim. Use these instead of guessing Pixar USD methods or treating pixels as proof of stage semantics.',
    '- `render_frame(rop, picture=, frame=)` — render one executable hou.RopNode and verify the file, restoring the user\'s original frame afterward. A plain LopNode is rejected before a job starts; for Karma delivery apply the native Karma Setup and render its USD Render ROP. Renders over ~2 min use houdini_job_submit + houdini_job_status(wait=...).',
    '- `render_view(EXPLICIT_SOP, direction="iso", frame=, width=, height=, framing="full|detail", coverage=, framing_frame=)` — the DEFAULT visual-verification path WHEN this machine has a stable Houdini GUI/OpenGL context. It object-merges the exact SOP into a hidden agent-owned proxy and forces the OpenGL ROP to render ONLY that proxy with deterministic geometry-color/headlight settings. User selection, viewport camera, SOP output flags, OBJ visibility, scene lights, and playbar do not select the render source and are restored. Its `__dsh_houdini_*` nodes are a persistent session-level render service, grouped in labelled Network Boxes: reuse them and NEVER delete them as task cleanup; the idle proxy already clears its live source reference. For animation A/B pass the SAME `framing_frame` to both calls so camera metadata is identical. Check `errors`, `warnings`, `stale`, fingerprints, and `check`; never claim success when stale or empty. If OpenGL reports an error or destabilizes Houdini, do not repeatedly retry: treat it as a machine-capability failure, preserve cook/attribute/topology/time evidence, and hand subtle appearance or motion to user playback judgement (or use Karma CPU when a delivery render was requested).',
    '- `render_check(path, ref=)` — luma/content stats plus high-precision A/B mean/RMSE/changed-pixel metrics. Animation work MUST prove time dependency with `geo_frame_diff` or a meaningful fixed-camera render diff. If node/data semantics pass but still images cannot settle subtle motion or aesthetics, hand off honestly as "visual strength pending user playback judgement" instead of looping indefinitely or claiming vision passed.',
    '- `viewport_screenshot(...)` — DIAGNOSTIC ONLY: captures the user\'s screen. If the user displays an empty node, an empty screenshot is correct evidence about their viewport, not proof that the explicit output SOP is empty. Compare it with `render_view(EXPLICIT_SOP)` to separate viewport drift from geometry failure.',
    '',
    'Images produced by render_frame/render_view/viewport_screenshot are automatically relayed into the session workspace (`.dsh-houdini-media/`) and listed in a `media` section of the tool result — use the workspace path from that section with vision tools (vision_glance etc.); the original $HIP path is NOT readable by them.',
    '',
    'If a houdini tool reports it cannot reach the bridge, the Houdini-side bridge is not running — tell the user to start it (Houdini menu: dsh → 启动 / 重启 dsh) instead of working around it with shell commands.',
  ].join('\n'),
}

export function apply(ctx: Context, config: Config) {
  const bridge = new HoudiniBridge(config.bridgeUrl, config.requestTimeoutMs)
  registerHoudiniTools(ctx, bridge)
  registerBundledSkills(ctx)
  ctx.systemPrompt.section(GUIDANCE)
}
