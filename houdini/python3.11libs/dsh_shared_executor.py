"""Explicit candidate registration UI; never starts/stops a shared DSH Host.

Current menu launch stays unchanged. Registry selection is a user action; main
thread captures HIP/Bridge facts, worker owns file locks and publication.
"""
from pathlib import Path
import os
import threading
import atexit

_BUSY = False
_TIMER = None


def prepare_registration():
    import hou
    import dsh_bridge as bridge
    from dsh_managed_runtime import has_owned_frontend
    if threading.get_ident() != bridge._HOU_THREAD_ID:
        raise RuntimeError('Registration must start on the Houdini main thread')
    if has_owned_frontend():
        raise RuntimeError('This Houdini still owns a single-instance DSH frontend. Do not switch active tasks; use a fresh Houdini for shared registration after saving existing work')
    if bridge._request_registry.active_count() or bridge._job_activity()['activeJobs'] or not bridge._work_queue.empty():
        raise RuntimeError('Wait for current Houdini work before registering a shared executor')
    hip = hou.hipFile.path()
    if hou.hipFile.isNewFile():
        raise RuntimeError('Save and name the HIP before registering; this action never saves your scene')
    # Bind directly to port zero; keep the server socket, no probe/rebind race.
    server = bridge._server or bridge.start(0)
    return {'hip': hip, 'version': bridge._HOU_VERSION, 'executor_id': bridge._EXECUTOR_ID,
            'runtime_id': bridge._RUNTIME_ID, 'port': server.server_port,
            'installation': str(Path(__file__).resolve().parents[2])}


def publish_registration(root, facts):
    from dsh_executor_registry import activate, active_registration
    root = Path(root)
    if not root.is_absolute():
        raise ValueError('Use the absolute shared DSH registry directory')
    if not Path(facts['hip']).is_file():
        raise ValueError('The named HIP has not been saved to disk')
    try:
        registration = active_registration()
    except RuntimeError:
        registration = activate(root, facts['executor_id'], installation=facts['installation'],
            version=facts['version'],port=facts['port'],runtime_id=facts['runtime_id'],hip=facts['hip'])
        atexit.register(registration.close)
    else:
        if registration.root != root.resolve() or registration.executor_id != facts['executor_id']:
            raise RuntimeError('This Houdini is already registered elsewhere; no automatic registry switch')
    return registration.publish(facts['port'], facts['runtime_id'], hip=facts['hip'])


def repair_registration():
    """Owning thread only: repair this Bridge, never the shared frontend."""
    from dsh_executor_registry import active_registration
    from dsh_launcher import restart_bridge
    registration = active_registration()
    facts = prepare_registration()
    if registration.executor_id != facts['executor_id']:
        raise RuntimeError('Shared executor identity changed; do not adopt this process')
    if registration._task is not None:
        registration.require_writer(registration._task, facts['hip'])
    restart_bridge(port=facts['port'])
    return registration.root, prepare_registration()


def show_registration(*, repair=False):
    global _BUSY, _TIMER
    import hou
    from hutil.Qt import QtCore
    if _BUSY:
        return
    if repair:
        button = hou.ui.displayMessage('Restart only this Houdini Bridge? Other executors and the shared DSH Host '
            'will not be stopped. Old in-flight outcomes cannot be replayed; active Houdini work blocks repair.',
            buttons=('Repair this executor', 'Cancel'),default_choice=1,close_choice=1)
        value = None
    else:
        button, value = hou.ui.readInput(
        'Shared DSH registry directory. Use the SAME directory configured on the shared Host. '
        'This registers only this Houdini; it does not start DSH, save HIP or bind an agent.',
        buttons=('Register executor', 'Cancel'),default_choice=1,close_choice=1,
        initial_contents=os.environ.get('DSH_HOUDINI_EXECUTOR_REGISTRY',''),title='Shared Houdini executor (candidate)')
    if button != 0:
        return
    try:
        if repair:
            value, facts = repair_registration()
        else:
            if not Path(value).is_absolute():
                raise ValueError('An absolute registry directory is required')
            facts = prepare_registration()
    except Exception as error:
        hou.ui.displayMessage(str(error))
        return
    _BUSY = True
    state = {}
    def worker():
        try: state['result'] = publish_registration(value, facts)
        except Exception as error: state['error'] = str(error)
        finally: state['done'] = True
    def finish():
        global _BUSY, _TIMER
        if not state.get('done'): return
        _TIMER.stop();_TIMER=None;_BUSY=False
        if state.get('error'):
            hou.ui.displayMessage(state['error'])
        else:
            hou.ui.displayMessage('Executor registered. In the shared DSH task, open Houdini 执行端 and choose this HIP. '
                'Registration alone is not a task binding or permission to edit another author’s nodes.')
    _TIMER = QtCore.QTimer(hou.qt.mainWindow())
    _TIMER.timeout.connect(finish);_TIMER.start(100)
    threading.Thread(target=worker,daemon=True).start()
