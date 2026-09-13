"""Source-only, opt-in component workspace from the Houdini menu.

The current saved HIP is the assembly executor. One Houdini-owned DSH Host
creates component workers on demand. No existing DSH data, HIP or process is
adopted, restarted, or migrated by this entry.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import urllib.request
import urllib.parse

_BUSY = False
_TIMER = None
_HOST_PROCESS = None
_SESSION = None
_STATE = None


def is_starting() -> bool:
    return _BUSY


def has_host_attempt() -> bool:
    """GUI-safe identity hint, including a stopped Host that must not be restarted."""
    return _HOST_PROCESS is not None


def _source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _preview_root() -> Path:
    local = os.environ.get('LOCALAPPDATA')
    if not local or not Path(local).is_absolute():
        raise RuntimeError('A Windows LOCALAPPDATA directory is required for the isolated component preview')
    root = Path(local).resolve() / 'DSH-Houdini' / 'component-preview'
    if root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise RuntimeError('Component preview data cannot be under the shared platform TEMP directory')
    return root


def _executable(value: str, name: str) -> Path:
    path = Path(value.strip().strip('"'))
    if not path.is_absolute() or not path.is_file():
        raise RuntimeError(f'{name} must be an existing absolute executable path')
    return path.resolve(strict=True)


def _validate_config(config: dict, root: Path) -> dict:
    if config.get('schema') != 1 or config.get('source') != str(_source_root()):
        raise RuntimeError('Component preview configuration belongs to a different source checkout')
    binary = _executable(config['bin'], 'DSH bin.js')
    if binary.name != 'bin.js' or binary.parent.name != 'lib':
        raise RuntimeError('Select the built DSH apps/cli/lib/bin.js')
    package = json.loads((binary.parent.parent / 'package.json').read_text(encoding='utf-8'))
    if package.get('name') != '@deepseek-ai/dsh':
        raise RuntimeError('Selected CLI is not the DSH package')
    _executable(config['python'], 'Python')
    houdini = _executable(config['houdini'], 'Houdini GUI')
    if houdini.name.lower() != 'houdini.exe':
        raise RuntimeError('Component preview needs the Houdini GUI executable, not hython')
    run = Path(config['run']).resolve()
    if not run.is_relative_to(root.resolve()) or run == root.resolve():
        raise RuntimeError('Component preview profile must be below its dedicated data root')
    for key in ('home', 'workers', 'registry'):
        if Path(config[key]).resolve() != run / key:
            raise RuntimeError('Component preview directory layout changed')
    return config


def _read_config(root: Path) -> dict | None:
    file = root / 'config.json'
    if not file.exists():
        return None
    config = _validate_config(json.loads(file.read_text(encoding='utf-8')), root)
    overlay = Path(config['home']) / 'component.cordis.yml'
    link = Path(config['home']) / 'profiles/web/node_modules/dsh-houdini'
    if (not overlay.is_file() or not link.exists() or link.resolve() != _source_root()
            or hashlib.sha256(overlay.read_bytes()).hexdigest() != config.get('overlaySha256')):
        raise RuntimeError('The isolated component profile is incomplete; it was not silently recreated')
    return config


def _prompt_path(hou, title: str, initial: str) -> str | None:
    button, value = hou.ui.readInput(title, buttons=('Use path', 'Cancel'), default_choice=1,
                                     close_choice=1, initial_contents=initial, title='Component workspace preview')
    return value.strip().strip('"') if button == 0 else None


def _valid_hint(value: str, name: str, required_name: str | None = None) -> str:
    """Only reuse a known executable path; never search or start a process on the GUI thread."""
    try:
        executable = _executable(value, name)
        if required_name and executable.name.lower() != required_name:
            return ''
        return str(executable)
    except (OSError, RuntimeError, ValueError):
        return ''


def _python_hint() -> str:
    def standalone(value: str) -> str:
        candidate = _valid_hint(value, 'Python', 'python.exe')
        # Windows' Store app-execution alias is an existing python.exe, but it
        # may only open the Store instead of running the supervisor.
        return '' if candidate and 'windowsapps' in [part.lower() for part in Path(candidate).parts] else candidate
    if Path(sys.executable).name.lower() == 'python.exe':
        candidate = standalone(sys.executable)
        if candidate:
            return candidate
    candidate = standalone(shutil.which('python') or '')
    if candidate:
        return candidate
    local = os.environ.get('LOCALAPPDATA', '')
    if local and Path(local).is_absolute():
        candidates = [hint for file in (Path(local) / 'Python').glob('pythoncore-*/python.exe')
                      if (hint := standalone(str(file)))]
        if len(candidates) == 1:
            return candidates[0]
    return ''


def _houdini_hint() -> str:
    candidate = _valid_hint(sys.executable, 'Houdini GUI', 'houdini.exe')
    if candidate:
        return candidate
    hfs = os.environ.get('HFS', '')
    if hfs and Path(hfs).is_absolute():
        return _valid_hint(str(Path(hfs) / 'bin' / 'houdini.exe'), 'Houdini GUI', 'houdini.exe')
    return ''


def _new_config(hou, root: Path) -> dict | None:
    import dsh_launcher as launcher
    # The ordinary launcher override can point to an official release without
    # provider-selected child cwd. Only a dedicated component override skips
    # the candidate choice; npm releases/cache hits are never inferred.
    binary = os.environ.get('DSH_HOUDINI_COMPONENT_BIN', '').strip().strip('"')
    if not binary:
        binary = _prompt_path(hou, 'Select a BUILT DSH CLI containing provider-selected child cwd (apps/cli/lib/bin.js). Official 0.1.5-rc.2 does not include this candidate change.',
                              os.environ.get('DSH_HOUDINI_DSH_BIN', ''))
    if binary is None:
        return None
    python = _python_hint() or _prompt_path(hou, 'Select a standalone Python executable for the isolated component supervisors.',
                                           shutil.which('python') or '')
    if python is None:
        return None
    houdini = _houdini_hint() or _prompt_path(hou, 'Select the Houdini GUI executable for component workers.', '')
    if houdini is None:
        return None
    run = root / uuid.uuid4().hex
    config = {'schema': 1, 'source': str(_source_root()), 'bin': binary, 'python': python,
              'houdini': houdini, 'run': str(run),
              **{key: str(run / key) for key in ('home', 'workers', 'registry')}}
    _validate_config(config, root)
    if not launcher.NODE or not Path(launcher.NODE).is_file():
        raise RuntimeError('The source launcher needs an installed Node executable')
    return config


def _ensure_profile(config: dict, root: Path) -> None:
    import dsh_launcher as launcher
    if (root / 'config.json').exists():
        _read_config(root)
        return
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(('DSH_', 'PYTHON', 'QT_', 'QTWEBENGINE_', 'QML', 'HOUDINI_', 'NODE_'))
           and key.upper() not in ('HFS', 'HSITE', 'HHP', 'HB', 'HDSO')
           and not any(secret in key.upper() for secret in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY', 'CREDENTIAL'))}
    env['DSH_HOME'] = config['home']
    env['DSH_HOUDINI_EXECUTOR_REGISTRY'] = config['registry']
    env['NPM_CONFIG_CACHE'] = launcher.NPM_CACHE
    script = _source_root() / 'tools/prepare-component-profile.mjs'
    result = subprocess.run([launcher.NODE, str(script), config['bin'], config['home'], config['python'],
                             config['houdini'], config['workers'], config['registry']],
                            cwd=_source_root(), env=env, capture_output=True, text=True, timeout=120,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('Component profile preparation failed: ' + result.stderr[-1200:])
    overlay = Path(config['home']) / 'component.cordis.yml'
    link = Path(config['home']) / 'profiles/web/node_modules/dsh-houdini'
    if not overlay.is_file() or not link.exists() or link.resolve() != _source_root():
        raise RuntimeError('Component profile preparation did not create the expected source link and Host overlay')
    config['overlaySha256'] = hashlib.sha256(overlay.read_bytes()).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    file = root / 'config.json'
    with file.open('x', encoding='utf-8') as stream:
        json.dump(config, stream, ensure_ascii=False, indent=2)


def _host_environment(config: dict) -> dict:
    import dsh_launcher as launcher
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(('DSH_', 'PYTHON', 'QT_', 'QTWEBENGINE_', 'QML', 'HOUDINI_', 'NODE_'))
           and key.upper() not in ('HFS', 'HSITE', 'HHP', 'HB', 'HDSO')
           and not any(secret in key.upper() for secret in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY', 'CREDENTIAL'))}
    env.update(DSH_HOME=config['home'], DSH_HOUDINI_EXECUTOR_REGISTRY=config['registry'],
               NPM_CONFIG_CACHE=launcher.NPM_CACHE, PYTHONNOUSERSITE='1')
    if os.environ.get('HOUDINI_LICENSE_SERVER'):
        env['HOUDINI_LICENSE_SERVER'] = os.environ['HOUDINI_LICENSE_SERVER']
    return env


def _start_host(config: dict, workspace: str, root: Path):
    import dsh_launcher as launcher
    import dsh_managed_runtime as runtime
    import dsh_web_auth
    global _HOST_PROCESS, _SESSION
    # The released ephemeral port may race another binder. Readiness below
    # checks native Job membership, never adopts or stops a responding port.
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    log_path = root / 'host.log'
    with log_path.open('ab') as log:
        offset = log.tell()
        command = [launcher.NODE, config['bin'], 'web', '--patch', str(Path(config['home']) / 'component.cordis.yml'),
                   '--port', str(port), '--no-open']
        process = runtime.spawn_frontend(command, node=launcher.NODE, cwd=workspace, stdout=log,
                                         stderr=subprocess.STDOUT, env=_host_environment(config),
                                         replace_existing=False,
                                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    _HOST_PROCESS = process
    session = dsh_web_auth.DshWebSession(f'http://127.0.0.1:{port}', str(log_path), str(root / 'runtime.json'))
    session.reset(log_offset=offset)
    _SESSION = session
    return process, session


def _check_ready(process, session) -> bool:
    import dsh_launcher as launcher
    import dsh_managed_runtime as runtime
    if process.poll() is not None:
        raise RuntimeError(f'Component Host exited ({process.returncode}); inspect the isolated host.log')
    port = urllib.parse.urlsplit(session.base_url).port
    if not launcher._port_open('127.0.0.1', port):
        return False
    if not runtime.owns_pid(launcher._port_pid(port)):
        raise RuntimeError('Frontend listener does not belong to this Houdini; no external process was adopted')
    try:
        session.authorize(2)
        payload = {'type': 'client-request', 'rpcId': 'component-preview-' + uuid.uuid4().hex,
                   'method': 'session/list', 'payload': {'args': {'_request': {}}}}
        request = urllib.request.Request(session.base_url + '/api/session/list',
                                         data=json.dumps(payload).encode(), headers={'content-type': 'application/json'})
        with session.open(request, timeout=2) as response:
            result = json.load(response)
        return bool(result.get('result', {}).get('ok') and
                    isinstance(result['result'].get('value', {}).get('items'), list))
    except (OSError, ValueError, RuntimeError):
        return False


def _worker(config: dict, facts: dict, workspace: str, root: Path, state: dict) -> None:
    global _HOST_PROCESS
    try:
        import dsh_launcher as launcher
        from dsh_shared_executor import publish_registration
        state['phase'] = 'Checking frontend ownership'
        if (_HOST_PROCESS is None or _HOST_PROCESS.poll() is not None) and launcher.dsh_managed_runtime.has_owned_frontend():
            raise RuntimeError('Another frontend was started during preparation; component preview cannot replace it')
        state['phase'] = 'Preparing isolated profile'
        _ensure_profile(config, root)
        if _HOST_PROCESS is not None and _HOST_PROCESS.poll() is None:
            process, session = _HOST_PROCESS, _SESSION
        else:
            state['phase'] = 'Registering this saved HIP'
            publish_registration(config['registry'], facts)
            state['phase'] = 'Starting component Host'
            process, session = _start_host(config, workspace, root)
        deadline = time.monotonic() + 90
        state['phase'] = 'Waiting for authenticated Host'
        while not _check_ready(process, session):
            if time.monotonic() >= deadline:
                raise RuntimeError('Component Host did not become ready within 90 seconds; owned process retained for diagnosis')
            time.sleep(.25)
        state['session'] = session
        state['result'] = 'ready'
    except Exception as error:
        state['error'] = str(error)
        state['result'] = 'error'


def open_workspace() -> None:
    """Menu entry: no network, process wait or filesystem profile creation on GUI thread."""
    global _BUSY, _TIMER, _STATE
    import hou
    import dsh_launcher as launcher
    import dsh_managed_runtime as runtime
    from dsh_executor_registry import is_shared_executor, active_registration
    from dsh_shared_executor import prepare_registration
    if _BUSY:
        return
    try:
        if launcher._MANAGED:
            raise RuntimeError('Component workspace is source-preview only; signed managed installations remain unchanged')
        if not hou.isUIAvailable():
            raise RuntimeError('Component workspace preview requires the Houdini GUI')
        if _HOST_PROCESS is not None and _HOST_PROCESS.poll() is not None:
            raise RuntimeError('The component Host stopped. Child work/requests may be unknown; no automatic restart or replay. Preserve the isolated profile and inspect its host.log before recovery.')
        preview_owned = runtime.has_owned_frontend() and _HOST_PROCESS is not None and _HOST_PROCESS.poll() is None
        if runtime.has_owned_frontend() and not preview_owned:
            raise RuntimeError('This Houdini owns another DSH frontend; save and finish that task before opening a fresh component workspace')
        workspace = launcher._hip_dir()
        if hou.hipFile.isNewFile() or Path(workspace).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise RuntimeError('Save the assembly HIP outside platform TEMP first; this menu never saves or changes it')
        root = _preview_root()
        config = _read_config(root)
        if config is None:
            config = _new_config(hou, root)
            if config is None:
                return
        if is_shared_executor() and active_registration().root != Path(config['registry']).resolve():
            raise RuntimeError('This Houdini is registered to another shared Host; no automatic registry switch')
        if preview_owned:
            registered_hip = active_registration().registered_hip() if is_shared_executor() else None
            if (not registered_hip or os.path.normcase(os.path.abspath(hou.hipFile.path()))
                    != os.path.normcase(registered_hip)):
                raise RuntimeError('Assembly HIP or registration changed; existing component Host cannot adopt another target')
            facts = {}
            if _STATE and _STATE.get('result') == 'ready' and _SESSION and _SESSION.launch_url():
                import dsh_webview
                dsh_webview.show_webview(workspace_dir=workspace, authenticated_url=_SESSION.launch_url(),
                                         frontend_url=_SESSION.base_url)
                return
        else:
            facts = prepare_registration()
        from hutil.Qt import QtCore, QtWidgets
        dialog = QtWidgets.QProgressDialog('Preparing component workspace', 'Hide', 0, 0, hou.qt.mainWindow())
        dialog.setWindowTitle('DSH-Houdini component preview')
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setMinimumDuration(0)
        dialog.show()
        state = {'phase': 'Starting', 'result': None}
        _STATE = state
        _BUSY = True
        timer = QtCore.QTimer(hou.qt.mainWindow())
        _TIMER = timer
        def tick():
            global _BUSY, _TIMER
            dialog.setLabelText(state['phase'])
            if state['result'] is None:
                return
            timer.stop(); _TIMER = None; _BUSY = False
            dialog.close()
            if state['result'] == 'ready':
                try:
                    import dsh_webview
                    dsh_webview.show_webview(workspace_dir=workspace,
                                             authenticated_url=state['session'].launch_url(),
                                             frontend_url=state['session'].base_url, force_reload=True)
                except Exception:
                    hou.ui.displayMessage('The owned component Host is ready, but the embedded page could not open. '
                                          'Use this menu to retry; no task or HIP was automatically migrated.')
            else:
                hou.ui.displayMessage(state['error'] + '\nThe existing HIP and other DSH processes were not changed. '
                    'Check the isolated component-preview/host.log. A stopped Host is not automatically restarted.')
        timer.timeout.connect(tick)
        timer.start(100)
        threading.Thread(target=_worker, args=(config, facts, workspace, root, state), daemon=True).start()
    except Exception as error:
        hou.ui.displayMessage(str(error))
