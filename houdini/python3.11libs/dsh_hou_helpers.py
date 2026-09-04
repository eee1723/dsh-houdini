"""dsh-houdini: 按 Houdini 数据流与真实 Tab 语义操作/检查场景。

解决两个问题：

1. **通用初始化** —— 部分单节点（如 ``copytopoints::2.0``）通过 Tab Menu 创建时，
   shelf tool 脚本会做额外初始化（按初始化按钮、建配套节点、设参数等）。裸
   ``hou.Node.createNode`` 不会做这些。本模块用 ``toolutils.testTool`` 跑真实的
   shelf tool，完整保留初始化语义，且对未来 SideFX 改动脚本自动跟随——不为任何
   节点写死「按哪个按钮」。

2. **真实菜单与 setup tool** —— node type 注册表不是用户菜单。parent-aware
   ``search_tab_entries`` 排除 hidden/deprecated 和 builder mask 外类型；多节点
   Karma Setup/Material Builder 走受限 ``tab_apply``，不压进单节点返回契约。

3. **永远最新版本** —— ``hou.preferredNodeType`` 实测不可靠（返回 None），这里枚举
   ``nodeTypes()`` 取 ``::N`` 最大的版本，创建和自省共用同一解析。

只依赖 ``hou`` / ``toolutils`` / 标准库，不导入项目 venv 任何包（进程边界）。
本模块被 ``dsh_bridge`` 预置进 exec namespace，agent 写 Python 时可直接：

    geo = tab_create(hou.node('/obj'), 'geo', name='my_geo')
    cop = tab_create(geo, 'copytopoints', inputs=[box, points])
    search_tab_menu('sop', 'cone')     # 查不猜：列出匹配类型 + 最新版
    search_tab_entries('/stage', 'karma')
    tab_apply('/stage', 'lop_karma_setup')

注意：``tab_create`` 返回 ``hou.Node``（供 agent 继续链式操作）；要回传结构化数据，
请手动转 JSON（``__result__ = {'path': node.path()}``），不要直接把 hou 对象塞进
``__result__``。
"""

from __future__ import annotations

import contextlib
import difflib
import fnmatch
import hashlib
import math
import os
import re
import struct
import time
import zlib
from typing import Any

import hou
import toolutils


# ``render_view`` infrastructure is session-scoped service state, not a
# per-task probe. Deleting an OpenGL ROP (or a node it references) after a
# successful render can make H21 enter its process-fatal GL capability path.
# Keep these constants near the generic node verbs so ``delete_node`` can
# enforce the ownership boundary before it asks Houdini for references.
_RENDER_OWNER_KEY = "dsh_houdini_owner"
_RENDER_OWNER_VALUE = "render_view_v2"
_RENDER_OBJ_BOX_NAME = "__dsh_houdini_render_service"
_RENDER_OUT_BOX_NAME = "__dsh_houdini_render_service"
_RENDER_BOX_COMMENT = "DSH-Houdini Render Service (persistent; do not delete during session)"

# Ordinary task nodes use runtime provenance, not their parent/path/name, as the
# authority boundary.  A user can create or duplicate a node inside an
# agent-created network at any time; that must not make the node agent-owned.
# ``userData`` is durable audit metadata, while the process-local sessionId
# registry is authoritative for automatic mutation/cleanup.  A copied node may
# copy userData, but receives a new Houdini sessionId and therefore remains
# foreign until the user explicitly authorizes an edit.
_TASK_OWNER_KEY = "dsh_houdini_task_owner"
_TASK_OWNER_CALL_KEY = "dsh_houdini_created_by_call"
_ACTIVE_OWNER_SESSION: str | None = None
_ACTIVE_OWNER_CALL: str | None = None
_OWNED_NODE_SESSIONS: dict[int, dict] = {}


def _set_execution_owner(session_id: str | None, call_id: str | None):
    """Install trusted host provenance for one serialized bridge execution."""
    global _ACTIVE_OWNER_SESSION, _ACTIVE_OWNER_CALL
    previous = (_ACTIVE_OWNER_SESSION, _ACTIVE_OWNER_CALL)
    _ACTIVE_OWNER_SESSION = str(session_id) if session_id else None
    _ACTIVE_OWNER_CALL = str(call_id) if call_id else None
    return previous


def _restore_execution_owner(previous) -> None:
    global _ACTIVE_OWNER_SESSION, _ACTIVE_OWNER_CALL
    _ACTIVE_OWNER_SESSION, _ACTIVE_OWNER_CALL = previous


@contextlib.contextmanager
def _execution_owner(session_id: str | None, call_id: str | None):
    """Scope trusted host provenance to exactly one serialized execution."""
    previous = _set_execution_owner(session_id, call_id)
    try:
        yield
    finally:
        _restore_execution_owner(previous)


def _register_owned_node(node) -> None:
    """Record a verb-created node and its initialized subtree."""
    if node is None or _ACTIVE_OWNER_SESSION is None:
        return
    items = [node]
    try:
        items.extend(node.allSubChildren())
    except Exception:
        pass
    for item in items:
        entry = {
            "session": _ACTIVE_OWNER_SESSION,
            "call": _ACTIVE_OWNER_CALL,
            "path_at_creation": item.path(),
        }
        _OWNED_NODE_SESSIONS[int(item.sessionId())] = entry
        item.setUserData(_TASK_OWNER_KEY, _ACTIVE_OWNER_SESSION)
        if _ACTIVE_OWNER_CALL:
            item.setUserData(_TASK_OWNER_CALL_KEY, _ACTIVE_OWNER_CALL)


def node_provenance(node) -> dict:
    """Report runtime ownership separately from durable, copyable audit tags."""
    n = _resolve(node)
    if n.userData(_RENDER_OWNER_KEY) == _RENDER_OWNER_VALUE:
        status = "dsh_service"
        runtime_owner = None
    else:
        runtime_owner = _OWNED_NODE_SESSIONS.get(int(n.sessionId()))
        if runtime_owner is None:
            status = "foreign"
        elif runtime_owner.get("session") == _ACTIVE_OWNER_SESSION:
            status = "owned_current_session"
        else:
            status = "owned_other_session"
    return {
        "path": n.path(),
        "session_id": int(n.sessionId()),
        "status": status,
        "writable": status == "owned_current_session" or _ACTIVE_OWNER_SESSION is None,
        "runtime_owner": dict(runtime_owner) if runtime_owner else None,
        "audit_owner_session": n.userData(_TASK_OWNER_KEY),
        "audit_created_by_call": n.userData(_TASK_OWNER_CALL_KEY),
    }


def _require_owned(node, operation: str, allow_foreign: str | None = None) -> None:
    """Guard one node mutation while preserving direct Python-shell workflows."""
    if _ACTIVE_OWNER_SESSION is None:
        return
    info = node_provenance(node)
    if info["status"] == "owned_current_session":
        return
    if info["status"] == "dsh_service":
        raise ValueError(
            f"{info['path']} belongs to the persistent dsh-houdini service; "
            f"{operation} is not allowed"
        )
    reason = str(allow_foreign or "").strip()
    if reason:
        print(
            f"[ownership] foreign-node exemption for {operation}: "
            f"{info['path']} — {reason}"
        )
        return
    raise ValueError(
        f"ownership guard: {operation} refused for foreign node {info['path']}. "
        "Nodes are not owned merely because they are inside an agent-created network. "
        "Read/inspect it freely; mutate it only when the user explicitly requested that "
        f"target, then retry with allow_foreign=\"<why the user authorized {operation}>\"."
    )

# ---------------------------------------------------------------------------
# 分类映射与版本解析
# ---------------------------------------------------------------------------

_CATEGORIES = {
    "obj": hou.objNodeTypeCategory,
    "sop": hou.sopNodeTypeCategory,
    "dop": hou.dopNodeTypeCategory,
    "chop": hou.chopNodeTypeCategory,
    "cop2": hou.cop2NodeTypeCategory,
    "shop": hou.shopNodeTypeCategory,
    "vop": hou.vopNodeTypeCategory,
    "rop": hou.ropNodeTypeCategory,
    "top": hou.topNodeTypeCategory,
    "lop": hou.lopNodeTypeCategory,
}

# UI 名/常见写法 → 内部名（2026-08-20 OTL 会话：agent 连猜 'Object'/'driver' 两次才蒙对）
_CATEGORY_ALIASES = {
    "object": "obj", "objects": "obj", "geometry": "sop", "sops": "sop",
    "driver": "rop", "drivers": "rop", "out": "rop", "dops": "dop",
    "chops": "chop", "vops": "vop", "tops": "top", "lops": "lop",
    "stage": "lop", "material": "shop", "materials": "shop",
    "shopnet": "shop", "cop": "cop2", "cops": "cop2", "img": "cop2",
}

_VERSION_RE = re.compile(r"^(.*)::(\d+(?:\.\d+)*)$")

# Tab tools execute arbitrary SideFX/user scripts. Start with the two deterministic,
# network-local setup intents proven by session-71d76525 and H21's shipped shelf files;
# expand only with a concrete trace + GUI state-restoration regression.
_TAB_TOOL_ALLOWLIST = {
    "lop_karma_setup",
    "vop_karmamtlxsubnet",
}
_PENDING_TAB_USER_STATE = None
_TAB_RESTORE_POSTED = False


def _category(category):
    if isinstance(category, hou.NodeTypeCategory):
        return category
    if isinstance(category, str):
        key = category.strip().lower()
        key = _CATEGORY_ALIASES.get(key, key)
        factory = _CATEGORIES.get(key)
        if factory is None:
            valid = ", ".join(sorted(_CATEGORIES))
            alias = ", ".join(f"{a}→{b}" for a, b in sorted(_CATEGORY_ALIASES.items()))
            raise ValueError(
                f"unknown node type category: {category!r}；"
                f"合法类别：{valid}；别名：{alias}"
            )
        return factory()
    raise ValueError(f"unknown node type category: {category!r}（合法：{', '.join(sorted(_CATEGORIES))}）")


def context_name(category) -> str:
    """hou.sopNodeTypeCategory() -> 'sop'（用于构造 shelf tool 名）。"""
    return _category(category).name().lower()


# --- scene 域 ---------------------------------------------------------------

def scene_info() -> dict:
    """只读场景/时间线摘要；不移动 playbar、不遍历整张节点图。"""
    hip_path = hou.hipFile.path()
    has_named_path = os.path.basename(hip_path).lower() != "untitled.hip"
    has_unsaved_changes = bool(hou.hipFile.hasUnsavedChanges())
    ui_available = bool(hou.isUIAvailable())
    return {
        "hip_path": hip_path,
        "hip_name": hou.hipFile.name(),
        "has_named_path": has_named_path,
        "has_unsaved_changes": has_unsaved_changes,
        "dirty_reliable": ui_available,
        "clean_on_disk": has_named_path and not has_unsaved_changes if ui_available else None,
        "version": hou.applicationVersionString(),
        "fps": float(hou.fps()),
        "frame": float(hou.frame()),
        "time": float(hou.time()),
        "frame_range": [float(v) for v in hou.playbar.frameRange()],
        "playback_range": [float(v) for v in hou.playbar.playbackRange()],
        "range_restricted": bool(hou.playbar.isRangeRestricted()),
        "playing": bool(hou.playbar.isPlaying()),
        "ui_available": ui_available,
    }


def scene_save(expected_path: str | None = None) -> dict:
    """保存当前已命名 HIP，并回报真实 dirty/file 状态；不承担 Save As。"""
    path = os.path.abspath(hou.hipFile.path())
    if os.path.basename(path).lower() == "untitled.hip":
        raise ValueError("当前 HIP 尚未命名；请先在 Houdini UI 中 Save As，再调用 scene_save")
    if expected_path is not None:
        expected = os.path.abspath(hou.expandString(str(expected_path)))
        if os.path.normcase(expected) != os.path.normcase(path):
            raise ValueError(f"expected_path 与当前 HIP 不一致：expected={expected!r}, current={path!r}")
    dirty_before = bool(hou.hipFile.hasUnsavedChanges())
    hou.hipFile.save()
    dirty_after = bool(hou.hipFile.hasUnsavedChanges())
    dirty_reliable = bool(hou.isUIAvailable())
    if not os.path.isfile(path):
        raise RuntimeError(f"hou.hipFile.save() 返回后文件不存在：{path}")
    stat = os.stat(path)
    return {
        "path": path,
        "dirty_before": dirty_before,
        "dirty_after": dirty_after,
        "dirty_reliable": dirty_reliable,
        "clean_on_disk": not dirty_after if dirty_reliable else None,
        "bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _frame_pair(value, label: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} 必须是 [start, end]")
    start, end = float(value[0]), float(value[1])
    if end < start:
        raise ValueError(f"{label} end 不能小于 start：{start}, {end}")
    return start, end


def set_timeline(fps=None, frame_range=None, playback_range=None,
                 current_frame=None) -> dict:
    """设置时间线；四项均可选，但至少提供一项。"""
    if all(value is None for value in (fps, frame_range, playback_range, current_frame)):
        raise ValueError("至少提供 fps/frame_range/playback_range/current_frame 一项")
    changed = {}
    if fps is not None:
        value = float(fps)
        if value <= 0:
            raise ValueError("fps 必须大于 0")
        hou.setFps(value)
        changed["fps"] = value
    if frame_range is not None:
        start, end = _frame_pair(frame_range, "frame_range")
        hou.playbar.setFrameRange(start, end)
        changed["frame_range"] = [start, end]
    if playback_range is not None:
        start, end = _frame_pair(playback_range, "playback_range")
        hou.playbar.setPlaybackRange(start, end)
        changed["playback_range"] = [start, end]
    if current_frame is not None:
        value = float(current_frame)
        hou.setFrame(value)
        changed["current_frame"] = value
    return {"changed": changed, "scene": scene_info()}


def list_bookmarks() -> list:
    """列出动画时间线 bookmarks。"""
    return [
        {
            "id": bookmark.sessionId(),
            "name": bookmark.name(),
            "start": float(bookmark.startFrame()),
            "end": float(bookmark.endFrame()),
            "enabled": bool(bookmark.isEnabled()),
            "visible": bool(bookmark.visible()),
            "temporary": bool(bookmark.isTemporary()),
            "comment": bookmark.comment(),
        }
        for bookmark in hou.anim.bookmarks()
    ]


def create_bookmark(name: str, start, end, replace: bool = False) -> dict:
    """创建 bookmark；同名默认拒绝，``replace=True`` 精确替换同名项。"""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("bookmark name 必须是非空字符串")
    name = name.strip()
    start_frame, end_frame = _frame_pair((start, end), "bookmark range")
    if not start_frame.is_integer() or not end_frame.is_integer():
        raise ValueError("bookmark start/end 必须是整数帧")
    existing = [bookmark for bookmark in hou.anim.bookmarks() if bookmark.name() == name]
    if existing and not replace:
        raise ValueError(f"bookmark {name!r} 已存在；确认替换时传 replace=True")
    if existing:
        hou.anim.removeBookmarks(existing)
    bookmark = hou.anim.newBookmark(name, int(start_frame), int(end_frame))
    return {
        "id": bookmark.sessionId(),
        "name": bookmark.name(),
        "start": float(bookmark.startFrame()),
        "end": float(bookmark.endFrame()),
        "replaced": len(existing),
    }


def delete_bookmark(name_or_id) -> dict:
    """按精确名称或 session id 删除 bookmark。"""
    matches = []
    for bookmark in hou.anim.bookmarks():
        if isinstance(name_or_id, int) and bookmark.sessionId() == name_or_id:
            matches.append(bookmark)
        elif isinstance(name_or_id, str) and bookmark.name() == name_or_id:
            matches.append(bookmark)
    if not matches:
        raise ValueError(
            f"找不到 bookmark {name_or_id!r}；现有："
            f"{[(item['id'], item['name']) for item in list_bookmarks()]}"
        )
    deleted = [
        {"id": bookmark.sessionId(), "name": bookmark.name()}
        for bookmark in matches
    ]
    hou.anim.removeBookmarks(matches)
    return {"deleted": deleted}


def _version_key(version: str):
    return tuple(int(p) for p in version.split("."))


def resolve_latest_type(category, base: str) -> str:
    """返回某节点族的最新版本全名，如 'copytopoints' -> 'copytopoints::2.0'。

    无版本化条目时原样返回 ``base``；有多个 ``::N`` 时取 ``N`` 最大者。
    只以 namespace 形式注册的族（'rigdoctor' -> 'kinefx::rigdoctor'）返回带
    namespace 的全名：`createNode(exact_type_name=True)` 不接受裸别名。
    多 namespace 同名时按名称排序取第一个（确定性兜底）。
    """
    cat = _category(category)
    names = cat.nodeTypes().keys()
    prefix = base + "::"
    best_key: tuple[int, ...] = ()
    best_name = base if base in names else None
    for name in names:
        if not name.startswith(prefix):
            continue
        m = _VERSION_RE.match(name)
        if not m:
            continue
        key = _version_key(m.group(2))
        if key > best_key:
            best_key = key
            best_name = name
    if best_name is not None:
        return best_name
    ns_key: tuple[int, ...] = ()
    ns_name = None
    for name in sorted(names):
        parts = name.split("::")
        if len(parts) == 2 and parts[1] == base and ns_name is None:
            ns_name = name
        elif len(parts) == 3 and parts[1] == base:
            key = _version_key(parts[2])
            if key > ns_key:
                ns_key = key
                ns_name = name
    return ns_name if ns_name is not None else base


# ---------------------------------------------------------------------------
# 通用 Tab Menu 创建
# ---------------------------------------------------------------------------

def _network_editor():
    pane = toolutils.networkEditor()
    if pane is not None:
        return pane
    for tab in hou.ui.paneTabs():
        if tab.type() == hou.paneTabType.NetworkEditor:
            return tab
    return None


def _run_shelf_tool(tool, parent: hou.Node, type_name: str) -> hou.Node | None:
    """在目标网络中跑 shelf tool，返回其新建的节点；无 pane/失败时返回 None。"""
    pane = _network_editor()
    if pane is None:
        return None

    prev_pwd = pane.pwd()
    try:
        pane.setPwd(parent)
        if pane.pwd() is None or pane.pwd().path() != parent.path():
            return None
    except Exception:
        return None

    before = {c.sessionId() for c in parent.children()}
    try:
        toolutils.testTool(
            tool,
            kwargs={
                "pane": pane,
                "toolname": type_name,
                "autoplace": True,
                "shiftclick": False,
                "ctrlclick": False,
                "altclick": False,
            },
        )
    except BaseException:
        # A failed shelf script may already have created part of its network.
        # Never let tab_create reinterpret that semantic failure as permission
        # to create a weaker bare node; clean the known partial creations and
        # re-raise so the bridge can roll back any other undoable edits.
        for child in reversed(parent.children()):
            if child.sessionId() not in before:
                try:
                    child.destroy()
                except Exception:
                    pass
        raise
    finally:
        try:
            if prev_pwd is not None:
                pane.setPwd(prev_pwd)
        except Exception:
            pass

    created = [c for c in parent.children() if c.sessionId() not in before]
    for child in created:
        _register_owned_node(child)
    if len(created) == 1:
        return created[0]
    # 多个新节点：优先类型完全匹配；否则取第一个（绝不回退 createNode——
    # tool 已经建过节点，再建一次就是场景里的重复残留）
    match = next((c for c in created if c.type().name() == type_name), None)
    if match is not None:
        return match
    return created[0] if created else None


def _tool_context(tool, parent: hou.Node) -> dict:
    """Return Network Editor menu metadata and whether *tool* applies to parent."""
    pane_type = hou.paneTabType.NetworkEditor
    try:
        categories = tuple(tool.toolMenuCategories(pane_type) or ())
    except Exception:
        categories = ()
    try:
        op_type = str(tool.toolMenuOpType(pane_type) or "")
    except Exception:
        op_type = ""
    try:
        locations = list(tool.toolMenuLocations() or ())
    except Exception:
        locations = []

    child_category = parent.childTypeCategory()
    category_match = child_category in categories
    op_type_match = False
    if op_type:
        category_name, _, operator_name = op_type.partition("/")
        if category_name.lower() == child_category.name().lower():
            # Material Library presents a Vop/materialbuilder network even though its
            # owning node is a Lop/materiallibrary. This is the shipped context for the
            # Karma/USD Material Builder tools.
            if operator_name == "materialbuilder":
                op_type_match = (
                    parent.type().category() == hou.lopNodeTypeCategory()
                    and parent.type().name().split("::", 1)[0] == "materiallibrary"
                )
            else:
                parent_type = parent.type().name().split("::", 1)[0]
                op_type_match = parent_type == operator_name
    return {
        "categories": [category.name() for category in categories],
        "op_type": op_type or None,
        "locations": locations,
        "matches": bool(category_match or op_type_match),
    }


def _visible_node_type(node_type) -> bool:
    try:
        if node_type.hidden() or node_type.deprecated():
            return False
    except Exception:
        pass
    return True


