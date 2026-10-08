"""One public, paid development run; keep all evidence outside the source tree."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid


import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--plugin',required=True,type=Path)
parser.add_argument('--run',required=True,type=Path)
parser.add_argument('--node',required=True,type=Path)
parser.add_argument('--dsh',required=True,type=Path)
parser.add_argument('--houdini',required=True,type=Path)
parser.add_argument('--credentials',required=True,type=Path)
parser.add_argument('--settings',required=True,type=Path,help='Verified user settings; only the selected provider/model is copied')
parser.add_argument('--model',required=True)
parser.add_argument('--provider',default='deepseek-official',help='Explicit provider route copied from the verified settings')
parser.add_argument('--show-gui',action='store_true',help='Show only the owned GUI worker for an authorized visible-surface trial')
parser.add_argument('--condition',required=True)
parser.add_argument('--seed-hip',type=Path,help='Explicit developer-owned input; never a live/user HIP')
parser.add_argument('--followup',type=Path,action='append',default=[],help='Same-author next phase, sent only after the preceding phase becomes idle')
parser.add_argument('--goal-rounds',type=int,default=0,help='Use native DSH Goal for the first phase with this round cap')
parser.add_argument('--smoke',action='store_true',help='No model calls: verify session/model route, seed and real GUI preview')
parser.add_argument('--scripted-smoke',action='store_true',help='With --smoke, intercept every model stream locally to exercise native Goal and followups')
parser.add_argument('--smoke-delivery',action='store_true',help='With scripted smoke, exercise mounted capture/read_image/present/node-entry carriers without a paid model')
parser.add_argument('--observe-model-images',action='store_true',help='Read-only evidence of real DSH LOOP image attachments and provider completion')
parser.add_argument('--probe-frontend',action='store_true',help='Inspect the selected real session and its delivery in the owned Houdini QtWebEngine before stop')
parser.add_argument('--max-seconds',type=int,default=600)
parser.add_argument('--max-output-tokens',type=int,default=32000,help='Per-request DeepSeek override; other providers retain their selected profile defaults')
parser.add_argument('--memory-mb',type=int,default=8192,help='Owned Houdini process-tree memory limit in MiB')
parser.add_argument('--require-image-input',action='store_true',help='Refuse a route whose actual pinned Host model resolver does not report image input')
parser.add_argument('--allow-paid',action='store_true')
args=parser.parse_args()
if not args.allow_paid and not args.smoke:parser.error('explicit --allow-paid required after user authorization')
if args.scripted_smoke and not args.smoke:parser.error('scripted-smoke requires smoke')
if args.smoke_delivery and not args.scripted_smoke:parser.error('smoke-delivery requires scripted-smoke')
if not 60<=args.max_seconds<=14400:parser.error('max-seconds must be 60..14400 for all model phases combined')
if args.goal_rounds<0:parser.error('goal-rounds must be nonnegative')
if not 1024<=args.max_output_tokens<=262144:parser.error('max-output-tokens must be 1024..262144 per request')
if not 128<=args.memory_mb<=65536:parser.error('memory-mb must be 128..65536')
ROOT=args.plugin.resolve(strict=True)
RUN=args.run.resolve(strict=True)
if RUN.is_relative_to(ROOT) or ROOT.is_relative_to(RUN):parser.error('frozen plugin and run must be separate trees')
TASK=RUN/'task';RUNTIME=RUN/'runtime';HOME=RUNTIME/'home';REGISTRY=RUNTIME/'registry';RAW=RUN/'raw';WORKER=RUN/'worker'
NODE=args.node.resolve(strict=True);DSH=args.dsh.resolve(strict=True);HOUDINI=args.houdini.resolve(strict=True)
HYTHON=HOUDINI.with_name('hython.exe');CREDENTIALS=args.credentials.resolve(strict=True)
SETTINGS=args.settings.resolve(strict=True)
MODEL=args.model;PROVIDER=args.provider;MAX_SECONDS=args.max_seconds
DRIVER_ROOT=Path(__file__).resolve().parents[1]

sys.path.insert(0, str(DRIVER_ROOT / "tools"))
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
from houdini_test_environment import isolated_environment, launch_directory, reexec_unpacked_test_cli
from dsh_web_auth import DshWebSession
from dsh_managed_runtime import spawn_frontend, stop_owned


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def tool_digest() -> str:
    rows=[]
    for base,pattern in [('lib','*.js'),('houdini/python3.11libs','*.py')]:
        for path in sorted((ROOT/base).rglob(pattern)):
            rows.append([path.relative_to(ROOT).as_posix(),digest(path)])
    return sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(*args: str, cwd: Path = ROOT, env: dict[str, str] | None = None,
                timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, env=env, check=True, timeout=timeout,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=subprocess.CREATE_NO_WINDOW)


def main() -> None:
    reexec_unpacked_test_cli()
    if RUNTIME.exists() or WORKER.exists() or (RUN / "lock.json").exists():
        raise RuntimeError("This run already started; never overwrite its input or evidence")
    if not TASK.is_dir() or not (TASK / "brief.md").is_file() or not (TASK / "task.json").is_file():
        raise RuntimeError("Missing prepared public task")
    if not all(p.is_file() for p in (NODE, DSH, HOUDINI, HYTHON, CREDENTIALS)):
        raise RuntimeError("Missing pinned runtime or existing credential store")
    head = "frozen-package:"+digest(ROOT/"package.json")
    RUNTIME.mkdir(exist_ok=False)
    RAW.mkdir(exist_ok=False)
    host_env = isolated_environment(RUNTIME / "host-env")
    host_env.update(DSH_HOME=str(HOME), DSH_HOUDINI_EXECUTOR_REGISTRY=str(REGISTRY),
                    DSH_PERMISSION_MODE="workspace-write")
    if args.scripted_smoke:
        host_env['DSH_MODELING_TRIAL_SMOKE_OUT']=str(RAW/'scripted-requests.json')
    if args.smoke_delivery:
        smoke_workspace=WORKER/'workspace'
        host_env['DSH_MODELING_TRIAL_DELIVERY_SMOKE']=json.dumps({'hip':str(smoke_workspace/'final.hip'),
            'image':str(smoke_workspace/'native-ui-smoke.png'),'source':str(smoke_workspace/'task.json')})
    if args.observe_model_images or args.require_image_input:
        host_env['DSH_MODELING_TRIAL_OBSERVER_OUT']=str(RAW/'model-image-consumption.jsonl')
        host_env['DSH_MODELING_TRIAL_MODEL_INFO_OUT']=str(RAW/'model-resolved-info.json')
        host_env['DSH_MODELING_TRIAL_PROVIDER']=PROVIDER
        host_env['DSH_MODELING_TRIAL_MODEL']=MODEL
    run_command(str(NODE), str(DRIVER_ROOT / "tools/tests/prepare-shared-host-fixture.mjs"),
                str(DSH), str(HOME), str(ROOT), env=host_env)
    selected=run_command(str(NODE),str(DRIVER_ROOT/'tools/prepare-model-settings.mjs'),
                         str(SETTINGS),str(HOME),PROVIDER,MODEL,str(DSH),str(CREDENTIALS),env=host_env)
    model_config=json.loads(selected.stdout.strip())
    overlay = RUNTIME / "model-host.patch.yml"
    overlay.write_text((ROOT / "shared-host.cordis.yml").read_text(encoding="utf-8")
                       + "\n- id: credentials\n  config:\n    path: "
                       + (HOME/'.credentials.yaml').as_posix() + "\n    watch: false\n"
                       + (HOME/'selected-model.patch.yml').read_text(encoding='utf-8')
                       + ("- id: llm-deepseek\n  config:\n    reasoningEffort: high\n"
                          + "    maxTokens: " + str(args.max_output_tokens) + "\n"
                          if PROVIDER=='deepseek-official' else ''), encoding="utf-8")
    if args.scripted_smoke:
        scripted_plugin=RUNTIME/'scripted-plugin'
        scripted_plugin.mkdir()
        write_json(scripted_plugin/'package.json',{'name':'dsh-modeling-trial-scripted','type':'module','main':'index.mjs'})
        shutil.copy2(DRIVER_ROOT/'tools/tests/modeling-trial-scripted.mjs',scripted_plugin/'index.mjs')
        with overlay.open('a',encoding='utf-8') as stream:
            stream.write('- insert:\n    - id: modeling-trial-scripted-smoke\n      name: '
                +(scripted_plugin/'index.mjs').as_uri()+'\n')
    if args.observe_model_images or args.require_image_input:
        observer_plugin=RUNTIME/'observer-plugin'
        observer_plugin.mkdir()
        write_json(observer_plugin/'package.json',{'name':'dsh-modeling-trial-observer','type':'module','main':'index.mjs'})
        shutil.copy2(DRIVER_ROOT/'tools/tests/modeling-trial-observer.mjs',observer_plugin/'index.mjs')
        with overlay.open('a',encoding='utf-8') as stream:
            stream.write('- insert:\n    - id: modeling-trial-image-observer\n      name: '
                +(observer_plugin/'index.mjs').as_uri()+'\n')
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    host_log = RAW / "host.log"
    supervisor_log = RAW / "supervisor.log"
    host_stream = host_log.open("wb")
    supervisor_stream = supervisor_log.open("wb")
    host = None
    supervisor = None
    bound = False
    result = {"schema": 1, "case": args.condition, "startedAt": utc(),
              "startedAtBeijing":datetime.now(timezone(timedelta(hours=8))).isoformat(),
              "sourceCommit": head, "provider": PROVIDER, "model": MODEL,
              "result": "not_started", "sessionId": None}
    try:
        host = spawn_frontend([str(NODE), str(DSH), "web", "--patch", str(overlay),
                               "--port", str(port), "--no-open"], node=str(NODE),
                              cwd=TASK, env=host_env, stdout=host_stream,
                              stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        supervisor = subprocess.Popen([sys.executable, str(DRIVER_ROOT / "tools/isolated-worker.py"),
                                       "--executable", str(HOUDINI), "--directory", str(WORKER),
                                       "--plugin",str(ROOT),
                                       "--registry", str(REGISTRY), "--gui", "--hip-name", "final.hip",
                                       "--memory-mb", str(args.memory_mb), "--threads", "4", "--startup-timeout", "120"]
                                      + (["--show"] if args.show_gui else [])
                                      + (["--seed-hip",str(args.seed_hip.resolve(strict=True))] if args.seed_hip else []),
                                      cwd=ROOT, env=isolated_environment(RUNTIME / "supervisor-env"),
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=supervisor_stream, text=True,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
        ready_lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=lambda: ready_lines.put(supervisor.stdout.readline()),
                         daemon=True).start()
        line = ready_lines.get(timeout=130)
        if not line:
            raise RuntimeError("Worker did not publish readiness")
        ready = json.loads(line)
        if not ready.get("ok"):
            raise RuntimeError("Worker readiness failed: " + str(ready.get("error", "unknown")))
        record = ready["record"]
        hip = Path(record["hip_path"])
        workspace = hip.parent
        for entry in TASK.iterdir():
            if entry.is_dir(): shutil.copytree(entry,workspace/entry.name)
            else: shutil.copy2(entry,workspace/entry.name)
        initial_hash = digest(hip)
        base = f"http://127.0.0.1:{port}"
        auth = DshWebSession(base, str(host_log), str(RUNTIME / "runtime.json"))

        def rpc(method: str, args: object, timeout: int = 20):
            body = {"type": "client-request", "rpcId": uuid.uuid4().hex,
                    "method": method, "payload": {"args": args}}
            request = urllib.request.Request(base + "/api/" + method,
                data=json.dumps(body).encode(), headers={"Content-Type": "application/json"},
                method="POST")
            with auth.open(request, timeout=timeout) as response:
                response_data = json.load(response)
            payload = response_data.get("result", {})
            if not payload.get("ok"):
                raise RuntimeError("RPC " + method + " failed: " + str(payload.get("error"))[:600])
            return payload.get("value")

        for _ in range(120):
            if host.poll() is not None:
                raise RuntimeError("Isolated DSH Host exited during startup")
            try:
                auth.authorize(1)
                rpc("session/list", {"_request": {}}, 3)
                break
            except Exception:
                time.sleep(.25)
        else:
            raise RuntimeError("Isolated DSH Host did not become ready")

        if args.require_image_input:
            resolved_file=RAW/'model-resolved-info.json'
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                live_model=json.loads(resolved_file.read_text(encoding='utf-8')) if resolved_file.exists() else {}
                if live_model.get('ok'):break
                time.sleep(.1)
            if not live_model.get('ok') or 'image' not in live_model['model'].get('inputModalities',[]):
                raise RuntimeError('Actual pinned Host model resolver does not report image input; no model request sent')
            model_config['actualResolvedModel']=live_model['model']

        # Registration is published by a startup thread. The first queue-backed
        # observation can still precede GUI readiness; wait only on this owned,
        # read-only health endpoint before claiming the executor.
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            try:
                request=urllib.request.Request(record['bridge_url']+'/health',
                    headers={'X-DSH-Houdini-Executor':record['executor_id']})
                with urllib.request.urlopen(request,timeout=2) as response:health=json.load(response)
                if health.get('ok') and health.get('runtimeId')==record['runtime_id']:break
            except (OSError,ValueError):pass
            if supervisor.poll() is not None:raise RuntimeError('Owned worker exited before its health endpoint became ready')
            time.sleep(.1)
        else:raise RuntimeError('Owned worker health did not become ready before session binding')

        session_id = str(uuid.uuid4())
        result["sessionId"] = session_id
        registered=rpc('workspace/create',{'request':{'path':str(workspace)}})
        workspace_id=registered['workspace']['workspaceId']
        result['workspaceId']=workspace_id
        rpc("session/create", {"request": {"sessionId": session_id,
                                            "workspaceId": workspace_id, "agentPreset": "houdini"}})
        rpc("houdiniTargets/select", {"input": {"sessionId": session_id,
            "executorId": record["executor_id"], "registrationId": record["registration_id"],
            "expectedHip": str(hip)}})
        bound = True
        rpc("session/selectModel", {"request": {"sessionId": session_id,
                                                "provider": PROVIDER, "model": MODEL}})
        def owned_bridge_exec(code,call):
            headers={'Content-Type':'application/json','X-DSH-Houdini-Executor':record['executor_id']}
            request=urllib.request.Request(record['bridge_url']+'/requests/prepare',
                data=json.dumps({'owner_session':session_id}).encode(),headers=headers)
            with urllib.request.urlopen(request,timeout=20) as response:ticket=json.load(response)
            request=urllib.request.Request(record['bridge_url']+'/exec',data=json.dumps({
                'owner_session':session_id,'owner_call':call,'request_ref':ticket['requestRef'],
                'expected_contract':{'version':ticket['executionContractVersion'],'hash':ticket['verbCatalog']['hash']},
                'code':code}).encode(),headers=headers)
            with urllib.request.urlopen(request,timeout=30) as response:return json.load(response)
        setup_module=str(DRIVER_ROOT/'tools/tests/modeling-trial-gui-setup.py')
        setup=owned_bridge_exec('import runpy\n__result__=runpy.run_path('+repr(setup_module)+
            ')["dismiss_owned_start_here"]()','trial-owned-gui-setup')
        if not setup.get('ok') or setup['result']['pid']!=record['pid']:
            raise RuntimeError('Owned GUI welcome setup identity failed before any model request')
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            observation=owned_bridge_exec('import runpy\n__result__=runpy.run_path('+repr(setup_module)+
                ')["observe_owned_start_here"]()','trial-owned-gui-setup-readback')
            if observation.get('ok') and observation['result']['pid']==record['pid'] and observation['result']['visibleCount']==0:break
            time.sleep(.1)
        else:raise RuntimeError('Owned Start Here window did not close before task observation')
        write_json(RAW/'owned-gui-setup.json',{'request':setup,'readback':observation})
        prompt = ("请读取当前工作目录中的 brief.md 和 task.json，完成这项公开开发任务。"
                  + ("你操作的是载入指定任务起始工程的隔离 Houdini 场景。" if args.seed_hip else "你操作的是新建的隔离 Houdini 场景。")
                  + "最终文件已预留为 " + str(hip)
                  + "；初始空场景文件不算交付。最后一次场景修改后，请调用 "
                  "scene_save(expected_path=" + repr(str(hip))
                  + ") 显式保存，并验证最终输出与主要控制。"
                  "最后说明已完成、失败和未验证的要求，给出最终 HIP 的绝对路径。")
        lock = {"schema": 1, "case": args.condition, "condition": args.condition,
                "createdAt": utc(), "sourceCommit": head,
                "clientTimeZone":"Asia/Shanghai",
                "dshVersion": json.loads((DSH.parent.parent/'package.json').read_text(encoding='utf-8'))['version'],
                "houdiniVersion": record['houdini_version'], "provider": PROVIDER, "model": MODEL,
                "reasoningEffort": "high" if PROVIDER=='deepseek-official' else 'selected_profile_default', "maxSeconds": MAX_SECONDS,
                "maxOutputTokens":args.max_output_tokens if PROVIDER=='deepseek-official' else None,
                "showOwnedGui":args.show_gui,"toolBuildSha256":tool_digest(),
                "modelConfiguration":model_config,"isolatedSettingsSha256":digest(HOME/'selected-model.patch.yml'),
                "workerThreads": 4, "workerMemoryMb": args.memory_mb,
                "briefSha256": digest(TASK / "brief.md"),
                "taskSha256": digest(TASK / "task.json"),
                "seedHipSha256":digest(args.seed_hip.resolve()) if args.seed_hip else None,
                "goalRounds":args.goal_rounds,"smoke":args.smoke,
                "followups":[{"sha256":digest(p.resolve(strict=True)),"text":p.read_text(encoding='utf-8')} for p in args.followup],
                "workspace":str(workspace),"hipDirectory":str(hip.parent),
                "promptSha256": sha256(prompt.encode()).hexdigest(),
                "prompt": prompt, "initialHipSha256": initial_hash,
                "hipPath": str(hip), "executorId": record["executor_id"],
                "runtimeId": record["runtime_id"],
                "hostBuildSha256": digest(ROOT / "lib/executor-host.js"),
                "workflowSha256": digest(ROOT / "skills/houdini-sop-workflow/SKILL.md"),
                "bridgeSha256": digest(ROOT / "houdini/python3.11libs/dsh_bridge.py")}
        write_json(RUN / "lock.json", lock)
        print("LOCKED public task, model route, source and runtime; session=" + session_id, flush=True)
        def admit(text, *, goal=False):
            if goal:
                return rpc('goals/create',{'agentId':session_id,'request':{
                    'objective':text,'maxGoalRounds':args.goal_rounds}},30)
            return rpc("session/prompt", {"request": {"sessionId": session_id,
                "requestId": str(uuid.uuid4()), "mode": "queue", "clientTimeZone":"Asia/Shanghai",
                "content": [{"type": "text", "text": text}]}}, 30)

        if args.smoke:
            def bridge_rpc(route,body=None):
                request=urllib.request.Request(record['bridge_url']+route,
                    data=None if body is None else json.dumps(body).encode(),
                    headers={'Content-Type':'application/json','X-DSH-Houdini-Executor':record['executor_id']})
                with urllib.request.urlopen(request,timeout=90) as response:return json.load(response)
            ticket=bridge_rpc('/requests/prepare',{'owner_session':session_id})
            smoke_code=("before=scene_info()\nbefore_nodes=[{'path':n.path(),'owner':n.userData('dsh_houdini_task_owner')} for n in hou.node('/obj').children()]\n"
                "g=tab_create('/obj','geo','evaluation_smoke')\n"
                "b=tab_create(g,'box','shape')\npreview=render_view(b,width=320,height=240)\n"
                "saved=scene_save(expected_path="+repr(str(hip))+")\n"
                "__result__={'before':before,'before_nodes':before_nodes,'preview':preview,'saved':saved}")
            smoke=bridge_rpc('/exec',{'owner_session':session_id,'owner_call':'evaluation-smoke',
                'request_ref':ticket['requestRef'],'expected_contract':{
                'version':ticket['executionContractVersion'],'hash':ticket['verbCatalog']['hash']},'code':smoke_code})
            write_json(RAW/'smoke.json',smoke)
            if not smoke.get('ok'):raise RuntimeError('isolated smoke failed; see raw/smoke.json')
            result['smoke']={'ok':True,'executionContractVersion':ticket['executionContractVersion'],
                'preview':smoke['result']['preview']['output'],'modelRequestSent':False}
        if not args.smoke or args.scripted_smoke:
            admit(prompt,goal=args.goal_rounds>0)
        result["result"] = "running"
        started = time.monotonic()
        saw_running = False
        last_report = -30
        phase_started = started
        phase_index = 0
        phase_records = []
        while time.monotonic() - started < MAX_SECONDS:
            if host.poll() is not None:
                result["result"] = "host_exit"
                break
            if supervisor.poll() is not None:
                result["result"] = "worker_exit"
                break
            listing = rpc("session/list", {"_request": {}}, 10)
            item = next((row for row in listing.get("items", [])
                         if row.get("sessionId") == session_id), None)
            if item is None:
                result["result"] = "session_missing"
                break
            elapsed = int(time.monotonic() - started)
            running = item.get("running")
            saw_running |= running is True
            if elapsed - last_report >= 30:
                print(f"elapsed={elapsed}s running={running} worker_alive=True", flush=True)
                last_report = elapsed
            if running is False and (args.smoke or saw_running or time.monotonic()-phase_started > 30):
                time.sleep(3)
                settled_listing=rpc('session/list',{'_request':{}},10)
                item=next(row for row in settled_listing['items'] if row['sessionId']==session_id)
                if item.get('running') is True:continue
                phase_dir=RUN/'review'
                phase_dir.mkdir(exist_ok=True)
                phase_hip=phase_dir/f'phase-{phase_index+1}.hip'
                shutil.copy2(hip,phase_hip)
                phase_records.append({'phase':phase_index+1,'elapsedSeconds':round(time.monotonic()-phase_started,2),
                    'hipPath':str(phase_hip),'hipSha256':digest(phase_hip),'sessionItem':item})
                write_json(RUN/'phases.json',phase_records)
                if phase_index<len(args.followup) and (not args.smoke or args.scripted_smoke):
                    admit(args.followup[phase_index].read_text(encoding='utf-8'))
                    phase_index+=1
                    phase_started=time.monotonic()
                    saw_running=False
                    continue
                result["result"] = "idle_after_prompt"
                break
            time.sleep(5)
        else:
            result["result"] = "wall_time_limit"
            try:
                rpc("session/cancel", {"request": {"sessionId": session_id}}, 15)
                result["cancelRequested"] = True
            except Exception as exc:
                result["cancelError"] = type(exc).__name__ + ": " + str(exc)[:300]
            time.sleep(10)
        result["elapsedSeconds"] = int(time.monotonic() - started)
        if result['result']=='worker_exit':
            try:
                rpc('session/cancel',{'request':{'sessionId':session_id}},15)
                result['cancelRequested']=True
                result['cancelReason']='owned Houdini worker exited; no continuation against a dead runtime'
            except Exception as exc:
                result['cancelError']=type(exc).__name__
        result['phases']=phase_records
        result['endedAt']=utc()
        if args.goal_rounds:
            result['goalState']=rpc('goals/get',{'agentId':session_id})
        result["finalSessionItem"] = item if "item" in locals() else None
        if args.probe_frontend and result['result']=='idle_after_prompt':
            frontend_config=RAW/'frontend-probe-config.json'
            frontend_output=RAW/'frontend-probe-result.json'
            session_file=next((HOME/'sessions').glob('*/'+session_id+'/session.v4.jsonl.zstd'))
            run_command(str(NODE),str(DRIVER_ROOT/'tools/tests/modeling-trial-ui-artifacts.mjs'),
                str(session_file),str(RAW/'frontend-artifacts.json'),str(workspace),session_id)
            write_json(frontend_config,{'base':base,'authenticatedUrl':auth.launch_url(),
                'sessionId':session_id,'output':str(frontend_output),
                'modelRunKind':'scripted-no-paid-carrier' if args.smoke else 'paid-agent-task'})
            request=urllib.request.Request(record['bridge_url']+'/requests/prepare',
                data=json.dumps({'owner_session':session_id}).encode(),
                headers={'Content-Type':'application/json','X-DSH-Houdini-Executor':record['executor_id']})
            with urllib.request.urlopen(request,timeout=30) as response:ticket=json.load(response)
            code=("import runpy\n__result__=runpy.run_path("+repr(str(DRIVER_ROOT/'tools/tests/modeling-trial-frontend-probe.py'))
                +")[\"start\"]("+repr(str(frontend_config))+")")
            request=urllib.request.Request(record['bridge_url']+'/exec',
                data=json.dumps({'owner_session':session_id,'owner_call':'trial-frontend-observation',
                  'request_ref':ticket['requestRef'],'expected_contract':{'version':ticket['executionContractVersion'],
                  'hash':ticket['verbCatalog']['hash']},'code':code}).encode(),
                headers={'Content-Type':'application/json','X-DSH-Houdini-Executor':record['executor_id']})
            with urllib.request.urlopen(request,timeout=45) as response:admission=json.load(response)
            write_json(RAW/'frontend-probe-admission.json',admission)
            deadline=time.monotonic()+120
            while admission.get('ok') and not frontend_output.exists() and time.monotonic()<deadline:
                if supervisor.poll() is not None:break
                time.sleep(.25)
            result['frontendProbe']=json.loads(frontend_output.read_text(encoding='utf-8')) if frontend_output.exists() else {'ok':False,'error':'Frontend probe did not finish; see admission'}
        result["hipSha256BeforeStop"] = digest(hip) if hip.is_file() else None
        result["hipChangedFromInitial"] = (result["hipSha256BeforeStop"] is not None
                                            and result["hipSha256BeforeStop"] != initial_hash)
        print("MODEL_PHASE=" + result["result"], flush=True)
        if supervisor.poll() is None:
            supervisor.stdin.write("STOP\n")
            supervisor.stdin.flush()
            try:
                result["supervisorExitCode"] = supervisor.wait(timeout=30)
            except subprocess.TimeoutExpired:
                result["supervisorExitCode"] = None
                result["stopTimeout"] = True
        else:
            result["supervisorExitCode"] = supervisor.returncode
        stop_state = WORKER / "stop-state.json"
        result["stopState"] = json.loads(stop_state.read_text(encoding="utf-8")) if stop_state.exists() else None
        result["hipSha256AfterStop"] = digest(hip) if hip.is_file() else None
        if result["supervisorExitCode"] == 0 and result["hipChangedFromInitial"]:
            review = RUN / "review"
            review.mkdir(exist_ok=True)
            candidate = review / "final-candidate.hip"
            shutil.copy2(hip, candidate)
            result["candidateCopy"] = str(candidate)
            result["candidateSha256"] = digest(candidate)
        write_json(RUN / "run-result.json", result)
        print("RESULT_FILE=" + str(RUN / "run-result.json"), flush=True)
    except Exception as exc:
        result["result"] = "driver_error"
        result["driverError"] = type(exc).__name__ + ": " + str(exc)[:1000]
        write_json(RUN / "run-result.json", result)
        raise
    finally:
        if supervisor is not None and supervisor.poll() is None:
            try:
                supervisor.stdin.write("STOP\n")
                supervisor.stdin.flush()
                supervisor.wait(timeout=30)
            except Exception:
                result["workerStopUncertain"] = True
                try: supervisor.stdin.close(); supervisor.wait(timeout=20)
                except Exception: pass
                write_json(RUN / "run-result.json", result)
        stop_owned()
        host_stream.close()
        supervisor_stream.close()


if __name__ == "__main__":
    main()
