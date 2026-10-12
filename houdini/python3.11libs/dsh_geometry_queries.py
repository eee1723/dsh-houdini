"""Houdini geometry queries. Executed on the Bridge owning thread."""
from __future__ import annotations

import difflib
import hashlib
import math
import struct
import time
import hou
import dsh_cook_control as _cook_control
import dsh_node_access


def geo_attrib_stats(node, name: str, attrib_class: str = "point", *, unique: bool = False,
                     max_elements: int = 100000) -> dict:
    """属性**值**统计：min/max/mean/count（`describe` 只给属性名清单，不给值）。

    用于验证驱动数据（@Cd/@curveu/@pscale…）是否符合预期，不用手写逐点循环。
    attrib_class: "point" / "prim" / "vertex" / "detail"。数值属性支持多分量
    （vector 按分量给 min/max/mean）。unique=True全量检查属性完整tuple的精确唯一性，
    返回unique_count/duplicate_count/all_unique和重复样本，支持int/float/string。
    用P检查精确重叠模板点，用id检查身份；不是容差焊接或几何碰撞判断。
    超max_elements或非有限值拒绝，不抽样后宣称唯一；不自动删除重复。
    """
    n = dsh_node_access._resolve(node)
    _cook_control.require_evaluation('geo_attrib_stats')
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
    if not isinstance(unique, bool) or type(max_elements) is not int or not 1 <= max_elements <= 1000000:
        raise ValueError('unique must be bool; max_elements integer in 1..1000000')
    uniqueness = {}
    if unique:
        from dsh_geometry_observation import attribute_uniqueness
        uniqueness = attribute_uniqueness(g, attrib, attrib_class, max_elements)
    if data_type == hou.attribData.String and not unique:
        raise ValueError(f"属性 '{name}' 是字符串属性，geo_attrib_stats 只统计数值属性")
    if data_type == hou.attribData.String:
        return {'node': n.path(), 'attrib': name, 'class': attrib_class,
                'data_type': 'string', 'size': size, **uniqueness}
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
        **uniqueness,
    }


def _summary(values: list) -> dict:
    if not values:
        return {"min": None, "max": None, "mean": None}
    return {
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
    }


