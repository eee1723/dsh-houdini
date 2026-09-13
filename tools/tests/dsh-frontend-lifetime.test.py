"""Real Windows source/managed frontend ownership; no DSH server, model or HIP."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import importlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
sys.modules.setdefault("hou", types.SimpleNamespace())
import dsh_launcher as launcher
import dsh_managed_runtime as runtime

assert os.name == "nt", "frontend Job regression requires Windows"
node = launcher.NODE
identity=runtime.executor_identity()
with patch.dict(os.environ,{'DSH_HOUDINI_EXECUTOR_ID':'f'*32}):
    importlib.reload(runtime)
    assert runtime.executor_identity()==identity,'reload/inherited env cannot change this process identity'
    fresh=subprocess.run([sys.executable,'-c',
        'import sys;sys.path.insert(0,sys.argv[1]);import dsh_managed_runtime as r;print(r.executor_identity())',
        str(ROOT/'houdini/python3.11libs')],capture_output=True,text=True,timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert fresh.returncode==0,fresh.stderr
    assert fresh.stdout.strip() not in (identity,'f'*32),fresh.stdout
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel.CloseHandle.argtypes = [wintypes.HANDLE]


def rows_from(process):
    rows = queue.Queue()
    def read():
        for line in process.stdout:
            rows.put(json.loads(line))
    threading.Thread(target=read, daemon=True).start()
    return rows


with tempfile.TemporaryDirectory(prefix="dsh-frontend-lifetime-中文 空格-") as temporary:
    fixture = Path(temporary)
    esm_entry = fixture / "native-main.mjs"
    esm_entry.write_text("""
if (!import.meta.main) throw Error('the CLI must remain the native Node main entry');
if (process.execArgv.length) throw Error('startup preload leaked into future fork/worker options');
console.log(JSON.stringify(process.argv.slice(2)));
""", encoding="utf-8")
    process = runtime.spawn_frontend(
        [node, str(esm_entry), "--fixture"], node=node, cwd=fixture,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr
        assert json.loads(stdout) == ["--fixture"]
    finally:
        runtime.stop_owned()

    entry = fixture / "entry.cjs"
    entry.write_text("""
const role = Number(process.argv[2]);
const report = value => console.log(JSON.stringify({role, pid: process.pid, ...value}));
if (role < 2) {
  report({argv: process.argv.slice(2), execArgv: process.execArgv});
  const child = require('node:child_process').spawn(process.execPath, [__filename, String(role + 1)], {
    stdio: ['ignore', 'pipe', 'inherit'], windowsHide: true
  });
  child.stdout.pipe(process.stdout);
} else {
  const server = require('node:net').createServer(socket => socket.end());
  server.listen(0, '127.0.0.1', () => report({port: server.address().port}));
}
setInterval(() => {}, 1000);
""", encoding="utf-8")
    external = subprocess.Popen(
        [node, str(entry), "2"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        external_row = rows_from(external).get(timeout=10)
        previous_process = None
        for use_shell in (False, True):
            original = [node, str(entry), "0"]
            command = subprocess.list2cmdline(original) if use_shell else original
            process = runtime.spawn_frontend(
                command, node=node, shell=use_shell, cwd=fixture,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            handles = []
            try:
                # A queued cancel from an older dialog must not touch this Job.
                assert launcher._terminate_pending_frontend(expected_process=None) is False
                if previous_process is not None:
                    for _ in range(2):
                        assert launcher._terminate_pending_frontend(expected_process=previous_process) is False
                rows = rows_from(process)
                observed = [rows.get(timeout=10) for _ in range(3)]
                assert {item["role"] for item in observed} == {0, 1, 2}, observed
                parent = next(item for item in observed if item["role"] == 0)
                listener = next(item for item in observed if item["role"] == 2)
                assert parent["argv"] == ["0"], "the direct CLI must receive its original argv"
                assert parent["execArgv"] == [], "fork/worker children must not inherit the startup gate"
                assert (parent["pid"] != process.pid) is use_shell
                for item in observed:
                    assert runtime.owns_pid(item["pid"]), item
                    handle = kernel.OpenProcess(0x100000 | 0x1000, False, item["pid"])
                    assert handle, ctypes.get_last_error()
                    handles.append(handle)
                assert not runtime.owns_pid(external.pid)
                assert not runtime.owns_pid(os.getpid())
                assert not runtime.owns_pid(None)

                with patch.object(launcher, "FRONTEND_PORT", listener["port"]), \
                     patch.object(launcher, "FRONTEND_URL", f"http://127.0.0.1:{listener['port']}"):
                    assert launcher._frontend_online(), "an npx descendant is our owned listener"
                # Even with a valid owned Job, Repair must not stop it when an
                # unrelated process occupies the frontend port instead.
                with patch.object(launcher, "FRONTEND_PORT", external_row["port"]):
                    try:
                        launcher.restart_frontend()
                    except RuntimeError as exc:
                        assert "frontend port conflict" in str(exc)
                    else:
                        raise AssertionError("unknown listener did not block repair")
                assert process.poll() is None and external.poll() is None

                # This is the actual GUI success cleanup and manager repair reload.
                # The persistent runtime Job, not _PENDING or runtime.json, owns it.
                launcher._PENDING.clear()
                importlib.reload(launcher)
                assert all(runtime.owns_pid(item["pid"]) for item in observed)
                marker = fixture / "runtime.json"
                marker.write_text('{"fixture": true}', encoding="utf-8")
                with patch.object(launcher, "FRONTEND_RUNTIME_STATE", str(marker)):
                    assert launcher._terminate_pending_frontend()
                assert not marker.exists()
                for handle in handles:
                    assert kernel.WaitForSingleObject(handle, 10000) == 0, "owned descendant survived"
                assert process.wait(timeout=10) is not None
                assert external.poll() is None, "an unrelated process was stopped"
                assert runtime.stop_owned() is False, "stopping the same Job must be idempotent"
                previous_process = process
            finally:
                runtime.stop_owned()
                process.wait(timeout=10)
                for handle in handles:
                    kernel.CloseHandle(handle)
                process.stdout.close()
                process.stderr.close()

        # A failed Job assignment must not execute even the CLI's first line.
        marker = fixture / "must-not-execute.txt"
        blocked = fixture / "blocked.cjs"
        blocked.write_text("require('node:fs').writeFileSync(process.argv[2], 'ran');", encoding="utf-8")
        with patch.object(runtime, "own_process", side_effect=RuntimeError("assignment fixture")):
            try:
                runtime.spawn_frontend(
                    [node, str(blocked), str(marker)], node=node, cwd=fixture,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except RuntimeError as exc:
                assert str(exc) == "assignment fixture"
            else:
                raise AssertionError("failed ownership released the entrypoint")
        assert not marker.exists()
    finally:
        runtime.stop_owned()
        external.terminate()
        external.wait(timeout=10)
        external.stdout.close()
        external.stderr.close()

print("Frontend ownership: direct CLI/npx descendants, conflict isolation, reload and gated startup passed")
