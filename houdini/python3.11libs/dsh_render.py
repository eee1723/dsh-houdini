"""Houdini render. Executed on the Bridge owning thread."""
from __future__ import annotations

import dsh_view_state

import functools
import contextlib
import hashlib
import math
import os
import re
import time
import hou
import dsh_cook_control as _cook_control
import dsh_errors
import dsh_geometry_queries
import dsh_image_pixels
import dsh_media_output
import dsh_node_access
import dsh_parameter_values
import dsh_render_service
import dsh_service_constants


def _with_render_slot(fn):
    """Serialize render_frame/render_view across shared-host executors (fail-fast)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        import dsh_executor_registry
        slot = dsh_executor_registry.render_slot()
        try:
            return fn(*args, **kwargs)
        finally:
            dsh_executor_registry.release_render_slot(slot)
    return wrapper


def _restore_render_frame(frame):
    errors = []
    if float(hou.frame()) != frame:
        try:
            hou.setFrame(frame)
        except Exception as error:
            errors.append(f'frame: {error}')
    if float(hou.frame()) != frame:
        errors.append('frame: restoration readback differs')
    return errors


@contextlib.contextmanager
def _render_preflight_frame(frame, node):
    original = float(hou.frame())
    try:
        if original != frame:
            hou.setFrame(frame)
        yield
    finally:
        errors = _restore_render_frame(original)
        if errors:
            raise dsh_errors.CheckpointError('render_frame preflight frame restoration failed', {
                'ok': False, 'phase': 'render_restore', 'restored': False,
                'restore_errors': errors, 'frame_restored': False,
                'path': node.path(), 'frame': frame, 'render_started': False,
                'scope': 'Temporary frame used to inspect composed USD output/framing',
            })


def _preserve_render_service_on_undo(fn):
    """Keep preview service edits out of a caller's deliverable undo group.

    A later Python error in the same exec rolls back authored nodes. If the
    first preview created an OpenGL ROP inside that group, native undo could
    delete the persistent renderer after it had rendered. Preview state is
    restored by render_view itself and its image is an external file effect.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with hou.undos.disabler():
            return fn(*args, **kwargs)
    return wrapper


def _render_validation(rendered, check, stale, pixel_supported=True, warnings=None) -> dict:
    errors = list(rendered.get('errors') or [])
    warnings = list(warnings or [])
    file_ok = bool(rendered.get('fresh') and rendered.get('file_bytes') and not errors)
    if not file_ok and not errors:
        errors.append('render output missing, empty or stale on disk')
    pixel_status = 'unverified'
    if pixel_supported:
        if not isinstance(check, dict) or check.get('error'):
            pixel_status = 'failed'
            errors.append('pixel inspection failed: ' + str((check or {}).get('error', 'missing check')))
        elif 'no_nonblack_content' in check.get('presentation', {}).get('reasons', []):
            pixel_status = 'failed'
            errors.append('pixel inspection: no_nonblack_content')
        elif check.get('presentation', {}).get('needs_review'):
            pixel_status = 'needs_review'
        else:
            pixel_status = 'passed'
    if stale:
        errors.append('target/proxy changed during rendering; recapture evidence')
    if warnings:
        errors.append(
            'render source has cook warnings; image retained for diagnosis but cannot pass acceptance: '
            + '; '.join(dict.fromkeys(str(item) for item in warnings))
        )
    return {'ok': not errors, 'errors': errors, 'file_status': 'passed' if file_ok else 'failed',
            'pixel_status': pixel_status, 'semantic_status': 'unverified'}


def camera_fit(camera, target, direction='iso', coverage: float = .82,
               width=None, height=None, frame=None, *, dry_run: bool = False,
               allow_foreign: str | None = None) -> dict:
    """拟合一个正式 OBJ cam 到显式 SOP 的世界空间包络，不渲染、不动用户视口。

    保留焦距/投影，按direction和coverage安全框求距离（正交则求orthowidth），
    写入后按实际矩阵回验。width/height默认取相机分辨率。允许parent变换，
    拒绝动画/表达式/约束相机、偏移或裁切窗口和lens shader。lookatpath会清空，
    只改指定相机、不移动目标；失败恢复参数。dry_run返回拟合计划，仍须exec。
    ownership及单次allow_foreign适用；持久render_view服务相机永不允许改作交付。
    Solaris用Scene Import导入此相机；render_frame(framing=...)按最终USD相机/产品
    预检，不能把OBJ取景通过当成USD产品通过。只证明当前帧包络，不证明位移/运动模糊。
    """
    _cook_control.require_evaluation('camera_fit')
    from dsh_camera_framing import fit_camera
    return fit_camera(camera, target, direction, coverage, width, height, frame, dry_run, allow_foreign)


