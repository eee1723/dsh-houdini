"""Preview framing/depth separation, real HOM with a renderer stub (no live HIP)."""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_camera_framing as f
import dsh_hou_helpers as h
import dsh_bridge as bridge


def lens(plan, projection):
    return {'projection': projection, **{k:plan[k] for k in ('focal','aperture','near','far','orthowidth')}}


focus = [[-53, 8, -5], [53, 61, 5]]
context = [[-80, 0, -45], [80, 61, 45]]
cases = 0
for bounds, depths in [(focus, context), ([[-.01,-2,-8],[.01,2,8]], [[-100,-4,-20],[60,4,200]]),
                       ([[2,3,4],[2,3,4]], [[-2,0,-3],[6,7,9]])]:
    for direction in ([1,.2,.25], [.35,.25,1], [0,1,0], [-1,.2,-.3]):
        for projection in ('orthographic', 'perspective'):
            for width,height in ((1280,720),(720,1280)):
                plans = {}
                for mode in ('full','detail'):
                    p = f.preview_plan(bounds, depths, direction, width, height, projection=projection, framing=mode)
                    result = f.preview_check(f.corners(bounds),f.corners(depths),p['matrix'],width,height,
                                             framing=mode,**lens(p,projection))
                    assert result['ok'] and result['depth_check']['ok'],result
                    assert result['depth_check']['depth_range'][0] >= p['near'],result
                    if mode=='full': assert not result['crop_reasons']
                    plans[mode] = p
                    cases += 1
                assert plans['full']['matrix']==plans['detail']['matrix'], 'zoom must not dolly the camera'
                if projection=='orthographic':
                    assert abs(plans['detail']['orthowidth']/plans['full']['orthowidth']-.55)<1e-9
                else:
                    assert abs(plans['full']['focal']/plans['detail']['focal']-.55)<1e-9

# Negative control: the former post-solve dolly cuts the target in both trace directions.
for direction in ([1,.2,.25],[.35,.25,1]):
    old=f.solve(f.corners(focus),direction,1280,720,projection='orthographic')
    matrix=hou.Matrix4(old['matrix'].asTuple())
    eye=hou.Vector3(old['center'])+hou.Vector3(old['direction'])*old['dist']*.55
    for i in range(3):matrix.setAt(3,i,eye[i])
    bad=f.preview_check(f.corners(focus),f.corners(context),matrix,1280,720,
                        framing='detail',projection='orthographic',orthowidth=old['orthowidth']*.55)
    assert not bad['ok'] and bad['framing_status']=='failed' and 'near_or_behind_camera' in bad['reasons']

root=hou.node('/obj').createNode('geo','preview_depth_fixture')
box=root.createNode('box','focus_source');box.parmTuple('size').set((106,53,10));box.parmTuple('t').set((0,34.5,0))
group=root.createNode('groupcreate','tag');group.setInput(0,box);group.parm('groupname').set('focus')
surround=root.createNode('box','context');surround.parmTuple('size').set((160,8,90));surround.parm('ty').set(4)
merge=root.createNode('merge','OUT');merge.setInput(0,group);merge.setInput(1,surround)
sentinel=hou.node('/obj').createNode('null','preview_sentinel');sentinel.setSelected(True,clear_all_selected=True)
real_ui,real_render,real_check=hou.isUIAvailable,h.render_frame,h.render_check
hou.isUIAvailable=lambda:True
calls=[]


def render(rop,picture=None,frame=None,**kwargs):
    cam=hou.node(rop.evalParm('camera'))
    proxy=hou.node(rop.evalParm('forceobjects')).node('OUT')
    geometry=proxy.geometryAtFrame(frame)
    inv=cam.worldTransform().inverted()
    actual_depths=[-(p.position()*inv)[2] for p in geometry.points()]
    assert min(actual_depths)>=cam.evalParm('near') and max(actual_depths)<=cam.evalParm('far')
    calls.append({'matrix':list(cam.worldTransform().asTuple()),'focal':cam.evalParm('focal'),
                  'orthowidth':cam.evalParm('orthowidth'),'points':len(actual_depths),'min_depth':min(actual_depths)})
    return {'fresh':True,'file_bytes':1,'errors':[],'output':picture}


