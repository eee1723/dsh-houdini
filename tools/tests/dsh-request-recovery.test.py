"""Real main-thread queue, response loss and same-reference admission."""
import sys,threading,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
from dsh_requests import RequestRegistry
owner='receipt-owner'
def handler(path,send):
    h=object.__new__(b._Handler);h.path=path;h._send=send
    return h
def ref():return b._RUNTIME_ID+'.'+uuid.uuid4().hex
def body(token,code):return {'code':code,'request_ref':token,'owner_session':owner,
    'owner_call':uuid.uuid4().hex,'expected_contract':{'version':b._EXECUTION_CONTRACT_VERSION,'hash':b._VERB_CATALOG_HASH}}
created=[];original=b._pump_active;b._pump_active=True
try:
    token=ref();name='__request_'+uuid.uuid4().hex[:8]
    payload=body(token,f'__result__=tab_create("/obj","geo","{name}").path()')
    sent=[];thread_errors=[]
    def disconnect(result,status=200):
        sent.append(result);raise BrokenPipeError('injected client disconnected')
    def worker():
        try:handler('/exec',disconnect)._route(payload)
        except BrokenPipeError:thread_errors.append('expected disconnect')
    thread=threading.Thread(target=worker);thread.start()
    deadline=time.monotonic()+3
    while b._work_queue.empty() and time.monotonic()<deadline:time.sleep(.01)
    assert not b._work_queue.empty()
    assert b._request_registry.status(token,owner)['status']=='queued'
    assert hou.node('/obj/'+name) is None
    queued=[]
    handler('/exec',lambda value,status=200:queued.append(value))._route(payload)
    assert queued[0]['requestReceipt']['status']=='queued' and b._work_queue.qsize()==1
    b._pump();thread.join(3);assert not thread.is_alive()
    node=hou.node('/obj/'+name);assert node is not None;created.append(node)
    assert thread_errors==['expected disconnect']
    recovered=[]
    handler('/requests/status',lambda value,status=200:recovered.append(value))._route({'request_ref':token,'owner_session':owner})
    receipt=recovered[0]['requestReceipt']
    assert receipt['status']=='done' and receipt['result']['result']==node.path()
    identity=node.sessionId();duplicate=[]
    handler('/exec',lambda value,status=200:duplicate.append((status,value)))._route(payload)
    assert duplicate[0][0]==200 and duplicate[0][1]['execution']['sequence']==sent[0]['execution']['sequence']
    assert hou.node('/obj/'+name).sessionId()==identity
    conflict=[]
    handler('/exec',lambda value,status=200:conflict.append(status))._route({**payload,'code':'raise RuntimeError()'})
    assert conflict==[409]
    assert b._request_registry.status(token,'foreign')['status']=='unknown'
    assert b._request_registry.status('f'*32+'.'+'e'*32,owner)['status']=='unknown_runtime'
    token2=ref();observed=[];release=threading.Event();entered=threading.Event();original_code=b.run_code
    def gated(*args,**kwargs):
        entered.set();assert release.wait(3);return original_code(*args,**kwargs)
    def observer():
        assert entered.wait(3);observed.append(b._request_registry.status(token2,owner)['status']);release.set()
    b.run_code=gated;watch=threading.Thread(target=observer);watch.start()
    try:handler('/exec',lambda *a,**k:None)._route(body(token2,'__result__=42'))
    finally:b.run_code=original_code
    watch.join(3);assert observed==['running']
    # Lost job admission reply still maps to exactly one job, before it runs.
    job_token=ref();job_name='__job_'+uuid.uuid4().hex[:8]
    job_payload=body(job_token,f'__result__=tab_create("/obj","geo","{job_name}").path()')
    try:handler('/jobs',disconnect)._route(job_payload)
    except BrokenPipeError:pass
    job_receipt=b._request_registry.status(job_token,owner)
    jid=job_receipt['result']['jobId']
    assert job_receipt['kind']=='job_submit' and job_receipt['owner_call']==job_payload['owner_call']
    job_ids=set(b._jobs);again=[]
    handler('/jobs',lambda value,status=200:again.append(value))._route(job_payload)
    assert again[0]['jobId']==jid and set(b._jobs)==job_ids
    deadline=time.monotonic()+3
    while b._work_queue.empty() and time.monotonic()<deadline:time.sleep(.01)
    b._pump()
    deadline=time.monotonic()+3
    while b._jobs[jid]['status'] in ('queued','running') and time.monotonic()<deadline:time.sleep(.01)
    assert b._jobs[jid]['status']=='done';created.append(hou.node('/obj/'+job_name))
    identity=created[-1].sessionId()
    handler('/jobs',lambda *a,**k:None)._route(job_payload)
    assert hou.node('/obj/'+job_name).sessionId()==identity and set(b._jobs)==job_ids
    index=[]
    handler('/requests/status',lambda value,status=200:index.append(value))._route({'request_ref':'index','owner_session':owner})
    assert any(r['owner_call']==job_payload['owner_call'] and r['request_ref']==job_token for r in index[0]['requestReceipt']['requests'])
    assert b._request_registry.recent('other')['requests']==[]
    # Rejection registers nonexecution and repeating the ref never admits later.
    original_max=b._MAX_ACTIVE_JOBS;b._MAX_ACTIVE_JOBS=0
    rejected=ref();rejected_body=body(rejected,'__result__=0');responses=[]
    try:handler('/jobs',lambda value,status=200:responses.append(status))._route(rejected_body)
    finally:b._MAX_ACTIVE_JOBS=original_max
    assert responses==[429] and b._request_registry.status(rejected,owner)['status']=='not_executed'
    handler('/jobs',lambda *a,**k:None)._route(rejected_body)
    assert set(b._jobs)==job_ids
    # Queued cancellation blocks the worker even when recovered much later.
    cancel_ref=ref();cancel_body=body(cancel_ref,'raise RuntimeError("cancelled job must never execute")');handles=[]
    handler('/jobs',lambda value,status=200:handles.append(value))._route(cancel_body)
    cancel_id=handles[0]['jobId']
    handler('/jobs/'+cancel_id+'/cancel',lambda *a,**k:None)._route({})
    assert b._jobs[cancel_id]['status']=='cancelled'
    deadline=time.monotonic()+3
    while b._work_queue.empty() and time.monotonic()<deadline:time.sleep(.01)
    b._pump()
    assert b._jobs[cancel_id]['status']=='cancelled'
    # Job links survive result retention expiry/budget; long jobs remain findable.
    tiny=RequestRegistry('a'*32,result_bytes=0,retention=-1)
    tiny.reserve('a'*32+'.'+'d'*32,owner,{'request_kind':'job_submit'})
    tiny.complete('a'*32+'.'+'d'*32,{'jobId':'long-job'})
    assert tiny.status('a'*32+'.'+'d'*32,owner)['jobId']=='long-job'
    registry=RequestRegistry('a'*32,limit=1,result_bytes=1000,retention=-1);old='a'*32+'.'+'b'*32
    assert registry.reserve(old,owner,{'code':'x'})
    registry.running(old);registry.complete(old,{'ok':True})
    assert registry.status(old,owner)['status']=='result_expired'
    assert not registry.reserve(old,owner,{'code':'x'})
    try:registry.reserve('a'*32+'.'+'c'*32,owner,{'code':'y'});raise AssertionError('capacity expected')
    except ValueError as e:assert 'capacity' in str(e)
    b._pump_active=False;token3=ref();failures=[]
    def unavailable():
        try:handler('/exec',lambda *a,**k:None)._route(body(token3,'raise RuntimeError("must not execute")'))
        except RuntimeError:failures.append(1)
    down=threading.Thread(target=unavailable);down.start();down.join(3)
    assert failures and b._request_registry.status(token3,owner)['status']=='not_executed'
finally:
    b._pump_active=original
    for n in created:n.destroy()
print('request queued/running/lost response/dedupe/conflict/owner/runtime/expiry/capacity/not-executed passed on '+hou.applicationVersionString())
