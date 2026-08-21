"""H21/H22 channel and KineFX foundation regression.

Run with hython. Uses disposable OBJ/SOP nodes, never saves a HIP, and records
the ground-truth contracts that the future set_keyframes verb and
houdini-rig-animation-workflow skill must preserve.
"""
from __future__ import annotations

import os
import sys
import textwrap


HERE = os.path.dirname(os.path.abspath(__file__))
LIBS = os.path.abspath(os.path.join(HERE, "..", "python3.11libs"))
sys.path.insert(0, LIBS)

import hou
import dsh_hou_helpers as H


CTRL_NAME = "dsh_channel_foundation_regress"
GEO_NAME = "dsh_kinefx_foundation_regress"
failures = []


def check(label, fn):
    try:
        fn()
        print(f"PASS  {label}")
    except Exception as error:
        failures.append(label)
        print(f"FAIL  {label}: {type(error).__name__}: {str(error)[:1200]}")


SKELETON_CODE = textwrap.dedent(
    r'''
    geo = hou.pwd().geometry()
    name_attrib = geo.addAttrib(hou.attribType.Point, "name", "")
    transform_attrib = geo.addAttrib(
        hou.attribType.Point,
        "transform",
        (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
    )
    points = []
    for name, position in (
        ("root", (0.0, 0.0, 0.0)),
        ("mid",  (0.0, 1.0, 0.0)),
        ("tip",  (0.0, 2.0, 0.0)),
    ):
        point = geo.createPoint()
        point.setPosition(position)
        point.setAttribValue(name_attrib, name)
        point.setAttribValue(
            transform_attrib,
            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        )
        points.append(point)
    for parent, child in ((0, 1), (1, 2)):
        bone = geo.createPolygon(is_closed=False)
        bone.addVertex(points[parent])
        bone.addVertex(points[child])
    '''
).strip()


def make_key(value, frame, expression):
    key = hou.Keyframe(float(value))
    key.setFrame(float(frame))
    key.setExpression(expression, hou.exprLanguage.Hscript)
    return key


