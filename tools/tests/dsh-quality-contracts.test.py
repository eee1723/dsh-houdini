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
    size=h.verify_network(root,output=out)['geometry']['bbox_size']
    assert len(size)==3 and all(abs(value-target)<1e-6 for value,target in zip(size,(2,1,1))),size
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
    assert result['control_summary']['case_counts']=={'pass':1,'fail':0,'unverified':0,'not_run':0}
    assert result['control_summary']['coverage']['declared_interfaces']==1
    assert result['control_summary']['cases'][0]['interface_status']=='pass'
    # A case-specific interface checks only the perturbed state; no baseline
    # contact contract is silently applied to an intentionally open state.
    conditional=[{'id':'length_case_interface','values':{'length':1.2},'expectations':[
      {'metric':'bounds_size','axis':0,'delta':[.199,.201]}],'interfaces':[interface]},
      {'id':'length_no_interface','values':{'length':1.3},'expectations':[
      {'metric':'bounds_size','axis':0,'delta':[.299,.301]}]}]
    scoped=h.test_controls(ctrl,out,conditional)
    assert scoped['ok'] and scoped['baseline_interfaces'] is None and scoped['restored'],scoped
    assert scoped['control_summary']['coverage']['declared_interfaces']==1,scoped
    assert scoped['control_summary']['coverage']['case_interface_contracts_declared']==1,scoped
    assert [case['interface_status'] for case in scoped['control_summary']['cases']]==['pass','not_checked'],scoped
    rejects(lambda:h.test_controls(ctrl,out,[{**conditional[0],
        'interfaces':[{**interface,'expected_points':0}]}]),'expected_points')
    assert ctrl.evalParm('length')==1
    invalid_case=h.test_controls(ctrl,out,[{**conditional[0],
        'interfaces':[{**interface,'expected_points':1}]}])
    assert invalid_case['status']=='fail' and invalid_case['restored'] and invalid_case['baseline_interfaces'] is None,invalid_case
    assert invalid_case['results'][0]['interfaces']['status']=='fail',invalid_case
    rejects(lambda:h.test_controls(ctrl,out,[conditional[0]],interfaces=[interface]),'unique')
    # Closed contact and opened separation require different relations. A
    # global closed-contact invariant should fail on opening; a case-specific
    # axis gap should pass while retaining automatic control/bgeo restoration.
    gap_ctrl=root.createNode('null','OPEN_CTRL')
    h.create_spare_parms(gap_ctrl,spec=[{'type':'float','name':'lift','default':0}])
    h.build_module(root,[
      {'name':'gap_base','type':'box','parms':{'sizey':.2,'ty':.1}},
      {'name':'gap_base_tag','type':'attribwrangle','inputs':['gap_base'],
       'parms':{'class':'primitive','snippet':'i@group_gap_base=1;'}},
      {'name':'gap_cap','type':'box','parms':{'sizey':.2,'ty':"ch('../OPEN_CTRL/lift')+0.3"}},
      {'name':'gap_cap_tag','type':'attribwrangle','inputs':['gap_cap'],
       'parms':{'class':'primitive','snippet':'i@group_gap_cap=1;'}},
      {'name':'gap_out','type':'merge','inputs':['gap_base_tag','gap_cap_tag']}],output='gap_out')
    gap_out=root.node('gap_out')
    contact={'id':'closed_contact','method':'axis_gap','source_group':'gap_cap','target_group':'gap_base',
             'axis':1,'gap_range':[-.001,.001],'min_overlap':.9}
    separated={'id':'opened_gap','method':'axis_gap','source_group':'gap_cap','target_group':'gap_base',
               'axis':1,'gap_range':[.99,1.01],'min_overlap':.9}
    assert h.geo_check_interfaces(gap_out,[contact])['ok']
    open_case=[{'id':'open','values':{'lift':1},'expectations':[
      {'metric':'bounds_size','axis':1,'delta':[.99,1.01]}],'interfaces':[separated]}]
    old_global=h.test_controls(gap_ctrl,gap_out,[{k:v for k,v in open_case[0].items() if k!='interfaces'}],
                               interfaces=[contact])
    assert old_global['status']=='fail' and old_global['restored'],old_global
    opened=h.test_controls(gap_ctrl,gap_out,open_case)
    assert opened['ok'] and opened['restored'] and gap_ctrl.evalParm('lift')==0,opened
    assert opened['results'][0]['interfaces']['results'][0]['gap']>0.99,opened
    assert opened['control_summary']['coverage']['relationship_scope']=='declared_contracts_only',opened
    full_cycle=h.test_controls(gap_ctrl,gap_out,open_case,baseline_interfaces=[contact])
    assert full_cycle['ok'] and full_cycle['restored'] and full_cycle['baseline_interfaces']['status']=='pass',full_cycle
    full_coverage=full_cycle['control_summary']['coverage']
    assert full_coverage['declared_interfaces']==2 and full_coverage['baseline_interface_status']=='pass',full_cycle
    assert full_coverage['cases_with_interface_checks']==1 and full_coverage['executed_interface_checks']==2,full_cycle
    assert full_cycle['contract_sha256']!=opened['contract_sha256'],full_cycle
    baseline_only=h.test_controls(gap_ctrl,gap_out,[{k:v for k,v in open_case[0].items() if k!='interfaces'}],
                                  baseline_interfaces=[contact])
    assert baseline_only['ok'] and baseline_only['control_summary']['coverage']['baseline_interface_status']=='pass',baseline_only
    assert baseline_only['control_summary']['coverage']['cases_with_interface_checks']==0,baseline_only
    assert baseline_only['control_summary']['coverage']['executed_interface_checks']==1,baseline_only
    rejects(lambda:h.test_controls(gap_ctrl,gap_out,open_case,interfaces=[contact],
        baseline_interfaces=[contact]),'unique')
    bad_baseline={**contact,'gap_range':[.5,1.5]}
    baseline_failed=h.test_controls(gap_ctrl,gap_out,open_case,baseline_interfaces=[bad_baseline])
    assert baseline_failed['status']=='fail' and baseline_failed['parameter_writes']==0,baseline_failed
    assert baseline_failed['results']==[] and gap_ctrl.evalParm('lift')==0,baseline_failed
    baseline_coverage=baseline_failed['control_summary']['coverage']
    assert baseline_coverage['baseline_interface_status']=='fail',baseline_failed
    assert baseline_coverage['cases_with_interface_checks']==0 and baseline_coverage['executed_interface_checks']==1,baseline_failed
    bad_open=[{**open_case[0],'interfaces':[{**separated,'gap_range':[2,3]}]}]
    opened_failed=h.test_controls(gap_ctrl,gap_out,bad_open,baseline_interfaces=[contact])
    assert opened_failed['status']=='fail' and opened_failed['restored'] and gap_ctrl.evalParm('lift')==0,opened_failed
    assert opened_failed['baseline_interfaces']['status']=='pass' and opened_failed['results'][0]['interfaces']['status']=='fail',opened_failed
    envelope=b.run_code(f'__result__=test_controls({gap_ctrl.path()!r},{gap_out.path()!r},{open_case!r},baseline_interfaces={[contact]!r})')
    bridge_result=next(item for item in envelope['evidence'] if item.get('verb')=='test_controls')
    assert bridge_result['control_summary']['coverage']['baseline_interface_status']=='pass',bridge_result
    assert bridge_result['control_summary']['coverage']['executed_interface_checks']==2,bridge_result
    assert bridge_result['control_summary']['cases'][0]['interface_status']=='pass',bridge_result
    # Absolute ranges apply to baseline too: a rejected baseline must not look
    # like an empty successful batch when author code prints only results.
    baseline_test=[{'id':'target_only_range','values':{'length':1.2},'expectations':[
        {'metric':'bounds_size','axis':0,'delta':[.199,.201],'range':[2.19,2.21]}]}]
    env=b.run_code(f'r=test_controls({ctrl.path()!r},{out.path()!r},{baseline_test!r},baseline_interfaces={[interface]!r}); print(r["results"])')
    evidence=next(e for e in env['evidence'] if e['verb']=='test_controls')
    summary=evidence['control_summary']
    assert env['ok'] and summary['status']=='fail' and summary['parameter_writes']==0,env
    assert summary['case_counts']['not_run']==1 and summary['case_id']=='target_only_range'
    assert summary['baseline']==2 and summary['expectation']['range']==[2.19,2.21]
    assert evidence['controller']==ctrl.path() and evidence['output']==out.path()
    assert summary['controller']==ctrl.path() and summary['output']==out.path()
    assert summary['coverage']['measured_cases']==0
    assert summary['coverage']['declared_controls']==['length']
    assert summary['coverage']['baseline_interface_status']=='pass' and summary['coverage']['executed_interface_checks']==1
    assert summary['cases'][0]['output_data_changed'] is None,'not_run must not be reported unchanged'
    assert ctrl.evalParm('length')==1 and evidence['results']==[]
    result=h.test_controls(ctrl,out,[{'id':'dead','values':{'unused':2},'expectations':[
      {'metric':'bounds_size','axis':0,'delta':[.1,2]}]}])
    assert not result['ok'] and result['restored'] and ctrl.evalParm('unused')==1,result
    failure=result['control_summary']['failures'][0]
    assert failure['id']=='dead' and failure['failed_measurement_count']==1
    assert failure['failed_measurements'][0]['delta']==0
    assert failure['geometry_changed'] is False
    assert result['control_summary']['cases'][0]['output_data_changed'] is False
    rejects(lambda:h.test_controls(ctrl,out,[{'id':'no_response','values':{'unused':2},'expectations':[
        {'metric':'bounds_size','axis':0,'delta':[-1,1]}]}]),'non-zero expected response')
    too_many=[{'metric':'bounds_size','axis':0,'delta':[.1,.3]} for _ in range(17)]
    rejects(lambda:h.test_controls(ctrl,out,[{'id':'split_me','values':{'length':1.2},
        'expectations':too_many}]),'split a larger check into multiple test cases with the same control values')
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
    # A shrinking part can pass an area response even after losing contact.
    detach_test=[{'id':'area_response','values':{'length':.8},'expectations':[
        {'metric':'area','delta':[-.801,-.799]}]}]
    narrow=h.test_controls(ctrl,out,detach_test)
    assert narrow['ok'] and narrow['control_summary']['coverage']['relationship_scope']=='not_checked',narrow
    assert narrow['control_summary']['coverage']['acceptance']=='declared_checks_only'
    result=h.test_controls(ctrl,out,tests,interfaces=[interface])
    assert not result['ok'] and result['restored'],result
    detached=h.test_controls(ctrl,out,detach_test,interfaces=[interface])
    assert not detached['ok'] and detached['restored'],detached
    assert detached['control_summary']['cases'][0]['interface_status']=='fail',detached
    h.set_parm(root.node('part_b'),'tx',"ch('../CONTROL/length')+0.5")

    # A local part moves inside a fixed outer envelope. Its global bbox does
    # not move, but it is not a dead control and must not be diagnosed as one.
    envelope=root.createNode('box','envelope');envelope.parmTuple('size').set((10,10,10))
    enclosed=root.createNode('merge','enclosed')
    enclosed.setInput(0,envelope);enclosed.setInput(1,out)
    local_test=[{'id':'local_motion','values':{'length':1.2},'expectations':[
        {'metric':'bounds_size','axis':0,'delta':[.199,.201]}]}]
    local=h.test_controls(ctrl,enclosed,local_test)
    assert not local['ok'] and local['restored']
    summary=local['control_summary']
    assert summary['cases'][0]['output_data_changed'] is True
    assert summary['cases'][0]['changed_output_with_failed_measurements'] is True
    assert summary['failures'][0]['geometry_changed'] is True
    env=b.run_code(f'__result__=test_controls({ctrl.path()!r},{enclosed.path()!r},{local_test!r})')
    ev=next(e for e in env['evidence'] if e['verb']=='test_controls')
    assert ev['control_summary']['cases'][0]['changed_output_with_failed_measurements'] is True
    local_test[0]['expectations'][0]={'metric':'bounds_center','axis':0,'group':'b_surface','delta':[.199,.201]}
    assert h.test_controls(ctrl,enclosed,local_test)['ok'],'measuring the affected part reveals the actual response'

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
    assert packed_result['control_summary']['case_counts']['not_run']==1
    assert 'restoration oracle' in packed_result['control_summary']['reason']
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

    # A visually coaxial shaft inside a capped Tube occupies the same solid
    # space. A real bored lug has no Boolean intersection with the shaft.
    bore_ctrl=root.createNode('null','BORE_CTRL')
    h.create_spare_parms(bore_ctrl,spec=[{'type':'float','name':'offset','default':0}])
    outer=root.createNode('tube','solid_lug')
    cutter=root.createNode('tube','bore_cutter')
    shaft=root.createNode('tube','bore_shaft')
    for node,radius,height in ((outer,.005,.02),(cutter,.0025,.022),(shaft,.002,.022)):
        h.set_parms(node,{'type':'poly','orient':'x','cap':1,'rad1':radius,
                          'rad2':radius,'height':height,'cols':32})
    h.set_parm(shaft,'ty',"ch('../BORE_CTRL/offset')")
    bored=root.createNode('boolean','bored_lug')
    bored.setInput(0,outer);bored.setInput(1,cutter)
    h.set_parm(bored,'booleanop','subtract')
    shaft_tag=root.createNode('attribwrangle','bore_shaft_tag')
    shaft_tag.setInput(0,shaft);shaft_tag.parm('class').set('primitive')
    shaft_tag.parm('snippet').set('setprimgroup(0,"shaft",@primnum,1);')
    def bore_assembly(source,name):
        tag=root.createNode('attribwrangle',name+'_lug_tag')
        tag.setInput(0,source);tag.parm('class').set('primitive')
        tag.parm('snippet').set('setprimgroup(0,"lug",@primnum,1);')
        merged=root.createNode('merge',name)
        merged.setInput(0,tag);merged.setInput(1,shaft_tag)
        return merged
    solid_assembly=bore_assembly(outer,'solid_bore_case')
    hollow_assembly=bore_assembly(bored,'hollow_bore_case')
    no_overlap={'id':'shaft_clearance','method':'solid_overlap','source_group':'lug',
                'target_group':'shaft','max_overlap_volume':1e-12}
    solid_check=h.geo_check_interfaces(solid_assembly,[no_overlap])
    assert solid_check['status']=='fail' and solid_check['results'][0]['overlap_volume']>2e-7,solid_check
    hollow_check=h.geo_check_interfaces(hollow_assembly,[no_overlap])
    assert hollow_check['status']=='pass' and hollow_check['results'][0]['overlap_volume']==0,hollow_check
    assert hollow_check['results'][0]['intersection_primitives']==0
    rejects(lambda:h.geo_check_interfaces(hollow_assembly,[no_overlap],max_pairs=1),'budget')
    rejects(lambda:h.geo_check_interfaces(hollow_assembly,[{**no_overlap,'max_overlap_volume':-1}]),'nonnegative')
    assert h.geo_check_interfaces(hollow_assembly,[{**no_overlap,'source_group':'missing'}])['status']=='fail'
    assert h.geo_check_interfaces(hollow_assembly,[{**no_overlap,'source_group':'shaft'}])['status']=='fail'
    h.set_parm(outer,'cap',0)
    assert h.geo_check_interfaces(solid_assembly,[no_overlap])['status']=='unverified'
    h.set_parm(outer,'cap',1)
    h.set_parm(outer,'type','prim')
    assert h.geo_check_interfaces(solid_assembly,[no_overlap])['status']=='unverified'
    h.set_parm(outer,'type','poly')
    within_bore=[{'id':'shaft_moves_inside_bore','values':{'offset':.0001},'expectations':[
      {'metric':'bounds_center','axis':1,'group':'shaft','delta':[.00009,.00011]}]}]
    moving_clear=h.test_controls(bore_ctrl,hollow_assembly,within_bore,interfaces=[no_overlap])
    assert moving_clear['ok'] and moving_clear['restored'],moving_clear
    assert moving_clear['control_summary']['coverage']['executed_interface_checks']==2,moving_clear
    shifted=[{'id':'shaft_hits_wall','values':{'offset':.003},'expectations':[
      {'metric':'bounds_center','axis':1,'group':'shaft','delta':[.0029,.0031]}]}]
    before=q._data_signature(hollow_assembly.geometry())
    moved=h.test_controls(bore_ctrl,hollow_assembly,shifted,interfaces=[no_overlap])
    assert moved['status']=='fail' and moved['restored'],moved
    assert moved['results'][0]['measurements'][0]['pass'] and moved['results'][0]['interfaces']['status']=='fail',moved
    assert q._data_signature(hollow_assembly.geometry())==before
    blocked=h.test_controls(bore_ctrl,solid_assembly,shifted,baseline_interfaces=[no_overlap])
    assert blocked['status']=='fail' and blocked['parameter_writes']==0 and blocked['results']==[],blocked
    envelope=b.run_code(f'__result__=geo_check_interfaces({solid_assembly.path()!r},{[no_overlap]!r})',read_only=True)
    evidence=next(row for row in envelope['evidence'] if row.get('verb')=='geo_check_interfaces')
    assert evidence['results'][0]['status']=='fail' and evidence['results'][0]['overlap_volume']>0,evidence

    # Construction fails atomically when its requested interface is absent.
    previous=set(root.children())
    rejects(lambda:h.build_module(root,[{'name':'bad_contract','type':'box'}],output='bad_contract',interfaces=[interface]),'interface')
    assert set(root.children())==previous
finally:root.destroy()

print('final geometry interface/control contracts passed')
