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


def _center_axis_surface_hits(prims, axes, lower, upper):
    """Intersect each basis-aligned bbox-center line with polygon triangles.

    This is surface evidence, not a solid classifier. In particular, zero hits
    along a declared hole axis can support a visible through opening only when
    closure/manifold checks also pass; a filled cap normally produces two hits.
    """
    center = [(lower[i] + upper[i]) * .5 for i in range(3)]
    scale = max((upper[i] - lower[i] for i in range(3)), default=1.0)
    determinant_epsilon = max(scale * scale, 1e-18) * 1e-10
    barycentric_epsilon = 1e-8
    position_epsilon = max(scale, 1e-9) * 1e-7

    def projected(position):
        values = [sum(float(position[k]) * axes[i][k] for k in range(3)) for i in range(3)]
        return [values[i] - center[i] for i in range(3)]

    def dot(a, b): return sum(x * y for x, y in zip(a, b))
    def sub(a, b): return [x - y for x, y in zip(a, b)]
    def cross(a, b):
        return [a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0]]

    rows = []
    for axis in range(3):
        direction = [1.0 if i == axis else 0.0 for i in range(3)]
        hits, coplanar = [], 0
        for prim in prims:
            polygon = [projected(v.point().position()) for v in prim.vertices()]
            if len(polygon) < 3:
                continue
            for index in range(1, len(polygon) - 1):
                a, b, c = polygon[0], polygon[index], polygon[index + 1]
                edge1, edge2 = sub(b, a), sub(c, a)
                h = cross(direction, edge2)
                determinant = dot(edge1, h)
                if abs(determinant) <= determinant_epsilon:
                    normal = cross(edge1, edge2)
                    if dot(normal, normal) > determinant_epsilon * determinant_epsilon and abs(dot(normal, a)) <= position_epsilon * math.sqrt(dot(normal, normal)):
                        coplanar += 1
                    continue
                inverse = 1.0 / determinant
                offset = [-value for value in a]
                u = inverse * dot(offset, h)
                q = cross(offset, edge1)
                v = inverse * dot(direction, q)
                if u < -barycentric_epsilon or v < -barycentric_epsilon or u + v > 1.0 + barycentric_epsilon:
                    continue
                hits.append(inverse * dot(edge2, q))
        unique = []
        for value in sorted(hits):
            if not unique or abs(value - unique[-1]) > position_epsilon:
                unique.append(value)
        rows.append({
            'axis': axis,
            'surface_hits': len(unique),
            'positions': unique[:16],
            'positions_truncated': len(unique) > 16,
            'status': 'unverified' if coplanar else 'observed',
            'coplanar_triangles': coplanar,
        })
    return {
        'origin': center,
        'axes': rows,
        'scope': 'Intersections of each basis-aligned line through the selected bbox center with fan-triangulated polygon surfaces. Zero hits is not alone proof of a through-hole; combine it with closed/manifold checks and an axis-aligned image.',
    }