@_with_render_slot
def render_frame(rop, picture=None, frame=None, timeout: float = 110, *, framing=None) -> dict:
    """渲染单帧并**验证产物**（等文件落盘 + 非空 + 采集 ROP 错误）。

    固化「设 picture → setFrame → rop.render() → 等产物 → 报大小」的样板：
    ``render()`` 不抛异常**不等于**产物存在（ROP 参数错、输出目录不可写、
    渲染器挂起都是静默失败），所以本动词等到文件落盘且非空才返回
    ``file_bytes``，否则在 ``errors`` 里说明。

    - rop：ROP 节点（hou.Node 或 path）。输出参数按常见名自动解析；图像参数
      ``outputimage`` 优先于 USD ``lopoutput``，Karma/Mantra/geometry 等 ROP 都覆盖。
      有 ``soho_foreground`` 时调用期临时等待渲染完成并在 finally 恢复。
    - picture：输出路径（含 $F 变量可直接传）；None = 用 ROP 当前设置。
      USD Render ROP未设outputimage时读取实际RenderSettings的磁盘raster产品，不写入覆盖项；
      多产品逐个检查并返回outputs，此时output为None。delegate/checkpoint产品单独列为未验证。
      继承路径按原生Husk展开；相对产品路径、RenderPass与未明确选择的settings不推测。
      裸文件名按输出用途放入$HIP/dsh-artifacts/renders/<HIPNAME>；COP copoutput放入dsh-artifacts/textures，
      几何/模拟/通道缓存放入dsh-artifacts/cache。已有含目录的ROP路径和显式绝对目的地不改写。
      诊断/测试图显式传picture='$HIP/dsh-artifacts/checks/previews/$HIPNAME/<task>/check.png'，
      不把过程检查写入成图目录；目录位置本身不证明已经交付或视觉正确。
    - frame：帧号；None = 当前帧。
    - timeout：等产物的上限（秒）。超过 ~110s 的渲染请走 houdini_job_submit
      （host 侧桥请求超时 120s），本动词面向单帧测试渲染。
    - framing：可选{target:绝对USD资产prim路径, coverage:.82}。只支持USD Render ROP，
      在renderer启动/文件写入前验证实际stage全部RenderProducts的相机与目标包络。
      包含resolution/pixelAspect/aperture conform/dataWindow；失败零渲染，不自动移动相机。
      未传则保留正式/艺术裁切镜头语义。只证明本帧USD bounds，不证明位移/快门/语义质量。
    """
    _cook_control.require_evaluation('render_frame')
    n = dsh_node_access._resolve(rop)
    if not isinstance(n, hou.RopNode) or not hasattr(n, "render"):
        if n.type().category() == hou.lopNodeTypeCategory():
            raise ValueError(
                f"{n.path()} 是普通 LOP（{n.type().name()}），不是可执行 ROP；"
                "请用 search_tab_entries('/stage', 'Karma (Setup)') + "
                "tab_apply('/stage', 'lop_karma_setup') 创建 USD Render ROP，"
                "再把该 usdrender_rop 传给 render_frame"
            )
        raise ValueError(f"{n.path()} 不是可执行 ROP，缺少 render()")
    p = None
    # USD Render ROP owns both `lopoutput` (temporary/exported USD) and
    # `outputimage` (rendered image override). Image output must win or a PNG
    # path is accidentally assigned as the USD file and no image is produced.
    for pname in ("picture", "vm_picture", "outputimage", "sopoutput",
                  "lopoutput", "dopoutput", "copoutput", "choutput"):
        p = n.parm(pname)
        if p is not None:
            break
    if p is None:
        raise ValueError(
            f"节点 '{n.path()}' 找不到输出路径参数（试过 picture/vm_picture/"
            "outputimage/sopoutput/lopoutput/dopoutput/copoutput/choutput）——"
            "它不是 ROP？（非常规输出参数请裸写 hou，词表不覆盖）"
        )
    f = hou.frame() if frame is None else float(frame)
    if not math.isfinite(f) or not math.isfinite(float(timeout)) or float(timeout) <= 0:
        raise ValueError('frame must be finite and timeout must be positive/finite')
    # Resolving before any parameter/frame write also rejects extensionless
    # outputs and relative files outside the project with zero scene effects.
    original_output = p.unexpandedString()
    output_role = ('cache' if p.name() in ('sopoutput', 'dopoutput', 'choutput') else
                   'texture' if p.name() == 'copoutput' else 'render')
    original_frame = float(hou.frame())
    inherited = None
    if n.type().name() == 'usdrender_rop' and picture is None and not p.evalAtFrame(f).strip():
        from dsh_usd_inspection import _render_product_files
        with _render_preflight_frame(f, n):
            inherited = _render_product_files(n, f)
        outputs = [{**row, 'output': dsh_media_output._resolve_output_path(row['output'], frame=f, expand_variables=False)}
                   for row in inherited['products']]
    else:
        outputs = [{'output': dsh_media_output._resolve_output_path(
            original_output if picture is None else picture, frame=f, default_role=output_role)}]
    target = outputs[0]['output'] if len(outputs) == 1 else None
    foreground_parm = n.parm("soho_foreground")
    parameter_state = dsh_parameter_values._parameter_snapshot(
        ([] if inherited is not None else [p]) + ([foreground_parm] if foreground_parm is not None else []))
    framing_evidence = None
    if framing is not None:
        from dsh_camera_framing import usd_check
        with _render_preflight_frame(f, n):
            framing_evidence = usd_check(n, framing, f)
            if not framing_evidence['ok']:
                raise dsh_errors.CheckpointError('USD framing failed before renderer start; fit the explicit camera or revise the intentional crop', framing_evidence)
    t0 = time.time()
    render_err = None
    file_bytes = None
    pre_fingerprint = None
    post_fingerprint = None

    def fingerprint(path):
        if not path or not os.path.isfile(path):
            return None
        stat = os.stat(path)
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            digest.update(handle.read(64 * 1024))
            if stat.st_size > 64 * 1024:
                handle.seek(max(0, stat.st_size - 64 * 1024))
                digest.update(handle.read(64 * 1024))
        return {
            "bytes": int(stat.st_size),
            "mtime_ns": str(stat.st_mtime_ns),
            "sample_sha256": digest.hexdigest(),
        }

    try:
        if inherited is None:
            dsh_parameter_values._clear_animation(p)
            p.set(dsh_media_output._literal_houdini_path(target), follow_parm_reference=False)
        hou.setFrame(f)
        if foreground_parm is not None:
            dsh_parameter_values._clear_animation(foreground_parm)
            foreground_parm.set(1, follow_parm_reference=False)
        for output in outputs:
            output['pre_fingerprint'] = fingerprint(output['output'])
            output['post_fingerprint'] = None
            output['preexisting'] = output['pre_fingerprint'] is not None
            output['fresh'] = False
            output['file_bytes'] = None
            out_dir = os.path.dirname(output['output'])
            if out_dir and not os.path.isdir(out_dir):
                os.makedirs(out_dir, exist_ok=True)
        try:
            if framing_evidence is not None:
                framing_evidence['render_started'] = True
            n.render(frame_range=(f, f))
        except Exception as e:  # hou.Error 等
            render_err = str(e)

        deadline = t0 + float(timeout)
        # Native render() is synchronous and can exceed the file-wait budget.
        # Always inspect the output once after it returns before reporting absence.
        while not render_err:
            for output in outputs:
                post = output['post_fingerprint'] = fingerprint(output['output'])
                output['fresh'] = bool(post is not None and post['bytes'] > 0 and post != output['pre_fingerprint'])
                output['file_bytes'] = post['bytes'] if output['fresh'] else None
            if all(output['fresh'] for output in outputs):
                file_bytes = sum(output['file_bytes'] for output in outputs)
                break
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            time.sleep(min(1, remaining))
    finally:
        if len(outputs) == 1:
            pre_fingerprint = outputs[0].get('pre_fingerprint')
            post_fingerprint = outputs[0].get('post_fingerprint')
        restore_errors = dsh_parameter_values._restore_parameters(parameter_state)
        # 渲染帧属于 agent 验证状态，不占用用户 playbar；即使 ROP 失败也还原。
        restore_errors.extend(_restore_render_frame(original_frame))
        if restore_errors:
            # Failed image/output checks are ordinary returned diagnostics.
            # An unrecovered temporary scene write is different: retain its
            # evidence and let the existing exec protocol block later writes,
            # cooks, renders and saves even when agent code catches this error.
            raise dsh_errors.CheckpointError('render_frame temporary state restoration failed', {
                'ok': False, 'phase': 'render_restore', 'restored': False,
                'restore_errors': restore_errors,
                'frame_restored': float(hou.frame()) == original_frame,
                'path': n.path(), 'output': target, 'frame': f,
                'fresh': file_bytes is not None, 'file_bytes': file_bytes,
                'pre_fingerprint': pre_fingerprint, 'post_fingerprint': post_fingerprint,
                **({'outputs': outputs, 'inherited_products': inherited} if inherited is not None else {}),
                'errors': ([render_err] if render_err else []) +
                          [f'restore failed: {error}' for error in restore_errors],
                'scope': 'snapshotted output/foreground parameters and frame only; '
                         'written files, renderer and callback side effects are separate',
            })

    errors: list[str] = []
    if render_err:
        errors.append(render_err)
    try:
        for e in n.errors():
            if e and e not in errors:
                errors.append(e)
    except Exception:
        pass
    if not render_err:
        for output in outputs:
            if not output.get('fresh'):
                errors.append(f"render() 未报错但产物缺失、为空或与渲染前指纹相同：{output['output']}")
    for output in outputs:
        if output.get('fresh'):
            dsh_media_output.report_image(output['output'])
    return {
        "path": n.path(),
        "output": target,
        "frame": f,
        "file_bytes": file_bytes,
        "preexisting": any(output.get('preexisting') for output in outputs),
        "fresh": file_bytes is not None,
        "pre_fingerprint": pre_fingerprint,
        "post_fingerprint": post_fingerprint,
        **({'outputs': outputs, 'inherited_products': inherited,
            'scope': 'File freshness for the listed disk raster products only; delegate/checkpoint products and visual semantics remain unverified'}
           if inherited is not None else {}),
        **({'framing': framing_evidence} if framing_evidence is not None else {}),
        "errors": errors,
        "ms": int((time.time() - t0) * 1000),
    }




