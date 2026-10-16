"""Houdini menu adapter: capture HOM on the main thread, activate on a worker."""
from pathlib import Path
import os
import sys
import threading
import uuid

_BUSY = False
_TIMER = None
_CALLBACK = None
_OBSERVATIONS = None


def observe_scene():
    import dsh_launcher
    from dsh_shared_executor import capture_scene
    observed = capture_scene(dsh_launcher._hip_dir())
    from dsh_executor_registry import active_registration
    try:
        registration = active_registration()
    except RuntimeError:
        return
    if not registration.workbench:
        return
    _OBSERVATIONS.put((registration, observed))


def install_observation():
    global _CALLBACK, _OBSERVATIONS
    if _CALLBACK is not None:
        return
    import hou
    import queue
    _OBSERVATIONS = queue.Queue()

    def worker():
        while True:
            registration, observed = _OBSERVATIONS.get()
            try:
                from dsh_shared_executor import observation_current
                registration.observe(observed['hip'], observed['scene'], is_current=lambda: observation_current(observed))
            except Exception as error:
                print('[dsh-houdini] 工程登记更新未完成：' + str(error), flush=True)

    def changed(kind, **kwargs):
        if kind in (hou.hipFileEventType.AfterLoad, hou.hipFileEventType.AfterClear):
            observe_scene()

    _CALLBACK = changed
    hou.hipFile.addEventCallback(changed)
    threading.Thread(target=worker, daemon=True).start()


def source_config(launcher):
    from dsh_profile_sync import dsh_home
    from dsh_workbench import reject_legacy_frontend
    reject_legacy_frontend(launcher.FRONTEND_RUNTIME_STATE)
    binary = launcher.DSH_BIN_ENV or launcher.dsh_runtime_compat.preferred_cached_bin(launcher.NPM_CACHE)
    if not binary:
        raise RuntimeError('源码运行环境尚未准备，请运行 npm run runtime:prepare。')
    python = Path(sys.prefix) / 'python.exe'
    return {'root': str(dsh_home() / 'houdini-workbench'), 'installation': str(Path(launcher._PROJECT_ROOT).resolve()),
            'plugin': launcher._PROJECT_ROOT, 'node': launcher.NODE, 'binary': str(binary),
            'home': str(dsh_home()), 'hfs': os.environ['HFS'], 'python': str(python)}


def open_workspace(launcher):
    global _BUSY, _TIMER
    if _BUSY:
        return
    import hou
    if not hou.isUIAvailable():
        raise RuntimeError('请从 Houdini 图形界面的 Open Workspace 打开工作台。')
    if launcher._MANAGED and not launcher._MANAGED.get('workbench'):
        raise RuntimeError('当前安装仍使用旧版启动入口。请运行配套新版安装器 Install.cmd，保存工程后重新打开 Houdini；已有对话和工程不需要删除。')
    from hutil.Qt import QtCore
    from dsh_workbench import ensure, control
    from dsh_shared_executor import prepare_registration, publish_registration
    from dsh_managed_runtime import has_owned_frontend
    if has_owned_frontend():
        raise RuntimeError('当前 Houdini 仍运行旧版内嵌工作区。请先保存任务并正常退出该 Houdini，再打开独立工作台；没有结束现有任务。')
    workspace = launcher._hip_dir()
    facts = prepare_registration(workbench=True, workspace=workspace, reuse_busy=True)
    install_observation()
    state = {}
    _BUSY = True
    hou.ui.setStatusMessage('正在打开 DSH-Houdini 工作台…')

    def worker():
        try:
            if launcher._MANAGED:
                from dsh_workbench import running
                record = running(launcher._MANAGED['root'])
                if not record:
                    raise RuntimeError('独立工作台已关闭，请从 Version & Updates 重新打开工作区。')
                desktop = control(record, 'status', timeout=5)
            else:
                config = source_config(launcher)
                config['initialWorkspace'] = workspace
                config['initialWorkspaceIsNew'] = facts['scene']['hip_is_new']
                os.environ['DSH_HOUDINI_WORKBENCH_ROOT'] = config['root']
                desktop = ensure(config)
            os.environ['DSH_HOUDINI_WORKBENCH_CONTEXT'] = desktop['context']['contextFile']
            if os.name == 'nt':
                import ctypes
                ctypes.windll.user32.AllowSetForegroundWindow(desktop['record']['pid'])
            if facts.get('busy'):
                if not facts.get('session_id'):
                    raise RuntimeError('当前 Houdini 仍有操作未完成，请稍后再打开此工程。工作台仍可用于其他工程。')
                state['result'] = control(desktop['record'], 'show', {'sessionId': facts['session_id']})
                return
            registration = publish_registration(desktop['context']['executorRegistry'], facts)
            state['result'] = control(desktop['record'], 'open', {
                'executorId': facts['executor_id'], 'registrationId': registration['registration_id'],
                'expectedHip': facts['hip'], 'requestId': uuid.uuid4().hex})
        except Exception as error:
            state['error'] = str(error)
        finally:
            state['done'] = True

    def finish():
        global _BUSY, _TIMER
        if not state.get('done'):
            return
        _TIMER.stop()
        _TIMER = None
        _BUSY = False
        if state.get('error'):
            launcher._startup_failure(state['error'])
        else:
            hou.ui.setStatusMessage('已打开 DSH-Houdini 工作台。')

    _TIMER = QtCore.QTimer(hou.qt.mainWindow())
    _TIMER.timeout.connect(finish)
    _TIMER.start(100)
    threading.Thread(target=worker, daemon=True).start()
