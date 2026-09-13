"""Public ports and packed-content checkpoints; isolated fixtures, no user HIP."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h
from dsh_sop_contracts import _content_nonempty

OWNER = 'output-publication-author'
def run(code, ok=True, owner=OWNER):
    r = b.run_code(code, owner_session=owner)
    assert r['ok'] is ok, r.get('error', r)
    return r

run("g=tab_create('/obj','geo','publication_fixture')\n"
    "s=tab_create(g,'subnet','module')\n"
    "shape=tab_create(s,'box','shape')\n"
    "empty=tab_create(s,'null','empty')")
root = hou.node('/obj/publication_fixture')
sub = root.node('module')
try:
    # Ordinary geo delivery needs only an explicit SOP and flags, no Output.
    run(f"plain=tab_create({root.path()!r},'box','plain')\nsop_set_output(plain)")
    assert root.node('output0') is None
    r=run(f"__result__=verify_network({root.path()!r},output='plain',nodes=[{root.node('plain').path()!r}])")['result']
    assert r['ok'] and r['public_output'] is None
    assert root.displayNode()==root.node('plain')
    # Recreate native initialization's unconnected output even in headless mode.
    if not sub.node('output0'):
        run(f"tab_create({sub.path()!r},'output','output0')")
    sub.node('output0').setInput(0, None)
    run(f"sop_set_output({sub.node('shape').path()!r})")
    assert not sub.geometry().prims() and sub.node('shape').geometry().prims()
    r = run(f"verify_network({sub.path()!r},output='shape',output_index=0)", ok=False)
    assert 'public_output' in r['error']
    # Publish reuses the native Output, never deletes it or invents a new subnet.
    identity = sub.node('output0').sessionId()
    r = run(f"__result__=sop_set_output({sub.node('shape').path()!r},output_index=0)")['result']
    assert r['public_output']['ok'] and sub.node('output0').sessionId() == identity
    assert sub.node('output0').input(0) == sub.node('shape')
    assert sub.displayNode() == sub.node('output0')
    run(f"verify_network({sub.path()!r},output='shape',output_index=0)")
    run(f"sop_set_output({sub.node('empty').path()!r})")
    assert sub.geometry().prims(), 'debug display must not change the public port'
    # Parent/root publication is explicit; source is the child subnet itself.
    run(f"sop_set_output({sub.path()!r},output_index=0)")
    assert root.node('output0').input(0) == sub
    assert root.displayNode() == root.node('output0')
    # Secondary ports preserve port zero and can be consumed separately.
    run(f"sop_set_output({sub.node('shape').path()!r},output_index=1)")
    assert sub.node('output0').sessionId() == identity
    run(f"c=tab_create({root.path()!r},'null','consumer')\nconnect({sub.path()!r},c,output=1)\ncook_node(c)")
    assert root.node('consumer').geometry().prims()
    # A wire from the wrong source port does not certify the default output.
    root.node('output0').setInput(0, sub, 1)
    r = run(f"verify_network({root.path()!r},output='module',output_index=0)", ok=False)
    assert 'public_output' in r['error']
    run(f"sop_set_output({sub.path()!r},output_index=0)")
    # Invalid index and foreign publication fail before rewiring/display changes.
    for value in ('True', '-1', '64', '1.5'):
        run(f"sop_set_output({sub.node('empty').path()!r},output_index={value})", ok=False)
    before = sub.node('output0').input(0)
    run(f"sop_set_output({sub.node('empty').path()!r},output_index=0)", ok=False, owner='other')
    assert sub.node('output0').input(0) == before
    # Owned source under a foreign parent still cannot publish its interface.
    run(f"foreign=tab_create({root.path()!r},'subnet','foreign_parent')", owner='other')
    run(f"mine=tab_create({root.path()!r}+'/foreign_parent','box','owned_shape')")
    foreign = root.node('foreign_parent')
    original_children = tuple(foreign.children())
    run(f"sop_set_output({foreign.node('owned_shape').path()!r},output_index=0)", ok=False)
    assert tuple(foreign.children()) == original_children
    run(f"dup=tab_create({sub.path()!r},'output','duplicate')")
    run(f"sop_set_output({sub.node('empty').path()!r},output_index=0)", ok=False)
    run(f"delete_node({sub.node('duplicate').path()!r})")
    run(f"down=tab_create({sub.path()!r},'null','after_port',inputs=[{sub.node('output0').path()!r}])")
    run(f"sop_set_output({sub.node('after_port').path()!r},output_index=0)", ok=False)
    # Empty native Pack has one wrapper primitive but no delivered geometry.
    run(f"p=tab_create({root.path()!r},'pack','empty_pack',inputs=[{sub.node('empty').path()!r}])", ok=False)
    run(f"e=tab_create({root.path()!r},'null','empty')\n"
        f"p=tab_create({root.path()!r},'pack','empty_pack',inputs=[e])")
    assert len(root.node('empty_pack').geometry().prims()) == 1
    r = run(f"verify_network({root.path()!r},output='empty_pack',nodes=[{root.node('empty_pack').path()!r}])", ok=False)
    assert 'empty_output' in r['error']
    run(f"connect({sub.path()!r},{root.node('empty_pack').path()!r})")
    run(f"verify_network({root.path()!r},output='empty_pack',nodes=[{root.node('empty_pack').path()!r}])")
    # Empty nested packs rejected; standalone points and native shapes accepted.
    run(f"connect({root.node('empty').path()!r},{root.node('empty_pack').path()!r})\n"
        f"tab_create({root.path()!r},'pack','nested',inputs=[{root.node('empty_pack').path()!r}])")
    run(f"verify_network({root.path()!r},output='nested',nodes=[{root.node('nested').path()!r}])", ok=False)
    point_geo = hou.Geometry(); point_geo.createPoint()
    assert _content_nonempty(point_geo)['nonempty'] is True
    assert _content_nonempty(root.node('nested').geometry(), max_depth=0)['nonempty'] is None
    # Module construction cannot certify an empty wrapper or retain failed nodes.
    spec = [{'name':'bad_pack','type':'pack','inputs':['empty']}]
    run(f"build_module({root.path()!r},{spec!r},output='bad_pack')", ok=False)
    assert root.node('bad_pack') is None
finally:
    root.destroy()
print('PASS public publication / display isolation / ownership / ports / empty nested packs '+hou.applicationVersionString())
