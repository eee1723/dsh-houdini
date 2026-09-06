"""Disposable H21/H22: bounded child testing, no delivery state or live scene."""
from pathlib import Path
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h
import dsh_quality_contracts as q

def rejects(fn,text):
    try:fn()
    except Exception as e:assert text in str(e),(text,str(e))
    else:raise AssertionError('expected rejection: '+text)

def request(action,owner='author',**values):
    return b.run_review({'owner_session':owner,'owner_call':'test','request':{'action':action,**values}})['result']

with h._execution_owner('author','build'):
    root=h.tab_create('/obj','geo',name='__review_service')
    ctrl=h.tab_create(root,'null',name='CTRL')
    h.create_spare_parms(ctrl,spec=[{'name':'width','type':'float','default':1}, {'name':'dead','type':'float','default':1}])
    h.build_module(root,[{'name':'body','type':'box','parms':{'sizex':'ch("../CTRL/width")'}},
                         {'name':'OUT','type':'null','inputs':['body']}],output='OUT')
out=root.node('OUT')
scope={'parent':root.path(),'output':out.path(),'controller':ctrl.path()}
tests=[{'id':'width','values':{'width':2},'expectations':[{'metric':'bounds_size','axis':0,'delta':[.99,1.01]}]},
       {'id':'dead','values':{'dead':2}}]
