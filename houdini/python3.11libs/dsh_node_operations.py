"""Houdini node operations. Executed on the Bridge owning thread."""
from __future__ import annotations

import hou
import dsh_node_creation
import dsh_parameter_values
import dsh_node_access
import dsh_node_layout
import dsh_ownership
import dsh_service_constants


def _matrix_values(matrix) -> list[float]:
    return [float(value) for value in matrix.asTuple()]


def set_object_parent(child, parent, keep_world: bool = True, reason: str = "",
                      index: int = 0, allow_foreign: str | None = None) -> dict:
    """显式设置 OBJ parent，参数顺序是 ``child, parent``。

    只表达明确的 OBJ hierarchy 操作，建模/rig 表示由当前任务决定。``reason``
    可记录可选的用途说明，不限制用途。``parent=None`` 表示 unparent；普通父级
    使用 ``index=0``，Blend 等明确多输入对象可指定其他 input。
    ``keep_world=True`` 在改层级后恢复 child 的原世界变换，并回读验证 parent。
    """
    c = dsh_node_access._resolve(child)
    p = None if parent is None else dsh_node_access._resolve(parent)
    obj_category = hou.objNodeTypeCategory()
    if c.type().category() != obj_category:
        raise ValueError(f"set_object_parent 的 child 必须是 OBJ，收到 {c.path()}")
    if p is not None and p.type().category() != obj_category:
        raise ValueError(f"set_object_parent 的 parent 必须是 OBJ 或 None，收到 {p.path()}")
    reason = str(reason or "").strip()
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

    dsh_ownership.require_owned(c, "set_object_parent child", allow_foreign)
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


def _input_state(node):
    connections = node.inputConnections()
    rows = []
    for connection in connections[:128]:
        source = connection.inputNode()
        # A native subnet indirect input is a NetworkMovableItem, not a Node.
        # Preserve that distinction instead of inventing a node or dropping it.
        indirect = connection.subnetIndirectInput() if source is None else None
        rows.append({'input': connection.inputIndex(),
                     'source': source.path() if source is not None else None,
                     'source_kind': 'node' if source is not None else
                                    'subnet_indirect_input' if indirect is not None else 'non_node',
                     'source_output': connection.outputIndex()})
    return {'connections': rows, 'count': len(connections), 'truncated': len(connections) > 128}


def _port_metadata(node):
    """Native connector metadata; no cook, guessing or name-to-role inference."""
    result = {}
    for direction in ('input', 'output'):
        names = tuple(getattr(node, direction + 'Names')())
        labels = tuple(getattr(node, direction + 'Labels')())
        types_method = getattr(node, direction + 'DataTypes', None)
        types = tuple(types_method()) if types_method else ()
        count = max(len(names), len(labels), len(getattr(node, direction + 'Connectors')()))
        result[direction + 's'] = [dict(index=i, name=names[i] if i < len(names) else None,
            label=labels[i] if i < len(labels) else None, data_type=types[i] if i < len(types) else None)
            for i in range(min(count, 128))]
        result[direction + '_count'] = count
        result[direction + '_truncated'] = count > 128
    return result


def _resolve_port(node, selector, direction):
    names = tuple(getattr(node, direction + 'Names')())
    if isinstance(selector, str):
        matches = [i for i, name in enumerate(names) if name == selector]
        if not selector or len(matches) != 1:
            raise ValueError(f'{direction} port name must match exactly once: {selector!r}; available={names[:128]}')
        return matches[0]
    if type(selector) is not int or selector < 0:
        raise ValueError(f'{direction} port must be a nonnegative integer or exact name')
    count = (node.type().maxNumInputs() if direction == 'input'
             else max(len(names), len(node.outputConnectors())))
    if selector >= count:
        raise ValueError(f'{direction} port index {selector} outside 0..{count - 1} on {node.path()}')
    return selector