def geo_piece_stats(node, piece_attrib: str | None = None,
                    sample: int = 16, *, inspect: bool = False, group=None, basis=None,
                    integrity_only: bool = False) -> dict:
    """按 primitive piece 报局部 bbox/面积，识别整体 bbox 掩盖的局部退化。

    ``piece_attrib=None`` 时用原生 Connectivity SOP Verb 在内存副本上生成临时
    primitive ``__dsh_piece``，不向用户网络加节点。也可传已有 primitive int/string
    piece 属性。返回全部 piece 的摘要和有限样本，避免 9000 个实例爆 token。
    inspect=True改为有界Polygon观测：group为精确primitive组，basis为3个正交单位轴；
    integrity_only=True统计最终Polygon表面完整性及闭合连通壳的有向体积符号，
    扩大有界预算并跳过昂贵的截面/中心线诊断；负号只提示检查单独部件是否整壳反向，
    嵌套空腔可有意出现反向内壳，不自动判错；还对比显式N属性与几何面朝向，
    反向着色法线只提示复核，不自动改写几何；
    boundary_edges单独提示核对有意开放接口，不一概当破面。
    平面大面若以重复点桥接孔，另报shading_review_status供视窗近景复核；
    这不是拓扑失败，也不证明已有可见着色瑕疵。
    planar_face_crossings只查单个近似平面闭合Polygon内非相邻边的严格内部交叉；
    每面最多256顶点、总计250000对边，须看coverage/skipped_faces；不查非平面面、
    端点接触、共线重合或跨面自交，合法洞桥不因重复边判错。已有风险只作非阻断复核。
    返回边界/非流形/边连通/零面积、surface_area与局部extent；center_axis_surface_hits
    量测三条basis轴向包围盒中心线与表面的交点（实心封口通常为2，通孔轴可为0，但须结合
    闭合/流形与轴向图像）；duplicate_boundary_faces及
    closed_planar_components是重合边界/闭合共面壳风险，不是任意重叠检测。observed不是形态pass。
    曲线/native/packed及超预算保持unverified；group/basis不能用于默认piece统计。
    """
    n = dsh_node_access._resolve(node)
    if n.type().category() != hou.sopNodeTypeCategory():
        raise ValueError("geo_piece_stats 只接受 SOP 节点")
    if not isinstance(sample, int) or sample <= 0 or sample > 256:
        raise ValueError("sample 必须是 1..256 的整数")
    _cook_control.require_evaluation('geo_piece_stats')
    source = n.geometry()
    if source is None:
        raise ValueError(f"节点 {n.path()} 没有 geometry")
    if not isinstance(inspect, bool): raise ValueError('inspect must be boolean')
    if type(integrity_only) is not bool: raise ValueError('integrity_only must be boolean')
    if integrity_only and not inspect:
        raise ValueError('integrity_only requires inspect=True')
    if inspect:
        from dsh_geometry_observation import polygon_observation
        return {'node': n.path(), 'frame': float(hou.frame()), 'checked_at': time.time(),
                **polygon_observation(source, group, basis, integrity_only=integrity_only)}
    if group is not None or basis is not None:
        raise ValueError('group/basis require inspect=True (selected polygon observation)')
    geometry = source
    generated = False
    attrib_name = piece_attrib
    attrib_class = "prim"
    if attrib_name is None:
        generated = True
        attrib_name = "__dsh_piece"
        verb = hou.sopNodeTypeCategory().nodeVerb("connectivity")
        if verb is None:
            raise RuntimeError("当前 Houdini 没有 Connectivity SOP Verb")
        verb.setParms({"attribname": attrib_name, "attribtype": 0, "connecttype": 0})
        geometry = hou.Geometry()
        verb.execute(geometry, [source])
        attrib_class = "point"
    else:
        attrib = geometry.findPrimAttrib(attrib_name)
        if attrib is None:
            attrib = geometry.findPointAttrib(attrib_name)
            attrib_class = "point"
        if attrib is None:
            raise ValueError(
                f"节点 {n.path()} 没有 primitive/point piece 属性 {attrib_name!r}；"
                "省略 piece_attrib 可按连接性自动生成"
            )
        if attrib.size() != 1:
            raise ValueError("piece_attrib 必须是单分量 primitive 属性")

    pieces = {}
    for prim in geometry.iterPrims():
        try:
            if attrib_class == "prim":
                piece_id = prim.attribValue(attrib_name)
            else:
                points = prim.points()
                if not points:
                    continue
                piece_id = points[0].attribValue(attrib_name)
        except Exception as error:
            raise ValueError(f"无法读取 {attrib_class} 属性 {attrib_name!r}: {error}") from error
        key = str(piece_id)
        record = pieces.get(key)
        if record is None:
            record = {
                "id": piece_id,
                "prims": 0,
                "vertices": 0,
                "surface_prims": 0,
                "area": 0.0,
                "min": [math.inf, math.inf, math.inf],
                "max": [-math.inf, -math.inf, -math.inf],
            }
            pieces[key] = record
        record["prims"] += 1
        points = prim.points()
        record["vertices"] += len(points)
        try:
            closed = bool(prim.intrinsicValue("closed"))
        except Exception:
            closed = False
        if closed and len(points) >= 3:
            try:
                area = float(prim.intrinsicValue("measuredarea"))
                record["area"] += max(0.0, area)
                record["surface_prims"] += 1
            except Exception:
                pass
        for point in points:
            position = point.position()
            for axis in range(3):
                value = float(position[axis])
                record["min"][axis] = min(record["min"][axis], value)
                record["max"][axis] = max(record["max"][axis], value)

    records = []
    for record in pieces.values():
        extents = [record["max"][i] - record["min"][i] for i in range(3)]
        records.append({
            "id": dsh_node_access._val(record["id"]),
            "prims": record["prims"],
            "vertices": record["vertices"],
            "surface_prims": record["surface_prims"],
            "area": record["area"],
            "bbox_min": record["min"],
            "bbox_max": record["max"],
            "extents": extents,
            "min_extent": min(extents),
            "max_extent": max(extents),
        })
    records.sort(key=lambda item: (
        0, float(item["id"])
    ) if isinstance(item["id"], (int, float)) else (1, str(item["id"])))
    source_bbox = source.boundingBox()
    source_scale = max(float(v) for v in source_bbox.sizevec()) if records else 1.0
    area_epsilon = max(source_scale * source_scale * 1e-12, 1e-16)
    degenerate = sum(
        1 for item in records
        if item["surface_prims"] > 0 and item["area"] <= area_epsilon
    )
    if len(records) <= sample:
        sampled = records
    elif sample == 1:
        sampled = [records[0]]
    else:
        indices = sorted({
            round(i * (len(records) - 1) / (sample - 1)) for i in range(sample)
        })
        sampled = [records[i] for i in indices]
    axis_extents = [[item["extents"][axis] for item in records] for axis in range(3)]
    return {
        "node": n.path(),
        "piece_attrib": attrib_name,
        "piece_attrib_class": attrib_class,
        "piece_attrib_generated": generated,
        "piece_count": len(records),
        "degenerate_surface_pieces": degenerate,
        "area_epsilon": area_epsilon,
        "area": _summary([item["area"] for item in records]),
        "extent_x": _summary(axis_extents[0]),
        "extent_y": _summary(axis_extents[1]),
        "extent_z": _summary(axis_extents[2]),
        "sampled_pieces": sampled,
    }


