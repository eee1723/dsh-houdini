"""Deterministic pinhole/orthographic framing. Called only on the HOM thread.

Geometry bounds are conservative, not pixel segmentation or a beauty verdict.
No renderer, viewport, network service, or implicit user-camera mutation here.
"""
from __future__ import annotations

import itertools
import math


def finite(value, label):
    if isinstance(value, bool):
        raise ValueError(f'{label} must be finite numeric')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f'{label} must be finite numeric')
    return value


def raster(width, height, aspect=1):
    width, height = finite(width, 'width'), finite(height, 'height')
    if any(isinstance(x, bool) or int(x) != x or not 1 <= x <= 16384 for x in (width, height)):
        raise ValueError('width/height must be integers in 1..16384')
    aspect = finite(aspect, 'pixel aspect')
    if aspect <= 0:
        raise ValueError('pixel aspect must be positive')
    return int(width), int(height), aspect


def corners(bounds):
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2 or any(not isinstance(v, (list,tuple)) or len(v) != 3 for v in bounds):
        raise ValueError('bounds must be [min_xyz,max_xyz]')
    low, high = [[finite(x, 'bounds') for x in v] for v in bounds]
    if any(a > b for a, b in zip(low, high)):
        raise ValueError('bounds must be ordered')
    return list(itertools.product(*zip(low, high)))


def axes(direction):
    import hou
    if not isinstance(direction, (list, tuple)) or len(direction) != 3:
        raise ValueError('direction must be a three-component vector')
    back = hou.Vector3([finite(x, 'direction') for x in direction])
    if back.length() < 1e-9:
        raise ValueError('direction cannot be zero')
    back = back.normalized()
    up = hou.Vector3(0, 1, 0) if abs(back[1]) < .999 else hou.Vector3(0, 0, 1)
    right = up.cross(back).normalized()
    up = back.cross(right).normalized()
    return right, up, back


def solve(points, direction, width, height, *, coverage=.82, aspect=1,
          projection='perspective', focal=50, aperture=41.4214, near=.001):
    """Fit every bound vertex to a centered safe rectangle, including depth."""
    import hou
    width, height, aspect = raster(width, height, aspect)
    coverage = finite(coverage, 'coverage')
    if not .1 <= coverage <= .95:
        raise ValueError('coverage must be in .1.. .95')
    if projection not in ('perspective', 'orthographic'):
        raise ValueError('only perspective/orthographic projection is supported')
    focal, aperture, near = [finite(v, k) for v, k in ((focal, 'focal'), (aperture, 'aperture'), (near, 'near'))]
    if min(focal, aperture, near) <= 0:
        raise ValueError('focal/aperture/near must be positive')
    if not points or len(points) > 8192:
        raise ValueError('framing needs 1..8192 bound vertices, no sampling')
    pts = [hou.Vector3([finite(x, 'point') for x in p]) for p in points]
    low = [min(p[i] for p in pts) for i in range(3)]
    high = [max(p[i] for p in pts) for i in range(3)]
    center = hou.Vector3([(a+b)/2 for a, b in zip(low, high)])
    right, up, back = axes(direction)
    local = [[(p-center).dot(a) for a in (right, up, back)] for p in pts]
    th = aperture/(2*focal)
    ratio = width*aspect/height
    tv = th/ratio
    if projection == 'perspective':
        dist = max(z + max(abs(x)/(coverage*th), abs(y)/(coverage*tv), near*1.01)
                   for x, y, z in local)
        ortho_width = None
    else:
        ortho_width = max(1e-6, max(max(abs(x), abs(y)*ratio)*2/coverage for x, y, z in local))
        dist = max(1, max(z for x, y, z in local) + near*2)
    dist = max(dist, near*2) * (1 + 1e-7)
    eye = center + back*dist
    matrix = hou.Matrix4(tuple(v for row in (tuple(right)+(0,), tuple(up)+(0,), tuple(back)+(0,), tuple(eye)+(1,)) for v in row))
    depths = [dist-z for x, y, z in local]
    return {'matrix': matrix, 'center': list(center), 'eye': list(eye), 'dist': dist,
            'direction': list(back), 'orthowidth': ortho_width,
            'near': min(near, min(depths)*.5), 'far': max(near*2, max(depths)*1.01),
            'bounds': [low, high]}


