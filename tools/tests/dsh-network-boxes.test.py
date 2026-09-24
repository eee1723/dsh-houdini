"""H21/H22 governed Network Box, ownership and local recovery regression."""
from __future__ import annotations
from pathlib import Path
import importlib,sys,tempfile,uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge
import dsh_hou_helpers as h
import dsh_network_boxes as boxes

suffix=uuid.uuid4().hex[:8];session='boxes-'+suffix

def call(code,owner=session):
    result=bridge.run_code(code,owner_session=owner,owner_call='call-'+uuid.uuid4().hex[:6])
    return result

def ok(code,owner=session):
    result=call(code,owner);assert result['ok'],result;return result

def preview(parent,groups,remove=None,allow=None):
    args=f", remove={remove!r}" if remove is not None else ''
    if allow is not None:args+=f", allow_foreign={allow!r}"
    return ok(f"__result__=network_boxes({parent!r},{groups!r}{args},dry_run=True)")['result']

def apply(parent,groups,plan,remove=None,allow=None):
    args=f", remove={remove!r}" if remove is not None else ''
    if allow is not None:args+=f", allow_foreign={allow!r}"
    return call(f"__result__=network_boxes({parent!r},{groups!r}{args},expected_plan={plan!r})")

with boxes.transaction_journal() as budget_journal:
    synthetic={'boxes':[],'nodes':[],'created_box_identities':list(range(33))}
    boxes._journal(synthetic,'budget-fixture')
    assert budget_journal['boxes']==33
    boxes._check_journal_capacity(31,0)
    try:boxes._check_journal_capacity(32,0)
    except ValueError as error:assert 'budget' in str(error)
    else:raise AssertionError('cumulative creation budget should reject before write')

