"""In-memory packed observation, dense solid intersection and restoration."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_quality_contracts as q
from dsh_geometry_evidence import expanded_view

with h._execution_owner('packed-evidence','fixture'):
    root=h.tab_create('/obj','geo','packed_evidence')
    ctrl=h.tab_create(root,'null','CTRL')
    h.create_spare_parms(ctrl,spec=[{'type':'float','name':'offset','default':3.0}])
    a=h.tab_create(root,'sphere','a');h.set_parms(a,{'type':'polymesh','rows':32,'cols':32})
    tag=h.tab_create(root,'groupcreate','tag_a');h.connect(a,tag,0);h.set_parms(tag,{'groupname':'a'})
    b=h.tab_create(root,'xform','b');h.connect(a,b,0);h.set_parms(b,{'tx':"ch('../CTRL/offset')"})
    tag_b=h.tab_create(root,'groupcreate','tag_b');h.connect(b,tag_b,0);h.set_parms(tag_b,{'groupname':'b'})
    out=h.tab_create(root,'merge','OUT_ASSET');h.connect(tag,out,0);h.connect(tag_b,out,1)
    overlap=[{'id':'clear','method':'solid_overlap','source_group':'a','target_group':'b','max_overlap_volume':0}]
    free=h.geo_check_interfaces(out,overlap)
    assert free['status']=='pass',free
    assert free['results'][0]['broad_phase']['cartesian_face_pairs']>900000
    h.set_parms(ctrl,{'offset':.5});colliding=h.geo_check_interfaces(out,overlap)
    assert colliding['status']=='fail' and colliding['results'][0]['overlap_volume']>0,colliding
    h.set_parms(ctrl,{'offset':3})
    pack_a=h.tab_create(root,'pack','pack_a');h.connect(tag,pack_a,0);h.set_parms(pack_a,{'transfer_groups':'*'})
    pack_b=h.tab_create(root,'pack','pack_b');h.connect(tag_b,pack_b,0);h.set_parms(pack_b,{'transfer_groups':'*'})
    packed=h.tab_create(root,'merge','packed');h.connect(pack_a,packed,0);h.connect(pack_b,packed,1)
    original=q._data_signature(packed.geometry());count=len(root.children())
    packed_check=h.geo_check_interfaces(packed,overlap)
    assert packed_check['status']=='pass' and packed_check['representation']['expanded'],packed_check
    assert len(root.children())==count and q._data_signature(packed.geometry())==original
    tests=[{'id':'move','values':{'offset':4.0},'expectations':[{'metric':'bounds_center','group':'b','axis':0,'delta':[.999,1.001]}]}]
    try: tested=h.test_controls(ctrl,packed,tests,interfaces=overlap)
    except h.CheckpointError as error:
        print(error.evidence["results"][-1]["geometry_restore"]);raise
    assert tested['status']=='pass' and tested['restored'],tested
    assert q._data_signature(packed.geometry())==original
    nested=h.tab_create(root,'pack','nested');h.connect(packed,nested,0)
    assert h.test_controls(ctrl,nested,tests,interfaces=overlap)['status']=='pass'
    # Hash includes embedded attributes, instance transforms and wrapper groups.
    stable=q._data_signature(nested.geometry())
    changed=hou.Geometry(nested.geometry());prim=changed.prims()[0]
    embedded=hou.Geometry(prim.getEmbeddedGeometry())
    embedded.addAttrib(hou.attribType.Global,'meaning','changed payload')
    prim.setEmbeddedGeometry(embedded)
    assert q._data_signature(changed)!=stable,'embedded user attributes must survive canonicalization'
    h.set_parms(b,{'ry':25});assert q._data_signature(nested.geometry())!=stable
    h.set_parms(b,{'ry':0});assert q._data_signature(nested.geometry())==stable
    # High-resolution partitioned surface review uses every named part.
    dense=h.tab_create(root,'sphere','dense');h.set_parms(dense,{'type':'polymesh','rows':151,'cols':151})
    named=h.tab_create(root,'attribwrangle','named');h.connect(dense,named,0)
    h.set_parms(named,{'class':'primitive','snippet':'s@part="outer";'})
    named_out=h.tab_create(root,'null','OUT_DENSE');h.connect(named,named_out,0)
    from dsh_geometry_evidence import surface_review,candidate_face_pairs
    review=surface_review(named_out.geometry())
    assert review['status']=='observed' and review['checked_parts']==1 and review['selected_primitives']>20000,review
    assert 'nonplanar' in review['planar_face_crossings']['skipped_faces']
    # Depth preflight rejects nested representations before parameter writes.
    deep=nested
    for i in range(8):
        layer=h.tab_create(root,'pack','deep_'+str(i));h.connect(deep,layer,0);deep=layer
    rejected=h.test_controls(ctrl,deep,tests)
    assert rejected['status']=='unverified' and rejected['parameter_writes']==0 and ctrl.evalParm('offset')==3,rejected
    volume=h.tab_create(root,'volume','unsupported_volume')
    rejected=h.test_controls(ctrl,volume,tests)
    assert rejected['status']=='unverified' and 'representation' in rejected['reason'],rejected
    # An unrelated native volume cannot invalidate declared polygon-only groups.
    mixed=h.tab_create(root,'merge','mixed');h.connect(packed,mixed,0);h.connect(volume,mixed,1)
    assert h.geo_check_interfaces(mixed,overlap)['status']=='pass'
    # Containment must use full operands even with no intersecting surface boxes.
    # Use smaller complete operands for this independent containment case.
    outer=hou.Geometry(a.geometry());inner=hou.Geometry(a.geometry());inner.transform(hou.hmath.buildScale((.2,.2,.2)))
    outer.createPrimGroup('outer').add(outer.prims());inner.createPrimGroup('inner').add(inner.prims());outer.merge(inner)
    contained=q._check_interfaces(outer,[{'id':'containment','method':'solid_overlap','source_group':'inner','target_group':'outer','max_overlap_volume':0}],50000)
    assert contained['status']=='fail',contained
    # Positive overlap after packing and native transforms must still fail.
    h.set_parms(ctrl,{'offset':.5})
    assert h.geo_check_interfaces(packed,overlap)['status']=='fail'
    h.set_parms(ctrl,{'offset':3})
    print('packed and dense evidence passed',hou.applicationVersionString())