def check(points, matrix, width, height, *, coverage=.82, aspect=1,
          projection='perspective', focal=50, aperture=41.4214,
          orthowidth=1, near=.001, far=10000, window=None):
    """Project actual camera transform; NDC here is [-1,1], not USD [0,1]."""
    import hou
    width, height, aspect = raster(width, height, aspect)
    coverage = finite(coverage, 'coverage')
    if not 0 < coverage <= 1:
        raise ValueError('check coverage must be in (0,1]')
    near, far = finite(near, 'near'), finite(far, 'far')
    if not 0 < near < far:
        raise ValueError('invalid clipping range')
    if projection not in ('perspective', 'orthographic'):
        raise ValueError('unsupported camera projection')
    focal, aperture, orthowidth = [finite(v, k) for v, k in ((focal, 'focal'), (aperture, 'aperture'), (orthowidth, 'orthowidth'))]
    if min(focal, aperture, orthowidth) <= 0:
        raise ValueError('invalid camera lens dimensions')
    if not points or len(points) > 8192:
        raise ValueError('framing needs 1..8192 bound vertices')
    window = [-1., -1., 1., 1.] if window is None else [finite(v, 'window') for v in window]
    if len(window) != 4 or window[0] >= window[2] or window[1] >= window[3]:
        raise ValueError('invalid camera data window')
    rows = [hou.Vector3(tuple(matrix.at(i,j) for j in range(3))) for i in range(3)]
    if any(not math.isfinite(v) for v in matrix.asTuple()) or any(
        abs(rows[i].dot(rows[j])-(1 if i==j else 0))>1e-6 for i in range(3) for j in range(3)
    ) or rows[0].cross(rows[1]).dot(rows[2]) < .999999:
        raise ValueError('camera world transform must be finite, rigid and right-handed; scale/shear unsupported')
    if any(abs(matrix.at(i,3))>1e-10 for i in range(3)) or abs(matrix.at(3,3)-1)>1e-10:
        raise ValueError('camera world transform must be affine')
    inv = matrix.inverted()
    positions = [hou.Vector3(p)*inv for p in points]
    depths = [-p[2] for p in positions]
    if not all(math.isfinite(v) for p in positions for v in p):
        raise ValueError('nonfinite camera projection')
    th = aperture/(2*focal)
    ratio = width*aspect/height
    projected = []
    for p, depth in zip(positions, depths):
        if depth <= 0:
            continue
        half_w = depth*th if projection == 'perspective' else orthowidth/2
        projected.append([p[0]/half_w, p[1]/(half_w/ratio)])
    ndc = [[min(p[i] for p in projected) for i in range(2)],
           [max(p[i] for p in projected) for i in range(2)]] if projected else None
    reasons = []
    if min(depths) < near: reasons.append('near_or_behind_camera')
    if max(depths) > far: reasons.append('far_clip')
    safe = [((window[i]+window[i+2])/2 - (window[i+2]-window[i])*coverage/2,
             (window[i]+window[i+2])/2 + (window[i+2]-window[i])*coverage/2) for i in range(2)]
    if ndc is None or any(ndc[0][i] < safe[i][0]-1e-6 or ndc[1][i] > safe[i][1]+1e-6 for i in range(2)):
        reasons.append('outside_safe_frame')
    margins = None if ndc is None else dict(zip(('left', 'right', 'bottom', 'top'),
        ((ndc[0][0]-window[0])*width/2, (window[2]-ndc[1][0])*width/2,
         (ndc[0][1]-window[1])*height/2, (window[3]-ndc[1][1])*height/2)))
    return {'ok': not reasons, 'framing_status': 'passed' if not reasons else 'failed',
            'reasons': reasons, 'projected_bounds_ndc': ndc, 'ndc_range': [-1, 1],
            'margin_px': margins, 'coverage': coverage, 'window_ndc': window, 'depth_range': [min(depths), max(depths)],
            'near': near, 'far': far, 'width': width, 'height': height, 'pixel_aspect': aspect,
            'projection': projection, 'focal': focal, 'aperture': aperture, 'orthowidth': orthowidth,
            'matrix': list(matrix.asTuple()), 'checked_vertices': len(points),
            'scope': 'bound vertices at the checked frame; not displacement, shutter envelope, occlusion or pixel segmentation',
            'semantic_status': 'unverified'}


