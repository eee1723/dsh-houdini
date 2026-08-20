"""H21/H22 regression for scene/display/geometry verification verbs.

Run with hython. The script uses only disposable /obj nodes and temp PNGs;
GUI-only render_view proxy isolation is covered by the live bridge probe.
"""
from __future__ import annotations

import os
import json
import math
import shutil
import sys
import tempfile


HERE = os.path.dirname(os.path.abspath(__file__))
LIBS = os.path.abspath(os.path.join(HERE, "..", "python3.11libs"))
sys.path.insert(0, LIBS)

import hou
import dsh_hou_helpers as H
import dsh_bridge


failures = []
temp_dir = tempfile.mkdtemp(prefix="dsh-scene-geometry-regress-")
probe_name = "dsh_scene_geometry_regress"


def check(label, fn):
    try:
        fn()
        print(f"PASS  {label}")
    except Exception as error:
        failures.append(label)
        print(f"FAIL  {label}: {type(error).__name__}: {str(error)[:500]}")


def cleanup():
    node = hou.node("/obj/" + probe_name)
    if node is not None:
        try:
            node.destroy()
        except Exception:
            pass
    if os.path.isdir(temp_dir) and os.path.basename(temp_dir).startswith(
        "dsh-scene-geometry-regress-"
    ):
        shutil.rmtree(temp_dir)


