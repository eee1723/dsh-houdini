"""Actual Houdini GUI release acceptance in an isolated installation.

No user's preferences/HIP are used. No model call is made. The launched GUI
process is owned by its Popen handle; its Node frontend has its own Job Object. This is
not a substitute for a second physical Windows machine or model-quality tests.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, launch_directory


def start_gui_probe():
    """Called by uiready.py in the newly launched Houdini, never by hython."""
    import hou
    from hutil.Qt import QtCore
    import dsh_bootstrap as bootstrap
    import dsh_deployment as deployment
    config = json.loads(Path(os.environ["DSH_GUI_TEST_CONFIG"]).read_text(encoding="utf-8"))
    output = Path(config["output"])
    fixture = Path(config["root"])
    assert hou.isUIAvailable(), "must run in the actual Houdini GUI"
    assert bootstrap._INITIALIZED and bootstrap._PINNED == config["installId"], "real startup hook did not pin the expected installation"
    if config.get("candidate"):
        trust = deployment.read_json(Path(config["trust"]))
        bootstrap.store = lambda: deployment.Store(config["managed"], trust, allow_candidate=True)
    scene = fixture / "workspace/smoke.hip"
    scene.parent.mkdir(parents=True, exist_ok=True)
    if Path(hou.hipFile.path()).name.lower() != "untitled.hip":
        raise RuntimeError("test GUI unexpectedly opened a non-fixture HIP")
    if scene.exists():
        hou.hipFile.load(str(scene), suppress_save_prompt=True, ignore_load_warnings=True)
    else:
        hou.hipFile.save(str(scene))
    messages = queue.Queue()
    state = {"phase": "opening", "started": time.monotonic(), "probe": False, "js": None, "first": None, "lastPhase": None}
    # Only this test instance's dialogs are intercepted to make failures finite
    # and observable; production code and the user's Houdini are untouched.
    original_message = hou.ui.displayMessage
    def record_dialog(message, *args, **kwargs):
        messages.put(("error", str(message)))
        return 0
    hou.ui.displayMessage = record_dialog
    window = bootstrap.show_manager()
    window.move(12000, 12000)
    bootstrap.open_workspace()
    timer = QtCore.QTimer(hou.qt.mainWindow())
    def finish(ok, detail):
        timer.stop()
        hou.ui.displayMessage = original_message
        deployment.atomic_json(output, {"ok": ok, "houdini": hou.applicationVersionString(), "gui": True,
            "installId": config["installId"], "phase": state["phase"], "detail": detail})
        # hou.exit raises SystemExit; from a PySide timer that can finalize
        # Python before Houdini's C++ UI destructors. Exercise the real window
        # close route instead, then require a clean process exit in the driver.
        QtCore.QTimer.singleShot(100, hou.qt.mainWindow().close)
    def probe_worker():
        try:
            import dsh_launcher as launcher
            import dsh_manager as manager
            ctx = bootstrap._CONTEXT
            runtime = manager._runtime_dsh_info()
            assert runtime["verified"] and runtime["version"] == ctx["dshVersion"]
            pid = manager._port_pid(ctx["frontendPort"])
            assert isinstance(pid, int) and pid > 0
            sessions = launcher._dsh_rpc_wire("session/list", {"args": {"_request": {}}}).get("items")
            rows = [row for row in sessions
                    if row.get("cwd") and Path(row["cwd"]).resolve() == scene.parent.resolve()
                    and (row.get("projections") or {}).get("values", {}).get("agentPreset") == "houdini"]
            assert len(rows) == 1, "The native client must create/reuse exactly one Houdini-preset task"
            sid = rows[0]["sessionId"]
            plugin = Path(ctx["install"]) / "app/node_modules/dsh-houdini"
            script = """
