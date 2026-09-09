"""Load the installed signed Python/Node pair in an isolated hython and exercise HTTP.

Invoked by the offline bundle e2e with DSH_HOUDINI_MANAGED_CONTEXT; never loads a
HIP or calls an LLM. The main thread explicitly pumps the headless bridge queue.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import time

filename = os.environ["DSH_HOUDINI_MANAGED_CONTEXT"]
ctx = json.loads(Path(filename).read_text(encoding="utf-8"))
plugin = Path(ctx["install"]) / "app/node_modules/dsh-houdini"
sys.dont_write_bytecode = True
sys.path.insert(0, str(plugin / "houdini/python3.11libs"))
import hou
import dsh_launcher as launcher
import dsh_manager as manager
import dsh_bridge as bridge
import dsh_webview as webview

for module in (launcher, manager, bridge, webview):
    assert Path(module.__file__).resolve().is_relative_to(plugin.resolve()), module.__file__
assert launcher.FRONTEND_PORT == manager._FRONTEND_PORT == webview.FRONTEND_PORT == ctx["frontendPort"]
assert launcher.BRIDGE_PORT == manager._BRIDGE_PORT == ctx["bridgePort"]
assert not Path(launcher._FALLBACK_WORKSPACE).is_relative_to(Path(ctx["install"]))
assert launcher._frontend_command()[2] == "managed-cli"
assert launcher.ensure_dependencies() == "managed dependencies ok (no package manager)"
runtime = manager._runtime_dsh_info()
assert runtime["verified"] and runtime["version"] == ctx["dshVersion"], runtime
assert launcher._kill_port_process(ctx["bridgePort"]) is False

bridge.start(ctx["bridgePort"])
bridge._pump_active = True
script = """
const { HoudiniBridge } = await import(process.argv[1]);
const bridge = new HoudiniBridge(process.argv[2], 15000);
const result = await bridge.exec("__result__ = hou.node('/obj').path()", undefined, undefined, {sessionId:'deployment-smoke',callId:'readonly'}, true);
if (!result.ok || result.result !== '/obj') throw new Error(JSON.stringify(result));
console.log('Managed Node/Bridge contract handshake and main-thread readonly HTTP exec passed');
"""
process = None
try:
    process = subprocess.Popen([str(Path(ctx["install"]) / "node/node.exe"), "--input-type=module", "-e", script,
                                (plugin / "lib/bridge.js").as_uri(), f"http://127.0.0.1:{ctx['bridgePort']}"],
                               cwd=plugin, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    deadline = time.monotonic() + 30
    while process.poll() is None and time.monotonic() < deadline:
        bridge._pump()
        time.sleep(0.02)
    assert process.poll() == 0, "installed bridge/client smoke failed or timed out"
finally:
    if process is not None and process.poll() is None:
        process.kill()
        process.wait(timeout=10)
    bridge.stop()
assert manager._runtime_dsh_info()["verified"], "the bridge smoke must not stop the independent frontend"
print("Installed managed bindings and readonly transport passed on", hou.applicationVersionString())
