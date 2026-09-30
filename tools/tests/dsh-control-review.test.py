"""Isolated H21/H22: early-failure identities and fixed control capture contract.

Render calls are instrumented; this proves scheduling/arguments/restoration,
not GPU output or semantic image interpretation.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as b

with h._execution_owner('control-review','fixture'):
    root=h.tab_create('/obj','geo','__control_review')
    ctrl=h.tab_create(root,'null','CTRL')
    h.create_spare_parms(ctrl,spec=[{'type':'float','name':'width','default':1.0}])
    box=h.tab_create(root,'box','body')
    h.set_parms(box,{'sizex':"ch('../CTRL/width')"})
    out=h.tab_create(root,'null','OUT_ASSET');h.connect(box,out,0)
    tests=[{'id':'width','values':{'width':2.0},'expectations':[
        {'metric':'bounds_size','axis':0,'range':[.5,3.0],'delta':[.999,1.001]}]}]
    code=f'__result__=test_controls({ctrl.path()!r},{out.path()!r},{tests!r})'
    h.set_parms(ctrl,{'width':.25})
    failed=b.run_code(code,owner_session='control-review')
    h.set_parms(ctrl,{'width':1.0})
    passed=b.run_code(code,owner_session='control-review')
    fail=next(e for e in failed['evidence'] if e['verb']=='test_controls')
    good=next(e for e in passed['evidence'] if e['verb']=='test_controls')
    assert fail['status']=='fail' and good['status']=='pass',(fail,good)
    assert fail['contract_sha256']==good['contract_sha256'] and len(good['contract_sha256'])==64
    assert fail['control_summary']['contract_sha256']==good['contract_sha256']
    # Every early zero-write outcome keeps the same declaration identity.
    domain=[{'id':'valid','left':'width','op':'ge','right':.5}]
    h.set_parms(ctrl,{'width':.25})
    early=h.test_controls(ctrl,out,tests,domain=domain)
    h.set_parms(ctrl,{'width':1.0})
    assert early['contract_sha256']==h.test_controls(ctrl,out,tests,domain=domain)['contract_sha256']
    assert early['parameter_writes']==0
    other=h.tab_create(root,'null','OTHER_CTRL')
    h.create_spare_parms(other,spec=[{'type':'float','name':'width','default':1.0}])
    other_result=h.test_controls(other,out,tests)
    assert other_result['contract_sha256']!=good['contract_sha256'],'different controller identities must not clear each other'
    original_render=h.render_view;original_ui=hou.isUIAvailable;original_restore=h._restore_parameters
    calls=[];bounds=[[-3,-3,-3],[3,3,3]]
    try:
        hou.isUIAvailable=lambda:True
        def render(node,**kwargs):
            calls.append((ctrl.evalParm('width'),dict(kwargs)))
            box=kwargs.get('framing_bounds',bounds)
            return {'ok':True,'stale':False,'picture':'fixture.png','user_state_restored':True,
                    'output':'fixture.png','artifact':{'capture_id':'fixture'},
                    'semantic_status':'unverified','framing':{'bounds':box,'depth_bounds':box}}
        h.render_view=render
        result=h.test_controls(ctrl,out,tests,views=['front','side'],view_bounds=bounds)
        assert result['status']=='pass' and result['restored'],result
        assert result['capture_status']=='observed' and len(result['baseline_captures'])==2,result
        assert result['baseline_captures'][0]['output']=='fixture.png' and result['baseline_captures'][0]['artifact']['capture_id']=='fixture'
        assert [value for value,_ in calls]==[1,1,2,2],calls
        assert all(k['framing_bounds']==bounds and k['depth_bounds']==bounds for _,k in calls),calls
        assert len({k['framing_frame'] for _,k in calls})==1
        assert ctrl.evalParm('width')==1
        calls.clear()
        locked=h.test_controls(ctrl,out,tests,views=['front'])
        assert 'framing_bounds' not in calls[0][1] and calls[1][1]['framing_bounds']==bounds,calls
        def overflow(node,**kwargs):
            if ctrl.evalParm('width')==2:raise h.CheckpointError('framing/depth envelope exceeded',
                {'framing_status':'failed','render_started':False,'user_state_restored':True})
            return render(node,**kwargs)
        h.render_view=overflow
        rejected=h.test_controls(ctrl,out,tests,views=['front'])
        assert rejected['status']=='unverified' and rejected['capture_status']=='unverified',rejected
        assert rejected['results'][0]['status']=='pass' and rejected['restored'],rejected
        assert ctrl.evalParm('width')==1
        # Failure to capture baseline must not silently refit the perturbed view.
        calls.clear()
        def missing_baseline(node,**kwargs):
            calls.append(ctrl.evalParm('width'));raise ValueError('renderer unavailable')
        h.render_view=missing_baseline
        unavailable=h.test_controls(ctrl,out,tests,views=['front'])
        assert calls==[1] and unavailable['capture_status']=='unverified',calls
        assert unavailable['restored'] and ctrl.evalParm('width')==1
        def unsafe_restore(node,**kwargs):
            raise h.CheckpointError('render state restoration failed',{'user_state_restored':False,'restore_errors':['fixture']})
        h.render_view=unsafe_restore
        try:h.test_controls(ctrl,out,tests,views=['front'])
        except h.CheckpointError as error:assert error.evidence['user_state_restored'] is False
        else:raise AssertionError('user-state restore failure must not become an ordinary missing capture')
        h.render_view=render
        def failed_restore(snapshots):
            errors=original_restore(snapshots);return errors+['injected restoration fault']
        h._restore_parameters=failed_restore
        try:
            h.test_controls(ctrl,out,tests)
            raise AssertionError('restoration fault must raise')
        except h.CheckpointError as error:
            assert error.evidence['contract_sha256']==good['contract_sha256']
            assert error.evidence['control_summary']['contract_sha256']==good['contract_sha256']
    finally:
        h.render_view=original_render;hou.isUIAvailable=original_ui;h._restore_parameters=original_restore
    headless=h.test_controls(ctrl,out,tests,views=['front'])
    assert headless['capture_status']=='unverified' and headless['restored'],headless
    try:h.test_controls(ctrl,out,tests,views=['front'],view_bounds=[[0,0,0],[0,1,1]])
    except ValueError:pass
    else:raise AssertionError('degenerate bounds accepted')
    assert ctrl.evalParm('width')==1
print('early/repaired/restoration receipt identity and fixed baseline/case captures passed on '+hou.applicationVersionString())
