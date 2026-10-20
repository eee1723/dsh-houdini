"""Focused checks for shared analysis and queries that never prepare edits."""

from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import tokenize
from types import ModuleType
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import dsh_ownership

import hou
import dsh_bridge as bridge
import dsh_code_analysis as analysis
import dsh_execution as execution
import dsh_hou_helpers as helpers
import dsh_media_output
import dsh_component_contracts
import dsh_network_boxes as boxes


# Queries, including failed queries, do not touch editing journals or the undo
# stack. Their ordinary ledger/result facts still flow through the same runtime.
with (patch.object(hou.undos, 'areEnabled', side_effect=AssertionError('query inspected undo')),
      patch.object(dsh_ownership, 'track_created_nodes', side_effect=AssertionError('query prepared creation journal')),
      patch.object(boxes, 'transaction_journal', side_effect=AssertionError('query prepared box journal'))):
    with patch.object(analysis.ast, 'parse', wraps=analysis.ast.parse) as parsed:
        result = bridge.run_code('__result__ = scene_info()["frame"]', read_only=True)
    assert parsed.call_count == 1, parsed.call_count
    assert result['ok'] and result['result'] == float(hou.frame()), result
    assert result['transaction']['status'] == 'no_scene_change', result

    failed = bridge.run_code("describe('/obj/__missing_query_fixture__')", read_only=True)
    assert not failed['ok'] and failed['transaction']['status'] == 'no_scene_change', failed
    assert 'rollback' not in failed, failed

    with patch.object(analysis.ast, 'parse', wraps=analysis.ast.parse) as parsed:
        blocked = bridge.run_code("hou.node('/obj').createNode('geo')", read_only=True)
    assert parsed.call_count == 1, parsed.call_count
    assert not blocked['ok'] and blocked['rawUsage']['gateOutcome'] == 'read_only_blocked', blocked
    assert blocked['transaction']['status'] == 'no_scene_change', blocked

# A warm vocabulary does not re-inspect all signatures on each request. When a
# callable changes, its actual new signature is used for both dispatch and help.
execution._VERB_SIGNATURES.clear()
with patch.object(execution.inspect, 'signature', wraps=execution.inspect.signature) as inspected:
    warm = bridge.run_code('__result__ = verb_help("scene_info")', read_only=True)
    assert warm['ok'], warm
    first_count = inspected.call_count
    repeat = bridge.run_code('__result__ = verb_help("scene_info")', read_only=True)
    assert repeat['ok'] and inspected.call_count == first_count, repeat

    original = execution._VERBS['scene_info']
    try:
        execution._VERBS['scene_info'] = lambda marker: marker
        rejected = bridge.run_code('scene_info()', read_only=True)
        assert not rejected['ok'] and rejected['evidence'][0]['phase'] == 'argument_binding', rejected
        assert inspected.call_count == first_count + 1, inspected.call_count
        info = bridge._verb_help('scene_info')
        assert info['signature'] == '(marker)', info
    finally:
        execution._VERBS['scene_info'] = original

# Nested image scopes survive failure and never leak into the next request.
with dsh_media_output.image_scope() as outer_images:
    helpers.report_image('outer.png')
    try:
        with dsh_media_output.image_scope() as inner_images:
            helpers.report_image('inner.png')
            raise RuntimeError('injected media failure')
    except RuntimeError:
        pass
    helpers.report_image('after.png')
    assert [__import__('os').path.basename(p) for p in outer_images] == ['outer.png','after.png']
    assert [__import__('os').path.basename(p) for p in inner_images] == ['inner.png']
with dsh_media_output.image_scope() as next_images:
    assert next_images == []

# Component rollback owns a deep snapshot, including nested contract metadata.
baseline = dsh_component_contracts.snapshot_imports()
try:
    dsh_component_contracts.restore_imports({'fixture': {'nested': {'hash': 'original'}}})
    captured = dsh_component_contracts.snapshot_imports()
    captured['fixture']['nested']['hash'] = 'detached'
    assert dsh_component_contracts.snapshot_imports()['fixture']['nested']['hash'] == 'original'
    dsh_component_contracts.restore_imports(captured)
    captured['fixture']['nested']['hash'] = 'changed after restore'
    assert dsh_component_contracts.snapshot_imports()['fixture']['nested']['hash'] == 'detached'
finally:
    dsh_component_contracts.restore_imports(baseline)

# A file source and its invocation share one AST, owner, ledger and transaction.
# The Bridge hashes transmitted bytes, never re-reads the named file on the GUI.
script_fixture = Path(os.environ['DSH_SCRIPT_FIXTURE_OUT']) if os.environ.get('DSH_SCRIPT_FIXTURE_OUT') else None
builder_path = script_fixture.with_suffix('.py') if script_fixture else Path(__file__).resolve().with_name('authored_builder.py')
def source_record(source, entry=None):
    record = {'path': str(builder_path.resolve()),
              'sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
              'bytes': len(source.encode('utf-8'))}
    if entry is not None:
        record['entry'] = entry
    return record

