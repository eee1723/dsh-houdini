"""Two disposable H21/H22 Bridges: registry, target routing and writer isolation.

Run with ordinary Python --hython <H21> --hython <H22>. No installed DSH, user
credentials, user HIP, GUI, global services or production registry are touched.
"""
from pathlib import Path
import argparse
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
sys.path.insert(0, str(ROOT / 'tools'))
from dsh_executor_registry import ExecutorRegistration, read_candidates
from houdini_test_environment import isolated_environment


def worker(args):
    import hou
    import dsh_bridge as bridge
    from dsh_managed_runtime import executor_identity
    from dsh_shared_executor import prepare_registration, publish_registration
    hou.hipFile.setName(args.hip)  # isolated fixture only, no file loaded or saved
    server = bridge.start(0)
    bridge._pump_active = True
    version = hou.applicationVersionString()
    facts = prepare_registration()
    registration = []
    def publish():
        record = publish_registration(args.registry, facts)
        from dsh_executor_registry import active_registration
        item = active_registration()
        registration.append(item)
        record = item.publish(server.server_port, bridge._RUNTIME_ID)
        print('READY=' + json.dumps(record), flush=True)
    published = threading.Thread(target=publish)
    published.start(); published.join()
    done = threading.Event()
    commands=queue.Queue()
    def input_loop():
        for line in sys.stdin:
            if line.strip()=='repair': commands.put('repair')
            else: done.set();return
        done.set()
    threading.Thread(target=input_loop, daemon=True).start()
    try:
        while not done.wait(.01):
            if not commands.empty():
                commands.get_nowait()
                from dsh_shared_executor import repair_registration
                root, facts=repair_registration()
                update=threading.Thread(target=lambda:publish_registration(root,facts))
                update.start();update.join()
                bridge._pump_active=True
            bridge._pump()
    finally:
        bridge.stop()
        cleanup = threading.Thread(target=lambda: [r.close() for r in registration])
        cleanup.start(); cleanup.join()


