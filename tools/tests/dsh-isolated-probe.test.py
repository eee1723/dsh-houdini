"""API probes and copied snapshots need no artificial SOP/output check."""
import importlib.util
import json
from pathlib import Path
import tempfile
import hou

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('isolated_check', ROOT/'tools/isolated-houdini-check.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
hython = Path(hou.text.expandString('$HFS'))/'bin/hython.exe'

with tempfile.TemporaryDirectory(prefix='dsh-isolated-probe-') as raw:
    root = Path(raw)
    manifest = root/'probe.json'
    script = root/'probe.py'
    data = root/'data.json'
    data.write_text(json.dumps({'marker':'DECLARED_DATA_COPY'}),encoding='utf-8')
    script.write_text('''"""A normal executable script with a declared adjacent dependency."""
from __future__ import annotations
import json
from pathlib import Path
if __name__ == '__main__':
    data = Path(__file__).with_name('data.json')
    __result__ = {
        'version': list(hou.applicationVersion()),
        'ui_available': hou.isUIAvailable(),
        'objects': len(hou.node('/obj').children()),
        'script': str(Path(__file__).resolve()),
        'data_path': str(data.resolve()),
        'payload': json.loads(data.read_text(encoding='utf-8')),
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

print('PASS staged script metadata/dependency, API probe, assertion/Raw Gate failures and snapshot load without output checks '+hou.applicationVersionString())
