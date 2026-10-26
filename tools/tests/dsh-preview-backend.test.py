"""Real H21/H22 ROP settings; stub pixels, no GUI claims."""

import sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import dsh_geometry_queries
import dsh_render
import dsh_render_service
import hou
import dsh_image_pixels
import dsh_render
import dsh_hou_helpers as h
old_ui,old_render,old_check=hou.isUIAvailable,dsh_render.render_frame,dsh_image_pixels.render_check
hou.isUIAvailable=lambda:True
calls=[]
def render(rop,picture=None,frame=None,**kwargs):
    calls.append(rop)
    return {'fresh':True,'file_bytes':1,'errors':[],'output':hou.expandStringAtFrame(picture,frame)}
dsh_render.render_frame=render
dsh_image_pixels.render_check=lambda *a,**kw:{'presentation':{'needs_review':False}}
warning_gate=dsh_render._render_validation(
    {'fresh':True,'file_bytes':1,'errors':[]},
    {'presentation':{'needs_review':False}},
    False,
    warnings=['attribute mismatch'],
)
assert not warning_gate['ok'] and warning_gate['file_status']=='passed'
assert 'cannot pass acceptance' in warning_gate['errors'][-1]
g=hou.node('/obj').createNode('geo','backend_fixture');box=g.createNode('box')
try:
 with tempfile.TemporaryDirectory() as tmp:
    tmp=str(Path(tmp).resolve())
    hou.hipFile.save(tmp+'/backend-fixture.hip')
    managed=[h.render_view(box,picture='managed.png') for _ in range(2)]
    assert len({row['output'] for row in managed})==2
    assert all(Path(row['output']).parent.parent==Path(tmp)/'dsh-artifacts/checks/previews'/'backend-fixture' for row in managed)
    assert all(row['artifact']['output_policy']=='managed' for row in managed)
    assert all(not any(key.startswith('_reservation') for key in row['artifact']) for row in managed)
    assert not list((Path(tmp)/'dsh-artifacts/checks').rglob('*.reserve'))
    delivered=[h.render_view(box,picture='final.png',output_policy='delivery') for _ in range(2)]
    assert len({row['output'] for row in delivered})==2
    assert all(Path(row['output']).parent.resolve()==(Path(tmp)/'dsh-artifacts/renders'/'backend-fixture').resolve() for row in delivered)
    assert all(row['artifact']['output_policy']=='delivery' for row in delivered)
    assert all(row['artifact']['actual_path']==row['output'] for row in delivered)
    assert all(row['artifact']['hip_relative_path'].startswith('dsh-artifacts/renders/') for row in delivered)
    assert all(row['artifact']['purpose']==managed[0]['artifact']['purpose'] for row in delivered)
    assert all(not any(key.startswith('_reservation') for key in row['artifact']) for row in delivered)
    assert not list((Path(tmp)/'dsh-artifacts/renders').rglob('*.reserve'))
    import dsh_media_output
    previous_hip=hou.hipFile.path()
    literal_hip=Path(tmp)/'variant.$F literal.hip'
    try:
        hou.hipFile.setName(dsh_media_output._literal_houdini_path(literal_hip.as_posix()))
        literal=h.render_view(box,picture='literal.png')
        assert literal['output']==literal['artifact']['actual_path']
        assert Path(literal['output']).parent.parent==Path(tmp)/'dsh-artifacts/checks/previews'/literal_hip.stem
    finally:hou.hipFile.setName(previous_hip)
    real_ensure=dsh_render_service._ensure_render_proxy
    def partial_proxy(target):
        proxy=hou.node('/obj/'+dsh_render_service._RENDER_PROXY_NAME)
        proxy.node('source').parm('objpath1').set(target.path())
        proxy.setUserData('dsh_render_state','active')
        raise RuntimeError('injected partial proxy setup')
    dsh_render_service._ensure_render_proxy=partial_proxy
    try:
        try:h.render_view(box,picture='partial-proxy.png')
        except RuntimeError as error:assert 'partial proxy setup' in str(error)
        else:raise AssertionError('partial proxy setup should reject')
    finally:dsh_render_service._ensure_render_proxy=real_ensure
    proxy=hou.node('/obj/'+dsh_render_service._RENDER_PROXY_NAME)
    assert proxy.userData('dsh_render_state')=='idle' and proxy.node('source').parm('objpath1').evalAsString()==''
    real_fingerprint=dsh_geometry_queries._geometry_fingerprint
    dsh_geometry_queries._geometry_fingerprint=lambda *_args,**_kwargs:{'errors':['injected pre-render failure']}
    try:
        try:h.render_view(box,picture='preflight.png')
        except ValueError as error:assert 'injected pre-render failure' in str(error)
        else:raise AssertionError('pre-render failure should reject')
    finally:dsh_geometry_queries._geometry_fingerprint=real_fingerprint
    assert not list((Path(tmp)/'dsh-artifacts/checks').rglob('*.reserve'))
    dsh_render.render_frame=lambda *_args,**_kwargs:(_ for _ in ()).throw(RuntimeError('injected renderer failure'))
    try:
        for policy in ('managed','delivery'):
            try:h.render_view(box,picture='renderer-failure.png',output_policy=policy)
            except RuntimeError as error:assert 'injected renderer failure' in str(error)
            else:raise AssertionError('renderer failure should propagate')
    finally:dsh_render.render_frame=render
    assert not list((Path(tmp)/'dsh-artifacts/checks').rglob('*.reserve'))
    assert not list((Path(tmp)/'dsh-artifacts/renders').rglob('*.reserve'))
    result=h.render_view(box,picture=tmp+'/first.png',output_policy='explicit')
    r=calls[-1]
    if hou.applicationVersion()[0]>=22:
        assert r.type().name()=='flipbook'
        assert result['preview_backend']=='flipbook_vulkan'
        assert r.parm('lighting').evalAsString()=='headlight'
        assert r.parm('worklighttype').evalAsString()=='headlight'
        assert r.parm('colorcorrect').evalAsString()=='ocio'
        assert result['output_color']['applied']['gamma'] is None
        r.parm('lighting').set('fullshadows');r.parm('motionblur').set(1)
        h.render_view(box,picture=tmp+'/again.png',output_policy='explicit')
        assert r.parm('lighting').evalAsString()=='headlight' and r.evalParm('motionblur')==0
    else:
        assert r.type().name()=='opengl'
        assert r.name()=='__dsh_houdini_opengl'
        assert result['preview_backend']=='opengl_legacy'
        assert r.evalParm('gamma')==1
    assert r.evalParm('forceobjects')==result['proxy']
    r.parm('dof').set(1)
    h.render_view(box,picture=tmp+'/clear-again.png',output_policy='explicit')
    assert r.evalParm('dof')==0, 'diagnostic previews never inherit service depth of field'
    assert r.evalParm('alights')=='' and r.evalParm('excludelights')=='*'
    tagged=g.createNode('attribwrangle','tagged')
    tagged.setInput(0,box);tagged.parm('class').set('point');tagged.parm('snippet').set('s@test_id="tagged";')
    plain=g.createNode('box','plain');plain.parm('tx').set(2)
    warning_merge=g.createNode('merge','warning_merge');warning_merge.setInput(0,tagged);warning_merge.setInput(1,plain)
    warning_merge.cook(force=True)
    assert warning_merge.warnings(), 'fixture must produce an attribute mismatch warning'
    warned=h.render_view(warning_merge,picture=tmp+'/warning.png',output_policy='explicit')
    assert not warned['ok'] and warned['file_status']=='passed' and warned['pixel_status']=='passed'
    assert warned['warnings'] and 'cannot pass acceptance' in warned['errors'][-1]
finally:
 hou.isUIAvailable=old_ui;dsh_render.render_frame=old_render;dsh_image_pixels.render_check=old_check
 g.destroy()
print('PASS version-specific preview backend '+hou.applicationVersionString())
