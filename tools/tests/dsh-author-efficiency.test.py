"""Isolated real HOM regression for author failures and diagnostic completeness."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as b

def rejects(fn, message):
    try:fn()
    except Exception as e:assert message in str(e),(message,str(e))
    else:raise AssertionError('expected rejection: '+message)

with h._execution_owner('efficiency','setup'):
    root=h.tab_create('/obj','geo','__author_efficiency')
    source=h.tab_create(root,'box','source')
    ctrl=h.tab_create(root,'null','CTRL')
    h.create_spare_parms(ctrl,spec=[{'type':'toggle','name':'enabled','default':True}])
    switch=h.tab_create(root,'switch','choice',inputs=[source])
try:
    rejects(lambda:h.node_info('Sop','box'),'existing absolute network')
    rejects(lambda:h.node_info('/obj','box'),'existing geometry container')
    for code in ['node_info("box")','node_info(type_name="box")','node_info(type="box",context="sop")']:
        env=b.run_code(code,read_only=True)
        assert not env['ok'] and 'node_info(parent, type_name' in env['error'],env
        assert 'existing_geo' in env['error'] and 'houdini_exec' in env['error'],env
        assert env['transaction']['status']=='no_scene_change',env
    with h._execution_owner('efficiency','test'):
        h.set_parm(switch,'input','chi("../CTRL/enabled")')
        assert not h.cook_node(switch)['ok']
        h.set_parm(switch,'input','1-ch("../CTRL/enabled")')
        assert h.cook_node(switch)['ok'],switch.errors()
        card=h.node_info(root,'groupexpression')
        assert {'expressions','groupname1','snippet1'} <= {p['name'] for p in card['parameters']}
        spec=[{'name':'groups','type':'groupexpression','inputs':['source'],
               'parms':{'groupname2':'upper','snippet2':'@P.y>0','expressions':2,'grouptype':'point','groupname1':'lower','snippet1':'@P.y<0'}}]
        assert h.build_module(root,spec,output='groups',dry_run=True)['valid']
        assert root.node('groups') is None
        built=h.build_module(root,spec,output='groups')
        g=root.node('groups').geometry()
        assert len(g.findPointGroup('lower').points())==len(g.findPointGroup('upper').points())==4
        rejects(lambda:h.build_module(root,[{'name':'invalid','type':'groupexpression','inputs':['source'],
            'parms':{'expressions':1,'snippet2':'1'}}],output='invalid'), 'unknown parameter')
        assert root.node('invalid') is None
        before={n.sessionId() for n in root.children()}
        # Exercise build cleanup inside the real Bridge undo transaction, after
        # an earlier mutation. The compiler cause must survive cleanup.
        result=b.run_code(f'set_parm({source.path()!r},"sizex",3)\nbuild_module({root.path()!r},'
            '[{"name":"bad","type":"attribwrangle","inputs":["source"],"parms":{"snippet":"unknown_function_zz();"}}],output="bad")',
            owner_session='efficiency',owner_call='failure')
        assert not result['ok'] and 'unknown_function_zz' in result['error'] and 'cook_details' in result['error'],result
        assert {n.sessionId() for n in root.children()}==before
        assert source.evalParm('sizex')==1
        assert h.node_provenance(source)['status']=='owned_current_session'
        # Simulate a partial shelf/undo result that leaves one exact registered
        # creation alive. Existing and independently created nodes must survive.
        original_undo=hou.undos.performUndo
        residual=[]
        def partial_undo():
            node=root.node('new_before_failure')
            node_id=node.sessionId()
            original_undo()
            # A real HOM non-undoable creation stands in for the residual; the
            # journal records identity, so an unrelated same-name node is not
            # automatically eligible for cleanup.
            with hou.undos.disabler():
                n=root.createNode('null','residual')
                h._register_owned_node(n)
                residual.append(n.sessionId())
                root.createNode('null','user_node')
        try:
            hou.undos.performUndo=partial_undo
            reply=b.run_code(f'tab_create({root.path()!r},"null","new_before_failure")\nraise RuntimeError("fault")',
                owner_session='efficiency',owner_call='residual')
        finally:hou.undos.performUndo=original_undo
        assert not reply['ok'] and root.node('residual') is None and root.node('user_node') is not None,reply
        assert root.node('source')==source and h.node_provenance(source)['status']=='owned_current_session'
        assert reply['rollback']['removed_created_residuals']==[root.path()+'/residual']
        root.node('user_node').destroy()
        # A fresh wrapper uses the same nonempty module contract. No weakening
        # of empty output validation to accommodate controller creation.
        rejects(lambda:h.build_module(root,[{'name':'empty','type':'null'}],output='empty'),'empty_output')
        assert root.node('empty') is None
        h.set_parm(source,'sizex','1+ch("../CTRL/enabled")')
        result=h.test_controls(ctrl,source,[{'id':'toggle','values':{'enabled':0},
            'expectations':[{'metric':'bounds_size','axis':0,'delta':[-1.01,-.99]}]}])
        assert result['ok'] and result['restored'] and ctrl.evalParm('enabled')==1,result
        rejects(lambda:h.test_controls(ctrl,source,[{'id':'bad','values':{'enabled':2},
            'expectations':[{'metric':'bounds_size','axis':0,'delta':[.9,1.1]}]}]),'toggle needs')
        # Exercise the real headless Copy node route (no monkeypatched shelf).
        copied=h.tab_create(root,'copytopoints','copied',inputs=[source,source])
        assert copied.geometry().intrinsicValue('pointcount')>0
finally:root.destroy()
print('author multiparm/preflight/error-refresh/compiler-diagnostics/undo/toggle/headless regression passed')