def geo_frame_diff(node, frame_a, frame_b, attrib: str = "P",
                   sample: int = 4096, tolerance: float = 1e-6) -> dict:
    """比较 SOP 两帧的 point 数值属性，不移动用户 playbar。

    使用 ``geometryAtFrame`` 取得冻结几何；拓扑一致时返回抽样点的 mean/max delta、
    p50/p90/p99、逐分量位移统计与 unchanged 百分比。适合区分“真实几何静止”和
    “ROP/图片缓存”；这些数值证明数据在动，不自动证明运动的审美语义。

    可比较结果的精确键是 ``mean_delta``、``max_delta``、
    ``delta_percentiles``（``p50/p90/p99``）、``component_delta``
    （``min/max/mean`` 数组）、``unchanged_pct``、``sampled_points``、
    ``tolerance``、``data_type`` 和 ``size``；不要读取不存在的简写
    ``mean``/``max``。所有结果另含 node/attrib/frame/counts/bbox。
    """
    n = dsh_node_access._resolve(node)
    if n.type().category() != hou.sopNodeTypeCategory():
        raise ValueError("geo_frame_diff 只接受 SOP 节点")
    if not isinstance(sample, int) or sample <= 0 or sample > 1_000_000:
        raise ValueError("sample 必须是 1..1000000 的整数")
    if tolerance < 0:
        raise ValueError("tolerance 不能为负")
    fa, fb = float(frame_a), float(frame_b)
    _cook_control.require_evaluation('geo_frame_diff')
    ga = n.geometryAtFrame(fa)
    gb = n.geometryAtFrame(fb)
    if ga is None or gb is None:
        raise ValueError(f"节点 {n.path()} 在指定帧没有 geometry")
    counts_a = {"points": len(ga.points()), "prims": len(ga.prims())}
    counts_b = {"points": len(gb.points()), "prims": len(gb.prims())}
    bbox_a, bbox_b = ga.boundingBox(), gb.boundingBox()
    base = {
        "node": n.path(),
        'correspondence': 'point_number',
        'scope': 'sampled attribute arrays aligned by point number after count/type checks; stable IDs and matching primitive topology are not verified, so point reordering can appear as change',
        "attrib": attrib,
        "frame_a": fa,
        "frame_b": fb,
        "counts_a": counts_a,
        "counts_b": counts_b,
        "bbox_a": {
            "min": [float(v) for v in bbox_a.minvec()],
            "max": [float(v) for v in bbox_a.maxvec()],
        },
        "bbox_b": {
            "min": [float(v) for v in bbox_b.minvec()],
            "max": [float(v) for v in bbox_b.maxvec()],
        },
    }
    if counts_a != counts_b:
        base.update({"comparable": False, "reason": "topology counts differ"})
        return base
    aa, ab = ga.findPointAttrib(attrib), gb.findPointAttrib(attrib)
    if aa is None or ab is None:
        raise ValueError(f"两帧都必须有 point 属性 {attrib!r}")
    if aa.size() != ab.size() or aa.dataType() != ab.dataType():
        base.update({"comparable": False, "reason": "attribute type/size differs"})
        return base
    if aa.dataType() == hou.attribData.String:
        raise ValueError("geo_frame_diff 只支持数值 point 属性")
    getter = "pointFloatAttribValues" if aa.dataType() == hou.attribData.Float else "pointIntAttribValues"
    values_a = list(getattr(ga, getter)(attrib))
    values_b = list(getattr(gb, getter)(attrib))
    size = aa.size()
    point_count = counts_a["points"]
    if point_count <= sample:
        indices = range(point_count)
    elif sample == 1:
        indices = [0]
    else:
        indices = sorted({
            round(i * (point_count - 1) / (sample - 1)) for i in range(sample)
        })
    deltas = []
    component_deltas = [[] for _ in range(size)]
    for index in indices:
        offset = index * size
        components = [
            float(values_b[offset + c]) - float(values_a[offset + c])
            for c in range(size)
        ]
        deltas.append(math.sqrt(sum(value * value for value in components)))
        for component, value in enumerate(components):
            component_deltas[component].append(value)
    unchanged = sum(1 for value in deltas if value <= tolerance)
    ordered = sorted(deltas)

    def percentile(fraction: float) -> float:
        if not ordered:
            return 0.0
        if len(ordered) == 1:
            return ordered[0]
        position = fraction * (len(ordered) - 1)
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return ordered[lower]
        weight = position - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    base.update({
        "comparable": True,
        "data_type": "float" if aa.dataType() == hou.attribData.Float else "int",
        "size": size,
        "sampled_points": len(deltas),
        "tolerance": float(tolerance),
        "mean_delta": sum(deltas) / len(deltas) if deltas else 0.0,
        "max_delta": max(deltas) if deltas else 0.0,
        "delta_percentiles": {
            "p50": percentile(0.50),
            "p90": percentile(0.90),
            "p99": percentile(0.99),
        },
        "component_delta": {
            "min": [min(values) if values else 0.0 for values in component_deltas],
            "max": [max(values) if values else 0.0 for values in component_deltas],
            "mean": [
                sum(values) / len(values) if values else 0.0
                for values in component_deltas
            ],
        },
        "unchanged_pct": unchanged * 100.0 / len(deltas) if deltas else 100.0,
    })
    return base


