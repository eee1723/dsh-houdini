"""Real HOM camera geometry assertions. No live HIP and no renderer required."""

import math
import json
import os
import pathlib
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import dsh_errors
import dsh_ownership
import dsh_service_constants
import hou
import dsh_hou_helpers as h
import dsh_bridge as bridge
import dsh_camera_framing as f
import dsh_usd_inspection as usd


def rejected(fn, needle):
    try: fn()
    except (ValueError, PermissionError, dsh_errors.CheckpointError) as exc:
        assert needle in str(exc), str(exc)
    else: raise AssertionError('expected rejection: '+needle)


points = f.corners([[-1.5115]*3,[1.5115]*3])
old = f.solve(points,[1,.7,1],1280,720)
assert abs(old['dist']-13.29868)<.0001
matrix = hou.Matrix4(old['matrix'].asTuple())
for i in range(3):matrix.setAt(3,i,old['direction'][i]*7.911284)
assert not f.check(points,matrix,1280,720)['ok'], 'old max-side framing must remain a negative control'
cases=0
for bounds in ([[-1,-1,-1],[1,1,1]], [[-10,-.1,-.1],[10,.1,.1]],
               [[30,4,-2],[31,4,4]], [[0,0,0],[0,0,0]]):
    pts=f.corners(bounds)
    for direction in ([1,.7,1],[0,1,0],[0,-1,0],[0,0,1],[-1,.1,-.4]):
        for width,height in ((1280,720),(720,1280),(640,640)):
            for projection in ('perspective','orthographic'):
                for aspect in (1,2):
                    plan=f.solve(pts,direction,width,height,projection=projection,aspect=aspect)
                    report=f.check(pts,plan['matrix'],width,height,projection=projection,aspect=aspect,
                                   orthowidth=plan['orthowidth'] or 1,near=plan['near'],far=plan['far']*1.001)
                    assert report['ok'],report
                    assert report['margin_px']['left'] >= width*.09-.01, report
                    cases+=1
rejected(lambda:f.solve(points,[0,0,0],1280,720),'zero')
rejected(lambda:f.solve(points,[1,float('nan'),1],1280,720),'finite')
rejected(lambda:f.solve(points,[1,1,1],1.2,720),'integers')
rejected(lambda:f.solve(points,[1,1,1],float('inf'),720),'finite')
for focal in (18,85,200):
    plan=f.solve(points,[1,.7,1],1280,720,focal=focal)
    assert f.check(points,plan['matrix'],1280,720,focal=focal,near=plan['near'],far=plan['far'])['ok']
assert 'far_clip' in f.check(points,old['matrix'],1280,720,far=1)['reasons']
assert 'near_or_behind_camera' in f.check(points,hou.Matrix4(1),1280,720)['reasons']
rejected(lambda:f.check(points,hou.hmath.buildScale((2,1,1)),1280,720),'rigid')

