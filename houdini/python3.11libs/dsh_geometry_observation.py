"""Bounded polygon observations; no scene nodes, side effects or art claims."""
import math
from collections import defaultdict
import hou


def selected_prims(g, group=None):
    if group is not None:
        if not isinstance(group, str) or not group:
            raise ValueError('group must be an exact nonempty primitive group name')
        selected = g.findPrimGroup(group)
        if selected is None: raise ValueError(f'missing primitive group: {group}')
        prims = list(selected.prims())
    else: prims = list(g.prims())
    if not prims: raise ValueError('empty observation selection')
    return prims


def polygon_observation(g, group=None, basis=None):
    prims = selected_prims(g, group)
    result = {'method': 'full selected polygon topology and point extents', 'group': group,
              'coordinate_space': 'SOP local', 'semantic_status': 'unverified',
              'note': 'Boundaries concern the selected surface, including intentional group cuts; no self-intersection, solid containment or art claim.'}
    if len(prims) > 20000:
        return {**result, 'status': 'unverified', 'reason': 'selection exceeds 20000 primitive budget'}
    if any(p.type() != hou.primType.Polygon or not p.isClosed() for p in prims):
        return {**result, 'status': 'unverified', 'reason': 'requires closed polygon faces; curves/native/packed are not interpreted as polygon surfaces'}
    if sum(len(p.vertices()) for p in prims) > 100000:
        return {**result, 'status': 'unverified', 'reason': 'selection exceeds 100000 vertex budget'}
    axes = basis if basis is not None else [[1,0,0],[0,1,0],[0,0,1]]
    if not isinstance(axes, (list, tuple)) or len(axes) != 3 or any(not isinstance(a,(list,tuple)) or len(a)!=3 for a in axes):
        raise ValueError('basis must contain three orthonormal 3D axes')
    axes = [[float(v) for v in a] for a in axes]
    if any(not math.isfinite(v) for a in axes for v in a) or any(abs(sum(x*y for x,y in zip(a,b)) - (1 if i==j else 0)) > 1e-6 for i,a in enumerate(axes) for j,b in enumerate(axes)):
        raise ValueError('basis must be finite and orthonormal')
    edges, directed = defaultdict(list), defaultdict(int)
    parent = {p.number():p.number() for p in prims}
    def root(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]; n = parent[n]
        return n
    pts, zero_area, zero_edges = {}, 0, 0
    for p in prims:
        ids = [v.point().number() for v in p.vertices()]
        for v in p.vertices(): pts[v.point().number()] = tuple(v.point().position())
        area = float(p.intrinsicValue('measuredarea'))
        if not math.isfinite(area) or area <= 1e-16: zero_area += 1
        for a,b in zip(ids,ids[1:]+ids[:1]):
            edges[tuple(sorted((a,b)))].append(p.number()); directed[a,b] += 1
            if a==b or pts[a]==pts[b]: zero_edges += 1
    for owners in edges.values():
        for other in owners[1:]: parent[root(other)] = root(owners[0])
    if any(not math.isfinite(v) for p in pts.values() for v in p):
        return {**result,'status':'unverified','reason':'nonfinite geometry coordinates'}
    coords = [[sum(v*a for v,a in zip(p,axis)) for axis in axes] for p in pts.values()]
    lower = [min(p[i] for p in coords) for i in range(3)]
    upper = [max(p[i] for p in coords) for i in range(3)]
    boundary = [edge for edge,owners in edges.items() if len(owners)==1]
    shells = defaultdict(list)
    for p in prims: shells[root(p.number())].append(p)
    edges_by_shell = defaultdict(list)
    for edge, owners in edges.items(): edges_by_shell[root(owners[0])].append((edge,owners))
    shell_rows = []
    for rid, faces in shells.items():
        shell_edges = edges_by_shell[rid]
        closed = all(len(o)==2 for e,o in shell_edges)
        consistent = all(len(o)!=2 or directed[a,b]==directed[b,a] for (a,b),o in shell_edges)
        row = {'component':rid, 'primitive_count':len(faces), 'closed':closed, 'consistent':consistent}
        if not closed or not consistent or any(float(p.intrinsicValue('measuredarea'))<=1e-16 for p in faces):
            row.update(status='unverified',reason='requires closed, consistently wound, nondegenerate polygon shell')
        else:
            positions = [hou.Vector3(pts[v.point().number()]) for p in faces for v in p.vertices()]
            low = [min(p[i] for p in positions) for i in range(3)]
            high = [max(p[i] for p in positions) for i in range(3)]
            origin = hou.Vector3([(a+b)*.5 for a,b in zip(low,high)])
            terms = []
            for p in faces:
                vs = [v.point().position()-origin for v in p.vertices()]
                # HOM polygon winding is opposite the right-handed fan product.
                terms.extend(-vs[0].dot(vs[i].cross(vs[i+1]))/6 for i in range(1,len(vs)-1))
            volume = math.fsum(terms)
            epsilon = max(high[i]-low[i] for i in range(3))**3 * 1e-12
            row.update(status='observed',oriented_volume=volume,
                       sign='positive' if volume>epsilon else 'negative' if volume < -epsilon else 'near_zero')
        shell_rows.append(row)
    orientation = {'status':'observed', 'components':shell_rows[:32], 'components_truncated':len(shell_rows)>32,
                   'positive_count':sum(r.get('sign')=='positive' for r in shell_rows),
                   'negative_count':sum(r.get('sign')=='negative' for r in shell_rows),
                   'unverified_count':sum(r['status']=='unverified' or r.get('sign')=='near_zero' for r in shell_rows),
                   'scope':'Positive follows outward HOM winding ONLY for a simple unnested closed shell. Self-intersections, nested cavities and solid validity are NOT tested. Near-zero or inconsistent/open shells cannot establish inward/outward.'}
    return {**result, 'status': 'observed', 'selected_primitives':len(prims), 'selected_points':len(pts),
            'edge_connected_components':len({root(n) for n in parent}),
            'boundary_edges':len(boundary), 'boundary_edge_sample':boundary[:16],
            'boundary_sample_truncated':len(boundary)>16,
            'nonmanifold_edges':sum(len(o)>2 for o in edges.values()),
            'orientation_conflicts':sum(len(o)==2 and directed[a,b]!=directed[b,a] for (a,b),o in edges.items()),
            'zero_area_faces':zero_area,'zero_length_edges':zero_edges,'shell_orientation':orientation,
            'basis':axes,'bounds_min':lower,'bounds_max':upper,'extents':[b-a for a,b in zip(lower,upper)]}


