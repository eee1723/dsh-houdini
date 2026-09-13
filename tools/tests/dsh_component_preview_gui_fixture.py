"""Invoked by an isolated GUI uiready hook; never load an existing HIP."""
from pathlib import Path
import json
import os
import time


def start():
    import hou
    from hutil.Qt import QtCore
    import dsh_component_preview as preview
    import dsh_launcher as launcher
    import dsh_managed_runtime as runtime
    import dsh_executor_registry as registry
    import dsh_webview

    root = Path(os.environ['DSH_COMPONENT_PREVIEW_GUI_FIXTURE'])
    output = root / 'result.json'
    messages = []
    choices = []
    def display_message(message, *args, **kwargs):
        if kwargs.get('buttons') == ('Regular workspace', 'Component preview', 'Cancel'):
            choices.append(kwargs)
            return 1
        messages.append(str(message))
        return 0
    hou.ui.displayMessage = display_message
    hip = root / 'assembly.hip'
    deadline = time.monotonic() + 90
    timer = QtCore.QTimer(hou.qt.mainWindow())
    def finish(ok, error=''):
        timer.stop()
        output.write_text(json.dumps({'ok': ok, 'error': error, 'messages': messages,
                                      'mode_choices': len(choices),
                                      'hip': str(hip), 'frontend_owned': runtime.has_owned_frontend()}), encoding='utf-8')
        if dsh_webview._window is not None:
            dsh_webview._dispose_webview()
        QtCore.QTimer.singleShot(100, hou.qt.mainWindow().close)
    def tick():
        if messages:
            finish(False, messages[-1]); return
        state = preview._STATE or {}
        if state.get('result') == 'error':
            finish(False, state.get('error', 'startup failed')); return
        if state.get('result') == 'ready' and not preview._BUSY and dsh_webview._view is not None:
            if (len(choices) != 1 or not registry.is_shared_executor()
                    or not runtime.has_owned_frontend() or not hip.is_file()):
                finish(False, 'assembly registration, owned Host or fixture HIP missing'); return
            if not dsh_webview._active_frontend_url.startswith('http://127.0.0.1:'):
                finish(False, 'embedded preview did not use its dynamic loopback Host'); return
            owned = preview._HOST_PROCESS
            try:
                from unittest.mock import patch
                with patch.object(launcher, '_dispatch_service_preflight',
                                  side_effect=AssertionError('ordinary launcher started a second Host')):
                    launcher.open_workspace(select_mode=True)
                if preview._HOST_PROCESS is not owned or messages:
                    finish(False, 'ordinary entry failed to reuse the owned component workspace'); return
            except Exception as error:
                finish(False, str(error)); return
            finish(True); return
        if time.monotonic() > deadline:
            finish(False, 'GUI preview did not reach the embedded page within 90 seconds')
    try:
        if not hou.hipFile.isNewFile():
            raise RuntimeError('GUI fixture must begin from a new scene')
        hou.hipFile.save(str(hip))
        launcher.open_workspace(select_mode=True)
        timer.timeout.connect(tick)
        timer.start(100)
    except Exception as error:
        finish(False, str(error))