root=hou.node('/obj').createNode('geo','camera_fit_test')
box=root.createNode('box'); box.parmTuple('size').set((3,2,1))
root.parmTuple('t').set((8,-3,2)); root.parmTuple('r').set((20,40,10))
cam=hou.node('/obj').createNode('cam','fit_test_camera')
parent=hou.node('/obj').createNode('null','fit_test_parent')
parent.parmTuple('t').set((3,6,-4)); parent.parmTuple('r').set((10,25,-20))
cam.setInput(0,parent)
try:
    with dsh_ownership.execution_owner('framing-test','create'):
        dsh_ownership.register_owned_node(cam)
        before=cam.worldTransform()
        dry=h.camera_fit(cam,box,dry_run=True)
        assert dry['ok'] and not dry['applied'] and dry['scene_writes']==0 and cam.worldTransform()==before
        projected=bridge.run_code(
            f'__result__=camera_fit({cam.path()!r},{box.path()!r},dry_run=True)',
            owner_session='framing-test',owner_call='camera-plan')
        assert projected['ok'] and projected['transaction']['status']=='no_scene_change',projected
        assert projected['execution']['impact']['attempted'] is False,projected
        result=h.camera_fit(cam,box)
        assert result['ok'] and cam.evalParm('focal')==50
        # Failed actual readback restores all channels even outside GUI undo.
        before={p.name():(tuple(p.keyframes()),p.eval()) for p in cam.parms()}
        real_check=f.check
        invocations=[]
        def fail_readback(*args,**kwargs):
            report=real_check(*args,**kwargs);invocations.append(1)
            return {**report,'ok':False} if len(invocations)==2 else report
        f.check=fail_readback
        try:rejected(lambda:h.camera_fit(cam,box,direction='front'),'failed framing')
        finally:f.check=real_check
        assert before=={p.name():(tuple(p.keyframes()),p.eval()) for p in cam.parms()}
        cam.parm('tx').lock(True)
        rejected(lambda:h.camera_fit(cam,box),'锁定')
        cam.parm('tx').lock(False)
        assert hou.frame()==1
        cam.parm('winx').set(.1)
        rejected(lambda:h.camera_fit(cam,box),'offsets')
        cam.parm('winx').set(0)
        cam.parm('cropr').set(.5)
        rejected(lambda:h.camera_fit(cam,box),'offsets')
        cam.parm('cropr').set(1)
        key=hou.Keyframe(1);cam.parm('tx').setKeyframe(key)
        rejected(lambda:h.camera_fit(cam,box),'animated')
        cam.parm('tx').deleteAllKeyframes()
    with dsh_ownership.execution_owner('other','try'):
        rejected(lambda:h.camera_fit(cam,box),'foreign')
        rejected(lambda:h.camera_fit(cam,box,allow_foreign=''),'nonempty')
        assert h.camera_fit(cam,box,allow_foreign='test explicit camera authorization')['ok']
        cam.setUserData(dsh_service_constants._RENDER_OWNER_KEY,dsh_service_constants._RENDER_OWNER_VALUE)
        rejected(lambda:h.camera_fit(cam,box,allow_foreign='test explicit camera authorization'),'persistent')
        cam.destroyUserData(dsh_service_constants._RENDER_OWNER_KEY)
    response=bridge.run_code(f'camera_fit({cam.path()!r},{box.path()!r})',read_only=True,owner_session='framing-test')
    assert not response['ok'],response
finally:
    cam.destroy();parent.destroy();root.destroy()

