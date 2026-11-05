"""A failed semantic Tab creation must not degrade to bare createNode.

Run with Houdini's hython. The injected failure simulates a SideFX shelf tool
that creates one partial node and then raises.
"""

from __future__ import annotations


from pathlib import Path
import sys
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))
import dsh_node_creation

import hou
import dsh_bridge
import dsh_hou_helpers


parent = hou.node("/obj").createNode("geo", f"__dsh_tab_failure_{uuid.uuid4().hex[:8]}")
render_settings = []
original = dsh_node_creation._run_shelf_tool


def fail_after_partial_create(tool, target, type_name):
    target.createNode("null", "partial_from_failed_tool")
    raise RuntimeError("synthetic shelf initialization failure")


try:
    dsh_node_creation._run_shelf_tool = fail_after_partial_create
    outcome = dsh_bridge.run_code(
        f"tab_create({parent.path()!r}, 'copytopoints')",
        owner_session="tab-create-failure-test",
        owner_call="call-create",
    )
    assert outcome["ok"] is False, outcome
    assert "synthetic shelf initialization failure" in outcome["error"], outcome
    assert parent.children() == (), [child.path() for child in parent.children()]
    missing = dsh_bridge.run_code(
        f"tab_create({parent.path()!r}, 'null', inputs=['missing'])",
        owner_session="tab-create-failure-test", owner_call="call-preflight")
    assert not missing['ok'] and missing['transaction']['status']=='no_scene_change', missing
    assert missing['verbs'][0]['summary']['phase']=='preflight', missing
    assert missing['verbs'][0]['summary']['scene_writes']==0, missing
    dsh_node_creation._run_shelf_tool = original
    relative = dsh_bridge.run_code(
        f"p=hou.node({parent.path()!r})\na=tab_create(p,'box',name='source')\n"
        "b=tab_create(p,'null',name='out',inputs=['source'])\n"
        "__result__=verify_network(p,output='out',nodes=['source','out'])",
        owner_session="tab-create-failure-test", owner_call="call-relative")
    assert relative['ok'] and relative['result']['ok'], relative
    assert parent.node('out').input(0)==parent.node('source')
    # Both creation entrances share declared multiparm initialization; field
    # order is not an implicit prerequisite and later failures remove new nodes.
    values={'pt0':[0,0,0],'pt1':[1,0,0],'prim0':'0 1','points':2,'prims':1}
    multi=dsh_bridge.run_code(
        f"a=tab_create({parent.path()!r},'add',name='multi_direct',parms={values!r})\n"
        f"b=build_module({parent.path()!r},[{{'name':'multi_module','type':'add','parms':{values!r}}}],output='multi_module')\n"
        "__result__={'direct':[len(a.geometry().points()),len(a.geometry().prims())]}",
        owner_session='tab-create-failure-test',owner_call='multiparm-shared')
    assert multi['ok'] and multi['result']['direct']==[2,1],multi
    assert len(parent.node('multi_module').geometry().points())==2
    broken=dsh_bridge.run_code(
        f"tab_create({parent.path()!r},'add',name='multi_failed',parms={{'points':2,'pt0':[0,0]}})",
        owner_session='tab-create-failure-test',owner_call='multiparm-failure')
    assert not broken['ok'] and parent.node('multi_failed') is None,broken
    # Static discovery budgets must not limit an already-created native node.
    large=dsh_bridge.run_code(
        f"n=tab_create({parent.path()!r},'add',name='multi_large',parms={{'pt64':[7,8,9],'points':65}})\n"
        "__result__={'count':n.evalParm('points'),'last':n.parmTuple('pt64').eval()}",
        owner_session='tab-create-failure-test',owner_call='multiparm-large')
    assert large['ok'] and large['result']=={'count':65,'last':[7.0,8.0,9.0]},large
    before=set(parent.children())
    static=dsh_bridge.run_code(
        f"build_module({parent.path()!r},[{{'name':'static_large','type':'add','parms':{{'points':65}}}}],output='static_large',dry_run=True)",
        owner_session='tab-create-failure-test',owner_call='multiparm-static-budget')
    assert not static['ok'] and 'static multiparm count' in static['error'],static
    assert set(parent.children())==before and static['transaction']['status']=='no_scene_change',static
    # Inner counts and leaves precede their absent parents in the input. Each
    # newly materialized native level must be discovered before leaf writes.
    with tempfile.TemporaryDirectory(prefix='dsh-created-multiparm-') as asset_dir:
        asset_file=str(Path(asset_dir)/'nested.hda')
        asset_type='created_multiparm_fixture::nested::1.0'
        prototype=parent.createNode('subnet','nested_prototype').createDigitalAsset(
            name=asset_type,hda_file_name=asset_file)
        outer=hou.FolderParmTemplate('groups','Groups',folder_type=hou.folderType.MultiparmBlock)
        inner=hou.FolderParmTemplate('items#','Items',folder_type=hou.folderType.MultiparmBlock)
        inner.addParmTemplate(hou.FloatParmTemplate('value#_#','Value',1))
        outer.addParmTemplate(inner)
        definition=prototype.type().definition()
        group=definition.parmTemplateGroup();group.append(outer);definition.setParmTemplateGroup(group)
        prototype.destroy()
        values={'value2_2':22,'value1_2':12,'items2':2,'items1':2,'groups':2}
        nested=dsh_bridge.run_code(
            f"n=tab_create({parent.path()!r},{asset_type!r},name='multi_nested',parms={values!r})\n"
            "__result__={p:n.evalParm(p) for p in ['groups','items1','items2','value1_2','value2_2']}",
            owner_session='tab-create-failure-test',owner_call='multiparm-nested')
        assert nested['ok'] and nested['result']=={'groups':2,'items1':2,'items2':2,'value1_2':12.0,'value2_2':22.0},nested
        invalid={**values,'value2_2':[1,2]}
        nested_failure=dsh_bridge.run_code(
            f"tab_create({parent.path()!r},{asset_type!r},name='nested_failed',parms={invalid!r})",
            owner_session='tab-create-failure-test',owner_call='multiparm-nested-failure')
        assert not nested_failure['ok'] and parent.node('nested_failed') is None,nested_failure
        parent.node('multi_nested').destroy()
        hou.hda.uninstallFile(asset_file)
    not_network = dsh_bridge.run_code(
        f"tab_create({parent.node('out').path()!r}, 'box', name='invalid_child')",
        owner_session="tab-create-failure-test", owner_call="call-leaf-parent")
    assert not not_network['ok'], not_network
    assert 'is not a network that can create nodes' in not_network['error'], not_network
    assert repr(parent.path()) in not_network['error'], not_network
    assert not_network['verbs'][0]['summary']['scene_writes'] == 0, not_network
    assert not_network['transaction']['status'] == 'no_scene_change', not_network
    # tab_create/build_module and the multi-node recipe share new-node render
    # defaults. Explicit authored artistic choices are applied afterwards.
    settings = dsh_bridge.run_code(
        "n=tab_create('/stage','karmarendersettings',name='clear_settings')\n__result__=n.path()",
        owner_session='tab-create-failure-test')
    assert settings['ok'], settings
    clear = hou.node(settings['result']); render_settings.append(clear)
    assert clear.evalParm('enabledof') == 0
    assert clear.parm('picture').unexpandedString() == '$HIP/dsh-artifacts/renders/$HIPNAME/$HIPNAME.$OS.$F4.exr'
    artistic = dsh_bridge.run_code(
        "n=tab_create('/stage','karmarendersettings',name='artistic_settings',"
        "parms={'enabledof':1,'picture':'$HIP/artist/beauty.$F4.exr'})\n__result__=n.path()",
        owner_session='tab-create-failure-test')
    assert artistic['ok'], artistic
    art = hou.node(artistic['result']); render_settings.append(art)
    assert art.evalParm('enabledof') == 1
    assert art.parm('picture').unexpandedString() == '$HIP/artist/beauty.$F4.exr'
    assert clear.evalParm('enabledof') == 0, 'new defaults never rewrite another settings node'
finally:
    dsh_node_creation._run_shelf_tool = original
    if parent is not None:
        parent.destroy()
    for node in render_settings:
        node.destroy()

print("tab_create failure regression passed")
