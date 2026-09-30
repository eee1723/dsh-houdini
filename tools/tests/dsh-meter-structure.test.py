"""Meter conversion, actual guide extents, surface-attached details and failures."""
from pathlib import Path
import sys,math
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_context
import dsh_bridge as bridge

def rejects(fn,text):
    try:fn()
    except Exception as error:assert text in str(error),(text,str(error))
    else:raise AssertionError('expected rejection: '+text)

assert dsh_context.unit_length_meters()==1
quantities={'base_l':{'value':120,'unit':'mm','source':'fixture'},'base_h':{'value':12,'unit':'mm'},
    'base_w':{'value':5,'unit':'cm'},'travel':{'value':30,'min':10,'max':70,'unit':'mm'},
    'count':{'value':4,'min':3,'max':6,'unit':'count'},'angle':{'value':math.pi/2,'unit':'rad'},
    'area':{'value':100,'unit':'mm2'},'volume':{'value':1000,'unit':'mm3'}}
before=hou.hipFile.path();q=h.modeling_dimensions(quantities)
assert q['canonical_values']['base_l']==.12 and q['canonical_values']['base_w']==.05
assert q['canonical_values']['count']==4 and abs(q['canonical_values']['angle']-90)<1e-9
assert abs(q['canonical_values']['area']-.0001)<1e-12 and abs(q['canonical_values']['volume']-.000001)<1e-12
assert hou.hipFile.path()==before and dsh_context.unit_length_meters()==1
with patch.object(dsh_context,'unit_length_meters',return_value=.001):
    rejects(lambda:h.modeling_dimensions(quantities),'not meter-based')
    adapted=h.modeling_dimensions(quantities,require_meter_scene=False)
    assert adapted['scene_values']['base_l']==120 and adapted['controller_spec'] is None
with patch.object(dsh_context,'unit_length_meters',return_value=None):rejects(lambda:h.modeling_dimensions(quantities),'unavailable')
rejects(lambda:h.modeling_dimensions({'bad':{'value':1,'unit':[]}}),'unsupported unit')
rejects(lambda:h.modeling_dimensions({'bad':{'value':True,'unit':'mm'}}),'finite scalar')
rejects(lambda:h.modeling_dimensions({'bad':{'value':2.2,'unit':'count'}}),'integers')

with h._execution_owner('meter-structure','fixture'):
    root=h.tab_create('/obj','geo','meter_structure');ctrl=h.tab_create(root,'null','CTRL')
    h.create_spare_parms(ctrl,spec=q['controller_spec'])
    base=h.tab_create(root,'box','base');h.set_parms(base,{'sizex':"ch('../CTRL/base_l')",'sizey':"ch('../CTRL/base_h')",'sizez':"ch('../CTRL/base_w')",'ty':"ch('../CTRL/base_h')/2"})
    tag=h.tab_create(root,'attribwrangle','tag');h.connect(base,tag,0)
    h.set_parms(tag,{'class':'primitive','snippet':'i@group_body=1;if(@N.y>0.5)i@group_mount_surface=1;'})
    # Primitive geometric normals are not assumed to exist as an N attribute.
    h.set_parms(tag,{'snippet':'i@group_body=1;vector n=prim_normal(0,@primnum,0.5,0.5);if(n.y>0.5)i@group_mount_surface=1;'})
    check=h.geo_check_interfaces(tag,[{'id':'length','method':'physical_extent','target_group':'body','axis':0,'expected_mm':120,'tolerance_mm':.01}])
    assert check['status']=='pass',check
    for name in ('final_custom_name','OUT_ASSET'):
        final=h.tab_create(root,'null',name);h.connect(tag,final,0)
        receipt=h.verify_network(root,output=final,nodes=[final])
        assert receipt['scene_unit_length_meters']==1
        assert abs(receipt['bbox_size_sop_local_mm'][0]-120)<.001
    h.set_parms(base,{'sizex':120})
    wrong=h.verify_network(root,output=root.node('final_custom_name'),nodes=[root.node('final_custom_name')])
    assert wrong['bbox_size_sop_local_mm'][0]==120000 and wrong['semantic_status']=='unverified'
    assert h.geo_check_interfaces(tag,[{'id':'length','method':'physical_extent','target_group':'body','axis':0,'expected_mm':120,'tolerance_mm':.01}])['status']=='fail'
    h.set_parms(base,{'sizex':"ch('../CTRL/base_l')"})
    guide=h.tab_create(root,'box','guide');h.set_parms(guide,{'size':(.116,.008,.012),'ty':.016})
    body=h.tab_create(root,'box','moving');h.set_parms(body,{'size':(.020,.010,.020),'ty':.025})
    plan=h.sop_recipe('guided_slider',{'name':'safe','inputs':['moving'],'guide':'guide','parameter':'travel',
        'travel_min':.01,'travel_max':.07,'clearance':.002})
    h.build_module(root,plan['nodes'],plan['output'])
    out=root.node(plan['output'])
    for value in (.01,.03,.07):
        h.set_parms(ctrl,{'travel':value});g=out.geometry();a=g.boundingBox();b=guide.geometry().boundingBox()
        assert a.minvec()[0]>=b.minvec()[0]+.00199 and a.maxvec()[0]<=b.maxvec()[0]-.00199
    h.set_parms(ctrl,{'travel':.03})
    h.set_parms(guide,{'sizex':.03})
    rejects(lambda:h.verify_network(root,output=out,nodes=[out]),'cook_error')
    h.set_parms(guide,{'sizex':.116});assert h.verify_network(root,output=out,nodes=[out])['ok']
    rib=h.sop_recipe('gusset',{'name':'rib','length':.010,'height':.008,'thickness':.002})
    h.build_module(root,rib['nodes'],rib['output'])
    mount=h.sop_recipe('surface_attach',{'name':'mount','inputs':[rib['output']],'receiver':'tag','receiver_group':'mount_surface',
        'origin':[0,.020,0],'tangent':[1,0,0],'max_distance':.02})
    h.build_module(root,mount['nodes'],mount['output'])
    merge=h.tab_create(root,'merge','OUT_ASSET');h.connect(tag,merge,0);h.connect(root.node(mount['output']),merge,1)
    contact=[{'id':'foot','source_group':'rib_foot','target_group':'body','expected_points':4,'max_distance':1e-7}]
    assert h.geo_check_interfaces(merge,contact)['status']=='pass'
    h.set_parms(ctrl,{'base_h':.018});assert h.geo_check_interfaces(merge,contact)['status']=='pass'
    h.set_parms(ctrl,{'base_h':.012})
    bad={**mount['nodes'][1],'name':'bad_frame','parms':dict(mount['nodes'][1]['parms'])}
    bad['parms']['snippet']=bad['parms']['snippet'].replace('mount_surface','absent_surface')
    rejects(lambda:h.build_module(root,[bad],bad['name']),'cook_error')
    assert root.node('bad_frame') is None
    bolt=h.sop_recipe('fastener',{'name':'bolt','shaft_radius':.002,'shaft_length':.008,'head_radius':.004,'head_height':.003})
    h.build_module(root,bolt['nodes'],bolt['output'])
    box=root.node(bolt['output']).geometry().boundingBox()
    assert abs(box.maxvec()[1]-.011)<1e-7 and abs(box.minvec()[1])<1e-7
    read=bridge.run_code('__result__=modeling_dimensions({"length":{"value":120,"unit":"mm"}})',read_only=True,owner_session='meter-structure')
    assert read['ok'] and read['result']['canonical_values']['length']==.12
print('meter conversion, guided travel and actual surface detail attachment passed',hou.applicationVersionString())
