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
    active = ExecutorRegistration(directory, uuid.uuid4().hex, installation=ROOT, version='22.0.368')
    try:
        active.publish(18765, uuid.uuid4().hex, hip=directory / 'scene.hip')
        rows = read_candidates(directory, installation=ROOT)
        assert len(rows) == 257
        assert next(row for row in rows if row['executor_id'] == active.executor_id)['state'] == 'registered'
        assert {row['executor_id'] for row in rows if row['state'] == 'disconnected'} == set(retired)
        assert all(row['connection_status'] == 'unverified' for row in rows)
        assert read_candidates(directory, installation=directory / 'other-install') == []

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
print('executor discovery preserves retired evidence and budgets registered targets separately')
