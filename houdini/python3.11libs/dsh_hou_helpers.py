"""dsh-houdini: 按 Tab Menu 语义创建 Houdini 节点。

解决两个问题：

1. **通用初始化** —— 部分节点（如 ``copytopoints::2.0``）通过 Tab Menu 创建时，
   shelf tool 脚本会做额外初始化（按初始化按钮、建配套节点、设参数等）。裸
   ``hou.Node.createNode`` 不会做这些。本模块用 ``toolutils.testTool`` 跑真实的
   shelf tool，完整保留初始化语义，且对未来 SideFX 改动脚本自动跟随——不为任何
   节点写死「按哪个按钮」。

2. **永远最新版本** —— ``hou.preferredNodeType`` 实测不可靠（返回 None），这里枚举
   ``nodeTypes()`` 取 ``::N`` 最大的版本，创建和自省共用同一解析。

只依赖 ``hou`` / ``toolutils`` / 标准库，不导入项目 venv 任何包（进程边界）。
本模块被 ``dsh_bridge`` 预置进 exec namespace，agent 写 Python 时可直接：

    geo = tab_create(hou.node('/obj'), 'geo', name='my_geo')
    cop = tab_create(geo, 'copytopoints', inputs=[box, points])
    search_tab_menu('sop', 'cone')     # 查不猜：列出匹配类型 + 最新版

注意：``tab_create`` 返回 ``hou.Node``（供 agent 继续链式操作）；要回传结构化数据，
请手动转 JSON（``__result__ = {'path': node.path()}``），不要直接把 hou 对象塞进
``__result__``。
"""

from __future__ import annotations

import difflib
import fnmatch
import math
import os
import re
import struct
import time
import zlib
from typing import Any

import hou
import toolutils

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

_VERSION_RE = re.compile(r"^(.*)::(\d+(?:\.\d+)*)$")


def _category(category):
    if isinstance(category, hou.NodeTypeCategory):
        return category
    if isinstance(category, str):
        factory = _CATEGORIES.get(category.strip().lower())
        if factory is None:
            raise ValueError(f"unknown node type category: {category!r}")
        return factory()
    raise ValueError(f"unknown node type category: {category!r}")


def context_name(category) -> str:
    """hou.sopNodeTypeCategory() -> 'sop'（用于构造 shelf tool 名）。"""
    return _category(category).name().lower()


def _version_key(version: str):
    return tuple(int(p) for p in version.split("."))


