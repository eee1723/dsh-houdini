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
    assert result['transaction']['status'] == 'no_scene_change', result
    assert result['transaction']['effects'] == 'none' and result['transaction']['native_evaluation'] is False, result
    assert result['transaction']['source_executed'] and result['execution']['read_only'], result
    assert not result['execution']['impact']['unavailable'], result

    # Standard-library method names such as compile are not dynamic HOM access.
    # Use the same callable provenance as Raw Gate instead of a second name list.
    standard_library = bridge.run_code(
        "import re\npattern = re.compile('box')\n__result__ = {'frame': scene_info()['frame'], 'matches': pattern.findall('box box')}",
        read_only=True)
    assert standard_library['ok'] and standard_library['result']['matches'] == ['box', 'box'], standard_library
    assert standard_library['transaction']['status'] == 'no_scene_change', standard_library
    assert not standard_library['execution']['impact']['unavailable'], standard_library

    failed = bridge.run_code("describe('/obj/__missing_query_fixture__')", read_only=True)
    assert not failed['ok'] and failed['transaction']['status'] == 'effects_unverified', failed
    assert failed['transaction']['effects'] == 'none' and failed['transaction']['native_evaluation'] is True, failed
    assert 'rollback' not in failed, failed

    with patch.object(analysis.ast, 'parse', wraps=analysis.ast.parse) as parsed:
        blocked = bridge.run_code("hou.node('/obj').createNode('geo')", read_only=True)
    assert parsed.call_count == 1, parsed.call_count
    assert not blocked['ok'] and blocked['rawUsage']['gateOutcome'] == 'read_only_blocked', blocked
    assert blocked['transaction']['status'] == 'no_scene_change', blocked
    assert blocked['transaction']['effects'] == 'none' and blocked['transaction']['native_evaluation'] is False, blocked
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
    assert alias['transaction']['status'] == 'no_scene_change', alias
    assert alias['transaction']['effects'] == 'none' and alias['transaction']['native_evaluation'] is False, alias
    assert alias['execution']['read_only'] and 'Requested' in alias['execution']['read_only_scope'], alias
    assert not alias['execution']['impact']['unavailable'] and not alias['execution']['impact']['attempted'], alias
    assert not alias['execution']['impact']['global'] and not alias['execution']['impact']['nodes'], alias
    assert len(alias['verbs']) == 1 and alias['verbs'][0]['verb'] == 'set_parm', alias
    assert alias['verbs'][0]['summary']['phase'] == 'access_mode' and alias['verbs'][0]['summary']['scene_writes'] == 0, alias
    assert 'rollback' not in alias, 'requested inspect did not perform native undo'

    alias_edit = bridge.run_code(alias_code, owner_session='effect-observer')
    assert alias_edit['ok'] and effect_node.evalParm('sizex') == 4, alias_edit
    assert alias_edit['transaction']['status'] == 'committed', alias_edit
    assert alias_edit['transaction']['effects'] == 'registered', alias_edit
    assert not alias_edit['execution']['impact']['unavailable'], alias_edit
    assert [row['verb'] for row in alias_edit['verbs']] == ['set_parm'], alias_edit

    dynamic_code = (f"target = hou.node({effect_node.path()!r}).parm('sizex')\n"
                    "method = 'set'\ngetattr(target, method)(6)")
    dynamic = bridge.run_code(dynamic_code, owner_session='effect-observer', read_only=True)
    assert dynamic['ok'] and effect_node.evalParm('sizex') == 6, dynamic
    assert dynamic['transaction']['status'] == 'effects_unverified', dynamic
    assert dynamic['transaction']['effects'] == 'none' and dynamic['transaction']['native_evaluation'] is False, dynamic
    assert dynamic['execution']['impact']['unavailable'], dynamic
    assert 'not a no-write guarantee' in dynamic['execution']['read_only_scope'], dynamic
    assert dynamic['rawUsage']['scope'].startswith('Static source classification'), dynamic

    dynamic_exec = bridge.run_code(dynamic_code, owner_session='effect-observer')
    assert dynamic_exec['ok'] and effect_node.evalParm('sizex') == 6, dynamic_exec
    assert dynamic_exec['transaction']['status'] == 'effects_unverified', dynamic_exec
    assert dynamic_exec['execution']['impact']['unavailable'], dynamic_exec
    assert not dynamic_exec['execution']['impact']['attempted'] and not dynamic_exec['execution']['impact']['global'], dynamic_exec

    failed_exec = bridge.run_code(dynamic_code.replace('(6)', '(7)') + "\nraise RuntimeError('failed custom edit')",
                                  owner_session='effect-observer')
    assert not failed_exec['ok'], failed_exec
    rollback = failed_exec.get('rollback', {})
    if rollback.get('applied') and not rollback.get('error'):
        assert failed_exec['transaction']['status'] == 'rolled_back' and effect_node.evalParm('sizex') == 6, failed_exec
        assert failed_exec['transaction']['effects'] == 'none', failed_exec
    else:
        assert failed_exec['transaction']['status'] == 'effects_unverified' and effect_node.evalParm('sizex') == 7, failed_exec
    assert 'outside this record' in failed_exec['transaction']['scope'], failed_exec

    dynamic_failure = bridge.run_code(dynamic_code + "\nraise RuntimeError('after hidden write')",
                                     owner_session='effect-observer', read_only=True)
    assert not dynamic_failure['ok'] and effect_node.evalParm('sizex') == 6, dynamic_failure
    assert dynamic_failure['transaction']['status'] == 'effects_unverified' and 'rollback' not in dynamic_failure, dynamic_failure

    # No instrumented evidence is not a zero-write proof: arbitrary Python can
    # reach HOM through imports/helpers without a literal hou.* token, so an
    # executed batch with an empty verb ledger keeps the conservative receipt.
    harmless = bridge.run_code("__result__ = 2 + 3", owner_session='effect-observer')
    assert harmless['ok'] and harmless['result'] == 5, harmless
    assert harmless['transaction']['status'] == 'effects_unverified', harmless
    assert harmless['transaction']['effects'] == 'none', harmless
    assert harmless['execution']['impact']['unavailable'] and not harmless['execution']['impact']['attempted'], harmless
    managed = bridge.run_code(f"set_parm({effect_node.path()!r}, 'sizex', 8)", owner_session='effect-observer')
    assert managed['ok'] and managed['transaction']['status'] == 'committed', managed
    assert managed['transaction']['effects'] == 'registered', managed
    assert managed['execution']['impact']['attempted'] and not managed['execution']['impact']['unavailable'], managed
    assert effect_node.sessionId() in {item['identity'] for item in managed['execution']['impact']['nodes']}, managed

    no_later_write = bridge.run_code(
        f"set_parm({effect_node.path()!r}, 'sizex', 9)\n"
        "mode = scene_info()['update_mode']\nset_update_mode(mode, expected_mode=mode)",
        owner_session='effect-observer')
    assert no_later_write['ok'] and no_later_write['transaction']['effects'] == 'registered', no_later_write
    assert no_later_write['verbs'][-1]['summary']['changed'] is False, no_later_write
    assert no_later_write['execution']['impact']['last_edit_ledger_index'] == 1, no_later_write

    # A cook/observation verb exercises Houdini without an instrumented scene
    # write; it is a managed operation (its facts are in the verb result), not a
    # metadata-read native evaluation.
    cook_only = bridge.run_code(f"cook_node({effect_node.path()!r})", owner_session='effect-observer')
    assert cook_only['ok'] and cook_only['transaction']['status'] == 'no_scene_change', cook_only
    assert cook_only['transaction']['effects'] == 'none' and cook_only['transaction']['native_evaluation'] is False, cook_only
    assert not cook_only['execution']['impact']['unavailable'], cook_only

    # The appearance of an exempted method in a dead branch is no evidence of
    # an executed edit. Preserve the static report separately from effects.
    exempted = bridge.run_code("if False:\n    hou.setFrame(90)", allow_raw='static unreachable fixture',
                               owner_session='effect-observer')
    assert exempted['ok'] and exempted['rawUsage']['gateOutcome'] == 'exempted', exempted
    assert exempted['transaction']['status'] == 'effects_unverified', exempted
    assert exempted['transaction']['effects'] == 'none' and exempted['execution']['impact']['unavailable'], exempted
    assert not exempted['execution']['impact']['attempted'] and not exempted['execution']['impact']['global'], exempted

    syntax = bridge.run_code("if :", owner_session='effect-observer', read_only=True)
    assert not syntax['ok'] and syntax['transaction']['status'] == 'no_scene_change', syntax
    assert syntax['transaction']['effects'] == 'none' and syntax['transaction']['native_evaluation'] is False, syntax
    assert not syntax['transaction']['source_executed'] and not syntax['execution']['impact']['unavailable'], syntax

    # A helper module can create a real node without any literal hou.* token and
    # without a traced verb. The empty ledger must not turn that write into a
    # no_scene_change claim.
    hidden_name = 'hidden_helper_write_fixture'
    with tempfile.TemporaryDirectory(prefix='dsh-hidden-helper-') as directory:
        Path(directory, 'hidden_helper.py').write_text(
            'import hou\n'
            'def build(parent, name):\n'
            '    return hou.node(parent).createNode("geo", node_name=name)\n',
            encoding='utf-8')
        hidden = bridge.run_code(
            f'import sys\nsys.path.insert(0, {directory!r})\nimport hidden_helper\n'
            f'hidden_helper.build("/obj", {hidden_name!r})',
            owner_session='effect-observer')
        try:
            assert hidden['ok'], hidden
            assert hou.node('/obj/' + hidden_name) is not None, 'the fixture write really created a node'
            assert hidden['transaction']['status'] == 'effects_unverified', hidden
            assert hidden['transaction']['effects'] == 'none', hidden
            assert hidden['transaction']['native_evaluation'] is False, hidden
            assert hidden['execution']['impact']['unavailable'], hidden
            assert hidden.get('verbs',[]) == [], hidden
        finally:
            hidden_node = hou.node('/obj/' + hidden_name)
            if hidden_node is not None:
                hidden_node.destroy()

    # A script that mixes a managed write with a helper-module raw write cannot
    # claim its impact is fully observed: the helper import is unresolved source.
    mixed_name = 'mixed_hidden_write_fixture'
    with tempfile.TemporaryDirectory(prefix='dsh-hidden-mixed-') as directory:
        Path(directory, 'mixed_helper.py').write_text(
            'import hou\n'
            'def bump(node):\n'
            '    hou.node(node).parm("tx").set(7.0)\n',
            encoding='utf-8')
        mixed = bridge.run_code(
            f'import sys\nsys.path.insert(0, {directory!r})\n'
            f'tab_create("/obj","geo",name={mixed_name!r})\n'
            f'import mixed_helper\nmixed_helper.bump("/obj/{mixed_name}")',
            owner_session='effect-observer')
        try:
            mixed_node = hou.node('/obj/' + mixed_name)
            assert mixed['ok'] and mixed_node is not None, mixed
            assert mixed_node.evalParm('tx') == 7.0, 'the fixture helper really changed the scene'
            assert mixed['transaction']['status'] == 'committed', mixed
            assert mixed['transaction']['effects'] == 'registered', mixed
            assert mixed['execution']['impact']['attempted'] is True, mixed
            assert mixed['execution']['impact']['unavailable'] is True, mixed
        finally:
            mixed_node = hou.node('/obj/' + mixed_name)
            if mixed_node is not None:
                mixed_node.destroy()

    # Imported implementation modules bypass the traced facade even in inspect
    # mode; the receipt keeps the unknown-effects fact instead of claiming a
    # no-write result (read_only_scope names the boundary explicitly).
    inspect_import = bridge.run_code('import dsh_node_creation\n__result__ = dsh_node_creation.tab_create.__name__', read_only=True)
    assert inspect_import['ok'] and inspect_import['result'] == 'tab_create', inspect_import
    assert inspect_import['transaction']['status'] == 'effects_unverified', inspect_import
    assert inspect_import['transaction']['effects'] == 'none', inspect_import
    assert inspect_import['execution']['impact']['unavailable'], inspect_import
    assert 'not a no-write guarantee' in inspect_import['execution']['read_only_scope'], inspect_import
