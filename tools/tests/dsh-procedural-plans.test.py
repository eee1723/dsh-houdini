"""Actual editable recipes, arbitrary shared pivots and pairwise test planning."""
import sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as bridge
import dsh_quality_contracts as q

with h._execution_owner('recipe-author','fixture'):
    # Every catalog entry supports the same discovery call; it must not require
    # guessing a partially populated spec or execute scene changes.
    before_objects=tuple(hou.node('/obj').children())
    catalog=h.sop_recipe('catalog')
    assert set(catalog['examples'])==set(catalog['recipes'])
    for kind in catalog['recipes']:
        example=h.sop_recipe(kind)
        assert example['example']==catalog['examples'][kind]
        proposal=h.sop_recipe(kind,example['example'])
        assert proposal['nodes'] and proposal['output']
    assert tuple(hou.node('/obj').children())==before_objects
    root=h.tab_create('/obj','geo','recipe_fixture')
    ctrl=h.tab_create(root,'null','CTRL')
    h.create_spare_parms(ctrl,spec=[{'type':'float','name':'angle','default':0},
        {'type':'float','name':'offset','default':0},{'type':'int','name':'count','default':3},
        {'type':'float','name':'origin_x','default':2},{'type':'float','name':'thickness','default':.2}])
    source=h.tab_create(root,'box','body');h.set_parms(source,{'tx':1})
    attachment=h.tab_create(root,'box','attachment');h.set_parms(attachment,{'tx':1,'ty':1})
    body_tag=h.tab_create(root,'attribwrangle','body_tag');h.connect(source,body_tag,0)
    h.set_parms(body_tag,{'class':'primitive','snippet':'i@group_body=1;'})
    attachment_tag=h.tab_create(root,'attribwrangle','attachment_tag');h.connect(attachment,attachment_tag,0)
    h.set_parms(attachment_tag,{'class':'point','snippet':'if(@P.y<1) i@group_attachment_port=1;'})
    relation=[{'id':'attached','source_group':'attachment_port','target_group':'body','expected_points':4,'max_distance':.00001}]
    for kind,parameter in [('hinge','angle'),('slider','offset'),('repeat','count')]:
        before=len(root.children())
        recipe=h.sop_recipe(kind,{'name':kind,'inputs':['body_tag','attachment_tag'],'controller':'CTRL',
            'parameter':parameter,'origin':[{'parm':'origin_x'},0,0],'axis':[0,0,1],**({'spacing':2} if kind=='repeat' else {})})
        assert len(root.children())==before
        h.build_module(root,recipe['nodes'],recipe['output'],required_outputs=recipe['required_outputs'])
        out=root.node(recipe['output']);g=out.geometry()
        assert len(g.prims())==(36 if kind=='repeat' else 12)
        if kind=='hinge':
            rest=[p.position()-hou.Vector3(2,0,0) for p in g.points()]
            h.set_parms(ctrl,{'angle':90})
            center=out.geometry().boundingBox().center()
            assert (center-hou.Vector3(1.5,1,0)).length()<1e-5,center
            frame=root.node(recipe['frame_output']).geometry().points()[0]
            assert (frame.position()-hou.Vector3(2,0,0)).length()<1e-6
            actual=out.geometry().points()
            for pos,point in zip(rest,actual):
                expected=hou.Vector3(-pos[1]+2,pos[0],pos[2])
                assert (point.position()-expected).length()<1e-5
            assert h.geo_check_interfaces(out,relation)['status']=='pass'
            # Freeze/misplace an attachment while both branches still cook.
            h.set_parms(attachment,{'ty':1.4})
            assert h.geo_check_interfaces(out,relation)['status']=='fail'
            h.set_parms(attachment,{'ty':1})
            h.set_parms(ctrl,{'origin_x':4})
            assert abs(out.geometry().boundingBox().center()[0]-3.5)<1e-6
            h.set_parms(ctrl,{'origin_x':2,'angle':0})
        if kind=='slider':
            h.set_parms(ctrl,{'offset':3})
            assert abs(out.geometry().boundingBox().center()[2]-3)<1e-6
            h.set_parms(ctrl,{'offset':0})
        if kind=='repeat':
            h.set_parms(ctrl,{'count':5});assert len(out.geometry().prims())==60
            h.set_parms(ctrl,{'count':3})
    grid=h.tab_create(root,'grid','profile');h.set_parms(grid,{'rows':2,'cols':2})
    oblique=h.sop_recipe('hinge',{'name':'oblique','inputs':['body_tag','attachment_tag'],
        'parameter':'angle','origin':[-1,2,3],'axis':[1,1,1]})
    h.build_module(root,oblique['nodes'],oblique['output'])
    local=[p.position() for n in (body_tag,attachment_tag) for p in n.geometry().points()]
    h.set_parms(ctrl,{'angle':120})
    for pos,point in zip(local,root.node(oblique['output']).geometry().points()):
        assert (point.position()-hou.Vector3(pos[2]-1,pos[0]+2,pos[1]+3)).length()<1e-5
    assert h.geo_check_interfaces(root.node(oblique['output']),relation)['status']=='pass'
    h.set_parms(ctrl,{'angle':0})
    shell=h.sop_recipe('profile_shell',{'name':'shell','inputs':['profile'],'thickness':{'parm':'thickness'}})
    h.build_module(root,shell['nodes'],shell['output'])
    assert q._check_topology(root.node(shell['output']).geometry(),[{'id':'closed','groups':['missing'],'require_closed':True}])['status']=='fail'
    line=h.tab_create(root,'line','path')
    tube=h.sop_recipe('sweep_tube',{'name':'tube','inputs':['path'],'radius':.1})
    h.build_module(root,tube['nodes'],tube['output'])
    assert root.node(tube['output']).geometry().intrinsicValue('primitivecount')>0
    before=q._data_signature(root.node('OUT_HINGE').geometry())
    levels={'angle':[0,45,90],'offset':[0,1,2],'count':[1,3,5]}
    plan=h.control_test_plan(ctrl,levels)
    assert plan['coverage']['status']=='complete_pairwise',plan
    assert len(plan['tests'])<=16 and all(not t['expectations'] for t in plan['tests'])
    assert q._data_signature(root.node('OUT_HINGE').geometry())==before
    partial=h.control_test_plan(ctrl,levels,max_cases=1)
    assert partial['coverage']['missing_count']>0 and partial['coverage']['status']=='partial_pairwise'
    plan=h.control_test_plan(ctrl,{'angle':[0,45,90]},domain=[{'id':'limit','left':'angle','op':'le','right':45}])
    assert plan['excluded_count']==1
    before_nodes=len(root.children())
    for kind,spec in [('hinge',{'name':'bad','inputs':['body'],'parameter':'angle','axis':[0,0,0]}),
                      ('hinge',{'name':'bad','inputs':['body'],'parameter':'angle','spacing':9}),
                      ('profile_shell',{'name':'bad','inputs':['body'],'thickness':-1})]:
        try:h.sop_recipe(kind,spec)
        except ValueError:pass
        else:raise AssertionError('invalid recipe accepted')
    assert len(root.children())==before_nodes
    try:h.test_controls(ctrl,root.node('OUT_HINGE'),plan['tests'])
    except ValueError as error:assert 'expectations' in str(error)
    else:raise AssertionError('empty generated expectations must not execute')
    read=bridge.run_code('__result__=sop_recipe("catalog")',read_only=True,owner_session='recipe-author')
    assert read['ok'] and 'hinge' in read['result']['recipes'],read
print('editable SOP recipes and pairwise plans passed',hou.applicationVersionString())
