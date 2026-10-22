"""Houdini usd inspection. Executed on the Bridge owning thread."""
from __future__ import annotations

import os
import hou
import dsh_node_access


def _lop_stage(node):
    node = dsh_node_access._resolve(node)
    if node.type().category() != hou.lopNodeTypeCategory() or not hasattr(node, "stage"):
        raise ValueError(f"{node.path()} 不是可提供 USD stage 的 LOP 节点")
    stage = node.stage()
    if stage is None:
        raise ValueError(f"{node.path()} 没有可用的 USD stage")
    return node, stage


def _render_settings(rop):
    """Read the ROP's composed stage and selected RenderSettings without edits."""
    from pxr import Sdf
    path = rop.evalParm('loppath')
    node = rop.node(path) if path else rop.inputFollowingOutputs(0)
    while node is not None and not isinstance(node, hou.LopNode):
        node = node.inputFollowingOutputs(0)
    if node is None or not isinstance(node, hou.LopNode):
        raise ValueError('USD ROP has no resolvable input LOP')
    node, stage = _lop_stage(node)
    if node.errors():
        raise ValueError('USD render stage has cook errors')
    selector = str(rop.evalParm('rendersettings')).strip()
    settings_path = selector or stage.GetMetadata('renderSettingsPrimPath')
    # /Render shorthand is a husk command selector convention. Stage metadata
    # must itself identify an absolute prim; do not repair malformed metadata.
    if selector and not selector.startswith('/'):
        settings_path = '/Render/' + selector
    if not settings_path:
        # A discoverable settings prim is not a renderer selection. OpenUSD's
        # GetStageRenderSettings likewise returns invalid without this metadata;
        # husk may use defaults rather than the sole prim we happen to find.
        raise ValueError('USD ROP has no explicit or stage-default RenderSettings; '
                         'set rendersettings or stage renderSettingsPrimPath to identify the rendered products')
    settings_path = Sdf.Path(str(settings_path))
    if not settings_path.IsAbsolutePath() or not settings_path.IsPrimPath():
        raise ValueError('USD output observation requires one absolute RenderSettings prim path after ROP shorthand expansion; '
                         'settings lists and patterns remain unverified')
    settings = stage.GetPrimAtPath(settings_path)
    if not settings or settings.GetTypeName() != 'RenderSettings':
        raise ValueError('USD ROP RenderSettings path is invalid')
    return node, stage, settings


def _render_product_files(rop, frame):
    """Observe inherited disk raster outputs; leave delegate products explicit."""
    from pxr import Usd
    if str(rop.evalParm('renderpass')).strip():
        raise ValueError('Inherited render output observation does not resolve RenderPass selection; specify the intended output explicitly')
    if rop.parm('dorenderexisting') is not None and rop.evalParm('dorenderexisting'):
        raise ValueError('Inherited render output observation does not resolve an existing USD file; '
                         'the input LOP is not authoritative for that render')
    node, stage, settings = _render_settings(rop)
    products, unverified = [], []
    for path in settings.GetRelationship('products').GetForwardedTargets():
        prim = stage.GetPrimAtPath(path)
        if not prim or prim.GetTypeName() != 'RenderProduct':
            raise ValueError(f'Invalid RenderProduct: {path}')
        time_code = Usd.TimeCode(frame)
        product_type = str(prim.GetAttribute('productType').Get(time_code) or 'raster')
        name = str(prim.GetAttribute('productName').Get(time_code) or '')
        row = {'product': str(path), 'product_type': product_type, 'product_name': name}
        expanded = hou.text.expandHuskFilePath(name, frame_start=frame, frame_inc=1, frame_idx=0)
        if product_type != 'raster' or expanded in ('ip', 'husk:null_raster'):
            unverified.append({**row, 'status': 'unverified',
                               'reason': 'Delegate/checkpoint or non-disk products are not disk raster completion evidence'})
            continue
        name = expanded
        # productName is a token, not an asset path. Relative names depend on
        # husk's working directory; resolving them against $HIP would observe
        # a different file while leaving the native render unchanged.
        if not name or not os.path.isabs(name):
            raise ValueError(f'Inherited raster product has no absolute disk output: {path} ({name!r}); author its productName or pass picture explicitly')
        products.append({**row, 'output': name})
    if not products:
        raise ValueError('USD RenderSettings has no observable disk raster products; author a productName or pass picture explicitly')
    return {'stage': node.path(), 'settings': str(settings.GetPath()),
            'products': products, 'unverified_products': unverified}


def _usd_value_preview(value, limit: int = 8):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return 0.0 if value == 0.0 else value
    try:
        if hasattr(value, "pathString"):
            return str(value)
    except Exception:
        pass
    if isinstance(value, dict):
        items = list(value.items())
        return {
            "size": len(items),
            "preview": {
                str(key): _usd_value_preview(item, limit)
                for key, item in items[:limit]
            },
        }
    if isinstance(value, (list, tuple)):
        return {
            "size": len(value),
            "preview": [_usd_value_preview(item, limit) for item in value[:limit]],
        }
    # Vt arrays and Gf vectors are iterable but should never dump full mesh data.
    try:
        size = len(value)
        return {
            "size": int(size),
            "preview": [
                _usd_value_preview(value[index], limit)
                for index in range(min(int(size), limit))
            ],
        }
    except Exception:
        pass
    return str(value)


def _usd_relationships(prim) -> list:
    result = []
    for relationship in prim.GetRelationships():
        result.append({
            "name": str(relationship.GetName()),
            "targets": [str(target) for target in relationship.GetTargets()],
        })
    result.sort(key=lambda item: item["name"])
    return result


