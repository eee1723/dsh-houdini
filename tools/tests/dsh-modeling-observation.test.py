"""Real HOM counterexamples for node knowledge, topology and control measurements."""
import sys, pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_quality_contracts as q
import dsh_geometry_observation as o
import dsh_bridge as b

root=hou.node('/obj').createNode('geo','modeling_observation_test')
def rejects(fn, text):
    try:fn()
    except (ValueError, q.UnsupportedEvidence) as e:assert text in str(e),(text,str(e))
    else:raise AssertionError('expected rejection: '+text)
try:
    card=h.node_info(root,'grid',parm_filter='size|row|col')
    assert card['parameter_count']==0 and card['total_parameter_count']>0 and card['filter_mode']=='literal_substring'
    assert h.node_info(root,'grid',parm_filter='size')['parameter_count']>0
    for name in ('sweep','polyextrude','revolve','blast','copytopoints','attribwrangle'):
        assert h.node_info(root,name)['operation_card']['id']
    circle=root.createNode('circle');circle.parm('type').set('poly')
    rejects(lambda:h.set_parm(circle,'rad',['ch("x")',1]),'numeric tuple')
    before=set(root.children())
    rejects(lambda:h.build_module(root,[{'name':'bad','type':'circle','parms':{'rad':['ch("x")',1]}}],output='bad'),'numeric tuple')
    assert set(root.children())==before
    grid=root.createNode('grid');grid.parm('rows').set(4);grid.parm('cols').set(4)
    grid.parmTuple('size').set((1,1))
    ext=root.createNode('polyextrude::2.0');ext.setInput(0,grid);ext.parm('dist').set(.1)
    ext.parm('outputback').set(0)
    open_report=h.geo_piece_stats(ext,inspect=True)
    assert open_report['boundary_edges']>0
    ext.parm('outputback').set(1)
    closed=h.geo_piece_stats(ext,inspect=True)
    assert closed['boundary_edges']==0 and closed['edge_connected_components']==1,closed
    tube=root.createNode('tube');tube.parm('type').set('poly');tube.parm('cap').set(1)
    tube.parm('orient').set('z');tube.parmTuple('rad').set((.15,.11));tube.parm('height').set(.04)
    tube_axes=h.geo_piece_stats(tube,inspect=True)['center_axis_surface_hits']['axes']
    assert [row['surface_hits'] for row in tube_axes]==[2,2,2],tube_axes
    torus=root.createNode('torus');torus.parm('type').set('poly');torus.parm('orient').set('y')
    torus_report=h.geo_piece_stats(torus,inspect=True)
    assert torus_report['boundary_edges']==0 and torus_report['nonmanifold_edges']==0,torus_report
    torus_integrity=h.geo_piece_stats(torus,inspect=True,integrity_only=True)
    assert torus_integrity['risk_status']=='no_detected_integrity_risk' and torus_integrity['boundary_edges']==0,torus_integrity
    assert torus_integrity['boundary_review_status']=='none',torus_integrity
    open_integrity=h.geo_piece_stats(grid,inspect=True,integrity_only=True)
    assert open_integrity['boundary_edges']>0 and open_integrity['risk_status']=='no_detected_integrity_risk',open_integrity
    assert open_integrity['boundary_review_status']=='open_boundary_unreviewed',open_integrity
    rejects(lambda:h.geo_piece_stats(grid,integrity_only=True),'requires inspect=True')
    rejects(lambda:h.geo_piece_stats(grid,inspect=True,integrity_only=1),'must be boolean')
    bridge_integrity=b.run_code(f"__result__=geo_piece_stats('{grid.path()}',inspect=True,integrity_only=True)",
                                owner_session='fixture',owner_call='integrity')
    assert bridge_integrity['ok'] and bridge_integrity['verbs'][0]['check_status']=='warning',bridge_integrity
    assert bridge_integrity['evidence'][0]['boundary_review_status']=='open_boundary_unreviewed',bridge_integrity
    assert bridge_integrity['evidence'][0]['risk_reasons']==[],bridge_integrity
    bridge_clean=b.run_code(f"__result__=geo_piece_stats('{torus.path()}',inspect=True,integrity_only=True)",
                            owner_session='fixture',owner_call='integrity-clean')
    assert bridge_clean['ok'] and bridge_clean['verbs'][0]['check_status']=='passed',bridge_clean
    broken=root.createNode('attribwrangle');broken.parm('class').set('detail')
    broken.parm('snippet').set('int a=addpoint(0,set(0,0,0));int b=addpoint(0,set(1,0,0));'
                               'int c=addpoint(0,set(0,1,0));int d=addpoint(0,set(0,-1,0));'
                               'int e=addpoint(0,set(0,0,1));'
                               'addprim(0,"poly",a,b,c);addprim(0,"poly",b,a,d);addprim(0,"poly",a,b,e);')
    bridge_bad=b.run_code(f"__result__=geo_piece_stats('{broken.path()}',inspect=True,integrity_only=True)",
                          owner_session='fixture',owner_call='integrity-bad')
    assert bridge_bad['ok'] and bridge_bad['verbs'][0]['check_status']=='warning',bridge_bad
    assert 'nonmanifold_edges' in bridge_bad['evidence'][0]['risk_reasons'],bridge_bad
    torus_axes=torus_report['center_axis_surface_hits']['axes']
    assert torus_axes[1]['status']=='observed' and torus_axes[1]['surface_hits']==0,torus_axes
    group=ext.geometry().freeze();pg=group.createPrimGroup('one_face');pg.add(group.prim(0))
    assert o.polygon_observation(group,'one_face')['boundary_edges']>0,'group cuts are intentional boundaries'
    rejects(lambda:o.polygon_observation(group,'missing'),'missing')
    rejects(lambda:o.polygon_observation(group,basis=[[1,0,0]]*3),'orthonormal')
    line=root.createNode('line');line.parmTuple('dir').set((0,0,1))
    assert h.geo_piece_stats(line,inspect=True)['status']=='unverified','curves are not closed surfaces'
    assert h.geo_piece_stats(line,inspect=True,integrity_only=True)['status']=='unverified'
    synthetic=hou.Geometry()
    def point(pos):
        p=synthetic.createPoint();p.setPosition(pos);return p
    a,bp=point((0,0,0)),point((1,0,0))
    for tip in (point((0,1,0)),point((0,-1,0)),point((0,0,1))):
        face=synthetic.createPolygon()
        for p in (a,bp,tip):face.addVertex(p)
    nonmanifold=o.polygon_observation(synthetic,integrity_only=True)
    assert nonmanifold['nonmanifold_edges']>0 and 'nonmanifold_edges' in nonmanifold['risk_reasons'],nonmanifold
    repeated=hou.Geometry()
    for _ in range(2):
        face=repeated.createPolygon()
        for pos in ((0,0,0),(1,0,0),(0,1,0)):
            p=repeated.createPoint();p.setPosition(pos);face.addVertex(p)
    repeated_report=o.polygon_observation(repeated,integrity_only=True)
    assert repeated_report['duplicate_boundary_faces']>0 and repeated_report['risk_status']=='needs_review',repeated_report
    collapsed=hou.Geometry();face=collapsed.createPolygon()
    for pos in ((0,0,0),(1,0,0),(2,0,0)):
        p=collapsed.createPoint();p.setPosition(pos);face.addVertex(p)
    assert o.polygon_observation(collapsed,integrity_only=True)['zero_area_faces']>0
    sweep=root.createNode('sweep::2.0');sweep.setInput(0,line);sweep.setInput(1,circle)
    circle.parm('orient').set('xy')
    good=sweep.geometry().boundingBox().sizevec()
    circle.parm('orient').set('yz')
    bad=sweep.geometry().boundingBox().sizevec()
    assert good[0]>.1 and good[1]>.1 and bad[0]<1e-5,(good,bad)
    rev=root.createNode('revolve::2.0');profile=root.createNode('line')
    profile.parmTuple('origin').set((1,0,0));profile.parmTuple('dir').set((0,1,0))
    rev.setInput(0,profile);rev.parm('type').set('closed');rev.parm('primtype').set('poly')
    assert h.geo_piece_stats(rev,inspect=True)['boundary_edges']>0,'closed revolution is not end-capped'
    blast=root.createNode('blast');blast.setInput(0,profile)
    blast.parm('grouptype').set('points');blast.parm('group').set('0')
    assert len(blast.geometry().points())==1
    blast.parm('grouptype').set('prims')
    assert len(blast.geometry().points())==0
    # Same bbox, real interior deformation, stable IDs and exact restoration.
    h.create_spare_parms(root,spec=[{'name':'dip','type':'float','default':0.0}])
    wr=root.createNode('attribwrangle');wr.setInput(0,grid)
    wr.parm('snippet').set('i@id=@ptnum; @P.y-=chf("../dip")*(1-pow(@P.x*2,2))*(1-pow(@P.z*2,2));')
    frozen=wr.geometry().freeze()
    tests=[{'id':'dish','values':{'dip':.2},'expectations':[
        {'metric':'max_point_displacement','id_attrib':'id','delta':[.1,.21]},
        {'metric':'boundary_edges','delta':[0,0],'range':[12,12]}]}]
    r=h.test_controls(root,wr,tests)
    assert r['ok'] and r['restored'],r
    assert root.evalParm('dip')==0
    assert q._data_signature(frozen)==q._data_signature(wr.geometry())
    altered=frozen.freeze();attr=altered.findPointAttrib('id')
    altered.point(0).setAttribValue(attr,altered.point(1).attribValue(attr))
    rejects(lambda:o.point_displacement(altered,frozen,tests[0]['expectations'][0]),'duplicate')
    # A permanently open surface cannot pass closure via unchanged boundary count.
    reject=h.test_controls(root,wr,[{'id':'bad_baseline','values':{'dip':.2},'expectations':[
        {'metric':'max_point_displacement','id_attrib':'id','delta':[.1,.21]},
        {'metric':'boundary_edges','delta':[0,0],'range':[0,0]}]}])
    assert reject['parameter_writes']==0 and not reject['ok']
    large=root.createNode('grid');large.parm('rows').set(152);large.parm('cols').set(152)
    assert h.geo_piece_stats(large,inspect=True)['status']=='unverified','full inspect retains its 20000-prim budget'
    large_integrity=h.geo_piece_stats(large,inspect=True,integrity_only=True)
    assert large_integrity['status']=='observed' and large_integrity['selected_primitives']>20000,large_integrity
    assert large_integrity['boundary_review_status']=='open_boundary_unreviewed' and not large_integrity['risk_reasons'],large_integrity
    result=b.run_code("n=tab_create('/obj','geo',name='transaction_fixture')\nraise ValueError('expected')",owner_session='fixture',owner_call='tx')
    assert result['transaction']['status'] in ('rolled_back','recovery_unverified'),result
    assert result['transaction']['nodes']
finally:
    root.destroy()
    node=hou.node('/obj/transaction_fixture')
    if node:node.destroy()
print('modeling observations passed: '+hou.applicationVersionString())
