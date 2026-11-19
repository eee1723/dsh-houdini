"""Actual USD binding resolution through an isolated Houdini/Bridge builder.

Run with ordinary Python, --hython <explicit hython> and --output-dir <new
directory in a managed evidence batch>. No GUI, renderer, user HIP or live port.
"""
from pathlib import Path
import argparse
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('isolated_check', ROOT / 'tools/isolated-houdini-check.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

BUILDER = r'''
from pxr import Usd, UsdGeom, UsdShade

authored = """from pxr import UsdGeom, UsdShade
s = hou.pwd().editableStage()
parent = UsdGeom.Xform.Define(s, '/Parent').GetPrim()
UsdGeom.Mesh.Define(s, '/Parent/Inherited')
local = UsdGeom.Mesh.Define(s, '/Parent/Local').GetPrim()
UsdGeom.Mesh.Define(s, '/Unbound')
parent_mat = UsdShade.Material.Define(s, '/Materials/Parent')
local_mat = UsdShade.Material.Define(s, '/Materials/Local')
UsdShade.MaterialBindingAPI.Apply(parent).Bind(parent_mat, UsdShade.Tokens.weakerThanDescendants)
UsdShade.MaterialBindingAPI.Apply(local).Bind(local_mat)
prototype = UsdGeom.Xform.Define(s, '/Prototype').GetPrim()
surface = UsdGeom.Mesh.Define(s, '/Prototype/Surface').GetPrim()
UsdShade.MaterialBindingAPI.Apply(surface).Bind(local_mat)
instance = UsdGeom.Xform.Define(s, '/Instance').GetPrim()
instance.GetReferences().AddInternalReference('/Prototype')
instance.SetInstanceable(True)
"""
node = tab_create('/stage', 'pythonscript', name='binding_fixture', parms={'python': authored})

def layers():
    # Hold the node while using its real composed stage. Snapshot every layer,
    # including the session layer, rather than just the root's sublayer paths.
    stage = node.stage()
    return [(layer.identifier, layer.ExportToString()) for layer in stage.GetLayerStack(includeSessionLayers=True)]

def inspect(path, **options):
    before = layers()
    info = usd_prim_info(node, path, **options)
    assert layers() == before, 'read-only inspection changed a USD layer'
    return info

def expected(info, material, relationship, strength):
    value = info['effective_material_binding']
    assert value['status'] == ('bound' if material else 'unbound'), value
    assert value['material_path'] == material, value
    assert value['relationship_path'] == relationship, value
    assert value['strength'] == strength, value
    assert value['material_purpose'] == 'allPurpose', value
    return value

inherited = inspect('/Parent/Inherited')
assert inherited['material_bindings'] == [], inherited
expected(inherited, '/Materials/Parent', '/Parent.material:binding', 'weakerThanDescendants')
local = inspect('/Parent/Local')
assert local['material_bindings'][0]['targets'] == ['/Materials/Local'], local
expected(local, '/Materials/Local', '/Parent/Local.material:binding', 'weakerThanDescendants')
unbound = inspect('/Unbound')
expected(unbound, None, None, None)
assert 'MaterialBindingAPI' not in node.stage().GetPrimAtPath('/Unbound').GetAppliedSchemas(), 'inspection applied a schema'
proxy = inspect('/Instance/Surface')
assert node.stage().GetPrimAtPath('/Instance/Surface').IsInstanceProxy()
expected(proxy, '/Materials/Local', '/Instance/Surface.material:binding', 'weakerThanDescendants')

# Change only the authored parent binding strength. The child's declared
# relationship stays local while its actual consumer changes to the ancestor.
strong = authored + "\nUsdShade.MaterialBindingAPI.SetMaterialBindingStrength(parent.GetRelationship('material:binding'), UsdShade.Tokens.strongerThanDescendants)\n"
set_parms(node, {'python': strong})
overridden = inspect('/Parent/Local')
assert overridden['material_bindings'] == local['material_bindings'], overridden
expected(overridden, '/Materials/Parent', '/Parent.material:binding', 'strongerThanDescendants')
limited = inspect('/Parent/Local', max_properties=1)
assert limited['properties_truncated']
assert limited['effective_material_binding'] == overridden['effective_material_binding']
set_parms(node, {'python': authored})
restored = inspect('/Parent/Local')
assert restored['effective_material_binding'] == local['effective_material_binding']

__result__ = {'version': hou.applicationVersionString(),
              'inherited': inherited['effective_material_binding'],
              'local': local['effective_material_binding'],
              'strong_parent': overridden['effective_material_binding'],
              'unbound': unbound['effective_material_binding'],
              'instance_proxy': proxy['effective_material_binding'],
              'read_only_layers': True, 'property_budget_preserves_resolution': True,
              'scope': 'Binding resolution only; no textures, renderer, live scene or visual validation.'}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hython', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    directory = args.output_dir.resolve()
    directory.mkdir(exist_ok=False)
    (directory / 'builder.py').write_text(BUILDER, encoding='utf-8')
    manifest = directory / 'manifest.json'
    manifest.write_text(json.dumps({'script': 'builder.py', 'checks': []}), encoding='utf-8')
    result = runner.check(manifest, args.hython.resolve(strict=True), directory / 'run',
                          trusted=True, timeout=120, memory_mb=4096)
    assert result['ok'], result.get('error', result)
    assert result['finished'] and result['worker']['tree_reaped'], result.get('worker')
    assert result['inputs_unchanged'] is True
    print('USD effective binding inheritance, strength, unbound, instance proxy and read-only layers passed')


if __name__ == '__main__':
    main()
