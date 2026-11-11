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


# Requested queries do not touch editing journals or the undo stack. Their
# entry mode is not proof about arbitrary Python effects; captured operation
# facts still flow through the same runtime.
with (patch.object(hou.undos, 'areEnabled', side_effect=AssertionError('query inspected undo')),
      patch.object(dsh_ownership, 'track_created_nodes', side_effect=AssertionError('query prepared creation journal')),
      patch.object(boxes, 'transaction_journal', side_effect=AssertionError('query prepared box journal'))):
    with patch.object(analysis.ast, 'parse', wraps=analysis.ast.parse) as parsed:
        result = bridge.run_code('__result__ = scene_info()["frame"]', read_only=True)
    assert parsed.call_count == 1, parsed.call_count
    assert result['ok'] and result['result'] == float(hou.frame()), result
    assert result['transaction']['status'] == 'effects_unverified', result
    assert result['transaction']['source_executed'] and result['execution']['read_only'], result
    assert result['execution']['impact']['unavailable'], result

    failed = bridge.run_code("describe('/obj/__missing_query_fixture__')", read_only=True)
    assert not failed['ok'] and failed['transaction']['status'] == 'effects_unverified', failed
    assert 'rollback' not in failed, failed

    with patch.object(analysis.ast, 'parse', wraps=analysis.ast.parse) as parsed:
        blocked = bridge.run_code("hou.node('/obj').createNode('geo')", read_only=True)
    assert parsed.call_count == 1, parsed.call_count
    assert not blocked['ok'] and blocked['rawUsage']['gateOutcome'] == 'read_only_blocked', blocked
    assert blocked['transaction']['status'] == 'no_scene_change', blocked
    assert not blocked['transaction']['source_executed'] and not blocked['execution']['impact']['unavailable'], blocked

# Public facade aliases now share request dispatch and access mode. Dynamic
# raw HOM still lies outside that narrow facade guarantee and must retain the
# phase-1 effects-unverified receipt. These are disposable isolated nodes.
with dsh_ownership.execution_owner('effect-observer', 'setup'):
    effect_root = helpers.tab_create('/obj', 'geo', name='receipt_effect_fixture')
    effect_node = helpers.tab_create(effect_root, 'box', name='observed')
try:
    alias_code = ("from dsh_hou_helpers import set_parm as change\n"
                  f"change({effect_node.path()!r}, 'sizex', 4)")
    alias = bridge.run_code(alias_code, owner_session='effect-observer', read_only=True)
    assert not alias['ok'] and effect_node.evalParm('sizex') == 1, alias
    assert alias['transaction']['status'] == 'effects_unverified', alias
    assert alias['execution']['read_only'] and 'Requested' in alias['execution']['read_only_scope'], alias
    assert alias['execution']['impact']['unavailable'] and not alias['execution']['impact']['attempted'], alias
    assert not alias['execution']['impact']['global'] and not alias['execution']['impact']['nodes'], alias
    assert len(alias['verbs']) == 1 and alias['verbs'][0]['verb'] == 'set_parm', alias
    assert alias['verbs'][0]['summary']['phase'] == 'access_mode' and alias['verbs'][0]['summary']['scene_writes'] == 0, alias
    assert 'rollback' not in alias, 'requested inspect did not perform native undo'

    alias_edit = bridge.run_code(alias_code, owner_session='effect-observer')
    assert alias_edit['ok'] and effect_node.evalParm('sizex') == 4, alias_edit
    assert alias_edit['transaction']['status'] == 'committed', alias_edit
    assert [row['verb'] for row in alias_edit['verbs']] == ['set_parm'], alias_edit

    dynamic_code = (f"target = hou.node({effect_node.path()!r}).parm('sizex')\n"
                    "method = 'set'\ngetattr(target, method)(6)")
    dynamic = bridge.run_code(dynamic_code, owner_session='effect-observer', read_only=True)
    assert dynamic['ok'] and effect_node.evalParm('sizex') == 6, dynamic
    assert dynamic['transaction']['status'] == 'effects_unverified', dynamic
    assert dynamic['execution']['impact']['unavailable'] and not dynamic['execution']['impact']['global'], dynamic
    assert dynamic['rawUsage']['scope'].startswith('Static source classification'), dynamic

    dynamic_exec = bridge.run_code(dynamic_code, owner_session='effect-observer')
    assert dynamic_exec['ok'] and effect_node.evalParm('sizex') == 6, dynamic_exec
    assert dynamic_exec['transaction']['status'] == 'effects_unverified', dynamic_exec
    assert not dynamic_exec['execution']['impact']['attempted'] and not dynamic_exec['execution']['impact']['global'], dynamic_exec

    failed_exec = bridge.run_code(dynamic_code.replace('(6)', '(7)') + "\nraise RuntimeError('failed custom edit')",
                                  owner_session='effect-observer')
    assert not failed_exec['ok'], failed_exec
    rollback = failed_exec.get('rollback', {})
    if rollback.get('applied') and not rollback.get('error'):
        assert failed_exec['transaction']['status'] == 'rolled_back' and effect_node.evalParm('sizex') == 6, failed_exec
    else:
        assert failed_exec['transaction']['status'] == 'effects_unverified' and effect_node.evalParm('sizex') == 7, failed_exec
    assert 'not fully observed or restored' in failed_exec['transaction']['scope'], failed_exec

    dynamic_failure = bridge.run_code(dynamic_code + "\nraise RuntimeError('after hidden write')",
                                     owner_session='effect-observer', read_only=True)
    assert not dynamic_failure['ok'] and effect_node.evalParm('sizex') == 6, dynamic_failure
    assert dynamic_failure['transaction']['status'] == 'effects_unverified' and 'rollback' not in dynamic_failure, dynamic_failure

    # Successful arbitrary code is unknown even when there was no real write;
    # the result must not manufacture a global edit to compensate for missing
    # observation. Explicit managed writes keep their actual bounded facts.
    harmless = bridge.run_code("__result__ = 2 + 3", owner_session='effect-observer')
    assert harmless['ok'] and harmless['result'] == 5, harmless
    assert harmless['transaction']['status'] == 'effects_unverified', harmless
    assert harmless['execution']['impact']['unavailable'] and not harmless['execution']['impact']['attempted'], harmless
    managed = bridge.run_code(f"set_parm({effect_node.path()!r}, 'sizex', 8)", owner_session='effect-observer')
    assert managed['ok'] and managed['transaction']['status'] == 'committed', managed
    assert managed['execution']['impact']['attempted'] and managed['execution']['impact']['unavailable'], managed
    assert effect_node.sessionId() in {item['identity'] for item in managed['execution']['impact']['nodes']}, managed

    # The appearance of an exempted method in a dead branch is no evidence of
    # an executed edit. Preserve the static report separately from effects.
    exempted = bridge.run_code("if False:\n    hou.setFrame(90)", allow_raw='static unreachable fixture',
                               owner_session='effect-observer')
    assert exempted['ok'] and exempted['rawUsage']['gateOutcome'] == 'exempted', exempted
    assert exempted['transaction']['status'] == 'effects_unverified', exempted
    assert not exempted['execution']['impact']['attempted'] and not exempted['execution']['impact']['global'], exempted

    syntax = bridge.run_code("if :", owner_session='effect-observer', read_only=True)
    assert not syntax['ok'] and syntax['transaction']['status'] == 'no_scene_change', syntax
    assert not syntax['transaction']['source_executed'] and not syntax['execution']['impact']['unavailable'], syntax
finally:
    effect_root.destroy()

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
