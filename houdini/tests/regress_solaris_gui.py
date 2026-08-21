"""GUI regression for parent-scoped Tab tools and native Karma setup.

Run on Houdini's main thread through the bridge:

    import importlib, runpy, dsh_hou_helpers
    importlib.reload(dsh_hou_helpers)
    result = runpy.run_path('.../regress_solaris_gui.py')['run']()

All nodes live in a disposable /obj LOP Network, not the user's /stage network.
"""
from __future__ import annotations

import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
LIBS = os.path.abspath(os.path.join(HERE, "..", "python3.11libs"))
if LIBS not in sys.path:
    sys.path.insert(0, LIBS)

import hou
import dsh_hou_helpers as H


def run():
    if not hou.isUIAvailable():
        raise RuntimeError("regress_solaris_gui.py requires a Houdini GUI session")
    obj = hou.node("/obj")
    pane = H._network_editor()
    if pane is None:
        raise RuntimeError("no Network Editor")

    original_pwd = pane.pwd()
    original_selection = [node.path() for node in hou.selectedNodes()]
    lopnet = None
    try:
        old = obj.node("dsh_solaris_regress")
        if old is not None:
            old.destroy()
        lopnet = obj.createNode("lopnet", "dsh_solaris_regress")
        sentinel = lopnet.createNode("null", "user_selected_lop")
        pane.setPwd(lopnet)
        hou.clearAllSelected()
        pane.setCurrentNode(sentinel)
        sentinel.setSelected(True)

        search = H.search_tab_entries(lopnet, "karma")
        by_name = {item["name"]: item for item in search["entries"]}
        if "lop_karma_setup" not in by_name:
            raise AssertionError(f"Karma Setup missing: {search}")
        if by_name["lop_karma_setup"]["executable"] is not True:
            raise AssertionError(f"Karma Setup not executable: {by_name['lop_karma_setup']}")
        if "karma" in by_name:
            raise AssertionError(f"hidden legacy Karma leaked into visible entries: {by_name['karma']}")

        setup = H.tab_apply(lopnet, "lop_karma_setup")
        from hutil.Qt import QtCore
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(20, loop.quit)
        loop.exec()
        if sorted(node.path() for node in hou.selectedNodes()) != [sentinel.path()]:
            raise AssertionError("Karma Setup did not restore the pre-call selection")
        created = [hou.node(item["path"]) for item in setup["created"]]
        created = [node for node in created if node is not None]
        settings = next(
            (node for node in created if node.type().name() == "karmarendersettings"),
            None,
        )
        usd_rop = next((node for node in created if isinstance(node, hou.RopNode)), None)
        if settings is None or usd_rop is None:
            raise AssertionError(f"Karma Setup did not create settings + ROP: {setup}")
        if usd_rop.type().name() != "usdrender_rop":
            raise AssertionError(f"unexpected Karma delivery ROP: {usd_rop.type().name()}")

        expressions = {}
        for parm_name in ("rendersettings", "husk_instantshutter", "renderer"):
            parm = usd_rop.parm(parm_name)
            expressions[parm_name] = parm.expression() if parm is not None else None
        if "primpath" not in (expressions["rendersettings"] or ""):
            raise AssertionError(f"render settings expression missing: {expressions}")
        if "enablemblur" not in (expressions["husk_instantshutter"] or ""):
            raise AssertionError(f"motion blur expression missing: {expressions}")
        if "engine" not in (expressions["renderer"] or ""):
            raise AssertionError(f"engine expression missing: {expressions}")

        matlib = H.tab_create(lopnet, "materiallibrary", name="dsh_materials")
        selection_after_tab_create = sorted(node.path() for node in hou.selectedNodes())
        hou.clearAllSelected()
        pane.setCurrentNode(sentinel)
        sentinel.setSelected(True)
        builder_search = H.search_tab_entries(matlib, "karma material")
        builder_names = [item["name"] for item in builder_search["entries"]]
        if builder_names != ["vop_karmamtlxsubnet"]:
            raise AssertionError(f"unexpected Material Library entries: {builder_search}")
        builder_result = H.tab_apply(matlib, "vop_karmamtlxsubnet")
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(20, loop.quit)
        loop.exec()
        if len(builder_result["created"]) != 1:
            raise AssertionError(f"Karma Material Builder cardinality changed: {builder_result}")
        builder = hou.node(builder_result["created"][0]["path"])
        child_types = {child.type().name() for child in builder.children()}
        required = {
            "mtlxstandard_surface", "mtlxdisplacement", "kma_material_properties", "suboutput",
        }
        if not required <= child_types:
            raise AssertionError(f"Karma Material Builder incomplete: {sorted(child_types)}")
        mask = builder.evalParm("tabmenumask")
        context = builder.evalParm("shader_rendercontextname")
        if "karma" not in mask.lower() or context != "kma":
            raise AssertionError(f"bad builder mask/context: mask={mask!r}, context={context!r}")

        if not setup["state_restored"]["network_pwd"]:
            raise AssertionError(f"Karma Setup did not restore pwd: {setup}")
        if not builder_result["state_restored"]["network_pwd"]:
            raise AssertionError(f"Material Builder did not restore pwd: {builder_result}")
        if sorted(node.path() for node in hou.selectedNodes()) != [sentinel.path()]:
            raise AssertionError("Material Builder did not restore the pre-call selection")

        summary = H.usd_stage_summary(settings)
        if summary["counts"]["render_settings"] < 1:
            raise AssertionError(f"Karma settings did not author RenderSettings: {summary}")
        return {
            "search": search,
            "setup": setup,
            "expressions": expressions,
            "builder": builder_result,
            "builder_children": sorted(child_types),
            "builder_mask": mask,
            "builder_context": context,
            "selection_after_tab_create": selection_after_tab_create,
            "stage_counts": summary["counts"],
        }
    finally:
        # The test drives multiple tab_apply calls in one bridge exec. Consume
        # the pending shared-baseline transaction before deleting its sentinel;
        # the following block then restores the real pre-test user state.
        try:
            H._finish_pending_tab_restore()
        except Exception:
            pass
        if lopnet is not None:
            try:
                lopnet.destroy()
            except Exception:
                pass
        try:
            pane.setPwd(original_pwd)
        except Exception:
            pass
        try:
            hou.clearAllSelected()
            for path in original_selection:
                node = hou.node(path)
                if node is not None:
                    node.setSelected(True)
        except Exception:
            pass


if __name__ == "__main__":
    print(run())