def preview_plan(focus_bounds, depth_bounds, direction, width, height, *,
                 coverage=.82, projection='perspective', framing='full'):
    """Service-only lens zoom; framing and rendered-content depth are independent.

    Plan from reference envelopes ONLY. Current geometry is checked separately;
    never move a frozen A/B camera to accommodate an out-of-envelope state.
    Public camera_fit keeps its original focal-preserving solve contract.
    """
    import hou
    if framing not in ('full', 'detail'):
        raise ValueError('framing must be full or detail')
    width, height, _ = raster(width, height)
    coverage = finite(coverage, 'coverage')
    focus, depth = corners(focus_bounds), corners(depth_bounds)
    plan = solve(focus, direction, width, height, coverage=coverage, projection=projection)
    center = hou.Vector3(plan['center'])
    right, up, back = axes(plan['direction'])
    z_values = [(hou.Vector3(p)-center).dot(back) for p in depth]
    near = .001
    dist = max(plan['dist'], (max(z_values)+2*near)*(1+1e-7))
    eye = center + back*dist
    matrix = hou.Matrix4(plan['matrix'].asTuple())
    for i in range(3): matrix.setAt(3, i, eye[i])
    focal, aperture = 50., 41.4214
    if projection == 'perspective' and dist > plan['dist']:
        # A foreground context can force the camera backward. Refit the service
        # lens to the same focus at that safe distance, not to the whole context.
        ratio = width/height
        local = [(hou.Vector3(p)-center) for p in focus]
        th = max(max(abs(p.dot(right)), abs(p.dot(up))*ratio) /
                 (coverage*(dist-p.dot(back))) for p in local)
        focal = min(1e9, aperture/(2*max(th, 1e-12)))
    zoom = .55 if framing == 'detail' else 1.
    if projection == 'perspective': focal /= zoom
    orthowidth = (plan['orthowidth'] or 1.)*zoom
    return {**plan, 'matrix': matrix, 'eye': list(eye), 'dist': dist,
            'focal': focal, 'aperture': aperture, 'orthowidth': orthowidth,
            'near': near, 'far': max(10000., max(dist-z for z in z_values)*1.01),
            'depth_bounds': [list(depth_bounds[0]), list(depth_bounds[1])]}


def preview_check(focus_points, rendered_points, matrix, width, height, *, framing='full', **lens):
    """Only XY safe-frame overflow is an intentional crop; depth errors fail.

    The rendered bound includes context outside focus_group unless isolated.
    Preserve raw projection reasons separately from accepted framing policy.
    """
    if framing not in ('full', 'detail'):
        raise ValueError('framing must be full or detail')
    focus = check(focus_points, matrix, width, height, **lens)
    rendered = check(rendered_points, matrix, width, height, **lens)
    depth_reasons = [r for r in rendered['reasons'] if r != 'outside_safe_frame']
    crop_reasons = [r for r in focus['reasons'] if r == 'outside_safe_frame'] if framing == 'detail' else []
    reasons = list(dict.fromkeys([r for r in focus['reasons'] if r not in crop_reasons] + depth_reasons))
    return {**focus, 'ok': not reasons, 'reasons': reasons,
            'projection_reasons': focus['reasons'], 'crop_reasons': crop_reasons,
            'framing_status': 'failed' if reasons else 'intentional_crop' if crop_reasons else 'passed',
            'depth_check': {'ok': not depth_reasons, 'reasons': depth_reasons,
                            'depth_range': rendered['depth_range'], 'near': rendered['near'], 'far': rendered['far'],
                            'scope': 'all rendered proxy bounds, including non-isolated context; not displacement/shutter envelope'}}


def obj_lens(cam):
    """Reject unsupported lens/window configurations instead of guessing."""
    if cam.type().category().name() != 'Object' or cam.type().name() != 'cam':
        raise ValueError('camera_fit currently edits an explicit OBJ cam; import it into Solaris using Scene Import')
    projection = cam.parm('projection').evalAsString()
    if projection not in ('perspective', 'ortho'):
        raise ValueError('camera_fit supports only pinhole perspective or orthographic cameras')
    for name, expected in (('winx', 0), ('winy', 0), ('winsizex', 1), ('winsizey', 1),
                           ('cropl',0),('cropr',1),('cropb',0),('cropt',1)):
        if abs(finite(cam.evalParm(name), name)-expected) > 1e-8:
            raise ValueError('camera window offsets/crops are unsupported; use an unshifted camera')
    if cam.parm('vm_lensshader') is not None and cam.evalParm('vm_lensshader'):
        raise ValueError('lens shaders are unsupported by geometric framing')
    return {'projection': 'perspective' if projection == 'perspective' else 'orthographic',
            **{k: cam.evalParm(p) for k, p in (('focal','focal'), ('aperture','aperture'),
               ('aspect','aspect'), ('orthowidth','orthowidth'), ('near','near'), ('far','far'))}}


