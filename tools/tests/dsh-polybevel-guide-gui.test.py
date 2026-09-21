"""Sacrificial GUI fixture for PolyBevel output and viewport-guide interaction.

Runs only in a newly isolated Houdini GUI. It never loads a user HIP or starts
DSH/model services. A native crash intentionally leaves no success report; the
driver preserves the process exit and log as evidence.
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


OUT = Path(os.environ["DSH_POLYBEVEL_GUI_DIR"])
ROOT = Path(os.environ["DSH_POLYBEVEL_GUI_REPO"])
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))


def atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def run():
    try:
        import dsh_bridge as bridge

        session = "polybevel-gui-" + uuid.uuid4().hex[:8]

        def call(code):
            result = bridge.run_code(code, owner_session=session, owner_call=uuid.uuid4().hex)
            if not result["ok"]:
                raise RuntimeError(result)
            return result

        built = call(
            "p=tab_create('/obj','geo',name='polybevel_guide_fixture')\n"
            "s=tab_create(p,'box',name='SOURCE_BOX')\n"
            "b=tab_create(p,'polybevel::3.0',name='BEVEL',inputs=[s],"
            "parms={'group':'','offset':0.004,'divisions':1})\n"
            "t=tab_create(p,'box',name='TEMPLATE_POINTS')\n"
            "c=tab_create(p,'copytopoints::2.0',name='COPY',inputs=[b,t])\n"
            "o=tab_create(p,'null',name='OUT_ASSET',inputs=[c])\n"
            "sop_set_output(o)\n"
            "v=verify_network(p,output=o)\n"
            "__result__={'parent':p.path(),'source':s.path(),'bevel':b.path(),"
            "'output':o.path(),'points':v['geometry']['points'],'prims':v['geometry']['prims']}"
        )["result"]
        parent = hou.node(built["parent"])
        hip = OUT / "polybevel-guide.hip"
        hou.hipFile.save(str(hip))
        atomic_json(OUT / "progress.json", {"phase": "built", "version": hou.applicationVersionString(), **built})

        network = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
        viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
        if network is None or viewer is None:
            raise RuntimeError("isolated GUI needs Network Editor and Scene Viewer panes")
        network.setPwd(parent)
        try:
            viewer.setPwd(parent)
        except Exception:
            pass

        phases = ["SOURCE_BOX", "BEVEL", "OUT_ASSET", "SOURCE_BOX"]
        state = {"index": 0, "visited": []}
        timer = QtCore.QTimer(hou.qt.mainWindow())

        def finish():
            timer.stop()
            result = {
                "ok": True,
                "version": hou.applicationVersionString(),
                "gui": True,
                "hip": str(hip),
                "visited": state["visited"],
                "output": built,
                "scope": "normal output cook/save plus current-node viewport guide refresh; not proof for every topology or interaction",
            }
            atomic_json(OUT / "results.json", result)
            QtCore.QTimer.singleShot(100, hou.qt.mainWindow().close)

        def tick():
            try:
                if state["index"] >= len(phases):
                    finish()
                    return
                name = phases[state["index"]]
                node = parent.node(name)
                if node is None:
                    raise RuntimeError("missing fixture node: " + name)
                node.setCurrent(True, clear_all_selected=True)
                node.setSelected(True, clear_all_selected=True)
                hou.ui.triggerUpdate()
                state["visited"].append(name)
                state["index"] += 1
                atomic_json(OUT / "progress.json", {
                    "phase": "guide_refresh",
                    "version": hou.applicationVersionString(),
                    "visited": state["visited"],
                })
            except Exception:
                timer.stop()
                (OUT / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
                QtCore.QTimer.singleShot(100, hou.qt.mainWindow().close)

        timer.timeout.connect(tick)
        timer.start(1000)
        hou.session._dsh_polybevel_guide_timer = timer
    except Exception:
        (OUT / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        QtCore.QTimer.singleShot(100, hou.qt.mainWindow().close)


hdefereval.executeDeferred(run)
