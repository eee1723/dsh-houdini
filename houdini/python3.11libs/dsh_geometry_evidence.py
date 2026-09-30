"""Bounded in-memory evidence views; never edits nodes or loads packed files."""
import hou

MAX_PRIMS=100000
MAX_POINTS=250000
MAX_VERTICES=400000
MAX_BYTES=32*1024*1024
MAX_DEPTH=8


def check_budget(g):
    if (g.intrinsicValue('primitivecount')>MAX_PRIMS or g.intrinsicValue('pointcount')>MAX_POINTS
            or g.intrinsicValue('vertexcount')>MAX_VERTICES or g.intrinsicValue('memoryusage')>MAX_BYTES):
        raise ValueError('geometry evidence budget exceeded; choose an explicit smaller final-output part')


def expanded_view(g, *, allow_native_unknown=False):
    """Only embedded PackedGeometry, fully transformed with groups/attributes.

    Preflight the full instance expansion before invoking Unpack; shared payloads
    count per instance. Disk/Alembic/fragments/agents remain unsupported.
    """
    totals={'primitives':0,'points':0,'vertices':0,'bytes':0,'packed_instances':0}
    def visit(geo,depth):
        if depth>MAX_DEPTH:raise ValueError('packed evidence nesting exceeds 8 levels')
        check_budget(geo)
        totals['points']+=len(geo.points())
        totals['bytes']+=int(geo.intrinsicValue('memoryusage'))
        for prim in geo.prims():
            name=prim.type().name()
            if name=='PackedGeometry':
                totals['packed_instances']+=1
                if totals['packed_instances']>4096:raise ValueError('packed evidence exceeds 4096 instances')
                visit(prim.getEmbeddedGeometry(),depth+1)
            elif name in ('Polygon','Mesh','Sphere','Tube') or (allow_native_unknown and not name.startswith('Packed') and 'Alembic' not in name and name!='Agent'):
                totals['primitives']+=1;totals['vertices']+=prim.numVertices()
            else:raise ValueError('unsupported evidence representation: '+name)
            if (totals['primitives']>MAX_PRIMS or totals['points']>MAX_POINTS
                    or totals['vertices']>MAX_VERTICES or totals['bytes']>MAX_BYTES):
                raise ValueError('expanded packed evidence budget exceeded before unpack')
    visit(g,0)
    if not totals['packed_instances']:return g,{'representation':'native','expanded':False,**totals}
    current=hou.Geometry(g)
    verb=hou.sopNodeTypeCategory().nodeVerb('unpack')
    verb.setParms({'iterations':1,'limit_iterations':1,'dotransform':1,
                   'transfer_attributes':'*','transfer_groups':'*','apply_style_sheets':0})
    for _ in range(MAX_DEPTH):
        if not any(p.type().name()=='PackedGeometry' for p in current.prims()):break
        result=hou.Geometry();verb.execute(result,[current]);check_budget(result);current=result
    if any(p.type().name()=='PackedGeometry' for p in current.prims()):
        raise ValueError('packed expansion incomplete')
    return current.freeze(read_only=True),{'representation':'embedded_packed','expanded':True,**totals,
        'scope':'transformed in-memory evidence copy; original packed geometry, transforms and embedded payload are separately fingerprinted; no disk loads'}


def candidate_face_pairs(source,target,budget):
    """Sweep one axis, test remaining AABBs; no surface sampling or simplification.

    Full closed operands still go to Boolean (containment has no surface pairs).
    Bounding boxes only reject impossible pairs, never prove positive contact.
    """
    events=[]
    for side,prims in enumerate((source,target)):
        for index,prim in enumerate(prims):
            box=prim.boundingBox();lo=tuple(box.minvec());hi=tuple(box.maxvec())
            events.append((lo[0],0,side,index,lo,hi));events.append((hi[0],1,side,index,lo,hi))
    active=[{},{}];count=0;visits=0
    for _,end,side,index,lo,hi in sorted(events):
        if end:active[side].pop(index,None);continue
        for other_lo,other_hi in active[1-side].values():
            visits+=1
            if visits>2000000:raise ValueError('solid_overlap broad-phase visit budget exceeded')
            if all(lo[a]<=other_hi[a] and other_lo[a]<=hi[a] for a in (1,2)):
                count+=1
                if count>budget:raise ValueError('solid_overlap candidate pair budget exceeded')
        active[side][index]=(lo,hi)
    return count


