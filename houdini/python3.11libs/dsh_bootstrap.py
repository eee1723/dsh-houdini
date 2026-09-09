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
_EVENTS = queue.Queue()


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
    return dsh_install_ui.show(store(), pinned=_PINNED, loaded=_CONTEXT, startup_error=_ERROR,
                               context_provider=lambda: (_PINNED, _CONTEXT))


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
    global _BUSY, _TIMER
    initialize()
    if _CONTEXT is not None:
        import dsh_launcher
        return dsh_launcher.open_workspace()
    if _ERROR or not _PINNED:
        return show_manager()
    if _BUSY:
        return
    import hou
    from hutil.Qt import QtCore
    # Capture HOM data on the GUI thread; workers never call hou.
    version = ".".join(str(x) for x in hou.applicationVersion()[:2])
    if any(name in sys.modules for name in ("dsh_launcher", "dsh_bridge", "dsh_hou_helpers")):
        hou.ui.displayMessage("A source/other plugin runtime is already loaded. Restart Houdini to use the managed installation.")
        return
    _BUSY = True
    def worker():
        try:
            context, lease = store().activate(_PINNED, version, lambda text: _EVENTS.put(("progress", text)), _prepare)
            _EVENTS.put(("ready", (context, lease)))
        except Exception as exc:
            _EVENTS.put(("error", str(exc)))
    def tick():
        global _BUSY, _CONTEXT, _LEASE
        while not _EVENTS.empty():
            kind, value = _EVENTS.get_nowait()
            if kind == "progress":
                hou.ui.setStatusMessage(value)
            else:
                _TIMER.stop()
                _BUSY = False
                if kind == "error":
                    hou.ui.displayMessage(value)
                    show_manager()
                    return
                _CONTEXT, _LEASE = value
                os.environ["DSH_HOUDINI_MANAGED_CONTEXT"] = str(Path(_CONTEXT["runtimeDir"]) / "context.json")
                sys.dont_write_bytecode = True
                plugin = Path(_CONTEXT["install"]) / "app/node_modules/dsh-houdini"
                sys.path.insert(0, str(plugin / "houdini/python3.11libs"))
                import dsh_launcher
                dsh_launcher.open_workspace()
    _TIMER = QtCore.QTimer(hou.qt.mainWindow())
    _TIMER.timeout.connect(tick)
    _TIMER.start(100)
    threading.Thread(target=worker, daemon=True).start()
