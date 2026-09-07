"""H21/H22 isolated HOM: decision cards, real geometry and advisory transport.

No live connection, HIP load/save or rendering. Defaults use direct creation;
the separate stool-repair regression exercises the actual Sweep shelf script.
"""
from pathlib import Path
from itertools import combinations
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as bridge
import dsh_operation_cards as cards

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
    families = ('sweep', 'polyextrude', 'polybevel', 'sphere', 'tube', 'circle', 'box', 'attribwrangle')
    for family in families:
        info = h.node_info(root, family, parm_filter='no_such_filter', limit=1)
        assert info['parameter_count'] == 0 and not info['parameters']
        assert info['operation_parameters'] and not info['operation_parameters_missing'], info
        actual = make(info['type'], 'template_' + family)
        for setting in info['operation_parameters']:
            assert actual.parmTuple(setting['name']) is not None, setting
            if setting.get('menu') and not setting.get('menu_dynamic'):
                assert {m['token'] for m in setting['menu']} == set(actual.parm(setting['name']).menuItems())
        actual.destroy()
    assert set(root.children()) == before
    assert cards.operation_card('polybevel::2.0') is None
    assert cards.operation_card('sweep::99.0') is None
    assert cards.operation_card('custom::sweep::2.0') is None
    detached = cards.operation_card('attribwrangle')
    detached['decisions'].clear()
    assert cards.operation_card('attribwrangle')['decisions'], 'cache must not be mutable by its consumer'
    done('runtime critical templates, filtering, version boundaries and cache isolation')

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

    # Advice is non-mutating, grouped, bounded and retained by Bridge evidence.
    spec = [{'name': 'advice_a', 'type': 'tube'}, {'name': 'advice_b', 'type': 'tube'}]
    before = set(root.children())
    plan = h.build_module(root, spec, output='advice_b', dry_run=True)
    assert plan['valid'] and set(root.children()) == before
    assert plan['operation_advisory_count'] == 1
    assert plan['operation_advisories'][0]['nodes'] == ['advice_a', 'advice_b']
    assert {d['id'] for d in plan['operation_advisories'][0]['decisions']} == {'representation', 'end_closure'}
    assert bridge._operation_summary('build_module', plan)['operation_advisories'] == plan['operation_advisories']
    explicit = [{'name': 'intentional_native', 'type': 'tube', 'parms': {'type': 'prim', 'cap': 0}}]
    built = h.build_module(root, explicit, output='intentional_native')
    assert not built['operation_advisories']
    assert root.node('intentional_native').parm('type').evalAsString() == 'prim'
    assert root.node('intentional_native').evalParm('cap') == 0
    inherited = h.build_module(root, [{'name': 'inherit_native', 'type': 'tube'}], output='inherit_native')
    assert inherited['operation_advisories'] and inherited['validation']['ok']
    assert root.node('inherit_native').parm('type').evalAsString() == 'prim', 'advice never rewrites defaults'
    intentional_all = h.build_module(root, [{'name': 'all_edges', 'type': 'polybevel',
        'inputs': [box.name()], 'parms': {'group': '', 'grouptype': 'edges', 'offset': .01}}], output='all_edges')
    assert not intentional_all['operation_advisories'] and intentional_all['validation']['ok']
    assert bridge._operation_summary('build_module', inherited)['operation_advisories']
    done('dry-run grouping and non-blocking native/open/all-edge intent preservation')

    variants = []
    for typ, values in [('polyextrude', {'outputfront': 1, 'outputback': 0, 'outputside': 1}),
                        ('tube', {'type': 'poly', 'cap': 0}),
                        ('polybevel', {'group': '', 'grouptype': 'edges', 'ignoreflatedges': 1, 'flatangle': 45})]:
        for count in range(len(values) + 1):
            for names in combinations(values, count):
                chosen = {n: values[n] for n in names}
                metadata = h.node_info(root, typ)['operation_card']
                if cards.decision_advisories(metadata, chosen):
                    variants.append({'name': 'variant_' + str(len(variants)), 'type': typ, 'parms': chosen})
    capped = h.build_module(root, variants, output=variants[-1]['name'], dry_run=True)
    assert capped['operation_advisory_count'] == len(variants) > 16
    assert len(capped['operation_advisories']) == 16 and capped['operation_advisories_truncated']
    assert root.node('variant_0') is None
    assert not cards.decision_advisories(cards.operation_card('attribwrangle'),
                                         {'class': {'expression': '2', 'language': 'hscript'}}), 'presence is not expression evaluation'
    done('bounded heterogeneous advice, explicit truncation and non-evaluating expressions')

    before = set(root.children())
    try:
        h.build_module(root, [{'name': 'bad_mode', 'type': 'attribwrangle', 'parms': {'runover': 0}}], output='bad_mode')
    except h.PreflightError as error:
        assert error.evidence['scene_writes'] == 0 and error.evidence['operation_advisories']
        assert error.evidence['errors'][0]['field'] == 'runover'
    else:
        raise AssertionError('invalid field accepted')
    assert set(root.children()) == before
    try:
        h.build_module(root, [{'name': 'empty_mode', 'type': 'attribwrangle'}], output='empty_mode')
    except h.CheckpointError as error:
        assert error.evidence['operation_advisories'] and not error.evidence['ok']
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
