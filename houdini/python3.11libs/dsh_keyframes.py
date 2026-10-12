"""Houdini keyframes. Executed on the Bridge owning thread."""
from __future__ import annotations

import difflib
import math
import hou
import dsh_errors
import dsh_node_access
import dsh_ownership
import dsh_parameter_values


_KEYFRAME_CURVES = {
    "constant": "constant()",
    "linear": "linear()",
    "bezier": "bezier()",
}


_KEYFRAME_INPUT_LIMIT = 10_000


_KEYFRAME_RESULT_LIMIT = 64


_KEYFRAME_SAMPLE_LIMIT = 32


def set_keyframes(node, channels: dict, replace: bool = True,
                  allow_foreign: str | None = None) -> dict:
    """批量写入标量数值参数关键帧，统一使用 frame 单位并提交后回读。

    ``channels`` 形如 ``{"tx": [{"frame": 1, "value": 0, "curve": "linear"}]}``。
    curve 仅支持 ``constant/linear/bezier``；它描述从该 key 离开的 segment。
    所有 channel 在修改前完成校验；任一写入失败会恢复本次涉及参数的原值、表达式、关键帧与当前帧；恢复错误保留在返回证据。
    ``replace=False`` 保留旧 keys，但拒绝覆盖同一 frame。该动词只负责 channel 数据，
    不替代有序状态机、KineFX/APEX rig logic 或 Animation Editor。
    """
    try:
        n = dsh_node_access._resolve(node)
        dsh_ownership.require_owned(n, "set_keyframes", allow_foreign)
        if not isinstance(channels, dict) or not channels:
            raise ValueError("channels 必须是非空 dict：{标量参数名: key spec 列表}")
        if not isinstance(replace, bool):
            raise ValueError("replace 必须是 bool")

        prepared = {}
        originals = {}
        for parm_name, specs in channels.items():
            if not isinstance(parm_name, str) or not parm_name:
                raise ValueError(f"channel 名必须是非空字符串，收到 {parm_name!r}")
            parm = n.parm(parm_name)
            if parm is None:
                if n.parmTuple(parm_name) is not None:
                    raise ValueError(
                        f"{n.path()}/{parm_name} 是参数元组；请按组件名分别提供 channel"
                    )
                suggestions = difflib.get_close_matches(
                    parm_name, [item.name() for item in n.parms()], n=5, cutoff=0.4
                )
                raise ValueError(
                    f"节点 {n.path()} 没有标量参数 {parm_name!r}；相似参数：{suggestions}"
                )
            template = parm.parmTemplate()
            try:
                template_type = template.type()
            except Exception:
                template_type = None
            if template_type not in (hou.parmTemplateType.Int, hou.parmTemplateType.Float):
                raise ValueError(
                    f"{parm.path()} 不是数值标量参数（类型={template_type}），不能写数值 keyframes"
                )
            if not isinstance(specs, (list, tuple)) or not specs:
                raise ValueError(f"channels[{parm_name!r}] 必须是非空 key spec 列表")
            if len(specs) > _KEYFRAME_INPUT_LIMIT:
                raise ValueError(
                    f"channels[{parm_name!r}] 超过 {_KEYFRAME_INPUT_LIMIT} keys；"
                    "请拆分任务或使用缓存/clip 工作流"
                )

            existing_keys = tuple(parm.keyframes())
            originals[parm_name] = existing_keys
            existing_frames = {float(key.frame()) for key in existing_keys}
            seen_frames = set()
            keys = []
            for index, spec in enumerate(specs):
                path = f"channels[{parm_name!r}][{index}]"
                if not isinstance(spec, dict):
                    raise ValueError(f"{path} 必须是 dict")
                unknown = set(spec) - {"frame", "value", "curve"}
                if unknown:
                    raise ValueError(f"{path} 有未知字段：{sorted(unknown)}")
                if "frame" not in spec or "value" not in spec:
                    raise ValueError(f"{path} 必须同时提供 frame 和 value")
                if isinstance(spec["frame"], bool) or isinstance(spec["value"], bool):
                    raise ValueError(f"{path}.frame/value 不能是 bool")
                frame = float(spec["frame"])
                value = float(spec["value"])
                if not math.isfinite(frame) or not math.isfinite(value):
                    raise ValueError(f"{path}.frame/value 必须是有限数值")
                if frame in seen_frames:
                    raise ValueError(f"{path}.frame={frame} 在同一 channel 重复")
                if not replace and frame in existing_frames:
                    raise ValueError(
                        f"{path}.frame={frame} 已存在；replace=False 不允许覆盖旧 key"
                    )
                seen_frames.add(frame)
                curve_name = str(spec.get("curve", "bezier")).strip().lower()
                expression = _KEYFRAME_CURVES.get(curve_name)
                if expression is None:
                    raise ValueError(
                        f"{path}.curve={curve_name!r} 不支持；可用 {sorted(_KEYFRAME_CURVES)}"
                    )
                key = hou.Keyframe(value)
                key.setFrame(frame)
                key.setExpression(expression, hou.exprLanguage.Hscript)
                keys.append(key)
            prepared[parm_name] = (parm, tuple(sorted(keys, key=lambda key: key.frame())))

        snapshots = dsh_parameter_values._parameter_snapshot([parm for parm, _ in prepared.values()])
    except (ValueError, TypeError, OverflowError, hou.Error) as error:
        raise dsh_errors.CheckpointError(str(error), {'ok': False, 'phase': 'keyframes_preflight',
            'scene_writes': 0, 'applied': False}) from error

    saved_frame = float(hou.frame())
    writes = 0
    try:
        for parm_name, (parm, keys) in prepared.items():
            writes += 1
            if replace:
                parm.deleteAllKeyframes()
            parm.setKeyframes(keys)
        if float(hou.frame()) != saved_frame:
            hou.setFrame(saved_frame)
        result = {}
        for parm_name, (parm, _) in prepared.items():
            keys = tuple(parm.keyframes())
            frames = [float(key.frame()) for key in keys]
            key_data = []
            for key in keys:
                try:
                    curve = key.expression()
                except Exception:
                    curve = None
                key_data.append({
                    "frame": float(key.frame()),
                    "value": float(key.value()),
                    "curve": curve,
                })
            if len(key_data) > _KEYFRAME_RESULT_LIMIT:
                key_preview = (
                    key_data[:_KEYFRAME_RESULT_LIMIT // 2]
                    + key_data[-_KEYFRAME_RESULT_LIMIT // 2:]
                )
                keys_truncated = len(key_data) - len(key_preview)
            else:
                key_preview = key_data
                keys_truncated = 0
            sample_candidates = sorted(set([
                frames[0],
                frames[-1],
                *(
                    (frames[index] + frames[index + 1]) / 2.0
                    for index in range(len(frames) - 1)
                ),
            ]))
            if len(sample_candidates) > _KEYFRAME_SAMPLE_LIMIT:
                sample_frames = (
                    sample_candidates[:_KEYFRAME_SAMPLE_LIMIT // 2]
                    + sample_candidates[-_KEYFRAME_SAMPLE_LIMIT // 2:]
                )
            else:
                sample_frames = sample_candidates
            result[parm_name] = {
                "key_count": len(keys),
                "first_frame": frames[0],
                "last_frame": frames[-1],
                "keys": key_preview,
                "samples": {
                    str(frame): float(parm.evalAtFrame(frame)) for frame in sample_frames
                },
                "replaced_existing": len(originals[parm_name]) if replace else 0,
            }
            if keys_truncated:
                result[parm_name]["keys_truncated"] = keys_truncated
        return {
            "node": n.path(),
            "replace": replace,
            "channels": result,
            "frame_restored": float(hou.frame()) == saved_frame,
            "scene_writes": writes,
        }

    except BaseException as error:
        restore_errors = dsh_parameter_values._restore_parameters(snapshots)
        if float(hou.frame()) != saved_frame:
            try:
                hou.setFrame(saved_frame)
            except Exception as failure:
                restore_errors.append(f'frame: {failure}')
        if float(hou.frame()) != saved_frame:
            restore_errors.append('frame: restoration readback differs')
        raise dsh_errors.CheckpointError(f'set_keyframes failed: {error}; restore_errors={restore_errors}',
            {'ok': False, 'phase': 'keyframes_write', 'scene_writes': writes,
             'restored': not restore_errors, 'restore_errors': restore_errors,
             'frame_restored': float(hou.frame()) == saved_frame,
             'scope': 'snapshotted channel values, expressions, keys and frame; external side effects are separate'}) from error
