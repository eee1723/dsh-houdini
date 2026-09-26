"""H21/H22: final selected physical extent and reversible control checks.

Run only in a fresh, isolated hython scene. No existing HIP is opened.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))

import hou
import dsh_hou_helpers as h
import dsh_quality_contracts as q
from dsh_context import unit_length_meters


def contract(expected_mm=160, group='part', identity='rail_length'):
    return {'id': identity, 'method': 'physical_extent', 'target_group': group,
            'axis': 2, 'expected_mm': expected_mm, 'tolerance_mm': .01}


original_unit = unit_length_meters()
assert original_unit is not None and original_unit > 0
root = h.tab_create('/obj', 'geo', '__physical_extent_fixture')
try:
    ctrl = root.createNode('null', 'CTRL')
    h.create_spare_parms(ctrl, spec=[{'type': 'float', 'name': 'length', 'default': .16}])
    body = root.createNode('box', 'body')
    body.parm('sizex').set(.02)
    body.parm('sizey').set(.02)
    body.parm('sizez').setExpression('ch("../CTRL/length")')
    tag = root.createNode('attribwrangle', 'tag_final_part')
    tag.setInput(0, body)
    tag.parm('class').set('primitive')
    tag.parm('snippet').set('i@group_part=1;')
    out = root.createNode('null', 'OUT_ASSET')
    out.setInput(0, tag)

    # Both HIP length scales measure the selected final part in millimeters.
    hou.hscript('unitlength 1')
    metres = h.geo_check_interfaces(out, [contract()])
    assert metres['status'] == 'pass' and abs(metres['results'][0]['observed_mm'] - 160) < .01, metres
    assert abs(metres['results'][0]['scene_unit_length_meters'] - 1) < 1e-12, metres
    assert metres['output'] == out.path() and metres['geometry_sha256'], metres
    assert h.geo_check_interfaces(out, [contract(group='missing')])['status'] == 'fail'

    ctrl.parm('length').set(160)
    hou.hscript('unitlength 0.001')
    millimetres = h.geo_check_interfaces(out, [contract()])
    assert millimetres['status'] == 'pass' and abs(millimetres['results'][0]['observed_mm'] - 160) < .01, millimetres
    assert abs(millimetres['results'][0]['scene_unit_length_meters'] - .001) < 1e-12, millimetres

    # A numeric span of 160 with a metres-per-unit scene is 160000 mm.
    hou.hscript('unitlength 1')
    thousandfold = h.geo_check_interfaces(out, [contract()])
    row = thousandfold['results'][0]
    assert thousandfold['status'] == 'fail' and abs(row['observed_mm'] - 160000) < .1, thousandfold
    assert abs(row['delta_mm'] - 159840) < .1, thousandfold
    ctrl.parm('length').set(.16)

    # A generic native surface and an open Polygon are not certified by bounds.
    tube = root.createNode('tube', 'native_tube')
    tube_tag = root.createNode('attribwrangle', 'tag_native')
    tube_tag.setInput(0, tube)
    tube_tag.parm('class').set('primitive')
    tube_tag.parm('snippet').set('i@group_part=1;')
    assert any(p.type() != hou.primType.Polygon for p in tube_tag.geometry().prims())
    assert h.geo_check_interfaces(tube_tag, [contract()])['status'] == 'unverified'

    line = root.createNode('line', 'open_line')
    line_tag = root.createNode('attribwrangle', 'tag_open')
    line_tag.setInput(0, line)
    line_tag.parm('class').set('primitive')
    line_tag.parm('snippet').set('i@group_part=1;')
    assert any(p.type() == hou.primType.Polygon and not p.intrinsicValue('closed')
               for p in line_tag.geometry().prims())
    assert h.geo_check_interfaces(line_tag, [contract()])['status'] == 'unverified'

    # SOP-local units cannot be reported as world dimensions after OBJ scale.
    root.parm('sx').set(2)
    transformed = h.geo_check_interfaces(out, [contract()])
    assert transformed['status'] == 'unverified', transformed
    assert transformed['results'][0]['reason'] == 'object_transform_requires_world_space_review', transformed
    root.parm('sx').set(1)

    # Control tests apply a baseline contract and a distinct case contract,
    # then restore the parameter and the exact final geometry.
    baseline = contract()
    case = contract(180, identity='rail_length_after_control')
    test = [{'id': 'length_180mm', 'values': {'length': .18},
             'expectations': [{'metric': 'bounds_size', 'axis': 2, 'delta': [.0199, .0201]}],
             'interfaces': [case]}]
    signature = q._data_signature(out.geometry())
    tested = h.test_controls(ctrl, out, test, baseline_interfaces=[baseline])
    assert tested['status'] == 'pass' and tested['restored'], tested
    assert tested['baseline_interfaces']['status'] == 'pass', tested
    assert tested['results'][0]['interfaces']['status'] == 'pass', tested
    assert ctrl.evalParm('length') == .16 and q._data_signature(out.geometry()) == signature, tested

    wrong_case = [{**test[0], 'interfaces': [contract(160, identity='wrong_case_mm')]}]
    failed_case = h.test_controls(ctrl, out, wrong_case, baseline_interfaces=[baseline])
    assert failed_case['status'] == 'fail' and failed_case['restored'], failed_case
    assert failed_case['results'][0]['interfaces']['status'] == 'fail', failed_case
    assert ctrl.evalParm('length') == .16 and q._data_signature(out.geometry()) == signature, failed_case

    wrong_baseline = h.test_controls(ctrl, out, test, baseline_interfaces=[contract(180)])
    assert wrong_baseline['status'] == 'fail' and wrong_baseline['parameter_writes'] == 0, wrong_baseline
    assert wrong_baseline['results'] == [] and ctrl.evalParm('length') == .16, wrong_baseline

    # A later additive/deform stage invalidates the previous output receipt.
    late = root.createNode('xform', 'later_edit')
    late.setInput(0, tag)
    late.parm('sz').set(2)
    out.setInput(0, late)
    after = h.geo_check_interfaces(out, [contract()])
    assert after['status'] == 'fail' and abs(after['results'][0]['observed_mm'] - 320) < .01, after
    assert after['geometry_sha256'] != metres['geometry_sha256'], after
    print('physical_extent final-group/unit/control/late-edit checks passed:', hou.applicationVersionString())
finally:
    hou.hscript('unitlength ' + str(original_unit))
    root.destroy()
