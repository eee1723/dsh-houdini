"""dsh-houdini bridge: an HTTP server running INSIDE Houdini's Python.

The `hou` module only exists inside Houdini, so the dsh plugin talks to this
server and this server executes the agent's Python code in the live session.

Start from Houdini's Python Shell (Windows > Python Shell) — after installing the
package, `python3.11libs` is already on sys.path, so a plain import works:

    import dsh_bridge
    dsh_bridge.start()                      # serves http://127.0.0.1:8765

Or headless with hython:

    hython <path-to-repo>/houdini/python3.11libs/dsh_bridge.py [scene.hip]

Endpoints:
    GET  /health              {}            -> version, raw gate, and active job counts
    POST /exec                {"code": str} -> ExecResult
    POST /jobs                {"code": str} -> {"jobId": str}
    POST /jobs/<id>/status    {}            -> JobStatus
    POST /jobs/<id>/cancel    {}            -> JobStatus

ExecResult includes ``ok/stdout/stderr/result/error`` plus the verb ledger,
Raw Gate classification, rollback outcome, advisory text and produced image
paths. The Host adds the final media-relay mapping after it copies images into
the DSH session workspace.

Threading note: `hou` is not thread-safe and must be called from Houdini's
main thread, so ALL code execution is marshaled onto the main thread through
a work queue drained by a pump (a QTimer in GUI mode, the __main__ loop in
headless hython). Execution is therefore strictly serial; background jobs
queue rather than run in parallel — they exist so the agent is not blocked on
renders / simulations. Cancellation is cooperative: a queued job is dropped
BEFORE its code runs (no scene side effects); a running job cannot be killed.
Note this freezes the GUI while code executes — exactly like a native cook.

Hardening: captured stdout/stderr and `__result__` are size-capped, deep
non-JSON values are coerced to `repr`, oversized request bodies are rejected,
and finished jobs are pruned so a long session cannot grow the registry
without bound.
"""

from __future__ import annotations

import ast
import contextlib
import difflib
import hashlib
import io
import inspect
import json
import math
import os
import queue
import threading
import time
import traceback
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import hou  # noqa: F401  (imported so it is bound in the exec namespace)
import dsh_hou_helpers  # noqa: F401  (verb vocabulary: see docs/tool-design.md)

# Cached while this module is imported on Houdini's owning thread. HTTP handler
# threads must not call HOM, including for seemingly harmless health metadata.
_HOU_VERSION = hou.applicationVersionString()
_HOU_THREAD_ID = threading.get_ident()
# Bump when operation semantics change without renaming verbs. Host generation
# reads the matching version declaration in docs/tool-design.md.
_EXECUTION_CONTRACT_VERSION = 35
_RUNTIME_ID = uuid.uuid4().hex
from dsh_requests import RequestRegistry
_request_registry = RequestRegistry(_RUNTIME_ID)
_EXECUTION_SEQUENCE = 0
# Remove the retired v8 callback when reloading an existing runtime.
if globals().get('_delivery_hip_callback') is not None:
    try:hou.hipFile.removeEventCallback(_delivery_hip_callback)
    except hou.Error:pass

# --- limits (kept small so a runaway agent cannot exhaust Houdini) ----------
_MAX_STREAM_BYTES = 1024 * 1024          # cap captured stdout/stderr per exec
_MAX_RESULT_BYTES = 4 * 1024 * 1024      # cap the serialized __result__
_MAX_BODY_BYTES = 16 * 1024 * 1024       # reject oversized HTTP bodies
_MAX_RESULT_DEPTH = 20                   # recursion depth for __result__ coercion
_MAX_RESULT_ITEMS = 1000                 # items per container before repr fallback
_MAX_JOBS = 1000                         # terminal-job registry cap
_MAX_ACTIVE_JOBS = 32                    # bound queued workers, not only history
_JOB_RETENTION_SECONDS = 600             # keep terminal job results for polling

_exec_lock = threading.Lock()
_jobs: dict[str, dict] = {}              # API-visible job payloads (schema-exact)
_job_meta: dict[str, float] = {}         # jobId -> created/finished timestamp
_jobs_lock = threading.Lock()

# /media 端点（图片字节回传）的限制
_MEDIA_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".webp"}
_MEDIA_MAX_BYTES = 64 * 1024 * 1024
_MEDIA_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".bmp": "image/bmp", ".tga": "image/x-tga", ".webp": "image/webp",
}


class _CappedStringIO(io.StringIO):
    """StringIO that stops growing past `limit`, appending a truncation marker."""

    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit
        self.overflowed = False

    def write(self, s) -> int:
        if self.overflowed:
            return len(s)
        remaining = self.limit - self.tell()
        if len(s) <= remaining:
            return super().write(s)
        super().write(s[:remaining])
        super().write("\n... [dsh-houdini: output truncated]\n")
        self.overflowed = True
        return len(s)


def _jsonable(value, _depth: int = 0):
    """Deep-coerce `value` to a JSON-safe object; non-JSON leaves become `repr`."""
    if _depth > _MAX_RESULT_DEPTH:
        return repr(value)
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return repr(value)
        # dsh-tools requires lossless JSON and deliberately rejects -0 because a
        # normal JSON snapshot may collapse it to +0. Houdini vectors/matrices and
        # quaternion probes commonly produce -0.0, so normalize it at the single
        # bridge boundary used by __result__ and the verb ledger.
        return 0.0 if value == 0.0 else value
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_RESULT_ITEMS:
            return repr(value)
        return [_jsonable(v, _depth + 1) for v in value]
    if isinstance(value, dict):
        if len(value) > _MAX_RESULT_ITEMS:
            return repr(value)
        return {str(k): _jsonable(v, _depth + 1) for k, v in value.items()}
    try:
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError):
        return repr(value)


# --- verb tracing ------------------------------------------------------------
# 每个动词（verb）的运行时调用都会被记录：动词名 / 入参 / 出参 / 是否成功 / 耗时。
# 记录随 exec 结果返回（`verbs` 字段），供 agent 和将来的 houdinitrace 视图
# 消费——让动词词表的调用情况「是否成功 + 具体输入输出」清晰可见。
def _verb_help(name: str) -> dict:
    """返回一个已注入动词的 signature/docstring，避免靠失败或仓库源码猜契约。"""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name 必须是非空动词名")
    key = name.strip()
    registry = globals().get("_VERBS", {})
    fn = registry.get(key)
    if fn is None:
        suggestions = difflib.get_close_matches(key, sorted(registry), n=8, cutoff=0.35)
        raise ValueError(f"未知动词 {key!r}；相似动词：{suggestions}")
    try:
        inspected = inspect.signature(fn)
        signature = str(inspected)
        returns = inspected.return_annotation
        return_type = None if returns is inspect.Signature.empty else inspect.formatannotation(returns)
    except Exception:
        signature = None
        return_type = None
    return {
        "name": key,
        "signature": signature,
        "return_type": return_type,
        "call_mode": "exec" if key in _MUTATING_VERB_NAMES else "query_or_exec",
        "doc": inspect.getdoc(fn) or "",
    }