def _shell_orientation(prims, edges, directed, root, *, include_planarity):
    """Report winding of each edge-connected shell; sign alone is not a solid classifier."""
    shells = defaultdict(list)
    for prim in prims:
        shells[root(prim.number())].append(prim)
    edges_by_shell = defaultdict(list)
    for edge, owners in edges.items():
        edges_by_shell[root(owners[0])].append((edge, owners))
    rows = []
    for component, faces in shells.items():
        shell_edges = edges_by_shell[component]
        closed = all(len(owners) == 2 for _, owners in shell_edges)
        consistent = all(len(owners) != 2 or directed[a,b] == directed[b,a]
                         for (a,b), owners in shell_edges)
        row = {'component': component, 'primitive_count': len(faces),
               'closed': closed, 'consistent': consistent}
        vertices = [tuple(vertex.point().position()) for face in faces for vertex in face.vertices()]
        low = [min(vertex[i] for vertex in vertices) for i in range(3)]
        high = [max(vertex[i] for vertex in vertices) for i in range(3)]
        scale = max(high[i] - low[i] for i in range(3))
        if include_planarity:
            center = hou.Vector3(vertices[0])
            normal = None
            for face in faces:
                polygon = [vertex.point().position() for vertex in face.vertices()]
                for index in range(1, len(polygon) - 1):
                    candidate = (polygon[index] - polygon[0]).cross(polygon[index + 1] - polygon[0])
                    if candidate.length() > max(scale * scale, 1e-24) * 1e-12:
                        normal = candidate.normalized()
                        break
                if normal is not None:
                    break
            row['planar'] = normal is not None and all(
                abs((hou.Vector3(vertex) - center).dot(normal)) <= max(scale, 1e-12) * 1e-8
                for vertex in vertices)
        if not closed or not consistent or any(float(face.intrinsicValue('measuredarea')) <= 1e-16
                                                for face in faces):
            row.update(status='unverified',
                       reason='requires closed, consistently wound, nondegenerate polygon shell')
        else:
            origin = hou.Vector3([(a + b) * .5 for a,b in zip(low, high)])
            terms = []
            for face in faces:
                face_vertices = [vertex.point().position() - origin for vertex in face.vertices()]
                # HOM polygon winding is opposite the right-handed fan product.
                terms.extend(-face_vertices[0].dot(face_vertices[index].cross(face_vertices[index + 1])) / 6
                             for index in range(1, len(face_vertices) - 1))
            volume = math.fsum(terms)
            epsilon = scale ** 3 * 1e-12
            row.update(status='observed', oriented_volume=volume,
                       sign='positive' if volume > epsilon else 'negative' if volume < -epsilon else 'near_zero')
        rows.append(row)
    limit = 32 if include_planarity else 8
    result = {'status': 'observed', 'components': rows[:limit],
              'components_truncated': len(rows) > limit,
              'positive_count': sum(row.get('sign') == 'positive' for row in rows),
              'negative_count': sum(row.get('sign') == 'negative' for row in rows),
              'unverified_count': sum(row['status'] == 'unverified' or row.get('sign') == 'near_zero'
                                      for row in rows),
              'scope': 'Positive follows outward HOM winding ONLY for a simple unnested closed shell. Self-intersections, nested cavities and solid validity are NOT tested. Near-zero or inconsistent/open shells cannot establish inward/outward.'}
    if not include_planarity:
        result['negative_sample'] = [row['component'] for row in rows if row.get('sign') == 'negative'][:8]
        result['negative_sample_truncated'] = result['negative_count'] > 8
    return result, sum(row['closed'] and row['planar'] for row in rows) if include_planarity else 0


def _normal_attribute_observation(g, prims):
    """Find N attributes pointing against their own Polygon winding, not against a design axis."""
    attributes = [('vertex', g.findVertexAttrib('N')),
                  ('point', g.findPointAttrib('N')),
                  ('primitive', g.findPrimAttrib('N'))]
    classes = []
    for kind, attribute in attributes:
        if attribute is None:
            continue
        row = {'class': kind, 'checked': 0, 'opposed': 0, 'invalid': 0, 'sample': []}
        for prim in prims:
            face_normal = prim.normal()
            face_length = face_normal.length()
            if kind == 'primitive':
                elements = [prim]
            else:
                elements = prim.vertices() if kind == 'vertex' else prim.points()
            for element in elements:
                try:
                    value = element.attribValue(attribute)
                    normal = hou.Vector3(value)
                    normal_length = normal.length()
                    if (face_length <= 1e-12 or normal_length <= 1e-12
                            or not all(math.isfinite(float(component)) for component in normal)):
                        row['invalid'] += 1
                        continue
                    row['checked'] += 1
                    if face_normal.dot(normal) / (face_length * normal_length) < -0.5:
                        row['opposed'] += 1
                        if len(row['sample']) < 8:
                            row['sample'].append(prim.number())
                except (TypeError, ValueError, hou.Error):
                    row['invalid'] += 1
        classes.append(row)
    checked = sum(row['checked'] for row in classes)
    opposed = sum(row['opposed'] for row in classes)
    return {'status': 'absent' if not classes else 'unverified' if not checked else
            'opposed_present' if opposed else 'observed', 'classes': classes,
            'opposed_count': opposed,
            'scope': 'Explicit N attributes compared with their own polygon geometric normals. Smoothing, stylized normals and mixed attribute classes require interpretation; this does not establish outward facing.'}


