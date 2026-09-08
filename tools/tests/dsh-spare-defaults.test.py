"""Existing spare defaults: literal updates, state preservation and fail-closed ownership."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as b


def rejects(fn, message):
    try:
        fn()
    except Exception as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError('expected rejection: ' + message)


with h._execution_owner('defaults-owner', 'setup'):
    ctrl = h.tab_create('/obj', 'null', '__spare_defaults')
    h.create_spare_parms(ctrl, spec=[{'type': 'folder', 'name': 'controls', 'parms': [
        {'type': 'float', 'name': 'length', 'default': 2., 'min': 0, 'min_strict': True},
        {'type': 'int', 'name': 'count', 'default': 3},
        {'type': 'toggle', 'name': 'enabled', 'default': True},
        {'type': 'string', 'name': 'label', 'default': 'initial'},
        {'type': 'float', 'name': 'other', 'default': 9.},
    ]}])
try:
    ctrl.parm('length').setExpression('2+$F/10', hou.exprLanguage.Hscript)
    k = hou.Keyframe(); k.setFrame(1); k.setValue(4)
    ctrl.parm('count').setKeyframe(k)
    ctrl.parm('label').set('$HIP/literal')
    ctrl.parm('other').lock(True)
    keys = {name: ctrl.parm(name).keyframes() for name in ('length', 'count')}
    old_frame = hou.frame()
    with h._execution_owner('defaults-owner', 'edit'):
        result = h.create_spare_parms(ctrl, update_defaults={'length': 3.5, 'count': 7, 'enabled': False, 'label': 'new'})
    assert result['ok'] and result['mode'] == 'update_defaults' and result['current_state_preserved'], result
    assert ctrl.parm('length').parmTemplate().defaultValue() == (3.5,)
    assert ctrl.parm('count').parmTemplate().defaultValue() == (7,)
    assert ctrl.parm('enabled').parmTemplate().defaultValue() is False
    assert ctrl.evalParm('enabled') == 1  # defaults do not reset current values
    assert ctrl.parm('label').unexpandedString() == '$HIP/literal'
    assert all(ctrl.parm(name).keyframes() == saved for name, saved in keys.items())
    assert ctrl.parm('other').isLocked() and ctrl.evalParm('other') == 9 and hou.frame() == old_frame
    # A reset now uses the new default, independently from the existing current value.
    ctrl.parm('label').revertToDefaults()
    assert ctrl.evalParm('label') == 'new'
    with h._execution_owner('defaults-owner', 'negative'):
        before = ctrl.parmTemplateGroup().asDialogScript()
        for updates, message in [({}, '1..32'), ({'length': 8, 'missing': 1}, 'existing spare'),
                                 ({'tx': 1}, 'existing spare'), ({'length': -1}, 'strict'),
                                 ({'length': float('nan')}, 'invalid literal'),
                                 ({'count': 1.5}, 'invalid literal'), ({'enabled': 2}, 'invalid literal'),
                                 ({'label': 5}, 'invalid literal'), ({'other': 5}, '锁定')]:
            rejects(lambda: h.create_spare_parms(ctrl, update_defaults=updates), message)
            assert ctrl.parmTemplateGroup().asDialogScript() == before
        rejects(lambda: h.create_spare_parms(ctrl, defaults={}, update_defaults={'length': 1}), 'exclusive')
        rejects(lambda: h.create_spare_parms(ctrl, spec=[{'type': 'float', 'name': 'length'}]), '隐式覆盖')
    # Unsupported controls are rejected before any template is written.
    ctrl.addSpareParmTuple(hou.FloatParmTemplate('vector', 'Vector', 3))
    ctrl.addSpareParmTuple(hou.IntParmTemplate('choice', 'Choice', 1, menu_items=('a', 'b')))
    callback = hou.FloatParmTemplate('callback', 'Callback', 1)
    callback.setScriptCallback('pass'); callback.setScriptCallbackLanguage(hou.scriptLanguage.Python)
    ctrl.addSpareParmTuple(callback)
    expression_default = hou.FloatParmTemplate('dynamic', 'Dynamic', 1, default_expression=('1+2',))
    ctrl.addSpareParmTuple(expression_default)
    with h._execution_owner('defaults-owner', 'unsupported'):
        for name, message in [('vectorx', 'scalar'), ('choice', 'menu'), ('callback', 'scalar'), ('dynamic', 'expression defaults')]:
            rejects(lambda: h.create_spare_parms(ctrl, update_defaults={name: 1}), message)
    with h._execution_owner('different-owner', 'foreign'):
        rejects(lambda: h.create_spare_parms(ctrl, update_defaults={'length': 6}), 'ownership guard')
        allowed = h.create_spare_parms(ctrl, update_defaults={'length': 6}, allow_foreign='User explicitly chose this controller')
        assert allowed['ok']
    ctrl.setUserData(h._RENDER_OWNER_KEY, h._RENDER_OWNER_VALUE)
    with h._execution_owner('different-owner', 'service'):
        rejects(lambda: h.create_spare_parms(ctrl, update_defaults={'length': 7}, allow_foreign='explicit target'), 'persistent')
    ctrl.destroyUserData(h._RENDER_OWNER_KEY)
    # Bridge denies query and raw template application even with an exemption.
    query = b.run_code(f'create_spare_parms({ctrl.path()!r}, update_defaults={{"length":7}})',
                       owner_session='defaults-owner', read_only=True)
    assert not query['ok'] and 'read-only' in query['error']
    edited = b.run_code(f'__result__=create_spare_parms({ctrl.path()!r}, update_defaults={{"length":7}})',
                        owner_session='defaults-owner', owner_call='bridge-update')
    assert edited['ok'] and edited['result']['updated']['length']['after'] == [7.0], edited
    assert edited['evidence'][0]['mode']=='update_defaults' and edited['evidence'][0]['current_state_preserved']
    assert ctrl.parm('length').keyframes() == keys['length']
    raw = b.run_code(f'n=hou.node({ctrl.path()!r}); n.setParmTemplateGroup(n.parmTemplateGroup())',
                     owner_session='defaults-owner', allow_raw='attempt to bypass covered defaults update')
    assert not raw['ok'] and 'cannot exempt' in raw['error']
    # A failed readback restores the entire previous template and current animation.
    original_restore = h._restore_parameters
    calls = []
    def fail_once(snapshots):
        errors = original_restore(snapshots); calls.append(1)
        return errors + (['injected restore failure'] if len(calls) == 1 else [])
    old = ctrl.parm('length').parmTemplate().defaultValue()
    try:
        h._restore_parameters = fail_once
        with h._execution_owner('defaults-owner', 'restore'):
            rejects(lambda: h.create_spare_parms(ctrl, update_defaults={'length': 8}), 'injected restore failure')
    finally:
        h._restore_parameters = original_restore
    assert ctrl.parm('length').parmTemplate().defaultValue() == old
    assert ctrl.parm('length').keyframes() == keys['length']
finally:
    ctrl.destroy()

print('spare default update/state/validation/ownership/rollback passed on ' + hou.applicationVersionString())
