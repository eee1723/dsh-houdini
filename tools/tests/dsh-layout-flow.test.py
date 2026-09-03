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


suffix = uuid.uuid4().hex[:8]
session = f"layout-flow-{suffix}"
parent_path = None


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

    # 3) connect 纠流：c 与 a 同排（违反自顶向下流），连 a→c 后 snap 到 a 正下方
    run(f"__result__ = tab_create({parent_path!r}, 'null', name='c').path()")
    cx, cy = pos(child("c"))
    assert cy >= ay, (cy, ay)
    result = run(f"__result__ = connect({child('a')!r}, {child('c')!r})")
    assert result["position_adjusted"] is True, result
    cx2, cy2 = pos(child("c"))
    assert cy2 < ay, (cy2, ay)
    assert abs(cx2 - ax) < 1e-6, (cx2, ax)

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

    print("layout-flow regression: ok")
finally:
    if parent_path is not None:
        node = hou.node(parent_path)
        if node is not None:
            node.destroy()
