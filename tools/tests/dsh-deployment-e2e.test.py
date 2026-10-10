"""Real signed payload smoke: isolated data, portable Node, profile and authenticated RPC.

No Houdini scene is loaded, no model call is made, and no user service is stopped.
Usage: python ... --bundle <signed-build-dir> --trust <trusted-public-keys.json>
       [--previous-bundle <previous-signed-build-dir>]
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


def progress(message):
    print(message, flush=True)


def fixture_data(home, label):
    # Inert session/config artifacts test Store's byte-preserving snapshot.
    # They do not claim native DSH session-format conversion or model resume.
    files = {
        "release-e2e/session.json": {"id": "dummy-session", "messages": [{"role": "user", "content": label}]},
        "release-e2e/config.json": {"fixture": label, "models": [], "credentials": {}},
    }
    for name, value in files.items():
        d.atomic_json(home / name, value)
    return {name: (home / name).read_bytes() for name in files}


def assert_data(home, expected):
    for name, content in expected.items():
        assert (home / name).read_bytes() == content, (home, name)


def failure_snapshot(store, ident, old_context):
    old_home = Path(old_context["home"])
    expected_old = fixture_data(old_home, "old data before failed activation")
    state = store.state()
    failed_home = store.root / "data" / ident
    def prepare_then_fail(context, notify):
        bootstrap._prepare(context, notify)
        d.atomic_json(Path(context["home"]) / "release-e2e/failed-attempt.json", {"fixture": "retain this incomplete snapshot"})
        raise RuntimeError("authored failure after real profile preparation")
    try:
        store.activate(ident, "21.0", progress, prepare_then_fail)
    except RuntimeError as error:
        if "authored failure after real profile preparation" not in str(error):
            raise
    else:
        raise AssertionError("authored activation failure was not reported")
    assert store.state() == state, "failed preparation changed the active selection"
    assert_data(old_home, expected_old)
    assert_data(failed_home, expected_old)
    assert (failed_home / "release-e2e/failed-attempt.json").is_file()
    # A retry must collect changes made in the still-active old data, instead
    # of silently reusing the stale failed snapshot.
    expected_retry = fixture_data(old_home, "old data changed before retry")
    context, lease = store.activate(ident, "21.0", progress, bootstrap._prepare)
    try:
        assert Path(context["home"]) != old_home
        assert_data(Path(context["home"]), expected_retry)
        assert_data(old_home, expected_retry)
        assert not (Path(context["home"]) / "release-e2e/failed-attempt.json").exists()
        retained = [path for path in (store.root / "data").glob("incomplete-*")
                    if (path / "release-e2e/failed-attempt.json").is_file()]
        assert len(retained) == 1, "incomplete activation data was lost or reused"
        assert_data(retained[0], expected_old)
        assert store.state()["current"] == ident and store.state()["previous"] == old_context["installId"]
        return context, lease, expected_retry, str(retained[0])
    except BaseException:
        lease.close()
        raise


def rollback_and_repair(store, context, bundle, old_context=None, expected_old=None):
    home = Path(context["home"])
    newer = fixture_data(home, "new version data")
    new_only = home / "release-e2e/new-session.json"
    d.atomic_json(new_only, {"id": "new-only-dummy-session", "messages": []})
    if old_context is not None:
        old_ident = old_context["installId"]
        assert store.rollback(progress) == old_ident
        restored, lease = store.activate(old_ident, "21.0", progress, bootstrap._prepare)
        try:
            assert restored["home"] == old_context["home"]
            assert_data(Path(restored["home"]), expected_old)
            assert not (Path(restored["home"]) / "release-e2e/new-session.json").exists()
            assert_data(home, newer)
            assert new_only.is_file(), "rollback removed new-version data"
        finally:
            lease.close()
        # Return to the retained newer version for its same-version repair.
        assert store.rollback(progress) == context["installId"]
        resumed, lease = store.activate(context["installId"], "21.0", progress, bootstrap._prepare)
        try:
            assert resumed["home"] == context["home"]
            assert_data(home, newer)
            assert new_only.is_file()
        finally:
            lease.close()
        print("Real signed previous/new selection, independent data and non-merging rollback passed", flush=True)
    install = Path(context["install"])
    media_names = ["app/node_modules/dsh-houdini/runtime/video/ffmpeg/bin/ffmpeg.exe",
                   "app/node_modules/dsh-houdini/runtime/video/ffmpeg/bin/ffprobe.exe"]
    inventory = d.read_json(install / "inventory.json")
    media = [d.checked_path(install, name) for name in media_names]
    assert all(path.is_file() and name in inventory for path, name in zip(media, media_names)), "signed bundle lacks its private media executables"
    expected_media = [inventory[name] for name in media_names]
    media[0].write_bytes(b"authored damaged private ffmpeg fixture")
    media[1].unlink()  # Only this test-created installation's explicit file.
    state = store.state()
    try:
        store.activate(context["installId"], "21.0", progress, bootstrap._prepare)
    except ValueError as error:
        assert "damaged" in str(error) or "missing" in str(error), str(error)
    else:
        raise AssertionError("damaged private media installation was accepted")
    assert store.state() == state
    assert_data(home, newer)
    repair_id = store.stage(bundle, progress)
    assert repair_id != context["installId"], "repair overwrote the serving installation"
    repaired, lease = store.activate(repair_id, "21.0", progress, bootstrap._prepare)
    try:
        assert repaired["version"] == context["version"] and repaired["dshVersion"] == context["dshVersion"]
        assert repaired["install"] != context["install"] and repaired["home"] != context["home"]
        assert_data(Path(repaired["home"]), newer)
        assert (Path(repaired["home"]) / "release-e2e/new-session.json").read_bytes() == new_only.read_bytes()
        assert_data(home, newer)
        restored_media = [d.checked_path(Path(repaired["install"]), name) for name in media_names]
        assert [d.digest(path) for path in restored_media] == expected_media
        assert media[0].read_bytes() == b"authored damaged private ffmpeg fixture" and not media[1].exists()
        versions = []
        for path in restored_media:
            result = subprocess.run([str(path), "-version"], cwd=path.parent, env=d.runtime_env(repaired),
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            assert result.returncode == 0, result.stderr
            versions.append(result.stdout.splitlines()[0])
        if old_context is not None:
            assert_data(Path(old_context["home"]), expected_old)
        return {"repairInstallId": repair_id, "repairHome": repaired["home"], "mediaVersions": versions,
                "rollbackChecked": old_context is not None}
    finally:
        lease.close()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--bundle", type=Path, required=True)
parser.add_argument("--trust", type=Path, required=True)
parser.add_argument("--previous-bundle", type=Path,
                    help="also verify real signed previous activation, failed snapshot retry and rollback")
parser.add_argument("--hython", action="append", type=Path, default=[])
args = parser.parse_args()
trust = d.read_json(args.trust)
# Persistent test output is intentionally outside user data; retain failure evidence.
test_root = Path(tempfile.mkdtemp(prefix="dsh-real-install-中文 空格-"))
print("Isolated test directory:", test_root, flush=True)
environment = isolated_environment(test_root / "environment")
os.environ.clear()
os.environ.update(environment)
store = d.Store(test_root / "managed", trust, allow_candidate=True)
old_context = None
expected_old = None
retained_snapshot = None
if args.previous_bundle is not None:
    previous_manifest = d.load_signed(args.previous_bundle, trust, allow_candidate=True)
    current_manifest = d.load_signed(args.bundle, trust, allow_candidate=True)
    assert previous_manifest["version"] != current_manifest["version"], "previous bundle must be a different version"
    previous_id = store.stage(args.previous_bundle, progress)
    old_context, old_lease = store.activate(previous_id, "21.0", progress, bootstrap._prepare)
    old_lease.close()
ident = store.stage(args.bundle, progress)
if old_context is not None:
    ctx, lease, expected_old, retained_snapshot = failure_snapshot(store, ident, old_context)
else:
    ctx, lease = store.activate(ident, "21.0", progress, bootstrap._prepare)
install = Path(ctx["install"])
env = d.runtime_env(ctx)
env["DSH_HOUDINI_MANAGED_CONTEXT"] = str(Path(ctx["runtimeDir"]) / "context.json")
# A clean PATH verifies the app uses its bundled Node. Windows system tools
# remain available, but neither Git nor a system Node/npm is reachable.
env["PATH"] = str(install / "node") + os.pathsep + str(Path(os.environ["WINDIR"]) / "System32")
assert env["DSH_HOME"] != str(Path.home() / ".dsh")
# Verify browser delivery and scoped tools use the managed installation.
binding_script = """
import {loadProfile, composeEntries} from '@deepseek-ai/dsh-app-boot';
import {interpolate} from '@deepseek-ai/cordis-plugin-loader';
import path from 'node:path';
const profile = loadProfile('dsh','web',path.resolve('node_modules/@deepseek-ai/dsh/package.json'));
if (profile.skippedBundles.length) throw Error(JSON.stringify(profile.skippedBundles));
const entries = composeEntries([...profile.layers.map(x=>x.patches), profile.patches]);
const carriers=entries.filter(x=>!x.disabled && x.name==='dsh-houdini');
const presets=entries.filter(x=>!x.disabled && x.name==='@deepseek-ai/dsh-agent-preset');
if (carriers.length!==1 || presets.length!==1 || presets[0].config.id!=='houdini') throw Error('managed browser/preset composition is incorrect');
const agents=presets[0].config.plugins.filter(x=>!x.disabled && x.name==='dsh-houdini/agent');
if (agents.length!==1 || interpolate({},agents[0].config).bridgeUrl!==process.env.DSH_HOUDINI_BRIDGE_URL) throw Error('managed scoped tool binding is incorrect');
if (entries.some(x=>!x.disabled && x.name==='dsh-houdini/agent')) throw Error('Houdini tools leaked into the root scope');
"""
subprocess.run([str(install / "node/node.exe"), "--input-type=module", "-e", binding_script],
               cwd=install / "app", env=env, capture_output=True, check=True, timeout=60)
cwd = test_root / "workspace"
cwd.mkdir()
log = Path(ctx["runtimeDir"]) / "frontend.log"
base = f"http://127.0.0.1:{ctx['frontendPort']}"
process = None
composition_file = Path(ctx["runtimeDir"]) / "composition.json"
inspector = Path(ctx["runtimeDir"]) / "inspect.mjs"
inspector.write_text("""
import fs from 'node:fs';
export const inject=['loader','tools','agentPresets','clientModules'];
export function apply(ctx) {
  ctx.effect(() => {
    let disposed=false;
    queueMicrotask(async () => {
      try {
        await ctx.loader.await();
        const roster=await ctx.agentPresets.remoteExportList();
        const lease=await ctx.agentPresets.acquireScope('houdini');
        try {
          const tools=ctx.tools.schemas(lease.key).map(tool=>tool.name);
          const graph=ctx.clientModules.graph();
          if(!disposed)fs.writeFileSync(process.env.DSH_MANAGED_COMPOSITION_OUT,JSON.stringify({roster,tools,graph}));
        } finally {await lease[Symbol.asyncDispose]();}
      } catch(error) {
        if(!disposed)fs.writeFileSync(process.env.DSH_MANAGED_COMPOSITION_OUT,JSON.stringify({error:String(error.stack||error)}));
      }
    });
    return () => {disposed=true;};
  });
}
""", encoding="utf-8")
overlay = Path(ctx["runtimeDir"]) / "inspect.patch.yml"
overlay.write_text('- insert:\n    - id: managed-composition-inspector\n      name: ' + inspector.as_uri() + '\n', encoding="utf-8")
env["DSH_MANAGED_COMPOSITION_OUT"] = str(composition_file)
try:
    with log.open("wb") as output:
        process = managed.spawn_frontend([str(install / "node/node.exe"), str(install / "app/node_modules/@deepseek-ai/dsh/lib/bin.js"), "web", "--patch", str(overlay), "--port", str(ctx["frontendPort"]), "--no-open"],
                                   node=str(install / "node/node.exe"),
                                   cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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
                if not composition_file.exists():
                    time.sleep(0.3)
                    continue
                facts=json.loads(composition_file.read_text(encoding='utf-8'))
                assert 'error' not in facts, facts
                presets=facts['roster']['presets']
                assert len(presets)==1 and presets[0]['id']=='houdini' and presets[0]['isDefault'], facts
                expected={'houdini_inspect','houdini_exec','houdini_ui_list','houdini_ui_screenshot','houdini_request','houdini_resource','houdini_capabilities',
                    'houdini_job_submit','houdini_job_status','houdini_job_cancel'}
                assert {name for name in facts['tools'] if name.startswith('houdini_')} == expected, facts
                graph_rows=facts['graph'] if isinstance(facts['graph'],list) else facts['graph']['entries']
                assert sum(row['id']=='dsh-houdini' for row in graph_rows)==1, facts
                break
            except AssertionError:
                raise
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
        assert not any((Path(ctx["home"]) / ".agent-presets" / name).exists()
                       for name in ("houdini", "houdini-dev", "houdini-product"))
        assert not (install / "app/node_modules/dsh-houdini/node_modules").exists()
        print("Real portable Node + exact DSH + isolated profile + plugin import + 401/200 authenticated RPC passed", flush=True)
        for hython in args.hython:
            prefs = tempfile.mkdtemp(prefix="dsh-installed-houdini-")
            hython = hython.resolve(strict=True)
            child_env = isolated_environment(prefs, executable=hython, base=env)
            # Restore only this fixture's explicitly created managed identity.
            child_env.update(DSH_HOME=ctx['home'], DSH_HOUDINI_MANAGED_CONTEXT=env['DSH_HOUDINI_MANAGED_CONTEXT'])
            traceback_file = test_root / (hython.parent.parent.name + "-managed-traceback.txt")
            child_script = """import runpy,sys,traceback
