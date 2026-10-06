"""Persistent preview boxes retain only service members and survive HIP reload."""

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))

import hou
import dsh_hou_helpers as h


def bounds(box):
    return tuple(box.position()), tuple(box.size())


def node_positions(parent):
    return {node.name(): tuple(node.position()) for node in parent.children()}


def service_node(parent, node_type, name):
    node = parent.createNode(node_type, name)
    node.setUserData(h._RENDER_OWNER_KEY, h._RENDER_OWNER_VALUE)
    return node


with tempfile.TemporaryDirectory(prefix='dsh-render-service-box-') as folder:
    hou.hipFile.clear(suppress_save_prompt=True)
    obj, out = hou.node('/obj'), hou.node('/out')
    foreign = obj.createNode('geo', 'user_asset')
    foreign.setPosition(hou.Vector2(0, 0))
    nodes = [service_node(obj, 'geo', h._RENDER_PROXY_NAME),
             service_node(obj, 'cam', h._RENDER_CAMERA_NAME),
             service_node(obj, 'null', h._RENDER_TARGET_NAME)]
    old_rop = service_node(out, 'opengl', h._RENDER_ROP_NAME)
    obj_box = h._render_service_box(obj, h._RENDER_OBJ_BOX_NAME, nodes)
    h._render_service_box(out, h._RENDER_OUT_BOX_NAME, [old_rop])
    old_position = tuple(old_rop.position())
    active_rop = h._owned_node(out, h._RENDER_FLIPBOOK_NAME, 'null')
    assert active_rop.position()[0] == old_rop.position()[0]
    assert active_rop.position()[1] < old_rop.position()[1]
    assert tuple(old_rop.position()) == old_position
    out_box = h._render_service_box(out, h._RENDER_OUT_BOX_NAME, [active_rop])
    assert set(obj_box.items(recurse=False)) == set(nodes)
    assert set(out_box.items(recurse=False)) == {old_rop, active_rop}
    assert not obj_box.autoFit() and not out_box.autoFit()
    assert obj_box.position()[0] > foreign.position()[0] + foreign.size()[0]
    expected_bounds = {'obj': bounds(obj_box), 'out': bounds(out_box)}
    expected_positions = {'obj': node_positions(obj), 'out': node_positions(out)}
    scene = str(Path(folder) / 'service.hip')
    hou.hipFile.save(scene)
    hou.hipFile.load(scene, suppress_save_prompt=True, ignore_load_warnings=True)
    obj, out = hou.node('/obj'), hou.node('/out')
    obj_box = obj.findNetworkBox(h._RENDER_OBJ_BOX_NAME)
    out_box = out.findNetworkBox(h._RENDER_OUT_BOX_NAME)
    assert obj_box.comment() == out_box.comment() == h._RENDER_BOX_COMMENT
    actual_bounds = {'obj': bounds(obj_box), 'out': bounds(out_box)}
    assert actual_bounds == expected_bounds, (actual_bounds, expected_bounds)
    assert {'obj': node_positions(obj), 'out': node_positions(out)} == expected_positions
    assert not obj_box.autoFit() and not out_box.autoFit()

    # Reproduce an older expanded box and accidental membership. Repair only
    # changes the box; authored and previously positioned service nodes stay put.
    foreign = obj.node('user_asset')
    obj_box.addItem(foreign)
    obj_box.setBounds(hou.BoundingRect(0, -5, 10, 3))
    obj_box.setAutoFit(True)
    before = node_positions(obj)
    nodes = [obj.node(name) for name in
             (h._RENDER_PROXY_NAME, h._RENDER_CAMERA_NAME, h._RENDER_TARGET_NAME)]
    repaired = h._render_service_box(obj, h._RENDER_OBJ_BOX_NAME, nodes)
    assert set(repaired.items(recurse=False)) == set(nodes)
    assert foreign.parentNetworkBox() is None
    assert node_positions(obj) == before
    assert bounds(repaired) == expected_bounds['obj']
    assert not repaired.autoFit()
    repeated = h._render_service_box(obj, h._RENDER_OBJ_BOX_NAME, nodes)
    assert bounds(repeated) == expected_bounds['obj']
    assert node_positions(obj) == before

    # A user may move the service group. Refit and reopening preserve that
    # actual placement instead of moving it back to a plugin-chosen anchor.
    repeated.move(hou.Vector2(7, -2))
    shifted_positions = node_positions(obj)
    h._render_service_box(obj, h._RENDER_OBJ_BOX_NAME, nodes)
    shifted_bounds = bounds(repeated)
    assert node_positions(obj) == shifted_positions
    assert shifted_positions['user_asset'] == before['user_asset']
    hou.hipFile.save(scene)
    hou.hipFile.load(scene, suppress_save_prompt=True, ignore_load_warnings=True)
    obj = hou.node('/obj')
    assert bounds(obj.findNetworkBox(h._RENDER_OBJ_BOX_NAME)) == shifted_bounds
    assert node_positions(obj) == shifted_positions
    hou.hipFile.clear(suppress_save_prompt=True)

print('render service box persistence passed on ' + hou.applicationVersionString())