def search_tab_entries(parent, query: str = "") -> dict:
    """列出父网络真实可见的节点/Tab tool entry，不把类型注册表冒充菜单。

    返回 entry 的 ``kind`` 为 ``node_type`` 或 ``tool``。Material Library 根层只
    暴露 builder tool；shader 应进入对应 builder 后再创建。隐藏/废弃 node type
    不进入 entries，但计入 excluded。``executable`` 仅表示 dsh 当前安全 allowlist，
    不是 SideFX 工具是否存在。
    """
    parent = _resolve(parent)
    if not parent.isNetwork():
        raise ValueError(f"{parent.path()} 不是可创建子节点的网络")
    q = str(query or "").strip().lower()
    child_category = parent.childTypeCategory()
    entries = []
    excluded_hidden = 0

    # Since H20 the Material Library root is a builder launcher, not a free-form VOP
    # graph. Its tool entries below are the truthful UI surface.
    material_library_root = (
        parent.type().category() == hou.lopNodeTypeCategory()
        and parent.type().name().split("::", 1)[0] == "materiallibrary"
    )
    if not material_library_root:
        families: dict[str, list] = {}
        for name, node_type in child_category.nodeTypes().items():
            label = node_type.description() or name
            if q and q not in name.lower() and q not in label.lower():
                continue
            if not _visible_node_type(node_type):
                excluded_hidden += 1
                continue
            match = _VERSION_RE.match(name)
            base = match.group(1) if match else name
            families.setdefault(base, []).append(node_type)
        for base, node_types in families.items():
            def version_key(node_type):
                match = _VERSION_RE.match(node_type.name())
                return _version_key(match.group(2)) if match else ()
            latest = max(node_types, key=version_key)
            entries.append({
                "kind": "node_type",
                "name": latest.name(),
                "base": base,
                "label": latest.description() or latest.name(),
                "versions": sorted(node_type.name() for node_type in node_types),
                "executable": True,
            })

    for tool_id, tool in hou.shelves.tools().items():
        try:
            label = tool.label() or tool_id
        except Exception:
            continue
        if q and q not in tool_id.lower() and q not in label.lower():
            continue
        context = _tool_context(tool, parent)
        if not context["matches"]:
            continue
        entries.append({
            "kind": "tool",
            "name": tool_id,
            "label": label,
            "locations": context["locations"],
            "op_type": context["op_type"],
            "executable": tool_id in _TAB_TOOL_ALLOWLIST,
        })

    entries.sort(key=lambda item: (item["label"].lower(), item["kind"], item["name"]))
    return {
        "parent": parent.path(),
        "child_category": child_category.name(),
        "query": query,
        "entries": entries,
        "excluded_hidden_or_deprecated": excluded_hidden,
    }


def _apply_karma_setup_recipe(parent: hou.Node) -> list:
    """Non-interactive adapter for SideFX ``lop_karma_setup`` semantics."""
    settings = parent.createNode("karmarendersettings", node_name="karmarendersettings")
    rop = parent.createNode("usdrender_rop")
    rop.setInput(0, settings)
    settings_name = settings.name()
    required = {
        "rendersettings": f'chs("../{settings_name}/primpath")',
        "husk_instantshutter": f'1 - ch("../{settings_name}/enablemblur")',
        "renderer": (
            f'"BRAY_HdKarma" + ifs(strmatch(chs("../{settings_name}/engine"), '
            '"xpu"), "XPU", "")'
        ),
    }
    for parm_name, expression in required.items():
        parm = rop.parm(parm_name)
        if parm is None:
            raise RuntimeError(
                f"当前 Houdini 的 {rop.type().name()} 缺少 Karma Setup 参数 {parm_name!r}"
            )
        parm.setExpression(expression, language=hou.exprLanguage.Hscript)
    return [settings, rop]


def _apply_karma_material_builder_recipe(parent: hou.Node) -> list:
    """Use the installed SideFX builder initializer without its selection UI."""
    import voptoolutils

    setup = getattr(voptoolutils, "_setupMtlXBuilderSubnet", None)
    mask = getattr(voptoolutils, "KARMAMTLX_TAB_MASK", None)
    if setup is None or not mask:
        raise RuntimeError(
            "当前 Houdini 缺少 Karma Material Builder initializer；"
            "请检查 voptoolutils 版本"
        )
    builder = parent.createNode("subnet", node_name="karmamaterial")
    result = setup(
        subnet_node=builder,
        name="karmamaterial",
        mask=mask,
        folder_label="Karma Material Builder",
        render_context="kma",
    )
    if result is None:
        raise RuntimeError("SideFX Karma Material Builder initializer 返回空")
    return [result]


def _capture_tab_user_state(pane) -> dict:
    selected = list(hou.selectedNodes())
    pane_current = None
    try:
        pane_current = pane.currentNode() if pane is not None else None
    except Exception:
        pass
    return {
        "pane": pane,
        "pwd": pane.pwd().path() if pane is not None and pane.pwd() is not None else None,
        "selected": [node.path() for node in selected],
        "current": [node.path() for node in selected if node.isCurrent()],
        "pane_current": pane_current.path() if pane_current is not None else None,
    }


def _apply_tab_user_state(state: dict) -> dict:
    pane = state.get("pane")
    pwd_path = state.get("pwd")
    if pane is not None and pwd_path:
        pwd = hou.node(pwd_path)
        if pwd is not None:
            pane.setPwd(pwd)
    hou.clearAllSelected()
    for path in state.get("current", []):
        node = hou.node(path)
        if node is not None:
            node.setCurrent(True)
    pane_current = hou.node(state.get("pane_current")) if state.get("pane_current") else None
    if pane is not None and pane_current is not None:
        pane.setCurrentNode(pane_current)
    for path in state.get("selected", []):
        node = hou.node(path)
        if node is not None:
            node.setSelected(True)
    actual_selected = sorted(node.path() for node in hou.selectedNodes())
    expected_selected = sorted(
        path for path in state.get("selected", []) if hou.node(path) is not None
    )
    return {
        "network_pwd": pane is None or not pwd_path or (
            pane.pwd() is not None and pane.pwd().path() == pwd_path
        ),
        "selection": actual_selected == expected_selected,
    }


def _finish_pending_tab_restore():
    global _PENDING_TAB_USER_STATE, _TAB_RESTORE_POSTED
    state = _PENDING_TAB_USER_STATE
    _PENDING_TAB_USER_STATE = None
    _TAB_RESTORE_POSTED = False
    if state is not None:
        try:
            _apply_tab_user_state(state)
        except Exception:
            pass


def _queue_final_tab_restore():
    """Second event-loop hop: run after Houdini's deferred node-selection post."""
    try:
        hou.ui.postEventCallback(_finish_pending_tab_restore)
    except Exception:
        _finish_pending_tab_restore()


def tab_apply(parent, tool_id: str) -> dict:
    """应用 allowlist 内的非交互 Tab setup recipe，返回全部新增节点。

    这和 ``tab_create`` 的单节点契约不同。当前只允许 H21/H22 的 Karma (Setup)
    与 Karma Material Builder；运行时仍验证真实 tool/context，但通过 SideFX recipe
    adapter 避开通用 shelf UI 的 selection/current/modal 副作用。未知工具明确拒绝。
    """
    parent = _resolve(parent)
    if not parent.isNetwork():
        raise ValueError(f"{parent.path()} 不是可应用 Tab tool 的网络")
    if not isinstance(tool_id, str) or not tool_id.strip():
        raise ValueError("tool_id 必须是非空字符串")
    tool_id = tool_id.strip()
    tool = hou.shelves.tool(tool_id)
    if tool is None:
        raise ValueError(f"找不到 Tab tool {tool_id!r}")
    context = _tool_context(tool, parent)
    if not context["matches"]:
        raise ValueError(
            f"Tab tool {tool_id!r} 不适用于 {parent.path()}"
            f"（child category={parent.childTypeCategory().name()}, "
            f"tool categories={context['categories']}, op_type={context['op_type']!r}）"
        )
    if tool_id not in _TAB_TOOL_ALLOWLIST:
        raise ValueError(
            f"Tab tool {tool_id!r} 存在但不在 dsh 安全 allowlist；"
            f"当前允许：{sorted(_TAB_TOOL_ALLOWLIST)}"
        )
    global _PENDING_TAB_USER_STATE, _TAB_RESTORE_POSTED
    pane = _network_editor() if hou.isUIAvailable() else None
    if pane is not None:
        if _PENDING_TAB_USER_STATE is None:
            _PENDING_TAB_USER_STATE = _capture_tab_user_state(pane)
        user_state = _PENDING_TAB_USER_STATE
    else:
        user_state = _capture_tab_user_state(None)
    before = {child.sessionId() for child in parent.children()}
    try:
        try:
            if tool_id == "lop_karma_setup":
                recipe_nodes = _apply_karma_setup_recipe(parent)
            elif tool_id == "vop_karmamtlxsubnet":
                recipe_nodes = _apply_karma_material_builder_recipe(parent)
            else:  # guarded by allowlist, defensive for future edits
                raise ValueError(f"Tab tool {tool_id!r} 没有安全 recipe adapter")
        except BaseException:
            # GUI exec has an undo transaction, but headless does not. Clean only
            # children created by this recipe attempt so a partial setup never leaks.
            for child in reversed(parent.children()):
                if child.sessionId() not in before:
                    try:
                        child.destroy()
                    except Exception:
                        pass
            raise
        created = [child for child in parent.children() if child.sessionId() not in before]
        if not created:
            raise RuntimeError(f"Tab tool {tool_id!r} 没有在 {parent.path()} 创建节点")
        for child in created:
            _register_owned_node(child)
        if not all(node in created for node in recipe_nodes):
            raise RuntimeError(f"Tab tool {tool_id!r} recipe 返回了父网络外节点")
        created.sort(key=lambda node: node.path())
        result = {
            "tool_id": tool_id,
            "label": tool.label() or tool_id,
            "parent": parent.path(),
            "execution": "sidefx_recipe_adapter",
            "created": [
                {
                    "path": node.path(),
                    "type": node.type().name(),
                    "category": node.type().category().name(),
                    "inputs": [source.path() if source is not None else None for source in node.inputs()],
                }
                for node in created
            ],
        }
    finally:
        try:
            immediate_state = _apply_tab_user_state(user_state)
        except Exception:
            immediate_state = {"network_pwd": False, "selection": False}
        if pane is not None and not _TAB_RESTORE_POSTED:
            try:
                # First hop runs after the surrounding exec unwinds; it queues the
                # actual restoration one event turn later than node creation's own
                # deferred selection update.
                hou.ui.postEventCallback(_queue_final_tab_restore)
                _TAB_RESTORE_POSTED = True
            except Exception:
                _finish_pending_tab_restore()

    result["state_restored"] = immediate_state
    result["final_restore"] = "posted" if pane is not None else "synchronous"
    return result


def _tool_has_extra_init(tool) -> bool:
    """判断 shelf tool 是否在 genericTool 之外还有「实质性」初始化。

    只有会真正改场景的操作才算额外初始化（按初始化按钮 / 建配套节点 / 连输入 /
    应用 recipe）；给 ``kwargs`` 设默认值（bbox/parms）或普通赋值不算——那些
    agent 直接设参数即可，不值得为每个节点做昂贵的 pane 导航 + testTool。
    """
    markers = ("pressButton(", "createNode(", "setInput(", "applyTabToolRecipe", ".parm(")
    script = tool.script() or ""
    for line in script.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("import ") or s.startswith("from "):
            continue
        if "genericTool(" in s:
            continue
        if any(m in s for m in markers):
            return True
    return False


def _flow_gaps(nodes):
    """由节点实际网络尺寸推导 flow 落位的水平/垂直间距（不用拍脑袋常量）。"""
    width = height = 0.0
    for n in nodes:
        try:
            size = n.size()
            width = max(width, float(size.x()))
            height = max(height, float(size.y()))
        except Exception:
            continue
    h_gap = (width if width > 0 else 2.0) + 0.8
    v_gap = (height if height > 0 else 1.0) + 0.4
    return h_gap, v_gap


def _place_created_node(node):
    """tab_create 智能落位：有输入放到输入下游，无输入放右侧新列（空网络落原点）。

    网络坐标 y 向下为负：输入下游 = 更小的 y；「最顶部」= 最大的 y。
    """
    parent = node.parent()
    inputs = [n for n in node.inputs() if n is not None]
    if inputs:
        _h_gap, v_gap = _flow_gaps([node, *inputs])
        x = sum(float(n.position().x()) for n in inputs) / len(inputs)
        y = min(float(n.position().y()) for n in inputs) - v_gap
    else:
        siblings = [c for c in parent.children() if c.sessionId() != node.sessionId()]
        if not siblings:
            return
        x = max(float(c.position().x()) + float(c.size().x()) for c in siblings) + 0.8
        y = max(float(c.position().y()) for c in siblings)
    node.setPosition(hou.Vector2(x, y))


def _snap_into_flow(node):
    """connect 纠流：节点违反自顶向下流（不在所有输入下游）时 snap 到输入正下方。

    已在下游（y 严格小于所有输入的 min y）的节点绝不动。返回是否移动了节点。
    """
    inputs = [n for n in node.inputs() if n is not None]
    if not inputs:
        return False
    min_y = min(float(n.position().y()) for n in inputs)
    if float(node.position().y()) < min_y:
        return False
    _h_gap, v_gap = _flow_gaps([node, *inputs])
    x = sum(float(n.position().x()) for n in inputs) / len(inputs)
    node.setPosition(hou.Vector2(x, min_y - v_gap))
    return True


def tab_create(
    parent: hou.Node,
    type_name: str,
    name: str | None = None,
    inputs: list | None = None,
) -> hou.Node | None:
    """按 Tab Menu 语义创建节点：最新版本 + 完整初始化，返回创建的节点。

    - ``parent``：目标父节点（hou.Node 或 path 字符串，如 '/obj'）。
    - ``type_name``：基名即可（'copytopoints'、'box'、'geo'），内部解析最新版。
    - ``inputs``：可选，创建后按序连到 input 0..n（节点或路径均可；
      连接失败会抛错，不会静默跳过）。
    - 有对应 shelf tool 且其带额外初始化时走 tool；否则回退 createNode(latest)
      （避免对 box/grid 这类纯节点做昂贵的 pane 导航）。
    - 落位：连完 inputs 后自动摆放——有输入时放到所有输入下游
      （x = 输入 x 均值，y = min(输入 y) − 垂直间距）；无输入时放到父网络
      现有内容右侧新列（空网络落原点）。间距由节点实际尺寸推导，见
      ``_place_created_node``。
    """
    parent = _resolve(parent)  # 铁律 1：hou.Node 或 path 字符串均可
    cat = parent.childTypeCategory()
    ctx = context_name(cat)
    latest = resolve_latest_type(cat, type_name)

    node_type = hou.nodeType(cat, latest)
    if node_type is not None and not _visible_node_type(node_type):
        raise ValueError(
            f"节点类型 {latest!r} 在当前 Houdini 中 hidden/deprecated；"
            "请用 search_tab_entries(parent, query) 查真实 Tab entry，"
            "setup 工具用 tab_apply(parent, tool_id)"
        )
    if (
        parent.type().category() == hou.lopNodeTypeCategory()
        and parent.type().name().split("::", 1)[0] == "materiallibrary"
    ):
        raise ValueError(
            f"Material Library 根层不直接创建 {latest!r}；"
            "先用 search_tab_entries(parent, query) 选择 Karma/USD/Preview Builder，"
            "再用 tab_apply 执行对应 builder tool"
        )

    tool = None
    try:
        tool = hou.shelves.tool(f"{ctx}_{latest}")
    except Exception:
        tool = None

    node: hou.Node | None = None
    if tool is not None and _tool_has_extra_init(tool):
        node = _run_shelf_tool(tool, parent, latest)

    if node is None:
        node = parent.createNode(latest, node_name=name, exact_type_name=True)
        _register_owned_node(node)
    elif name is not None:
        try:
            node.setName(name, unique_name=True)
        except Exception:
            pass

    if node is not None and inputs:
        for index, source in enumerate(inputs):
            # setInput 只接受 hou.Node（实测 H21/H22 对 path 字符串抛 TypeError），
            # 且失败必须显式报错——静默跳过会让 agent 基于错误的连线继续推理。
            try:
                node.setInput(index, _resolve(source))
            except Exception as e:
                raise ValueError(
                    f"连接输入失败：{node.path()} 的第 {index} 个输入 ← {source!r}（{e}）"
                ) from e

    if node is not None:
        _place_created_node(node)

    return node


# ---------------------------------------------------------------------------
# 只读查询：查不猜
# ---------------------------------------------------------------------------

def search_tab_menu(category, query: str = "") -> dict:
    """只读：列出某 context 下匹配 ``query`` 的节点族，标注各自最新版本。

    返回 ``{families: [...], latest_of_query: ...}``。用于回答「有没有 cone /
    这个节点叫什么 / 最新版是什么」，而不是让模型去猜类型名。
    """
    cat = _category(category)
    q = query.lower().strip()
    q_key = re.sub(r"[^a-z0-9]+", "", q)

    # 按族键聚合（去版本），族键 = 名字去掉末尾 ::N
    families: dict[str, list[str]] = {}
    labels: dict[str, set[str]] = {}
    for name, node_type in cat.nodeTypes().items():
        m = _VERSION_RE.match(name)
        base = m.group(1) if m else name
        try:
            label = node_type.description() or ""
        except Exception:
            label = ""
        haystacks = (name.lower(), base.lower(), label.lower())
        compact = tuple(re.sub(r"[^a-z0-9]+", "", value) for value in haystacks)
        if q and not any(q in value for value in haystacks) and not (
            q_key and any(q_key in value for value in compact)
        ):
            continue
        families.setdefault(base, []).append(name)
        if label:
            labels.setdefault(base, set()).add(label)

    result = []
    for base in sorted(families):
        latest = resolve_latest_type(cat, base)
        result.append(
            {
                "base": base,
                "latest": latest,
                "versions": sorted(families[base]),
            }
        )

    # 若 query 精确命中某个族名，给出它的最新版
    exact = None
    if q:
        for entry in result:
            base_key = re.sub(r"[^a-z0-9]+", "", entry["base"].lower())
            label_keys = {
                re.sub(r"[^a-z0-9]+", "", label.lower())
                for label in labels.get(entry["base"], set())
            }
            if entry["base"].lower() == q or base_key == q_key or q_key in label_keys:
                exact = entry["latest"]
                break
    return {"families": result, "latest_of_query": exact}


# ---------------------------------------------------------------------------
# Solaris / USD 只读自省
# ---------------------------------------------------------------------------

def _lop_stage(node):
    node = _resolve(node)
    if node.type().category() != hou.lopNodeTypeCategory() or not hasattr(node, "stage"):
        raise ValueError(f"{node.path()} 不是可提供 USD stage 的 LOP 节点")
    stage = node.stage()
    if stage is None:
        raise ValueError(f"{node.path()} 没有可用的 USD stage")
    return node, stage


def _usd_value_preview(value, limit: int = 8):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return 0.0 if value == 0.0 else value
    try:
        if hasattr(value, "pathString"):
            return str(value)
    except Exception:
        pass
    if isinstance(value, dict):
        items = list(value.items())
        return {
            "size": len(items),
            "preview": {
                str(key): _usd_value_preview(item, limit)
                for key, item in items[:limit]
            },
        }
    if isinstance(value, (list, tuple)):
        return {
            "size": len(value),
            "preview": [_usd_value_preview(item, limit) for item in value[:limit]],
        }
    # Vt arrays and Gf vectors are iterable but should never dump full mesh data.
    try:
        size = len(value)
        return {
            "size": int(size),
            "preview": [
                _usd_value_preview(value[index], limit)
                for index in range(min(int(size), limit))
            ],
        }
    except Exception:
        pass
    return str(value)


def _usd_relationships(prim) -> list:
    result = []
    for relationship in prim.GetRelationships():
        result.append({
            "name": str(relationship.GetName()),
            "targets": [str(target) for target in relationship.GetTargets()],
        })
    result.sort(key=lambda item: item["name"])
    return result


def usd_stage_summary(node, max_paths: int = 64) -> dict:
    """只读概览 LOP 的 USD stage：prim 类型、材质绑定、渲染和时间采样语义。"""
    node, stage = _lop_stage(node)
    max_paths = int(max_paths)
    if max_paths < 1 or max_paths > 500:
        raise ValueError("max_paths 必须在 1..500")

    groups = {
        "geometry": [],
        "materials": [],
        "lights": [],
        "cameras": [],
        "render_settings": [],
        "render_products": [],
        "render_vars": [],
        "other": [],
    }
    group_counts = {name: 0 for name in groups}
    material_bindings = []
    time_sampled = []
    time_sampled_total = 0
    total_prims = 0
    geometry_types = {
        "Mesh", "BasisCurves", "NurbsCurves", "Points", "Volume", "Capsule",
        "Cone", "Cube", "Cylinder", "Plane", "Sphere",
    }

    for prim in stage.Traverse():
        total_prims += 1
        path = str(prim.GetPath())
        type_name = str(prim.GetTypeName() or "")
        if type_name in geometry_types:
            group = "geometry"
        elif type_name == "Material":
            group = "materials"
        elif type_name.endswith("Light") or type_name == "Light":
            group = "lights"
        elif type_name == "Camera":
            group = "cameras"
        elif type_name == "RenderSettings":
            group = "render_settings"
        elif type_name == "RenderProduct":
            group = "render_products"
        elif type_name == "RenderVar":
            group = "render_vars"
        else:
            group = "other"
        group_counts[group] += 1
        if len(groups[group]) < max_paths:
            groups[group].append({"path": path, "type": type_name or None})

        relationships = _usd_relationships(prim)
        bindings = [
            relationship for relationship in relationships
            if relationship["name"].startswith("material:binding")
        ]
        if bindings and len(material_bindings) < max_paths:
            material_bindings.append({"prim": path, "bindings": bindings})

        for attribute in prim.GetAttributes():
            try:
                count = int(attribute.GetNumTimeSamples())
            except Exception:
                count = 0
            if count:
                time_sampled_total += 1
            if count and len(time_sampled) < max_paths:
                samples = list(attribute.GetTimeSamples())
                time_sampled.append({
                    "prim": path,
                    "attribute": str(attribute.GetName()),
                    "count": count,
                    "samples": [float(sample) for sample in samples[:16]],
                    "samples_truncated": len(samples) > 16,
                })

    return {
        "node": node.path(),
        "total_prims": total_prims,
        "counts": group_counts,
        "prims": groups,
        "paths_truncated": {
            name: group_counts[name] > len(groups[name]) for name in groups
        },
        "material_bindings": material_bindings,
        "time_sampled_attributes": time_sampled,
        "time_samples_truncated": time_sampled_total > len(time_sampled),
        "errors": list(node.errors()),
        "warnings": list(node.warnings()),
    }


