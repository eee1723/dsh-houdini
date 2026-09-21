"""H21/H22 HOM regression: 人性化落位（O1）。

覆盖 tab_create 智能落位（有/无 inputs）、connect 纠流（违反流才 snap、
已在下游绝不动）、layout_nodes flow 拓扑分层（深度分行、阅读顺序、居中、
ownership 过滤、非法 mode 拒绝）与默认 children 模式不回归。

Run with Houdini's hython. 直接 ``hou`` 调用只模拟用户手摆位置；
bridge 执行一律走动词。
"""

from __future__ import annotations

from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

import hou
import dsh_bridge
import dsh_network_boxes as network_boxes_module


suffix = uuid.uuid4().hex[:8]
session = f"layout-flow-{suffix}"
parent_path = None
extra_parents = []


def run(code):
    result = dsh_bridge.run_code(code, owner_session=session, owner_call="call-layout")
    assert result["ok"] is True, result
    return result["result"]


def pos(path):
    p = hou.node(path).position()
    return float(p.x()), float(p.y())


try:
    parent_path = run(
        f"p = tab_create('/obj', 'geo', name='__dsh_layout_{suffix}')\n"
        "__result__ = p.path()"
    )
    child = lambda name: f"{parent_path}/{name}"

    # 1) 无 inputs：首个节点落原点，第二个放右侧新列（同排、不堆叠）
    run(f"__result__ = tab_create({parent_path!r}, 'null', name='a').path()")
    run(f"__result__ = tab_create({parent_path!r}, 'null', name='b').path()")
    ax, ay = pos(child("a"))
    bx, by = pos(child("b"))
    assert (ax, ay) == (0.0, 0.0), (ax, ay)
    a_width = float(hou.node(child("a")).size().x())
    assert bx > ax + a_width, (ax, bx, a_width)
    assert by == ay, (ay, by)

    # 2) 有 inputs：merge 落到输入下游、x 为输入均值
    run(
        f"__result__ = tab_create({parent_path!r}, 'merge', name='m', "
        f"inputs=[{child('a')!r}, {child('b')!r}]).path()"
    )
    mx, my = pos(child("m"))
    assert my < min(ay, by), (my, ay, by)
    assert abs(mx - (ax + bx) / 2.0) < 1e-6, (mx, ax, bx)

    # 新节点的首选右侧列被Sticky Note占用时必须避让，且不能移动注释。
    note = hou.node(parent_path).createStickyNote("placement_obstacle")
    note_x = max(float(n.position().x()) + float(n.size().x()) for n in hou.node(parent_path).children()) + 0.8
    note.setPosition(hou.Vector2(note_x, 0.0)); note.setSize(hou.Vector2(3.0, 1.5))
    note_before = (tuple(note.position()), tuple(note.size()))

    # 3) connect 纠流：c 与 a 同排（违反自顶向下流），连 a→c 后放到 a 下游。
    #    首选位置若会碰到已有 m，则允许横向避让，但必须报告并保持无重叠。
    run(f"__result__ = tab_create({parent_path!r}, 'null', name='c').path()")
    cx, cy = pos(child("c"))
    c_size = hou.node(child("c")).size()
    assert cx + float(c_size.x()) <= note_x or cx >= note_x + 3.0 or cy + float(c_size.y()) <= 0.0 or cy >= 1.5
    assert note_before == (tuple(note.position()), tuple(note.size()))
    # 模拟用户随后把目标拖回输入同排，以单独覆盖connect纠流。
    hou.node(child("c")).setPosition(hou.Vector2(cx, ay)); cx, cy = pos(child("c"))
    assert cy >= ay, (cy, ay)
    result = run(f"__result__ = connect({child('a')!r}, {child('c')!r})")
    assert result["position_adjusted"] is True, result
    assert result["placement_status"] == "adjusted", result
    assert result["placement_blockers"] == [], result
    cx2, cy2 = pos(child("c"))
    assert cy2 < ay, (cy2, ay)
    m_size = hou.node(child("m")).size()
    separated = (
        cx2 + float(c_size.x()) <= mx
        or mx + float(m_size.x()) <= cx2
        or cy2 + float(c_size.y()) <= my
        or my + float(m_size.y()) <= cy2
    )
    assert separated, ((cx2, cy2), (mx, my))

    # 4) connect 绝不动已在下游的节点
    run(
        f"__result__ = tab_create({parent_path!r}, 'merge', name='d', "
        f"inputs=[{child('m')!r}]).path()"
    )
    dx, dy = pos(child("d"))
    assert dy < my, (dy, my)
    result = run(f"__result__ = connect({child('b')!r}, {child('d')!r}, index=1)")
    assert result["position_adjusted"] is False, result
    assert pos(child("d")) == (dx, dy), (pos(child("d")), (dx, dy))

    # 5) layout_nodes flow：打乱位置后按拓扑深度分层，同深度按打乱前 x 保持
    #    阅读顺序并整体居中（a/b 深度 0，c/m 深度 1，d 深度 2）
    hou.node(child("a")).setPosition(hou.Vector2(10.0, -3.0))
    hou.node(child("b")).setPosition(hou.Vector2(-10.0, -7.0))
    hou.node(child("c")).setPosition(hou.Vector2(5.0, -1.0))
    hou.node(child("m")).setPosition(hou.Vector2(-5.0, -9.0))
    hou.node(child("d")).setPosition(hou.Vector2(0.0, -20.0))
    result = run(f"__result__ = layout_nodes({parent_path!r}, mode='flow')")
    assert result["mode"] == "flow", result
    flow = {n["path"].split("/")[-1]: n["position"] for n in result["nodes"]}
    assert flow["a"][1] == 0.0 and flow["b"][1] == 0.0, flow
    assert flow["b"][0] < 0.0 < flow["a"][0], flow  # b 在左、a 在右（打乱前 x 序）
    assert abs(flow["a"][0] + flow["b"][0]) < 1e-6, flow  # 行整体居中
    assert flow["m"][1] == flow["c"][1] < 0.0, flow
    assert flow["m"][0] < 0.0 < flow["c"][0], flow
    assert flow["d"][1] < flow["m"][1], flow
    assert abs(flow["d"][0]) < 1e-6, flow

    # 6) ownership：foreign 节点不进 flow 布局、位置不动
    foreign = hou.node(parent_path).createNode("null", "foreign")
    foreign.setPosition(hou.Vector2(99.0, 99.0))
    result = run(f"__result__ = layout_nodes({parent_path!r}, mode='flow')")
    assert child("foreign") in result["foreign_nodes_skipped"], result
    assert pos(child("foreign")) == (99.0, 99.0), pos(child("foreign"))

    # 7) 默认 children 模式不回归；非法 mode 明确拒绝
    result = run(f"__result__ = layout_nodes({parent_path!r})")
    assert result["mode"] == "children", result
    bad = dsh_bridge.run_code(
        f"__result__ = layout_nodes({parent_path!r}, mode='bogus')",
        owner_session=session,
        owner_call="call-layout-bad-mode",
    )
    assert bad["ok"] is False and "mode" in str(bad.get("error")), bad

    # 8) connect在受治理Box内搜索：首选被挡时继续找合法contained候选。
    contained_parent = run(f"p=tab_create('/obj','geo',name='__dsh_contained_{suffix}')\n__result__=p.path()")
    extra_parents.append(contained_parent)
    source = run(f"__result__=tab_create({contained_parent!r},'null',name='source').path()")
    destination = run(f"__result__=tab_create({contained_parent!r},'null',name='destination').path()")
    blocker = run(f"__result__=tab_create({contained_parent!r},'null',name='blocker').path()")
    source_node,destination_node,blocker_node=map(hou.node,(source,destination,blocker))
    source_node.setPosition(hou.Vector2(0,0));destination_node.setPosition(hou.Vector2(3,0));blocker_node.setPosition(hou.Vector2(0,-.7))
    group=[{'name':'contained','label':'Contained placement','role':'assembly','members':[source,destination,blocker]}]
    plan=run(f"__result__=network_boxes({contained_parent!r},{group!r},dry_run=True)")
    run(f"__result__=network_boxes({contained_parent!r},{group!r},expected_plan={plan['plan_sha256']!r})")
    governed=hou.node(contained_parent).findNetworkBox('contained');governed.setBounds(hou.BoundingRect(-4,-4,6,2))
    fixed_before=(tuple(source_node.position()),tuple(blocker_node.position()),tuple(governed.position()),tuple(governed.size()))
    adjusted=run(f"__result__=connect({source!r},{destination!r})")
    assert adjusted['placement_status']=='adjusted' and adjusted['position_adjusted'] is True,adjusted
    assert fixed_before==(tuple(source_node.position()),tuple(blocker_node.position()),tuple(governed.position()),tuple(governed.size()))

    # 9) Box内没有合法位置：wire保留、destination/Box和其他节点都不动。
    blocked_parent = run(f"p=tab_create('/obj','geo',name='__dsh_connect_blocked_{suffix}')\n__result__=p.path()")
    extra_parents.append(blocked_parent)
    blocked_source=run(f"__result__=tab_create({blocked_parent!r},'null',name='source').path()")
    blocked_destination=run(f"__result__=tab_create({blocked_parent!r},'null',name='destination').path()")
    bs,bd=hou.node(blocked_source),hou.node(blocked_destination);bs.setPosition(hou.Vector2(0,0));bd.setPosition(hou.Vector2(0,0))
    blocked_group=[{'name':'tight','label':'Tight box','role':'assembly','members':[blocked_source,blocked_destination]}]
    plan=run(f"__result__=network_boxes({blocked_parent!r},{blocked_group!r},dry_run=True)")
    run(f"__result__=network_boxes({blocked_parent!r},{blocked_group!r},expected_plan={plan['plan_sha256']!r})")
    tight=hou.node(blocked_parent).findNetworkBox('tight');size=bd.size();tight.setBounds(hou.BoundingRect(0,0,float(size.x()),float(size.y())))
    blocked_before=(tuple(bs.position()),tuple(bd.position()),tuple(tight.position()),tuple(tight.size()))
    blocked_result=run(f"__result__=connect({blocked_source!r},{blocked_destination!r})")
    assert blocked_result['placement_status']=='blocked' and blocked_result['position_adjusted'] is False,blocked_result
    assert bd.input(0)==bs and blocked_before==(tuple(bs.position()),tuple(bd.position()),tuple(tight.position()),tuple(tight.size()))

    # 10) tab_create完全被挡时原子清理；Obstacle量测失败也必须fail closed。
    creation_parent = run(f"p=tab_create('/obj','geo',name='__dsh_create_blocked_{suffix}')\n__result__=p.path()")
    extra_parents.append(creation_parent)
    huge=hou.node(creation_parent).createNetworkBox('huge_obstacle');huge.setBounds(hou.BoundingRect(-1000,-1000,1000,1000))
    creation_failed=dsh_bridge.run_code(f"tab_create({creation_parent!r},'null',name='must_not_remain')",owner_session=session,owner_call='blocked-create')
    assert not creation_failed['ok'] and hou.node(creation_parent+'/must_not_remain') is None,creation_failed
    huge.destroy()
    bad_note=hou.node(creation_parent).createStickyNote('bad_measurement');bad_note.setSize(hou.Vector2(2,1))
    measured_source=run(f"__result__=tab_create({creation_parent!r},'null',name='measured_source').path()")
    measured_destination=run(f"__result__=tab_create({creation_parent!r},'null',name='measured_destination').path()")
    hou.node(measured_source).setPosition(hou.Vector2(0,0));hou.node(measured_destination).setPosition(hou.Vector2(2,0))
    original_measure=network_boxes_module._presentation_item_rect
    def reject_note(item,label,dot_footprint):
        if label=='note':raise RuntimeError('injected note measurement failure')
        return original_measure(item,label,dot_footprint)
    network_boxes_module._presentation_item_rect=reject_note
    try:
        connect_measurement=dsh_bridge.run_code(f"__result__=connect({measured_source!r},{measured_destination!r})",owner_session=session,owner_call='connect-measurement-failure')
        measurement_failed=dsh_bridge.run_code(f"tab_create({creation_parent!r},'null',name='unmeasured')",owner_session=session,owner_call='measurement-failure')
    finally:
        network_boxes_module._presentation_item_rect=original_measure
    assert connect_measurement['ok'] and connect_measurement['result']['placement_status']=='blocked',connect_measurement
    assert hou.node(measured_destination).input(0)==hou.node(measured_source)
    assert not measurement_failed['ok'] and hou.node(creation_parent+'/unmeasured') is None,measurement_failed

    print("layout-flow regression: ok")
finally:
    for candidate in [parent_path,*extra_parents]:
        node = hou.node(candidate) if candidate is not None else None
        if node is not None:
            node.destroy()
