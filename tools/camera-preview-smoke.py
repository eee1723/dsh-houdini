"""Launch ONLY in a disposable Houdini GUI: houdini waitforui this_script.py.

DSH_CAMERA_SMOKE_DIR must name a freshly allocated temporary directory. No live
bridge, source HIP, or user preference writes. Process exits when the test ends.
Uses production render_view; backend selection is not overridden by the fixture.
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
    def record(row):
        records.append(row)
        (output/'partial-results.json').write_text(json.dumps(records,indent=2),encoding='utf8')
    try:
        import dsh_hou_helpers as h
        assert hou.isUIAvailable()
        geo=hou.node('/obj').createNode('geo','framing_preview_asset')
        box=geo.createNode('box','OUT')
        hou.hipFile.save((output/'managed-preview-fixture.hip').as_posix())
        # A foreign visible sentinel proves proxy isolation and state recovery.
        sentinel=hou.node('/obj').createNode('geo','user_sentinel')
        other=sentinel.createNode('box');other.parm('tx').set(100)
        viewer=hou.ui.curDesktop().paneTabOfType(hou.paneTabType.SceneViewer)
        viewport=viewer.curViewport()
        scene_camera=hou.node('/obj').createNode('cam','viewport_state_guard')
        first_key=hou.Keyframe(7.0);first_key.setFrame(1)
        second_key=hou.Keyframe(9.0);second_key.setFrame(10)
        scene_camera.parm('tx').setKeyframes((first_key,second_key))
        camera_keys=tuple((key.frame(),key.value()) for key in scene_camera.parm('tx').keyframes())
        viewport.setCamera(scene_camera);viewport.lockCameraToView(True)
        hou.setFrame(37)
        before_frame=float(hou.frame())
        camera_matrix=tuple(scene_camera.worldTransform().asTuple())
        sentinel.setSelected(True,clear_all_selected=True)
        initial_selection=tuple(n.path() for n in hou.selectedNodes())
        initial_visibility={n.path():n.isDisplayFlagSet() for n in (geo,sentinel,scene_camera)}
        def assert_user_state():
            assert float(hou.frame())==before_frame
            assert tuple(n.path() for n in hou.selectedNodes())==initial_selection
            assert all(hou.node(p).isDisplayFlagSet()==v for p,v in initial_visibility.items())
            assert viewer.curViewport().camera()==scene_camera and viewer.curViewport().isCameraLockedToView()
            assert tuple((key.frame(),key.value()) for key in scene_camera.parm('tx').keyframes())==camera_keys
            assert tuple(scene_camera.worldTransform().asTuple())==camera_matrix
        for name,size,res,direction,projection in (
            ('cube_iso',(3.023,)*3,(640,360),'iso','perspective'),
            ('tall_portrait',(1,5,.7),(360,640),[1,.3,1],'perspective'),
            ('ortho_oblique',(4,.8,2),(640,360),'iso','orthographic')):
            (output/'progress.txt').write_text('rendering '+name,encoding='utf8')
            box.parmTuple('size').set(size)
            result=h.render_view(box,direction=direction,width=res[0],height=res[1],
                                 picture=str(output/(name+'.png')),projection=projection,
                                 frame=11,output_policy='explicit')
            record({'case':name,'result':result})
            assert result['ok'] and result['framing']['framing_status']=='passed',result
            assert result['user_state_restored'],result
            assert_user_state()
            pixels=result['check'];x0,y0,x1,y1=pixels['content_bbox']
            assert x0>=res[0]*.09-3 and x1<=res[0]*.91+3 and y0>=res[1]*.09-3 and y1<=res[1]*.91+3,pixels
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
                    focus_group='focus',isolate=isolated,framing='detail',
                    frame=11,output_policy='explicit')
                assert result['ok'] and result['framing']['depth_check']['ok'],result
                assert result['framing']['framing_status']=='intentional_crop',result
                assert result['pixels']==result['check'] and result['check']['nonblack_pct']>1
                matrix=hou.Matrix4(result['framing']['matrix']).inverted()
                geom=box.geometry() if isolated else merged.geometry()
                depths=[-(p.position()*matrix)[2] for p in geom.points()]
                assert min(depths)>=result['framing']['near'] and max(depths)<=result['framing']['far']
                assert result['user_state_restored'],result
                assert_user_state()
                record({'case':name,'actual_depth_range':[min(depths),max(depths)],'result':result})

        # Transparent and opaque controls share one immutable SOP output. The
        # real green backplates distinguish RGB blending from alpha metadata.
        alpha_geo=hou.node('/obj').createNode('geo','alpha_preview_controls')
        alpha_output=alpha_geo.createNode('merge','OUT')
        positions=[]
        def swatch(name,x,z,color,alpha,size=(1.3,1.3,.3)):
            shape=alpha_geo.createNode('box',name+'_shape')
            shape.parmTuple('size').set(size);shape.parmTuple('t').set((x,0,z))
            attrib=alpha_geo.createNode('attribwrangle',name);attrib.setInput(0,shape)
            attrib.parm('snippet').set('@Cd=set(%s);f@Alpha=%s;'%(','.join(map(str,color)),alpha))
            alpha_output.setNextInput(attrib)
        for name,x,alpha,backed in (
            ('alpha25_free',-3,.25,False),('alpha25_backed',-1,.25,True),
            ('alpha100_free',1,1,False),('alpha100_backed',3,1,True)):
            swatch(name,x,0,(1,0,1),alpha);positions.append((name,x))
            if backed:
                swatch(name+'_background',x,-.6,(0,1,0),1,size=(1.5,1.5,.1))
        alpha_output.setDisplayFlag(True);alpha_output.setRenderFlag(True)
        (output/'progress.txt').write_text('rendering alpha_controls',encoding='utf8')
        result=h.render_view(alpha_output,direction=[0,0,1],frame=11,width=960,height=300,
            picture=str(output/'alpha_controls.png'),projection='orthographic',output_policy='explicit')
        from hutil.Qt import QtGui
        image=QtGui.QImage(result['output'])
        assert not image.isNull() and (image.width(),image.height())==(960,300)
        camera=hou.node(result['camera']);orthowidth=camera.parm('orthowidth').eval()
        samples={}
        for name,x in positions:
            projected=hou.Vector3(x,0,0)*camera.worldTransform().inverted()
            px=round(960*(.5+projected[0]/orthowidth))
            py=round(300*(.5-projected[1]/(orthowidth*300/960)))
            color=image.pixelColor(px,py)
            samples[name]={'pixel':[px,py],'rgba':[color.red(),color.green(),color.blue(),color.alpha()]}
        record({'case':'alpha_controls','result':result,'samples':samples})
        assert result['ok'] and result['user_state_restored'],result
        assert_user_state()
        transparent=samples['alpha25_free']['rgba'];opaque=samples['alpha100_free']['rgba']
        assert 0<transparent[3]<opaque[3]-20 and opaque[3]>=250,samples
        assert min(transparent[0],transparent[2])>20,samples  # not a vanished transparent object
        blended=samples['alpha25_backed']['rgba'];solid=samples['alpha100_backed']['rgba']
        assert blended[1]>solid[1]+20 and min(blended[0],blended[2])>20,samples
        assert min(solid[0],solid[2])>solid[1]+20,samples

        root_pngs_before={item.name for item in output.glob('*.png')}
        managed_viewports=[]
        for index in range(6):
            viewport=h.viewport_screenshot(f'viewport_{index+1}.png',frame=12+index,
                                           clean=True,frame_target=box)
            assert viewport['ok'] and viewport['fresh'] and viewport['user_state_restored'],viewport
            assert float(hou.frame())==before_frame
            assert Path(viewport['path']).parent.parent==output/'dsh-visual-checks',viewport
            assert viewport['artifact']['output_policy']=='managed'
            assert viewer.curViewport().camera()==scene_camera and viewer.curViewport().isCameraLockedToView()
            assert tuple((key.frame(),key.value()) for key in scene_camera.parm('tx').keyframes())==camera_keys
            managed_viewports.append(viewport)
        assert len({item['path'] for item in managed_viewports})==6
        assert {item.name for item in output.glob('*.png')}==root_pngs_before
        record({'case':'managed_viewports','results':managed_viewports})
        explicit_screens=[]
        for extension in ('bmp','tga'):
            capture=h.viewport_screenshot(str(output/f'viewport_compat.{extension}'),frame=20,
                clean=True,frame_target=box,output_policy='explicit')
            assert capture['ok'] and capture['fresh'] and capture['user_state_restored'],capture
            assert capture['artifact']['output_policy']=='explicit'
            explicit_screens.append(capture)
        record({'case':'explicit_viewport_formats','results':explicit_screens})
        (output/'results.json').write_text(json.dumps({'ok':True,'version':hou.applicationVersionString(),
            'scope':'production render_view pixel framing, real alpha/backplate blending and user-state restoration; not new agent quality acceptance',
            'cases':records},indent=2),encoding='utf8')
        hou.exit(exit_code=0,suppress_save_prompt=True)
    except Exception:
        error=traceback.format_exc()
        (output/'error.txt').write_text(error,encoding='utf8')
        (output/'results.json').write_text(json.dumps({'ok':False,'version':hou.applicationVersionString(),
            'cases':records,'error':error},indent=2),encoding='utf8')
        hou.exit(exit_code=1,suppress_save_prompt=True)


hdefereval.executeDeferred(run)