def usd_prim_info(node, prim_path: str, max_properties: int = 200) -> dict:
    """只读检查一个 USD prim 的属性、primvar、关系、绑定和 time samples。"""
    node, stage = _lop_stage(node)
    max_properties = int(max_properties)
    if max_properties < 1 or max_properties > 1000:
        raise ValueError("max_properties 必须在 1..1000")
    prim = stage.GetPrimAtPath(str(prim_path))
    if not prim or not prim.IsValid():
        similar = []
        needle = str(prim_path).lower().rsplit("/", 1)[-1]
        for candidate in stage.Traverse():
            path = str(candidate.GetPath())
            if needle and needle in path.lower():
                similar.append(path)
            if len(similar) >= 12:
                break
        raise ValueError(f"找不到 USD prim {prim_path!r}；相似：{similar}")

    attributes = []
    primvars = []
    properties = list(prim.GetProperties())
    for prop in properties[:max_properties]:
        if not hasattr(prop, "GetTypeName"):
            continue
        name = str(prop.GetName())
        samples = list(prop.GetTimeSamples())
        # Avoid pulling full topology/point arrays merely to answer structure.
        heavy = name in {
            "points", "normals", "faceVertexCounts", "faceVertexIndices",
            "velocities", "accelerations",
        }
        value = None
        if not heavy:
            try:
                value = _usd_value_preview(prop.Get())
            except Exception:
                value = None
        item = {
            "name": name,
            "type": str(prop.GetTypeName()),
            "value": value,
            "value_omitted": heavy,
            "time_sample_count": len(samples),
            "time_samples": [float(sample) for sample in samples[:16]],
            "time_samples_truncated": len(samples) > 16,
        }
        attributes.append(item)
        if name.startswith("primvars:"):
            primvars.append(item)

    relationships = _usd_relationships(prim)
    material_bindings = [
        relationship for relationship in relationships
        if relationship["name"].startswith("material:binding")
    ]
    return {
        "node": node.path(),
        "path": str(prim.GetPath()),
        "name": str(prim.GetName()),
        "type": str(prim.GetTypeName() or "") or None,
        "active": bool(prim.IsActive()),
        "defined": bool(prim.IsDefined()),
        "loaded": bool(prim.IsLoaded()),
        "instance": bool(prim.IsInstance()),
        "instanceable": bool(prim.IsInstanceable()),
        "kind": prim.GetMetadata("kind"),
        "attributes": attributes,
        "primvars": primvars,
        "relationships": relationships,
        "material_bindings": material_bindings,
        "property_count": len(properties),
        "properties_truncated": len(properties) > max_properties,
    }


# ---------------------------------------------------------------------------
# 通用动词层（node 域 + parm 域）
# 设计见 docs/tool-design.md。铁律：节点参数统一接受 hou.Node 或 path 字符串；
# 返回精简 JSON 安全；只增不改；hou 永远是逃生舱。
# ---------------------------------------------------------------------------

def _resolve(node) -> hou.Node:
    """把 hou.Node 或 path 字符串统一解析成 hou.Node；不存在抛明确错误。"""
    if isinstance(node, hou.Node):
        return node
    if isinstance(node, str):
        n = hou.node(node)
        if n is None:
            raise ValueError(f"no node at path '{node}'")
        return n
    raise ValueError(f"expected a node or path string, got {type(node).__name__}")


def _val(v):
    """把 HOM 值转成 JSON 安全（Vector/Matrix/Color → list），其余原样返回。"""
    if isinstance(v, (hou.Vector2, hou.Vector3, hou.Vector4)):
        return [float(x) for x in v]
    if isinstance(v, hou.Color):
        return [float(v.r()), float(v.g()), float(v.b()), float(v.a())]
    if isinstance(v, (hou.Matrix3, hou.Matrix4)):
        return [[float(x) for x in row] for row in v]
    return v


# --- node 域：查 -----------------------------------------------------------

def find_nodes(pattern: str = "*", category=None, node_type=None, root=None) -> list:
    """在场景里找**已存在**的节点，返回扁平 path 列表（按路径排序）。

    - ``pattern``：glob 匹配节点名（``fnmatch``）。
    - ``category``：可选，按节点类别过滤（'sop'/'obj'/...）。
    - ``node_type``：可选，按类型名过滤（基名或全名，不区分大小写）。
    - ``root``：从哪个节点开始搜（默认 '/'）。
    """
    root_node = _resolve(root) if root is not None else hou.node("/")
    cat = _category(category) if category else None
    qtype = node_type.lower() if isinstance(node_type, str) else None

    results = []
    for n in root_node.allSubChildren():
        if pattern and pattern != "*" and not fnmatch.fnmatch(n.name(), pattern):
            continue
        if cat is not None and n.type().category().name() != cat.name():
            continue
        if qtype is not None:
            tname = n.type().name()
            base = tname.split("::", 1)[0]
            if qtype not in (tname.lower(), base.lower()):
                continue
        results.append(n.path())
    results.sort()
    return results


def _neighbors(node: hou.Node, direction: str) -> list:
    # 防御：HOM 文档口径里 inputs() 可能含 None 占位（未连接的输入），
    # 实测 H21/H22 是紧凑元组，但此处不赌版本行为。
    if direction == "up":
        return [n for n in node.inputs() if n is not None]
    if direction == "down":
        return [n for n in node.outputs() if n is not None]
    raise ValueError(f"bad direction {direction!r}")


def _hop_paths(node: hou.Node, direction: str, depth: int) -> list:
    """BFS 收集 depth 跳内的邻接节点 path（不含自身），去重、按 path 排序。"""
    if depth < 1:
        return []
    seen: set[str] = set()
    frontier = [node]
    for _ in range(depth):
        nxt = []
        for x in frontier:
            for nb in _neighbors(x, direction):
                p = nb.path()
                if p not in seen:
                    seen.add(p)
                    nxt.append(nb)
        frontier = nxt
    return sorted(seen)


def graph(node, depth: int = 1, direction: str = "both") -> dict:
    """返回节点的直接依赖关系（默认 1 跳）。

    - ``inputs``：直接上游（数据流输入）。
    - ``outputs``：直接下游（谁把本节点当输入）。
    - ``parm_refs``：通过 ``ch()`` 等表达式引用本节点的节点（`outputs()` 看不到的隐形边）。
    - ``depth``：按需递归（>1 时 BFS）；``direction``：'up'/'down'/'both'。
    """
    n = _resolve(node)
    up = _hop_paths(n, "up", depth) if direction in ("both", "up") else []
    down = _hop_paths(n, "down", depth) if direction in ("both", "down") else []
    refs = sorted(x.path() for x in n.parmsReferencingThis())
    return {"path": n.path(), "inputs": up, "outputs": down, "parm_refs": refs}


def _geo_summary(geo) -> dict:
    s: dict = {}
    for intrinsic, key in (
        ("pointcount", "points"),
        ("primitivecount", "prims"),
        ("vertexcount", "verts"),
        ("pointattributes", "point_attrs"),
        ("primitiveattributes", "prim_attrs"),
        ("vertexattributes", "vertex_attrs"),
        ("detailattributes", "detail_attrs"),
    ):
        try:
            s[key] = geo.intrinsicValue(intrinsic)
        except Exception:
            s[key] = None
    try:
        bb = geo.boundingBox()
        s["bbox_min"] = [float(x) for x in bb.minvec()]
        s["bbox_max"] = [float(x) for x in bb.maxvec()]
    except Exception:
        pass
    return s


def describe(node) -> dict:
    """节点状态 + 几何摘要 + 帮助元数据（Stage 1）——一次拿到「它现在什么状态、流着什么数据」。"""
    n = _resolve(node)
    t = n.type()
    info: dict = {
        "path": n.path(),
        "name": n.name(),
        "type": t.name(),
        "category": t.category().name(),
    }

    # 生命周期状态
    try:
        info["bypassed"] = n.isBypassed()
    except Exception:
        info["bypassed"] = False
    try:
        info["locked_hda"] = n.isLockedHDA()
    except Exception:
        info["locked_hda"] = False
    try:
        info["needs_cook"] = n.needsToCook()
    except Exception:
        info["needs_cook"] = None
    try:
        info["errors"] = list(n.errors())
    except Exception:
        info["errors"] = []
    try:
        info["warnings"] = list(n.warnings())
    except Exception:
        info["warnings"] = []

    # 几何摘要（仅 SOP 有 geometry()）。用类别对象比较而非名字字符串：
    # category().name() 返回 'Sop'（首字母大写），== 'sop' 永不成立——这个
    # 大小写 bug 让 describe 长期静默不返回 geometry（2026-08-19 实证：草地
    # trace 里 agent 在 describe 之后仍手写 bbox/点数循环，就是因为拿不到）。
    if t.category() == hou.sopNodeTypeCategory():
        geo = None
        try:
            geo = n.geometry()
            info["geometry"] = _geo_summary(geo) if geo is not None else None
        except Exception:
            info["geometry"] = None

        # 属性增量（attrib_delta）：本节点相对 input 0 增/删了哪些属性——
        # MMB 节点信息里美术心算的那一步（「这个节点对数据干了什么」），
        # 固化为动词输出。只对 input 0 做 diff（merge 类多输入节点的语义
        # 是合并，diff 无意义）；只报名称增删，不报值变化（贵且误导）。
        # cook 本节点已拉起上游 cook，两个几何体都在缓存里，代价≈集合运算。
        if geo is not None:
            try:
                inputs = n.inputs()
                up = inputs[0] if inputs else None
                if up is not None and up.type().category() == hou.sopNodeTypeCategory():
                    up_geo = up.geometry()
                    if up_geo is not None:
                        delta: dict[str, Any] = {}
                        for intrinsic, cls in (
                            ("pointattributes", "point"),
                            ("primitiveattributes", "prim"),
                            ("vertexattributes", "vertex"),
                            ("detailattributes", "detail"),
                        ):
                            try:
                                before = set(up_geo.intrinsicValue(intrinsic) or [])
                                after = set(geo.intrinsicValue(intrinsic) or [])
                            except Exception:
                                continue
                            added = sorted(after - before)
                            removed = sorted(before - after)
                            if added:
                                delta.setdefault("added", {})[cls] = added
                            if removed:
                                delta.setdefault("removed", {})[cls] = removed
                        if delta:
                            info["attrib_delta"] = delta
            except Exception:
                pass

    # 帮助元数据（Stage 1：免费元数据，完整帮助见 tool-design.md 三阶段）
    help_meta: dict = {}
    try:
        help_meta["description"] = t.description()
    except Exception:
        help_meta["description"] = None
    try:
        help_meta["default_help_url"] = t.defaultHelpUrl()
    except Exception:
        help_meta["default_help_url"] = None
    try:
        help_meta["embedded_help"] = t.embeddedHelp() or None
    except Exception:
        help_meta["embedded_help"] = None
    info["help"] = help_meta

    return info


# --- node 域：写 -----------------------------------------------------------

_OBJECT_PARENT_REASONS = {
    "scene_assembly",
    "camera_light_null",
    "existing_legacy",
    "explicit_user",
    "downstream_obj_delivery",
}


def _matrix_values(matrix) -> list[float]:
    return [float(value) for value in matrix.asTuple()]


def set_object_parent(child, parent, keep_world: bool = True, reason: str = "",
                      index: int = 0, allow_foreign: str | None = None) -> dict:
    """显式设置 OBJ parent，参数顺序是 ``child, parent``。

    这是 scene hierarchy 例外入口，不是新建几何 FK rig 的默认表示。``reason``
    必须是 ``scene_assembly/camera_light_null/existing_legacy/explicit_user/``
    ``downstream_obj_delivery`` 之一。``parent=None`` 表示 unparent；普通父级
    使用 ``index=0``，Blend 等明确多输入对象可指定其他 input。
    ``keep_world=True`` 在改层级后恢复 child 的原世界变换，并回读验证 parent。
    """
    c = _resolve(child)
    p = None if parent is None else _resolve(parent)
    obj_category = hou.objNodeTypeCategory()
    if c.type().category() != obj_category:
        raise ValueError(f"set_object_parent 的 child 必须是 OBJ，收到 {c.path()}")
    if p is not None and p.type().category() != obj_category:
        raise ValueError(f"set_object_parent 的 parent 必须是 OBJ 或 None，收到 {p.path()}")
    reason = str(reason or "").strip()
    if reason not in _OBJECT_PARENT_REASONS:
        raise ValueError(
            "reason 必须明确 OBJ parenting 的合法边界，可用："
            f"{sorted(_OBJECT_PARENT_REASONS)}。新建几何父子机械/FK 请使用 KineFX。"
        )
    if p is not None and int(p.sessionId()) == int(c.sessionId()):
        raise ValueError("对象不能 parent 到自身")
    index = int(index)
    if index < 0 or index >= len(c.inputConnectors()):
        raise ValueError(
            f"input index {index} 超出 {c.path()} 的有效范围 "
            f"0..{len(c.inputConnectors()) - 1}"
        )
    if p is not None:
        pending = [p]
        seen = set()
        while pending:
            cursor = pending.pop()
            sid = int(cursor.sessionId())
            if sid in seen:
                continue
            seen.add(sid)
            if int(cursor.sessionId()) == int(c.sessionId()):
                raise ValueError(
                    f"OBJ parenting 会形成环：{c.path()} <- {p.path()}"
                )
            pending.extend(item for item in cursor.inputs() if item is not None)

    _require_owned(c, "set_object_parent child", allow_foreign)
    previous = c.input(index)
    world_before = c.worldTransform()
    local_before = {
        "t": [float(v) for v in c.parmTuple("t").eval()],
        "r": [float(v) for v in c.parmTuple("r").eval()],
        "s": [float(v) for v in c.parmTuple("s").eval()],
    }
    c.setInput(index, p)
    if bool(keep_world):
        c.setWorldTransform(world_before)
    actual = c.input(index)
    actual_matches = (
        (actual is None and p is None)
        or (actual is not None and p is not None
            and int(actual.sessionId()) == int(p.sessionId()))
    )
    if not actual_matches:
        raise RuntimeError(
            f"OBJ parenting 回读不一致：requested={p.path() if p else None}, "
            f"actual={actual.path() if actual else None}"
        )
    world_after = c.worldTransform()
    before_values = _matrix_values(world_before)
    after_values = _matrix_values(world_after)
    world_delta = max(abs(a - b) for a, b in zip(before_values, after_values))
    return {
        "child": c.path(),
        "parent": p.path() if p is not None else None,
        "previous_parent": previous.path() if previous is not None else None,
        "input": index,
        "reason": reason,
        "keep_world": bool(keep_world),
        "verified": actual_matches,
        "world_transform_preserved": world_delta <= 1e-6 if keep_world else None,
        "world_delta_max": world_delta,
        "local_before": local_before,
        "local_after": {
            "t": [float(v) for v in c.parmTuple("t").eval()],
            "r": [float(v) for v in c.parmTuple("r").eval()],
            "s": [float(v) for v in c.parmTuple("s").eval()],
        },
    }

def connect(src, dst, index: int = 0, allow_foreign: str | None = None) -> dict:
    """把 ``src`` 的输出连到 ``dst`` 的第 ``index`` 个输入。

    只表达普通网络 dataflow；OBJ→OBJ 是 parenting，明确拒绝并要求
    ``set_object_parent(child, parent, reason=...)``。
    返回 ``{"node": dst path, "input": 实际落到的输入口, "position_adjusted": bool}``。
    请求的端口不存在时退化为「下一个可用输入」，此时返回里会带 ``note``——落口
    与请求不一致必须让调用方知道，静默改口会让 agent 基于错误的连线继续推理。
    连接成功后做 flow 纠流（``_snap_into_flow``）：dst 不在所有输入下游时 snap 到
    输入正下方；已在下游的节点绝不动。
    """
    s = _resolve(src)
    d = _resolve(dst)
    if (s.type().category() == hou.objNodeTypeCategory()
            and d.type().category() == hou.objNodeTypeCategory()):
        raise ValueError(
            "connect 只表达网络数据流，不执行 OBJ parenting。"
            f"当前连线会把 {s.path()} 作为 parent、{d.path()} 作为 child；"
            "请改用 set_object_parent(child, parent, keep_world=True, reason=...)。"
            "新建几何父子机械/FK 默认使用 KineFX；/obj 只表示创建位置。"
        )
    _require_owned(d, "connect destination", allow_foreign)
    try:
        d.setInput(index, s)
        return {"node": d.path(), "input": index, "position_adjusted": _snap_into_flow(d)}
    except Exception:
        pass
    try:
        d.setNextInput(s)
    except Exception as e:
        raise ValueError(
            f"连接失败：{s.path()} → {d.path()}：输入口 {index} 不存在，"
            f"且没有可退化的空闲输入口（{e}）"
        ) from e
    used = [i for n_, i, _o in d.inputsWithIndices() if n_ == s]
    return {
        "node": d.path(),
        "input": used[-1] if used else None,
        "note": f"请求的输入口 {index} 不可用，已退化为下一个可用输入",
        "position_adjusted": _snap_into_flow(d),
    }


def disconnect_input(dst, index: int = 0, allow_foreign: str | None = None) -> dict:
    """断开普通网络 ``dst`` 输入；OBJ unparent 改用 ``set_object_parent``。"""
    d = _resolve(dst)
    if d.type().category() == hou.objNodeTypeCategory():
        raise ValueError(
            "disconnect_input 不执行 OBJ unparent；请用 "
            "set_object_parent(child, None, keep_world=True, reason=...)"
        )
    _require_owned(d, "disconnect_input", allow_foreign)
    index = int(index)
    if index < 0 or index >= len(d.inputConnectors()):
        raise ValueError(f"输入口 {index} 超出 {d.path()} 的有效范围 0..{len(d.inputConnectors()) - 1}")
    previous = d.input(index)
    d.setInput(index, None)
    return {
        "node": d.path(),
        "input": index,
        "disconnected": previous.path() if previous is not None else None,
    }


def rename_node(node, name: str, allow_foreign: str | None = None) -> str:
    """重命名节点（自动去重），返回新 path。"""
    n = _resolve(node)
    _require_owned(n, "rename_node", allow_foreign)
    n.setName(name, unique_name=True)
    return n.path()


def delete_node(node, allow_foreign: str | None = None) -> dict:
    """删除普通节点；持久 render_view 服务节点受生命周期守卫保护。"""
    n = _resolve(node)
    if n.userData(_RENDER_OWNER_KEY) == _RENDER_OWNER_VALUE:
        raise ValueError(
            f"{n.path()} belongs to the persistent dsh-houdini render service; "
            "do not delete it during the Houdini session. render_view reuses "
            "this infrastructure and clears its live source reference after each render."
        )
    _require_owned(n, "delete_node", allow_foreign)
    refs = sorted(x.path() for x in n.parmsReferencingThis())
    session_ids = [int(n.sessionId())]
    session_ids.extend(int(child.sessionId()) for child in n.allSubChildren())
    path = n.path()
    n.destroy()
    for session_id in session_ids:
        _OWNED_NODE_SESSIONS.pop(session_id, None)
    result: dict = {"deleted": path}
    if refs:
        result["orphaned_parm_refs"] = refs
    return result


def cook_node(node, force: bool = False) -> dict:
    """cook 节点并采集 errors/warnings；``healthy`` 要求两者都为空。"""
    n = _resolve(node)
    cook_error = None
    try:
        n.cook(force=bool(force))
    except Exception as e:  # hou.OperationFailed 等
        cook_error = str(e)
    errors = list(n.errors())
    if cook_error and cook_error not in errors:
        errors.insert(0, cook_error)
    warnings = list(n.warnings())
    return {
        "path": n.path(),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
        "warning_free": not warnings,
        "healthy": not errors and not warnings,
        "forced": bool(force),
    }


def sop_set_output(node, render: bool = True,
                   allow_foreign: str | None = None) -> dict:
    """把 SOP display（默认连同 render）旗标移到指定输出节点。

    这是用户 viewport/交付状态，不是 ``render_view`` 的前置条件；agent 的
    离屏验证会从显式 SOP 建 proxy，不依赖这里的旗标。
    """
    n = _resolve(node)
    _require_owned(n, "sop_set_output", allow_foreign)
    if n.type().category() != hou.sopNodeTypeCategory():
        raise ValueError(
            f"sop_set_output 只接受 SOP，收到 {n.path()} "
            f"({n.type().category().name()})；OBJ 可见性请用 set_object_visible"
        )
    n.setDisplayFlag(True)
    if render:
        n.setRenderFlag(True)
    return {
        "context": "sop",
        "node": n.path(),
        "display": True,
        "render": bool(render),
    }