_VERBS: dict[str, object] = {
    "verb_help": _verb_help,
    "scene_info": dsh_hou_helpers.scene_info,
    "scene_save": dsh_hou_helpers.scene_save,
    "scene_save_as": dsh_hou_helpers.scene_save_as,
    "set_timeline": dsh_hou_helpers.set_timeline,
    "list_bookmarks": dsh_hou_helpers.list_bookmarks,
    "create_bookmark": dsh_hou_helpers.create_bookmark,
    "delete_bookmark": dsh_hou_helpers.delete_bookmark,
    "search_tab_menu": dsh_hou_helpers.search_tab_menu,
    "search_tab_entries": dsh_hou_helpers.search_tab_entries,
    "resolve_latest_type": dsh_hou_helpers.resolve_latest_type,
    "tab_create": dsh_hou_helpers.tab_create,
    "node_info": dsh_hou_helpers.node_info,
    "build_module": dsh_hou_helpers.build_module,
    "verify_network": dsh_hou_helpers.verify_network,
    "tab_apply": dsh_hou_helpers.tab_apply,
    "find_nodes": dsh_hou_helpers.find_nodes,
    "graph": dsh_hou_helpers.graph,
    "describe": dsh_hou_helpers.describe,
    "node_provenance": dsh_hou_helpers.node_provenance,
    "connect": dsh_hou_helpers.connect,
    "set_object_parent": dsh_hou_helpers.set_object_parent,
    "disconnect_input": dsh_hou_helpers.disconnect_input,
    "rename_node": dsh_hou_helpers.rename_node,
    "delete_node": dsh_hou_helpers.delete_node,
    "cook_node": dsh_hou_helpers.cook_node,
    "set_update_mode": dsh_hou_helpers.set_update_mode,
    "set_display": dsh_hou_helpers.set_display,
    "display_node": dsh_hou_helpers.display_node,
    "sop_set_output": dsh_hou_helpers.sop_set_output,
    "sop_output_node": dsh_hou_helpers.sop_output_node,
    "set_object_visible": dsh_hou_helpers.set_object_visible,
    "visible_objects": dsh_hou_helpers.visible_objects,
    "layout_nodes": dsh_hou_helpers.layout_nodes,
    "list_parms": dsh_hou_helpers.list_parms,
    "read_parms": dsh_hou_helpers.read_parms,
    "set_parm": dsh_hou_helpers.set_parm,
    "set_parms": dsh_hou_helpers.set_parms,
    "set_keyframes": dsh_hou_helpers.set_keyframes,
    "create_spare_parms": dsh_hou_helpers.create_spare_parms,
    "parameter_ui": dsh_hou_helpers.parameter_ui,
    "bind_controls": dsh_hou_helpers.bind_controls,
    "hda_create": dsh_hou_helpers.hda_create,
    "hda_edit": dsh_hou_helpers.hda_edit,
    "hda_info": dsh_hou_helpers.hda_info,
    "hda_get_section": dsh_hou_helpers.hda_get_section,
    "hda_set_section": dsh_hou_helpers.hda_set_section,
    "hda_patch_section": dsh_hou_helpers.hda_patch_section,
    "hda_set_interface": dsh_hou_helpers.hda_set_interface,
    "geo_attrib_stats": dsh_hou_helpers.geo_attrib_stats,
    "geo_point_spacing": dsh_hou_helpers.geo_point_spacing,
    "geo_check_interfaces": dsh_hou_helpers.geo_check_interfaces,
    "test_controls": dsh_hou_helpers.test_controls,
    "cop_layer_stats": dsh_hou_helpers.cop_layer_stats,
    "cop_compare_layers": dsh_hou_helpers.cop_compare_layers,
    "test_cop_controls": dsh_hou_helpers.test_cop_controls,
    "geo_piece_stats": dsh_hou_helpers.geo_piece_stats,
    "geo_frame_diff": dsh_hou_helpers.geo_frame_diff,
    "usd_stage_summary": dsh_hou_helpers.usd_stage_summary,
    "usd_prim_info": dsh_hou_helpers.usd_prim_info,
    "render_frame": dsh_hou_helpers.render_frame,
    "camera_fit": dsh_hou_helpers.camera_fit,
    "render_check": dsh_hou_helpers.render_check,
    "render_view": dsh_hou_helpers.render_view,
    "viewport_screenshot": dsh_hou_helpers.viewport_screenshot,
}

# Runtime truth, independently derived from the verbs actually injected into
# this Houdini process. The host derives its expected hash from tool-design.md;
# comparing the two catches a stale in-process bridge before any scene edit.
_VERB_NAMES = tuple(sorted(_VERBS))
_VERB_CATALOG_HASH = hashlib.sha256("\n".join(_VERB_NAMES).encode("utf-8")).hexdigest()

_MUTATING_VERB_NAMES = {
    "cop_layer_stats", "cop_compare_layers", "test_cop_controls",
    "scene_save", "scene_save_as", "build_module", "verify_network", "test_controls", "set_timeline", "create_bookmark", "delete_bookmark",
    "tab_create", "tab_apply", "connect", "set_object_parent", "disconnect_input", "rename_node",
    "delete_node", "cook_node", "set_display", "sop_set_output",
    "set_object_visible", "layout_nodes", "set_parm", "set_parms",
    "set_keyframes", "create_spare_parms", "hda_create", "hda_set_section",
    "hda_patch_section", "hda_set_interface", "hda_edit", "render_frame", "render_view",
    "viewport_screenshot", "camera_fit", "bind_controls", "set_update_mode",
}

# These verbs may cook or manage services but do not author the deliverable's
# graph/parameters on a successful, restored call. Unknown effects stay unknown.
_OBSERVATION_VERBS = {'cop_layer_stats', 'cop_compare_layers', 'test_cop_controls', 'scene_save', 'create_bookmark', 'delete_bookmark', 'layout_nodes',
    'cook_node', 'verify_network', 'test_controls', 'render_frame', 'render_view', 'viewport_screenshot'}
_GLOBAL_EDIT_VERBS = {'set_timeline', 'set_update_mode', 'scene_save_as', 'hda_create', 'hda_set_section', 'bind_controls',
                     'hda_patch_section', 'hda_set_interface', 'hda_edit'}


def _observe_impact(nodes, impact, descendants=False):
    """No cook: bounded native wire/expression references, before and after edits.

    HOM dependents are based on last cook and cannot prove all dynamic/external
    dependencies. This is an invalidation hint, never an unaffected-scene proof.
    """
    pending = list(nodes)
    seen = set()
    while pending:
        if len(impact['nodes']) >= 256 or len(seen) >= 256:
            impact['truncated'] = True
            break
        node = pending.pop()
        try:
            identity = node.sessionId()
            if identity in seen:
                continue
            seen.add(identity)
            impact['nodes'][identity] = node.path()
            pending.extend(node.outputs())
            pending.extend(node.dependents(include_children=False))
            if descendants and node.isNetwork():
                pending.extend(node.children())
        except Exception:
            impact['unavailable'] = True

_VERB_ENTRY_LIMIT = 500       # 单次 exec 最多记录的动词调用数
_VERB_VALUE_CHARS = 2000      # 单个入参/出参序列化后的截断长度

# --- raw-hou advisory ---------------------------------------------------------
# 动词词表是主接口，裸 hou 只是逃生手段。对每次 exec 的代码做 AST 扫描：统计
# 那些动词已覆盖的裸 hou 调用；一旦代码完全没走动词却用了这些调用，就在返回
# 里附一条 advisory，点明对应的动词——让 agent 从结果里直接看到可替代方案。
_RAW_HOU_VERB_MAP = {
    "hipFile.save": "scene_save",
    "hipFile.setName": "scene_save_as",
    "createNode": "search_tab_entries + tab_create/tab_apply",
    "setInput": "connect, set_object_parent, or disconnect_input",
    "setFirstInput": "connect, set_object_parent, or disconnect_input",
    "connectInputs": "connect",
    "setName": "rename_node",
    "destroy": "delete_node",
    "cook": "cook_node",
    "setDisplayFlag": "sop_set_output or set_object_visible",
    "setRenderFlag": "sop_set_output",
    "layoutChildren": "layout_nodes",
    "moveToGoodPosition": "layout_nodes",
    "parm().set": "set_parm",   # 由 _raw_hou_calls 特判 parm(...).set(...) 模式
    "setExpression": "set_parm",  # set_parm 收到字符串值即走表达式路由
    "createDigitalAsset": "hda_create",
    "allowEditingOfContents": "hda_edit",
    "updateFromNode": "hda_edit",
    "matchCurrentDefinition": "hda_edit",
    "removeSpareParms": "hda_edit",
    "setParmTemplateGroup": "hda_set_interface or create_spare_parms",
    "addSpareParmTuple": "create_spare_parms",
    "setKeyframe": "set_keyframes",
    "setKeyframes": "set_keyframes",
    "deleteAllKeyframes": "set_keyframes or set_parm",
    "addSection": "hda_set_section",
    "setConditional": "hda_set_interface",
}


def _raw_hou_calls(code: str) -> dict[str, int]:
    """Count raw hou calls a verb already covers (AST-based; {} when unparseable)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    counts: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        func = node.func
        path = _call_path(func)
        if path in ("hou.hipFile.save", "hou.hipFile.setName"):
            key = path.removeprefix("hou.")
        elif func.attr in _RAW_HOU_VERB_MAP:
            key = func.attr
        elif (
            func.attr == "set"
            and isinstance(func.value, ast.Call)
            and isinstance(func.value.func, ast.Attribute)
            and func.value.func.attr in ("parm", "parmTuple")
        ):
            key = "parm().set"
        else:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def _raw_hou_advisory(code: str, verb_ledger: list) -> str | None:
    """Advisory text when code bypassed the verb vocabulary with raw hou calls."""
    if verb_ledger:
        return None
    counts = _raw_hou_calls(code)
    if not counts:
        return None
    verbs = sorted({_RAW_HOU_VERB_MAP[key] for key in counts})
    detail = ", ".join(f"{key}x{n}" for key, n in sorted(counts.items()))
    return (
        f"{sum(counts.values())} raw hou call(s) bypassed the verb vocabulary "
        f"({detail}). These are covered by verbs: {', '.join(verbs)}. "
        "Prefer the verbs next time — raw hou is the escape hatch for what the "
        "vocabulary does not cover."
    )


def _forbidden_hip_lifecycle_message(code: str) -> str | None:
    """Reject direct HIP replacement/reset calls before execution.

    Loading a HIP resets the scene/process lifecycle that owns this very bridge
    request: H21 GUI reproduction lost results/images and eventually restarted
    Houdini, so neither undo nor a Python ``finally`` can make it transactional.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in ("load", "clear"):
            continue
        owner = node.func.value
        if (
            isinstance(owner, ast.Attribute)
            and owner.attr == "hipFile"
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "hou"
        ):
            method = node.func.attr
            return (
                f"hou.hipFile.{method}() is forbidden inside dsh-houdini bridge exec: "
                "HIP replacement/reset invalidates the active exec/bridge lifecycle and can "
                "disconnect or restart the shared Houdini process. Open the HIP in "
                "the Houdini UI (including File > New), or use a future host-level "
                "reconnecting operation."
            )
    return None