obj = hou.node("/obj")
ctrl = obj.node(CTRL_NAME)
geo = obj.node(GEO_NAME)
try:
    for node in (ctrl, geo):
        if node is not None:
            node.destroy()
    ctrl = obj.createNode("null", CTRL_NAME)
    geo = obj.createNode("geo", GEO_NAME)
    for child in geo.children():
        child.destroy()

    def t1():
        parm = ctrl.parm("tx")
        saved = hou.frame()
        samples = {}
        try:
            for expression in ("constant()", "linear()", "bezier()"):
                parm.deleteAllKeyframes()
                parm.setKeyframes((
                    make_key(0.0, 1.0, expression),
                    make_key(10.0, 11.0, expression),
                ))
                keys = parm.keyframes()
                samples[expression] = parm.evalAtFrame(6)
                assert [key.frame() for key in keys] == [1.0, 11.0], keys
                assert [key.expression() for key in keys] == [expression, expression], keys
            assert samples == {
                "constant()": 0.0,
                "linear()": 5.0,
                "bezier()": 5.0,
            }, samples
            assert hou.frame() == saved
        finally:
            parm.deleteAllKeyframes()
            parm.set(0.0)
            hou.setFrame(saved)
    check("1 H21/H22 keyframe expressions and frame units round-trip", t1)

    def t2():
        saved = hou.frame()
        hou.setFrame(7)
        try:
            result = H.set_keyframes(ctrl, {
                "tx": [
                    {"frame": 1, "value": 0, "curve": "constant"},
                    {"frame": 11, "value": 10, "curve": "constant"},
                ],
                "ty": [
                    {"frame": 1, "value": 0, "curve": "linear"},
                    {"frame": 11, "value": 10, "curve": "linear"},
                ],
                "tz": [
                    {"frame": 1, "value": 0, "curve": "bezier"},
                    {"frame": 11, "value": 10, "curve": "bezier"},
                ],
            })
            assert result["frame_restored"] and hou.frame() == 7, result
            assert ctrl.parm("tx").evalAtFrame(6) == 0.0, result
            assert ctrl.parm("ty").evalAtFrame(6) == 5.0, result
            assert ctrl.parm("tz").evalAtFrame(6) == 5.0, result

            summary = {item["name"]: item for item in H.read_parms(ctrl)}
            for name, curve in (
                ("tx", "constant()"), ("ty", "linear()"), ("tz", "bezier()")
            ):
                assert summary[name]["animated"] is True, summary[name]
                assert summary[name]["time_dependent"] is True, summary[name]
                assert summary[name]["key_count"] == 2, summary[name]
                assert summary[name]["first_frame"] == 1.0, summary[name]
                assert summary[name]["last_frame"] == 11.0, summary[name]
                assert curve in summary[name]["curves"], summary[name]

            before = tuple(ctrl.parm("tx").keyframes())
            try:
                H.set_keyframes(ctrl, {
                    "tx": [{"frame": 21, "value": 20, "curve": "linear"}],
                    "missing": [{"frame": 1, "value": 0}],
                })
            except ValueError:
                pass
            else:
                raise AssertionError("invalid multi-channel request did not fail")
            assert tuple(ctrl.parm("tx").keyframes()) == before

            appended = H.set_keyframes(ctrl, {
                "tx": [{"frame": 21, "value": 20, "curve": "linear"}],
            }, replace=False)
            assert appended["channels"]["tx"]["key_count"] == 3, appended
            try:
                H.set_keyframes(ctrl, {
                    "tx": [{"frame": 21, "value": 30, "curve": "linear"}],
                }, replace=False)
            except ValueError as error:
                assert "不允许覆盖" in str(error), error
            else:
                raise AssertionError("replace=False overwrote an existing frame")
        finally:
            for name in ("tx", "ty", "tz"):
                ctrl.parm(name).deleteAllKeyframes()
                ctrl.parm(name).set(0.0)
            hou.setFrame(saved)
    check("2 set_keyframes is atomic, frame-based, and summarized", t2)

    controller = geo.createNode("null", "rig_controller")

    def t3():
        result = H.create_spare_parms(controller, spec=[{
            "type": "folder",
            "name": "rig_controls",
            "label": "Rig Controls",
            "parms": [
                {"type": "float", "name": "gain", "label": "Gain", "default": 0.5, "min": 0, "max": 1},
                {"type": "int", "name": "steps", "default": 4, "min": 1, "max": 16},
                {"type": "toggle", "name": "enabled", "default": True},
                {"type": "string", "name": "label", "default": "rig"},
            ],
        }])
        assert result["mode"] == "spec", result
        assert result["leaf_values"] == {
            "gain": 0.5, "steps": 4, "enabled": 1, "label": "rig"
        }, result
        try:
            H.create_spare_parms(controller, spec=[{
                "type": "float", "name": "gain", "default": 1.0,
            }])
        except ValueError as error:
            assert "已存在" in str(error), error
        else:
            raise AssertionError("controller spec overwrote an existing parm")
    check("3 create_spare_parms spec builds a safe controller interface", t3)

    skeleton = geo.createNode("python", "rest_skeleton")
    skeleton.parm("python").set(SKELETON_CODE)

    skin = geo.createNode("box", "rest_skin")
    skin.parmTuple("size").set((0.45, 2.4, 0.45))
    skin.parmTuple("t").set((0.0, 1.0, 0.0))

    rig_pose = H.tab_create(
        geo,
        "kinefx::rigpose",
        name="animated_pose",
        inputs=[skeleton],
    )
    rig_pose.parm("transformations").set(1)
    rig_pose.parm("group0").set("@name=mid")
    rig_pose.parm("mode0").set("pre")
    rig_pose.parm("r0z").setExpression("($F-1)*4.5", hou.exprLanguage.Hscript)

    capture = H.tab_create(
        geo,
        "kinefx::jointcaptureproximity",
        name="capture_skin",
        inputs=[skin, skeleton],
    )
    capture.parm("maxinfluences").set(2)

    deform = H.tab_create(
        geo,
        "kinefx::jointdeform",
        name="deformed_skin",
        inputs=[capture, skeleton, rig_pose],
    )

    def t2():
        try:
            skeleton.cook(force=True)
        except hou.Error:
            print("      skeleton cook:", skeleton.errors(), skeleton.warnings())
            raise
        if skeleton.errors() or skeleton.warnings():
            print("      skeleton cook:", skeleton.errors(), skeleton.warnings())
        assert not skeleton.errors() and not skeleton.warnings(), (
            skeleton.errors(), skeleton.warnings()
        )
        rest_geo = skeleton.geometry()
        assert rest_geo is not None
        assert len(rest_geo.points()) == 3, len(rest_geo.points())
        assert len(rest_geo.prims()) == 2, len(rest_geo.prims())
        assert {point.attribValue("name") for point in rest_geo.points()} == {
            "root", "mid", "tip"
        }
        assert rest_geo.findPointAttrib("transform") is not None
    check("4 KineFX skeleton has stable names, topology, and transforms", t2)

    def t3():
        captured = capture.geometry()
        bone_capture = captured.findPointAttrib("boneCapture")
        assert bone_capture is not None, [attrib.name() for attrib in captured.pointAttribs()]
        assert not capture.errors() and not capture.warnings(), (
            capture.errors(), capture.warnings()
        )
    check("5 Joint Capture Proximity creates boneCapture", t3)

    def t4():
        frame_one = rig_pose.geometryAtFrame(1)
        frame_eleven = rig_pose.geometryAtFrame(11)
        p1 = {point.attribValue("name"): point.position() for point in frame_one.points()}
        p11 = {point.attribValue("name"): point.position() for point in frame_eleven.points()}
        assert (p1["root"] - p11["root"]).length() < 1e-6
        assert (p1["mid"] - p11["mid"]).length() < 1e-6
        assert (p1["tip"] - p11["tip"]).length() > 0.1, (p1["tip"], p11["tip"])
        transform_diff = H.geo_frame_diff(
            rig_pose, 1, 11, attrib="transform", sample=16
        )
        assert transform_diff["comparable"] and transform_diff["max_delta"] > 0.1
    check("6 Rig Pose changes child pose while preserving parent joints", t4)

    def t5():
        saved = hou.frame()
        diff = H.geo_frame_diff(deform, 1, 11, sample=256)
        assert diff["comparable"] and diff["max_delta"] > 0.1, diff
        assert diff["unchanged_pct"] < 100.0, diff
        assert not deform.errors() and not deform.warnings(), (
            deform.errors(), deform.warnings()
        )
        assert hou.frame() == saved
    check("7 Joint Deform produces time-varying captured skin", t5)

finally:
    for node in (ctrl, geo):
        if node is not None:
            try:
                node.destroy()
            except Exception:
                pass


print()
print("FAILED:" if failures else "ALL PASS", failures if failures else "")
sys.exit(1 if failures else 0)
