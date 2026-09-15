"""Isolated ordinary subnet exchange; no user scene or HDA definition writes."""
from pathlib import Path
import sys
import tempfile
import hashlib
import json
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h
import dsh_component_contracts as components


def run(code, owner='source', ok=True):
    result = b.run_code(code, owner_session=owner)
    assert result['ok'] is ok, result.get('error', result)
    return result.get('result')


if len(sys.argv) > 1 and sys.argv[1] != '--parameters':
    mode, directory = sys.argv[1:3]
    folder = Path(directory)
    hou.hipFile.setName(str(folder / ('assembly.hip' if mode != 'export' else 'source.hip')))
    if mode == 'export':
        for index in range(2):
            run(f"g=tab_create('/obj','geo','source{index}')\ns=tab_create(g,'subnet','module')\n"
                "box=tab_create(s,'box','shape')\nsop_set_output(box,output_index=0)")
            source = hou.node(f'/obj/source{index}/module')
            # Test fixture authors a public spare and a relative expression.
            with h._execution_owner('source', 'fixture'):
                ptg = source.parmTemplateGroup()
                ptg.append(hou.FloatParmTemplate('width', 'Width', 1, default_value=(1,)))
                ptg.append(hou.FloatParmTemplate('thickness', 'Thickness', 1, default_value=(0.08,)))
                source.setParmTemplateGroup(ptg)
                source.node('shape').parm('sizex').setExpression('ch("../width")')
            contract = {'module_id': f'part{index}', 'revision': 1, 'units': 'm', 'outputs': [0]}
            result = run(f'__result__=component_export({source.path()!r},{str(folder/f"part{index}.dshcomponent")!r},{contract!r})')
            (folder / f'part{index}.json').write_text(json.dumps(result), encoding='utf-8')
    elif mode == 'import':
        run("tab_create('/obj','geo','assembly')", owner='assembly')
        for index in range(2):
            source = json.loads((folder / f'part{index}.json').read_text(encoding='utf-8'))
            run(f'component_import("/obj/assembly",{source["file"]!r},{source["sha256"]!r},"part{index}",trusted=True)', owner='assembly')
            imported = hou.node(f'/obj/assembly/part{index}')
            assert (imported.parm('width').eval(), imported.parm('thickness').eval()) == (1.0, 0.08)
            if index == 0:
                # The observed live drift happened after a faithful import,
                # across requests; do not misdiagnose it as archive corruption.
                run("create_spare_parms('/obj/assembly',spec=[{'type':'folder','name':'master',"
                    "'label':'Master','parms':[{'type':'float','name':'width',"
                    "'default':1.0}]}])", owner='assembly')
                assert (imported.parm('width').eval(), imported.parm('thickness').eval()) == (1.0, 0.08)
            run(f'set_parms("/obj/assembly/part{index}",{{"width":{index+2}}})', owner='assembly')
            assert abs(hou.node(f'/obj/assembly/part{index}').geometry().boundingBox().sizevec()[0] - (index+2)) < 1e-6
        run('scene_save()', owner='assembly')
    elif mode == 'reopen':
        # Driver-only fresh process load, never through Bridge exec.
        hou.hipFile.load(str(folder / 'assembly.hip'), suppress_save_prompt=True)
        for index in range(2):
            root = hou.node(f'/obj/assembly/part{index}')
            assert abs(root.geometry().boundingBox().sizevec()[0] - (index+2)) < 1e-6
            with h._execution_owner('assembly', 'reopen'):
                assert h.node_provenance(root)['status'] == 'foreign'
    else:
        raise ValueError(mode)
    print('PASS component independent process ' + mode + ' ' + hou.applicationVersionString())
    raise SystemExit(0)


