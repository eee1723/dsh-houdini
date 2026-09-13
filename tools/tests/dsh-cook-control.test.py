"""Bounded risk rejection and Manual metadata behavior, no unsafe loops executed."""
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h
import dsh_quality_contracts as q
import dsh_cook_control as cook_control
from dsh_cook_control import validate_vex

for code in ['while(npoints(0)>0) removepoint(0,npoints(0)-1);',
             'while (nprimitives(0) > 0) { removeprim(0,0,1); }',
             'while(npoints(0)>0) { removepoint(0,0); /* break; */ }',
             'while(npoints(0)>0) { removepoint(0,0); removeprim(0,0,1); }',
             'while(npoints(0)>0) { break; } while(nprimitives(0)>0) removeprim(0,0,1);']:
    try:validate_vex(code)
    except (ValueError, RuntimeError) as error:
        assert 'unsafe VEX deletion loop' in str(error)
    else:raise AssertionError('unsafe deletion loop accepted')
validate_vex('for(int i=npoints(0)-1;i>=0;i--) removepoint(0,i);')
validate_vex('// while(npoints(0)>0) removepoint(0,0);\nfloat x=1;')
for source in [
        's@doc="while(npoints(0)>0) removepoint(0,0);";',
        "s@doc='while(npoints(0)>0) removepoint(0,0);';",
        '/* while(npoints(0)>0) removepoint(0,0); */ float x=1;',
        'while(npoints(0)>0) { removepoint(0,0); break; }',
        'while(npoints(0)>0) { break; } removepoint(0,0);',
        'while(npoints(0)>0) { return; } removepoint(0,0);',
        'while(npoints(0)>0) { if(@ptnum==0) break; removepoint(0,0); }',
        # Unknown control flow/function effects are not a termination proof.
        # These sources are classified only, NEVER compiled or executed.
        'while(npoints(0)>0) { for(int i=0;i<1;i++) { break; } removepoint(0,0); }',
        'while(npoints(0)>0) removepoint(0,custom_function());',
        '#if 0\nwhile(npoints(0)>0) removepoint(0,0);\n#endif',
]:
    validate_vex(source)
# Nested unknown control flow is scanned iteratively, not with repeated
# whole-body searches/slices. It is never executed or claimed to terminate.
validate_vex('while(npoints(0)>0) { removepoint(0,0); ' * 1000 + 'break;' + '}' * 1000)
assert '_cook_node' not in b._VERBS, 'private batch implementation must not be a verb'

# One dependency traversal per explicit batch, without a hidden 512-node cap.
# Mutable fixture graphs also prove that a later source/connection change is
# checked afresh; no validation state survives a call.
class DependencyNode:
    visits = 0
    def __init__(self, identity, inputs=(), snippet=None):
        self.identity, self.sources, self.snippet = identity, inputs, snippet
    def sessionId(self):return self.identity
    def type(self):return self
    def name(self):return 'attribwrangle' if self.snippet is not None else 'null'
    def parm(self, name):return self if name == 'snippet' else None
    def keyframes(self):return ()
    def unexpandedString(self):return self.snippet
    def inputs(self):
        DependencyNode.visits += 1
        return self.sources

dependencies=[]
for identity in range(513):
    dependencies.append(DependencyNode(identity,dependencies[-1:] if dependencies else ()))
cook_control.preflight(dependencies)
assert DependencyNode.visits==513,DependencyNode.visits
cycle_a, cycle_b = DependencyNode(600), DependencyNode(601)
cycle_a.sources, cycle_b.sources = [cycle_b], [cycle_a]
DependencyNode.visits = 0
cook_control.preflight([cycle_a,cycle_b])
assert DependencyNode.visits==2,DependencyNode.visits
bad=DependencyNode(514,snippet='f@value=1;')
cook_control.preflight([bad])
bad.snippet='while(npoints(0)>0) removepoint(0,0);'
for roots in ([bad], [DependencyNode(515,[bad])]):
    try:cook_control.preflight(roots)
    except ValueError as error:assert 'unsafe VEX deletion loop' in str(error)
    else:raise AssertionError('later source/connection change reused earlier validation')