from pathlib import Path
try:
    runpy.run_path(sys.argv[1],run_name='__main__')
except BaseException:
    Path(sys.argv[2]).write_text(traceback.format_exc(),encoding='utf-8')
    raise
"""
            completed = subprocess.run([str(hython), "-u", "-c", child_script,
                                       str(ROOT / "tools/tests/dsh-managed-houdini.test.py"), str(traceback_file)],
                           cwd=launch_directory(hython), env=child_env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=120,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            (test_root / (hython.parent.parent.name + "-managed-output.log")).write_text(
                completed.stdout + "\n--- stderr ---\n" + completed.stderr, encoding="utf-8")
            if completed.returncode:
                if traceback_file.exists():
                    print(traceback_file.read_text(encoding="utf-8"), flush=True)
                print(completed.stdout[-4000:] + "\n" + completed.stderr[-4000:], flush=True)
                raise subprocess.CalledProcessError(completed.returncode, completed.args)
            print(completed.stdout.strip(), flush=True)
finally:
    managed.stop_owned()
    if process is not None:
        process.wait(timeout=20)
    lease.close()
assert process.returncode is not None
print("Owned frontend terminated; no external process or user HIP was touched", flush=True)
recovery = rollback_and_repair(store, ctx, args.bundle, old_context, expected_old)
d.atomic_json(test_root / "lifecycle-evidence.json", {"currentVersion": ctx["version"],
    "previousVersion": old_context["version"] if old_context else None,
    "incompleteSnapshot": retained_snapshot, "recovery": recovery, "state": store.state()})
print("Real signed same-version repair restored private FFmpeg/ffprobe and preserved independent data", flush=True)
