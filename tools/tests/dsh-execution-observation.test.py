"""Ordered runtime observations and bounded native dependency impact, without extra cooks."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as b
with h._execution_owner('observation-owner','setup'):
    root=h.tab_create('/obj','geo','__execution_observation')
    ctrl=h.tab_create(root,'null','CTRL')
    h.create_spare_parms(ctrl,spec=[{'type':'float','name':'width','default':1}])
    h.build_module(root,[{'name':'unit','type':'box','parms':{'sizex':'1+ch("../CTRL/width")'}},
                         {'name':'OUT','type':'null','inputs':['unit']},
                         {'name':'unrelated','type':'sphere'}],output='OUT')
try:
    def run(code,**options):
        return b.run_code(code,owner_session='observation-owner',**options)
    out=root.node('OUT');other=root.node('unrelated')
    reply=run(f'set_parm({ctrl.path()!r},"width",2)')
    assert reply['ok'],reply
    observation=reply['execution']
    ids={n['identity'] for n in observation['impact']['nodes']}
    assert out.sessionId() in ids and ctrl.sessionId() in ids,observation
    assert other.sessionId() not in ids,observation
    assert out.needsToCook(),'dependency observation must not cook geometry'
    assert observation['impact']['last_edit_ledger_index']==1
    query=run(f'read_parms({ctrl.path()!r},names=["width"])',read_only=True)
    assert query['execution']['runtime_id']==observation['runtime_id']
    assert query['execution']['sequence']>observation['sequence']
    assert not query['execution']['impact']['attempted'] and not query['execution']['impact']['nodes']
    assert query['transaction']['nodes'][0]['identity']==ctrl.sessionId()
    checked=run(f'verify_network({root.path()!r},output={out.path()!r})')
    assert checked['execution']['outputs'][0]['identity']==out.sessionId(),checked
    assert not checked['execution']['impact']['attempted']
    mixed=run(f'verify_network({root.path()!r},output={out.path()!r})\nset_parm({ctrl.path()!r},"width",3)')
    assert mixed['execution']['impact']['last_edit_ledger_index']==2
    invalid=run(f'set_parm({ctrl.path()!r},"width",4,unexpected=True)')
    assert invalid['transaction']['status']=='no_scene_change'
    assert invalid['execution']['impact']['nodes']==[]
    unit=root.node('unit');identity=unit.sessionId()
    deleted=run(f'delete_node({unit.path()!r})')
    assert any(n['identity']==identity and n['exists'] is False for n in deleted['transaction']['nodes'])
    assert out.sessionId() in {n['identity'] for n in deleted['execution']['impact']['nodes']}
    impact={'nodes':{},'global':False,'unavailable':False,'truncated':False}
    # Native graph traversal reaches a bounded limit, never silently claims completeness.
    class Many:
        def __init__(self,i):self.i=i
        def sessionId(self):return self.i
        def path(self):return '/test/'+str(self.i)
        def outputs(self):return [Many(self.i+1)] if self.i<300 else []
        def dependents(self,include_children=False):return []
    b._observe_impact([Many(1)],impact)
    assert len(impact['nodes'])==256 and impact['truncated']
    class Unavailable(Many):
        def outputs(self):raise RuntimeError('dependency provider unavailable')
    unavailable={'nodes':{},'global':False,'unavailable':False,'truncated':False}
    b._observe_impact([Unavailable(1)],unavailable)
    assert unavailable['unavailable'],'diagnostic lookup failure must be marked, not escape into operation failure'
finally:
    root.destroy()
print('execution observation: runtime/order, actual expression+wire dependency, unrelated branch, no cook, outputs, same-call edit and deletion passed on '+hou.applicationVersionString())