# Native hython coerces OnMouseUp to AutoUpdate on both supported versions.
# Never let an unsupported request accidentally leave an existing Manual mode.
assert not hou.isUIAvailable(), 'run this regression in isolated hython'
original_mode=hou.updateModeSetting()
native_set_mode=hou.setUpdateMode
try:
    for before, name in ((hou.updateMode.AutoUpdate,'auto'),(hou.updateMode.Manual,'manual')):
        native_set_mode(before)
        with patch.object(hou,'setUpdateMode',wraps=native_set_mode) as writes:
            try:h.set_update_mode('on_mouse_up',name)
            except ValueError as error:assert 'unsupported' in str(error).lower(),error
            else:raise AssertionError('headless OnMouseUp was accepted')
        assert writes.call_count==0 and hou.updateModeSetting()==before
    for name, native in (('auto',hou.updateMode.AutoUpdate),('manual',hou.updateMode.Manual)):
        current=h.scene_info()['update_mode']
        changed=h.set_update_mode(name,current)
        assert changed['before']==current and changed['after']==h.scene_info()['update_mode']==name,changed
        assert changed['changed']==(current!=name) and hou.updateModeSetting()==native,changed
        unchanged=h.set_update_mode(name,name)
        assert unchanged['after']==name and unchanged['changed'] is False,unchanged
    # Exercise the GUI readback-mismatch branch using real hython coercion.
    # Patching the availability flag is not a claim of native GUI validation.
    native_set_mode(hou.updateMode.Manual)
    with patch.object(hou,'isUIAvailable',return_value=True), \
         patch.object(hou,'setUpdateMode',wraps=native_set_mode) as writes:
        try:h.set_update_mode('on_mouse_up','manual')
        except RuntimeError as error:
            assert 'readback=auto' in str(error) and 'previous_mode_restored=True' in str(error),error
            assert 'side effects' in str(error),error
        else:raise AssertionError('unapplied GUI update mode was reported successful')
    assert [call.args[0] for call in writes.call_args_list]==[hou.updateMode.OnMouseUp,hou.updateMode.Manual]
    assert hou.updateModeSetting()==hou.updateMode.Manual
    def write_then_fail(mode):
        native_set_mode(mode)
        if mode==hou.updateMode.AutoUpdate:raise RuntimeError('injected after native write')
    with patch.object(hou,'setUpdateMode',side_effect=write_then_fail):
        try:h.set_update_mode('auto','manual')
        except RuntimeError as error:
            assert 'injected after native write' in str(error) and 'previous_mode_restored=True' in str(error),error
        else:raise AssertionError('partial setter failure was ignored')
    assert hou.updateModeSetting()==hou.updateMode.Manual
    def refuse_restore(mode):
        if mode==hou.updateMode.Manual:raise RuntimeError('injected restore refusal')
        native_set_mode(mode)
    with patch.object(hou,'isUIAvailable',return_value=True), \
         patch.object(hou,'setUpdateMode',side_effect=refuse_restore):
        try:h.set_update_mode('on_mouse_up','manual')
        except RuntimeError as error:
            assert 'previous_mode_restored=False' in str(error) and 'current_mode=auto' in str(error),error
            assert 'injected restore refusal' in str(error),error
        else:raise AssertionError('failed update-mode restoration was certified')
    assert hou.updateModeSetting()==hou.updateMode.AutoUpdate
finally:
    native_set_mode(original_mode)