source = '''\ufefffrom __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar
@dataclass
class Dimensions:
    label: ClassVar[str] = 'module annotation resolved'
    width: float = 2.0
def build(parent):
    g = tab_create(parent, 'geo', name='source_runtime_fixture')
    n = tab_create(g, 'box', name='OUT', parms={'sizex': Dimensions().width})
    return g, n
if __name__ == '__main__':
    raise AssertionError('invocation must not run the standalone test body')
'''
entry = "g,n=build('/obj')\n__result__={'file':__file__,'name':__name__,'width':n.geometry().boundingBox().sizevec()[0]}"
record = source_record(source, entry)
prior_module = ModuleType('__dsh_builder__')
previous = sys.modules.get('__dsh_builder__')
sys.modules['__dsh_builder__'] = prior_module
try:
    result = bridge.run_code(source, owner_session='source-author', owner_call='source-call', script=record)
    assert result['ok'] and result['result']['width'] == 2.0, result
    assert result['script'] == record and result['result']['file'] == record['path'], result
    assert result['result']['name'] == '__dsh_builder__', result
    assert result['execution']['owner_session'] == 'source-author', result
    assert [v['verb'] for v in result['verbs']] == ['tab_create','tab_create'], result
    assert sys.modules['__dsh_builder__'] is prior_module
    if script_fixture is not None:
        script_fixture.parent.mkdir(parents=True, exist_ok=True)
        builder_path.write_bytes(source.encode('utf-8'))
        script_fixture.write_text(json.dumps({'source': source, 'record': record, 'receipt': result},
                                             ensure_ascii=False), encoding='utf-8')
    foreign = bridge.run_code("set_parms('/obj/source_runtime_fixture/OUT',{'sizex':3})",
                              owner_session='another-author')
    assert not foreign['ok'], foreign
    assert bridge.run_code("delete_node('/obj/source_runtime_fixture')", owner_session='source-author')['ok']
    query = bridge.run_code(source, owner_session='source-author', read_only=True, script=record)
    assert not query['ok'] and query['rawUsage']['gateOutcome'] == 'read_only_blocked', query
    assert hou.node('/obj/source_runtime_fixture') is None

    standalone = "__result__={'file':__file__,'name':__name__}"
    original_main = sys.modules['__main__']
    completed = bridge.run_code(standalone, script=source_record(standalone))
    assert completed['ok'] and completed['result']['name'] == '__main__', completed
    assert sys.modules['__main__'] is original_main
    with patch.dict(bridge._jobs, {'0f0f0f0f0f0f': {'status': 'queued'}}):
        queued = bridge._job_body('0f0f0f0f0f0f', standalone, owner_session='source-author',
                                  owner_call='source-job', script=source_record(standalone))
        assert queued['ok'] and queued['script'] == source_record(standalone), queued
        assert queued['execution']['owner_session'] == 'source-author', queued
        assert sys.modules['__main__'] is original_main

    # Full-source analysis includes cross-boundary aliases in the invocation.
    raw_source = "make=hou.node('/obj').createNode"
    refused = bridge.run_code(raw_source, allow_raw='cannot exempt a covered builder write',
                              script=source_record(raw_source, "make('geo','hidden_source_write')"))
    assert not refused['ok'] and 'allow_raw cannot exempt' in refused['error'], refused
    assert hou.node('/obj/hidden_source_write') is None
    assert refused['script']['sha256'] == source_record(raw_source)['sha256']
    assert sys.modules['__dsh_builder__'] is prior_module

    for broken, tail in (("text = '''", "'''\n__result__=True"),
                         ('value = 1 + \\', '2\n__result__=True')):
        failed = bridge.run_code(broken, script=source_record(broken, tail))
        assert not failed['ok'] and 'SyntaxError' in failed['error'], failed
    before_sequence = bridge._runtime.sequence
    tampered = bridge.run_code(standalone+'\n# changed', script=source_record(standalone))
    assert not tampered['ok'] and tampered['transaction']['status'] == 'no_scene_change', tampered
    assert bridge._runtime.sequence == before_sequence, 'invalid source must not enter execution'
    assert sys.modules['__dsh_builder__'] is prior_module
    with tempfile.TemporaryDirectory(prefix='dsh-frozen-source-') as raw:
        filename = Path(raw)/'mutable.py'
        filename.write_text("raise RuntimeError('LATER FILE CONTENT')", encoding='utf-8')
        frozen = "raise RuntimeError('original frozen source')"
        frozen_record = {**source_record(frozen), 'path': str(filename)}
        native_open = tokenize.open
        def diagnostic_open(target):
            assert str(target) != str(filename), 'traceback reopened the Host-read source path'
            return native_open(target)
        with patch.object(tokenize, 'open', side_effect=diagnostic_open):
            failure = bridge.run_code(frozen, script=frozen_record)
        assert not failure['ok'] and 'original frozen source' in failure['error'], failure
        assert 'LATER FILE CONTENT' not in failure['error'], failure
        assert failure['script'] == frozen_record
finally:
    if previous is None:
        sys.modules.pop('__dsh_builder__', None)
    else:
        sys.modules['__dsh_builder__'] = previous

print('single analysis / query isolation / callable signature cache / nested media / detached component rollback passed on ' + hou.applicationVersionString())
