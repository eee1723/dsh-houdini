"""Explicit offline CLI; inspect a saved HIP with a predeclared delivery contract.

Usage: hython tools/prototypes/audit_saved_sop.py HIP CONTRACT --report REPORT
Optional --test-controls runs reversible tests only inside this disposable process.
Never saves the HIP, never connects to a live Bridge, and never applies repairs.
"""
from pathlib import Path
import argparse
import contextlib
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'houdini/python3.11libs'),str(ROOT/'tools/prototypes')]
import hou
from delivery_audit import DeliveryAudit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hip',type=Path)
    parser.add_argument('contract',type=Path)
    parser.add_argument('--report',required=True,type=Path)
    parser.add_argument('--test-controls',action='store_true')
    args = parser.parse_args()
    hip, contract_path, report_path = args.hip.resolve(strict=True), args.contract.resolve(strict=True), args.report.resolve()
    if report_path in (hip,contract_path) or report_path.suffix.lower() != '.json' or report_path.exists():
        parser.error('report must be a NEW .json file, never an existing artifact or source')
    if hou.isUIAvailable(): parser.error('disposable hython only')
    source_hash = hashlib.sha256(hip.read_bytes()).hexdigest()
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    with contextlib.redirect_stdout(sys.stderr):
        hou.hipFile.load(hip.as_posix(),suppress_save_prompt=True,ignore_load_warnings=True)
        audit = DeliveryAudit(contract)
        before = audit.receipt()
        if args.test_controls:
            for case in contract['controls']:
                audit.test_control(case['id'])  # restoration exceptions abort; never continue
        after = audit.receipt()
    unchanged = hashlib.sha256(hip.read_bytes()).hexdigest()==source_hash
    if not unchanged: raise RuntimeError('source file changed during audit; report invalid')
    report = {'schema':1,'prototype':True,'source':hip.as_posix(),'source_sha256':source_hash,
              'file_unchanged':unchanged,'contract_file':contract_path.as_posix(),
              'before':before,'after':after,'houdini':hou.applicationVersionString()}
    # Generated diagnostic artifact, not a production/file editing path.
    with report_path.open('x',encoding='utf-8') as handle:
        json.dump(report,handle,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({'report':report_path.as_posix(),'status':after['status'],
                      'source_unchanged':unchanged,'ready_for_independent_review':after['ready_for_independent_review']}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
