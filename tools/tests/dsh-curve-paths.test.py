"""Native editable curve construction and adversarial polyline-envelope evidence.

Run in a fresh isolated H21/H22 hython. No user HIP or GUI is used.
"""
import copy
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_ownership
import dsh_bridge as bridge
from dsh_curve_paths import _segment_distance


def rejects(call, message):
    try:
        call()
    except ValueError as error:
        assert message in str(error), (message, str(error))
    else:
        raise AssertionError('expected ' + message)


def lines(root, name, paths, radii=None):
    """Fixture-only native data creation; actual consumer is the public verb."""
    g = hou.Geometry()
    radius_attrib = g.addAttrib(hou.attribType.Prim, 'radius', 0.01)
    for index, path in enumerate(paths):
        prim = g.createPolygon(is_closed=False)
        for position in path:
            point = g.createPoint(); point.setPosition(position); prim.addVertex(point)
        prim.setAttribValue(radius_attrib, radii[index] if radii else 0.01)
    node = root.createNode('stash', node_name=name)
    dsh_ownership.register_owned_node(node)
    node.parm('stash').set(g)
    return node


# Nearly parallel interior crossings must not be reduced to endpoint distances.
near = _segment_distance((-1., -1e-10, 0), (1., 1e-10, 0), (-1., 1e-10, 0), (1., -1e-10, 0))
assert near[0] < 1e-20 and abs(near[1] - .5) < 1e-10 and abs(near[2] - .5) < 1e-10, near
parallel = _segment_distance((0,0,0), (10,0,0), (3,.02,0), (6,.02,0))
assert abs(parallel[0] - .02) < 1e-12, parallel
point_domain=_segment_distance((-1,0,0),(1,0,0),(0,-1,0),(0,1,0),[(0.,1.)])
assert abs(point_domain[0]-math.sqrt(2)) < 1e-12 and point_domain[1:3] == (0.,1.),point_domain
line_domain=_segment_distance((-1,0,0),(1,0,0),(0,-1,0),(0,1,0),[(0.,0.),(0.,1.)])
assert abs(line_domain[0]-1) < 1e-12,line_domain