with h._execution_owner('cook-test','setup'):
    g=h.tab_create('/obj','geo',name='cook_test')
    n=h.tab_create(g,'box')
    w=h.tab_create(g,'attribwrangle')
    h.set_update_mode('manual','auto')
    assert h.scene_info()['update_mode']=='manual'
    assert h.describe(n)['geometry_status']=='not_evaluated_manual'
    assert h.cook_node(n)['status']=='not_cooked_manual'
    # Geometry consumers must not cook implicitly or label unknown as empty.
    count=n.cookCount()
    report=h.verify_network(g,output=n,require_valid=False)
    assert report['status']=='not_evaluated_manual' and report['nonempty'] is None,report
    assert report['geometry'] is None and report['output_fingerprint'] is None,report
    assert report['failure_reasons']==['not_evaluated_manual'],report
    assert n.cookCount()==count and hou.updateModeSetting()==hou.updateMode.Manual
    try:h.verify_network(g,output=n)
    except h.CheckpointError as error:assert error.evidence['status']=='not_evaluated_manual'
    else:raise AssertionError('Manual verification was certified')
    for operation in (lambda:h.geo_attrib_stats(n,'P'), lambda:h.geo_piece_stats(n),
                      lambda:h.geo_frame_diff(n,1,2), lambda:h.geo_point_spacing(n,1,.1)):
        try:operation()
        except ValueError as error:assert 'Manual' in str(error),error
        else:raise AssertionError('Manual geometry was evaluated')
    children=tuple(g.children())
    spec=[{'name':'manual_module','type':'box'}]
    assert h.build_module(g,spec,output='manual_module',dry_run=True)['dry_run']
    try:h.build_module(g,spec,output='manual_module')
    except ValueError as error:assert 'Manual' in str(error),error
    else:raise AssertionError('Manual build started modifying the scene')
    assert tuple(g.children())==children and n.cookCount()==count
    interface={'id':'manual','source_group':'port','target_group':'surface',
               'max_distance':.01,'expected_points':1}
    controls=[{'id':'size','values':{'sizex':2},
               'expectations':[{'metric':'bounds_size','axis':0,'delta':[.9,1.1]}]}]
    value=n.evalParm('sizex');frame=hou.frame()
    for operation in (lambda:h.geo_check_interfaces(n,[interface]),
                      lambda:h.test_controls(n,n,controls),
                      lambda:h.camera_fit('/obj/not_created_camera',n),
                      lambda:h.render_frame('/out/not_created_rop'),
                      lambda:h.render_view(n)):
        with patch.object(hou,'isUIAvailable',return_value=True):
            try:operation()
            except ValueError as error:assert 'Manual' in str(error),error
            else:raise AssertionError('Manual operation was evaluated')
    assert n.evalParm('sizex')==value and hou.frame()==frame and n.cookCount()==count
    for code in (f'__result__=verify_network({g.path()!r},output={n.path()!r},require_valid=False)',
                 f'__result__=cook_node({n.path()!r})'):
        result=b.run_code(code,owner_session='cook-test')
        assert result['ok'] and result['result']['ok'] is False,result
        assert result['verbs'][-1]['check_status']=='unverified',result
    before=w.parm('snippet').unexpandedString()
    try:h.set_parms(w,{'snippet':'while(npoints(0)>0) removepoint(0,0);'})
    except (ValueError, RuntimeError) as error:
        assert 'unsafe VEX deletion loop' in str(error)
    else:raise AssertionError('unsafe source written')
    assert w.parm('snippet').unexpandedString()==before
    r=b.run_code("set_update_mode('auto','manual')",owner_session='cook-test',read_only=True)
    assert not r['ok'] and hou.updateModeSetting()==hou.updateMode.Manual
    h.set_update_mode('auto','manual')
    h.connect(n,w)
    h.set_parms(w,{'snippet':'s@doc="while(npoints(0)>0) removepoint(0,0);";'})
    assert h.cook_node(w)['ok']
    assert w.geometry().pointStringAttribValues('doc')==('while(npoints(0)>0) removepoint(0,0);',)*8
    for safe_source in ('while(npoints(0)>0) { removepoint(0,0); break; }',
                        'while(npoints(0)>0) { break; } removepoint(0,0);'):
        h.set_parms(w,{'snippet':safe_source})
        assert h.cook_node(w)['ok']
        assert w.geometry().intrinsicValue('pointcount')==7
    assert h.cook_node(n,timeout_ms=1000)['ok']
    assert h.verify_network(g,output=n,nodes=[n])['nonempty'] is True
    assert h.geo_attrib_stats(n,'P')['count']==8
    assert h.geo_piece_stats(n)['piece_count']==1
    assert h.geo_frame_diff(n,1,2)['max_delta']==0
    failure={'path':n.path(),'ok':False,'healthy':False,'warning_free':True,
             'errors':['injected interrupted cook'],'warnings':[]}
    # A successful control test reads baseline, perturbation and restored data.
    # A failed restoration cook must stop before the third geometry read: HOM
    # geometry() could otherwise retry the failed/interrupted computation.
    with patch.object(q,'_geometry',wraps=q._geometry) as geometry_reads:
        control_result=h.test_controls(n,n,controls)
    assert control_result['ok'] and control_result['restored'],control_result
    assert geometry_reads.call_count==3,geometry_reads.call_count
    state=(n.evalParm('sizex'),tuple(n.parm('sizex').keyframes()),hou.frame(),n.sessionId())
    real_cook=h.cook_node
    cook_calls=[]
    def fail_restoration(*args,**kwargs):
        cook_calls.append((args,kwargs))
        return real_cook(*args,**kwargs) if len(cook_calls)==1 else failure
    with patch.object(h,'cook_node',side_effect=fail_restoration), \
         patch.object(q,'_geometry',wraps=q._geometry) as geometry_reads:
        try:h.test_controls(n,n,controls)
        except h.CheckpointError as error:
            evidence=error.evidence
        else:raise AssertionError('failed restoration cook was certified')
    assert len(cook_calls)==2,cook_calls
    assert geometry_reads.call_count==2,('implicit retry after failed restoration cook',geometry_reads.call_count)
    assert evidence['restored'] is False and evidence['results'][0]['restored'] is False,evidence
    assert any('injected interrupted cook' in error for error in evidence['results'][0]['restore_errors']),evidence
    assert evidence['results'][0]['parameter_restore']['ok'],evidence
    assert (n.evalParm('sizex'),tuple(n.parm('sizex').keyframes()),hou.frame(),n.sessionId())==state
    with patch.object(h,'_cook_node',return_value=failure), \
         patch.object(hou.SopNode,'geometry',side_effect=AssertionError('implicit retry after failed cook')):
        failed=h.verify_network(g,output=n,nodes=[n],require_valid=False)
    assert failed['failure_reasons']==['cook_error'] and failed['nonempty'] is None,failed
    assert failed['output_fingerprint'] is None and failed['geometry_status']=='not_evaluated_cook_failed',failed
    with patch.object(hou.SopNode,'cook',side_effect=RuntimeError()):
        failed=h.cook_node(n)
    assert failed['ok'] is False and 'RuntimeError' in failed['errors'],failed
    with patch.object(cook_control,'preflight',side_effect=ValueError('injected preflight refusal')), \
         patch.object(hou.SopNode,'cook',side_effect=AssertionError('cook after preflight refusal')), \
         patch.object(hou.SopNode,'geometry',side_effect=AssertionError('geometry after preflight refusal')):
        for operation in (lambda:h.cook_node(n),lambda:h.verify_network(g,output=n)):
            try:operation()
            except ValueError as error:assert 'injected preflight refusal' in str(error),error
            else:raise AssertionError('preflight refusal was ignored')
    # Real nonempty SOP chain exceeds the old hidden upstream limit. Validate
    # every selected node, but inspect each dependency only once for this batch.
    large=g.createNode('subnet','large_dependency_scope')
    source=large.createNode('box')
    chain=[source]
    for index in range(513):
        child=large.createNode('null')
        child.setInput(0,chain[-1])
        chain.append(child)
    assert h.cook_node(chain[-1])['ok']
    with patch.object(cook_control,'preflight',wraps=cook_control.preflight) as scans:
        verified=h.verify_network(large,output=chain[-1],limit=1024)
    assert verified['ok'] and verified['node_count']==len(chain),verified
    assert scans.call_count==1,scans.call_count
    assert set(scans.call_args.args[0])==set(chain),scans.call_args
    g.destroy()
print('cook risk/Manual metadata/mode guard passed '+hou.applicationVersionString())