def call(record, path, body=None, expected=None):
    request = urllib.request.Request(record['bridge_url'] + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'X-DSH-Houdini-Executor': expected or record['executor_id']})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def driver(args):
    children=[]
    with tempfile.TemporaryDirectory(prefix='dsh-multi-test-') as temporary:
        base=Path(temporary)
        registry=base/'registry'
        try:
            records=[]
            for index, binary in enumerate(args.hython):
                binary=Path(binary).resolve(strict=True)
                hip=base/f'project-{index}.hip'
                # File identity fixture only; never loaded into Houdini.
                hip.write_bytes(b'cooperative writer fixture')
                child=subprocess.Popen([str(binary),str(Path(__file__).resolve()),'--worker',
                    '--registry',str(registry),'--hip',str(hip),'--task',f'task-{index}'],
                    cwd=binary.parent,env=isolated_environment(base/f'env-{index}',executable=binary),
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                    encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                children.append(child)
                messages=queue.Queue()
                def reader(process=child, inbox=messages):
                    for line in process.stdout:
                        inbox.put(line)
                    inbox.put(None)
                threading.Thread(target=reader,daemon=True).start()
                deadline=time.monotonic()+45
                diagnostic=[]
                while True:
                    line=messages.get(timeout=max(.01,deadline-time.monotonic()))
                    if line is None: raise RuntimeError('worker failed: '+''.join(diagnostic)[-3000:])
                    if line.startswith('READY='):
                        records.append(json.loads(line[6:]));break
                    diagnostic.append(line)
            assert len(records)==2
            a,b=records
            assert a['executor_id']!=b['executor_id'] and a['bridge_url']!=b['bridge_url']
            assert a['hip_path']!=b['hip_path'] and a['task_id'] is None and b['task_id'] is None
            for i,record in enumerate(records):
                task='task-'+str(i)
                status,blocked=call(record,'/exec',{'code':'__result__=1','owner_session':task})
                assert status==200 and not blocked['ok'] and 'reservation mismatch' in blocked['error'],blocked
                assert call(record,'/executor/claim',{'task_id':task,'registration_id':'f'*32,
                    'expected_hip':record['hip_path']})[0]!=200
                status,claimed=call(record,'/executor/claim',{'task_id':task,'registration_id':record['registration_id'],
                    'expected_hip':record['hip_path']})
                assert status==200 and claimed['ok'],claimed
                record.update(claimed['result'])
                status,created=call(record,'/exec',{'code':"g=tab_create('/obj','geo',name='owned_fixture')\n__result__=g.path()",'owner_session':task})
                assert status==200 and created['ok'],created
                status,denied=call(record,'/exec',{'code':"delete_node('/obj/owned_fixture')",'owner_session':'wrong-task'})
                assert status==200 and not denied['ok'] and 'reservation mismatch' in denied['error'],denied
                output=base/f'forbidden-save-{i}.hip'
                status,denied=call(record,'/exec',{'code':f'scene_save_as({str(output)!r},{record["hip_path"]!r},"isolated test target")','owner_session':task})
                assert status==200 and not denied['ok'] and 'new writer reservation' in denied['error'],denied
                assert not output.exists()
                assert call(record,'/executor/claim',{'task_id':'another','registration_id':record['registration_id'],
                    'expected_hip':record['hip_path']})[0]!=200
            discovered=read_candidates(registry,installation=ROOT)
            assert {r['executor_id'] for r in discovered}=={a['executor_id'],b['executor_id']}
            assert all(r['connection_status']=='unverified' for r in discovered)
            assert read_candidates(registry,installation=base/'another-install')==[]
            if args.host_node:
                host_result=subprocess.run([str(Path(args.host_node).resolve(strict=True)),str(ROOT/'tools/multi-executor-host-smoke.mjs'),
                    str(registry)],cwd=ROOT,env=isolated_environment(base/'host-env'),check=True,timeout=60,
                    capture_output=True,text=True,encoding='utf-8',errors='replace',
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                assert 'two real Houdini main-thread Bridges passed' in host_result.stdout,host_result
                print(host_result.stdout.strip(),flush=True)
            try: ExecutorRegistration(registry,a['executor_id'],installation=ROOT,version='21.0.440')
            except RuntimeError: pass
            else: raise AssertionError('duplicate live executor admitted')
            for record, other in ((a,b),(b,a)):
                assert call(record,'/health')[1]['executorId']==record['executor_id']
                assert call(record,'/exec',{'code':'raise RuntimeError("wrong target")'},other['executor_id'])[0]==409
                _,health=call(record,'/requests/prepare',{'owner_session':record['task_id']})
                status,result=call(record,'/exec',{'code':'__result__=hou.applicationVersionString()',
                    'owner_session':record['task_id'],'owner_call':'probe','read_only':True,
                    'request_ref':health['requestRef'],
                    'expected_contract':{'version':health['executionContractVersion'],'hash':health['verbCatalog']['hash']}})
                assert status==200 and result['result']==record['houdini_version'],result
            third=ExecutorRegistration(registry,'d'*32,installation=ROOT,version='22.0.368')
            try:
                for target in (a['hip_path'],b['hip_path']):
                    try: third.claim_writer('conflict',target)
                    except RuntimeError: pass
                    else: raise AssertionError('concurrent HIP writer admitted')
                alias=base/'hardlink.hip'
                os.link(a['hip_path'],alias)
                try: third.claim_writer('alias-conflict',alias)
                except RuntimeError: pass
                else: raise AssertionError('hardlink bypassed writer exclusion')
                # Shared Repair changes only A's generation, retaining its exact
                # in-process node provenance and leaving B's service untouched.
                before_runtime=a['runtime_id']
                children[0].stdin.write('repair\n');children[0].stdin.flush()
                deadline=time.monotonic()+20
                while time.monotonic()<deadline:
                    updated=json.loads((registry/'endpoints'/(a['executor_id']+'.json')).read_text(encoding='utf-8'))
                    if updated['runtime_id']!=before_runtime:break
                    time.sleep(.1)
                assert updated['runtime_id']!=before_runtime
                a.update(updated)
                assert call(b,'/health')[1]['runtimeId']==b['runtime_id']
                status,edited=call(a,'/exec',{'code':"set_parms('/obj/owned_fixture',{'tx':2})",'owner_session':a['task_id']})
                assert status==200 and edited['ok'],edited
                # Kill only the process created by this test; other Bridge stays available.
                children[0].kill();children[0].wait(timeout=10)
                assert call(b,'/health')[0]==200
                third.claim_writer('after-exit',a['hip_path'])
                third.claim_writer('after-exit',a['hip_path'])  # exact retry is idempotent
                try: third.claim_writer('another-author',a['hip_path'])
                except RuntimeError: pass
                else: raise AssertionError('two authors on the same executor admitted')
                rows=read_candidates(registry,installation=ROOT)
                assert next(r for r in rows if r['executor_id']==a['executor_id'])['connection_status']=='unverified'
                # OS release is not an automatic task/ownership transfer.
                assert third._task=='after-exit'
            finally: third.close()
            children[1].stdin.write('\n');children[1].stdin.flush();children[1].wait(timeout=10)
            rows=read_candidates(registry,installation=ROOT)
            assert next(r for r in rows if r['executor_id']==b['executor_id'])['state']=='disconnected'
            try: ExecutorRegistration(registry,b['executor_id'],installation=ROOT,version='22.0.368')
            except RuntimeError: pass
            else: raise AssertionError('retired executor identity was reused')
            print('PASS: two real Bridges, distinct targets, zero cross-target dispatch, HIP/hardlink exclusion, single-process loss and orderly exit')
        finally:
            for process in children:
                if process.poll() is None: process.kill()
                process.communicate(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--registry');parser.add_argument('--hip');parser.add_argument('--task')
    parser.add_argument('--hython',action='append',default=[])
    parser.add_argument('--host-node',help='Optional Node runtime to verify shared TypeScript Host routing against both test Bridges')
    args=parser.parse_args()
    if args.worker: worker(args)
    else:
        if len(args.hython)!=2: parser.error('provide exactly two --hython executables')
        driver(args)
