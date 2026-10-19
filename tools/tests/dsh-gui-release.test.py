"""Actual Houdini menu and standalone Qt release acceptance in an isolated installation.

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
import urllib.parse
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, launch_directory, reexec_unpacked_test_cli


def close_desktop(install_root):
    import ctypes
    from ctypes import wintypes
    from dsh_workbench import running
    from dsh_deployment import _process_started
    record=running(install_root)
    if record is None:
        return
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def close(hwnd,unused):
        pid=wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==record['pid']:
            user.PostMessageW(hwnd,0x0010,0,0)
        return True
    user.EnumWindows(callback(close),0)
    deadline=time.monotonic()+30
    while time.monotonic()<deadline and _process_started(record['pid'])==record['processStarted']:
        time.sleep(.1)
    assert _process_started(record['pid'])!=record['processStarted'],'Own standalone desktop did not close normally'


def start_gui_probe():
    import hou, socket, threading, queue
    from hutil.Qt import QtCore, QtWidgets
    import dsh_bootstrap as bootstrap
    import dsh_deployment as deployment
    import dsh_workbench as workbench
    config=json.loads(Path(os.environ['DSH_GUI_TEST_CONFIG']).read_text(encoding='utf-8'))
    output=Path(config['output']);fixture=Path(config['root'])
    assert hou.isUIAvailable() and bootstrap._INITIALIZED and bootstrap._PINNED==config['installId']
    scene=fixture/'workspace'/('h'+str(hou.applicationVersion()[0]))/'smoke.hip';scene.parent.mkdir(parents=True,exist_ok=True)
    assert hou.hipFile.name().lower().endswith('untitled.hip')
    hou.hipFile.save(scene.as_posix())
    hou.qt.mainWindow().move(12000,12000)
    window=bootstrap.show_manager();window.move(12000,12000)
    state={'phase':'opening','started':time.monotonic(),'first':None,'reused':None,'busy':False,'debugPort':None}
    messages=queue.Queue()
    original_ensure=workbench.ensure
    def ensure(value, **kwargs):
        if state['debugPort'] is None:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1',0));state['debugPort']=probe.getsockname()[1]
        return original_ensure(dict(value,debugPort=state['debugPort']), **kwargs)
    workbench.ensure=ensure
    original_control=workbench.control
    def control(record, action, payload=None, timeout=120):
        value=original_control(record, action, payload, timeout)
        if action == 'open':
            state['launch']=value  # The Host's explicit native launch result, never writer ownership.
        return value
    workbench.control=control
    bootstrap.open_workspace()
    timer=QtCore.QTimer(hou.qt.mainWindow())
    def finish(ok,detail):
        timer.stop()
        deployment.atomic_json(output,{'ok':ok,'houdini':hou.applicationVersionString(),'gui':True,'standalone':True,'installId':config['installId'],'detail':detail})
        QtCore.QTimer.singleShot(100,hou.qt.mainWindow().close)
    def worker():
        try:
            import ctypes
            from ctypes import wintypes
            import dsh_launcher as launcher
            ctx=bootstrap._CONTEXT
            record=workbench.running(config['managed'])
            assert record and record['installation']==config['installId']
            status=workbench.control(record,'status',timeout=5)
            assert status['context']['dshVersion']=='0.2.1-rc.2'
            user=ctypes.WinDLL('user32',use_last_error=True)
            user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
            user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
            callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
            def move(hwnd,unused):
                pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                if pid.value==record['pid']:user.SetWindowPos(hwnd,0,12000,12000,0,0,0x15)
                return True
            user.EnumWindows(callback(move),0)
            # A restarted desktop has a new port. Query its live context.
            import urllib.request
            from dsh_web_auth import DshWebSession
            ctx=status['context']
            base='http://127.0.0.1:'+str(ctx['frontendPort'])
            auth=DshWebSession(base,str(Path(ctx['runtimeDir'])/'frontend.log'),str(Path(ctx['runtimeDir'])/'runtime.json'))
            auth.authorize(5)
            request=urllib.request.Request(base+'/api/session/list',data=json.dumps({'type':'client-request','rpcId':'release-current-desktop','method':'session/list','payload':{'args':{'_request':{}}}}).encode(),headers={'Content-Type':'application/json'})
            with auth.open(request,timeout=10) as response:
                listed=json.load(response)['result']
            assert listed['ok'],listed
            rows=listed['value']['items']
            from dsh_executor_registry import active_registration
            endpoint=deployment.read_json(active_registration()._file)
            launch=state.get('launch')
            assert launch and isinstance(launch.get('sessionId'),str), 'Open Workspace returned no explicit native session identity'
            sid=launch['sessionId']
            selected=[row for row in rows if row['sessionId']==sid]
            assert len(selected)==1, (launch, rows)
            row=selected[0]
            values=(row.get('projections') or {}).get('values',{})
            target=(values.get('houdiniExecutorIdentity') or {}).get('target')
            assert values.get('agentPreset')=='houdini' and target, row
            assert row.get('cwd') and Path(row['cwd']).resolve()==scene.parent.resolve(),row
            assert all(target[key]==endpoint[key] for key in ('executor_id','runtime_id','scene_epoch','scene_id')), (target,endpoint)
            assert launch.get('selectedTarget')==target, (launch,target)
            assert endpoint['task_id'] is None, 'Opening/selecting a scene must not acquire its writer'
            prior_ids=[value['sessionId'] for value in (state['first'],state['reused']) if value]
            assert all(any(row['sessionId']==previous for row in rows) for previous in prior_ids), 'Desktop reopening must retain native conversation history'
            result=output.with_suffix('.browser.json')
            png=output.with_suffix('.webview.png')
            subprocess.run([str(Path(ctx['install'])/'node/node.exe'),str(ROOT/'tools/tests/dsh-release-workbench-browser.mjs'),str(state['debugPort']),sid,str(scene.parent),str(png),str(result),'check-model-setup' if state['first'] is None else 'skip-model-setup'],check=True,capture_output=True,text=True,encoding='utf-8',timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            facts=deployment.read_json(result)
            runtime=deployment.read_json(Path(ctx['runtimeDir'])/'runtime.json')
            messages.put(('ready',dict(facts,sessionId=sid,desktopPid=record['pid'],hostPid=runtime['pid'],dshVersion=ctx['dshVersion'])))
        except Exception as error:
            import traceback
            messages.put(('error',traceback.format_exc()+getattr(error,'stderr','')))
    def tick():
        try:
            if time.monotonic()-state['started']>360:
                raise RuntimeError('Standalone GUI probe timed out')
            if bootstrap._LAST_OPEN_ERROR:
                raise RuntimeError(bootstrap._LAST_OPEN_ERROR)
            if not messages.empty():
                kind,value=messages.get_nowait()
                if kind=='error':raise RuntimeError(value)
                if kind=='closed':
                    state['busy']=False;state['phase']='restarting';bootstrap.open_workspace()
                    return
                state['busy']=False
                if state['first'] is None:
                    state['first']=value;state['phase']='reopening';bootstrap.open_workspace()
                    return
                assert value['sessionId']!=state['first']['sessionId'], 'Default Open Workspace creates a new explicit conversation, not a guessed historical one'
                if state['reused'] is None:
                    assert value['desktopPid']==state['first']['desktopPid']
                    assert value['hostPid']==state['first']['hostPid']
                    state['reused']=value;state['phase']='closing';state['busy']=True
                    def close_worker():
                        try:
                            close_desktop(config['managed'])
                            messages.put(('closed',None))
                        except Exception as error:
                            messages.put(('error',str(error)))
                    threading.Thread(target=close_worker,daemon=True).start()
                    return
                assert state['phase']=='restarting'
                assert value['sessionId']!=state['reused']['sessionId'], 'A restarted desktop retains history without silently selecting an old conversation'
                assert value['desktopPid']!=state['first']['desktopPid']
                assert value['hostPid']!=state['first']['hostPid']
                labels=[label.text() for label in window.findChildren(QtWidgets.QLabel) if label.isVisible()]
                assert '当前版本已加载。尚未检查更新。' in labels,labels
                assert window.grab().save(str(output.with_suffix('.manager.png')))
                finish(True,dict(value,newConversationOnDefaultOpen=True,historyRetained=True,samePidOnReopen=True,newPidAfterClose=True,apiKeyEntry=state['first']['apiKeyEntry'],setupScreenshot=state['first'].get('setupScreenshot'),managerTracksLoadedVersion=True))
                return
            if bootstrap._CONTEXT and not bootstrap._BUSY and not state['busy']:
                import dsh_workbench_client
                if not dsh_workbench_client._BUSY:
                    state['busy']=True
                    threading.Thread(target=worker,daemon=True).start()
        except Exception as error:
            finish(False,str(error))
    timer.timeout.connect(tick);timer.start(200)
    hou.session._dsh_gui_release_timer=timer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--trust", type=Path, required=True)
    parser.add_argument("--houdini", type=Path, action="append", required=True)
    parser.add_argument("--candidate", action="store_true")
    parser.add_argument("--reuse-fixture", type=Path,
                        help="Reuse only this test's verified installation; GUI preferences and HIP remain new")
    args = parser.parse_args()
    reexec_unpacked_test_cli()
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
    if args.reuse_fixture:
        previous_fixture = args.reuse_fixture.resolve(strict=True)
        temp_root = Path(tempfile.gettempdir()).resolve()
        if (previous_fixture.parent != temp_root or not previous_fixture.name.startswith("dsh-full-gui-中文 空格-")
                or previous_fixture.is_symlink()):
            raise ValueError("Reuse requires an existing own GUI-test fixture under the temporary directory")
        old_configs = list(previous_fixture.glob("config-*.json"))
        if not old_configs:
            raise ValueError("Reuse fixture has no original GUI-test configuration")
        configs = [deployment.read_json(path) for path in old_configs]
        if any(Path(config["root"]).resolve() != previous_fixture
               or Path(config["managed"]).resolve() != previous_fixture / "managed"
               or bool(config.get("candidate")) != args.candidate for config in configs):
            raise ValueError("Original fixture configuration does not identify this isolated installation")
        old_ids = {config["installId"] for config in configs}
        if len(old_ids) != 1:
            raise ValueError("Original fixture configurations disagree on the installation identity")
        install_root = previous_fixture / "managed"
    store = deployment.Store(install_root, deployment.read_json(args.trust), allow_candidate=args.candidate)
    if args.reuse_fixture:
        ident = next(iter(old_ids))
        saved_state = store.state()
        if ((saved_state["current"] != ident or saved_state["pending"] not in (None, ident))
                and (saved_state["pending"] != ident or saved_state["current"] not in (None, ident))):
            raise ValueError("Installation current/pending identity differs from the own fixture configuration")
        requested_manifest = deployment.load_signed(args.bundle, store.trust, allow_candidate=args.candidate)
        installed_manifest = store.manifest(ident)
        if requested_manifest != installed_manifest:
            raise ValueError("Reuse installation is not the entire exact signed release manifest requested")
        archive = args.bundle / requested_manifest["asset"]["name"]
        if archive.stat().st_size != requested_manifest["asset"]["size"] or deployment.digest(archive) != requested_manifest["asset"]["sha256"]:
            raise ValueError("Requested release archive differs from its signed manifest")
        inventory = deployment.verify_inventory(store.installation(ident), installed_manifest)
        deployment.atomic_json(fixture / "reuse-verification.json", {
            "manifest": installed_manifest, "installId": ident, "filesVerified": len(inventory),
            "originalFixture": str(previous_fixture), "state": saved_state})
        print("Exact signed installation reverified:", ident, len(inventory), "files", flush=True)
    else:
        ident = store.stage(args.bundle, lambda text: None)
    for executable in args.houdini:
        executable = executable.resolve(strict=True)
        # Installation folder names are user-selected; query the paired HOM
        # runtime instead of certifying a version from a directory label.
        hython = executable.with_name("hython.exe")
        version_env = isolated_environment(fixture / ("version-probe-" + executable.parent.parent.name), executable=hython)
        probe = subprocess.run([str(hython), "-c", "import hou; print('DSH_GUI_VERSION=' + '.'.join(map(str, hou.applicationVersion()[:2])))"],
                               cwd=launch_directory(hython), env=version_env, check=True, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=60,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        match = re.search(r"DSH_GUI_VERSION=(21\.0|22\.0)", probe.stdout)
        if not match:
            raise ValueError("test requires actual supported H21/H22 runtimes")
        version = match[1]
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
                close_desktop(install_root)
    print("Actual GUI installation, standalone workspace, selected task, pin and reopen acceptance passed", flush=True)


if __name__ == "__main__":
    main()
