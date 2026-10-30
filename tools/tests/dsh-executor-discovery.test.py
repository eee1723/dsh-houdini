"""Retired executor evidence must not exhaust discovery for current registrations."""
from pathlib import Path
import json
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from dsh_executor_registry import ExecutorRegistration, read_candidates

with tempfile.TemporaryDirectory(prefix='dsh-executor-history-') as raw:
    directory = Path(raw)
    retired = []
    for _ in range(256):
        registration = ExecutorRegistration(directory, uuid.uuid4().hex, installation=ROOT, version='22.0.368')
        registration.publish(18765, uuid.uuid4().hex, hip=directory / 'scene.hip')
        registration.close()
        retired.append(registration.executor_id)
    runtime = {'hfs': str(directory / 'H22'), 'python': str(directory / 'H22/python313/python.exe'),
               'pythonVersion': '3.13.7', 'executable': str(directory / 'H22/bin/houdini.exe')}
    helper = {'id': 'a' * 16, 'version': '0.0.1-fixture'}
    active = ExecutorRegistration(directory, uuid.uuid4().hex, installation=ROOT, version='22.0.368', runtime=runtime, helper=helper)
    try:
        active.publish(18765, uuid.uuid4().hex, hip=directory / 'scene.hip')
        rows = read_candidates(directory, installation=ROOT)
        assert len(rows) == 257
        assert next(row for row in rows if row['executor_id'] == active.executor_id)['state'] == 'registered'
        assert next(row for row in rows if row['executor_id'] == active.executor_id)['runtime'] == runtime
        assert next(row for row in rows if row['executor_id'] == active.executor_id)['helper'] == helper
        assert all('helper' not in row for row in rows if row['executor_id'] in retired), 'older helper records remain readable'
        assert {row['executor_id'] for row in rows if row['state'] == 'disconnected'} == set(retired)
        assert all(row['connection_status'] == 'unverified' for row in rows)
        assert read_candidates(directory, installation=directory / 'other-install') == []
        active_file = directory / 'endpoints' / (active.executor_id + '.json')
        saved_active = active_file.read_text(encoding='utf8')
        active_file.write_text(json.dumps({**json.loads(saved_active), 'helper': {'id': 123, 'version': []}}), encoding='utf8')
        incomplete = next(row for row in read_candidates(directory, installation=ROOT) if row['executor_id'] == active.executor_id)
        assert incomplete['helper'] == {'id': None, 'version': None}, 'update metadata must not block executor discovery'
        active_file.write_text(json.dumps({**json.loads(saved_active), 'runtime': {**runtime, 'python': 'python.exe'}}), encoding='utf8')
        try:
            read_candidates(directory, installation=ROOT)
        except ValueError as error:
            assert 'invalid Houdini installation runtime' in str(error)
        else:
            raise AssertionError('Invalid relative interpreter was silently accepted')
        active_file.write_text(saved_active, encoding='utf8')

        # Retaining history does not relax record validation or active capacity.
        record_file = directory / 'endpoints' / (retired[0] + '.json')
        saved = record_file.read_text(encoding='utf8')
        record_file.write_text('{}', encoding='utf8')
        try:
            read_candidates(directory, installation=ROOT)
        except ValueError as error:
            assert 'invalid executor record' in str(error)
        else:
            raise AssertionError('Malformed history was silently accepted')
        record_file.write_text(saved, encoding='utf8')
        for ident in retired:
            filename = directory / 'endpoints' / (ident + '.json')
            value = json.loads(filename.read_text(encoding='utf8'))
            filename.write_text(json.dumps({**value, 'state': 'registered'}), encoding='utf8')
        try:
            read_candidates(directory, installation=ROOT)
        except ValueError as error:
            assert '256 registered records' in str(error)
        else:
            raise AssertionError('Active discovery capacity was not enforced')
    finally:
        active.close()
    # The menu's publication path carries the owning-thread Bridge snapshot;
    # it must not infer the loaded helper from the newly selected Package.
    from dsh_shared_executor import publish_registration
    from dsh_executor_registry import active_registration
    hip = directory / 'published.hip'
    hip.write_bytes(b'fixture-only')
    published = publish_registration(directory / 'menu-registry', {
        'hip': str(hip), 'version': '22.0.368', 'executor_id': uuid.uuid4().hex,
        'runtime_id': uuid.uuid4().hex, 'port': 18765, 'installation': str(ROOT),
        'runtime': runtime, 'helper': helper,
    })
    try:
        assert published['helper'] == helper
        assert read_candidates(directory / 'menu-registry', installation=ROOT)[0]['helper'] == helper
    finally:
        active_registration().close()
print('executor discovery preserves retired evidence and budgets registered targets separately')