with dsh_ownership.execution_owner('curve-path-tests', 'fixture'):
    root = h.tab_create('/obj', 'geo', 'curve_paths_test')
    try:
        ctrl = h.tab_create(root, 'null', 'CTRL')
        h.create_spare_parms(ctrl, spec=[{'type':'float','name':'plug_x','default':0.0},
                                        {'type':'float','name':'handle_y','default':.08}])
        spec = {'name': 'lead', 'controller': 'CTRL', 'segment_length': .005,
                'anchors': [
                    {'name':'plug', 'position':[{'parm':'plug_x'}, .8, 0], 'handle':[0, {'parm':'handle_y'}, 0]},
                    {'name':'rest', 'position':[.25, .79, .2], 'handle':[.08, 0, 0]},
                    {'name':'probe', 'position':[.5, .79, .15], 'handle':[0, 0, -.04]}]}
        before = tuple(root.children())
        plan = h.sop_recipe('curve_path', spec)
        discovery = h.sop_recipe('curve_path'); discovery['example']['anchors'][0]['name'] = 'local_change'
        assert h.sop_recipe('curve_path')['example']['anchors'][0]['name'] == 'plug'
        assert tuple(root.children()) == before, 'planning mutated the scene'
        built = h.build_module(root, plan['nodes'], output=plan['output'], required_outputs=plan['required_outputs'])
        assert built['valid'], built
        source, curve, sampled = (root.node(plan['edit_nodes'][key]) for key in ('control_points','native_curve','polyline'))
        assert curve.type().name() == 'curve::2.0' and source.type().name() == 'add'
        cp = [tuple(p.position()) for p in curve.geometry().points()]
        assert len(cp) == 7 and math.dist(cp[3],(.25,.79,.2)) < 1e-7, cp
        p = curve.geometry().prim(0)
        assert p.type() == hou.primType.BezierCurve and not p.isClosed()
        assert (p.positionAt(.5) - hou.Vector3((.25,.79,.2))).length() < 1e-7
        assert math.dist([a-b for a,b in zip(cp[3],cp[2])], [a-b for a,b in zip(cp[4],cp[3])]) < 1e-7
        eps = 1e-5
        left = (p.positionAt(.5) - p.positionAt(.5-eps)) / eps
        right = (p.positionAt(.5+eps) - p.positionAt(.5)) / eps
        assert (left - right).length() < .01 * max(left.length(),right.length()), (left, right)
        assert all(q.type() == hou.primType.Polygon and not q.isClosed() for q in sampled.geometry().prims())
        assert h.geo_curve_clearance(sampled,.002)['ok'], 'normal structured path misclassified as overlapping'
        assert plan['anchors'][1] == {'name':'rest','anchor_point':3,'out_handle_point':4,'in_handle_point':2}
        # Shared numerical controls affect the actual native curve and final tube.
        tube = h.tab_create(root, 'sweep', 'tube', inputs=[sampled],
                            parms={'surfaceshape':'tube','radius':.002,'cols':12,'endcaptype':'single'})
        old_points = tube.geometry().pointFloatAttribValues('P')
        h.set_parms(ctrl, {'plug_x':.12,'handle_y':.12})
        changed = [tuple(x.position()) for x in curve.geometry().points()]
        assert abs(changed[0][0] - .12) < 1e-6 and abs(changed[1][1] - .92) < 1e-6, changed
        assert tube.geometry().pointFloatAttribValues('P') != old_points
        h.set_parms(ctrl, {'plug_x':0.,'handle_y':.08})
        restored = [tuple(x.position()) for x in curve.geometry().points()]
        assert restored == cp and not tube.errors()
        # Native control-point edit is consumed, with no generated VEX/Python SOP.
        h.set_parms(source, {'pt3z':.23})
        assert abs(curve.geometry().prim(0).positionAt(.5)[2] - .23) < 1e-6
        assert not any(n.type().name().startswith(('attribwrangle','python')) for n in root.children())
        # Closed smooth representations and sparse point-only tests cannot pass.
        assert h.geo_curve_clearance(curve,.002)['reason'] == 'requires_open_polygon_curves'
        bad = copy.deepcopy(spec); bad['anchors'][1]['name'] = 'plug'
        rejects(lambda:h.sop_recipe('curve_path',bad),'unique')
        bad = copy.deepcopy(spec); bad['anchors'][0]['position'] = [0, 0]
        rejects(lambda:h.sop_recipe('curve_path',bad),'three')
        bad = copy.deepcopy(spec); bad['segment_length'] = 0
        rejects(lambda:h.sop_recipe('curve_path',bad),'positive')
        bad = copy.deepcopy(spec); bad['anchors'][0]['position'][0] = {'point':'guess'}
        rejects(lambda:h.sop_recipe('curve_path',bad),'finite')

        crossing = lines(root,'crossing',[[(-1,0,0),(1,0,0)],[(0,-1,0),(0,1,0)]])
        digest = (crossing.geometry().pointFloatAttribValues('P'),
                  tuple(tuple(v.point().number() for v in p.vertices()) for p in crossing.geometry().prims()),
                  crossing.geometry().primFloatAttribValues('radius'))
        count = len(root.children()); frame = hou.frame()
        failure = h.geo_curve_clearance(crossing,.01)
        assert failure['status'] == 'fail' and failure['min_envelope_gap'] == -.02, failure
        assert failure['worst_pairs'][0]['left']['segment_u'] == .5
        assert (crossing.geometry().pointFloatAttribValues('P'),
                tuple(tuple(v.point().number() for v in p.vertices()) for p in crossing.geometry().prims()),
                crossing.geometry().primFloatAttribValues('radius')) == digest
        assert len(root.children()) == count and hou.frame() == frame
        safe = lines(root,'safe',[[(-1,0,0),(1,0,0)],[(-1,.05,0),(1,.05,0)]],[.01,.02])
        passed = h.geo_curve_clearance(safe,'radius',clearance=.01)
        assert passed['ok'] and abs(passed['min_envelope_gap']-.02)<1e-7, passed
        rejects(lambda:h.geo_curve_clearance(safe,'missing'),'attribute')
        rejects(lambda:h.geo_curve_clearance(safe,True),'finite')
        rejects(lambda:h.geo_curve_clearance(safe,.01,group='absent'),'missing')
        one = lines(root,'one',[[(-1,0,0),(1,0,0)]])
        no_pairs = h.geo_curve_clearance(one,.01)
        assert no_pairs['status']=='unverified' and no_pairs['reason']=='no_nonlocal_pairs',no_pairs
        degenerate = lines(root,'degenerate',[[(0,0,0),(0,0,0)]])
        assert h.geo_curve_clearance(degenerate,.01)['reason']=='degenerate_segment'
        box=h.tab_create(root,'box','not_a_curve')
        assert h.geo_curve_clearance(box,.01)['reason']=='requires_open_polygon_curves'
        assert h.geo_curve_clearance(safe,.01,max_segments=1)['reason']=='segment_budget_exceeded'
        budget = h.geo_curve_clearance(crossing,.01,max_pairs=1)
        assert budget['coverage']['measured_pairs']==1
        many = lines(root,'many',[[(-1,i*.1,0),(1,i*.1,0)] for i in range(4)])
        budget = h.geo_curve_clearance(many,.01,max_pairs=2)
        assert budget['reason']=='pair_budget_exceeded' and budget['coverage']['measured_pairs']==0, budget
        bounded = h.geo_curve_clearance(many,.01,max_results=1)
        assert bounded['coverage']['measured_pairs']==6 and len(bounded['worst_pairs'])==1 and bounded['truncated_results']
        # Explicit selection cannot certify the unselected mixed surface.
        mix = hou.Geometry();mix.merge(crossing.geometry());mix.merge(box.geometry())
        chosen = mix.createPrimGroup('wires');chosen.add(mix.prims()[:2])
        mixed = root.createNode('stash',node_name='mixed');dsh_ownership.register_owned_node(mixed);mixed.parm('stash').set(mix)
        assert h.geo_curve_clearance(mixed,.01)['status']=='unverified'
        selected = h.geo_curve_clearance(mixed,.01,group='wires')
        assert selected['status']=='fail' and selected['selected_primitives']==2 and selected['source_primitives']>2,selected
        # Open Polygon with equal first/last positions: omit both seam neighbors.
        loop = lines(root,'loop',[[(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,0)]])
        observed_loop = h.geo_curve_clearance(loop,.01,self_exclusion=.04)
        assert observed_loop['coverage']['curves'][0]['geometric_loop']
        assert observed_loop['coverage']['partially_clipped_self_pairs']==4 and observed_loop['ok'],observed_loop
        # Short intervening arc does not justify dropping two long overlapping
        # segments. The closest-point minimization must use the nonlocal domain.
        hairpin = lines(root,'coarse_hairpin',[[(0,-10,0),(0,0,0),(10,0,0),(10,.005,0),(5,.005,0)]])
        hairpin_result = h.geo_curve_clearance(hairpin,.01)
        assert hairpin_result['status']=='fail' and hairpin_result['min_envelope_gap'] < -.014, hairpin_result
        # The same counterexample with DIRECTLY adjacent reversed long edges.
        backtrack = lines(root,'adjacent_backtrack',[[(0,0,0),(10,0,0),(5,0,0)]])
        backtrack_result = h.geo_curve_clearance(backtrack,.01)
        assert backtrack_result['status']=='fail' and backtrack_result['min_envelope_gap'] < -.019,backtrack_result
        # A long straight join remains clear after clipping only local points.
        straight = lines(root,'straight',[[(0,0,0),(1,0,0),(2,0,0)]])
        straight_result = h.geo_curve_clearance(straight,.01)
        assert straight_result['ok'] and straight_result['min_envelope_gap'] > .01,straight_result
        gentle = lines(root,'gentle',[[(0,0,0),(1,0,0),(2,.001,0)]])
        assert h.geo_curve_clearance(gentle,.01)['ok'], 'ordinary shallow bend misclassified'
        arc = lines(root,'arc',[[(math.cos(i*.005),math.sin(i*.005),0) for i in range(81)]])
        assert h.geo_curve_clearance(arc,.01)['ok'], 'ordinary large-radius arc misclassified'
        short_loop=lines(root,'short_loop',[[(0,0,0),(.001,0,0),(.001,.001,0),(0,.001,0),(0,0,0)]])
        short_result=h.geo_curve_clearance(short_loop,.01)
        assert short_result['status']=='unverified' and short_result['reason']=='no_nonlocal_pairs',short_result
        # A crowded helix recreates the general pitch/radius failure without a task asset.
        helix = [(math.cos(i*.1), math.sin(i*.1), i*.1*.01/(2*math.pi)) for i in range(190)]
        coil = lines(root,'coil',[helix])
        collision = h.geo_curve_clearance(coil,.01)
        assert collision['status']=='fail' and collision['min_envelope_gap'] < -.009, collision
        # Read-only Bridge dispatch, complete help and selected-group scope.
        native = bridge._verb_help('geo_curve_clearance',detail='full')
        assert native['call_mode']=='query_or_exec' and native['operation_contract']['examples']
        result = bridge.run_code('__result__=geo_curve_clearance('+repr(safe.path())+', "radius")',read_only=True,
                                 owner_session='curve-path-tests')
        assert result['ok'] and result['result']['status']=='pass',result
        print(json.dumps({'houdini':hou.applicationVersionString(),'native_curve':'BezierCurve',
                          'structured_anchors':len(spec['anchors']),'crossing_gap':failure['min_envelope_gap'],
                          'helix_gap':collision['min_envelope_gap'],'loop_clipped_pairs':4,'dispatch':'query_passed'}))
    finally:
        h.delete_node(root)
