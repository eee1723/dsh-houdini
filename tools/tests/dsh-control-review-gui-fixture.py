"""Self-owned GUI fixture for paired control captures; launched only by the runner.

Records real images, camera evidence and exact numeric/user-state restoration.
It never opens a user HIP and does not certify image semantics.
"""
from pathlib import Path
import json, os, sys, traceback
import hou, hdefereval
from hutil.Qt import QtCore
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(os.environ['DSH_CONTROL_REVIEW_GUI_DIR'])
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
def record(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def run():
    hip=OUT/'fixture.hip'
    try:
        import dsh_hou_helpers as h
        import dsh_quality_contracts as qc
        result={'version':hou.applicationVersionString(),'real_gui':hou.isUIAvailable(),'semantic_status':'unverified'}
        with h._execution_owner('capture-review','fixture'):
            root=h.tab_create('/obj','geo','__capture_review')
            ctrl=h.tab_create(root,'null','CTRL')
            h.create_spare_parms(ctrl,spec=[{'type':'float','name':'width','default':1.0}])
            box=h.tab_create(root,'box','body');h.set_parms(box,{'sizex':"ch('../CTRL/width')"})
            out=h.tab_create(root,'null','OUT_ASSET');h.connect(box,out,0)
            out.setDisplayFlag(True);out.setRenderFlag(True)
            root.setSelected(True,clear_all_selected=True)
            hou.setFrame(7)
            key=hou.Keyframe();key.setFrame(7);key.setValue(1);ctrl.parm('width').setKeyframe(key)
            key=hou.Keyframe();key.setFrame(14);key.setValue(1.4);ctrl.parm('width').setKeyframe(key)
            hou.hipFile.save(str(hip))
            tests=[{'id':'width','values':{'width':2.0},'expectations':[{'metric':'bounds_size','axis':0,'range':[.5,3],'delta':[.999,1.001]}]}]
            def state():
                out.cook(force=True)
                return {'width':ctrl.evalParm('width'),'keys':[k.asCode() for k in ctrl.parm('width').keyframes()],
                        'frame':hou.frame(),'hash':qc._data_signature(out.geometry()),
                        'selected':[n.path() for n in hou.selectedNodes()],
                        'display':root.isDisplayFlagSet(),'render':out.isRenderFlagSet()}
            baseline=state();result['baseline_state']=baseline
            original=h.render_view
            raw=[]
            def observe(*args,**kwargs):
                try:
                    r=original(*args,**kwargs)
                    raw.append({'kwargs':kwargs,'width':ctrl.evalParm('width'),'result':r})
                    record('raw-renders.json',raw)
                    return r
                except BaseException as e:
                    raw.append({'kwargs':kwargs,'width':ctrl.evalParm('width'),'error_type':type(e).__name__,'error':str(e),'evidence':getattr(e,'evidence',{})})
                    record('raw-renders.json',raw)
                    raise
            h.render_view=observe
            for label,extra in [('shared',{'view_bounds':[[-2,-2,-2],[2,2,2]]}),('baseline_lock',{})]:
                record('progress.json',{'phase':label,'version':result['version']})
                try:
                    value=h.test_controls(ctrl,out,tests,views=['front'],**extra)
                    result[label]={'returned':value}
                except BaseException as e:
                    result[label]={'exception':type(e).__name__,'error':str(e),'evidence':getattr(e,'evidence',{}),'traceback':traceback.format_exc()}
                result[label]['state_after']=state()
                result[label]['state_restored']=state()==baseline
                record('results.json',result)
            h.render_view=original
            result['raw_render_count']=len(raw)
            result['images']=[{'output':r['result'].get('output'),'exists':Path(r['result'].get('output','')).is_file(),
                              'semantic':r['result'].get('semantic_status')} for r in raw if 'result' in r]
            record('results.json',result)
            hou.hipFile.save(str(hip))
        QtCore.QTimer.singleShot(200,hou.qt.mainWindow().close)
    except BaseException:
        (OUT/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        try:hou.hipFile.save(str(hip))
        except Exception:pass
        QtCore.QTimer.singleShot(200,hou.qt.mainWindow().close)
hdefereval.executeDeferred(run)
