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

# --- limits (kept small so a runaway agent cannot exhaust Houdini) ----------
_MAX_STREAM_BYTES = 1024 * 1024          # cap captured stdout/stderr per exec
_MAX_RESULT_BYTES = 4 * 1024 * 1024      # cap the serialized __result__
_MAX_BODY_BYTES = 16 * 1024 * 1024       # reject oversized HTTP bodies
_MAX_RESULT_DEPTH = 20                   # recursion depth for __result__ coercion
_MAX_RESULT_ITEMS = 1000                 # items per container before repr fallback
_MAX_JOBS = 1000                         # terminal-job registry cap
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
        signature = str(inspect.signature(fn))
    except Exception:
        signature = None
    return {
        "name": key,
        "signature": signature,
        "doc": inspect.getdoc(fn) or "",
    }


_VERBS: dict[str, object] = {
    "verb_help": _verb_help,
    "scene_info": dsh_hou_helpers.scene_info,
    "set_timeline": dsh_hou_helpers.set_timeline,
    "list_bookmarks": dsh_hou_helpers.list_bookmarks,
    "create_bookmark": dsh_hou_helpers.create_bookmark,
    "delete_bookmark": dsh_hou_helpers.delete_bookmark,
    "search_tab_menu": dsh_hou_helpers.search_tab_menu,
    "search_tab_entries": dsh_hou_helpers.search_tab_entries,
    "resolve_latest_type": dsh_hou_helpers.resolve_latest_type,
    "tab_create": dsh_hou_helpers.tab_create,
    "tab_apply": dsh_hou_helpers.tab_apply,
    "find_nodes": dsh_hou_helpers.find_nodes,
    "graph": dsh_hou_helpers.graph,
    "describe": dsh_hou_helpers.describe,
    "node_provenance": dsh_hou_helpers.node_provenance,
    "connect": dsh_hou_helpers.connect,
    "rename_node": dsh_hou_helpers.rename_node,
    "delete_node": dsh_hou_helpers.delete_node,
    "cook_node": dsh_hou_helpers.cook_node,
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
    "hda_create": dsh_hou_helpers.hda_create,
    "hda_info": dsh_hou_helpers.hda_info,
    "hda_get_section": dsh_hou_helpers.hda_get_section,
    "hda_set_section": dsh_hou_helpers.hda_set_section,
    "hda_patch_section": dsh_hou_helpers.hda_patch_section,
    "hda_set_interface": dsh_hou_helpers.hda_set_interface,
    "geo_attrib_stats": dsh_hou_helpers.geo_attrib_stats,
    "geo_piece_stats": dsh_hou_helpers.geo_piece_stats,
    "geo_frame_diff": dsh_hou_helpers.geo_frame_diff,
    "usd_stage_summary": dsh_hou_helpers.usd_stage_summary,
    "usd_prim_info": dsh_hou_helpers.usd_prim_info,
    "render_frame": dsh_hou_helpers.render_frame,
    "render_check": dsh_hou_helpers.render_check,
    "render_view": dsh_hou_helpers.render_view,
    "viewport_screenshot": dsh_hou_helpers.viewport_screenshot,
}

# Runtime truth, independently derived from the verbs actually injected into
# this Houdini process. The host derives its expected hash from tool-design.md;
# comparing the two catches a stale in-process bridge before any scene edit.
_VERB_NAMES = tuple(sorted(_VERBS))
_VERB_CATALOG_HASH = hashlib.sha256("\n".join(_VERB_NAMES).encode("utf-8")).hexdigest()

_VERB_ENTRY_LIMIT = 500       # 单次 exec 最多记录的动词调用数
_VERB_VALUE_CHARS = 2000      # 单个入参/出参序列化后的截断长度

