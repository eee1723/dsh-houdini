"""Deliberate structural faults must fail actual final-geometry checks.

These generic fixtures are production mechanism regressions, not product task
answers or a visual benchmark. Healthy cook is deliberately insufficient.
"""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h

with h._execution_owner('fault-injection','fixture'):
    root=h.tab_create('/obj','geo','fault_fixture')
    a=h.tab_create(root,'box','a')
    a_tag=h.tab_create(root,'attribwrangle','a_tag');h.connect(a,a_tag,0)
    h.set_parms(a_tag,{'class':'point','snippet':'if(@P.x>0) i@group_contact=1;'})
    b=h.tab_create(root,'box','b');h.set_parms(b,{'tx':1})
    b_tag=h.tab_create(root,'attribwrangle','b_tag');h.connect(b,b_tag,0)
    h.set_parms(b_tag,{'class':'primitive','snippet':'i@group_receiver=1;'})
    a_prim=h.tab_create(root,'attribwrangle','a_prim');h.connect(a_tag,a_prim,0)
    h.set_parms(a_prim,{'class':'primitive','snippet':'i@group_sender=1;'})
    merge=h.tab_create(root,'merge','assembly');h.connect(a_prim,merge,0);h.connect(b_tag,merge,1)
    all_tag=h.tab_create(root,'attribwrangle','all');h.connect(merge,all_tag,0)
    h.set_parms(all_tag,{'class':'primitive','snippet':'i@group_complete=1;'})
    out=h.tab_create(root,'null','OUT_ASSET');h.connect(all_tag,out,0)
    checks=[{'id':'members','method':'component_count','target_group':'complete','expected_components':2},
        {'id':'attachment','source_group':'contact','target_group':'receiver','expected_points':4,'max_distance':1e-5},
        {'id':'collision','method':'solid_overlap','source_group':'sender','target_group':'receiver','max_overlap_volume':0}]
    assert h.geo_check_interfaces(out,checks)['status']=='pass'
    results=[]
    for name,setup,restore,expected in [
        ('floating',lambda:h.set_parms(b,{'tx':1.2}),lambda:h.set_parms(b,{'tx':1}),'attachment'),
        ('penetration',lambda:h.set_parms(b,{'tx':.8}),lambda:h.set_parms(b,{'tx':1}),'collision'),
        ('missing_branch',lambda:h.disconnect_input(merge,1),lambda:h.connect(b_tag,merge,1),'members'),
        ('duplicate_instance',lambda:h.connect(b_tag,merge,2),lambda:h.disconnect_input(merge,2),'members'),
    ]:
        try:
            setup()
            # The very condition which previously tempted premature completion.
            assert h.verify_network(root,output=out)['ok']
            actual=h.geo_check_interfaces(out,checks)
            row=next(r for r in actual['results'] if r['id']==expected)
            assert row['status']=='fail',(name,actual)
            results.append({'fault':name,'detected_by':expected,'status':row['status']})
        finally:restore()
        assert h.geo_check_interfaces(out,checks)['status']=='pass'
    # A small but real gap can pass a relaxed tolerance; that does not satisfy
    # the original design requirement (Host binding has a paired regression).
    h.set_parms(b,{'tx':1.000181})
    strict={**checks[1],'max_distance':.00005}
    loose={**strict,'max_distance':.0002}
    actual=h.geo_check_interfaces(out,[strict])
    assert actual['status']=='fail' and .00017<actual['results'][0]['max_distance']<.00019
    assert h.geo_check_interfaces(out,[loose])['status']=='pass'
    h.set_parms(b,{'tx':1})
    # A zero-size Box is eight coincident points, not a single template point.
    # Eight such placements copy 64 solids even though only eight are visible.
    member=h.tab_create(root,'box','repeat_source');h.set_parms(member,{'size':(.01,.01,.01)})
    tag=h.tab_create(root,'attribwrangle','repeat_tag');h.connect(member,tag,0)
    h.set_parms(tag,{'class':'primitive','snippet':'i@group_repeated=1;'})
    target=h.tab_create(root,'box','bad_point');h.set_parms(target,{'size':(0,0,0)})
    points=h.tab_create(root,'copyxform','eight_positions');h.connect(target,points,0)
    h.set_parms(points,{'ncy':8,'tx':.02})
    copies=h.tab_create(root,'copytopoints::2.0','repeated');h.connect(tag,copies,0);h.connect(points,copies,1)
    assert len(points.geometry().points())==64
    count=h.geo_check_interfaces(copies,[{'id':'copies','method':'component_count','target_group':'repeated','expected_components':8}])
    assert count['status']=='fail' and count['results'][0]['observed_components']==64,count
    results.extend([{'fault':'relaxed_contact_limit','detected_by':'original tolerance','status':'fail'},
                    {'fault':'coincident_template_points','detected_by':'component_count','observed':64,'expected':8}])
    print(json.dumps({'version':hou.applicationVersionString(),'faults':results}))
