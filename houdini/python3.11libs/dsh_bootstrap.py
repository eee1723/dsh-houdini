"""Stable Houdini menu host: pins an installation at process startup.

Missing Node/DSH/plugin files never prevent opening the independent manager.
Verification, data snapshots and subprocesses run only in a worker thread.
"""
from __future__ import annotations

import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import uuid

import dsh_deployment as deployment

_INITIALIZED = False
_PINNED = None
_ERROR = None
_CONTEXT = None
_LEASE = None
_TIMER = None
_BUSY = False
_PROBLEM_WINDOW = None
_LAST_OPEN_ERROR = None
_EVENTS = queue.Queue()
_BOOTSTRAP_MODULES = frozenset((
    "dsh_bootstrap", "dsh_deployment", "dsh_release_policy", "dsh_install_ui", "dsh_ui_style",
    "dsh_support_ui", "dsh_support_report", "dsh_workbench",
))


def store():
    root = os.environ.get("DSH_HOUDINI_INSTALL_ROOT") or str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DSH-Houdini")
    trust = Path(__file__).resolve().parents[1] / "release-trust.json"
    if not trust.is_file():
        trust = Path(__file__).resolve().parents[2] / "installer/release-trust.json"
    return deployment.Store(root, deployment.read_json(trust))


def initialize():
    global _INITIALIZED, _PINNED, _ERROR
    if _INITIALIZED:
        return
    _INITIALIZED = True
    try:
        state = store().state()
        _PINNED = state["pending"] or state["current"]
    except Exception as exc:
        _ERROR = str(exc)


def show_manager():
    initialize()
    import dsh_install_ui
    return dsh_install_ui.show(store(), pinned=_PINNED, loaded=_CONTEXT, startup_error=_ERROR or _LAST_OPEN_ERROR,
                               context_provider=lambda: (_PINNED, _CONTEXT), startup_error_provider=lambda: _ERROR or _LAST_OPEN_ERROR)


def _prepare(context, progress):
    # Distinct ports avoid binding to, reusing, or stopping a developer's DSH.
    with socket.socket() as bridge, socket.socket() as frontend:
        bridge.bind(("127.0.0.1", 0))
        frontend.bind(("127.0.0.1", 0))
        context["bridgePort"] = bridge.getsockname()[1]
        context["frontendPort"] = frontend.getsockname()[1]
    context["runtimeDir"] = str(Path(context["root"]) / "runtime" / (str(os.getpid()) + "-" + uuid.uuid4().hex[:8]))
    runtime = Path(context["runtimeDir"])
    runtime.mkdir(parents=True)
    context_file = runtime / "context.json"
    deployment.atomic_json(context_file, context)
    progress("Preparing the isolated DSH profile and Houdini presets")
    install = Path(context["install"])
    result = subprocess.run(
        [str(install / "node/node.exe"), str(install / "app/prepare-profile.mjs"), str(context_file)],
        cwd=install / "app", env=deployment.runtime_env(context), capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise RuntimeError("Isolated profile preparation failed: " + (result.stderr or result.stdout)[-3000:])


def open_workspace():
    global _BUSY, _TIMER, _LAST_OPEN_ERROR
    initialize()
    from dsh_ui_style import clear_startup_problem
    clear_startup_problem()
    _LAST_OPEN_ERROR = None
    if _ERROR or not _PINNED:
        return show_manager()
    if _BUSY:
        return
    import hou
    # Opening source diagnostics already imports runtime/path modules, without
    # importing the launcher. Those cached modules cannot serve another release.
    if _CONTEXT is None and any(name.startswith("dsh_") and name not in _BOOTSTRAP_MODULES
           and module is not None for name, module in tuple(sys.modules.items())):
        hou.ui.displayMessage("当前进程已加载源码版或其他版本的运行模块。请完整重开 Houdini，再使用受管安装。")
        return
    from hutil.Qt import QtCore
    # Capture HOM data on the GUI thread; workers never call hou.
    version = ".".join(str(x) for x in hou.applicationVersion()[:2])
    config = {'managed': True, 'root': str(store().root), 'installation': _PINNED,
              'trustData': store().trust, 'houdiniVersion': version,
              'hfs': os.environ['HFS'], 'python': str(Path(sys.prefix) / 'python.exe')}
    initial_unsaved = hou.hipFile.isNewFile()
    config['initialWorkspaceIsNew'] = initial_unsaved
    if not initial_unsaved:
        config['initialWorkspace'] = str(Path(hou.hipFile.path()).parent)
    else:
        loaded_launcher = sys.modules.get('dsh_launcher')
        existing = getattr(loaded_launcher, '_UNSAVED_WORKSPACE', None) if _CONTEXT is not None else None
        scratch = Path(existing) if existing else store().root / 'workspaces/unsaved' / ('untitled-' + str(os.getpid()) + '-' + uuid.uuid4().hex[:8])
        scratch.mkdir(parents=True, exist_ok=True)
        config['initialWorkspace'] = str(scratch)
    _BUSY = True
    def worker():
        try:
            os.environ['DSH_HOUDINI_WORKBENCH_ROOT'] = config['root']
            from dsh_workbench import ensure
            desktop = ensure(config)
            _EVENTS.put(("ready", (desktop['context'], None)))
        except Exception as exc:
            _EVENTS.put(("error", exc))
    def tick():
        global _BUSY, _CONTEXT, _LEASE, _PROBLEM_WINDOW, _LAST_OPEN_ERROR
        while not _EVENTS.empty():
            kind, value = _EVENTS.get_nowait()
            if kind == "progress":
                hou.ui.setStatusMessage(value)
            else:
                _TIMER.stop()
                _BUSY = False
                if kind == "error":
                    from dsh_ui_style import show_startup_problem
                    message = deployment.workspace_busy_message(value) if isinstance(value, deployment.LeaseBusyError) and value.path.name == 'runtime.lock' else str(value)
                    detail = str(value) + ('\n' + str(value.owner) if isinstance(value, deployment.LeaseBusyError) else '')
                    _LAST_OPEN_ERROR = detail
                    _PROBLEM_WINDOW = show_startup_problem(message, detail, hou.qt.mainWindow())
                    return
                _CONTEXT, _LEASE = value
                os.environ["DSH_HOUDINI_MANAGED_CONTEXT"] = str(Path(_CONTEXT["runtimeDir"]) / "context.json")
                sys.dont_write_bytecode = True
                plugin = Path(_CONTEXT["install"]) / "app/node_modules/dsh-houdini"
                sys.path.insert(0, str(plugin / "houdini/python3.11libs"))
                import dsh_launcher
                if initial_unsaved and hou.hipFile.isNewFile() and dsh_launcher._UNSAVED_WORKSPACE is None:
                    dsh_launcher._UNSAVED_WORKSPACE = config['initialWorkspace']
                dsh_launcher.open_workspace()
    _TIMER = QtCore.QTimer(hou.qt.mainWindow())
    _TIMER.timeout.connect(tick)
    _TIMER.start(100)
    threading.Thread(target=worker, daemon=True).start()
