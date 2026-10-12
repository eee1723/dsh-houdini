"""Houdini node layout. Executed on the Bridge owning thread."""
from __future__ import annotations

import hou
import dsh_errors
import dsh_node_access
import dsh_ownership


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


def _local_free_position(node, preferred):
    from dsh_network_layout import Rect, find_free_translation
    from dsh_network_boxes import _effective_box_rect,collect_editor_obstacles
    parent=node.parent();size=node.size();width,height=float(size.x()),float(size.y())
    source=Rect(0,0,width,height);current_box=node.parentNetworkBox()
    obstacles=collect_editor_obstacles(parent,excluded_node_ids=[int(node.sessionId())],
        excluded_box_ids=[] if current_box is None else [int(current_box.sessionId())],
        dot_footprint=(width*.5,height))
    container=None if current_box is None else _effective_box_rect(current_box)
    result=find_free_translation(source,obstacles,preferred=preferred,
        step=(max(width*1.5,1e-3),max(height*2.0,1e-3)),
        clearance=(width*.5,height*.75),container=container,max_candidates=512)
    return {'ok':result['ok'],'status':'adjusted' if result['ok'] else 'blocked',
            'position':result.get('translation'),'blockers':result.get('blocked_by') or []}


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
        if siblings:
            x = max(float(c.position().x()) + float(c.size().x()) for c in siblings) + 0.8
            y = max(float(c.position().y()) for c in siblings)
        else:
            x=y=0.0
    placement=_local_free_position(node,(x,y))
    if not placement['ok']:
        raise RuntimeError(f"no bounded collision-free position for {node.path()}: {placement['blockers']}")
    node.setPosition(hou.Vector2(*placement['position']))