def polygon_observation(g, group=None, basis=None, *, integrity_only=False):
    if type(integrity_only) is not bool:
        raise ValueError('integrity_only must be boolean')
    prims = selected_prims(g, group)
    result = {'method': ('bounded polygon surface integrity' if integrity_only else
                         'full selected polygon topology and point extents'), 'group': group,
              'coordinate_space': 'SOP local', 'semantic_status': 'unverified',
              'note': 'Boundaries concern the selected surface, including intentional group cuts; no self-intersection, solid containment or art claim.'}
    if not prims:
        return {**result, 'status': 'unverified', 'reason': 'empty polygon selection'}
    primitive_budget = 100000 if integrity_only else 20000
    vertex_budget = 400000 if integrity_only else 100000
    if len(prims) > primitive_budget:
        return {**result, 'status': 'unverified',
                'reason': f'selection exceeds {primitive_budget} primitive budget'}
    if any(p.type() != hou.primType.Polygon or not p.isClosed() for p in prims):
        return {**result, 'status': 'unverified', 'reason': 'requires closed polygon faces; curves/native/packed are not interpreted as polygon surfaces'}
    if sum(len(p.vertices()) for p in prims) > vertex_budget:
        return {**result, 'status': 'unverified',
                'reason': f'selection exceeds {vertex_budget} vertex budget'}
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
    face_keys, repeated_faces, areas = set(), [], []
    planar_repeated_point_ngons = []
    for p in prims:
        ids = [v.point().number() for v in p.vertices()]
        for v in p.vertices(): pts[v.point().number()] = tuple(v.point().position())
        area = float(p.intrinsicValue('measuredarea'))
        areas.append(area)
        coords_face = [pts[i] for i in ids]
        if integrity_only and len(ids) >= 8 and len(set(ids)) < len(ids):
            # Boolean can preserve a planar face with bridge vertices around
            # holes. That is valid topology, yet implicit smooth shading may
            # make its flat interior look dented while the object rotates.
            normal = p.normal()
            if normal.length() > 1e-12:
                origin = hou.Vector3(coords_face[0])
                plane_tolerance = max(max(float(v) for v in p.boundingBox().sizevec()) * 1e-6, 1e-9)
                if all(abs((hou.Vector3(position) - origin).dot(normal.normalized())) <= plane_tolerance
                       for position in coords_face):
                    planar_repeated_point_ngons.append(p.number())
        if coords_face:
            # Cyclic boundary equality, not a sorted vertex-set guess. Reverse
            # winding and distinct point identities may still duplicate a face.
            def canonical_cycle(values):
                start = min(range(len(values)), key=values.__getitem__)
                return tuple(values[start:] + values[:start])
            key = min(canonical_cycle(coords_face), canonical_cycle(list(reversed(coords_face))))
            if key in face_keys: repeated_faces.append(p.number())
            face_keys.add(key)
        if not math.isfinite(area) or area <= 1e-16: zero_area += 1
        for a,b in zip(ids,ids[1:]+ids[:1]):
            edges[tuple(sorted((a,b)))].append(p.number()); directed[a,b] += 1
            if a==b or pts[a]==pts[b]: zero_edges += 1
    for owners in edges.values():
        for other in owners[1:]: parent[root(other)] = root(owners[0])
    if any(not math.isfinite(v) for p in pts.values() for v in p):
        return {**result,'status':'unverified','reason':'nonfinite geometry coordinates'}
    if integrity_only:
        orientation, _ = _shell_orientation(prims, edges, directed, root, include_planarity=False)
        shading_normals = _normal_attribute_observation(g, prims)
        boundary_count = sum(len(owners) == 1 for owners in edges.values())
        nonmanifold_count = sum(len(owners) > 2 for owners in edges.values())
        orientation_count = sum(len(owners) == 2 and directed[a,b] != directed[b,a]
                                for (a,b), owners in edges.items())
        risks = [name for name, count in (
            ('nonmanifold_edges', nonmanifold_count),
            ('orientation_conflicts', orientation_count),
            ('zero_area_faces', zero_area),
            ('zero_length_edges', zero_edges),
            ('duplicate_boundary_faces', len(repeated_faces)),
        ) if count]
        if orientation['negative_count']:
            risks.append('negative_closed_shell_winding_requires_review')
        if shading_normals['opposed_count']:
            risks.append('N_attribute_opposes_polygon_winding')
        return {**result, 'status': 'observed', 'selected_primitives': len(prims),
                'selected_points': len(pts), 'boundary_edges': boundary_count,
                'nonmanifold_edges': nonmanifold_count,
                'orientation_conflicts': orientation_count,
                'zero_area_faces': zero_area, 'zero_length_edges': zero_edges,
                'duplicate_boundary_faces': len(repeated_faces),
                'duplicate_face_sample': repeated_faces[:8],
                'planar_repeated_point_ngons': len(planar_repeated_point_ngons),
                'planar_repeated_point_sample': planar_repeated_point_ngons[:8],
                'shading_review_status': ('needs_visual_review' if planar_repeated_point_ngons else 'none'),
                'shell_orientation': orientation,
                'shading_normals': shading_normals,
                'orientation_review_status': ('negative_closed_shells_present' if orientation['negative_count']
                                              else 'unverified' if orientation['unverified_count'] else 'none'),
                'risk_status': 'needs_review' if risks else 'no_detected_integrity_risk',
                'risk_reasons': risks,
                'boundary_review_status': ('open_boundary_unreviewed' if boundary_count else 'none'),
                'scope': 'Bounded final polygon surface diagnostic only. Planar repeated-point n-gons are shading review candidates, not integrity failure. Open boundaries can be intentional; no contact, self-intersection, strength, or appearance certification.'}
    coords = [[sum(v*a for v,a in zip(p,axis)) for axis in axes] for p in pts.values()]
    lower = [min(p[i] for p in coords) for i in range(3)]
    upper = [max(p[i] for p in coords) for i in range(3)]
    boundary = [edge for edge,owners in edges.items() if len(owners)==1]
    orientation, closed_planar_count = _shell_orientation(prims, edges, directed, root,
                                                          include_planarity=True)
    center_axis_hits = _center_axis_surface_hits(prims, axes, lower, upper)
    return {**result, 'status': 'observed', 'selected_primitives':len(prims), 'selected_points':len(pts),
            'surface_area': math.fsum(areas),
            'duplicate_boundary_faces':len(repeated_faces), 'duplicate_face_sample':repeated_faces[:16],
            'closed_planar_components':closed_planar_count,
            'overlap_scope':'Exact coincident cyclic boundaries and closed coplanar shells are risk evidence, not arbitrary overlap detection. A filled polygon plus tessellation can close a zero-thickness shell; intentional double-sided surfaces require explicit interpretation.',
            'edge_connected_components':len({root(n) for n in parent}),
            'boundary_edges':len(boundary), 'boundary_edge_sample':boundary[:16],
            'boundary_sample_truncated':len(boundary)>16,
            'nonmanifold_edges':sum(len(o)>2 for o in edges.values()),
            'orientation_conflicts':sum(len(o)==2 and directed[a,b]!=directed[b,a] for (a,b),o in edges.items()),
            'zero_area_faces':zero_area,'zero_length_edges':zero_edges,'shell_orientation':orientation,
            'center_axis_surface_hits':center_axis_hits,
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


def attribute_uniqueness(g, attrib, attrib_class, max_elements):
    """Exact tuple identity; finite, complete, bounded, no rounding/sampling."""
    count = 1 if attrib_class == 'detail' else int(g.intrinsicValue(
        {'point':'pointcount','prim':'primitivecount','vertex':'vertexcount'}[attrib_class]))
    if count > max_elements or count*attrib.size() > 1000000:
        raise ValueError('uniqueness budget exceeded; narrow the input, no sampling')
    if attrib.isArrayType():
        raise ValueError('array attributes are not supported by tuple uniqueness')
    elements = {'point':g.points, 'prim':g.prims,
                'vertex':lambda:(v for p in g.prims() for v in p.vertices()), 'detail':lambda:[g]}[attrib_class]()
    counts, samples = {}, {}
    for index, element in enumerate(elements):
        value = element.attribValue(attrib)
        key = tuple(value) if isinstance(value,(tuple,list)) else (value,)
        if any(isinstance(v, (float,int)) and not math.isfinite(v) for v in key):
            raise ValueError('nonfinite attribute value; uniqueness unverified')
        counts[key] = counts.get(key, 0)+1
        if key not in samples: samples[key] = index
    duplicates = [{'value':list(k), 'count':v, 'first_element':samples[k]} for k,v in counts.items() if v>1]
    return {'count':count, 'unique_count':len(counts), 'duplicate_count':count-len(counts),
            'all_unique':count>0 and count==len(counts), 'duplicate_samples':duplicates[:8],
            'samples_truncated':len(duplicates)>8, 'comparison':'exact_complete_attribute_tuple',
            'coverage':'all_elements', 'semantic_status':'unverified'}


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
    transform = hou.Matrix4(item['transform']) if item['metric']=='max_transform_error' else hou.Matrix4(1)
    distances=[(a[k]*transform-b[k]).length() for k in a]
    if any(not math.isfinite(v) for v in distances):raise ValueError('nonfinite displacement')
    return max(distances) if item['metric'] in ('max_point_displacement','max_transform_error') else sum(distances)/len(distances)
