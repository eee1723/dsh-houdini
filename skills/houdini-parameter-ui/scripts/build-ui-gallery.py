"""Build independent generic UI samples in a disposable hython/GUI test process."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'houdini/python3.11libs'))


def build(output):
    import hou
    import dsh_bridge as bridge
    if hou.hipFile.hasUnsavedChanges() or hou.node('/obj').children():
        raise RuntimeError('gallery builder requires an empty disposable session')
    output = Path(output).resolve()
    if output.is_relative_to(ROOT):
        raise ValueError('gallery HIP/HDA output must be outside the plugin repository')
    output.mkdir(parents=True, exist_ok=True)
    layouts = json.loads((Path(__file__).resolve().parents[1]/'assets/ui-component-gallery.json').read_text(encoding='utf-8'))
    targets = [output/(name+'.hda') for name in layouts] + [output/'ui-gallery.hip']
    if any(p.exists() for p in targets):
        raise ValueError('gallery output already exists; choose a new output directory')
    nodes = {}
    for name, layout in layouts.items():
        path = str(output/(name+'.hda'))
        code = f"""
g=tab_create('/obj','geo',name={name!r})
n=tab_create(g,'subnet',name='ui_controls')
asset=hda_create(n,{'dsh_ui::'+name+'::1.0'!r},hda_file={path!r})
check=hda_set_interface(asset['node'],layout={layout!r},keep_std=False)
__result__={{'node':asset['node'],'analysis':check['ui_analysis']}}
"""
        result = bridge.run_code(code, owner_session='ui-gallery-author', owner_call=name)
        if not result['ok']:
            raise RuntimeError(result['error'])
        nodes[name] = result['result']['node']
    result = bridge.run_code(
        f"__result__=scene_save_as({str(output/'ui-gallery.hip')!r}, expected_current_path={hou.hipFile.path()!r}, reason='explicit UI gallery output')",
        owner_session='ui-gallery-author', owner_call='save-gallery')
    if not result['ok']:
        raise RuntimeError(result['error'])
    report = {'houdini': hou.applicationVersionString(), 'nodes': nodes,
              'hip': str(output/'ui-gallery.hip'),
              'scope': 'generic UI mechanisms only; no source asset code or modeled effect'}
    (output/'gallery.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(build(args.output),indent=2))
