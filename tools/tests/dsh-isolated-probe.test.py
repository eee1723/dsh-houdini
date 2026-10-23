"""API probes and copied snapshots need no artificial SOP/output check."""
import importlib.util
import json
import sys
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import patch
import hou

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
spec = importlib.util.spec_from_file_location('isolated_check', ROOT/'tools/isolated-houdini-check.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
import dsh_worker_limits as limits
hython = Path(hou.text.expandString('$HFS'))/'bin/hython.exe'

with tempfile.TemporaryDirectory(prefix='dsh-isolated-probe-') as raw:
    root = Path(raw).resolve()
    manifest = root/'probe.json'
    script = root/'probe.py'
    data = root/'data.json'
    data.write_text(json.dumps({'marker':'DECLARED_DATA_COPY'}),encoding='utf-8')
    script.write_text('''"""A normal executable script with a declared adjacent dependency."""
from __future__ import annotations
from dataclasses import dataclass, fields
from typing import ClassVar
import json
from pathlib import Path
@dataclass
class ProbeSettings:
    labels: ClassVar[list[str]] = []
    width: float = 2.0
if __name__ == '__main__':
    data = Path(__file__).with_name('data.json')
    __result__ = {
        'version': list(hou.applicationVersion()),
        'ui_available': hou.isUIAvailable(),
        'objects': len(hou.node('/obj').children()),
        'script': str(Path(__file__).resolve()),
        'data_path': str(data.resolve()),
        'payload': json.loads(data.read_text(encoding='utf-8')),
        'dataclass_width': ProbeSettings().width,
        'dataclass_fields': [field.name for field in fields(ProbeSettings)],
        'module_name': __name__,
    }
    assert not __result__['ui_available'], 'probe must use a headless process'
    assert __result__['objects'] == 0, 'probe must start with an empty scene'
    assert __result__['payload']['marker'] == 'DECLARED_DATA_COPY'
    print('ISOLATED_API_PROBE_COMPLETED')
''', encoding='utf-8')
    original = {file:runner.digest(file) for file in (script,data)}
    manifest.write_text(json.dumps({'script':'probe.py','files':['data.json']}), encoding='utf-8')
    success = runner.check(manifest,hython,root/'success',trusted=True)
    assert success['ok'] and success['finished'] and success['inputs_unchanged'],success
    assert success['result']['checks'] == []
    builder = success['result']['builder']
    assert builder['ok'] and builder['result']['ui_available'] is False
    assert builder['result']['version'] == list(hou.applicationVersion())
    assert builder['result']['objects'] == 0
    assert Path(builder['result']['script']) == root/'success/inputs/probe.py'
    assert Path(builder['result']['data_path']) == root/'success/inputs/data.json'
    assert builder['result']['payload'] == {'marker':'DECLARED_DATA_COPY'}
    assert builder['result']['dataclass_width']==2.0 and builder['result']['dataclass_fields']==['width']
    assert builder['result']['module_name']=='__main__'
    assert builder['script']['path']==str((root/'success/inputs/probe.py').resolve())
    assert builder['script']['sha256']==original[script] and builder['script']['bytes']==script.stat().st_size
    assert len(success['inputs']) == 2
    assert all(runner.digest(file)==digest for file,digest in original.items())
    assert 'ISOLATED_API_PROBE_COMPLETED' in builder['stdout']
    assert not (root/'success/artifacts').exists(), 'read-only API probes need no artifact'

    script.write_text("from __future__ import annotations\nif __name__ == '__main__':\n    assert hou.isUIAvailable(), 'ISOLATED_EXPECTED_ASSERTION_FAILURE'\n", encoding='utf-8')
    manifest.write_text(json.dumps({'script':'probe.py','checks':[]}), encoding='utf-8')
    failure = runner.check(manifest,hython,root/'failure',trusted=True)
    assert not failure['ok'] and failure['finished'],failure
    assert failure['result']['checks'] == [] and failure['result']['builder']['ok'] is False
    assert 'ISOLATED_EXPECTED_ASSERTION_FAILURE' in failure['error'],failure
    assert 'ISOLATED_EXPECTED_ASSERTION_FAILURE' in failure['result']['builder']['error']

    script.write_text("from __future__ import annotations\nif __name__ == '__main__':\n    hou.node('/obj').createNode('geo','raw_bypass')\n",encoding='utf-8')
    blocked = runner.check(manifest,hython,root/'raw-gate',trusted=True)
    assert not blocked['ok'] and blocked['result']['builder']['ok'] is False,blocked
    assert 'raw-hou gate' in blocked['result']['builder']['error'].lower(),blocked

    # This test owns its fresh parent process; only this authored saved file is copied.
    snapshot = root/'saved.hip'
    hou.hipFile.save(str(snapshot))
    before = runner.digest(snapshot)
    manifest.write_text(json.dumps({'hip':'saved.hip'}), encoding='utf-8')
    loaded = runner.check(manifest,hython,root/'snapshot',trusted=True)
    assert loaded['ok'] and loaded['finished'] and loaded['inputs_unchanged'],loaded
    assert loaded['result']['checks'] == []
    assert loaded['result']['builder']['result'] == {'snapshot_loaded':True}
    assert loaded['result']['snapshot']['sha256'] == before == runner.digest(snapshot)
    assert 'Without checks, success proves only builder execution or snapshot loading.' in loaded['scope']

    # A saved HIP plus a setup script is one disposable owner scope. The script
    # can tune loaded nodes through verbs; it still cannot raw-load another HIP.
    source=hou.node('/obj').createNode('geo','snapshot_source')
    source_shape=source.createNode('box','shape')
    source_shape.parm('sizex').set(1.0)
    hou.hipFile.save(str(snapshot))
    snapshot_hash=runner.digest(snapshot)
    scripts=root/'scripts';scripts.mkdir()
    setup=scripts/'setup.py'
    setup.write_text("set_parms('/obj/snapshot_source/shape',{'sizex':2.0})\n"
                     "__result__={'width':hou.node('/obj/snapshot_source/shape').parm('sizex').eval(),"
                     "'owner':node_provenance('/obj/snapshot_source/shape')}\n",encoding='utf-8')
    setup_hash=runner.digest(setup)
    combined=scripts/'snapshot-check.json'
    combined.write_text(json.dumps({'input_root':'..','hip':'saved.hip','script':'scripts/setup.py',
                                   'checks':[{'id':'shape','kind':'cook','node':'/obj/snapshot_source/shape','frame':1}]}),encoding='utf-8')
    tuned=runner.check(combined,hython,root/'snapshot-setup',trusted=True)
    assert tuned['ok'] and tuned['inputs_unchanged'],tuned
    assert tuned['result']['builder']['result']['width']==2.0
    assert tuned['result']['snapshot']['sha256']==snapshot_hash
    assert runner.digest(snapshot)==snapshot_hash and runner.digest(setup)==setup_hash
    assert runner.digest(root/'snapshot-setup/inputs/saved.hip')==snapshot_hash
    assert tuned['result']['runtime']['runtime_id']==tuned['result']['builder']['execution']['runtime_id']
    assert tuned['runtime_environment']['cleaned'] and not (root/'snapshot-setup/runtime').exists()
    # The source process and saved file are unchanged by setup in the worker.
    assert source_shape.parm('sizex').eval()==1.0

    # An explicitly authorized save can replace this test's own original input
    # after the worker has copied and loaded its initial version. That external
    # file effect is observed separately from successful execution/checks.
    setup.write_text("set_parms('/obj/snapshot_source/shape',{'sizex':3.0})\n"
        + "saved=scene_save_as("+repr(str(snapshot))+",expected_current_path=scene_info()['hip_path'],"
          "overwrite=True,reason='Test authorization to replace this authored source HIP with the tuned result')\n"
        + "__result__={'saved':saved,'width':hou.node('/obj/snapshot_source/shape').evalParm('sizex')}\n",encoding='utf-8')
    replaced=runner.check(combined,hython,root/'authorized-source-save',trusted=True)
    assert replaced['ok'] and replaced['inputs_unchanged'] is False,replaced
    changed=next(row for row in replaced['input_observations'] if row['file']=='saved.hip')
    assert changed['status']=='changed' and changed['before_sha256']==snapshot_hash
    assert changed['after_sha256']==runner.digest(snapshot)!=snapshot_hash
    assert replaced['result']['snapshot']['sha256']==snapshot_hash
    assert runner.digest(root/'authorized-source-save/inputs/saved.hip')==snapshot_hash
    assert replaced['result']['builder']['result']['width']==3.0
    assert not replaced.get('error')

    setup.write_text("set_parms('/obj/snapshot_source/shape',{'sizex':4.0})\n"
        + "scene_save_as("+repr(str(snapshot))+",expected_current_path=scene_info()['hip_path'],"
          "overwrite=True,reason='Test authorization to save this authored source before an intentional script failure')\n"
        + "raise RuntimeError('SOURCE_SAVE_THEN_EXPECTED_FAILURE')\n",encoding='utf-8')
    failed_save=runner.check(combined,hython,root/'failed-after-source-save',trusted=True)
    assert not failed_save['ok'] and failed_save['inputs_unchanged'] is False,failed_save
    assert 'SOURCE_SAVE_THEN_EXPECTED_FAILURE' in failed_save['error']
    assert next(row for row in failed_save['input_observations'] if row['file']=='saved.hip')['status']=='changed'

    # Concurrent edits/deletion of an original dependency do not change the
    # verified copied bytes consumed by this worker. Deletion is unavailable
    # evidence, not a false assertion that a new version was read.
    for mutation in ('edit','delete'):
        data.write_text('initial source data',encoding='utf-8')
        ready=root/('ready-'+mutation);release=root/('release-'+mutation)
        script.write_text("from pathlib import Path\nimport time\n"
            + "copied=Path(__file__).with_name('data.json').read_text(encoding='utf-8')\n"
            + "Path("+repr(str(ready))+").write_text('ready',encoding='utf-8')\n"
            + "deadline=time.monotonic()+10\nwhile not Path("+repr(str(release))+").exists():\n"
              "    if time.monotonic()>deadline:raise RuntimeError('source mutation test timed out')\n    time.sleep(.01)\n"
            + "assert Path(__file__).with_name('data.json').read_text(encoding='utf-8')==copied\n__result__={'copied':copied}\n",encoding='utf-8')
        manifest.write_text(json.dumps({'script':'probe.py','files':['data.json']}),encoding='utf-8')
        mutation_errors=[]
        def mutate_source():
            try:
                deadline=time.monotonic()+30
                while not ready.exists():
                    if time.monotonic()>deadline:raise RuntimeError('worker did not reach source mutation barrier')
                    time.sleep(.01)
                if mutation=='edit':data.write_text('new source data',encoding='utf-8')
                else:data.unlink()
                release.write_text('continue',encoding='utf-8')
            except Exception as error:mutation_errors.append(str(error))
        thread=threading.Thread(target=mutate_source);thread.start()
        try:concurrent=runner.check(manifest,hython,root/('concurrent-'+mutation),trusted=True,timeout=45)
        finally:thread.join(timeout=35)
        assert not thread.is_alive() and not mutation_errors,mutation_errors
        assert concurrent['ok'] and concurrent['result']['builder']['result']['copied']=='initial source data',concurrent
        observed=next(row for row in concurrent['input_observations'] if row['file']=='data.json')
        assert observed['status']==('changed' if mutation=='edit' else 'unavailable'),observed
        assert concurrent['inputs_unchanged'] is (False if mutation=='edit' else None)

    # The worker's pre-load digest guard still catches a changed copied script
    # after staging and before any authored code is executed.
    script.write_text("raise RuntimeError('CORRUPTED_SCRIPT_MUST_NOT_EXECUTE')\n",encoding='utf-8')
    manifest.write_text(json.dumps({'script':'probe.py'}),encoding='utf-8')
    gated_worker=limits.run_gated_worker
    def corrupt_staged_script(command,**kwargs):
        request_path=Path(command[-1])
        (request_path.parent/'inputs/probe.py').write_text("raise RuntimeError('changed copied code')\n",encoding='utf-8')
        return gated_worker(command,**kwargs)
    with patch.object(limits,'run_gated_worker',side_effect=corrupt_staged_script):
        corrupt=runner.check(manifest,hython,root/'copied-script-corruption',trusted=True)
    assert not corrupt['ok'] and 'staged input digest mismatch' in corrupt['error'],corrupt
    assert corrupt['inputs_unchanged'] is True

    setup.write_text("hou.hipFile.load('not-authorized.hip')\n",encoding='utf-8')
    blocked_setup=runner.check(combined,hython,root/'snapshot-raw-load',trusted=True)
    assert not blocked_setup['ok'] and 'forbidden' in blocked_setup['error'].lower(),blocked_setup

print('PASS staged inputs, API probes, failures, snapshot load/setup and unchanged sources '+hou.applicationVersionString())
