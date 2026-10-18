"""Houdini media output. Executed on the Bridge owning thread."""
from __future__ import annotations

import os
import contextlib
import time
import hou
from dsh_project_paths import directory_path as _project_directory
import dsh_errors
import dsh_ownership
import dsh_scene


_PRODUCED_IMAGES: list = []


@contextlib.contextmanager
def image_scope():
    """Request-local output collector; nested calls cannot erase outer images."""
    global _PRODUCED_IMAGES
    previous = _PRODUCED_IMAGES
    images = []
    _PRODUCED_IMAGES = images
    try:
        yield images
    finally:
        _PRODUCED_IMAGES = previous


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".webp"}


_PREVIEW_IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff",
    ".exr", ".hdr", ".pic", ".rat",
}


def report_image(path: str) -> str:
    """登记一张本次 exec 产出的图片（返回绝对路径）。动词外手写的产出也可登记。

    只登记图片扩展名——geometry ROP 的 .bgeo 等产物不该进 media relay。
    """
    p = os.path.abspath(path)
    if os.path.splitext(p)[1].lower() in _IMAGE_EXTS and p not in _PRODUCED_IMAGES:
        _PRODUCED_IMAGES.append(p)
    return p


def _resolve_output_path(path, *, frame, default_subdir=None) -> str:
    """Resolve output files BEFORE mutation; never use the process cwd.

    A bare filename goes to $HIP/default_subdir (dsh-artifacts/renders by default); a relative subpath is $HIP
    relative. Absolute paths remain explicit caller intent except repository
    paths. Relative traversal/junction escapes and extensionless files fail.
    """
    default_subdir = _project_directory('render') if default_subdir is None else default_subdir
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw.strip() or '\x00' in raw:
        raise ValueError('output path must be a nonempty file path')
    expanded = hou.expandStringAtFrame(raw, float(frame)).replace('\\', '/')
    if not os.path.splitext(os.path.basename(expanded))[1]:
        raise ValueError('output extension is required; use .png for previews, .exr for linear images or the intended cache extension')
    if not os.path.isabs(expanded):
        if os.path.splitdrive(expanded)[0] or not dsh_scene.scene_info()['has_named_path']:
            raise ValueError('relative output requires a named HIP; confirm a project and use scene_save_as first')
        hip = os.path.realpath(os.path.dirname(hou.hipFile.path()))
        relative = expanded if '/' in expanded else os.path.join(default_subdir, expanded)
        target = os.path.realpath(os.path.join(hip, relative))
        if os.path.commonpath([hip, target]) != hip:
            raise ValueError(f'relative output is outside $HIP: {raw!r}')
    else:
        target = os.path.realpath(expanded)
    repo = os.path.realpath(os.path.join(os.path.dirname(__file__), '..', '..'))
    try:
        in_repo = os.path.commonpath([repo, target]) == repo
    except ValueError:
        in_repo = False
    if in_repo:
        raise ValueError('output cannot be written into the plugin repository; choose the HIP project directory')
    return target.replace('\\', '/')


def _preview_artifact(path, *, frame, purpose, output_policy, default_label,
                      default_subdir, allowed_extensions=_PREVIEW_IMAGE_EXTS):
    """Resolve preview output policy before renderer/viewer state changes."""
    if output_policy not in ("managed", "delivery", "explicit"):
        raise ValueError("output_policy must be 'managed', 'delivery' or 'explicit'")
    scene = dsh_scene.scene_info()
    hip_path = scene["hip_path"] if scene["has_named_path"] else None
    from dsh_preview_paths import allocate_managed, explicit_artifact, _safe_component
    if output_policy in ("managed", "delivery"):
        # Validate literal caller input before expansion/allocation. Only this
        # pure filename check proves zero scene writes; later failures keep
        # their own recovery semantics (including expression/renderer effects).
        if isinstance(path, str):
            try:
                _safe_component(path, field="filename")
            except ValueError as error:
                raise dsh_errors.CheckpointError(str(error), {
                    'ok': False, 'phase': 'output_path_preflight', 'scene_writes': 0,
                    'field': 'filename', 'output_policy': output_policy,
                }) from error
        artifact = allocate_managed(
            hip_path,
            path,
            frame=frame,
            purpose=purpose,
            owner_session=dsh_ownership.current_session(),
            repository_root=os.path.join(os.path.dirname(__file__), '..', '..'),
            default_label=default_label,
            default_extension=".png",
            allowed_extensions=allowed_extensions,
            expand=lambda value: hou.expandStringAtFrame(value, float(frame)),
            output_policy=output_policy,
        )
        return artifact["actual_path"], artifact, hip_path
    if path is None:
        frame_tag = str(float(frame)).replace('-', 'm').replace('.', 'p')
        path = f"{default_label}_{time.time_ns()}_f{frame_tag}.png"
    target = _resolve_output_path(path, frame=frame, default_subdir=default_subdir)
    extension = os.path.splitext(target)[1].lower()
    if allowed_extensions and extension not in allowed_extensions:
        raise ValueError(f"unsupported preview image extension: {extension}; use PNG or EXR")
    return target, explicit_artifact(hip_path, target, frame=frame, purpose=purpose), hip_path


def _release_preview_reservation(artifact) -> list[str]:
    from dsh_preview_paths import release_reservation
    return release_reservation(artifact)
