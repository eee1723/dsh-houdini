"""Headless rejection and literal native UI command arguments in isolated HOM."""
from pathlib import Path
import sys
import hou

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_ui_capture as capture
import dsh_hou_helpers as helpers

assert not hou.isUIAvailable(), 'this regression must run in hython'
before = (hou.hipFile.path(), hou.hipFile.hasUnsavedChanges(), hou.frame(), tuple(hou.selectedNodes()), tuple(hou.node('/obj').children()))
for view in ('parameters', 'network'):
    try:
        capture.prepare_ui_capture('/obj', view=view)
        raise AssertionError('headless UI unexpectedly succeeded')
    except ValueError as error:
        assert 'unsupported in headless' in str(error), str(error)
assert before == (hou.hipFile.path(), hou.hipFile.hasUnsavedChanges(), hou.frame(), tuple(hou.selectedNodes()), tuple(hou.node('/obj').children()))
assert not helpers._PRODUCED_IMAGES
for value in ("/obj/正常节点", "$F", "`strlen('x')`", "semi; echo altered", "quote'and\\slash", 'double"quote'):
    output, error = hou.hscript('echo -n ' + capture._hscript_literal(value))
    assert not error and output == value, (value, output, error)
for value in ('line\nbreak', 'line\rbreak', 'zero\x00byte'):
    try:
        capture._hscript_literal(value)
        raise AssertionError('native command accepted multiline input')
    except ValueError:
        pass
print('native UI screenshot headless rejection and HScript literal quoting passed: ' + hou.applicationVersionString())