def surface_review(g):
    """Whole output integrity with complete, disjoint named-part partitions.

    Per-part closure is intentional; inter-part overlap requires interfaces.
    A missing/empty identity falls back to one complete bounded observation.
    """
    from dsh_geometry_observation import polygon_observation
    try:g,representation=expanded_view(g)
    except ValueError as error:return {'status':'unverified','reason':str(error)}
    attr=next((g.findPrimAttrib(n) for n in ('part','name') if g.findPrimAttrib(n)
               and g.findPrimAttrib(n).dataType()==hou.attribData.String and g.findPrimAttrib(n).size()==1),None)
    if attr is None or len(g.prims())<=20000:
        return {**polygon_observation(g,integrity_only=True),'representation':representation}
    parts={}
    for prim in g.prims():parts.setdefault(prim.attribValue(attr),[]).append(prim.number())
    if '' in parts or len(parts)>256:
        return {**polygon_observation(g,integrity_only=True),'representation':representation}
    copy=hou.Geometry(g);key='__dsh_evidence_partition'
    while copy.findPrimGroup(key):key+='x'
    group=copy.createPrimGroup(key);prims=copy.prims();reports=[]
    for name,ids in sorted(parts.items()):
        group.clear();group.add([prims[i] for i in ids])
        reports.append({'part':name,**polygon_observation(copy,key,integrity_only=True)})
    numeric=('selected_primitives','selected_points','boundary_edges','nonmanifold_edges','orientation_conflicts',
             'zero_area_faces','zero_length_edges','duplicate_boundary_faces','planar_repeated_point_ngons')
    risks=sorted({r for report in reports for r in report.get('risk_reasons',[])})
    unknown=[r['part'] for r in reports if r.get('status')!='observed']
    crossings=[r.get('planar_face_crossings',{}) for r in reports]
    crossing_unknown=bool(unknown) or any(c.get('status')!='observed' for c in crossings)
    return {'status':'unverified' if unknown else 'observed','method':'bounded partitioned polygon surface integrity',
            **{field:sum(r.get(field,0) for r in reports) for field in numeric},
            'selected_points':len(g.points()),
            'risk_status':'needs_review' if risks else 'unverified' if unknown else 'no_detected_integrity_risk',
            'risk_reasons':risks,'representation':representation,'partition_attribute':attr.name(),
            'part_count':len(parts),'checked_parts':len(parts)-len(unknown),'unverified_parts':unknown,
            'part_reports':[{k:r.get(k) for k in ('part','status','reason','risk_reasons','boundary_edges','selected_primitives')} for r in reports],
            'shell_orientation':{k:sum(r.get('shell_orientation',{}).get(k,0) for r in reports)
                                 for k in ('positive_count','negative_count','unverified_count')},
            'shading_review_status':'needs_visual_review' if any(r.get('shading_review_status')=='needs_visual_review' for r in reports) else 'none',
            'planar_face_crossings':{'status':'unverified' if crossing_unknown else 'observed',
                'coverage':'partial' if crossing_unknown else 'complete_within_scope',
                **{k:sum(c.get(k,0) for c in crossings) for k in ('checked_faces','triangle_faces','crossed_faces','crossing_pairs','tested_edge_pairs')},
                'skipped_faces':{k:sum(c.get('skipped_faces',{}).get(k,0) for c in crossings)
                                 for k in ('nonplanar','degenerate','face_vertex_budget','pair_budget')},
                'scope':'per-part eligible planar faces only; skipped scope preserved; not general 3-D intersection'},
            'scope':'complete disjoint part selections; part-local integrity only, cross-part overlap/attachment and visual quality require separate checks'}
