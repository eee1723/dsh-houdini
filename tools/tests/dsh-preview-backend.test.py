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
g=hou.node('/obj').createNode('geo','backend_fixture');box=g.createNode('box')
try:
 with tempfile.TemporaryDirectory() as tmp:
    result=h.render_view(box,picture=tmp+'/first.png')
    r=calls[-1]
    if hou.applicationVersion()[0]>=22:
        assert r.type().name()=='flipbook'
        assert result['preview_backend']=='flipbook_vulkan'
        assert r.parm('lighting').evalAsString()=='headlight'
        assert r.parm('worklighttype').evalAsString()=='headlight'
        assert r.parm('colorcorrect').evalAsString()=='ocio'
        assert result['output_color']['applied']['gamma'] is None
        r.parm('lighting').set('fullshadows');r.parm('motionblur').set(1)
        h.render_view(box,picture=tmp+'/again.png')
        assert r.parm('lighting').evalAsString()=='headlight' and r.evalParm('motionblur')==0
    else:
        assert r.type().name()=='opengl'
        assert r.name()=='__dsh_houdini_opengl'
        assert result['preview_backend']=='opengl_legacy'
        assert r.evalParm('gamma')==1
    assert r.evalParm('forceobjects')==result['proxy']
    assert r.evalParm('alights')=='' and r.evalParm('excludelights')=='*'
finally:
 hou.isUIAvailable=old_ui;h.render_frame=old_render;h.render_check=old_check
 g.destroy()
print('PASS version-specific preview backend '+hou.applicationVersionString())
