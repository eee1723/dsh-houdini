"""Isolated ordinary subnet exchange; no user scene or HDA definition writes."""
from pathlib import Path
import sys
import tempfile
import hashlib
import json
import re
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h
import dsh_component_contracts as components

# Verbatim historical implementations, extracted with git cat-file (exact
# blob bytes) and pinned by sha256. They are falsification controls, not
# approximations: the R4 legacy restore as of 0effe03 rebuilds every key
# from its value alone, and the pre-iteration-6 capture raises NameError
# on the first-key-no-expression branch.
RESTORE_0EFFE03_SHA256 = '6b69895d08effb94bcbdcafed2ef6f38da60a29ca9ea02682aa7dee93c6ea5c6'
RESTORE_0EFFE03 = "def _restore_parm(parm, captured):\n    kind, payload = captured\n    if kind == 'keys':\n        parm.deleteAllKeyframes()\n        for clone in payload:\n            parm.setKeyframe(clone)\n        return\n    parm.deleteAllKeyframes()\n    parm.set(payload)\n"
CAPTURE_49BF56E_SHA256 = '5129fa165366c179a340fd4e589d2acc9ad034f4b186f215774bbf73889fa9fd'
CAPTURE_49BF56E = 'def _capture_parm(parm):\n    """Restorable snapshot of one live channel; expression-driven keys cannot be restored.\n\n    Segment functions (bezier()/linear()/...) are plain animation data and migrate;\n    any other keyframe expression is refused rather than rewritten. The snapshot\n    carries the Keyframe objects returned by keyframes() VERBATIM - frame, value,\n    slopes, acceleration and segment state all survive - instead of rebuilding a\n    partial copy field by field.\n    """\n    keys = parm.keyframes()\n    if keys:\n        for key in keys:\n            try:\n                if key.isExpressionSet():\n                    segment = key.expression()\n            except hou.OperationFailed:\n                continue\n            else:\n                if segment is not None and not re.fullmatch(r\'[A-Za-z_][A-Za-z0-9_]*\\(\\)\', segment.strip()):\n                    raise ValueError(\'keyframes driven by expressions are not migrated: \' + parm.path())\n        return (\'keys\', keys)\n    if parm.parmTemplate().type() == hou.parmTemplateType.String:\n        return (\'string\', parm.unexpandedString())\n    return (\'value\', parm.eval())\n'
CAPTURE_0EFFE03_SHA256 = '02135861a3253b59df5a29086c717929991b69fc838118a286bb77837cbf6e9f'
CAPTURE_0EFFE03 = 'def _capture_parm(parm):\n    """Restorable snapshot of one live channel; expression-driven keys cannot be restored.\n\n    Segment functions (bezier()/linear()/…) are plain animation data and migrate;\n    any other keyframe expression is refused rather than rewritten.\n    """\n    keys = parm.keyframes()\n    if keys:\n        clones = []\n        for key in keys:\n            segment = None\n            try:\n                if key.isExpressionSet():\n                    segment = key.expression()\n            except hou.OperationFailed:\n                segment = None\n            if segment is not None:\n                if not re.fullmatch(r\'[A-Za-z_][A-Za-z0-9_]*\\(\\)\', segment.strip()):\n                    raise ValueError(\'keyframes driven by expressions are not migrated: \' + parm.path())\n                segment = (segment, key.expressionLanguage())\n            clone = hou.Keyframe()\n            clone.setFrame(key.frame())\n            clone.setValue(key.value())\n            clone.setSlope(key.slope())\n            clone.setInSlope(key.inSlope())\n            clone.setAccel(key.accel())\n            if segment is not None:\n                clone.setExpression(segment[0], segment[1])\n            clones.append(clone)\n        return (\'keys\', clones)\n    if parm.parmTemplate().type() == hou.parmTemplateType.String:\n        return (\'string\', parm.unexpandedString())\n    return (\'value\', parm.eval())\n'


def run(code, owner='source', ok=True):
    result = b.run_code(code, owner_session=owner)
    assert result['ok'] is ok, result.get('error', result)
    return result.get('result')


