"""H21/H22 regression for ordered rigid-piece animation state.

Run with hython. Builds a disposable packed-piece network containing both:

1. a correct ordered R -> U -> U^-1 -> R^-1 evaluator that updates logical
   membership after each completed move; and
2. the rejected initial-membership/independent-channel model from trace
   a41c853a.

The scene is never saved and every disposable node is removed.
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


PROBE = "dsh_rig_state_regress"
failures = []


def check(label, fn):
    try:
        fn()
        print(f"PASS  {label}")
    except Exception as error:
        failures.append(label)
        print(f"FAIL  {label}: {type(error).__name__}: {str(error)[:1000]}")


REST_CODE = textwrap.dedent(
    r'''
    geo = hou.pwd().geometry()
    name_attrib = geo.addAttrib(hou.attribType.Point, "name", "")
    ix_attrib = geo.addAttrib(hou.attribType.Point, "ix", 0)
    iy_attrib = geo.addAttrib(hou.attribType.Point, "iy", 0)
    iz_attrib = geo.addAttrib(hou.attribType.Point, "iz", 0)
    for ix in (-1, 0, 1):
        for iy in (-1, 0, 1):
            for iz in (-1, 0, 1):
                point = geo.createPoint()
                point.setPosition((ix, iy, iz))
                point.setAttribValue(name_attrib, "piece_%d_%d_%d" % (ix, iy, iz))
                point.setAttribValue(ix_attrib, ix)
                point.setAttribValue(iy_attrib, iy)
                point.setAttribValue(iz_attrib, iz)
    '''
).strip()


CORRECT_CODE = textwrap.dedent(
    r'''
    geo = hou.pwd().geometry()
    frame = float(hou.frame())
    name_attrib = geo.addAttrib(hou.attribType.Point, "name", "")
    orient_attrib = geo.addAttrib(hou.attribType.Point, "orient", (0.0, 0.0, 0.0, 1.0))
    ix_attrib = geo.addAttrib(hou.attribType.Point, "ix", 0)
    iy_attrib = geo.addAttrib(hou.attribType.Point, "iy", 0)
    iz_attrib = geo.addAttrib(hou.attribType.Point, "iz", 0)
    lx_attrib = geo.addAttrib(hou.attribType.Point, "lx", 0)
    ly_attrib = geo.addAttrib(hou.attribType.Point, "ly", 0)
    lz_attrib = geo.addAttrib(hou.attribType.Point, "lz", 0)

    moves = (
        # axis index, side, axis vector, degrees, start, end
        (0, 1, (1, 0, 0),  90.0, 10.0, 20.0),  # R
        (1, 1, (0, 1, 0),  90.0, 20.0, 30.0),  # U in the state after R
        (1, 1, (0, 1, 0), -90.0, 30.0, 40.0),  # U inverse
        (0, 1, (1, 0, 0), -90.0, 40.0, 50.0),  # R inverse
    )

    def rotation(axis, degrees):
        return hou.hmath.buildRotateAboutAxis(hou.Vector3(axis), degrees)

    for ix in (-1, 0, 1):
        for iy in (-1, 0, 1):
            for iz in (-1, 0, 1):
                logical = [ix, iy, iz]
                position = hou.Vector3(ix, iy, iz)
                orient = hou.Matrix3(1)
                for axis_index, side, axis, degrees, start, end in moves:
                    selected = logical[axis_index] == side
                    if frame >= end:
                        if selected:
                            matrix4 = rotation(axis, degrees)
                            position = position * matrix4
                            orient = orient * matrix4.extractRotationMatrix3()
                            logical = [int(round(value)) for value in position]
                        continue
                    if frame <= start:
                        break
                    if selected:
                        amount = (frame - start) / (end - start)
                        matrix4 = rotation(axis, degrees * amount)
                        position = position * matrix4
                        orient = orient * matrix4.extractRotationMatrix3()
                    break

                point = geo.createPoint()
                point.setPosition(position)
                point.setAttribValue(name_attrib, "piece_%d_%d_%d" % (ix, iy, iz))
                point.setAttribValue(orient_attrib, tuple(hou.Quaternion(orient)))
                point.setAttribValue(ix_attrib, ix)
                point.setAttribValue(iy_attrib, iy)
                point.setAttribValue(iz_attrib, iz)
                point.setAttribValue(lx_attrib, logical[0])
                point.setAttribValue(ly_attrib, logical[1])
                point.setAttribValue(lz_attrib, logical[2])
    '''
).strip()


NAIVE_CODE = textwrap.dedent(
    r'''
    geo = hou.pwd().geometry()
    frame = float(hou.frame())
    name_attrib = geo.addAttrib(hou.attribType.Point, "name", "")
    orient_attrib = geo.addAttrib(hou.attribType.Point, "orient", (0.0, 0.0, 0.0, 1.0))
    ix_attrib = geo.addAttrib(hou.attribType.Point, "ix", 0)
    iy_attrib = geo.addAttrib(hou.attribType.Point, "iy", 0)
    iz_attrib = geo.addAttrib(hou.attribType.Point, "iz", 0)
    lx_attrib = geo.addAttrib(hou.attribType.Point, "lx", 0)
    ly_attrib = geo.addAttrib(hou.attribType.Point, "ly", 0)
    lz_attrib = geo.addAttrib(hou.attribType.Point, "lz", 0)

    def ramp(start, end, value_a, value_b):
        if frame <= start:
            return value_a
        if frame >= end:
            return value_b
        amount = (frame - start) / (end - start)
        return value_a + (value_b - value_a) * amount

    # Independent absolute channels: R holds while U rises/falls, then R returns.
    r_angle = ramp(10.0, 20.0, 0.0, 90.0)
    if frame >= 40.0:
        r_angle = ramp(40.0, 50.0, 90.0, 0.0)
    u_angle = ramp(20.0, 30.0, 0.0, 90.0)
    if frame >= 30.0:
        u_angle = ramp(30.0, 40.0, 90.0, 0.0)

    for ix in (-1, 0, 1):
        for iy in (-1, 0, 1):
            for iz in (-1, 0, 1):
                orient = hou.Matrix3(1)
                position = hou.Vector3(ix, iy, iz)
                if ix == 1:
                    matrix4 = hou.hmath.buildRotateAboutAxis(hou.Vector3(1, 0, 0), r_angle)
                    position = position * matrix4
                    orient = orient * matrix4.extractRotationMatrix3()
                if iy == 1:
                    matrix4 = hou.hmath.buildRotateAboutAxis(hou.Vector3(0, 1, 0), u_angle)
                    position = position * matrix4
                    orient = orient * matrix4.extractRotationMatrix3()

                point = geo.createPoint()
                point.setPosition(position)
                point.setAttribValue(name_attrib, "piece_%d_%d_%d" % (ix, iy, iz))
                point.setAttribValue(orient_attrib, tuple(hou.Quaternion(orient)))
                point.setAttribValue(ix_attrib, ix)
                point.setAttribValue(iy_attrib, iy)
                point.setAttribValue(iz_attrib, iz)
                # The rejected model never updates logical membership.
                point.setAttribValue(lx_attrib, ix)
                point.setAttribValue(ly_attrib, iy)
                point.setAttribValue(lz_attrib, iz)
    '''
).strip()


def points_by_name(node, frame):
    geometry = node.geometryAtFrame(frame)
    return {
        point.attribValue("name"): {
            "P": tuple(float(value) for value in point.position()),
            "orient": tuple(float(value) for value in point.attribValue("orient")),
            "logical": (
                int(point.attribValue("lx")),
                int(point.attribValue("ly")),
                int(point.attribValue("lz")),
            ),
            "initial": (
                int(point.attribValue("ix")),
                int(point.attribValue("iy")),
                int(point.attribValue("iz")),
            ),
        }
        for point in geometry.points()
    }


def changed_names(node, frame_a, frame_b, tolerance=1e-6):
    first = points_by_name(node, frame_a)
    second = points_by_name(node, frame_b)
    changed = set()
    for name in first:
        delta = hou.Vector3(first[name]["P"]) - hou.Vector3(second[name]["P"])
        orient_a = hou.Vector4(first[name]["orient"])
        orient_b = hou.Vector4(second[name]["orient"])
        # q and -q encode the same orientation, so compare the smaller distance.
        orient_delta = min(
            (orient_a - orient_b).length(),
            (orient_a + orient_b).length(),
        )
        if delta.length() > tolerance or orient_delta > tolerance:
            changed.add(name)
    return changed


container = None
try:
    obj = hou.node("/obj")
    old = obj.node(PROBE)
    if old is not None:
        old.destroy()
    container = obj.createNode("geo", PROBE)
    for child in container.children():
        child.destroy()

    box = container.createNode("box", "piece_shape")
    box.parmTuple("size").set((0.82, 0.82, 0.82))

    rest = container.createNode("python", "rest_points")
    rest.parm("python").set(REST_CODE)

    copies = H.tab_create(
        container,
        "copytopoints",
        name="packed_pieces",
        inputs=[box, rest],
    )
    copies.parm("pack").set(1)

    named_pieces = H.tab_create(
        container,
        "attribcopy",
        name="named_packed_pieces",
        inputs=[copies, rest],
    )
    named_pieces.parm("attribname").set("name")
    named_pieces.parm("copyp").set(0)

    correct_state = container.createNode("python", "correct_ordered_state")
    correct_state.parm("python").set(CORRECT_CODE)
    naive_state = container.createNode("python", "naive_absolute_channels")
    naive_state.parm("python").set(NAIVE_CODE)

    correct = container.createNode("xformpieces", "correct_transform_pieces")
    correct.setInput(0, named_pieces)
    correct.setInput(1, correct_state)
    correct.setInput(2, rest)
    correct.parm("attribmode").set(1)
    correct.parm("attrib").set("name")

    naive = container.createNode("xformpieces", "naive_transform_pieces")
    naive.setInput(0, named_pieces)
    naive.setInput(1, naive_state)
    naive.setInput(2, rest)
    naive.parm("attribmode").set(1)
    naive.parm("attrib").set("name")

    def t1():
        packed = named_pieces.geometry()
        point_attribs = {attrib.name() for attrib in packed.pointAttribs()}
        prim_attribs = {attrib.name() for attrib in packed.primAttribs()}
        print("      packed attrs:", sorted(point_attribs), sorted(prim_attribs))
        assert len(packed.prims()) == 27, len(packed.prims())
        assert all(primitive.type().name() == "PackedGeometry" for primitive in packed.prims())
        if "name" in prim_attribs:
            names = {primitive.attribValue("name") for primitive in packed.prims()}
        elif "name" in point_attribs:
            names = {primitive.points()[0].attribValue("name") for primitive in packed.prims()}
        else:
            raise AssertionError("packed Copy to Points output has no name attribute")
        assert len(names) == 27, names
        assert not named_pieces.errors() and not named_pieces.warnings(), (
            named_pieces.errors(), named_pieces.warnings()
        )
    check("1 Copy to Points produces 27 named packed pieces", t1)

    def t2():
        rest_data = points_by_name(correct_state, 1)
        after_r = points_by_name(correct_state, 20)
        initial_u = {name for name, item in rest_data.items() if item["initial"][1] == 1}
        current_u = {name for name, item in after_r.items() if item["logical"][1] == 1}
        assert len(initial_u) == 9 and len(current_u) == 9
        assert current_u != initial_u, (initial_u, current_u)
        assert len(initial_u.symmetric_difference(current_u)) > 0
    check("2 R updates logical membership before U selection", t2)

    def t3():
        correct_u = changed_names(correct_state, 20, 25)
        naive_u = changed_names(naive_state, 20, 25)
        expected = {
            name for name, item in points_by_name(correct_state, 20).items()
            if item["logical"][1] == 1
        }
        initial = {
            name for name, item in points_by_name(naive_state, 20).items()
            if item["initial"][1] == 1
        }
        assert correct_u == expected, (correct_u, expected)
        assert naive_u == initial, (naive_u, initial)
        assert correct_u != naive_u
    check("3 correct and rejected U active sets diverge", t3)

    def t4():
        correct_data = points_by_name(correct_state, 30)
        naive_data = points_by_name(naive_state, 30)
        differences = []
        for name in correct_data:
            p_correct = hou.Vector3(correct_data[name]["P"])
            p_naive = hou.Vector3(naive_data[name]["P"])
            if (p_correct - p_naive).length() > 1e-6:
                differences.append(name)
        assert differences, "R->U sequence did not separate the models"
    check("4 ordered R->U state differs from absolute channels", t4)

    def t5():
        for node in (correct_state, naive_state):
            start = points_by_name(node, 1)
            end = points_by_name(node, 50)
            assert start.keys() == end.keys()
            for name in start:
                assert (hou.Vector3(start[name]["P"]) - hou.Vector3(end[name]["P"])).length() < 1e-6
        # Both models returning to rest proves why endpoint equality alone is non-diagnostic.
    check("5 both models return to rest, so endpoint equality is insufficient", t5)

    def t6():
        mid = H.geo_frame_diff(correct, 20, 25, sample=128)
        orient_mid = H.geo_frame_diff(correct_state, 20, 25, attrib="orient", sample=128)
        loop = H.geo_frame_diff(correct, 1, 50, sample=128)
        # P sees eight translations; the ninth U face-center piece rotates in place.
        assert mid["comparable"] and 68.0 <= mid["unchanged_pct"] <= 72.0, mid
        assert mid["max_delta"] > 0.1, mid
        assert orient_mid["comparable"], orient_mid
        assert 65.0 <= orient_mid["unchanged_pct"] <= 68.0, orient_mid
        assert orient_mid["max_delta"] > 0.1, orient_mid
        assert loop["max_delta"] == 0.0 and loop["unchanged_pct"] == 100.0, loop
        for node in (correct, naive):
            node.cook(force=True)
            assert not node.errors() and not node.warnings(), (node.path(), node.errors(), node.warnings())
            geometry = node.geometryAtFrame(30)
            assert len(geometry.prims()) == 27, len(geometry.prims())
            assert all(primitive.type().name() == "PackedGeometry" for primitive in geometry.prims())
    check("6 Transform Pieces cooks packed rigid states and frame diff", t6)

finally:
    if container is not None:
        try:
            container.destroy()
        except Exception:
            pass


print()
print("FAILED:" if failures else "ALL PASS", failures if failures else "")
sys.exit(1 if failures else 0)
