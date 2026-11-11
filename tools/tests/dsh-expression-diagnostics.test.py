"""Expression write/evaluation is distinct from cook/effect; zero is legitimate."""

import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import dsh_errors
import dsh_ownership
import hou
import dsh_hou_helpers as h
import dsh_bridge as b

with dsh_ownership.execution_owner('expression-owner','test'):
    root=h.tab_create('/obj','geo','__expression_diagnostics')
    box=h.tab_create(root,'box','shape')
    try:
        for expression,language in [('0','hscript'),('ch("ty")','hscript'),('0','python')]:
            r=h.set_parm(box,'tx',{'expression':expression,'language':language})
            assert r['value']==0 and r['evaluation']['status']=='evaluated' and r['effect_status']=='unverified',r
            assert r['language']==language and r['write_status']=='written'
        # The native evaluator reports many errors on the NODE, returning 0
        # rather than raising from Parm.eval(). The setter must retain that cause.
        for expression,language,reason in [('not_a_function(1)','hscript','Unknown function'),
            ('1 +','hscript','Expression stack'),('chf("ty")','hscript','Bad data type'),
            ('1/0','python','ZeroDivisionError'),('float("nan")','python','non-finite')]:
            old=box.parm('tx').keyframes()
            try:
                h.set_parm(box,'tx',{'expression':expression,'language':language})
                raise AssertionError('evaluation failure was accepted')
            except dsh_errors.CheckpointError as error:
                assert reason in str(error),(reason,str(error))
                assert error.evidence['parameter_state_restored'] and error.evidence['write_status']=='restored',error.evidence
                assert error.evidence['evaluation']['status']=='failed'
                assert error.evidence['failure_stage']=='evaluation'
            assert box.parm('tx').keyframes()==old
        # Missing-reference warnings are visible; forward references remain
        # possible and are never advertised as verified geometry.
        r=h.set_parm(box,'tx','ch("../missing/width")')
        assert r['value']==0 and r['evaluation']['status']=='warning' and r['evaluation']['warnings'],r
        read=h.read_parms(box,names=['tx'])[0]
        assert read['language']=='hscript' and read['evaluation']['status']=='warning',read
        h.set_parm(box,'tx','0')
        assert h.read_parms(box,names=['tx'])[0]['evaluation']['status']=='evaluated'
        # An unrelated node cook error must not be attributed to the new channel.
        invalid=h.tab_create(root,'xform','no_input')
        assert not h.cook_node(invalid,force=True)['ok']
        r=h.set_parm(invalid,'tx','0')
        assert r['value']==0 and not r['evaluation']['errors'],r
        # Diagnostics from a sibling tuple component must not fail this channel.
        sibling=h.tab_create(root,'box','sibling_diagnostics')
        sibling.parm('ty').setExpression('ch("../missing/height")',hou.exprLanguage.Hscript)
        sibling.parm('ty').eval()
        r=h.set_parm(sibling,'tx','0')
        assert r['value']==0 and not r['evaluation']['errors'],r
        assert r['effect_status']=='unverified' and 'sibling' in r['evaluation']['scope'],r
        sibling.parm('ty').setExpression('not_a_function(1)',hou.exprLanguage.Hscript)
        sibling.parm('ty').eval()
        r=h.set_parm(sibling,'tx','0')
        assert r['value']==0 and not r['evaluation']['errors'],r
        assert h.read_parms(sibling,names=['ty'])[0]['evaluation']['status']=='unverified'
        # Batch restores preceding literals AND original animation after failure.
        k=hou.Keyframe();k.setFrame(1);k.setValue(2);box.parm('ty').setKeyframe(k)
        k=hou.Keyframe();k.setFrame(10);k.setValue(4);box.parm('ty').setKeyframe(k)
        keys=box.parm('ty').keyframes()
        try:
            h.set_parms(box,{'ty':8,'tz':{'expression':'1/0','language':'python'}})
            raise AssertionError('bad batch accepted')
        except dsh_errors.CheckpointError as error:
            assert error.evidence['batch_parameter_state_restored'],error.evidence
        assert box.parm('ty').keyframes()==keys and box.evalParm('tz')==0

        # Strict batch results observe dependencies after all writes. They do
        # not evaluate the new expression once during writing and again later.
        batch=h.tab_create(root,'box','batch_dependencies')
        h.create_spare_parms(batch,spec=[{'type':'float','name':'follow','default':0.},
                                       {'type':'float','name':'driver','default':0.}])
        for values, expected in [({'follow':'ch("driver")','driver':7},7),
                                 ({'follow':'ch("sizex")','size':[3,4,5]},3)]:
            result=h.set_parms(batch,values)
            assert result['readback_timing']=='after_batch_writes',result
            assert result['set']['follow']==expected and result['evaluations']['follow']['value']==expected,result
        assert result['set']['size']==[3,4,5],result
        h.set_parms(batch,{'follow':0,'driver':0})
        hou.session.dsh_batch_expression_reads=0
        counted=("hou.session.dsh_batch_expression_reads += 1\n"
                 "return hou.pwd().evalParm('driver')")
        result=h.set_parms(batch,{'follow':{'expression':counted,'language':'python'},'driver':11})
        assert result['set']['follow']==11 and result['evaluations']['follow']['status']=='evaluated',result
        assert hou.session.dsh_batch_expression_reads==1,'batch must not explicitly evaluate the authored Python expression twice'
        h.set_parm(batch,'follow',0)
        del hou.session.dsh_batch_expression_reads
        # A direct setter still reports its own write-time value, and explicit
        # partial-success mode retains the same per-item evaluation boundary.
        h.set_parm(batch,'driver',0)
        single=h.set_parm(batch,'follow','ch("driver")')
        assert single['value']==0 and 'readback_timing' not in single,single
        partial=h.set_parms(batch,{'follow':'ch("driver")','driver':17},strict=False)
        assert partial['readback_timing']=='after_each_write' and partial['set']['follow']==0,partial
        assert batch.evalParm('follow')==17
        # A late evaluation error restores every written value and the original
        # channels, including tuple literals written after the bad expression.
        follow_keys=batch.parm('follow').keyframes()
        size_before=batch.parmTuple('size').eval()
        try:
            h.set_parms(batch,{'driver':19,'follow':{'expression':'1/0','language':'python'},'size':[9,9,9]})
            raise AssertionError('deferred expression error was accepted')
        except dsh_errors.CheckpointError as error:
            assert error.evidence['batch_parameter_state_restored'] and error.evidence['failure_stage']=='evaluation',error.evidence
        assert batch.evalParm('driver')==17 and batch.parm('follow').keyframes()==follow_keys
        assert batch.parmTuple('size').eval()==size_before

        native_set=hou.Parm.setExpression
        def refuse_write(p,*args,**kwargs):
            if p.path()==box.parm('tx').path():raise hou.OperationFailed('injected native write failure')
            return native_set(p,*args,**kwargs)
        old=box.parm('tx').keyframes()
        try:
            hou.Parm.setExpression=refuse_write
            try:h.set_parm(box,'tx','0');raise AssertionError('write failure expected')
            except dsh_errors.CheckpointError as error:
                assert error.evidence['failure_stage']=='write' and error.evidence['evaluation']['status']=='not_run'
                assert error.evidence['parameter_state_restored']
        finally:hou.Parm.setExpression=native_set
        assert box.parm('tx').keyframes()==old
        # A successful evaluation can still generate empty geometry; only the
        # explicit output checkpoint can judge that later stage.
        empty=h.tab_create(root,'null','empty')
        switch=h.tab_create(root,'switch','selector',inputs=[box,empty])
        r=h.set_parm(switch,'input','1')
        assert r['evaluation']['status']=='evaluated'
        assert h.cook_node(switch)['ok'] and len(switch.geometry().points())==0
        try:
            h.verify_network(root,output=switch,nodes=[switch])
            raise AssertionError('valid expression must not certify empty output')
        except dsh_errors.CheckpointError as error:
            assert 'empty_output' in str(error),str(error)
        h.set_parm(switch,'input','0')
        assert h.cook_node(switch)['ok']
        # Failed cook diagnostics may survive a corrected expression evaluation.
        switch.parm('input').setExpression('chi("missing")',hou.exprLanguage.Hscript)
        assert not h.cook_node(switch,force=True)['ok']
        corrected=h.set_parm(switch,'input','0')
        assert corrected['value']==0 and corrected['evaluation']['status']=='unverified',corrected
        assert h.cook_node(switch,force=True)['ok']
        assert h.read_parms(switch,names=['input'])[0]['evaluation']['status']=='evaluated'
        h.cook_node(box,force=True)
        h.set_parm(box,'tx','0')
        assert box.needsToCook(),'expression diagnostics must not cook the geometry'
        warning_values={'tx':'ch("../gone/width")'}
        warning=b.run_code(f'__result__=set_parms({box.path()!r},{warning_values!r})',owner_session='expression-owner')
        assert warning['ok'] and warning['checks'][0]['status']=='warning',warning
        assert warning['evidence'][0]['evaluations']['tx']['status']=='warning'
        h.set_parm(box,'tx','0')
        failed=b.run_code(f'set_parms({box.path()!r},{{"tx":3,"tz":{{"expression":"1/0","language":"python"}}}})',owner_session='expression-owner')
        assert not failed['ok'] and failed['transaction']['status']=='rolled_back',failed
        assert failed['evidence'][0]['evaluation']['language']=='python'
        assert failed['evidence'][0]['batch_parameter_state_restored']
        assert box.evalParm('tx')==0
        # Existing bad source can be inspected and represented in valid JSON.
        box.parm('tx').setExpression('float("nan")',hou.exprLanguage.Python)
        read=h.read_parms(box,names=['tx'])[0]
        assert read['evaluation']['status']=='failed' and read['value']=='nan',read
        json.dumps(read,allow_nan=False)
        h.set_parm(box,'tx',0)
        denied=b.run_code(f'set_parm({box.path()!r},"tx","0")',owner_session='foreign')
        assert not denied['ok'] and 'ownership guard' in denied['error']
        query=b.run_code(f'set_parm({box.path()!r},"tx","0")',read_only=True)
        assert not query['ok'] and 'read-only' in query['error']
    finally:
        h.delete_node(root)
print('expression zero/error/warning/language/readback/batch animation restoration/cook boundary/ownership passed on '+hou.applicationVersionString())
