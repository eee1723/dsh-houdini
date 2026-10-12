"""Houdini node access. Executed on the Bridge owning thread."""
from __future__ import annotations

import hou


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


def _resolve_in_parent(parent, value) -> hou.Node:
    """A node reference uses an explicit parent, never Houdini's ambient cwd."""
    if isinstance(value, str) and not value.startswith('/'):
        node = parent.node(value)
        if node is None:
            raise ValueError(f"节点不存在：{value!r} relative to {parent.path()}")
        return node
    return _resolve(value)


def _val(v):
    """把 HOM 值转成 JSON 安全（Vector/Matrix/Color → list），其余原样返回。"""
    if isinstance(v, (hou.Vector2, hou.Vector3, hou.Vector4)):
        return [float(x) for x in v]
    if isinstance(v, hou.Color):
        return [float(v.r()), float(v.g()), float(v.b()), float(v.a())]
    if isinstance(v, (hou.Matrix3, hou.Matrix4)):
        return [[float(x) for x in row] for row in v]
    return v


def _hda_definition(node) -> tuple[hou.Node, hou.HDADefinition]:
    n = _resolve(node)
    definition = n.type().definition()
    if definition is None:
        raise ValueError(
            f"节点 '{n.path()}' 不是数字资产（node.type().definition() 为 None）；"
            "请先用 hda_create 把 subnet 转为 HDA"
        )
    return n, definition
