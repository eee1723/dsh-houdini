"""No Houdini needed: strict inputs, no overwrite, and incomplete result refusal."""
import importlib.util
import builtins
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
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
    root = Path(raw).resolve()
    (root / 'build.py').write_text('raise RuntimeError("must not execute in pure tests")', encoding='utf-8')
    file = root / 'request-manifest.json'
    valid = {'script':'build.py', 'checks':[{'id':'output','kind':'cook','node':'/obj/geo/OUT','frame':1}]}
    def save(value):file.write_text(json.dumps(value), encoding='utf-8')
    save(valid)

    assert runner.load_manifest(file)==valid
    def chatty_native_call():
        os.write(1,b'prefix\n'+b'x'*200000+b'\n')
        os.write(1,b"[12:34:56] mantra: Unable to load texture 'E:/missing.png'\n")
        os.write(1,b"[12:34:57] mantra: Unable to load texture 'E:/missing.png'\n")
        os.write(1,b'Command: husk --renderer HdStormRendererPlugin -s /Render/settings\n')
        os.write(1,b"[12:34:57] Unable to load texture '../../../run/inputs/roughness.png'\n")
        # A diagnostic-looking fragment inside a long log line is not a match.
        os.write(1,b'z'*(runner._NATIVE_LINE_LIMIT+1) + b"[12:34:58] Unable to load texture 'fragment.png'\n")
        os.write(1,b'y'*200000)
        return {'ok':True,'outcome':{'checks':{'failed':0}}}
    envelope=runner._execute_with_native_output(chatty_native_call)
    assert envelope['native_output_omitted_bytes']>0 and len(envelope['native_output'])<300000
    assert 'Unable to load texture' not in envelope['native_output'], 'only the full stream contains the failures'
    assert [row['path'] for row in envelope['native_diagnostics']]==['E:/missing.png','../../../run/inputs/roughness.png']
    assert [row['renderer'] for row in envelope['native_diagnostics']]==['mantra','unknown']
    assert envelope['outcome']['checks']['failed']==1,'two diagnostics belong to one native renderer operation'
    try:runner._successful_execution_result(envelope)
    except RuntimeError as error:assert 'Unable to load texture' in str(error)
    else:raise AssertionError('a native texture failure was accepted')
    def many_texture_failures():
        for index in range(runner._NATIVE_DIAGNOSTIC_LIMIT+3):
            os.write(2,f"[12:34:57] Unable to load texture 'missing{index}.png'\n".encode('ascii'))
        return {'ok':True}
    many=runner._execute_with_native_output(many_texture_failures)
    assert len(many['native_diagnostics'])==runner._NATIVE_DIAGNOSTIC_LIMIT
    assert many['native_diagnostics_omitted_matches']==3
    # An ordinary authored check failure is not a native renderer diagnostic and
    # must not be reinterpreted by the isolated runner's texture-failure rule.
    ordinary={'ok':True,'result':{'points':8},'outcome':{'checks':{'failed':1}}}
    assert runner._successful_execution_result(ordinary)=={'points':8}
    cases=json.loads((ROOT/'tools/tests/fixtures/isolated-file-sequences.json').read_text(encoding='utf-8'))
    for case in cases['valid']:
        assert runner.manifest_inputs({'script':'build.py','files':case['files']})==case['expected']
    for files in cases['invalid']:
        rejects(lambda:runner.manifest_inputs({'script':'build.py','files':files}))
    # A short simulation's two 240-frame dependencies are ordinary input, not
    # 480 model-authored strings and not a reason to move computation to live.
    sequences=[{'pattern':'cache/'+name+'.$F4.txt','start':1,'end':240} for name in ('points','surface')]
    sequence_manifest={'script':'build.py','files':sequences,'checks':[]}
    (root/'cache').mkdir()
    for name in runner.manifest_inputs(sequence_manifest)[1:]:
        (root/name).write_text('exact frame input',encoding='utf-8')
    save(sequence_manifest)
    assert runner.load_manifest(file)==sequence_manifest
    assert len(runner.manifest_inputs(sequence_manifest))==481
    plan_bytes=json.dumps(sequence_manifest).encode('utf-8')
    with patch.object(runner,'regular_file',side_effect=AssertionError('planning must not read dependencies')):
        plan=runner.plan_manifest_bytes(plan_bytes)
    assert len(plan['files'])==481 and plan['input_root']=='.'
    assert plan['files'][0]=={'path':'build.py','max_bytes':1048576}
    planned=subprocess.run([sys.executable,str(ROOT/'tools/isolated-houdini-check.py'),'--plan'],
                           input=plan_bytes,capture_output=True,check=True)
    assert json.loads(planned.stdout)['plan']==plan
    for budgets in ({'memory_mb':127},{'memory_mb':65537},{'timeout':86401},{'timeout':float('nan')}):
        rejects(lambda:runner.plan_manifest_bytes(plan_bytes,**budgets))
    # Future manifest fields/limits cannot pass the Host and fail only after a
    # job starts: the pure planner uses the same complete validator as staging.
    for bad in ({'files':[]},{'script':'build.py','checks':[{'kind':'bogus'}]},
                {'script':'build.py','input_root':None}):
        rejects(lambda:runner.plan_manifest_bytes(json.dumps(bad).encode('utf-8')))
    authorized=runner.digest(file)
    assert runner.load_manifest(file,expected_sha256=authorized)==sequence_manifest
    save(valid)
    rejects(lambda:runner.check(file,root/'unused-hython',root/'manifest-drift',trusted=True,manifest_sha256=authorized))
    assert not (root/'manifest-drift').exists(), 'manifest drift rejects before staging or worker creation'
    (root/'cache/surface.0240.txt').unlink()
    save(sequence_manifest)
    rejects(lambda:runner.load_manifest(file))
    save(valid)
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

    # Inline builder source is first-class manifest syntax: same pure planner,
    # same bounded bytes, and it cannot alias a declared input file.
    save(valid)
    inline={'code':'__result__={"inline":True}','checks':[]}
    inline_bytes=json.dumps(inline).encode('utf-8')
    assert runner.plan_manifest_bytes(inline_bytes)['files']==[]
    save(inline)
    assert runner.load_manifest(file)==inline
    for bad in ({'code':'__result__={}','script':'build.py','checks':[]},
                {'code':''},{'code':'  \n'},{'code':None},{'code':1},
                {'code':'__result__={}','files':[runner.INLINE_SCRIPT]},
                {'code':'y'*(runner.INPUT_POLICY['maxInlineCodeBytes']+1)}):
        rejects(lambda:runner.plan_manifest_bytes(json.dumps(bad).encode('utf-8')))
    rejects(lambda:runner.plan_manifest_bytes(b'{"code":"\\ud800","checks":[]}'))
    comment_only={'code':'# a comment-only plan is not a builder\n','checks':[]}
    save(comment_only)
    assert runner.load_manifest(file)==comment_only
    # A manifest file keeps its own folder as the input anchor; an inline
    # manifest is anchored by the Host-supplied workspace base instead.
    bare={'code':'__result__={}','input_root':'.','checks':[]}
    inline_manifests=root/'inline-manifests';inline_manifests.mkdir()
    bare_path=inline_manifests/'bare-inline.json'
    bare_path.write_text(json.dumps(bare),encoding='utf-8')
    assert runner.manifest_input_root(bare_path,bare,str(root))==root.resolve()
    assert runner.manifest_input_root(bare_path,bare)==inline_manifests.resolve()
    assert runner.load_manifest(bare_path,base=str(root))==bare
    # The Host reserves the run directory atomically; the checker accepts only
    # that empty reservation and never writes over prior evidence.
    reserved=root/'reserved';reserved.mkdir()
    (reserved/'prior.txt').write_text('prior evidence',encoding='utf-8')
    rejects(lambda:runner.check(file,Path(sys.executable),reserved,trusted=True,reserved_output=True))
    assert (reserved/'prior.txt').read_text(encoding='utf-8')=='prior evidence'
    rejects(lambda:runner.check(file,Path(sys.executable),root/'reserved-missing',trusted=True,reserved_output=True))
    assert not (root/'reserved-missing').exists()
    save(valid)

    preview=root/'checks'/'preview.png';preview.parent.mkdir();preview.write_bytes(b'png fixture')
    candidates=[{'path':str(preview),'role':'visual-check','source':'render_view'},
                {'path':str(root/'outside.png'),'role':'diagnostic','source':'render_frame'}]
    rows=runner.visual_artifacts(root,[{'artifactCandidates':candidates}],
        [{'id':'render','status':'passed','artifact':{'file':'checks/preview.png','bytes':preview.stat().st_size,'sha256':runner.digest(preview)}}])
    assert len(rows)==2, 'deduplicated builder image and explicit check artifact, plus one unavailable path'
    assert rows[0]['artifact']=={'file':'checks/preview.png','bytes':preview.stat().st_size,'sha256':runner.digest(preview)}
    assert rows[0]['role']=='visual-check' and rows[0]['source']=='render_view'
    assert rows[1]['status']=='failed' and rows[1]['artifact']['file'].endswith('outside.png')
    assert rows[1]['error'], 'image transport failure stays separate from execution success'

    second_preview=root/'checks'/'second.png';second_preview.write_bytes(b'different image fixture')
    repeated=runner.visual_artifacts(root,[{'artifactCandidates':[
        {'path':str(preview)}, {'path':str(second_preview)}, {'path':str(preview)}]}],
        [{'status':'passed','artifact':{'file':'checks/preview.png','bytes':preview.stat().st_size,'sha256':runner.digest(preview)}}])
    assert len(repeated)==2
    for row, image in zip(repeated,(preview,second_preview)):
        assert row['artifact']=={'file':image.relative_to(root).as_posix(),'bytes':image.stat().st_size,'sha256':runner.digest(image)}, \
            'duplicate images must not overwrite another image fingerprint'

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
    many_fields={**envelope,'outcome':{'batch':'completed','operations':{'total':2,'failed':1}},
                 'execution':{'runtime_id':'r'*32,'verbose':['x'*300 for _ in range(100)]},
                 'transaction':{'status':'rolled_back','nodes':['node'*100 for _ in range(100)]},
                 'result':{'selected':'important result','payload':['z'*500 for _ in range(100)]},
                 'stdout':'authored note\n'+('log '*20000)}
    many_projected=runner.execution_projection(details_root,'many-fields',many_fields)
    assert len(runner._encoded(many_projected))<=runner.DETAIL_THRESHOLD,'one budget must cover the entire execution, not each field separately'
    assert many_projected['outcome']==many_fields['outcome']
    assert many_projected['execution']['runtime_id']=='r'*32
    assert runner.read_execution(details_root,many_projected)==many_fields
    assert runner.read_execution(details_root,projected)==envelope
    assert len(list((details_root/'executions').iterdir()))==2,'each distinct execution is archived once'
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
        if mode=='wrong-exit':
            assert result['result']['ok'] is True and 'process did not exit cleanly' in result['error']
            assert 'returncode=1' in result['error'], result
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

    # Input-root copying is version-pinned even if a source changes while the
    # worker runs. Original-source observations never replace execution facts.
    nested.write_text(json.dumps(combined),encoding='utf-8')
    snapshot_bytes=(root/'saved.hip').read_bytes()
    for mode in ('success','failed','deleted','unreadable'):
        (root/'saved.hip').write_bytes(snapshot_bytes)
        directory=root/('source-'+mode)
        def fake_changed_source(command, **kwargs):
            request=runner.read_json(Path(command[-1]));runtime='e'*32
            assert [row['file'] for row in request['inputs']]==['saved.hip','build.py']
            assert (directory/'inputs/saved.hip').read_bytes()==snapshot_bytes
            assert (directory/'inputs/build.py').read_bytes()==(root/'build.py').read_bytes()
            if mode=='deleted':(root/'saved.hip').unlink()
            else:(root/'saved.hip').write_bytes(b'new source version during execution')
            result={'run_id':request['run_id'],'ok':mode!='failed','phase':'completed',
                    'runtime':{'runtime_id':runtime},'checks':[],
                    'snapshot':{'sha256':request['inputs'][0]['sha256'],
                                'path':str(directory/'inputs/saved.hip')},
                    'builder':{'ok':mode!='failed','execution':{'runtime_id':runtime}}}
            if mode=='failed':result.update(error=original_error)
            runner.write_json(directory/'worker-result.json',result)
            return {'status':'failed' if mode=='failed' else 'completed','returncode':1 if mode=='failed' else 0,
                    'started':True,'released':True,'tree_reaped':True,'output':''}
        original_digest=runner.digest
        def unreadable_source(path):
            if Path(path)==root/'saved.hip' and (directory/'worker-result.json').exists():
                raise PermissionError('source read unavailable after execution')
            return original_digest(path)
        with patch.object(limits,'run_gated_worker',side_effect=fake_changed_source):
            if mode=='unreadable':
                with patch.object(runner,'digest',side_effect=unreadable_source):
                    changed=runner.check(nested,Path(sys.executable),directory,trusted=True)
            else:changed=runner.check(nested,Path(sys.executable),directory,trusted=True)
        assert changed['ok'] is (mode!='failed'),changed
        observation=changed['input_observations'][0]
        assert observation['before_sha256']==original_digest(directory/'inputs/saved.hip')
        assert observation['source_path']==str(root/'saved.hip')
        assert changed['inputs_unchanged'] is (None if mode in ('deleted','unreadable') else False)
        if mode in ('deleted','unreadable'):
            assert observation['status']=='unavailable' and observation['after_sha256'] is None and observation['error']
        else:
            assert observation['status']=='changed' and observation['after_sha256']==original_digest(root/'saved.hip')
        if mode=='failed':assert changed['error']==original_error
        else:assert not changed.get('error'),changed
        assert (directory/'inputs/saved.hip').read_bytes()==snapshot_bytes
        state=runner.status(directory)
        assert state['input_observations']==changed['input_observations'] and state['inputs_unchanged']==changed['inputs_unchanged']

    # Staging integrity still fails before a worker can consume altered bytes.
    (root/'saved.hip').write_bytes(snapshot_bytes)
    original_copy=runner.shutil.copy2
    def corrupt_copy(source,target):
        original_copy(source,target)
        Path(target).write_bytes(b'corrupted during staging')
    with patch.object(runner.shutil,'copy2',side_effect=corrupt_copy), \
         patch.object(limits,'run_gated_worker',side_effect=AssertionError('worker must not be started')):
        corrupted=runner.check(nested,Path(sys.executable),root/'corrupt-staging',trusted=True)
    assert not corrupted['ok'] and 'input changed during staging' in corrupted['error'],corrupted
    def second_copy_failed(source,target):
        if Path(target).name=='build.py':raise OSError('second source staging failed')
        return original_copy(source,target)
    with patch.object(runner.shutil,'copy2',side_effect=second_copy_failed), \
         patch.object(limits,'run_gated_worker',side_effect=AssertionError('worker must not be started')):
        partial=runner.check(nested,Path(sys.executable),root/'partial-staging',trusted=True)
    assert not partial['ok'] and partial['error']=='second source staging failed',partial
    assert partial['inputs_unchanged'] is None
    assert len(partial['inputs'])==1 and len(partial['input_observations'])==2
    pending=partial['input_observations'][1]
    assert pending['file']=='build.py' and pending['status']=='unavailable'
    assert pending['before_sha256'] is None and pending['after_sha256'] is None and 'not fully staged' in pending['error']

    package=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))
    assert all(name in package['files'] for name in ('tools/isolated-houdini-check.py','tools/houdini_test_environment.py'))
    # Status/cancel works during staging before a request file exists; it never
    # infers liveness or mistakes a cancellation request for terminal success.
    staging=root/'staging';staging.mkdir()
    runner.write_json(staging/'report.json',{'ok':False,'finished':False,'phase':'staging','run_id':'a'*32})
    state=runner.status(staging,cancel=True)
    assert state['phase']=='staging' and state['cancel_requested'] and not state['finished']
    # A bounded manifest may expand to a larger staged inventory. Worker and
    # status readers use the run budget, not the small authored-manifest budget.
    expanded={'run_id':'a'*32,'inputs':[{'file':('segment/'*50)+str(i)+'.txt','sha256':'a'*64,'bytes':1}
                                    for i in range(9000)]}
    runner.write_json(staging/'request.json',expanded)
    assert (staging/'request.json').stat().st_size>4*1024*1024
    assert runner.read_json(staging/'request.json',runner.MAX_ARCHIVE_BYTES)==expanded
    assert runner.status(staging)['phase']=='staging'
    runner.write_json(staging/'request.json',{'run_id':'b'*32,'inputs':[]})
    rejects(lambda:runner.status(staging))
