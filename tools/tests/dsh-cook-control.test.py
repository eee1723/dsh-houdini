"""Bounded risk rejection and Manual metadata behavior, no unsafe loops executed."""
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h
from dsh_cook_control import validate_vex

for code in ['while(npoints(0)>0) removepoint(0,npoints(0)-1);',
             'while (nprimitives(0) > 0) { removeprim(0,0,1); }']:
    try:validate_vex(code)
    except (ValueError, RuntimeError) as error:
        assert 'unsafe VEX deletion loop' in str(error)
    else:raise AssertionError('unsafe deletion loop accepted')
validate_vex('for(int i=npoints(0)-1;i>=0;i--) removepoint(0,i);')
validate_vex('// while(npoints(0)>0) removepoint(0,0);\nfloat x=1;')
with h._execution_owner('cook-test','setup'):
    g=h.tab_create('/obj','geo',name='cook_test')
    n=h.tab_create(g,'box')
    w=h.tab_create(g,'attribwrangle')
    h.set_update_mode('manual','auto')
    assert h.scene_info()['update_mode']=='manual'
    assert h.describe(n)['geometry_status']=='not_evaluated_manual'
    assert h.cook_node(n)['status']=='not_cooked_manual'
    # Geometry consumers must not cook implicitly or label unknown as empty.
    count=n.cookCount()
    report=h.verify_network(g,output=n,require_valid=False)
    assert report['status']=='not_evaluated_manual' and report['nonempty'] is None,report
    assert report['geometry'] is None and report['output_fingerprint'] is None,report
    assert report['failure_reasons']==['not_evaluated_manual'],report
    assert n.cookCount()==count and hou.updateModeSetting()==hou.updateMode.Manual
    try:h.verify_network(g,output=n)
    except h.CheckpointError as error:assert error.evidence['status']=='not_evaluated_manual'
    else:raise AssertionError('Manual verification was certified')
    for operation in (lambda:h.geo_attrib_stats(n,'P'), lambda:h.geo_piece_stats(n),
                      lambda:h.geo_frame_diff(n,1,2), lambda:h.geo_point_spacing(n,1,.1)):
        try:operation()
        except ValueError as error:assert 'Manual' in str(error),error
        else:raise AssertionError('Manual geometry was evaluated')
    children=tuple(g.children())
    spec=[{'name':'manual_module','type':'box'}]
    assert h.build_module(g,spec,output='manual_module',dry_run=True)['dry_run']
    try:h.build_module(g,spec,output='manual_module')
    except ValueError as error:assert 'Manual' in str(error),error
    else:raise AssertionError('Manual build started modifying the scene')
    assert tuple(g.children())==children and n.cookCount()==count
    interface={'id':'manual','source_group':'port','target_group':'surface',
               'max_distance':.01,'expected_points':1}
    controls=[{'id':'size','values':{'sizex':2},
               'expectations':[{'metric':'bounds_size','axis':0,'delta':[.9,1.1]}]}]
    value=n.evalParm('sizex');frame=hou.frame()
    for operation in (lambda:h.geo_check_interfaces(n,[interface]),
                      lambda:h.test_controls(n,n,controls),
                      lambda:h.camera_fit('/obj/not_created_camera',n),
                      lambda:h.render_frame('/out/not_created_rop'),
                      lambda:h.render_view(n)):
        with patch.object(hou,'isUIAvailable',return_value=True):
            try:operation()
            except ValueError as error:assert 'Manual' in str(error),error
            else:raise AssertionError('Manual operation was evaluated')
    assert n.evalParm('sizex')==value and hou.frame()==frame and n.cookCount()==count
    for code in (f'__result__=verify_network({g.path()!r},output={n.path()!r},require_valid=False)',
                 f'__result__=cook_node({n.path()!r})'):
        result=b.run_code(code,owner_session='cook-test')
        assert result['ok'] and result['result']['ok'] is False,result
        assert result['verbs'][-1]['check_status']=='unverified',result
    before=w.parm('snippet').unexpandedString()
    try:h.set_parms(w,{'snippet':'while(npoints(0)>0) removepoint(0,0);'})
    except (ValueError, RuntimeError) as error:
        assert 'unsafe VEX deletion loop' in str(error)
    else:raise AssertionError('unsafe source written')
    assert w.parm('snippet').unexpandedString()==before
    r=b.run_code("set_update_mode('auto','manual')",owner_session='cook-test',read_only=True)
    assert not r['ok'] and hou.updateModeSetting()==hou.updateMode.Manual
    h.set_update_mode('auto','manual')
    assert h.cook_node(n,timeout_ms=1000)['ok']
    assert h.verify_network(g,output=n,nodes=[n])['nonempty'] is True
    assert h.geo_attrib_stats(n,'P')['count']==8
    assert h.geo_piece_stats(n)['piece_count']==1
    assert h.geo_frame_diff(n,1,2)['max_delta']==0
    failure={'path':n.path(),'ok':False,'healthy':False,'warning_free':True,
             'errors':['injected interrupted cook'],'warnings':[]}
    with patch.object(h,'cook_node',return_value=failure), \
         patch.object(hou.SopNode,'geometry',side_effect=AssertionError('implicit retry after failed cook')):
        failed=h.verify_network(g,output=n,nodes=[n],require_valid=False)
    assert failed['failure_reasons']==['cook_error'] and failed['nonempty'] is None,failed
    assert failed['output_fingerprint'] is None and failed['geometry_status']=='not_evaluated_cook_failed',failed
    with patch.object(hou.SopNode,'cook',side_effect=RuntimeError()):
        failed=h.cook_node(n)
    assert failed['ok'] is False and 'RuntimeError' in failed['errors'],failed
    g.destroy()
print('cook risk/Manual metadata/mode guard passed '+hou.applicationVersionString())
