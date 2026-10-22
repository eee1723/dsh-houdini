"""Houdini viewport. Executed on the Bridge owning thread."""
from __future__ import annotations

import hashlib
import math
import os
import re
import time
import hou
import dsh_cook_control as _cook_control
import dsh_errors
import dsh_image_pixels
import dsh_media_output
import dsh_node_access


_CLEAN_GUIDES = (
    "XYPlane", "YZPlane", "XZPlane",
    "OriginGnomon", "FloatingGnomon",
    "NodeHandles", "NodeGuides",
    "ObjectNames", "ObjectPaths",
    "CameraMask", "SafeArea",
    "ShowDrawTime", "ViewPivot",
)


def _display_bbox(n):
    """节点的显示几何 bbox：obj 级取其 displayNode，SOP 直接取。"""
    _cook_control.require_evaluation('display geometry bounds')
    try:
        d = n.displayNode()
        if d is not None:
            return d.geometry().boundingBox()
    except Exception:
        pass
    return n.geometry().boundingBox()


def _webview_was_minimized():
    """Return the pre-capture minimized state when the optional WebView exists."""
    try:
        import dsh_webview
        win = getattr(dsh_webview, "_window", None)
        return None if win is None else bool(win.isMinimized())
    except Exception:
        return None


def _restore_webview_window(was_minimized=None) -> None:
    """截图后还原被最小化的内嵌 web UI 窗口（dsh_webview）。

    用户报告（2026-08-18）：agent 截图时 agent 窗口会最小化，要手动从
    任务栏点回。只在确实处于最小化状态时还原——用户只是切去 Houdini
    干活（失焦/被遮）时不抢焦点。可选依赖：webview 未开过/导入失败就静默。
    """
    try:
        import dsh_webview
    except Exception:
        return
    win = getattr(dsh_webview, "_window", None)
    if win is None:
        return
    try:
        if was_minimized is not True and win.isMinimized():
            win.showNormal()
            dsh_webview._bring_to_front(win)
    except Exception:
        pass


def _viewport_camera_state(camera) -> tuple:
    """Comparable readback for the documented H21/H22 viewport-camera surface."""
    values = []
    for name in ('translation', 'rotation', 'pivot', 'aperture', 'aspectRatio',
                 'clipPlanes', 'focalLength', 'focalUnitScale', 'orthoWidth',
                 'windowOffset', 'windowSize', 'isOrthographic'):
        method = getattr(camera, name, None)
        if not callable(method):
            raise RuntimeError(f'viewport camera readback unavailable: {name}')
        value = method()
        if isinstance(value, (hou.Matrix3, hou.Matrix4)):
            value = tuple(float(item) for item in value.asTuple())
        elif isinstance(value, (tuple, list, hou.Vector2, hou.Vector3, hou.Vector4)):
            value = tuple(float(item) for item in value)
        elif isinstance(value, bool):
            value = bool(value)
        else:
            value = float(value)
        values.append((name, value))
    return tuple(values)


def _viewport_camera_states_equal(before, after, tolerance=1e-8) -> bool:
    before_map, after_map = dict(before), dict(after)
    if set(before_map) != set(after_map):
        return False
    for name_a, value_a in before:
        if name_a == 'orthoWidth' and not before_map['isOrthographic'] and not after_map['isOrthographic']:
            continue  # inactive perspective-camera field is normalized by setDefaultCamera
        value_b = after_map[name_a]
        if isinstance(value_a, tuple):
            if not isinstance(value_b, tuple) or len(value_a) != len(value_b):
                return False
            if any(not math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=tolerance)
                   for a, b in zip(value_a, value_b)):
                return False
        elif isinstance(value_a, bool):
            if value_a is not value_b:
                return False
        elif not math.isclose(float(value_a), float(value_b), rel_tol=0.0, abs_tol=tolerance):
            return False
    return True


def _same_network_item(left, right) -> bool:
    if left is right:
        return True
    try:
        return int(left.sessionId()) == int(right.sessionId())
    except Exception:
        try:
            return left.path() == right.path()
        except Exception:
            return False