_DISPLAY_IMAGE_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff",
})


_LINEAR_IMAGE_EXTENSIONS = frozenset({".exr", ".hdr", ".pic", ".rat"})


_SRGB_OCIO_SPACE_PREFERENCES = (
    # Houdini 22 / OCIO config 3 (ACES 2).
    "sRGB Encoded Rec.709 (sRGB)",
    # Houdini 21 / OCIO config 2.1 (ACES 1.3).
    "sRGB - Texture",
    # Common studio/legacy alias.
    "Utility - sRGB - Texture",
)


def _select_srgb_ocio_space(spaces=None) -> str | None:
    """Return an encoded sRGB output space across shipped H21/H22 configs."""
    if spaces is None:
        try:
            spaces = hou.Color.ocio_spaces()
        except Exception:
            spaces = ()
    available = {str(space) for space in spaces}
    for preferred in _SRGB_OCIO_SPACE_PREFERENCES:
        if preferred in available:
            return preferred

    # Custom configs often rename the utility space.  Prefer an encoded or
    # texture sRGB space, but never silently select a display reference space:
    # the OpenGL ROP parameter expects an output colorspace, not a display/view
    # pair.
    candidates = sorted(
        space for space in available
        if "srgb" in space.lower()
        and "display" not in space.lower()
        and ("encoded" in space.lower() or "texture" in space.lower())
    )
    return candidates[0] if candidates else None


