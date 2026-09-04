"""H21/H22 HOM regression: KineFX 机械 FK + rigid deliverable recipe。

锁定官方现行栈的 agent 可驱动路径（rig-animation-design.md §11 实测基线）：

- skeleton：Python SOP 点 + polyline（name + 16-float rest_transform 属性）；
- rigdoctor `inittransforms=1` 初始化 transform/localtransform；
- `kinefx::rigpose` 的 transformations multiparm 用 `@name=<joint>` 组语法寻址
  （裸 joint 名会命中空组并 warning），r{N}x/y/z 可由 set_keyframes 打关键帧；
- `kinefx::capturepackedgeo` 按 `name` 做 100% rigid capture；
- `kinefx::jointdeform` 消费 capture/animated pose，最终 link 几何真实运动；
- skeleton 总 bbox 会随 FK 变化，但不能冒充 driven geometry oracle；
- resolve_latest_type 的 namespace 解析：'rigdoctor' → 'kinefx::rigdoctor'；
  H22 裸名 'rigpose' 会命中 apex::rigpose（接口不同），跨版本 recipe 必须钉
  `kinefx::` 命名空间。

Run with Houdini's hython.
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
session = f"kinefx-fk-{suffix}"
geo_path = None
rp_path = None


def run(code):
    result = dsh_bridge.run_code(code, owner_session=session, owner_call="call-kinefx-fk")
    assert result["ok"] is True, result
    return result["result"]


def bbox_center_at(node_path, frame):
    run(f"__result__ = set_timeline(current_frame={frame})")
    run(f"__result__ = cook_node({node_path!r}, force=True)")
    return run(f"""geo = hou.node({node_path!r}).geometry()
bb = geo.boundingBox()
c = (bb.minvec() + bb.maxvec()) / 2
__result__ = [round(float(v), 3) for v in c]""")


def bbox_extent_at(node_path, frame):
    run(f"__result__ = set_timeline(current_frame={frame})")
    run(f"__result__ = cook_node({node_path!r}, force=True)")
    return run(f"""geo = hou.node({node_path!r}).geometry()
size = geo.boundingBox().sizevec()
__result__ = [round(float(v), 3) for v in size]""")


SKELETON_PY = """node = hou.pwd()
geo = node.geometry()
geo.addAttrib(hou.attribType.Point, 'name', '')
ident = (1.0,0,0,0, 0,1.0,0,0, 0,0,1.0,0, 0,0,0,1.0)
geo.addAttrib(hou.attribType.Point, 'rest_transform', ident)
for i, n in enumerate(['root', 'mid', 'tip']):
    p = geo.createPoint()
    p.setPosition(hou.Vector3(0, i, 0))
    p.setAttribValue('name', n)
    m = list(ident); m[13] = float(i)
    p.setAttribValue('rest_transform', tuple(m))
poly = geo.createPolygon(is_closed=False)
for p in geo.iterPoints():
    poly.addVertex(p)
"""

try:
    # 0) namespace 解析：kinefx 类型可经裸名解析，显式命名空间原样保留
    resolved = run(
        "__result__ = {'rd': resolve_latest_type('sop', 'rigdoctor'), "
        "'pinned': resolve_latest_type('sop', 'kinefx::rigpose')}"
    )
    assert resolved["rd"] == "kinefx::rigdoctor", resolved
    assert resolved["pinned"] == "kinefx::rigpose", resolved

    # 1) 骨架 + transform 初始化 + rigpose（钉 kinefx:: 命名空间）
    geo_path = run(
        "g = tab_create('/obj', 'geo', name='__dsh_kinefx_fk_" + suffix + "')\n"
        "py = tab_create(g, 'python', name='skel')\n"
        f"set_parm(py, 'python', {SKELETON_PY!r})\n"
        "rd = tab_create(g, 'rigdoctor', name='init_tf', inputs=[py])\n"
        "set_parm(rd, 'inittransforms', 1)\n"
        "rp = tab_create(g, 'kinefx::rigpose', name='pose', inputs=[rd])\n"
        "__result__ = g.path()"
    )
    rp_path = geo_path + "/pose"

    # 2) multiparm 插入（无动词的低层缺口，单独裸调用）+ 组寻址 + set_keyframes
    run(f"hou.node({rp_path!r}).parm('transformations').insertMultiParmInstance(0)\n__result__ = True")
    run(f"set_parm({rp_path!r}, 'group0', '@name=mid')\n__result__ = True")
    run(
        f"__result__ = set_keyframes({rp_path!r}, "
        "{'r0z': [{'frame': 1, 'value': 0.0, 'curve': 'linear'}, "
        "{'frame': 24, 'value': 90.0, 'curve': 'linear'}, "
        "{'frame': 48, 'value': 0.0, 'curve': 'linear'}]})"
    )

    # 3) FK：mid 关节 local rotation 在 frame 24 为绕 z 90°
    def mid_row0(frame):
        run(f"__result__ = set_timeline(current_frame={frame})")
        run(f"__result__ = cook_node({rp_path!r}, force=True)")
        return run(f"""rp = hou.node({rp_path!r})