def fail_with(code, owner='assembly'):
    result = b.run_code(code, owner_session=owner)
    assert result['ok'] is False, result
    return str(result.get('error'))


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
    # A: expected_contract pins the candidate to the contract recorded at import.
    accepted = run(f'__result__=component_import("/obj/assembly",{file!r},{exported["sha256"]!r},"rev1",trusted=True)', owner='assembly')
    stale = fail_with('component_replace("/obj/assembly/renamed","/obj/assembly/rev1",'
                      'expected_contract={"module_id":"part","revision":2})')
    assert 'stale or unexpected' in stale and 'revision 2' in stale and 'revision 1' in stale, stale
    for bad_contract in ({'module_id': 'part'}, {'module_id': 'part', 'revision': 0},
                         {'module_id': 'part', 'revision': '1'}, {'module_id': 'part', 'revision': 1, 'units': 'm'}):
        assert 'expected_contract' in fail_with(
            f'component_replace("/obj/assembly/renamed","/obj/assembly/rev1",expected_contract={bad_contract!r})'), bad_contract
    run('s=tab_create("/obj/assembly","subnet","handmade")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)', owner='assembly')
    unknown = fail_with('component_replace("/obj/assembly/renamed","/obj/assembly/handmade",'
                        'expected_contract={"module_id":"part","revision":1})')
    assert 'provenance is unknown' in unknown, unknown
    # C: a stale commit names the drifted side instead of a generic mismatch.
    preview = run('__result__=component_replace("/obj/assembly/renamed","/obj/assembly/rev1")', owner='assembly')
    assert set(preview['plan']['parts']) == {'old', 'candidate', 'wires', 'migration'}
    run('set_parms("/obj/assembly/renamed/shape",{"sizez":4})', owner='assembly')
    drift = fail_with(f'component_replace("/obj/assembly/renamed","/obj/assembly/rev1",dry_run=False,expected_plan={preview["plan"]!r})')
    assert 'local fork' in drift and 'no wires changed' in drift, drift
    assert hou.node('/obj/assembly/consumer').input(0) == root
    preview = run('__result__=component_replace("/obj/assembly/renamed","/obj/assembly/rev1")', owner='assembly')
    run('set_parms("/obj/assembly/rev1/shape",{"sizey":5})', owner='assembly')
    drift = fail_with(f'component_replace("/obj/assembly/renamed","/obj/assembly/rev1",dry_run=False,expected_plan={preview["plan"]!r})')
    assert 'candidate modified' in drift, drift
    preview = run('__result__=component_replace("/obj/assembly/renamed","/obj/assembly/rev1")', owner='assembly')
    run('late=tab_create("/obj/assembly","null","late",inputs=["/obj/assembly/renamed"])', owner='assembly')
    drift = fail_with(f'component_replace("/obj/assembly/renamed","/obj/assembly/rev1",dry_run=False,expected_plan={preview["plan"]!r})')
    assert 'consumers changed' in drift, drift
    # A+C positive: matching contract and fresh plan commit together, migrating both consumers.
    preview = run('__result__=component_replace("/obj/assembly/renamed","/obj/assembly/rev1")', owner='assembly')
    final = run(f'__result__=component_replace("/obj/assembly/renamed","/obj/assembly/rev1",dry_run=False,'
                f'expected_plan={preview["plan"]!r},expected_contract={{"module_id":"part","revision":1}})', owner='assembly')
    assert final['contract']['module_id'] == 'part' and final['contract']['revision'] == 1
    assert hou.node('/obj/assembly/consumer').input(0).path() == accepted['node']
    assert hou.node('/obj/assembly/late').input(0).path() == accepted['node']
    # B: explicit migration plan — input wires, public values/keys, parameter consumers.
    run('s=tab_create("/obj/assembly","subnet","oldmod")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)', owner='assembly')
    run('s=tab_create("/obj/assembly","subnet","newmod")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)', owner='assembly')
    run('feeder=tab_create("/obj/assembly","box","feeder")\nconnect("/obj/assembly/feeder","/obj/assembly/oldmod")', owner='assembly')
    run('sink=tab_create("/obj/assembly","null","sink",inputs=["/obj/assembly/oldmod"])', owner='assembly')
    run('create_spare_parms("/obj/assembly/oldmod",layout=[{"type":"float","name":"width","default":1}])', owner='assembly')
    uncovered = fail_with('component_replace("/obj/assembly/oldmod","/obj/assembly/newmod")')
    assert 'not covered by the migration plan' in uncovered, uncovered
    run('ctrl=tab_create("/obj/assembly","null","ctrl")', owner='assembly')
    run('create_spare_parms("/obj/assembly/ctrl",layout=[{"type":"float","name":"drive","default":0}])\n'
        'set_parms("/obj/assembly/ctrl",{"drive":"ch(\\"/obj/assembly/oldmod/width\\")"})', owner='assembly')
    hidden = fail_with('component_replace("/obj/assembly/oldmod","/obj/assembly/newmod",migration={"inputs":{"0":0}})')
    assert 'outside the declared migration plan' in hidden, hidden
    missing = fail_with('component_replace("/obj/assembly/oldmod","/obj/assembly/newmod",migration={"inputs":{"0":0},"public_parms":["width"]})')
    assert 'candidate lacks the declared public parameter' in missing, missing
    run('create_spare_parms("/obj/assembly/newmod",layout=[{"type":"float","name":"width","default":9}])', owner='assembly')
    run('blocker=tab_create("/obj/assembly","box","blocker")\nconnect("/obj/assembly/blocker","/obj/assembly/newmod")', owner='assembly')
    occupied = fail_with('component_replace("/obj/assembly/oldmod","/obj/assembly/newmod",migration={"inputs":{"0":0},"public_parms":["width"]})')
    assert 'already connected' in occupied, occupied
    run('disconnect_input("/obj/assembly/newmod",index=0)', owner='assembly')
    preview = run('__result__=component_replace("/obj/assembly/oldmod","/obj/assembly/newmod",migration={"inputs":{"0":0},"public_parms":["width"]})', owner='assembly')
    assert preview['migration']['inputs'][0]['slot'] == 0 and len(preview['migration']['parameter_consumers']) == 1
    drift = fail_with('component_replace("/obj/assembly/oldmod","/obj/assembly/newmod",dry_run=False,'
                      f'expected_plan={preview["plan"]!r},migration={{"inputs":{{0:1}},"public_parms":["width"]}})')
    assert 'migration inputs/parameters/consumers changed after preview' in drift, drift
    run('set_parms("/obj/assembly/oldmod",{"width":3})', owner='assembly')
    preview = run('__result__=component_replace("/obj/assembly/oldmod","/obj/assembly/newmod",migration={"inputs":{"0":0},"public_parms":["width"]})', owner='assembly')
    with patch.object(h, 'cook_node', side_effect=RuntimeError('injected consumer cook failure')):
        fail_with(f'component_replace("/obj/assembly/oldmod","/obj/assembly/newmod",dry_run=False,expected_plan={preview["plan"]!r},'
                  'migration={"inputs":{"0":0},"public_parms":["width"]})')
    assert hou.node('/obj/assembly/oldmod').input(0).path() == '/obj/assembly/feeder'
    assert hou.node('/obj/assembly/newmod').input(0) is None
    assert 'oldmod' in hou.parm('/obj/assembly/ctrl/drive').expression()
    assert hou.node('/obj/assembly/newmod').parm('width').eval() == 9
    assert hou.node('/obj/assembly/sink').input(0).path() == '/obj/assembly/oldmod'
    run('set_keyframes("/obj/assembly/oldmod",{"width":[{"frame":1,"value":2},{"frame":12,"value":5}]})', owner='assembly')
    preview = run('__result__=component_replace("/obj/assembly/oldmod","/obj/assembly/newmod",migration={"inputs":{"0":0},"public_parms":["width"]})', owner='assembly')
    final = run(f'__result__=component_replace("/obj/assembly/oldmod","/obj/assembly/newmod",dry_run=False,expected_plan={preview["plan"]!r},'
                'migration={"inputs":{"0":0},"public_parms":["width"]})', owner='assembly')
    assert final['migrated'] == {'inputs': 1, 'public_parms': ['width'], 'parameter_consumers': 1}
    keys = hou.node('/obj/assembly/newmod').parm('width').keyframes()
    assert [k.frame() for k in keys] == [1, 12] and [k.value() for k in keys] == [2, 5]
    assert hou.node('/obj/assembly/newmod').input(0).path() == '/obj/assembly/feeder'
    assert hou.node('/obj/assembly/oldmod').input(0) is None
    assert 'newmod' in hou.parm('/obj/assembly/ctrl/drive').expression()
    assert hou.parm('/obj/assembly/ctrl/drive') in hou.node('/obj/assembly/newmod').parm('width').parmsReferencingThis()
    assert hou.parm('/obj/assembly/ctrl/drive') not in hou.node('/obj/assembly/oldmod').parm('width').parmsReferencingThis()
    assert hou.node('/obj/assembly/oldmod').parm('width').keyframes(), 'the old module keeps its own channels'
    # Counterexample: a failure raised INSIDE the migration commit, after the
    # real write and before the commit function returns, must still be fully
    # rolled back — the rollback ledger entry is registered BEFORE the
    # mutation, not after it succeeds.
    run('s=tab_create("/obj/assembly","subnet","oldmod2")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)', owner='assembly')
    run('s=tab_create("/obj/assembly","subnet","newmod2")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)', owner='assembly')
    run('feeder2=tab_create("/obj/assembly","box","feeder2")\nconnect("/obj/assembly/feeder2","/obj/assembly/oldmod2")', owner='assembly')
    run('sink2=tab_create("/obj/assembly","null","sink2",inputs=["/obj/assembly/oldmod2"])', owner='assembly')
    run('create_spare_parms("/obj/assembly/oldmod2",layout=[{"type":"float","name":"width","default":1}])', owner='assembly')
    run('create_spare_parms("/obj/assembly/newmod2",layout=[{"type":"float","name":"width","default":9}])', owner='assembly')
    run('ctrl2=tab_create("/obj/assembly","null","ctrl2")', owner='assembly')
    run('create_spare_parms("/obj/assembly/ctrl2",layout=[{"type":"float","name":"drive","default":0}])\n'
        'set_parms("/obj/assembly/ctrl2",{"drive":"ch(\\"/obj/assembly/oldmod2/width\\")"})', owner='assembly')
    run('set_keyframes("/obj/assembly/oldmod2",{"width":[{"frame":2,"value":3},{"frame":10,"value":7}]})', owner='assembly')
    preview = run('__result__=component_replace("/obj/assembly/oldmod2","/obj/assembly/newmod2",migration={"inputs":{"0":0},"public_parms":["width"]})', owner='assembly')
    # R5: the fault fires INSIDE the migration commit after the real write
    # (keys already moved onto the candidate, then provably corrupted to 123.0)
    # and before the commit returns. Verified at BOTH layers, separately:
    # direct helper (no bridge undo - the ledger alone must heal), then bridge.
    real_restore = components._restore_parm
    corruption = []
    injections = {'n': 0}
    def corrupt_then_raise(parm, captured):
        injections['n'] += 1
        if injections['n'] != 1:
            return real_restore(parm, captured)  # rollback-phase restores stay clean
        real_restore(parm, captured)
        parm.set(123.0)
        corruption.append(parm.eval())
        raise RuntimeError('injected failure after the real write, before the commit returns')
    with h._execution_owner('assembly', 'direct-partial-write'):
        with patch.object(components, '_restore_parm', corrupt_then_raise):
            try:
                components.component_replace('/obj/assembly/oldmod2', '/obj/assembly/newmod2', dry_run=False,
                                             expected_plan=preview['plan'],
                                             migration={'inputs': {'0': 0}, 'public_parms': ['width']})
            except RuntimeError as error:
                assert 'injected failure after the real write' in str(error), error
            else:
                raise AssertionError('the injected post-write failure must fail the commit')
    assert corruption == [123.0], 'the real write must have happened before the injected failure'
    assert hou.node('/obj/assembly/newmod2').parm('width').eval() == 9, \
        'the internal ledger must recover the really-corrupted value on a direct call'
    assert not hou.node('/obj/assembly/newmod2').parm('width').keyframes()
    # Bridge layer, independently: the same in-commit failure through run_code heals too.
    injections['n'] = 0
    corruption.clear()
    with patch.object(components, '_restore_parm', corrupt_then_raise):
        failed = fail_with(f'component_replace("/obj/assembly/oldmod2","/obj/assembly/newmod2",dry_run=False,'
                           f'expected_plan={preview["plan"]!r},migration={{"inputs":{{"0":0}},"public_parms":["width"]}})')
    assert 'injected failure after the real write' in failed, failed
    assert corruption == [123.0], corruption
    assert hou.node('/obj/assembly/oldmod2').input(0).path() == '/obj/assembly/feeder2'
    assert hou.node('/obj/assembly/newmod2').input(0) is None
    assert 'oldmod2' in hou.parm('/obj/assembly/ctrl2/drive').expression()
    assert [k.frame() for k in hou.node('/obj/assembly/oldmod2').parm('width').keyframes()] == [2, 10]
    assert not hou.node('/obj/assembly/newmod2').parm('width').keyframes()
    assert hou.node('/obj/assembly/newmod2').parm('width').eval() == 9
    assert hou.node('/obj/assembly/sink2').input(0).path() == '/obj/assembly/oldmod2'
    # R5: same-exec consistency - a successful replace followed by a later failure
    # in the SAME exec restores the component import records together with the scene.
    run("g=tab_create('/obj','geo','swapsource')\ns=tab_create(g,'subnet','module')\nb=tab_create(s,'box','shape')\nsop_set_output(b,output_index=0)")
    swap_contract = {'module_id': 'swapmod', 'revision': 1, 'units': 'm', 'outputs': [0]}
    swap_file = str(Path(folder) / 'swapmod.dshcomponent')
    swap_export = run(f'__result__=component_export("/obj/swapsource/module",{swap_file!r},{swap_contract!r})')
    run(f'__result__=component_import("/obj/assembly",{swap_export["file"]!r},{swap_export["sha256"]!r},"swapold",trusted=True)', owner='assembly')
    swap_new = run(f'__result__=component_import("/obj/assembly",{swap_export["file"]!r},{swap_export["sha256"]!r},"swapnew",trusted=True)', owner='assembly')
    run('sink5=tab_create("/obj/assembly","null","sink5",inputs=["/obj/assembly/swapold"])', owner='assembly')
    swap_preview = run('__result__=component_replace("/obj/assembly/swapold","/obj/assembly/swapnew",'
                       'expected_contract={"module_id":"swapmod","revision":1},migration={"inputs":{},"public_parms":[]})', owner='assembly')
    swap_failed = fail_with(
        f'__result__=component_replace("/obj/assembly/swapold","/obj/assembly/swapnew",dry_run=False,'
        f'expected_contract={{"module_id":"swapmod","revision":1}},expected_plan={swap_preview["plan"]!r},'
        f'migration={{"inputs":{{}},"public_parms":[]}})\nraise RuntimeError("post-replace failure")', owner='assembly')
    assert 'post-replace failure' in swap_failed, swap_failed
    assert int(swap_new['identity']) in components._IMPORT_RECORDS, \
        'the rollback must restore the candidate import record with the scene'
    assert hou.node('/obj/assembly/sink5').input(0).path() == '/obj/assembly/swapold'
    swap_redone = run(f'__result__=component_replace("/obj/assembly/swapold","/obj/assembly/swapnew",dry_run=False,'
                      f'expected_contract={{"module_id":"swapmod","revision":1}},expected_plan={swap_preview["plan"]!r},'
                      f'migration={{"inputs":{{}},"public_parms":[]}})', owner='assembly')
    assert swap_redone['ok'] is True, swap_redone
    assert hou.node('/obj/assembly/sink2').input(0).path() == '/obj/assembly/oldmod2'
    # Counterexample: a failing internal restoration is escalated, not silently
    # claimed complete. At bridge level the caught-failure undo additionally
    # restores the whole batch on top of the ledger restore.
    preview = run('__result__=component_replace("/obj/assembly/oldmod2","/obj/assembly/newmod2",migration={"inputs":{"0":0},"public_parms":["width"]})', owner='assembly')
    flaky = {'n': 0}
    def restore_fails_on_rollback(parm, captured):
        flaky['n'] += 1
        if flaky['n'] == 2:
            raise RuntimeError('injected restore failure')
        return real_restore(parm, captured)
    with patch.object(components, '_restore_parm', restore_fails_on_rollback), \
            patch.object(h, 'cook_node', side_effect=RuntimeError('injected consumer cook failure')):
        failed = fail_with(f'component_replace("/obj/assembly/oldmod2","/obj/assembly/newmod2",dry_run=False,'
                           f'expected_plan={preview["plan"]!r},migration={{"inputs":{{"0":0}},"public_parms":["width"]}})')
    assert 'component replacement restoration failed' in failed and 'injected restore failure' in failed, failed
    assert hou.node('/obj/assembly/sink2').input(0).path() == '/obj/assembly/oldmod2'
    assert hou.node('/obj/assembly/oldmod2').input(0).path() == '/obj/assembly/feeder2'
    assert 'oldmod2' in hou.parm('/obj/assembly/ctrl2/drive').expression()
    assert [k.frame() for k in hou.node('/obj/assembly/oldmod2').parm('width').keyframes()] == [2, 10]
    assert not hou.node('/obj/assembly/newmod2').parm('width').keyframes()
    # Direct call (no bridge undo): the internal partial restore is visible —
    # every ledger entry except the failing one was restored in reverse order.
    with h._execution_owner('assembly', 'direct-replace'):
        direct_preview = components.component_replace('/obj/assembly/oldmod2', '/obj/assembly/newmod2',
                                                      dry_run=True, migration={'inputs': {'0': 0}, 'public_parms': ['width']})
        flaky2 = {'n': 0}
        def restore_fails_direct(parm, captured):
            flaky2['n'] += 1
            if flaky2['n'] == 2:
                raise RuntimeError('injected restore failure')
            return real_restore(parm, captured)
        with patch.object(components, '_restore_parm', restore_fails_direct), \
                patch.object(h, 'cook_node', side_effect=RuntimeError('injected consumer cook failure')):
            try:
                components.component_replace('/obj/assembly/oldmod2', '/obj/assembly/newmod2', dry_run=False,
                                             expected_plan=direct_preview['plan'],
                                             migration={'inputs': {'0': 0}, 'public_parms': ['width']})
            except RuntimeError as error:
                assert 'component replacement restoration failed' in str(error), error
                assert 'injected restore failure' in str(error), error
                assert 'injected consumer cook failure' in str(error.__cause__), error
            else:
                raise AssertionError('a failed restoration must escalate as RuntimeError')
    assert [k.frame() for k in hou.node('/obj/assembly/newmod2').parm('width').keyframes()] == [2, 10], \
        'the failed ledger entry residual stays visible on a direct call'
    assert hou.node('/obj/assembly/sink2').input(0).path() == '/obj/assembly/oldmod2'
    assert hou.node('/obj/assembly/oldmod2').input(0).path() == '/obj/assembly/feeder2'
    assert 'oldmod2' in hou.parm('/obj/assembly/ctrl2/drive').expression()
    assert hou.node('/obj/assembly/oldmod2').parm('width').keyframes()
    # R3/R4: multi-channel public parameter migration - aggregation, deep-relative
    # preservation, write-ahead refusal, full keyframe state, type/arity/slot checks.
    run('s=tab_create("/obj/assembly","subnet","tupleold")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)', owner='assembly')
    run('s=tab_create("/obj/assembly","subnet","tuplenew")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)', owner='assembly')
    run('sink3=tab_create("/obj/assembly","null","sink3",inputs=["/obj/assembly/tupleold"])', owner='assembly')
    run('create_spare_parms("/obj/assembly/tupleold",layout=[{"type":"float","name":"tri","components":3,"default":[0,0,0]}])', owner='assembly')
    run('create_spare_parms("/obj/assembly/tuplenew",layout=[{"type":"float","name":"tri","components":3,"default":[5,5,5]}])', owner='assembly')
    run('set_keyframes("/obj/assembly/tupleold",{"trix":[{"frame":1,"value":11,"curve":"bezier"}],'
        '"triy":[{"frame":2,"value":22,"curve":"bezier"}],"triz":[{"frame":3,"value":33,"curve":"bezier"}]})', owner='assembly')
    # A key with explicit slope/acceleration: full curve state, not just frame+value.
    rich = hou.Keyframe()
    rich.setFrame(3)
    rich.setValue(33)
    rich.setSlope(2.0)
    rich.setInSlope(-1.0)
    rich.setAccel(3.0)
    hou.parm('/obj/assembly/tupleold/triz').setKeyframe(rich)
    # Full-state baseline: every channel's keyframes with slopes and acceleration,
    # captured BEFORE the migration (Houdini may normalize accel on write; the
    # migration must be faithful to whatever the source curve actually holds).
    expected_state = {channel: [(k.frame(), k.value(), k.slope(), k.inSlope(), k.accel())
                                for k in hou.parm(f'/obj/assembly/tupleold/{channel}').keyframes()]
                      for channel in ('trix', 'triy', 'triz')}
    # One consumer referencing TWO migrated channels plus a deep-relative
    # reference that resolves OUTSIDE the old component and must stay untouched.
    run('ctrl3=tab_create("/obj/assembly","null","ctrl3")\n'
        'create_spare_parms("/obj/assembly/ctrl3",layout=[{"type":"float","name":"drive","default":0}])\n'
        'set_parms("/obj/assembly/ctrl3",{"drive":"ch(\\"../tupleold/trix\\") + ch(\\"../tupleold/triy\\") + ch(\\"../../tupleold/triy\\")"})', owner='assembly')
    # A consumer with a NON-LITERAL argument that cannot be proven independent of
    # the old component: the whole replace refuses BEFORE any write.
    run('ctrl4=tab_create("/obj/assembly","null","ctrl4")\n'
        'create_spare_parms("/obj/assembly/ctrl4",layout=[{"type":"float","name":"drive","default":0}])\n'
        'set_parms("/obj/assembly/ctrl4",{"drive":"ch(\\"../tupleold/trix\\") + ch(\\"../\\" + \\"tupleold/triy\\")"})', owner='assembly')
    nonliteral = fail_with('component_replace("/obj/assembly/tupleold","/obj/assembly/tuplenew",'
                           'migration={"inputs":{},"public_parms":["tri"]})')
    assert 'embedded in a larger expression' in nonliteral and 'ctrl4' in nonliteral, nonliteral
    assert not hou.parm('/obj/assembly/tuplenew/trix').keyframes(), 'a refused preview must not write'
    hou.node('/obj/assembly/ctrl4').destroy()
    # Fixed counterexample 2 of the concatenated-reference class: the fragment
    # literal ALONE ('../tupleold/' + 'triy'). Its literal prefix resolves into
    # the old component, so an unguarded rewrite would silently migrate half a
    # reference. The commit path must refuse it before any write, not rewrite it.
    run('ctrl5=tab_create("/obj/assembly","null","ctrl5")\n'
        'create_spare_parms("/obj/assembly/ctrl5",layout=[{"type":"float","name":"drive","default":0}])\n'
        'set_parms("/obj/assembly/ctrl5",{"drive":"ch(\\"../tupleold/\\" + \\"triy\\")"})', owner='assembly')
    fragment = fail_with('component_replace("/obj/assembly/tupleold","/obj/assembly/tuplenew",dry_run=False,'
                         'migration={"inputs":{},"public_parms":["tri"]})')
    assert 'embedded in a larger expression' in fragment and 'ctrl5' in fragment, fragment
    assert hou.parm('/obj/assembly/ctrl5/drive').expression() == 'ch("../tupleold/" + "triy")', \
        'the refused consumer expression must remain untouched'
    assert not hou.parm('/obj/assembly/tuplenew/trix').keyframes(), 'the refused commit must not write'
    hou.node('/obj/assembly/ctrl5').destroy()
    # Fixed positives for complete-path references: the absolute form is
    # rewritten to the same target. The redundant mid-path navigation form is
    # NOT a tracked Houdini dependency (parmsReferencingThis does not link it),
    # so it stays out of the declared migration scope and keeps targeting the
    # retained old component; the rewrite leaves it byte-identical.
    run('ctrl6=tab_create("/obj/assembly","null","ctrl6")\n'
        'create_spare_parms("/obj/assembly/ctrl6",layout=[{"type":"float","name":"drive","default":0}])\n'
        'set_parms("/obj/assembly/ctrl6",{"drive":"ch(\\"/obj/assembly/tupleold/trix\\") + '
        'ch(\\"../tupleold/triy\\") + ch(\\"../null/../tupleold/triz\\")"})', owner='assembly')
    # Ambiguous slot spelling: {0: 1, "0": 2} is a conflicting plan, refused.
    collision = fail_with('component_replace("/obj/assembly/tupleold","/obj/assembly/tuplenew",'
                          'migration={"inputs":{0:1,"0":2},"public_parms":["tri"]})')
    assert 'slot 0 twice' in collision, collision
    # Candidate type/arity incompatibility is refused at the plan check.
    run('s=tab_create("/obj/assembly","subnet","tuplenarrow")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)\n'
        'create_spare_parms("/obj/assembly/tuplenarrow",layout=[{"type":"float","name":"tri","components":2,"default":[0,0]}])', owner='assembly')
    arity = fail_with('component_replace("/obj/assembly/tupleold","/obj/assembly/tuplenarrow",'
                      'migration={"inputs":{},"public_parms":["tri"]})')
    assert 'arity differs' in arity, arity
    run('s=tab_create("/obj/assembly","subnet","tupletext")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)\n'
        'create_spare_parms("/obj/assembly/tupletext",layout=[{"type":"int","name":"tri","components":3,"default":[0,0,0]}])', owner='assembly')
    type_refused = fail_with('component_replace("/obj/assembly/tupleold","/obj/assembly/tupletext",'
                             'migration={"inputs":{},"public_parms":["tri"]})')
    assert 'type differs' in type_refused, type_refused
    # Channel-level declaration stays refused with the tuple name named.
    channel_only = fail_with('component_replace("/obj/assembly/tupleold","/obj/assembly/tuplenew",'
                             'migration={"inputs":{},"public_parms":["trix"]})')
    assert 'channel of tuple' in channel_only and "'tri'" in channel_only, channel_only
    tuple_preview = run('__result__=component_replace("/obj/assembly/tupleold","/obj/assembly/tuplenew",'
                        'migration={"inputs":{},"public_parms":["tri"]})', owner='assembly')
    assert tuple_preview['ok'] is True, tuple_preview
    rows = tuple_preview['migration']['parameter_consumers']
    assert sorted((row['parm'].split('/')[-2], tuple(row['channels'])) for row in rows) == \
        [('ctrl3', ('trix', 'triy')), ('ctrl6', ('trix', 'triy'))], rows
    run(f'__result__=component_replace("/obj/assembly/tupleold","/obj/assembly/tuplenew",dry_run=False,'
        f'expected_plan={tuple_preview["plan"]!r},migration={{"inputs":{{}},"public_parms":["tri"]}})', owner='assembly')
    for channel in ('trix', 'triy', 'triz'):
        moved_keys = hou.parm(f'/obj/assembly/tuplenew/{channel}').keyframes()
        moved_state = [(k.frame(), k.value(), k.slope(), k.inSlope(), k.accel()) for k in moved_keys]
        assert moved_state == expected_state[channel], (
            'full keyframe state must survive the migration: ' + channel
            + ' ' + repr(moved_state) + ' != ' + repr(expected_state[channel]))
        kept_keys = hou.parm(f'/obj/assembly/tupleold/{channel}').keyframes()
        assert [(k.frame(), k.value()) for k in kept_keys] == [(s[0], s[1]) for s in expected_state[channel]], channel
    assert hou.parm('/obj/assembly/ctrl3/drive').expression() == \
        'ch("../tuplenew/trix") + ch("../tuplenew/triy") + ch("../../tupleold/triy")', \
        hou.parm('/obj/assembly/ctrl3/drive').expression()
    # Complete-path forms are rewritten to the same resolved target: the
    # absolute form stays absolute, and even the mid-path navigation reference
    # that Houdini's dependency graph does not track is repointed by its
    # resolved target - no textual reference into the old component survives.
    assert hou.parm('/obj/assembly/ctrl6/drive').expression() == \
        'ch("/obj/assembly/tuplenew/trix") + ch("../tuplenew/triy") + ch("../tuplenew/triz")', \
        hou.parm('/obj/assembly/ctrl6/drive').expression()
    assert hou.node('/obj/assembly/sink3').input(0).path() == '/obj/assembly/tuplenew'
    assert hou.node('/obj/assembly/sink2').input(0) is not None  # earlier scenario untouched
    # Expression-driven keyframes are refused at preview, not mid-commit.
    run('s=tab_create("/obj/assembly","subnet","keyold")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)\n'
        'create_spare_parms("/obj/assembly/keyold",layout=[{"type":"float","name":"speed","default":1}])', owner='assembly')
    run('s=tab_create("/obj/assembly","subnet","keynew")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)\n'
        'create_spare_parms("/obj/assembly/keynew",layout=[{"type":"float","name":"speed","default":1}])', owner='assembly')
    run('keysink=tab_create("/obj/assembly","null","keysink",inputs=["/obj/assembly/keyold"])', owner='assembly')
    expression_key = hou.Keyframe()
    expression_key.setFrame(1)
    expression_key.setExpression('1 + $F', hou.exprLanguage.Hscript)
    hou.parm('/obj/assembly/keyold/speed').setKeyframe(expression_key)
    refused = fail_with('component_replace("/obj/assembly/keyold","/obj/assembly/keynew",migration={"public_parms":["speed"]})')
    assert 'keyframes driven by expressions are not migrated' in refused, refused
    # R4: per-key segment state. The migrated keys must carry the FULL segment
    # state per key - segment expressions (including non-default linear), raw
    # slope/acceleration data on expression-free keys, and incoming
    # acceleration, set or unset. The guarantee is per-key segment-state
    # faithfulness for these covered classes; it is not a blanket promise that
    # every conceivable curve state survives.
    # HOM fact (probed, H21/H22): a key read back from a live parm always
    # reports isExpressionSet() True - Houdini materializes the default
    # bezier() segment on write. The capture-side first-key-no-expression
    # branch is therefore exercised at the unit level below with real
    # in-memory hou.Keyframe objects whose HOM read-back state is
    # isExpressionSet() False.
    run('s=tab_create("/obj/assembly","subnet","segold")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)', owner='assembly')
    run('s=tab_create("/obj/assembly","subnet","segnew")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)', owner='assembly')
    run('segsink=tab_create("/obj/assembly","null","segsink",inputs=["/obj/assembly/segold"])', owner='assembly')
    run('create_spare_parms("/obj/assembly/segold",layout=[{"type":"float","name":"speed","default":1}])', owner='assembly')
    run('create_spare_parms("/obj/assembly/segnew",layout=[{"type":"float","name":"speed","default":2}])', owner='assembly')
    seg_old = hou.parm('/obj/assembly/segold/speed')
    with h._execution_owner('assembly', 'segment-state-fixture'):
        first_raw = hou.Keyframe(5.0)
        first_raw.setFrame(2)
        first_raw.setSlope(1.5)
        first_raw.setAccel(2.0)
        expr_bezier = hou.Keyframe(7.0)
        expr_bezier.setFrame(10)
        expr_bezier.setExpression('bezier()', hou.exprLanguage.Hscript)
        expr_bezier.setSlope(0.75)
        expr_bezier.setInSlope(-1.25)
        expr_bezier.setAccel(1.5)
        expr_bezier.setInAccel(2.5)
        mid_raw = hou.Keyframe(8.0)
        mid_raw.setFrame(15)
        mid_raw.setSlope(-0.25)
        mid_raw.setInSlope(0.5)
        mid_raw.setAccel(0.9)
        mid_raw.setInAccel(0.5)
        expr_linear = hou.Keyframe(9.0)
        expr_linear.setFrame(20)
        expr_linear.setExpression('linear()', hou.exprLanguage.Hscript)
        seg_old.setKeyframes([first_raw, expr_bezier, mid_raw, expr_linear])
    def optional(accessor, key):
        try:
            return accessor()
        except hou.KeyframeValueNotSet:
            return None
    def full_state(parm):
        return [(k.frame(), k.value(), k.slope(), k.inSlope(),
                 optional(k.accel, k), optional(k.inAccel, k),
                 k.expression() if k.isExpressionSet() else None) for k in parm.keyframes()]
    # Precondition pinned by HOM read-back of the ACTUAL curve (not variable
    # names): every written key carries a materialized segment expression
    # (bezier() default or the real one), and Houdini's own write
    # normalization recomputes incoming accelerations - the baseline below is
    # whatever the source curve actually holds, and the migration must be
    # faithful to exactly that state.
    pre_state = seg_old.keyframes()
    assert [k.isExpressionSet() for k in pre_state] == [True, True, True, True], \
        [k.isExpressionSet() for k in pre_state]
    assert [k.expression() if k.isExpressionSet() else None for k in pre_state] == \
        ['bezier()', 'bezier()', 'bezier()', 'linear()'], \
        [k.expression() if k.isExpressionSet() else None for k in pre_state]
    seg_baseline = full_state(seg_old)
    seg_preview = run('__result__=component_replace("/obj/assembly/segold","/obj/assembly/segnew",'
                      'migration={"inputs":{},"public_parms":["speed"]})', owner='assembly')
    run(f'__result__=component_replace("/obj/assembly/segold","/obj/assembly/segnew",dry_run=False,'
        f'expected_plan={seg_preview["plan"]!r},migration={{"inputs":{{}},"public_parms":["speed"]}})', owner='assembly')
    seg_moved = full_state(hou.parm('/obj/assembly/segnew/speed'))
    assert len(seg_moved) == 4, seg_moved
    for before, after in zip(seg_baseline, seg_moved):
        for field, left, right in zip(('frame', 'value', 'slope', 'accel', 'inAccel', 'expression'), before, after):
            if isinstance(left, float):
                # Houdini re-normalizes segment acceleration on EVERY write:
                # re-writing the read-back payload shifts an incoming
                # acceleration by up to ~6.4e-9 even for a pure batch set
                # (probed on H21). The migration is faithful to the source
                # state within Houdini's own write-to-write variance; frames,
                # values and expressions stay exact.
                assert abs(left - right) < 1e-7, (field, left, right)
            else:
                assert left == right, (field, left, right)
    assert seg_moved[3][6] == 'linear()', 'the linear segment expression must survive the migration'
    assert seg_moved[1][5] is not None and abs(seg_moved[1][5] - seg_baseline[1][5]) < 1e-7, \
        ('the non-default incoming acceleration of the expression key must survive', seg_baseline, seg_moved)
    assert seg_moved[2][5] is not None and abs(seg_moved[2][5] - seg_baseline[2][5]) < 1e-7, \
        ('the non-default incoming acceleration of the raw key must survive', seg_baseline, seg_moved)
    assert seg_moved[3][5] is None and seg_baseline[3][5] is None, \
        'the trailing linear() key must not grow a spurious incoming acceleration'
    # The same fixed test proves the REAL historical implementation fails:
    # the capture+restore pair as of 0effe03 (verbatim git blobs, sha256
    # pinned above) rebuilds each captured key field by field WITHOUT the
    # incoming acceleration and writes keys one by one, so on the same input
    # the incoming-acceleration state is lost and the outgoing acceleration
    # is recomputed by the write path - far beyond the write-to-write
    # variance the fixed implementation stays within. Segment expressions do
    # survive this pair (the capture carried them); the known-lost states are
    # the incoming acceleration and the write-path acceleration fidelity.
    assert hashlib.sha256(RESTORE_0EFFE03.encode('utf-8')).hexdigest() == RESTORE_0EFFE03_SHA256
    assert hashlib.sha256(CAPTURE_0EFFE03.encode('utf-8')).hexdigest() == CAPTURE_0EFFE03_SHA256
    legacy_ns = {'hou': hou, 're': re}
    exec(CAPTURE_0EFFE03, legacy_ns)
    exec(RESTORE_0EFFE03, legacy_ns)
    with h._execution_owner('assembly', 'segment-state-fixture'):
        scratch = hou.node('/obj/assembly/segnew').createNode('null', 'legacyscratch')
        ptg = scratch.parmTemplateGroup()
        ptg.append(hou.FloatParmTemplate('speed', 'speed', 1, default_value=(0,)))
        scratch.setParmTemplateGroup(ptg)
        legacy_target = scratch.parm('speed')
        legacy_ns['_restore_parm'](legacy_target, legacy_ns['_capture_parm'](seg_old))
    legacy_state = full_state(legacy_target)
    legacy_failed = []
    for before, after in zip(seg_baseline, legacy_state):
        for field, left, right in zip(('frame', 'value', 'slope', 'inSlope', 'accel', 'inAccel', 'expression'), before, after):
            same = abs(left - right) < 1e-7 if isinstance(left, float) else left == right
            if not same:
                legacy_failed.append((field, left, right))
    assert any(field == 'inAccel' for field, left, right in legacy_failed), \
        'the historical pair must lose the incoming-acceleration state: ' + repr(legacy_failed)
    assert any(field == 'accel' and isinstance(left, float) and isinstance(right, float)
               and abs(left - right) > 1e-7 for field, left, right in legacy_failed), \
        'the historical per-key write must recompute the outgoing acceleration: ' + repr(legacy_failed)
    assert all(entry[0] != 'expression' for entry in legacy_failed), \
        'the historical pair carries segment expressions; the known-lost states are acceleration-only: ' \
        + repr(legacy_failed)
    scratch.destroy()
    # Capture-side per-key segment initialization: the pre-iteration-6 capture
    # (verbatim git blob, sha256 pinned above) used its `segment` variable
    # without initializing it per key, so a curve whose FIRST key reports no
    # expression raised NameError instead of capturing. Live parms always
    # materialize a segment expression (HOM fact above), so the branch is hit
    # with real in-memory hou.Keyframe objects: their HOM read-back state
    # (isExpressionSet() False) is the precondition, the pre-fix capture
    # raises NameError on the same input, the fixed capture succeeds.
    assert hashlib.sha256(CAPTURE_49BF56E.encode('utf-8')).hexdigest() == CAPTURE_49BF56E_SHA256
    class _FakeParm:
        def __init__(self, keys):
            self._keys = keys
        def keyframes(self):
            return list(self._keys)
    bare_first = hou.Keyframe(3.0)
    bare_first.setFrame(1)
    expressed_second = hou.Keyframe(4.0)
    expressed_second.setFrame(9)
    expressed_second.setExpression('bezier()', hou.exprLanguage.Hscript)
    assert bare_first.isExpressionSet() is False, 'the in-memory first key must read back expression-free'
    assert expressed_second.isExpressionSet() is True
    fake_parm = _FakeParm([bare_first, expressed_second])
    buggy_ns = {'hou': hou, 're': re}
    exec(CAPTURE_49BF56E, buggy_ns)
    try:
        buggy_ns['_capture_parm'](fake_parm)
        raise AssertionError('the pre-iteration-6 capture must fail on the first-key-no-expression branch')
    except NameError:
        pass
    fixed_keys = components._capture_parm(fake_parm)
    assert fixed_keys[0] == 'keys' and fixed_keys[1] == [bare_first, expressed_second], fixed_keys
    # R3 scope: expression-language support, lexical discrimination and the
    # refusal boundary. Supported language: HScript channel expressions only.
    # Within HScript the scan is lexical - string literals are data whose raw
    # text is preserved (a backslash stops termination without changing the
    # value, probed), so an ordinary string containing ch(...) text is never
    # rewritten - while the first literal argument of an ACTUAL channel call is
    # the only rewritable reference. Python-language references are refused
    # before any write, and audited on every detected consumer node because
    # the dependency graph does not track them (probed).
    run('s=tab_create("/obj/assembly","subnet","refold")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)', owner='assembly')
    run('s=tab_create("/obj/assembly","subnet","refnew")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)', owner='assembly')
    run('create_spare_parms("/obj/assembly/refold",layout=[{"type":"float","name":"gain","default":1}])', owner='assembly')
    run('create_spare_parms("/obj/assembly/refnew",layout=[{"type":"float","name":"gain","default":2}])', owner='assembly')
    run('refsink=tab_create("/obj/assembly","null","refsink",inputs=["/obj/assembly/refold"])', owner='assembly')
    # (1) An actual reference PLUS an ordinary string containing ch(...) text:
    # the reference is rewritten, the string survives byte-identical.
    string_expr = 'ch("../refold/gain") + 0*strcmp("ch(../unrelated/gain)", "x")'
    run('ctrl7=tab_create("/obj/assembly","null","ctrl7")\n'
        'create_spare_parms("/obj/assembly/ctrl7",layout=[{"type":"float","name":"drive","default":0}])\n'
        f'set_parms("/obj/assembly/ctrl7",{{"drive":{string_expr!r}}})', owner='assembly')
    # (2) Escaped-quote variant: the string holds a full ch("...") reference
    # shape with backslash-escaped quotes; still data, still preserved raw.
    # (2) Escaped quotes: a string holding backslash-escaped quotes stays raw
    # data (the lexer must not end the literal early) while the real reference
    # is rewritten. (HOM fact, probed: an expression whose string embeds
    # escaped ch(...) text is NOT tracked by the dependency graph at all, so
    # the escaped ch-text case is pinned at the unit level below, where the
    # pure string constant carries both.)
    escaped_expr = 'ch("../refold/gain") * (1 - strcmp("a \\"quoted\\" word", ""))'
    run('ctrl7b=tab_create("/obj/assembly","null","ctrl7b")\n'
        'create_spare_parms("/obj/assembly/ctrl7b",layout=[{"type":"float","name":"drive","default":0}])\n'
        f'set_parms("/obj/assembly/ctrl7b",{{"drive":{escaped_expr!r}}})', owner='assembly')
    ref_preview = run('__result__=component_replace("/obj/assembly/refold","/obj/assembly/refnew",'
                      'migration={"inputs":{},"public_parms":["gain"]})', owner='assembly')
    assert sorted(row['parm'].split('/')[-2] for row in ref_preview['migration']['parameter_consumers']) == \
        ['ctrl7', 'ctrl7b'], ref_preview['migration']['parameter_consumers']
    run(f'__result__=component_replace("/obj/assembly/refold","/obj/assembly/refnew",dry_run=False,'
        f'expected_plan={ref_preview["plan"]!r},migration={{"inputs":{{}},"public_parms":["gain"]}})', owner='assembly')
    assert hou.parm('/obj/assembly/ctrl7/drive').expression() == \
        'ch("../refnew/gain") + 0*strcmp("ch(../unrelated/gain)", "x")', \
        hou.parm('/obj/assembly/ctrl7/drive').expression()
    assert hou.parm('/obj/assembly/ctrl7b/drive').expression() == \
        'ch("../refnew/gain") * (1 - strcmp("a \\"quoted\\" word", ""))', \
        hou.parm('/obj/assembly/ctrl7b/drive').expression()
    # (3) A python-language reference on a detected consumer node: the graph
    # does not track it, so the audit refuses the replace before any write.
    # A fresh pair is used: a candidate that already received parameter
    # consumers is refused by the existing already-has-consumers invariant, so
    # the second replace must not reuse the committed pair.
    run('s=tab_create("/obj/assembly","subnet","pyold")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)', owner='assembly')
    run('s=tab_create("/obj/assembly","subnet","pynnew")\nb=tab_create(s,"box","shape")\nsop_set_output(b,output_index=0)', owner='assembly')
    run('create_spare_parms("/obj/assembly/pyold",layout=[{"type":"float","name":"gain","default":1}])', owner='assembly')
    run('create_spare_parms("/obj/assembly/pynnew",layout=[{"type":"float","name":"gain","default":2}])', owner='assembly')
    run('pysink=tab_create("/obj/assembly","null","pysink",inputs=["/obj/assembly/pyold"])', owner='assembly')
    py_expr = 'ch("../pyold/gain")'
    run('ctrl8=tab_create("/obj/assembly","null","ctrl8")\n'
        'create_spare_parms("/obj/assembly/ctrl8",layout=[{"type":"float","name":"drive","default":0}])\n'
        f'set_parms("/obj/assembly/ctrl8",{{"drive":{py_expr!r}}})', owner='assembly')
    run('create_spare_parms("/obj/assembly/ctrl8",layout=[{"type":"string","name":"brief","default":"x"}])', owner='assembly')
    with h._execution_owner('assembly', 'r3-scope'):
        hou.node('/obj/assembly/ctrl8').parm('brief').setExpression('ch("../pyold/gain") * 2', hou.exprLanguage.Python)
    python_refused = fail_with('component_replace("/obj/assembly/pyold","/obj/assembly/pynnew",dry_run=False,'
                               'migration={"inputs":{},"public_parms":["gain"]})')
    assert 'unsupported expression language' in python_refused and 'ctrl8' in python_refused, python_refused
    assert not hou.parm('/obj/assembly/pynnew/gain').keyframes(), 'a refused replace must not write'
    # Unit level: the rewriter refuses the python-language consumer itself, a
    # pure string constant (no actual call), and leaves the refused parms
    # byte-identical.
    from dsh_component_contracts import _repoint_expression as _repoint
    try:
        _repoint(hou.node('/obj/assembly/ctrl8').parm('brief'),
                 hou.node('/obj/assembly/pyold'), hou.node('/obj/assembly/pynnew'))
        raise AssertionError('python-language consumers must be refused')
    except ValueError as error:
        assert 'unsupported expression language' in str(error), error
    assert hou.node('/obj/assembly/ctrl8').parm('brief').expression() == 'ch("../pyold/gain") * 2'
    # A pure string constant is data end to end: no actual call, nothing to
    # rewrite, the text survives byte-identical.
    constant_expr = '"see ch(\\"../pyold/gain\\") docs"'
    with h._execution_owner('assembly', 'r3-scope'):
        hou.node('/obj/assembly/ctrl8').parm('brief').setExpression(constant_expr, hou.exprLanguage.Hscript)
    try:
        _repoint(hou.node('/obj/assembly/ctrl8').parm('brief'),
                 hou.node('/obj/assembly/pyold'), hou.node('/obj/assembly/pynnew'))
        raise AssertionError('a pure string constant is not a rewritable reference')
    except ValueError as error:
        assert 'unsupported consumer reference form' in str(error), error
    assert hou.node('/obj/assembly/ctrl8').parm('brief').expression() == constant_expr, \
        hou.node('/obj/assembly/ctrl8').parm('brief').expression()
    hou.node('/obj/assembly/ctrl8').destroy()
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
