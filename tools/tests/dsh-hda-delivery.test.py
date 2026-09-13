"""Public callbacks and fresh-process delivery, including missing dependencies."""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import hou
import dsh_bridge as b

spec = importlib.util.spec_from_file_location('delivery_check', ROOT / 'tools/hda-delivery-check.py')
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)


def run(code):
    result = b.run_code(code, owner_session='delivery-author', owner_call='author-fixture')
    assert result['ok'], result.get('error')
    return result.get('result')


with tempfile.TemporaryDirectory(prefix='dsh-authored-tool-') as temporary:
    temp = Path(temporary)
    assets = temp / 'asset.hda'
    child_asset = temp / 'child.hda'
    modules = temp / 'python'; modules.mkdir()
    (modules / 'delivery_fixture_support.py').write_text('def calculate(value):\n    return value * 2\n', encoding='utf-8')
    target = run(f"""
n=tab_create('/obj','subnet',name='delivery_source')
g=tab_create(n,'geo',name='geometry')
child=tab_create(g,'subnet',name='output_box')
box=tab_create(child,'box',name='box')
hda_create(child,'dsh_fixture::child::1.0',hda_file={str(child_asset)!r})
__result__=hda_create(n,'dsh_fixture::delivery::1.0',hda_file={str(assets)!r})
""")['node']
    module = '''def choices(kwargs):
    return ["double", "Double", "triple", "Triple"]

def execute(kwargs):
    from delivery_fixture_support import calculate
    node = kwargs["node"]
    gain = node.evalParm("gain")
    if gain < 0:
        raise ValueError("gain must be nonnegative")
    if gain == 0:
        import hou
        hou.setUpdateMode(hou.updateMode.Manual)
        return
    node.parm("result").set(calculate(gain))
    node.parm("runs").set(node.evalParm("runs") + 1)
'''
    run(f'hda_set_section({target!r}, "PythonModule", {module!r})')
    ui = [{'type': 'float', 'name': 'gain', 'default': 2.0},
          {'type': 'float', 'name': 'result', 'default': 0.0},
          {'type': 'int', 'name': 'runs', 'default': 0},
          {'type': 'string', 'name': 'choice', 'default': 'double'},
          {'type': 'button', 'name': 'execute', 'callback': 'kwargs["node"].hdaModule().execute(kwargs)'}]
    run(f'hda_set_interface({target!r}, {ui!r}, keep_std=False)')
    # Native fixture setup for a dynamic-menu type not yet writable in the spec.
    definition = hou.node(target).type().definition()
    group = definition.parmTemplateGroup()
    menu = group.find('choice')
    menu.setItemGeneratorScript('kwargs["node"].hdaModule().choices(kwargs)')
    menu.setItemGeneratorScriptLanguage(hou.scriptLanguage.Python)
    group.replace('choice', menu)
    definition.setParmTemplateGroup(group)
    original = assets.read_bytes()
    manifest = {'assets': ['child.hda', 'asset.hda'], 'python_paths': ['python'], 'category': 'Object',
                'type': 'dsh_fixture::delivery::1.0', 'cases': [
                    {'id': 'default_and_repeat', 'buttons': ['execute', 'execute'],
                     'menus': {'choice': ['double', 'triple']},
                     'expect_parms': {'gain': 2.0, 'result': 4.0, 'runs': 2, 'choice': 'double'},
                     'expect_geometry': {'output': 'geometry/output_box', 'points': 8, 'primitives': 6, 'bounds_size':[1,1,1]}},
                    {'id': 'different_input', 'values': {'gain': 3.5}, 'buttons': ['execute'],
                     'expect_parms': {'result': 7.0, 'runs': 1}},
                    {'id': 'invalid_input', 'values': {'gain': -1}, 'buttons': ['execute'],
                     'expect_error': 'gain must be nonnegative', 'expect_parms': {'result': 0.0, 'runs': 0}},
                ]}
    source = temp / 'manifest.json'
    source.write_text(json.dumps(manifest), encoding='utf-8')
    hython = Path(hou.text.expandString('$HFS')) / 'bin/hython.exe'
    report = runner.check(source, hython)
    assert report['ok'], report
    assert len(report['cases']) == 3 and report['exit_code'] == 0
    assert report['worker']['released'] and report['worker']['phase'] == 'run'
    assert assets.read_bytes() == original
    report = runner.check(source, temp / 'missing-hython.exe')
    assert not report['ok'] and report['worker']['phase'] == 'spawn', report
    assert not report['worker']['started'] and not report['worker']['released'], report
    cancel = temp / 'cancel'
    cancel.write_text('cancel', encoding='utf-8')
    report = runner.check(source, hython, cancel_file=cancel)
    assert not report['ok'] and report['worker']['status'] == 'cancelled_before_start', report
    assert not report['worker']['released'] and assets.read_bytes() == original
    normal_cases = manifest['cases']
    # Same point/primitive counts cannot conceal an incorrect dimension or Cd.
    for expectation, message in [({'bounds_size':[2,1,1]},'bounds_size'),
                                 ({'point_cd':[1,0,0]},'point_cd')]:
        manifest['cases']=[{'id':'false-green-counterexample','expect_geometry':
            {'output':'geometry/output_box','points':8,'primitives':6,**expectation}}]
        source.write_text(json.dumps(manifest),encoding='utf-8-sig')
        report=runner.check(source,hython)
        assert not report['ok'] and message in json.dumps(report),report
    manifest['cases']=normal_cases
    manifest['cases'] = [{'id':'manual-output','values':{'gain':0},'buttons':['execute'],
                          'expect_geometry':{'output':'geometry/output_box','points':8,'primitives':6}}]
    source.write_text(json.dumps(manifest), encoding='utf-8')
    report = runner.check(source, hython)
    assert not report['ok'] and 'not_cooked_manual' in json.dumps(report), report
    manifest['cases'] = normal_cases
    # Same package without its Python dependency must fail in a fresh process,
    # even though the author machine has the original module directory.
    manifest['python_paths'] = []
    source.write_text(json.dumps(manifest), encoding='utf-8')
    report = runner.check(source, hython)
    assert not report['ok'] and 'delivery_fixture_support' in json.dumps(report), report
    assert assets.read_bytes() == original
    manifest['python_paths'] = ['python']
    manifest['assets'] = ['asset.hda']
    source.write_text(json.dumps(manifest), encoding='utf-8')
    report = runner.check(source, hython)
    assert not report['ok'] and not report['cases'][0]['ok'], report
    manifest['assets'] = ['child.hda', 'asset.hda']
    # A callback that ran is insufficient when the expected actual result is wrong.
    manifest['python_paths'] = ['python']
    manifest['cases'] = [{'id': 'wrong_output', 'buttons': ['execute'], 'expect_parms': {'result': 999}}]
    source.write_text(json.dumps(manifest), encoding='utf-8')
    report = runner.check(source, hython)
    assert not report['ok'] and report['cases'][0]['buttons_executed'] == ['execute'], report
    # Definition remains usable after unloading/reinstalling only the actual file.
    hou.node(target).destroy(); hou.hda.uninstallFile(str(assets))
    hou.hda.uninstallFile(str(child_asset))

print('HDA real callbacks/menu/repeat/input/error/fresh-process dependencies passed on ' + hou.applicationVersionString())
