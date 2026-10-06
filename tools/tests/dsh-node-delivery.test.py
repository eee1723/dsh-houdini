"""H21/H22 persistent node deliveries, exact HIP resolution and metadata rollback."""
from pathlib import Path
import sys,tempfile,uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge
import dsh_network_navigation as nav

session='node-delivery-'+uuid.uuid4().hex
def call(code,read_only=False):
    return bridge.run_code(code,owner_session=session,owner_call=uuid.uuid4().hex,read_only=read_only)
def ok(code):
    r=call(code);assert r['ok'],r;return r
with tempfile.TemporaryDirectory(prefix='dsh-node-delivery-') as directory:
    hip=str(Path(directory)/'asset.hip')
    obj=ok("p=tab_create('/obj','geo',name='node_delivery_fixture')\nc=tab_create(p,'null',name='panel')\nb=tab_create(p,'box',name='body')\no=tab_create(p,'null',name='OUT',inputs=[b])\nsop_set_output(o)\n__result__=p.path()")['result']
    ok(f"scene_save_as({hip!r},expected_current_path={hou.hipFile.path()!r},reason='isolated node delivery fixture')")
    code=f"__result__=present_nodes([{{'node':{obj+'/panel'!r},'label':'工程控制','role':'control','description':'调整尺寸和重复数量'}},{{'node':{obj+'/OUT'!r},'label':'模型输出','role':'output'}}])"
    before={n.path():(n.isDisplayFlagSet(),n.isRenderFlagSet(),[(p.name(),p.rawValue()) for p in n.parms()]) for n in hou.node(obj).children()}
    first=ok(code)['result'];assert first['kind']=='houdini/node-delivery-v1' and first['requires_save']
    assert len(first['nodes'])==2 and len({n['id'] for n in first['nodes']})==2
    assert first['nodes'][0]['description']=='调整尺寸和重复数量' and first['nodes'][0]['context']=='Sop'
    assert before=={n.path():(n.isDisplayFlagSet(),n.isRenderFlagSet(),[(p.name(),p.rawValue()) for p in n.parms()]) for n in hou.node(obj).children()}
    again=ok(code);assert again['result']['scene_writes']==0 and not again['result']['requires_save']
    assert again['transaction']['status']=='no_scene_change'
    assert [n['id'] for n in first['nodes']]==[n['id'] for n in again['result']['nodes']]
    reference={'id':first['nodes'][0]['id']}
    old=reference['id']
    fail=call(f"present_nodes([{{'node':{obj+'/panel'!r},'role':'control','label':'failed','new_identity':True}}])\nraise RuntimeError('after publishing failure')")
    assert not fail['ok'] and hou.node(obj+'/panel').userData(nav.NODE_ID_KEY)==old,fail
    assert hou.node(obj+'/panel').userData(nav.CONTROL_KEY)=='工程控制' and fail['rollback']['network_controls']['ok']
    denied=call(code,read_only=True);assert not denied['ok']
    ok(f"rename_node({obj+'/panel'!r},'renamed_panel')\nscene_save(expected_path={hip!r})")
    hou.hipFile.load(hip,suppress_save_prompt=True)
    resolved=nav.resolve_reference(reference,hip)
    assert resolved.path()==obj+'/renamed_panel' and resolved.userData(nav.CONTROL_KEY)=='工程控制'
    try:nav.resolve_reference(reference,str(Path(directory)/'other.hip'))
    except ValueError as error:assert '工程不同' in str(error)
    else:raise AssertionError('different HIP must reject')
    duplicate=hou.node(obj).copyItems([resolved])[0]
    assert duplicate.userData(nav.NODE_ID_KEY)==old
    try:nav.resolve_reference(reference,hip)
    except ValueError as error:assert '重复' in str(error)
    else:raise AssertionError('duplicate UUID must reject')
    renew=ok(f"__result__=present_nodes([{{'node':{duplicate.path()!r},'new_identity':True}}],allow_foreign='explicit copied node in isolated fixture')")['result']
    assert renew['nodes'][0]['id']!=old and nav.resolve_reference(reference,hip)==resolved
    original_path=resolved.path();resolved.destroy()
    replacement=hou.node(obj).createNode('null','renamed_panel')
    assert replacement.path()==original_path
    try:nav.resolve_reference(reference,hip)
    except ValueError as error:assert '没有这个节点' in str(error)
    else:raise AssertionError('same path replacement must not be targeted')
    assert not hasattr(nav,'show_controls')
    print('persistent node delivery contract passed on '+hou.applicationVersionString())