parent=None
try:
    parent=ok(f"p=tab_create('/obj','geo',name='__boxes_{suffix}')\n__result__=p.path()")['result']
    names=['ctrl','points','proto_a','proto_b','assemble','OUT','spare']
    paths={}
    for name in names:
        paths[name]=ok(f"__result__=tab_create({parent!r},'null',name={name!r}).path()")['result']
    ok(f"__result__=connect({paths['proto_a']!r},{paths['assemble']!r})")
    ok(f"__result__=connect({paths['assemble']!r},{paths['OUT']!r})")
    hou.node(paths['ctrl']).setSelected(True,clear_all_selected=True)
    before_positions={name:tuple(float(v) for v in hou.node(path).position()) for name,path in paths.items()}
    before_cook={path:hou.node(path).needsToCook() for path in paths.values()}
    before_flags={path:(hou.node(path).isDisplayFlagSet(),hou.node(path).isRenderFlagSet()) for path in paths.values()}
    before_frame=float(hou.frame());before_selection=tuple(node.path() for node in hou.selectedNodes())
    groups=[
      {'name':'controls','label':'User controls','role':'controls','members':[paths['ctrl']]},
      {'name':'placement','label':'Placement stream','role':'placement','members':[paths['points']]},
      {'name':'sources','label':'Replaceable prototypes','role':'source','members':[paths['proto_a'],paths['proto_b']]},
      {'name':'assembly','label':'Assembly processing','role':'assembly','members':[paths['assemble']]},
      {'name':'delivery','label':'Published output','role':'output','members':[paths['OUT']]},
    ]
    bad_component={'name':'bad_component','label':'Must wrap leaves','role':'component',
                   'members':[paths['ctrl']]}
    rejected_component=call(f"__result__=network_boxes({parent!r},[{bad_component!r}],dry_run=True)")
    assert not rejected_component['ok'] and 'component role requires boxes' in rejected_component['error']
    dry=preview(parent,groups)
    assert dry['dry_run'] and not dry['applied'] and dry['scene_writes']==0
    query_blocked=bridge.run_code(f"network_boxes({parent!r},{groups!r},dry_run=True)",read_only=True,owner_session=session)
    assert not query_blocked['ok'] and 'read-only' in query_blocked['error']
    dry_envelope=call(f"__result__=network_boxes({parent!r},{groups!r},dry_run=True)")
    assert dry_envelope['transaction']['status']=='no_scene_change',dry_envelope
    created=apply(parent,groups,dry['plan_sha256']);assert created['ok'],created
    result=created['result'];assert result['applied'] and set(result['created'])=={g['name'] for g in groups}
    assert result['layout_status']=='not_performed'
    assert created['execution']['impact']['attempted'] is False,created['execution']['impact']
    palette=boxes.ROLE_COLORS
    for group in groups:
        box=hou.node(parent).findNetworkBox(group['name']);assert box is not None
        assert {item.path() for item in box.items(recurse=False)}==set(group['members'])
        assert all(abs(a-b)<1e-5 for a,b in zip(box.color().rgb(),palette[group['role']]))
    assert {name:tuple(float(v) for v in hou.node(path).position()) for name,path in paths.items()}==before_positions
    assert {path:hou.node(path).needsToCook() for path in paths.values()}==before_cook
    assert {path:(hou.node(path).isDisplayFlagSet(),hou.node(path).isRenderFlagSet()) for path in paths.values()}==before_flags
    assert float(hou.frame())==before_frame and tuple(node.path() for node in hou.selectedNodes())==before_selection
    assert hou.node(paths['assemble']).input(0)==hou.node(paths['proto_a'])
    assert hou.node(paths['OUT']).input(0)==hou.node(paths['assemble'])
    assert all(isinstance(key,tuple) and key[0]=='network_box' for key in boxes._OWNED_BOXES)
    broad=call(f"__result__=layout_nodes({parent!r},mode='children')")
    assert not broad['ok'] and 'scatter Network Box members' in broad['error'],broad
    assert {name:tuple(float(v) for v in hou.node(path).position()) for name,path in paths.items()}==before_positions
    broad_flow=call(f"__result__=layout_nodes({parent!r},mode='flow')")
    assert not broad_flow['ok'] and 'mode=\'handoff\'' in broad_flow['error'],broad_flow

    # Component presentation hierarchy is exactly two levels: first create
    # and lay out leaf role boxes, then wrap existing leaves in one container.
    nested=ok(
        f"p=tab_create('/obj','geo',name='__nested_boxes_{suffix}')\n"
        "s=tab_create(p,'box',name='source')\nq=tab_create(p,'null',name='points')\n"
        "c=tab_create(p,'copytopoints',name='copy',inputs=[s,q])\n"
        "o=tab_create(p,'null',name='OUT',inputs=[c])\n"
        "__result__={'parent':p.path(),'nodes':[s.path(),q.path(),c.path(),o.path()]}")['result']
    nested_parent=nested['parent']
    leaf_groups=[
      {'name':'part_source','label':'PART source','role':'source','members':[nested['nodes'][0]]},
      {'name':'part_place','label':'PART template/copy','role':'placement','members':nested['nodes'][1:3]},
      {'name':'part_out','label':'PART output','role':'output','members':[nested['nodes'][3]]},
    ]
    leaf_plan=preview(nested_parent,leaf_groups);assert apply(nested_parent,leaf_groups,leaf_plan['plan_sha256'])['ok']
    leaf_names=[row['name'] for row in leaf_groups]
    layout_plan=call(f"__result__=layout_nodes({nested_parent!r},mode='handoff',boxes={leaf_names!r},dry_run=True)")
    assert layout_plan['ok'] and layout_plan['result']['layout_status']=='planned',layout_plan
    layout_apply=call(f"__result__=layout_nodes({nested_parent!r},mode='handoff',boxes={leaf_names!r},expected_plan={layout_plan['result']['plan_sha256']!r})")
    assert layout_apply['ok'] and layout_apply['result']['layout_status']=='passed',layout_apply
    component=[{'name':'part_component','label':'PART component','role':'component','boxes':leaf_names,'color':[.2,.35,.55]}]
    component_plan=preview(nested_parent,component)
    assert component_plan['boxes'][0]['boxes']==leaf_names and component_plan['boxes'][0]['members']==[]
    component_apply=apply(nested_parent,component,component_plan['plan_sha256']);assert component_apply['ok'],component_apply
    outer=hou.node(nested_parent).findNetworkBox('part_component')
    assert {box.name() for box in outer.networkBoxes()}==set(leaf_names)
    assert all(hou.node(nested_parent).findNetworkBox(name).parentNetworkBox()==outer for name in leaf_names)
    assert all(hou.node(path).parentNetworkBox().name() in leaf_names for path in nested['nodes'])
    component_layout_plan=call(f"__result__=layout_nodes({nested_parent!r},mode='component',boxes=['part_component'],dry_run=True)")
    assert component_layout_plan['ok'] and component_layout_plan['result']['layout_status']=='planned',component_layout_plan
    component_layout=call(f"__result__=layout_nodes({nested_parent!r},mode='component',boxes=['part_component'],expected_plan={component_layout_plan['result']['plan_sha256']!r})")
    assert component_layout['ok'] and component_layout['result']['layout_status']=='passed',component_layout
    assert component_layout['result']['leaf_box_overlap_count']==0 and component_layout['result']['component_box_overlap_count']==0
    component_layout_fresh=call(f"__result__=layout_nodes({nested_parent!r},mode='component',boxes=['part_component'],dry_run=True)")
    component_layout_noop=call(f"__result__=layout_nodes({nested_parent!r},mode='component',boxes=['part_component'],expected_plan={component_layout_fresh['result']['plan_sha256']!r})")
    assert component_layout_noop['ok'] and component_layout_noop['result']['scene_writes']==0
    wrong_mode=call(f"__result__=layout_nodes({nested_parent!r},mode='component',boxes=['part_source'],dry_run=True)")
    assert not wrong_mode['ok'] and 'top-level component container' in wrong_mode['error']
    repeated=preview(nested_parent,component);repeated_apply=apply(nested_parent,component,repeated['plan_sha256'])
    assert repeated_apply['ok'] and repeated_apply['result']['scene_writes']==0
    mixed={**component[0],'members':[nested['nodes'][0]]}
    mixed_call=call(f"__result__=network_boxes({nested_parent!r},[{mixed!r}],dry_run=True)")
    assert not mixed_call['ok'] and 'exactly one' in mixed_call['error']
    deep={'name':'too_deep','label':'Too deep','role':'component','boxes':['part_component']}
    deep_call=call(f"__result__=network_boxes({nested_parent!r},[{deep!r}],dry_run=True)")
    assert not deep_call['ok'] and 'already a component container' in deep_call['error']
    remove_outer=preview(nested_parent,[],remove=['part_component'])
    assert apply(nested_parent,[],remove_outer['plan_sha256'],remove=['part_component'])['ok']
    assert all(hou.node(nested_parent).findNetworkBox(name).parentNetworkBox() is None for name in leaf_names)
    rolled=call(
        f"a=network_boxes({nested_parent!r},{component!r},dry_run=True)\n"
        f"network_boxes({nested_parent!r},{component!r},expected_plan=a['plan_sha256'])\n"
        "raise RuntimeError('rollback nested component container')")
    assert not rolled['ok'] and rolled['rollback']['applied'] and rolled['rollback']['network_boxes']['ok'],rolled
    assert hou.node(nested_parent).findNetworkBox('part_component') is None
    assert all(hou.node(nested_parent).findNetworkBox(name).parentNetworkBox() is None for name in leaf_names)
    assert call(f"__result__=delete_node({nested_parent!r})")['ok']

    multi_node=ok(f"__result__=tab_create({parent!r},'null',name='multi_node').path()")['result']
    multi_group={'name':'temp_multi','label':'First','role':'assembly','members':[multi_node]}
    multi_update={**multi_group,'label':'Second'}
    multi=call(
        f"a=network_boxes({parent!r},[{multi_group!r}],dry_run=True)\n"
        f"network_boxes({parent!r},[{multi_group!r}],expected_plan=a['plan_sha256'])\n"
        f"b=network_boxes({parent!r},[{multi_update!r}],dry_run=True)\n"
        f"network_boxes({parent!r},[{multi_update!r}],expected_plan=b['plan_sha256'])\n"
        "raise RuntimeError('create update failure')")
    assert not multi['ok'] and multi['rollback']['applied'] and multi['rollback']['network_boxes']['ok'],multi
    assert hou.node(parent).findNetworkBox('temp_multi') is None
    assert not any(entry.get('name_at_creation')=='temp_multi' for entry in boxes._OWNED_BOXES.values())

    create_remove=call(
        f"a=network_boxes({parent!r},[{multi_group!r}],dry_run=True)\n"
        f"network_boxes({parent!r},[{multi_group!r}],expected_plan=a['plan_sha256'])\n"
        f"b=network_boxes({parent!r},[],remove=['temp_multi'],dry_run=True)\n"
        f"network_boxes({parent!r},[],remove=['temp_multi'],expected_plan=b['plan_sha256'])\n"
        "raise RuntimeError('create remove failure')")
    assert not create_remove['ok'] and create_remove['rollback']['network_boxes']['ok'],create_remove
    assert hou.node(parent).findNetworkBox('temp_multi') is None

    twice1=[dict(row) for row in groups];twice1[0]={**twice1[0],'label':'First temporary'}
    twice2=[dict(row) for row in groups];twice2[0]={**twice2[0],'label':'Second temporary'}
    two_updates=call(
        f"a=network_boxes({parent!r},{twice1!r},dry_run=True)\n"
        f"network_boxes({parent!r},{twice1!r},expected_plan=a['plan_sha256'])\n"
        f"b=network_boxes({parent!r},{twice2!r},dry_run=True)\n"
        f"network_boxes({parent!r},{twice2!r},expected_plan=b['plan_sha256'])\n"
        "raise RuntimeError('two update failure')")
    assert not two_updates['ok'] and two_updates['rollback']['network_boxes']['ok'],two_updates
    assert hou.node(parent).findNetworkBox('controls').comment()=='User controls'

    before_undo_positions={path:tuple(float(v) for v in hou.node(path).position()) for path in (paths['ctrl'],paths['points'])}
    moved_then_group=call(
        f"layout_nodes({parent!r},nodes={[paths['ctrl'],paths['points']]!r},mode='flow')\n"
        f"a=network_boxes({parent!r},{twice1!r},dry_run=True)\n"
        f"network_boxes({parent!r},{twice1!r},expected_plan=a['plan_sha256'])\n"
        "raise RuntimeError('movement before grouping failure')")
    assert not moved_then_group['ok'] and moved_then_group['rollback']['network_boxes']['ok'],moved_then_group
    assert {path:tuple(float(v) for v in hou.node(path).position()) for path in before_undo_positions}==before_undo_positions

    # A named existing network remains denied by default, but an explicit
    # user authorization can cover the exact foreign boxes and their members.
    foreign_layout=ok(
        "p=tab_create('/obj','geo',name='__foreign_layout_"+suffix+"')\n"
        "a=tab_create(p,'box',name='source')\n"
        "b=tab_create(p,'xform',name='process',inputs=[a])\n"
        "o=tab_create(p,'null',name='OUT',inputs=[b])\n"
        "__result__={'parent':p.path(),'nodes':[a.path(),b.path(),o.path()]}",owner='other-layout')['result']
    foreign_groups=[
      {'name':'foreign_source','label':'Existing source','role':'source','members':[foreign_layout['nodes'][0]]},
      {'name':'foreign_process','label':'Existing processing','role':'assembly','members':[foreign_layout['nodes'][1]]},
      {'name':'foreign_output','label':'Existing output','role':'output','members':[foreign_layout['nodes'][2]]},
    ]
    foreign_box_plan=preview(foreign_layout['parent'],foreign_groups,allow='fixture creates another author network')
    assert apply(foreign_layout['parent'],foreign_groups,foreign_box_plan['plan_sha256'],allow='fixture creates another author network')['ok']
    denied_layout=call(f"__result__=layout_nodes({foreign_layout['parent']!r},mode='handoff',boxes={[g['name'] for g in foreign_groups]!r},dry_run=True)")
    assert not denied_layout['ok'] and 'ownership guard' in denied_layout['error'],denied_layout
    layout_reason='user explicitly requested layout repair of this existing network'
    allowed_plan=call(f"__result__=layout_nodes({foreign_layout['parent']!r},mode='handoff',boxes={[g['name'] for g in foreign_groups]!r},dry_run=True,allow_foreign={layout_reason!r})")
    assert allowed_plan['ok'] and allowed_plan['result']['layout_status']=='planned',allowed_plan
    allowed_apply=call(f"__result__=layout_nodes({foreign_layout['parent']!r},mode='handoff',boxes={[g['name'] for g in foreign_groups]!r},expected_plan={allowed_plan['result']['plan_sha256']!r},allow_foreign={layout_reason!r})")
    assert allowed_apply['ok'] and allowed_apply['result']['layout_status']=='passed',allowed_apply
    assert call(f"__result__=delete_node({foreign_layout['parent']!r},allow_foreign={layout_reason!r})")['ok']

    renamed_parent_path='/obj/renamed_parent_'+suffix
    renamed_groups=[]
    for row in twice1:
        renamed_groups.append({**row,'members':[member.replace(parent,renamed_parent_path) for member in row['members']]})
    parent_rename=call(
        f"rename_node({parent!r},{('renamed_parent_'+suffix)!r})\n"
        f"a=network_boxes({renamed_parent_path!r},{renamed_groups!r},dry_run=True)\n"
        f"network_boxes({renamed_parent_path!r},{renamed_groups!r},expected_plan=a['plan_sha256'])\n"
        "raise RuntimeError('parent rename then box failure')")
    assert not parent_rename['ok'] and parent_rename['rollback']['network_boxes']['ok'],parent_rename
    assert hou.node(parent) is not None and hou.node(renamed_parent_path) is None
    assert boxes.box_provenance(hou.node(parent).findNetworkBox('controls'),session)['status']=='owned_current_session'

    after_delete=[dict(row) for row in groups]
    after_delete[2]={**after_delete[2],'label':'Intermediate after member delete','members':[paths['proto_b']]}
    member_delete=call(
        f"delete_node({paths['proto_a']!r})\n"
        f"a=network_boxes({parent!r},{after_delete!r},dry_run=True)\n"
        f"network_boxes({parent!r},{after_delete!r},expected_plan=a['plan_sha256'])\n"
        "raise RuntimeError('member delete then box failure')")
    assert not member_delete['ok'] and member_delete['rollback']['network_boxes']['ok'],member_delete
    assert hou.node(paths['proto_a']) is not None and hou.node(paths['assemble']).input(0)==hou.node(paths['proto_a'])
    assert {item.path() for item in hou.node(parent).findNetworkBox('sources').items(recurse=False)}=={
        paths['proto_a'],paths['proto_b']}

    # Fresh repeated plan is a real no-op, including transaction state.
    again=preview(parent,groups);no_op=apply(parent,groups,again['plan_sha256'])
    assert no_op['ok'] and not no_op['result']['applied'] and no_op['result']['scene_writes']==0
    assert no_op['transaction']['status']=='no_scene_change',no_op

    # A later failure in the same exec uses native undo, then reconciles typed
    # box provenance/presentation without polluting transaction.nodes.
    later=[dict(row) for row in groups];later[0]={**later[0],'label':'temporary same-exec label'}
    later_plan=preview(parent,later)
    rolled=call(f"network_boxes({parent!r},{later!r},expected_plan={later_plan['plan_sha256']!r})\nraise RuntimeError('later same-exec failure')")
    assert not rolled['ok'] and rolled['rollback']['applied'] is True,rolled
    assert rolled['rollback']['network_boxes']['ok'] is True,rolled
    assert rolled['transaction']['status']=='rolled_back' and rolled['transaction']['network_boxes']['entry_count']==1
    assert hou.node(parent).findNetworkBox('controls').comment()=='User controls'
    assert boxes.box_provenance(hou.node(parent).findNetworkBox('controls'),session)['status']=='owned_current_session'

    # Existing customized color survives normal upsert; explicit color replaces it.
    source_box=hou.node(parent).findNetworkBox('sources');source_box.setColor(hou.Color((.11,.22,.33)))
    source_box.setBounds(hou.BoundingRect(-20,-20,20,20));manual_bounds=boxes._box_rect(source_box)
    keep=preview(parent,groups);kept=apply(parent,groups,keep['plan_sha256']);assert kept['ok']
    assert all(abs(a-b)<1e-5 for a,b in zip(source_box.color().rgb(),(.11,.22,.33)))
    assert boxes._rect_close(boxes._box_rect(source_box),manual_bounds)
    recolor=[dict(row) for row in groups]
    recolor[2]={**recolor[2],'color':[.2,.3,.4]}
    explicit=preview(parent,recolor);changed=apply(parent,recolor,explicit['plan_sha256']);assert changed['ok']
    assert all(abs(a-b)<1e-5 for a,b in zip(source_box.color().rgb(),(.2,.3,.4)))
    groups=recolor

    # Stale plan rejects before writes.
    stale=preview(parent,groups);node=hou.node(paths['ctrl']);node.setPosition(node.position()+hou.Vector2(1,0))
    rejected=apply(parent,groups,stale['plan_sha256']);assert not rejected['ok'] and 'stale' in rejected['error']
    node.setPosition(hou.Vector2(*before_positions['ctrl']))

    # Inject a failure after member/label/color writes; local recovery works in hython without undo.
    failing=[dict(row) for row in groups]
    failing[0]={**failing[0],'label':'Changed then restored','members':[paths['ctrl'],paths['spare']], 'color':[.8,.1,.1]}
    planned=preview(parent,failing)
    real_bounds=boxes._content_bounds
    boxes._content_bounds=lambda _nodes:(_ for _ in ()).throw(RuntimeError('injected bounds failure'))
    try:
        with hou.undos.disabler():failed=apply(parent,failing,planned['plan_sha256'])
    finally:boxes._content_bounds=real_bounds
    assert not failed['ok'] and failed['rollback']['supported'] is False,failed
    evidence=failed['evidence'][0];assert evidence['restored'] is True,evidence
    ctrl_box=hou.node(parent).findNetworkBox('controls')
    assert ctrl_box.comment()=='User controls' and {x.path() for x in ctrl_box.items(recurse=False)}=={paths['ctrl']}
    assert hou.node(paths['spare']).parentNetworkBox() is None
    assert tuple(float(v) for v in hou.node(paths['spare']).position())==before_positions['spare']
    restore_plan=preview(parent,failing)
    real_bounds,real_restore=boxes._content_bounds,boxes._restore
    boxes._content_bounds=lambda _nodes:(_ for _ in ()).throw(RuntimeError('second injected failure'))
    def restore_with_report(snapshot):
        errors,remaps=real_restore(snapshot);return errors+['injected restore readback failure'],remaps
    boxes._restore=restore_with_report
    try:
        with hou.undos.disabler():restore_failed=apply(parent,failing,restore_plan['plan_sha256'])
    finally:
        boxes._content_bounds,boxes._restore=real_bounds,real_restore
    assert not restore_failed['ok'] and restore_failed['evidence'][0]['restored'] is False
    assert 'injected restore readback failure' in restore_failed['evidence'][0]['restore_errors']
    assert {x.path() for x in hou.node(parent).findNetworkBox('controls').items(recurse=False)}=={paths['ctrl']}
    raise_plan=preview(parent,failing)
    boxes._content_bounds=lambda _nodes:(_ for _ in ()).throw(RuntimeError('write before recovery exception'))
    boxes._restore=lambda _snapshot:(_ for _ in ()).throw(ValueError('injected recovery exception'))
    try:
        with hou.undos.disabler():recovery_raised=apply(parent,failing,raise_plan['plan_sha256'])
    finally:
        boxes._content_bounds,boxes._restore=real_bounds,real_restore
    raised_evidence=recovery_raised['evidence'][0]
    assert not recovery_raised['ok'] and raised_evidence['phase']=='apply_failure'
    assert raised_evidence['scene_writes']>0 and raised_evidence['restored'] is False
    assert 'injected recovery exception' in raised_evidence['recovery_exception']
    assert recovery_raised['transaction']['status']=='recovery_unverified'
    repair_plan=preview(parent,groups);assert apply(parent,groups,repair_plan['plan_sha256'])['ok']

    native_raise_plan=preview(parent,failing)
    boxes._content_bounds=lambda _nodes:(_ for _ in ()).throw(RuntimeError('write before native recovery'))
    boxes._restore=lambda _snapshot:(_ for _ in ()).throw(ValueError('native recovery exception'))
    try:native_recovery=apply(parent,failing,native_raise_plan['plan_sha256'])
    finally:boxes._content_bounds,boxes._restore=real_bounds,real_restore
    assert not native_recovery['ok'] and native_recovery['rollback']['applied'] is True,native_recovery
    assert native_recovery['rollback']['network_boxes']['ok'] is True,native_recovery
    assert native_recovery['evidence'][0]['journaled'] is True
    assert hou.node(parent).findNetworkBox('controls').comment()=='User controls'

    final_plan_groups=[dict(row) for row in groups];final_plan_groups[0]={**final_plan_groups[0],'label':'readback fault'}
    final_plan=preview(parent,final_plan_groups)
    real_state=boxes._state;state_calls={'count':0,'raised':False}
    def one_readback_failure(box):
        state_calls['count']+=1
        if state_calls['count']>10 and not state_calls['raised']:
            state_calls['raised']=True;raise RuntimeError('final result readback failure')
        return real_state(box)
    boxes._state=one_readback_failure
    try:final_failure=apply(parent,final_plan_groups,final_plan['plan_sha256'])
    finally:boxes._state=real_state
    assert not final_failure['ok'] and final_failure['rollback']['network_boxes']['entry_count']==1,final_failure
    assert final_failure['rollback']['network_boxes']['ok'] is True
    compensated_plan=preview(parent,failing)
    boxes._content_bounds=lambda _nodes:(_ for _ in ()).throw(RuntimeError('compensation then undo'))
    try:compensated=apply(parent,failing,compensated_plan['plan_sha256'])
    finally:boxes._content_bounds=real_bounds
    assert not compensated['ok'] and compensated['rollback']['applied'] is True,compensated
    assert compensated['rollback']['network_boxes']['ok'] is True,compensated
    assert {x.path() for x in hou.node(parent).findNetworkBox('controls').items(recurse=False)}=={paths['ctrl']}

    # Strict argument/structure preflight stays zero-write.
    missing=call(f"__result__=network_boxes({parent!r},{groups!r})")
    assert not missing['ok'] and 'stale or missing' in missing['error']
    assert missing['evidence'][0]['phase']=='preflight' and missing['evidence'][0]['scene_writes']==0
    assert missing['transaction']['status']=='no_scene_change'
    mixed=call(f"rename_node({paths['spare']!r},'spare_temp')\nnetwork_boxes({parent!r},[],dry_run=1)")
    assert not mixed['ok'] and mixed['rollback']['applied'] is True,mixed
    assert mixed['evidence'][-1]['phase']=='preflight' and mixed['evidence'][-1]['scene_writes']==0
    assert hou.node(paths['spare']) is not None and hou.node(parent+'/spare_temp') is None
    for bad_group,needle in (
        ({**groups[0],'role':'status_green'},'unknown'),
        ({**groups[0],'unexpected':1},'name,label,role'),
        ({**groups[0],'members':[paths['ctrl'],paths['ctrl']]},'multiple groups'),
    ):
        bad_call=call(f"__result__=network_boxes({parent!r},[{bad_group!r}],dry_run=True)")
        assert not bad_call['ok'] and needle in bad_call['error'],bad_call
    bad_bool=call(f"__result__=network_boxes({parent!r},[],dry_run=1)")
    assert not bad_bool['ok'] and 'boolean' in bad_bool['error']
    collision={'name':'ctrl','label':'Collision','role':'controls','members':[paths['spare']]}
    occupied=call(f"__result__=network_boxes({parent!r},[{collision!r}],dry_run=True)")
    assert not occupied['ok'] and 'occupied by a node' in occupied['error']
    minimized=hou.node(parent).createNetworkBox('minimized_user');minimized.addItem(hou.node(paths['spare']));minimized.setMinimized(True)
    minimized_group={'name':'minimized_user','label':'Unsupported','role':'source','members':[paths['spare']]}
    unsupported=call(f"__result__=network_boxes({parent!r},[{minimized_group!r}],dry_run=True,allow_foreign='fixture')")
    assert not unsupported['ok'] and 'minimized' in unsupported['error'];minimized.destroy(destroy_contents=False)
    outer=hou.node(parent).createNetworkBox('outer_user');inner=hou.node(parent).createNetworkBox('inner_user')
    outer.addNetworkBox(inner);inner.addItem(hou.node(paths['spare']))
    too_deep=hou.node(parent).createNetworkBox('too_deep_user');too_deep.addNetworkBox(outer)
    deep_group={'name':'deep_target','label':'Unsupported third level','role':'component','boxes':['inner_user']}
    unsupported_nested=call(f"__result__=network_boxes({parent!r},[{deep_group!r}],dry_run=True,allow_foreign='fixture')")
    assert not unsupported_nested['ok'] and ('deeper than one' in unsupported_nested['error'] or 'component container' in unsupported_nested['error'])
    too_deep.removeNetworkBox(outer);outer.removeNetworkBox(inner)
    inner.destroy(destroy_contents=False);outer.destroy(destroy_contents=False);too_deep.destroy(destroy_contents=False)
    sticky=hou.node(parent).createStickyNote('note');note_box=hou.node(parent).createNetworkBox('note_box');note_box.addItem(sticky)
    note_group={'name':'note_box','label':'Unsupported','role':'source','members':[paths['spare']]}
    unsupported_note=call(f"__result__=network_boxes({parent!r},[{note_group!r}],dry_run=True,allow_foreign='fixture')")
    assert not unsupported_note['ok'] and 'non-node' in unsupported_note['error']
    note_box.destroy(destroy_contents=False);sticky.destroy()
    foreign_member=hou.node(parent).createNode('null','foreign_member')
    ctrl_box=hou.node(parent).findNetworkBox('controls');ctrl_box.addItem(foreign_member)
    foreign_member_refusal=call(f"__result__=network_boxes({parent!r},{groups!r},dry_run=True)")
    assert not foreign_member_refusal['ok'] and 'foreign node' in foreign_member_refusal['error']
    ctrl_box.removeItem(foreign_member);foreign_member.destroy()

    # Moving a node out of an unmentioned source box is rejected.
    bad=[dict(row) for row in groups if row['name']!='sources']
    bad[3 if len(bad)>3 else -1]=dict(bad[3 if len(bad)>3 else -1])
    bad[-1]['members']=list(bad[-1]['members'])+[paths['proto_b']]
    refused=call(f"__result__=network_boxes({parent!r},{bad!r},dry_run=True)")
    assert not refused['ok'] and 'unmentioned box' in refused['error'],refused

    # Removal preserves nodes, wires and positions.
    remove_plan=preview(parent,[row for row in groups if row['name']!='delivery'],remove=['delivery'])
    removed=apply(parent,[row for row in groups if row['name']!='delivery'],remove_plan['plan_sha256'],remove=['delivery'])
    assert removed['ok'] and hou.node(parent).findNetworkBox('delivery') is None
    assert hou.node(paths['OUT']) is not None and hou.node(paths['OUT']).input(0)==hou.node(paths['assemble'])
    assert tuple(float(v) for v in hou.node(paths['OUT']).position())==before_positions['OUT']
    groups=[row for row in groups if row['name']!='delivery']

    # A foreign box stays foreign even after an explicitly authorized update.
    foreign=hou.node(parent).createNetworkBox('foreign_user');foreign.addItem(hou.node(paths['spare']))
    foreign_group={'name':'foreign_user','label':'Foreign user box','role':'source','members':[paths['spare']]}
    denied=call(f"__result__=network_boxes({parent!r},[{foreign_group!r}],dry_run=True)")
    assert not denied['ok'] and 'ownership guard' in denied['error'],denied
    reason='user explicitly requested organization of this existing box'
    foreign_dry=preview(parent,[foreign_group],allow=reason)
    foreign_apply=apply(parent,[foreign_group],foreign_dry['plan_sha256'],allow=reason);assert foreign_apply['ok']
    assert boxes.box_provenance(foreign,session)['status']=='foreign'

    # Render-service registration is exact identity protection and cannot be bypassed.
    service_node=hou.node(parent).createNode('null','service_probe')
    service_node.setUserData(h._RENDER_OWNER_KEY,h._RENDER_OWNER_VALUE)
    service=h._render_service_box(hou.node(parent),h._RENDER_OBJ_BOX_NAME,[service_node])
    service_group={'name':service.name(),'label':'no','role':'assembly','members':[service_node.path()]}
    protected=call(f"__result__=network_boxes({parent!r},[{service_group!r}],dry_run=True,allow_foreign='test bypass')")
    assert not protected['ok'] and 'service' in protected['error'].lower(),protected
    service.setName('renamed_service_box')
    renamed_service={**service_group,'name':'renamed_service_box'}
    still_protected=call(f"__result__=network_boxes({parent!r},[{renamed_service!r}],dry_run=True,allow_foreign='test bypass')")
    assert not still_protected['ok'] and 'service' in still_protected['error'].lower(),still_protected
    protected_remove=call(f"__result__=network_boxes({parent!r},[],remove=['renamed_service_box'],dry_run=True,allow_foreign='test bypass')")
    assert not protected_remove['ok'] and 'service' in protected_remove['error'].lower(),protected_remove
    service_parent=hou.node('/obj').createNode('geo','service_parent_'+suffix)
    service_parent.setUserData(h._RENDER_OWNER_KEY,h._RENDER_OWNER_VALUE)
    untagged=service_parent.createNode('null','untagged_child')
    service_parent_group={'name':'child_box','label':'No bypass','role':'assembly','members':[untagged.path()]}
    ancestor_protected=call(f"__result__=network_boxes({service_parent.path()!r},[{service_parent_group!r}],dry_run=True,allow_foreign='test bypass')")
    assert not ancestor_protected['ok'] and 'service' in ancestor_protected['error'].lower()
    service_parent.destroy()
    real_service_check=boxes._service_node_or_ancestor
    boxes._service_node_or_ancestor=lambda _node:(_ for _ in ()).throw(RuntimeError('injected ancestry inspection failure'))
    try:inspection_failed=call(f"__result__=network_boxes({parent!r},{groups!r},dry_run=True,allow_foreign='must not bypass unknown service state')")
    finally:boxes._service_node_or_ancestor=real_service_check
    assert not inspection_failed['ok'] and inspection_failed['evidence'][0]['phase']=='preflight'
    assert inspection_failed['evidence'][0]['scene_writes']==0

    # Same-process reload preserves exact live box provenance, not arbitrary replacements.
    stable_plan=preview(parent,groups)
    registry=boxes._OWNED_BOXES;owned=hou.node(parent).findNetworkBox('controls')
    importlib.reload(boxes)
    assert boxes._OWNED_BOXES is registry and boxes.box_provenance(owned,session)['status']=='owned_current_session'
    assert preview(parent,groups)['plan_sha256']==stable_plan['plan_sha256']
    generation=boxes._BOX_GENERATION;boxes._BOX_GENERATION='simulated-new-process-generation'
    try:generation_stale=apply(parent,groups,stable_plan['plan_sha256'])
    finally:boxes._BOX_GENERATION=generation
    assert not generation_stale['ok'] and 'stale' in generation_stale['error']

    # Parent deletion cannot bypass a foreign/service box.
    blocked_delete=call(f"__result__=delete_node({parent!r})")
    assert not blocked_delete['ok'] and ('foreign Network Box' in blocked_delete['error'] or 'service' in blocked_delete['error'].lower())

    # Owned parent deletion records exact box provenance; a later failure can
    # undo parent/box together, after which an ordinary delete commits cleanly.
    delete_parent=ok(f"p=tab_create('/obj','geo',name='__box_delete_{suffix}')\nn=tab_create(p,'null',name='n')\n__result__=p.path()")['result']
    delete_group=[{'name':'owned_box','label':'Owned deletion box','role':'assembly',
                   'members':[delete_parent+'/n']}]
    delete_dry=preview(delete_parent,delete_group)
    assert apply(delete_parent,delete_group,delete_dry['plan_sha256'])['ok']
    delete_rolled=call(f"delete_node({delete_parent!r})\nraise RuntimeError('undo parent deletion')")
    assert not delete_rolled['ok'] and delete_rolled['rollback']['applied'] is True,delete_rolled
    restored_parent=hou.node(delete_parent);restored_box=restored_parent.findNetworkBox('owned_box')
    assert restored_box is not None and boxes.box_provenance(restored_box,session)['status']=='owned_current_session'
    deleted=call(f"__result__=delete_node({delete_parent!r})")
    assert deleted['ok'] and hou.node(delete_parent) is None,deleted

    # The declared 64-box boundary permits same-exec preview/no-op after
    # creation (old accounting double-counted existing upserts).
    budget_created=ok(
        f"p=tab_create('/obj','geo',name='__box_budget_{suffix}')\n"
        "items=[]\n"
        "for i in range(64): items.append(tab_create(p,'null',name='n%02d'%i).path())\n"
        "__result__={'parent':p.path(),'items':items}")['result']
    budget_parent=budget_created['parent']
    budget_groups=[{'name':'b%02d'%index,'label':'Budget %02d'%index,'role':'assembly',
                    'members':[path]} for index,path in enumerate(budget_created['items'])]
    budget_noop=call(
        f"a=network_boxes({budget_parent!r},{budget_groups!r},dry_run=True)\n"
        f"network_boxes({budget_parent!r},{budget_groups!r},expected_plan=a['plan_sha256'])\n"
        f"b=network_boxes({budget_parent!r},{budget_groups!r},dry_run=True)\n"
        f"__result__=network_boxes({budget_parent!r},{budget_groups!r},expected_plan=b['plan_sha256'])")
    assert budget_noop['ok'] and not budget_noop['result']['applied']
    assert budget_noop['transaction']['network_boxes']['entry_count']==1
    assert call(f"__result__=delete_node({budget_parent!r})")['ok']

    overflow_created=ok(
        f"p=tab_create('/obj','geo',name='__box_overflow_{suffix}')\nitems=[]\n"
        "for i in range(65): items.append(tab_create(p,'null',name='n%02d'%i).path())\n"
        "__result__={'parent':p.path(),'items':items}")['result']
    overflow_parent=overflow_created['parent']
    first=[{'name':'a%02d'%i,'label':'A%02d'%i,'role':'assembly','members':[path]}
           for i,path in enumerate(overflow_created['items'][:33])]
    second=[{'name':'z%02d'%i,'label':'Z%02d'%i,'role':'source','members':[path]}
            for i,path in enumerate(overflow_created['items'][33:])]
    overflow=call(
        f"a=network_boxes({overflow_parent!r},{first!r},dry_run=True)\n"
        f"network_boxes({overflow_parent!r},{first!r},expected_plan=a['plan_sha256'])\n"
        f"b=network_boxes({overflow_parent!r},{second!r},dry_run=True)\n"
        f"network_boxes({overflow_parent!r},{second!r},expected_plan=b['plan_sha256'])")
    assert not overflow['ok'] and 'journal budget' in overflow['error'] and overflow['rollback']['applied']
    assert not hou.node(overflow_parent).networkBoxes()
    assert call(f"__result__=delete_node({overflow_parent!r})")['ok']

    # A failed creation at an owned box's old name must not revoke the renamed
    # original's authority merely because name_at_creation matches.
    original_controls=hou.node(parent).findNetworkBox('controls');original_controls.setName('controls_renamed')
    replacement_group={'name':'controls','label':'Temporary replacement','role':'controls','members':[multi_node]}
    replacement_plan=preview(parent,[replacement_group])
    real_bounds=boxes._content_bounds
    boxes._content_bounds=lambda _nodes:(_ for _ in ()).throw(RuntimeError('replacement failure'))
    try:
        with hou.undos.disabler():replacement_failure=apply(parent,[replacement_group],replacement_plan['plan_sha256'])
    finally:boxes._content_bounds=real_bounds
    assert not replacement_failure['ok'] and hou.node(parent).findNetworkBox('controls') is None
    assert boxes.box_provenance(original_controls,session)['status']=='owned_current_session'
    original_controls.setName('controls')

    # Save/reopen preserves native presentation but never runtime ownership.
    with tempfile.TemporaryDirectory(prefix='dsh-box-reopen-') as tmp:
        hip=(Path(tmp)/'boxes.hip').as_posix();hou.hipFile.save(hip);hou.hipFile.load(hip,suppress_save_prompt=True)
        reopened_parent=hou.node(parent);reopened=reopened_parent.findNetworkBox('controls')
        assert reopened is not None and boxes.box_provenance(reopened,session)['status']=='foreign'
    print('governed Network Box contract passed on '+hou.applicationVersionString())
finally:
    if parent and hou.node(parent) is not None:hou.node(parent).destroy()