# Only the released one-shot worker enters native shutdown. Ordinary CLI and
# pure manifest planning must remain usable without Houdini/USD installed.
original_import=builtins.__import__
def without_hom(name,*args,**kwargs):
    if name=='hou' or name=='pxr' or name.startswith('pxr.'):
        raise AssertionError('ordinary CLI imported native Houdini/USD')
    return original_import(name,*args,**kwargs)
with patch.object(sys,'argv',['checker','--worker','unused-request.json']), \
     patch.object(sys,'stdin',io.StringIO('NOT_GO\n')), \
     patch.object(runner,'worker',side_effect=AssertionError('unreleased worker executed')), \
     patch.object(builtins,'__import__',side_effect=without_hom):
    assert runner.main()==2
with patch.object(sys,'argv',['checker','--plan']), \
     patch.object(sys,'stdin',io.TextIOWrapper(io.BytesIO(b'{"script":"build.py"}'),encoding='utf-8')), \
     patch.object(sys,'stdout',io.StringIO()) as output, \
     patch.object(builtins,'__import__',side_effect=without_hom):
    assert runner.main()==0 and json.loads(output.getvalue())['ok']
events=[]
def native_exit(*,exit_code,suppress_save_prompt):
    events.append(('exit',exit_code,suppress_save_prompt))
    raise SystemExit(exit_code)
