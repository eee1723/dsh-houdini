"""HDA authoring boundary regressions; run only in isolated H21/H22 hython."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge


def run(code, ok=True):
    result = bridge.run_code(code, owner_session='public-hda-author', owner_call='public-contract')
    assert result['ok'] is ok, result.get('error')
    return result


with tempfile.TemporaryDirectory(prefix='dsh-public-hda-') as temp:
    library = Path(temp) / 'public.hda'
    run("g=tab_create('/obj','geo',name='public_fixture')\n"
        "s=tab_create(g,'subnet',name='source')\n"
        "box=tab_create(s,'box',name='shape')\n"
        "out=tab_create(s,'output',name='out')")
    source = hou.node('/obj/public_fixture/source')
    slot = source.indirectInputs()[1]
    run("s=hou.node('/obj/public_fixture/source')\n"
        "tap=tab_create(s,'null',name='tap',inputs=[s.indirectInputs()[1]])")
    r = run(f"__result__=connect({slot.path()!r}, '/obj/public_fixture/source/out')")['result']
    assert r['source'] == slot.path() and r['subnet_input'] == 1 and r['source_output'] == 0
    assert r['inputs_after']['connections'][0]['resolved_source'] is None
    assert source.node('tap').inputConnections()[0].subnetIndirectInput() == slot
    # A multi-output external node supplies port 1; the local wire still uses
    # output 0 of the explicitly selected connector and keeps tracking rewires.
    run("g=hou.node('/obj/public_fixture')\n"
        "up=tab_create(g,'subnet',name='up')\n"
        "b=tab_create(up,'box',name='wide',parms={'sizex':3})\n"
        "o=tab_create(up,'output',name='o1',inputs=[b],parms={'outputidx':1})\n"
        "connect(up, g.node('source'), index=1, output=1)")
    r = run("__result__=connect(hou.node('/obj/public_fixture/source').indirectInputs()[1],"
            "'/obj/public_fixture/source/out')")['result']
    wire = r['inputs_after']['connections'][0]
    assert (wire['subnet_input'], wire['source_output'], wire['source_item']) == (1, 0, slot.path())
    assert (wire['resolved_source'], wire['resolved_output']) == ('/obj/public_fixture/up', 1)
    assert abs(source.node('tap').geometry().boundingBox().sizevec()[0] - 3) < 1e-6
    external = '/obj/public_fixture/up'
    hou.node(external).setPosition(hou.Vector2(10000, -10000))
    run("s=hou.node('/obj/public_fixture/source')\n"
        "second=tab_create(s,'null',name='second_tap',inputs=[s.indirectInputs()[1]])\n"
        "replacement=tab_create(s.parent(),'box',name='replacement',parms={'sizex':5})\n"
        "connect(replacement,s,index=1)")
    assert abs(source.node('second_tap').position().x() - slot.position().x()) < 100
    assert abs(source.node('tap').geometry().boundingBox().sizevec()[0] - 5) < 1e-6
    for bad in (f"connect({slot.path()!r}, {external!r})",
                f"connect({slot.path()!r}, '/obj/public_fixture/source/out', output=1)",
                f"tab_create({external!r}, 'null', name='wrong_network', inputs=[{slot.path()!r}])"):
        run(bad, ok=False)
    assert not hou.node(external+'/wrong_network')
    foreign = bridge.run_code(f"connect({slot.path()!r}, '/obj/public_fixture/source/out')",
                              owner_session='other-author', owner_call='foreign-wire')
    assert not foreign['ok'] and source.node('out').inputConnections()[0].subnetIndirectInput() == slot
    run("disconnect_input('/obj/public_fixture/source',1)")
    r = run("__result__=connect('/obj/public_fixture/source/shape','/obj/public_fixture/source/out')")['result']
    assert r['inputs_before']['connections'][0]['source'] is None
    assert r['inputs_before']['connections'][0]['source_kind'] == 'subnet_indirect_input'
    assert r['inputs_after']['connections'][0]['source'].endswith('/shape')
    run("set_parms('/obj/public_fixture/source/shape',{'sizex':2})")
    r = run(f"__result__=hda_create({source.path()!r},'contract_test::solid::1.0',"
            f"hda_file={str(library)!r},min_inputs=0,max_inputs=0,max_outputs=1)")['result']
    assert r['max_outputs'] == 1
    source = hou.node(r['node'])
    layout = [{'type': 'float', 'name': 'width', 'default': 2., 'help': 'Width in scene units'},
              {'type': 'label', 'name': 'business_heading', 'label': 'Dimensions'}]
    run(f"hda_set_interface({source.path()!r},layout={layout!r})")
    source = hou.node('/obj/public_fixture/source')
    for name in ('label1', 'label2', 'label3', 'label4'):
        assert source.parmTemplateGroup().find(name).isHidden(), name
    assert not source.parmTemplateGroup().find('business_heading').isHidden()
    # Known native definition save, not an assertion that a missing authoring
    # step is a serialization bug. Direct HOM is restricted to this test fixture.
    source.node('shape').parm('sizex').setExpression('ch("../width")', hou.exprLanguage.Hscript)
    plan = run(f"__result__=hda_edit({source.path()!r},'save',dry_run=True)")['result']
    run(f"hda_edit({source.path()!r},'save',expected_plan={plan['plan_sha256']!r})")
    source.matchCurrentDefinition()
    run("a=tab_create('/obj/public_fixture','contract_test::solid::1.0',name='a')\n"
        "b=tab_create('/obj/public_fixture','contract_test::solid::1.0',name='b')\n"
        "consumer=tab_create('/obj/public_fixture','null',name='consumer',inputs=[a])\n"
        "set_parms(a,{'width':5})\ncook_node(consumer)")
    a = hou.node('/obj/public_fixture/a')
    b = hou.node('/obj/public_fixture/b')
    assert a.node('shape').parm('sizex').expression() == 'ch("../width")'
    assert abs(hou.node('/obj/public_fixture/consumer').geometry().boundingBox().sizevec()[0] - 5) < 1e-6
    assert b.evalParm('width') == 2
    assert abs(b.geometry().boundingBox().sizevec()[0] - 2) < 1e-6
    assert a.isLockedHDA() and a.matchesCurrentDefinition()
    # Preserve the exact file and instance state when a conflicting spare
    # interface would otherwise be merged into the new definition after write.
    overlay = a.parmTemplateGroup()
    overlay.append(hou.FloatParmTemplate('overlay_value', 'Overlay', 1, default_value=(7.,)))
    a.setParmTemplateGroup(overlay)
    before = library.read_bytes()
    r = run(f"hda_set_interface({a.path()!r},layout=[{{'type':'float','name':'overlay_value','default':1}}])", ok=False)
    assert 'spare interface conflicts' in r['error']
    assert library.read_bytes() == before
    assert a.evalParm('overlay_value') == 7
    # Port contract validation is before library creation, not after mutation.
    before = library.read_bytes()
    r = run(f"hda_create({a.path()!r},'unused::invalid::1.0',hda_file={str(library)!r},max_outputs=0)", ok=False)
    assert 'max_outputs' in r['error'] and library.read_bytes() == before
    # Multi-output declaration is verified through two real downstream ports,
    # not by the definition count or the internal display flag alone.
    multi_library = Path(temp) / 'multi.hda'
    run("s=tab_create('/obj/public_fixture','subnet',name='multi_source')\n"
        "first=tab_create(s,'box',name='first')\n"
        "second=tab_create(s,'box',name='second')\n"
        "set_parms(second,{'sizex':3})\n"
        "o0=tab_create(s,'output',name='first_output',inputs=[first])\n"
        "o1=tab_create(s,'output',name='second_output',inputs=[second])\n"
        "set_parms(o1,{'outputidx':1})")
    run(f"hda_create('/obj/public_fixture/multi_source','contract_test::multi::1.0',"
        f"hda_file={str(multi_library)!r},max_outputs=2)")
    run("m=tab_create('/obj/public_fixture','contract_test::multi::1.0',name='multi')\n"
        "c0=tab_create('/obj/public_fixture','null',name='consumer_zero')\n"
        "c1=tab_create('/obj/public_fixture','null',name='consumer_one')\n"
        "connect(m,c0,output=0)\nconnect(m,c1,output=1)\ncook_node(c0)\ncook_node(c1)")
    for name, width in [('consumer_zero',1),('consumer_one',3)]:
        assert abs(hou.node('/obj/public_fixture/'+name).geometry().boundingBox().sizevec()[0]-width)<1e-6
print('PASS HDA public output / indirect connector / hidden management labels / expression roundtrip / instance isolation / preflight')
