"""Real signed payload smoke: isolated data, portable Node, profile and authenticated RPC.

No Houdini scene is loaded, no model call is made, and no user service is stopped.
Usage: python ... --bundle <signed-build-dir> --trust <trusted-public-keys.json>
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, launch_directory
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
import dsh_deployment as d
import dsh_bootstrap as bootstrap
import dsh_managed_runtime as managed
from dsh_web_auth import DshWebSession

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--bundle", type=Path, required=True)
parser.add_argument("--trust", type=Path, required=True)
parser.add_argument("--hython", action="append", type=Path, default=[])
args = parser.parse_args()
trust = d.read_json(args.trust)
# Persistent test output is intentionally outside user data; retain failure evidence.
test_root = Path(tempfile.mkdtemp(prefix="dsh-real-install-中文 空格-"))
print("Isolated test directory:", test_root, flush=True)
store = d.Store(test_root / "managed", trust, allow_candidate=True)
ident = store.stage(args.bundle, lambda text: print(text, flush=True))
ctx, lease = store.activate(ident, "21.0", lambda text: print(text, flush=True), bootstrap._prepare)
install = Path(ctx["install"])
env = d.runtime_env(ctx)
env["DSH_HOUDINI_MANAGED_CONTEXT"] = str(Path(ctx["runtimeDir"]) / "context.json")
# A clean PATH verifies the app uses its bundled Node. Windows system tools
# remain available, but neither Git nor a system Node/npm is reachable.
env["PATH"] = str(install / "node") + os.pathsep + str(Path(os.environ["WINDIR"]) / "System32")
assert env["DSH_HOME"] != str(Path.home() / ".dsh")
# Verify the profile's root tools as well as per-agent presets bind to this
# managed Bridge, not a developer's unrelated listener on the default port.
binding_script = """
import {loadProfile, composeEntries} from '@deepseek-ai/dsh-app-boot';
import {interpolate} from '@deepseek-ai/cordis-plugin-loader';
import path from 'node:path';
const profile = loadProfile('dsh','web',path.resolve('node_modules/@deepseek-ai/dsh/package.json'));
const entries = composeEntries([...profile.layers.map(x=>x.patches), profile.patches]);
const row = entries.find(x=>x.id==='houdini');
if (!row || interpolate({}, row.config).bridgeUrl !== process.env.DSH_HOUDINI_BRIDGE_URL) throw Error('managed root tool binding is incorrect');
"""
subprocess.run([str(install / "node/node.exe"), "--input-type=module", "-e", binding_script],
               cwd=install / "app", env=env, capture_output=True, check=True, timeout=60)
cwd = test_root / "workspace"
cwd.mkdir()
log = Path(ctx["runtimeDir"]) / "frontend.log"
base = f"http://127.0.0.1:{ctx['frontendPort']}"
process = None
try:
    with log.open("wb") as output:
        process = subprocess.Popen([str(install / "node/node.exe"), str(install / "app/node_modules/@deepseek-ai/dsh/lib/bin.js"), "web", "--port", str(ctx["frontendPort"]), "--no-open"],
                                   cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        managed.own_process(process)
        d.atomic_json(Path(ctx["runtimeDir"]) / "runtime.json", {"pid": process.pid, "version": ctx["dshVersion"], "authLogOffset": 0, "source": "managed-e2e"})
        auth = DshWebSession(base, str(log), str(Path(ctx["runtimeDir"]) / "runtime.json"))
        deadline = time.monotonic() + 90
        last_error = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Bundled frontend exited before readiness; inspect the isolated frontend.log")
            try:
                auth.authorize(timeout=3)
                rpc_body = json.dumps({"type": "client-request", "rpcId": "release-smoke-list", "method": "session/list", "payload": {"args": {"_request": {}}}}).encode()
                request = urllib.request.Request(base + "/api/session/list", data=rpc_body, headers={"Content-Type": "application/json"}, method="POST")
                with auth.open(request, timeout=3) as response:
                    result = json.load(response)
                    assert response.status == 200 and result.get("result", {}).get("ok") is True, "RPC must succeed, not merely return HTTP 200"
                    assert isinstance(result["result"].get("value", {}).get("items"), list)
                break
            except Exception as exc:
                last_error = type(exc).__name__
                time.sleep(0.3)
        else:
            raise RuntimeError("Bundled frontend RPC was not ready: " + str(last_error))
        # Unauthenticated API requests must not silently gain access.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        # CookieJar adds headers to a Request object in-place. A genuinely
        # unauthenticated check must use a fresh object, not the authorized one.
        unauthenticated = urllib.request.Request(base + "/api/session/list", data=rpc_body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            opener.open(unauthenticated, timeout=3)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("unauthenticated RPC was accepted")
        presets = Path(ctx["home"]) / ".agent-presets/houdini/agent.cordis.yml"
        assert f"bridgeUrl: http://127.0.0.1:{ctx['bridgePort']}" in presets.read_text(encoding="utf-8")
        assert not (install / "app/node_modules/dsh-houdini/node_modules").exists()
        print("Real portable Node + exact DSH + isolated profile + plugin import + 401/200 authenticated RPC passed", flush=True)
        for hython in args.hython:
            prefs = tempfile.mkdtemp(prefix="dsh-installed-houdini-")
            hython = hython.resolve(strict=True)
            child_env = isolated_environment(prefs, executable=hython, base=env)
            # Restore only this fixture's explicitly created managed identity.
            child_env.update(DSH_HOME=ctx['home'], DSH_HOUDINI_MANAGED_CONTEXT=env['DSH_HOUDINI_MANAGED_CONTEXT'])
            subprocess.run([str(hython), str(ROOT / "tools/tests/dsh-managed-houdini.test.py")],
                           cwd=launch_directory(hython), env=child_env, check=True, timeout=120,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
finally:
    managed.stop_owned()
    if process is not None:
        process.wait(timeout=20)
    lease.close()
assert process.returncode is not None
print("Owned frontend terminated; no external process or user HIP was touched", flush=True)
