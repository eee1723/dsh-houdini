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
import re
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

    - ``parent``：目标父节点（如 hou.node('/obj') 或某个 geo）。
    - ``type_name``：基名即可（'copytopoints'、'box'、'geo'），内部解析最新版。
    - ``inputs``：可选，创建后按序连到 input 0..n（节点或路径均可；
      连接失败会抛错，不会静默跳过）。
    - 有对应 shelf tool 且其带额外初始化时走 tool；否则回退 createNode(latest)
      （避免对 box/grid 这类纯节点做昂贵的 pane 导航）。
    """
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

    # 几何摘要（仅 SOP 有 geometry()）
    if t.category().name() == "sop":
        try:
            geo = n.geometry()
            info["geometry"] = _geo_summary(geo) if geo is not None else None
        except Exception:
            info["geometry"] = None

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