def usd_stage_summary(node, max_paths: int = 64) -> dict:
    """只读概览 LOP 的 USD stage：prim 类型、材质绑定、渲染和时间采样语义。"""
    from pxr import UsdLux
    node, stage = _lop_stage(node)
    max_paths = int(max_paths)
    if max_paths < 1 or max_paths > 500:
        raise ValueError("max_paths 必须在 1..500")

    groups = {
        "geometry": [],
        "materials": [],
        "lights": [],
        "cameras": [],
        "render_settings": [],
        "render_products": [],
        "render_vars": [],
        "other": [],
    }
    group_counts = {name: 0 for name in groups}
    material_bindings = []
    time_sampled = []
    time_sampled_total = 0
    total_prims = 0
    geometry_types = {
        "Mesh", "BasisCurves", "NurbsCurves", "Points", "Volume", "Capsule",
        "Cone", "Cube", "Cylinder", "Plane", "Sphere",
    }

    for prim in stage.Traverse():
        total_prims += 1
        path = str(prim.GetPath())
        type_name = str(prim.GetTypeName() or "")
        if prim.HasAPI(UsdLux.LightAPI):
            group = "lights"
        elif type_name in geometry_types:
            group = "geometry"
        elif type_name == "Material":
            group = "materials"
        elif type_name == "Camera":
            group = "cameras"
        elif type_name == "RenderSettings":
            group = "render_settings"
        elif type_name == "RenderProduct":
            group = "render_products"
        elif type_name == "RenderVar":
            group = "render_vars"
        else:
            group = "other"
        roles = [group]
        # Applied light APIs do not erase the prim's geometry role. An emissive
        # mesh must remain discoverable as geometry as well as a light source.
        if group == "lights" and type_name in geometry_types:
            roles.append("geometry")
        for role in roles:
            group_counts[role] += 1
            if len(groups[role]) < max_paths:
                groups[role].append({"path": path, "type": type_name or None})

        relationships = _usd_relationships(prim)
        bindings = [
            relationship for relationship in relationships
            if relationship["name"].startswith("material:binding")
        ]
        if bindings and len(material_bindings) < max_paths:
            material_bindings.append({"prim": path, "bindings": bindings})

        for attribute in prim.GetAttributes():
            try:
                count = int(attribute.GetNumTimeSamples())
            except Exception:
                count = 0
            if count:
                time_sampled_total += 1
            if count and len(time_sampled) < max_paths:
                samples = list(attribute.GetTimeSamples())
                time_sampled.append({
                    "prim": path,
                    "attribute": str(attribute.GetName()),
                    "count": count,
                    "samples": [float(sample) for sample in samples[:16]],
                    "samples_truncated": len(samples) > 16,
                })

    return {
        "node": node.path(),
        "total_prims": total_prims,
        "counts": group_counts,
        "prims": groups,
        "paths_truncated": {
            name: group_counts[name] > len(groups[name]) for name in groups
        },
        "material_bindings": material_bindings,
        "time_sampled_attributes": time_sampled,
        "time_samples_truncated": time_sampled_total > len(time_sampled),
        "errors": list(node.errors()),
        "warnings": list(node.warnings()),
    }


def usd_prim_info(node, prim_path: str, max_properties: int = 200) -> dict:
    """只读检查一个 USD prim 的属性、primvar、关系、绑定和 time samples。"""
    node, stage = _lop_stage(node)
    max_properties = int(max_properties)
    if max_properties < 1 or max_properties > 1000:
        raise ValueError("max_properties 必须在 1..1000")
    prim = stage.GetPrimAtPath(str(prim_path))
    if not prim or not prim.IsValid():
        similar = []
        needle = str(prim_path).lower().rsplit("/", 1)[-1]
        for candidate in stage.Traverse():
            path = str(candidate.GetPath())
            if needle and needle in path.lower():
                similar.append(path)
            if len(similar) >= 12:
                break
        raise ValueError(f"找不到 USD prim {prim_path!r}；相似：{similar}")

    attributes = []
    primvars = []
    properties = list(prim.GetProperties())
    for prop in properties[:max_properties]:
        if not hasattr(prop, "GetTypeName"):
            continue
        name = str(prop.GetName())
        samples = list(prop.GetTimeSamples())
        # Avoid pulling full topology/point arrays merely to answer structure.
        heavy = name in {
            "points", "normals", "faceVertexCounts", "faceVertexIndices",
            "velocities", "accelerations",
        }
        value = None
        if not heavy:
            try:
                value = _usd_value_preview(prop.Get())
            except Exception:
                value = None
        item = {
            "name": name,
            "type": str(prop.GetTypeName()),
            "value": value,
            "value_omitted": heavy,
            "time_sample_count": len(samples),
            "time_samples": [float(sample) for sample in samples[:16]],
            "time_samples_truncated": len(samples) > 16,
        }
        attributes.append(item)
        if name.startswith("primvars:"):
            primvars.append(item)

    relationships = _usd_relationships(prim)
    material_bindings = [
        relationship for relationship in relationships
        if relationship["name"].startswith("material:binding")
    ]
    return {
        "node": node.path(),
        "path": str(prim.GetPath()),
        "name": str(prim.GetName()),
        "type": str(prim.GetTypeName() or "") or None,
        "active": bool(prim.IsActive()),
        "defined": bool(prim.IsDefined()),
        "loaded": bool(prim.IsLoaded()),
        "instance": bool(prim.IsInstance()),
        "instanceable": bool(prim.IsInstanceable()),
        "kind": prim.GetMetadata("kind"),
        "attributes": attributes,
        "primvars": primvars,
        "relationships": relationships,
        "material_bindings": material_bindings,
        "property_count": len(properties),
        "properties_truncated": len(properties) > max_properties,
    }