# Exercise the real USD Render ROP's stage path/products through a Python LOP.
stage=hou.node('/stage')
py=stage.createNode('pythonscript','framing_stage_test')
rop=stage.createNode('usdrender_rop','framing_rop_test');rop.setInput(0,py)
scene_code='''from pxr import UsdGeom, UsdRender, Gf
s=hou.pwd().editableStage()
UsdGeom.Cube.Define(s,'/asset')
c=UsdGeom.Camera.Define(s,'/camera')
c.AddTranslateOp().Set(Gf.Vec3d(0,0,12))
c.CreateHorizontalApertureAttr(41.4214)
c.CreateVerticalApertureAttr(41.4214*720/1280)
c.CreateFocalLengthAttr(50)
r=UsdRender.Settings.Define(s,'/Render/settings')
r.CreateCameraRel().SetTargets(['/camera'])
r.CreateResolutionAttr(Gf.Vec2i(1280,720))
r.CreateIncludedPurposesAttr(['default','render'])
p=UsdRender.Product.Define(s,'/Render/product')
r.CreateProductsRel().SetTargets(['/Render/product'])
'''
try:
    py.parm('python').set(scene_code)
    rop.parm('rendersettings').set('/Render/settings')
    valid=f.usd_check(rop,{'target':'/asset'},1)
    assert valid['ok'],valid
    rop.parm('override_camera').set('/other')
    rejected(lambda:f.usd_check(rop,{'target':'/asset'},1),'override_camera')
    rop.parm('override_camera').set('')
    rop.parm('override_res').set('64 64')
    rejected(lambda:f.usd_check(rop,{'target':'/asset'},1),'override_res')
    rop.parm('override_res').set('')
    rop.parm('prerender').set('echo change_camera')
    rejected(lambda:f.usd_check(rop,{'target':'/asset'},1),'script')
    rop.parm('prerender').set('')
    py.parm('python').set(scene_code+"\np2=UsdRender.Product.Define(s,'/Render/product2')\np2.CreateDataWindowNDCAttr(Gf.Vec4f(0,0,.1,1))\nr.CreateProductsRel().SetTargets(['/Render/product','/Render/product2'])\n")
    all_products=f.usd_check(rop,{'target':'/asset'},1)
    assert not all_products['ok'] and len(all_products['products'])==2 and all_products['products'][0]['ok']
    for policy in ('expandAperture','cropAperture','adjustApertureWidth','adjustApertureHeight','adjustPixelAspectRatio'):
        py.parm('python').set(scene_code+f"\np.CreateAspectRatioConformPolicyAttr('{policy}')\np.CreateResolutionAttr(Gf.Vec2i(720,1280))\n")
        assert f.usd_check(rop,{'target':'/asset'},1)['ok']
    py.parm('python').set(scene_code+"\np.CreateDataWindowNDCAttr(Gf.Vec4f(0,0,.1,1))\n")
    clipped=f.usd_check(rop,{'target':'/asset'},1)
    assert not clipped['ok'],clipped
    frame_before=hou.frame()
    # It must reject without creating the directory/file or reaching render().
    with tempfile.TemporaryDirectory() as tmp:
        picture=pathlib.Path(tmp)/'not-created'/'clip.png'
        rejected(lambda:h.render_frame(rop,picture=str(picture),frame=2,framing={'target':'/asset'}),'before renderer')
        assert not picture.parent.exists() and hou.frame()==frame_before
    py.parm('python').set(scene_code+"\np.CreateCameraRel().SetTargets(['/missing'])\n")
    rejected(lambda:f.usd_check(rop,{'target':'/asset'},1),'missing')

    # The authored stage, requested time and native ROP selection determine
    # inherited products. Only rendering is replaced; this fixture never starts
    # Karma, and its byte files make no image/semantic quality claim.
    from pxr import Usd, UsdRender
    with tempfile.TemporaryDirectory(prefix='dsh-inherited-products-') as tmp:
        base=pathlib.Path(tmp)
        first=base/'beauty.<F4>.exr'
        second=base/'second.%04d.exr'
        multi_code=scene_code+f'''
p.CreateProductNameAttr().Set({(base/'old-beauty.exr').as_posix()!r},1)
p.GetProductNameAttr().Set({first.as_posix()!r}.replace('beauty.','beauty.'+chr(96)+'1+1'+chr(96)+'.'),3)
p2=UsdRender.Product.Define(s,'/Render/product2')
p2.CreateProductNameAttr().Set({(base/'old-second.exr').as_posix()!r},1)
p2.GetProductNameAttr().Set({second.as_posix()!r},3)
checkpoint=UsdRender.Product.Define(s,'/Render/checkpoint')
checkpoint.CreateProductTypeAttr('karma:checkpoint')
checkpoint.CreateProductNameAttr({(base/'optional.checkpoint').as_posix()!r})
null=UsdRender.Product.Define(s,'/Render/null')
null.CreateProductNameAttr('husk:null_raster')
r.CreateProductsRel().SetTargets(['/Render/product','/Render/product2','/Render/checkpoint','/Render/null'])
'''
        py.parm('python').set(multi_code)
        rop.parm('loppath').set('../'+py.name())
        rop.parm('rendersettings').set('settings')  # native /Render shorthand
        rop.parm('outputimage').set('')
        assert py.stage() is not None,py.errors()
        selected=usd._render_product_files(rop,3)
        expected=[base/'beauty.`1+1`.0003.exr',base/'second.0003.exr']
        assert [pathlib.Path(row['output']) for row in selected['products']]==expected,selected
        assert len(selected['unverified_products'])==2,selected
        assert usd._render_settings(rop)[0]==py

        # No metadata does not authorize selecting the sole discoverable prim.
        rop.parm('rendersettings').set('')
        assert not UsdRender.Settings.GetStageRenderSettings(py.stage())
        rejected(lambda:usd._render_settings(rop),'no explicit or stage-default')
        rejected(lambda:f.usd_check(rop,{'target':'/asset'},3),'no explicit or stage-default')
        before_rejection=hou.frame()
        with patch.object(hou.RopNode,'render',side_effect=AssertionError('unexpected renderer dispatch')) as no_render:
            rejected(lambda:h.render_frame(rop,frame=3),'no explicit or stage-default')
            no_render.assert_not_called()
        assert hou.frame()==before_rejection
        metadata_code=multi_code+"\nfrom pxr import Usd\nwith Usd.EditContext(s,s.GetSessionLayer()):\n s.SetMetadata('renderSettingsPrimPath','/Render/settings')\n"
        py.parm('python').set(metadata_code)
        assert py.stage() is not None,py.errors()
        assert usd._render_settings(rop)[2].GetPath()=='/Render/settings'
        py.parm('python').set(metadata_code.replace("s.SetMetadata('renderSettingsPrimPath','/Render/settings')",
                                                    "s.SetMetadata('renderSettingsPrimPath','settings')"))
        rejected(lambda:usd._render_settings(rop),'one absolute')
        py.parm('python').set(metadata_code)
        if rop.parm('dorenderexisting') is not None:
            rop.parm('dorenderexisting').set(1)
            rejected(lambda:usd._render_product_files(rop,3),'existing USD file')
            rop.parm('dorenderexisting').set(0)

        calls=[]
        omitted=set()
        def render_fixture(render_rop,frame_range):
            assert render_rop==rop and frame_range==(3.0,3.0)
            assert hou.frame()==3
            override=render_rop.evalParm('outputimage')
            calls.append({'override':override,'frame':hou.frame()})
            if override:
                pathlib.Path(override).write_bytes(('override-'+str(len(calls))).encode())
                return
            # Independently consume the real composed USD, without using the
            # output-discovery helper that is under test.
            composed=py.stage()
            settings=composed.GetPrimAtPath(composed.GetMetadata('renderSettingsPrimPath'))
            for target in settings.GetRelationship('products').GetForwardedTargets():
                product=UsdRender.Product(composed.GetPrimAtPath(target))
                name=product.GetProductNameAttr().Get(Usd.TimeCode(hou.frame()))
                if str(target) in omitted or product.GetProductTypeAttr().Get()!='raster' or name=='husk:null_raster':
                    continue
                actual=hou.text.expandHuskFilePath(name,3,1,0)
                pathlib.Path(actual).write_bytes(('product-'+str(target)+'-'+str(len(calls))).encode())

        saved_frame=hou.frame()
        try:
            with patch.object(hou.RopNode,'render',render_fixture):
                inherited=h.render_frame(rop,frame=3,timeout=.01)
                assert inherited['fresh'] and not inherited['errors'],inherited
                assert inherited['output'] is None and len(inherited['outputs'])==2,inherited
                assert all(row['fresh'] and row['file_bytes'] for row in inherited['outputs'])
                for row in inherited['outputs']:
                    for key in ('pre_fingerprint','post_fingerprint'):
                        if row[key] is None:
                            continue
                        nanos=row[key]['mtime_ns']
                        assert isinstance(nanos,str) and str(int(nanos))==nanos,row
                    assert row['post_fingerprint']['mtime_ns']==str(pathlib.Path(row['output']).stat().st_mtime_ns),row
                assert len(inherited['inherited_products']['unverified_products'])==2
                assert calls[-1]['override']=='' and rop.evalParm('outputimage')==''
                assert hou.frame()==saved_frame

                # One stale file remains on disk; the other output's success
                # cannot certify the whole multi-product render.
                omitted.add('/Render/product2')
                partial=h.render_frame(rop,frame=3,timeout=.01)
                assert not partial['fresh'] and partial['errors'],partial
                assert [row['fresh'] for row in partial['outputs']]==[True,False],partial
                assert hou.frame()==saved_frame and rop.evalParm('outputimage')==''
                omitted.clear()

                py.parm('python').set(metadata_code+"\nr.CreateProductsRel().SetTargets(['/Render/product'])\n")
                single=h.render_frame(rop,frame=3,timeout=.01)
                assert single['fresh'] and pathlib.Path(single['output'])==expected[0],single
                assert single['file_bytes']==single['outputs'][0]['file_bytes']
                assert single['post_fingerprint']==single['outputs'][0]['post_fingerprint']
                assert single['preexisting'] and hou.frame()==saved_frame
                py.parm('python').set(metadata_code)

                explicit=h.render_frame(rop,picture=str(base/'override.exr'),frame=3,timeout=.01)
                assert explicit['fresh'] and pathlib.Path(explicit['output'])==base/'override.exr',explicit
                assert 'outputs' not in explicit and calls[-1]['override']==str(base/'override.exr').replace('\\','/')
                assert rop.evalParm('outputimage')=='' and hou.frame()==saved_frame
                assert not (base/'optional.checkpoint').exists()

                with dsh_ownership.execution_owner('inherited-product-test','register'):
                    dsh_ownership.register_owned_node(rop)
                response=bridge.run_code(f'__result__=render_frame({rop.path()!r},frame=3,timeout=.01)',
                                         owner_session='inherited-product-test',owner_call='render-products')
                assert response['ok'] and response['result']['fresh'],response
                summary=response['verbs'][0]['summary']
                assert len(summary['outputs'])==2 and summary['output'] is None,summary
                assert len(summary['inherited_products']['unverified_products'])==2,summary
                candidates=response['artifactCandidates']
                assert {pathlib.Path(row['path']) for row in candidates}==set(expected),candidates
                assert all(row['role']=='delivery-candidate' for row in candidates),candidates
                assert hou.frame()==saved_frame and rop.evalParm('outputimage')==''
                if os.environ.get('DSH_RENDER_FIXTURE_OUT'):
                    receipt_path=pathlib.Path(os.environ['DSH_RENDER_FIXTURE_OUT'])
                    receipt_path.parent.mkdir(parents=True,exist_ok=True)
                    receipt_path.write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding='utf-8')

                # Failure to restore the discovery frame is an unrecovered
                # temporary write, even when author code catches the error.
                real_set_frame=hou.setFrame
                def fail_frame_restore(value):
                    if value==saved_frame and hou.frame()!=saved_frame:
                        raise RuntimeError('injected preflight frame restoration failure')
                    return real_set_frame(value)
                render_count=len(calls)
                with patch.object(hou,'setFrame',fail_frame_restore):
                    poisoned=bridge.run_code(
                        f'try:\n render_frame({rop.path()!r},frame=3,timeout=.01)\nexcept Exception:\n pass\n'
                        'try:\n scene_save()\nexcept Exception:\n pass\n'
                        f'__result__=describe({rop.path()!r})',owner_session='inherited-product-test',owner_call='failed-frame-restore')
                real_set_frame(saved_frame)
                assert not poisoned['ok'] and len(calls)==render_count,poisoned
                failed=poisoned['verbs'][0]['summary']
                assert failed['phase']=='render_restore' and failed['restored'] is False,poisoned
                assert poisoned['verbs'][1]['summary']['dispatched'] is False,poisoned
                assert poisoned['verbs'][2]['ok'] and hou.frame()==saved_frame,poisoned
        finally:
            hou.setFrame(saved_frame)
