"""Houdini scene capture on the main thread; official Desktop activation on a worker."""
import os
from pathlib import Path
import threading
import uuid

if '_BUSY' not in globals():
    _BUSY = False
    _TIMER = None
    _CALLBACK = None
    _OBSERVATIONS = None
if '_PENDING_MENU' not in globals():
    _PENDING_MENU = None


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


def _scene_snapshot(hou):
    return {'hfs': os.environ.get('HFS', ''), 'hipPath': hou.hipFile.path(),
            'hipIsNew': bool(hou.hipFile.isNewFile())}


def _admitted_ticket(value, identifier):
    if (not isinstance(value, dict) or value.get('id') != identifier
            or not isinstance(value.get('phase'), str)
            or any(not isinstance(value.get(field), str) or not Path(value[field]).is_absolute()
                   for field in ('workspace', 'hfs'))
            or value.get('hip') is not None and (not isinstance(value['hip'], str) or not Path(value['hip']).is_absolute())):
        raise RuntimeError('Desktop 未能确认这次 Houdini 启动，请在 Desktop 中重试连接。\n原因：启动准入信息格式无效。')
    return value


def open_workspace(launcher, *, reload=False, launch_ticket=None):
    """One connection pipeline for explicit menu and automatic launch intents.

    Main-thread scene capture is never retried by transport. Workers authenticate
    a current Host, publish once, and retain the same menu request or receipt.
    """
    global _BUSY, _TIMER, _PENDING_MENU
    if _BUSY:
        if launch_ticket is None:
            # This is one explicit user intention, not an inferred new writer.
            _PENDING_MENU = {'reload': reload or bool((_PENDING_MENU or {}).get('reload'))}
            import hou
            hou.ui.setStatusMessage('正在连接，请稍候；完成后会打开 Desktop。')
        return False
    import hou
    if not hou.isUIAvailable():
        raise RuntimeError('请从 Houdini 图形界面的 Open Workspace 接入官方 DSH Desktop。')
    from hutil.Qt import QtCore
    launcher.require_local_modules()
    if reload:
        from dsh_executor_registry import is_shared_executor
        if is_shared_executor():
            from dsh_shared_executor import repair_registration
            repair_registration()
        else:
            launcher.restart_bridge(port=0)
    initial = _scene_snapshot(hou)
    state = {'phase': 'connecting', 'initial': initial, 'requestId': uuid.uuid4().hex}
    _BUSY = True
    hou.ui.setStatusMessage('正在连接 DSH Desktop…')

    def local_failure(error):
        state['error'] = str(error)
        channel, identifier = state.get('channel'), state.get('operationId')
        if channel is not None and identifier:
            try:
                channel.call('launch-failed', {'id': identifier, 'error': str(error)})
            except Exception:
                pass

    def prepare():
        try:
            from dsh_desktop_client import DesktopConnection, read_launch_ticket, activate_desktop
            channel = DesktopConnection(timeout=30, activate=launch_ticket is None)
            state['channel'] = channel
            desktop = channel.current()
            if launch_ticket is None:
                if not channel.activated:
                    activate_desktop()
                    channel.activated = True
            else:
                from dsh_deployment import _process_started
                ticket = read_launch_ticket(launch_ticket, desktop)
                state['operationId'] = ticket['id']
                birth = _process_started(os.getpid())
                if not birth:
                    raise RuntimeError('尚未确认这个 Houdini 窗口，连接未完成。请从本窗口的 Open Workspace 重试。\n原因：无法读取进程创建身份。')
                identity = {'id': ticket['id'], 'pid': os.getpid(), 'processStarted': birth,
                            'hfs': str(Path(initial['hfs']).resolve()),
                            'hipPath': initial['hipPath'], 'hipIsNew': initial['hipIsNew']}
                admitted = channel.call('ticket-current', identity)
                state['ticket'] = _admitted_ticket(admitted, ticket['id'])
                channel.progress(ticket['id'], 'capturing')
            if os.name == 'nt':
                import ctypes
                ctypes.windll.user32.AllowSetForegroundWindow(desktop['pid'])
            state['phase'] = 'capturing'
        except Exception as error:
            from dsh_desktop_client import DesktopRefusal, DesktopUnavailable
            if isinstance(error, (DesktopRefusal, DesktopUnavailable)):
                state['error'] = str(error)
            else:
                local_failure(error)
        finally:
            state['prepared'] = True

    def publish(facts):
        try:
            from dsh_shared_executor import publish_registration
            channel, identifier = state['channel'], state.get('operationId')
            if identifier:
                channel.progress(identifier, 'registering')
            state['phase'] = 'registering'
            desktop = channel.current_admitted()
            registration = publish_registration(desktop['executorRegistry'], facts)
            receipt = {'executorId': facts['executor_id'], 'registrationId': registration['registration_id'],
                       'expectedHip': facts['hip']}
            if identifier:
                receipt['id'] = identifier
                channel.progress(identifier, 'binding')
            else:
                receipt['requestId'] = state['requestId']
            state['phase'] = 'binding'
            state['result'] = channel.call('launch-attached' if identifier else 'open-workspace', receipt)
        except Exception as error:
            from dsh_desktop_client import DesktopRefusal, DesktopUnavailable
            if isinstance(error, (DesktopRefusal, DesktopUnavailable)):
                # A missing HTTP response is not evidence of a preparation or
                # binding failure. The Host may already hold the same receipt.
                state['error'] = str(error)
            else:
                local_failure(error)
        finally:
            state['done'] = True

    def finish():
        global _BUSY, _TIMER, _PENDING_MENU
        if not state.get('done') and state.get('prepared') and not state.get('captured'):
            state['captured'] = True
            if state.get('error'):
                state['done'] = True
            else:
                try:
                    from dsh_shared_executor import prepare_registration
                    if _scene_snapshot(hou) != initial:
                        raise RuntimeError('工程在连接时发生了变化，本次未连接到对话。请从当前窗口重新打开 Open Workspace。')
                    launcher.require_local_modules()
                    ticket = state.get('ticket')
                    if ticket and initial['hipIsNew']:
                        launcher._UNSAVED_WORKSPACE = ticket['workspace']
                    workspace = ticket['workspace'] if ticket else launcher._hip_dir()
                    # The record bit describes scene-aware registration, not a shell.
                    facts = prepare_registration(workbench=True, workspace=workspace, reuse_busy=ticket is None)
                    install_observation()
                    if facts.get('busy'):
                        state.update(busy=True, done=True)
                    else:
                        threading.Thread(target=lambda: publish(facts), daemon=True).start()
                except Exception as error:
                    state['error'] = str(error)
                    state['done'] = True
                    threading.Thread(target=lambda retained=error: local_failure(retained), daemon=True).start()
        phase = state.get('phase')
        if phase != state.get('shownPhase') and not state.get('done'):
            state['shownPhase'] = phase
            hou.ui.setStatusMessage({'connecting': '正在连接 DSH Desktop…', 'capturing': '正在确认当前工程…',
                                    'registering': '正在连接当前 Houdini…', 'binding': '正在打开工程对话…'}[phase])
        if not state.get('done'):
            return
        pending_menu, _PENDING_MENU = _PENDING_MENU, None
        result = state.get('result') or {}
        confirmed = not state.get('error') and result.get('phase') not in ('waiting', 'detached', 'error')
        if pending_menu and confirmed and not pending_menu['reload'] and not state.get('activationOnly'):
            # A successful automatic connection already has the right native
            # Session/target. The pending menu only asks to reveal that app.
            state.update(activationOnly=True, done=False)
            def reveal():
                try:
                    from dsh_desktop_client import activate_desktop
                    activate_desktop()
                except Exception as error:
                    state['error'] = str(error)
                finally:
                    state['done'] = True
            threading.Thread(target=reveal, daemon=True).start()
            return
        _TIMER.stop()
        _TIMER = None
        _BUSY = False
        if pending_menu and (not confirmed or pending_menu['reload']):
            # The old launch producer has ended. Consume this separate menu
            # intention with fresh scene facts; never retry its old launch.
            QtCore.QTimer.singleShot(0, lambda: open_workspace(launcher, reload=pending_menu['reload']))
            return
        if state.get('error'):
            launcher._startup_failure(state['error'])
        else:
            hou.ui.setStatusMessage('已打开 Desktop。Houdini 正在执行操作，可在原对话查看进度。' if state.get('busy') else
                                   'Houdini 已就绪，当前对话的现场选择未改变。可在 Desktop 中继续选择。' if result.get('phase') == 'detached' else
                                   'Houdini 已就绪，Desktop 尚未确认连接。请到 Desktop 查看。' if result.get('phase') == 'waiting' else
                                   '当前 Houdini 已连接，可在 Desktop 中继续。')

    _TIMER = QtCore.QTimer(hou.qt.mainWindow())
    _TIMER.timeout.connect(finish)
    _TIMER.start(100)
    threading.Thread(target=prepare, daemon=True).start()
    return True
