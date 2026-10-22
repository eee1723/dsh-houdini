"""Channel/animation restoration, post-cook readback and later undo isolation."""

import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import dsh_errors
import dsh_ownership
import dsh_parameter_values
import hou
import dsh_node_operations
import dsh_hou_helpers as h
import dsh_bridge as b
import dsh_quality_contracts as q

with dsh_ownership.execution_owner('state-restore-owner','setup'):
    root=h.tab_create('/obj','geo','__control_state_restore')
    ctrl=h.tab_create(root,'null','CTRL')
    h.create_spare_parms(ctrl,spec=[{'type':'float','name':'width','default':1},
        {'type':'int','name':'mode','default':3},{'type':'toggle','name':'visible','default':True}])
    h.build_module(root,[{'name':'surface','type':'box','parms':{'sizex':'ch("../CTRL/width")'}}],output='surface')
    out=root.node('surface')
    tests=[{'id':'width','values':{'width':2,'mode':5,'visible':0},
            'expectations':[{'metric':'bounds_size','axis':0,'delta':[.99,1.01]}]}]
    empty=h.tab_create(root,'null','hidden_empty')
    visible=h.tab_create(root,'switch','visible_output',inputs=[empty,out],parms={'input':'ch("../CTRL/visible")'})
    hide_tests=[{'id':'hide','values':{'visible':0},'expectations':[
        {'metric':'point_count','delta':[-8,-8],'range':[0,8]},
        {'metric':'primitive_count','delta':[-6,-6],'range':[0,6]}]}]
    original_restore=dsh_parameter_values._restore_parameters
    original_cook=dsh_node_operations.cook_node
    saved_frame=hou.frame()
    try:
        # A visibility control's expected empty output is a measured zero,
        # while the same parameter/geometry restoration guarantee still holds.
        hidden=h.test_controls(ctrl,visible,hide_tests)
        assert hidden['ok'] and hidden['restored'] and ctrl.evalParm('visible')==1,hidden
        assert [m['measured'] for m in hidden['results'][0]['measurements']]==[0,0],hidden
        assert hidden['results'][0]['geometry_restore']['matches'] and hou.frame()==saved_frame
        h.set_parm(ctrl,'visible',0)
        try:
            shown=h.test_controls(ctrl,visible,[{'id':'show','values':{'visible':1},'expectations':[
                {'metric':'point_count','delta':[8,8],'range':[0,8]},
                {'metric':'primitive_count','delta':[6,6],'range':[0,6]}]}])
            assert shown['ok'] and shown['restored'] and ctrl.evalParm('visible')==0,shown
            assert visible.geometry().intrinsicValue('pointcount')==0
        finally:h.set_parm(ctrl,'visible',1)
        bounds_empty=h.test_controls(ctrl,visible,[{'id':'hide_bounds','values':{'visible':0},'expectations':[
            {'metric':'primitive_count','delta':[-6,-6]},
            {'metric':'bounds_size','axis':0,'delta':[-1,-1]}]}])
        assert not bounds_empty['ok'] and bounds_empty['restored'],bounds_empty
        assert 'empty' in bounds_empty['results'][0]['reason'] and ctrl.evalParm('visible')==1
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
        # A changed bgeo observation must identify the failing section even
        # when every controller channel and the frame were restored exactly.
        original_geometry=q.observation.geometry
        reads=[]
        def changed_restore_geometry(node,*args,**kwargs):
            resolved,geometry,scope=original_geometry(node,*args,**kwargs)
            reads.append(1)
            if len(reads)==3:
                changed=hou.Geometry(geometry)
                point=changed.points()[0]
                point.setPosition(point.position()+hou.Vector3(.25,0,0))
                return resolved,changed,scope
            return resolved,geometry,scope
        for measured_output,cases in ((out,tests),(visible,hide_tests)):
            reads.clear()
            q.observation.geometry=changed_restore_geometry
            try:
                h.test_controls(ctrl,measured_output,cases)
                raise AssertionError('different output bgeo must fail restoration')
            except dsh_errors.CheckpointError as error:
                row=error.evidence['results'][-1]
                assert row['status']=='pass' and row['parameter_restore']['ok'],row
                assert row['restored'] is False and row['geometry_restore']['matches'] is False,row
                assert row['geometry_restore']['differing_section_count']>0,row
                assert row['geometry_restore']['differing_sections'][0]['first_difference']['path'],row
                assert error.evidence['control_summary']['case_counts']=={'pass':0,'fail':1,'unverified':0,'not_run':0}
            finally:
                q.observation.geometry=original_geometry
        assert h.test_controls(ctrl,out,tests)['restored']
        def failed_baseline_cook(*args,**kwargs):
            return {'ok':False,'errors':['injected baseline failure']}
        dsh_node_operations.cook_node=failed_baseline_cook
        try:
            baseline_failure=h.test_controls(ctrl,out,tests)
            assert baseline_failure['status']=='fail' and baseline_failure['results']==[],baseline_failure
            assert baseline_failure['parameter_writes']==0 and baseline_failure['restored']
            assert b._operation_summary('test_controls',baseline_failure)['cook_errors']==['injected baseline failure']
            assert ctrl.evalParm('width')==1
        finally:
            dsh_node_operations.cook_node=original_cook
        def drifting_baseline_cook(node,*args,**kwargs):
            result=original_cook(node,*args,**kwargs)
            ctrl.parm('mode').set(7)
            return result
        dsh_node_operations.cook_node=drifting_baseline_cook
        try:
            h.test_controls(ctrl,out,tests)
            raise AssertionError('baseline cook channel drift must fail before perturbation')
        except dsh_errors.CheckpointError as error:
            assert error.evidence['parameter_writes']==0 and error.evidence['restored'] is False
            assert not error.evidence['parameter_restore']['ok']
        finally:
            dsh_node_operations.cook_node=original_cook
            h.set_parm(ctrl,'mode',3)
        # Fault: a non-geometric control is omitted by the restore routine.
        def omit_mode(snapshots):
            return original_restore({k:v for k,v in snapshots.items() if k!='mode'})
        dsh_parameter_values._restore_parameters=omit_mode
        try:
            h.test_controls(ctrl,out,tests)
            raise AssertionError('same geometry must not certify channel restoration')
        except dsh_errors.CheckpointError as error:
            row=error.evidence['results'][-1]
            assert row['restored'] is False and row['parameter_restore']['ok'] is False
            mode=next(c for c in row['parameter_restore']['channels'] if c['parameter'].endswith('/mode'))
            assert mode['expected_value']==3 and mode['actual_value']==5,mode
        finally:
            dsh_parameter_values._restore_parameters=original_restore
            h.set_parm(ctrl,'mode',3)
        # Fault occurs during the restoration cook, AFTER set-values returned.
        cooks=[]
        def late_change(node,*args,**kwargs):
            result=original_cook(node,*args,**kwargs);cooks.append(1)
            if len(cooks)==3:ctrl.parm('mode').set(7)
            return result
        dsh_node_operations.cook_node=late_change
        try:
            h.test_controls(ctrl,out,tests)
            raise AssertionError('post-cook channel drift must fail')
        except dsh_errors.CheckpointError as error:
            assert not error.evidence['results'][-1]['parameter_restore']['ok']
        finally:
            dsh_node_operations.cook_node=original_cook
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
        dsh_parameter_values._restore_parameters=flatten_mode
        try:
            h.test_controls(ctrl,out,tests)
            raise AssertionError('equal value with lost expression must fail')
        except dsh_errors.CheckpointError as error:
            assert not error.evidence['results'][-1]['parameter_restore']['ok']
        finally:
            dsh_parameter_values._restore_parameters=original_restore
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
                dsh_node_operations.cook_node(out,force=True)
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
        dsh_parameter_values._restore_parameters=original_restore;dsh_node_operations.cook_node=original_cook
        hou.setFrame(saved_frame)
        h.delete_node(root)
print('exact control restoration, post-cook drift, expression/keys, independent rollback and ownership passed on '+hou.applicationVersionString())