def sop_bounds(target, frame):
    import hou
    if target.type().category() != hou.sopNodeTypeCategory():
        raise ValueError('target must be an explicit SOP output')
    geo = target.geometryAtFrame(frame)
    if geo is None or target.errors() or not geo.intrinsicValue('pointcount'):
        raise ValueError('target SOP is empty or has cook errors')
    parent = target.parent()
    while parent is not None and not isinstance(parent, hou.ObjNode):
        parent = parent.parent()
    transform = parent.worldTransformAtTime(hou.frameToTime(frame)) if parent else hou.Matrix4(1)
    box = geo.boundingBox()
    return [list(hou.Vector3(p)*transform) for p in corners([list(box.minvec()), list(box.maxvec())])]


def fit_camera(camera, target, direction, coverage, width, height, frame, dry_run, allow_foreign):
    import hou
    import dsh_hou_helpers as h
    cam, target = h._resolve(camera), h._resolve(target)
    h._require_owned(cam, 'camera_fit', allow_foreign)
    # Even allow_foreign must not repurpose the persistent preview service.
    if cam.userData(h._RENDER_OWNER_KEY) == h._RENDER_OWNER_VALUE:
        raise ValueError('camera_fit cannot edit render_view service cameras')
    if not isinstance(dry_run, bool):
        raise ValueError('dry_run must be bool')
    f = finite(hou.frame() if frame is None else frame, 'frame')
    if f != hou.frame():
        raise ValueError('camera_fit edits a static camera at the current frame; evaluate animated cameras separately')
    lens = obj_lens(cam)
    width = cam.evalParm('resx') if width is None else width
    height = cam.evalParm('resy') if height is None else height
    points = sop_bounds(target, f)
    direction = h._NAMED_DIRECTIONS.get(direction, direction) if isinstance(direction, str) else direction
    plan = solve(points, direction, width, height, coverage=coverage, **{k:lens[k] for k in ('projection','focal','aperture','aspect','near')})
    # Snapshot every channel setWorldTransform may alter; never follow references.
    names = ('t','r','s','p','pr','shear')
    parms = [p for name in names if cam.parmTuple(name) is not None for p in cam.parmTuple(name)]
    parms += [cam.parm(n) for n in ('scale','lookatpath','near','far','orthowidth','resx','resy') if cam.parm(n) is not None]
    # Shipped OBJ cameras lock scale to one using lock(1). These channels are
    # not authored by framing and must neither be unlocked nor reject a new cam.
    def default_scale(p):
        return p.name() in ('sx','sy','sz','scale') and len(p.keyframes()) == 1 and p.expression() == 'lock(1)'
    if any(p.keyframes() and not default_scale(p) for p in parms):
        raise ValueError('camera_fit refuses animated/expression-driven camera channels')
    if cam.parm('constraints_on') is not None and cam.evalParm('constraints_on'):
        raise ValueError('camera_fit refuses constrained cameras')
    state = h._parameter_snapshot(parms)
    common = {'camera': cam.path(), 'target': target.path(), 'frame': f,
              'dry_run': dry_run, 'bounds': plan['bounds'], 'eye': plan['eye'],
              'center': plan['center'], 'dist': plan['dist'], 'direction': plan['direction']}
    fitted_lens = {**lens, 'near': plan['near'], 'far': max(lens['far'], plan['far']),
                  'orthowidth': plan['orthowidth'] or lens['orthowidth']}
    predicted = check(points, plan['matrix'], width, height, coverage=coverage, **fitted_lens)
    if dry_run:
        return {**common, **predicted, 'applied': False}
    try:
        cam.parm('lookatpath').set('', follow_parm_reference=False)
        cam.setWorldTransform(plan['matrix'], fail_on_locked_parms=True)
        for name, value in (('near', fitted_lens['near']), ('far', fitted_lens['far']),
                            ('orthowidth', fitted_lens['orthowidth']), ('resx', width), ('resy', height)):
            cam.parm(name).set(value, follow_parm_reference=False)
        actual = check(points, cam.worldTransform(), width, height, coverage=coverage, **obj_lens(cam))
        if not cam.worldTransform().isAlmostEqual(plan['matrix'], 1e-6):
            raise h.CheckpointError('camera_fit cannot realize the requested world transform (parent scale/shear/pretransform)', actual)
        if not actual['ok']:
            raise h.CheckpointError('camera_fit actual camera failed framing', actual)
        return {**common, **actual, 'applied': True}
    except BaseException:
        errors = h._restore_parameters(state)
        if errors:
            raise RuntimeError(f'camera_fit restoration failed: {errors}')
        raise