work=SimpleNamespace(SetConcurrencyLimit=lambda count:events.append(('limit',count)))
native=SimpleNamespace(isUIAvailable=lambda:False,exit=native_exit)
with patch.dict(sys.modules,{'hou':native,'pxr':SimpleNamespace(Work=work)}):
    for expected in (0,1,17):
        events.clear()
        def completed(_request):
            events.append('work-and-report-completed')
            return expected
        with patch.object(sys,'argv',['checker','--worker','owned-request.json']), \
             patch.object(sys,'stdin',io.StringIO('GO\n')), patch.object(runner,'worker',side_effect=completed):
            try:runner.main()
            except SystemExit as exited:assert exited.code==expected
            else:raise AssertionError('native worker exit returned')
        assert events==['work-and-report-completed',('limit',1),('exit',expected,True)]
    for target,name in ((work,'SetConcurrencyLimit'),(native,'exit')):
        with patch.object(target,name,side_effect=RuntimeError('EXPECTED_SHUTDOWN_FAILURE')):
            try:runner._exit_worker(0)
            except RuntimeError as error:assert str(error)=='EXPECTED_SHUTDOWN_FAILURE'
            else:raise AssertionError('shutdown failure was ignored')
    with patch.object(native,'isUIAvailable',return_value=True):
        try:runner._exit_worker(0)
        except RuntimeError as error:assert 'headless' in str(error)
        else:raise AssertionError('a GUI process was accepted for disposable shutdown')
print('isolated manifest, trust, path aliases, result completeness/runtime, native shutdown and packaging contracts passed')
