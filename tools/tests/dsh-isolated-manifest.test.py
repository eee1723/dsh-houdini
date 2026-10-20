"""No Houdini needed: strict inputs, no overwrite, and incomplete result refusal."""
import importlib.util
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_worker_limits as limits
spec = importlib.util.spec_from_file_location('isolated_check', ROOT / 'tools/isolated-houdini-check.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

def rejects(call):
    try:call()
    except (ValueError, OSError):return
    raise AssertionError('invalid request was accepted')

with tempfile.TemporaryDirectory(prefix='dsh-isolated-manifest-') as raw:
    root = Path(raw)
    (root / 'build.py').write_text('raise RuntimeError("must not execute in pure tests")', encoding='utf-8')
    file = root / 'request-manifest.json'
    valid = {'script':'build.py', 'checks':[{'id':'output','kind':'cook','node':'/obj/geo/OUT','frame':1}]}
    def save(value):file.write_text(json.dumps(value), encoding='utf-8')
    save(valid)

    assert runner.load_manifest(file)==valid
    for probe in ({'script':'build.py'}, {'script':'build.py','checks':[]}):
        save(probe)
        assert runner.load_manifest(file)=={'script':'build.py','checks':[]}
    for path in ('../escape', '/absolute', 'C:/escape', 'a\\b', 'a//b', './a', 'a/../b',
                 'a.txt:stream', 'NUL.txt', 'COM1/x', 'COM¹.txt', 'CON .txt', 'a.', 'a/ tail', '$HIP/file', 'a\x00b'):
        rejects(lambda:runner.relative_file(path))
    invalid = [{**valid,'unknown':1}, {**valid,'script':'scene.hip'}, {**valid,'files':['build.py']},
               {**valid,'files':['../outside']}, {**valid,'checks':None}, {**valid,'checks':valid['checks']*2},
               {**valid,'checks':[{**valid['checks'][0],'id':'out'+str(i)} for i in range(17)]}]
    for override in ({'id':'con'}, {'frame':True}, {'frame':float('nan')}, {'kind':'python'},
                     {'node':'/obj/../out'}, {'expect':{'points':True}}, {'expect':{'points':-1}},
                     {'expect':{'bbox':1}}, {'file':'unexpected.bgeo'}, {'kind':'cache','file':'missing.exe'},
                     {'kind':'render','file':'x.png','expect':{'points':8}}):
        invalid.append({**valid,'checks':[{**valid['checks'][0],**override}]})
    for value in invalid:
        save(value)
        rejects(lambda:runner.load_manifest(file))
    file.write_text('{"script":"build.py","script":"other.py","checks":[]}', encoding='utf-8')
    rejects(lambda:runner.load_manifest(file))
    save(valid)
    rejects(lambda:runner.check(file,Path(sys.executable),root/'untrusted'))
    assert not (root/'untrusted').exists()
    with patch.object(runner,'is_reparse',side_effect=lambda path:path==root/'artifacts'):
        rejects(lambda:runner.artifact_target(root,{'id':'out','file':'file.bgeo'}))
    assert not (root/'artifacts').exists(), 'must reject reparse ancestry before creating/exporting'
    target=runner.artifact_target(root,{'id':'out','file':'nested/file.bgeo'})
    target.write_bytes(b'original')
    rejects(lambda:runner.artifact_target(root,{'id':'out','file':'nested/file.bgeo'}))
    assert target.read_bytes()==b'original'

    # A manifest can live with scripts while explicitly naming the project
    # input root. File names still cannot traverse outside that root.
    manifest_dir=root/'scripts';manifest_dir.mkdir()
    nested=manifest_dir/'render.json'
    (root/'saved.hip').write_bytes(b'authored disposable HIP placeholder')
    combined={'input_root':'..','hip':'saved.hip','script':'build.py','checks':[]}
    nested.write_text(json.dumps(combined),encoding='utf-8')
    assert runner.load_manifest(nested)==combined
    assert runner.manifest_input_root(nested,combined)==root.resolve()
    assert runner.manifest_inputs(combined)==['saved.hip','build.py']
    absolute={**combined,'input_root':str(root)}
    nested.write_text(json.dumps(absolute),encoding='utf-8')
    assert runner.load_manifest(nested)==absolute
    for override in ({'hip':'../saved.hip'}, {'script':'/absolute.py'},
                     {'files':['saved.hip']}, {'input_root':str(root/'build.py')},
                     {'input_root':''}, {'input_root':17}):
        nested.write_text(json.dumps({**combined,**override}),encoding='utf-8')
        rejects(lambda:runner.load_manifest(nested))
    # Explicit roots follow native aliases, just like the default manifest
    # directory. Reparse traversal *below* the selected root still refuses.
    alias=root/'explicit-root-alias'
    if os.name=='nt':
        linked=subprocess.run(['cmd','/d','/c','mklink','/J',str(alias),str(root)],capture_output=True,text=True)
        assert linked.returncode==0,linked.stderr
    else:
        alias.symlink_to(root,target_is_directory=True)
    try:
        named={**combined,'input_root':str(alias)}
        nested.write_text(json.dumps(named),encoding='utf-8')
        assert runner.load_manifest(nested)==named
        selected=runner.manifest_input_root(nested,named)
        assert selected==root.resolve() and runner.regular_file(selected,'build.py')==root/'build.py'
        rejects(lambda:runner.regular_file(selected,'explicit-root-alias/build.py'))
    finally:
        alias.rmdir() if os.name=='nt' else alias.unlink()
    with tempfile.TemporaryDirectory(prefix='dsh-isolated-external-') as external:
        external=Path(external);(external/'outside.py').write_text('outside',encoding='utf-8')
        child=root/'redirected-child'
        if os.name=='nt':
            linked=subprocess.run(['cmd','/d','/c','mklink','/J',str(child),str(external)],capture_output=True,text=True)
            assert linked.returncode==0,linked.stderr
        else:
            child.symlink_to(external,target_is_directory=True)
        try:
            rejects(lambda:runner.regular_file(root,'redirected-child/outside.py'))
        finally:
            child.rmdir() if os.name=='nt' else child.unlink()

    # Raw envelopes larger than the former 4 MiB reader are archived once.
    # Their execution error remains directly visible in the compact projection.
    details_root=root/'large-details';details_root.mkdir()
    original_error='ValueError: box transaction journal budget exceeded; split the exec before any writes'
    envelope={'ok':False,'error':original_error,'stdout':'[verb] large inventory '+('x'*5_700_000),
              'outcome':{'batch':'failed','checks':{'failed':1}},
              'transaction':{'status':'rolled_back'},'execution':{'runtime_id':'a'*32,'owner_session':'isolated-test'},
              'verbs':[{'check_status':'passed'}],
              'evidence':[{'ledgerIndex':1,'verb':'test_controls','restored':True,'case_id':'actual-control'}]}
    projected=runner.execution_projection(details_root,'builder',envelope)
    assert projected['ok'] is False and projected['error']==original_error
    assert projected['details']['stored'] and projected['details']['bytes']>5_700_000
    assert len(runner._encoded(projected))<runner.DETAIL_THRESHOLD
    assert runner.read_execution(details_root,projected)==envelope
    assert len(list((details_root/'executions').iterdir()))==1
    assert projected['evidence']==envelope['evidence']
    original_bytes=Path(projected['details']['path']).read_bytes()
    # Attempting to reuse the same archive id reports archival failure only.
    collision=runner.execution_projection(details_root,'builder',envelope)
    assert collision['ok'] is False and collision['error']==original_error and not collision['details']['stored']
    assert collision['stdout']==envelope['stdout'] and collision['evidence']==envelope['evidence']
    assert 'detail_pointer' not in runner._encoded(collision)
    assert Path(projected['details']['path']).read_bytes()==original_bytes
    stale=deepcopy(projected);stale['details']['sha256']='0'*64
    assert runner.read_execution(details_root,stale)['error']==original_error and stale['details_error']
    escaped=deepcopy(projected);escaped['details']['path']=str(root/'build.py')
    assert runner.read_execution(details_root,escaped)['error']==original_error and escaped['details_error']
    Path(projected['details']['path']).write_bytes(b'corrupt')
    assert runner.read_execution(details_root,projected)['error']==original_error and projected['details_error']
    ok_envelope={**envelope,'ok':True,'error':None,'scope':'execution only','semantic_status':'unverified',
                 'restored':False,'script':{'path':str(root/'build.py'),'sha256':'e'*64,'bytes':17},
                 'result':{'ok':True,'nonempty':True,'fresh':True,'errors':[],
                           'user_payload':'y'*100_000,'scope':'selected output only',
                           'semantic_status':'unverified','restored':False,'tiny_fact':17}}
    ok_projected=runner.execution_projection(details_root,'successful',ok_envelope)
    assert ok_projected['ok'] and ok_projected['result']['ok'] and ok_projected['result']['nonempty']
    assert ok_projected['result']['fresh'] and ok_projected['result']['errors']==[]
    assert ok_projected['result']['user_payload']['detail_pointer']=='/result/user_payload'
    assert ok_projected['result']['tiny_fact']==17
    with patch.object(runner,'MAX_ARCHIVE_BYTES',32):
        unavailable=runner.execution_projection(details_root,'over-budget',ok_envelope)
    assert unavailable['ok'] and unavailable['details']['stored'] is False
    assert unavailable['details']['full_retained'] is False
    assert unavailable['scope']=='execution only' and unavailable['semantic_status']=='unverified'
    assert unavailable['restored'] is False and unavailable['script']==ok_envelope['script']
    assert unavailable['result']['scope']=='selected output only' and unavailable['result']['restored'] is False
    assert unavailable['result']['semantic_status']=='unverified'
    assert unavailable['result']['user_payload']['unavailable_field']=='/result/user_payload'
    assert 'detail_pointer' not in runner._encoded(unavailable)
    # A run with little remaining inline space stays readable even if an
    # otherwise retainable envelope cannot be archived.
    limited=runner.execution_projection(details_root,'builder',ok_envelope,inline_budget=100_000)
    assert limited['ok'] and limited['details']['stored'] is False and limited['details']['full_retained'] is False
    assert len(runner._encoded(limited).encode('utf-8'))<100_000
    # Failure/restoration facts precede a large successful inspection inventory.
    evidence=[{'ledgerIndex':1,'verb':'verify_network','ok':True,'scope':'passed selected output','large':'w'*100_000},
              {'ledgerIndex':2,'verb':'set_parms','ok':False,'restored':False,'restore_errors':['restore incomplete']}]
    priority=runner.execution_projection(details_root,'evidence-priority',{**envelope,'evidence':evidence,
        'verbs':[{'check_status':'passed','ok':True},{'ok':False}]})
    assert priority['evidence'][0]['verb']=='set_parms' and priority['evidence'][0]['restored'] is False
    assert priority['evidence'][1]['verb']=='verify_network'
    expanded={'errors':['x'*190 for _ in range(400)],'failure_reasons':['y'*190 for _ in range(400)],
              'scope':'explicit output only','semantic_status':'unverified','restored':False,
              'status':'passed','phase':'completed'}
    displayed=runner._bounded(expanded,'/result')
    for key in ('scope','semantic_status','restored','status','phase'):
        assert displayed[key]==expanded[key],(key,displayed)
    neutral=runner._brief_text('a'*30_000)
    assert 'this field was shortened' in neutral
    assert 'was not retained' not in neutral and 'see execution details' not in neutral

    # A worker exit code or author-supplied ok flag cannot replace evidence.
    for index, mode in enumerate(('valid', 'missing', 'malformed', 'wrong-identity', 'incomplete', 'wrong-runtime', 'wrong-exit')):
        directory=root/('result-'+str(index))
        def fake_worker(command, **kwargs):
            request=runner.read_json(Path(command[-1]))
            runtime='a'*32
            result={'run_id':request['run_id'],'ok':True,'phase':'completed',
                    'runtime':{'runtime_id':runtime},'builder':{'ok':True,'execution':{'runtime_id':runtime}},
                    'checks':[{**valid['checks'][0],'status':'passed',
                               'execution':{'ok':True,'execution':{'runtime_id':runtime},'result':{'ok':True,'nonempty':True}}}]}
            if mode=='wrong-identity':result['run_id']='foreign'
            if mode=='incomplete':result['checks']=[]
            if mode=='wrong-runtime':result['checks'][0]['execution']['execution']['runtime_id']='b'*32
            if mode=='malformed':(directory/'worker-result.json').write_text('{broken',encoding='utf-8')
            elif mode!='missing':runner.write_json(directory/'worker-result.json',result)
            return {'status':'completed','returncode':1 if mode=='wrong-exit' else 0,'started':True,
                    'released':True,'tree_reaped':True,'output':''}
        with patch.object(limits,'run_gated_worker',side_effect=fake_worker):
            result=runner.check(file,Path(sys.executable),directory,trusted=True)
        assert result['ok'] is (mode=='valid'),(mode,result)
        assert runner.read_json(directory/'report.json')['ok'] is (mode=='valid')
        assert result['runtime_environment']['cleaned']
        assert not Path(result['runtime_environment']['path']).exists()
        assert not (directory/'runtime').exists()

    # A failed/changed detail does not replace the actual operation failure;
    # the full raw error can always be distinguished from archival availability.
    for index, mode in enumerate(('large-ok','large-error','corrupt','stale','runtime-drift','unreaped','cleanup-failed')):
        directory=root/('archived-'+str(index))
        def fake_archived(command, **kwargs):
            request=runner.read_json(Path(command[-1]));runtime='c'*32
            raw={'ok':mode!='large-error','error':original_error if mode=='large-error' else None,
                 'stdout':'[verb] '+('z'*5_700_000),'result':{'probe':17},
                 'execution':{'runtime_id':runtime}}
            item=runner.execution_projection(directory,'builder',raw)
            if mode=='corrupt':Path(item['details']['path']).write_bytes(b'changed after worker')
            if mode=='stale':item['details']['sha256']='0'*64
            if mode=='runtime-drift':item['execution']['runtime_id']='d'*32
            value={'run_id':request['run_id'],'ok':raw['ok'],'phase':'completed',
                   'runtime':{'runtime_id':runtime},'builder':item,'checks':[]}
            if not raw['ok']:value['error']=original_error
            runner.write_json(directory/'worker-result.json',value)
            return {'status':'completed' if raw['ok'] else 'failed','returncode':0 if raw['ok'] else 1,
                    'started':True,'released':True,'tree_reaped':mode!='unreaped','output':''}
        save({'script':'build.py','checks':[]})
        with patch.object(limits,'run_gated_worker',side_effect=fake_archived):
            if mode=='cleanup-failed':
                with patch.object(runner.shutil,'rmtree',side_effect=PermissionError('runtime fixture still busy')):
                    result=runner.check(file,Path(sys.executable),directory,trusted=True)
            else:
                result=runner.check(file,Path(sys.executable),directory,trusted=True)
        assert result['ok'] is (mode not in ('large-error','runtime-drift')),(mode,result)
        assert (directory/'report.json').stat().st_size<100_000
        if mode=='large-error':assert result['error']==original_error
        if mode in ('corrupt','stale'):assert result['result']['builder']['details_error']
        if mode in ('unreaped','cleanup-failed'):
            assert not result['runtime_environment']['cleaned']
            assert Path(result['runtime_environment']['path']).exists()
            if mode=='cleanup-failed':assert result['runtime_environment']['cleanup_error']
            # This fake worker never started a process; the test owns its temp.
            import shutil
            shutil.rmtree(result['runtime_environment']['path'])
    save(valid)

    # Input-root copying is version-pinned even if the source changes while the
    # worker runs; that finding must not hide an independent execution error.
    nested.write_text(json.dumps(combined),encoding='utf-8')
    snapshot_bytes=(root/'saved.hip').read_bytes()
    directory=root/'changed-source'
    def fake_changed_source(command, **kwargs):
        request=runner.read_json(Path(command[-1]))
        assert [row['file'] for row in request['inputs']]==['saved.hip','build.py']
        assert (directory/'inputs/saved.hip').read_bytes()==snapshot_bytes
        assert (directory/'inputs/build.py').read_bytes()==(root/'build.py').read_bytes()
        (root/'saved.hip').write_bytes(b'new source version during execution')
        runner.write_json(directory/'worker-result.json',{'run_id':request['run_id'],'ok':False,
            'phase':'builder','error':original_error,'checks':[],'builder':{'ok':False,'error':original_error}})
        return {'status':'failed','returncode':1,'started':True,'released':True,'tree_reaped':True,'output':''}
    with patch.object(limits,'run_gated_worker',side_effect=fake_changed_source):
        changed=runner.check(nested,Path(sys.executable),directory,trusted=True)
    assert not changed['ok'] and not changed['inputs_unchanged']
    assert changed['error']==original_error and changed['input_check_error']
    assert (directory/'inputs/saved.hip').read_bytes()==snapshot_bytes

    package=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))
    assert all(name in package['files'] for name in ('tools/isolated-houdini-check.py','tools/houdini_test_environment.py'))
    # Status/cancel works during staging before a request file exists; it never
    # infers liveness or mistakes a cancellation request for terminal success.
    staging=root/'staging';staging.mkdir()
    runner.write_json(staging/'report.json',{'ok':False,'finished':False,'phase':'staging','run_id':'a'*32})
    state=runner.status(staging,cancel=True)
    assert state['phase']=='staging' and state['cancel_requested'] and not state['finished']
    runner.write_json(staging/'request.json',{'run_id':'b'*32,'inputs':[]})
    rejects(lambda:runner.status(staging))
print('isolated manifest, trust, path aliases, result completeness/runtime and packaging contracts passed')
