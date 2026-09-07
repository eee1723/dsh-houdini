"""H21/H22: final-geometry interface checks and reversible control contracts."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as b


def rejects(fn, match):
    try: fn()
    except Exception as e:
        assert match in str(e), str(e)
        return
    raise AssertionError('expected rejection: ' + match)


root = hou.node('/obj').createNode('geo','__quality_contract')
try:
    ctrl=root.createNode('null','CONTROL')
    h.create_spare_parms(ctrl,spec=[{'type':'float','name':'length','default':1},
                                  {'type':'float','name':'unused','default':1}])
    # Two boxes share a mating plane. Named groups reference real final faces,
    # not an independent point/axis helper that can pass while the boxes detach.
    specs=[
      {'name':'part_a','type':'box','parms':{'sizex':"ch('../CONTROL/length')",'tx':"ch('../CONTROL/length')/2"}},
      {'name':'tag_a','type':'attribwrangle','inputs':['part_a'],'parms':{'class':'point','snippet':
         'if (@P.x>0.0001) setpointgroup(0,"a_port",@ptnum,1);'}},
      {'name':'part_b','type':'box','parms':{'tx':"ch('../CONTROL/length')+0.5"}},
      {'name':'tag_b','type':'attribwrangle','inputs':['part_b'],'parms':{'class':'primitive','snippet':
         'setprimgroup(0,"b_surface",@primnum,1);'}},
      {'name':'assembly','type':'merge','inputs':['tag_a','tag_b']},
      {'name':'OUT','type':'null','inputs':['assembly']},
    ]
    interface={'id':'join','source_group':'a_port','target_group':'b_surface','max_distance':.001,'expected_points':4}
    built=h.build_module(root,specs,output='OUT',interfaces=[interface])
    assert built['interface_checks']['ok'],built
    out=root.node('OUT')
    checks=h.geo_check_interfaces(out,[interface])
    assert checks['ok'] and checks['results'][0]['max_distance']<1e-6,checks
    # Coverage names come from actual selected final primitives, not the name
    # of the interface group or an agent-authored completeness claim.
    import dsh_quality_contracts as q
    named=out.geometry().freeze()
    named.addAttrib(hou.attribType.Prim,'name','')
    target_ids={p.number() for p in named.findPrimGroup('b_surface').prims()}
    for prim in named.prims():prim.setAttribValue('name','member_b' if prim.number() in target_ids else 'member_a')
    coverage=q._check_interfaces(named,[interface],50000)['results'][0]
    assert coverage['source_pieces']==['member_a'] and coverage['target_pieces']==['member_b'],coverage
    assert not coverage['piece_coverage_truncated']
    h.set_parm(root.node('part_b'),'ty',.3)
    detached=h.geo_check_interfaces(out,[interface])
    assert detached['status']=='fail' and detached['results'][0]['failure_count']>0,detached
    h.set_parm(root.node('part_b'),'ty',0)
    missing={**interface,'source_group':'not_present'}
    assert not h.geo_check_interfaces(out,[missing])['ok']
    assert h.geo_check_interfaces(out,[{**interface,'expected_points':1}])['status']=='fail'
    rejects(lambda:h.geo_check_interfaces(out,[interface],max_pairs=1),'budget')
    rejects(lambda:h.geo_check_interfaces(out,[interface,interface]),'unique')
    rejects(lambda:h.geo_check_interfaces(out,[{**interface,'max_distance':float('nan')}]),'finite')
    self_surface=root.createNode('attribwrangle','self_surface')
    self_surface.setInput(0,out);self_surface.parm('class').set('primitive')
    self_surface.parm('snippet').set('setprimgroup(0,"self",@primnum,1);')
    self_check=h.geo_check_interfaces(self_surface,[{**interface,'target_group':'self'}])
    assert self_check['results'][0]['reason']=='source_and_target_overlap_cannot_self_validate',self_check
    # Unattached driver points must not masquerade as final surface interfaces.
    isolated=root.createNode('attribwrangle','isolated')
    isolated.setInput(0,out);isolated.parm('class').set('detail')
    isolated.parm('snippet').set('int pt=addpoint(0,set(1,0,0));setpointgroup(0,"driver",pt,1);')
    driver_check=h.geo_check_interfaces(isolated,[{**interface,'source_group':'driver','expected_points':1}])
    assert driver_check['status']=='unverified',driver_check
    # Open polylines are not target surfaces; no false confirmation from them.
    unsupported=root.createNode('attribwrangle','unsupported')
    unsupported.setInput(0,out);unsupported.parm('class').set('detail')
    unsupported.parm('snippet').set('int a=addpoint(0,set(1,0,0));int b=addpoint(0,set(1,1,0));int pr=addprim(0,"polyline",a,b);setprimgroup(0,"wire",pr,1);')
    assert h.geo_check_interfaces(unsupported,[{**interface,'target_group':'wire'}])['status']=='unverified'

    # The relation is also rechecked while the user control is perturbed.
    tests=[{'id':'length_response','values':{'length':1.2},'expectations':[
      {'metric':'bounds_size','axis':0,'delta':[.199,.201]}]}]
    result=h.test_controls(ctrl,out,tests,interfaces=[interface])
    assert result['ok'] and result['restored'] and ctrl.evalParm('length')==1,result
    result=h.test_controls(ctrl,out,[{'id':'dead','values':{'unused':2},'expectations':[
      {'metric':'bounds_size','axis':0,'delta':[.1,2]}]}])
    assert not result['ok'] and result['restored'] and ctrl.evalParm('unused')==1,result
    rejects(lambda:h.test_controls(ctrl,out,[{'id':'no_response','values':{'unused':2},'expectations':[
        {'metric':'bounds_size','axis':0,'delta':[-1,1]}]}]),'non-zero expected response')
    # Local selection: avoid a global bbox hiding the expected module response.
    tests_group=[{'id':'local','values':{'length':1.2},'expectations':[
      {'metric':'bounds_center','group':'b_surface','axis':0,'delta':[.199,.201]}]}]
    assert h.test_controls(ctrl,out,tests_group)['ok']
    rejects(lambda:h.test_controls(ctrl,out,[{'id':'missing','values':{'length':1.2},'expectations':[
      {'metric':'bounds_size','axis':0,'group':'missing','delta':[.1,1]}]}]),'missing measurement group')
    assert ctrl.evalParm('length')==1
    from dsh_quality_contracts import _measure
    empty_geometry=hou.Geometry(out.geometry());empty_geometry.createPrimGroup('empty')
    rejects(lambda:_measure(empty_geometry,{'metric':'point_count','group':'empty'}),'empty')
    ctrl.parm('length').lock(True)
    rejects(lambda:h.test_controls(ctrl,out,tests),'锁定')
    ctrl.parm('length').lock(False)
    # A hard-coded neighbor makes the default relation correct but perturbation wrong.
    h.set_parm(root.node('part_b'),'tx',1.5)
    result=h.test_controls(ctrl,out,tests,interfaces=[interface])
    assert not result['ok'] and result['restored'],result
    h.set_parm(root.node('part_b'),'tx',"ch('../CONTROL/length')+0.5")

    # Native Tube: radius lives in primitive intrinsic state, not point P.
    native=root.createNode('tube','native')
    native.parm('rad1').set(.25);native.parm('rad2').set(.25)
    result=h.test_controls(native,native,[{'id':'radius','values':{'rad1':.35,'rad2':.35},
      'expectations':[{'metric':'bounds_size','axis':0,'delta':[.199,.201]}]}])
    assert result['ok'] and result['restored'],result
    packed=root.createNode('pack','packed');packed.setInput(0,root.node('part_a'))
    packed_test=[{'id':'packed_size','values':{'length':1.2},'expectations':[
        {'metric':'bounds_size','axis':0,'delta':[.199,.201]}]}]
    packed_result=h.test_controls(ctrl,packed,packed_test)
    assert packed_result['status']=='unverified' and packed_result['parameter_writes']==0 and ctrl.evalParm('length')==1,packed_result
    area_test=[{'id':'packed_area','values':{'length':1.2},'expectations':[
        {'metric':'area','delta':[.1,1]}]}]
    unsupported_area=h.test_controls(ctrl,packed,area_test)
    assert unsupported_area['status']=='unverified' and ctrl.evalParm('length')==1,unsupported_area
    # Expression/keys and frame remain unchanged even if the perturbed cook fails.
    ctrl.parm('length').setExpression('1+0*$F',hou.exprLanguage.Hscript)
    bad=root.createNode('attribwrangle','bad')
    bad.parm('class').set('detail');bad.setInput(0,root.node('part_a'))
    bad.parm('snippet').set('if(ch("../CONTROL/length")>1.1) error("intentional cook failure");')
    frame=hou.frame()
    result=h.test_controls(ctrl,bad,tests)
    assert not result['ok'] and result['restored'] and hou.frame()==frame,result
    assert ctrl.parm('length').expression()=='1+0*$F'
    # Never continue silently when restoration itself reports a problem.
    original_restore=h._restore_parameters
    def restore_then_report_failure(values):
        errors=original_restore(values)
        return errors+['injected restoration report failure']
    try:
        h._restore_parameters=restore_then_report_failure
        rejects(lambda:h.test_controls(ctrl,out,tests_group),'restoration failed')
    finally:h._restore_parameters=original_restore
    assert ctrl.parm('length').expression()=='1+0*$F'

    # Foreign controllers cannot be perturbed just because the output is readable.
    with h._execution_owner('different-session','test'):
        rejects(lambda:h.test_controls(ctrl,out,tests),'ownership guard')
        allowed=h.test_controls(ctrl,out,tests_group,allow_foreign='user explicitly authorized testing this controller')
        assert allowed['restored'],allowed
    # Persistent service protection does not accept foreign exemptions.
    ctrl.setUserData(h._RENDER_OWNER_KEY,h._RENDER_OWNER_VALUE)
    with h._execution_owner('different-session','service-test'):
        rejects(lambda:h.test_controls(ctrl,out,tests,allow_foreign='test'),'persistent')
    ctrl.destroyUserData(h._RENDER_OWNER_KEY)
    query=b.run_code(f'test_controls({ctrl.path()!r},{out.path()!r},[])',read_only=True)
    assert not query['ok'] and 'read-only' in query['error'],query

    # Construction fails atomically when its requested interface is absent.
    previous=set(root.children())
    rejects(lambda:h.build_module(root,[{'name':'bad_contract','type':'box'}],output='bad_contract',interfaces=[interface]),'interface')
    assert set(root.children())==previous
finally:root.destroy()

print('final geometry interface/control contracts passed')