def sop_output_node(parent) -> dict:
    """报告 SOP 网络的 singular display/render 输出节点。"""
    p = _resolve(parent)
    try:
        child_category = p.childTypeCategory()
    except Exception:
        child_category = None
    if child_category != hou.sopNodeTypeCategory():
        raise ValueError(
            f"sop_output_node 需要包含 SOP 的父网络，收到 {p.path()}；"
            "OBJ 层是 plural visibility，请用 visible_objects('/obj')"
        )

    def _flag(name):
        try:
            return getattr(p, name)()
        except Exception:
            return None

    d = _flag("displayNode")
    r = _flag("renderNode")
    result: dict = {
        "context": "sop",
        "parent": p.path(),
        "display": d.path() if d is not None else None,
        "render": r.path() if r is not None else None,
    }
    if d is not None:
        downstream = [o.path() for o in d.outputs()]
        result["is_leaf"] = not downstream
        if downstream:
            result["note"] = (
                f"display 旗标不在链尾，下游 {len(downstream)} 个节点 "
                f"({', '.join(downstream[:5])}) 不会显示/渲染；"
                "如需以链尾为输出，用 set_display 把旗标移过去"
            )
    return result


def set_object_visible(node, visible: bool = True,
                       allow_foreign: str | None = None) -> dict:
    """设置单个 OBJ 的 viewport 可见性；OBJ 没有 SOP 式 render flag。"""
    n = _resolve(node)
    _require_owned(n, "set_object_visible", allow_foreign)
    if n.type().category() != hou.objNodeTypeCategory():
        raise ValueError(
            f"set_object_visible 只接受 OBJ，收到 {n.path()} "
            f"({n.type().category().name()})；SOP 输出请用 sop_set_output"
        )
    n.setDisplayFlag(bool(visible))
    effective = None
    try:
        effective = bool(n.isObjectDisplayed())
    except Exception:
        pass
    return {
        "context": "obj",
        "node": n.path(),
        "visible": bool(n.isDisplayFlagSet()),
        "effective_visible": effective,
    }


def visible_objects(root="/obj") -> dict:
    """列出 OBJ 层所有对象的 plural visibility 状态。"""
    p = _resolve(root)
    try:
        child_category = p.childTypeCategory()
    except Exception:
        child_category = None
    if child_category != hou.objNodeTypeCategory():
        raise ValueError(
            f"visible_objects 需要 OBJ manager（通常 /obj），收到 {p.path()}"
        )
    objects = []
    for child in p.children():
        try:
            visible = bool(child.isDisplayFlagSet())
        except Exception:
            continue
        try:
            effective = bool(child.isObjectDisplayed())
        except Exception:
            effective = None
        objects.append({
            "path": child.path(),
            "type": child.type().name(),
            "visible": visible,
            "effective_visible": effective,
            "agent_owned": child.userData(_RENDER_OWNER_KEY) == _RENDER_OWNER_VALUE,
            "provenance": node_provenance(child)["status"],
        })
    return {"context": "obj", "root": p.path(), "objects": objects}


def set_display(node, render: bool = True,
                allow_foreign: str | None = None) -> dict:
    """兼容入口：SOP → sop_set_output；OBJ → set_object_visible。

    新代码请使用语义明确的新动词。OBJ 没有独立 render flag，``render`` 在
    OBJ 分支被忽略并回报 note。
    """
    n = _resolve(node)
    if n.type().category() == hou.sopNodeTypeCategory():
        return sop_set_output(n, render=render, allow_foreign=allow_foreign)
    if n.type().category() == hou.objNodeTypeCategory():
        result = set_object_visible(n, True, allow_foreign=allow_foreign)
        result["note"] = "OBJ 没有 SOP 式 render flag；render 参数已忽略"
        return result
    raise ValueError(
        f"set_display 不支持 {n.path()} ({n.type().category().name()})；"
        "请用 sop_set_output 或 set_object_visible"
    )


def display_node(parent) -> dict:
    """兼容入口：SOP 网络 → sop_output_node；OBJ manager → visible_objects。"""
    p = _resolve(parent)
    try:
        child_category = p.childTypeCategory()
    except Exception:
        child_category = None
    if child_category == hou.sopNodeTypeCategory():
        return sop_output_node(p)
    if child_category == hou.objNodeTypeCategory():
        return visible_objects(p)
    raise ValueError(
        f"display_node 无法判断 {p.path()} 的显示语义；"
        "请用 sop_output_node 或 visible_objects"
    )


def _layout_flow(items, horizontal_spacing: float, vertical_spacing: float) -> None:
    """flow 布局：按最长路径深度分行（深度 0 最上），同深度按当前 x 排序保持
    左右阅读顺序、等距排开并整体居中。有环时环上边按 0 深度贡献兜底，不断裂。"""
    item_ids = {int(n.sessionId()) for n in items}
    depth: dict[int, int] = {}

    def visit(node, visiting: set) -> int:
        sid = int(node.sessionId())
        if sid in depth:
            return depth[sid]
        if sid in visiting:  # 环：按 0 贡献兜底
            return 0
        visiting.add(sid)
        ups = [i for i in node.inputs() if i is not None and int(i.sessionId()) in item_ids]
        d = 0 if not ups else 1 + max(visit(i, visiting) for i in ups)
        visiting.discard(sid)
        depth[sid] = d
        return d

    for n in items:
        visit(n, set())

    h_gap, v_gap = _flow_gaps(items)
    h_pitch = float(horizontal_spacing) if horizontal_spacing > 0 else h_gap
    v_pitch = float(vertical_spacing) if vertical_spacing > 0 else v_gap

    rows: dict[int, list] = {}
    for n in items:
        rows.setdefault(depth[int(n.sessionId())], []).append(n)
    for d, row in rows.items():
        row.sort(key=lambda n: (float(n.position().x()), n.path()))
        for i, n in enumerate(row):
            x = (i - (len(row) - 1) / 2.0) * h_pitch
            n.setPosition(hou.Vector2(x, -d * v_pitch))


def layout_nodes(parent, nodes=None, horizontal_spacing: float = -1.0,
                 vertical_spacing: float = -1.0,
                 allow_foreign: str | None = None,
                 mode: str = "children") -> dict:
    """布局全部或显式指定的网络项。

    ``mode='children'``（默认）= 原生 layoutChildren，行为不变；
    ``mode='flow'`` = 自研拓扑分层（``_layout_flow``）：深度 0 最上、
    y = −depth × 垂直间距，同深度按当前 x 排序居中，环上边兜底不断裂。
    ownership 过滤与 ``foreign_nodes_skipped`` 语义两种模式一致。
    """
    if mode not in ("children", "flow"):
        raise ValueError(f"mode 必须是 'children' 或 'flow'，收到 {mode!r}")
    p = _resolve(parent)
    items = []
    foreign_skipped = []
    if nodes is not None:
        if not isinstance(nodes, (list, tuple)):
            raise ValueError("nodes 必须是 Node/path 列表或 None（None = 全部子项）")
        for item in nodes:
            n = _resolve(item)
            if n.parent() != p:
                raise ValueError(f"节点 {n.path()} 不属于父网络 {p.path()}")
            _require_owned(n, "layout_nodes", allow_foreign)
            items.append(n)
    elif _ACTIVE_OWNER_SESSION is not None:
        for child in p.children():
            if node_provenance(child)["status"] == "owned_current_session":
                items.append(child)
            else:
                foreign_skipped.append(child.path())
    else:
        items = list(p.children())
    if items:
        if mode == "children":
            p.layoutChildren(
                items=tuple(items),
                horizontal_spacing=float(horizontal_spacing),
                vertical_spacing=float(vertical_spacing),
            )
        else:
            _layout_flow(items, horizontal_spacing, vertical_spacing)
    return {
        "parent": p.path(),
        "mode": mode,
        "nodes": [
            {"path": n.path(), "position": [float(v) for v in n.position()]}
            for n in items
        ],
        "foreign_nodes_skipped": foreign_skipped,
    }


# --- parm 域 ---------------------------------------------------------------

def list_parms(node) -> list:
    """参数**目录**：名字/标签/类型/帮助，不给值（导航用，回答「想改的参数叫什么」）。"""
    n = _resolve(node)
    out = []
    for pt in n.parmTuples():
        entry: dict = {"name": pt.name()}
        tpl = pt.parmTemplate()
        if tpl is not None:
            try:
                entry["label"] = tpl.label()
            except Exception:
                entry["label"] = None
            try:
                entry["type"] = tpl.type().name()
            except Exception:
                entry["type"] = None
            try:
                entry["size"] = tpl.numComponents()
            except Exception:
                try:
                    entry["size"] = len(pt)
                except Exception:
                    pass
            for field, getter in (("help", "help"), ("description", "description")):
                try:
                    v = getattr(tpl, getter)()
                    if v:
                        entry[field] = v
                except Exception:
                    pass
        else:
            entry["label"] = None
        out.append(entry)
    return out


def read_parms(node, changed_only: bool = True) -> list:
    """参数**值**：默认只看「非默认 + 带表达式 + 被引用」的参数（意图解读用）。

    带表达式的参数会顺带解析引用目标（``referenced_parm``），被其他参数引用的
    参数会标 ``referenced_by``——两个方向的依赖对 agent 判断「动谁会波及谁」都需要。
    返回 ``list[dict]``，每项至少有 ``name/value``；不是 name→value 字典。
    """
    n = _resolve(node)
    out = []
    for p in n.parms():
        try:
            is_default = p.isDefault()
        except Exception:
            is_default = False
        # hou.Parm 没有 hasExpression()（H21/H22 均无；静默 try/except 曾让表达式
        # 维度整个失效）。正确判定：expression() 在无表达式时抛 OperationFailed。
        try:
            expr = p.expression()
            has_expr = True
        except Exception:
            expr = None
            has_expr = False
        try:
            # hou.Parm 也没有 isReferencedBy()；引用自省用 parmsReferencingThis()。
            is_ref = bool(p.parmsReferencingThis())
        except Exception:
            is_ref = False
        try:
            keys = list(p.keyframes())
        except Exception:
            keys = []
        try:
            time_dependent = bool(p.isTimeDependent())
        except Exception:
            time_dependent = False
        if changed_only and is_default and not has_expr and not is_ref and not keys and not time_dependent:
            continue
        entry: dict = {"name": p.name()}
        tpl = p.parmTemplate()
        if tpl is not None:
            try:
                entry["label"] = tpl.label()
            except Exception:
                entry["label"] = None
        try:
            entry["value"] = _val(p.eval())
        except Exception:
            try:
                entry["value"] = p.evalAsString()
            except Exception:
                entry["value"] = None
        if has_expr:
            entry["expression"] = expr
            try:
                ref = p.getReferencedParm()
                if ref is not None:
                    entry["referenced_parm"] = ref.path()
            except Exception:
                pass
        if is_ref:
            entry["referenced_by"] = True
        if keys or time_dependent:
            entry["animated"] = True
            entry["time_dependent"] = time_dependent
        if keys:
            frames = sorted(float(key.frame()) for key in keys)
            curves = []
            for key in keys:
                try:
                    curve = key.expression()
                except Exception:
                    curve = None
                if curve and curve not in curves:
                    curves.append(curve)
            entry.update({
                "key_count": len(keys),
                "first_frame": frames[0],
                "last_frame": frames[-1],
            })
            if curves:
                entry["curves"] = curves
        out.append(entry)
    return out


def _clear_animation(p) -> str | None:
    """参数上有表达式/关键帧时清除并返回描述；没有则返回 None。

    2026-08-20 OTL 会话（seq 28944）：``parm.set`` 被 ``$FEND`` 表达式静默架空，
    eval 纹丝不动但无报错。「set 就是 set」——清掉再设，并在返回里告知清了什么。
    """
    try:
        expr = p.expression()
    except Exception:
        expr = None
    keys = []
    try:
        keys = list(p.keyframes())
    except Exception:
        pass
    if expr is None and not keys:
        return None
    desc = f"expression {expr!r}" if expr is not None else f"{len(keys)} keyframe(s)"
    p.deleteAllKeyframes()
    return desc


def set_parm(node, name: str, value,
             allow_foreign: str | None = None) -> dict:
    """设参数（组件名或元组名均可）；失败时列出相似参数名供自纠。

    数值型参数收到字符串值时按**表达式**处理（H21/H22 实测 ``Parm.set(str)``
    对数值参数直接抛 TypeError，必须走 ``setExpression``）——这让
    ``set_parm(n, 'tx', 'ch(\"ty\")')`` 这类最高频操作可用。

    参数上已有表达式/关键帧时**自动清除再设值**（2026-08-20 拍板），返回带
    ``note`` 说明清掉了什么；想保留动画请显式传字符串表达式。
    """
    n = _resolve(node)
    _require_owned(n, "set_parm", allow_foreign)
    p = n.parm(name)
    if p is not None:
        if isinstance(value, str):
            tpl_type = None
            try:
                tpl_type = p.parmTemplate().type()
            except Exception:
                pass
            if tpl_type in (hou.parmTemplateType.Int, hou.parmTemplateType.Float):
                p.setExpression(value)
                return {"parm": p.name(), "expression": value, "value": _val(p.eval())}
        cleared = _clear_animation(p)
        p.set(value)
        out = {"parm": p.name(), "value": _val(p.eval())}
        if cleared:
            out["note"] = f"cleared {cleared}"
        return out

    pt = n.parmTuple(name)
    if pt is not None:
        if isinstance(value, (list, tuple)):
            cleared = [c for pp in pt for c in [_clear_animation(pp)] if c]
            pt.set(value)
            out = {"parm": pt.name(), "value": [_val(v) for v in pt.eval()]}
            if cleared:
                out["note"] = f"cleared {', '.join(cleared)}"
            return out
        comps = [pp.name() for pp in n.parms() if pp.tuple().name() == name]
        raise ValueError(
            f"'{name}' 在 '{n.path()}' 上是 {len(comps)} 分量元组 "
            f"({', '.join(comps)})；请传 list/tuple"
        )

    names = [pp.name() for pp in n.parms()]
    suggestions = difflib.get_close_matches(name, names, n=5, cutoff=0.4)
    raise ValueError(
        f"节点 '{n.path()}' 没有参数 '{name}'。相似参数：{suggestions}"
    )


def set_parms(node, values: dict,
              allow_foreign: str | None = None) -> dict:
    """批量设参：``{name: value}`` 逐项走 ``set_parm`` 同一套语义（含表达式/关键帧清除）。

    **逐项容错**：单项失败不中断，返回分 ``set``/``failed`` 两组——收尾恢复默认值、
    测试摆场景这类「一串赋值」不用再手写 ``parm().set`` 循环。
    """
    n = _resolve(node)
    _require_owned(n, "set_parms", allow_foreign)
    if not isinstance(values, dict) or not values:
        raise ValueError("values 必须是非空 dict：{参数名: 值}")
    done, failed, notes = {}, {}, {}
    for key, value in values.items():
        try:
            r = set_parm(n, key, value, allow_foreign=allow_foreign)
            done[r["parm"]] = r.get("value", r.get("expression"))
            if "note" in r:
                notes[r["parm"]] = r["note"]
        except Exception as e:
            failed[key] = str(e)
    out = {"node": n.path(), "set": done}
    if notes:
        out["notes"] = notes
    if failed:
        out["failed"] = failed
    return out


_KEYFRAME_CURVES = {
    "constant": "constant()",
    "linear": "linear()",
    "bezier": "bezier()",
}
_KEYFRAME_INPUT_LIMIT = 10_000
_KEYFRAME_RESULT_LIMIT = 64
_KEYFRAME_SAMPLE_LIMIT = 32


