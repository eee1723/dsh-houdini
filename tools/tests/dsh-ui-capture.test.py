"""Headless UI observation rejection in isolated HOM."""

from pathlib import Path
import sys
import hou

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_media_output
import dsh_bridge as bridge
import dsh_ui_capture as capture
import dsh_hou_helpers as helpers

assert not hou.isUIAvailable(), 'this regression must run in hython'
before = (hou.hipFile.path(), hou.hipFile.hasUnsavedChanges(), hou.frame(), tuple(hou.selectedNodes()), tuple(hou.node('/obj').children()))
for call in (lambda: capture.discover_ui_surfaces(runtime_id=bridge._RUNTIME_ID), lambda: capture.prepare_ui_capture(runtime_id=bridge._RUNTIME_ID, target='ui:headless')):
    try:
        call()
        raise AssertionError('headless existing-surface capture unexpectedly succeeded')
    except ValueError as error:
        assert 'unsupported in headless' in str(error), str(error)
assert before == (hou.hipFile.path(), hou.hipFile.hasUnsavedChanges(), hou.frame(), tuple(hou.selectedNodes()), tuple(hou.node('/obj').children()))
assert not dsh_media_output._PRODUCED_IMAGES
print('native UI observation headless rejection passed: ' + hou.applicationVersionString())
