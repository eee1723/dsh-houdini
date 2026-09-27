"""Sacrificial H21/H22 GUI probe for render_view followed by an exec failure.

The launcher supplies empty preferences and a new HIP. This fixture does not
load or modify any user project and never starts a DSH Host or model session.
"""
from pathlib import Path
import json
import os
import sys
import traceback
import uuid

import hdefereval
import hou
from hutil.Qt import QtCore


OUT = Path(os.environ["DSH_RENDER_UNDO_GUI_DIR"])
ROOT = Path(os.environ["DSH_RENDER_UNDO_GUI_REPO"])
MODE = os.environ["DSH_RENDER_UNDO_GUI_MODE"]
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))


def record(name, value):
    path = OUT / name
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def run():
    try:
        import dsh_bridge as bridge

        if MODE not in ("control", "post_render_failure", "post_render_authored_failure"):
            raise ValueError("unknown probe mode")
        service_path = ("/out/__dsh_houdini_flipbook" if hou.applicationVersion()[0] >= 22
                        else "/out/__dsh_houdini_opengl")
        if hou.node(service_path) is not None:
            raise RuntimeError("render service exists before isolated probe")

        parent = hou.node("/obj").createNode("geo", "render_undo_fixture")
        box = parent.createNode("box", "SOURCE_BOX")
        output = parent.createNode("null", "OUT_ASSET")
        output.setInput(0, box)
        output.setDisplayFlag(True)
        output.setRenderFlag(True)
        hip = OUT / "fixture.hip"
        hou.hipFile.save(str(hip))
        record("progress.json", {"phase": "before_bridge", "mode": MODE,
                                 "version": hou.applicationVersionString(),
                                 "hip": str(hip), "service_preexists": False})

        # This marker distinguishes a completed render_view call from a crash
        # during the renderer, pixel check, or render_view's own finally block.
        original = bridge._VERBS["render_view"]

        def marked_render_view(*args, **kwargs):
            result = original(*args, **kwargs)
            record("render-returned.json", {"phase": "render_view_returned",
                                            "ok": result.get("ok"),
                                            "output": result.get("output"),
                                            "service_exists": hou.node(service_path) is not None,
                                            "authored_node_exists": parent.node("TX_TEMP") is not None})
            return result

        bridge._VERBS["render_view"] = marked_render_view
        code = ("tab_create('/obj/render_undo_fixture', 'box', name='TX_TEMP')\n"
                if MODE == "post_render_authored_failure" else "")
        code += ("r=render_view('/obj/render_undo_fixture/OUT_ASSET', "
                 "direction='iso', framing='full', coverage=0.85, width=640, height=360)\n")
        if MODE != "control":
            # json is imported in dsh_bridge, but intentionally absent from its
            # exec namespace. This mirrors the interrupted author's last call.
            code += "print(json.dumps(r.get('check', {})))\n"
        else:
            code += "print(r.get('ok'), r.get('output'))\n"

        result = bridge.run_code(code, owner_session="render-undo-" + uuid.uuid4().hex[:8],
                                 owner_call=uuid.uuid4().hex)
        record("results.json", {"phase": "after_bridge", "mode": MODE,
                                "ok": result.get("ok"),
                                "error": str(result.get("error") or "")[-3000:],
                                "rollback": result.get("rollback"),
                                "transaction": result.get("transaction"),
                                "service_exists": hou.node(service_path) is not None,
                                "authored_node_exists": parent.node("TX_TEMP") is not None,
                                "stdout": str(result.get("stdout") or "")[-1000:]})
        # Keep the scratch HIP clean so the ordinary main-window close path does
        # not stop at a Save Changes dialog after render_view edits its service.
        hou.hipFile.save(str(hip))
        QtCore.QTimer.singleShot(200, hou.qt.mainWindow().close)
    except BaseException:
        (OUT / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        QtCore.QTimer.singleShot(200, hou.qt.mainWindow().close)


hdefereval.executeDeferred(run)
