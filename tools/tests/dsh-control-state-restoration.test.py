"""Channel/animation restoration, post-cook readback and later undo isolation."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as b

with h._execution_owner('state-restore-owner','setup'):
    root=h.tab_create('/obj','geo','__control_state_restore')
    ctrl=h.tab_create(root,'null','CTRL')
    h.create_spare_parms(ctrl,spec=[{'type':'float','name':'width','default':1},
        {'type':'int','name':'mode','default':3},{'type':'toggle','name':'visible','default':True}])
    h.build_module(root,[{'name':'surface','type':'box','parms':{'sizex':'ch("../CTRL/width")'}}],output='surface')
    out=root.node('surface')
    tests=[{'id':'width','values':{'width':2,'mode':5,'visible':0},
            'expectations':[{'metric':'bounds_size','axis':0,'delta':[.99,1.01]}]}]
    original_restore=h._restore_parameters
    original_cook=h.cook_node
    saved_frame=hou.frame()
    try:
        # Stable success across repeated tests, later ordinary edits and an
        # independent failed transaction. A final undo must not cross calls.
        def run(code):return b.run_code(code,owner_session='state-restore-owner')
        for _ in range(3):
            tested=run(f'__result__=test_controls({ctrl.path()!r},{out.path()!r},{tests!r})')
            assert tested['ok'] and tested['result']['parameter_restore']['ok'],tested
            actual={n:ctrl.evalParm(n) for n in ('width','mode','visible')}
            assert actual=={'width':1,'mode':3,'visible':1},actual
            failed=run(f'set_parm({out.path()!r},"ty",4)\nraise RuntimeError("later failure")')
            assert not failed['ok'] and failed['transaction']['status']=='rolled_back',failed
            assert {n:ctrl.evalParm(n) for n in actual}==actual and out.evalParm('ty')==0
        # Fault: a non-geometric control is omitted by the restore routine.
        def omit_mode(snapshots):
            return original_restore({k:v for k,v in snapshots.items() if k!='mode'})
        h._restore_parameters=omit_mode
        try:
            h.test_controls(ctrl,out,tests)
            raise AssertionError('same geometry must not certify channel restoration')
        except h.CheckpointError as error:
            row=error.evidence['results'][-1]
            assert row['restored'] is False and row['parameter_restore']['ok'] is False
            mode=next(c for c in row['parameter_restore']['channels'] if c['parameter'].endswith('/mode'))
            assert mode['expected_value']==3 and mode['actual_value']==5,mode
        finally:
            h._restore_parameters=original_restore
            h.set_parm(ctrl,'mode',3)
        # Fault occurs during the restoration cook, AFTER set-values returned.
        cooks=[]
        def late_change(node,*args,**kwargs):
            result=original_cook(node,*args,**kwargs);cooks.append(1)
            if len(cooks)==2:ctrl.parm('mode').set(7)
            return result
        h.cook_node=late_change
        try:
            h.test_controls(ctrl,out,tests)
            raise AssertionError('post-cook channel drift must fail')
        except h.CheckpointError as error:
            assert not error.evidence['results'][-1]['parameter_restore']['ok']
        finally:
            h.cook_node=original_cook
            h.set_parm(ctrl,'mode',3)
        # Preserve expressions and multiple keys; same evaluated value is not
        # enough if the animation was flattened during restoration.
        ctrl.parm('mode').setExpression('2+$F',hou.exprLanguage.Hscript)
        keys=ctrl.parm('mode').keyframes()
        r=h.test_controls(ctrl,out,tests)
        assert r['parameter_restore']['ok'] and ctrl.parm('mode').keyframes()==keys
        def flatten_mode(snapshots):
            errors=original_restore(snapshots)
            ctrl.parm('mode').deleteAllKeyframes();ctrl.parm('mode').set(3)
            return errors
        h._restore_parameters=flatten_mode
        try:
            h.test_controls(ctrl,out,tests)
            raise AssertionError('equal value with lost expression must fail')
        except h.CheckpointError as error:
            assert not error.evidence['results'][-1]['parameter_restore']['ok']
        finally:
            h._restore_parameters=original_restore
            ctrl.parm('mode').deleteAllKeyframes();ctrl.parm('mode').setKeyframes(keys)
        for frame,value in ((1,1),(24,4)):
            k=hou.Keyframe();k.setFrame(frame);k.setValue(value);ctrl.parm('width').setKeyframe(k)
        width_keys=ctrl.parm('width').keyframes()
        animated=h.test_controls(ctrl,out,tests)
        assert animated['restored'] and ctrl.parm('width').keyframes()==width_keys and hou.frame()==saved_frame
        # Long-lived OBJ controller: edit old fields and append a folder in the
        # same committed call, then fail a different dependent node's edit.
        # Read channels after every boundary rather than inferring from geometry.
        obj_ctrl=h.tab_create('/obj','null','__persistent_control_state')
        try:
            h.create_spare_parms(obj_ctrl,spec=[{'type':'float','name':'height','default':3},
                {'type':'float','name':'radius','default':2}])
            change=run(f'set_parms({obj_ctrl.path()!r},{{"height":4.25,"radius":2.75}})\n'
                f'create_spare_parms({obj_ctrl.path()!r},spec=[{{"type":"folder","name":"extra","parms":[{{"type":"int","name":"segments","default":8}}]}}])')
            assert change['ok'] and change['transaction']['status']=='committed',change
            expected={'height':4.25,'radius':2.75,'segments':8}
            def state():return {k:obj_ctrl.evalParm(k) for k in expected}
            assert state()==expected,state()
            h.set_parm(out,'ty',f'ch("{obj_ctrl.path()}/height")')
            for code in (f'set_parm({out.path()!r},"tx","not_a_function(1)")',
                         f'set_parm({out.path()!r},"tx",2)\nraise RuntimeError("later independent failure")'):
                failed=run(code)
                assert not failed['ok'] and failed['transaction']['status']=='rolled_back',failed
                assert state()==expected,state()
                h.cook_node(out,force=True)
                assert state()==expected and out.evalParm('ty')==expected['height']
        finally:
            h.set_parm(out,'ty',0)
            h.delete_node(obj_ctrl)
        # All normal Bridge boundaries still apply.
        denied=b.run_code(f'test_controls({ctrl.path()!r},{out.path()!r},{tests!r})',read_only=True)
        assert not denied['ok'] and 'read-only' in denied['error']
        foreign=b.run_code(f'test_controls({ctrl.path()!r},{out.path()!r},{tests!r})',owner_session='other')
        assert not foreign['ok'] and 'ownership guard' in foreign['error']
    finally:
        h._restore_parameters=original_restore;h.cook_node=original_cook
        hou.setFrame(saved_frame)
        h.delete_node(root)
print('exact control restoration, post-cook drift, expression/keys, independent rollback and ownership passed on '+hou.applicationVersionString())
