"""Houdini scene. Executed on the Bridge owning thread."""
from __future__ import annotations

import math
import os
import hou
import dsh_errors


def scene_info() -> dict:
    """只读场景/时间线、HIP单位及project_layout目录；不创建目录、不证明写权限。"""
    from dsh_context import hip_file_state, unit_length_meters
    hip = hip_file_state()
    file_exists = hip['file_exists']
    has_unsaved_changes = bool(hou.hipFile.hasUnsavedChanges())
    ui_available = bool(hou.isUIAvailable())
    return {
        **hip,
        "hip_name": hou.hipFile.name(),
        "has_unsaved_changes": has_unsaved_changes,
        "dirty_reliable": ui_available,
        "clean_on_disk": file_exists and not has_unsaved_changes if ui_available else None,
        "version": hou.applicationVersionString(),
        "unit_length_meters": unit_length_meters(),
        "update_mode": {hou.updateMode.AutoUpdate:'auto', hou.updateMode.Manual:'manual', hou.updateMode.OnMouseUp:'on_mouse_up'}[hou.updateModeSetting()],
        "fps": float(hou.fps()),
        "frame": float(hou.frame()),
        "time": float(hou.time()),
        "frame_range": [float(v) for v in hou.playbar.frameRange()],
        "playback_range": [float(v) for v in hou.playbar.playbackRange()],
        "range_restricted": bool(hou.playbar.isRangeRestricted()),
        "playing": bool(hou.playbar.isPlaying()),
        "ui_available": ui_available,
    }


