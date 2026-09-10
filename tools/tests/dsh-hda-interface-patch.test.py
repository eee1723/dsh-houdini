"""Real HDA definition edits: old channels, multiple instances, preview and rollback."""
import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h
import dsh_hda_interfaces as api


def run(code, owner='tool-author', read_only=False):
    result = b.run_code(code, owner_session=owner, owner_call='interface-test', read_only=read_only)
    assert result['ok'], result.get('error')
    return result.get('result')


def reject(fn, text):
    try:
        fn()
    except Exception as error:
        assert text in str(error), str(error)
    else:
        raise AssertionError('expected rejection: ' + text)


with tempfile.TemporaryDirectory(prefix='dsh-interface-') as temp:
    library = Path(temp) / 'test.hda'
    target = run(f"""
n = tab_create('/obj', 'subnet', name='interface_fixture')
__result__ = hda_create(n, 'dsh_fixture::interface::1.0', hda_file={str(library)!r})
""")['node']
    spec = [{'type': 'folder', 'name': 'controls', 'label': 'Controls', 'parms': [
        {'type': 'float', 'name': 'amount', 'default': 2.0},
        {'type': 'int', 'name': 'count', 'default': 3},
        {'type': 'string', 'name': 'resource', 'default': 'relative'},
    ]}]
    run(f'hda_set_interface({target!r}, {spec!r}, keep_std=False)')
    second = run("__result__=tab_create('/obj', 'dsh_fixture::interface::1.0', name='second').path()")
    n, n2 = hou.node(target), hou.node(second)
    # Direct HOM here arranges adversarial fixture state, never a user HIP.
    n.parm('amount').setExpression('$F*0.5', hou.exprLanguage.Hscript)
    key = hou.Keyframe(); key.setFrame(1); key.setValue(7)
    n.parm('count').setKeyframe(key)
    n.parm('resource').set('$HIP/asset.bgeo'); n.parm('resource').lock(True)
    n2.parm('amount').set(4.0)
    before_states = api.parameter_states(n), api.parameter_states(n2)
    old_bytes = library.read_bytes()
    info = run(f'__result__=hda_info({target!r}, include_state=True)', read_only=True)
    assert info['parameter_states'] == before_states[0]
    revision = info['interface_sha256']
    edits = [{'op': 'update', 'name': 'amount', 'fields': {'label': 'Magnitude', 'default': 5.0, 'help': 'Unit distance'}},
             {'op': 'add', 'folder': 'controls', 'spec': {'type': 'toggle', 'name': 'enabled', 'default': True}}]
    call = f'hda_set_interface({target!r}, edits={edits!r}, expected_sha256={revision!r}'
    preview = run('__result__=' + call + ', dry_run=True)')
    assert preview['scene_writes'] == 0 and not preview['applied']
    assert library.read_bytes() == old_bytes and api.parameter_states(n) == before_states[0]
    envelope = b.run_code('__result__=' + call + ', dry_run=True)', owner_session='tool-author')
    assert envelope['transaction']['status'] == 'no_scene_change', envelope
    result = run('__result__=' + call + ')')
    assert result['current_state_preserved'] and len(result['affected_instances']) == 2
    for node, state in zip((n, n2), before_states):
        after = {p['name']: p for p in api.parameter_states(node)}
        assert all(after[p['name']] == p for p in state)
        assert node.parm('amount').parmTemplate().label() == 'Magnitude'
        assert node.parm('amount').parmTemplate().defaultValue() == (5.0,)
    third = run("__result__=tab_create('/obj', 'dsh_fixture::interface::1.0', name='new_defaults').path()")
    assert hou.node(third).evalParm('amount') == 5.0
    # Entire batch rejected, with byte-for-byte library/state preservation.
    snapshot = library.read_bytes()
    bad = b.run_code(call + ')', owner_session='tool-author')
    assert not bad['ok'] and 'stale interface' in bad['error']
    assert bad['transaction']['status'] == 'no_scene_change', bad
    assert library.read_bytes() == snapshot
    revision = api.interface_revision(n)
    with h._execution_owner('tool-author', 'negative'):
        for bad_edits, message in [
            ([{'op': 'update', 'name': 'amount', 'fields': {'label': 'Never applied'}},
              {'op': 'update', 'name': 'missing', 'fields': {'label': 'x'}}], 'missing template'),
            ([{'op': 'update', 'name': 'amount', 'fields': {'name': 'renamed'}}], 'supported fields'),
            ([{'op': 'update', 'name': 'amount', 'fields': {'default': float('nan')}}], 'invalid literal'),
            ([{'op': 'update', 'name': 'count', 'fields': {'min': 1.5}}], 'must be an integer'),
            ([{'op': 'add', 'spec': {'type': 'float', 'name': 'amount'}}], '重复'),
            ([{'op': 'add', 'spec': {'type': 'float', 'name': 'x', 'typo': 1}}], 'unknown fields'),
            ([{'op': 'add', 'spec': {'type': 'float', 'name': 'x', 'default': float('nan')}}], 'invalid literal'),
            ([{'op': 'add', 'spec': {'type': 'float', 'name': 'x', 'callback': 'pass'}}], 'unknown fields'),
            ([{'op': 'add', 'spec': {'type': 'int', 'name': 'x', 'default': 1.5}}], 'invalid literal'),
        ]:
            reject(lambda: h.hda_set_interface(n, edits=bad_edits, expected_sha256=revision), message)
            assert library.read_bytes() == snapshot
    # Definition affects all instances, even when the explicitly targeted node is owned.
    foreign = run("__result__=tab_create('/obj', 'dsh_fixture::interface::1.0', name='foreign').path()", owner='other')
    with h._execution_owner('tool-author', 'foreign'):
        edit = [{'op': 'update', 'name': 'amount', 'fields': {'help': 'Updated help'}}]
        reject(lambda: h.hda_set_interface(n, edits=edit, expected_sha256=revision), 'ownership guard')
    assert library.read_bytes() == snapshot
    hou.node(foreign).destroy()
    # Query and covered raw mutation remain rejected.
    denied = b.run_code(f'hda_set_interface({target!r}, edits={edit!r}, expected_sha256={revision!r})',
                        owner_session='tool-author', read_only=True)
    assert not denied['ok'] and 'read-only' in denied['error']
    denied = b.run_code(f'n=hou.node({target!r}); n.setParmTemplateGroup(n.parmTemplateGroup())',
                        owner_session='tool-author', allow_raw='cannot bypass')
    assert not denied['ok'] and 'cannot exempt' in denied['error']
    # Fail after disk write; restore loaded definition, disk bytes and old channels.
    original_restore = api._restore
    calls = []
    def fail_once(states):
        errors = original_restore(states)
        calls.append(1)
        return errors + (['injected restoration failure'] if len(calls) == 1 else [])
    try:
        api._restore = fail_once
        with h._execution_owner('tool-author', 'rollback'):
            reject(lambda: h.hda_set_interface(n, edits=edit, expected_sha256=revision), 'injected restoration failure')
    finally:
        api._restore = original_restore
    assert library.read_bytes() == snapshot and api.interface_revision(n) == revision
    assert n.parm('amount').keyframes() and n.parm('resource').isLocked()
    before_condition_keys = n.parm('count').keyframes()
    with h._execution_owner('tool-author', 'conditional'):
        result = h.hda_set_interface(n, edits=[{'op': 'update', 'name': 'count', 'fields': {
            'disable_when': '{ enabled == 0 }', 'hide_when': '{ enabled == 0 }'}}], expected_sha256=revision)
    assert n.parm('count').parmTemplate().conditionals()[hou.parmCondType.DisableWhen] == '{ enabled == 0 }'
    assert n.parm('count').keyframes() == before_condition_keys
    assert result['current_state_preserved']
    for node in (n, n2, hou.node(third)):
        node.destroy()
    hou.hda.uninstallFile(str(library))

# Repair must pick up changed interface code, without opening a server in this test.
import dsh_launcher as launcher
reload_module = launcher.importlib.reload
stop_bridge, start_bridge = b.stop, b.start
events = []
original_states = api.parameter_states
try:
    api.parameter_states = lambda node: 'stale interface module'
    b.stop = lambda: events.append('stop')
    b.start = lambda *args: events.append('start')
    launcher.importlib.reload = lambda module: reload_module(module) if module is api else module
    launcher.restart_bridge()
    assert api.parameter_states is not original_states
    assert api.parameter_states.__module__ == 'dsh_hda_interfaces'
    assert events == ['stop', 'start']
finally:
    launcher.importlib.reload = reload_module
    b.stop, b.start = stop_bridge, start_bridge

print('HDA interface preview/state/ownership/rollback/reload passed on ' + hou.applicationVersionString())