# --- repo-write advisory ------------------------------------------------------
# agent 产出锚定 $HIP，不写插件仓库。dsh 侧（pwsh/fs/vision）由工作区沙箱
# 强制（工作区对准 $HIP 目录后仓库天然是禁区）；桥 exec 是逃生舱不做硬拦，
# 只对「代码里出现仓库根路径字面量 + 写语义关键词」附一条 advisory。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REPO_WRITE_HINTS = (
    ".write(", ".write_text(", ".write_bytes(", "shutil.copy", "shutil.move",
    ".save(", "hipfile.save(", "render_frame(", "render_view(",
    "viewport_screenshot(", ".render(", "json.dump(", "pickle.dump(",
    ".export", "makedirs(", "mkdir(", ".touch(",
)


def _repo_write_advisory(code: str) -> str | None:
    """exec 代码疑似往插件仓库写文件时返回警告文本；否则 None。

    纯文本启发式（提醒层，不是安全边界）：路径由变量间接拼出的写检不到。
    """
    norm = code.replace("/", "\\").lower()
    root = _REPO_ROOT.replace("/", "\\").lower()
    if root not in norm:
        return None
    if not any(hint in norm for hint in _REPO_WRITE_HINTS):
        return None
    return (
        f"code appears to write into the dsh-houdini plugin repository ({_REPO_ROOT}). "
        "Agent outputs must anchor at $HIP (the directory of hou.hipFile.path()), "
        "never the plugin repo — write under $HIP instead (e.g. $HIP/screenshots, "
        "$HIP/render). If this write is truly intentional, explain why to the user."
    )


# --- raw-hou gate（默认开启，可由 Python Shell 临时关闭） -----------------------
# 软硬结合的硬边界：exec 代码里
# 「动词已覆盖的裸 hou 调用」与「疑似修改场景的裸 hou 调用」在执行前被拒，
# 报错指明对应动词；词表真覆盖不了的低层操作可用 allow_raw="理由" 一次性
# 豁免并留痕。allow_raw 不得旁路已被动词明确覆盖的调用，否则模型可以用一句
# 泛化理由重新提交整段 createNode/parm.set/cook 代码，使 gate 退化成 advisory。
# 高级开发调试仍可从 Houdini Python Shell 临时 set_raw_gate(False)。桥重启恢复安全默认。
_raw_gate = True


def set_raw_gate(on: bool) -> str:
    """开关 raw-hou gate（不进 exec 命名空间，用户从 Python Shell 调）。"""
    global _raw_gate
    _raw_gate = bool(on)
    return f"raw-hou gate {'ON' if _raw_gate else 'OFF'}"


# 疑似修改场景的方法名前缀。AST 只能看形状不能解析接收者，所以必须把
# 与 HOM 不重名的标准 Python 容器方法排除；否则只读聚合也会被错误拦截。
_GATE_MUTATING_PREFIXES = (
    "set", "add", "create", "delete", "destroy", "remove", "rename",
    "save", "cook", "render", "bake", "lock", "unlock", "install",
    "copy", "move", "enable", "disable", "press",
)
_GATE_SAFE_PYTHON_METHODS = {"setdefault"}
_GATE_READ_ONLY_PREFIX_COLLISIONS = {"displayNode", "renderNode"}


def _call_path(node: ast.AST) -> str | None:
    """Return a dotted call path rooted at ``hou`` when one is statically visible.

    ``hou.node(...)`` becomes ``hou.node`` and ``hou.hipFile.save()`` becomes
    ``hou.hipFile.save``.  Calls made through a local alias cannot be proven to
    be HOM here and are deliberately omitted instead of being mislabeled.
    """
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name) or current.id != "hou":
        return None
    return ".".join(["hou", *reversed(parts)])


def _python_set_names(tree: ast.AST) -> set[str]:
    """Find local names definitely initialized as Python ``set`` containers."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        is_set = isinstance(value, ast.Set) or (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "set"
        )
        if not is_set:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _is_safe_python_method(node: ast.Call, python_sets: set[str]) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr in _GATE_SAFE_PYTHON_METHODS or node.func.attr in _GATE_READ_ONLY_PREFIX_COLLISIONS:
        return True
    # Real trace: ``names = set(); names.add(...)`` is read-only scene
    # aggregation.  Treat only receivers statically proven to be Python sets as
    # safe; ``hou.Geometry.addAttrib`` and other HOM ``add*`` calls remain gated.
    return (
        node.func.attr == "add"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in python_sets
    )


def _raw_usage_analysis(code: str) -> dict:
    """Describe raw HOM syntax and gate-relevant mutations for UI/auditing.

    This is structured execution evidence, not a source-code regex.  It shares
    the same covered/suspected mutation rules as the Raw Gate so the client can
    distinguish harmless reads, blocked writes and audited exemptions.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    python_sets = _python_set_names(tree)
    direct: dict[str, int] = {}
    covered: dict[str, int] = {}
    suspected: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        path = _call_path(node.func)
        if path is not None:
            direct[path] = direct.get(path, 0) + 1
        attr = node.func.attr
        if path in ("hou.hipFile.save", "hou.hipFile.setName"):
            key = path.removeprefix("hou.")
            covered[key] = covered.get(key, 0) + 1
        elif attr in _RAW_HOU_VERB_MAP:
            covered[attr] = covered.get(attr, 0) + 1
        elif (
            attr == "set"
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Attribute)
            and node.func.value.func.attr in ("parm", "parmTuple")
        ):
            covered["parm().set"] = covered.get("parm().set", 0) + 1
        elif (
            not _is_safe_python_method(node, python_sets)
            and attr.startswith(_GATE_MUTATING_PREFIXES)
        ):
            suspected[attr] = suspected.get(attr, 0) + 1
    return {
        "directCalls": [
            {"name": name, "count": count}
            for name, count in sorted(direct.items())
        ],
        "coveredMutations": [
            {"name": name, "count": count, "verb": _RAW_HOU_VERB_MAP[name]}
            for name, count in sorted(covered.items())
        ],
        "suspectedMutations": [
            {"name": name, "count": count}
            for name, count in sorted(suspected.items())
        ],
    }


def _gate_message(code: str, allow_raw: str | None = None) -> str | None:
    """Return a pre-exec rejection, or ``None`` when this code may run.

    Verb-covered raw calls are never exemptible: use the verb or split the
    low-level operation into a separate, justified ``allow_raw`` call.  The
    exemption only applies to mutating calls for which the vocabulary has no
    direct intent-level operation.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None  # 语法错误交给 exec 自己报
    # Gate and audit must classify the same operation; formerly these loops
    # drifted independently (notably hipFile.setName versus Node.setName).
    usage = _raw_usage_analysis(code)
    covered = {item['name']: item['count'] for item in usage['coveredMutations']}
    mutating = {item['name']: item['count'] for item in usage['suspectedMutations']}
    if not covered and not mutating:
        return None
    if not covered and allow_raw:
        return None
    lines = [
        "raw-hou gate: blocked BEFORE execution (the verb vocabulary is the "
        "primary interface; raw hou is gated)."
    ]
    if covered:
        pairs = ", ".join(f"{a} -> {_RAW_HOU_VERB_MAP[a]}" for a in sorted(covered))
        lines.append(f"verb-covered raw call(s): {pairs} — use the verbs instead.")
    if mutating:
        lines.append(
            "possibly scene-mutating raw call(s) with no direct verb: "
            + ", ".join(sorted(mutating)) + "."
        )
    if covered:
        lines.append(
            "allow_raw cannot exempt verb-covered calls. Split genuine low-level "
            "work into a separate call and use verbs for the covered scene operations."
        )
    else:
        lines.append(
            "If no verb genuinely covers the operation, re-issue the SAME call with "
            "allow_raw=\"<why no verb fits>\" — a one-time exemption that is recorded "
            "in the trace (each exemption documents a vocabulary gap)."
        )
    return "\n".join(lines)


def _query_mutation_message(code: str) -> str | None:
    """Reject mutation intent before a ``houdini_query`` reaches Houdini."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    verbs = sorted({
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id in _MUTATING_VERB_NAMES
    })
    usage = _raw_usage_analysis(code)
    raw = [item["name"] for item in usage.get("coveredMutations", [])]
    raw += [item["name"] for item in usage.get("suspectedMutations", [])]
    if not verbs and not raw:
        return None
    detail = []
    if verbs:
        detail.append("mutating verb(s): " + ", ".join(verbs))
    if raw:
        detail.append("raw/suspected mutation(s): " + ", ".join(sorted(set(raw))))
    return (
        "houdini_query is read-only and rejected this code BEFORE execution ("
        + "; ".join(detail)
        + "). Use houdini_exec for scene changes and cooks."
    )