def scene_save(expected_path: str | None = None) -> dict:
    """保存当前已命名 HIP，并回报真实 dirty/file 状态；不承担 Save As。"""
    path = os.path.abspath(hou.hipFile.path())
    if not scene_info()["has_named_path"]:
        raise ValueError("当前 HIP 尚未命名；确认目标路径后用 scene_save_as，或先在 Houdini UI 中 Save As")
    if expected_path is not None:
        expected = os.path.abspath(hou.expandString(str(expected_path)))
        if os.path.normcase(expected) != os.path.normcase(path):
            raise ValueError(f"expected_path 与当前 HIP 不一致：expected={expected!r}, current={path!r}")
    dirty_before = bool(hou.hipFile.hasUnsavedChanges())
    from dsh_scene_recovery import after_save
    try:
        hou.hipFile.save()
    except BaseException:
        after_save(path, False)
        raise
    after_save(path, True)
    dirty_after = bool(hou.hipFile.hasUnsavedChanges())
    dirty_reliable = bool(hou.isUIAvailable())
    if not os.path.isfile(path):
        raise RuntimeError(f"hou.hipFile.save() 返回后文件不存在：{path}")
    stat = os.stat(path)
    if stat.st_size == 0:
        raise RuntimeError(f"保存后 HIP 文件为空：{path}")
    return {
        "path": path,
        "dirty_before": dirty_before,
        "dirty_after": dirty_after,
        "dirty_reliable": dirty_reliable,
        "clean_on_disk": not dirty_after if dirty_reliable else None,
        "bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def scene_save_as(path: str, expected_current_path: str, reason: str,
                  overwrite: bool = False) -> dict:
    """Save As to an explicitly authorized absolute HIP path; never load/clear.

    ``expected_current_path`` must match the current scene. Existing targets
    require explicit ``overwrite=True`` and user authorization in ``reason``.
    File I/O is not undoable; a failed save may leave a partial new target.
    After a workspace change, use Open Workspace to select the matching DSH session.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason 必须记录用户对目标路径/覆盖的明确授权")
    if not isinstance(overwrite, bool):
        raise ValueError("overwrite 必须是 bool")
    current = os.path.abspath(hou.hipFile.path())
    if not isinstance(expected_current_path, str) or not expected_current_path:
        raise ValueError("expected_current_path 必须来自 scene_info().hip_path")
    expected = os.path.abspath(hou.expandString(expected_current_path))
    if os.path.normcase(expected) != os.path.normcase(current):
        raise ValueError(f"expected_current_path 不匹配：{expected!r} != {current!r}")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path 必须是明确的绝对 HIP 路径")
    target = hou.expandString(path)
    if not os.path.isabs(target) or os.path.splitext(target)[1].lower() not in (".hip", ".hiplc", ".hipnc"):
        raise ValueError("path 必须是绝对路径，扩展名为 .hip/.hiplc/.hipnc")
    target = os.path.realpath(target)
    from dsh_executor_registry import require_save_target
    require_save_target(target)
    repo = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    try:
        in_repo = os.path.commonpath([repo, target]) == repo
    except ValueError:
        in_repo = False
    if in_repo:
        raise ValueError("HIP 产物不能保存到插件仓库；请选择用户项目目录")
    existed = os.path.lexists(target)
    if existed and not overwrite:
        raise ValueError(f"target exists: {target}; 当前文件请用 scene_save，另存覆盖需要明确授权 overwrite=True")
    if existed and not os.path.isfile(target):
        raise ValueError(f"target is not a regular file: {target}")
    dirty_before = bool(hou.hipFile.hasUnsavedChanges())
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if not overwrite:
        # Reserve without a check-then-overwrite race. Only a new empty file is
        # created; a concurrent existing target causes FileExistsError.
        with open(target, "xb"):
            pass
    try:
        # H21 file-event callbacks do not consistently escape Windows backslashes.
        hou.hipFile.save(file_name=target.replace("\\", "/"))
        from dsh_scene_recovery import after_save
        after_save(target, True)
        if os.path.normcase(os.path.realpath(hou.hipFile.path())) != os.path.normcase(target):
            raise RuntimeError("Save As 返回后当前 HIP 路径与目标不一致")
        stat = os.stat(target)
        if stat.st_size == 0:
            raise RuntimeError("Save As 返回后目标 HIP 为空")
    except BaseException:
        # Restoring the in-memory name is not a claim that disk I/O rolled back.
        hou.hipFile.setName(current.replace("\\", "/"))
        raise
    reliable = bool(hou.isUIAvailable())
    dirty_after = bool(hou.hipFile.hasUnsavedChanges())
    return {"path": target, "previous_path": current, "reason": reason.strip(),
            "overwrote": existed, "dirty_before": dirty_before, "dirty_after": dirty_after,
            "dirty_reliable": reliable, "clean_on_disk": not dirty_after if reliable else None,
            "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "workspace_changed": os.path.normcase(os.path.dirname(current)) != os.path.normcase(os.path.dirname(target)),
            "note": "文件写入不能撤销。更换工程目录后，请选择 DSH-Houdini → Open Workspace。"}


def _frame_pair(value, label: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} 必须是 [start, end]")
    start, end = float(value[0]), float(value[1])
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError(f"{label} 必须是有限帧数")
    if end < start:
        raise ValueError(f"{label} end 不能小于 start：{start}, {end}")
    return start, end


def set_timeline(fps=None, frame_range=None, playback_range=None,
                 current_frame=None) -> dict:
    """设置时间线；先验证所有字段，写入失败恢复原fps、范围与当前帧。"""
    changed = {}
    try:
        if all(value is None for value in (fps, frame_range, playback_range, current_frame)):
            raise ValueError("至少提供 fps/frame_range/playback_range/current_frame 一项")
        if fps is not None:
            value = float(fps)
            if not math.isfinite(value) or value <= 0:
                raise ValueError("fps 必须是大于 0 的有限数值")
            changed['fps'] = value
        for key, value in (('frame_range', frame_range), ('playback_range', playback_range)):
            if value is not None:
                changed[key] = list(_frame_pair(value, key))
        if current_frame is not None:
            value = float(current_frame)
            if not math.isfinite(value):
                raise ValueError('current_frame 必须是有限帧数')
            changed['current_frame'] = value
        before = scene_info()
    except (ValueError, TypeError, OverflowError, hou.Error) as error:
        raise dsh_errors.CheckpointError(str(error), {'ok': False, 'phase': 'timeline_preflight',
            'scene_writes': 0, 'applied': False}) from error
    setters = {'fps': lambda v: hou.setFps(v),
               'frame_range': lambda v: hou.playbar.setFrameRange(*v),
               'playback_range': lambda v: hou.playbar.setPlaybackRange(*v),
               'current_frame': lambda v: hou.setFrame(v)}
    writes = 0
    try:
        for key, value in changed.items():
            writes += 1
            setters[key](value)
        return {'changed': changed, 'scene': scene_info(), 'scene_writes': writes}
    except BaseException as error:
        restore_errors = []
        # FPS/ranges can affect the frame; restore the original frame last.
        for key, value in (('fps', before['fps']), ('frame_range', before['frame_range']),
                           ('playback_range', before['playback_range']), ('current_frame', before['frame'])):
            try:
                setters[key](value)
            except Exception as failure:
                restore_errors.append(f'{key}: {failure}')
        try:
            after = scene_info()
            for key in ('fps', 'frame_range', 'playback_range', 'frame'):
                if after[key] != before[key]:
                    restore_errors.append(f'{key}: restoration readback differs')
        except Exception as failure:
            restore_errors.append(f'restoration readback: {failure}')
        raise dsh_errors.CheckpointError(f'set_timeline failed: {error}; restore_errors={restore_errors}',
            {'ok': False, 'phase': 'timeline_write', 'scene_writes': writes,
             'restored': not restore_errors, 'restore_errors': restore_errors,
             'scope': 'timeline state only; cooks and external side effects are not restored'}) from error


def list_bookmarks() -> list:
    """列出动画时间线 bookmarks。"""
    return [
        {
            "id": bookmark.sessionId(),
            "name": bookmark.name(),
            "start": float(bookmark.startFrame()),
            "end": float(bookmark.endFrame()),
            "enabled": bool(bookmark.isEnabled()),
            "visible": bool(bookmark.visible()),
            "temporary": bool(bookmark.isTemporary()),
            "comment": bookmark.comment(),
        }
        for bookmark in hou.anim.bookmarks()
    ]


def create_bookmark(name: str, start, end, replace: bool = False) -> dict:
    """创建 bookmark；同名默认拒绝，``replace=True`` 精确替换同名项。"""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("bookmark name 必须是非空字符串")
    name = name.strip()
    start_frame, end_frame = _frame_pair((start, end), "bookmark range")
    if not start_frame.is_integer() or not end_frame.is_integer():
        raise ValueError("bookmark start/end 必须是整数帧")
    existing = [bookmark for bookmark in hou.anim.bookmarks() if bookmark.name() == name]
    if existing and not replace:
        raise ValueError(f"bookmark {name!r} 已存在；确认替换时传 replace=True")
    if existing:
        hou.anim.removeBookmarks(existing)
    bookmark = hou.anim.newBookmark(name, int(start_frame), int(end_frame))
    return {
        "id": bookmark.sessionId(),
        "name": bookmark.name(),
        "start": float(bookmark.startFrame()),
        "end": float(bookmark.endFrame()),
        "replaced": len(existing),
    }


def delete_bookmark(name_or_id) -> dict:
    """按精确名称或 session id 删除 bookmark。"""
    matches = []
    for bookmark in hou.anim.bookmarks():
        if isinstance(name_or_id, int) and bookmark.sessionId() == name_or_id:
            matches.append(bookmark)
        elif isinstance(name_or_id, str) and bookmark.name() == name_or_id:
            matches.append(bookmark)
    if not matches:
        raise ValueError(
            f"找不到 bookmark {name_or_id!r}；现有："
            f"{[(item['id'], item['name']) for item in list_bookmarks()]}"
        )
    deleted = [
        {"id": bookmark.sessionId(), "name": bookmark.name()}
        for bookmark in matches
    ]
    hou.anim.removeBookmarks(matches)
    return {"deleted": deleted}
