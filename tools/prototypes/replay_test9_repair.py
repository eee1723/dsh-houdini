"""Task-specific diagnostic replay, never shipped to the agent as a recipe.

Reuses the archived test9 artifact, reconnects its existing missing part ONLY in
disposable memory, then proves prior control results expire. Never saves HIP.
Usage: hython tools/prototypes/replay_test9_repair.py HIP NEW_REPORT.json
"""
from pathlib import Path
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'houdini/python3.11libs'),str(ROOT/'tools/prototypes')]
import hou
import dsh_hou_helpers as h
from delivery_audit import DeliveryAudit

source=Path(sys.argv[1]).resolve(strict=True)
report=Path(sys.argv[2]).resolve()
if report.exists() or report.suffix.lower()!='.json': raise ValueError('new JSON report required')
sha=hashlib.sha256(source.read_bytes()).hexdigest()
if sha!='2ec19787302b4a139277db223948a5c3aef3b02d5b7664d4db1425dbe527f28f':
    raise ValueError('expected frozen test9 bytes; do not run this replay on another asset')
if hou.isUIAvailable(): raise RuntimeError('disposable hython only')
hou.hipFile.load(source.as_posix(),suppress_save_prompt=True,ignore_load_warnings=True)
contract=json.loads((ROOT/'tools/prototypes/fixtures/test9-obligations.json').read_text(encoding='utf-8'))
audit=DeliveryAudit(contract)
def check(receipt,name):return next(r for r in receipt['checks'] if r['id']==name)
for case in contract['controls']:audit.test_control(case['id'])
before=audit.receipt()
assert check(before,'required-tread')['status']=='fail'
assert check(before,'hub-width-response')['status']=='fail'
assert check(before,'drive-offset-response')['status']=='fail'

# One ordinary local correction, not a rebuild or a generated algorithm.
h.connect('/obj/MTB/KNOBS_GRP','/obj/MTB/WHEEL_MERGE',index=5)
after=audit.receipt()
assert check(after,'required-tread')['status']=='pass'
assert check(after,'required-tread')['actual_prims']==1584  # 792 per wheel
assert check(after,'hub-width-response')['status']=='unverified'
assert check(after,'drive-offset-response')['status']=='unverified'
assert after['epoch']>before['epoch']
for case in contract['controls']:audit.test_control(case['id'])
rechecked=audit.receipt()
assert check(rechecked,'required-tread')['status']=='pass'
assert check(rechecked,'hub-width-response')['status']=='fail'
assert check(rechecked,'drive-offset-response')['status']=='fail'
assert not rechecked['ready_for_independent_review']
assert hashlib.sha256(source.read_bytes()).hexdigest()==sha
payload={'source':source.as_posix(),'source_sha256':sha,'file_unchanged':True,
         'houdini':hou.applicationVersionString(),'repair_scope':'one existing wire, disposable memory only',
         'before':before,'after_local_repair':after,'after_recheck':rechecked}
with report.open('x',encoding='utf-8') as f:json.dump(payload,f,ensure_ascii=False,indent=2)
print(json.dumps({'file_unchanged':True,'tread_final_prims':1584,'control_evidence_invalidated':True,
                  'still_partial':True,'report':report.as_posix()}))
