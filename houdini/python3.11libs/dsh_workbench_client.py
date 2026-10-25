"""Houdini menu adapter: capture HOM on the main thread, activate on a worker."""
from pathlib import Path
import os
import sys
import threading
import uuid

if '_BUSY' not in globals():
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
    home = dsh_home()
    roots = [Path(launcher.NPM_CACHE) / '_npx']
    if launcher.DSH_BIN_ENV:
        roots.append(Path(launcher.DSH_BIN_ENV).resolve().parent.parent)
    reject_legacy_frontend(launcher.FRONTEND_RUNTIME_STATE, home=str(home), cli_roots=roots,
                           port=launcher.FRONTEND_PORT, listener_pid=launcher._port_pid)
    binary = launcher.DSH_BIN_ENV or launcher.dsh_runtime_compat.preferred_cached_bin(launcher.NPM_CACHE)
    if not binary:
        raise RuntimeError('源码运行环境尚未准备，请运行 npm run runtime:prepare。')
    python = Path(sys.prefix) / 'python.exe'
    return {'root': str(home / 'houdini-workbench'), 'installation': str(Path(launcher._PROJECT_ROOT).resolve()),
            'plugin': launcher._PROJECT_ROOT, 'node': launcher.NODE, 'binary': str(binary),
            'home': str(home), 'hfs': os.environ['HFS'], 'python': str(python)}


def open_workspace(launcher, *, reload=False):
    global _BUSY, _TIMER
    if _BUSY:
        return
    import hou
    if not hou.isUIAvailable():
        raise RuntimeError('请从 Houdini 图形界面的 Open Workspace 打开工作台。')
    if launcher._MANAGED and not launcher._MANAGED.get('workbench'):
        raise RuntimeError('当前安装仍使用旧版启动入口。请运行配套新版安装器 Install.cmd，保存工程后重新打开 Houdini；已有对话和工程不需要删除。')
    from hutil.Qt import QtCore
    from dsh_workbench import ensure, control, running, close_when_idle
    from dsh_shared_executor import prepare_registration, publish_registration
    from dsh_managed_runtime import has_owned_frontend
    if has_owned_frontend():
        raise RuntimeError('当前 Houdini 仍运行旧版内嵌工作区。请先保存任务并正常退出该 Houdini，再打开独立工作台；没有结束现有任务。')
    workspace = launcher._hip_dir()
    facts = prepare_registration(workbench=True, workspace=workspace, reuse_busy=True)
    install_observation()
    state = {}
    reloaded = threading.Event()
    _BUSY = True
    hou.ui.setStatusMessage('正在检查并重新加载运行环境…' if reload else '正在打开 DSH-Houdini 工作台…')

    def worker():
        try:
            if launcher._MANAGED:
                record = running(launcher._MANAGED['root'])
                if not record and not reload:
                    raise RuntimeError('独立工作台已关闭，请从 Version & Updates 重新打开工作区。')
                if reload:
                    from dsh_deployment import read_json
                    config = read_json(Path(launcher._MANAGED['root']) / 'workbench/launch-config.json')
                else:
                    desktop = control(record, 'status', timeout=5)
            else:
                config = source_config(launcher)
                config['initialWorkspace'] = workspace
                config['initialWorkspaceIsNew'] = facts['scene']['hip_is_new']
                os.environ['DSH_HOUDINI_WORKBENCH_ROOT'] = config['root']
                if reload:
                    record = running(config['root'])
                else:
                    desktop = ensure(config)
            if reload:
                if record and record['installation'] != config['installation']:
                    raise RuntimeError('当前工作台来自另一个安装，未重新加载任何运行环境。')
                if record:
                    # Let the original desktop check activity and save DSH
                    # before closing. Only after that Host is gone may this
                    # process replace its Bridge implementation.
                    close_when_idle(config, record)
                    state['desktop_closed'] = True
                state['reload_requested'] = True
                reloaded.wait()
                if state.get('error'):
                    return
                publish_registration(state['registry_root'], facts)
                desktop = ensure(config)
                state['desktop_reloaded'] = True
            os.environ['DSH_HOUDINI_WORKBENCH_CONTEXT'] = desktop['context']['contextFile']
            if os.name == 'nt':
                import ctypes
                ctypes.windll.user32.AllowSetForegroundWindow(desktop['record']['pid'])
            if reload:
                # DSH restores its own selected conversation and draft from its
                # persistent browser store; do not create or switch conversations.
                state['result'] = control(desktop['record'], 'show')
                return
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
            prefix = ('运行环境已重新加载，但恢复工作台窗口未完成：' if state.get('desktop_reloaded') else
                      '当前 Houdini 连接已重新加载，工作台尚未重开：' if state.get('bridge_reloaded') else
                      '工作台已关闭，Houdini 连接尚未重新加载：' if state.get('desktop_closed') else '')
            state['error'] = prefix + str(error)
        finally:
            state['done'] = True

    def finish():
        global _BUSY, _TIMER
        nonlocal facts, workspace
        if state.pop('reload_requested', False):
            try:
                # The native menu owns maintenance, not an Agent's node write
                # reservation. The existing restart path rechecks queue idleness.
                from dsh_shared_executor import repair_registration
                state['registry_root'], facts = repair_registration()
                state['bridge_reloaded'] = True
                workspace = launcher._hip_dir()
            except Exception as error:
                state['error'] = ('工作台已关闭，当前 Houdini 连接未重新加载；可等待操作结束后重试：'
                                  if state.get('desktop_closed') else '') + str(error)
            finally:
                reloaded.set()
            return
        if not state.get('done'):
            return
        _TIMER.stop()
        _TIMER = None
        _BUSY = False
        if state.get('error'):
            launcher._startup_failure(state['error'])
        else:
            hou.ui.setStatusMessage('运行环境已重新加载，工程内容保持不变。' if reload else '已打开 DSH-Houdini 工作台。')

    _TIMER = QtCore.QTimer(hou.qt.mainWindow())
    _TIMER.timeout.connect(finish)
    _TIMER.start(100)
    threading.Thread(target=worker, daemon=True).start()