h.render_frame=render
h.render_check=lambda *a,**kw:{'path':a[0],'content_bbox':[1,1,128,72],'presentation':{'needs_review':False}}


def rejects(fn, reason):
    count=len(calls)
    before_selection=tuple(hou.selectedNodes())
    visibility={n.path():n.isDisplayFlagSet() for n in hou.node('/obj').children()}
    try:fn()
    except h.CheckpointError as error:
        assert not error.evidence['ok'] and not error.evidence['render_started'],error.evidence
        assert reason in error.evidence['reasons'],error.evidence
        assert bridge._operation_summary('render_view',error.evidence)['depth_check']==error.evidence['depth_check']
    else:raise AssertionError('unsafe framing was rendered')
    assert len(calls)==count
    assert tuple(hou.selectedNodes())==before_selection
    assert all(hou.node(p).isDisplayFlagSet()==v for p,v in visibility.items())


try:
    with tempfile.TemporaryDirectory() as tmp:
        path=tmp+'/preview.png'
        for projection in ('orthographic','perspective'):
            for isolate in (False,True):
                options={'focus_group':'focus','isolate':isolate,'projection':projection,'direction':[1,.2,.25],'picture':path}
                a=h.render_view(merge,**options)
                b=h.render_view(merge,framing='detail',**options)
                assert a['framing']['matrix']==b['framing']['matrix']
                assert b['framing']['ok'] and b['framing']['depth_check']['ok']
                assert b['framing']['framing_status']=='intentional_crop'
                assert a['check'] is a['pixels'] and a['pixels']['presentation']==a['check']['presentation']
                evidence=bridge._operation_summary('render_view',a)
                assert evidence['check']==evidence['pixels']==a['check']
                if not isolate:
                    frozen={'framing_bounds':a['framing']['bounds'],'depth_bounds':a['framing']['depth_bounds']}
                    box.parm('sizex').set(80);surround.parm('sizex').set(140)
                    c=h.render_view(merge,**frozen,**options)
                    assert a['framing']['matrix']==c['framing']['matrix']
                    assert a['framing']['focal']==c['framing']['focal']
                    assert a['framing']['orthowidth']==c['framing']['orthowidth']
                    surround.parm('tx').set(1000)
                    for mode in ('full','detail'):
                        rejects(lambda:h.render_view(merge,framing=mode,**frozen,**options),'near_or_behind_camera')
                    surround.parm('tx').set(-20000)
                    rejects(lambda:h.render_view(merge,framing='detail',**frozen,**options),'far_clip')
                    surround.parm('tx').set(0);box.parm('sizex').set(106);surround.parm('sizex').set(160)
                assert hou.node(b['proxy']).node('source').evalParm('objpath1')==''

        # Fixed frame observes the depth envelope at that frame, not the new one.
        surround.parm('tx').setExpression('($F-1)*1000')
        rejects(lambda:h.render_view(merge,frame=2,framing_frame=1,focus_group='focus',
                                    projection='orthographic',framing='detail',direction=[1,.2,.25],picture=path),'near_or_behind_camera')
        surround.parm('tx').deleteAllKeyframes();surround.parm('tx').set(0)
        # Local ROI needs detail; full keeps rejecting XY overflow, with useful guidance.
        roi=[[40,0,-10],[60,20,10]]
        rejects(lambda:h.render_view(merge,framing_bounds=roi,depth_bounds=context,projection='orthographic',picture=path),
                'outside_safe_frame')
        close=h.render_view(merge,framing='detail',framing_bounds=roi,depth_bounds=context,projection='orthographic',picture=path)
        assert close['framing']['ok'] and close['framing']['depth_check']['ok']
        # Fault injection: even detail cannot hide a broken lens's depth clipping.
        original=f.obj_lens
        f.obj_lens=lambda cam:{**original(cam),'far':original(cam)['near']*2}
        try:rejects(lambda:h.render_view(merge,framing='detail',projection='orthographic',picture=path),'far_clip')
        finally:f.obj_lens=original
finally:
    hou.isUIAvailable=real_ui;h.render_frame=real_render;h.render_check=real_check
    root.destroy();sentinel.destroy()

print(f'preview depth: {cases} math cases, {len(calls)} safe rendered HOM states, frozen-envelope/fault/alias checks passed on {hou.applicationVersionString()} (renderer stub)')
