"""Real bounded worker cook/cache/ROP checks; only authored disposable fixtures."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import hou
import dsh_worker_limits as limits

spec = importlib.util.spec_from_file_location('isolated_check', ROOT / 'tools/isolated-houdini-check.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
hython = Path(hou.text.expandString('$HFS')) / 'bin/hython.exe'
before = (hou.hipFile.path(), hou.frame(), tuple(n.sessionId() for n in hou.node('/obj').children()))

with tempfile.TemporaryDirectory(prefix='dsh-isolated-中文 空格-') as raw:
    root = Path(raw)
    script = root / 'build.py'
    code = '''from __future__ import annotations
g=tab_create('/obj','geo',name='isolated')
n=tab_create(g,'box',name='OUT')
r=tab_create('/out','geometry',name='CACHE_ROP')
set_parms(r,{'soppath':n.path()})
'''
    script.write_text(code, encoding='utf-8')
    manifest_path = root / 'manifest.json'
    checks = [
        {'id':'cook','kind':'cook','node':'/obj/isolated/OUT','frame':1,'expect':{'points':8,'primitives':6}},
        {'id':'cache','kind':'cache','node':'/obj/isolated/OUT','frame':2,'file':'box.bgeo.sc','expect':{'points':8}},
        {'id':'rop','kind':'render','node':'/out/CACHE_ROP','frame':3,'file':'rop.bgeo.sc'},
    ]
    def manifest(rows=checks, files=None):
        value={'script':'build.py','checks':rows}
        if files is not None:value['files']=files
        manifest_path.write_text(json.dumps(value), encoding='utf-8')
    def run(name, **options):
        result = runner.check(manifest_path, hython, root / name, trusted=True, **options)
        assert runner.read_json(root / name / 'report.json') == result
        return result
    manifest()
    try:runner.check(manifest_path, hython, root / 'untrusted')
    except ValueError as error:assert 'trusted' in str(error)
    else:raise AssertionError('unconfirmed execution accepted')
    assert not (root / 'untrusted').exists()
    success = run('success')
    assert success['ok'], success
    assert success['worker']['status']=='completed' and success['worker']['released']
    assert len(success['result']['checks'])==3 and success['inputs_unchanged']
    assert success['result']['builder']['transaction']['status']=='committed'
    assert script.read_text(encoding='utf-8')==code
    original_report=(root/'success/report.json').read_bytes()
    try:run('success')
    except FileExistsError:pass
    else:raise AssertionError('existing evidence was overwritten')
    assert (root/'success/report.json').read_bytes()==original_report

    manifest([checks[0]])
    again=run('another')
    assert again['ok'] and again['run_id']!=success['run_id']
    assert again['result']['runtime']['runtime_id']!=success['result']['runtime']['runtime_id']
    (root/'dsh_isolated_fixture_support.py').write_text('VALUE=17\n',encoding='utf-8')
    script.write_text(code+'\nimport dsh_isolated_fixture_support\nassert dsh_isolated_fixture_support.VALUE==17\n',encoding='utf-8')
    manifest([checks[0]], files=['dsh_isolated_fixture_support.py'])
    dependency=run('declared-dependency')
    assert dependency['ok'] and len(dependency['inputs'])==2,dependency
    manifest([checks[0]])
    missing_dependency=run('undeclared-dependency')
    assert not missing_dependency['ok'] and 'dsh_isolated_fixture_support' in missing_dependency['error'],missing_dependency
    script.write_text(code,encoding='utf-8')
    manifest([{**checks[0], 'expect':{'points':999}}])
    bad=run('wrong-count')
    assert not bad['ok'] and 'expected=999' in bad['result']['checks'][0]['error'],bad
    manifest([{**checks[0], 'node':'/obj/isolated/MISSING'}])
    assert not run('missing-output')['ok']

    manifest([checks[0]])
    script.write_text("hou.node('/obj').createNode('geo','raw_bypass')", encoding='utf-8')
    bad=run('raw-gate')
    assert not bad['ok'] and bad['result']['builder']['ok'] is False,bad
    assert 'gate' in bad['result']['builder']['error'].lower(),bad
    script.write_text(code + "set_update_mode('manual','auto')", encoding='utf-8')
    bad=run('manual')
    assert not bad['ok'] and 'Manual' in bad['result']['checks'][0]['error'],bad
    script.write_text("g=tab_create('/obj','geo',name='isolated')\nn=tab_create(g,'null',name='OUT')", encoding='utf-8')
    bad=run('empty')
    assert not bad['ok'] and 'empty_output' in bad['result']['checks'][0]['error'],bad

    script.write_text(code, encoding='utf-8')
    cancel=root/'cancel'
    cancel.write_text('cancel', encoding='utf-8')
    stopped=run('cancel-before',cancel_file=cancel)
    assert not stopped['ok'] and stopped['worker']['status']=='cancelled_before_start'
    assert not stopped['worker']['started']
    cancel.unlink()
    script.write_text('import time\ntime.sleep(60)\n' + code.replace('from __future__ import annotations\n',''), encoding='utf-8')
    observed=[]
    def cancel_when_released():
        deadline=time.monotonic()+30
        path=root/'cancel-running/worker-result.json'
        while time.monotonic()<deadline:
            if path.exists() and runner.read_json(path).get('phase')=='builder':
                observed.append(True)
                cancel.write_text('cancel', encoding='utf-8')
                return
            time.sleep(.05)
    thread=threading.Thread(target=cancel_when_released)
    thread.start()
    try:stopped=run('cancel-running',cancel_file=cancel,timeout=40)
    finally:thread.join(timeout=35)
    assert observed and not stopped['ok'] and stopped['worker']['status']=='cancelled',stopped
    assert stopped['worker']['released'] and stopped['result']['phase']=='builder',stopped
    timed=run('deadline',timeout=5)
    assert not timed['ok'] and timed['worker']['status']=='timed_out',timed

    script.write_text(code, encoding='utf-8')
    manifest([checks[1]])
    original_worker=limits.run_gated_worker
    def corrupt_after_exit(*args, **kwargs):
        process=original_worker(*args, **kwargs)
        artifact=root/'corrupt/artifacts/cache/box.bgeo.sc'
        assert process['status']=='completed' and artifact.exists(),process
        artifact.write_bytes(b'corrupted fixture cache')
        return process
    with patch.object(limits,'run_gated_worker',side_effect=corrupt_after_exit):
        bad=run('corrupt')
    assert not bad['ok'] and 'integrity mismatch' in bad['error'],bad
    missing=runner.check(manifest_path,root/'missing-hython.exe',root/'missing-worker',trusted=True)
    assert not missing['ok'] and missing['worker']['phase']=='spawn',missing

assert before == (hou.hipFile.path(), hou.frame(), tuple(n.sessionId() for n in hou.node('/obj').children()))
print('isolated builder/cook/cache/ROP, Raw Gate, Manual, cancellation, integrity and unchanged caller passed on '+hou.applicationVersionString(), flush=True)
