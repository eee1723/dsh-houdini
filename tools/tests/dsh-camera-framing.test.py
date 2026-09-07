"""Real HOM camera geometry assertions. No live HIP and no renderer required."""
import math
import pathlib
import sys
import tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as bridge
import dsh_camera_framing as f


def rejected(fn, needle):
    try: fn()
    except (ValueError, PermissionError, h.CheckpointError) as exc:
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
    with h._execution_owner('framing-test','create'):
        h._register_owned_node(cam)
        before=cam.worldTransform()
        dry=h.camera_fit(cam,box,dry_run=True)
        assert dry['ok'] and not dry['applied'] and cam.worldTransform()==before
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
    with h._execution_owner('other','try'):
        rejected(lambda:h.camera_fit(cam,box),'foreign')
        rejected(lambda:h.camera_fit(cam,box,allow_foreign=''),'nonempty')
        assert h.camera_fit(cam,box,allow_foreign='test explicit camera authorization')['ok']
        cam.setUserData(h._RENDER_OWNER_KEY,h._RENDER_OWNER_VALUE)
        rejected(lambda:h.camera_fit(cam,box,allow_foreign='test explicit camera authorization'),'persistent')
        cam.destroyUserData(h._RENDER_OWNER_KEY)
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
finally:
    rop.destroy();py.destroy()

# Repair reloads lazy modules/cache without contacting any server in this test.
import importlib
import dsh_launcher as launcher
import dsh_operation_cards as cards
import dsh_geometry_observation as observation
real_reload=importlib.reload
real_stop,real_start=bridge.stop,bridge.start
started=[]
try:
    bridge.stop=lambda:None
    bridge.start=lambda *a,**kw:started.append((a,kw))
    importlib.reload=lambda m:m if m is bridge else real_reload(m)
    f.solve=None
    observation.attribute_uniqueness=None
    cards._cards=lambda:{'cards':{}}
    launcher.restart_bridge()
    assert callable(f.solve) and callable(observation.attribute_uniqueness)
    assert cards.operation_card('attribwrangle')['id']=='wrangle-execution-v3'
    assert len(started)==1
finally:
    importlib.reload=real_reload
    bridge.stop,bridge.start=real_stop,real_start
print(f'camera framing: {cases} projection cases + OBJ ownership/dry-run + composed USD product preflight passed on {hou.applicationVersionString()} (no GUI/pixel claim)')
