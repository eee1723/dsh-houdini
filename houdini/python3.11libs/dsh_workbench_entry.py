"""Native GUI discovery and explicit launch handshake after the UI is ready."""
import os
from pathlib import Path


_SAVE_HOOKS = set()
_READY_SCHEDULED = globals().get('_READY_SCHEDULED', False)


def after_save(native_context, wrapper):
    """Run DSH's notification and preserve the next native save script.

    Houdini executes only the first scripts/afterscenesave.py on its search
    path. The workbench forwarder adds DSH's notification, then forwards to
    the first remaining match. That script owns any further chaining; running
    all matches here would activate normally shadowed third-party scripts.
    """
    import hou
    current = Path(wrapper).resolve()
    outermost = not _SAVE_HOOKS
    _SAVE_HOOKS.add(current)
    arguments = native_context.get('kwargs')
    errors = []
    def execute(filename):
        path = Path(filename).resolve()
        if path in _SAVE_HOOKS:
            return
        _SAVE_HOOKS.add(path)
        context = {**native_context, '__file__': str(filename),
                   'kwargs': dict(arguments) if isinstance(arguments, dict) else arguments}
        exec(compile(path.read_bytes(), str(filename), 'exec'), context)
    def run(filename):
        try:
            execute(filename)
        # Still notify the native script if the plugin notification failed.
        except BaseException as error:
            errors.append((str(filename), error))
    try:
        discovered = tuple(Path(filename) for filename in hou.findFiles('scripts/afterscenesave.py'))
        if outermost:
            import sys
            recovery = sys.modules.get('dsh_scene_recovery')
            if recovery is not None:
                try:
                    if isinstance(arguments, dict) and 'success' in arguments:
                        recovery.after_save(arguments['file'], arguments['success'])
                    else:
                        recovery.save_unverified('Houdini 未提供保存成功标志；请使用规范路径重新保存。')
                except BaseException as error:
                    errors.append((str(current), error))
        for filename in discovered:
            if filename.resolve() in _SAVE_HOOKS:
                continue
            run(filename)
            break
        if any(isinstance(error, KeyboardInterrupt) for _, error in errors):
            raise KeyboardInterrupt
        if errors:
            raise RuntimeError('保存脚本执行失败：' + '；'.join(
                f'{path}：{type(error).__name__}: {error}' for path, error in errors))
    finally:
        if outermost:
            _SAVE_HOOKS.clear()


def after_ui_ready(native_context=None, wrapper=None):
    """One GUI attach; Houdini itself runs every matching uiready script."""
    global _READY_SCHEDULED
    import hou
    if not hou.isUIAvailable() or _READY_SCHEDULED:
        return False
    from hutil.Qt import QtCore
    _READY_SCHEDULED = True
    QtCore.QTimer.singleShot(0, attach)
    return True


def attach():
    """Keep ticket handoff explicit; ordinary GUI startup only advertises itself."""
    import hou
    if not hou.isUIAvailable():
        return False
    ticket = os.environ.get('DSH_HOUDINI_LAUNCH_TICKET')
    import dsh_launcher
    try:
        if not ticket:
            from dsh_workbench_client import discover_current_scene
            return discover_current_scene(dsh_launcher)
        from dsh_workbench_client import open_workspace
        started = open_workspace(dsh_launcher, launch_ticket=ticket)
        if started:
            os.environ.pop('DSH_HOUDINI_LAUNCH_TICKET', None)
        return started
    except Exception as error:
        if ticket:
            dsh_launcher._startup_failure(error)
        else:
            dsh_launcher._LAST_STARTUP_FAILURE = str(error)
            dsh_launcher._report('自动登记未完成：' + str(error))
        return False
