"""H21 regression for save, disconnect, and fresh render contracts."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import uuid


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

    disconnected = dsh_bridge.run_code(
        f"__result__ = disconnect_input({target_path!r}, 0)",
        owner_session=session,
        owner_call="disconnect",
    )
    assert disconnected["ok"] is True, disconnected
    assert disconnected["result"] == {
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
            timeout=30,
        )
        assert result["fresh"] is True, result
        assert result["preexisting"] is False, result
        assert result["file_bytes"] > 0, result
        assert result["post_fingerprint"]["sample_sha256"], result
        assert rop.parm("sopoutput").unexpandedString() == original_output, result

finally:
    node = hou.node(parent_path)
    if node is not None:
        node.destroy()
    rop = hou.node(rop_path)
    if rop is not None:
        rop.destroy()

print("scene/network/render contract regression passed")