def set_keyframes(node, channels: dict, replace: bool = True,
                  allow_foreign: str | None = None) -> dict:
    """批量写入标量数值参数关键帧，统一使用 frame 单位并提交后回读。

    ``channels`` 形如 ``{"tx": [{"frame": 1, "value": 0, "curve": "linear"}]}``。
    curve 仅支持 ``constant/linear/bezier``；它描述从该 key 离开的 segment。
    所有 channel 在修改前完成校验；任一写入失败会恢复本次涉及参数的原 keyframes。
    ``replace=False`` 保留旧 keys，但拒绝覆盖同一 frame。该动词只负责 channel 数据，
    不替代有序状态机、KineFX/APEX rig logic 或 Animation Editor。
    """
    n = _resolve(node)
    _require_owned(n, "set_keyframes", allow_foreign)
    if not isinstance(channels, dict) or not channels:
        raise ValueError("channels 必须是非空 dict：{标量参数名: key spec 列表}")
    if not isinstance(replace, bool):
        raise ValueError("replace 必须是 bool")

    prepared = {}
    originals = {}
    for parm_name, specs in channels.items():
        if not isinstance(parm_name, str) or not parm_name:
            raise ValueError(f"channel 名必须是非空字符串，收到 {parm_name!r}")
        parm = n.parm(parm_name)
        if parm is None:
            if n.parmTuple(parm_name) is not None:
                raise ValueError(
                    f"{n.path()}/{parm_name} 是参数元组；请按组件名分别提供 channel"
                )
            suggestions = difflib.get_close_matches(
                parm_name, [item.name() for item in n.parms()], n=5, cutoff=0.4
            )
            raise ValueError(
                f"节点 {n.path()} 没有标量参数 {parm_name!r}；相似参数：{suggestions}"
            )
        template = parm.parmTemplate()
        try:
            template_type = template.type()
        except Exception:
            template_type = None
        if template_type not in (hou.parmTemplateType.Int, hou.parmTemplateType.Float):
            raise ValueError(
                f"{parm.path()} 不是数值标量参数（类型={template_type}），不能写数值 keyframes"
            )
        if not isinstance(specs, (list, tuple)) or not specs:
            raise ValueError(f"channels[{parm_name!r}] 必须是非空 key spec 列表")
        if len(specs) > _KEYFRAME_INPUT_LIMIT:
            raise ValueError(
                f"channels[{parm_name!r}] 超过 {_KEYFRAME_INPUT_LIMIT} keys；"
                "请拆分任务或使用缓存/clip 工作流"
            )

        existing_keys = tuple(parm.keyframes())
        originals[parm_name] = existing_keys
        existing_frames = {float(key.frame()) for key in existing_keys}
        seen_frames = set()
        keys = []
        for index, spec in enumerate(specs):
            path = f"channels[{parm_name!r}][{index}]"
            if not isinstance(spec, dict):
                raise ValueError(f"{path} 必须是 dict")
            unknown = set(spec) - {"frame", "value", "curve"}
            if unknown:
                raise ValueError(f"{path} 有未知字段：{sorted(unknown)}")
            if "frame" not in spec or "value" not in spec:
                raise ValueError(f"{path} 必须同时提供 frame 和 value")
            if isinstance(spec["frame"], bool) or isinstance(spec["value"], bool):
                raise ValueError(f"{path}.frame/value 不能是 bool")
            frame = float(spec["frame"])
            value = float(spec["value"])
            if not math.isfinite(frame) or not math.isfinite(value):
                raise ValueError(f"{path}.frame/value 必须是有限数值")
            if frame in seen_frames:
                raise ValueError(f"{path}.frame={frame} 在同一 channel 重复")
            if not replace and frame in existing_frames:
                raise ValueError(
                    f"{path}.frame={frame} 已存在；replace=False 不允许覆盖旧 key"
                )
            seen_frames.add(frame)
            curve_name = str(spec.get("curve", "bezier")).strip().lower()
            expression = _KEYFRAME_CURVES.get(curve_name)
            if expression is None:
                raise ValueError(
                    f"{path}.curve={curve_name!r} 不支持；可用 {sorted(_KEYFRAME_CURVES)}"
                )
            key = hou.Keyframe(value)
            key.setFrame(frame)
            key.setExpression(expression, hou.exprLanguage.Hscript)
            keys.append(key)
        prepared[parm_name] = (parm, tuple(sorted(keys, key=lambda key: key.frame())))

    saved_frame = float(hou.frame())
    applied = []
    try:
        for parm_name, (parm, keys) in prepared.items():
            if replace:
                parm.deleteAllKeyframes()
            parm.setKeyframes(keys)
            applied.append(parm_name)
    except Exception:
        for parm_name, (parm, _) in prepared.items():
            try:
                parm.deleteAllKeyframes()
                if originals[parm_name]:
                    parm.setKeyframes(originals[parm_name])
            except Exception:
                pass
        raise
    finally:
        if float(hou.frame()) != saved_frame:
            hou.setFrame(saved_frame)

    result = {}
    for parm_name, (parm, _) in prepared.items():
        keys = tuple(parm.keyframes())
        frames = [float(key.frame()) for key in keys]
        key_data = []
        for key in keys:
            try:
                curve = key.expression()
            except Exception:
                curve = None
            key_data.append({
                "frame": float(key.frame()),
                "value": float(key.value()),
                "curve": curve,
            })
        if len(key_data) > _KEYFRAME_RESULT_LIMIT:
            key_preview = (
                key_data[:_KEYFRAME_RESULT_LIMIT // 2]
                + key_data[-_KEYFRAME_RESULT_LIMIT // 2:]
            )
            keys_truncated = len(key_data) - len(key_preview)
        else:
            key_preview = key_data
            keys_truncated = 0
        sample_candidates = sorted(set([
            frames[0],
            frames[-1],
            *(
                (frames[index] + frames[index + 1]) / 2.0
                for index in range(len(frames) - 1)
            ),
        ]))
        if len(sample_candidates) > _KEYFRAME_SAMPLE_LIMIT:
            sample_frames = (
                sample_candidates[:_KEYFRAME_SAMPLE_LIMIT // 2]
                + sample_candidates[-_KEYFRAME_SAMPLE_LIMIT // 2:]
            )
        else:
            sample_frames = sample_candidates
        result[parm_name] = {
            "key_count": len(keys),
            "first_frame": frames[0],
            "last_frame": frames[-1],
            "keys": key_preview,
            "samples": {
                str(frame): float(parm.evalAtFrame(frame)) for frame in sample_frames
            },
            "replaced_existing": len(originals[parm_name]) if replace else 0,
        }
        if keys_truncated:
            result[parm_name]["keys_truncated"] = keys_truncated
    return {
        "node": n.path(),
        "replace": replace,
        "channels": result,
        "frame_restored": float(hou.frame()) == saved_frame,
    }


def _spare_spec_template(item: dict, path: str, names: set):
    if not isinstance(item, dict):
        raise ValueError(f"{path} 必须是 dict")
    kind = str(item.get("type", "")).strip().lower()
    if kind not in {"folder", "toggle", "int", "float", "string"}:
        raise ValueError(
            f"{path}.type 不支持 {kind!r}；可用 folder/toggle/int/float/string"
        )
    name = item.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"{path}.name 必须是合法 Houdini 参数名")
    if name in names:
        raise ValueError(f"参数/文件夹名 {name!r} 重复")
    names.add(name)
    label = str(item.get("label", name.replace("_", " ").title()))
    if kind == "folder":
        children = item.get("parms", [])
        if not isinstance(children, (list, tuple)) or not children:
            raise ValueError(f"{path}.parms 必须是非空 list")
        template = hou.FolderParmTemplate(name, label, folder_type=hou.folderType.Simple)
        for index, child in enumerate(children):
            template.addParmTemplate(
                _spare_spec_template(child, f"{path}.parms[{index}]", names)
            )
    elif kind == "toggle":
        template = hou.ToggleParmTemplate(
            name, label, default_value=bool(item.get("default", False))
        )
    elif kind in ("int", "float"):
        default = item.get("default", 0)
        minimum = item.get("min", 0)
        maximum = item.get("max", 10)
        kwargs = {
            "default_value": (float(default),) if kind == "float" else (int(default),),
            "min": float(minimum) if kind == "float" else int(minimum),
            "max": float(maximum) if kind == "float" else int(maximum),
            "min_is_strict": bool(item.get("min_strict", False)),
            "max_is_strict": bool(item.get("max_strict", False)),
        }
        cls = hou.FloatParmTemplate if kind == "float" else hou.IntParmTemplate
        template = cls(name, label, 1, **kwargs)
    else:
        template = hou.StringParmTemplate(
            name, label, 1, default_value=(str(item.get("default", "")),)
        )
    if item.get("help") is not None:
        template.setHelp(str(item["help"]))
    return template


def create_spare_parms(node, code_parm: str = "snippet",
                       defaults: dict | None = None,
                       spec: list | None = None,
                       allow_foreign: str | None = None) -> dict:
    """从代码参数的 ch/chf/chi/chv/chs 引用创建缺失 spare parameters。

    对齐 Wrangle 参数编辑器的 Create Parameters 意图，但要求默认值显式可审计；
    已存在参数不重建。``chramp`` 等复杂引用列入 unsupported，交给 HDA/interface
    或裸 hou 处理。

    ``spec`` 的精确递归 schema：folder 条目是
    ``{"type":"folder","name":"controls","label":"Controls","parms":[...]}``；
    scalar 条目是 ``{"type":"toggle|int|float|string","name":"speed",
    "label":"Speed","default":1,"min":0,"max":10,
    "min_strict":False,"max_strict":False,"help":"..."}``。只有 folder 接受
    ``parms``；scalar 必须有 ``name``，其余字段可选。例如::

        create_spare_parms(node, spec=[
            {"type": "folder", "name": "controls", "parms": [
                {"type": "toggle", "name": "enabled", "default": True},
                {"type": "float", "name": "speed", "default": 1.0,
                 "min": 0.0, "max": 10.0},
            ]},
        ])

    spec 模式返回 ``node/mode/created/leaf_values``；扫描模式返回
    ``node/code_parm/references/created/existing/defaults_applied/unsupported``。
    """
    n = _resolve(node)
    _require_owned(n, "create_spare_parms", allow_foreign)
    if spec is not None:
        if not isinstance(spec, (list, tuple)) or not spec:
            raise ValueError("spec 必须是非空 list")
        names = set()
        templates = [
            _spare_spec_template(item, f"spec[{index}]", names)
            for index, item in enumerate(spec)
        ]
        conflicts = sorted(
            name for name in names
            if n.parm(name) is not None or n.parmTuple(name) is not None
        )
        if conflicts:
            raise ValueError(
                f"节点 {n.path()} 已存在同名参数/文件夹：{conflicts}；"
                "显式 spec 不做隐式覆盖"
            )
        group = n.parmTemplateGroup()
        for template in templates:
            group.append(template)
        n.setParmTemplateGroup(group, rename_conflicting_parms=False)
        leaves = []
        def collect(items):
            for item in items:
                if str(item.get("type", "")).strip().lower() == "folder":
                    collect(item.get("parms", []))
                else:
                    leaves.append(item["name"])
        collect(spec)
        return {
            "node": n.path(),
            "mode": "spec",
            "created": sorted(names),
            "leaf_values": {
                name: _val(n.parm(name).eval()) for name in leaves
            },
        }
    defaults = {} if defaults is None else defaults
    if not isinstance(defaults, dict):
        raise ValueError("defaults 必须是 dict：{参数名: 默认值}")
    code_parameter = n.parm(code_parm)
    if code_parameter is None:
        raise ValueError(
            f"节点 {n.path()} 没有代码参数 {code_parm!r}；"
            "先用 list_parms 找真实代码参数名"
        )
    code = code_parameter.evalAsString()
    pattern = re.compile(
        r"\b(?P<func>ch|chf|chi|chv|chs)\s*\(\s*['\"](?P<name>[A-Za-z_]\w*)['\"]"
    )
    references = {}
    for match in pattern.finditer(code):
        references.setdefault(match.group("name"), match.group("func"))
    unsupported = sorted(set(
        match.group(1) for match in re.finditer(
            r"\b(chramp|chdict|chsop|chsoplist)\s*\(", code
        )
    ))
    if not references:
        return {
            "node": n.path(), "code_parm": code_parm,
            "created": [], "existing": [], "unsupported": unsupported,
        }
    group = n.parmTemplateGroup()
    templates = []
    created_names = []
    existing = []
    for name, func in references.items():
        if n.parm(name) is not None or n.parmTuple(name) is not None:
            existing.append(name)
            continue
        label = name.replace("_", " ").title()
        default = defaults.get(name)
        if func == "chi":
            value = int(0 if default is None else default)
            template = hou.IntParmTemplate(name, label, 1, default_value=(value,))
        elif func == "chv":
            if default is None:
                values = (0.0, 0.0, 0.0)
            elif isinstance(default, (list, tuple)) and len(default) == 3:
                values = tuple(float(value) for value in default)
            else:
                raise ValueError(f"chv 参数 {name!r} 的默认值必须是 3 分量 list/tuple")
            template = hou.FloatParmTemplate(name, label, 3, default_value=values)
        elif func == "chs":
            value = "" if default is None else str(default)
            template = hou.StringParmTemplate(name, label, 1, default_value=(value,))
        else:  # ch / chf
            value = float(0.0 if default is None else default)
            template = hou.FloatParmTemplate(name, label, 1, default_value=(value,))
        templates.append(template)
        created_names.append(name)
    for template in templates:
        group.append(template)
    if templates:
        n.setParmTemplateGroup(group, rename_conflicting_parms=False)
    applied = {}
    for name in created_names:
        if name in defaults:
            result = set_parm(n, name, defaults[name])
            applied[name] = result.get("value", result.get("expression"))
    return {
        "node": n.path(),
        "code_parm": code_parm,
        "references": references,
        "created": created_names,
        "existing": existing,
        "defaults_applied": applied,
        "unsupported": unsupported,
    }


# --- asset 域（HDA / 数字资产） ---------------------------------------------

_HDA_MANAGED_TAG = "dsh_houdini::managed"
_PARM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _hda_definition(node) -> tuple[hou.Node, hou.HDADefinition]:
    n = _resolve(node)
    definition = n.type().definition()
    if definition is None:
        raise ValueError(
            f"节点 '{n.path()}' 不是数字资产（node.type().definition() 为 None）；"
            "请先用 hda_create 把 subnet 转为 HDA"
        )
    return n, definition


def _default_hda_file(name: str) -> str:
    hip_path = hou.hipFile.path()
    hip_dir = os.path.dirname(hip_path)
    if not hip_dir or os.path.basename(hip_path).lower() == "untitled.hip":
        raise ValueError(
            "当前 hip 尚未保存，无法推导默认 HDA 位置；请先保存 hip，"
            "或显式传 hda_file"
        )
    file_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._") or "asset"
    return os.path.join(hip_dir, "otls", file_stem + ".hda")


def hda_create(
    node,
    name: str,
    description: str | None = None,
    hda_file: str | None = None,
    min_inputs: int = 0,
    max_inputs: int = 0,
    replace: bool = False,
    allow_foreign: str | None = None,
) -> dict:
    """把已有节点（通常 subnet）转为 HDA；默认写到 ``$HIP/otls``。

    ``replace=False`` 遇到同名已安装类型会报错且零修改。``replace=True`` 会先
    销毁同类型的全部现有实例，再逐一定义 ``destroy()``（只删目标定义，不会粗暴
    uninstall 整个多资产库），最后从传入的源节点重建。传入源节点本身不能已经是
    待替换类型，否则销毁实例后就没有可供重建的源节点。
    """
    n = _resolve(node)
    _require_owned(n, "hda_create", allow_foreign)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name 必须是非空 HDA 类型名")
    name = name.strip()
    if not isinstance(min_inputs, int) or not isinstance(max_inputs, int):
        raise ValueError("min_inputs/max_inputs 必须是整数")
    if min_inputs < 0 or max_inputs < min_inputs:
        raise ValueError(
            f"输入数不合法：需要 0 <= min_inputs <= max_inputs，"
            f"收到 {min_inputs}/{max_inputs}"
        )

    category = n.type().category()
    existing_type = category.nodeTypes().get(name)
    definitions = []
    instances = []
    if existing_type is not None:
        try:
            definitions = list(existing_type.allInstalledDefinitions())
        except Exception:
            d = existing_type.definition()
            definitions = [d] if d is not None else []
        try:
            instances = list(existing_type.instances())
        except Exception:
            instances = []

    # 不能用 replace 抢占 Houdini 原生/编译节点类型；否则 instances() 会把场景里
    # 所有同类原生节点都列出来，按“替换 HDA”语义销毁将造成灾难性误删。
    if existing_type is not None and not definitions:
        raise ValueError(
            f"类型名 '{name}' 已被 Houdini 原生/无可编辑 definition 的节点类型占用；"
            "replace 也不会覆盖它，请换一个带项目/工作室命名空间的 HDA 类型名"
        )

    if (definitions or instances) and not replace:
        files = sorted({d.libraryFilePath() for d in definitions})
        paths = sorted(i.path() for i in instances)
        raise ValueError(
            f"HDA 类型 '{name}' 已存在；definitions={files}，instances={paths}。"
            "确认要整体重建时传 replace=True"
        )
    if replace and existing_type is n.type():
        raise ValueError(
            f"源节点 '{n.path()}' 本身就是待替换类型 '{name}'；"
            "请先建一个普通 subnet 作为重建源，避免 replace 销毁源节点"
        )

    target = _default_hda_file(name) if hda_file is None else hou.expandString(str(hda_file))
    target = os.path.abspath(target)
    parent_dir = os.path.dirname(target)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    destroyed = []
    removed_definitions = []
    if replace:
        # 子实例先删，避免父实例删除后子路径失效。
        for inst in sorted(instances, key=lambda x: x.path().count("/"), reverse=True):
            _require_owned(inst, "hda_create replace instance", allow_foreign)
            path = inst.path()
            session_ids = [int(inst.sessionId())]
            session_ids.extend(int(child.sessionId()) for child in inst.allSubChildren())
            inst.destroy()
            for session_id in session_ids:
                _OWNED_NODE_SESSIONS.pop(session_id, None)
            destroyed.append(path)
        for definition in definitions:
            file_path = definition.libraryFilePath()
            definition.destroy()
            removed_definitions.append(file_path)

    created = n.createDigitalAsset(
        name=name,
        hda_file_name=target,
        description=description,
        min_num_inputs=min_inputs,
        max_num_inputs=max_inputs,
        change_node_type=True,
        create_backup=not replace,
    )
    definition = created.type().definition()
    if definition is None:
        raise RuntimeError(f"createDigitalAsset 返回后类型 '{name}' 没有 definition")
    return {
        "node": created.path(),
        "type": created.type().name(),
        "description": created.type().description(),
        "hda_file": definition.libraryFilePath(),
        "min_inputs": definition.minNumInputs(),
        "max_inputs": definition.maxNumInputs(),
        "replaced": bool(replace),
        "destroyed_instances": destroyed,
        "removed_definitions": removed_definitions,
    }


def _enum_name(value) -> str:
    try:
        return value.name()
    except Exception:
        return str(value).split(".")[-1]


def _template_info(template, depth: int, max_depth: int) -> dict:
    entry = {
        "name": template.name(),
        "label": template.label(),
        "type": _enum_name(template.type()),
    }
    for key, getter in (
        ("hidden", "isHidden"),
        ("join_next", "joinsWithNext"),
        ("help", "help"),
        ("default", "defaultValue"),
        ("menu_items", "menuItems"),
        ("menu_labels", "menuLabels"),
    ):
        try:
            value = getattr(template, getter)()
        except Exception:
            continue
        if value not in (None, "", (), [], {}):
            entry[key] = _val(value)
    try:
        conditions = {
            _enum_name(k): v for k, v in template.conditionals().items()
        }
        if conditions:
            entry["conditionals"] = conditions
    except Exception:
        pass
    try:
        tags = template.tags()
        if tags:
            entry["tags"] = dict(tags)
    except Exception:
        pass
    if isinstance(template, hou.FolderParmTemplate):
        entry["folder_type"] = _enum_name(template.folderType())
        children = list(template.parmTemplates())
        if depth < max_depth:
            entry["parms"] = [
                _template_info(child, depth + 1, max_depth) for child in children
            ]
        elif children:
            entry["parms_omitted"] = len(children)
    return entry


def hda_info(node, max_depth: int = 6) -> dict:
    """只读自省 HDA 定义与参数模板树；普通节点也可查看参数树。"""
    n = _resolve(node)
    if not isinstance(max_depth, int) or max_depth < 0 or max_depth > 20:
        raise ValueError("max_depth 必须是 0..20 的整数")
    definition = n.type().definition()
    out = {
        "node": n.path(),
        "category": n.type().category().name(),
        "type": n.type().name(),
        "description": n.type().description(),
        "definition": None,
        "interface": [
            _template_info(entry, 0, max_depth)
            for entry in n.parmTemplateGroup().entries()
        ],
    }
    if definition is not None:
        sections = []
        for name, section in sorted(definition.sections().items()):
            try:
                size = len(section.contents())
            except Exception:
                size = None
            sections.append({"name": name, "chars": size})
        out["definition"] = {
            "library_file": definition.libraryFilePath(),
            "node_type": definition.nodeTypeName(),
            "description": definition.description(),
            "version": definition.version(),
            "min_inputs": definition.minNumInputs(),
            "max_inputs": definition.maxNumInputs(),
            "sections": sections,
        }
    return out


def _section_contents(definition: hou.HDADefinition, section: str) -> str:
    if not isinstance(section, str) or not section.strip():
        raise ValueError("section 必须是非空字符串")
    section = section.strip()
    sections = definition.sections()
    if section not in sections:
        raise ValueError(
            f"HDA 没有 section {section!r}；现有：{sorted(sections)}"
        )
    return sections[section].contents()


def hda_get_section(node, section: str = "PythonModule") -> dict:
    """读取 HDA section 全文；不存在时列出现有 section 名。"""
    n, definition = _hda_definition(node)
    code = _section_contents(definition, section)
    return {
        "node": n.path(),
        "section": section,
        "code": code,
        "chars": len(code),
        "sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
    }


def _validate_section_code(section: str, code: str) -> None:
    if not isinstance(code, str):
        raise ValueError("code 必须是字符串")
    if section.lower().endswith("pythonmodule"):
        try:
            compile(code, f"<HDA:{section}>", "exec")
        except SyntaxError as e:
            source = (e.text or "").strip()
            where = f"line {e.lineno}" + (f", column {e.offset}" if e.offset else "")
            raise ValueError(
                f"{section} Python 语法错误（{where}）：{e.msg}"
                + (f"；{source}" if source else "")
            ) from e


def _write_hda_section(definition: hou.HDADefinition, section: str, code: str) -> dict:
    _validate_section_code(section, code)
    before = None
    existing = definition.sections().get(section)
    if existing is not None:
        before = existing.contents()
    definition.addSection(section, code)
    actual = _section_contents(definition, section)
    if actual != code:
        raise RuntimeError(
            f"HDA section {section!r} 写后读回不一致："
            f"expected {len(code)} chars, got {len(actual)}"
        )
    return {
        "section": section,
        "changed": before != code,
        "chars": len(code),
        "lines": code.count("\n") + (1 if code else 0),
        "sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
    }


def hda_set_section(node, section: str, code: str,
                    allow_foreign: str | None = None) -> dict:
    """全量写 HDA section；PythonModule 写前编译、写后逐字读回校验。"""
    n, definition = _hda_definition(node)
    _require_owned(n, "hda_set_section", allow_foreign)
    if not isinstance(section, str) or not section.strip():
        raise ValueError("section 必须是非空字符串")
    out = _write_hda_section(definition, section.strip(), code)
    out["node"] = n.path()
    return out


def hda_patch_section(
    node,
    section: str,
    old: str,
    new: str,
    count: int = 1,
    allow_foreign: str | None = None,
) -> dict:
    """按唯一锚点局部替换 HDA section，拒绝缺失或歧义锚点。"""
    n, definition = _hda_definition(node)
    _require_owned(n, "hda_patch_section", allow_foreign)
    if not isinstance(old, str) or not old:
        raise ValueError("old 必须是非空字符串（空锚点会产生歧义）")
    if not isinstance(new, str):
        raise ValueError("new 必须是字符串")
    if not isinstance(count, int) or count <= 0:
        raise ValueError("count 必须是正整数")
    source = _section_contents(definition, section)
    actual_count = source.count(old)
    if actual_count != count:
        raise ValueError(
            f"section {section!r} 中锚点期望出现 {count} 次，实际 {actual_count} 次；"
            "0 次说明锚点过期，多于期望说明锚点不唯一，请扩大 old 上下文"
        )
    patched = source.replace(old, new, count)
    out = _write_hda_section(definition, section, patched)
    out.update({"node": n.path(), "replacements": count})
    return out


def _spec_name(item: dict, path: str) -> str:
    name = item.get("name")
    if not isinstance(name, str) or not _PARM_NAME_RE.fullmatch(name):
        raise ValueError(
            f"{path}.name 必须匹配 {_PARM_NAME_RE.pattern!r}，收到 {name!r}"
        )
    return name


def _menu_data(item: dict, path: str) -> tuple[list[str], list[str]]:
    menu = item.get("menu")
    if not isinstance(menu, dict):
        raise ValueError(f"{path}.menu 必须是 {{items:[...], labels:[...]}}")
    items = menu.get("items")
    labels = menu.get("labels", items)
    if not isinstance(items, (list, tuple)) or not items:
        raise ValueError(f"{path}.menu.items 必须是非空 list")
    if not isinstance(labels, (list, tuple)) or len(labels) != len(items):
        raise ValueError(f"{path}.menu.labels 必须与 items 等长")
    return [str(x) for x in items], [str(x) for x in labels]


def _normalize_hide_when(value, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}.hide_when 必须是非空字符串")
    value = value.strip()
    if not (value.startswith("{") and value.endswith("}")):
        value = "{ " + value + " }"
    return value


def _apply_template_common(template, item: dict, path: str, conditions: dict) -> None:
    help_text = item.get("help")
    if help_text is not None:
        template.setHelp(str(help_text))
    if item.get("join_next"):
        template.setJoinWithNext(True)
    hide_when = _normalize_hide_when(item.get("hide_when"), path)
    if hide_when is not None:
        if isinstance(template, hou.FolderParmTemplate):
            raise ValueError(
                f"{path}.hide_when 不能设在 folder 上；Houdini 不支持 folder conditional，"
                "隐藏整页请用 hide_builtin_tabs 或调整具体参数"
            )
        template.setConditional(hou.parmCondType.HideWhen, hide_when)
        conditions[template.name()] = hide_when
    tags = dict(template.tags())
    user_tags = item.get("tags", {})
    if not isinstance(user_tags, dict):
        raise ValueError(f"{path}.tags 必须是 dict")
    tags.update({str(k): str(v) for k, v in user_tags.items()})
    tags[_HDA_MANAGED_TAG] = "1"
    template.setTags(tags)


def _build_interface_template(
    item: dict,
    path: str,
    names: set,
    conditions: dict,
):
    if not isinstance(item, dict):
        raise ValueError(f"{path} 必须是 dict")
    kind = str(item.get("type", "")).strip().lower()
    if kind not in {
        "folder", "separator", "toggle", "int", "float", "string", "button", "menu"
    }:
        raise ValueError(
            f"{path}.type 不支持 {kind!r}；可用 folder/separator/toggle/int/float/"
            "string/button/menu"
        )
    name = _spec_name(item, path)
    if name in names:
        raise ValueError(f"参数/文件夹名 {name!r} 重复（Houdini 参数名全局唯一）")
    names.add(name)
    label = str(item.get("label", name))

    if kind == "folder":
        folder_type = str(item.get("folder_type", "simple")).strip().lower()
        folder_types = {
            "simple": hou.folderType.Simple,
            "tabs": hou.folderType.Tabs,
            "collapsible": hou.folderType.Collapsible,
        }
        if folder_type not in folder_types:
            raise ValueError(f"{path}.folder_type 只能是 {sorted(folder_types)}")
        children = item.get("parms", [])
        if not isinstance(children, (list, tuple)):
            raise ValueError(f"{path}.parms 必须是 list")
        template = hou.FolderParmTemplate(
            name, label, folder_type=folder_types[folder_type]
        )
        for index, child in enumerate(children):
            template.addParmTemplate(
                _build_interface_template(
                    child, f"{path}.parms[{index}]", names, conditions
                )
            )
    elif kind == "separator":
        template = hou.SeparatorParmTemplate(name, label)
    elif kind == "toggle":
        template = hou.ToggleParmTemplate(
            name, label, default_value=bool(item.get("default", False))
        )
    elif kind in ("int", "float"):
        default = item.get("default", 0)
        minimum = item.get("min", 0)
        maximum = item.get("max", 10)
        if kind == "float" and "menu" in item:
            raise ValueError(
                f"{path}: Houdini FloatParmTemplate 不支持菜单；"
                "需要菜单请用 int+menu（值为索引）或 string"
            )
        kwargs = {
            "default_value": (float(default),) if kind == "float" else (int(default),),
            "min": float(minimum) if kind == "float" else int(minimum),
            "max": float(maximum) if kind == "float" else int(maximum),
            "min_is_strict": bool(item.get("min_strict", False)),
            "max_is_strict": bool(item.get("max_strict", False)),
        }
        if kind == "int" and "menu" in item:
            items, labels = _menu_data(item, path)
            index = int(default)
            if not 0 <= index < len(items):
                raise ValueError(
                    f"{path}.default={index} 超出菜单索引 0..{len(items) - 1}；"
                    "Houdini 的 Int 菜单存索引，不存 item token"
                )
            kwargs.update(menu_items=items, menu_labels=labels)
        cls = hou.FloatParmTemplate if kind == "float" else hou.IntParmTemplate
        template = cls(name, label, 1, **kwargs)
    elif kind == "string":
        default = str(item.get("default", ""))
        file_kind = item.get("file")
        kwargs = {"default_value": (default,)}
        if file_kind is not None:
            file_key = str(file_kind).strip().lower()
            file_types = {
                "dir": hou.fileType.Directory,
                "geo": hou.fileType.Geometry,
                "alembic": hou.fileType.Geometry,
                "image": hou.fileType.Image,
                "any": hou.fileType.Any,
            }
            if file_key not in file_types:
                raise ValueError(f"{path}.file 只能是 {sorted(file_types)}")
            kwargs.update(
                string_type=hou.stringParmType.FileReference,
                file_type=file_types[file_key],
            )
        template = hou.StringParmTemplate(name, label, 1, **kwargs)
    elif kind == "button":
        callback = item.get("callback")
        if not isinstance(callback, str) or not callback.strip():
            raise ValueError(f"{path}.callback 必须是非空 Python 回调字符串")
        template = hou.ButtonParmTemplate(name, label)
        template.setScriptCallback(callback)
        template.setScriptCallbackLanguage(hou.scriptLanguage.Python)
    else:  # menu
        items, labels = _menu_data(item, path)
        default = int(item.get("default", 0))
        if not 0 <= default < len(items):
            raise ValueError(f"{path}.default 必须是菜单索引 0..{len(items) - 1}")
        template = hou.MenuParmTemplate(
            name, label, items, menu_labels=labels, default_value=default
        )

    _apply_template_common(template, item, path, conditions)
    return template


def _template_has_managed(template) -> bool:
    try:
        if template.tags().get(_HDA_MANAGED_TAG) == "1":
            return True
    except Exception:
        pass
    if isinstance(template, hou.FolderParmTemplate):
        return any(_template_has_managed(c) for c in template.parmTemplates())
    return False


def _standard_interface_entries(node: hou.Node) -> list:
    """取 HDA 源 subnet 的标准界面；找不到基型时保留未受本动词管理的旧条目。"""
    source_name = _enum_name(node.type().source()).lower()
    if source_name == "subnet":
        base_type = node.type().category().nodeTypes().get("subnet")
        if base_type is not None and base_type is not node.type():
            return [entry.clone() for entry in base_type.parmTemplateGroup().entries()]
    return [
        entry.clone() for entry in node.parmTemplateGroup().entries()
        if not _template_has_managed(entry)
    ]


def _all_template_names(templates) -> set:
    names = set()
    for template in templates:
        names.add(template.name())
        if isinstance(template, hou.FolderParmTemplate):
            names.update(_all_template_names(template.parmTemplates()))
    return names


def _balanced_block_end(text: str, start: int) -> int:
    brace = text.find("{", start)
    if brace < 0:
        raise ValueError("DialogScript parm 块缺少 '{'")
    depth = 0
    quote = None
    escaped = False
    for index in range(brace, len(text)):
        ch = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError("DialogScript parm 块大括号不平衡")


def _patch_dialog_hide_when(dialog: str, name: str, condition: str) -> str:
    block_re = re.compile(r"(?m)^[ \t]*parm[ \t]*\{[ \t]*$")
    name_re = re.compile(r"(?m)^[ \t]*name[ \t]+\"" + re.escape(name) + r"\"[ \t]*$")
    for match in block_re.finditer(dialog):
        end = _balanced_block_end(dialog, match.start())
        block = dialog[match.start():end]
        name_match = name_re.search(block)
        if name_match is None:
            continue
        escaped = condition.replace("\\", "\\\\").replace('"', '\\"')
        hide_re = re.compile(r"(?m)^(?P<indent>[ \t]*)hidewhen[ \t]+\".*\"[ \t]*$")
        existing = hide_re.search(block)
        if existing is not None:
            replacement = existing.group("indent") + f'hidewhen "{escaped}"'
            block = block[:existing.start()] + replacement + block[existing.end():]
        else:
            indent = re.match(r"[ \t]*", block[name_match.start():]).group(0)
            close_line = block.rfind("\n", 0, len(block) - 1) + 1
            newline = "\r\n" if "\r\n" in block else "\n"
            insertion = indent + f'hidewhen "{escaped}"' + newline
            block = block[:close_line] + insertion + block[close_line:]
        return dialog[:match.start()] + block + dialog[end:]
    raise ValueError(f"DialogScript 中找不到参数 {name!r} 的 parm 块")


def hda_set_interface(
    node,
    spec: list,
    keep_std: bool = True,
    hide_builtin_tabs: bool = False,
    allow_foreign: str | None = None,
) -> dict:
    """按 JSON 安全 spec 声明式重建 HDA 参数面板并验证 conditional。

    自定义部分是**整组重建**，不是 merge。``keep_std`` 对 subnet HDA 从原生
    subnet 类型重新取得 Transform/Subnet 等标准页，避免把旧自定义参数夹带回来；
    ``hide_builtin_tabs`` 通过公开的 ParmTemplateGroup.hide 隐藏这些页。所有
    ``hide_when`` 在提交后读回验证，Houdini 若吞掉 conditional，则自动补丁
    DialogScript 的 ``hidewhen`` 并再次验证。
    """
    n, definition = _hda_definition(node)
    _require_owned(n, "hda_set_interface", allow_foreign)
    if not isinstance(spec, (list, tuple)):
        raise ValueError("spec 必须是参数条目 list")
    names: set = set()
    conditions: dict[str, str] = {}
    custom = [
        _build_interface_template(item, f"spec[{index}]", names, conditions)
        for index, item in enumerate(spec)
    ]

    standard = _standard_interface_entries(n) if keep_std else []
    conflicts = names & _all_template_names(standard)
    if conflicts:
        raise ValueError(
            f"自定义 spec 与 Houdini 标准参数重名：{sorted(conflicts)}；"
            "请改自定义 name（不要覆盖 tx/rx 等内置参数）"
        )

    group = hou.ParmTemplateGroup()
    # 自定义界面优先：顶层按钮会自然出现在最上方，标准页排在其后。
    for template in custom:
        group.append(template)
    standard_names = []
    for template in standard:
        group.append(template)
        standard_names.append(template.name())
    if hide_builtin_tabs:
        for name in standard_names:
            try:
                group.hide(name, True)
            except Exception as e:
                raise ValueError(f"隐藏标准页 {name!r} 失败：{e}") from e

    definition.setParmTemplateGroup(group, rename_conflicting_parms=False)

    # H21 实测 setParmTemplateGroup 会吞一部分 API setConditional：先读回，
    # 只对丢失项走 DialogScript 兜底，避免无谓改写定义源码。
    after = n.parmTemplateGroup()
    missing = {}
    for name, expected in conditions.items():
        template = after.find(name)
        actual = None
        if template is not None:
            actual = template.conditionals().get(hou.parmCondType.HideWhen)
        if actual != expected:
            missing[name] = expected
    patched = []
    if missing:
        sections = definition.sections()
        if "DialogScript" not in sections:
            raise RuntimeError(
                f"conditional 被 Houdini 吞掉，但定义没有 DialogScript section：{sorted(missing)}"
            )
        dialog = sections["DialogScript"].contents()
        for name, condition in missing.items():
            dialog = _patch_dialog_hide_when(dialog, name, condition)
            patched.append(name)
        definition.addSection("DialogScript", dialog)

    verified = {}
    final_group = n.parmTemplateGroup()
    for name, expected in conditions.items():
        template = final_group.find(name)
        actual = None if template is None else template.conditionals().get(
            hou.parmCondType.HideWhen
        )
        if actual != expected:
            raise RuntimeError(
                f"参数 {name!r} hide_when 写后验证失败：expected={expected!r}, actual={actual!r}"
            )
        verified[name] = actual

    hidden_std = []
    if hide_builtin_tabs:
        final_group = n.parmTemplateGroup()
        for template in final_group.entries():
            try:
                if template.isHidden() and template.label() in {
                    t.label() for t in standard
                }:
                    hidden_std.append(template.label())
            except Exception:
                pass
    return {
        "node": n.path(),
        "custom_entries": [t.name() for t in custom],
        "custom_parms": sorted(names),
        "standard_kept": bool(keep_std),
        "standard_entries": standard_names,
        "hidden_standard_tabs": sorted(hidden_std),
        "hide_when_verified": verified,
        "dialogscript_patched": patched,
    }


# --- geometry 域 -------------------------------------------------------------

def geo_attrib_stats(node, name: str, attrib_class: str = "point") -> dict:
    """属性**值**统计：min/max/mean/count（`describe` 只给属性名清单，不给值）。

    用于验证驱动数据（@Cd/@curveu/@pscale…）是否符合预期，不用手写逐点循环。
    attrib_class: "point" / "prim" / "vertex" / "detail"。数值属性支持多分量
    （vector 按分量给 min/max/mean）；字符串属性报明确错误。
    """
    n = _resolve(node)
    g = n.geometry()
    finders = {
        "point": (g.findPointAttrib, g.pointFloatAttribValues, g.pointIntAttribValues),
        "prim": (g.findPrimAttrib, g.primFloatAttribValues, g.primIntAttribValues),
        "vertex": (g.findVertexAttrib, g.vertexFloatAttribValues, g.vertexIntAttribValues),
        # detail 属性只有一个值，没有批量取值 API，用 attribValue 特判
        "detail": (g.findGlobalAttrib, None, None),
    }
    if attrib_class not in finders:
        raise ValueError(f"attrib_class 只能是 {sorted(finders)}，收到 {attrib_class!r}")
    find, floats, ints = finders[attrib_class]
    attrib = find(name)
    if attrib is None:
        pool = {
            "point": [a.name() for a in g.pointAttribs()],
            "prim": [a.name() for a in g.primAttribs()],
            "vertex": [a.name() for a in g.vertexAttribs()],
            "detail": [a.name() for a in g.globalAttribs()],
        }[attrib_class]
        suggestions = difflib.get_close_matches(name, pool, n=5, cutoff=0.4)
        raise ValueError(
            f"节点 '{n.path()}' 没有 {attrib_class} 属性 '{name}'。相似属性：{suggestions}"
        )
    data_type = attrib.dataType()
    size = attrib.size()
    if data_type == hou.attribData.String:
        raise ValueError(f"属性 '{name}' 是字符串属性，geo_attrib_stats 只统计数值属性")
    if attrib_class == "detail":
        v = g.attribValue(name)
        values = list(v) if isinstance(v, (tuple, list)) else [v]
    else:
        values = list(floats(name) if data_type == hou.attribData.Float else ints(name))
    count = len(values) // size if size else 0
    mins, maxs, means = [], [], []
    for comp in range(size):
        col = values[comp::size]
        if not col:
            mins.append(None); maxs.append(None); means.append(None)
            continue
        mins.append(min(col)); maxs.append(max(col))
        means.append(sum(col) / len(col))
    def _collapse(v):
        return v[0] if size == 1 else v
    return {
        "node": n.path(),
        "attrib": name,
        "class": attrib_class,
        "data_type": "float" if data_type == hou.attribData.Float else "int",
        "size": size,
        "count": count,
        "min": _collapse(mins),
        "max": _collapse(maxs),
        "mean": _collapse(means),
    }


def _summary(values: list) -> dict:
    if not values:
        return {"min": None, "max": None, "mean": None}
    return {
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
    }


def geo_piece_stats(node, piece_attrib: str | None = None,
                    sample: int = 16) -> dict:
    """按 primitive piece 报局部 bbox/面积，识别整体 bbox 掩盖的局部退化。

    ``piece_attrib=None`` 时用原生 Connectivity SOP Verb 在内存副本上生成临时
    primitive ``__dsh_piece``，不向用户网络加节点。也可传已有 primitive int/string
    piece 属性。返回全部 piece 的摘要和有限样本，避免 9000 个实例爆 token。
    """
    n = _resolve(node)
    if n.type().category() != hou.sopNodeTypeCategory():
        raise ValueError("geo_piece_stats 只接受 SOP 节点")
    if not isinstance(sample, int) or sample <= 0 or sample > 256:
        raise ValueError("sample 必须是 1..256 的整数")
    source = n.geometry()
    if source is None:
        raise ValueError(f"节点 {n.path()} 没有 geometry")
    geometry = source
    generated = False
    attrib_name = piece_attrib
    attrib_class = "prim"
    if attrib_name is None:
        generated = True
        attrib_name = "__dsh_piece"
        verb = hou.sopNodeTypeCategory().nodeVerb("connectivity")
        if verb is None:
            raise RuntimeError("当前 Houdini 没有 Connectivity SOP Verb")
        verb.setParms({"attribname": attrib_name, "attribtype": 0, "connecttype": 0})
        geometry = hou.Geometry()
        verb.execute(geometry, [source])
        attrib_class = "point"
    else:
        attrib = geometry.findPrimAttrib(attrib_name)
        if attrib is None:
            attrib = geometry.findPointAttrib(attrib_name)
            attrib_class = "point"
        if attrib is None:
            raise ValueError(
                f"节点 {n.path()} 没有 primitive/point piece 属性 {attrib_name!r}；"
                "省略 piece_attrib 可按连接性自动生成"
            )
        if attrib.size() != 1:
            raise ValueError("piece_attrib 必须是单分量 primitive 属性")

    pieces = {}
    for prim in geometry.iterPrims():
        try:
            if attrib_class == "prim":
                piece_id = prim.attribValue(attrib_name)
            else:
                points = prim.points()
                if not points:
                    continue
                piece_id = points[0].attribValue(attrib_name)
        except Exception as error:
            raise ValueError(f"无法读取 {attrib_class} 属性 {attrib_name!r}: {error}") from error
        key = str(piece_id)
        record = pieces.get(key)
        if record is None:
            record = {
                "id": piece_id,
                "prims": 0,
                "vertices": 0,
                "surface_prims": 0,
                "area": 0.0,
                "min": [math.inf, math.inf, math.inf],
                "max": [-math.inf, -math.inf, -math.inf],
            }
            pieces[key] = record
        record["prims"] += 1
        points = prim.points()
        record["vertices"] += len(points)
        try:
            closed = bool(prim.intrinsicValue("closed"))
        except Exception:
            closed = False
        if closed and len(points) >= 3:
            try:
                area = float(prim.intrinsicValue("measuredarea"))
                record["area"] += max(0.0, area)
                record["surface_prims"] += 1
            except Exception:
                pass
        for point in points:
            position = point.position()
            for axis in range(3):
                value = float(position[axis])
                record["min"][axis] = min(record["min"][axis], value)
                record["max"][axis] = max(record["max"][axis], value)

    records = []
    for record in pieces.values():
        extents = [record["max"][i] - record["min"][i] for i in range(3)]
        records.append({
            "id": _val(record["id"]),
            "prims": record["prims"],
            "vertices": record["vertices"],
            "surface_prims": record["surface_prims"],
            "area": record["area"],
            "bbox_min": record["min"],
            "bbox_max": record["max"],
            "extents": extents,
            "min_extent": min(extents),
            "max_extent": max(extents),
        })
    records.sort(key=lambda item: (
        0, float(item["id"])
    ) if isinstance(item["id"], (int, float)) else (1, str(item["id"])))
    source_bbox = source.boundingBox()
    source_scale = max(float(v) for v in source_bbox.sizevec()) if records else 1.0
    area_epsilon = max(source_scale * source_scale * 1e-12, 1e-16)
    degenerate = sum(
        1 for item in records
        if item["surface_prims"] > 0 and item["area"] <= area_epsilon
    )
    if len(records) <= sample:
        sampled = records
    elif sample == 1:
        sampled = [records[0]]
    else:
        indices = sorted({
            round(i * (len(records) - 1) / (sample - 1)) for i in range(sample)
        })
        sampled = [records[i] for i in indices]
    axis_extents = [[item["extents"][axis] for item in records] for axis in range(3)]
    return {
        "node": n.path(),
        "piece_attrib": attrib_name,
        "piece_attrib_class": attrib_class,
        "piece_attrib_generated": generated,
        "piece_count": len(records),
        "degenerate_surface_pieces": degenerate,
        "area_epsilon": area_epsilon,
        "area": _summary([item["area"] for item in records]),
        "extent_x": _summary(axis_extents[0]),
        "extent_y": _summary(axis_extents[1]),
        "extent_z": _summary(axis_extents[2]),
        "sampled_pieces": sampled,
    }


def geo_frame_diff(node, frame_a, frame_b, attrib: str = "P",
                   sample: int = 4096, tolerance: float = 1e-6) -> dict:
    """比较 SOP 两帧的 point 数值属性，不移动用户 playbar。

    使用 ``geometryAtFrame`` 取得冻结几何；拓扑一致时返回抽样点的 mean/max delta、
    p50/p90/p99、逐分量位移统计与 unchanged 百分比。适合区分“真实几何静止”和
    “ROP/图片缓存”；这些数值证明数据在动，不自动证明运动的审美语义。

    可比较结果的精确键是 ``mean_delta``、``max_delta``、
    ``delta_percentiles``（``p50/p90/p99``）、``component_delta``
    （``min/max/mean`` 数组）、``unchanged_pct``、``sampled_points``、
    ``tolerance``、``data_type`` 和 ``size``；不要读取不存在的简写
    ``mean``/``max``。所有结果另含 node/attrib/frame/counts/bbox。
    """
    n = _resolve(node)
    if n.type().category() != hou.sopNodeTypeCategory():
        raise ValueError("geo_frame_diff 只接受 SOP 节点")
    if not isinstance(sample, int) or sample <= 0 or sample > 1_000_000:
        raise ValueError("sample 必须是 1..1000000 的整数")
    if tolerance < 0:
        raise ValueError("tolerance 不能为负")
    fa, fb = float(frame_a), float(frame_b)
    ga = n.geometryAtFrame(fa)
    gb = n.geometryAtFrame(fb)
    if ga is None or gb is None:
        raise ValueError(f"节点 {n.path()} 在指定帧没有 geometry")
    counts_a = {"points": len(ga.points()), "prims": len(ga.prims())}
    counts_b = {"points": len(gb.points()), "prims": len(gb.prims())}
    bbox_a, bbox_b = ga.boundingBox(), gb.boundingBox()
    base = {
        "node": n.path(),
        "attrib": attrib,
        "frame_a": fa,
        "frame_b": fb,
        "counts_a": counts_a,
        "counts_b": counts_b,
        "bbox_a": {
            "min": [float(v) for v in bbox_a.minvec()],
            "max": [float(v) for v in bbox_a.maxvec()],
        },
        "bbox_b": {
            "min": [float(v) for v in bbox_b.minvec()],
            "max": [float(v) for v in bbox_b.maxvec()],
        },
    }
    if counts_a != counts_b:
        base.update({"comparable": False, "reason": "topology counts differ"})
        return base
    aa, ab = ga.findPointAttrib(attrib), gb.findPointAttrib(attrib)
    if aa is None or ab is None:
        raise ValueError(f"两帧都必须有 point 属性 {attrib!r}")
    if aa.size() != ab.size() or aa.dataType() != ab.dataType():
        base.update({"comparable": False, "reason": "attribute type/size differs"})
        return base
    if aa.dataType() == hou.attribData.String:
        raise ValueError("geo_frame_diff 只支持数值 point 属性")
    getter = "pointFloatAttribValues" if aa.dataType() == hou.attribData.Float else "pointIntAttribValues"
    values_a = list(getattr(ga, getter)(attrib))
    values_b = list(getattr(gb, getter)(attrib))
    size = aa.size()
    point_count = counts_a["points"]
    if point_count <= sample:
        indices = range(point_count)
    elif sample == 1:
        indices = [0]
    else:
        indices = sorted({
            round(i * (point_count - 1) / (sample - 1)) for i in range(sample)
        })
    deltas = []
    component_deltas = [[] for _ in range(size)]
    for index in indices:
        offset = index * size
        components = [
            float(values_b[offset + c]) - float(values_a[offset + c])
            for c in range(size)
        ]
        deltas.append(math.sqrt(sum(value * value for value in components)))
        for component, value in enumerate(components):
            component_deltas[component].append(value)
    unchanged = sum(1 for value in deltas if value <= tolerance)
    ordered = sorted(deltas)

    def percentile(fraction: float) -> float:
        if not ordered:
            return 0.0
        if len(ordered) == 1:
            return ordered[0]
        position = fraction * (len(ordered) - 1)
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return ordered[lower]
        weight = position - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    base.update({
        "comparable": True,
        "data_type": "float" if aa.dataType() == hou.attribData.Float else "int",
        "size": size,
        "sampled_points": len(deltas),
        "tolerance": float(tolerance),
        "mean_delta": sum(deltas) / len(deltas) if deltas else 0.0,
        "max_delta": max(deltas) if deltas else 0.0,
        "delta_percentiles": {
            "p50": percentile(0.50),
            "p90": percentile(0.90),
            "p99": percentile(0.99),
        },
        "component_delta": {
            "min": [min(values) if values else 0.0 for values in component_deltas],
            "max": [max(values) if values else 0.0 for values in component_deltas],
            "mean": [
                sum(values) / len(values) if values else 0.0
                for values in component_deltas
            ],
        },
        "unchanged_pct": unchanged * 100.0 / len(deltas) if deltas else 100.0,
    })
    return base


# --- render / sim 域 ---------------------------------------------------------

# --- 图片产出登记（media relay 数据源） --------------------------------------
# 动词产出的图片路径登记在这里；bridge 在每次 exec 结束后把它放进 envelope
# 的 `images` 字段，host 侧经 /media 端点把字节拉回会话工作区——vision/fs
# 工具被沙箱限制在工作区内，直接读不到 $HIP 下的产物（2026-08-19 草地任务
# trace：vision_glance 被 "image escapes the allowed directories" 拦截）。
_PRODUCED_IMAGES: list = []
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".webp"}


def report_image(path: str) -> str:
    """登记一张本次 exec 产出的图片（返回绝对路径）。动词外手写的产出也可登记。

    只登记图片扩展名——geometry ROP 的 .bgeo 等产物不该进 media relay。
    """
    p = os.path.abspath(path)
    if os.path.splitext(p)[1].lower() in _IMAGE_EXTS and p not in _PRODUCED_IMAGES:
        _PRODUCED_IMAGES.append(p)
    return p


def render_frame(rop, picture=None, frame=None, timeout: float = 110) -> dict:
    """渲染单帧并**验证产物**（等文件落盘 + 非空 + 采集 ROP 错误）。

    固化「设 picture → setFrame → rop.render() → 等产物 → 报大小」的样板：
    ``render()`` 不抛异常**不等于**产物存在（ROP 参数错、输出目录不可写、
    渲染器挂起都是静默失败），所以本动词等到文件落盘且非空才返回
    ``file_bytes``，否则在 ``errors`` 里说明。

    - rop：ROP 节点（hou.Node 或 path）。输出参数按常见名自动解析；图像参数
      ``outputimage`` 优先于 USD ``lopoutput``，Karma/Mantra/geometry 等 ROP 都覆盖。
      有 ``soho_foreground`` 时调用期临时等待渲染完成并在 finally 恢复。
    - picture：输出路径（含 $F 变量可直接传）；None = 用 ROP 当前设置。
    - frame：帧号；None = 当前帧。
    - timeout：等产物的上限（秒）。超过 ~110s 的渲染请走 houdini_job_submit
      （host 侧桥请求超时 120s），本动词面向单帧测试渲染。
    """
    n = _resolve(rop)
    if not isinstance(n, hou.RopNode) or not hasattr(n, "render"):
        if n.type().category() == hou.lopNodeTypeCategory():
            raise ValueError(
                f"{n.path()} 是普通 LOP（{n.type().name()}），不是可执行 ROP；"
                "请用 search_tab_entries('/stage', 'Karma (Setup)') + "
                "tab_apply('/stage', 'lop_karma_setup') 创建 USD Render ROP，"
                "再把该 usdrender_rop 传给 render_frame"
            )
        raise ValueError(f"{n.path()} 不是可执行 ROP，缺少 render()")
    p = None
    # USD Render ROP owns both `lopoutput` (temporary/exported USD) and
    # `outputimage` (rendered image override). Image output must win or a PNG
    # path is accidentally assigned as the USD file and no image is produced.
    for pname in ("picture", "vm_picture", "outputimage", "sopoutput",
                  "lopoutput", "dopoutput", "copoutput", "choutput"):
        p = n.parm(pname)
        if p is not None:
            break
    if p is None:
        raise ValueError(
            f"节点 '{n.path()}' 找不到输出路径参数（试过 picture/vm_picture/"
            "outputimage/sopoutput/lopoutput/dopoutput/copoutput/choutput）——"
            "它不是 ROP？（非常规输出参数请裸写 hou，词表不覆盖）"
        )
    original_output = p.unexpandedString()
    if picture is not None:
        p.set(picture)
    f = hou.frame() if frame is None else float(frame)
    original_frame = float(hou.frame())
    foreground_parm = n.parm("soho_foreground")
    original_foreground = foreground_parm.eval() if foreground_parm is not None else None
    target = None
    t0 = time.time()
    render_err = None
    file_bytes = None
    pre_fingerprint = None
    post_fingerprint = None

    def fingerprint(path):
        if not path or not os.path.isfile(path):
            return None
        stat = os.stat(path)
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            digest.update(handle.read(64 * 1024))
            if stat.st_size > 64 * 1024:
                handle.seek(max(0, stat.st_size - 64 * 1024))
                digest.update(handle.read(64 * 1024))
        return {
            "bytes": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
            "sample_sha256": digest.hexdigest(),
        }

    try:
        hou.setFrame(f)
        if foreground_parm is not None:
            foreground_parm.set(1)
        target = hou.text.expandString(p.unexpandedString())
        pre_fingerprint = fingerprint(target)
        out_dir = os.path.dirname(target)
        if out_dir and not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        try:
            n.render(frame_range=(f, f))
        except Exception as e:  # hou.Error 等
            render_err = str(e)

        deadline = t0 + float(timeout)
        while not render_err and time.time() < deadline:
            post_fingerprint = fingerprint(target)
            if post_fingerprint is not None and post_fingerprint != pre_fingerprint:
                file_bytes = post_fingerprint["bytes"]
                break
            time.sleep(1)
    finally:
        if picture is not None:
            try:
                p.set(original_output)
            except Exception:
                pass
        if foreground_parm is not None and original_foreground is not None:
            try:
                foreground_parm.set(original_foreground)
            except Exception:
                pass
        # 渲染帧属于 agent 验证状态，不占用用户 playbar；即使 ROP 失败也还原。
        if float(hou.frame()) != original_frame:
            try:
                hou.setFrame(original_frame)
            except Exception:
                pass

    errors: list[str] = []
    if render_err:
        errors.append(render_err)
    try:
        for e in n.errors():
            if e and e not in errors:
                errors.append(e)
    except Exception:
        pass
    if not render_err and file_bytes is None:
        errors.append(f"render() 未报错但产物缺失、为空或与渲染前指纹相同：{target}")
    if file_bytes:
        report_image(target)
    return {
        "path": n.path(),
        "output": target,
        "frame": f,
        "file_bytes": file_bytes,
        "preexisting": pre_fingerprint is not None,
        "fresh": file_bytes is not None,
        "pre_fingerprint": pre_fingerprint,
        "post_fingerprint": post_fingerprint,
        "errors": errors,
        "ms": int((time.time() - t0) * 1000),
    }


def _read_pixels_qt(path: str):
    """QImage 读像素（Houdini GUI/hython 均带 PySide6）；失败返回 None。"""
    try:
        from PySide6.QtGui import QImage
        img = QImage(path)
        if img.isNull():
            return None
        img = img.convertToFormat(QImage.Format.Format_RGB888)
        w, h = img.width(), img.height()
        pixels = []
        for y in range(h):
            row = []
            for x in range(w):
                c = img.pixelColor(x, y)
                row.append((c.red(), c.green(), c.blue()))
            pixels.append(row)
        return w, h, pixels
    except Exception:
        return None


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def _read_pixels_png(path: str):
    """纯标准库 PNG 解码（8-bit grey/RGB/RGBA，无交错）——hython 无 GUI 时的
    fallback。返回 (w, h, pixels)；不支持的格式返回 None。"""
    try:
        data = open(path, "rb").read()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        pos = 8
        idat = b""
        w = h = bitd = colort = None
        while pos < len(data):
            ln = struct.unpack(">I", data[pos:pos+4])[0]
            typ = data[pos+4:pos+8]
            chunk = data[pos+8:pos+8+ln]
            if typ == b"IHDR":
                w, h, bitd, colort = struct.unpack(">IIBB", chunk[:10])
            elif typ == b"IDAT":
                idat += chunk
            elif typ == b"IEND":
                break
            pos += 12 + ln
        if bitd != 8 or colort not in (0, 2, 6):
            return None
        channels = {0: 1, 2: 3, 6: 4}[colort]
        raw = zlib.decompress(idat)
        stride = w * channels
        pixels = []
        prev = bytearray(stride)
        off = 0
        for _y in range(h):
            filt = raw[off]
            line = bytearray(raw[off+1:off+1+stride])
            off += 1 + stride
            for i in range(stride):
                a = line[i-channels] if i >= channels else 0
                b = prev[i]
                c = prev[i-channels] if i >= channels else 0
                if filt == 1:
                    line[i] = (line[i] + a) & 0xFF
                elif filt == 2:
                    line[i] = (line[i] + b) & 0xFF
                elif filt == 3:
                    line[i] = (line[i] + (a + b) // 2) & 0xFF
                elif filt == 4:
                    line[i] = (line[i] + _paeth(a, b, c)) & 0xFF
            row = []
            for x in range(w):
                base = x * channels
                if channels == 1:
                    row.append((line[base],) * 3)
                else:
                    row.append((line[base], line[base+1], line[base+2]))
            pixels.append(row)
            prev = line
        return w, h, pixels
    except Exception:
        return None


def _read_pixels(path: str):
    return _read_pixels_qt(path) or _read_pixels_png(path)


def _image_stats(w: int, h: int, pixels, max_samples: int = 512) -> dict:
    """从像素矩阵算客观指标（大图先按网格抽样，上限 max_samples 边长）。"""
    step = max(1, int(max(w, h) / max_samples) + 1)
    lumas = []
    rs = gs = bs = nb = 0
    bbox = None
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = pixels[y][x]
            luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
            lumas.append(luma)
            if luma > 8:  # 非黑
                nb += 1
                rs += r; gs += g; bs += b
                if bbox is None:
                    bbox = [x, y, x, y]
                else:
                    bbox[0] = min(bbox[0], x); bbox[1] = min(bbox[1], y)
                    bbox[2] = max(bbox[2], x); bbox[3] = max(bbox[3], y)
    total = len(lumas) or 1
    return {
        "mean_luma": round(sum(lumas) / total, 2),
        "max_luma": round(max(lumas), 2) if lumas else 0,
        "nonblack_pct": round(nb * 100.0 / total, 2),
        "dominant": [rs // nb, gs // nb, bs // nb] if nb else None,
        "content_bbox": bbox,
    }


def render_check(path: str, ref=None) -> dict:
    """渲染产物的**客观验证**——无视觉模型时的盲验手段。

    返回亮度统计 / 非黑像素占比 / 主色 / 内容 bbox，回答「渲染是不是黑的、
    有没有内容、内容在哪」；传 ``ref``（另一张图路径）再算两图差异
    （``identical`` / ``mean_abs_diff``），用于循环帧一致性、A/B 对比。

    解码优先 PySide6 QImage（PNG/JPEG/BMP/TGA），hython 无 GUI 时退回纯
    Python PNG 解码（8-bit）；EXR 等 HDR 格式不在覆盖范围（裸 hou 逃生舱）。
    """
    result = _read_pixels(path)
    if result is None:
        raise ValueError(
            f"无法解码 '{path}'（支持 PNG/JPEG/BMP/TGA，EXR 等请裸写 hou.image）"
        )
    w, h, pixels = result
    out: dict[str, Any] = {
        "path": path,
        "width": w,
        "height": h,
        "bytes": os.path.getsize(path),
    }
    out.update(_image_stats(w, h, pixels))

    if ref is not None:
        result2 = _read_pixels(ref)
        if result2 is None:
            raise ValueError(f"无法解码 ref 图 '{ref}'")
        w2, h2, pixels2 = result2
        if (w2, h2) != (w, h):
            out["diff_vs_ref"] = {"comparable": False, "ref_size": [w2, h2]}
        else:
            step = max(1, int(max(w, h) / 512) + 1)
            diffs = []
            squared = 0.0
            channel_abs = 0.0
            changed = meaningful = 0
            for y in range(0, h, step):
                for x in range(0, w, step):
                    p1, p2 = pixels[y][x], pixels2[y][x]
                    channels = [abs(p1[i] - p2[i]) for i in range(3)]
                    pixel_diff = max(channels)
                    diffs.append(pixel_diff)
                    channel_abs += sum(channels)
                    squared += sum(value * value for value in channels)
                    if pixel_diff > 0:
                        changed += 1
                    if pixel_diff > 2:
                        meaningful += 1
            count = len(diffs)
            out["diff_vs_ref"] = {
                "comparable": True,
                "identical": max(diffs) == 0 if diffs else True,
                # 不过早舍入：40054277 草地 frame 1/12 的微小非零差异曾被
                # round(..., 3) 压成 0，掩盖“几乎静止”的关键证据。
                "mean_abs_diff": round(channel_abs / (count * 3), 8) if count else 0,
                "mean_max_channel_diff": round(sum(diffs) / count, 8) if count else 0,
                "rmse": round(math.sqrt(squared / (count * 3)), 8) if count else 0,
                "max_abs_diff": max(diffs) if diffs else 0,
                "changed_pixel_pct": round(changed * 100.0 / count, 6) if count else 0,
                "meaningful_pixel_pct": round(meaningful * 100.0 / count, 6) if count else 0,
                "sample_step": step,
                "sampled_pixels": count,
            }
    return out


# --- viewport 域 -------------------------------------------------------------

# clean 模式要隐藏的视口装饰（hou.viewportGuide 枚举名）：参考平面网格、
# 坐标指示器、手柄、物体标签、相机遮幅/安全框、性能 HUD、视图中心点。
# 网格线横穿模型会给图像识别（VLM 或 render_check 的 bbox）注入大量杂边，
# 隐藏后主体更突出；纹理（displayTextures）保留并强制开启——材质是识别线索。
_CLEAN_GUIDES = (
    "XYPlane", "YZPlane", "XZPlane",
    "OriginGnomon", "FloatingGnomon",
    "NodeHandles", "NodeGuides",
    "ObjectNames", "ObjectPaths",
    "CameraMask", "SafeArea",
    "ShowDrawTime", "ViewPivot",
)


def _display_bbox(n):
    """节点的显示几何 bbox：obj 级取其 displayNode，SOP 直接取。"""
    try:
        d = n.displayNode()
        if d is not None:
            return d.geometry().boundingBox()
    except Exception:
        pass
    return n.geometry().boundingBox()


def _restore_webview_window() -> None:
    """截图后还原被最小化的内嵌 web UI 窗口（dsh_webview）。

    用户报告（2026-08-18）：agent 截图时 agent 窗口会最小化，要手动从
    任务栏点回。只在确实处于最小化状态时还原——用户只是切去 Houdini
    干活（失焦/被遮）时不抢焦点。可选依赖：webview 未开过/导入失败就静默。
    """
    try:
        import dsh_webview
    except Exception:
        return
    win = getattr(dsh_webview, "_window", None)
    if win is None:
        return
    try:
        if win.isMinimized():
            win.showNormal()
            dsh_webview._bring_to_front(win)
    except Exception:
        pass


def viewport_screenshot(path=None, frame=None, clean=True, frame_target=None,
                        textures=None, backface_cull=False) -> dict:
    """抓取当前场景视口截图（所见即所得）——**GUI 模式限定**。

    视觉验证的另一半：``render_frame``/``render_check`` 管渲染产物，本动词
    回答「用户现在在视口里看到什么」。无 UI（hython/批渲染）时抛明确错误，
    请改用 ``render_frame``。

    - path：保存路径；None = ``$HIP/screenshots/viewport_f<帧>_<时间>.png``
      （hip 未保存时落在当前目录的 ``screenshots/`` 下）。
    - frame：抓哪一帧；None = 当前帧。
    - clean：True（默认）时临时隐藏视口装饰（参考平面网格/坐标指示器/手柄/
      标签/相机遮幅/性能 HUD 等，见 ``_CLEAN_GUIDES``），截完恢复原设置。
    - frame_target：节点（hou.Node 或 path），或 ``True`` = 「/obj 下当前挂
      display 旗标的对象」。给了就把视口取景到该节点的显示几何 bbox
      （`frameBoundingBox`），主体占满画面；视图变换尽力恢复
      （ViewportCamera 支持 setTransform 时），恢复不了则停留在取景位置。
    - textures：None（默认）不动纹理显示；True/False 临时强制开/关纹理
      （模型上的 UV 贴图/棋盘格不想入镜就传 False），截完恢复。
    - backface_cull：True 时临时开启背面剔除（`removeBackfaces`）——HOM 只
      暴露剔除开关，背面 tint 颜色没有 API；默认 False 不动。

    实现走 SceneViewer 的 flipbook 通道（单帧、不进 MPlay），因此视口显示
    什么就抓什么——包括 display 旗标位置错误造成的「只显示一个圆环」这类
    事故，截图前先用 ``display_node`` 核对旗标。

    注意：flipbook 是**异步**渲染——所有视口设置的恢复都必须等到产物文件
    落盘确认之后，否则截图时设置已被还原（2026-08-17 实测踩坑）。
    """
    if not hou.isUIAvailable():
        raise ValueError(
            "viewport_screenshot 需要 Houdini GUI（当前无 UI）；"
            "headless 环境请用 render_frame"
        )
    viewer = hou.ui.curDesktop().paneTabOfType(hou.paneTabType.SceneViewer)
    if viewer is None:
        raise ValueError("当前桌面没有 Scene Viewer 面板——请先打开一个场景视口")
    f = hou.frame() if frame is None else float(frame)
    if path is None:
        hip = os.path.dirname(hou.hipFile.path()) or os.getcwd()
        stamp = time.strftime("%H%M%S")
        path = os.path.join(hip, "screenshots", f"viewport_f{int(f)}_{stamp}.png")
    out_dir = os.path.dirname(path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    hou.setFrame(f)
    vp = viewer.curViewport()
    if vp is None:
        raise ValueError("Scene Viewer 没有活动视口")

    st = vp.settings()
    saved_guides = []
    saved_textures = None
    saved_backface = None
    refplane = None
    refplane_was = False
    if clean:
        # 地面参考网格不是 viewportGuide 枚举，是 SceneViewer 的
        # hou.ReferencePlane 对象（setIsVisible）——H21 实测 XZPlane guide
        # 默认就是 False 但网格照画，真正的开关在这里。
        try:
            refplane = viewer.referencePlane()
            refplane_was = bool(refplane.isVisible())
            if refplane_was:
                refplane.setIsVisible(False)
        except Exception:
            refplane = None
        for name in _CLEAN_GUIDES:
            g = getattr(hou.viewportGuide, name, None)
            if g is None:
                continue
            try:
                if st.guideEnabled(g):
                    st.enableGuide(g, False)
                    saved_guides.append(g)
            except Exception:
                continue
    if textures is not None:
        try:
            saved_textures = st.displayTextures()
            st.setDisplayTextures(bool(textures))
        except Exception:
            saved_textures = None
    if backface_cull:
        try:
            saved_backface = st.removeBackfaces()
            st.setRemoveBackfaces(True)
        except Exception:
            saved_backface = None

    # 取景：frame_target=True 表示「/obj 下当前挂 display 旗标的对象」
    # （agent 的直觉写法——2026-08-18 trace 实测 agent 这么传然后报错）。
    if frame_target is True:
        try:
            frame_target = next(
                (c for c in hou.node("/obj").children() if c.isDisplayFlagSet()),
                None,
            )
        except Exception:
            frame_target = None
    cam_restore = None
    framed = None
    if frame_target is not None:
        tn = _resolve(frame_target)
        framed = tn.path()
        try:
            cam = vp.defaultCamera()
            cam_restore = (cam, cam.transform())
        except Exception:
            cam_restore = None
        vp.frameBoundingBox(_display_bbox(tn))

    # FlipbookSettings 是抽象类（无构造），唯一来源是 viewer.flipbookSettings()；
    # flipbook(viewport=None, settings=None, ...) 的 settings 是**一次性覆盖**，
    # 不改对话框设置。但 flipbookSettings() 可能返回对话框的活对象，所以改完
    # 恢复现场，两边都安全。
    settings = viewer.flipbookSettings()
    saved = (settings.output(), settings.outputToMPlay(), settings.frameRange())
    settings.output(path)
    settings.outputToMPlay(False)
    settings.frameRange((f, f))
    try:
        viewer.flipbook(settings=settings)

        actual = path
        deadline = time.time() + 15  # flipbook 异步落盘，等确认
        import glob as _glob
        stem, ext = os.path.splitext(path)
        while time.time() < deadline:
            if os.path.exists(actual) and os.path.getsize(actual) > 0:
                break
            # flipbook 可能给文件名补帧号后缀，按 stem 找最新产物
            candidates = _glob.glob(stem + "*" + ext) or _glob.glob(stem + "*")
            candidates = [c for c in candidates if os.path.getsize(c) > 0]
            if candidates:
                actual = max(candidates, key=os.path.getmtime)
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"flipbook 未产出截图：{path}")
    finally:
        # 恢复必须在文件落盘之后（flipbook 异步）：先恢复 flipbook 对话框设置，
        # 再恢复相机，最后恢复视口显示设置。
        settings.output(saved[0])
        settings.outputToMPlay(saved[1])
        settings.frameRange(saved[2])
        if cam_restore is not None:
            try:
                cam_restore[0].setTransform(cam_restore[1])
            except Exception:
                pass
        if refplane is not None and refplane_was:
            try:
                refplane.setIsVisible(True)
            except Exception:
                pass
        for g in saved_guides:
            try:
                st.enableGuide(g, True)
            except Exception:
                pass
        if saved_textures is not None:
            try:
                st.setDisplayTextures(saved_textures)
            except Exception:
                pass
        if saved_backface is not None:
            try:
                st.setRemoveBackfaces(saved_backface)
            except Exception:
                pass

    result: dict[str, Any] = {
        "path": actual,
        "viewer": viewer.name(),
        "viewport": vp.name(),
        "frame": f,
        "bytes": os.path.getsize(actual),
        "clean": bool(clean),
    }
    if framed is not None:
        result["framed"] = framed
    report_image(actual)
    _restore_webview_window()
    return result


def _try_set(node: hou.Node, name: str, value) -> bool:
    """防御性设参：参数存在才设，返回是否成功（跨版本参数名可能不同）。"""
    p = node.parm(name)
    if p is None:
        return False
    try:
        p.set(value)
        return True
    except Exception:
        return False


_RENDER_PROXY_NAME = "__dsh_houdini_render_proxy"
_RENDER_CAMERA_NAME = "__dsh_houdini_cam"
_RENDER_TARGET_NAME = "__dsh_houdini_target"
_RENDER_ROP_NAME = "__dsh_houdini_opengl"


def _owned_node(parent: hou.Node, name: str, type_name: str) -> hou.Node:
    node = parent.node(name)
    if node is not None:
        if node.userData(_RENDER_OWNER_KEY) != _RENDER_OWNER_VALUE:
            raise ValueError(
                f"agent render 基础设施路径 {node.path()} 已被用户节点占用；"
                f"请重命名该节点后重试（不会自动接管/删除用户节点）"
            )
        return node
    node = parent.createNode(type_name, node_name=name)
    node.setUserData(_RENDER_OWNER_KEY, _RENDER_OWNER_VALUE)
    return node


def _render_service_box(parent: hou.Node, name: str,
                        nodes: list[hou.Node]) -> hou.NetworkBox:
    """Keep persistent render infrastructure grouped away from user nodes.

    Only the first creation chooses a position. Subsequent calls preserve any
    placement the user made while still repairing box membership/comment.
    """
    box = parent.findNetworkBox(name)
    created = box is None
    if box is None:
        box = parent.createNetworkBox(name)

    if created:
        owned = set(nodes)
        positions = [
            child.position() for child in parent.children()
            if child not in owned
        ]
        anchor_x = max((float(pos[0]) for pos in positions), default=0.0) + 6.0
        anchor_y = max((float(pos[1]) for pos in positions), default=0.0)
        for index, node in enumerate(nodes):
            node.setPosition(hou.Vector2(anchor_x, anchor_y - index * 1.5))

    members = set(box.items(recurse=False))
    for node in nodes:
        if node not in members:
            box.addItem(node)
    box.setComment(_RENDER_BOX_COMMENT)
    box.setColor(hou.Color((0.16, 0.30, 0.48)))
    box.fitAroundContents()
    return box


def _resolve_render_sop(node) -> tuple[hou.Node, str | None]:
    target = _resolve(node)
    category = target.type().category()
    if category == hou.sopNodeTypeCategory():
        return target, None
    if category == hou.objNodeTypeCategory():
        resolved = None
        for getter in ("renderNode", "displayNode"):
            try:
                resolved = getattr(target, getter)()
            except Exception:
                resolved = None
            if resolved is not None:
                break
        if resolved is None:
            raise ValueError(
                f"OBJ {target.path()} 没有可解析的 render/display SOP；"
                "为确定性验证请直接传显式 SOP 输出节点"
            )
        return resolved, (
            f"传入 OBJ {target.path()}，调用开始时解析为 {resolved.path()}；"
            "用户可移动 OBJ 内旗标，确定性验证建议直接传 SOP path"
        )
    raise ValueError(
        f"render_view 只接受 SOP 或 Geometry OBJ，收到 {target.path()} "
        f"({category.name()})"
    )


def _geometry_fingerprint(node: hou.Node, frame: float) -> dict:
    geometry = node.geometryAtFrame(frame)
    if geometry is None:
        raise ValueError(f"节点 {node.path()} 在 frame {frame} 没有 geometry")
    points = len(geometry.points())
    prims = len(geometry.prims())
    if points == 0 and prims == 0:
        raise ValueError(
            f"节点 {node.path()} 在 frame {frame} cook 成功但没有可渲染几何；"
            "请传非空显式输出 SOP"
        )
    bbox = geometry.boundingBox()
    bbox_min = [float(v) for v in bbox.minvec()]
    bbox_max = [float(v) for v in bbox.maxvec()]
    signature = hashlib.sha256()
    signature.update(f"{points}|{prims}|{bbox_min}|{bbox_max}".encode("utf-8"))
    # 有界抽样 P：检测用户/上游在验证期间改变真实目标，不遍历百万点全量。
    if points and geometry.findPointAttrib("P") is not None:
        values = list(geometry.pointFloatAttribValues("P"))
        count = min(points, 257)
        indices = [0] if count == 1 else sorted({
            round(i * (points - 1) / (count - 1)) for i in range(count)
        })
        for index in indices:
            offset = index * 3
            signature.update(struct.pack(
                "<3d",
                float(values[offset]),
                float(values[offset + 1]),
                float(values[offset + 2]),
            ))
    errors = list(node.errors())
    warnings = list(node.warnings())
    return {
        "path": node.path(),
        "session_id": node.sessionId(),
        "type": node.type().name(),
        "frame": float(frame),
        "points": points,
        "prims": prims,
        "bbox_min": bbox_min,
        "bbox_max": bbox_max,
        "point_attrs": sorted(a.name() for a in geometry.pointAttribs()),
        "prim_attrs": sorted(a.name() for a in geometry.primAttribs()),
        "errors": errors,
        "warnings": warnings,
        "signature": signature.hexdigest()[:24],
    }


def _ensure_render_proxy(target_sop: hou.Node) -> tuple[hou.Node, hou.Node]:
    obj = hou.node("/obj")
    proxy = _owned_node(obj, _RENDER_PROXY_NAME, "geo")
    if target_sop.parent() == proxy:
        raise ValueError("render_view 不能把 agent render proxy 自身作为源")
    source = proxy.node("source")
    if source is None:
        for child in list(proxy.children()):
            child.destroy()
        source = proxy.createNode("object_merge", node_name="source")
        source.setUserData(_RENDER_OWNER_KEY, _RENDER_OWNER_VALUE)
    elif source.userData(_RENDER_OWNER_KEY) != _RENDER_OWNER_VALUE:
        raise ValueError(f"agent proxy 内部路径 {source.path()} 被非 agent 节点占用")
    output = proxy.node("OUT")
    if output is None:
        output = proxy.createNode("null", node_name="OUT")
        output.setUserData(_RENDER_OWNER_KEY, _RENDER_OWNER_VALUE)
    elif output.userData(_RENDER_OWNER_KEY) != _RENDER_OWNER_VALUE:
        raise ValueError(f"agent proxy 内部路径 {output.path()} 被非 agent 节点占用")
    source.parm("objpath1").set(target_sop.path())
    proxy.setUserData("dsh_render_state", "active")
    proxy.setUserData("dsh_last_target", target_sop.path())
    source.setComment(
        "Temporary render_view source; bound only for the active render.\n"
        f"Current target: {target_sop.path()}"
    )
    _try_set(source, "xformtype", 1)  # Into This Object：保留源 OBJ 世界变换
    output.setInput(0, source)
    output.setDisplayFlag(True)
    output.setRenderFlag(True)
    output.cook(force=True)
    proxy.setDisplayFlag(False)  # forceobjects 仍可渲染；用户 viewport 不出现 proxy
    return proxy, output


def _snapshot_obj_visibility() -> dict:
    states = {}
    for child in hou.node("/obj").children():
        try:
            states[child.path()] = bool(child.isDisplayFlagSet())
        except Exception:
            pass
    return states


def _restore_obj_visibility(states: dict) -> list:
    errors = []
    for path, visible in states.items():
        node = hou.node(path)
        if node is None:
            errors.append(f"missing object during restore: {path}")
            continue
        try:
            node.setDisplayFlag(bool(visible))
        except Exception as error:
            errors.append(f"{path}: {error}")
    return errors


def _snapshot_selection() -> list:
    try:
        return [node.path() for node in hou.selectedNodes()]
    except Exception:
        return []


def _restore_selection(paths: list) -> list:
    errors = []
    try:
        hou.clearAllSelected()
    except Exception as error:
        return [str(error)]
    for path in paths:
        node = hou.node(path)
        if node is not None:
            try:
                node.setSelected(True)
            except Exception as error:
                errors.append(f"{path}: {error}")
    return errors


# render_view 的命名视角（direction 接受这些字符串）：意图层词汇，
# top 故意不沿正 Y（与 up 向量共线会导致 lookat 退化）。
_NAMED_DIRECTIONS = {
    "iso": (1.0, 0.7, 1.0),
    "front": (0.0, 0.25, 1.0),
    "side": (1.0, 0.25, 0.0),
    "top": (0.001, 1.0, 0.001),
}


def render_view(node, direction="iso", frame=None,
                width: int = 1280, height: int = 720, picture=None,
                framing: str = "full", coverage: float = 0.82,
                framing_frame=None) -> dict:
    """显式 SOP → agent proxy → OpenGL ROP → render_check 的隔离验证。

    用户可随时把源 OBJ 的 display/render flag 切到空节点：本动词不跟随它，
    而是让 agent-owned Object Merge 指向传入的**具体 SOP**，OpenGL ROP 用
    ``forceobjects`` 只渲染 proxy。用户 OBJ 可见性、selection、playbar 均恢复。

    - ``node``：强烈建议显式 SOP；传 OBJ 时只在调用开始解析一次 render/display SOP。
    - ``direction``：视线方向（从目标指向相机的偏移向量），默认 3/4 俯视。
      也接受命名视角：``'iso'``（3/4 俯视）、``'front'``、``'side'``、
      ``'top'``（草地重跑 trace：agent 直觉写法就是 ``'iso'``——命名视角
      是意图，向量是实现）。
    - ``frame``：帧号；None = 当前帧。
    - ``framing``：``full`` 完整入镜；``detail`` 拉近到约 55% 距离。
    - ``coverage``：full framing 的画面覆盖率（0.1..0.95）。
    - ``framing_frame``：用哪一帧的 bbox 计算相机；None = 跟随 ``frame``。动画
      A/B 应给两次调用传同一个 framing_frame，确保相机 center/eye/dist 完全一致。
    - 返回 source/proxy fingerprint；真实目标在验证期间变化时 ``stale=True``。

    需要 GUI 会话（OpenGL ROP 要 GL 上下文）；headless 请用 render_frame
    走 CPU 渲染器。注意 GL 渲染在 Windows 锁屏/远程桌面断开时可能失败，
    失败会体现在返回的 ``errors`` 里。
    """
    if not hou.isUIAvailable():
        raise ValueError(
            "render_view 需要 Houdini GUI（OpenGL ROP 要 GL 上下文）；"
            "headless 环境请用 render_frame 走 CPU 渲染器"
        )
    if framing not in ("full", "detail"):
        raise ValueError("framing 只能是 'full' 或 'detail'")
    coverage = float(coverage)
    if not 0.1 <= coverage <= 0.95:
        raise ValueError("coverage 必须在 0.1..0.95")
    if int(width) <= 0 or int(height) <= 0:
        raise ValueError("width/height 必须为正整数")

    target, resolution_note = _resolve_render_sop(node)
    f = float(hou.frame()) if frame is None else float(frame)
    framing_f = f if framing_frame is None else float(framing_frame)
    before = _geometry_fingerprint(target, f)
    if before["errors"]:
        raise ValueError(f"目标 {target.path()} cook error：{before['errors']}")

    obj_visibility = _snapshot_obj_visibility()
    selection = _snapshot_selection()
    proxy = proxy_out = cam = aim = rop = None
    result_payload = None
    try:
        proxy, proxy_out = _ensure_render_proxy(target)
        proxy_before = _geometry_fingerprint(proxy_out, f)
        if proxy_before["errors"]:
            raise ValueError(
                f"agent render proxy 无法读取 {target.path()}：{proxy_before['errors']}"
            )
        framing_fingerprint = _geometry_fingerprint(target, framing_f)
        if framing_fingerprint["errors"]:
            raise ValueError(
                f"目标 {target.path()} 在 framing_frame={framing_f} cook error："
                f"{framing_fingerprint['errors']}"
            )
        framing_geometry = proxy_out.geometryAtFrame(framing_f)
        if framing_geometry is None or len(framing_geometry.points()) == 0:
            raise ValueError(
                f"目标 {target.path()} 在 framing_frame={framing_f} 没有可取景几何"
            )
        bb = framing_geometry.boundingBox()
        center = bb.center()
        extents = bb.sizevec()
        size = max(float(extents[0]), float(extents[1]), float(extents[2]))

        obj = hou.node("/obj")
        out = hou.node("/out")
        cam = _owned_node(obj, _RENDER_CAMERA_NAME, "cam")
        aim = _owned_node(obj, _RENDER_TARGET_NAME, "null")
        rop = _owned_node(out, _RENDER_ROP_NAME, "opengl")
        obj_service_box = _render_service_box(
            obj, _RENDER_OBJ_BOX_NAME, [proxy, cam, aim])
        out_service_box = _render_service_box(
            out, _RENDER_OUT_BOX_NAME, [rop])
        for infra in (cam, aim, proxy):
            try:
                infra.setDisplayFlag(False)
            except Exception:
                pass
        # 创建 agent 节点可能改变 OBJ flags；渲染前立即还原用户现场。
        _restore_obj_visibility(obj_visibility)
        aim.parmTuple("t").set([float(center[0]), float(center[1]), float(center[2])])

        focal, aperture = 50.0, 41.4214
        try:
            focal = float(cam.parm("focal").eval())
            aperture = float(cam.parm("aperture").eval())
        except Exception:
            pass
        fov_h = 2.0 * math.atan(aperture / (2.0 * focal))
        fov_v = 2.0 * math.atan(math.tan(fov_h / 2.0) * float(height) / float(width))
        fov = min(fov_h, fov_v)
        dist = (max(size, 1e-3) / 2.0) / math.tan(fov / 2.0) / coverage
        if framing == "detail":
            dist *= 0.55

        if isinstance(direction, str):
            named = _NAMED_DIRECTIONS.get(direction.strip().lower())
            if named is None:
                raise ValueError(
                    f"direction 收到未知名称 {direction!r}；可用："
                    f"{sorted(_NAMED_DIRECTIONS)} 或三分量向量 [x, y, z]"
                )
            direction = named
        d = hou.Vector3(*[float(x) for x in direction])
        if d.length() < 1e-6:
            raise ValueError(f"direction 不能是零向量：{direction!r}")
        d = d.normalized()
        eye = center + d * dist
        cam.parmTuple("t").set([float(eye[0]), float(eye[1]), float(eye[2])])
        if not _try_set(cam, "lookat", aim.path()):
            up = hou.Vector3(0, 1, 0)
            fwd = (center - eye).normalized()
            right = fwd.cross(up).normalized()
            up2 = right.cross(fwd).normalized()
            cam.setWorldTransform(hou.Matrix4((
                right[0], right[1], right[2], 0.0,
                up2[0], up2[1], up2[2], 0.0,
                -fwd[0], -fwd[1], -fwd[2], 0.0,
                eye[0], eye[1], eye[2], 1.0,
            )))

        # OpenGL ROP 完全拥有自己的对象/灯光/颜色设置，不消费用户 display/light。
        settings = {
            "camera": cam.path(),
            "vobjects": proxy.path(),
            "forceobjects": proxy.path(),
            "excludeobjects": f"{cam.path()} {aim.path()}",
            "alights": "",
            "forcelights": "",
            "excludelights": "*",
            "shadingmode": "smooth",
            "usegeocolor": True,
            "colorcorrect": "none",
            "gamma": 1.0,
            "tres": True,
            "override_camerares": True,
            "res1": int(width),
            "res2": int(height),
        }
        applied = {name: _try_set(rop, name, value) for name, value in settings.items()}

        if picture is None:
            hip = os.path.dirname(hou.hipFile.path()) or os.getcwd()
            frame_tag = str(f).replace("-", "m").replace(".", "p")
            picture = os.path.join(
                hip, "render", f"dsh_view_{time.time_ns()}_f{frame_tag}.png")

        rendered = render_frame(rop, picture=picture, frame=f)
        check = None
        if rendered.get("file_bytes"):
            try:
                check = render_check(rendered["output"])
            except Exception as error:
                check = {"error": str(error)}
        after = _geometry_fingerprint(target, f)
        proxy_after = _geometry_fingerprint(proxy_out, f)
        stale = before["signature"] != after["signature"]
        proxy_stale = proxy_before["signature"] != proxy_after["signature"]
        result_payload = {
            "target": target.path(),
            "resolved_from": _resolve(node).path(),
            "proxy": proxy.path(),
            "proxy_output": proxy_out.path(),
            "camera": cam.path(),
            "rop": rop.path(),
            "render_service": {
                "persistent": True,
                "delete_during_session": False,
                "obj_network_box": obj_service_box.name(),
                "out_network_box": out_service_box.name(),
            },
            "output": rendered["output"],
            "frame": f,
            "file_bytes": rendered["file_bytes"],
            "errors": rendered["errors"],
            "warnings": list(dict.fromkeys(before["warnings"] + proxy_before["warnings"])),
            "stale": stale or proxy_stale,
            "source_fingerprint_before": before,
            "source_fingerprint_after": after,
            "proxy_signature_before": proxy_before["signature"],
            "proxy_signature_after": proxy_after["signature"],
            "framing": {
                "mode": framing,
                "frame": framing_f,
                "coverage": coverage,
                "center": [float(x) for x in center],
                "size": float(size),
                "dist": round(float(dist), 6),
                "eye": [float(x) for x in eye],
                "direction": [float(x) for x in d],
                "source_signature": framing_fingerprint["signature"],
            },
            "rop_settings_applied": applied,
            "check": check,
        }
        if resolution_note:
            result_payload["note"] = resolution_note
        if result_payload["stale"]:
            result_payload["stale_reason"] = (
                "target/proxy geometry changed during visual verification；"
                "不要据此宣称成功，请重新检查并渲染"
            )
        return result_payload
    finally:
        restore_errors = _restore_obj_visibility(obj_visibility)
        restore_errors.extend(_restore_selection(selection))
        if proxy is not None:
            try:
                proxy.setDisplayFlag(False)
            except Exception as error:
                restore_errors.append(f"{proxy.path()}: {error}")
            # 空闲 proxy 不长期引用用户节点；下一次 render_view 会重新绑定显式 SOP。
            try:
                source = proxy.node("source")
                if source is not None and source.parm("objpath1") is not None:
                    source.parm("objpath1").set("")
                    last_target = target.path()
                    last_frame = result_payload.get("frame") if result_payload else f
                    last_output = result_payload.get("output") if result_payload else None
                    proxy.setUserData("dsh_render_state", "idle")
                    proxy.setUserData("dsh_last_target", last_target)
                    proxy.setUserData("dsh_last_frame", str(last_frame))
                    if last_output:
                        proxy.setUserData("dsh_last_output", str(last_output))
                    source.setComment(
                        "Temporary render_view source; objpath1 is bound only while rendering "
                        "and cleared afterward.\n"
                        f"Last target: {last_target}\nLast frame: {last_frame}"
                    )
            except Exception as error:
                restore_errors.append(f"{proxy.path()}/source: {error}")
        if result_payload is not None:
            result_payload["user_state_restored"] = not restore_errors
            if restore_errors:
                result_payload["restore_errors"] = restore_errors