def _snap_into_flow(node):
    """connect 纠流：节点违反自顶向下流（不在所有输入下游）时 snap 到输入正下方。

    已在下游（y 严格小于所有输入的 min y）的节点绝不动。返回是否移动了节点。
    """
    inputs = [n for n in node.inputs() if n is not None]
    if not inputs:
        return {'adjusted':False,'status':'unchanged','blockers':[]}
    min_y = min(float(n.position().y()) for n in inputs)
    if float(node.position().y()) < min_y:
        return {'adjusted':False,'status':'unchanged','blockers':[]}
    _h_gap, v_gap = _flow_gaps([node, *inputs])
    x = sum(float(n.position().x()) for n in inputs) / len(inputs)
    from dsh_network_boxes import journal_containing_boxes
    try:
        placement=_local_free_position(node,(x,min_y-v_gap))
    except Exception as error:
        return {'adjusted':False,'status':'blocked',
                'blockers':['obstacle_measurement_failed:'+str(error)]}
    if not placement['ok']:
        return {'adjusted':False,'status':'blocked','blockers':placement['blockers']}
    journal_containing_boxes([node], 'connect_position_before')
    node.setPosition(hou.Vector2(*placement['position']))
    return {'adjusted':True,'status':'adjusted','blockers':[]}


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
                 mode: str = "children", *, boxes=None,
                 profile: str = "comfortable", dry_run: bool = False,
                 expected_plan=None) -> dict:
    """布局全部或显式指定的网络项。

    ``mode='children'``（默认）= 原生 layoutChildren，行为不变；
    ``mode='flow'`` = 自研拓扑分层（``_layout_flow``）：深度 0 最上、
    y = −depth × 垂直间距，同深度按当前 x 排序居中，环上边兜底不断裂。
    ownership 过滤与 ``foreign_nodes_skipped`` 语义两种模式一致。
    ``mode='handoff'`` = 对显式叶子Network Box排布；comfortable保留宽松分层，
    readable让连续主输入链竖直对齐、侧支分列，并把声明的控制/检查区分开。
    ``mode='component'`` = 对显式一层组件容器布局，整体移动其叶子框及节点。
    两者可直接应用；dry_run和expected_plan供需要预览/确认状态的调用使用。
    其他网络项全部作为固定障碍。
    """
    if mode not in ("children", "flow", "handoff", "component"):
        raise ValueError(f"mode 必须是 'children'、'flow'、'handoff' 或 'component'，收到 {mode!r}")
    p = dsh_node_access._resolve(parent)
    if mode in ('handoff','component'):
        if nodes is not None:raise ValueError(f'{mode} mode derives items from boxes; nodes must be None')
        if boxes is None:raise ValueError(f'{mode} mode requires explicit boxes')
        if horizontal_spacing!=-1.0 or vertical_spacing!=-1.0:
            raise ValueError(f'{mode} mode uses profile clearances, not children/flow spacing')
        from dsh_network_boxes import NetworkBoxOperationError,apply_component_layout,apply_handoff_layout
        try:
            operation=apply_handoff_layout if mode=='handoff' else apply_component_layout
            return operation(p,boxes,profile=profile,dry_run=dry_run,
                expected_plan=expected_plan,active_owner_session=dsh_ownership.current_session(),
                node_provenance=dsh_ownership.node_provenance,allow_foreign=allow_foreign,
                require_node_owned=dsh_ownership.require_owned)
        except NetworkBoxOperationError as error:
            raise dsh_errors.CheckpointError(str(error),error.evidence) from error
    if boxes is not None or profile!='comfortable' or dry_run is not False or expected_plan is not None:
        raise ValueError('boxes/profile/dry_run/expected_plan are handoff-only arguments')
    if nodes is None and any(any(isinstance(item, hou.Node) for item in box.items(recurse=True))
                             for box in p.networkBoxes()):
        raise ValueError("layout_nodes broad children/flow would scatter Network Box members; "
                         "use mode='handoff' with explicit leaf boxes, "
                         "or pass an explicit node subset for a local edit")
    items = []
    foreign_skipped = []
    if nodes is not None:
        if not isinstance(nodes, (list, tuple)):
            raise ValueError("nodes 必须是 Node/path 列表或 None（None = 全部子项）")
        for item in nodes:
            n = dsh_node_access._resolve_in_parent(p, item)
            if n.parent() != p:
                raise ValueError(f"节点 {n.path()} 不属于父网络 {p.path()}")
            dsh_ownership.require_owned(n, "layout_nodes", allow_foreign)
            items.append(n)
    elif dsh_ownership.current_session() is not None:
        for child in p.children():
            if dsh_ownership.node_provenance(child)["status"] == "owned_current_session":
                items.append(child)
            else:
                foreign_skipped.append(child.path())
    else:
        items = list(p.children())
    if items:
        from dsh_network_boxes import journal_containing_boxes
        journal_containing_boxes(items, 'layout_nodes_before')
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


def network_boxes(parent, groups, *, remove=None, dry_run=False,
                  expected_plan=None, allow_foreign=None) -> dict:
    """Create/update/remove Network Boxes without moving or cooking nodes.

    groups=[{name, members?: [Node|absolute|parent-relative path], boxes?: [name],
    label?: string, role?: string, color?: [r,g,b]}]. members and boxes may coexist;
    child boxes may be existing or declared anywhere in this batch. Cycles fail
    before creation. role is a color hint, never a component/leaf restriction.
    Labels default to names; unknown roles use neutral colors. dry_run previews
    without writes; expected_plan optionally requires that preview to remain
    current. By default the call directly applies. Membership and appearance
    are presentation facts, not geometry or task-quality evidence.
    """
    try:
        p = dsh_node_access._resolve(parent)
    except (ValueError, TypeError) as error:
        raise dsh_errors.CheckpointError(str(error), {
            'ok':False,'dry_run':bool(dry_run) if type(dry_run) is bool else None,
            'applied':False,'phase':'preflight','scene_writes':0,
            'parent':str(parent),'restored':True,'restore_errors':[],
            'layout_status':'not_performed','scope':'Network Box parent resolution; zero scene writes'}) from error
    from dsh_network_boxes import NetworkBoxOperationError, apply_network_boxes
    try:
        return apply_network_boxes(
            p, groups, remove=remove, dry_run=dry_run,
            expected_plan=expected_plan, allow_foreign=allow_foreign,
            active_owner_session=dsh_ownership.current_session(),
            active_owner_call=dsh_ownership.current_call(),
            resolve_node=lambda value: dsh_node_access._resolve_in_parent(p, value), require_node_owned=dsh_ownership.require_owned)
    except NetworkBoxOperationError as error:
        raise dsh_errors.CheckpointError(str(error), error.evidence) from error