def _verb_value(value, _depth: int = 0):
    """把动词的入参/出参转成紧凑 JSON 安全形式（hou.Node → path，逐层递归）。"""
    if _depth > 8:
        return repr(value)
    if isinstance(value, hou.Node):
        try:
            return {"node": value.path()}
        except Exception:
            return {"node": repr(value)}
    if isinstance(value, (hou.Vector2, hou.Vector3, hou.Vector4)):
        return [_jsonable(float(x)) for x in value]
    if isinstance(value, hou.Color):
        return [_jsonable(float(x)) for x in (
            value.r(), value.g(), value.b(), value.a(),
        )]
    if isinstance(value, (hou.Matrix3, hou.Matrix4)):
        return [[_jsonable(float(x)) for x in row] for row in value]
    if isinstance(value, (list, tuple)):
        if len(value) > 50:
            return repr(value)
        return [_verb_value(v, _depth + 1) for v in value]
    if isinstance(value, dict):
        if len(value) > 50:
            return repr(value)
        return {str(k): _verb_value(v, _depth + 1) for k, v in value.items()}
    return _jsonable(value)


def _clip(obj) -> str:
    """序列化并截断，供 stdout 摘要行使用。"""
    try:
        text = json.dumps(obj, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):
        text = repr(obj)
    return text if len(text) <= _VERB_VALUE_CHARS else text[:_VERB_VALUE_CHARS] + "..."


def _operation_summary(name: str, result):
    """Small, untruncated evidence before verbose node lists/service metadata."""
    if not isinstance(result, dict):
        return None
    r = result.get('validation', result) if name == 'build_module' else result
    if name in ('set_parm','set_parms') and ('evaluation' in r or 'evaluations' in r):
        return r
    if name == 'set_parm' and 'patch' in r:
        return r
    if name == 'set_parms' and r.get('patched'):
        return {'node': r['node'], 'ok': r['ok'],
                'patches': {key: r['set'][key] for key in r['patched']}}
    if name == 'node_info':
        components = [{'name':p['name'],'components':p['components']} for p in r.get('parameters',[]) if len(p.get('components',[]))>1]
        return {k:r[k] for k in ('parent','type','version','visible','operation_card','usage_notes','operation_parameters','operation_parameters_missing','operation_parameter_scope','filter_mode','filter','parameter_count','total_parameter_count','next_action') if k in r} | {
            'tuple_components':components[:20], 'tuple_components_truncated':len(components)>20,
            'setting_cards':[{k:p[k] for k in ('name','type','components','default','menu','menu_dynamic') if k in p}
                             for p in r.get('parameters',[])[:24]],
            'setting_cards_truncated':len(r.get('parameters',[]))>24,
            'parameter_scope':'returned filtered parameter card only; retain components and menu set_value when summarizing'}
    if name in ('connect','disconnect_input'):
        return result
    if name == 'camera_fit':
        return result
    if name == 'geo_attrib_stats' and 'unique_count' in result:
        return result
    if name == 'create_spare_parms' and result.get('mode') == 'update_defaults':
        return result
    if name == 'bind_controls' or name == 'create_spare_parms' and result.get('mode') == 'layout':
        return {k: result[k] for k in ('ok','mode','controller','node','dry_run','applied','phase',
            'scene_writes','created','current_state_preserved','plan_sha256','bindings','restored','restore_errors','scope') if k in result}
    if name == 'hda_edit':
        return result
    if name == 'hda_set_interface':
        return {k: result[k] for k in ('ok', 'mode', 'node', 'dry_run', 'applied', 'phase',
                'scene_writes', 'before_sha256', 'after_sha256', 'current_state_preserved',
                'preserved_channels', 'restored', 'restore_errors', 'scope') if k in result}
    if name == 'geo_piece_stats' and 'shell_orientation' in r:
        return {k:r[k] for k in ('node','frame','group','status','reason','boundary_edges','nonmanifold_edges','orientation_conflicts','shell_orientation','zero_area_faces','extents','bounds_min','bounds_max') if k in r}
    if name in ('cop_layer_stats', 'cop_compare_layers', 'test_cop_controls'):
        return {k:r[k] for k in ('ok','status','semantic_status','node','output','output_port','controller',
                'frame','checked_at','scope','resolution','channels','statistics','sha256','freshness','cache',
                'formula','max_abs_difference','max_abs_error','tolerance','before','after','expected_delta',
                'restored','parameter_writes','coverage','case_id','reason','results') if k in r}
    if name not in ('verify_network', 'build_module', 'render_view', 'render_frame', 'geo_point_spacing','geo_check_interfaces','test_controls'):
        return None
    fields = ('ok','output','target','frame','checked_at','scope','scope_signature','node_count','nonempty','healthy',
              'warning_free','failure_reasons','next_action','file_status','pixel_status','semantic_status',
              'fresh','file_bytes','stale','user_state_restored','dry_run','valid','node','status',
              'expected','tolerance','order','closed','coordinate_space','coverage','pair_count',
              'min_distance','max_distance','failure_count','failures','failures_truncated','sequence_sha256',
              'results','geometry_sha256','contract_sha256','restored','baseline_sha256','controller',
              'baseline_interfaces','baseline_topology','baseline_domain','baseline','expectation','case_id','control_summary',
              'pair_tests','reason','parameter_writes','required_outputs','geometry_status','update_mode')
    out = {k: r[k] for k in fields if k in r}
    if name == 'build_module':
        out.update({k: result[k] for k in ('operation_advisories','operation_advisory_count',
                                          'operation_advisories_truncated','operation_advisory_scope') if k in result})
    if name in ('render_view','render_frame') and isinstance(r.get('framing'), dict):
        out['framing'] = r['framing']
    if 'framing_status' in r:
        out.update({k:r[k] for k in ('framing_status','products','reasons','render_started','projected_bounds_ndc','margin_px','depth_check','crop_reasons') if k in r})
    if result.get('interface_checks') is not None:
        out['interface_checks'] = result['interface_checks']
    for field in ('error_nodes','warning_nodes','errors','warnings'):
        if field in r:
            values = r[field]
            out[field] = [str(v)[:400] for v in values[:12]]
            out[field + '_count'] = len(values)
    fp = r.get('output_fingerprint') or r.get('source_fingerprint_after')
    if isinstance(fp, dict):
        out['source'] = {k: fp[k] for k in ('path','frame','signature','points','prims') if k in fp}
    check = r.get('check')
    if isinstance(check, dict):
        out['check'] = check
        out['pixels'] = check  # compatibility alias; matches the Python result
    return out


class _DispatchBlockedError(RuntimeError):
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = evidence


class _VerbArgumentError(TypeError):
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = evidence


