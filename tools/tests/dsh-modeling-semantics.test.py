"""v13: setting contracts, connection feedback, shell orientation and surface sections."""
import sys, pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_quality_contracts as q
import dsh_geometry_observation as o
import dsh_bridge as b
root=h.tab_create('/obj','geo','v13_contract_fixture')
try:
    card=h.node_info(root,'color',parm_filter='class')['parameters'][0]
    entry=next(m for m in card['menu'] if m['token']=='primitive')
    assert entry['set_value']==1,entry
    spec=[{'name':'source','type':'box'},{'name':'tint','type':'color','inputs':['source'],'parms':{'class':'primitive','colorr':.3}}]
    assert h.build_module(root,spec,output='tint',dry_run=True)['valid']
    assert h.build_module(root,spec,output='tint')['validation']['ok']
    color=root.node('tint');assert color.evalParm('class')==1 and not color.errors()
    h.set_parm(color,'class',{'expression':'2','language':'hscript'})
    keys=color.parm('class').keyframes()
    try:h.set_parm(color,'class','not_a_token')
    except ValueError:pass
    else:raise AssertionError('invalid integer menu token accepted')
    assert color.parm('class').keyframes()==keys
    h.set_parm(color,'class',entry['set_value']);assert color.evalParm('class')==1
    assert h.verify_network(root,output='tint')['ok']
    before=set(root.children())
    try:h.build_module(root,[{'name':'bad','type':'color','inputs':['source'],'parms':{'class':'not_a_token'}}],output='bad')
    except h.PreflightError:pass
    else:raise AssertionError('invalid token not statically rejected')
    assert set(root.children())==before
    # Int menu with token-valued storage must not confuse storage values and indices.
    ctrl=h.tab_create(root,'null','CTRL')
    tpl=hou.IntParmTemplate('choice','Choice',1,default_value=(10,),menu_items=('10','20'),menu_labels=('A','B'),menu_use_token=True)
    ctrl.addSpareParmTuple(tpl)
    h.set_parm(ctrl,'choice','20');assert ctrl.evalParm('choice')==20
    # Plain numeric strings still express channels outside menus.
    h.set_parm(root.node('source'),'sizex','2');assert root.node('source').evalParm('sizex')==2
    nodes=[h.tab_create(root,'null',n,inputs=[root.node('source')]) for n in ['first','middle','last','replacement']]
    m=h.tab_create(root,'merge','assembled',inputs=nodes[:3])
    r=h.connect(nodes[3],m,0)
    assert [n.name() for n in m.inputs()]==['replacement','middle','last']
    assert len(r['inputs_before']['connections'])==3 and len(r['inputs_after']['connections'])==3
    r=h.disconnect_input(m,0)
    assert [c['source'].split('/')[-1] for c in r['inputs_after']['connections']]==['middle','last']
    env=b.run_code(f'__result__=connect({nodes[3].path()!r},{m.path()!r},0)')
    assert 'inputs_after' in env['evidence'][0]
    # Primitive winding: reference box, fully reversed, mixed, and open.
    g=root.node('source').geometry().freeze()
    positive=o.polygon_observation(g)['shell_orientation'];assert positive['positive_count']==1,positive
    quick_positive=o.polygon_observation(g,integrity_only=True)
    assert quick_positive['risk_status']=='no_detected_integrity_risk' and quick_positive['shell_orientation']['positive_count']==1,quick_positive
    assert quick_positive['planar_repeated_point_ngons']==0
    # A Boolean-like flat face with bridge vertices around a hole can be
    # topologically valid yet shade unevenly. Report visual review separately
    # from geometry integrity.
    bridge_geo=hou.Geometry()
    bridge_points=[]
    for x,z in ((0,0),(4,0),(4,4),(0,4),(1,1),(1,3),(3,3),(3,1)):
        point=bridge_geo.createPoint();point.setPosition((x,0,z));bridge_points.append(point)
    bridge_face=bridge_geo.createPolygon()
    for index in (0,1,2,3,0,4,5,6,7,4):bridge_face.addVertex(bridge_points[index])
    bridge_obs=o.polygon_observation(bridge_geo,integrity_only=True)
    assert bridge_obs['planar_repeated_point_ngons']==1 and bridge_obs['shading_review_status']=='needs_visual_review',bridge_obs
    assert bridge_obs['risk_status']=='no_detected_integrity_risk','shading candidate is not a topology failure'
    bridge_points[6].setPosition((3,.01,3))
    assert o.polygon_observation(bridge_geo,integrity_only=True)['planar_repeated_point_ngons']==0
    shading=root.createNode('normal','reversed_shading_normals')
    shading.setInput(0,root.node('source'))
    shading.parm('type').set('typeprim')
    shading.parm('reverse').set(1)
    quick_shading=o.polygon_observation(shading.geometry(),integrity_only=True)
    assert quick_shading['shell_orientation']['positive_count']==1 and quick_shading['shading_normals']['opposed_count']>0,quick_shading
    assert 'N_attribute_opposes_polygon_winding' in quick_shading['risk_reasons'],quick_shading
    bridge_check=b.run_code(f'__result__=geo_piece_stats({shading.path()!r},inspect=True,integrity_only=True)')
    summary=next(item for item in bridge_check['evidence'] if item.get('verb')=='geo_piece_stats')
    assert summary['shading_normals']['opposed_count']>0 and summary['shell_orientation']['positive_count']==1,summary
    def reversed_faces(source, selected):
        target=hou.Geometry();points={p.number():target.createPoint() for p in source.points()}
        for p in source.points():points[p.number()].setPosition(p.position())
        for face in source.prims():
            poly=target.createPolygon();ids=[v.point().number() for v in face.vertices()]
            for i in (list(reversed(ids)) if face.number() in selected else ids):poly.addVertex(points[i])
        return target
    g=reversed_faces(g,{p.number() for p in g.prims()})
    negative=o.polygon_observation(g)['shell_orientation'];assert negative['negative_count']==1,negative
    quick_negative=o.polygon_observation(g,integrity_only=True)
    assert quick_negative['orientation_conflicts']==0 and quick_negative['risk_status']=='needs_review',quick_negative
    assert quick_negative['shell_orientation']['negative_count']==1 and quick_negative['orientation_review_status']=='negative_closed_shells_present',quick_negative
    assert 'negative_closed_shell_winding_requires_review' in quick_negative['risk_reasons'],quick_negative
    reverse_node=root.createNode('reverse','whole_shell_inverse')
    reverse_node.setInput(0,root.node('source'))
    reverse_node.parm('vtxsort').set('reverse')
    inverted_packet=b.run_code(f'__result__=geo_piece_stats({reverse_node.path()!r},inspect=True,integrity_only=True)')
    inverted_summary=next(item for item in inverted_packet['evidence'] if item.get('verb')=='geo_piece_stats')
    assert inverted_summary['shell_orientation']['negative_count']==1 and inverted_summary['risk_status']=='needs_review',inverted_summary
    g=reversed_faces(g,{0})
    mixed=o.polygon_observation(g);assert mixed['orientation_conflicts']>0 and mixed['shell_orientation']['unverified_count']==1
    g.deletePrims([g.prims()[0]],False)
    assert o.polygon_observation(g)['shell_orientation']['unverified_count']==1
    # Independent actual polygon components. Planes move through sparse long faces.
    h.create_spare_parms(ctrl,spec=[{'name':'height','type':'float','default':.25},
                                  {'name':'ceiling','type':'float','default':1.0},
                                  {'name':'thickness','type':'float','default':.1}])
    h.build_module(root,[
      {'name':'beam_a','type':'box','parms':{'sizex':.1,'sizey':1.,'sizez':.1,'tx':-.2,'ty':.5}},
      {'name':'beam_b','type':'box','parms':{'sizex':.1,'sizey':1.,'sizez':.1,'tx':.2,'ty':.5}},
      {'name':'beams','type':'merge','inputs':['beam_a','beam_b']},
      {'name':'beam_tag','type':'attribwrangle','inputs':['beams'],'parms':{'class':'primitive','snippet':'i@group_beams=1;'}},
      {'name':'slab','type':'box','parms':{'sizex':1.,'sizey':.01,'sizez':1.,'ty':'ch("../CTRL/height")'}},
      {'name':'slab_tag','type':'attribwrangle','inputs':['slab'],'parms':{'class':'primitive','snippet':'i@group_slab=1;'}},
      {'name':'OUT','type':'merge','inputs':['beam_tag','slab_tag']}],output='OUT')
    out=root.node('OUT');base=q._data_signature(out.geometry());children=set(root.children())
    interfaces=[{'id':'section','method':'section_proximity','source_group':'beams','target_group':'slab','axis':1,'plane_at':'target_center','expected_components':2,'max_distance':.006}]
    for height in [.22,.25,.27,.34,.46]:
        h.set_parm(ctrl,'height',height)
        result=h.geo_check_interfaces(out,interfaces)
        assert result['ok'],result
        assert len(result['results'][0]['component_coverage'])==2
        assert len(out.geometry().prims())==18,'observation must not densify geometry'
    h.set_parm(ctrl,'height',.25)
    assert q._data_signature(out.geometry())==base and set(root.children())==children
    assert not h.geo_check_interfaces(out,[{**interfaces[0],'expected_components':3}])['ok']
    assert h.geo_check_interfaces(out,[{**interfaces[0],'source_group':'missing'}])['status']=='fail'
    assert h.geo_check_interfaces(out,[{**interfaces[0],'target_group':'beams'}])['status']=='fail'
    assert h.geo_check_interfaces(out,[{**interfaces[0],'plane_at':0.}])['status']=='unverified','coplanar cap must not become a confident section'
    try:h.geo_check_interfaces(out,interfaces,max_pairs=1)
    except ValueError:pass
    else:raise AssertionError('section pair budget was bypassed')
    try:q.validate_domain([{'id':'bad','left':'height','op':'lt','right':{'terms':{'ceiling':float('inf')}}}])
    except ValueError:pass
    else:raise AssertionError('nonfinite domain coefficient accepted')
    h.set_parm(root.node('slab'),'tx',3.)
    assert h.geo_check_interfaces(out,interfaces)['status']=='fail'
    h.set_parm(root.node('slab'),'tx',0.)
    h.set_parm(ctrl,'height',1.5)
    assert h.geo_check_interfaces(out,interfaces)['status']=='fail'
    h.set_parm(ctrl,'height',.25)
    domain=[{'id':'clearance','left':'height','op':'lt','right':{'terms':{'ceiling':1,'thickness':-1},'constant':-.05}}]
    tests=[{'id':'ordinary','values':{'height':.27},'expectations':[{'metric':'bounds_center','axis':1,'group':'slab','delta':[.019,.021]}]},
           {'id':'invalid_coupled','values':{'height':.9},'expectations':[{'metric':'bounds_center','axis':1,'group':'slab','delta':[.64,.66]}]}]
    result=h.test_controls(ctrl,out,tests,interfaces=interfaces,domain=domain)
    assert result['results'][0]['status']=='pass',result
    assert result['results'][1]['parameter_writes']==0 and result['results'][1]['status']=='fail'
    assert result['restored'] and q._data_signature(out.geometry())==base
    print('PASS v13 setting, wiring, orientation, section and domain contracts',hou.applicationVersionString())
finally:root.destroy()
