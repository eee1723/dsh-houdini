"""Template cardinality and actual-output transform oracles, not bbox proxies."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_quality_contracts as q
import dsh_geometry_observation as o


def rejected(fn, needle):
    try:fn()
    except (ValueError,q.UnsupportedEvidence) as error:assert needle in str(error),str(error)
    else:raise AssertionError('expected '+needle)


root=hou.node('/obj').createNode('geo','modeling_identity_test')
try:
    wr=root.createNode('attribwrangle','templates')
    wr.parm('snippet').set('for(int i=0;i<7;i++){int p=addpoint(0,set(i,0,0));setpointattrib(0,"id",p,i);}')
    wr.parm('class').set('number')
    repeated=h.geo_attrib_stats(wr,'P',unique=True)
    assert repeated['count']>7 and repeated['unique_count']==7 and not repeated['all_unique'],repeated
    wr.parm('class').set('detail')
    assert h.geo_attrib_stats(wr,'id',unique=True)['all_unique']
    assert h.geo_attrib_stats(wr,'P',unique=True)['count']==7
    rejected(lambda:h.geo_attrib_stats(wr,'P',unique=True,max_elements=3),'budget')
    # Intentional Numbers mode is valid when each iteration creates its own point.
    wr.parm('class').set('number');wr.parm('snippet').set('int p=addpoint(0,set(@elemnum,0,0));setpointattrib(0,"id",p,@elemnum);')
    assert h.geo_attrib_stats(wr,'id',unique=True)['all_unique']
    # String IDs, exact near-coincident tuples, vertex class, empty/nonfinite limits.
    geo=hou.Geometry();attr=geo.addAttrib(hou.attribType.Point,'label','')
    for i in range(3):
        pt=geo.createPoint();pt.setPosition((i*1e-8,0,0));pt.setAttribValue(attr,'same' if i<2 else 'other')
    assert o.attribute_uniqueness(geo,attr,'point',100)['unique_count']==2
    assert o.attribute_uniqueness(geo,geo.findPointAttrib('P'),'point',100)['all_unique']
    geo.point(0).setPosition((float('nan'),0,0))
    rejected(lambda:o.attribute_uniqueness(geo,geo.findPointAttrib('P'),'point',100),'nonfinite')
    empty=hou.Geometry()
    assert o.attribute_uniqueness(empty,empty.findPointAttrib('P'),'point',100)['all_unique'] is False
    mesh=root.createNode('box','attribute_classes')
    classes=mesh.geometry().freeze()
    vertex_attr=classes.addAttrib(hou.attribType.Vertex,'tag',0)
    detail_attr=classes.addAttrib(hou.attribType.Global,'vector_value',(1.,2.,3.))
    prim_attr=classes.addAttrib(hou.attribType.Prim,'name','same')
    for i,v in enumerate(v for p in classes.prims() for v in p.vertices()):v.setAttribValue(vertex_attr,i)
    assert o.attribute_uniqueness(classes,vertex_attr,'vertex',100)['unique_count']==24
    assert o.attribute_uniqueness(classes,detail_attr,'detail',100)['all_unique']
    assert o.attribute_uniqueness(classes,prim_attr,'prim',100)['duplicate_count']==5

    ctrl=root.createNode('null','CONTROL')
    h.create_spare_parms(ctrl,spec=[{'type':'float','name':'angle','default':0},
                                  {'type':'float','name':'wrong_follow','default':0}])
    body=root.createNode('box','body');body.parm('tx').set(2)
    tile=root.createNode('box','tile');tile.parmTuple('size').set((.1,.5,.5));tile.parm('tx').set(2.6)
    still=root.createNode('box','still');still.parm('tx').set(-2)
    merge=root.createNode('merge','assembly');merge.setInput(0,body);merge.setInput(1,tile);merge.setInput(2,still)
    tag=root.createNode('attribwrangle','identity');tag.setInput(0,merge)
    tag.parm('class').set('point');tag.parm('snippet').set('i@id=@ptnum;')
    groups=root.createNode('attribwrangle','groups');groups.setInput(0,tag)
    groups.parm('class').set('primitive');groups.parm('snippet').set('i@group_moving=@primnum<12; i@group_still=@primnum>=12;')
    twist=root.createNode('attribwrangle','twist');twist.setInput(0,groups)
    twist.parm('snippet').set('matrix3 r=ident(); rotate(r,radians(ch("../CONTROL/angle")),{0,0,1}); if(@ptnum<16){if(@ptnum<8 || ch("../CONTROL/wrong_follow")==0) @P*=r;}')
    expected=list(hou.hmath.buildRotate((0,0,45)).asTuple())
    exp={'metric':'max_transform_error','group':'moving','id_attrib':'id','transform':expected,'delta':[0,1e-5],'range':[0,1e-5]}
    test=[{'id':'rigid_follow','values':{'angle':45},'expectations':[
        {'metric':'max_point_displacement','group':'moving','id_attrib':'id','delta':[1,3]},
        exp,
        {'metric':'max_transform_error','group':'still','id_attrib':'id','transform':list(hou.Matrix4(1).asTuple()),'delta':[0,1e-5]}]}]
    baseline=q._data_signature(twist.geometry())
    good=h.test_controls(ctrl,twist,test)
    assert good['ok'] and good['restored'],good
    assert baseline==q._data_signature(twist.geometry())
    ctrl.parm('wrong_follow').set(1)
    bad=h.test_controls(ctrl,twist,test)
    assert bad['status']=='fail' and bad['restored'],bad
    assert any(not m['pass'] and m['expectation']['metric']=='max_transform_error' for m in bad['results'][0]['measurements']),bad
    rejected(lambda:q._validate_expectation({**exp,'transform':[0]*16}),'affine')
    frozen=twist.geometry().freeze();frozen.point(0).setAttribValue('id',1)
    rejected(lambda:q._measure(frozen,exp),'duplicate')
    # Whole-assembly bounds can scale correctly while an interior part receives
    # an extra local deformation. Stable-ID transform checks must reject this.
    h.create_spare_parms(ctrl,spec=[{'type':'float','name':'scale','default':1}])
    scaling=root.createNode('attribwrangle','scaling');scaling.setInput(0,groups)
    scaling.parm('snippet').set('float s=ch("../CONTROL/scale"); if(@ptnum<8) @P.x+=0.2*(s-1); @P*=s;')
    scale_test=[{'id':'scale_response','values':{'scale':1.05},'expectations':[
        {'metric':'bounds_size','axis':0,'delta':[.25,.27]}]}]
    scaled=h.test_controls(ctrl,scaling,scale_test)
    assert scaled['ok'] and scaled['control_summary']['coverage']['relationship_scope']=='not_checked',scaled
    scale_test[0]['expectations'].append({'metric':'max_transform_error','id_attrib':'id',
        'transform':list(hou.hmath.buildScale((1.05,1.05,1.05)).asTuple()),'delta':[0,1e-5],'range':[0,1e-5]})
    signature=q._data_signature(scaling.geometry())
    nonuniform=h.test_controls(ctrl,scaling,scale_test)
    assert nonuniform['status']=='fail' and nonuniform['restored'],nonuniform
    assert nonuniform['results'][0]['measurements'][-1]['measured']>.01
    assert signature==q._data_signature(scaling.geometry()) and ctrl.evalParm('scale')==1
    scaling.parm('snippet').set('@P*=ch("../CONTROL/scale");')
    assert h.test_controls(ctrl,scaling,scale_test)['ok'],'genuine uniform scale still passes'
finally:
    root.destroy()
print('template uniqueness / intentional Numbers / transform-follow negative control / restoration passed: '+hou.applicationVersionString())