# --- raw-hou advisory ---------------------------------------------------------
# 动词词表是主接口，裸 hou 只是逃生手段。对每次 exec 的代码做 AST 扫描：统计
# 那些动词已覆盖的裸 hou 调用；一旦代码完全没走动词却用了这些调用，就在返回
# 里附一条 advisory，点明对应的动词——让 agent 从结果里直接看到可替代方案。
_RAW_HOU_VERB_MAP = {
    "createNode": "search_tab_entries + tab_create/tab_apply",
    "setInput": "connect",
    "setFirstInput": "connect",
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
        if func.attr in _RAW_HOU_VERB_MAP:
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


def _forbidden_hip_load_message(code: str) -> str | None:
    """Reject direct ``hou.hipFile.load`` before execution.

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
        if node.func.attr != "load":
            continue
        owner = node.func.value
        if (
            isinstance(owner, ast.Attribute)
            and owner.attr == "hipFile"
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "hou"
        ):
            return (
                "hou.hipFile.load() is forbidden inside dsh-houdini bridge exec: "
                "HIP loading invalidates the active exec/bridge lifecycle and can "
                "disconnect or restart the shared Houdini process. Open the HIP in "
                "the Houdini UI, or use a future host-level reconnecting operation."
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
    "copy", "move", "enable", "disable",
)
_GATE_SAFE_PYTHON_METHODS = {"setdefault"}


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
    if node.func.attr in _GATE_SAFE_PYTHON_METHODS:
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
        if attr in _RAW_HOU_VERB_MAP:
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
    python_sets = _python_set_names(tree)
    covered: dict[str, int] = {}
    mutating: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr
        if attr in _RAW_HOU_VERB_MAP:
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
            mutating[attr] = mutating.get(attr, 0) + 1
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


def _make_tracer(name: str, fn, ledger: list):
    def wrapped(*args, **kwargs):
        if len(ledger) >= _VERB_ENTRY_LIMIT:
            return fn(*args, **kwargs)
        start = time.time()
        args_json = _verb_value(list(args))
        kwargs_json = {str(k): _verb_value(v) for k, v in kwargs.items()}
        try:
            result = fn(*args, **kwargs)
            entry = {
                "verb": name,
                "ts": round(start, 3),  # 绝对时间戳（epoch 秒）：跨 exec 重建真实调用顺序
                "args": args_json,
                "kwargs": kwargs_json,
                "ok": True,
                "result": _verb_value(result),
                "ms": round((time.time() - start) * 1000, 1),
            }
            ledger.append(entry)
            kw = f", {_clip(kwargs_json)}" if kwargs_json else ""
            print(f"[verb] {name}({_clip(args_json)}{kw}) -> {_clip(entry['result'])}  ({entry['ms']}ms)")
            return result
        except BaseException as e:  # 记录失败调用并原样抛出，不改变原语义
            ledger.append({
                "verb": name,
                "ts": round(start, 3),
                "args": args_json,
                "kwargs": kwargs_json,
                "ok": False,
                "error": str(e),
                "ms": round((time.time() - start) * 1000, 1),
            })
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
             owner_call: str | None = None) -> dict:
    """Execute code with `hou` available; capture stdout/stderr and `__result__`.

    Must run on Houdini's main thread (see module docstring) — callers route
    through `_execute`. BaseException is caught so agent code calling
    `sys.exit()` or raising KeyboardInterrupt cannot kill a handler/job thread
    or leave a job stuck in `running` forever.

    allow_raw：词表未覆盖的低层修改的一次性豁免理由（见 _gate_message）；
    它不能旁路已被动词覆盖的裸调用。豁免会打印 [gate] 行进 stdout，进结果与 trace。
    """
    verb_ledger: list = []
    namespace = {"hou": hou}
    for _name, _fn in _VERBS.items():
        namespace[_name] = _make_tracer(_name, _fn, verb_ledger)
    stdout = _CappedStringIO(_MAX_STREAM_BYTES)
    stderr = _CappedStringIO(_MAX_STREAM_BYTES)
    error = None
    rollback = None
    raw_usage = _raw_usage_analysis(code)
    gate_outcome = "not_applicable"
    with _exec_lock, dsh_hou_helpers._execution_owner(owner_session, owner_call):
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                error = _forbidden_hip_load_message(code)
                if error is not None:
                    gate_outcome = "forbidden"
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
                    dsh_hou_helpers._PRODUCED_IMAGES.clear()
                    compiled = compile(code, "<dsh-houdini>", "exec")
                    undo_enabled = bool(hou.undos.areEnabled())
                    if undo_enabled:
                        label = f"dsh-houdini exec {uuid.uuid4().hex}"
                        try:
                            with hou.undos.group(label):
                                exec(compiled, namespace)
                                _raise_caught_verb_failure(verb_ledger)
                        except BaseException:
                            original_error = traceback.format_exc()
                            applied = False
                            rollback_error = None
                            try:
                                labels = list(hou.undos.undoLabels())
                                if labels and labels[0] == label:
                                    hou.undos.performUndo()
                                    applied = True
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
    envelope = {
        "ok": error is None,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
    }
    # 本次 exec 产出的图片（render_frame/render_view/viewport_screenshot 登记）：
    # host 侧经 /media 端点把字节拉回会话工作区，vision/fs 工具才读得到
    # （工作区沙箱；2026-08-19 草地 trace：vision_glance 读 $HIP 截图被拒）。
    images = [p for p in dsh_hou_helpers._PRODUCED_IMAGES if os.path.isfile(p)]
    if images:
        envelope["images"] = images
    if verb_ledger:
        envelope["verbs"] = verb_ledger
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
    while True:
        try:
            func, done, holder = _work_queue.get_nowait()
        except queue.Empty:
            return
        try:
            holder["result"] = func()
        except BaseException as exc:  # a failing task must not kill the pump
            holder["error"] = exc
        finally:
            done.set()


def _execute(func):
    """Run `func` on Houdini's main thread and wait for its return value.

    Falls back to inline execution only when no main-thread pump exists
    (interactive hython without the __main__ loop) — the documented entry
    points (GUI menu / Python Shell, `hython dsh_bridge.py`) always have one.
    """
    if not _pump_active:
        return func()
    done = threading.Event()
    holder: dict = {}
    _work_queue.put((func, done, holder))
    done.wait()
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
    outcome = _execute(
        lambda: _job_body(job_id, code, allow_raw, owner_session, owner_call)
    )
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
                    "houVersion": hou.applicationVersionString(),
                    "rawGate": _raw_gate,
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
        if self.path.startswith("/media"):
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
                    data = fh.read()
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
            length = int(self.headers.get("content-length") or 0)
            if length > _MAX_BODY_BYTES:
                self._send(
                    {"ok": False, "error": f"request body too large ({length} > {_MAX_BODY_BYTES})"},
                    status=413,
                )
                return
            body = json.loads(self.rfile.read(length) or b"{}")
            self._route(body)
        except Exception:
            self._send({"ok": False, "error": traceback.format_exc()}, status=500)

    def _route(self, body: dict) -> None:
        if self.path == "/exec":
            code = str(body.get("code", ""))
            allow_raw = body.get("allow_raw")
            allow_raw = str(allow_raw) if allow_raw else None
            owner_session = body.get("owner_session")
            owner_call = body.get("owner_call")
            self._send(_execute(lambda: run_code(
                code,
                allow_raw,
                str(owner_session) if owner_session else None,
                str(owner_call) if owner_call else None,
            )))
            return
        if self.path == "/jobs":
            job_id = uuid.uuid4().hex[:12]
            with _jobs_lock:
                _jobs[job_id] = {
                    "jobId": job_id, "status": "queued",
                    "ok": False, "stdout": "", "stderr": "",
                }
                _job_meta[job_id] = time.time()
            allow_raw = body.get("allow_raw")
            allow_raw = str(allow_raw) if allow_raw else None
            owner_session = body.get("owner_session")
            owner_call = body.get("owner_call")
            threading.Thread(
                target=_run_job,
                args=(
                    job_id,
                    str(body.get("code", "")),
                    allow_raw,
                    str(owner_session) if owner_session else None,
                    str(owner_call) if owner_call else None,
                ),
                daemon=True,
            ).start()
            _prune_jobs()
            self._send({"jobId": job_id})
            return
        parts = [p for p in self.path.split("/") if p]
        if len(parts) == 3 and parts[0] == "jobs":
            with _jobs_lock:
                job = _jobs.get(parts[1])
                if job is not None and parts[2] == "cancel" and job["status"] in ("queued", "running"):
                    job["status"] = "cancelled"
                    _job_meta[parts[1]] = time.time()
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
                    self._send(dict(job))
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
    global _server
    stop()
    server = ThreadingHTTPServer((host, port), _Handler)
    _server = server
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True).start()
    try:
        ui = hou.isUIAvailable()
    except Exception:
        ui = False
    if ui and not _install_gui_pump():
        print("[dsh-houdini] WARNING: no main-thread pump; code will run on "
              "handler threads, which is NOT safe for hou in GUI mode")
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
