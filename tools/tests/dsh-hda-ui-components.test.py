"""Native recreation of generic HDA layout patterns; no reference asset code."""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h
from dsh_parameter_ui import expand_layout, analyze_ui

layouts = json.loads((ROOT/'skills/houdini-parameter-ui/assets/ui-component-gallery.json').read_text(encoding='utf-8'))


def run(code, query=False):
    r = b.run_code(code, owner_session='layout-author', owner_call='layout-test', read_only=query)
    assert r['ok'], r.get('error')
    return r


def rejects(fn, part):
    try:
        fn()
    except Exception as e:
        assert part in str(e), str(e)
    else:
        raise AssertionError('expected failure: '+part)


with tempfile.TemporaryDirectory(prefix='dsh-ui-components-') as temp:
    nodes=[]
    for name, layout in layouts.items():
        library=Path(temp)/(name+'.hda')
        path=run(f"""
g=tab_create('/obj','geo',name={name!r})
n=tab_create(g,'subnet',name='controls')
__result__=hda_create(n,{'dsh_ui::'+name+'::1.0'!r},hda_file={str(library)!r})
""")['result']['node']
        n=hou.node(path); nodes.append(n)
        original=library.read_bytes()
        preview=run(f'__result__=hda_set_interface({path!r},layout={layout!r},keep_std=False,dry_run=True)')
        assert preview['transaction']['status']=='no_scene_change'
        assert library.read_bytes()==original
        assert not preview['result']['ui_analysis']['issues'], preview['result']['ui_analysis']
        result=run(f'__result__=hda_set_interface({path!r},layout={layout!r},keep_std=False)')['result']
        assert not result['ui_analysis']['issues'],result['ui_analysis']
        info=run(f'__result__=hda_info({path!r},max_depth=12,analyze_ui=True)',True)['result']
        assert info['ui_analysis']['entries']>15
        if name=='shape_controls':
            group=n.parmTemplateGroup()
            assert n.parmTuple('offset').eval()==(0.,0.,0.)
            assert group.find('direction').tags()['sidefx::header_toggle']=='direction_enabled'
            assert group.find('direction').tags()['sidefx::header_parm']=='direction_weight'
            assert group.find('noise_page').tabConditionals()[hou.parmCondType.HideWhen]=='{ detail_mode == pattern }'
            assert group.find('remap_options').tabConditionals()[hou.parmCondType.HideWhen]=='{ profile_enabled == 0 }'
            n.updateParmStates()
            assert n.parm('profile_ramp').isHidden()
            assert n.parm('direction_weight').isDisabled()
            run(f"set_parms({path!r},{{'direction_enabled':1,'profile_enabled':1}})")
            n.updateParmStates()
            assert not n.parm('profile_ramp').isHidden()
            assert not n.parm('direction_weight').isDisabled()
            assert len(n.parm('profile_ramp').evalAsRamp().keys())==2
        else:
            assert n.parmTemplateGroup().find('range_heading').columnLabels()==('Value Range',)
            assert n.parmTuple('preview_color').eval()==(0.2,0.6,0.9)
            assert n.evalParm('entries')==2 and n.parm('entry_name2') is not None
            # Test native UI repetition lifecycle only in this disposable fixture.
            n.parm('entry_name1').set('first');n.parm('entry_name2').set('second')
            n.parm('entries').insertMultiParmInstance(1)
            assert n.evalParm('entry_name3')=='second'
            n.parm('entries').removeMultiParmInstance(1)
            assert n.evalParm('entry_name2')=='second'
        # Header/help/controls survive save/reload, without serializing user assets.
        hip=Path(temp)/(name+'.hip')
        hou.hipFile.save(str(hip))
        hou.hipFile.load(str(hip),suppress_save_prompt=True)
        n=hou.node(path)
        assert n is not None
        if name=='attribute_controls':
            assert n.evalParm('entry_name2')=='second'
        # Save optional generic gallery artifacts only when a caller explicitly supplies a directory.
        output=os.environ.get('DSH_UI_GALLERY_OUTPUT')
        if output:
            import shutil
            out=Path(output);out.mkdir(parents=True,exist_ok=True)
            shutil.copy2(library,out/library.name)
    # Schema failures occur before writing the targeted definition.
    with h._execution_owner('layout-author','reject'):
        # HIP reload changes provenance, so the selected self-created fixture is explicit here.
        for layout,part in [
            ([{'component':'row','parms':[{'type':'ramp','name':'curve'}]}],'leaf'),
            ([{'component':'section','name':'s','parms':[],'enabld':True}],'unknown'),
            ([{'type':'float','name':'vec','components':3,'default':[0,1]}],'match components'),
            ([{'component':'repeater','name':'items','parms':[{'type':'float','name':'value'}]}],'placeholders'),
        ]:
            before=n.type().definition().sections()['DialogScript'].contents()
            rejects(lambda: h.hda_set_interface(n,layout=layout,keep_std=False,
                    allow_foreign='this test created and reloaded this fixture'),part)
            assert n.type().definition().sections()['DialogScript'].contents()==before
    diagnostic=analyze_ui([{'name':'control','type':'Float','conditionals':{'DisableWhen':'{ absent == 0 }'}}])
    assert diagnostic['issues'][0]['code']=='unresolved_reference'
    # No restriction that all UIs use components: one plain control stays one control.
    plain=[{'type':'float','name':'simple','default':1}]
    assert expand_layout(plain)==plain
    hou.hipFile.clear(suppress_save_prompt=True)

print('UI components/conditions/tuples/ramp/multiparm/reload passed on '+hou.applicationVersionString())
