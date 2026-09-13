"""Metadata must not evaluate geometry or alter shared UI state."""
import sys, pathlib, threading, types
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_context as c
import dsh_bridge as b
headless=c.scene_context('test',threading.get_ident())
assert headless['frame']==hou.frame() and not headless['ui_available']
assert headless['geometry_selection']['status']=='not_observed'
original_mode=hou.updateModeSetting()
try:
    for mode, name in ((hou.updateMode.AutoUpdate,'auto'), (hou.updateMode.Manual,'manual'),
                       (hou.updateMode.OnMouseUp,'on_mouse_up')):
        hou.setUpdateMode(mode)
        observed=hou.updateModeSetting()
        expected={hou.updateMode.AutoUpdate:'auto',hou.updateMode.Manual:'manual',hou.updateMode.OnMouseUp:'on_mouse_up'}[observed]
        assert c.scene_context('test',threading.get_ident())['update_mode']==expected
        if mode != hou.updateMode.OnMouseUp:
            assert expected==name
finally:
    hou.setUpdateMode(original_mode)
handler=object.__new__(b._Handler);handler.path='/context';responses=[]
handler._send=lambda payload,status=200:responses.append((status,payload))
handler._route({'schema_version':1})
assert responses[-1][1]['ok'] and responses[-1][1]['result']['schema_version']==1
handler._route({'schema_version':True})
assert responses[-1][0]==400
handler._route({'schema_version':1,'code':'raise RuntimeError()'})
assert responses[-1][0]==400,'context is a fixed metadata endpoint, not another code execution route'
class Node:
    def path(self):return '/obj/g'
    def type(self):return types.SimpleNamespace(name=lambda:'geo')
    def needsToCook(self):return True
    def errors(self):return ()
    def warnings(self):return ()
    def childTypeCategory(self):return 'sop'
    def displayNode(self):return self
    def renderNode(self):return self
    def geometry(self):raise AssertionError('metadata cooked geometry')
class Pane:
    def type(self):return 'network'
    def pwd(self):return Node()
    def currentNode(self):return Node()
real=c.hou
c.hou=types.SimpleNamespace(isUIAvailable=lambda:True,
    applicationVersionString=lambda:'fixture',hipFile=types.SimpleNamespace(path=lambda:'x.hip',hasUnsavedChanges=lambda:True),
    frame=lambda:10,selectedNodes=lambda:[Node()]*20,playbar=types.SimpleNamespace(isPlaying=lambda:False),
    ui=types.SimpleNamespace(paneTabs=lambda:[Pane(),Pane()]),
    updateMode=hou.updateMode,updateModeSetting=lambda:hou.updateMode.Manual,
    paneTabType=types.SimpleNamespace(NetworkEditor='network',SceneViewer='viewer'),sopNodeTypeCategory=lambda:'sop',Error=Exception)
try:
    result=c.scene_context('fixture',threading.get_ident())
    assert result['selection_count']==20 and len(result['selection'])==16
    assert result['selection_truncated'] and result['focus']=='unknown'
    assert result['update_mode']=='manual'
    assert len(result['panes'])==2 and result['panes'][0]['display']=='/obj/g'
finally:c.hou=real
errors=[]
def wrong_thread():
    try:c.scene_context('test',b._HOU_THREAD_ID)
    except RuntimeError:errors.append(True)
t=threading.Thread(target=wrong_thread);t.start();t.join();assert errors
executed=[]
old=b._pump_active;b._pump_active=True
def queued():
    try:b._execute(lambda:executed.append(True),timeout=0.01)
    except TimeoutError:errors.append(True)
t=threading.Thread(target=queued);t.start();t.join(2)
assert not t.is_alive()
b._pump();b._pump_active=old
assert not executed,'expired metadata task must never run later'
print('metadata observation: bounded selection, ambiguous panes, no geometry, thread and queue expiry passed')