def connect(src, dst, index: int | str = 0, *, output: int | str = 0, allow_foreign: str | None = None) -> dict:
    """把 ``src`` 的输出连到 ``dst`` 的第 ``index`` 个输入。

    只表达普通网络 dataflow；OBJ→OBJ 是 parenting，明确拒绝并要求
    ``set_object_parent(child, parent)``。
    返回 ``{"node": dst path, "input": 实际落到的输入口, "position_adjusted": bool}``。
    请求的端口不存在或连接失败时明确拒绝，不尝试改接其他端口。
    index 为目标输入名/索引；keyword-only output 为源输出名/索引，默认0保持兼容。
    先解析两端并检查类型，再写入；不按label猜名称、不自动改接；第4位置参数拒绝。
    连接成功后做 flow 纠流（``_snap_into_flow``）：dst 不在所有输入下游时，以输入
    正下方为首选并对节点、Box与注释项做有界避障；已在下游的节点绝不动。若没有
    安全落位，接线保留并以``placement_status='blocked'``报告，不移动dst。
    """
    s = dsh_node_access._resolve(src)
    d = dsh_node_access._resolve(dst)
    if (s.type().category() == hou.objNodeTypeCategory()
            and d.type().category() == hou.objNodeTypeCategory()):
        raise ValueError(
            "connect 只表达网络数据流，不执行 OBJ parenting。"
            f"当前连线会把 {s.path()} 作为 parent、{d.path()} 作为 child；"
            "请改用 set_object_parent(child, parent, keep_world=True)。"
        )
    dsh_ownership.require_owned(d, "connect destination", allow_foreign)
    if s.parent() != d.parent():
        raise ValueError(f'different_parent: source={s.path()} parent={s.parent().path()}, destination={d.path()} parent={d.parent().path()}; use an Object Merge inside the destination SOP network or an explicit subnet input. Changing the input index cannot fix this boundary')
    index = _resolve_port(d, index, 'input')
    output = _resolve_port(s, output, 'output')
    compatible = getattr(d, 'isInputCompatible', None)
    # COP Cache/Null-like ports acquire their signature from the first wire.
    # Native isInputCompatible reports false while they are still 'undef'.
    dynamic_type = (isinstance(d, hou.CopNode) and
                    (index >= len(d.inputDataTypes()) or d.inputDataTypes()[index] == 'undef'))
    # H22 USD Material COP reports incompatible even for native RGB->RGB
    # and Mono->Mono wires that setInput accepts. Keep the exception narrow:
    # concrete, identical image signatures only; no implicit channel coercion.
    material_signature = False
    if (isinstance(s, hou.CopNode) and isinstance(d, hou.CopNode)
            and d.type().nameComponents()[2] == 'usdmaterial'):
        source_types, target_types = s.outputDataTypes(), d.inputDataTypes()
        material_signature = (output < len(source_types) and index < len(target_types)
                              and source_types[output] == target_types[index]
                              and source_types[output] in ('Mono', 'UV', 'RGB', 'RGBA'))
    if compatible is not None and not dynamic_type and not material_signature and not compatible(index, s, output):
        raise ValueError(f'incompatible ports: {s.path()} output {output} -> {d.path()} input {index}; zero connection writes')
    before = _input_state(d)
    try:
        d.setInput(index, s, output)
    except Exception as e:
        raise ValueError(f"连接失败：{s.path()} → {d.path()} input {index}（{e}）；未尝试其他端口") from e
    actual = [c for c in d.inputConnections() if c.inputIndex() == index]
    if len(actual) != 1 or actual[0].inputNode() != s or actual[0].outputIndex() != output:
        raise RuntimeError('connect readback mismatch; transaction must roll back')
    placement = dsh_node_layout._snap_into_flow(d)
    return {"node": d.path(), "input": index, "source": s.path(), "source_output": output,
            'source_output_name': s.outputNames()[output] if output < len(s.outputNames()) else None,
            'input_name': d.inputNames()[index] if index < len(d.inputNames()) else None,
            'type_check': 'cop_material_exact_signature' if material_signature else 'deferred_dynamic_signature' if dynamic_type else 'native' if compatible else 'native_setInput',
            'verified': True, 'semantic_status': 'unverified', "position_adjusted": placement['adjusted'],
            'placement_status':placement['status'],'placement_blockers':placement['blockers'],
            'inputs_before':before, 'inputs_after':_input_state(d),
            'note':'connect replaces the current occupant; do not disconnect first to replace a Merge input'}


def disconnect_input(dst, index: int = 0, *, allow_foreign: str | None = None) -> dict:
    """断开普通网络 ``dst`` 输入；OBJ unparent 改用 ``set_object_parent``。"""
    d = dsh_node_access._resolve(dst)
    if d.type().category() == hou.objNodeTypeCategory():
        raise ValueError(
            "disconnect_input 不执行 OBJ unparent；请用 "
            "set_object_parent(child, None, keep_world=True, reason=...)"
        )
    dsh_ownership.require_owned(d, "disconnect_input", allow_foreign)
    index = int(index)
    if index < 0 or index >= len(d.inputConnectors()):
        raise ValueError(f"输入口 {index} 超出 {d.path()} 的有效范围 0..{len(d.inputConnectors()) - 1}")
    previous = d.input(index)
    before = _input_state(d)
    d.setInput(index, None)
    return {
        "node": d.path(),
        "input": index,
        "disconnected": previous.path() if previous is not None else None,
        'inputs_before':before, 'inputs_after':_input_state(d),
        'next_action':'Use inputs_after: variable inputs may shift after disconnect; old indices are no longer reliable.',
    }


