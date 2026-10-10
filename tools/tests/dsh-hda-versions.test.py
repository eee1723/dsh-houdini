"""Real native versions: source library, old definitions, channels, wires and failure recovery."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge
import dsh_hda_versions as versions
import dsh_hou_helpers as helpers


def run(code, ok=True, owner='version-author', query=False):
    result = bridge.run_code(code, owner_session=owner, owner_call='version-test', read_only=query)
    assert result['ok'] is ok, result.get('error')
    return result


with tempfile.TemporaryDirectory(prefix='dsh-hda-versions-') as tmp:
    library = Path(tmp) / 'package' / 'otls' / 'asset.hda'
    library.parent.mkdir(parents=True)
    # Foreign package asset and another type share a real Houdini library.
    geo = hou.node('/obj').createNode('geo', 'fixture')
    node = geo.createNode('subnet', 'asset')
    shape = node.createNode('box', 'shape')
    out = node.createNode('output', 'out'); out.setInput(0, shape)
    node = node.createDigitalAsset('test::nested::asset', str(library), min_num_inputs=0, max_num_inputs=1)
    source = node.type().definition()
    group = source.parmTemplateGroup()
    group.append(hou.StringParmTemplate('label1', 'Label 1', 1))
    group.append(hou.StringParmTemplate('label2', 'Label 2', 1))
    group.append(hou.FloatParmTemplate('width', 'Width', 1, default_value=(1.0,)))
    source.setParmTemplateGroup(group)
    source.addSection('PythonModule', 'VALUE = 1\n')
    source.copyToHDAFile(str(library), new_name='test::other::1.0')
    hou.hda.reloadFile(str(library))
    node.matchCurrentDefinition()
    peer = geo.createNode('test::nested::asset', 'peer', exact_type_name=True)
    upstream = geo.createNode('null', 'upstream'); node.setInput(0, upstream)
    downstream = geo.createNode('null', 'downstream'); downstream.setInput(0, node)
    # Standard subnet parameters remain matching channels in both versions.
    node.parm('label1').set('artist value')
    node.parm('label2').setExpression('"frame " + $F', hou.exprLanguage.Hscript)
    node.parm('label1').lock(True)
    key = hou.Keyframe(); key.setFrame(12); key.setValue(2.5)
    node.parm('width').setKeyframe(key)
    path = node.path()
    auth = "用户明确授权原工具版本升级和此实例切换"
    original = library.read_bytes()
    assert 'ownership' in run(f"hda_version({path!r},'1.1')", False)['error']
    assert library.read_bytes() == original
    run(f"hda_version({path!r},'1.1',allow_foreign={auth!r})", False, query=True)
    preview = run(f"__result__=hda_version({path!r},'1.1',dry_run=True,allow_foreign={auth!r})")['result']
    assert not preview['applied'] and library.read_bytes() == original
    result = run(f"__result__=hda_version({path!r},'1.1',allow_foreign={auth!r})")['result']
    assert result['type'] == 'test::nested::asset::1.1'
    assert Path(result['hda_file']) == library and result['instances_migrated'] == 0
    assert node.type().name() == peer.type().name() == 'test::nested::asset'
    order = list(node.type().versionNamespaceOrder())
    assert result['type'] in order and 'test::nested::asset' in order, order
    latest = geo.createNode('test::nested::asset', 'latest_default')
    assert latest.type().name() == result['type'], latest.type().name()
    latest.destroy()
    assert {d.nodeTypeName() for d in hou.hda.definitionsInFile(str(library))} == {'test::nested::asset', 'test::other::1.0', result['type']}
    detail = run("__result__=tool_inspect('node_type','test::nested::asset',category='Sop')", query=True)['result']
    assert len(detail['type_versions']) == 2 and detail['type_version'] == ''
    before = library.read_bytes()
    run(f"hda_version({path!r},'1.1',allow_foreign={auth!r})", False)
    assert library.read_bytes() == before
    target = hou.nodeType(hou.sopNodeTypeCategory(), result['type']).definition()
    target.addSection('PythonModule', 'VALUE = 2\n')
    switched = run(f"__result__=hda_switch_version({path!r},{result['type']!r},allow_foreign={auth!r})")['result']
    changed = hou.node(path)
    assert switched['applied'] and changed.hdaModule().VALUE == 2
    assert peer.hdaModule().VALUE == 1 and peer.type().name() == 'test::nested::asset'
    assert changed.parm('label1').eval() == 'artist value' and changed.parm('label1').isLocked()
    assert changed.parm('label2').expression() == '"frame " + $F'
    assert changed.parm('width').keyframes()[0].frame() == 12
    assert changed.parm('width').keyframes()[0].value() == 2.5
    assert changed.input(0) == upstream and downstream.input(0) == changed
    foreign_provenance = run(f"__result__=[node_provenance(n) for n in hou.node({path!r}).allSubChildren(sync_delayed_definition=True)]")['result']
    assert foreign_provenance and all(row['status'] == 'foreign' for row in foreign_provenance)
    # Adding a version to a foreign library never grants later write authority.
    run(f"hda_set_section({path!r},'PythonModule','VALUE = 3\\n')", False)
    run(f"hda_switch_version({path!r},'test::other::1.0',allow_foreign={auth!r})", False)
    # Roll back to the unversioned native type, preserving channels and wires.
    run(f"hda_switch_version({path!r},'test::nested::asset',allow_foreign={auth!r})")
    assert hou.node(path).hdaModule().VALUE == 1
    assert downstream.input(0) == hou.node(path)
    before = library.read_bytes()
    native_copy = versions._copy_version
    def fail_after_copy(*args):
        native_copy(*args)
        raise RuntimeError('injected after native copy')
    versions._copy_version = fail_after_copy
    try:
        failure = run(f"hda_version({path!r},'1.2',allow_foreign={auth!r})", False)
        assert 'restored' in str(failure) and 'injected after native copy' in failure['error']
        assert library.read_bytes() == before
        assert hou.nodeType(hou.sopNodeTypeCategory(), 'test::nested::asset::1.2') is None
    finally:
        versions._copy_version = native_copy
    # Raw paths now have actionable supported operations; query cannot mutate.
    run(f"hou.node({path!r}).changeNodeType('test::nested::asset::1.1')", False)
    run(f"hda_switch_version({path!r},'test::nested::asset::1.1',allow_foreign={auth!r})", False, query=True)
    # Directory preference is a task decision, not an execution prohibition.
    # Use a private preference root even when this test is launched manually.
    original_preferences=hou.getenv('HOUDINI_USER_PREF_DIR')
    private_preferences=Path(tmp)/'personal-preferences'
    hou.putenv('HOUDINI_USER_PREF_DIR',str(private_preferences))
    try:
        for folder in ('otls','hda'):
            destination=private_preferences/folder/'independent.hda'
            fork=run(f"__result__=hda_fork({path!r},'test::personal_{folder}::1.0',{str(destination)!r})")['result']
            assert Path(fork['hda_file']).resolve()==destination.resolve() and destination.is_file()
            saved=destination.read_bytes()
            failure=run(f"hda_fork({path!r},'test::collision_{folder}::1.0',{str(destination)!r})",False)
            assert 'already exists' in failure['error'] and destination.read_bytes()==saved
            own_library=private_preferences/folder/'new_tool.otl'
            result=run(f"n=tab_create('/obj','subnet','personal_{folder}'); "
                f"__result__=hda_create(n,'test::new_personal_{folder}::1.0',hda_file={str(own_library)!r})")['result']
            assert own_library.is_file()
            assert Path(hou.node(result['node']).type().definition().libraryFilePath()).resolve()==own_library.resolve()
        vendor=Path(hou.expandString('$HFS'))/'otls'/'dsh_forbidden_fixture.hda'
        rejected=run(f"hda_fork({path!r},'test::vendor_forbidden::1.0',{str(vendor)!r})",False)
        assert '$HFS' in rejected['error'] and not vendor.exists()
        target=run("__result__=tab_create('/obj','subnet','vendor_forbidden').path()")['result']
        rejected=run(f"hda_create({target!r},'test::vendor_new_forbidden::1.0',hda_file={str(vendor)!r})",False)
        assert '$HFS' in rejected['error'] and not vendor.exists()
    finally:
        if original_preferences is None: hou.unsetenv('HOUDINI_USER_PREF_DIR')
        else: hou.putenv('HOUDINI_USER_PREF_DIR',original_preferences)
    print('PASS explicit personal otls/hda creation and fork; collisions and vendor writes refused')

    # An owned library and owned root can version without adopting foreign content.
    owned = str(Path(tmp) / 'owned.hda')
    ownpath = run(f"n=tab_create('/obj','subnet','owned'); __result__=hda_create(n,'test::owned::1.0',hda_file={owned!r})")['result']['node']
    run(f"hda_version({ownpath!r},'1.1')")
    p = run(f"__result__=hda_edit({ownpath!r},'lock',dry_run=True,discard_changes=True)")['result']['plan_sha256']
    run(f"hda_edit({ownpath!r},'lock',discard_changes=True,expected_plan={p!r})")
    run(f"hda_switch_version({ownpath!r},'test::owned::1.1')")
    run(f"hda_set_section({ownpath!r},'PythonModule','VALUE = 3\\n')")
    run(f"hda_switch_version({ownpath!r},'test::owned::1.0')")
    run(f"hda_set_section({ownpath!r},'PythonModule','VALUE = 4\\n')")
    run(f"hda_switch_version({ownpath!r},'test::owned::1.1')")
    # Failure after authority refresh must restore the prior authority as well
    # as bytes, so the next legitimate authoring call does not fail spuriously.
    import dsh_hda_interfaces as interfaces
    register = interfaces.register_created_definition
    owned_before = Path(owned).read_bytes()
    def fail_registration(definition):
        register(definition)
        raise RuntimeError('injected registration failure')
    interfaces.register_created_definition = fail_registration
    try:
        run(f"hda_version({ownpath!r},'1.2')", False)
        assert Path(owned).read_bytes() == owned_before
    finally:
        interfaces.register_created_definition = register
    run(f"hda_version({ownpath!r},'1.2')")

    # A verb-created, nonempty instance owns its initialized contents even when
    # its shared definition belongs to someone else. Switching must preserve
    # that usability after an ordinary geometry observation materializes it.
    fresh = run("__result__=tab_create('/obj/fixture','test::nested::asset::1.1','owned_instance').path()")['result']
    for target_name in ('test::nested::asset', 'test::nested::asset::1.1'):
        previous_ids = {int(child.sessionId()) for child in hou.node(fresh).allSubChildren()}
        run(f"hda_switch_version({fresh!r},{target_name!r})")
        observed = run(f"__result__=describe({fresh!r})", query=True)['result']
        assert observed['geometry']['points'] == 8 and observed['geometry']['prims'] == 6
        provenance = run(f"__result__=[node_provenance(n) for n in hou.node({fresh!r}).allSubChildren()]", query=True)['result']
        assert provenance and all(row['status'] == 'owned_current_session' for row in provenance)
        assert previous_ids.isdisjoint(row['session_id'] for row in provenance)
        assert not previous_ids.intersection(helpers._OWNED_NODE_SESSIONS)
    # Neither a version switch nor the new internal ownership grants the
    # foreign shared definition to this author or the instance to another task.
    run(f"hda_set_section({fresh!r},'PythonModule','VALUE = 99\\n')", False)
    run(f"hda_switch_version({fresh!r},'test::nested::asset')", False, owner='other-author')
    run(f"delete_node({fresh!r})")

print('PASS native HDA versions, source package library, coexistence, selective switch, rollback, authority and channels ' + hou.applicationVersionString())
