"""Houdini render service. Executed on the Bridge owning thread."""
from __future__ import annotations

import hou
import dsh_node_access
import dsh_service_constants


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


_RENDER_FLIPBOOK_NAME = "__dsh_houdini_flipbook"


def _owned_node(parent: hou.Node, name: str, type_name: str) -> hou.Node:
    node = parent.node(name)
    if node is not None:
        if node.userData(dsh_service_constants._RENDER_OWNER_KEY) != dsh_service_constants._RENDER_OWNER_VALUE:
            raise ValueError(
                f"agent render 基础设施路径 {node.path()} 已被用户节点占用；"
                f"请重命名该节点后重试（不会自动接管/删除用户节点）"
            )
        return node
    node = parent.createNode(type_name, node_name=name)
    node.setUserData(dsh_service_constants._RENDER_OWNER_KEY, dsh_service_constants._RENDER_OWNER_VALUE)
    # A current preview may add Flipbook to a HIP retaining the legacy OpenGL
    # renderer. Place only this newly created root service node beside the
    # existing service group; its default origin would enlarge the box again.
    if (parent.path() in ('/obj', '/out')
            and parent.findNetworkBox(dsh_service_constants._RENDER_OBJ_BOX_NAME) is not None):
        existing = [child for child in parent.children()
                    if child != node
                    and child.userData(dsh_service_constants._RENDER_OWNER_KEY) == dsh_service_constants._RENDER_OWNER_VALUE]
        if existing:
            node.setPosition(hou.Vector2(
                min(float(child.position()[0]) for child in existing),
                min(float(child.position()[1]) for child in existing) - 1.5))
    return node


def _render_service_box(parent: hou.Node, name: str,
                        nodes: list[hou.Node]) -> hou.NetworkBox:
    """Keep persistent render infrastructure grouped away from user nodes.

    Only the first creation chooses a position. Subsequent calls preserve any
    placement the user made while still repairing box membership/comment.
    Persist a fixed fit. The title must round-trip through HIP metadata; an
    invalid native title can reset the bounds to the origin on the next load.
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

    # A HIP can retain both a legacy OpenGL ROP and the current Flipbook ROP. They are
    # persistent service nodes even when only one is used by this preview.
    owned = {
        child for child in parent.children()
        if child.userData(dsh_service_constants._RENDER_OWNER_KEY) == dsh_service_constants._RENDER_OWNER_VALUE
    }
    members = set(box.items(recurse=False))
    for item in members - owned:
        box.removeItem(item)
    for node in owned - members:
        box.addItem(node)
    box.setComment(dsh_service_constants._RENDER_BOX_COMMENT)
    box.setColor(hou.Color((0.12, 0.20, 0.30)))
    box.setAutoFit(False)
    box.fitAroundContents()
    from dsh_network_boxes import register_service_box
    register_service_box(box)
    return box


def _resolve_render_sop(node) -> tuple[hou.Node, str | None]:
    target = dsh_node_access._resolve(node)
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
        source.setUserData(dsh_service_constants._RENDER_OWNER_KEY, dsh_service_constants._RENDER_OWNER_VALUE)
    elif source.userData(dsh_service_constants._RENDER_OWNER_KEY) != dsh_service_constants._RENDER_OWNER_VALUE:
        raise ValueError(f"agent proxy 内部路径 {source.path()} 被非 agent 节点占用")
    output = proxy.node("OUT")
    if output is None:
        output = proxy.createNode("null", node_name="OUT")
        output.setUserData(dsh_service_constants._RENDER_OWNER_KEY, dsh_service_constants._RENDER_OWNER_VALUE)
    elif output.userData(dsh_service_constants._RENDER_OWNER_KEY) != dsh_service_constants._RENDER_OWNER_VALUE:
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
