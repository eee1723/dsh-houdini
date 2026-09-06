"""Bounded final-geometry checks with optional controlled review preview capture.

All calls run through the owning-thread Bridge. Named groups are explicit user/
agent-selected interfaces, not inferred semantics. This is not a solid collision
solver; unsupported representations stay unverified, never silently sampled.
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
import json
import math
import operator
import time
import hou
import hjson

_MAX_GEOMETRY_BYTES = 32 * 1024 * 1024
_MAX_POINTS = 250000
_MAX_PRIMS = 100000
_SURFACE_TYPES = {'Polygon', 'Mesh', 'Sphere', 'Tube'}


class UnsupportedEvidence(ValueError):
    pass


def validate_domain(domain):
    if not isinstance(domain,list) or len(domain)>32:
        raise ValueError('domain must contain at most 32 scalar comparisons')
    ids=set()
    for c in domain:
        _exact_keys(c,{'id','left','op','right'},'domain condition')
        if set(c)!={'id','left','op','right'}:raise ValueError('domain needs id/left/op/right')
        for name in ('id','left'):
            if not isinstance(c[name],str) or not c[name].strip():raise ValueError(f'domain {name} must be nonempty')
        if c['id'] in ids:raise ValueError('domain ids must be unique')
        ids.add(c['id'])
        if c['op'] not in ('lt','le','gt','ge','eq','ne'):raise ValueError('domain op must be exactly lt, le, gt, ge, eq or ne')
        if isinstance(c['right'],str):
            if not c['right'].strip():raise ValueError('domain right control must be nonempty')
        else:_finite(c['right'],'domain right')


def domain_checks(ctrl, domain, overrides=None):
    """Compare numeric spare values; no eval strings, solving or parameter writes."""
    names={p.name() for p in ctrl.spareParms() if p.parmTemplate().type() in (hou.parmTemplateType.Float,hou.parmTemplateType.Int)}
    def value(name):
        if name not in names:raise ValueError(f'domain references missing numeric spare control {name!r}')
        return _finite(overrides[name] if overrides and name in overrides else ctrl.evalParm(name),'domain value')
    compare={'lt':operator.lt,'le':operator.le,'gt':operator.gt,'ge':operator.ge,'eq':operator.eq,'ne':operator.ne}
    rows=[]
    for c in domain:
        left=value(c['left']);right=value(c['right']) if isinstance(c['right'],str) else c['right']
        rows.append({'id':c['id'],'kind':'domain','status':'pass' if compare[c['op']](left,right) else 'fail',
                     'condition':dict(c),'left_value':left,'right_value':right,
                     'scope':'current or proposed scalar values only; not proof of all combinations',
                     'next_action':'Restore a design-valid value or explicitly revise the design contract; no silent clamping.'})
    return rows


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be a finite number')
    return float(value)


def _exact_keys(obj, allowed, label):
    if not isinstance(obj, dict) or set(obj) - set(allowed):
        raise ValueError(f'{label} supports only {sorted(allowed)}')


def validate_interfaces(interfaces):
    if not isinstance(interfaces, list) or not 1 <= len(interfaces) <= 16:
        raise ValueError('interfaces must contain 1..16 explicit contracts')
    ids = set()
    for item in interfaces:
        _exact_keys(item, {'id','source_group','target_group','max_distance','expected_points'}, 'interface')
        for key in ('id', 'source_group', 'target_group'):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f'interface {key} must be nonempty')
        if item['id'] in ids:
            raise ValueError('interface ids must be unique')
        ids.add(item['id'])
        if _finite(item.get('max_distance'), 'max_distance') < 0:
            raise ValueError('max_distance must be nonnegative (SOP local units)')
        if type(item.get('expected_points')) is not int or not 1 <= item['expected_points'] <= 512:
            raise ValueError('expected_points must be an integer in 1..512; do not silently accept missing endpoints')


def _geometry(output):
    import dsh_hou_helpers as h
    node = h._resolve(output)
    if node.type().category() != hou.sopNodeTypeCategory():
        raise ValueError('explicit output must be a SOP')
    g = node.geometry()
    if g is None or node.errors():
        raise ValueError(f'output has no healthy geometry: {node.path()}: {node.errors()}')
    if (g.intrinsicValue('pointcount') > _MAX_POINTS or g.intrinsicValue('primitivecount') > _MAX_PRIMS
            or g.intrinsicValue('memoryusage') > _MAX_GEOMETRY_BYTES):
        raise ValueError('geometry evidence budget exceeded; use a smaller explicit deliverable module')
    return node, g.freeze(read_only=True)


def _data_signature(g):
    # bgeo contains topology, attributes AND primitive intrinsics (native Tube
    # radius, packed transforms, etc.). P-only signatures miss such changes.
    data = g.data()
    if len(data) > _MAX_GEOMETRY_BYTES:
        raise ValueError('serialized geometry evidence budget exceeded')
    # Houdini's bgeo writer injects wall-clock info.date on EACH serialization.
    # Raw bytes can disagree across one second with identical geometry. Decode
    # the complete payload and remove ONLY that export-header timestamp; user
    # attributes named date, topology, intrinsics and all groups remain included.
    payload=hjson.loads(data)
    if not isinstance(payload,list) or len(payload)%2 or any(not isinstance(k,str) for k in payload[::2]):
        raise ValueError('unsupported bgeo root schema; no restoration fingerprint fallback')
    for i in range(0,len(payload),2):
        if payload[i]=='info' and isinstance(payload[i+1],dict):
            payload[i+1]={k:v for k,v in payload[i+1].items() if k!='date'}
    canonical=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    if len(canonical)>4*_MAX_GEOMETRY_BYTES:raise ValueError('decoded geometry evidence budget exceeded')
    return hashlib.sha256(canonical).hexdigest()


def _supported_surface(prim):
    kind = prim.type().name()
    return kind in _SURFACE_TYPES and (kind != 'Polygon' or (bool(prim.intrinsicValue('closed')) and prim.numVertices() >= 3))


def _check_interfaces(g, interfaces, max_pairs):
    total_pairs = 0
    selections = []
    results = []
    for item in interfaces:
        pg = g.findPointGroup(item['source_group'])
        tg = g.findPrimGroup(item['target_group'])
        points = list(pg.points()) if pg else []
        prims = list(tg.prims()) if tg else []
        base = {'id':item['id'],'source_group':item['source_group'],'target_group':item['target_group'],
                'source_count':len(points),'target_count':len(prims),'expected_points':item['expected_points'],
                'tolerance':item['max_distance']}
        if len(points) != item['expected_points'] or not prims:
            results.append({**base,'status':'fail','reason':'missing_group_or_cardinality_mismatch'})
            continue
        total_pairs += len(points) * len(prims)
        if total_pairs > max_pairs:
            raise ValueError('interface nearest-surface budget exceeded; narrow the explicit interface groups')
        if any(not _supported_surface(p) for p in prims):
            results.append({**base,'status':'unverified','reason':'unsupported_target_surface_type'})
            continue
        # Source ports must be actual polygon/mesh vertices, not the center of
        # a quadric or free-standing driver/anchor points included in the output.
        if any(not p.vertices() or not any(v.prim().type().name() in ('Polygon','Mesh') and _supported_surface(v.prim())
                                         for v in p.vertices()) for p in points):
            results.append({**base,'status':'unverified','reason':'source_group_not_on_final_surface_vertices'})
            continue
        target_point_ids = {p.number() for prim in prims for p in prim.points()}
        if any(p.number() in target_point_ids for p in points):
            results.append({**base,'status':'fail','reason':'source_and_target_overlap_cannot_self_validate',
                            'next_action':'Shared vertices are not an independent-surface distance test. For fused polygon parts use test_controls topology; do not enlarge tolerance or remove correct shared vertices.'})
            continue
        selections.append((base, points, prims))
    for base, points, prims in selections:
        distances = []
        failure = []
        try:
            for point in points:
                candidates = []
                pos = point.position()
                if not all(math.isfinite(float(v)) for v in pos):
                    raise UnsupportedEvidence('nonfinite source point')
                for prim in prims:
                    u, v, distance = prim.nearestToPosition(pos)
                    if not math.isfinite(distance) or distance < 0:
                        raise UnsupportedEvidence('invalid nearest surface result')
                    candidates.append((float(distance),prim.number()))
                distance, target_prim = min(candidates)
                distances.append(distance)
                if distance > base['tolerance']:
                    failure.append({'point':point.number(),'nearest_prim':target_prim,'distance':distance,'position':list(pos)})
        except (hou.Error, UnsupportedEvidence) as error:
            results.append({**base,'status':'unverified','reason':str(error)})
            continue
        results.append({**base,'status':'fail' if failure else 'pass','min_distance':min(distances),
                        'max_distance':max(distances),'failure_count':len(failure),
                        'failures':sorted(failure,key=lambda r:r['distance'],reverse=True)[:8]})
    order = {i['id']:n for n,i in enumerate(interfaces)}
    results.sort(key=lambda r:order[r['id']])
    status = 'fail' if any(r['status']=='fail' for r in results) else 'unverified' if any(r['status']=='unverified' for r in results) else 'pass'
    return {'ok':status=='pass','status':status,'results':results,'pair_tests':total_pairs,
            'coverage':'every declared source vertex against every selected target surface',
            'coordinate_space':'explicit output SOP local',
            'scope':'point-to-surface interface proximity only; not solid overlap, penetration, mechanical strength or all-surface clearance'}


def geo_check_interfaces(output, interfaces, max_pairs=50000):
    """Measure declared surface interfaces in ONE actual output, not proxy nodes."""
    validate_interfaces(interfaces)
    if type(max_pairs) is not int or not 1 <= max_pairs <= 100000:
        raise ValueError('max_pairs must be in 1..100000')
    node, g = _geometry(output)
    result = _check_interfaces(g, interfaces, max_pairs)
    return {**result,'output':node.path(),'frame':float(hou.frame()),'checked_at':time.time(),
            'geometry_sha256':_data_signature(g),'contract_sha256':hashlib.sha256(json.dumps(interfaces,sort_keys=True).encode()).hexdigest(),
            'semantic_status':'unverified','next_action':'Repair failing declared interfaces then rerun; this does not certify unspecified relationships.'}


def validate_topology(topology):
    if not isinstance(topology,list) or not 1<=len(topology)<=16:
        raise ValueError('topology needs 1..16 shared-surface contracts')
    ids=set()
    for c in topology:
        _exact_keys(c,{'id','groups','require_closed'},'topology')
        if not isinstance(c.get('id'),str) or not c['id'].strip() or c['id'] in ids:raise ValueError('topology ids must be nonempty and unique')
        ids.add(c['id']);groups=c.get('groups')
        if (not isinstance(groups,list) or not 2<=len(groups)<=16 or any(not isinstance(n,str) or not n.strip() for n in groups)
                or len(set(groups))!=len(groups)):raise ValueError('topology groups must name 2..16 distinct nonempty primitive groups')
        if type(c.get('require_closed',True)) is not bool:raise ValueError('require_closed must be bool')


def _check_topology(g, topology):
    """Shared polygon EDGE connectivity of named final surfaces, never proximity.

    A point-touch, disconnected overlapping boxes or unrelated driver points do
    not prove a fused surface. Not a solid intersection/strength/shape oracle.
    """
    results=[]
    for c in topology:
        row={'id':c['id'],'method':'shared_polygon_edges','groups':c['groups'],
             'require_closed':c.get('require_closed',True),'scope':'selected final polygon surface topology only; not strength, self-intersection or intended shape'}
        selected={};reason=None
        for name in c['groups']:
            group=g.findPrimGroup(name);prims=list(group.prims()) if group is not None else []
            if not prims:reason='missing_or_empty_part_group';break
            if any(p.number() in selected for p in prims):reason='overlapping_part_groups_cannot_self_validate';break
            selected.update((p.number(),p) for p in prims)
        if reason:
            results.append({**row,'status':'fail','reason':reason});continue
        if len(selected)>20000:raise ValueError('topology budget exceeded; narrow selected surfaces')
        if any(p.type().name()!='Polygon' or not bool(p.intrinsicValue('closed')) for p in selected.values()):
            results.append({**row,'status':'unverified','reason':'shared topology supports closed Polygon faces only'});continue
        edges=defaultdict(list);directed=Counter();parents={n:n for n in selected};vertices=0
        def root(n):
            while parents[n]!=n:
                parents[n]=parents[parents[n]];n=parents[n]
            return n
        for n,p in selected.items():
            ids=[v.point().number() for v in p.vertices()];vertices+=len(ids)
            if vertices>100000:raise ValueError('topology vertex budget exceeded')
            area=float(p.intrinsicValue('measuredarea'))
            if len(set(ids))!=len(ids) or len(ids)<3 or not math.isfinite(area) or area<=0:
                reason='degenerate_polygon_face';break
            positions=[tuple(v.point().position()) for v in p.vertices()]
            if any(not math.isfinite(x) for pos in positions for x in pos) or any(a==b for a,b in zip(positions,positions[1:]+positions[:1])):
                reason='nonfinite_or_zero_length_surface_edge';break
            for a,b in zip(ids,ids[1:]+ids[:1]):edges[tuple(sorted((a,b)))].append(n);directed[a,b]+=1
        if reason:
            results.append({**row,'status':'fail','reason':reason});continue
        for owners in edges.values():
            for n in owners[1:]:parents[root(n)]=root(owners[0])
        components=len({root(n) for n in parents})
        boundary=sum(len(v)==1 for v in edges.values());nonmanifold=sum(len(v)>2 for v in edges.values())
        orientation=sum(len(owners)==2 and directed[a,b]!=directed[b,a] for (a,b),owners in edges.items())
        failures=[]
        if components!=1:failures.append('disconnected_selected_surfaces')
        if nonmanifold:failures.append('nonmanifold_edges')
        if row['require_closed'] and boundary:failures.append('open_selected_surface')
        if orientation:failures.append('inconsistent_face_orientation')
        results.append({**row,'status':'fail' if failures else 'pass','failure_reasons':failures,
                        'surface_components':components,'boundary_edges':boundary,'nonmanifold_edges':nonmanifold,
                        'orientation_conflicts':orientation,'selected_prims':len(selected),
                        'next_action':'For fused parts fix shared final topology; for separate touching parts use independent surface interfaces, not this method.'})
    status='fail' if any(r['status']=='fail' for r in results) else 'unverified' if any(r['status']=='unverified' for r in results) else 'pass'
    return {'ok':status=='pass','status':status,'results':results,'semantic_status':'unverified'}


def _validate_expectation(item):
    _exact_keys(item, {'group','metric','axis','delta'}, 'expectation')
    metric = item.get('metric')
    if metric not in ('bounds_size','bounds_center','bounds_min','bounds_max','point_count','primitive_count','area'):
        raise ValueError('unsupported metric; exact values: bounds_size, bounds_center, bounds_min, bounds_max, point_count, primitive_count, area')
    if metric.startswith('bounds_') and (type(item.get('axis')) is not int or not 0 <= item['axis'] <= 2):
        raise ValueError('bounds metric needs axis=0/1/2')
    if 'group' in item and (not isinstance(item['group'],str) or not item['group']):
        raise ValueError('group must name a nonempty primitive group in the actual output')
    delta = item.get('delta')
    if not isinstance(delta, (list,tuple)) or len(delta) != 2:
        raise ValueError('expected signed delta must be [minimum,maximum]')
    lo, hi = [_finite(v,'delta') for v in delta]
    if lo > hi:
        raise ValueError('delta minimum must be <= maximum')


def _measure(g, item):
    group = g.findPrimGroup(item['group']) if item.get('group') else None
    if item.get('group') and group is None:
        raise ValueError(f'missing measurement group {item["group"]!r}')
    prims = list(group.prims()) if group is not None else list(g.prims())
    metric = item['metric']
    if group is not None and not prims:
        raise ValueError('measurement selection is empty')
    if not prims and metric != 'point_count':
        raise ValueError('measurement selection is empty')
    if metric == 'primitive_count':return len(prims)
    if metric == 'point_count':
        return len({p.number() for prim in prims for p in prim.points()}) if group is not None else int(g.intrinsicValue('pointcount'))
    # Bounds are explicitly spatial response metrics, not proof of connectivity.
    if metric.startswith('bounds_'):
        # The default hou.BoundingBox contains the origin; it is not an empty
        # accumulator. Starting there corrupts local measurements off-origin.
        bbox = prims[0].boundingBox()
        for prim in prims[1:]:bbox.enlargeToContain(prim.boundingBox())
        values = {'bounds_min':bbox.minvec(),'bounds_max':bbox.maxvec(),'bounds_size':bbox.sizevec(),'bounds_center':bbox.center()}
        return float(values[metric][item['axis']])
    if any(not _supported_surface(p) for p in prims):
        raise UnsupportedEvidence('area not verified for this primitive representation')
    return sum(float(p.intrinsicValue('measuredarea')) for p in prims)


def validate_capture_views(views):
    if not isinstance(views,list) or len(views)>2 or any(v not in ('iso','front','side','top') for v in views):
        raise ValueError('views must be at most two of iso/front/side/top')


def capture_views(output, views):
    import dsh_hou_helpers as h
    validate_capture_views(views)
    captures=[]
    for view in views:
        if not hou.isUIAvailable():
            captures.append({'view':view,'status':'unverified','reason':'GUI/OpenGL unavailable'});continue
        result=h.render_view(output,direction=view)
        captures.append({k:result[k] for k in ('ok','picture','file_status','pixel_status','semantic_status','stale','camera','framing','check','errors','user_state_restored') if k in result} | {'view':view})
        if result.get('user_state_restored') is False:
            raise h.CheckpointError('review capture did not restore user state',{'restored':False,'captures':captures})
    return captures


def test_controls(controller, output, tests, interfaces=None, allow_foreign=None, *, domain=None, topology=None, views=None, response_only=False):
    """Bounded numeric-control perturbation, declared measurement and restoration.

    Each test has id, numeric values dict and expectations [{metric,axis?,group?,
    delta:[min,max]}]. Optional actual-output interfaces are rechecked throughout.
    Operates only on numeric scalar controller parms, no menus/buttons/multiparms.
    Geometry bgeo fingerprints include primitive intrinsics, not just P. External
    files, Python/solver side effects and user callbacks are NOT transactional.
    """
    import dsh_hou_helpers as h
    ctrl=h._resolve(controller)
    h._require_owned(ctrl,'test_controls',allow_foreign)
    if type(response_only) is not bool:raise ValueError('response_only must be boolean')
    views=[] if views is None else views
    validate_capture_views(views)
    if not isinstance(tests,list) or not 1 <= len(tests) <= 16:
        raise ValueError('tests must contain 1..16 bounded cases')
    if interfaces is not None:validate_interfaces(interfaces)
    if domain is not None:validate_domain(domain)
    if topology is not None:validate_topology(topology)
    ids=set();names=set()
    for test in tests:
        _exact_keys(test, {'id','values','expectations'}, 'control test')
        if not isinstance(test.get('id'),str) or not test['id'] or test['id'] in ids:
            raise ValueError('test ids must be nonempty and unique')
        ids.add(test['id'])
        values=test.get('values')
        expectations=test.get('expectations',[]) if response_only else test.get('expectations')
        if not isinstance(values,dict) or not 1 <= len(values) <= 8:
            raise ValueError('each test needs 1..8 numeric scalar parameter values')
        if not isinstance(expectations,list) or not (0 if response_only else 1) <= len(expectations) <= 16:
            raise ValueError('each test needs 1..16 declared measurement expectations')
        for name,value in values.items():
            _finite(value,'control value')
            p=ctrl.parm(name)
            if p is None or p.parmTemplate().type() not in (hou.parmTemplateType.Float,hou.parmTemplateType.Int):
                raise ValueError(f'{name}: only numeric scalar controls supported')
            tpl=p.parmTemplate()
            if tpl.scriptCallback() or p.isMultiParmInstance():
                raise ValueError(f'{name}: callbacks/multiparms are not supported control-test targets')
            try:
                if tpl.menuItems():
                    raise ValueError(f'{name}: menu controls are not supported')
            except AttributeError:
                pass
            if tpl.type()==hou.parmTemplateType.Int and type(value) is not int:
                raise ValueError(f'{name}: integer parameter needs integer value')
            if float(p.eval())==float(value):
                raise ValueError(f'{name}: perturbation must differ from current value')
            names.add(name)
        for expectation in expectations:_validate_expectation(expectation)
        if expectations and not any(e['delta'][0] > 0 or e['delta'][1] < 0 for e in expectations):
            raise ValueError('each control case needs at least one non-zero expected response; add invariants as additional expectations')
    snapshots=h._parameter_snapshot([ctrl.parm(n) for n in sorted(names)])
    original_frame=float(hou.frame())
    baseline_domain=domain_checks(ctrl,domain or [])
    if any(r['status']=='fail' for r in baseline_domain):
        return {'ok':False,'status':'fail','controller':ctrl.path(),'output':h._resolve(output).path(),
                'results':[],'baseline_domain':baseline_domain,'restored':True,'parameter_writes':0,
                'reason':'baseline outside declared parameter domain','semantic_status':'unverified'}
    node, baseline=_geometry(output)
    unsupported_types=sorted({p.type().name() for p in baseline.prims()} - {'Polygon','Mesh','Sphere','Tube'})
    if unsupported_types:
        # Packed serialization may contain recook-varying IDs. A raw bgeo hash
        # is not an established restoration oracle for those representations.
        return {'ok':False,'status':'unverified','controller':ctrl.path(),'output':node.path(),
                'frame':original_frame,'checked_at':time.time(),'restored':True,'results':[],
                'reason':f'control restoration oracle not verified for {unsupported_types}',
                'parameter_writes':0,'semantic_status':'unverified',
                'scope':'unsupported output representation; zero parameter writes'}
    baseline_hash=_data_signature(baseline)
    baseline_relations=_check_interfaces(baseline,interfaces,50000) if interfaces is not None else None
    baseline_topology=_check_topology(baseline,topology) if topology is not None else None
    if baseline_topology is not None and not baseline_topology['ok']:
        return {'ok':False,'status':baseline_topology['status'],'controller':ctrl.path(),'output':node.path(),
                'frame':original_frame,'checked_at':time.time(),'restored':True,'baseline_topology':baseline_topology,
                'parameter_writes':0,'results':[],'semantic_status':'unverified',
                'next_action':'Fix the baseline selected surface topology before testing controls; zero parameter writes.'}
    if baseline_relations is not None and not baseline_relations['ok']:
        return {'ok':False,'status':baseline_relations['status'],'controller':ctrl.path(),'output':node.path(),
                'frame':original_frame,'checked_at':time.time(),'restored':True,'baseline_interfaces':baseline_relations,
                'results':[],'semantic_status':'unverified','next_action':'Fix the baseline interface before perturbing controls; zero parameter writes.'}
    # Resolve every measurement BEFORE the first write.
    try:
        baselines={test['id']:[_measure(baseline,e) for e in test.get('expectations',[])] for test in tests}
        if not all(math.isfinite(float(v)) for values in baselines.values() for v in values):
            raise UnsupportedEvidence('nonfinite baseline measurement; zero parameter writes')
    except UnsupportedEvidence as error:
        return {'ok':False,'status':'unverified','controller':ctrl.path(),'output':node.path(),
                'frame':original_frame,'checked_at':time.time(),'restored':True,'results':[],
                'reason':str(error),'semantic_status':'unverified','scope':'unsupported metric; zero parameter writes'}
    rows=[];all_restored=True
    for test in tests:
        row={'id':test['id'],'values':test['values'],'status':'fail'}
        # Independent unkeyed controls permit zero-write candidate preflight.
        # Expressions/animation may couple other domain variables: check their
        # actual values AFTER applying the case instead of predicting them.
        domain_names={c['left'] for c in domain or []} | {c['right'] for c in domain or [] if isinstance(c['right'],str)}
        if domain and not any(ctrl.parm(n).keyframes() for n in domain_names | set(test['values'])):
            proposed=domain_checks(ctrl,domain,test['values'])
            if any(r['status']=='fail' for r in proposed):
                rows.append({**row,'domain':proposed,'reason':'test value outside declared parameter domain',
                             'restored':True,'parameter_writes':0})
                continue
        try:
            h.set_parms(ctrl,test['values'],allow_foreign=allow_foreign)
            actual={name:ctrl.parm(name).eval() for name in test['values']}
            row['actual_values']=actual
            if any(not math.isclose(float(actual[name]),float(value),rel_tol=1e-9,abs_tol=1e-12)
                   for name,value in test['values'].items()):
                raise ValueError('requested test value did not apply exactly (possibly clamped); do not accept an unexercised case')
            if domain:
                row['domain']=domain_checks(ctrl,domain)
                if any(r['status']=='fail' for r in row['domain']):
                    raise ValueError('actual perturbed values outside declared parameter domain')
            cook=h.cook_node(node,force=True)
            if not cook['ok']:raise ValueError(f'perturbed cook failed: {cook["errors"]}')
            _,g=_geometry(node)
            measurements=[]
            for exp,start in zip(test.get('expectations',[]),baselines[test['id']]):
                end=_measure(g,exp);delta=end-start;lo,hi=exp['delta']
                if not math.isfinite(float(end)):raise UnsupportedEvidence('nonfinite measured value')
                measurements.append({'expectation':exp,'baseline':start,'measured':end,'delta':delta,'pass':lo<=delta<=hi})
            relations=_check_interfaces(g,interfaces,50000) if interfaces is not None else None
            topology_check=_check_topology(g,topology) if topology is not None else None
            measurements_pass=all(m['pass'] for m in measurements)
            checks=[r for r in (relations,topology_check) if r is not None]
            case_status='fail' if not measurements_pass or any(r['status']=='fail' for r in checks) else 'unverified' if any(r['status']=='unverified' for r in checks) else 'pass'
            row.update({'status':case_status,'measurements':measurements,'interfaces':relations,'topology':topology_check,
                        'geometry_changed':_data_signature(g)!=baseline_hash,'warnings':cook['warnings']})
            if not measurements:
                row['response_status']='responsive' if row['geometry_changed'] else 'unchanged'
                if row['status']=='pass':row['status']='unverified'
            if views:row['captures']=capture_views(node,views)
        except UnsupportedEvidence as error:
            row.update({'status':'unverified','reason':str(error)})
        except h.CheckpointError:
            # Restoring numeric controls cannot erase a broader user-state fault.
            raise
        except Exception as error:
            row.update({'status':'fail','reason':str(error)})
        finally:
            errors=h._restore_parameters(snapshots)
            if float(hou.frame())!=original_frame:
                try:hou.setFrame(original_frame)
                except Exception as error:errors.append('frame: '+str(error))
            try:
                cook=h.cook_node(node,force=True)
                _,restored=_geometry(node)
                geometry_restored=cook['ok'] and _data_signature(restored)==baseline_hash
            except Exception as error:
                errors.append('output restore: '+str(error));geometry_restored=False
            row['restored']=not errors and geometry_restored
            row['restore_errors']=errors
            if not row['restored']:
                all_restored=False
                raise h.CheckpointError('test_controls restoration failed; inspect controller/output before continuing',
                                        {'ok':False,'output':node.path(),'restored':False,'results':rows+[row]})
        rows.append(row)
    ok=all(r['status']=='pass' for r in rows) and (baseline_relations is None or baseline_relations['ok'])
    status='pass' if ok else 'fail' if any(r['status']=='fail' for r in rows) or (baseline_relations and baseline_relations['status']=='fail') else 'unverified'
    return {'ok':ok,'status':status,'controller':ctrl.path(),'output':node.path(),
            'frame':original_frame,'checked_at':time.time(),'restored':all_restored,'baseline_sha256':baseline_hash,
            'baseline_interfaces':baseline_relations,'baseline_topology':baseline_topology,'baseline_domain':baseline_domain,'results':rows,'semantic_status':'unverified',
            'contract_sha256':hashlib.sha256(json.dumps({'tests':tests,'interfaces':interfaces,'domain':domain,'topology':topology},sort_keys=True).encode()).hexdigest(),
            'scope':'only declared control cases and explicit-output measurements; not all combinations or unspecified relationships',
            'next_action':'Fix failed responses/interfaces; preserve drafts. Do not claim full controllability from one global geometry change.'}