finally:
    effect_root.destroy()

# Structured query dispatch derives its data-only allowlist from the shared verb
# access contract instead of a second hand-written list. Read-only verbs that
# were previously rejected must dispatch; write/cook verbs stay exec-only.
assert 'set_parm' not in execution._STRUCTURED_QUERY_VERBS
assert 'cook_node' not in execution._STRUCTURED_QUERY_VERBS
for allowed_name in ('scene_info', 'node_info', 'read_parms', 'node_provenance', 'graph',
                     'parameter_ui', 'geo_piece_stats', 'visible_objects', 'find_nodes', 'verb_help'):
    assert allowed_name in execution._STRUCTURED_QUERY_VERBS, allowed_name
for allowed_name in execution._STRUCTURED_QUERY_VERBS:
    assert allowed_name == 'selection' or (
        execution._VERB_DEFINITIONS[allowed_name].access == 'query_or_exec'
        and execution._VERB_DEFINITIONS[allowed_name].content_impact == 'none'), allowed_name
query_batch = bridge._runtime.run_queries([
    {'verb': 'scene_info'},
    {'verb': 'node_provenance', 'args': ['/obj']},
    {'verb': 'find_nodes', 'kwargs': {'pattern': '*', 'root': '/obj'}},
    {'verb': 'set_parm', 'args': ['/obj', 'tx', 1]},
], owner_session='query-allowlist-fixture', owner_call='query-allowlist')
query_rows = {row['index']: row for row in query_batch['result']['rows']}
assert query_batch['ok'], query_batch
assert [query_rows[index]['status'] for index in (0, 1, 2)] == ['succeeded'] * 3, query_batch['result']['rows']
assert query_rows[3]['status'] == 'rejected' and 'execution tool' in query_rows[3]['error'], query_rows[3]
assert query_batch['result']['counts'] == {'succeeded': 3, 'rejected': 1, 'failed': 0}, query_batch['result']['counts']

