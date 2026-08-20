"""GUI H21/H22 regression for render_view v2 isolation.

Run on Houdini's main thread, normally through the dsh bridge:

    import runpy
    result = runpy.run_path('.../regress_visual_gui.py')['run']()

The test deliberately points the source OBJ at an empty SOP and adds a large
visible interferer. The explicit GOOD_OUT render must remain identical before
and after user-like display/visibility changes. Probe nodes/files are cleaned.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile


HERE = os.path.dirname(os.path.abspath(__file__))
LIBS = os.path.abspath(os.path.join(HERE, "..", "python3.11libs"))
if LIBS not in sys.path:
    sys.path.insert(0, LIBS)

import hou
import dsh_hou_helpers as H


def run():
    if not hou.isUIAvailable():
        raise RuntimeError("regress_visual_gui.py requires a Houdini GUI session")
    obj = hou.node("/obj")
    temp_dir = tempfile.mkdtemp(prefix="dsh-visual-regress-")
    source = interferer = None
    original_frame = hou.frame()
    original_selection = [node.path() for node in hou.selectedNodes()]
    original_flags = {
        child.path(): bool(child.isDisplayFlagSet()) for child in obj.children()
    }
    diagnostic_keys = (
        "dsh_render_state", "dsh_last_target", "dsh_last_frame", "dsh_last_output",
    )
    existing_proxy = hou.node("/obj/__dsh_houdini_render_proxy")
    diagnostic_snapshot = {
        key: existing_proxy.userData(key) if existing_proxy is not None else None
        for key in diagnostic_keys
    }
    existing_source = existing_proxy.node("source") if existing_proxy is not None else None
    source_comment_before = existing_source.comment() if existing_source is not None else None
    try:
        source = obj.createNode("geo", "dsh_visual_regress_source")
        for child in source.children():
            child.destroy()
        source.parm("tx").set(2.0)
        box = source.createNode("box", "good_box")
        green = source.createNode("color", "GOOD_OUT")
        green.setInput(0, box)
        H.set_parms(green, {
            "colortype": 0, "colorr": 0.0, "colorg": 1.0, "colorb": 0.0,
        })
        empty = source.createNode("null", "empty")
        H.sop_set_output(empty)
        H.set_object_visible(source, False)

        interferer = obj.createNode("geo", "dsh_visual_regress_interferer")
        for child in interferer.children():
            child.destroy()
        sphere = interferer.createNode("sphere", "sphere")
        red = interferer.createNode("color", "RED_OUT")
        red.setInput(0, sphere)
        H.set_parms(red, {
            "colortype": 0, "colorr": 1.0, "colorg": 0.0, "colorb": 0.0,
        })
        interferer.parm("sx").set(8.0)
        H.sop_set_output(red)
        H.set_object_visible(interferer, True)
        hou.clearAllSelected()
        interferer.setSelected(True)
        hou.setFrame(7)

        user_paths = {source.path(), interferer.path()}
        before_flags = {
            path: bool(hou.node(path).isDisplayFlagSet()) for path in user_paths
        }
        before_selection = sorted(node.path() for node in hou.selectedNodes())
        first_path = os.path.join(temp_dir, "first.png")
        first = H.render_view(
            green, direction="iso", frame=3, width=320, height=240,
            picture=first_path,
        )
        if first["errors"] or first["stale"]:
            raise AssertionError(first)
        if first["check"]["dominant"][1] <= first["check"]["dominant"][0] * 2:
            raise AssertionError(f"explicit green target was not isolated: {first['check']}")
        after_first_flags = {
            path: bool(hou.node(path).isDisplayFlagSet()) for path in user_paths
        }
        if after_first_flags != before_flags or not first["user_state_restored"]:
            raise AssertionError(
                f"render_view changed user OBJ visibility: {before_flags} -> {after_first_flags}"
            )
        if sorted(node.path() for node in hou.selectedNodes()) != before_selection:
            raise AssertionError("first render did not restore selection")

        # User-like drift between calls: change both SOP output and OBJ visibility.
        H.sop_set_output(box)
        H.set_object_visible(source, True)
        second_path = os.path.join(temp_dir, "second.png")
        second = H.render_view(
            green, direction="iso", frame=3, width=320, height=240,
            picture=second_path,
        )
        diff = H.render_check(second_path, ref=first_path)["diff_vs_ref"]
        if not diff["identical"]:
            raise AssertionError(f"display drift changed explicit render: {diff}")
        if second["framing"]["center"][0] != 2.0:
            raise AssertionError(f"source OBJ transform was lost: {second['framing']}")
        if hou.frame() != 7:
            raise AssertionError("render_view/render_frame did not restore user frame")
        if sorted(node.path() for node in hou.selectedNodes()) != before_selection:
            raise AssertionError("render_view did not restore selection")

        # Animation A/B can share one framing frame so pixel diffs are not
        # contaminated by per-frame bbox recentering/zooming.
        moving = source.createNode("xform", "MOVING_OUT")
        moving.setInput(0, green)
        moving.parm("tx").setExpression("$F * 0.1", language=hou.exprLanguage.Hscript)
        moving_a = H.render_view(
            moving, direction="iso", frame=1, framing_frame=1,
            width=160, height=120, picture=os.path.join(temp_dir, "moving_a.png"),
        )
        moving_b = H.render_view(
            moving, direction="iso", frame=2, framing_frame=1,
            width=160, height=120, picture=os.path.join(temp_dir, "moving_b.png"),
        )
        for key in ("frame", "center", "size", "dist", "eye", "direction", "source_signature"):
            if moving_a["framing"][key] != moving_b["framing"][key]:
                raise AssertionError(
                    f"fixed framing changed {key}: "
                    f"{moving_a['framing'][key]} -> {moving_b['framing'][key]}"
                )
        if moving_a["source_fingerprint_before"]["signature"] == moving_b["source_fingerprint_before"]["signature"]:
            raise AssertionError("animated source fingerprints did not change across frames")

        # Empty explicit SOP must fail before generating a misleading black image.
        try:
            H.render_view(empty, width=64, height=64, picture=os.path.join(temp_dir, "empty.png"))
        except ValueError as error:
            if "没有可渲染几何" not in str(error):
                raise
        else:
            raise AssertionError("render_view accepted an empty explicit SOP")

        proxy = hou.node("/obj/__dsh_houdini_render_proxy")
        proxy_source = proxy.node("source") if proxy is not None else None
        if proxy_source is None or proxy_source.parm("objpath1").evalAsString():
            raise AssertionError("idle render proxy retained a live source reference")
        if proxy.userData("dsh_render_state") != "idle":
            raise AssertionError("idle render proxy has no truthful lifecycle metadata")
        if proxy.userData("dsh_last_target") != moving.path():
            raise AssertionError("idle render proxy did not record its last explicit target")
        if "cleared afterward" not in proxy_source.comment():
            raise AssertionError("idle render proxy source does not explain why it is empty")
        return {
            "first": first["check"],
            "second": second["check"],
            "diff": diff,
            "source_output_after_drift": H.sop_output_node(source),
            "proxy_hidden": proxy is not None and not proxy.isDisplayFlagSet(),
            "proxy_idle": proxy.userData("dsh_render_state") == "idle",
            "proxy_last_target": proxy.userData("dsh_last_target"),
            "fixed_framing": moving_a["framing"],
            "frame_restored": hou.frame() == 7,
            "selection_restored": sorted(node.path() for node in hou.selectedNodes()) == before_selection,
            "flags_before_first_render": before_flags,
        }
    finally:
        for node in (interferer, source):
            if node is not None:
                try:
                    node.destroy()
                except Exception:
                    pass
        for path, visible in original_flags.items():
            node = hou.node(path)
            if node is not None:
                try:
                    node.setDisplayFlag(visible)
                except Exception:
                    pass
        try:
            hou.setFrame(original_frame)
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
        proxy = hou.node("/obj/__dsh_houdini_render_proxy")
        if proxy is not None:
            for key, value in diagnostic_snapshot.items():
                try:
                    if value is None:
                        proxy.destroyUserData(key)
                    else:
                        proxy.setUserData(key, value)
                except Exception:
                    pass
            source = proxy.node("source")
            if source is not None:
                try:
                    source.setComment(source_comment_before or "")
                except Exception:
                    pass
        if os.path.isdir(temp_dir) and os.path.basename(temp_dir).startswith("dsh-visual-regress-"):
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    print(run())