try:
    rejects(lambda:request('begin','stranger',scope=scope),'ownership guard')
    token=request('begin',scope=scope)['token']
    rejects(lambda:request('begin',scope=scope),'another review')
    request('bind',token=token,child='reviewer')
    rejects(lambda:request('bind',token=token,child='different'),'exactly one')
    rejects(lambda:request('test','stranger',token=token,request={'tests':tests}),'different child')
    rejects(lambda:request('test','reviewer',token='fake',request={}),'absent or expired')
    rejects(lambda:b.run_code('set_parm("'+ctrl.path()+'","width",4)',owner_session='author',owner_call='edit'),'review is active')
    with h._execution_owner('reviewer','ordinary'):
        rejects(lambda:h.set_parm(ctrl,'width',9),'ownership guard')
    baseline=request('test','reviewer',token=token,request={})
    assert len(baseline['controls'])==2 and baseline['network']['healthy'],baseline
    result=request('test','reviewer',token=token,request={'tests':tests})
    assert result['cases'][0]['status']=='pass' and result['cases'][0]['restored'],result
    assert result['cases'][1]['response_status']=='unchanged' and result['cases'][1]['status']=='unverified',result
    assert ctrl.evalParm('width')==ctrl.evalParm('dead')==1
    assert h._REVIEW_PARAMETER_ACCESS is None
    with h._execution_owner('author','provenance'):
        assert h.node_provenance(ctrl)['status']=='owned_current_session'
    # Independent response smoke is never silently upgraded to design correctness.
    result=request('test','reviewer',token=token,request={'tests':[{'id':'responsive','values':{'width':1.5}}]})
    assert result['cases'][0]['response_status']=='responsive' and result['status']=='unverified'
    rejects(lambda:request('test','reviewer',token=token,request={'tests':[{'id':'bad','values':{'tx':1}}]}),'numeric spare')
    rejects(lambda:request('test','reviewer',token=token,request={'owner':'author'}),'expected fields')
    # Capture runs on the perturbed state and returns after restoration, without
    # relying on a real GL context in deterministic headless tests.
    original_ui=hou.isUIAvailable;original_render=h.render_view;seen=[]
    try:
        hou.isUIAvailable=lambda:True
        def render(node,**kwargs):
            seen.append(ctrl.evalParm('width'))
            return {'ok':True,'picture':'fixture.png','user_state_restored':True,'framing':{'center':[0,0,0]}}
        h.render_view=render
        result=request('test','reviewer',token=token,request={'tests':[tests[0]],'views':['iso']})
        assert seen==[1,2] and ctrl.evalParm('width')==1 and result['cases'][0]['restored'],(seen,result)
        def failed_capture(node,**kwargs):
            if ctrl.evalParm('width')!=1:raise RuntimeError('injected capture failure')
            return render(node,**kwargs)
        h.render_view=failed_capture
        failed=request('test','reviewer',token=token,request={'tests':[tests[0]],'views':['iso']})
        assert failed['cases'][0]['status']=='fail' and failed['cases'][0]['restored'] and ctrl.evalParm('width')==1,failed
    finally:hou.isUIAvailable=original_ui;h.render_view=original_render
    request('end',token=token)
    rejects(lambda:request('test','reviewer',token=token,request={'tests':tests}),'absent or expired')
    assert not b._review_busy
    # A user change is not overwritten by review restoration.
    token=request('begin',scope=scope)['token'];request('bind',token=token,child='reviewer')
    ctrl.parm('width').set(1.25)
    rejects(lambda:request('test','reviewer',token=token,request={'tests':tests}),'changed outside')
    assert ctrl.evalParm('width')==1.25
    rejects(lambda:request('end',token=token),'changed outside')
    assert not b._review_busy
    ctrl.parm('width').set(1)
    # No VEX/Python/file/callback mutation experiments; normal authoring is not gated.
    node=root.createNode('python','unsafe')
    token=request('begin',scope=scope)['token'];request('bind',token=token,child='reviewer')
    unsupported=request('test','reviewer',token=token,request={'tests':tests})
    assert unsupported['status']=='unverified' and unsupported['parameter_writes']==0
    request('end',token=token);node.destroy()
    # Explicit restoration fault poisons further experiments and reaches parent.
    token=request('begin',scope=scope)['token'];request('bind',token=token,child='reviewer')
    restore=h._restore_parameters
    try:
        h._restore_parameters=lambda saved:restore(saved)+['injected restore fault']
        rejects(lambda:request('test','reviewer',token=token,request={'tests':[tests[0]]}),'restoration failed')
    finally:h._restore_parameters=restore
    rejects(lambda:request('test','reviewer',token=token,request={}),'previous restoration')
    rejects(lambda:request('end',token=token),'restoration failure')
    assert h._REVIEW_PARAMETER_ACCESS is None and not b._review_busy
    # A viewport restoration failure must escape the numeric finally and stop
    # the batch even when all numeric parameters have been restored correctly.
    token=request('begin',scope=scope)['token'];request('bind',token=token,child='reviewer')
    original_ui=hou.isUIAvailable;original_render=h.render_view
    try:
        hou.isUIAvailable=lambda:True
        h.render_view=lambda node,**kw:{'ok':True,'user_state_restored':ctrl.evalParm('width')==1}
        rejects(lambda:request('test','reviewer',token=token,request={'tests':[tests[0],tests[1]],'views':['iso']}),'restore user state')
        assert ctrl.evalParm('width')==1 and ctrl.evalParm('dead')==1
        rejects(lambda:request('test','reviewer',token=token,request={}),'previous restoration')
    finally:hou.isUIAvailable=original_ui;h.render_view=original_render
    rejects(lambda:request('end',token=token),'restoration failure')
    token=request('begin',scope=scope)['token'];request('bind',token=token,child='reviewer')
    b._review_service.lease['expires']=0
    rejects(lambda:request('test','reviewer',token=token,request={}),'absent or expired')
    assert request('end',token=token)['released'] and not b._review_busy
    with b._jobs_lock:b._jobs['fixture']={'status':'queued'}
    rejects(lambda:request('begin',scope=scope),'active jobs')
    with b._jobs_lock:b._jobs.clear()
    errors=[]
    def worker():
        try:request('begin',scope=scope)
        except Exception as e:errors.append(str(e))
    thread=threading.Thread(target=worker);thread.start();thread.join()
    assert errors and 'owning thread' in errors[0]
finally:
    b._review_service.lease=None;b._review_busy=False
    root.destroy()
print('review permission/batch/response/capture/restoration/drift/unsupported/main-thread regressions passed')