p = [x for x in rp.geometry().points() if x.attribValue('name') == 'mid'][0]
t = p.attribValue('transform')
__result__ = [round(t[i], 3) for i in range(3)]""")

    assert mid_row0(1) == [1.0, 0.0, 0.0]
    row = mid_row0(24)
    assert abs(row[0]) < 1e-3 and abs(row[1] - 1.0) < 1e-3, row
    assert run(f"__result__ = hou.node({rp_path!r}).parm('r0z').isTimeDependent()") is True

    # 4) 负对照：driver skeleton 的总 bbox 本身就会变化，不能作为 link oracle。
    skel_c1 = bbox_center_at(rp_path, 1)
    skel_c24 = bbox_center_at(rp_path, 24)
    assert sum(abs(a - b) for a, b in zip(skel_c1, skel_c24)) > 0.5

    # 5) rigid capture + deform：只在最终 driven geometry 上验 link。
    deform_path = run(
        f"bx = tab_create({geo_path!r}, 'box', name='link_tip')\n"
        "set_parms(bx, {'sizex': 0.2, 'sizey': 1.0, 'sizez': 0.3, 'ty': 2.5})\n"
        f"nm = tab_create({geo_path!r}, 'name', name='name_tip', inputs=[bx])\n"
        "set_parm(nm, 'name1', 'tip')\n"
        f"cap = tab_create({geo_path!r}, 'kinefx::capturepackedgeo', name='capture_link', inputs=[nm, {geo_path + '/init_tf'!r}])\n"
        "set_parms(cap, {'packinput': 1, 'useconnectivity': 0, 'nameattribute': 'name', "
        "'capturebyname': 1, 'skinattr': 'name', 'skelattr': 'name'})\n"
        f"deform = tab_create({geo_path!r}, 'kinefx::jointdeform', name='deform_link', inputs=[cap, {geo_path + '/init_tf'!r}, {rp_path!r}])\n"
        "__result__ = deform.path()"
    )

    captured = run(f"""g = hou.node({geo_path + '/capture_link'!r}).geometry()
__result__ = {{
    'point_attribs': sorted(a.name() for a in g.pointAttribs()),
    'prim_types': sorted(set(str(p.type()).split('.')[-1] for p in g.prims())),
}}""")
    assert "boneCapture" in captured["point_attribs"], captured

    health = run(
        f"__result__ = {{'capture': cook_node({geo_path + '/capture_link'!r}, force=True), "
        f"'deform': cook_node({deform_path!r}, force=True)}}"
    )
    assert health["capture"]["healthy"] is True, health
    assert health["deform"]["healthy"] is True, health

    delivered = run(f"""g = hou.node({deform_path!r}).geometry()
__result__ = {{
    'points': len(g.points()), 'prims': len(g.prims()),
    'point_attribs': sorted(a.name() for a in g.pointAttribs()),
    'prim_types': sorted(set(str(p.type()).split('.')[-1] for p in g.prims())),
}}""")
    assert delivered["points"] == 1 and delivered["prims"] == 1, delivered
    assert "Polygon" not in delivered["prim_types"], delivered

    c1 = bbox_center_at(deform_path, 1)
    c24 = bbox_center_at(deform_path, 24)
    c48 = bbox_center_at(deform_path, 48)
    moved = sum(abs(a - b) for a, b in zip(c1, c24))
    assert moved > 0.5, (c1, c24, moved)
    assert c1 == [0.0, 2.5, 0.0], c1
    assert c24 == [-1.5, 1.0, 0.0], c24
    assert c48 == c1, (c1, c48)

    e1 = bbox_extent_at(deform_path, 1)
    e24 = bbox_extent_at(deform_path, 24)
    assert e1 == [0.2, 1.0, 0.3], e1
    assert e24 == [1.0, 0.2, 0.3], e24

    print("kinefx-fk regression: ok")
finally:
    if geo_path is not None:
        node = hou.node(geo_path)
        if node is not None:
            node.destroy()
