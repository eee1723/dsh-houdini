"""No Houdini needed: strict inputs, no overwrite, and incomplete result refusal."""
import importlib.util
import json
from pathlib import Path
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
    for path in ('../escape', '/absolute', 'C:/escape', 'a\\b', 'a//b', './a', 'a/../b',
                 'a.txt:stream', 'NUL.txt', 'COM1/x', 'COM¹.txt', 'CON .txt', 'a.', 'a/ tail', '$HIP/file', 'a\x00b'):
        rejects(lambda:runner.relative_file(path))
    invalid = [{**valid,'unknown':1}, {**valid,'script':'scene.hip'}, {**valid,'files':['build.py']},
               {**valid,'files':['../outside']}, {**valid,'checks':[]}, {**valid,'checks':valid['checks']*2}]
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
            return {'status':'completed','returncode':1 if mode=='wrong-exit' else 0,'started':True,'released':True,'output':''}
        with patch.object(limits,'run_gated_worker',side_effect=fake_worker):
            result=runner.check(file,Path(sys.executable),directory,trusted=True)
        assert result['ok'] is (mode=='valid'),(mode,result)
        assert runner.read_json(directory/'report.json')['ok'] is (mode=='valid')

    package=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))
    assert all(name in package['files'] for name in ('tools/isolated-houdini-check.py','tools/houdini_test_environment.py'))
print('isolated manifest, trust, path aliases, result completeness/runtime and packaging contracts passed')