def _readable_tga(path: str) -> bool:
    """Bounded structural completeness check for common TGA flipbook output."""
    if os.path.splitext(path)[1].lower() != '.tga':
        return False
    try:
        with open(path, 'rb') as source:
            data = source.read(dsh_image_pixels._MAX_IMAGE_FILE_BYTES + 1)
        if len(data) > dsh_image_pixels._MAX_IMAGE_FILE_BYTES or len(data) < 18:
            return False
        ident, cmap, kind = data[0], data[1], data[2]
        cmap_len = int.from_bytes(data[5:7], 'little')
        cmap_bits = data[7]
        width = int.from_bytes(data[12:14], 'little')
        height = int.from_bytes(data[14:16], 'little')
        depth = data[16]
        if not width or not height or width * height > dsh_image_pixels._MAX_IMAGE_PIXELS:
            return False
        if cmap not in (0, 1) or kind not in (2, 3, 10, 11) or depth not in (8, 16, 24, 32):
            return False
        offset = 18 + ident + ((cmap_len * cmap_bits + 7) // 8 if cmap else 0)
        bytes_per_pixel = (depth + 7) // 8
        pixels = width * height
        if kind in (2, 3):
            return len(data) >= offset + pixels * bytes_per_pixel
        produced = 0
        while produced < pixels and offset < len(data):
            header = data[offset]; offset += 1
            count = (header & 0x7f) + 1
            payload = bytes_per_pixel if header & 0x80 else count * bytes_per_pixel
            if offset + payload > len(data):
                return False
            offset += payload; produced += count
        return produced == pixels
    except Exception:
        return False


def _screenshot_readable(path: str) -> bool:
    return (dsh_image_pixels._read_pixels_qt(path) is not None or dsh_image_pixels._read_pixels_png(path) is not None
            or _readable_tga(path))


def viewport_screenshot(path=None, frame=None, clean=True, frame_target=None,
                        textures=None, backface_cull=False, *,
                        output_policy: str = "managed") -> dict:
    """Capture the selected viewport with bounded freshness and full restoration.

    Managed output (the default) accepts only an omitted filename or safe
    basename and writes under ``$HIP/dsh-artifacts/checks/previews/<HIPNAME>/<run-id>/``. Deliberate
    Delivery images use ``output_policy='delivery'`` under ``$HIP/dsh-artifacts/renders/<HIPNAME>``;
    custom destinations use ``output_policy='explicit'``; an explicit bare
    filename goes under ``$HIP/dsh-artifacts/checks/previews/<HIPNAME>/``. The capture is a user-screen
    diagnostic: readable pixels are required, but visual semantics remain
    unverified.  H21/H22 require stashed flipbook and viewport-camera state;
    unsupported restoration combinations reject before mutation.
    """
    if not hou.isUIAvailable():
        raise ValueError("viewport_screenshot 需要 Houdini GUI（当前无 UI）；headless 环境请用 render_frame")
    f = float(hou.frame()) if frame is None else float(frame)
    if not math.isfinite(f):
        raise ValueError('frame must be finite')
    viewer = hou.ui.curDesktop().paneTabOfType(hou.paneTabType.SceneViewer)
    if viewer is None:
        raise ValueError("当前桌面没有 Scene Viewer 面板——请先打开一个场景视口")
    vp = viewer.curViewport()
    if vp is None:
        raise ValueError("Scene Viewer 没有活动视口")
    st = vp.settings()

    # Resolve identity only. Geometry is evaluated after path validation and
    # after switching to the requested frame inside the protected lifecycle.
    target_node = None
    if frame_target is True:
        try:
            frame_target = next((c for c in hou.node('/obj').children() if c.isDisplayFlagSet()), None)
        except Exception:
            frame_target = None
    if frame_target is not None:
        target_node = dsh_node_access._resolve(frame_target)
    framed = target_node.path() if target_node is not None else None

    live_settings = viewer.flipbookSettings()
    stash_settings = getattr(live_settings, 'stash', None)
    if not callable(stash_settings):
        raise RuntimeError('copied flipbook settings are unavailable on this Houdini build')
    settings = stash_settings()
    if settings is None or settings is live_settings:
        raise RuntimeError('flipbook settings stash did not return an independent copy')
    leave_getter = getattr(live_settings, 'leaveFrameAtEnd', None)
    live_before = (live_settings.output(), live_settings.outputToMPlay(), live_settings.frameRange(),
                   leave_getter() if callable(leave_getter) else None)

    camera_snapshot = None
    camera_state_before = None
    linked_camera = None
    camera_lock_before = None
    if target_node is not None:
        camera = vp.defaultCamera()
        stash_camera = getattr(camera, 'stash', None)
        if not callable(stash_camera) or not callable(getattr(vp, 'setDefaultCamera', None)):
            raise RuntimeError('full viewport camera restoration is unavailable on this Houdini build')
        camera_snapshot = stash_camera()
        camera_state_before = _viewport_camera_state(camera)
        for name in ('camera', 'setCamera', 'useDefaultCamera', 'isCameraLockedToView', 'lockCameraToView'):
            if not callable(getattr(vp, name, None)):
                raise RuntimeError(f'viewport camera association restoration is unavailable: {name}')
        linked_camera = vp.camera()
        camera_lock_before = bool(vp.isCameraLockedToView())

    path, artifact, artifact_hip_path = dsh_media_output._preview_artifact(
        path, frame=f, purpose='viewport_diagnostic', output_policy=output_policy,
        default_label='viewport',
        allowed_extensions={'.png', '.jpg', '.jpeg', '.bmp', '.tga'})

    import glob as _glob
    stem, ext = os.path.splitext(path)

    def candidate_allowed(candidate):
        if os.path.normcase(os.path.abspath(candidate)) == os.path.normcase(os.path.abspath(path)):
            return True
        if not float(f).is_integer():
            return False
        if os.path.dirname(os.path.abspath(candidate)) != os.path.dirname(os.path.abspath(path)):
            return False
        name = os.path.basename(candidate)
        base = os.path.basename(stem)
        if not name.lower().endswith(ext.lower()) or not name.startswith(base):
            return False
        suffix = name[len(base):len(name) - len(ext)]
        match = re.fullmatch(r'[._-](\d+)', suffix)
        return bool(match and int(match.group(1)) == int(f))

    def candidates():
        found = {os.path.normcase(os.path.abspath(path)): path}
        pattern = _glob.escape(stem) + '*' + _glob.escape(ext)
        for item in _glob.glob(pattern):
            if candidate_allowed(item):
                found.setdefault(os.path.normcase(os.path.abspath(item)), item)
        return sorted(found.values())

    def fingerprint(candidate):
        if not os.path.isfile(candidate):
            return None
        stat = os.stat(candidate)
        digest = hashlib.sha256()
        with open(candidate, 'rb') as handle:
            digest.update(handle.read(64 * 1024))
            if stat.st_size > 64 * 1024:
                handle.seek(max(0, stat.st_size - 64 * 1024))
                digest.update(handle.read(64 * 1024))
        return (int(stat.st_size), int(stat.st_mtime_ns), digest.hexdigest())

    original_frame = float(hou.frame())
    webview_was_minimized = _webview_was_minimized()
    before_files = {}
    actual = None
    capture_error = None
    capture_unresolved = False
    dispatch_attempted = False
    capture_settled = False
    restore_errors = []
    saved_guides = []
    saved_textures = None
    saved_backface = None
    refplane = None
    refplane_was = False
    lock_attempted = detach_attempted = detached = False

    try:
        out_dir = os.path.dirname(path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        before_files = {candidate: fingerprint(candidate) for candidate in candidates()}

        # A linked camera is detached before frame or viewport manipulation.
        if target_node is not None and linked_camera is not None:
            if camera_lock_before:
                lock_attempted = True
                vp.lockCameraToView(False)
                if vp.isCameraLockedToView():
                    raise RuntimeError('viewport camera remained locked after unlock')
            detach_attempted = True
            vp.useDefaultCamera()
            detached = vp.camera() is None
            if not detached:
                raise RuntimeError('viewport camera remained linked after detachment')

        hou.setFrame(f)
        if float(hou.frame()) != f:
            raise RuntimeError('requested capture frame was not applied')

        if clean:
            try:
                refplane = viewer.referencePlane()
                refplane_was = bool(refplane.isVisible())
            except Exception:
                refplane = None
            if refplane is not None and refplane_was:
                refplane.setIsVisible(False)
            for name in _CLEAN_GUIDES:
                guide = getattr(hou.viewportGuide, name, None)
                if guide is None:
                    continue
                try:
                    enabled = bool(st.guideEnabled(guide))
                except Exception:
                    continue
                if enabled:
                    saved_guides.append(guide)
                    st.enableGuide(guide, False)
        if textures is not None:
            saved_textures = bool(st.displayTextures())
            st.setDisplayTextures(bool(textures))
        if backface_cull:
            saved_backface = bool(st.removeBackfaces())
            st.setRemoveBackfaces(True)
        if target_node is not None:
            vp.frameBoundingBox(_display_bbox(target_node))

        settings.output(path)
        settings.outputToMPlay(False)
        settings.frameRange((f, f))
        leave_at_end = getattr(settings, 'leaveFrameAtEnd', None)
        if callable(leave_at_end):
            leave_at_end(False)
        dispatch_attempted = True
        viewer.flipbook(viewport=vp, settings=settings)

        deadline = time.time() + 15
        stable = {}
        while time.time() < deadline:
            changed = []
            for candidate in candidates():
                current = fingerprint(candidate)
                if current is not None and current[0] > 0 and current != before_files.get(candidate):
                    changed.append((candidate, current))
            if len(changed) > 1:
                raise RuntimeError(f"flipbook produced ambiguous screenshot candidates: {[item[0] for item in changed]}")
            if changed:
                candidate, current = changed[0]
                if _screenshot_readable(candidate):
                    if stable.get(candidate) == current:
                        actual = candidate
                        break
                    stable = {candidate: current}
                else:
                    stable = {}
            time.sleep(0.2)
        else:
            capture_unresolved = True
            raise RuntimeError(f"flipbook did not produce a stable readable screenshot: {path}")
    except BaseException as error:
        capture_error = error
        if dispatch_attempted and not capture_settled:
            capture_unresolved = True
    finally:
        # Restore display state first while the viewport remains safely detached.
        if refplane is not None and refplane_was:
            try:
                refplane.setIsVisible(True)
                if not refplane.isVisible():
                    raise RuntimeError('readback remained hidden')
            except Exception as error:
                restore_errors.append(f'reference plane: {error}')
        for guide in saved_guides:
            try:
                st.enableGuide(guide, True)
                if not st.guideEnabled(guide):
                    raise RuntimeError('readback remained disabled')
            except Exception as error:
                restore_errors.append(f'viewport guide: {error}')
        if saved_textures is not None:
            try:
                st.setDisplayTextures(saved_textures)
                if bool(st.displayTextures()) != saved_textures:
                    raise RuntimeError('readback mismatch')
            except Exception as error:
                restore_errors.append(f'textures: {error}')
        if saved_backface is not None:
            try:
                st.setRemoveBackfaces(saved_backface)
                if bool(st.removeBackfaces()) != saved_backface:
                    raise RuntimeError('readback mismatch')
            except Exception as error:
                restore_errors.append(f'backface culling: {error}')

        # If detachment partially failed, retry a safe detach before any
        # viewport-camera snapshot is applied. Never setDefaultCamera while a
        # linked, locked scene camera remains active.
        safe_default = target_node is not None and linked_camera is None
        if target_node is not None and linked_camera is not None:
            try:
                if vp.isCameraLockedToView():
                    vp.lockCameraToView(False)
                if vp.camera() is not None:
                    vp.useDefaultCamera()
                safe_default = vp.camera() is None and not vp.isCameraLockedToView()
                if not safe_default:
                    raise RuntimeError('could not obtain a safely detached viewport')
            except Exception as error:
                restore_errors.append(f'camera detachment: {error}')
                safe_default = False
        try:
            if float(hou.frame()) != original_frame:
                hou.setFrame(original_frame)
            if float(hou.frame()) != original_frame:
                raise RuntimeError('frame readback mismatch')
        except Exception as error:
            restore_errors.append(f'frame: {error}')

        if target_node is not None and safe_default:
            try:
                vp.setDefaultCamera(camera_snapshot)
                camera_state_after = _viewport_camera_state(vp.defaultCamera())
                if not _viewport_camera_states_equal(camera_state_before, camera_state_after):
                    raise RuntimeError(f'viewport camera readback mismatch: before={camera_state_before!r}, after={camera_state_after!r}')
            except Exception as error:
                restore_errors.append(f'viewport camera: {error}')
        if target_node is not None and linked_camera is not None:
            try:
                vp.setCamera(linked_camera)
                if not _same_network_item(vp.camera(), linked_camera):
                    raise RuntimeError('linked camera readback mismatch')
            except Exception as error:
                restore_errors.append(f'linked camera: {error}')
            try:
                vp.lockCameraToView(camera_lock_before)
                if bool(vp.isCameraLockedToView()) != camera_lock_before:
                    raise RuntimeError('camera lock readback mismatch')
            except Exception as error:
                restore_errors.append(f'camera lock: {error}')

        try:
            leave_now = leave_getter() if callable(leave_getter) else None
            live_after = (live_settings.output(), live_settings.outputToMPlay(),
                          live_settings.frameRange(), leave_now)
            if live_after != live_before:
                raise RuntimeError('interactive flipbook settings changed')
        except Exception as error:
            restore_errors.append(f'flipbook settings: {error}')
        _restore_webview_window(webview_was_minimized)

    from dsh_preview_paths import retain_reservation, with_actual_path
    validated_artifact = None
    actual_validated = False
    try:
        validated_artifact = with_actual_path(artifact, actual or path, artifact_hip_path)
        actual_validated = actual is not None
        if actual_validated:
            capture_settled = True
    except Exception as error:
        capture_error = capture_error or error
    if dispatch_attempted and not capture_settled:
        capture_unresolved = True
    if capture_unresolved:
        retain_reservation(artifact)
    else:
        restore_errors.extend(dsh_media_output._release_preview_reservation(artifact))
    if validated_artifact is not None:
        if artifact.get('reservation_retained'):
            validated_artifact['reservation_retained'] = True
        artifact = validated_artifact
    else:
        artifact = {key: value for key, value in artifact.items()
                    if not key.startswith('_reservation')}
    if actual_validated:
        dsh_media_output.report_image(actual)
    failure_evidence = {
        'ok': False, 'path': actual or path, 'artifact': artifact, 'frame': f,
        'fresh': actual_validated, 'file_status': 'passed' if actual_validated else 'failed',
        'capture_unresolved': capture_unresolved,
        'semantic_status': 'unverified', 'user_state_restored': not restore_errors,
        'restore_errors': restore_errors,
        'scope': 'frame, copied flipbook settings, changed viewport guides/display settings, framing camera and camera association',
    }
    if capture_error is not None or restore_errors:
        reasons = ([str(capture_error)] if capture_error is not None else [])
        reasons.extend(f'restore failed: {item}' for item in restore_errors)
        failure_evidence['errors'] = reasons
        raise dsh_errors.CheckpointError('viewport screenshot failed: ' + '; '.join(reasons), failure_evidence)

    result: dict = {
        'ok': True, 'path': actual, 'artifact': artifact,
        'viewer': viewer.name(), 'viewport': vp.name(), 'frame': f,
        'bytes': os.path.getsize(actual), 'fresh': True, 'file_status': 'passed',
        'semantic_status': 'unverified', 'user_state_restored': True,
        'restore_errors': [],
        'scope': 'frame, copied flipbook settings, changed viewport guides/display settings, framing camera and camera association',
        'clean': bool(clean),
    }
    if framed is not None:
        result['framed'] = framed
    return result
