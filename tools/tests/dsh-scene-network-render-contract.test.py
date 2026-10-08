"""H21 regression for save, disconnect, and fresh render contracts."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import uuid
import json
import shutil
import subprocess
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

import hou
import dsh_bridge
import dsh_hou_helpers


suffix = uuid.uuid4().hex[:8]
session = f"scene-contract-{suffix}"
parent_path = f"/obj/__dsh_scene_contract_{suffix}"
rop_path = f"/out/__dsh_scene_contract_{suffix}"

try:
    created = dsh_bridge.run_code(
        f"parent = tab_create('/obj', 'geo', name='__dsh_scene_contract_{suffix}')\n"
        "source = tab_create(parent, 'box', name='source')\n"
        "target = tab_create(parent, 'xform', name='target', inputs=[source])\n"
        "__result__ = {'parent': parent.path(), 'source': source.path(), 'target': target.path()}",
        owner_session=session,
        owner_call="create",
    )
    assert created["ok"] is True, created
    source_path = created["result"]["source"]
    target_path = created["result"]["target"]

    # Invalid literal managed filenames fail before allocation/cook/render.
    # Fake only GUI availability: the actual path validator and Bridge run.
    with patch.object(hou, 'isUIAvailable', return_value=True), \
         patch.object(dsh_hou_helpers, '_geometry_fingerprint', side_effect=AssertionError('preflight cooked geometry')):
        preview = f"render_view({target_path!r}, picture='nested/preview.png')"
        rejected = dsh_bridge.run_code(preview, owner_session=session, owner_call='preview-path-only')
        assert not rejected['ok'] and rejected['transaction']['status'] == 'no_scene_change', rejected
        assert rejected['verbs'][0]['summary']['phase'] == 'output_path_preflight', rejected
        assert rejected['verbs'][0]['summary']['scene_writes'] == 0, rejected
        assert not rejected['execution']['impact']['attempted'], rejected
        for policy in ('managed', 'delivery'):
            for filename in ('nested/preview.png', '`python("1")`.png'):
                allocated = dsh_bridge.run_code(
                    f"render_view({target_path!r}, picture={filename!r}, output_policy={policy!r})",
                    owner_session=session, owner_call='allocated-path-preflight')
                assert not allocated['ok'] and allocated['transaction']['status'] == 'no_scene_change', allocated
                assert allocated['verbs'][0]['summary']['phase'] == 'output_path_preflight', allocated
                assert allocated['verbs'][0]['kwargs']['output_policy'] == policy, allocated
                assert not allocated['execution']['impact']['attempted'], allocated
        before_tx = hou.node(target_path).parm('tx').eval()
        mixed = dsh_bridge.run_code(
            f"set_parm({target_path!r}, 'tx', 2)\n" + preview,
            owner_session=session, owner_call='preview-path-after-edit')
        assert not mixed['ok'] and mixed['transaction']['status'] == 'rolled_back', mixed
        assert hou.node(target_path).parm('tx').eval() == before_tx, mixed
        caught = dsh_bridge.run_code(
            "try:\n    " + preview + "\nexcept Exception:\n    pass\n"
            + f"set_parm({target_path!r}, 'tx', 1)",
            owner_session=session, owner_call='preview-path-caught')
        assert caught['ok'] and caught['outcome']['operations']['failed'] == 1, caught
        assert hou.node(target_path).parm('tx').eval() == 1, caught
        assert dsh_bridge.run_code(f"set_parm({target_path!r}, 'tx', {before_tx!r})",
                                  owner_session=session)['ok']

    # Static errors must not partially change global timeline or animation.
    timeline = dsh_hou_helpers.scene_info()
    invalid_timeline = dsh_bridge.run_code(
        'set_timeline(fps=60, frame_range=[20, 10])',
        owner_session=session, owner_call='timeline-preflight')
    assert invalid_timeline['ok'] is False, invalid_timeline
    assert invalid_timeline['transaction']['status'] == 'no_scene_change', invalid_timeline
    assert hou.fps() == timeline['fps'], invalid_timeline
    updated = dsh_hou_helpers.set_timeline(fps=timeline['fps'] + 6,
                                         current_frame=timeline['frame'] + 1)
    assert updated['scene']['fps'] == timeline['fps'] + 6, updated
    dsh_hou_helpers.set_timeline(fps=timeline['fps'], frame_range=timeline['frame_range'],
                                playback_range=timeline['playback_range'], current_frame=timeline['frame'])
    original_set_range = hou.playbar.setFrameRange
    reject_range = [True]
    def interrupted_range(*values):
        if reject_range[0]:
            reject_range[0] = False
            raise RuntimeError('injected range write failure')
        return original_set_range(*values)
    with patch.object(hou.playbar, 'setFrameRange', interrupted_range):
        try:
            dsh_hou_helpers.set_timeline(fps=60, frame_range=[2, 12])
            raise AssertionError('timeline write failure expected')
        except dsh_hou_helpers.CheckpointError as error:
            assert error.evidence['restored'] is True, error.evidence
    assert dsh_hou_helpers.scene_info()['fps'] == timeline['fps']
    assert dsh_hou_helpers.scene_info()['frame_range'] == timeline['frame_range']

    animated = hou.node(target_path)
    animated.parm('tx').set(5)
    animated.parm('ty').setExpression('2 + 7', hou.exprLanguage.Hscript)
    keys_before = tuple(animated.parm('ty').keyframes())
    original_set_keys = hou.Parm.setKeyframes
    reject_second = [True]
    def interrupted_keys(parm, keys):
        if parm.name() == 'ty' and reject_second[0]:
            reject_second[0] = False
            hou.setFrame(timeline['frame'] + 3)
            raise RuntimeError('injected second channel failure')
        return original_set_keys(parm, keys)
    with patch.object(hou.Parm, 'setKeyframes', interrupted_keys):
        try:
            dsh_hou_helpers.set_keyframes(animated,
                {'tx': [{'frame': 1, 'value': 0}], 'ty': [{'frame': 1, 'value': 1}]})
            raise AssertionError('second-channel failure expected')
        except dsh_hou_helpers.CheckpointError as error:
            assert error.evidence['restored'] is True, error.evidence
            assert error.evidence['restore_errors'] == [], error.evidence
    assert animated.parm('tx').eval() == 5
    assert not animated.parm('tx').keyframes()
    assert tuple(animated.parm('ty').keyframes()) == keys_before
    assert hou.frame() == timeline['frame']
    animated.parm('ty').lock(True)
    preflight = dsh_bridge.run_code(
        f'set_keyframes({target_path!r}, {{"tx":[{{"frame":1,"value":0}}], "ty":[{{"frame":1,"value":1}}]}})',
        owner_session=session, owner_call='keyframes-preflight')
    assert preflight['ok'] is False, preflight
    assert preflight['transaction']['status'] == 'no_scene_change', preflight
    assert animated.parm('tx').eval() == 5 and animated.parm('ty').isLocked()
    animated.parm('ty').lock(False)
    keyed = dsh_hou_helpers.set_keyframes(animated, {'tx': [
        {'frame': 1, 'value': 2, 'curve': 'linear'}, {'frame': 9, 'value': 6, 'curve': 'linear'}]})
    assert keyed['channels']['tx']['samples']['5.0'] == 4, keyed
    assert hou.frame() == timeline['frame']
    recovered = dsh_bridge.run_code(
        f'try:\n set_parms({target_path!r}, {{"ty":2,"tx":[1]}})\n'
        f'except RuntimeError:\n pass\n__result__=set_parm({target_path!r}, "ty", 3)',
        owner_session=session, owner_call='parameter-restored-continue')
    assert recovered['ok'] is True, recovered
    assert recovered['verbs'][0]['summary']['restored'] is True, recovered
    assert 'external side effects' in recovered['verbs'][0]['summary']['restoration_scope'], recovered
    assert animated.parm('ty').eval() == 3 and animated.parm('tx').keyframes()

    dry = dsh_bridge.run_code(
        f'__result__ = build_module({parent_path!r}, [{{"name":"dry_source","type":"box"}}], "dry_source", True)',
        owner_session=session, owner_call='module-dry-run')
    assert dry['ok'] is True and dry['transaction']['status'] == 'no_scene_change', dry
    assert dry['execution']['impact']['attempted'] is False, dry
    assert hou.node(parent_path + '/dry_source') is None

    disconnected = dsh_bridge.run_code(
        f"__result__ = disconnect_input({target_path!r}, 0)",
        owner_session=session,
        owner_call="disconnect",
    )
    assert disconnected["ok"] is True, disconnected
    assert {k:disconnected["result"][k] for k in ("node","input","disconnected")} == {
        "node": target_path,
        "input": 0,
        "disconnected": source_path,
    }, disconnected
    assert hou.node(target_path).input(0) is None

    with tempfile.TemporaryDirectory(prefix="dsh-scene-contract-") as tmp:
        tmp_path = Path(tmp)
        hip_path = tmp_path / "scene_contract.hip"
        hou.hipFile.save(file_name=hip_path.as_posix())
        hou.node(source_path).parm("sizex").set(1.25)
        saved = dsh_bridge.run_code(
            f"__result__ = scene_save({hip_path.as_posix()!r})",
            owner_session=session,
            owner_call="save",
        )
        assert saved["ok"] is True, saved
        assert saved["result"]["path"] == str(hip_path.resolve()), saved
        assert saved["result"]["dirty_before"] is True, saved
        assert saved["result"]["dirty_reliable"] is False, saved
        assert saved["result"]["clean_on_disk"] is None, saved
        assert saved["result"]["bytes"] > 0, saved

        mismatch = dsh_bridge.run_code(
            f"scene_save({(tmp_path / 'wrong.hip').as_posix()!r})",
            owner_session=session,
            owner_call="save-mismatch",
        )
        assert mismatch["ok"] is False, mismatch
        assert "expected_path 与当前 HIP 不一致" in mismatch["error"], mismatch

        rop = hou.node("/out").createNode("geometry", f"__dsh_scene_contract_{suffix}")
        rop.parm("soppath").set(source_path)
        original_output = str(tmp_path / "original.$F4.bgeo.sc")
        test_output = str(tmp_path / "override.$F4.bgeo.sc")
        rop.parm("sopoutput").set(original_output)
        result = dsh_hou_helpers.render_frame(
            rop,
            picture=test_output,
            frame=1,
            # Output exists even when blocking native render exceeds the wait budget.
            timeout=0.000001,
        )
        assert result["fresh"] is True, result
        assert result["preexisting"] is False, result
        assert result["file_bytes"] > 0, result
        assert result["post_fingerprint"]["sample_sha256"], result
        assert rop.parm("sopoutput").unexpandedString() == original_output, result

        # Ordinary renderer/output failure remains a returned check failure;
        # confirmed restoration permits the next explicit scene operation.
        rop.parm('soppath').set('/obj/__missing_render_source__')
        check_failed = dsh_bridge.run_code(
            f"__result__=render_frame({rop.path()!r},picture={(tmp_path / 'failed.bgeo.sc').as_posix()!r},timeout=.01)\n"
            f"set_parm({target_path!r},'tx',2)", owner_session=session)
        assert check_failed['ok'] and check_failed['result']['errors'], check_failed
        assert check_failed['outcome']['checks']['failed'] == 1, check_failed
        assert hou.node(target_path).evalParm('tx') == 2
        assert rop.parm('sopoutput').unexpandedString() == original_output
        rop.parm('soppath').set(source_path)

        # A real native post-render callback makes the temporary output write
        # impossible to restore. This is a failed mutation, not image quality.
        rop.parm('lpostrender').set('python')
        rop.parm('postrender').set("hou.pwd().parm('sopoutput').lock(True)")
        saved_mtime = hip_path.stat().st_mtime_ns
        try:
            restore_failed = dsh_bridge.run_code(
                f"try:\n render_frame({rop.path()!r},picture={(tmp_path / 'locked.bgeo.sc').as_posix()!r},timeout=.01)\n"
                f"except Exception:\n pass\ntry:\n set_parm({target_path!r},'tx',999)\n"
                "except Exception:\n pass\ntry:\n scene_save()\nexcept Exception:\n pass\n"
                f"describe({target_path!r})", owner_session=session)
            assert not restore_failed['ok'], restore_failed
            failure = restore_failed['verbs'][0]['summary']
            assert failure['phase'] == 'render_restore' and failure['restored'] is False, restore_failed
            assert failure['fresh'] is True and failure['restore_errors'], restore_failed
            assert all(row['summary']['dispatched'] is False for row in restore_failed['verbs'][1:3]), restore_failed
            assert restore_failed['verbs'][3]['ok'] is True, restore_failed
            assert hou.node(target_path).evalParm('tx') == 2
            assert hip_path.stat().st_mtime_ns == saved_mtime
            assert (tmp_path / 'locked.bgeo.sc').is_file()  # External file is retained.
        finally:
            rop.parm('sopoutput').lock(False)
            rop.parm('postrender').set('')


finally:
    node = hou.node(parent_path)
    if node is not None:
        node.destroy()
    rop = hou.node(rop_path)
    if rop is not None:
        rop.destroy()

print("scene/network/render contract regression passed")