def network_notes(parent, notes=None, *, remove=None, allow_foreign=None) -> dict:
    """Read or locally maintain named Sticky Notes without changing nodes.

    With no notes/remove, return actual text/position/size/color/provenance.
    notes=[{name,text,position?:[x,y],size?:[w,h],color?:[r,g,b]}] upserts only
    explicit notes. New notes default beside existing network content. remove
    names are explicit; a name or owned parent never grants note ownership.
    Notes remain standalone fixed layout obstacles, not implicit Box members.
    """
    from dsh_network_notes import apply_network_notes
    return apply_network_notes(dsh_node_access._resolve(parent), notes, remove=remove,
        active_owner_session=dsh_ownership.current_session(), active_owner_call=dsh_ownership.current_call(),
        allow_foreign=allow_foreign)


def network_controls(parent, controls=None, *, remove=None,
                     allow_foreign: str | None = None) -> dict:
    """Declare or list the actual user control entry nodes in a network.

    controls=[{'node':'CTRL_ENGINEERING','label':'Engineering controls'}] explicitly
    marks explicit nodes inside parent with a label saved in their HIP userData.
    remove is an explicit node/path list. Neither names nor spare parms imply a role.
    Omit controls/remove to list declared entries recursively without cooking.
    Declarations only aid navigation; they prove no bindings or model correctness.
    present_nodes publishes these entries as clickable node delivery cards.
    """
    from dsh_network_navigation import declare_controls, list_controls
    p = dsh_node_access._resolve(parent)
    if controls is None and remove is None:
        return {'parent': p.path(), 'controls': list_controls(p), 'scene_writes': 0}
    return declare_controls(p, controls if controls is not None else [],
                            remove if remove is not None else [],
                            require_owned=dsh_ownership.require_owned, allow_foreign=allow_foreign)


def present_nodes(nodes, *, allow_foreign: str | None = None) -> dict:
    """Declare clickable node entries for delivery alongside DSH's file cards.

    nodes=[{'node':'/obj/asset/CTRL','label':'Engineering controls','role':'control',
            'description':'Adjust dimensions and repetition'},
           {'node':'/obj/asset/OUT','label':'Model output','role':'output'}].
    Saves a persistent reference ID on explicit nodes when absent; ownership applies.
    Save the named HIP after first declaration so cards survive reopening it.
    role is navigation intent, never control/geometry certification. new_identity=True
    is for explicitly renewing a copied entry and invalidates its previous ID.
    The successful verb receipt publishes cards independently of __result__ wrapping.
    Failed batches do not publish cards; the returned value remains inspectable.
    """
    from dsh_network_navigation import present_nodes as present
    return present(nodes, require_owned=dsh_ownership.require_owned, allow_foreign=allow_foreign)


def focus_node(reference, *, expected_hip: str) -> dict:
    """Explicit UI navigation by a delivered persistent ID in the expected HIP.

    Used by node delivery clicks through the main-thread queue. Expands containing
    boxes, locates the actual node and opens parameters; no geometry/parameter
    edits or HIP load/save. Renames and same-HIP reopen keep the entry valid;
    missing or duplicated IDs and a different HIP are reported without guessing.
    """
    from dsh_network_navigation import focus_reference
    return focus_reference(reference, expected_hip=expected_hip)
