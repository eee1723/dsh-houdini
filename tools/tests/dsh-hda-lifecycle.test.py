"""Generic HDA save/lock and definition-failure contracts; isolated hython only."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h
import dsh_hda_interfaces as interfaces
from dsh_hda_lifecycle import _interface_differences

def run(code, ok=True, owner='lifecycle-author', query=False):
    r=b.run_code(code,owner_session=owner,owner_call='lifecycle-test',read_only=query)
    assert r['ok'] is ok, r.get('error')
    return r

def edit(path,action,**kwargs):
    tail=''.join(f', {key}={value!r}' for key,value in kwargs.items())
    call=f'hda_edit({path!r},{action!r}{tail}'
    p=run('__result__='+call+',dry_run=True)')
    assert p['transaction']['status']=='no_scene_change', p
    return run('__result__='+call+f",expected_plan={p['result']['plan_sha256']!r})")['result']

with tempfile.TemporaryDirectory(prefix='dsh-hda-lifecycle-') as tmp:
    library=Path(tmp)/'a.hda'
    path='/obj/lifecycle/asset'
    run("g=tab_create('/obj','geo',name='lifecycle')\n"
        "n=tab_create(g,'subnet',name='asset')\n"
        "shape=tab_create(n,'box',name='shape')\n"
        "out=tab_create(n,'output',name='out',inputs=[shape])\n"
        f"hda_create(n,'contract::lifecycle::1.0',hda_file={str(library)!r})")
    layout=[{'type':'float','name':'width','default':2.}]
    run(f'hda_set_interface({path!r},layout={layout!r})')
    run(f"set_parms({(path+'/shape')!r},{{'sizex':'ch(\"../width\")'}})")
    before=library.read_bytes()
    # Missing/stale plan is a zero-write rejection.
    assert 'expected_plan' in run(f"hda_edit({path!r},'save')",False)['error']
    assert library.read_bytes()==before
    p=run(f"__result__=hda_edit({path!r},'save',dry_run=True)")['result']['plan_sha256']
    run(f"set_parms({path!r},{{'width':3}})")
    assert 'stale' in run(f"hda_edit({path!r},'save',expected_plan={p!r})",False)['error']
    saved=edit(path,'save')
    assert saved['applied']
    run("other=tab_create('/obj/lifecycle','contract::lifecycle::1.0',name='other')\ncook_node(other)")
    other=hou.node('/obj/lifecycle/other')
    assert other.node('shape').parm('sizex').expression()=='ch("../width")'
    assert other.geometry().intrinsicValue('pointcount')==8
    assert 'discard' in run(f"hda_edit({path!r},'lock',dry_run=True)",False)['error']
    locked=edit(path,'lock',discard_changes=True)
    assert locked['locked_after'] and locked['matches_definition_after']
    original_children=[c.sessionId() for c in hou.node(path).allSubChildren()]
    edit(path,'unlock')
    assert not hou.node(path).isLockedHDA()
    assert [c.sessionId() for c in hou.node(path).allSubChildren()]==original_children
    # Query and raw aliases cannot acquire lifecycle mutation authority.
    run(f"hda_edit({path!r},'unlock',dry_run=True)",False,query=True)
    raw=run(f"hou.node({path!r}).allowEditingOfContents()",False)
    assert 'gate' in raw['error']
    run(f"hda_edit({path!r},'save',dry_run=True)",False,owner='other-session')
    # Native user-created instance of the same definition blocks a shared write.
    foreign=hou.node('/obj/lifecycle').createNode('contract::lifecycle::1.0','foreign')
    assert 'ownership' in run(f"hda_edit({path!r},'save',dry_run=True)",False)['error']
    # This is test-fixture cleanup, not a production ownership exemption.
    foreign.destroy()
    # Existing spec (not only layout) must also reject foreign affected instances.
    foreign=hou.node('/obj/lifecycle').createNode('contract::lifecycle::1.0','foreign')
    assert 'ownership' in run(f"hda_set_interface({path!r},spec={layout!r})",False)['error']
    foreign.destroy()
    before=library.read_bytes()
    n=hou.node(path)
    n.parm('width').set(7.)
    sections={key:bytes(value.binaryContents()) for key,value in n.type().definition().sections().items()}
    original=h._rebuild_hda_interface
    def injected(*args,**kwargs):
        value=original(*args,**kwargs)
        if not kwargs.get('dry_run'):
            raise RuntimeError('injected AFTER definition write')
        return value
    h._rebuild_hda_interface=injected
    try:
        failed=run(f"hda_set_interface({path!r},layout=[{{'type':'float','name':'replacement','default':9}}])",False)
    finally:
        h._rebuild_hda_interface=original
    assert 'injected AFTER' in failed['error']
    assert library.read_bytes()==before
    assert n.evalParm('width')==7 and n.parm('replacement') is None, (n.evalParm('width'),n.parm('replacement'),failed)
    assert {key:bytes(value.binaryContents()) for key,value in n.type().definition().sections().items()}==sections
    # Definition recovery must not disable unrelated edits' outer scene undo.
    h._rebuild_hda_interface=injected
    try:
        failed=run(f"set_parms({path!r},{{'width':11}})\nhda_set_interface({path!r},layout=[{{'type':'float','name':'replacement','default':9}}])",False)
    finally:
        h._rebuild_hda_interface=original
    assert failed['rollback']['applied'] and n.evalParm('width')==7
    assert library.read_bytes()==before
    # A normal empty-label separator is serialized differently in the native
    # instance and definition DialogScripts. It is not an interface overlay.
    semantic_library=Path(tmp)/'semantic.hda'
    semantic_layout=[
        {'type':'float','name':'gain','label':'Gain','default':2.},
        {'type':'separator','name':'sep','label':'','hidden':True}]
    run("g=tab_create('/obj','geo',name='semantic')\np=tab_create(g,'subnet',name='source')\n"
        f"hda_create(p,'contract::semantic::1.0',hda_file={str(semantic_library)!r})\n"
        f"hda_set_interface('/obj/semantic/source',layout={semantic_layout!r},keep_std=False)\n"
        "other=tab_create(g,'contract::semantic::1.0',name='other')")
    source=hou.node('/obj/semantic/source')
    other=hou.node('/obj/semantic/other')
    definition=source.type().definition()
    for instance in (source,other):
        group=instance.parmTemplateGroup()
        assert not instance.spareParms()
        assert group==definition.parmTemplateGroup()
        assert group.asDialogScript(full_info=True)!=definition.parmTemplateGroup().asDialogScript(full_info=True)
    edit(source.path(),'save')

    def override(group,name,change):
        template=group.find(name)
        change(template)
        group.replace(name,template)

    # Native template equality omits help/conditionals. Verify real HOM groups,
    # including nested templates, rather than rely on native equality/asCode.
    reference=hou.ParmTemplateGroup((hou.FolderParmTemplate('controls','Controls',(
        hou.FloatParmTemplate('gain','Gain',1,default_value=(2.,)),hou.SeparatorParmTemplate('sep'))),))
    assert not _interface_differences(reference,reference)
    changes=[
        ('label',lambda group: override(group,'gain',lambda t: t.setLabel('Changed')),'gain'),
        ('default',lambda group: override(group,'gain',lambda t: t.setDefaultValue((9.,))),'gain'),
        ('type',lambda group: group.replace('gain',hou.IntParmTemplate('gain','Gain',1,default_value=(2,))),'gain: type'),
        ('help',lambda group: override(group,'gain',lambda t: t.setHelp('Changed help')),'gain: help'),
        ('disable',lambda group: override(group,'gain',lambda t: t.setConditional(hou.parmCondType.DisableWhen,'{ gain == 0 }')),'gain: conditionals'),
        ('hide',lambda group: override(group,'gain',lambda t: t.setConditional(hou.parmCondType.HideWhen,'{ gain == 0 }')),'gain: conditionals'),
        ('tab',lambda group: override(group,'controls',lambda t: t.setTabConditional(hou.parmCondType.HideWhen,'{ gain == 0 }')),'controls: tab conditionals'),
        ('export',lambda group: override(group,'gain',lambda t: t._setExportLevel(1)),'gain'),
        ('default expression language',lambda group: override(group,'gain',lambda t: t.setDefaultExpressionLanguage((hou.scriptLanguage.Python,))),'gain'),
    ]
    for name,change,difference in changes:
        group=hou.ParmTemplateGroup(reference.entries())
        change(group)
        actual=_interface_differences(group,reference)
        assert any(difference in item for item in actual),(name,actual)
    # Houdini ignores required definition parms' label/default/type changes at
    # the instance setter. Arrange actual supported per-instance overrides.
    actual_overrides=[
        ('hidden',lambda group: group.hide('gain',True),'gain'),
        ('spare',lambda group: group.append(hou.FloatParmTemplate('extra','Extra',1)),'template order/names'),
        ('reorder',lambda group: (group.remove('gain'),group.append(reference.find('gain'))),'template order/names'),
    ]
    for action,target in (('save',source),('promote',other)):
        for name,change,difference in actual_overrides:
            group=definition.parmTemplateGroup()
            change(group)
            target.setParmTemplateGroup(group)  # Adversarial state in our fixture only.
            old_bytes=semantic_library.read_bytes()
            before_states=interfaces.parameter_states(target)
            failed=run(f"hda_edit({source.path()!r},{action!r},dry_run=True)",False)
            assert difference in failed['error'], (action,name,failed)
            if action=='promote':
                assert other.path() in failed['error'],failed
            assert semantic_library.read_bytes()==old_bytes
            assert interfaces.parameter_states(target)==before_states
            target.removeSpareParms()
    # Ordinary other instances must allow additive promotion; animated/current
    # channel values remain distinct while the new definition gains the spare.
    source.parm('gain').setExpression('$F*2',hou.exprLanguage.Hscript)
    other.parm('gain').set(7.)
    group=source.parmTemplateGroup()
    group.append(hou.FloatParmTemplate('additional','Additional',1,default_value=(4.,)))
    source.setParmTemplateGroup(group)
    source.parm('additional').set(6.)
    promoted=edit(source.path(),'promote')
    assert promoted['promoted_templates']==['additional']
    assert source.parm('gain').expression()=='$F*2' and other.evalParm('gain')==7
    assert source.evalParm('additional')==6 and not source.parm('additional').isSpare()
    assert other.parm('additional') is not None and not other.parm('additional').isSpare()
    print('PASS semantic interface save/promote separator and real overlays')
    # A different asset family: additive spare UI with multiparm and animation,
    # promoted before any modeling recipe. No example-asset constants.
    migration_library=Path(tmp)/'migration.hda'
    migration_layout=[{'type':'float','name':'gain','default':2.},
        {'component':'repeater','name':'items','count':2,'parms':[
            {'type':'string','name':'item_name#','default':'item'},
            {'type':'float','name':'item_value#','default':1.}]}]
    run("g=tab_create('/obj','geo',name='migration')\np=tab_create(g,'subnet',name='source')\n"
        f"create_spare_parms(p,layout={migration_layout!r})\n"
        f"hda_create(p,'contract::migration::1.0',hda_file={str(migration_library)!r})")
    p=hou.node('/obj/migration/source')
    p.parm('gain').setExpression('$F*2',hou.exprLanguage.Hscript)
    p.parm('item_name2').set('second')
    p.parm('item_value2').set(8.)
    r=edit(p.path(),'promote')
    assert r['applied'] and p.parm('gain').expression()=='$F*2'
    assert p.evalParm('item_name2')=='second' and p.evalParm('item_value2')==8
    assert p.type().definition().parmTemplateGroup().find('gain') is not None
    run("new=tab_create('/obj/migration','contract::migration::1.0',name='new')")
    new=hou.node('/obj/migration/new')
    assert new.parm('gain') is not None and new.parm('item_value2') is not None
    assert not new.parm('gain').isSpare()
    assert len(new.parmTemplateGroup().find('items').parmTemplates())==2
    # Failed promotion must restore the source overlay too, including repeated
    # values, rather than just restoring the shared DialogScript.
    overlay=p.parmTemplateGroup()
    overlay.append(hou.FloatParmTemplate('additional','Additional',1,default_value=(4.,)))
    p.setParmTemplateGroup(overlay)
    p.parm('additional').set(6.)
    old_bytes=migration_library.read_bytes()
    original_restore=interfaces._restore
    calls=[0]
    def fail_once(states):
        calls[0]+=1
        if calls[0]==1:
            return ['injected promotion restore failure']
        return original_restore(states)
    plan=run(f"__result__=hda_edit({p.path()!r},'promote',dry_run=True)")['result']['plan_sha256']
    interfaces._restore=fail_once
    try:
        r=run(f"hda_edit({p.path()!r},'promote',expected_plan={plan!r})",False)
    finally:
        interfaces._restore=original_restore
    assert 'injected promotion restore failure' in r['error']
    assert migration_library.read_bytes()==old_bytes
    assert p.parm('additional').isSpare() and p.evalParm('additional')==6
    assert p.type().definition().parmTemplateGroup().find('additional') is None
    assert p.evalParm('item_name2')=='second' and p.evalParm('item_value2')==8
    # Scene-level tool HDA: not a SOP/geometry-only special case.
    object_library=Path(tmp)/'object.hda'
    run("obj=tab_create('/obj','subnet',name='object_tool')\n"
        f"hda_create(obj,'contract::object_tool::1.0',hda_file={str(object_library)!r})")
    obj=hou.node('/obj/object_tool')
    run(f"hda_set_interface({obj.path()!r},layout=[{{'type':'float','name':'amount','default':1}}],keep_std=False)")
    edit(obj.path(),'save')
    edit(obj.path(),'lock',discard_changes=True)
    assert obj.isLockedHDA()
    edit(obj.path(),'unlock')
    assert not obj.isLockedHDA()
    # Destructive replacement must preflight ALL instances even without undo.
    replacement=run("__result__=tab_create('/obj','subnet',name='object_replacement').path()")['result']
    foreign=hou.node('/obj').createNode('contract::object_tool::1.0','foreign_object')
    before=object_library.read_bytes()
    with hou.undos.disabler():
        run(f"hda_create({replacement!r},'contract::object_tool::1.0',hda_file={str(object_library)!r},replace=True)",False)
    assert hou.node('/obj/object_tool') is not None and foreign is not None
    assert object_library.read_bytes()==before
    foreign.destroy()
    # Deleting an owned container is not authority to delete an inserted user node.
    foreign_child=hou.node(replacement).createNode('null','user_child')
    with hou.undos.disabler():
        run(f'delete_node({replacement!r})',False)
    assert hou.node(replacement) is not None and foreign_child.parent()==hou.node(replacement)
    # Native definition refresh creates children in existing owned instances.
    # They must remain editable/cleanable without allow_foreign (test76).
    rebuild_library=Path(tmp)/'rebuild.hda'
    root='/obj/rebuild_fixture'
    asset=root+'/source'
    run(f"g=tab_create('/obj','geo',name='rebuild_fixture'); n=tab_create(g,'subnet',name='source'); "
        f"w=tab_create(n,'attribwrangle',name='shape'); sop_set_output(w,output_index=0); "
        f"hda_create(n,'contract::rebuild::1.0',hda_file={str(rebuild_library)!r})")
    edit(asset,'save')
    run(f"tab_create({root!r},'contract::rebuild::1.0',name='consumer')")
    run(f"tab_create({asset!r},'switch',name='new_mode')")
    edit(asset,'save')
    run(f"cook_node({root+'/consumer'!r})")
    def assert_owned(target):
        facts=run(f"__result__=[node_provenance(n) for n in hou.node({target!r}).allSubChildren()]",query=True)['result']
        assert facts and all(n['status']=='owned_current_session' for n in facts),facts
    assert_owned(root+'/consumer')
    edit(asset,'lock',discard_changes=True)
    assert_owned(asset)
    edit(asset,'unlock')
    # A failed batch can make Undo recreate nested native nodes that were alive
    # immediately before Undo. Recovery must retain exact ownership.
    before_owned={c.sessionId():c.path() for c in hou.node(asset).allSubChildren()}
    at_undo={}
    original_undo=hou.undos.performUndo
    def observe_undo():
        at_undo.update({identity:hou.nodeBySessionId(identity) is not None for identity in before_owned})
        return original_undo()
    hou.undos.performUndo=observe_undo
    try:
        failed=run(f"p=hda_edit({asset!r},'lock',dry_run=True,discard_changes=True); "
            f"hda_edit({asset!r},'lock',expected_plan=p['plan_sha256'],discard_changes=True); "
            "raise RuntimeError('after native lock')",False)
    finally:
        hou.undos.performUndo=original_undo
    assert failed.get('rollback',{}).get('applied'),failed
    assert_owned(asset)
    replaced_during_undo=[path for identity,path in before_owned.items()
                          if at_undo.get(identity) and hou.nodeBySessionId(identity) is None]
    assert replaced_during_undo, 'fixture must cover children replaced by Undo itself'
    print('PASS identities alive before Undo and restored with new IDs:',replaced_during_undo)
    run(f"delete_node({root+'/consumer'!r})")
    # Foreign/other-session instances are still protected. Explicit one-shot
    # library maintenance does not grant their new children lasting ownership.
    foreign=hou.node(root).createNode('contract::rebuild::1.0','foreign_consumer')
    run(f"tab_create({root!r},'contract::rebuild::1.0',name='other_consumer')",owner='other-session')
    if hou.node(asset).isLockedHDA(): edit(asset,'unlock')
    run(f"tab_create({asset!r},'null',name='second_mode')")
    assert 'ownership' in run(f"hda_edit({asset!r},'save',dry_run=True)",False)['error']
    edit(asset,'save',allow_foreign='fixture explicitly authorizes shared definition write')
    for target in [foreign.path(),root+'/other_consumer']:
        fact=run(f"__result__=node_provenance({target+'/second_mode'!r})",query=True)['result']
        assert fact['status']=='foreign',fact
    # Pre-existing user child in an owned authoring network remains foreign.
    user_child=hou.node(asset).createNode('subnet','user_child')
    user_nested=user_child.createNode('attribwrangle','nested')
    edit(asset,'save',allow_foreign='fixture shared definition')
    assert run(f"__result__=node_provenance({user_nested.path()!r})",query=True)['result']['status']=='foreign'
    assert 'ownership' in run(f"hda_edit({asset!r},'lock',discard_changes=True,dry_run=True)",False)['error']
    print('PASS native definition rebuild ownership, rollback and foreign boundaries')
    print('PASS lifecycle and definition write recovery',hou.applicationVersionString())
