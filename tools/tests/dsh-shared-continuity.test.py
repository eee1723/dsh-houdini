"""Healthy legacy shared executors may assess continuity, never adopt/reload."""
from pathlib import Path
import sys,tempfile,uuid
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_scene_recovery as recovery
import dsh_executor_registry as registry

class Request:
    path='/recovery/assess'
    def _send(self,value,status=200):self.value=value;self.status=status

owner='shared-continuity'
r=b.run_code("g=tab_create('/obj','geo','owned');tab_create(g,'box','OUT')",owner_session=owner,owner_call='first')
assert r['ok'],r
recovery.task_target(owner)
body={'expected_contract':{'version':b._EXECUTION_CONTRACT_VERSION,'hash':b._VERB_CATALOG_HASH},
      'session_id':owner,'previous_executor':b._EXECUTOR_ID,'source_executors':[b._EXECUTOR_ID],
      'expected':{'scene_id':recovery.facts()['scene_id']}}
with patch.object(registry,'is_shared_executor',return_value=True),patch.object(registry,'active_registration',return_value=SimpleNamespace(workbench=False)):
    request=Request();b._Handler._recover(request,body)
    assert request.value['status']=='connected' and request.value['executor_id']==b._EXECUTOR_ID
    for change,action in [({'previous_executor':uuid.uuid4().hex},'assess'),({'expected':{'scene_id':uuid.uuid4().hex}},'assess'),({},'prepare'),({},'activate')]:
        request=Request();request.path='/recovery/'+action
        try:b._Handler._recover(request,{**body,**change})
        except (RuntimeError,ValueError):pass
        else:raise AssertionError('unsupported recovery or wrong identity was accepted')
    assert hou.node('/obj/owned/OUT') is not None
print('PASS shared same-runtime assessment, different executor/scene rejection and no prepare/activate '+hou.applicationVersionString())