def usd_check(rop, spec, frame):
    """Resolve the ROP's actual composed stage/settings/products. Never refit."""
    import hou
    from pxr import Usd, UsdGeom
    if not isinstance(spec, dict) or set(spec)-{'target','coverage'} or not isinstance(spec.get('target'), str):
        raise ValueError('framing must be {target: absolute USD prim path, coverage?: .82}')
    if rop.type().name() != 'usdrender_rop':
        raise ValueError('render_frame framing currently supports USD Render ROP only')
    # Husk overrides/run scripts can change what is rendered after stage cook.
    # Reject unsupported overrides rather than validate a different camera/file.
    for name in ('override_camera','override_res','renderpass'):
        if rop.parm(name) is not None and str(rop.evalParm(name)).strip():
            raise ValueError(f'framing does not support ROP {name}; author it in RenderSettings/Product')
    for name in ('dorenderexisting','husk_dopopulationmask','husk_tile','husk_slapcomp'):
        if rop.parm(name) is not None and rop.evalParm(name):
            raise ValueError(f'framing does not support ROP {name}')
    for name in ('prerender','preframe','husk_prerender','husk_preframe','husk_presnapshot'):
        toggle = rop.parm('t'+name) if not name.startswith('husk_') else rop.parm('husk_t'+name[5:])
        if rop.parm(name) is not None and (toggle is None or toggle.eval()) and str(rop.evalParm(name)).strip():
            raise ValueError(f'framing cannot guarantee ROP script {name}; use explicit artistic/unverified render')
    if rop.parm('rendercommand') is not None and rop.evalParm('rendercommand').strip() != 'husk':
        raise ValueError('framing requires the standard husk render command')
    coverage = finite(spec.get('coverage', .82), 'coverage')
    if not .1 <= coverage <= .95:
        raise ValueError('framing coverage must be in .1.. .95')
    path = rop.evalParm('loppath')
    node = hou.node(path) if path else rop.input(0)
    if node is None or not isinstance(node, hou.LopNode):
        raise ValueError('USD ROP has no resolvable input LOP')
    stage = node.stage()
    if stage is None or node.errors():
        raise ValueError('USD render stage has cook errors or is missing')
    settings_path = rop.evalParm('rendersettings') or stage.GetMetadata('renderSettingsPrimPath')
    if not settings_path:
        candidates = []
        for i, p in enumerate(stage.Traverse()):
            if i >= 4096:
                raise ValueError('USD settings discovery budget exceeded; set rendersettings explicitly')
            if p.GetTypeName() == 'RenderSettings': candidates.append(str(p.GetPath()))
        if len(candidates) != 1:
            raise ValueError('USD ROP must resolve one explicit RenderSettings')
        settings_path = candidates[0]
    settings = stage.GetPrimAtPath(settings_path)
    if not settings or settings.GetTypeName() != 'RenderSettings':
        raise ValueError('USD ROP RenderSettings path is invalid')
    from pxr import Sdf
    target_path = Sdf.Path(spec['target'])
    if not target_path.IsAbsolutePath() or not target_path.IsPrimPath():
        raise ValueError('framing target must be an absolute USD prim path')
    target = stage.GetPrimAtPath(target_path)
    if not target or spec['target'] == '/' or not target.IsActive() or not target.IsLoaded():
        raise ValueError('framing target must be an active, loaded, explicit USD asset prim')
    time_code = Usd.TimeCode(frame)
    for index, descendant in enumerate(Usd.PrimRange(target)):
        if index >= 4096:
            raise ValueError('USD target exceeds 4096-prim framing budget; select a smaller asset')
        if descendant.GetTypeName() in ('Volume','PointInstancer'):
            raise ValueError('volume/point-instancer framing requires an independently verified extent; unsupported')
    product_paths = settings.GetRelationship('products').GetForwardedTargets()
    if not 1 <= len(product_paths) <= 16:
        raise ValueError('framing requires 1..16 RenderProducts; no silent first-product selection')
    rows = []
    for product_path in product_paths:
        product = stage.GetPrimAtPath(product_path)
        if not product or product.GetTypeName() != 'RenderProduct':
            raise ValueError('invalid RenderProduct')
        def attr(name):
            p = product.GetAttribute(name)
            return p.Get(time_code) if p and p.HasAuthoredValueOpinion() else settings.GetAttribute(name).Get(time_code)
        camera_rel = product.GetRelationship('camera')
        camera_paths = camera_rel.GetForwardedTargets() if camera_rel else []
        if not camera_paths: camera_paths = settings.GetRelationship('camera').GetForwardedTargets()
        if len(camera_paths) != 1:
            raise ValueError('each render product must resolve exactly one camera')
        camera = stage.GetPrimAtPath(camera_paths[0])
        if not camera or camera.GetTypeName() != 'Camera':
            raise ValueError('render product camera is missing')
        # Unknown lens modes must not receive a pinhole guarantee.
        for prop in camera.GetAttributes():
            if ('lensshader' in prop.GetName().lower() or 'lens:shader' in prop.GetName().lower()) and prop.Get(time_code):
                raise ValueError('USD lens shader framing is unsupported')
        gf_cam = UsdGeom.Camera(camera).GetCamera(time_code)
        if abs(finite(gf_cam.horizontalApertureOffset,'horizontal aperture offset'))+abs(finite(gf_cam.verticalApertureOffset,'vertical aperture offset')) > 1e-8:
            raise ValueError('USD aperture offsets are unsupported by framing preflight')
        projection = str(camera.GetAttribute('projection').Get(time_code))
        width, height = list(attr('resolution'))
        pixel_aspect = float(attr('pixelAspectRatio'))
        width, height, pixel_aspect = raster(width, height, pixel_aspect)
        ha, va = finite(gf_cam.horizontalAperture,'horizontal aperture'), finite(gf_cam.verticalAperture,'vertical aperture')
        if min(ha, va) <= 0:
            raise ValueError('invalid USD camera apertures')
        ratio = width*pixel_aspect/height
        policy = str(attr('aspectRatioConformPolicy'))
        if policy == 'adjustPixelAspectRatio':
            pixel_aspect = (ha/va)*height/width
        elif policy == 'adjustApertureWidth': ha = va*ratio
        elif policy == 'adjustApertureHeight': va = ha/ratio
        elif policy == 'expandAperture':
            if ha/va < ratio: ha = va*ratio
            else: va = ha/ratio
        elif policy == 'cropAperture':
            if ha/va > ratio: ha = va*ratio
            else: va = ha/ratio
        else:
            raise ValueError(f'unsupported USD aspectRatioConformPolicy: {policy}')
        purposes = settings.GetAttribute('includedPurposes').Get(time_code) or ['default','render']
        # Houdini's default husk purpose menu uses "geometry" for USD default.
        if rop.parm('husk_purpose') is not None:
            purpose_override = rop.evalParm('husk_purpose').strip()
            if purpose_override:
                purposes = ['default' if x.strip()=='geometry' else x.strip() for x in purpose_override.split(',')]
                if any(p not in ('default','render','proxy','guide') for p in purposes):
                    raise ValueError('unsupported husk purpose override')
        cache = UsdGeom.BBoxCache(time_code, list(purposes), useExtentsHint=False, ignoreVisibility=False)
        bound = cache.ComputeWorldBound(target).ComputeAlignedRange()
        if bound.IsEmpty():
            raise ValueError('USD target has no visible bounds for the included render purposes')
        world = hou.Matrix4(tuple(float(v) for row in gf_cam.transform for v in row))
        points = corners([list(bound.GetMin()), list(bound.GetMax())])
        data_window = list(attr('dataWindowNDC'))
        result = check(points, world, width, height, coverage=coverage, aspect=pixel_aspect,
            projection=projection, focal=float(gf_cam.focalLength), aperture=ha,
            orthowidth=ha*.1, near=float(gf_cam.clippingRange.min), far=float(gf_cam.clippingRange.max),
            window=[2*float(v)-1 for v in data_window])
        rows.append({**result, 'product': str(product_path), 'camera': str(camera_paths[0]),
                     'aspect_ratio_conform_policy': policy, 'effective_apertures': [ha, va]})
    return {'ok': all(r['ok'] for r in rows),
            'framing_status': 'passed' if all(r['ok'] for r in rows) else 'failed',
            'stage': node.path(), 'settings': str(settings_path), 'target': spec['target'],
            'frame': frame, 'products': rows, 'render_started': False,
            'scope': 'composed USD bounds/cameras/products at one frame; displacement, lens effects and shutter envelope unverified',
            'semantic_status': 'unverified'}
