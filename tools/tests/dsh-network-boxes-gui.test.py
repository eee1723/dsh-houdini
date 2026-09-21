"""Sacrificial GUI fixture for native Network Box colors/undo/save-reopen."""
from pathlib import Path
import json,os,sys,traceback,uuid
import hdefereval,hou

OUT=Path(os.environ['DSH_BOX_GUI_DIR']);ROOT=Path(os.environ['DSH_BOX_GUI_REPO'])
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))

def run():
 try:
  import dsh_bridge as bridge
  import dsh_network_boxes as boxes
  import dsh_hou_helpers as helpers
  session='box-gui-'+uuid.uuid4().hex[:8]
  def call(code):
   result=bridge.run_code(code,owner_session=session,owner_call=uuid.uuid4().hex)
   if not result['ok']:raise RuntimeError(result)
   return result
  parent=call("p=tab_create('/obj','geo',name='box_gui_fixture')\n__result__=p.path()")['result']
  paths=[]
  for index in range(18):
   path=call(f"__result__=tab_create({parent!r},'null',name='node_{index:02d}').path()")['result'];paths.append(path)
   hou.node(path).setPosition(hou.Vector2((index%6)*2.4,-(index//6)*2.0))
  groups=[
   {'name':'controls','label':'User controls','role':'controls','members':paths[0:2]},
   {'name':'placement','label':'Placement and driving attributes','role':'placement','members':paths[2:6]},
   {'name':'sources','label':'Replaceable source geometry','role':'source','members':paths[6:10]},
   {'name':'assembly','label':'Processing and assembly','role':'assembly','members':paths[10:16]},
   {'name':'output','label':'Published output and delivery','role':'output','members':paths[16:18]},
  ]
  dry=call(f"__result__=network_boxes({parent!r},{groups!r},dry_run=True)")['result']
  applied=call(f"__result__=network_boxes({parent!r},{groups!r},expected_plan={dry['plan_sha256']!r})")
  assert applied['result']['applied'] and applied['execution']['impact']['attempted'] is False
  for source,target in ((1,2),(5,6),(9,10),(15,16)):
   call(f"connect({paths[source]!r},{paths[target]!r})")
  foreign=hou.node(parent).createNode('null','fixed_foreign');foreign.setPosition(hou.Vector2(0,-8))
  foreign_box=hou.node(parent).createNetworkBox('fixed_foreign_box');foreign_box.addItem(foreign);foreign_box.setBounds(hou.BoundingRect(-2,-10,3,-6))
  note=hou.node(parent).createStickyNote('fixed_review_note');note.setText('Fixed review note');note.setPosition(hou.Vector2(8,-6));note.setSize(hou.Vector2(4,2))
  dot=hou.node(parent).createNetworkDot();dot.setPosition(hou.Vector2(14,-4))
  service_node=hou.node(parent).createNode('null','service_node');service_node.setPosition(hou.Vector2(14,0))
  service_node.setUserData(helpers._RENDER_OWNER_KEY,helpers._RENDER_OWNER_VALUE)
  service_box=helpers._render_service_box(hou.node(parent),helpers._RENDER_OBJ_BOX_NAME,[service_node])
  obstacle_before={'node':[float(v) for v in foreign.position()],
                   'box':[float(v) for v in (*foreign_box.position(),*foreign_box.size())],
                   'note':[float(v) for v in (*note.position(),*note.size())],
                   'dot':[float(v) for v in dot.position()],
                   'service_node':[float(v) for v in service_node.position()],
                   'service_box':[float(v) for v in (*service_box.position(),*service_box.size())]}
  handoff_names=[row['name'] for row in groups]
  handoff_dry=call(f"__result__=layout_nodes({parent!r},mode='handoff',boxes={handoff_names!r},dry_run=True)")['result']
  handoff=call(f"__result__=layout_nodes({parent!r},mode='handoff',boxes={handoff_names!r},expected_plan={handoff_dry['plan_sha256']!r})")['result']
  assert handoff['layout_status']=='passed' and handoff['node_overlap_count']==0 and handoff['box_overlap_count']==0
  assert handoff['obstacle_overlap_count']==0 and not handoff['containment_failures']
  assert not handoff['clearance_failures'] and handoff['achieved_clearances']==handoff['minimum_clearances']
  fresh=call(f"__result__=layout_nodes({parent!r},mode='handoff',boxes={handoff_names!r},dry_run=True)")['result']
  handoff_noop=call(f"__result__=layout_nodes({parent!r},mode='handoff',boxes={handoff_names!r},expected_plan={fresh['plan_sha256']!r})")
  assert not handoff_noop['result']['applied'] and handoff_noop['result']['scene_writes']==0
  component=[{'name':'structure_component','label':'STRUCTURE component','role':'component',
              'boxes':['placement','sources','assembly'],'color':[.22,.38,.58]}]
  component_dry=call(f"__result__=network_boxes({parent!r},{component!r},dry_run=True)")['result']
  component_apply=call(f"__result__=network_boxes({parent!r},{component!r},expected_plan={component_dry['plan_sha256']!r})")['result']
  component_box=hou.node(parent).findNetworkBox('structure_component')
  assert component_apply['applied'] and {box.name() for box in component_box.networkBoxes()}=={'placement','sources','assembly'}
  component_layout_dry=call(f"__result__=layout_nodes({parent!r},mode='component',boxes=['structure_component'],dry_run=True)")['result']
  component_layout=call(f"__result__=layout_nodes({parent!r},mode='component',boxes=['structure_component'],expected_plan={component_layout_dry['plan_sha256']!r})")['result']
  assert component_layout['layout_status']=='passed' and component_layout['leaf_box_overlap_count']==0
  assert obstacle_before=={'node':[float(v) for v in foreign.position()],
                           'box':[float(v) for v in (*foreign_box.position(),*foreign_box.size())],
                           'note':[float(v) for v in (*note.position(),*note.size())],
                           'dot':[float(v) for v in dot.position()],
                           'service_node':[float(v) for v in service_node.position()],
                           'service_box':[float(v) for v in (*service_box.position(),*service_box.size())]}
  before={box.name():{'identity':int(box.sessionId()),'label':box.comment(),
      'color':[float(v) for v in box.color().rgb()],
      'members':sorted(item.path() for item in box.items(recurse=False)),
      'bounds':[float(v) for v in (*box.position(),*box.size())]}
      for box in hou.node(parent).networkBoxes()}
  positions={path:[float(v) for v in hou.node(path).position()] for path in paths}
  changed=[dict(row) for row in groups];changed[3]={**changed[3],'label':'Temporary undo label'}
  changed_plan=call(f"__result__=network_boxes({parent!r},{changed!r},dry_run=True)")['result']
  rolled=bridge.run_code(
      f"network_boxes({parent!r},{changed!r},expected_plan={changed_plan['plan_sha256']!r})\nraise RuntimeError('gui later failure')",
      owner_session=session,owner_call='later-failure')
  assert not rolled['ok'] and rolled['rollback']['applied'] and rolled['rollback']['network_boxes']['ok']
  assert hou.node(parent).findNetworkBox('assembly').comment()=='Processing and assembly'
  assert positions=={path:[float(v) for v in hou.node(path).position()] for path in paths}
  rollback_cases=[{'case':'single_update','entry_count':rolled['rollback']['network_boxes']['entry_count']}]
  extra=call(f"__result__=tab_create({parent!r},'null',name='extra').path()")['result']
  create={'name':'temp_multi','label':'first','role':'assembly','members':[extra]}
  update={**create,'label':'second'}
  multi=bridge.run_code(
      f"a=network_boxes({parent!r},[{create!r}],dry_run=True)\nnetwork_boxes({parent!r},[{create!r}],expected_plan=a['plan_sha256'])\n"
      f"b=network_boxes({parent!r},[{update!r}],dry_run=True)\nnetwork_boxes({parent!r},[{update!r}],expected_plan=b['plan_sha256'])\nraise RuntimeError('multi')",
      owner_session=session,owner_call='create-update')
  assert not multi['ok'] and multi['rollback']['network_boxes']['ok'] and hou.node(parent).findNetworkBox('temp_multi') is None
  rollback_cases.append({'case':'create_update','entry_count':multi['rollback']['network_boxes']['entry_count']})
  create_remove=bridge.run_code(
      f"a=network_boxes({parent!r},[{create!r}],dry_run=True)\nnetwork_boxes({parent!r},[{create!r}],expected_plan=a['plan_sha256'])\n"
      f"b=network_boxes({parent!r},[],remove=['temp_multi'],dry_run=True)\nnetwork_boxes({parent!r},[],remove=['temp_multi'],expected_plan=b['plan_sha256'])\nraise RuntimeError('create-remove')",
      owner_session=session,owner_call='create-remove')
  assert not create_remove['ok'] and create_remove['rollback']['network_boxes']['ok'] and hou.node(parent).findNetworkBox('temp_multi') is None
  rollback_cases.append({'case':'create_remove','entry_count':create_remove['rollback']['network_boxes']['entry_count']})
  update1=[dict(row) for row in groups];update1[0]={**update1[0],'label':'first update'}
  update2=[dict(row) for row in groups];update2[0]={**update2[0],'label':'second update'}
  twice=bridge.run_code(
      f"a=network_boxes({parent!r},{update1!r},dry_run=True)\nnetwork_boxes({parent!r},{update1!r},expected_plan=a['plan_sha256'])\n"
      f"b=network_boxes({parent!r},{update2!r},dry_run=True)\nnetwork_boxes({parent!r},{update2!r},expected_plan=b['plan_sha256'])\nraise RuntimeError('twice')",
      owner_session=session,owner_call='two-updates')
  assert not twice['ok'] and twice['rollback']['network_boxes']['ok'] and hou.node(parent).findNetworkBox('controls').comment()=='User controls'
  rollback_cases.append({'case':'two_updates','entry_count':twice['rollback']['network_boxes']['entry_count']})
  selected=paths[:2];selected_before={path:[float(v) for v in hou.node(path).position()] for path in selected}
  moved=bridge.run_code(
      f"layout_nodes({parent!r},nodes={selected!r},mode='flow')\n"
      f"a=network_boxes({parent!r},{update1!r},dry_run=True)\nnetwork_boxes({parent!r},{update1!r},expected_plan=a['plan_sha256'])\nraise RuntimeError('move-before-box')",
      owner_session=session,owner_call='move-before-box')
  assert not moved['ok'] and moved['rollback']['network_boxes']['ok']
  assert selected_before=={path:[float(v) for v in hou.node(path).position()] for path in selected}
  rollback_cases.append({'case':'move_before_group','entry_count':moved['rollback']['network_boxes']['entry_count']})
  renamed_parent='/obj/box_gui_renamed'
  renamed_groups=[{**row,'members':[member.replace(parent,renamed_parent) for member in row['members']]}
                  for row in update1]
  parent_rename=bridge.run_code(
      f"rename_node({parent!r},'box_gui_renamed')\na=network_boxes({renamed_parent!r},{renamed_groups!r},dry_run=True)\n"
      f"network_boxes({renamed_parent!r},{renamed_groups!r},expected_plan=a['plan_sha256'])\nraise RuntimeError('parent rename')",
      owner_session=session,owner_call='parent-rename')
  assert not parent_rename['ok'] and parent_rename['rollback']['network_boxes']['ok']
  assert hou.node(parent) is not None and hou.node(renamed_parent) is None
  rollback_cases.append({'case':'parent_rename','entry_count':parent_rename['rollback']['network_boxes']['entry_count']})
  after_delete=[dict(row) for row in groups]
  after_delete[2]={**after_delete[2],'members':paths[7:10],'label':'after member delete'}
  member_delete=bridge.run_code(
      f"delete_node({paths[6]!r})\na=network_boxes({parent!r},{after_delete!r},dry_run=True)\n"
      f"network_boxes({parent!r},{after_delete!r},expected_plan=a['plan_sha256'])\nraise RuntimeError('member delete')",
      owner_session=session,owner_call='member-delete')
  assert not member_delete['ok'],member_delete
  assert member_delete.get('rollback',{}).get('network_boxes',{}).get('ok'),member_delete
  assert member_delete['rollback']['network_boxes']['entry_count']==2,member_delete
  assert hou.node(paths[6]) is not None and {item.path() for item in hou.node(parent).findNetworkBox('sources').items(recurse=False)}==set(paths[6:10])
  rollback_cases.append({'case':'member_delete','entry_count':member_delete['rollback']['network_boxes']['entry_count']})
  hip=(OUT/'network-boxes.hip').as_posix();hou.hipFile.save(hip)
  hou.hipFile.load(hip,suppress_save_prompt=True)
  reopened=hou.node(parent);after={box.name():{'label':box.comment(),
      'color':[float(v) for v in box.color().rgb()],
      'members':sorted(item.path() for item in box.items(recurse=False))}
      for box in reopened.networkBoxes()}
  assert set(after)==set(before)
  for name in handoff_names:
   assert after[name]['label']==before[name]['label'] and after[name]['color']==before[name]['color'] and after[name]['members']==before[name]['members']
  assert {box.name() for box in reopened.findNetworkBox('structure_component').networkBoxes()}=={'placement','sources','assembly'}
  assert all(reopened.findNetworkBox(name).parentNetworkBox()==reopened.findNetworkBox('structure_component')
             for name in ('placement','sources','assembly'))
  assert all(boxes.box_provenance(box,session)['status']=='foreign' for box in reopened.networkBoxes())
  reopened_positions={path:[float(v) for v in hou.node(path).position()] for path in paths}
  max_position_delta=max(abs(a-b) for path in paths for a,b in zip(positions[path],reopened_positions[path]))
  assert max_position_delta<=1e-6,max_position_delta
  report={'ok':True,'version':hou.applicationVersionString(),'hip':hip,
          'scope':'native GUI Network Box color/node+box membership, comfortable leaf handoff, one component container, Bridge undo and save/reopen',
          'before':before,'after':after,'positions_preserved':True,
          'max_position_delta':max_position_delta,
          'handoff':handoff,'handoff_noop':handoff_noop['result'],'component':component_apply,
          'component_layout':component_layout,
          'fixed_obstacles_preserved':True,'fixed_obstacles':obstacle_before,
          'rollback':rolled['rollback'],'rollback_cases':rollback_cases,
          'transaction':rolled['transaction']}
  (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  hou.exit(exit_code=0,suppress_save_prompt=True)
 except Exception:
  (OUT/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
  hou.exit(exit_code=1,suppress_save_prompt=True)

hdefereval.executeDeferred(run)
