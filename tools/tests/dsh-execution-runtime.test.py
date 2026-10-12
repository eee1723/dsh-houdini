"""Focused checks for shared analysis and queries that never prepare edits."""

from pathlib import Path
import sys
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

print('single analysis / query isolation / callable signature cache / nested media / detached component rollback passed on ' + hou.applicationVersionString())
