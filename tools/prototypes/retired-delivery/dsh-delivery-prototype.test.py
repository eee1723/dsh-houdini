"""Historical v8 vertical slice, excluded from the current test suite.

No task-specific bicycle recipe. Runs from any cwd using installed H21/H22 hython.
"""
from pathlib import Path
import copy
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'houdini/python3.11libs'),str(ROOT/'tools/prototypes')]
import hou
import dsh_hou_helpers as h
from delivery_audit import DeliveryAudit

def row(receipt, name):
    return next(r for r in receipt['checks'] if r['id']==name)

def rejects(fn, message):
    try: fn()
    except Exception as e:
        assert message in str(e),str(e)
    else: raise AssertionError('expected rejection')

root = hou.node('/obj').createNode('geo','__delivery_prototype')
try:
    ctrl = root.createNode('null','CONTROL')
    h.create_spare_parms(ctrl,spec=[{'name':'length','type':'float','default':1},
                                  {'name':'height','type':'float','default':1}])
    specs = [
        {'name':'part_a','type':'box','parms':{'sizex':"ch('../CONTROL/length')",'tx':"ch('../CONTROL/length')/2"}},
        {'name':'port_a','type':'attribwrangle','inputs':['part_a'],'parms':{'class':'point',
            'snippet':'if(@P.x>0.0001) setpointgroup(0,"a_port",@ptnum,1);'}},
        {'name':'tag_a','type':'attribwrangle','inputs':['port_a'],'parms':{'class':'primitive',
            'snippet':'setprimgroup(0,"a",@primnum,1);'}},
        {'name':'part_b','type':'box','parms':{'tx':"ch('../CONTROL/length')+0.5"}},
        {'name':'tag_b','type':'attribwrangle','inputs':['part_b'],'parms':{'class':'primitive',
            'snippet':'setprimgroup(0,"b",@primnum,1);'}},
        {'name':'assembly','type':'merge','inputs':['tag_a','tag_b']},
        {'name':'OUT','type':'null','inputs':['assembly']},
    ]
    h.build_module(root,specs,output='OUT')
    contract = {'parent':root.path(),'output':root.node('OUT').path(),'controller':ctrl.path(),
        'parts':[{'id':'part-a','group':'a','min_prims':6},{'id':'part-b','group':'b','min_prims':6}],
        'controls':[{'id':'length-response','parm':'length','value':1.2,
                     'expectations':[{'group':'b','metric':'bounds_center','axis':0,'delta':[.199,.201]}]},
                    {'id':'height-response','parm':'height','value':2,
                     'expectations':[{'group':'b','metric':'bounds_size','axis':1,'delta':[.999,1.001]}]}],
        'interfaces':[{'id':'joint','source_group':'a_port','target_group':'b','expected_points':4,'max_distance':.001}]}
    audit = DeliveryAudit(contract)
    first = audit.receipt()
    assert first['status']=='unverified',first
    assert row(first,'part-b')['status']=='pass' and row(first,'joint')['status']=='pass'
    assert audit.test_control('length-response')['status']=='pass'
    assert audit.test_control('height-response')['status']=='fail'  # real dead control
    failed = audit.receipt()
    assert failed['status']=='fail' and ctrl.evalParm('height')==1,failed
    # Local correction uses existing verbs + native Box, not a bigger prompt.
    h.set_parm(root.node('part_b'),'sizey',"ch('../CONTROL/height')")
    invalidated = audit.receipt()
    assert invalidated['epoch']>failed['epoch'],invalidated
    assert row(invalidated,'length-response')['status']=='unverified'
    assert set(invalidated['invalidated_control_cases'])=={'length-response','height-response'}
    for name in ['length-response','height-response']: assert audit.test_control(name)['status']=='pass'
    passed = audit.receipt()
    assert passed['status']=='pass' and passed['ready_for_independent_review'],passed
    assert passed['semantic_status']=='unverified' and passed['delivery_status']!='complete'
    assert audit.receipt()['epoch']==passed['epoch']  # no false invalidation on unchanged reads
    # A failed observer must not leave older passes reusable after a retry.
    original_snapshot=audit._snapshot
    snapshot_count=[0]
    def fail_after_test():
        snapshot_count[0]+=1
        if snapshot_count[0]==2:raise ValueError('injected post-test observation failure')
        return original_snapshot()
    audit._snapshot=fail_after_test
    try:rejects(lambda:audit.test_control('length-response'),'injected')
    finally:audit._snapshot=original_snapshot
    assert row(audit.receipt(),'length-response')['status']=='unverified'
    for name in ['length-response','height-response']:audit.test_control(name)
    # A caller cannot turn an old returned row into trusted evidence.
    returned_contract = audit.contract; returned_contract['parts']=[]
    assert audit.contract['parts']==contract['parts']
    # Module exists and cooks, but is absent from final OUT after disconnection.
    h.disconnect_input(root.node('assembly'),index=1)
    missing = audit.receipt()
    assert row(missing,'part-b')['status']=='fail',missing
    assert root.node('tag_b').geometry().intrinsicValue('primitivecount')==6
    assert row(missing,'length-response')['status']=='unverified'
    h.connect(root.node('tag_b'),root.node('assembly'),index=1)
    restored = audit.receipt()
    assert row(restored,'part-b')['status']=='pass'
    assert row(restored,'length-response')['status']=='unverified'  # old pass not resurrected
    # Present, parallel, valid cook, but actual interface is detached.
    h.set_parm(root.node('part_b'),'ty',.3)
    detached = audit.receipt()
    assert row(detached,'joint')['status']=='fail'
    h.set_parm(root.node('part_b'),'ty',0)
    for name in ['length-response','height-response']: audit.test_control(name)
    assert audit.receipt()['status']=='pass'
    # Rewire between pre-existing, identical geometry sources: the graph change
    # must invalidate even though final geometry/parameters/node IDs do not change.
    clone=root.createNode('null','clone_b'); clone.setInput(0,root.node('tag_b'))
    for name in ['length-response','height-response']: audit.test_control(name)
    assert audit.receipt()['status']=='pass'
    h.connect(clone,root.node('assembly'),index=1)
    assert row(audit.receipt(),'length-response')['status']=='unverified'
    for name in ['length-response','height-response']: audit.test_control(name)
    # Byte-identical geometry is not enough: parameter expression changed, so tests invalidate.
    h.set_parm(root.node('part_b'),'tx',"ch('../CONTROL/length')+0.5+0")
    assert row(audit.receipt(),'length-response')['status']=='unverified'
    # New exposed control is automatically an uncovered obligation, not silently ignored.
    h.create_spare_parms(ctrl,spec=[{'name':'extra','type':'float','default':1}])
    assert row(audit.receipt(),'uncovered:extra')['status']=='unverified'
    for name in ['length-response','height-response']: audit.test_control(name)
    assert audit.receipt()['status']=='unverified'
    # A frozen contract cannot be weakened silently; fresh registration carries no old tests.
    replacement = DeliveryAudit(contract)
    assert row(replacement.receipt(),'length-response')['status']=='unverified'
    invalid = copy.deepcopy(contract); invalid['controls'][0]['value']=float('nan')
    rejects(lambda:DeliveryAudit(invalid),'finite')
    invalid = copy.deepcopy(contract); invalid['parts'][0]['min_prims']=0
    rejects(lambda:DeliveryAudit(invalid),'positive')
    invalid = copy.deepcopy(contract); invalid['parts'][0]['id']='joint'
    rejects(lambda:DeliveryAudit(invalid),'unique')
    invalid = copy.deepcopy(contract); invalid['parts'][0]['id']='network'
    rejects(lambda:DeliveryAudit(invalid),'reserved')
    invalid = copy.deepcopy(contract); invalid['parts'][0]['id']='uncovered:extra'
    rejects(lambda:DeliveryAudit(invalid),'reserved')
    rejects(lambda:audit.test_control('model-says-pass'),'unknown')
    # New node object at same path, same input/shape must also invalidate provenance.
    old_out=root.node('OUT'); old_out.destroy()
    new_out=root.createNode('null','OUT');new_out.setInput(0,root.node('assembly'))
    assert row(audit.receipt(),'length-response')['status']=='unverified'
    # Unsupported representation never looks like a successful numerical delivery.
    packed=root.createNode('pack','pack');packed.setInput(0,root.node('assembly'));new_out.setInput(0,packed)
    unsupported=audit.receipt()
    assert unsupported['status']=='unverified' and 'Polygon' in unsupported['reason'],unsupported
    new_out.destroy()
    assert not audit.receipt()['ready_for_independent_review']
finally:
    root.destroy()
print('delivery prototype: missing-part/dead-control/interface/local-repair/invalidation/coverage passed')