def rename_node(node, name: str, allow_foreign: str | None = None) -> str:
    """重命名节点（自动去重），返回新 path。"""
    n = dsh_node_access._resolve(node)
    dsh_ownership.require_owned(n, "rename_node", allow_foreign)
    n.setName(name, unique_name=True)
    return n.path()


def delete_node(node, allow_foreign: str | None = None) -> dict:
    """删除前检查节点及所有后代权限；持久render_view服务始终受保护。"""
    n = dsh_node_access._resolve(node)
    if n.userData(dsh_service_constants._RENDER_OWNER_KEY) == dsh_service_constants._RENDER_OWNER_VALUE:
        raise ValueError(
            f"{n.path()} belongs to the persistent dsh-houdini render service; "
            "do not delete it during the Houdini session. render_view reuses "
            "this infrastructure and clears its live source reference after each render."
        )
    dsh_ownership.require_owned(n, "delete_node", allow_foreign)
    for child in n.allSubChildren():
        dsh_ownership.require_owned(child, "delete_node descendant", allow_foreign)
    from dsh_network_boxes import prepare_parent_deletion, commit_parent_deletion
    box_deletion = prepare_parent_deletion(
        n, active_owner_session=dsh_ownership.current_session(),
        allow_foreign=allow_foreign, require_node_owned=dsh_ownership.require_owned)
    from dsh_network_notes import prepare_parent_deletion as prepare_note_deletion, commit_parent_deletion as commit_note_deletion
    note_deletion = prepare_note_deletion(
        n, active_owner_session=dsh_ownership.current_session(), allow_foreign=allow_foreign)
    refs = sorted(x.path() for x in n.parmsReferencingThis())
    session_ids = [int(n.sessionId())]
    session_ids.extend(int(child.sessionId()) for child in n.allSubChildren())
    consumers = []
    for connection in n.outputConnections():
        consumer = connection.outputNode()
        if consumer is not None:
            consumers.append((consumer, connection.inputIndex(), connection.outputIndex()))
    path = n.path()
    n.destroy()
    commit_parent_deletion(box_deletion)
    commit_note_deletion(note_deletion)
    for session_id in session_ids:
        dsh_ownership.forget(session_id)
    result: dict = {"deleted": path}
    result['affected_connections'] = [
        {'destination': consumer.path(), 'input': index, 'deleted_source_output': port,
         'inputs_after': _input_state(consumer)} for consumer, index, port in consumers[:64]]
    result['affected_connections_truncated'] = len(consumers) > 64
    result['next_action'] = 'Deletion may reconnect/bypass native wires. A same-named replacement does not restore them; inspect affected_connections and explicitly reconnect, then retest final-output controls.'
    if refs:
        result["orphaned_parm_refs"] = refs
    return result


def set_update_mode(mode: str, expected_mode: str) -> dict:
    """Explicit global auto/manual/on_mouse_up switch; requires current expected_mode.
    Switching to auto may trigger dirty networks. Never an interrupt or automatic recovery.
    """
    from dsh_cook_control import set_update_mode as change
    return change(mode, expected_mode)


def cook_node(node, force: bool = False, timeout_ms: int = 30000) -> dict:
    """Cook and read health; refresh an existing error once to avoid stale diagnostics."""
    return _cook_node(node, force, timeout_ms)


def _cook_node(node, force=False, timeout_ms=30000, *, preflight=True):
    """Internal cook core; only verify_network's already-checked batch skips DFS."""
    n = dsh_node_access._resolve(node)
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 120000:
        raise ValueError('timeout_ms must be 1..120000; cooperative timeout, not an OOM guarantee')
    mode = hou.updateModeSetting()
    if mode == hou.updateMode.Manual:
        return {'path':n.path(), 'ok':False, 'healthy':False, 'warning_free':True,
                'status':'not_cooked_manual', 'errors':[], 'warnings':[], 'forced':False,
                'update_mode':'manual', 'next_action':'Keep Manual for inspection/editing; explicitly authorize a policy change before evaluation. Missing geometry is not an empty successful output.'}
    if preflight:
        from dsh_cook_control import preflight as check_dependencies
        check_dependencies([n])
    effective_force = bool(force) or bool(n.errors())
    cook_error = None
    try:
        with hou.InterruptableOperation('DSH cook', timeout_ms=timeout_ms) as operation:
            operation.updateProgress(0)
            n.cook(force=effective_force)
            operation.updateProgress(1)
    except Exception as e:  # hou.OperationFailed 等
        cook_error = str(e) or type(e).__name__
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
        "forced": effective_force,
        'timeout_ms':timeout_ms, 'interrupt_scope':'cooperative native checkpoints only; cannot guarantee immediate interruption or memory safety',
    }