def _render_output_color_plan(picture, ocio_spaces=None) -> dict:
    """Choose scene-linear vs display encoding from the requested file type."""
    extension = os.path.splitext(os.fspath(picture))[1].lower()
    if extension in _LINEAR_IMAGE_EXTENSIONS:
        return {
            "mode": "scene_linear",
            "extension": extension,
            "method": "none",
            "ocio_colorspace": None,
            "approximate": False,
            "settings": {
                "colorcorrect": "none",
                "gamma": 1.0,
                "lut": "",
                "ociocolorspace": "",
                "ociolooks": "",
            },
        }

    # Unknown extensions follow render_view's presentation intent.  Known
    # display formats are listed explicitly for diagnostics, but defaulting an
    # unfamiliar 8-bit writer to linear would recreate the original dark-image
    # failure.
    target = _select_srgb_ocio_space(ocio_spaces)
    if target:
        return {
            "mode": "display_srgb",
            "extension": extension,
            "known_display_extension": extension in _DISPLAY_IMAGE_EXTENSIONS,
            "method": "ocio_colorspace",
            "ocio_colorspace": target,
            "approximate": False,
            "settings": {
                "colorcorrect": "ocio",
                "gamma": 1.0,
                "lut": "",
                "ociocolorspace": target,
                "ociolooks": "",
            },
        }

    # A custom OCIO config may expose no encoded sRGB output space.  Preserve a
    # usable visual-inspection PNG with the OpenGL ROP's gamma path, and report
    # that this is an approximation rather than pretending it is an exact sRGB
    # transfer function.
    return {
        "mode": "display_srgb",
        "extension": extension,
        "known_display_extension": extension in _DISPLAY_IMAGE_EXTENSIONS,
        "method": "gamma_fallback",
        "ocio_colorspace": None,
        "approximate": True,
        "settings": {
            "colorcorrect": "lut_gamma",
            "gamma": 2.2,
            "lut": "",
            "ociocolorspace": "",
            "ociolooks": "",
        },
    }


