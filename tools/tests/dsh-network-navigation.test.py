"""Isolated H21/H22 explicit control discovery, persistence and compensation."""
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import hou
import dsh_network_navigation as navigation


suffix = uuid.uuid4().hex[:8]
parent = hou.node('/obj').createNode('geo', '__control_navigation_' + suffix)
parent_path = parent.path()
controller = parent.createNode('null', 'parameter_panel')
decoy = parent.createNode('null', 'CTRL_ENGINEERING')
subnet = parent.createNode('subnet', 'component')
local = subnet.createNode('null', 'local_dimensions')
body = parent.createNode('box', 'body')
body.parm('sizex').setExpression('2+$F', hou.exprLanguage.Hscript)
body.setDisplayFlag(True)
body.setRenderFlag(True)
other = hou.node('/obj').createNode('null', '__control_outside_' + suffix)
checks = []


def owned(node, operation, allow_foreign):
    checks.append((node.path(), operation, allow_foreign))
    if node == decoy and allow_foreign is None:
        raise PermissionError('fixture foreign node')


def declare(controls=None, remove=None, allow=None):
    return navigation.declare_controls(parent, controls, remove, owned, allow)


def rejected(callback, expected):
    try:
        callback()
    except Exception as error:
        assert expected in str(error), error
    else:
        raise AssertionError('expected rejection: ' + expected)


