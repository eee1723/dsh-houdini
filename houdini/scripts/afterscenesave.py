"""Native save success notification; do not load a runtime just to save a HIP."""
import sys
_recovery = sys.modules.get('dsh_scene_recovery')
_save_args = globals().pop('kwargs', None)
if _recovery is not None:
    if isinstance(_save_args, dict) and 'success' in _save_args:
        _recovery.after_save(_save_args['file'], _save_args['success'])
    else:
        # H21 can fail to construct kwargs for a raw Windows backslash path.
        # Absence of success evidence must never commit an ownership snapshot.
        _recovery.save_unverified('Houdini 未提供保存成功标志；请使用规范路径重新保存。')