finally:
    rop.destroy();py.destroy()

# Repair reloads lazy modules/cache without contacting any server in this test.
import importlib
import dsh_launcher as launcher
import dsh_operation_cards as cards
import dsh_geometry_observation as observation
import dsh_preview_paths as preview_paths
import dsh_network_layout as network_layout
import dsh_network_boxes as network_boxes_module
real_reload=importlib.reload
real_stop,real_start=bridge.stop,bridge.start
expected_wrangle_card=cards.operation_card('attribwrangle')
started=[]
try:
    bridge.stop=lambda:None
    bridge.start=lambda *a,**kw:started.append((a,kw))
    importlib.reload=lambda m:m if m is bridge else real_reload(m)
    f.solve=None
    observation.attribute_uniqueness=None
    preview_paths.allocate_managed=None
    network_layout.union=None
    box_registry=network_boxes_module._OWNED_BOXES
    network_boxes_module.apply_network_boxes=None
    cards._cards=lambda:{'cards':{}}
    launcher.restart_bridge()
    assert callable(f.solve) and callable(observation.attribute_uniqueness)
    assert callable(preview_paths.allocate_managed)
    assert callable(network_layout.union) and callable(network_boxes_module.apply_network_boxes)
    assert network_boxes_module._OWNED_BOXES is box_registry
    assert cards.operation_card('attribwrangle')==expected_wrangle_card
    assert len(started)==1
finally:
    importlib.reload=real_reload
    bridge.stop,bridge.start=real_stop,real_start
print(f'camera framing: {cases} projection cases + OBJ ownership/dry-run + composed USD product preflight passed on {hou.applicationVersionString()} (no GUI/pixel claim)')
