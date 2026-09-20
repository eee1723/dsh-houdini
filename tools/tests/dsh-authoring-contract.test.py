"""Scalar definition/spare parity and conversion-bound native provenance, isolated HOM."""
from pathlib import Path
import sys,tempfile,json
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h

def run(code,ok=True,owner='author'):
    r=b.run_code(code,owner_session=owner,owner_call='authoring-contract')
    assert r['ok'] is ok,r.get('error')
    return r

def result(code,**kwargs):return run('__result__='+code,**kwargs)['result']

with tempfile.TemporaryDirectory(prefix='dsh-authoring-contract-') as tmp:
    lib=str(Path(tmp)/'gain.hda')
    run("g=tab_create('/obj','geo','authoring')\ns=tab_create(g,'subnet','asset')\n"
        "create_spare_parms(s,spec=[{'type':'float','name':'gain','default':2}])\n"
        "shape=tab_create(s,'box','shape',parms={'sizex':'ch(\"../gain\")'})\n"
        "tag=tab_create(s,'attribwrangle','tag',inputs=[shape],parms={'snippet':'i@kind=1;'})\n"
        "sop_set_output(tag,output_index=0)\ncook_node(tag)")
    p='/obj/authoring/asset';out=p+'/tag'
    cases=[{'id':'gain','values':{'gain':3},'expectations':[{'metric':'bounds_size','axis':0,'delta':[.99,1.01]}]}]
    domain=[{'id':'gain_min','left':'gain','op':'ge','right':1}]
    before=result(f'test_controls({p!r},{out!r},{cases!r},domain={domain!r})')
    assert before['ok'] and before['restored']
    with h._execution_owner("author","capture-before-conversion"):
        one_shot=h._snapshot_native_conversion(hou.node(p))
    created=result(f'hda_create({p!r},"contract::authoring::1.0",hda_file={lib!r})')
    assert created['pending_spare_parameters']==['gain'] and 'promote' in created['next_action']
    assert created['native_identity_transfers'],created
    with h._execution_owner('author','repeat-reconcile'):
        assert h._reconcile_native_conversion(one_shot)==[], 'mapping is consumed, never a future adoption rule'
    run(f'cook_node({p!r})')
    assert all(n['status']=='owned_current_session' for n in result(f'[node_provenance(n) for n in hou.node({p!r}).allSubChildren()]'))
    for action in ['unlock','promote']:
        plan=result(f'hda_edit({p!r},{action!r},dry_run=True)')
        applied=result(f'hda_edit({p!r},{action!r},expected_plan={plan["plan_sha256"]!r})')
        assert applied['applied']
    run("fresh=tab_create('/obj/authoring','contract::authoring::1.0','fresh')")
    fresh='/obj/authoring/fresh'
    assert not hou.node(fresh).parm('gain').isSpare()
    after=result(f'test_controls({fresh!r},{fresh!r},{cases!r},domain={domain!r})')
    assert after['ok'] and after['restored']
    # Illegal baseline rejects before writing; same result on either carrier.
    invalid=[{**domain[0],'right':4}]
    rejected=result(f'test_controls({fresh!r},{fresh!r},{cases!r},domain={invalid!r})')
    assert rejected['status']=='fail' and rejected['parameter_writes']==0
    assert hou.node(fresh).evalParm('gain')==2
    # Invalid domains (including right-hand references) are not silently dropped.
    for bad in [dict(domain[0],left='missing'),dict(domain[0],right='missing')]:
        r=run(f'test_controls({fresh!r},{fresh!r},{cases!r},domain={[bad]!r})',False)
        assert 'numeric scalar' in r['error']
        assert hou.node(fresh).evalParm('gain')==2
    # Native fixture-only templates: prove domain never invokes callbacks/menus.
    node=hou.node(fresh);group=node.parmTemplateGroup()
    callback=hou.FloatParmTemplate('callback','Callback',1);callback.setScriptCallback('raise RuntimeError("must not execute")')
    menu=hou.IntParmTemplate('mode','Mode',1,menu_items=('a','b'))
    group.append(callback);group.append(menu);group.append(hou.StringParmTemplate('text','Text',1))
    node.setParmTemplateGroup(group)
    for name,reason in [('callback','callbacks'),('mode','menu'),('text','numeric scalar')]:
        r=run(f'test_controls({fresh!r},{fresh!r},{cases!r},domain={[dict(domain[0],left=name)]!r})',False)
        assert reason in r['error'],r['error']
        assert hou.node(fresh).evalParm('gain')==2
    # A named numeric component is scalar; a whole tuple/list value is not.
    run("tab_create('/obj/authoring','box','native_box')")
    component=[{'id':'size_component','values':{'sizex':2},'expectations':[{'metric':'bounds_size','axis':0,'delta':[.99,1.01]}]}]
    component_result=result(f'test_controls("/obj/authoring/native_box","/obj/authoring/native_box",{component!r},domain={[dict(domain[0],left="sizex",right=0.5)]!r})')
    assert component_result['ok'] and component_result['restored']
    # All interface preview modes report operation success without writes.
    layout=[{'type':'float','name':'amount','default':1}]
    run("s=tab_create('/obj/authoring','subnet','ui')\n"+f'hda_create(s,"contract::authoring_ui::1.0",hda_file={str(Path(tmp)/"ui.hda")!r})')
    ui='/obj/authoring/ui'
    for key in ['spec','layout']:
        initial=Path(tmp,'ui.hda').read_bytes();old=hou.node(ui).parmTemplateGroup().asDialogScript()
        preview=result(f'hda_set_interface({ui!r},{key}={layout!r},dry_run=True)')
        assert preview['ok'] and preview['dry_run'] and not preview['applied'] and preview['scene_writes']==0
        assert Path(tmp,'ui.hda').read_bytes()==initial and hou.node(ui).parmTemplateGroup().asDialogScript()==old
    # Foreign child survives conversion and is the exact reason cleanup refuses.
    run("s=tab_create('/obj/authoring','subnet','mixed')\nw=tab_create(s,'attribwrangle','native')\ncook_node(w)")
    run("tab_create('/obj/authoring/mixed','null','other_author')",owner='second-author')
    run(f'hda_create("/obj/authoring/mixed","contract::mixed::1.0",hda_file={str(Path(tmp)/"mixed.hda")!r})')
    r=run('delete_node("/obj/authoring/mixed")',False)
    assert 'other_author' in r['error'] and 'native/attribvop1' not in r['error'],r['error']
    assert result('node_provenance("/obj/authoring/mixed/other_author")')['status']=='owned_other_session'
    # A copied audit tag on an unregistered GUI-created node grants nothing.
    foreign=hou.node('/obj/authoring/mixed').createNode('null','manual')
    foreign.setUserData(h._TASK_OWNER_KEY,'author')
    assert result('node_provenance("/obj/authoring/mixed/manual")')['status']=='foreign'
    # Unlocked/modified native definition is outside the reconciliation whitelist.
    run("s=tab_create('/obj/authoring','subnet','modified_native')\nw=tab_create(s,'attribwrangle','w')")
    native=hou.node('/obj/authoring/modified_native/w');native.allowEditingOfContents()
    native.createNode('null','manual_internal').setUserData(h._TASK_OWNER_KEY,'author')
    run(f'hda_create("/obj/authoring/modified_native","contract::modified_native::1.0",hda_file={str(Path(tmp)/"modified.hda")!r})')
    assert result('node_provenance("/obj/authoring/modified_native/w/manual_internal")')['status']=='foreign'
    # A same-path replacement cannot satisfy the surviving-native-anchor condition.
    run("s=tab_create('/obj/authoring','subnet','slot')\nw=tab_create(s,'attribwrangle','native')\ncook_node(w)")
    with h._execution_owner('author','capture'):
        captured=h._snapshot_native_conversion(hou.node('/obj/authoring/slot'))
    assert captured
    run('delete_node("/obj/authoring/slot/native")')
    replacement=hou.node('/obj/authoring/slot').createNode('attribwrangle','native')
    replacement.setUserData(h._TASK_OWNER_KEY,'author')
    with h._execution_owner('author','reconcile'):
        assert h._reconcile_native_conversion(captured)==[]
    assert result('node_provenance("/obj/authoring/slot/native")')['status']=='foreign'
    # A user-library definition, even locked, is never a trusted native anchor.
    run("s=tab_create('/obj/authoring','subnet','user_definition')\ntab_create(s,'box','shape')\n"+
        f'hda_create(s,"contract::user_definition::1.0",hda_file={str(Path(tmp)/"user.hda")!r})')
    custom=hou.node('/obj/authoring/user_definition');custom.matchCurrentDefinition()
    assert custom.isLockedHDA() and h._native_definition_identity(custom,{}) is None
    # Render-service tags exclude a whole native subtree from transfer.
    run("s=tab_create('/obj/authoring','subnet','service_case')\nw=tab_create(s,'attribwrangle','native')\ncook_node(w)")
    internal=hou.node('/obj/authoring/service_case/native/attribvop1')
    internal.setUserData(h._RENDER_OWNER_KEY,h._RENDER_OWNER_VALUE)
    service_result=result(f'hda_create("/obj/authoring/service_case","contract::service_case::1.0",hda_file={str(Path(tmp)/"service.hda")!r})')
    assert service_result['native_identity_transfers']==[]
    assert result('node_provenance("/obj/authoring/service_case/native/attribvop1")')['status']!='owned_current_session'
    # A failed conversion preflight cannot change ownership or node identities.
    run("s=tab_create('/obj/authoring','subnet','failed_create')\ntab_create(s,'attribwrangle','native')")
    failed_root=hou.node('/obj/authoring/failed_create')
    ids=[n.sessionId() for n in failed_root.allSubChildren()]
    blocker=Path(tmp)/'regular-file';blocker.write_text('not a directory')
    run(f'hda_create("/obj/authoring/failed_create","contract::failed_create::1.0",hda_file={str(blocker/"asset.hda")!r})',False)
    assert [n.sessionId() for n in failed_root.allSubChildren()]==ids
    assert all(row['status']=='owned_current_session' for row in result('[node_provenance(n) for n in hou.node("/obj/authoring/failed_create").allSubChildren()]'))
    # Provenance does not leak into another author; ordinary owned cleanup works.
    run(f'delete_node({p!r})',False,owner='second-author')
    run(f'delete_node({p!r})')
    assert hou.node(p) is None
print('PASS authoring: definition/spare domain parity, zero-write rejection, preview shape, native conversion and foreign counterexamples '+hou.applicationVersionString())
