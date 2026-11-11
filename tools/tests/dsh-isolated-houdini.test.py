"""Real bounded worker cook/cache/ROP checks; only authored disposable fixtures."""
import hashlib
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
    assert success['worker']['tree_reaped'] and success['runtime_environment']['cleaned']
    assert not Path(success['runtime_environment']['path']).exists()
    assert not (root/'success/runtime').exists()
    assert len(success['result']['checks'])==3 and success['inputs_unchanged']
    assert success['result']['builder']['transaction']['status']=='committed'
    state=runner.status(root/'success')
    assert state['ok'] and state['finished'] and 'output' not in state['worker'],state
    assert 'output' in success['worker'], 'full worker output belongs to the report'
    assert script.read_text(encoding='utf-8')==code
    original_report=(root/'success/report.json').read_bytes()
    try:run('success')
    except FileExistsError:pass
    else:raise AssertionError('existing evidence was overwritten')
    assert (root/'success/report.json').read_bytes()==original_report

    # Inline builder in a Host-reserved run directory: one call, same evidence
    # contract, and the executed source stays in the run.
    inline_code='g=tab_create("/obj","geo",name="inline")\n__result__={"inline":True}\n'
    manifest_path.write_text(json.dumps({'code':inline_code,'checks':[]}),encoding='utf-8')
    reserved_run=root/'inline-reserved';reserved_run.mkdir()
    inline=runner.check(manifest_path,hython,reserved_run,trusted=True,reserved_output=True)
    assert runner.read_json(reserved_run/'report.json')==inline
    assert inline['ok'],inline
    assert inline['result']['builder']['result']=={'inline':True}
    assert inline['result']['builder']['transaction']['status']=='committed'
    assert inline['inputs_unchanged'] is True and inline['input_observations']==[]
    inline_bytes=inline_code.encode('utf-8')
    assert inline['inline_source']['file']==runner.INLINE_SCRIPT
    assert inline['inline_source']['sha256']==hashlib.sha256(inline_bytes).hexdigest()
    assert inline['inline_source']['bytes']==len(inline_bytes)
    assert inline['inline_source']['scope']
    assert inline['inputs']==[{'file':runner.INLINE_SCRIPT,'sha256':hashlib.sha256(inline_bytes).hexdigest(),
        'bytes':len(inline_bytes),'origin':'inline-code'}]
    assert (reserved_run/'inputs'/runner.INLINE_SCRIPT).read_text(encoding='utf-8')==inline_code
    inline_request=runner.read_json(reserved_run/'request.json')
    assert inline_request['manifest']['script']==runner.INLINE_SCRIPT
    assert 'code' not in inline_request['manifest'], 'the executed manifest never mixes script and inline code'
    assert inline_request['original_manifest']['code']==inline_code
    assert inline_request['original_manifest']=={'code':inline_code,'checks':[]}
    assert inline['result']['runtime']['owner_session'].startswith('isolated-')

    # A developer workspace may be the checkout. Cook/cache evidence can use
    # its new run directory; renderer output keeps its own repository boundary.
    (ROOT/'tools/out').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dsh-isolated-workspace-',dir=ROOT/'tools/out') as workspace:
        manifest(checks[:2])
        workspace_run=runner.check(manifest_path,hython,Path(workspace)/'run',trusted=True)
        assert workspace_run['ok'] and workspace_run['inputs_unchanged'],workspace_run

    manifest([checks[0]])
    again=run('another')
    assert again['ok'] and again['run_id']!=success['run_id']
    assert again['result']['runtime']['runtime_id']!=success['result']['runtime']['runtime_id']

    # USD classification can finish correctly yet crash H22 during native
    # library shutdown. The real production child must exit cleanly without
    # restricting computation or converting a failed builder into success.
    usd_code = code + '''
lop=tab_create('/stage','pythonscript',name='usd_shutdown')
set_parms(lop,{'python': "from pxr import UsdLux,UsdGeom\\ns=hou.pwd().editableStage()\\nUsdLux.DomeLight.Define(s,'/Dome')\\nUsdLux.LightAPI.Apply(UsdGeom.Mesh.Define(s,'/EmissiveMesh').GetPrim())\\ns.DefinePrim('/NotALight','CustomLightishThing')"})
summary=usd_stage_summary(lop)
assert {row['path'] for row in summary['prims']['lights']}=={'/Dome','/EmissiveMesh'}
assert {row['path'] for row in summary['prims']['geometry']}=={'/EmissiveMesh'}
__result__={'lights':summary['counts']['lights'],'compute_threads':hou.maxThreads()}
'''
    script.write_text(usd_code,encoding='utf-8')
    usd=run('usd-native-exit')
    assert usd['ok'] and usd['worker']['returncode']==0 and usd['worker']['tree_reaped'],usd
    usd_builder=runner.read_execution(root/'usd-native-exit',usd['result']['builder'])
    assert usd_builder['result']=={'lights':2,'compute_threads':2},usd_builder
    script.write_text(usd_code+"\nraise RuntimeError('EXPECTED_USD_BUILDER_FAILURE')\n",encoding='utf-8')
    usd_failure=run('usd-native-failure-exit')
    assert not usd_failure['ok'] and usd_failure['worker']['returncode']==1,usd_failure
    assert 'EXPECTED_USD_BUILDER_FAILURE' in usd_failure['error'],usd_failure
    assert usd_failure['inputs_unchanged'] and usd_failure['worker']['tree_reaped'],usd_failure

    (root/'dsh_isolated_fixture_support.py').write_text('VALUE=17\n',encoding='utf-8')
    script.write_text(code+'\nimport dsh_isolated_fixture_support\nassert dsh_isolated_fixture_support.VALUE==17\n',encoding='utf-8')
    manifest([checks[0]], files=['dsh_isolated_fixture_support.py'])
    dependency=run('declared-dependency')
    assert dependency['ok'] and len(dependency['inputs'])==2,dependency
    manifest([checks[0]])
    missing_dependency=run('undeclared-dependency')
    assert not missing_dependency['ok'] and 'dsh_isolated_fixture_support' in missing_dependency['error'],missing_dependency

    # A saved HIP's $HIP-relative texture is lazy renderer input: loading the
    # copied HIP succeeds, but Mantra must not produce a false-green check when
    # that texture was omitted from the manifest. The original stays immutable.
    import base64
    texture_root=root/'textures';texture_root.mkdir()
    texture_source=texture_root/'roughness.png'
    texture_source.write_bytes(base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a+p8AAAAASUVORK5CYII='))
    texture_hip=root/'texture_fixture.hip'
    texture_builder=root/'texture_builder.py'
    texture_builder.write_text('''from __future__ import annotations
g=tab_create('/obj','geo',name='texture_fixture')
n=tab_create(g,'box',name='OUT')
mat=tab_create('/mat','principledshader',name='TEXTURE_FIXTURE_MAT')
set_parms(mat,{'rough_useTexture':1,'rough_texture':'$HIP/textures/roughness.png','rough':1.0})
assigned=tab_create(g,'material',name='ASSIGN',inputs=[n],parms={'shop_materialpath1':mat.path()})
sop_set_output(assigned)
cam=tab_create('/obj','cam',name='TEXTURE_FIXTURE_CAM')
camera_fit(cam,assigned,width=16,height=16)
dry_fit=camera_fit(cam,assigned,width=16,height=16,dry_run=True)
tab_create('/obj','hlight',name='TEXTURE_FIXTURE_LIGHT',parms={'tx':1.0,'ty':1.0,'tz':1.0,'light_intensity':1.0})
for name in ('TEXTURE_ROP_FIRST','TEXTURE_ROP_LATER'):
 tab_create('/out','ifd',name=name,parms={'camera':cam.path(),'vobject':g.path(),
  'vm_renderengine':'pbrraytrace','override_camerares':1,'res_fraction':'specific','res_overridex':16,'res_overridey':16})
saved=scene_save_as(path='''+repr(texture_hip.as_posix())+''',expected_current_path=scene_info()['hip_path'],
 reason='Create authored isolated texture fixture')
__result__={'saved':saved,'dry_fit':dry_fit}
''',encoding='utf-8')
    manifest_path.write_text(json.dumps({'script':'texture_builder.py','checks':[]}),encoding='utf-8')
    fixture=run('texture-fixture')
    assert fixture['ok'] and texture_hip.is_file(),fixture
    assert fixture['result']['builder']['outcome']['checks']['unverified']==1,fixture
    fixture_hash=runner.digest(texture_hip)
    texture_checks=[
        {'id':'first','kind':'render','node':'/out/TEXTURE_ROP_FIRST','frame':1,'file':'first.png'},
        {'id':'later','kind':'render','node':'/out/TEXTURE_ROP_LATER','frame':1,'file':'later.png'},
    ]
    manifest_path.write_text(json.dumps({'hip':'texture_fixture.hip','checks':texture_checks}),encoding='utf-8')
    missing_texture=run('texture-undeclared')
    assert not missing_texture['ok'] and 'Unable to load texture' in missing_texture['error'],missing_texture
    assert missing_texture['result']['phase']=='check:first',missing_texture
    assert len(missing_texture['result']['checks'])==1,missing_texture
    failed_texture=missing_texture['result']['checks'][0]
    assert failed_texture['status']=='failed',failed_texture
    failed_execution=failed_texture['execution']
    assert failed_execution['outcome']['checks']['failed']==1,failed_execution
    assert failed_execution['native_diagnostics'][0]['kind']=='texture_load_failed',failed_execution
    expected_missing=(root/'texture-undeclared/inputs/textures/roughness.png').as_posix()
    assert failed_execution['native_diagnostics'][0]['path']==expected_missing,failed_execution
    assert expected_missing in failed_execution['native_output'],failed_execution
    assert not (root/'texture-undeclared/artifacts/later').exists(),'later render must not execute'
    assert runner.digest(texture_hip)==fixture_hash

    # Builder execution and validation are separate in the Bridge envelope.
    # Even authored code that ignores the returned render result cannot hide a
    # failed native check from the isolated run or continue to manifest checks.
    ignore_script=root/'texture_ignore_result.py'
    ignore_script.write_text('''from pathlib import Path
picture=Path(hou.hipFile.path()).parent.parent/'builder-diagnostic.png'
rendered=render_frame('/out/TEXTURE_ROP_FIRST',picture=str(picture),frame=1)
__result__={'ignored_render_errors':rendered['errors']}
''',encoding='utf-8')
    manifest_path.write_text(json.dumps({'hip':'texture_fixture.hip','script':'texture_ignore_result.py',
        'checks':texture_checks[1:]}),encoding='utf-8')
    ignored_texture=run('texture-builder-failed-check')
    assert not ignored_texture['ok'] and 'Unable to load texture' in ignored_texture['error'],ignored_texture
    assert ignored_texture['result']['phase']=='builder',ignored_texture
    assert ignored_texture['result']['checks']==[],ignored_texture
    assert ignored_texture['result']['builder']['outcome']['checks']['failed']==1,ignored_texture
    assert ignored_texture['result']['builder']['native_diagnostics'],ignored_texture
    assert not (root/'texture-builder-failed-check/artifacts/later').exists()
    assert runner.digest(texture_hip)==fixture_hash

    manifest_path.write_text(json.dumps({'hip':'texture_fixture.hip',
        'files':['textures/roughness.png'],'checks':texture_checks[:1]}),encoding='utf-8')
    declared_texture=run('texture-declared')
    assert declared_texture['ok'],declared_texture
    declared_execution=declared_texture['result']['checks'][0]['execution']
    assert declared_execution['outcome']['checks']['failed']==0,declared_execution
    assert not declared_execution.get('native_diagnostics'),declared_execution
    assert (root/'texture-declared/inputs/textures/roughness.png').is_file()
    assert runner.digest(texture_hip)==fixture_hash

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
                observed.append(runner.status(root/'cancel-running',cancel=True))
                return
            time.sleep(.05)
    thread=threading.Thread(target=cancel_when_released)
    thread.start()
    try:stopped=run('cancel-running',cancel_file=cancel,timeout=40)
    finally:thread.join(timeout=35)
    assert observed and not stopped['ok'] and stopped['worker']['status']=='cancelled',stopped
    assert stopped['worker']['released'] and stopped['result']['phase']=='builder',stopped
    assert stopped['worker']['tree_reaped'] and stopped['runtime_environment']['cleaned'],stopped
    assert observed[0]['cancel_requested'] and not observed[0]['finished'],observed
    assert runner.status(root/'cancel-running')['cancel_requested'] and cancel.exists()
    assert not (root/'cancel-running/cancel.request').exists(), 'custom cancellation path was ignored'
    timed=run('deadline',timeout=5)
    assert not timed['ok'] and timed['worker']['status']=='timed_out',timed
    assert timed['worker']['tree_reaped'] and timed['runtime_environment']['cleaned'],timed

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