with tempfile.TemporaryDirectory(prefix='dsh-component-test-') as folder:
    hou.hipFile.setName(str(Path(folder) / 'source.hip'))
    if '--parameters' in sys.argv:
        run("g=tab_create('/obj','geo','parameter_exchange')")
        for kind in ('polybevel', 'polyextrude', 'attribwrangle'):
            run(f"s=tab_create('/obj/parameter_exchange','subnet',{kind!r})\n"
                "b=tab_create(s,'box','shape')\n"
                f"n=tab_create(s,{kind!r},'operation',inputs=[b])\nsop_set_output(n,output_index=0)")
            source = hou.node('/obj/parameter_exchange/' + kind)
            if kind == 'attribwrangle':
                run(f"set_parms({source.node('operation').path()!r},{{'snippet':'@P.x *= 2;'}})")
            artifact = str(Path(folder) / (kind + '.dshcomponent'))
            contract = {'module_id': kind, 'revision': 1, 'units': 'm', 'outputs': [0]}
            result = run(f'__result__=component_export({source.path()!r},{artifact!r},{contract!r})')
            imported = run(f'__result__=component_import("/obj/parameter_exchange",{artifact!r},{result["sha256"]!r},{kind+"_copy"!r},trusted=True)')
            target = hou.node(imported['node'])
            package = json.loads(Path(artifact).read_bytes())
            assert package['schema'] == 2
            assert all(not row['parms'] and not row['spare_templates'] for row in package['snapshot'] if row['path'] != '.')
            assert len(target.geometry().prims()) == len(source.geometry().prims())
            assert tuple(target.geometry().boundingBox().sizevec()) == tuple(source.geometry().boundingBox().sizevec())
            assert [tuple(p.position()) for p in target.geometry().points()] == [tuple(p.position()) for p in source.geometry().points()]
            assert [[v.point().number() for v in p.vertices()] for p in target.geometry().prims()] == [[v.point().number() for v in p.vertices()] for p in source.geometry().prims()]
            for original in (source, *source.allSubChildren()):
                clone = target if original == source else target.node(source.relativePathTo(original))
                for parm in original.parms():
                    if parm.parmTemplate().type() == hou.parmTemplateType.Ramp:
                        left, right = parm.eval(), clone.parm(parm.name()).eval()
                        assert left.basis() == right.basis() and left.keys() == right.keys() and left.values() == right.values()
            run(f"tab_create('/obj/parameter_exchange','null',{kind+'consumer'!r},inputs=[{source.path()!r}])")
            run(f'component_replace({source.path()!r},{target.path()!r})')
            print('PASS native parameter exchange ' + kind)
        # Dependency checks are not removed with the internal value mirror.
        run("s=tab_create('/obj/parameter_exchange','subnet','external')\nb=tab_create(s,'box','shape')\nsop_set_output(b,output_index=0)\n"
            "outside=tab_create('/obj/parameter_exchange','box','outside')\nset_parms(b,{'sizex':'ch(\"../../outside/sizex\")'})")
        rejected = str(Path(folder) / 'external.dshcomponent')
        run(f'component_export("/obj/parameter_exchange/external",{rejected!r},{contract!r})', ok=False)
        assert not Path(rejected).exists()
        # The native archive preserves internal ramps without asking our value codec.
        original = components._parm_value
        def forbid_internal_ramp(parm):
            if parm.parmTemplate().type() == hou.parmTemplateType.Ramp:
                raise AssertionError('internal Ramp must remain native archive data')
            return original(parm)
        with patch.object(components, '_parm_value', side_effect=forbid_internal_ramp):
            run(f'component_export("/obj/parameter_exchange/polybevel",{str(Path(folder)/"native_only.dshcomponent")!r},{contract!r})')
        raise SystemExit(0)
    run("g=tab_create('/obj','geo','source')\ns=tab_create(g,'subnet','module')\n"
        "box=tab_create(s,'box','shape')\nsop_set_output(box,output_index=0)")
    file = str(Path(folder) / 'part.dshcomponent')
    contract = {'module_id': 'part', 'revision': 1, 'units': 'm', 'outputs': [0]}
    exported = run(f'__result__=component_export("/obj/source/module",{file!r},{contract!r})')
    # SideFX HDAs may materialize definition-owned implementation children on
    # first cook. They belong to the owned built-in instance and must not make
    # a self-authored component impossible to export.
    run("m=tab_create('/obj/source/module','matchsize','builtin_hda',inputs=['/obj/source/module/shape'])\n"
        "sop_set_output(m,output_index=2)\ncook_node(m)")
    lazy_file = str(Path(folder) / 'builtin_hda.dshcomponent')
    lazy_contract = {**contract, 'outputs': [0, 2]}
    run(f'__result__=component_export("/obj/source/module",{lazy_file!r},{lazy_contract!r})')
    query = b.run_code(f'component_export("/obj/source/module",{file!r},{contract!r})', owner_session='source', read_only=True)
    assert not query['ok']
    for method in ('saveItemsToFile', 'loadItemsFromFile', 'saveChildrenToFile', 'loadChildrenFromFile'):
        assert b._raw_hou_calls(f'hou.node("/obj").{method}("x")')
    run("tab_create('/obj','geo','assembly')", owner='assembly')
    args = f'"/obj/assembly",{file!r},{exported["sha256"]!r},"renamed"'
    run(f'component_import({args})', owner='assembly', ok=False)
    result = run(f'__result__=component_import({args},trusted=True)', owner='assembly')
    root = hou.node(result['node'])
    assert root.type().name() == 'subnet' and root.geometry().prims()
    uppercase = run(
        f'__result__=component_import("/obj/assembly",{file!r},{exported["sha256"].upper()!r},'
        '"uppercase_digest",trusted=True)',
        owner='assembly',
    )
    assert uppercase['sha256'] == exported['sha256']
    run('delete_node("/obj/assembly/uppercase_digest")', owner='assembly')
    with h._execution_owner('assembly', 'check'):
        assert all(h.node_provenance(n)['status'] == 'owned_current_session' for n in (root, *root.allSubChildren()))
    run(f'set_parms({root.node("shape").path()!r},{{"sizex":2}})', owner='assembly')
    assert abs(root.geometry().boundingBox().sizevec()[0] - 2) < 1e-6
    run(f'set_parms({root.node("shape").path()!r},{{"sizex":3}})', owner='source', ok=False)
    run('consumer=tab_create("/obj/assembly","null","consumer",inputs=["/obj/assembly/renamed"])', owner='assembly')
    replacement = run(f'__result__=component_import("/obj/assembly",{file!r},{exported["sha256"]!r},"replacement",trusted=True)', owner='assembly')
    preview = run('__result__=component_replace("/obj/assembly/renamed","/obj/assembly/replacement")', owner='assembly')
    run('set_parms("/obj/assembly/renamed/shape",{"sizey":2})', owner='assembly')
    run(f'component_replace("/obj/assembly/renamed","/obj/assembly/replacement",dry_run=False,expected_plan={preview["plan"]!r})', owner='assembly', ok=False)
    assert hou.node('/obj/assembly/consumer').input(0) == root
    preview = run('__result__=component_replace("/obj/assembly/renamed","/obj/assembly/replacement")', owner='assembly')
    run(f'component_replace("/obj/assembly/renamed","/obj/assembly/replacement",dry_run=False,expected_plan={preview["plan"]!r})', owner='assembly')
    assert hou.node('/obj/assembly/consumer').input(0).path() == replacement['node']
    assert hou.node('/obj/assembly/renamed') == root
    # A failed downstream cook restores the original wire without removing either module.
    run('connect("/obj/assembly/renamed","/obj/assembly/consumer")', owner='assembly')
    preview = run('__result__=component_replace("/obj/assembly/renamed","/obj/assembly/replacement")', owner='assembly')
    with patch.object(h, 'cook_node', side_effect=RuntimeError('injected consumer cook failure')):
        run(f'component_replace("/obj/assembly/renamed","/obj/assembly/replacement",dry_run=False,expected_plan={preview["plan"]!r})', owner='assembly', ok=False)
    assert hou.node('/obj/assembly/consumer').input(0) == root
    run('sop_set_output("/obj/source/module/shape",output_index=1)')
    multi_file = str(Path(folder) / 'multi.dshcomponent')
    multi_contract = {**contract, 'outputs': [0, 1]}
    multi = run(f'__result__=component_export("/obj/source/module",{multi_file!r},{multi_contract!r})')
    run(f'component_import("/obj/assembly",{multi_file!r},{multi["sha256"]!r},"multi",trusted=True)', owner='assembly')
    run('extra=tab_create("/obj/assembly","null","extra");connect("/obj/assembly/multi",extra,output=1);cook_node(extra)', owner='assembly')
    assert len(hou.node('/obj/assembly/extra').geometry().prims()) == 6
    before = tuple(hou.node('/obj/assembly').children())
    run(f'component_import("/obj/assembly",{file!r},{"0"*64!r},"bad",trusted=True)', owner='assembly', ok=False)
    package = json.loads(Path(file).read_bytes())
    package['snapshot'][0]['type'] = 'wrong'
    bad = Path(folder) / 'bad.dshcomponent'
    bad.write_text(json.dumps(package), encoding='utf-8')
    digest = hashlib.sha256(bad.read_bytes()).hexdigest()
    run(f'component_import("/obj/assembly",{str(bad)!r},{digest!r},"bad",trusted=True)', owner='assembly', ok=False)
    assert tuple(hou.node('/obj/assembly').children()) == before
    package['houdini'] = '0.0.0'
    bad.write_text(json.dumps(package), encoding='utf-8')
    digest = hashlib.sha256(bad.read_bytes()).hexdigest()
    run(f'component_import("/obj/assembly",{str(bad)!r},{digest!r},"bad",trusted=True)', owner='assembly', ok=False)
    assert tuple(hou.node('/obj/assembly').children()) == before
    run(f'component_export("/obj/source/module",{str(Path(folder)/"foreign.dshcomponent")!r},{contract!r})', owner='assembly', ok=False)
    run(f'component_import({args},trusted=True)', owner='source', ok=False)
    run(f'component_import({args},trusted=True)', owner='assembly', ok=False)
    run(f'component_export("/obj/source/module",{file!r},{contract!r})', ok=False)
    assert not any(n.name().startswith('__component') for n in hou.node('/obj/assembly').children())
print('PASS ordinary subnet trusted exchange ' + hou.applicationVersionString())
