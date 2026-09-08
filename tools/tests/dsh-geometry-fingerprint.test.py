"""Group-directory order is incidental; selection, ordered members and geometry are not."""
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import hjson
import dsh_quality_contracts as q
import dsh_hou_helpers as h

root=hou.node('/obj').createNode('geo','__fingerprint')
try:
    box=root.createNode('box','source')
    g=box.geometry().freeze()
    for name,ids in [('upper',[0,1]),('lower',[2,3])]:
        g.createPrimGroup(name).add([g.prim(i) for i in ids])
    g.createPointGroup('ordered',is_ordered=True).add([g.point(i) for i in [3,1,2]])
    g.createPointGroup('ordinary').add([g.point(0)])
    g.createVertexGroup('corners').add([g.prim(0).vertices()[0]])
    g.createEdgeGroup('edge').add([g.findEdge(g.prim(0).points()[0],g.prim(0).points()[1])])
    payload=hjson.loads(g.data())
    canonical=q._canonical_geometry_payload(g.data())
    # Replay the complete real writer payload with only group records permuted.
    reordered=copy.deepcopy(payload)
    for i in range(0,len(reordered),2):
        if reordered[i].endswith('groups'):
            reordered[i+1].reverse()
        elif reordered[i]=='info':
            reordered[i+1]['date']='different export time'
            reordered[i+1]['group_summary']='same groups listed in a different order'
    assert q._canonical_geometry_payload(json.dumps(reordered))==canonical
    signature=q._data_signature(g)
    changed=hou.Geometry(g)
    changed.findPrimGroup('upper').remove(changed.prim(0))
    assert q._data_signature(changed)!=signature,'real group membership must remain visible'
    changed=hou.Geometry(g)
    ordered=changed.findPointGroup('ordered');ordered.clear()
    ordered.add([changed.point(i) for i in [2,1,3]])
    assert q._data_signature(changed)!=signature,'ordered group element order must not be sorted away'
    changed=hou.Geometry(g)
    changed.findPrimGroup('upper').destroy()
    changed.createPrimGroup('renamed').add([changed.prim(0),changed.prim(1)])
    assert q._data_signature(changed)!=signature,'group names matter'
    # User attributes coincidentally named like export headers remain protected.
    for name in ['date','group_summary']:
        changed=hou.Geometry(g);changed.addAttrib(hou.attribType.Global,name,'original')
        before=q._data_signature(changed);changed.setGlobalAttribValue(name,'changed')
        assert q._data_signature(changed)!=before,name
    changed=hou.Geometry(g);changed.point(0).setPosition((10,20,30))
    assert q._data_signature(changed)!=signature
    changed=hou.Geometry(g);changed.deletePrims([changed.prim(0)],False)
    assert q._data_signature(changed)!=signature
    native=root.createNode('sphere','native')
    original=q._data_signature(native.geometry());p=list(native.geometry().pointFloatAttribValues('P'))
    native.parm('radx').set(2)
    assert list(native.geometry().pointFloatAttribValues('P'))==p
    assert q._data_signature(native.geometry())!=original,'native intrinsic changes are not point changes'
    malformed=copy.deepcopy(payload);idx=malformed.index('primitivegroups')+1
    malformed[idx].append(copy.deepcopy(malformed[idx][0]))
    try:q._canonical_geometry_payload(json.dumps(malformed))
    except ValueError as e:assert 'group names' in str(e)
    else:raise AssertionError('duplicate group names must not be merged or discarded')
    malformed[idx]=['unknown group record']
    try:q._canonical_geometry_payload(json.dumps(malformed))
    except ValueError:pass
    else:raise AssertionError('unknown group schema must fail closed')

    # Real control-test restoration with recooked groups, no external HIP fixture.
    ctrl=root.createNode('null','CTRL')
    h.create_spare_parms(ctrl,spec=[{'type':'float','name':'length','default':1.}])
    box.parm('sizex').setExpression('ch("../CTRL/length")')
    tags=root.createNode('attribwrangle','tags');tags.setInput(0,box);tags.parm('class').set('primitive')
    tags.parm('snippet').set('setprimgroup(0, sprintf("piece_%d", @primnum), @primnum, 1);')
    result=h.test_controls(ctrl,tags,[{'id':'longer','values':{'length':2.},'expectations':[
        {'metric':'bounds_size','axis':0,'delta':[.999,1.001]}]}])
    assert result['ok'] and result['restored'],result
finally:
    root.destroy()
print('geometry fingerprint: group order/ordered members/user attributes/topology/native intrinsics passed on '+hou.applicationVersionString())