# Some data-only reads still evaluate native data (cook/expressions). Their
# receipt must carry the native-evaluation scope; navigation stays exec-only.
query_owner = 'query-native-eval-fixture'
with dsh_ownership.execution_owner(query_owner, 'setup'):
    eval_root = helpers.tab_create('/obj', 'geo', name='query_native_eval_fixture')
    eval_box = helpers.tab_create(eval_root, 'box', name='box')
try:
    native_batch = bridge._runtime.run_queries(
        [{'verb': 'describe', 'args': [eval_box.path()]}],
        owner_session=query_owner, owner_call='query-native-eval')
    assert native_batch['ok'], native_batch
    assert native_batch['result']['rows'][0]['status'] == 'succeeded', native_batch['result']['rows']
    assert native_batch['transaction']['status'] == 'effects_unverified', native_batch['transaction']
    assert native_batch['transaction']['effects'] == 'none' and native_batch['transaction']['native_evaluation'] is True, native_batch['transaction']
    assert native_batch['execution']['impact']['unavailable'] is True, native_batch['execution']['impact']
    assert 'native' in native_batch['transaction']['scope'], native_batch['transaction']['scope']
    pure_batch = bridge._runtime.run_queries(
        [{'verb': 'scene_info'}], owner_session=query_owner, owner_call='query-pure-metadata')
    assert pure_batch['transaction']['status'] == 'no_scene_change', pure_batch['transaction']
    assert pure_batch['transaction']['effects'] == 'none' and pure_batch['transaction']['native_evaluation'] is False, pure_batch['transaction']
    assert pure_batch['execution']['impact']['unavailable'] is False, pure_batch['execution']['impact']
    assert 'focus_node' not in execution._STRUCTURED_QUERY_VERBS, 'navigation must stay execution-only'
    assert 'control_test_plan' in execution._QUERY_NATIVE_EVALUATION_VERBS, 'parameter evaluation must be marked'
    assert 'render_check' not in execution._QUERY_NATIVE_EVALUATION_VERBS, 'file decoding is not native evaluation'
finally:
    eval_root.destroy()

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