def _make_tracer(name: str, fn, ledger: list, observed_nodes=None, impact=None):
    # Give a precise, zero-write recovery path for repeated discovery mistakes;
    # do not label TypeErrors raised inside the implementation as argument errors.
    try:
        discovery_signature = inspect.signature(fn)
    except (TypeError, ValueError):
        discovery_signature = None
    def wrapped(*args, **kwargs):
        if observed_nodes is not None and (name in _MUTATING_VERB_NAMES or name in
                ('describe', 'read_parms', 'list_parms', 'node_provenance', 'display_node', 'sop_output_node')):
            for value in list(args[:2]) + [kwargs[k] for k in ('node', 'parent', 'output', 'controller', 'camera', 'target') if k in kwargs]:
                try:
                    node = value if isinstance(value, hou.Node) else hou.node(value) if isinstance(value, str) and value.startswith('/') else None
                    if node is not None: observed_nodes[node.sessionId()] = node.path()
                except hou.Error:
                    pass
        if len(ledger) >= _VERB_ENTRY_LIMIT:
            error = f"verb ledger limit {_VERB_ENTRY_LIMIT} reached; split into smaller checkpoints"
            if len(ledger) == _VERB_ENTRY_LIMIT:
                ledger.append({"verb": name, "ok": False, "error": error, "args": [], "kwargs": {}, "ms": 0})
            raise RuntimeError(error)
        start = time.time()
        args_json = _verb_value(list(args))
        kwargs_json = {str(k): _verb_value(v) for k, v in kwargs.items()}
        try:
            if name in _MUTATING_VERB_NAMES:
                failed = next((entry for entry in ledger if not entry.get('ok', False)), None)
                if failed is not None:
                    raise _DispatchBlockedError(
                        f"{name} blocked before dispatch: earlier verb {failed['verb']} failed; "
                        "this exec cannot commit. Read-only diagnostics may continue; repair in a new exec.",
                        {'ok': False, 'phase': 'prior_verb_failure', 'scene_writes': 0,
                         'dispatched': False, 'failed_verb': failed['verb']})
            if discovery_signature is not None:
                try:
                    discovery_signature.bind(*args, **kwargs)
                except TypeError as error:
                    hint = ( ' parent is an existing creation network, not a category. '
                             'For SOPs use node_info(existing_geo, "box"); if no geometry container exists, '
                             'first create one with tab_create("/obj", "geo", name=...) through houdini_exec.'
                             if name == 'node_info' else '')
                    message = (f'{error}. Call {name}{discovery_signature}. '
                               f'Use verb_help("{name}") for return type and documentation. '
                               'This call was not dispatched and made no scene writes.' + hint)
                    raise _VerbArgumentError(message, {'ok': False, 'phase': 'argument_binding',
                        'scene_writes': 0, 'dispatched': False, 'signature': str(discovery_signature),
                        'next_action': f'verb_help("{name}")'}) from error
            targets = []
            edits_content = name in _MUTATING_VERB_NAMES and name not in _OBSERVATION_VERBS
            if name in ('hda_set_interface', 'create_spare_parms', 'bind_controls', 'hda_edit') and kwargs.get('dry_run') is True:
                edits_content = False
            if impact is not None and edits_content:
                impact['attempted'] = True
                if name in _GLOBAL_EDIT_VERBS:
                    impact['global'] = True
                for value in list(args[:2]) + [kwargs[k] for k in ('node', 'parent', 'output', 'controller', 'target', 'src', 'dst') if k in kwargs]:
                    try:
                        node = value if isinstance(value, hou.Node) else hou.node(value) if isinstance(value, str) and value.startswith('/') else None
                        if node is not None:
                            targets.append(node)
                    except hou.Error:
                        impact['unavailable'] = True
                if not targets:
                    impact['global'] = True
                _observe_impact(targets, impact, descendants=name in ('delete_node', 'rename_node'))
            result = fn(*args, **kwargs)
            if impact is not None:
                if edits_content:
                    impact['last_edit_ledger_index'] = len(ledger) + 1
                    if name != 'delete_node':
                        _observe_impact(targets, impact, descendants=name == 'rename_node')
                if name in ('test_controls', 'test_cop_controls') and isinstance(result, dict) and result.get('restored') is not True:
                    impact['global'] = True
                    impact['attempted'] = True
            entry = {
                "verb": name,
                "ts": round(start, 3),  # 绝对时间戳（epoch 秒）：跨 exec 重建真实调用顺序
                "args": args_json,
                "kwargs": kwargs_json,
                "ok": True,
                "result": _verb_value(result),
                "ms": round((time.time() - start) * 1000, 1),
            }
            check = result.get("validation", result) if isinstance(result, dict) else None
            if name=='set_parm' and isinstance(check,dict) and isinstance(check.get('evaluation'),dict):
                status=check['evaluation'].get('status')
                entry['check_status']={'failed':'failed','warning':'warning','unverified':'unverified'}.get(status,'passed')
                entry['check_scope']='parameter evaluation only; geometry effect unverified'
            if name in ("set_parms", "cook_node", "verify_network", "build_module", "render_frame", "render_view", "camera_fit", "geo_point_spacing","geo_check_interfaces","test_controls", "cop_layer_stats", "cop_compare_layers", "test_cop_controls") and isinstance(check, dict):
                if check.get('status') in ('unverified', 'not_evaluated_manual', 'not_cooked_manual'):
                    entry['check_status'] = 'unverified'
                elif check.get("ok") is False or check.get("errors") or check.get("fresh") is False:
                    entry["check_status"] = "failed"
                elif check.get("healthy") is False or check.get("warning_free") is False or check.get('pixel_status') == 'needs_review':
                    entry["check_status"] = "warning"
                else:
                    entry["check_status"] = "passed" if not result.get("dry_run") else "unverified"
            summary = _operation_summary(name, result)
            if summary is not None:
                entry['summary'] = _jsonable(summary)
            ledger.append(entry)
            kw = f", {_clip(kwargs_json)}" if kwargs_json else ""
            print(f"[verb] {name}({_clip(args_json)}{kw}) -> {_clip(entry['result'])}  ({entry['ms']}ms)")
            return result
        except BaseException as e:  # 记录失败调用并原样抛出，不改变原语义
            if impact is not None and name in ('test_controls', 'test_cop_controls'):
                impact['global'] = True
                impact['attempted'] = True
            ledger.append({
                "verb": name,
                "ts": round(start, 3),
                "args": args_json,
                "kwargs": kwargs_json,
                "ok": False,
                "error": str(e),
                "ms": round((time.time() - start) * 1000, 1),
            })
            if isinstance(e, dsh_hou_helpers.CheckpointError):
                ledger[-1]['summary'] = _jsonable(_operation_summary(name, e.evidence))
                ledger[-1]['check_status'] = 'failed'
            if isinstance(e, (dsh_hou_helpers.PreflightError, dsh_hou_helpers.ParameterPatchError,
                              _DispatchBlockedError, _VerbArgumentError)):
                ledger[-1]['summary'] = _jsonable(e.evidence)
                ledger[-1]['check_status'] = 'failed'
            kw = f", {_clip(kwargs_json)}" if kwargs_json else ""
            print(f"[verb] {name}({_clip(args_json)}{kw}) -> ERROR: {e}")
            raise
    return wrapped


def _raise_caught_verb_failure(verb_ledger: list) -> None:
    """Fail an exec that caught a verb exception and continued.

    The tracer records an exception before re-raising it. Agent code used to
    catch that exception, print diagnostics, and let the outer exec commit a
    potentially partial scene as ``ok: true``. This check runs while the same
    undo group is still open, so the normal failure path can roll back every
    Houdini-undoable edit in the batch.
    """
    failed = [entry for entry in verb_ledger if not entry.get("ok", False)]
    if not failed:
        return
    names = ", ".join(str(entry.get("verb", "?")) for entry in failed[:8])
    if len(failed) > 8:
        names += f", +{len(failed) - 8} more"
    raise RuntimeError(
        "agent code caught and suppressed a verb exception "
        f"({names}); the exec is failed so undoable scene edits can roll back. "
        "Do not catch mutation failures unless you re-raise them."
    )