@_with_render_slot
@_preserve_render_service_on_undo
def render_view(node, direction="iso", frame=None,
                width: int = 1280, height: int = 720, picture=None,
                framing: str = "full", coverage: float = 0.82,
                framing_frame=None, *, output_policy: str = "managed",
                focus_group=None, isolate: bool = False,
                projection: str = 'perspective', framing_bounds=None, depth_bounds=None) -> dict:
    """显式 SOP → agent proxy → viewport ROP → render_check 的隔离验证。
    H22使用Flipbook/Vulkan及独立Work Lights；H21保持原OpenGL ROP设置。

    用户可随时把源 OBJ 的 display/render flag 切到空节点：本动词不跟随它，
    而是让 agent-owned Object Merge 指向传入的**具体 SOP**，OpenGL ROP 用
    ``forceobjects`` 只渲染 proxy。用户 OBJ 可见性、selection、playbar 均恢复。

    - ``node``：强烈建议显式 SOP；传 OBJ 时只在调用开始解析一次 render/display SOP。
    - ``direction``：视线方向（从目标指向相机的偏移向量），默认 3/4 俯视。
      也接受命名视角：``'iso'``（3/4 俯视）、``'front'``、``'side'``、
      ``'top'``（草地重跑 trace：agent 直觉写法就是 ``'iso'``——命名视角
      是意图，向量是实现）。
    - ``frame``：帧号；None = 当前帧。
    - ``picture/output_policy``：默认managed，只接收省略或安全basename并写入
      ``$HIP/dsh-artifacts/checks/previews/<HIPNAME>/<run-id>/``。
      最终交付用``output_policy='delivery'``分配到``$HIP/dsh-artifacts/renders/<HIPNAME>/``；自定路径用
      ``output_policy='explicit'``，其中裸文件名放进``$HIP/dsh-artifacts/checks/previews/<HIPNAME>/``。
      各模式均返回``artifact``路径事实，输出位置不证明验收通过。
    - ``framing``：``full`` 完整入镜；``detail`` 缩小画幅（正交宽度/透视视角），不推进相机。
      detail仅允许画框外裁切，near/far深度裁切始终拒绝；不以拓扑正确排除相机切断。
    - ``coverage``：full中央安全框宽/高占比（0.1..0.95）；.82为每侧至少9%边距。
    - ``framing_frame``：用哪一帧的 bbox 计算相机；None = 跟随 ``frame``。动画
      A/B 应给两次调用传同一个 framing_frame，确保相机 center/eye/dist 完全一致。
    - 输出颜色按扩展名自动管理：PNG/JPEG/TIFF 等展示格式从当前
      ``scene_linear`` 经 OCIO 转为编码 sRGB；EXR/HDR 保持线性供 Nuke/合成。
      返回 ``output_color`` 记录实际方法与目标空间，不用 gamma 猜测冒充 OCIO。
    - 返回 source/proxy fingerprint；真实目标在验证期间变化时 ``stale=True``。
    - focus_group为精确primitive组，空/缺失拒绝；isolate只在持久proxy中保留该组。
      projection为perspective/orthographic。framing_bounds=[min_xyz,max_xyz]使用proxy世界坐标；
      full中是完整取景包络，不是局部ROI。局部观察用focus_group，或detail配合局部bounds。
    - depth_bounds=[min_xyz,max_xyz]是全部实际渲染内容的深度包络，含未隔离上下文。
      默认取framing_frame的全部proxy；给framing_bounds但没给depth_bounds时沿用同一包络。
      A/B同时复用返回framing.bounds和framing.depth_bounds及相同方向/画幅/模式；越界拒绝不漂移。
    - 返回dict含output/check/framing/errors/stale；check含presentation/content_bbox等像素事实。
      pixels是check兼容别名，Bridge证据也提供check/pixels；不能把ok当视觉语义通过。
      源或proxy有cook warning时仍保留诊断图片，但返回ok=False并把warning写入errors，
      不能用文件/像素成功核销视觉完成门。

    本工具仍要求GUI会话；这不是对Flipbook原生headless能力的限制声明。
    H22要求Vulkan兼容设备，H21保持原GUI边界；headless另走render_frame。
    硬件预览在Windows锁屏/远程桌面断开时可能失败，
    失败会体现在返回的 ``errors`` 里。
    """
    if not hou.isUIAvailable():
        raise ValueError(
            "render_view 当前支持范围需要 Houdini GUI；"
            "headless 环境请用 render_frame 走 CPU 渲染器"
        )
    _cook_control.require_evaluation('render_view')
    if framing not in ("full", "detail"):
        raise ValueError("framing 只能是 'full' 或 'detail'")
    if not isinstance(isolate, bool) or (isolate and focus_group is None):
        raise ValueError('isolate requires an explicit focus_group')
    if projection not in ('perspective', 'orthographic'):
        raise ValueError('projection must be perspective or orthographic')
    if focus_group is not None and (not isinstance(focus_group,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',focus_group)):
        raise ValueError('focus_group must be an exact named primitive group, not a pattern')
    coverage = float(coverage)
    if not 0.1 <= coverage <= 0.95:
        raise ValueError("coverage 必须在 0.1..0.95")
    if int(width) <= 0 or int(height) <= 0:
        raise ValueError("width/height 必须为正整数")

    target, resolution_note = dsh_render_service._resolve_render_sop(node)
    f = float(hou.frame()) if frame is None else float(frame)
    framing_f = f if framing_frame is None else float(framing_frame)
    if not math.isfinite(f) or not math.isfinite(framing_f):
        raise ValueError('frame/framing_frame must be finite')
    direction_label = direction if isinstance(direction, str) else 'view'
    picture, artifact, _artifact_hip_path = dsh_media_output._preview_artifact(
        picture,
        frame=f,
        purpose='model_visual_verification',
        output_policy=output_policy,
        default_label=f'{target.name()}_{direction_label}',
    )
    try:
        image_ext = os.path.splitext(picture)[1].lower()
        if image_ext not in ('.png','.jpg','.jpeg','.bmp','.tga','.tif','.tiff','.exr','.hdr','.pic','.rat'):
            raise ValueError(f'unsupported render_view image extension: {image_ext}; use PNG or EXR')
        before = dsh_geometry_queries._geometry_fingerprint(target, f)
        if before["errors"]:
            raise ValueError(f"目标 {target.path()} cook error：{before['errors']}")
        obj_visibility = dsh_view_state._snapshot_obj_visibility()
        selection = dsh_view_state._snapshot_selection()
    except BaseException as error:
        reservation_errors = dsh_media_output._release_preview_reservation(artifact)
        if reservation_errors:
            raise RuntimeError(str(error) + '; ' + '; '.join(reservation_errors)) from error
        raise
    proxy = proxy_out = cam = aim = rop = None
    result_payload = None
    failure_payload = None
    pending_error = None
    try:
        proxy, proxy_out = dsh_render_service._ensure_render_proxy(target)
        focus_bounds = None
        if focus_group is not None:
            from dsh_geometry_observation import selected_prims
            focus_geometry = proxy_out.geometryAtFrame(framing_f)
            focus_prims = selected_prims(focus_geometry, focus_group)
            focus_bounds = focus_prims[0].boundingBox()
            for prim in focus_prims[1:]: focus_bounds.enlargeToContain(prim.boundingBox())
            # Check the rendered frame too; never silently fall back to an empty group.
            selected_prims(proxy_out.geometryAtFrame(f), focus_group)
            if isolate:
                focus_node = dsh_render_service._owned_node(proxy, 'focus', 'blast')
                focus_node.setInput(0, proxy.node('source'))
                focus_node.parm('grouptype').set('prims')
                focus_node.parm('group').set(focus_group)
                focus_node.parm('negate').set(1)
                proxy_out.setInput(0, focus_node)
                proxy_out.cook(force=True)
        proxy_before = dsh_geometry_queries._geometry_fingerprint(proxy_out, f)
        if proxy_before["errors"]:
            raise ValueError(
                f"agent render proxy 无法读取 {target.path()}：{proxy_before['errors']}"
            )
        framing_fingerprint = dsh_geometry_queries._geometry_fingerprint(target, framing_f)
        if framing_fingerprint["errors"]:
            raise ValueError(
                f"目标 {target.path()} 在 framing_frame={framing_f} cook error："
                f"{framing_fingerprint['errors']}"
            )
        framing_geometry = proxy_out.geometryAtFrame(framing_f)
        if framing_geometry is None or len(framing_geometry.points()) == 0:
            raise ValueError(
                f"目标 {target.path()} 在 framing_frame={framing_f} 没有可取景几何"
            )
        bb = focus_bounds if focus_bounds is not None else framing_geometry.boundingBox()
        if framing_bounds is not None:
            if not isinstance(framing_bounds,(list,tuple)) or len(framing_bounds)!=2 or any(not isinstance(v,(list,tuple)) or len(v)!=3 for v in framing_bounds):
                raise ValueError('framing_bounds must be [min_xyz,max_xyz] in render-proxy world space')
            low,high = [[float(x) for x in v] for v in framing_bounds]
            if not all(math.isfinite(x) for v in (low,high) for x in v) or any(a>b for a,b in zip(low,high)) or low==high:
                raise ValueError('framing_bounds must be finite ordered nonzero bounds')
            bb = hou.BoundingBox(*(low+high))
        reference_depth_bounds = depth_bounds if depth_bounds is not None else framing_bounds
        depth_source = 'explicit' if depth_bounds is not None else 'framing_bounds' if framing_bounds is not None else 'framing_frame_output'
        if reference_depth_bounds is None:
            depth_bb = framing_geometry.boundingBox()
            reference_depth_bounds = [list(depth_bb.minvec()), list(depth_bb.maxvec())]
        center = bb.center()
        extents = bb.sizevec()
        size = max(float(extents[0]), float(extents[1]), float(extents[2]))

        obj = hou.node("/obj")
        out = hou.node("/out")
        cam = dsh_render_service._owned_node(obj, dsh_render_service._RENDER_CAMERA_NAME, "cam")
        cam.parm('projection').set('ortho' if projection == 'orthographic' else 'perspective')
        aim = dsh_render_service._owned_node(obj, dsh_render_service._RENDER_TARGET_NAME, "null")
        # Both supported versions provide Flipbook, but H21.0.440 Work Lights
        # ignore geometry Alpha; its original OpenGL path still composites it.
        # Keep the tested renderer boundary until the supported H21 build also
        # passes the real transparency contract, not only the shared node schema.
        use_flipbook = hou.applicationVersion()[0] >= 22
        rop = dsh_render_service._owned_node(out, dsh_render_service._RENDER_FLIPBOOK_NAME if use_flipbook else dsh_render_service._RENDER_ROP_NAME,
                          "flipbook" if use_flipbook else "opengl")
        obj_service_box = dsh_render_service._render_service_box(
            obj, dsh_service_constants._RENDER_OBJ_BOX_NAME, [proxy, cam, aim])
        out_service_box = dsh_render_service._render_service_box(
            out, dsh_service_constants._RENDER_OUT_BOX_NAME, [rop])
        for infra in (cam, aim, proxy):
            try:
                infra.setDisplayFlag(False)
            except Exception:
                pass
        # 创建 agent 节点可能改变 OBJ flags；渲染前立即还原用户现场。
        dsh_view_state._restore_obj_visibility(obj_visibility)
        aim.parmTuple("t").set([float(center[0]), float(center[1]), float(center[2])])

        from dsh_camera_framing import corners, preview_plan, preview_check, obj_lens
        if isinstance(direction, str):
            named = dsh_view_state._NAMED_DIRECTIONS.get(direction.strip().lower())
            if named is None:
                raise ValueError(
                    f"direction 收到未知名称 {direction!r}；可用："
                    f"{sorted(dsh_view_state._NAMED_DIRECTIONS)} 或三分量向量 [x, y, z]"
                )
            direction = named
        # Service state must not inherit a prior shot's lens/window settings.
        for name, value in {'focal':50.0, 'aperture':41.4214, 'aspect':1.0,
                            'winx':0, 'winy':0, 'winsizex':1, 'winsizey':1,
                            'cropl':0, 'cropr':1, 'cropb':0, 'cropt':1, 'constraints_on':0,
                            'lookatpath':'', 'resx':int(width), 'resy':int(height),
                            'vm_lensshader':''}.items():
            parm = cam.parm(name)
            if parm is not None:
                dsh_parameter_values._clear_animation(parm)
                parm.set(value, follow_parm_reference=False)
        plan = preview_plan([list(bb.minvec()), list(bb.maxvec())], reference_depth_bounds,
                            direction, width, height, coverage=coverage, projection=projection, framing=framing)
        dist = plan['dist']
        d = hou.Vector3(plan['direction'])
        eye = center + d*dist
        matrix = plan['matrix']
        matrix.setAt(3, 0, eye[0]); matrix.setAt(3, 1, eye[1]); matrix.setAt(3, 2, eye[2])
        cam.setWorldTransform(matrix)
        cam.parm('near').set(plan['near'])
        cam.parm('far').set(plan['far'])
        cam.parm('focal').set(plan['focal'])
        if projection == 'orthographic':
            cam.parm('orthowidth').set(plan['orthowidth'])
        # Check the rendered state, not only framing_frame/explicit bounds. A
        # stale A/B envelope must fail, never move the supposedly locked camera.
        current_geo = proxy_out.geometryAtFrame(f)
        current_bb = current_geo.boundingBox()
        rendered_points = corners([list(current_bb.minvec()), list(current_bb.maxvec())])
        if focus_group is not None:
            current_prims = selected_prims(current_geo, focus_group)
            current_bb = current_prims[0].boundingBox()
            for prim in current_prims[1:]: current_bb.enlargeToContain(prim.boundingBox())
        framing_check = preview_check(corners([list(current_bb.minvec()), list(current_bb.maxvec())]),
            rendered_points, cam.worldTransform(), width, height, framing=framing, coverage=coverage, **obj_lens(cam))
        if not framing_check['ok']:
            action = ('Depth clipping is never an intentional crop. Supply shared depth_bounds covering all rendered context, '
                      'or isolate an explicit focus_group; no automatic camera drift.' if not framing_check['depth_check']['ok'] else
                      'full framing_bounds must cover the whole focus, not a local ROI. For a close-up use focus_group or '
                      'framing="detail"; for A/B provide fixed framing_bounds AND depth_bounds covering the test states.')
            if framing == 'full' and 'outside_safe_frame' in framing_check['reasons'] and not framing_check['depth_check']['ok']:
                action += ' full also requires complete focus framing: local ROI needs focus_group or framing="detail", not repeated envelope guesses.'
            raise dsh_errors.CheckpointError('render_view framing failed before render. ' + action,
                                  {**framing_check, 'render_started': False, 'target': target.path(), 'next_action': action})

        output_color = _render_output_color_plan(picture)

        # OpenGL ROP 完全拥有自己的对象/灯光/颜色设置，不消费用户 display/light。
        # 颜色设置由目标文件类型决定：展示格式写 display-encoded sRGB，
        # EXR/HDR 保持 scene-linear。不能把 linear RGB 原样量化进 PNG。
        settings = {
            "camera": cam.path(),
            "vobjects": proxy.path(),
            "forceobjects": proxy.path(),
            "excludeobjects": f"{cam.path()} {aim.path()}",
            "alights": "",
            "forcelights": "",
            "excludelights": "*",
            "shadingmode": "smooth",
            "dof": False,
            "usegeocolor": True,
            "tres": True,
            "override_camerares": True,
            "res1": int(width),
            "res2": int(height),
            **output_color["settings"],
        }
        if use_flipbook:
            # Flipbook has explicit work lighting and no legacy gamma knob.
            # Do not inherit Scene Lights (its default) or the user's viewport.
            if output_color['method'] == 'gamma_fallback':
                raise RuntimeError('H22 Flipbook requires an available encoded sRGB OCIO colorspace; no legacy gamma fallback')
            settings.pop('gamma', None)
            settings.pop('lut', None)
            settings.pop('override_camerares', None)
            settings.update(opsource='obj', scenepath='/obj', sopsource='render',
                            lighting='headlight', worklighttype='headlight',
                            headlightint=1.0, headlightrotate1=22.0, headlightrotate2=22.0,
                            useraytrace=False, motionblur=False, dof=False, bloom=False,
                            uniformfog=False, volumefog=False, onionskin=False, slapcomp=False,
                            ociolooks='', bgimage='', aspect=1.0)
        applied = {name: dsh_render_service._try_set(rop, name, value) for name, value in settings.items()}
        if use_flipbook:
            missing = [name for name, ok in applied.items() if not ok]
            if missing:
                raise RuntimeError(f'Flipbook preview settings unavailable: {missing}')

        color_required = ["colorcorrect"] if use_flipbook else ["colorcorrect", "gamma"]
        if output_color["method"] == "ocio_colorspace":
            color_required.append("ociocolorspace")
        missing_color_settings = [name for name in color_required if not applied.get(name)]
        if missing_color_settings:
            raise RuntimeError(
                "OpenGL ROP 无法应用输出颜色管理参数："
                f"{missing_color_settings}；拒绝生成颜色空间不明的 {picture}"
            )
        output_color = {
            key: value for key, value in output_color.items() if key != "settings"
        }
        try:
            output_color["ocio_config"] = hou.Color.ocio_configPath()
        except Exception:
            output_color["ocio_config"] = None
        output_color["applied"] = {
            "colorcorrect": rop.parm("colorcorrect").rawValue(),
            "gamma": None if use_flipbook else float(rop.parm("gamma").eval()),
            "ocio_colorspace": rop.parm("ociocolorspace").eval(),
        }

        # Allocation already returned a concrete file, not a new caller
        # template. Protect literal HIP-name characters at this second entry.
        rendered = render_frame(rop, picture=dsh_media_output._literal_houdini_path(picture), frame=f)
        check = None
        if rendered.get("file_bytes"):
            try:
                check = dsh_image_pixels.render_check(rendered["output"])
            except Exception as error:
                check = {"error": str(error)}
        after = dsh_geometry_queries._geometry_fingerprint(target, f)
        proxy_after = dsh_geometry_queries._geometry_fingerprint(proxy_out, f)
        stale = before["signature"] != after["signature"]
        proxy_stale = proxy_before["signature"] != proxy_after["signature"]
        render_warnings = list(dict.fromkeys(before["warnings"] + proxy_before["warnings"]))
        validation = _render_validation(
            rendered,
            check,
            stale or proxy_stale,
            pixel_supported=image_ext not in ('.exr','.hdr','.pic','.rat'),
            warnings=render_warnings,
        )
        result_payload = {
            **validation,
            "artifact": artifact,
            "preview_backend": "flipbook_vulkan" if use_flipbook else "opengl_legacy",
            "target": target.path(),
            "resolved_from": dsh_node_access._resolve(node).path(),
            "proxy": proxy.path(),
            "proxy_output": proxy_out.path(),
            "camera": cam.path(),
            "rop": rop.path(),
            "render_service": {
                "persistent": True,
                "delete_during_session": False,
                "obj_network_box": obj_service_box.name(),
                "out_network_box": out_service_box.name(),
            },
            "output": rendered["output"],
            "frame": f,
            "file_bytes": rendered["file_bytes"],
            "errors": validation['errors'],
            "warnings": render_warnings,
            "stale": stale or proxy_stale,
            "source_fingerprint_before": before,
            "source_fingerprint_after": after,
            "proxy_signature_before": proxy_before["signature"],
            "proxy_signature_after": proxy_after["signature"],
            "framing": {
                **framing_check,
                "focus_group": focus_group, "isolated": isolate, "projection": projection,
                "bounds": [[float(x) for x in bb.minvec()],[float(x) for x in bb.maxvec()]],
                "bounds_source": 'explicit' if framing_bounds is not None else 'focus_group' if focus_group else 'output',
                "depth_bounds": plan['depth_bounds'], "depth_bounds_source": depth_source,
                "coordinate_space": 'render proxy world space',
                "mode": framing,
                "frame": framing_f,
                "coverage": coverage,
                "center": [float(x) for x in center],
                "size": float(size),
                "dist": round(float(dist), 6),
                "eye": [float(x) for x in eye],
                "direction": [float(x) for x in d],
                "source_signature": framing_fingerprint["signature"],
            },
            "rop_settings_applied": applied,
            "output_color": output_color,
            "check": check,
            "pixels": check,
        }
        if resolution_note:
            result_payload["note"] = resolution_note
        if result_payload["stale"]:
            result_payload["stale_reason"] = (
                "target/proxy geometry changed during visual verification；"
                "不要据此宣称成功，请重新检查并渲染"
            )
        return result_payload
    except BaseException as error:
        pending_error = error
        if isinstance(error, dsh_errors.CheckpointError):
            failure_payload = error.evidence
        raise
    finally:
        restore_errors = dsh_media_output._release_preview_reservation(artifact)
        restore_errors.extend(dsh_view_state._restore_obj_visibility(obj_visibility))
        restore_errors.extend(dsh_view_state._restore_selection(selection))
        # _ensure_render_proxy may fail after binding its source but before it
        # returns. The service is intentionally non-undoable, so idle that
        # owned partial proxy here instead of relying on Bridge rollback.
        if proxy is None:
            partial = hou.node('/obj/' + dsh_render_service._RENDER_PROXY_NAME)
            if (partial is not None and partial.userData(dsh_service_constants._RENDER_OWNER_KEY) == dsh_service_constants._RENDER_OWNER_VALUE
                    and partial.userData('dsh_render_state') == 'active'):
                proxy = partial
        if proxy is not None:
            try:
                proxy.setDisplayFlag(False)
            except Exception as error:
                restore_errors.append(f"{proxy.path()}: {error}")
            # 空闲 proxy 不长期引用用户节点；下一次 render_view 会重新绑定显式 SOP。
            try:
                source = proxy.node("source")
                if (source is not None and source.userData(dsh_service_constants._RENDER_OWNER_KEY) == dsh_service_constants._RENDER_OWNER_VALUE
                        and source.parm("objpath1") is not None):
                    source.parm("objpath1").set("")
                    last_target = target.path()
                    last_frame = result_payload.get("frame") if result_payload else f
                    last_output = result_payload.get("output") if result_payload else None
                    proxy.setUserData("dsh_render_state", "idle")
                    proxy.setUserData("dsh_last_target", last_target)
                    proxy.setUserData("dsh_last_frame", str(last_frame))
                    if last_output:
                        proxy.setUserData("dsh_last_output", str(last_output))
                    source.setComment(
                        "Temporary render_view source; objpath1 is bound only while rendering "
                        "and cleared afterward.\n"
                        f"Last target: {last_target}\nLast frame: {last_frame}"
                    )
            except Exception as error:
                restore_errors.append(f"{proxy.path()}/source: {error}")
        if failure_payload is not None:
            failure_payload['user_state_restored'] = not restore_errors
            if restore_errors:
                failure_payload['restore_errors'] = restore_errors
        elif pending_error is not None and restore_errors:
            raise dsh_errors.CheckpointError('render_view failed and user state restoration failed',
                                  {'ok':False,'user_state_restored':False,'restore_errors':restore_errors,
                                   'original_error':str(pending_error)[:400]}) from pending_error
        if result_payload is not None:
            result_payload["user_state_restored"] = not restore_errors
            if restore_errors:
                result_payload["restore_errors"] = restore_errors
                result_payload['ok'] = False
                result_payload['errors'].extend(f'user state restore failed: {e}' for e in restore_errors)
