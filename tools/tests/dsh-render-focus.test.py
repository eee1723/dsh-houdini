"""Camera/proxy contract using real HOM and a stub renderer; NOT a GUI pixel test."""
import sys,pathlib,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
root=hou.node('/obj').createNode('geo','focus_test')
box=root.createNode('box');group=root.createNode('groupcreate');group.setInput(0,box)
group.parm('groupname').set('target')
real_ui=hou.isUIAvailable;real_render=h.render_frame;real_check=h.render_check
hou.isUIAvailable=lambda:True
calls=[]
def render(rop,picture=None,frame=None,**kwargs):
    calls.append(rop.parm('camera').eval())
    return {'fresh':True,'file_bytes':1,'errors':[],'output':picture}
h.render_frame=render
h.render_check=lambda *a,**kw:{'presentation':{'needs_review':False}}
try:
    with tempfile.TemporaryDirectory() as tmp:
        a=h.render_view(group,focus_group='target',isolate=True,projection='orthographic',picture=tmp+'/a.png')
        assert a['framing']['focus_group']=='target' and a['framing']['isolated']
        assert hou.node(a['camera']).evalParm('projection')==1
        assert hou.node(a['proxy']).node('source').evalParm('objpath1')==''
        box.parm('sizex').set(2)
        b=h.render_view(group,focus_group='target',projection='orthographic',framing_bounds=a['framing']['bounds'],picture=tmp+'/b.png')
        assert a['framing']['eye']==b['framing']['eye'] and a['framing']['center']==b['framing']['center']
        assert b['framing']['bounds_source']=='explicit'
        c=h.render_view(group,picture=tmp+'/c.png')
        assert hou.node(c['camera']).evalParm('projection')==0,'previous ortho mode must not leak'
        try:h.render_view(group,focus_group='missing',picture=tmp+'/d.png')
        except ValueError as e:assert 'missing primitive group' in str(e)
        else:raise AssertionError('empty focus silently rendered whole object')
        assert len(calls)==3
finally:
    hou.isUIAvailable=real_ui;h.render_frame=real_render;h.render_check=real_check
    root.destroy()
print('render focus camera/proxy contract passed (renderer stub): '+hou.applicationVersionString())