def run_code(code: str, allow_raw: str | None = None,
             owner_session: str | None = None,
             owner_call: str | None = None,
             read_only: bool = False) -> dict:
    """Execute code with `hou` available; capture stdout/stderr and `__result__`.

    Must run on Houdini's main thread (see module docstring) — callers route
    through `_execute`. BaseException is caught so agent code calling
    `sys.exit()` or raising KeyboardInterrupt cannot kill a handler/job thread
    or leave a job stuck in `running` forever.

    allow_raw：词表未覆盖的低层修改的一次性豁免理由（见 _gate_message）；
    它不能旁路已被动词覆盖的裸调用。豁免会打印 [gate] 行进 stdout，进结果与 trace。
    """
    if threading.get_ident() != _HOU_THREAD_ID:
        raise RuntimeError("run_code must execute on Houdini's owning thread")
    global _EXECUTION_SEQUENCE
    _EXECUTION_SEQUENCE += 1
    execution_sequence = _EXECUTION_SEQUENCE
    verb_ledger: list = []
    observed_nodes = {}
    impact = {'nodes': {}, 'attempted': False, 'global': False, 'truncated': False, 'unavailable': False}
    namespace = {"hou": hou}
    for _name, _fn in _VERBS.items():
        if read_only and _name in _MUTATING_VERB_NAMES:
            continue
        namespace[_name] = _make_tracer(_name, _fn, verb_ledger, observed_nodes, impact)
    stdout = _CappedStringIO(_MAX_STREAM_BYTES)
    stderr = _CappedStringIO(_MAX_STREAM_BYTES)
    error = None
    rollback = None
    raw_usage = _raw_usage_analysis(code)
    gate_outcome = "not_applicable"
    with _exec_lock, dsh_hou_helpers._execution_owner(owner_session, owner_call), dsh_hou_helpers._track_created_nodes() as created_nodes:
        # Clear even for preflight rejection and snapshot before releasing the
        # execution lock, so one request cannot inherit another request's media.
        dsh_hou_helpers._PRODUCED_IMAGES.clear()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                error = _forbidden_hip_lifecycle_message(code)
                if error is not None:
                    gate_outcome = "forbidden"
                if error is None and read_only:
                    error = _query_mutation_message(code)
                    if error is not None:
                        gate_outcome = "read_only_blocked"
                if error is None and _raw_gate:
                    error = _gate_message(code, allow_raw)  # None = 放行
                    if error is not None:
                        gate_outcome = "blocked"
                if error is None:
                    has_covered = bool(raw_usage.get("coveredMutations"))
                    has_suspected = bool(raw_usage.get("suspectedMutations"))
                    has_direct = bool(raw_usage.get("directCalls"))
                    if _raw_gate and allow_raw and has_suspected and not has_covered:
                        gate_outcome = "exempted"
                        print(f"[gate] raw-hou exemption: {allow_raw}")
                    elif not _raw_gate and (has_covered or has_suspected):
                        gate_outcome = "disabled"
                    elif has_direct and not has_covered and not has_suspected:
                        gate_outcome = "read_only"
                    elif has_covered or has_suspected:
                        gate_outcome = "allowed"
                    compiled = compile(code, "<dsh-houdini>", "exec")
                    undo_enabled = bool(hou.undos.areEnabled())
                    if undo_enabled:
                        label = f"dsh-houdini exec {uuid.uuid4().hex}"
                        ownership_before = dict(dsh_hou_helpers._OWNED_NODE_SESSIONS)
                        try:
                            with hou.undos.group(label):
                                exec(compiled, namespace)
                                _raise_caught_verb_failure(verb_ledger)
                        except BaseException:
                            original_error = traceback.format_exc()
                            applied = False
                            rollback_error = None
                            removed_residuals = []
                            try:
                                labels = list(hou.undos.undoLabels())
                                if labels and labels[0] == label:
                                    hou.undos.performUndo()
                                    applied = True
                                    dsh_hou_helpers._OWNED_NODE_SESSIONS.clear()
                                    dsh_hou_helpers._OWNED_NODE_SESSIONS.update(ownership_before)
                                    removed_residuals = dsh_hou_helpers._cleanup_failed_creations(created_nodes, ownership_before)
                            except BaseException as undo_error:
                                rollback_error = str(undo_error)
                            rollback = {
                                "supported": True,
                                "applied": applied,
                                "scope": "Houdini undoable scene edits only",
                            }
                            if not applied and rollback_error is None:
                                rollback["note"] = (
                                    "exec failed but produced no matching undo group；"
                                    "file I/O/HDA library edits and non-undoable effects cannot roll back"
                                )
                            if rollback_error is not None:
                                rollback["error"] = rollback_error
                            if removed_residuals:
                                rollback['removed_created_residuals'] = removed_residuals
                            error = original_error
                    else:
                        try:
                            exec(compiled, namespace)
                            _raise_caught_verb_failure(verb_ledger)
                        except BaseException:
                            rollback = {
                                "supported": False,
                                "applied": False,
                                "scope": "Houdini undo stack disabled (commonly headless)",
                            }
                            error = traceback.format_exc()
            except BaseException:
                if error is None:
                    error = traceback.format_exc()
        images = [p for p in dsh_hou_helpers._PRODUCED_IMAGES if os.path.isfile(p)]
    envelope = {
        "ok": error is None,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
    }
    mutation_attempted = any(v['verb'] in _MUTATING_VERB_NAMES and
        not (v['verb'] in ('hda_set_interface', 'create_spare_parms', 'bind_controls', 'hda_edit') and (v.get('summary') or {}).get('scene_writes') == 0)
        for v in verb_ledger) or bool(raw_usage.get('coveredMutations') or raw_usage.get('suspectedMutations'))
    if error is None:
        transaction_status = 'committed' if mutation_attempted else 'no_scene_change'
    elif rollback and rollback.get('applied') and not rollback.get('error'):
        transaction_status = 'rolled_back'
    elif not mutation_attempted or gate_outcome in ('blocked', 'forbidden', 'read_only_blocked'):
        transaction_status = 'no_scene_change'
    elif not created_nodes and not raw_usage.get('coveredMutations') and not raw_usage.get('suspectedMutations') and all(
            v.get('summary',{}).get('scene_writes') == 0 for v in verb_ledger if v['verb'] in _MUTATING_VERB_NAMES):
        transaction_status = 'no_scene_change'
    else:
        transaction_status = 'recovery_unverified'
    identities = sorted(set(observed_nodes) | created_nodes | set(impact['nodes']))
    states = []
    for identity in identities[:64]:
        node = hou.nodeBySessionId(identity)
        states.append({'identity': identity, 'prior_path': observed_nodes.get(identity, impact['nodes'].get(identity)),
                       'exists': node is not None, 'path': node.path() if node else None})
    envelope['transaction'] = {'status': transaction_status, 'scope': 'Houdini undoable scene edits only; file/external side effects are separate',
                               'nodes': states, 'nodes_truncated': len(identities) > 64,
                               'coverage': 'created identities, primary arguments and bounded native dependency cone; not all implicit dependencies'}
    if transaction_status != 'no_scene_change':
        _observe_impact([node for identity in created_nodes if (node := hou.nodeBySessionId(identity)) is not None], impact)
        if raw_usage.get('coveredMutations') or raw_usage.get('suspectedMutations'):
            impact['global'] = True
            impact['attempted'] = True
    else:
        impact = {'nodes': {}, 'attempted': False, 'global': False, 'truncated': False, 'unavailable': False}
    envelope['execution'] = {'runtime_id': _RUNTIME_ID, 'sequence': execution_sequence,
        'observed_at': time.time(), 'frame': float(hou.frame()), 'hip_path': hou.hipFile.path(),
        'update_mode': dsh_hou_helpers.scene_info()['update_mode'],
        'owner_session': owner_session, 'read_only': read_only,
        'impact': {**{k:v for k,v in impact.items() if k != 'nodes'},
            'nodes': [{'identity': identity, 'path': path} for identity, path in impact['nodes'].items()],
            'scope': 'bounded native wires and last-cook expression dependents; excludes unobserved GUI, dynamic and external changes'}}
    # 本次 exec 产出的图片（render_frame/render_view/viewport_screenshot 登记）：
    # host 侧经 /media 端点把字节拉回会话工作区，vision/fs 工具才读得到
    # （工作区沙箱；2026-08-19 草地 trace：vision_glance 读 $HIP 截图被拒）。
    if images:
        envelope["images"] = images
    if verb_ledger:
        envelope["verbs"] = verb_ledger
        evidence = [{'ledgerIndex': i + 1, 'verb': v['verb'], **v['summary']}
                    for i, v in enumerate(verb_ledger) if isinstance(v.get('summary'), dict)]
        if evidence:
            envelope['evidence'] = evidence
        checks = [{"verb": v["verb"], "status": v["check_status"]}
                  for v in verb_ledger if v.get("check_status") in ("failed", "warning", "unverified")]
        if checks:
            envelope["checks"] = checks
    if (
        raw_usage.get("directCalls")
        or raw_usage.get("coveredMutations")
        or raw_usage.get("suspectedMutations")
        or gate_outcome not in ("not_applicable", "read_only")
    ):
        raw_usage["gateOutcome"] = gate_outcome
        if allow_raw:
            raw_usage["exemptionReason"] = allow_raw
        envelope["rawUsage"] = raw_usage
    advisories = [a for a in (_raw_hou_advisory(code, verb_ledger), _repo_write_advisory(code)) if a]
    if advisories:
        envelope["advisory"] = "\n".join(advisories)
    if rollback is not None:
        envelope["rollback"] = rollback
    if error is not None:
        envelope["error"] = error
    if error is None and "__result__" in namespace:
        result = _jsonable(namespace["__result__"])
        try:
            if len(json.dumps(result, allow_nan=False)) > _MAX_RESULT_BYTES:
                result = f"[dsh-houdini: __result__ serialized to more than {_MAX_RESULT_BYTES} bytes; omitted]"
        except (TypeError, ValueError):
            result = repr(result)
        envelope["result"] = result
    bindings = []
    for item in envelope.get('evidence', []):
        if len(bindings) >= 64:
            break
        if item.get('verb') in ('render_view', 'render_frame'):
            source = item.get('source')
            target = item.get('target') or (source.get('path') if isinstance(source, dict) else None)
        else:
            target = item.get('output') if isinstance(item.get('output'), str) else item.get('node')
            if item.get('verb') == 'cop_compare_layers':
                target = (item.get('after') or {}).get('node')
        if isinstance(target, str) and target.startswith('/'):
            try:
                node = hou.node(target)
                binding = {'ledger_index': item['ledgerIndex'], 'verb': item['verb'],
                                 'path': target, 'identity': node.sessionId() if node else None,
                                 'exists': node is not None}
                if item.get('verb') == 'cop_compare_layers':
                    binding['dependencies'] = [{k: m[k] for k in ('node', 'identity', 'output') if k in m}
                        for m in (item.get('before'), item.get('after'), item.get('expected_delta')) if isinstance(m, dict)]
                bindings.append(binding)
            except Exception:
                envelope['execution']['outputs_unavailable'] = True
    envelope['execution']['outputs'] = bindings
    return envelope