def _geometry_fingerprint(node: hou.Node, frame: float) -> dict:
    _cook_control.require_evaluation('geometry fingerprint')
    geometry = node.geometryAtFrame(frame)
    if geometry is None:
        raise ValueError(f"节点 {node.path()} 在 frame {frame} 没有 geometry")
    points = int(geometry.intrinsicValue("pointcount"))
    prims = int(geometry.intrinsicValue("primitivecount"))
    if points == 0 and prims == 0:
        raise ValueError(
            f"节点 {node.path()} 在 frame {frame} cook 成功但没有可渲染几何；"
            "请传非空显式输出 SOP"
        )
    bbox = geometry.boundingBox()
    bbox_min = [float(v) for v in bbox.minvec()]
    bbox_max = [float(v) for v in bbox.maxvec()]
    signature = hashlib.sha256()
    signature.update(f"{points}|{prims}|{bbox_min}|{bbox_max}".encode("utf-8"))
    # 有界抽样 P：检测用户/上游在验证期间改变真实目标，不遍历百万点全量。
    if points and geometry.findPointAttrib("P") is not None:
        count = min(points, 257)
        indices = [0] if count == 1 else sorted({
            round(i * (points - 1) / (count - 1)) for i in range(count)
        })
        for index in indices:
            position = geometry.point(index).position()
            signature.update(struct.pack(
                "<3d",
                float(position[0]),
                float(position[1]),
                float(position[2]),
            ))
    errors = list(node.errors())
    warnings = list(node.warnings())
    return {
        "path": node.path(),
        "session_id": node.sessionId(),
        "type": node.type().name(),
        "frame": float(frame),
        "points": points,
        "prims": prims,
        "bbox_min": bbox_min,
        "bbox_max": bbox_max,
        "point_attrs": sorted(a.name() for a in geometry.pointAttribs()),
        "prim_attrs": sorted(a.name() for a in geometry.primAttribs()),
        "errors": errors,
        "warnings": warnings,
        "signature": signature.hexdigest()[:24],
        'signature_scope': 'counts, bounds and at most 257 sampled point positions; excludes unsampled positions, attribute values, primitive topology/intrinsics and object transforms. Equal signatures mean no sampled change detected, not complete geometry identity',
    }
