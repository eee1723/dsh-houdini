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
    group=ext.geometry().freeze();pg=group.createPrimGroup('one_face');pg.add(group.prim(0))
    assert o.polygon_observation(group,'one_face')['boundary_edges']>0,'group cuts are intentional boundaries'
    rejects(lambda:o.polygon_observation(group,'missing'),'missing')
    rejects(lambda:o.polygon_observation(group,basis=[[1,0,0]]*3),'orthonormal')
    line=root.createNode('line');line.parmTuple('dir').set((0,0,1))
    assert h.geo_piece_stats(line,inspect=True)['status']=='unverified','curves are not closed surfaces'
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
    result=b.run_code("n=tab_create('/obj','geo',name='transaction_fixture')\nraise ValueError('expected')",owner_session='fixture',owner_call='tx')
    assert result['transaction']['status'] in ('rolled_back','recovery_unverified'),result
    assert result['transaction']['nodes']
finally:
    root.destroy()
    node=hou.node('/obj/transaction_fixture')
    if node:node.destroy()
print('modeling observations passed: '+hou.applicationVersionString())