# --- main-thread execution queue --------------------------------------------
# `hou` is only safe on Houdini's main thread. HTTP handler / job threads never
# touch `hou` directly: they enqueue work and block until the main-thread pump
# reports back. The pump is a QTimer in GUI mode and the __main__ loop headless.
_work_queue: queue.Queue = queue.Queue()
_pump_active = False   # whether a main-thread pump is draining _work_queue
_pump_timer = None     # GUI-mode QTimer (kept alive; stopped by stop())


def _pump() -> None:
    """Main-thread: run every queued work item, FIFO. Never raises."""
    if threading.get_ident() != _HOU_THREAD_ID:
        raise RuntimeError("Houdini pump must run on its owning thread")
    while True:
        try:
            func, done, holder = _work_queue.get_nowait()
        except queue.Empty:
            return
        if holder.get("cancelled"):
            done.set()
            continue
        try:
            holder["result"] = func()
        except BaseException as exc:  # a failing task must not kill the pump
            holder["error"] = exc
        finally:
            done.set()


def _execute(func, timeout=None):
    """Run `func` on Houdini's main thread and wait for its return value.

    Owning-thread callers may execute inline (including disposable hython).
    Worker callers must have a live pump; never fall back to worker-thread HOM.
    """
    if threading.get_ident() == _HOU_THREAD_ID:
        return func()
    if not _pump_active:
        raise RuntimeError("Houdini main-thread pump is unavailable; refusing execution on a worker thread")
    done = threading.Event()
    holder: dict = {}
    _work_queue.put((func, done, holder))
    deadline = time.monotonic() + timeout if timeout is not None else None
    while not done.wait(0.25):
        if deadline is not None and time.monotonic() >= deadline:
            holder['cancelled'] = True
            raise TimeoutError('Houdini main-thread queue is busy; metadata observation expired')
        if not _pump_active:
            holder["cancelled"] = True
            raise RuntimeError("Houdini main-thread pump stopped before queued execution completed")
    if "error" in holder:
        raise holder["error"]
    return holder["result"]


def _install_gui_pump() -> bool:
    """GUI mode: drain the work queue with a QTimer owned by the main thread.

    Must be called from the main thread (the documented entry points are).
    """
    global _pump_active, _pump_timer
    try:
        try:
            from PySide6 import QtCore
        except ImportError:
            from PySide2 import QtCore
        app = QtCore.QCoreApplication.instance()
        if app is None:
            return False
        timer = QtCore.QTimer(app)
        timer.setInterval(30)
        timer.timeout.connect(_pump)
        timer.start()
        _pump_timer = timer
        _pump_active = True
        return True
    except Exception:
        return False


def _prune_jobs() -> None:
    """Drop expired terminal jobs and cap the registry; queued/running stay."""
    now = time.time()
    with _jobs_lock:
        for job_id in list(_jobs):
            if _jobs[job_id]["status"] in ("done", "failed", "cancelled"):
                if now - _job_meta.get(job_id, now) > _JOB_RETENTION_SECONDS:
                    _jobs.pop(job_id, None)
                    _job_meta.pop(job_id, None)
        if len(_jobs) > _MAX_JOBS:
            terminal = sorted(
                (jid for jid, j in _jobs.items()
                 if j["status"] in ("done", "failed", "cancelled")),
                key=lambda jid: _job_meta.get(jid, 0),
            )
            for job_id in terminal[: len(_jobs) - _MAX_JOBS]:
                _jobs.pop(job_id, None)
                _job_meta.pop(job_id, None)


def _job_activity() -> dict:
    """Return non-terminal job counts without exposing job payloads."""
    with _jobs_lock:
        queued = sum(1 for job in _jobs.values() if job.get("status") == "queued")
        running = sum(1 for job in _jobs.values() if job.get("status") == "running")
    return {
        "activeJobs": queued + running,
        "queuedJobs": queued,
        "runningJobs": running,
    }