def sop_set_output(node, render: bool = True,
                   allow_foreign: str | None = None, *, output_index: int | None = None) -> dict:
    """把 SOP display（默认连同 render）旗标移到指定输出节点。

    这是用户 viewport/交付状态，不是 ``render_view`` 的前置条件；agent 的
    离屏验证会从显式 SOP 建 proxy，不依赖这里的旗标。
    output_index=None只切旗标；显式0..63在同一父网络复用/创建并接线原生Output，
    普通geo交付保持None，无需Output节点；subnet/HDA公共交付才指定索引。
    固定容器公共出口，再把旗标设到该Output。逐层发布，不猜祖先输出。
    不cook、不保存定义；用verify_network(parent,output=源SOP,output_index=同索引)
    另验接线和几何。公共出口、显示和HDA新实例验收是不同层。
    """
    n = dsh_node_access._resolve(node)
    dsh_ownership.require_owned(n, "sop_set_output", allow_foreign)
    if n.type().category() != hou.sopNodeTypeCategory():
        raise ValueError(
            f"sop_set_output 只接受 SOP，收到 {n.path()} "
            f"({n.type().category().name()})；OBJ 可见性请用 set_object_visible"
        )
    if not isinstance(render, bool):
        raise ValueError('render must be bool')
    source = n
    published = None
    if output_index is not None:
        published = publish_output(n, output_index, allow_foreign)
        n = dsh_node_access._resolve(published['node'])
    n.setDisplayFlag(True)
    if render:
        n.setRenderFlag(True)
    return {'context': 'sop', 'node': n.path(), 'display': True, 'render': render,
            'source': source.path(), 'public_output': published}


def sop_output_node(parent) -> dict:
    """报告 SOP 网络的 singular display/render 输出节点。"""
    p = dsh_node_access._resolve(parent)
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
                "如需以链尾为输出，用 sop_set_output 把旗标移过去"
            )
    return result


def set_object_visible(node, visible: bool = True,
                       allow_foreign: str | None = None) -> dict:
    """设置单个 OBJ 的 viewport 可见性；OBJ 没有 SOP 式 render flag。"""
    n = dsh_node_access._resolve(node)
    dsh_ownership.require_owned(n, "set_object_visible", allow_foreign)
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
    p = dsh_node_access._resolve(root)
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
            "agent_owned": child.userData(dsh_service_constants._RENDER_OWNER_KEY) == dsh_service_constants._RENDER_OWNER_VALUE,
            "provenance": dsh_ownership.node_provenance(child)["status"],
        })
    return {"context": "obj", "root": p.path(), "objects": objects}


def _output_ports(parent):
    return [n for n in parent.children() if n.type().name() == 'output']


def _output_index(index):
    if type(index) is not int or not 0 <= index <= 63:
        raise ValueError('output_index must be an integer in 0..63, or None for display-only')


def _public_output(parent, source, index):
    _output_index(index)
    ports = [n for n in _output_ports(parent) if n.evalParm('outputidx') == index]
    port = ports[0] if len(ports) == 1 else None
    valid = port is not None and (port == source or any(
        c.inputIndex() == 0 and c.inputNode() == source and c.outputIndex() == 0
        for c in port.inputConnections()))
    return {'ok': valid, 'index': index, 'node': port.path() if port else None,
            'source': source.path(), 'matches': [n.path() for n in ports],
            'reason': None if valid else 'missing_duplicate_or_unwired_public_output',
            'scope': 'direct Output wiring only; not ancestor visibility or fresh-instance behavior'}


def publish_output(source, index, allow_foreign=None):
    """Explicit port authoring, no cooking or automatic ancestor publication."""

    _output_index(index)
    parent = source.parent()
    ports = [n for n in _output_ports(parent) if n.evalParm('outputidx') == index]
    if len(ports) > 1:
        raise ValueError(f'duplicate Output index {index}; inspect and resolve explicitly')
    port = ports[0] if ports else None
    if source.type().name() == 'output':
        if port != source:
            raise ValueError('source is an Output with a different index; edit the port explicitly')
    else:
        if port is not None and port in source.inputAncestors():
            raise ValueError('publishing this source would create an Output dependency cycle')
        # An owned child does not authorize replacing a foreign public interface.
        dsh_ownership.require_owned(parent, 'publish SOP output', allow_foreign)
        if port is not None:
            dsh_ownership.require_owned(port, 'publish SOP output', allow_foreign)
        else:
            port = dsh_node_creation.tab_create(parent, 'output', name=f'output{index}')
            dsh_parameter_values.set_parms(port, {'outputidx': index})
        connect(source, port, allow_foreign=allow_foreign)
    result = _public_output(parent, source, index)
    if not result['ok']:
        raise ValueError('public Output wiring readback failed')
    return result