try:
    before = {'frame': float(hou.frame()), 'expression': body.parm('sizex').expression(),
              'flags': [(node.path(), node.isDisplayFlagSet(), node.isRenderFlagSet())
                        for node in (controller, decoy, subnet, body)],
              'positions': [(node.path(), tuple(node.position())) for node in parent.children()],
              'needs_cook': body.needsToCook()}
    assert navigation.list_controls(parent) == []  # A convincing name is not a declaration.
    rejected(lambda: declare([{'node': controller, 'label': '工程控制'},
                               {'node': decoy, 'label': '不得先写'}]), 'foreign')
    assert controller.userData(navigation.CONTROL_KEY) is None
    rejected(lambda: declare([{'node': other, 'label': '范围外'}]), 'outside control scope')
    rejected(lambda: declare([{'node': controller, 'label': ''}]), 'label must be nonempty')
    rejected(lambda: declare([{'node': controller, 'label': '控制\n换行'}]), 'control characters')
    rejected(lambda: declare([{'node': controller, 'label': '控制'}], [controller]), 'conflicting')
    rejected(lambda: declare([{'node': controller, 'label': '控制'},
                               {'node': controller.path(), 'label': '重复'}]), 'duplicate')

    first = declare([{'node': 'parameter_panel', 'label': '工程控制'},
                     {'node': 'component/local_dimensions', 'label': '部件尺寸'}])
    assert first['ok'] and first['scene_writes'] == 2
    rows = navigation.list_controls(parent)
    assert {row['label'] for row in rows} == {'工程控制', '部件尺寸'}
    assert all(row['asset'] == parent_path for row in rows)
    assert {row['path'] for row in navigation.list_controls(parent, recursive=False)} == {controller.path()}
    assert len(navigation.list_controls(controller)) == 1
    assert decoy.path() not in {row['path'] for row in rows}
    unchanged = declare([{'node': controller, 'label': '工程控制'}])
    assert unchanged['scene_writes'] == 0
    assert checks[-1] == (controller.path(), 'network_controls', None)
    assert before == {'frame': float(hou.frame()), 'expression': body.parm('sizex').expression(),
                      'flags': [(node.path(), node.isDisplayFlagSet(), node.isRenderFlagSet())
                                for node in (controller, decoy, subnet, body)],
                      'positions': [(node.path(), tuple(node.position())) for node in parent.children()],
                      'needs_cook': body.needsToCook()}

    # A partial setter failure restores both prior declarations, including the
    # previously written first item. The module reports compensation evidence.
    original_write = navigation._write_control
    def fail_second(node, label):
        if node == local and label == 'injected setter failure':
            raise RuntimeError('injected setter failure')
        original_write(node, label)
    navigation._write_control = fail_second
    try:
        rejected(lambda: declare([{'node': controller, 'label': 'changed first'},
                                  {'node': local, 'label': 'injected setter failure'}]), 'restored=True')
    finally:
        navigation._write_control = original_write
    assert controller.userData(navigation.CONTROL_KEY) == '工程控制'
    assert local.userData(navigation.CONTROL_KEY) == '部件尺寸'

    # Later exec failures need compensation even when native Undo is disabled.
    # Two updates of the same node reconcile back to the original declaration.
    with navigation.transaction_journal() as journal:
        declare([{'node': controller, 'label': 'first change'}])
        declare([{'node': controller, 'label': 'second change'}], [local])
    recovery = navigation.reconcile_transaction(journal)
    assert recovery['ok'] and recovery['entry_count'] == 2
    assert controller.userData(navigation.CONTROL_KEY) == '工程控制'
    assert local.userData(navigation.CONTROL_KEY) == '部件尺寸'

    # Identity follows renames, while a same-path replacement is never restored.
    controller.setName('renamed_panel')
    assert any(row['path'] == controller.path() and row['label'] == '工程控制'
               for row in navigation.list_controls(parent))
    obsolete = parent.createNode('null', 'replaceable')
    obsolete.setUserData(navigation.CONTROL_KEY, 'old declaration')
    snapshot = navigation.snapshot_controls([obsolete])
    path = obsolete.path()
    obsolete.destroy()
    replacement = parent.createNode('null', 'replaceable')
    replacement.setUserData(navigation.CONTROL_KEY, 'new declaration')
    restored = navigation.restore_controls(snapshot)
    assert restored['ok'] and restored['missing_nodes'] == [path]
    assert replacement.userData(navigation.CONTROL_KEY) == 'new declaration'
    replacement.destroy()

    allowed = declare([{'node': decoy, 'label': '明确授权的入口'}], allow='user explicitly selected fixture decoy')
    assert allowed['scene_writes'] == 1
    declare(remove=[decoy], allow='user explicitly selected fixture decoy')
    assert decoy.userData(navigation.CONTROL_KEY) is None
    assert controller.userData(navigation.CONTROL_KEY) == '工程控制'

    # Native userData persistence is the entry index: save/reopen has no registry.
    with tempfile.TemporaryDirectory(prefix='dsh-network-controls-') as temporary:
        hip = str(Path(temporary) / 'declared-controls.hip')
        saved_rows = navigation.list_controls(parent)
        hou.hipFile.save(hip)
        hou.hipFile.load(hip, suppress_save_prompt=True)
        reopened = navigation.list_controls(parent_path)
        assert [(row['path'], row['label'], row['asset']) for row in reopened] == [
            (row['path'], row['label'], row['asset']) for row in saved_rows]
        assert hou.node(parent_path + '/CTRL_ENGINEERING').userData(navigation.CONTROL_KEY) is None

    # Exercise the actual registered bridge verb and the enclosing exec journal.
    import dsh_bridge as bridge
    import dsh_hou_helpers as helpers
    def bridge_contract():
        owner = 'navigation-' + suffix
        code = "p=tab_create('/obj','geo',name='bridge_controls_%s')\nc=tab_create(p,'null',name='panel')\n__result__={'parent':p.path(),'control':c.path()}" % suffix
        created = bridge.run_code(code, owner_session=owner, owner_call='create')
        assert created['ok'], created
        scope, path = created['result']['parent'], created['result']['control']
        applied = bridge.run_code(f"__result__=network_controls({scope!r},[{{'node':{path!r},'label':'实际入口'}}])",
                                  owner_session=owner, owner_call='declare')
        assert applied['ok'] and hou.node(path).userData(navigation.CONTROL_KEY) == '实际入口', applied
        read = bridge.run_code(f'__result__=network_controls({scope!r})',
                               owner_session=owner, owner_call='read')
        assert read['ok'] and read['result']['controls'][0]['path'] == path, read
        assert read['transaction']['status'] == 'no_scene_change', read
        failed = bridge.run_code(f"network_controls({scope!r},[{{'node':{path!r},'label':'failed exec'}}])\nraise RuntimeError('later failure')",
                                 owner_session=owner, owner_call='later-failure')
        assert not failed['ok'] and hou.node(path).userData(navigation.CONTROL_KEY) == '实际入口', failed
        assert failed['rollback']['network_controls']['ok'], failed
        # Headless exec compensation must report a real setter failure instead
        # of claiming restored metadata. GUI may already restore it by Undo.
        if not hou.undos.areEnabled():
            original_write = navigation._write_control
            def fail_restore(node, label):
                if node.path() == path and label == '实际入口':
                    raise RuntimeError('injected restore failure')
                original_write(node, label)
            navigation._write_control = fail_restore
            try:
                bad_restore = bridge.run_code(
                    f"network_controls({scope!r},[{{'node':{path!r},'label':'unrestored'}}])\nraise RuntimeError('restore failure case')",
                    owner_session=owner, owner_call='restore-failure')
                assert not bad_restore['ok'] and not bad_restore['rollback']['network_controls']['ok'], bad_restore
                assert 'injected restore failure' in bad_restore['rollback']['error'], bad_restore
                assert bad_restore['transaction']['status'] == 'recovery_unverified', bad_restore
            finally:
                navigation._write_control = original_write
                navigation._write_control(hou.node(path), '实际入口')
        renamed = bridge.run_code(f"rename_node({path!r},'renamed')\nnetwork_controls({scope!r},[{{'node':'renamed','label':'renamed failure'}}])\nraise RuntimeError('rename then fail')",
                                  owner_session=owner, owner_call='rename-failure')
        assert not renamed['ok'] and renamed['rollback']['network_controls']['ok'], renamed
        live_path = path if hou.node(path) is not None else scope + '/renamed'
        assert hou.node(live_path).userData(navigation.CONTROL_KEY) == '实际入口', renamed
        replacement_name = hou.node(live_path).name()
        replaced = bridge.run_code(
            f"network_controls({scope!r},[{{'node':{live_path!r},'label':'old metadata'}}])\n"
            f"delete_node({live_path!r})\nc=tab_create({scope!r},'null',name={replacement_name!r})\n"
            f"network_controls({scope!r},[{{'node':{replacement_name!r},'label':'new metadata'}}])\n"
            "raise RuntimeError('replacement then fail')",
                                   owner_session=owner, owner_call='replacement-failure')
        assert not replaced['ok'] and replaced['rollback']['network_controls']['ok'], replaced
        surviving = hou.node(live_path)
        if surviving is not None:
            assert surviving.userData(navigation.CONTROL_KEY) in (None, '实际入口'), replaced
        path = live_path
        denied = bridge.run_code(f"network_controls({scope!r},[{{'node':{path!r},'label':'read only'}}])",
                                 read_only=True, owner_session=owner, owner_call='read-only')
        assert not denied['ok'], denied
        hou.node(scope).destroy()

    bridge_contract()

    print('PASS explicit controls: no-name inference, scoped ownership, no cook, local/exec compensation, rename and HIP persistence ' + hou.applicationVersionString())
finally:
    current = hou.node(parent_path)
    if current is not None:
        current.destroy()
    current = hou.node('/obj/__control_outside_' + suffix)
    if current is not None:
        current.destroy()
