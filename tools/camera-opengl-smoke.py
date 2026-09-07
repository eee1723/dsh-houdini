"""Launch ONLY in a disposable Houdini GUI: houdini waitforui this_script.py.

DSH_CAMERA_SMOKE_DIR must name a freshly allocated temporary directory. No live
bridge, source HIP, or user preference writes. Process exits when the test ends.
"""
import json
import os
from pathlib import Path
import sys
import traceback
import hou
import hdefereval

output=Path(os.environ['DSH_CAMERA_SMOKE_DIR'])
repo=Path(os.environ['DSH_CAMERA_SMOKE_REPO'])
sys.path.insert(0,str(repo/'houdini/python3.11libs'))


def run():
    records=[]
    try:
        import dsh_hou_helpers as h
        assert hou.isUIAvailable()
        geo=hou.node('/obj').createNode('geo','framing_preview_asset')
        box=geo.createNode('box','OUT')
        # A foreign visible sentinel proves proxy isolation and state recovery.
        sentinel=hou.node('/obj').createNode('geo','user_sentinel')
        other=sentinel.createNode('box');other.parm('tx').set(100)
        sentinel.setSelected(True,clear_all_selected=True)
        initial_selection=tuple(n.path() for n in hou.selectedNodes())
        initial_visibility={n.path():n.isDisplayFlagSet() for n in (geo,sentinel)}
        for name,size,res,direction,projection in (
            ('cube_iso',(3.023,)*3,(640,360),'iso','perspective'),
            ('tall_portrait',(1,5,.7),(360,640),[1,.3,1],'perspective'),
            ('ortho_oblique',(4,.8,2),(640,360),'iso','orthographic')):
            (output/'progress.txt').write_text('rendering '+name,encoding='utf8')
            box.parmTuple('size').set(size)
            result=h.render_view(box,direction=direction,width=res[0],height=res[1],
                                 picture=str(output/(name+'.png')),projection=projection)
            assert result['ok'] and result['framing']['framing_status']=='passed',result
            assert result['user_state_restored'],result
            assert tuple(n.path() for n in hou.selectedNodes())==initial_selection
            assert all(hou.node(p).isDisplayFlagSet()==v for p,v in initial_visibility.items())
            pixels=result['check'];x0,y0,x1,y1=pixels['content_bbox']
            assert x0>=res[0]*.09-3 and x1<=res[0]*.91+3 and y0>=res[1]*.09-3 and y1<=res[1]*.91+3,pixels
            records.append({'case':name,'result':result})
        # Oblique focus with foreground/background context: detail may crop XY,
        # but no rendered geometry may cross the camera's near or far plane.
        box.parmTuple('size').set((8,4,.8));box.parmTuple('t').set((0,3,0))
        tag=geo.createNode('groupcreate','focus_tag');tag.setInput(0,box);tag.parm('groupname').set('focus')
        context=geo.createNode('box','context');context.parmTuple('size').set((16,.5,8))
        merged=geo.createNode('merge','context_out');merged.setInput(0,tag);merged.setInput(1,context)
        for projection in ('orthographic','perspective'):
            for isolated in (False,True):
                name=f'detail_{projection}_{isolated}'
                (output/'progress.txt').write_text('rendering '+name,encoding='utf8')
                result=h.render_view(merged,direction=[1,.2,.25],width=640,height=360,
                    picture=str(output/(name+'.png')),projection=projection,
                    focus_group='focus',isolate=isolated,framing='detail')
                assert result['ok'] and result['framing']['depth_check']['ok'],result
                assert result['framing']['framing_status']=='intentional_crop',result
                assert result['pixels']==result['check'] and result['check']['nonblack_pct']>1
                matrix=hou.Matrix4(result['framing']['matrix']).inverted()
                geom=box.geometry() if isolated else merged.geometry()
                depths=[-(p.position()*matrix)[2] for p in geom.points()]
                assert min(depths)>=result['framing']['near'] and max(depths)<=result['framing']['far']
                assert result['user_state_restored'] and tuple(n.path() for n in hou.selectedNodes())==initial_selection
                assert all(hou.node(p).isDisplayFlagSet()==v for p,v in initial_visibility.items())
                records.append({'case':name,'actual_depth_range':[min(depths),max(depths)],'result':result})
        (output/'results.json').write_text(json.dumps({'ok':True,'version':hou.applicationVersionString(),
            'scope':'real GUI OpenGL pixel framing and user-state restoration; not new agent quality acceptance',
            'cases':records},indent=2),encoding='utf8')
        hou.exit(exit_code=0,suppress_save_prompt=True)
    except Exception:
        (output/'error.txt').write_text(traceback.format_exc(),encoding='utf8')
        hou.exit(exit_code=1,suppress_save_prompt=True)


hdefereval.executeDeferred(run)