def resolve_latest_type(category, base: str) -> str:
    """返回某节点族的最新版本全名，如 'copytopoints' -> 'copytopoints::2.0'。

    无版本化条目时原样返回 ``base``；有多个 ``::N`` 时取 ``N`` 最大者。
    """
    cat = _category(category)
    prefix = base + "::"
    best_key: tuple[int, ...] = ()
    best_name = base
    for name in cat.nodeTypes().keys():
        if not name.startswith(prefix):
            continue
        m = _VERSION_RE.match(name)
        if not m:
            continue
        key = _version_key(m.group(2))
        if key > best_key:
            best_key = key
            best_name = name
    return best_name


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
    except Exception:
        raise
    finally:
        try:
            if prev_pwd is not None:
                pane.setPwd(prev_pwd)
        except Exception:
            pass

    created = [c for c in parent.children() if c.sessionId() not in before]
    if len(created) == 1:
        return created[0]
    # 多个新节点：优先类型完全匹配；否则取第一个（绝不回退 createNode——
    # tool 已经建过节点，再建一次就是场景里的重复残留）
    match = next((c for c in created if c.type().name() == type_name), None)
    if match is not None:
        return match
    return created[0] if created else None


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
    """
    parent = _resolve(parent)  # 铁律 1：hou.Node 或 path 字符串均可
    cat = parent.childTypeCategory()
    ctx = context_name(cat)
    latest = resolve_latest_type(cat, type_name)

    tool = None
    try:
        tool = hou.shelves.tool(f"{ctx}_{latest}")
    except Exception:
        tool = None

    node: hou.Node | None = None
    if tool is not None and _tool_has_extra_init(tool):
        try:
            node = _run_shelf_tool(tool, parent, latest)
        except Exception:
            node = None  # tool 执行失败 → 回退裸 createNode

    if node is None:
        node = parent.createNode(latest, node_name=name, exact_type_name=True)
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

    # 按族键聚合（去版本），族键 = 名字去掉末尾 ::N
    families: dict[str, list[str]] = {}
    for name in cat.nodeTypes().keys():
        if q and q not in name.lower():
            continue
        m = _VERSION_RE.match(name)
        base = m.group(1) if m else name
        families.setdefault(base, []).append(name)

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
            if entry["base"].lower() == q:
                exact = entry["latest"]
                break
    return {"families": result, "latest_of_query": exact}


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

def connect(src, dst, index: int = 0) -> dict:
    """把 ``src`` 的输出连到 ``dst`` 的第 ``index`` 个输入。

    返回 ``{"node": dst path, "input": 实际落到的输入口}``。请求的端口不存在时
    退化为「下一个可用输入」，此时返回里会带 ``note``——落口与请求不一致必须
    让调用方知道，静默改口会让 agent 基于错误的连线继续推理。
    """
    s = _resolve(src)
    d = _resolve(dst)
    try:
        d.setInput(index, s)
        return {"node": d.path(), "input": index}
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
    }


def rename_node(node, name: str) -> str:
    """重命名节点（自动去重），返回新 path。"""
    n = _resolve(node)
    n.setName(name, unique_name=True)
    return n.path()


def delete_node(node) -> dict:
    """删除节点，返回被删 path 及「谁曾用表达式引用它」（删除后可能断链的上游）。"""
    n = _resolve(node)
    refs = sorted(x.path() for x in n.parmsReferencingThis())
    path = n.path()
    n.destroy()
    result: dict = {"deleted": path}
    if refs:
        result["orphaned_parm_refs"] = refs
    return result


def cook_node(node) -> dict:
    """cook 节点并采集 errors/warnings（不强制重 cook）。"""
    n = _resolve(node)
    cook_error = None
    try:
        n.cook(force=False)
    except Exception as e:  # hou.OperationFailed 等
        cook_error = str(e)
    errors = list(n.errors())
    if cook_error and cook_error not in errors:
        errors.insert(0, cook_error)
    return {
        "path": n.path(),
        "errors": errors,
        "warnings": list(n.warnings()),
    }


def set_display(node, render: bool = True) -> dict:
    """把 display（默认连同 render）旗标移到指定节点。

    视口和渲染只认挂旗标的那个节点——「最后建的节点」不等于「被显示的
    节点」。搭完/改完 SOP 链后、渲染或截图前，必须把旗标移到最终输出
    节点，否则画面里只有链上某一个中间节点（典型事故：渲染出来只有
    第一个 circle，后面整串 polywire/merge 都不可见）。
    """
    n = _resolve(node)
    n.setDisplayFlag(True)
    if render:
        n.setRenderFlag(True)
    return {"node": n.path(), "display": True, "render": bool(render)}


def display_node(parent) -> dict:
    """报告网络里 display / render 旗标当前挂在哪个节点（渲染前核对用）。

    返回里附 `is_leaf`：旗标节点还有下游时标 False 并带 `note`——下游
    节点不会出现在视口/渲染里，多半意味着旗标忘了移到链尾。
    """
    p = _resolve(parent)

    def _flag(getter):
        try:
            return getter()
        except Exception:  # 非 SOP 网络 / 无旗标节点等
            return None

    d = _flag(p.displayNode)
    r = _flag(p.renderNode)
    result: dict = {
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
        if changed_only and is_default and not has_expr and not is_ref:
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
        out.append(entry)
    return out


def set_parm(node, name: str, value) -> dict:
    """设参数（组件名或元组名均可）；失败时列出相似参数名供自纠。

    数值型参数收到字符串值时按**表达式**处理（H21/H22 实测 ``Parm.set(str)``
    对数值参数直接抛 TypeError，必须走 ``setExpression``）——这让
    ``set_parm(n, 'tx', 'ch(\"ty\")')`` 这类最高频操作可用。
    """
    n = _resolve(node)
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
        p.set(value)
        return {"parm": p.name(), "value": _val(p.eval())}

    pt = n.parmTuple(name)
    if pt is not None:
        if isinstance(value, (list, tuple)):
            pt.set(value)
            return {"parm": pt.name(), "value": [_val(v) for v in pt.eval()]}
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

    - rop：ROP 节点（hou.Node 或 path）。输出参数按常见名自动解析
      （picture / vm_picture / sopoutput / lopoutput / outputimage / dopoutput /
      copoutput / choutput），Karma/Mantra/geometry 等 ROP 都覆盖。
    - picture：输出路径（含 $F 变量可直接传）；None = 用 ROP 当前设置。
    - frame：帧号；None = 当前帧。
    - timeout：等产物的上限（秒）。超过 ~110s 的渲染请走 houdini_job_submit
      （host 侧桥请求超时 120s），本动词面向单帧测试渲染。
    """
    n = _resolve(rop)
    p = None
    for pname in ("picture", "vm_picture", "sopoutput", "lopoutput",
                  "outputimage", "dopoutput", "copoutput", "choutput"):
        p = n.parm(pname)
        if p is not None:
            break
    if p is None:
        raise ValueError(
            f"节点 '{n.path()}' 找不到输出路径参数（试过 picture/vm_picture/"
            "sopoutput/lopoutput/outputimage/dopoutput/copoutput/choutput）——"
            "它不是 ROP？（非常规输出参数请裸写 hou，词表不覆盖）"
        )
    if picture is not None:
        p.set(picture)
    f = hou.frame() if frame is None else float(frame)
    hou.setFrame(f)
    target = hou.text.expandString(p.unexpandedString())
    out_dir = os.path.dirname(target)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    t0 = time.time()
    render_err = None
    try:
        n.render(frame_range=(f, f))
    except Exception as e:  # hou.Error 等
        render_err = str(e)

    file_bytes = None
    deadline = t0 + float(timeout)
    while not render_err and time.time() < deadline:
        if os.path.exists(target) and os.path.getsize(target) > 0:
            file_bytes = os.path.getsize(target)
            break
        time.sleep(1)

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
        errors.append(f"render() 未报错但产物缺失或为空：{target}")
    if file_bytes:
        report_image(target)
    return {
        "path": n.path(),
        "output": target,
        "frame": f,
        "file_bytes": file_bytes,
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
            for y in range(0, h, step):
                for x in range(0, w, step):
                    p1, p2 = pixels[y][x], pixels2[y][x]
                    diffs.append(max(abs(p1[i] - p2[i]) for i in range(3)))
            out["diff_vs_ref"] = {
                "comparable": True,
                "identical": max(diffs) == 0 if diffs else True,
                "mean_abs_diff": round(sum(diffs) / len(diffs), 3) if diffs else 0,
                "max_abs_diff": max(diffs) if diffs else 0,
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


# render_view 的命名视角（direction 接受这些字符串）：意图层词汇，
# top 故意不沿正 Y（与 up 向量共线会导致 lookat 退化）。
_NAMED_DIRECTIONS = {
    "iso": (1.0, 0.7, 1.0),
    "front": (0.0, 0.25, 1.0),
    "side": (1.0, 0.25, 0.0),
    "top": (0.001, 1.0, 0.001),
}


def render_view(node, direction=(1.0, 0.7, 1.0), frame=None,
                width: int = 1280, height: int = 720, picture=None) -> dict:
    """验证渲染一步到位：专用相机取景 → OpenGL ROP 离屏渲染 → render_check。

    「副驾驶」定位下的视觉验证主干：视口是用户的草稿纸（随时可能被用户
    移动/最小化），验证不碰它——本动词用 agent 自己拥有的相机
    （``/obj/dsh_cam`` + ``/obj/dsh_cam_target``，复用不重复创建）和
    ``/out/dsh_opengl`` ROP 离屏出图，质量≈视口（实时 GL 光栅化），
    确定性≈渲染管线。构图（取景角度/距离/焦距）想精细控制时，拆开来用
    裸 hou 调 ``/obj/dsh_cam`` 再 ``render_frame``。

    - ``node``：取景目标（SOP 或 OBJ），按显示几何 bbox 取景。
    - ``direction``：视线方向（从目标指向相机的偏移向量），默认 3/4 俯视。
      也接受命名视角：``'iso'``（3/4 俯视）、``'front'``、``'side'``、
      ``'top'``（草地重跑 trace：agent 直觉写法就是 ``'iso'``——命名视角
      是意图，向量是实现）。
    - ``frame``：帧号；None = 当前帧。
    - ``picture``：输出路径；None = ``$HIP/render/dsh_view_<时间>.png``。
    - 返回含 ``check``（render_check 结果）与取景参数；产物自动登记进
      ``images``（host 回传到工作区，vision 工具可读）。

    需要 GUI 会话（OpenGL ROP 要 GL 上下文）；headless 请用 render_frame
    走 CPU 渲染器。注意 GL 渲染在 Windows 锁屏/远程桌面断开时可能失败，
    失败会体现在返回的 ``errors`` 里。
    """
    if not hou.isUIAvailable():
        raise ValueError(
            "render_view 需要 Houdini GUI（OpenGL ROP 要 GL 上下文）；"
            "headless 环境请用 render_frame 走 CPU 渲染器"
        )
    target = _resolve(node)
    bb = _display_bbox(target)
    center = bb.center()
    extents = bb.sizevec()
    size = max(float(extents[0]), float(extents[1]), float(extents[2]))

    # --- 相机与目标点（复用，不重复创建） ---
    cam = hou.node("/obj/dsh_cam") or tab_create("/obj", "cam", "dsh_cam")
    aim = hou.node("/obj/dsh_cam_target") or tab_create("/obj", "null", "dsh_cam_target")
    aim.parmTuple("t").set([float(center[0]), float(center[1]), float(center[2])])

    # --- 取景：距离按相机视场角反推，保证主体完整入镜并留边距 ---
    focal, aperture = 50.0, 41.4214
    try:
        focal = float(cam.parm("focal").eval())
        aperture = float(cam.parm("aperture").eval())
    except Exception:
        pass
    fov_h = 2.0 * math.atan(aperture / (2.0 * focal))
    fov_v = 2.0 * math.atan(math.tan(fov_h / 2.0) * float(height) / float(width))
    fov = min(fov_h, fov_v)
    dist = (max(size, 1e-3) / 2.0) / math.tan(fov / 2.0) * 1.4  # 1.4 = 边距

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
        # 无 lookat 参数（非常规相机）时的回退：直接写世界变换。
        # Houdini 约定：相机看向局部 -Z，Matrix4 行主序，
        # 行 0/1/2 = 相机局部 X/Y/Z 轴的世界方向，行 3 = 平移。
        up = hou.Vector3(0, 1, 0)
        fwd = (center - eye).normalized()
        right = fwd.cross(up).normalized()
        up2 = right.cross(fwd).normalized()
        m = hou.Matrix4((
            right[0], right[1], right[2], 0.0,
            up2[0], up2[1], up2[2], 0.0,
            -fwd[0], -fwd[1], -fwd[2], 0.0,
            eye[0], eye[1], eye[2], 1.0,
        ))
        cam.setWorldTransform(m)

    # --- OpenGL ROP（复用） ---
    # 分辨率开关在不同版本叫 tres / override_camerares——两个都试（幂等）。
    rop = hou.node("/out/dsh_opengl") or tab_create("/out", "opengl", "dsh_opengl")
    _try_set(rop, "camera", cam.path())
    _try_set(rop, "tres", True)
    _try_set(rop, "override_camerares", True)
    _try_set(rop, "res1", int(width))
    _try_set(rop, "res2", int(height))

    if picture is None:
        hip = os.path.dirname(hou.hipFile.path()) or os.getcwd()
        picture = os.path.join(
            hip, "render", f"dsh_view_{time.strftime('%H%M%S')}.png")

    f = hou.frame() if frame is None else float(frame)
    r = render_frame(rop, picture=picture, frame=f)
    check = None
    if r.get("file_bytes"):
        try:
            check = render_check(r["output"])
        except Exception as e:
            check = {"error": str(e)}
    return {
        "target": target.path(),
        "camera": cam.path(),
        "rop": rop.path(),
        "output": r["output"],
        "frame": f,
        "file_bytes": r["file_bytes"],
        "errors": r["errors"],
        "framing": {
            "center": [float(x) for x in center],
            "size": float(size),
            "dist": round(float(dist), 3),
        },
        "check": check,
    }
