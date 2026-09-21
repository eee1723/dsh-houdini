"""Real H21/H22 ROP settings; stub pixels, no GUI claims."""
import sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
old_ui,old_render,old_check=hou.isUIAvailable,h.render_frame,h.render_check
hou.isUIAvailable=lambda:True
calls=[]
def render(rop,picture=None,frame=None,**kwargs):
    calls.append(rop)
    return {'fresh':True,'file_bytes':1,'errors':[],'output':picture}
h.render_frame=render
h.render_check=lambda *a,**kw:{'presentation':{'needs_review':False}}
warning_gate=h._render_validation(
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
    hou.hipFile.save(tmp+'/backend-fixture.hip')
    managed=[h.render_view(box,picture='managed.png') for _ in range(2)]
    assert len({row['output'] for row in managed})==2
    assert all(Path(row['output']).parent.parent==Path(tmp)/'dsh-visual-checks' for row in managed)
    assert all(row['artifact']['output_policy']=='managed' for row in managed)
    assert all(not any(key.startswith('_reservation') for key in row['artifact']) for row in managed)
    assert not list((Path(tmp)/'dsh-visual-checks').rglob('*.reserve'))
    real_fingerprint=h._geometry_fingerprint
    h._geometry_fingerprint=lambda *_args,**_kwargs:{'errors':['injected pre-render failure']}
    try:
        try:h.render_view(box,picture='preflight.png')
        except ValueError as error:assert 'injected pre-render failure' in str(error)
        else:raise AssertionError('pre-render failure should reject')
    finally:h._geometry_fingerprint=real_fingerprint
    assert not list((Path(tmp)/'dsh-visual-checks').rglob('*.reserve'))
    h.render_frame=lambda *_args,**_kwargs:(_ for _ in ()).throw(RuntimeError('injected renderer failure'))
    try:
        try:h.render_view(box,picture='renderer-failure.png')
        except RuntimeError as error:assert 'injected renderer failure' in str(error)
        else:raise AssertionError('renderer failure should propagate')
    finally:h.render_frame=render
    assert not list((Path(tmp)/'dsh-visual-checks').rglob('*.reserve'))
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
 hou.isUIAvailable=old_ui;h.render_frame=old_render;h.render_check=old_check
 g.destroy()
print('PASS version-specific preview backend '+hou.applicationVersionString())