try:
    obj = hou.node("/obj")
    geo = obj.createNode("geo", probe_name)
    for child in geo.children():
        child.destroy()
    box = geo.createNode("box", "good_box")
    empty = geo.createNode("null", "empty")

    def t1():
        before = hou.frame()
        info = H.scene_info()
        assert info["version"] == hou.applicationVersionString(), info
        assert info["fps"] == hou.fps(), info
        assert info["frame"] == before, info
        assert len(info["playback_range"]) == 2, info
        assert hou.frame() == before, "scene_info changed current frame"
    check("1 scene_info is complete and read-only", t1)

    def t2():
        result = H.sop_set_output(box)
        assert result["display"] and result["render"], result
        state = H.sop_output_node(geo)
        assert state["display"] == box.path() and state["render"] == box.path(), state
        H.set_object_visible(geo, False)
        hidden = H.visible_objects("/obj")
        entry = next(item for item in hidden["objects"] if item["path"] == geo.path())
        assert entry["visible"] is False, entry
        H.set_object_visible(geo, True)
        compat = H.display_node("/obj")
        assert compat["context"] == "obj" and isinstance(compat["objects"], list), compat
    check("2 SOP output and OBJ visibility have separate contracts", t2)

    def t3():
        left = geo.createNode("box", "piece_left")
        left.parmTuple("t").set((-2, 0, 0))
        right = geo.createNode("box", "piece_right")
        right.parmTuple("t").set((2, 0, 0))
        merge = geo.createNode("merge", "two_pieces")
        merge.setInput(0, left)
        merge.setInput(1, right)
        stats = H.geo_piece_stats(merge, sample=4)
        assert stats["piece_count"] == 2, stats
        assert stats["degenerate_surface_pieces"] == 0, stats

        grid = geo.createNode("grid", "degenerate_grid")
        grid.parmTuple("size").set((0, 1))
        bad = H.geo_piece_stats(grid, sample=2)
        assert bad["piece_count"] == 1, bad
        assert bad["degenerate_surface_pieces"] >= 1, bad
    check("3 geo_piece_stats finds pieces and zero-area surfaces", t3)

    def t4():
        xform = geo.createNode("xform", "animated_xform")
        xform.setInput(0, box)
        xform.parm("tx").setExpression("$F", language=hou.exprLanguage.Hscript)
        current = hou.frame()
        diff = H.geo_frame_diff(xform, 1, 2, sample=128)
        assert diff["comparable"] is True, diff
        assert 0.99 <= diff["max_delta"] <= 1.01, diff
        assert 0.99 <= diff["delta_percentiles"]["p50"] <= 1.01, diff
        assert 0.99 <= diff["component_delta"]["mean"][0] <= 1.01, diff
        assert abs(diff["component_delta"]["mean"][1]) <= 1e-9, diff
        assert abs(diff["component_delta"]["mean"][2]) <= 1e-9, diff
        assert diff["unchanged_pct"] == 0.0, diff
        assert hou.frame() == current, "geo_frame_diff changed current frame"
    check("4 geo_frame_diff detects animation without moving playbar", t4)

    def t5():
        nodes = [box, empty]
        box.setPosition(hou.Vector2(0, 0))
        empty.setPosition(hou.Vector2(0, 0))
        result = H.layout_nodes(geo, nodes)
        assert len(result["nodes"]) == 2, result
        assert box.position() != empty.position(), result
    check("5 layout_nodes lays out an explicit subset", t5)

    def t6():
        from PySide6.QtGui import QColor, QImage

        first = os.path.join(temp_dir, "a.png")
        second = os.path.join(temp_dir, "b.png")
        a = QImage(16, 16, QImage.Format.Format_RGB888)
        a.fill(QColor(0, 0, 0))
        assert a.save(first)
        b = QImage(first)
        b.setPixelColor(0, 0, QColor(1, 0, 0))
        assert b.save(second)
        diff = H.render_check(second, ref=first)["diff_vs_ref"]
        assert diff["identical"] is False, diff
        assert diff["changed_pixel_pct"] > 0, diff
        assert diff["mean_abs_diff"] > 0, diff
        assert diff["rmse"] > 0, diff
    check("6 render_check preserves small non-zero image differences", t6)

    def t7():
        group = empty.parmTemplateGroup()
        group.append(hou.StringParmTemplate("snippet", "Snippet", 1, default_value=("",)))
        empty.setParmTemplateGroup(group)
        empty.parm("snippet").set(
            'float a=ch("amp"); int s=chi("seed"); vector d=chv("dir"); string n=chs("name");'
        )
        result = H.create_spare_parms(
            empty,
            defaults={"amp": 0.25, "seed": 7, "dir": [1, 0, 0], "name": "wind"},
        )
        assert set(result["created"]) == {"amp", "seed", "dir", "name"}, result
        assert empty.parm("amp").eval() == 0.25, result
        assert empty.parm("seed").eval() == 7, result
        assert tuple(empty.parmTuple("dir").eval()) == (1.0, 0.0, 0.0), result
        assert empty.parm("name").eval() == "wind", result
    check("7 create_spare_parms materializes code channel references", t7)

    def t8():
        original = H.scene_info()
        bookmark_name = "__dsh_scene_regress__"
        try:
            H.set_timeline(
                fps=30,
                frame_range=[10, 40],
                playback_range=[12, 36],
                current_frame=20,
            )
            changed = H.scene_info()
            assert changed["fps"] == 30 and changed["frame"] == 20, changed
            assert changed["frame_range"] == [10.0, 40.0], changed
            created = H.create_bookmark(bookmark_name, 12, 18)
            assert created["name"] == bookmark_name, created
            assert any(item["name"] == bookmark_name for item in H.list_bookmarks())
            deleted = H.delete_bookmark(bookmark_name)
            assert deleted["deleted"][0]["name"] == bookmark_name, deleted
        finally:
            try:
                H.delete_bookmark(bookmark_name)
            except Exception:
                pass
            H.set_timeline(
                fps=original["fps"],
                frame_range=original["frame_range"],
                playback_range=original["playback_range"],
                current_frame=original["frame"],
            )
    check("8 timeline and bookmark intents round-trip cleanly", t8)

    def t9():
        def assert_no_negative_zero(value):
            if isinstance(value, float):
                assert not (value == 0.0 and math.copysign(1.0, value) < 0), value
            elif isinstance(value, dict):
                for child in value.values():
                    assert_no_negative_zero(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    assert_no_negative_zero(child)

        direct = dsh_bridge._jsonable({
            "zero": -0.0,
            "nested": [-0.0, float("nan"), float("inf"), -float("inf")],
        })
        assert direct == {
            "zero": 0.0,
            "nested": [0.0, "nan", "inf", "-inf"],
        }, direct
        vector = dsh_bridge._verb_value(hou.Vector3(-0.0, 1.0, -0.0))
        assert vector == [0.0, 1.0, 0.0], vector
        result = dsh_bridge.run_code(
            "__result__ = {'zero': -0.0, 'nested': [-0.0, float('nan')]}"
        )
        assert result["ok"] is True, result
        json.dumps(result, allow_nan=False)
        assert_no_negative_zero(result)
        assert result["result"] == {"zero": 0.0, "nested": [0.0, "nan"]}, result
        contract = dsh_bridge.run_code("__result__ = verb_help('read_parms')")
        assert contract["ok"] is True, contract
        assert contract["result"]["signature"].startswith("(node,"), contract
        assert "list[dict]" in contract["result"]["doc"], contract
    check("9 bridge normalizes lossless-JSON floats everywhere", t9)

finally:
    cleanup()


print()
print("FAILED:" if failures else "ALL PASS", failures if failures else "")
sys.exit(1 if failures else 0)