def _job_body(job_id: str, code: str, allow_raw: str | None = None,
              owner_session: str | None = None,
              owner_call: str | None = None) -> dict | None:
    """Job work item, run on the main thread via `_execute`.

    Re-checks cancellation AT execution time: a job cancelled while waiting in
    the queue returns None and its code never runs — no scene side effects.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None or job["status"] == "cancelled":
            return None
        job["status"] = "running"
    return run_code(code, allow_raw, owner_session, owner_call)


def _run_job(job_id: str, code: str, allow_raw: str | None = None,
             owner_session: str | None = None,
             owner_call: str | None = None) -> None:
    try:
        outcome = _execute(
            lambda: _job_body(job_id, code, allow_raw, owner_session, owner_call)
        )
    except BaseException:
        outcome = {"ok": False, "stdout": "", "stderr": "", "error": traceback.format_exc()}
    if outcome is None:
        return  # cancelled while queued: code never ran, scene untouched
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None or job["status"] == "cancelled":
            return
        job.update(outcome)
        job["status"] = "done" if outcome["ok"] else "failed"
        _job_meta[job_id] = time.time()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep Houdini's console quiet
        pass

    def handle_one_request(self) -> None:  # noqa: N802 (http.server naming)
        try:
            super().handle_one_request()
        except (ConnectionError, TimeoutError):
            # A client (probe, killed browser tab, health check) went away
            # mid-request. Harmless — drop the connection and keep serving.
            self.close_connection = True

    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        if self.path == "/health":
            try:
                self._send({
                    "ok": True,
                    "houVersion": _HOU_VERSION,
                    "rawGate": _raw_gate,
                    "executionContractVersion": _EXECUTION_CONTRACT_VERSION,
                    "runtimeId": _RUNTIME_ID,
                    "verbCatalog": {
                        "hash": _VERB_CATALOG_HASH,
                        "count": len(_VERB_NAMES),
                        "names": list(_VERB_NAMES),
                    },
                    **_job_activity(),
                })
            except Exception:
                self._send({"ok": False, "error": traceback.format_exc()}, status=500)
            return
        # /media?path=<abs>：把桥进程读得到的图片字节回传给 host——host 再写进
        # 会话工作区，弥合「$HIP 产物」与「工作区沙箱的 vision/fs 工具」之间的
        # 路径断层。只读、限图片扩展名、限大小；不碰 hou，handler 线程安全。
        if urllib.parse.urlparse(self.path).path == "/media":
            try:
                params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                target = os.path.abspath(params.get("path", [""])[0])
                ext = os.path.splitext(target)[1].lower()
                if ext not in _MEDIA_EXTS:
                    self._send({"ok": False, "error": f"media type not allowed: {ext or '(none)'}"}, status=403)
                    return
                if not os.path.isfile(target):
                    self._send({"ok": False, "error": f"no such file: {target}"}, status=404)
                    return
                size = os.path.getsize(target)
                if size > _MEDIA_MAX_BYTES:
                    self._send({"ok": False, "error": f"file too large ({size} > {_MEDIA_MAX_BYTES})"}, status=413)
                    return
                with open(target, "rb") as fh:
                    data = fh.read(_MEDIA_MAX_BYTES + 1)
                if len(data) > _MEDIA_MAX_BYTES:
                    self._send({"ok": False, "error": "media grew beyond size limit"}, status=413)
                    return
                self.send_response(200)
                self.send_header("content-type", _MEDIA_MIME.get(ext, "application/octet-stream"))
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self._send({"ok": False, "error": traceback.format_exc()}, status=500)
            return
        self._send({"ok": False, "error": f"unknown endpoint {self.path}"}, status=404)

    def do_POST(self) -> None:  # noqa: N802 (http.server naming)
        try:
            # Reject browser simple-request CSRF against this trusted loopback
            # execution service. No CORS permission is granted. This does not
            # make arbitrary local Python or the Raw Gate a security sandbox.
            if self.headers.get('origin') is not None or self.headers.get_content_type() != 'application/json':
                self.close_connection = True
                self._send({"ok": False, "error": "JSON requests from trusted local clients only (no browser Origin)"}, status=403)
                return
            length = int(self.headers.get("content-length") or 0)
            if length < 0 or length > _MAX_BODY_BYTES or self.headers.get('transfer-encoding'):
                self.close_connection = True
                self._send(
                    {"ok": False, "error": f"invalid request body length/encoding ({length}, max {_MAX_BODY_BYTES})"},
                    status=413,
                )
                return
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                self._send({"ok": False, "error": "JSON body must be an object"}, status=400)
                return
            self._route(body)
        except (ValueError, UnicodeError) as error:
            self.close_connection = True
            self._send({"ok": False, "error": str(error)}, status=400)
        except Exception:
            self._send({"ok": False, "error": traceback.format_exc()}, status=500)

    def _route(self, body: dict) -> None:
        if self.path == '/requests/status':
            if set(body)!={'request_ref','owner_session'} or not all(isinstance(v,str) and v for v in body.values()):
                self._send({'ok':False,'error':'request_ref and owner_session required'},status=400)
                return
            self._send({'ok':True,'stdout':'','stderr':'',
                        'requestReceipt':(_request_registry.recent(body['owner_session']) if body['request_ref']=='index'
                                          else _request_registry.status(body['request_ref'],body['owner_session']))})
            return
        if self.path == '/context':
            if type(body.get('schema_version')) is not int or body.get('schema_version') != 1 or set(body) != {'schema_version'}:
                self._send({'ok': False, 'error': 'context requires schema_version=1 only'}, status=400)
                return
            from dsh_context import scene_context
            try:
                self._send({'ok': True, 'result': _execute(
                    lambda: scene_context(_RUNTIME_ID, _HOU_THREAD_ID), timeout=1.5)})
            except (TimeoutError, RuntimeError) as exc:
                self._send({'ok': False, 'status': 'unavailable', 'reason': str(exc)})
            return
        if self.path in ("/exec", "/jobs"):
            expected = body.get("expected_contract")
            if expected is not None and expected != {"version": _EXECUTION_CONTRACT_VERSION, "hash": _VERB_CATALOG_HASH}:
                self._send({"ok": False, "error": "execution contract mismatch; Repair and restart runtime"}, status=409)
                return
            if not isinstance(body.get("code"), str):
                self._send({"ok": False, "error": "code must be a string"}, status=400)
                return
        if self.path == "/exec":
            code = str(body.get("code", ""))
            allow_raw = body.get("allow_raw")
            allow_raw = str(allow_raw) if allow_raw else None
            owner_session = body.get("owner_session")
            owner_call = body.get("owner_call")
            read_only_value = body.get("read_only")
            if type(read_only_value) not in (bool, str, type(None)) or read_only_value not in (None, True, False, "true", "false"):
                self._send({"ok": False, "error": "read_only must be a boolean or true/false string"}, status=400)
                return
            read_only = read_only_value is True or str(read_only_value).strip().lower() in ("1", "true", "yes", "on")
            invoke=lambda: run_code(
                code,
                allow_raw,
                str(owner_session) if owner_session else None,
                str(owner_call) if owner_call else None,
                read_only,
            )
            ref=body.get('request_ref')
            if ref is None:
                self._send(_execute(invoke))
                return
            try:
                admitted=_request_registry.reserve(ref,owner_session,body)
            except ValueError as error:
                self._send({'ok':False,'error':str(error)},status=409)
                return
            if not admitted:
                receipt=_request_registry.status(ref,owner_session)
                if receipt['status']=='done':self._send(receipt['result'])
                else:self._send({'ok':False,'stdout':'','stderr':'','requestReceipt':receipt,
                                'error':'Request already admitted; retrieve status instead of resubmitting.'})
                return
            def tracked():
                _request_registry.running(ref)
                try:result=invoke()
                except BaseException:
                    result={'ok':False,'stdout':'','stderr':'','error':traceback.format_exc()}
                result['requestReceipt']={'request_ref':ref,'runtime_id':_RUNTIME_ID,'status':'done'}
                _request_registry.complete(ref,result)
                return result
            try:
                result=_execute(tracked)
            except BaseException as error:
                # Only a still queued receipt proves that HOM never began.
                if _request_registry.status(ref,owner_session)['status']=='queued':
                    _request_registry.fail_before_dispatch(ref,error)
                raise
            self._send(result)
            return
        if self.path == "/jobs":
            ref=body.get('request_ref')
            owner_session=body.get('owner_session')
            if ref is not None:
                try:admitted=_request_registry.reserve(ref,owner_session,{**body,'request_kind':'job_submit'})
                except ValueError as error:
                    self._send({'ok':False,'error':str(error)},status=409);return
                if not admitted:
                    receipt=_request_registry.status(ref,owner_session)
                    self._send(receipt['result'] if receipt['status']=='done' else {'requestReceipt':receipt})
                    return
            job_id = uuid.uuid4().hex[:12]
            with _jobs_lock:
                overloaded = sum(j['status'] in ('queued', 'running') for j in _jobs.values()) >= _MAX_ACTIVE_JOBS
                if not overloaded:
                    _jobs[job_id] = {
                        "jobId": job_id, "status": "queued",
                        "ok": False, "stdout": "", "stderr": "",
                    }
                    _job_meta[job_id] = time.time()
            if overloaded:
                if ref is not None:_request_registry.fail_before_dispatch(ref,'job admission refused: active job limit')
                self._send({"ok": False, "error": "too many active Houdini jobs; await existing work"}, status=429)
                return
            allow_raw = body.get("allow_raw")
            allow_raw = str(allow_raw) if allow_raw else None
            owner_session = body.get("owner_session")
            owner_call = body.get("owner_call")
            worker=threading.Thread(
                target=_run_job,
                args=(
                    job_id,
                    str(body.get("code", "")),
                    allow_raw,
                    str(owner_session) if owner_session else None,
                    str(owner_call) if owner_call else None,
                ),
                daemon=True,
            )
            try:worker.start()
            except BaseException:
                with _jobs_lock:
                    _jobs.pop(job_id,None);_job_meta.pop(job_id,None)
                if ref is not None:_request_registry.fail_before_dispatch(ref,'job worker did not start')
                raise
            handle={'jobId':job_id}
            if ref is not None:
                handle['requestReceipt']={'request_ref':ref,'runtime_id':_RUNTIME_ID,
                                          'status':'job_submitted','jobId':job_id,
                                          'note':'Admission confirmed, not execution completion; collect with houdini_job_status.'}
                _request_registry.complete(ref,handle)
            _prune_jobs()
            self._send(handle)
            return
        parts = [p for p in self.path.split("/") if p]
        if len(parts) == 3 and parts[0] == "jobs":
            with _jobs_lock:
                job = _jobs.get(parts[1])
                if job is not None and parts[2] == "cancel" and job["status"] == "queued":
                    job["status"] = "cancelled"
                    _job_meta[parts[1]] = time.time()
                elif job is not None and parts[2] == "cancel" and job["status"] == "running":
                    job["advisory"] = "Running HOM cannot be interrupted; job remains running and its actual result will be retained."
            if job is None:
                self._send({"ok": False, "error": f"unknown job {parts[1]}"}, status=404)
                return
            if parts[2] == "status":
                # 长轮询：body 带 wait（秒，上限 600）时在本 handler 线程里
                # 等到终态或超时一次返回——调用方不必 sleep 循环刷状态。
                # 注意必须在 _jobs_lock 之外等待：持锁等待会把 _run_job
                # 标记终态的路堵死（plain Lock，且内层再取同锁即自死锁）。
                wait = body.get("wait")
                if isinstance(wait, (int, float)) and wait > 0:
                    deadline = time.time() + min(float(wait), 600.0)
                    while time.time() < deadline:
                        with _jobs_lock:
                            terminal = job["status"] not in ("queued", "running")
                        if terminal:
                            break
                        time.sleep(0.25)
            if parts[2] in ("status", "cancel"):
                with _jobs_lock:
                    snapshot = dict(job)
                self._send(snapshot)
                return
        self._send({"ok": False, "error": f"unknown endpoint {self.path}"}, status=404)


_server: ThreadingHTTPServer | None = None


def stop() -> None:
    """Stop the in-process bridge server and GUI pump (if any); idempotent."""
    global _server, _pump_active, _pump_timer
    server = _server
    _server = None
    if server is not None:
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass
    timer = _pump_timer
    _pump_timer = None
    _pump_active = False
    while True:
        try:
            _func, done, holder = _work_queue.get_nowait()
        except queue.Empty:
            break
        holder["cancelled"] = True
        holder["error"] = RuntimeError("Houdini bridge stopped before queued work executed")
        done.set()
    if timer is not None:
        try:
            timer.stop()
        except Exception:
            pass


def start(port: int = 8765, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """Start the bridge in a daemon thread; restarts if one is already running.

    In GUI mode call this from the main thread (Python Shell / menu — the
    documented entry points are) so the execution pump binds to the Qt loop.
    """
    global _server, _RUNTIME_ID, _request_registry
    if threading.get_ident() != _HOU_THREAD_ID:
        raise RuntimeError("start must run on Houdini's owning thread")
    stop()
    _RUNTIME_ID=uuid.uuid4().hex
    _request_registry=RequestRegistry(_RUNTIME_ID)
    if hou.isUIAvailable() and not _install_gui_pump():
        raise RuntimeError("Cannot start bridge without a Houdini GUI main-thread pump")
    try:
        server = ThreadingHTTPServer((host, port), _Handler)
    except BaseException:
        stop()
        raise
    _server = server
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True).start()
    print(f"[dsh-houdini] bridge serving on http://{host}:{port}")
    return server


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        hou.hipFile.load(sys.argv[1])
        print(f"[dsh-houdini] loaded scene {sys.argv[1]}")
    start()
    _pump_active = True  # headless: the main thread below IS the pump
    while True:  # hython exits when the script returns; keep the session alive
        _pump()
        time.sleep(0.05)
