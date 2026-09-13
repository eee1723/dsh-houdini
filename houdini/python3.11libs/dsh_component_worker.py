"""A new component executor owned by one supervisor, never an existing HIP.

The supervisor owns process handles and the Windows Job. This entry initializes
HOM only on the new process's owning thread and publishes its actual identity.
"""
from pathlib import Path
import json
import os
import threading
import time

_TIMER = None
_STOP = threading.Event()


def start():
    """Initialize a fresh, explicitly configured component process after GO."""
    import hou
    import dsh_bridge as bridge
    from dsh_shared_executor import prepare_registration, publish_registration
    request_file = Path(os.environ['DSH_COMPONENT_WORKER_REQUEST']).resolve(strict=True)
    request = json.loads(request_file.read_text(encoding='utf-8'))
    root = request_file.parent
    workspace = Path(request['workspace']).resolve(strict=True)
    hip = workspace / 'component.hip'
    if Path(hou.hipFile.path()).name.lower() != 'untitled.hip' or hip.exists():
        raise RuntimeError('component worker requires a new scene and unused HIP path')
    # Supervisor writes GO only after assigning its exact process to the Job.
    gate = root / 'go'
    deadline = time.monotonic() + request['startup_timeout']
    while not gate.exists():
        if hou.isUIAvailable():
            raise RuntimeError('GUI initialization arrived before supervisor release')
        if time.monotonic() >= deadline:
            raise RuntimeError('component worker was not released by its supervisor')
        time.sleep(.01)
    hou.hipFile.save(str(hip))
    bridge.start(0)
    facts = prepare_registration()

    def publish():
        try:
            record = publish_registration(request['registry'], facts)
            result = {'ok': True, 'record': record, 'workspace': str(workspace)}
        except Exception as error:
            result = {'ok': False, 'error': str(error)}
        with (root / 'ready.json').open('x', encoding='utf-8') as stream:
            json.dump(result, stream)

    threading.Thread(target=publish, daemon=True).start()

    def stop_reader():
        while not _STOP.wait(.1):
            if (root / 'stop').exists():
                _STOP.set()

    threading.Thread(target=stop_reader, daemon=True).start()

    def idle_stop():
        if not _STOP.is_set():
            return False
        if bridge._request_registry.active_count() or bridge._job_activity()['activeJobs'] or not bridge._work_queue.empty():
            return False
        if Path(hou.hipFile.path()).resolve() != hip:
            raise RuntimeError('worker HIP changed; refusing automatic checkpoint/exit')
        hou.hipFile.save(str(hip))
        return True

    if hou.isUIAvailable():
        from hutil.Qt import QtCore
        if not request.get('show_ui', False):
            hou.qt.mainWindow().hide()
        global _TIMER
        _TIMER = QtCore.QTimer(hou.qt.mainWindow())
        def tick():
            if idle_stop():
                _TIMER.stop()
                hou.qt.mainWindow().close()
        _TIMER.timeout.connect(tick)
        _TIMER.start(100)
    else:
        bridge._pump_active = True
        try:
            while not idle_stop():
                bridge._pump()
                time.sleep(.01)
        finally:
            bridge.stop()


if __name__ == '__main__':
    start()