def surface_sections(prims, axis, position, expected_components):
    """Intersect actual polygon faces with a plane; never edit or resample the asset."""
    if len(prims)>20000 or sum(len(p.vertices()) for p in prims)>100000:
        raise ValueError('section exceeds polygon budget')
    if any(p.type()!=hou.primType.Polygon or not p.isClosed() for p in prims):
        raise ValueError('section requires closed polygon faces')
    parents={p.number():p.number() for p in prims};owners={}
    def root(i):
        while parents[i]!=i:
            parents[i]=parents[parents[i]];i=parents[i]
        return i
    coords=[v.point().position() for p in prims for v in p.vertices()]
    if not coords or any(not math.isfinite(x) for v in coords for x in v):raise ValueError('empty or nonfinite section source')
    scale=max(max(v[i] for v in coords)-min(v[i] for v in coords) for i in range(3))
    eps=max(scale,1e-9)*1e-9
    for p in prims:
        ids=[v.point().number() for v in p.vertices()]
        for a,b in zip(ids,ids[1:]+ids[:1]):
            key=tuple(sorted((a,b)))
            if key in owners:parents[root(p.number())]=root(owners[key])
            else:owners[key]=p.number()
    components={root(i) for i in parents}
    if len(components)!=expected_components:raise ValueError('source component count differs from expected_components')
    def key(v):return tuple(round(x/eps) for x in v)
    segments=defaultdict(dict)
    for p in prims:
        vs=[v.point().position() for v in p.vertices()];dist=[v[axis]-position for v in vs]
        if all(abs(d)<=eps for d in dist):raise ValueError('coplanar source face makes section ambiguous')
        hits={}
        for a,b in zip(vs,vs[1:]+vs[:1]):
            da,db=a[axis]-position,b[axis]-position
            if abs(da)<=eps:hits[key(a)]=a
            if da*db<0 and abs(da)>eps and abs(db)>eps:
                v=a+(b-a)*(da/(da-db));hits[key(v)]=v
        if len(hits)==1:continue  # plane touches a single vertex
        if len(hits)>2:raise ValueError('nonconvex or coplanar-edge face section is ambiguous')
        if len(hits)==2:
            keys=tuple(sorted(hits));segments[root(p.number())][keys]=(hits[keys[0]],hits[keys[1]],p.number())
    samples=[];coverage=[]
    for cid in sorted(components):
        segs=segments[cid];degree=defaultdict(int)
        for a,b in segs:degree[a]+=1;degree[b]+=1
        if not segs or any(n!=2 for n in degree.values()):raise ValueError('each source component must have a nonempty closed section')
        coverage.append({'component':cid,'segments':len(segs)})
        for a,b,pid in segs.values():samples.append({'position':(a+b)*.5,'source_primitive':pid,'component':cid})
    if len(samples)>512:raise ValueError('section exceeds 512 sample budget; narrow source groups')
    return samples,coverage


def point_displacement(g, reference, item):
    """Stable IDs plus identical face membership required; never compare by point order."""
    name = item.get('id_attrib')
    if not isinstance(name,str) or not name: raise ValueError('point displacement requires id_attrib with stable unique point IDs')
    def mapped(geo):
        attr=geo.findPointAttrib(name)
        if attr is None or attr.size()!=1 or attr.dataType() not in (hou.attribData.Int,hou.attribData.String):
            raise ValueError('id_attrib must be a scalar integer/string point attribute')
        prims=selected_prims(geo,item.get('group'))
        if len(prims)>20000 or sum(len(p.vertices()) for p in prims)>100000:raise ValueError('displacement exceeds geometry budget')
        if any(p.type()!=hou.primType.Polygon for p in prims):raise ValueError('point displacement only supports polygon geometry')
        points={p.number():p for prim in prims for p in prim.points()}
        ids={i:p.attribValue(attr) for i,p in points.items()}
        if len(set(ids.values()))!=len(ids):raise ValueError('duplicate stable point IDs')
        topology=sorted((bool(pr.isClosed()),tuple(ids[p.number()] for p in pr.points())) for pr in prims)
        return {ids[i]:p.position() for i,p in points.items()},topology
    a,ta=mapped(reference);b,tb=mapped(g)
    if a.keys()!=b.keys() or ta!=tb:raise ValueError('stable-ID topology changed; displacement correspondence unverified')
    distances=[(a[k]-b[k]).length() for k in a]
    if any(not math.isfinite(v) for v in distances):raise ValueError('nonfinite displacement')
    return max(distances) if item['metric']=='max_point_displacement' else sum(distances)/len(distances)
