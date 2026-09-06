"""Frozen test10 regression: reuse saved seven-node asset, never save source HIP.

Developer-only fixture, not a modeling recipe in agent guidance or packaged tools.
Usage: hython tools/prototypes/replay_test10_delivery.py ORIGINAL_HIP NEW_REPORT.json
"""
from pathlib import Path
import copy
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import hou
from dsh_delivery import DeliveryAudit, inspect_scope

source=Path(sys.argv[1]).resolve(strict=True);report=Path(sys.argv[2]).resolve()
if hou.isUIAvailable():raise RuntimeError('disposable hython only')
if report.exists() or report.suffix.lower()!='.json':raise ValueError('new JSON report required')
sha=hashlib.sha256(source.read_bytes()).hexdigest()
if sha!='9a487f344898a1ef1d1370392e6c4d6108ed1d414c9856005b3f45be9a464a40':
    raise ValueError('expected frozen test10 bytes; do not run on a changed scene')
hou.hipFile.load(source.as_posix(),suppress_save_prompt=True,ignore_load_warnings=True)
scope={'parent':'/obj/l_bracket','output':'/obj/l_bracket/OUT','controller':'/obj/l_bracket/CONTROLS'}
discovered=inspect_scope(**scope)
contract={**scope,'parts':[{'id':'base','group':'base','min_prims':1},{'id':'vertical','group':'vertical','min_prims':1}],
          'controls':[{'id':'width_case','parm':'width','value':8,'expectations':[{'metric':'bounds_size','axis':0,'delta':[.399,.401]}]},
                      {'id':'height_case','parm':'height','value':8,'expectations':[{'metric':'bounds_size','axis':1,'delta':[1.999,2.001]}]},
                      {'id':'thickness_case','parm':'thickness','value':1.5,'expectations':[{'group':'base','metric':'bounds_size','axis':1,'delta':[.499,.501]}]}],
          'interfaces':[],'domain':[{'id':'positive_t','left':'thickness','op':'gt','right':0},
                                   {'id':'thin_w','left':'thickness','op':'lt','right':'width'},
                                   {'id':'thin_h','left':'thickness','op':'lt','right':'height'}]}
audit=DeliveryAudit(contract)
for case in contract['controls']:assert audit.test_control(case['id'])['status']=='pass'
passed=audit.receipt()
assert passed['status']=='pass' and passed['semantic_status']=='unverified'
ctrl=hou.node(scope['controller']);before={p:ctrl.evalParm(p) for p in ['width','height','thickness']}
try:
    ctrl.parm('thickness').set(7)
    invalid=audit.receipt()
    assert invalid['status']=='fail'
    assert next(r for r in invalid['checks'] if r['id']=='vertical')['actual_prims']==0
    assert next(r for r in invalid['checks'] if r['id']=='thin_h')['status']=='fail'
finally:ctrl.parm('thickness').set(before['thickness'])
restored=audit.receipt()
assert restored['status']=='unverified'
for case in contract['controls']:assert audit.test_control(case['id'])['status']=='pass'
rechecked=audit.receipt();assert rechecked['status']=='pass'
bad=copy.deepcopy(contract);bad['controls'][2]['value']=7
preflight=DeliveryAudit(bad).test_control('thickness_case')
assert preflight['status']=='fail' and preflight['evidence']['results'][0]['parameter_writes']==0
assert all(ctrl.evalParm(p)==v for p,v in before.items())
assert hashlib.sha256(source.read_bytes()).hexdigest()==sha
result={'source':source.as_posix(),'sha256':sha,'source_unchanged':True,'houdini':hou.applicationVersionString(),
        'node_count':len(hou.node(scope['parent']).children()),'discovery':discovered,'contract':contract,
        'passed':passed,'invalid_actual_state':invalid,'restored_needs_retest':restored,
        'rechecked':rechecked,'invalid_candidate_preflight':preflight,
        'note':'Developer frozen-asset regression, not K3 autonomous adoption or artistic acceptance. No source save.'}
with report.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({'source_unchanged':True,'node_count':result['node_count'],'domain_failure_detected':True,
                  'invalid_candidate_writes':0,'restored_and_rechecked':True,'report':report.as_posix()}))
