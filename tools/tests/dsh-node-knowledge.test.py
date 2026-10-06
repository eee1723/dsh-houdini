"""H21/H22 isolated HOM: node knowledge, real geometry and metadata transport.

No live connection, HIP load/save or rendering. Defaults use direct creation;
the separate stool-repair regression exercises the actual Sweep shelf script.
"""
from pathlib import Path
import math
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as bridge
import dsh_operation_cards as cards
from dsh_geometry_observation import polygon_observation

root = hou.node('/obj').createNode('geo', 'node_knowledge_fixture')
checks = []


def done(label):
    checks.append(label)


def make(typ, name, parms=None, inputs=None):
    node = root.createNode(typ, name)
    for i, source in enumerate(inputs or []):
        if source is not None:
            node.setInput(i, source)
    if parms:
        h.set_parms(node, parms)
    return node


def observed(node):
    result = h.geo_piece_stats(node, inspect=True)
    assert not node.errors(), node.errors()
    return result


def positions(node):
    return {tuple(round(v, 6) for v in p.position()) for p in node.geometry().points()}


try:
    # Critical fields survive unrelated filters and limit=1; no scratch/cook.
    before = set(root.children())
    families = ('sweep', 'polyextrude', 'polybevel', 'sphere', 'tube', 'circle', 'box',
                'revolve', 'normal', 'reverse', 'attribwrangle', 'object_merge', 'boolean',
                'mirror', 'bend', 'skin', 'pathdeform')
    for family in families:
        info = h.node_info(root, family, parm_filter='no_such_filter', limit=1)
        assert info['parameter_count'] == 0 and not info['parameters']
        assert info['operation_parameters'] and not info['operation_parameters_missing'], info
        actual = make(info['type'], 'template_' + family)
        for setting in info['operation_parameters']:
            actual_tuple = actual.parmTuple(setting['name'])
            assert actual_tuple is not None, setting
            assert setting['size'] == len(actual_tuple), setting
            assert setting['components'] == [p.name() for p in actual_tuple], setting
            if setting.get('menu') and not setting.get('menu_dynamic'):
                assert {m['token'] for m in setting['menu']} == set(actual.parm(setting['name']).menuItems())
        actual.destroy()
    assert h.node_info(root, 'box', parm_filter='size')['filter'] == 'size'
    assert set(root.children()) == before
    resolved = h.node_info(root, 'polybevel', limit=1)
    assert resolved['requested_type'] == 'polybevel'
    assert resolved['type'] == h.resolve_latest_type(hou.sopNodeTypeCategory(), 'polybevel')
    # Failed discovery reports the actual network and real visible candidates;
    # no guessed aliases, implicit type replacement or scratch nodes.
    for requested in ('tube::999.0', 'polybevl'):
        try:
            h.node_info(root, requested)
        except ValueError as error:
            message = str(error)
            expected = 'tube' if requested.startswith('tube') else 'polybevel'
            assert root.path() in message and 'Sop' in message and expected in message, message
            assert 'search_tab_entries' in message and 'not replacements' in message, message
        else:
            raise AssertionError('invalid node type accepted: ' + requested)
    for row in h._node_type_suggestions(hou.sopNodeTypeCategory(), 'polybevl'):
        typ = hou.nodeType(hou.sopNodeTypeCategory(), row['type'])
        assert typ is not None and h._visible_node_type(typ), row
    leaf = make('null', 'discovery_leaf')
    try:
        h.node_info(leaf, 'box')
    except ValueError as error:
        assert 'not a network' in str(error) and root.path() in str(error), str(error)
    else:
        raise AssertionError('leaf accepted as node creation network')
    leaf.destroy()
    assert set(root.children()) == before
    # MaxMin is another built-in naming scheme not exposed by the SOP cards.
    legacy_cop = root.createNode('cop2net', 'tuple_naming_fixture', run_init_scripts=False)
    try:
        mapping = legacy_cop.createNode('colormap', run_init_scripts=False)
        actual_tuple = mapping.parmTuple('from')
        card = h._parm_template_card(actual_tuple.parmTemplate())
        assert card['size'] == len(actual_tuple) == 2, card
        assert card['components'] == [p.name() for p in actual_tuple] == ['frommax', 'frommin'], card
    finally:
        legacy_cop.destroy()
    assert cards.operation_card('polybevel::2.0') is None
    assert cards.operation_card('sweep::99.0') is None
    assert cards.operation_card('revolve::99.0') is None
    assert cards.operation_card('custom::sweep::2.0') is None
    detached = cards.operation_card('attribwrangle')
    detached['decisions'].clear()
    assert cards.operation_card('attribwrangle')['decisions'], 'cache must not be mutable by its consumer'
    done('runtime critical templates, filtering, version boundaries and cache isolation')

    # Cross-OBJ assembly must choose its transform space explicitly.  A path by
    # itself reads SOP-local geometry; Into This Object preserves the source OBJ
    # placement relative to the current network.
    source_obj = hou.node('/obj').createNode('geo', 'object_merge_source')
    source_obj.parm('tx').set(3)
    source_box = source_obj.createNode('box', 'shape')
    imported = make('object_merge', 'placed_import', {'objpath1': source_box.path(), 'xformtype': 0})
    local_center = imported.geometry().boundingBox().center()[0]
    h.set_parm(imported, 'xformtype', 1)
    world_center = imported.geometry().boundingBox().center()[0]
    assert abs(local_center) < 1e-6 and abs(world_center - 3) < 1e-6, (local_center, world_center)
    imported.destroy(); source_obj.destroy()
    done('Object Merge local-space counterexample and Into This Object placement')

    # Actual native and polygon output, not only parameter labels.
    for family in ('sphere', 'tube', 'circle'):
        native = make(family, 'native_' + family)
        assert native.parm('type').evalAsString() == 'prim'
        assert any(p.type() != hou.primType.Polygon for p in native.geometry().prims())
        poly = make(family, 'polygon_' + family, {'type': 'poly'})
        assert poly.geometry().prims() and all(p.type() == hou.primType.Polygon for p in poly.geometry().prims())
        if family == 'tube':
            assert observed(poly)['boundary_edges'] > 0
            h.set_parm(poly, 'cap', 1)
            assert observed(poly)['boundary_edges'] == 0
    box = make('box', 'solid')
    assert box.parm('type').evalAsString() == 'poly'
    assert len(box.geometry().prims()) == 6
    done('native/poly output and explicit tube closure; Box counterexample')

    # Mirror keeps copy choice and a confirmed seam separate. This fixture is an
    # intentionally open sheet, not a solid that should become watertight.
    half = make('grid', 'mirror_half', {'rows': 2, 'cols': 2, 'size': [1, 1], 't': [.5, 0, 0]})
    mirrored = make('mirror', 'editable_mirror', {'operation': 'all', 'dirtype': 'direction',
                    'origin': [0, 0, 0], 'dir': [1, 0, 0], 'keepOriginal': 1,
                    'consolidatepts': 0}, [half])
    assert len(mirrored.geometry().points()) == 8 and observed(mirrored)['boundary_edges'] == 8
    h.set_parm(mirrored, 'consolidatepts', 1)
    assert len(mirrored.geometry().points()) == 6 and observed(mirrored)['boundary_edges'] == 6
    h.set_parm(mirrored, 'keepOriginal', 0)
    assert len(mirrored.geometry().prims()) == 1
    assert {p[0] for p in positions(mirrored)} == {-1., 0.}
    h.set_parm(mirrored, 'keepOriginal', 1)
    h.set_parms(half, {'size': [2, 1], 't': [1, 0, 0]})
    assert {p[0] for p in positions(mirrored)} == {-2., 0., 2.}
    assert observed(mirrored)['boundary_edges'] == 6, 'source width edit retains the shared seam'
    # A full-width source crossing the plane is duplicated by all, not clipped.
    h.set_parm(half, 'tx', 0)
    assert len(mirrored.geometry().points()) == 8 and len(positions(mirrored)) == 4
    h.set_parm(mirrored, 'operation', 'clip')
    assert len(mirrored.geometry().points()) == len(positions(mirrored)) == 6
    assert observed(mirrored)['boundary_edges'] == 6
    done('Mirror copy versus replace, optional seam and upstream width edit; clip versus overlapping full source')

    # Bend moves existing points. It does not refine a two-point segment, infer the
    # capture axis, or enable Twist merely because a nonzero twist angle was set.
    spine = make('line', 'bend_spine', {'origin': [0, 0, 0], 'dir': [0, 0, 1], 'dist': 2, 'points': 2})
    deform = make('bend', 'editable_bend', {'origin': [0, 0, 0], 'dir': [0, 0, 1],
                  'upvectorcontrol': 'custom', 'up': [0, 1, 0], 'length': 2,
                  'bendmode': 'angle', 'bend': 90}, [spine])
    coarse = [p.position() for p in deform.geometry().points()]
    assert len(coarse) == 2
    assert (coarse[-1] - hou.Vector3(0, 4 / math.pi, 4 / math.pi)).length() < 1e-5
    h.set_parm(spine, 'points', 17)
    dense = [p.position() for p in deform.geometry().points()]
    assert len(dense) == 17 and (dense[-1] - coarse[-1]).length() < 1e-5
    assert (dense[8] - (coarse[0] + coarse[-1]) * .5).length() > .3
    h.set_parm(deform, 'bend', 45)
    assert deform.geometry().points()[-1].position()[2] > 1.8
    h.set_parms(deform, {'bend': 90, 'dir': [0, 1, 0], 'up': [1, 0, 0]})
    assert positions(deform) == positions(spine), 'points at the capture origin plane do not bend along the intended Z span'
    h.set_parms(deform, {'dir': [0, 0, 1], 'up': [0, 1, 0], 'length': 1, 'limit_deformation': 1})
    limited = [p.position() for p in deform.geometry().points()]
    assert abs(limited[-1][2] - 2 / math.pi) < 1e-5
    assert abs((limited[-1] - limited[8]).length() - 1) < 1e-5, 'outside span follows the end tangent rigidly'
    h.set_parm(deform, 'limit_deformation', 0)
    assert abs(deform.geometry().points()[-1].position()[2]) < 1e-5, 'unlimited bend continues curvature beyond capture end'
    h.set_parms(spine, {'origin': [1, 0, 0], 'points': 3})
    h.set_parms(deform, {'enablebend': 0, 'enabletwist': 0, 'twist': 90, 'length': 2, 'limit_deformation': 1})
    assert positions(deform) == positions(spine), 'inactive Twist value does not deform'
    h.set_parm(deform, 'enabletwist', 1)
    assert (deform.geometry().points()[-1].position() - hou.Vector3(0, 1, 2)).length() < 1e-5
    h.set_parm(deform, 'length', 4)
    assert (deform.geometry().points()[-1].position() - hou.Vector3(2**-.5, 2**-.5, 2)).length() < 1e-5
    h.set_parms(deform, {'length': 2, 'twist': 180})
    assert (deform.geometry().points()[-1].position() - hou.Vector3(-1, 0, 2)).length() < 1e-5
    h.set_parm(deform, 'originx', 1)
    assert positions(deform) == positions(spine), 'a point on the capture axis has no twist displacement'
    assert not deform.errors() and not mirrored.errors()
    done('Bend/Twist axis, sampled shape, enable state, capture limit and editable angle/length/origin')

    # Loft keeps editable section inputs. Correct topology/counts alone cannot
    # distinguish an ordered loft from a cooked, wrong-order connection.
    sections = [make('circle', 'loft_section_' + str(i),
                     {'type': 'poly', 'orient': 'xy', 'rad': [r, r],
                      't': [0, 0, i], 'divs': 12})
                for i, r in enumerate((.5, 1, .75))]
    section_stack = make('merge', 'loft_sections', inputs=sections)
    loft = make('skin', 'section_loft',
                {'keepshape': 1, 'polys': 1, 'surftype': 'quads',
                 'closev': 'nonewv', 'prim': 0}, [section_stack])
    assert len(loft.geometry().prims()) == 24
    assert all(p.type() == hou.primType.Polygon for p in loft.geometry().prims())
    assert observed(loft)['boundary_edges'] == 24
    assert positions(loft) == set().union(*(positions(s) for s in sections))
    old_ends = {p for p in positions(loft) if p[2] in (0, 2)}
    h.set_parm(sections[1], 'radx', 1.5)
    changed = positions(loft)
    assert {p for p in changed if p[2] in (0, 2)} == old_ends
    assert abs(max(abs(p[0]) for p in changed if p[2] == 1) - 1.5) < 1e-6
    assert changed == set().union(*(positions(s) for s in sections))
    def loft_z_spans():
        return [max(v.point().position()[2] for v in p.vertices())
                - min(v.point().position()[2] for v in p.vertices())
                for p in loft.geometry().prims()]
    assert max(loft_z_spans()) == 1
    section_stack.setInput(1, sections[2]); section_stack.setInput(2, sections[1])
    assert not loft.errors() and len(loft.geometry().prims()) == 24
    assert max(loft_z_spans()) == 2, 'wrong section order must remain an observed counterexample'
    section_stack.setInput(1, sections[1]); section_stack.setInput(2, sections[2])
    assert max(loft_z_spans()) == 1
    done('Skin ordered sections, local section edit and error-free wrong-order counterexample')

    # An asymmetric polygon solid makes source orientation/width/height
    # observable after bending. Its nine rings retain point correspondence.
    def fixture_point(geometry, position):
        point = geometry.createPoint(); point.setPosition(position)
        return point
    def fixture_stash(name, geometry):
        node = make('stash', name); node.parm('stash').set(geometry)
        return node
    straight = hou.Geometry()
    rings = [[fixture_point(straight, (x, y, j / 4.0))
              for x, y in ((-.1, -.05), (.1, -.05), (.1, .05), (-.1, .05))]
             for j in range(9)]
    for j in range(8):
        for k in range(4):
            face = straight.createPolygon()
            for point in (rings[j][k], rings[j][(k+1)%4],
                          rings[j+1][(k+1)%4], rings[j+1][k]):
                face.addVertex(point)
    for ring in (list(reversed(rings[0])), rings[-1]):
        face = straight.createPolygon()
        for point in ring: face.addVertex(point)
    source = fixture_stash('path_deform_source', straight)
    def quarter_arc(radius):
        geometry = hou.Geometry(); curve = geometry.createPolygon(is_closed=False)
        for i in range(65):
            angle = math.pi * .5 * i / 64
            curve.addVertex(fixture_point(geometry,
                (radius * (1-math.cos(angle)), 0, radius * math.sin(angle))))
        return geometry
    spine = fixture_stash('path_deform_spine', quarter_arc(2))
    deform = make('pathdeform', 'existing_geometry_bend', {
        'geo_controlaxis': 'z', 'geo_controlup': 'y', 'curve_controlup': 'yaxis',
        'curve_orientpointattribs': 0, 'geo_origin': 'relativebbox',
        'geo_centeroncurve': 1, 'geo_offsetunit': 'fractiongeolength',
        'geo_capturestart': 0, 'geo_captureend': 1,
        'curve_endunit': 'fractioncurvelength', 'curve_posend': 1,
        'startbehavior': 'extend', 'endbehavior': 'extend'}, [source, spine])
    source_topology = [tuple(v.point().number() for v in p.vertices())
                       for p in source.geometry().prims()]
    def ring_centers():
        points = [p.position() for p in deform.geometry().points()]
        assert len(points) == 36 and not deform.errors(), deform.errors()
        return [sum(points[i:i+4], hou.Vector3()) / 4 for i in range(0, 36, 4)]
    def check_bent_sections(radius):
        centers = ring_centers()
        points = [p.position() for p in deform.geometry().points()]
        assert [tuple(v.point().number() for v in p.vertices())
                for p in deform.geometry().prims()] == source_topology
        assert observed(deform)['boundary_edges'] == 0
        for j, center in enumerate(centers):
            angle = math.pi * .5 * j / 8
            expected = hou.Vector3(radius * (1-math.cos(angle)), 0, radius * math.sin(angle))
            assert (center - expected).length() < 1e-5, (center, expected)
            i = j * 4
            assert abs((points[i+1]-points[i]).length() - .2) < 1e-5
            assert abs((points[i+2]-points[i+1]).length() - .1) < 1e-5
            assert (points[i+2]-points[i+1]).normalized().dot(hou.Vector3(0,1,0)) > .999
    check_bent_sections(2)
    h.set_parm(deform, 'curve_endunit', 'fractiongeolength')
    end = ring_centers()[-1]
    # Source length is 2, quarter-circle length is pi; preserving source
    # length reaches approximately angle=1 radian, not the curve endpoint.
    expected = hou.Vector3(2*(1-math.cos(1)), 0, 2*math.sin(1))
    assert (end-expected).length() < .001 and (end-hou.Vector3(2,0,2)).length() > 1
    h.set_parms(deform, {'curve_endunit': 'fractioncurvelength',
                         'geo_capturestart': .25, 'geo_captureend': .75})
    centers = ring_centers()
    assert centers[2].length() < 1e-5
    assert (centers[6]-hou.Vector3(2,0,2)).length() < 1e-5
    # Uncaptured half-unit ends extend along the actual sampled end tangents.
    path_points = [p.position() for p in spine.geometry().points()]
    tangent_start = (path_points[1]-path_points[0]).normalized()
    tangent_end = (path_points[-1]-path_points[-2]).normalized()
    assert (centers[0] + tangent_start*.5).length() < 1e-5
    assert (centers[-1] - hou.Vector3(2,0,2) - tangent_end*.5).length() < 1e-5
    h.set_parms(deform, {'geo_capturestart': 0, 'geo_captureend': 1})
    spine.parm('stash').set(quarter_arc(3))
    check_bent_sections(3)
    h.set_parm(deform, 'geo_controlaxis', 'x')
    assert ring_centers()[0].length() > 1 and not deform.errors()
    h.set_parm(deform, 'geo_controlaxis', 'z')
    check_bent_sections(3)
    done('Path Deform source frame, length/capture mapping, local path edit and wrong-axis counterexample')

    # A writable tessellation value may be inactive in the current mode. The
    # reciprocal modes are both checked against real geometry, not UI labels.
    sphere = make('sphere', 'resolution_modes',
                  {'type': 'poly', 'freq': 2, 'rows': 10, 'cols': 12})
    polygon_counts = (len(sphere.geometry().points()), len(sphere.geometry().prims()))
    h.set_parms(sphere, {'rows': 20, 'cols': 24})
    assert (len(sphere.geometry().points()), len(sphere.geometry().prims())) == polygon_counts
    h.set_parm(sphere, 'freq', 4)
    assert len(sphere.geometry().prims()) > polygon_counts[1]
    h.set_parms(sphere, {'type': 'polymesh', 'rows': 10, 'cols': 12, 'freq': 2})
    mesh_count = len(sphere.geometry().prims())
    h.set_parm(sphere, 'rows', 20)
    row_count = len(sphere.geometry().prims())
    assert row_count > mesh_count
    h.set_parm(sphere, 'cols', 24)
    column_count = len(sphere.geometry().prims())
    assert column_count > row_count
    h.set_parm(sphere, 'freq', 4)
    assert len(sphere.geometry().prims()) == column_count
    assert {d['id'] for d in cards.operation_card('sphere')['always_advisories']} == {'effective_resolution'}
    done('Sphere poly frequency versus Polygon Mesh rows/columns: inactive writes do not refine')

    line = make('line', 'path', {'dir': [0, 0, 1]})
    profile = make('circle', 'profile', {'type': 'poly', 'orient': 'xy', 'rad': [.3, .15]})
    sweep = make('sweep::2.0', 'swept', inputs=[line, profile])
    assert sweep.parm('surfaceshape').evalAsString() == 'input'
    assert sweep.parm('endcaptype').evalAsString() == 'none'
    assert observed(sweep)['boundary_edges'] > 0
    h.set_parm(sweep, 'endcaptype', 'single')
    assert observed(sweep)['boundary_edges'] == 0
    assert abs(sweep.geometry().boundingBox().sizevec()[0] - .6) < 1e-5
    h.set_parms(sweep, {'surfaceshape': 'tube', 'radius': .1, 'endcaptype': 'none'})
    assert abs(sweep.geometry().boundingBox().sizevec()[0] - .2) < 1e-5
    assert observed(sweep)['boundary_edges'] > 0, 'intentional open built-in tube'
    done('Sweep external/built-in section and cap/open geometry')

    # Cable counterexample: a sampled helix that abruptly switches to a
    # straight end produced a sharp corner and a 90-degree hand-built ring
    # frame jump in a natural task. Build only the centerline, join its loose
    # end with a tangent-controlled cubic, then let native Sweep make/cap it.
    tau=2*math.pi;centerline=[]
    for i in range(241):
        t=i/240;theta=tau*4.5*t
        centerline.append(hou.Vector3(-.025+.045*t,.108+.0582*math.cos(theta),.0582*math.sin(theta)))
    start=centerline[-1];incoming=(start-centerline[-2]).normalized()
    end=hou.Vector3(.030,.030,-.020);outgoing=hou.Vector3(.2,-1,.1).normalized()
    handle1=start+incoming*.008;handle2=end-outgoing*.008
    for i in range(1,29):
        t=i/28
        centerline.append(start*(1-t)**3+handle1*3*(1-t)**2*t+handle2*3*(1-t)*t*t+end*t**3)
    turns=[]
    for i in range(1,len(centerline)-1):
        before=(centerline[i]-centerline[i-1]).normalized()
        after=(centerline[i+1]-centerline[i]).normalized()
        cosine=max(-1,min(1,float(before.dot(after))))
        turns.append(math.degrees(math.acos(cosine)))
    assert max(turns)<10 and max(turns[238:243])<10,turns[238:243]
    path_geo=hou.Geometry();curve=path_geo.createPolygon(is_closed=False)
    for position in centerline:
        point=path_geo.createPoint();point.setPosition(position);curve.addVertex(point)
    path_geo.incrementAllDataIds()
    sweep_verb=hou.sopNodeTypeCategory().nodeVerb('sweep::2.0')
    sweep_verb.setParms({'surfaceshape':1,'surfacetype':5,'radius':.0032,'cols':10,'endcaptype':1})
    cable_geo=hou.Geometry();sweep_verb.execute(cable_geo,[path_geo])  # input 0 is the backbone
    cable_check=polygon_observation(cable_geo,integrity_only=True)
    assert cable_check['status']=='observed' and cable_check['boundary_edges']==0,cable_check
    assert cable_check['risk_status']=='no_detected_integrity_risk',cable_check
    assert cable_check['shell_orientation']['positive_count']==1,cable_check
    done('tangent-continuous cable centerline + native Sweep closed surface')

    # The same Revolve can be a clean closed shell facing inward or outward.
    # Normal.reverse changes N, not the primitive vertex order; Reverse does.
    profile = make('line', 'revolve_profile', {'origin': [1, 0, 0], 'dir': [0, 1, 0]})
    revolved = make('revolve::2.0', 'revolved', {'cap': 0}, [profile])
    assert observed(revolved)['boundary_edges'] > 0
    h.set_parm(revolved, 'cap', 1)
    inward = observed(revolved)
    assert inward['boundary_edges'] == 0 and inward['orientation_conflicts'] == 0
    assert inward['shell_orientation']['negative_count'] == 1, inward
    h.set_parm(revolved, 'reversecrosssections', 1)
    outward = observed(revolved)
    assert outward['shell_orientation']['positive_count'] == 1, outward
    h.set_parm(revolved, 'swaprowcol', 0)
    swapped = observed(revolved)
    assert swapped['shell_orientation']['negative_count'] == 1, swapped
    h.set_parm(revolved, 'swaprowcol', 1)
    shaded = make('normal', 'shading_only', {'type': 'typeprim', 'reverse': 1}, [revolved])
    shaded_result = observed(shaded)
    assert shaded_result['shell_orientation']['positive_count'] == 1, shaded_result
    face = shaded.geometry().prims()[0]
    assert hou.Vector3(face.attribValue('N')).dot(face.normal()) < -.99
    reoriented = make('reverse', 'reverse_winding', {'vtxsort': 'reverse'}, [revolved])
    flipped = observed(reoriented)
    assert flipped['shell_orientation']['negative_count'] == 1, flipped
    revolve_card = cards.operation_card('revolve::2.0')
    card_ids = {d['id'] for d in revolve_card['decisions'] + revolve_card['always_advisories']}
    assert {'axis', 'surface_output', 'end_closure', 'surface_orientation'} == card_ids
    assert {d['id'] for d in cards.operation_card('normal')['always_advisories']} == {'winding_vs_normal'}
    done('Revolve cap and winding; Normal attribute versus Reverse vertex order')

    # An ordinary annular solid is already closed/outward. Reversing it alone
    # makes A-B include cutter material outside A with no Boolean warning.
    profile_source = ('int pts[]; append(pts,addpoint(0,set(1,0,0))); '
                      'append(pts,addpoint(0,set(1,1,0))); '
                      'append(pts,addpoint(0,set(2,1,0))); '
                      'append(pts,addpoint(0,set(2,0,0))); ')
    ring_profile = make('attribwrangle', 'solid_profile',
                        {'class': 'detail', 'snippet': profile_source + 'addprim(0,"poly",pts);'})
    ring = make('revolve::2.0', 'annular_solid',
                {'divs': 24, 'surftype': 'quads', 'primtype': 'poly', 'type': 'closed'}, [ring_profile])
    source_integrity = observed(ring)
    assert source_integrity['boundary_edges'] == 0
    assert source_integrity['shell_orientation']['positive_count'] == 1
    cutter = make('box', 'solid_cutter', {'size': [.8, .8, .8], 't': [1.5, .8, 0]})
    difference = make('boolean::2.0', 'solid_difference',
                      {'booleanop': 'subtract', 'subtractchoices': 'aminusb'}, [ring, cutter])
    correct_positions = positions(difference)
    assert observed(difference)['boundary_edges'] == 0
    assert abs(difference.geometry().boundingBox().maxvec()[1] - 1) < 1e-6
    assert not difference.warnings()
    h.set_parm(ring, 'reversecrosssections', 1)
    assert observed(ring)['shell_orientation']['negative_count'] == 1
    assert difference.geometry().boundingBox().maxvec()[1] > ring.geometry().boundingBox().maxvec()[1] + .1
    assert not difference.errors() and not difference.warnings(), 'success is not intended subtraction'
    h.set_parm(ring, 'reversecrosssections', 0)
    assert positions(difference) == correct_positions

    # The same visible profile with coincident open endpoints has an actual
    # seam. A targeted Fuse repairs it; the legitimate closed source above
    # does not need that repair. No blanket Fuse/Reverse policy is warranted.
    h.set_parm(ring_profile, 'snippet', profile_source +
               'append(pts,addpoint(0,set(1,0,0))); addprim(0,"polyline",pts);')
    assert observed(ring)['boundary_edges'] > 0
    seam_fuse = make('fuse::2.0', 'repair_confirmed_seam', inputs=[ring])
    assert observed(seam_fuse)['boundary_edges'] == 0
    assert observed(seam_fuse)['shell_orientation']['positive_count'] == 1
    difference.setInput(0, seam_fuse)
    assert positions(difference) == correct_positions
    assert not difference.errors() and not difference.warnings()
    assert {d['id'] for d in cards.operation_card('boolean::2.0')['always_advisories']} == {'solid_input_validity'}
    done('Boolean A-B outward/inward counterexample and independently repaired profile seam')

    semantic_specs = [
        {'name': 'advised_sphere', 'type': 'sphere',
         'parms': {'type': 'poly', 'freq': 2, 'rows': 20, 'cols': 24}},
        {'name': 'advised_difference', 'type': 'boolean',
         'parms': {'booleanop': 'subtract', 'subtractchoices': 'aminusb'},
         'inputs': [seam_fuse.name(), cutter.name()]},
    ]
    preview = h.build_module(root, semantic_specs, output='advised_difference', dry_run=True)
    assert root.node('advised_sphere') is None and root.node('advised_difference') is None
    semantic_build = h.build_module(root, semantic_specs, output='advised_difference')
    assert semantic_build['validation']['ok'] and preview['valid']
    assert len(root.node('advised_sphere').geometry().prims()) == polygon_counts[1], 'build preserves declared resolution'
    assert positions(root.node('advised_difference')) == correct_positions
    done('Sphere/Boolean batch preserves declared parameters and real geometry')

    sheet = make('grid', 'sheet', {'rows': 2, 'cols': 2})
    ext = make('polyextrude::2.0', 'thick_sheet', {'dist': .2}, [sheet])
    assert [ext.evalParm(n) for n in ('outputfront', 'outputback', 'outputside')] == [1, 0, 1]
    assert observed(ext)['boundary_edges'] > 0
    h.set_parm(ext, 'outputback', 1)
    assert observed(ext)['boundary_edges'] == 0
    solid_ext = make('polyextrude::2.0', 'solid_extrusion', {'group': '0', 'dist': .2}, [box])
    clean = observed(solid_ext)
    assert clean['boundary_edges'] == 0 and clean['nonmanifold_edges'] == 0, clean
    h.set_parm(solid_ext, 'outputback', 1)
    assert observed(solid_ext)['nonmanifold_edges'] > 0, 'universal Back creates interior face'
    done('PolyExtrude sheet closure and existing-solid interior-face counterexample')

    cylinder = make('tube', 'bevel_source', {'type': 'poly', 'cap': 1, 'cols': 12, 'height': 2})
    bevel = make('polybevel::3.0', 'angle_bevel', {'offset': .03, 'divisions': 2}, [cylinder])
    assert bevel.evalParm('ignoreflatedges') == 0
    all_count = len(bevel.geometry().prims())
    all_positions = positions(bevel)
    h.set_parms(bevel, {'ignoreflatedges': 1, 'flatangle': 45})
    sharp_count = len(bevel.geometry().prims())
    assert sharp_count < all_count and positions(bevel) != all_positions, (sharp_count, all_count)
    assert observed(bevel)['boundary_edges'] == 0
    h.set_parm(bevel, 'flatangle', 100)
    assert positions(bevel) == positions(cylinder), 'larger threshold excludes 90 degree ring edges too'
    assert len(bevel.geometry().prims()) == len(cylinder.geometry().prims())
    # Semantic edge group recomputed from geometry, not a list of stable edge IDs.
    group = make('attribwrangle', 'top_ring_group', {'class': 'point', 'snippet':
        'vector hi=getbbox_max(0); if(abs(@P.y-hi.y)<1e-5) {'
        'foreach(int nb; neighbours(0,@ptnum)) {vector q=point(0,"P",nb);'
        'if(abs(q.y-hi.y)<1e-5) setedgegroup(0,"top_ring",@ptnum,nb,1);}}'}, [cylinder])
    assert len(group.geometry().findEdgeGroup('top_ring').edges()) == 12
    selected = make('polybevel::3.0', 'selected_bevel',
                    {'group': 'top_ring', 'grouptype': 'edges', 'offset': .03, 'divisions': 2}, [group])
    source_positions, selected_positions = positions(cylinder), positions(selected)
    bottom = {p for p in source_positions if p[1] < 0}
    assert bottom.issubset(selected_positions) and source_positions != selected_positions
    assert observed(selected)['boundary_edges'] == 0
    h.set_parm(cylinder, 'cols', 16)
    assert len(group.geometry().findEdgeGroup('top_ring').edges()) == 16
    assert {p for p in positions(cylinder) if p[1] < 0}.issubset(positions(selected))
    assert observed(selected)['boundary_edges'] == 0
    done('PolyBevel angle direction and procedural edge-only selection across topology changes')

    generator = make('attribwrangle', 'generator', {'class': 'detail', 'snippet':
        'for(int i=0;i<5;i++) addpoint(0,set(i,0,0));'})
    assert len(generator.geometry().points()) == 5
    assert h.geo_attrib_stats(generator, 'P', unique=True)['all_unique']
    h.set_parms(generator, {'class': 'number', 'vex_numcount': 3})
    assert len(generator.geometry().points()) == 15
    assert h.geo_attrib_stats(generator, 'P', unique=True)['duplicate_count'] == 10
    h.set_parm(generator, 'snippet', 'addpoint(0,set(@elemnum,0,0));')
    assert len(generator.geometry().points()) == 3
    assert h.geo_attrib_stats(generator, 'P', unique=True)['all_unique']
    h.set_parm(generator, 'class', 'point')
    assert len(generator.geometry().points()) == 0, 'empty input has no point executions'
    tag = make('attribwrangle', 'class_tag', {'class': 'primitive', 'snippet': 'i@seen=1;'}, [box])
    assert tag.geometry().findPrimAttrib('seen') and tag.geometry().findPointAttrib('seen') is None
    h.set_parm(tag, 'class', 'vertex')
    assert tag.geometry().findVertexAttrib('seen') and tag.geometry().findPrimAttrib('seen') is None
    assert len([v for p in tag.geometry().prims() for v in p.vertices() if v.attribValue('seen') == 1]) == 24
    done('Wrangle execution multiplicity, Numbers counterexample and attribute class')

    # Include location is a file path; Evaluation Node Path controls ch(), not
    # include resolution. Exercise both an intentional node base and the
    # observed filesystem-base mistake using an owned temporary library.
    with tempfile.TemporaryDirectory(prefix='dsh-vex-include-') as directory:
        library = Path(directory) / 'shared.h'
        library.write_text('float shared_value(){return 2.0;}\n', encoding='utf-8')
        controller = make('null', 'include_controls')
        h.create_spare_parms(controller, spec=[{'name': 'gain', 'label': 'Gain', 'type': 'float', 'default': 3.0}])
        code = f'#include "{library.as_posix()}"\nf@value=shared_value()*chf("../include_controls/gain");'
        included = make('attribwrangle', 'include_consumer', {'class': 'detail', 'snippet': code})
        assert included.geometry().attribValue('value') == 6.0
        h.set_parm(included, 'vex_cwdpath', directory.replace('\\', '/'))
        assert included.geometry().attribValue('value') == 0.0, 'filesystem base must not resolve a sibling channel'
        h.set_parm(included, 'vex_cwdpath', '.')
        assert included.geometry().attribValue('value') == 6.0
        h.set_parms(included, {'vex_cwdpath': controller.path(),
                              'snippet': code.replace('../include_controls/gain', 'gain')})
        assert included.geometry().attribValue('value') == 6.0, 'intentional node-relative override stays supported'
        library.write_text('float shared_value(){return 5.0;}\n', encoding='utf-8')
        h.set_parms(included, {'vex_cwdpath': '.', 'snippet': code + '\n// library revision 2'})
        assert included.geometry().attribValue('value') == 15.0, 'verify changed behavior after actual recompilation'
        included.destroy()
        controller.destroy()
    done('Wrangle external include and channel evaluation use distinct paths; edited library actually recompiles')

    # Explicit and omitted choices preserve the actual Houdini parameters.
    spec = [{'name': 'advice_a', 'type': 'tube'}, {'name': 'advice_b', 'type': 'tube'}]
    before = set(root.children())
    plan = h.build_module(root, spec, output='advice_b', dry_run=True)
    assert plan['valid'] and set(root.children()) == before
    explicit = [{'name': 'intentional_native', 'type': 'tube', 'parms': {'type': 'prim', 'cap': 0}}]
    built = h.build_module(root, explicit, output='intentional_native')
    assert built['validation']['ok']
    assert root.node('intentional_native').parm('type').evalAsString() == 'prim'
    assert root.node('intentional_native').evalParm('cap') == 0
    inherited = h.build_module(root, [{'name': 'inherit_native', 'type': 'tube'}], output='inherit_native')
    assert inherited['validation']['ok']
    assert root.node('inherit_native').parm('type').evalAsString() == 'prim', 'build preserves native defaults'
    intentional_all = h.build_module(root, [{'name': 'all_edges', 'type': 'polybevel',
        'inputs': [box.name()], 'parms': {'group': '', 'grouptype': 'edges', 'offset': .01}}], output='all_edges')
    assert intentional_all['validation']['ok']
    done('dry-run and native/open/all-edge intent preservation')

    before = set(root.children())
    try:
        h.build_module(root, [{'name': 'bad_mode', 'type': 'attribwrangle', 'parms': {'runover': 0}}], output='bad_mode')
    except h.PreflightError as error:
        assert error.evidence['scene_writes'] == 0
        assert error.evidence['errors'][0]['field'] == 'runover'
    else:
        raise AssertionError('invalid field accepted')
    assert set(root.children()) == before
    try:
        h.build_module(root, [{'name': 'empty_mode', 'type': 'attribwrangle'}], output='empty_mode')
    except h.CheckpointError as error:
        assert not error.evidence['ok']
    else:
        raise AssertionError('empty wrangle passed')
    assert set(root.children()) == before
    packet = bridge.run_code(f'node_info({root.path()!r},"attribwrangle",parm_filter="snippet",limit=1)', read_only=True)
    assert packet['ok'], packet
    evidence = packet['evidence'][0]
    assert any(p['name'] == 'class' and p['menu'] for p in evidence['operation_parameters'])
    done('zero-write errors, failed-cook cleanup and unfiltered critical-card Bridge transport')
finally:
    root.destroy()

print(f'node knowledge: {len(checks)} groups passed on {hou.applicationVersionString()}')
for check in checks:
    print('  PASS ' + check)