const {HoudiniBridge} = await import(process.argv[1]);
const result = await new HoudiniBridge(process.argv[2],15000).exec("__result__ = hou.node('/obj').path()",undefined,undefined,{sessionId:'gui-release',callId:'read'},true);
if(!result.ok || result.result!=='/obj') throw Error('readonly GUI bridge call failed');
"""
            subprocess.run([str(Path(ctx["install"]) / "node/node.exe"), "--input-type=module", "-e", script,
                            (plugin / "lib/bridge.js").as_uri(), f"http://127.0.0.1:{ctx['bridgePort']}"],
                            env=deployment.runtime_env(ctx), capture_output=True, check=True, timeout=30,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            messages.put(("probe", {"sessionId": sid, "pid": pid, "nodeVersion": ctx["nodeVersion"],
                                    "dshVersion": ctx["dshVersion"], "workspace": str(scene.parent), "frontendPort": ctx["frontendPort"]}))
        except Exception as exc:
            messages.put(("error", type(exc).__name__ + ": " + str(exc)))
    def javascript(page):
        page.runJavaScript("""
if (!window.__releaseSmoke) {
  window.__releaseSmoke = {pending:true};
  fetch('/api/session/list',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:'gui-release',method:'session/list',payload:{args:{_request:{}}}})})
    .then(async r=>{const j=await r.json();window.__releaseSmoke={status:r.status,ok:j.result?.ok===true,count:j.result?.value?.items?.length};})
    .catch(e=>{window.__releaseSmoke={error:String(e)}});
}
JSON.stringify({ready:document.readyState,text:document.body?.innerText?.slice(0,6000),rpc:window.__releaseSmoke,tokenInUrl:new URL(location.href).searchParams.has('token'),navigationPending:new URL(location.href).searchParams.has('dsh-houdini-workspace'),navigationError:document.querySelector('#dsh-houdini-navigation[role="alert"]')?.textContent});
""", 0, lambda value: state.update(js=json.loads(value) if value else None))
    def tick():
        try:
            if time.monotonic() - state["started"] > 600:
                finish(False, "GUI acceptance timed out; inspect the isolated runtime log")
                return
            if state["lastPhase"] != state["phase"]:
                state["lastPhase"] = state["phase"]
                deployment.atomic_json(output.with_suffix(".progress.json"), {"phase": state["phase"], "elapsed": int(time.monotonic()-state["started"])})
            while not messages.empty():
                kind, value = messages.get_nowait()
                if kind == "error":
                    finish(False, value)
                    return
                if kind == "probe":
                    import dsh_webview as webview
                    if state["first"] is None:
                        state["first"] = value
                        state.update(phase="reopening", probe=False, js=None)
                        bootstrap.open_workspace()
                        return
                    assert value["sessionId"] == state["first"]["sessionId"], "reopen created a duplicate session"
                    assert value["pid"] == state["first"]["pid"], "reopen restarted the serving runtime"
                    assert webview._window.grab().save(str(output.with_suffix(".webview.png")))
                    assert window.grab().save(str(output.with_suffix(".manager.png")))
                    finish(True, {**value, "webRpc": True, "sameSessionOnReopen": True, "samePidOnReopen": True,
                                  "bodyText": state["js"]["text"][:2000]})
                    return
            if bootstrap._CONTEXT is None:
                return
            import dsh_webview as webview
            if webview._view is None:
                return
            webview._window.move(12000, 12000)
            javascript(webview._view.page())
            observed = state["js"]
            if observed and observed.get("navigationError"):
                finish(False, observed["navigationError"])
                return
            if (observed and observed.get("ready") == "complete" and len(observed.get("text") or "") > 80
                    and observed.get("rpc", {}).get("ok") and observed["rpc"].get("count", 0) >= 1
                    and not observed.get("tokenInUrl") and not observed.get("navigationPending") and not state["probe"]):
                state["probe"] = True
                state["phase"] = "checking-reopen" if state["first"] else "checking-workspace"
                threading.Thread(target=probe_worker, daemon=True).start()
        except Exception as exc:
            finish(False, type(exc).__name__ + ": " + str(exc))
    timer.timeout.connect(tick)
    timer.start(500)
    hou.session._dsh_gui_release_timer = timer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--trust", type=Path, required=True)
    parser.add_argument("--houdini", type=Path, action="append", required=True)
    parser.add_argument("--candidate", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
    import dsh_deployment as deployment
    import dsh_managed_runtime as managed
    fixture = Path(tempfile.mkdtemp(prefix="dsh-full-gui-中文 空格-"))
    print("GUI fixture:", fixture, flush=True)
    installer = fixture / "installer"
    installer.mkdir()
    with zipfile.ZipFile(args.bundle / "dsh-houdini-installer.zip") as archive:
        for info in archive.infolist():
            path = deployment.checked_path(installer, info.filename.rstrip("/"))
            if info.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, path.open("xb") as target:
                    import shutil
                    shutil.copyfileobj(source, target)
    install_root = fixture / "managed"
    store = deployment.Store(install_root, deployment.read_json(args.trust), allow_candidate=args.candidate)
    ident = store.stage(args.bundle, lambda text: None)
    for executable in args.houdini:
        executable = executable.resolve(strict=True)
        match = re.search(r"Houdini (21|22)\.0", str(executable))
        if not match:
            raise ValueError("test requires explicit H21/H22 executable paths")
        version = match[1] + ".0"
        py_version = "3.11" if version == "21.0" else "3.13"
        env = isolated_environment(fixture / ('gui-' + version), executable=executable, gui=True)
        prefs_pattern = env['HOUDINI_USER_PREF_DIR']
        prefs = Path(prefs_pattern.replace("__HVER__", version))
        env["PATH"] = str(executable.parent) + os.pathsep + str(Path(os.environ["WINDIR"]) / "System32") + os.pathsep + str(Path(os.environ["WINDIR"]) / "System32/WindowsPowerShell/v1.0")
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(installer / "installer/install.ps1"),
                        "-Root", str(install_root), "-PackagesDir", str(prefs / "packages")], env=env, check=True,
                        capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        hook = prefs / ("python" + py_version + "libs/uiready.py")
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("import importlib.util\ns=importlib.util.spec_from_file_location('release_gui_probe', " + repr(str(Path(__file__).resolve())) + ")\nm=importlib.util.module_from_spec(s)\ns.loader.exec_module(m)\nm.start_gui_probe()\n", encoding="utf-8")
        result = fixture / ("gui-" + version + ".json")
        config_file = fixture / ("config-" + version + ".json")
        deployment.atomic_json(config_file, {"root": str(fixture), "managed": str(install_root), "installId": ident,
                                           "output": str(result), "trust": str(args.trust.resolve()), "candidate": args.candidate})
        env["DSH_GUI_TEST_CONFIG"] = str(config_file)
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 0
        with (fixture / ("houdini-" + version + ".log")).open("wb") as log:
            process = subprocess.Popen([str(executable), "-foreground", "-geometry=1024x768+12000+12000"],
                                       # Match the vendor shortcut. H22's Qt
                                       # helper resolves native DLLs from this
                                       # launch directory, independently of $HIP.
                                       cwd=launch_directory(executable), env=env, stdout=log, stderr=subprocess.STDOUT,
                                       startupinfo=info, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            # Do not put the GUI host inside the Node-style restrictive job:
            # Chromium's Windows sandbox must establish its own child jobs.
            try:
                deadline = time.monotonic() + 720
                last = None
                while not result.exists() and time.monotonic() < deadline:
                    progress = result.with_suffix(".progress.json")
                    if progress.exists():
                        value = deployment.read_json(progress)
                        if value != last:
                            print(version, value, flush=True)
                            last = value
                    time.sleep(1)
                if not result.exists():
                    raise RuntimeError("No GUI result; inspect " + str(fixture))
                value = deployment.read_json(result)
                print(json.dumps(value, ensure_ascii=True), flush=True)
                if not value["ok"]:
                    raise RuntimeError("GUI release acceptance failed")
                try:
                    exit_code = process.wait(timeout=30)
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError("GUI did not shut down through its normal close route") from exc
                if exit_code != 0:
                    value.update(ok=False, processExit=exit_code)
                    deployment.atomic_json(result, value)
                    raise RuntimeError("GUI process failed during shutdown: " + str(exit_code))
                value["processExit"] = exit_code
                deployment.atomic_json(result, value)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=20)
    print("Actual H21/H22 GUI installation, workspace, reopen and WebView acceptance passed", flush=True)


if __name__ == "__main__":
    main()
