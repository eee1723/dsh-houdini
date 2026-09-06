"""Historical v8 test; not a current production regression."""
from pathlib import Path
import copy
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_quality_contracts as q
from dsh_delivery import DeliveryAudit, type_admission

def rejects(fn, text):
    try:fn()
    except Exception as e:assert text in str(e),str(e)
    else:raise AssertionError('expected rejection: '+text)

root=hou.node('/obj').createNode('geo','__boolean_domain')
try:
    # Type discovery uses the exact runtime admission policy and creates nothing.
    before=set(root.children())
    card=h.node_info(root,'boolean')
    assert card['delivery']['eligible_type'] and 'INPUT' in card['usage_notes'][0],card
    assert not h.node_info(root,'attribwrangle')['delivery']['eligible_type']
    assert not type_admission('Sop','vendor::boolean::2.0')['eligible_type']
    assert set(root.children())==before
    dry=h.build_module(root,[{'name':'probe','type':'boolean'}],output='probe',dry_run=True)
    assert dry['delivery']['eligible_types'] and set(root.children())==before
    unsupported=h.build_module(root,[{'name':'probe','type':'attribwrangle'}],output='probe',dry_run=True)
    assert not unsupported['delivery']['eligible_types'] and set(root.children())==before
    ctrl=root.createNode('null','CTRL')
    h.create_spare_parms(ctrl,spec=[{'name':'width','type':'float','default':4},
                                   {'name':'height','type':'float','default':6},
                                   {'name':'thickness','type':'float','default':1}])
    specs=[
      {'name':'base','type':'box','parms':{'sizex':"ch('../CTRL/width')",'sizey':"ch('../CTRL/thickness')",'sizez':"ch('../CTRL/width')",'ty':"ch('../CTRL/thickness')/2"}},
      {'name':'vertical','type':'box','parms':{'sizex':"ch('../CTRL/thickness')",'sizey':"ch('../CTRL/height')",'sizez':"ch('../CTRL/width')",'tx':"(ch('../CTRL/width')-ch('../CTRL/thickness'))/2",'ty':"ch('../CTRL/height')/2"}},
      {'name':'base_group','type':'groupcreate','inputs':['base'],'parms':{'groupname':'base'}},
      {'name':'vertical_group','type':'groupcreate','inputs':['vertical'],'parms':{'groupname':'vertical'}},
      {'name':'join','type':'boolean','inputs':['base_group','vertical_group'],'parms':{'booleanop':'union'}},
      {'name':'OUT','type':'null','inputs':['join']}]
    built=h.build_module(root,specs,output='OUT')
    assert built['delivery']['eligible_types']
    out=root.node('OUT')
    domain=[{'id':'positive','left':'thickness','op':'gt','right':0},
            {'id':'below_width','left':'thickness','op':'lt','right':'width'},
            {'id':'below_height','left':'thickness','op':'lt','right':'height'}]
    contract={'parent':root.path(),'output':out.path(),'controller':ctrl.path(),
              'parts':[{'id':'base_part','group':'base','min_prims':1},{'id':'vertical_part','group':'vertical','min_prims':1}],
              'controls':[{'id':'w','parm':'width','value':6,'expectations':[{'metric':'bounds_size','axis':0,'delta':[1.99,2.01]}]},
                          {'id':'h','parm':'height','value':9,'expectations':[{'metric':'bounds_size','axis':1,'delta':[2.99,3.01]}]},
                          {'id':'t','parm':'thickness','value':1.5,'expectations':[{'group':'base','metric':'bounds_size','axis':1,'delta':[.49,.51]}]}],
              'interfaces':[],'domain':domain}
    audit=DeliveryAudit(contract)
    for case in ('w','h','t'):assert audit.test_control(case)['status']=='pass'
    passed=audit.receipt()
    assert passed['status']=='pass' and passed['semantic_status']=='unverified',passed
    # Same external edit as test10: don't accept old control evidence at a new baseline.
    ctrl.parm('width').set(7.6)
    changed=audit.receipt()
    assert changed['status']=='unverified' and set(changed['invalidated_control_cases'])=={'w','h','t'}
    # Topology and groups change when thickness swallows height, even with clean cook.
    ctrl.parm('thickness').set(7)
    invalid=audit.receipt()
    assert invalid['status']=='fail',invalid
    assert next(r for r in invalid['checks'] if r['id']=='below_height')['status']=='fail'
    assert next(r for r in invalid['checks'] if r['id']=='vertical_part')['actual_prims']==0
    assert not out.errors()
    ctrl.parm('width').set(4);ctrl.parm('thickness').set(1)
    assert audit.receipt()['status']=='unverified'  # returning to baseline doesn't resurrect pass
    # Invalid candidate, no writes: independent scalar comparison can reject early.
    invalid_contract=copy.deepcopy(contract);invalid_contract['controls'][2]['value']=7
    invalid_audit=DeliveryAudit(invalid_contract)
    rejected=invalid_audit.test_control('t')
    assert rejected['status']=='fail' and rejected['evidence']['results'][0]['parameter_writes']==0,rejected
    assert ctrl.evalParm('thickness')==1
    # The baseline domain itself fails before any test writes.
    ctrl.parm('thickness').set(7)
    rejected=invalid_audit.test_control('w')
    assert rejected['evidence']['parameter_writes']==0 and ctrl.evalParm('thickness')==7
    ctrl.parm('thickness').set(1)
    # A coupled expression requires actual post-write evaluation, not guessed overrides.
    ctrl.parm('height').setExpression("ch('width')+2",hou.exprLanguage.Hscript)
    coupling=[{'id':'coupled','left':'width','op':'lt','right':'height'}]
    test=[{'id':'grow','values':{'width':8},'expectations':[{'metric':'bounds_size','axis':0,'delta':[3.99,4.01]}]}]
    result=h.test_controls(ctrl,out,test,domain=coupling)
    assert result['ok'] and result['restored'],result
    assert ctrl.evalParm('width')==4 and ctrl.parm('height').expression()=="ch('width')+2"
    # Opposite coupling is invalid only after the candidate is applied; must restore.
    ctrl.parm('height').setExpression("10-ch('width')",hou.exprLanguage.Hscript)
    result=h.test_controls(ctrl,out,test,domain=coupling)
    assert not result['ok'] and result['restored'] and ctrl.evalParm('width')==4,result
    assert 'actual perturbed' in result['results'][0]['reason']
    ctrl.parm('height').deleteAllKeyframes();ctrl.parm('height').set(6)
    for op,left,right in [('le',1,1),('ge',1,1),('eq',1,1),('ne',1,2)]:
        assert q.domain_checks(ctrl,[{'id':'op','left':'thickness','op':op,'right':right}])[0]['status']=='pass'
    for bad in [None,{},[{'id':'x','left':'thickness','op':'exec','right':0}],
                [{'id':'x','left':'thickness','op':'lt','right':True}],
                [{'id':'x','left':'thickness','op':'lt','right':float('nan')}]]:
        try:q.validate_domain(bad)
        except ValueError:pass
        else:raise AssertionError('accepted malformed domain')
    rejects(lambda:DeliveryAudit({**contract,'domain':[domain[0],domain[0]]}),'unique')
    bad=copy.deepcopy(contract);bad['domain'][0]['id']='network'
    rejects(lambda:DeliveryAudit(bad),'reserved')
    bad=copy.deepcopy(contract);bad['domain'][0]['left']='../base/sizex'
    assert DeliveryAudit(bad).receipt()['status']=='unverified'
finally:root.destroy()
print('Boolean early admission/domain/changed baseline/coupled values/restoration passed')
