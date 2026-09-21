"""H21/H22 governed handoff layout regression with fixed obstacles."""
from pathlib import Path
import sys,uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge
import dsh_network_boxes as boxes
import dsh_hou_helpers as h

suffix=uuid.uuid4().hex[:8];session='handoff-'+suffix
def call(code):return bridge.run_code(code,owner_session=session,owner_call=uuid.uuid4().hex)
def ok(code):
 r=call(code);assert r['ok'],r;return r

parent=None
try:
 parent=ok(f"p=tab_create('/obj','geo',name='__handoff_{suffix}')\n__result__=p.path()")['result']
 paths=[]
 for index in range(18):paths.append(ok(f"__result__=tab_create({parent!r},'null',name='n{index:02d}').path()")['result'])
 for source,target in ((0,6),(1,6),(2,10),(3,10),(6,10),(10,16),(11,16),(16,17)):
  ok(f"connect({paths[source]!r},{paths[target]!r})")
 for index,path in enumerate(paths):hou.node(path).setPosition(hou.Vector2((index%6)*1.1,-(index//6)*.7))
 groups=[
  {'name':'controls','label':'Long user control label','role':'controls','members':paths[0:2]},
  {'name':'placement','label':'Placement and driving attributes','role':'placement','members':paths[2:6]},
  {'name':'sources','label':'Replaceable source geometry prototypes','role':'source','members':paths[6:10]},
  {'name':'assembly','label':'Processing and assembly network','role':'assembly','members':paths[10:16]},
  {'name':'output','label':'Published output and delivery','role':'output','members':paths[16:18]},]
 dry=ok(f"__result__=network_boxes({parent!r},{groups!r},dry_run=True)")['result']
 ok(f"network_boxes({parent!r},{groups!r},expected_plan={dry['plan_sha256']!r})")
 foreign=hou.node(parent).createNode('null','foreign_obstacle');foreign.setPosition(hou.Vector2(0,-8));foreign_pos=tuple(foreign.position())
 foreign_box=hou.node(parent).createNetworkBox('foreign_box');foreign_box.addItem(foreign);foreign_box.setBounds(hou.BoundingRect(-2,-10,3,-6));foreign_bounds=(tuple(foreign_box.position()),tuple(foreign_box.size()))
 note=hou.node(parent).createStickyNote('fixed_user_note');note.setText('Fixed user note');note.setPosition(hou.Vector2(8,-6));note.setSize(hou.Vector2(4,2))
 dot=hou.node(parent).createNetworkDot();dot.setPosition(hou.Vector2(14,-4));dot_pos=tuple(dot.position())
 service_node=hou.node(parent).createNode('null','service_node');service_node.setUserData(h._RENDER_OWNER_KEY,h._RENDER_OWNER_VALUE)
 service=h._render_service_box(hou.node(parent),h._RENDER_OBJ_BOX_NAME,[service_node]);service_bounds=(tuple(service.position()),tuple(service.size()))
 frame=float(hou.frame());selection=tuple(node.path() for node in hou.selectedNodes())
 wires={path:[item.path() if item else None for item in hou.node(path).inputs()] for path in paths}
 flags={path:(hou.node(path).isDisplayFlagSet(),hou.node(path).isRenderFlagSet(),hou.node(path).needsToCook()) for path in paths}
 selected=[row['name'] for row in groups]
 preview=call(f"__result__=layout_nodes({parent!r},mode='handoff',boxes={selected!r},dry_run=True)")
 assert preview['ok'] and preview['result']['layout_status']=='planned',preview
 assert preview['transaction']['status']=='no_scene_change' and preview['result']['scene_writes']==0
 old_plan=preview['result']['plan_sha256']
 applied=call(f"__result__=layout_nodes({parent!r},mode='handoff',boxes={selected!r},expected_plan={old_plan!r})")
 assert applied['ok'] and applied['result']['layout_status']=='passed',applied
 result=applied['result'];assert result['node_overlap_count']==result['box_overlap_count']==result['obstacle_overlap_count']==0
 assert not result['containment_failures'] and result['moved_node_count']>0
 assert not result['clearance_failures'] and result['profile']=='comfortable'
 assert result['required_clearances']['node_horizontal_clearance']>0
 assert result['achieved_clearances']==result['minimum_clearances']
 assert result['achieved_clearances']['containment_margins']['minimum_title']>=result['required_clearances']['box_title_allowance']-1e-5
 assert tuple(foreign.position())==foreign_pos and (tuple(foreign_box.position()),tuple(foreign_box.size()))==foreign_bounds
 assert (tuple(service.position()),tuple(service.size()))==service_bounds
 assert tuple(dot.position())==dot_pos and any(row[0].startswith('dot:') for row in result['fixed_obstacles'])
 assert float(hou.frame())==frame and tuple(node.path() for node in hou.selectedNodes())==selection
 assert {path:[item.path() if item else None for item in hou.node(path).inputs()] for path in paths}==wires
 assert {path:(hou.node(path).isDisplayFlagSet(),hou.node(path).isRenderFlagSet(),hou.node(path).needsToCook()) for path in paths}==flags
 stale=call(f"layout_nodes({parent!r},mode='handoff',boxes={selected!r},expected_plan={old_plan!r})")
 assert not stale['ok'] and 'stale' in stale['error']
 fresh=ok(f"__result__=layout_nodes({parent!r},mode='handoff',boxes={selected!r},dry_run=True)")['result']
 noop=call(f"__result__=layout_nodes({parent!r},mode='handoff',boxes={selected!r},expected_plan={fresh['plan_sha256']!r})")
 assert noop['ok'] and not noop['result']['applied'] and noop['result']['scene_writes']==0
 assert noop['transaction']['status']=='no_scene_change'
 denied=call(f"layout_nodes({parent!r},mode='handoff',boxes=['foreign_box'],dry_run=True,allow_foreign='no broad handoff')")
 assert not denied['ok'] and 'owned' in denied['error']
 # Apply failure after some node moves restores through the accepted box journal.
 shifted=hou.node(paths[0]);shifted.setPosition(shifted.position()+hou.Vector2(3,0))
 fail_plan=ok(f"__result__=layout_nodes({parent!r},mode='handoff',boxes={selected!r},dry_run=True)")['result']
 original_position=boxes._set_node_position;calls={'n':0}
 def fail_once(node,target):
  calls['n']+=1
  if calls['n']==2:raise RuntimeError('injected handoff position failure')
  return original_position(node,target)
 boxes._set_node_position=fail_once
 try:failed=call(f"layout_nodes({parent!r},mode='handoff',boxes={selected!r},expected_plan={fail_plan['plan_sha256']!r})")
 finally:boxes._set_node_position=original_position
 assert not failed['ok'] and failed['evidence'][0]['restored'] is True,failed
 print('handoff layout contract passed on '+hou.applicationVersionString())
finally:
 if parent and hou.node(parent) is not None:hou.node(parent).destroy()
