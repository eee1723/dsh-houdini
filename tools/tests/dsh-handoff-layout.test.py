"""H21/H22 governed handoff layout regression with fixed obstacles."""

from pathlib import Path
import sys,uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import dsh_render_service
import dsh_service_constants
import hou
import dsh_bridge as bridge
import dsh_network_boxes as boxes
import dsh_hou_helpers as h

suffix=uuid.uuid4().hex[:8];session='handoff-'+suffix
def call(code):return bridge.run_code(code,owner_session=session,owner_call=uuid.uuid4().hex)
def ok(code):
 r=call(code);assert r['ok'],r;return r

def wiring(node):
 rows=[]
 for connection in node.inputConnections():
  source=connection.inputNode()
  indirect=connection.subnetIndirectInput() if source is None else None
  rows.append((connection.inputIndex(),connection.outputIndex(),
   ('node',source.sessionId()) if source is not None else
   ('indirect',indirect.sessionId()) if indirect is not None else None))
 return rows

parent=None;large_parent=None;subnet_parent=None
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
 service_node=hou.node(parent).createNode('null','service_node');service_node.setUserData(dsh_service_constants._RENDER_OWNER_KEY,dsh_service_constants._RENDER_OWNER_VALUE)
 service=dsh_render_service._render_service_box(hou.node(parent),dsh_service_constants._RENDER_OBJ_BOX_NAME,[service_node]);service_bounds=(tuple(service.position()),tuple(service.size()))
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
 denied=call(f"layout_nodes({parent!r},mode='handoff',boxes=['foreign_box'],dry_run=True)")
 assert not denied['ok'] and 'ownership guard' in denied['error']
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
 # The readable adapter must preserve model state and remain stable on reapply.
 readable=ok(f"__result__=layout_nodes({parent!r},mode='handoff',boxes={selected!r},profile='readable')")['result']
 assert readable['layout_status']=='passed' and readable['readability'],readable
 assert not readable['clearance_failures'] and not readable['containment_failures']
 assert {path:[item.path() if item else None for item in hou.node(path).inputs()] for path in paths}==wires
 assert {path:(hou.node(path).isDisplayFlagSet(),hou.node(path).isRenderFlagSet(),hou.node(path).needsToCook()) for path in paths}==flags
 stable=ok(f"__result__=layout_nodes({parent!r},mode='handoff',boxes={selected!r},profile='readable')")
 assert not stable['result']['applied'] and stable['transaction']['status']=='no_scene_change',stable
 # More than the old 512-node and 512-obstacle thresholds: one explicit owned
 # scope, complete unselected geometry, and a blocker appended after all others.
 large=ok(
  f"p=tab_create('/obj','geo',name='__large_handoff_{suffix}')\n"
  "paths=[];previous=None\n"
  "for i in range(620):\n"
  " n=tab_create(p,'null',name='n%04d'%i,inputs=[] if previous is None else [previous]);paths.append(n.path());previous=n\n"
  "network_boxes(p,[{'name':'model','members':paths}])\n"
  "__result__={'parent':p.path(),'paths':paths}")['result']
 large_parent=large['parent'];large_network=hou.node(large_parent)
 with boxes.transaction_journal() as journal:
  for path in large['paths']:boxes.journal_containing_boxes([hou.node(path)])
  assert journal['boxes']==1 and journal['nodes']==620
  snapshots=[row['snapshot'] for row in journal['entries']]
  assert sum(len(row['boxes']) for row in snapshots)==1
  assert sum(len(row['nodes']) for row in snapshots)==620
  assert sum(len(state['members']) for row in snapshots for state in row['boxes'])==620
 for index in range(700):
  fixed=large_network.createNode('null','fixed%04d'%index)
  fixed.setPosition(hou.Vector2(index*3,10000))
 before=ok(f"__result__=layout_nodes({large_parent!r},mode='handoff',boxes=['model'],dry_run=True)")['result']
 blocker=large_network.createStickyNote('late_blocker')
 bounds=before['box_bounds']['model'];blocker.setPosition(hou.Vector2(bounds[0],bounds[1]));blocker.setSize(hou.Vector2(bounds[2]-bounds[0],bounds[3]-bounds[1]))
 obstacle_state=boxes.collect_editor_obstacles(large_network,excluded_node_ids=[int(hou.node(path).sessionId()) for path in large['paths']],
   excluded_box_ids=[int(large_network.findNetworkBox('model').sessionId())],dot_footprint=(1,1))
 large_applied=ok(f"__result__=layout_nodes({large_parent!r},mode='handoff',boxes=['model'])")['result']
 assert large_applied['layout_status']=='passed' and large_applied['movable_node_count']==620,large_applied
 assert len(large_applied['fixed_obstacles'])==701 and not large_applied['obstacle_overlap_count']
 assert boxes.collect_editor_obstacles(large_network,excluded_node_ids=[int(hou.node(path).sessionId()) for path in large['paths']],
   excluded_box_ids=[int(large_network.findNetworkBox('model').sessionId())],dot_footprint=(1,1))==obstacle_state
 # A real default-profile grouped DAG may return to the first presentation box.
 cyclic=ok(f"__result__=network_boxes({parent!r},[{{'name':'back','members':[{paths[1]!r},{paths[10]!r}]}},{{'name':'middle','members':[{paths[6]!r}]}}])")
 assert cyclic['result']['applied']
 cycle_layout=ok(f"__result__=layout_nodes({parent!r},mode='handoff',boxes=['back','middle'])")['result']
 assert cycle_layout['layout_status']=='passed',cycle_layout
 # Failure after hundreds of successful moves restores only the written node
 # positions and the explicit boxes; foreign obstacles remain exactly fixed.
 for path in large['paths']:hou.node(path).setPosition(hou.node(path).position()+hou.Vector2(20,0))
 position_before={path:tuple(hou.node(path).position()) for path in large['paths']}
 bounds_before=boxes._state(large_network.findNetworkBox('model'))
 original_position=boxes._set_node_position;calls={'n':0}
 def late_failure(node,target):
  calls['n']+=1
  if calls['n']==550:raise RuntimeError('injected late large layout failure')
  return original_position(node,target)
 boxes._set_node_position=late_failure
 try:failed=call(f"layout_nodes({large_parent!r},mode='handoff',boxes=['model'])")
 finally:boxes._set_node_position=original_position
 assert not failed['ok'] and failed['evidence'][0]['restored'],failed
 assert {path:tuple(hou.node(path).position()) for path in large['paths']}==position_before
 assert not boxes._state_mismatches(bounds_before,boxes._state(large_network.findNetworkBox('model')))
 # Component layout translates explicitly selected leaf boxes as units; the
 # total node count is independent from the small rectangle planning problem.
 regroup=[{'name':'part_a','members':large['paths'][:310]},
          {'name':'part_b','members':large['paths'][310:]},
          {'name':'asset','boxes':['part_a','part_b']}]
 ok(f"network_boxes({large_parent!r},{regroup!r},remove=['model'])")
 component=ok(f"__result__=layout_nodes({large_parent!r},mode='component',boxes=['asset'],profile='readable')")['result']
 assert component['layout_status']=='passed' and component['movable_node_count']==620
 assert component['leaf_box_count']==2 and component['obstacle_overlap_count']==0,component
 # Explicit semantic nesting belongs to the author. Layout of either level
 # preserves the other level, public wiring, parameter references and the
 # actual consumer after a source control changes.
 nested=ok(
  f"p=tab_create('/obj','geo',name='__subnet_handoff_{suffix}')\n"
  "ctrl=tab_create(p,'null',name='CTRL')\n"
  "create_spare_parms(ctrl,spec=[{'type':'float','name':'width','default':2}])\n"
  "source=tab_create(p,'box',name='SOURCE')\n"
  "module=tab_create(p,'subnet',name='MODULE',inputs=[source])\n"
  "entry=tab_create(module,'null',name='IN_SOURCE')\n"
  "branches=[];inside=[entry.path()]\n"
  "for i in range(48):\n"
  " a=tab_create(module,'null',name='branch%02d_a'%i,inputs=[entry])\n"
  " b=tab_create(module,'null',name='branch%02d_b'%i,inputs=[a])\n"
  " branches.append(b);inside.extend([a.path(),b.path()])\n"
  "merged=tab_create(module,'merge',name='ASSEMBLE',inputs=branches)\n"
  "published=sop_set_output(merged,output_index=0)['public_output']['node']\n"
  "inside.extend([merged.path(),published])\n"
  "consumer=tab_create(p,'null',name='OUT',inputs=[module])\n"
  "network_boxes(module,[{'name':'model','members':inside}])\n"
  "network_boxes(p,[{'name':'controls','members':[ctrl.path()],'role':'controls'},"
  "{'name':'assembly','members':[source.path(),module.path()]},"
  "{'name':'output','members':[consumer.path()],'role':'output'}])\n"
  "__result__={'parent':p.path(),'module':module.path(),'source':source.path(),"
  "'ctrl':ctrl.path(),'consumer':consumer.path(),'inside':inside}")['result']
 subnet_parent=nested['parent'];network=hou.node(subnet_parent);module=hou.node(nested['module'])
 # Native indirect input initialization is fixture setup, not an escape from
 # production ownership or a path-based source recovery rule.
 module.node('IN_SOURCE').setInput(0,module.indirectInputs()[0])
 expression='ch("../CTRL/width")';hou.node(nested['source']).parm('sizex').setExpression(expression,hou.exprLanguage.Hscript)
 consumer=hou.node(nested['consumer'])
 assert abs(consumer.geometry().boundingBox().sizevec()[0]-2)<1e-6
 outside_positions={node.path():tuple(node.position()) for node in network.children()}
 outside_wires={node.path():tuple(item.path() if item else None for item in node.inputs()) for node in network.children()}
 inside_ids={node.sessionId() for node in module.children()}
 inside_connections={node.path():wiring(node) for node in module.children()}
 inner=ok(f"__result__=layout_nodes({module.path()!r},mode='handoff',boxes=['model'],profile='readable')")['result']
 assert inner['layout_status']=='passed' and not inner['clearance_failures'],inner
 bounds=boxes._box_rect(module.findNetworkBox('model')).as_list();assert bounds[2]-bounds[0]<200,bounds
 assert {node.path():tuple(node.position()) for node in network.children()}==outside_positions
 assert {node.path():tuple(item.path() if item else None for item in node.inputs()) for node in network.children()}==outside_wires
 assert {node.sessionId() for node in module.children()}==inside_ids
 assert {node.path():wiring(node) for node in module.children()}==inside_connections
 inside_positions={node.path():tuple(node.position()) for node in module.children()}
 outer=ok(f"__result__=layout_nodes({network.path()!r},mode='handoff',boxes=['controls','assembly','output'],profile='readable')")['result']
 assert outer['layout_status']=='passed' and not outer['clearance_failures'],outer
 assert {node.path():tuple(node.position()) for node in module.children()}==inside_positions
 assert {node.path():wiring(node) for node in module.children()}==inside_connections
 assert hou.node(nested['source']).parm('sizex').expression()==expression
 ok(f"set_parms({nested['ctrl']!r},{{'width':4}})\ncook_node({nested['consumer']!r})")
 assert abs(consumer.geometry().boundingBox().sizevec()[0]-4)<1e-6
 assert not consumer.errors() and {node.sessionId() for node in module.children()}==inside_ids
 print('handoff layout contract passed on '+hou.applicationVersionString())
finally:
 if subnet_parent and hou.node(subnet_parent) is not None:hou.node(subnet_parent).destroy()
 if large_parent and hou.node(large_parent) is not None:hou.node(large_parent).destroy()
 if parent and hou.node(parent) is not None:hou.node(parent).destroy()
