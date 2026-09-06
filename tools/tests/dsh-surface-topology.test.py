"""Fused surfaces vs independent contacts + full bgeo export-date normalization."""
from pathlib import Path
import copy,json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou,hjson
import dsh_hou_helpers as h
import dsh_quality_contracts as q

def rejects(fn,text):
    try:fn()
    except Exception as e:assert text in str(e),str(e)
    else:raise AssertionError('expected rejection')

root=hou.node('/obj').createNode('geo','__surface_topology')
try:
    ctrl=root.createNode('null','CTRL');h.create_spare_parms(ctrl,spec=[{'name':'offset','type':'float','default':.75}])
    spec=[{'name':'a','type':'box'},
          {'name':'b','type':'box','parms':{'tx':"ch('../CTRL/offset')"}},
          {'name':'ga','type':'groupcreate','inputs':['a'],'parms':{'groupname':'a'}},
          {'name':'gb','type':'groupcreate','inputs':['b'],'parms':{'groupname':'b'}},
          {'name':'union','type':'boolean','inputs':['ga','gb'],'parms':{'booleanop':'union'}},
          {'name':'OUT','type':'null','inputs':['union']}]
    h.build_module(root,spec,output='OUT');out=root.node('OUT')
    top=[{'id':'connection','groups':['a','b'],'require_closed':True}]
    contract={'parent':root.path(),'output':out.path(),'controller':ctrl.path(),'interfaces':[],
              'parts':[{'id':'a','group':'a','min_prims':1},{'id':'b','group':'b','min_prims':1}],
              'controls':[{'id':'move','parm':'offset','value':2,'expectations':[{'metric':'bounds_size','axis':0,'delta':[1.249,1.251]}]}],
              'topology':top}
    assert q._check_topology(out.geometry(),top)['status']=='pass'
    def test_move():
        return h.test_controls(ctrl,out,[{'id':'move','values':{'offset':2},'expectations':contract['controls'][0]['expectations']}],topology=top)
    # Bounds respond as requested, but the two selected surfaces disconnect.
    tested=test_move()
    result=tested['results'][0]
    assert tested['status']=='fail' and result['measurements'][0]['pass'] and result['restored'],tested
    assert result['topology']['results'][0]['surface_components']==2
    assert ctrl.evalParm('offset')==.75
    # Coincident/contacting boxes without fused point IDs are NOT shared topology.
    merge=root.createNode('merge','independent');merge.setInput(0,root.node('ga'));merge.setInput(1,root.node('gb'))
    for offset in (.75,1,2):
        ctrl.parm('offset').set(offset)
        assert q._check_topology(merge.geometry(),top)['status']=='fail'
    ctrl.parm('offset').set(.75)
    geo=hou.Geometry(out.geometry());missing=copy.deepcopy(top);missing[0]['groups'][1]='missing'
    assert q._check_topology(geo,missing)['status']=='fail'
    overlapping=geo.createPrimGroup('all');overlapping.add(geo.prims())
    assert q._check_topology(geo,[{'id':'bad','groups':['a','all']}])['results'][0]['reason']=='overlapping_part_groups_cannot_self_validate'
    # Open surface and inconsistent orientation must not become a fused-solid pass.
    cut=hou.Geometry(out.geometry());cut.deletePrims([cut.prims()[0]],False)
    assert q._check_topology(cut,top)['status']=='fail'
    collapsed=hou.Geometry(out.geometry());pts=collapsed.prims()[0].points();pts[1].setPosition(pts[0].position())
    assert q._check_topology(collapsed,top)['status']=='fail'
    reverse=root.createNode('reverse','flipped');reverse.setInput(0,out);reverse.parm('group').set('0')
    assert q._check_topology(reverse.geometry(),top)['results'][0]['orientation_conflicts']>0
    tube=root.createNode('tube','native');tg=hou.Geometry(tube.geometry());tg.createPrimGroup('a').add(tg.prims())
    # Unsupported primitive representations remain unverified, not P-only topology.
    tg.merge(root.node('gb').geometry())
    assert q._check_topology(tg,top)['status']=='unverified'
    rejects(lambda:q.validate_topology([{'id':'x','groups':['a','a']}]),'distinct')
    assert q._check_topology(out.geometry(),[{'id':'x','groups':['a','unknown']}])['status']=='fail'

    # Same complete bgeo payload, only serialization time differs: same signature.
    payload=hjson.loads(out.geometry().data());later=copy.deepcopy(payload)
    for i in range(0,len(later),2):
        if later[i]=='info':later[i+1]['date']='2099-12-31 23:59:59'
    class Serialized:
        def __init__(self,value):self.value=value
        def data(self):return json.dumps(self.value,allow_nan=False).encode('utf-8')
    assert q._data_signature(Serialized(payload))==q._data_signature(Serialized(later))
    # Actual user attributes and native primitive shape ARE still compared.
    g=hou.Geometry(out.geometry());g.addAttrib(hou.attribType.Global,'date','initial')
    before=q._data_signature(g);g.setGlobalAttribValue('date','changed')
    assert q._data_signature(g)!=before
    before=q._data_signature(tube.geometry());tube.parm('rad1').set(.9)
    assert q._data_signature(tube.geometry())!=before
    tube.destroy()
    # A report error from restoration still blocks even if topology itself passed.
    restore=h._restore_parameters
    try:
        h._restore_parameters=lambda saved:restore(saved)+['injected failure']
        rejects(test_move,'restoration failed')
    finally:h._restore_parameters=restore
finally:root.destroy()
print('surface topology/representation/perturbed disconnect/full-payload restoration tests passed')
