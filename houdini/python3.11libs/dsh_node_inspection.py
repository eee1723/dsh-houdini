"""Houdini node inspection. Executed on the Bridge owning thread."""
from __future__ import annotations

import fnmatch
import hou
import dsh_node_access
import dsh_node_operations
import dsh_node_types


def find_nodes(pattern: str = "*", category=None, node_type=None, root=None) -> list:
    """在场景里找**已存在**的节点，返回扁平 path 列表（按路径排序）。

    - ``pattern``：glob 匹配节点名（``fnmatch``）。
    - ``category``：可选，按节点类别过滤（'sop'/'obj'/...）。
    - ``node_type``：可选，按类型名过滤（基名或全名，不区分大小写）。
    - ``root``：从哪个节点开始搜（默认 '/'）。
    """
    root_node = dsh_node_access._resolve(root) if root is not None else hou.node("/")
    cat = dsh_node_types._category(category) if category else None
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
    n = dsh_node_access._resolve(node)
    up = _hop_paths(n, "up", depth) if direction in ("both", "up") else []
    down = _hop_paths(n, "down", depth) if direction in ("both", "down") else []
    refs = sorted(x.path() for x in n.parmsReferencingThis()
                  if x.node() != n and not x.node().path().startswith(n.path() + '/'))
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
        s["bbox_size"] = [float(x) for x in bb.sizevec()]
    except Exception:
        pass
    return s


def describe(node) -> dict:
    """节点状态 + 几何摘要 + 帮助元数据（Stage 1）——一次拿到「它现在什么状态、流着什么数据」。"""
    n = dsh_node_access._resolve(node)
    t = n.type()
    info: dict = {
        "path": n.path(),
        "name": n.name(),
        "type": t.name(),
        "category": t.category().name(),
    }
    info['ports'] = dsh_node_operations._port_metadata(n)

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
        if hou.updateModeSetting() == hou.updateMode.Manual:
            info['geometry'] = None
            info['geometry_status'] = 'not_evaluated_manual'
            info['update_mode'] = 'manual'
            info['geometry_note'] = 'Metadata only: no geometry evaluation requested in Manual mode; not proof of empty geometry.'
            return info
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
