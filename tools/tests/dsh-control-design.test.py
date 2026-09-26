"""Few independent dimensions must still keep actual body/accessory contacts.

An abstract adjustable plate, end cap and surface attachment exercise shared
derived coordinates. This tests the existing measurement/restore mechanism,
not an LLM's design choices, arbitrary collision freedom or visual quality.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_quality_contracts as q


def interval(value):
    return [value - 0.0001, value + 0.0001]


def case(name, length=2.0, width=1.0):
    values = {key: value for key, value, baseline in
              [('length', length, 2.0), ('width', width, 1.0)] if value != baseline}
    return {'id': name, 'values': values, 'expectations': [
        {'metric': 'bounds_size', 'group': 'plate', 'axis': 0,
         'delta': interval(length - 2)},
        {'metric': 'bounds_size', 'group': 'plate', 'axis': 2,
         'delta': interval(width - 1)},
        {'metric': 'bounds_size', 'group': 'plate', 'axis': 1,
         'delta': interval(0), 'range': interval(0.2)},
        {'metric': 'bounds_center', 'group': 'cap', 'axis': 0,
         'delta': interval(length - 2)},
        {'metric': 'bounds_center', 'group': 'attachment', 'axis': 2,
         'delta': interval((width - 1) / 2)},
    ]}


with h._execution_owner('control-design-fixture', 'isolated-test'):
    root = h.tab_create('/obj', 'geo', '__control_design')
    try:
        ctrl = h.tab_create(root, 'null', 'CTRL')
        h.create_spare_parms(ctrl, spec=[
            {'type': 'float', 'name': 'length', 'default': 2.0},
            {'type': 'float', 'name': 'width', 'default': 1.0},
        ])
        derived = h.tab_create(root, 'null', 'DESIGN')
        h.create_spare_parms(derived, spec=[
            {'type': 'float', 'name': 'end_x', 'default': 0.0},
            {'type': 'float', 'name': 'half_width', 'default': 0.0},
        ])
        h.set_parm(derived, 'end_x', "ch('../CTRL/length')")
        h.set_parm(derived, 'half_width', "ch('../CTRL/width')/2")
        specs = [
            {'name': 'plate_shape', 'type': 'box', 'parms': {
                'sizex': "ch('../DESIGN/end_x')", 'sizey': 0.2,
                'sizez': "2*ch('../DESIGN/half_width')",
                'tx': "ch('../DESIGN/end_x')/2", 'ty': 0.1}},
            {'name': 'plate_tag', 'type': 'attribwrangle', 'inputs': ['plate_shape'],
             'parms': {'class': 'primitive', 'snippet': 'i@group_plate=1; s@part="plate";'}},
            {'name': 'cap_shape', 'type': 'box', 'parms': {
                'sizex': 0.2, 'sizey': 0.2, 'sizez': "2*ch('../DESIGN/half_width')",
                'tx': "ch('../DESIGN/end_x')+0.1", 'ty': 0.1}},
            {'name': 'cap_tag', 'type': 'attribwrangle', 'inputs': ['cap_shape'],
             'parms': {'class': 'primitive', 'snippet': 'i@group_cap=1; s@part="cap";'}},
            {'name': 'cap_port', 'type': 'attribwrangle', 'inputs': ['cap_tag'],
             'parms': {'class': 'point', 'snippet':
                       'if(@P.x < getbbox_center(0).x) i@group_cap_port=1;'}},
            {'name': 'attachment_shape', 'type': 'box', 'parms': {
                'sizex': 0.1, 'sizey': 0.1, 'sizez': 0.1,
                'tx': "ch('../DESIGN/end_x')-0.2", 'ty': 0.25,
                'tz': "ch('../DESIGN/half_width')-0.15"}},
            {'name': 'attachment_tag', 'type': 'attribwrangle', 'inputs': ['attachment_shape'],
             'parms': {'class': 'primitive', 'snippet':
                       'i@group_attachment=1; s@part="attachment";'}},
            {'name': 'attachment_port', 'type': 'attribwrangle', 'inputs': ['attachment_tag'],
             'parms': {'class': 'point', 'snippet':
                       'if(@P.y < getbbox_center(0).y) i@group_attachment_port=1;'}},
            {'name': 'assembly', 'type': 'merge',
             'inputs': ['plate_tag', 'cap_port', 'attachment_port']},
            {'name': 'OUT', 'type': 'null', 'inputs': ['assembly']},
        ]
        interfaces = [
            {'id': 'cap_contact', 'source_group': 'cap_port', 'target_group': 'plate',
             'expected_points': 4, 'max_distance': 0.0001},
            {'id': 'attachment_contact', 'source_group': 'attachment_port', 'target_group': 'plate',
             'expected_points': 4, 'max_distance': 0.0001},
        ]
        h.build_module(root, specs, output='OUT', interfaces=interfaces)
        out = root.node('OUT')
        assert {p.attribValue('part') for p in out.geometry().prims()} == {'plate', 'cap', 'attachment'}
        tests = [case('length_only', length=2.4), case('width_only', width=1.4),
                 case('short_narrow', length=1.2, width=0.5),
                 case('long_wide', length=2.8, width=1.6)]
        domain = [
            {'id': 'minimum_length', 'left': 'length', 'op': 'ge', 'right': 1.2},
            {'id': 'maximum_length', 'left': 'length', 'op': 'le', 'right': 2.8},
            {'id': 'minimum_width', 'left': 'width', 'op': 'ge', 'right': 0.5},
            {'id': 'maximum_width', 'left': 'width', 'op': 'le', 'right': 1.6},
        ]
        signature = q._data_signature(out.geometry())
        frame = hou.frame()
        positive = h.test_controls(ctrl, out, tests, interfaces=interfaces, domain=domain)
        assert positive['ok'] and positive['restored'], positive
        assert positive['control_summary']['case_counts']['pass'] == 4, positive
        assert positive['control_summary']['coverage']['executed_interface_checks'] == 10, positive
        assert ctrl.evalParm('length') == 2 and ctrl.evalParm('width') == 1
        assert derived.parm('end_x').expression() == "ch('../CTRL/length')"
        assert derived.parm('half_width').expression() == "ch('../CTRL/width')/2"
        assert hou.frame() == frame and q._data_signature(out.geometry()) == signature

        # Freeze only the small attachment. Body dimensions and both public
        # controls still respond, and the default contact remains correct.
        h.set_parm(root.node('attachment_shape'), 'tz', 0.35)
        assert h.geo_check_interfaces(out, interfaces)['ok']
        broken_signature = q._data_signature(out.geometry())
        body_only = [{**tests[2], 'expectations': tests[2]['expectations'][:3]}]
        narrow = h.test_controls(ctrl, out, body_only, domain=domain)
        assert narrow['ok'] and narrow['restored'], narrow
        assert narrow['control_summary']['coverage']['relationship_scope'] == 'not_checked'
        checked = h.test_controls(ctrl, out, body_only, interfaces=interfaces, domain=domain)
        assert checked['status'] == 'fail' and checked['restored'], checked
        row = checked['results'][0]
        assert all(item['pass'] for item in row['measurements']), row
        contacts = {item['id']: item['status'] for item in row['interfaces']['results']}
        assert contacts == {'cap_contact': 'pass', 'attachment_contact': 'fail'}, contacts
        assert ctrl.evalParm('length') == 2 and ctrl.evalParm('width') == 1
        assert hou.frame() == frame and q._data_signature(out.geometry()) == broken_signature

        # Restore the shared source, then recertify the same failed combination.
        h.set_parm(root.node('attachment_shape'), 'tz', "ch('../DESIGN/half_width')-0.15")
        repaired = h.test_controls(ctrl, out, [tests[2]], interfaces=interfaces, domain=domain)
        assert repaired['ok'] and repaired['restored'], repaired
        assert q._data_signature(out.geometry()) == signature
    finally:
        root.destroy()

print('control design: shared derived coordinates, four scalar/combined cases, '
      'missed accessory contact and exact restoration passed on ' + hou.applicationVersionString())
