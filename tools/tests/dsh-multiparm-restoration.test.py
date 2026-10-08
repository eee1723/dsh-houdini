"""Count rollback preserves real nested instances, channels and recovery facts."""
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h

OWNER = 'multiparm-restoration'


def run(code):
    return b.run_code(code, owner_session=OWNER, owner_call='multiparm-test')


def channels(node):
    """Independent native readback, including the actual instantiated tree."""
    result = {}
    for p in node.parms():
        if not (p.isMultiParmParent() or p.isMultiParmInstance()):
            continue
        keys = tuple(p.keyframes())
        value = (p.unexpandedString() if p.parmTemplate().type() == hou.parmTemplateType.String
                 else p.eval()) if not keys else None
        if isinstance(value, hou.Ramp):
            value = (value.basis(), value.keys(), value.values())
        result[p.name()] = (value, tuple(k.asCode() for k in keys), p.isLocked(),
                            tuple(child.name() for child in p.multiParmInstances()))
    return result


created = run("g=tab_create('/obj','geo',name='__multiparm_restore')\n"
              "m=tab_create(g,'object_merge',name='merge')\n"
              "set_parms(m,{'numobj':2})\n"
              "set_parms(m,{'objpath1':'/obj/USER_A','objpath2':'/obj/USER_B'})\n"
              "__result__=g.path()")
assert created['ok'], created
root = hou.node(created['result'])
try:
    merge = root.node('merge')
    before = channels(merge)
    receipt = run(f"try:\n set_parms({merge.path()!r},{{'numobj':0,'xformtype':'invalid-token'}})\n"
                  f"except Exception:\n pass\nset_parm({root.path()!r},'ty',7)")
    assert receipt['ok'] and receipt['verbs'][0]['summary']['restored'] is True, receipt
    assert channels(merge) == before, (before, channels(merge))
    assert root.evalParm('ty') == 7

    # Native nested structure: different counts in each outer instance. It
    # carries literal strings, keyed numeric channels, expressions and locks.
    outer = hou.FolderParmTemplate('groups', 'Groups', folder_type=hou.folderType.MultiparmBlock)
    inner = hou.FolderParmTemplate('items#', 'Items', folder_type=hou.folderType.MultiparmBlock)
    inner.addParmTemplate(hou.FloatParmTemplate('value#_#', 'Value', 1))
    outer.addParmTemplate(inner)
    outer.addParmTemplate(hou.StringParmTemplate('label#', 'Label', 1))
    outer.addParmTemplate(hou.RampParmTemplate('profile#', 'Profile', hou.rampParmType.Float))
    group = root.parmTemplateGroup()
    group.append(outer)
    root.setParmTemplateGroup(group)
    root.parm('groups').set(2)
    root.parm('items1').set(2)
    root.parm('items2').set(1)
    root.parm('label1').set('$HIP/authored-input.bgeo.sc')
    root.parm('label2').setExpression('"item_"+str(hou.frame())', hou.exprLanguage.Python)
    root.parm('profile1').set(hou.Ramp((hou.rampBasis.Linear, hou.rampBasis.CatmullRom),
                                   (0.0, 1.0), (0.2, 0.8)))
    keys = []
    for frame, value in ((1, 3), (12, 9)):
        key = hou.Keyframe(value)
        key.setFrame(frame)
        keys.append(key)
    root.parm('value1_1').setKeyframes(keys)
    root.parm('value1_2').setExpression('2+$F', hou.exprLanguage.Hscript)
    root.parm('value2_1').set(23)
    root.parm('value2_1').lock(True)
    before = channels(root)
    # Explicit leaf comes before its count, so snapshot insertion order must
    # not decide restoration order or mistake implicit snapshots for overlap.
    receipt = run(f"try:\n set_parms({root.path()!r},{{'label1':'changed','groups':0,'tx':[1]}})\n"
                  "except Exception:\n pass")
    assert receipt['ok'] and receipt['verbs'][0]['summary']['restored'] is True, receipt
    assert channels(root) == before, (before, channels(root))
    assert receipt['transaction']['status'] == 'no_scene_change', receipt
    nested = run(f"try:\n set_parms({root.path()!r},{{'items1':0,'tx':[1]}})\n"
                 "except Exception:\n pass")
    assert nested['ok'] and channels(root) == before, nested
    accepted = run(f"set_parms({root.path()!r},{{'groups':2,'label1':'explicit leaf'}})")
    assert accepted['ok'] and root.evalParm('label1') == 'explicit leaf', accepted
    root.parm('label1').set('$HIP/authored-input.bgeo.sc')

    # A failed native count restoration stays unrecovered and blocks the next
    # mutation even when the agent catches both exceptions in the same exec.
    original_set = hou.Parm.set
    def fail_count_restore(parm, value, *args, **kwargs):
        if parm.node() == root and parm.name() == 'groups' and value == 2:
            raise RuntimeError('injected native count restoration failure')
        return original_set(parm, value, *args, **kwargs)
    with patch.object(hou.Parm, 'set', fail_count_restore):
        failed = run(f"try:\n set_parms({root.path()!r},{{'groups':0,'tx':[1]}})\n"
                     f"except Exception:\n pass\ntry:\n set_parm({root.path()!r},'ty',999)\n"
                     "except Exception:\n pass")
    assert not failed['ok'] and failed['verbs'][0]['summary']['restored'] is False, failed
    assert failed['verbs'][1]['summary']['dispatched'] is False, failed
    assert root.evalParm('ty') == 7, failed

    # A same-path replacement must never become the snapshot's target.
    old = root.createNode('xform', 'replacement')
    state = h._parameter_snapshot([old.parm('tx')])
    old.destroy()
    replacement = root.createNode('xform', 'replacement')
    replacement.parm('tx').set(31)
    assert h._restore_parameters(state)
    assert replacement.evalParm('tx') == 31
finally:
    root.destroy()

print('multiparm tree/value/expression/key/lock restoration and failure dispatch passed on ' + hou.applicationVersionString())
