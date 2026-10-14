"""Isolated H21/H22 asset-level controls and incremental COP handoff.

Uses existing public operations: no inferred promotion, global dependency scan,
user HIP, new execution policy or product-specific fixture.
"""
from pathlib import Path
import json,os,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
OWNER='asset-edit-entry-fixture';G='/obj/editable_asset';C=G+'/CTRL';LOCAL=G+'/detail_images/CTRL_DETAIL'

def run(code,read=False):
    r=b.run_code(code,owner_session=OWNER,owner_call='fixture',read_only=read)
    assert r['ok'],r.get('error',r)
    return r.get('result')

def observe():
    return run(f"__result__=cop_layer_stats({G+'/detail_images/OUT_COLOR'!r})")

def pixel_hash():
    # The public observation hash includes process-local node identity. Use
    # actual buffer bytes plus explicit layer metadata for cross-process proof.
    return run(f'''import hashlib
l=hou.node({G+'/detail_images/OUT_COLOR'!r}).layer(0)
try: __result__=hashlib.sha256(l.allBufferElements()).hexdigest()
finally: l.close()
''',True)

def inspect():
    return run(f'''
g=hou.node({G!r});c=g.node('CTRL');local=g.node('detail_images/CTRL_DETAIL')
__result__={{'controls':{{p:c.evalParm(p) for p in ('width','map_gain','map_repeat','map_enabled')}},
 'local':{{p:local.evalParm(p) for p in ('gain','repeat','enabled','technical_bias')}},
 'references':{{p:local.parm(p).getReferencedParm().path() for p in ('gain','repeat','enabled')}},
 'expressions':{{p:local.parm(p).expression() for p in ('gain','repeat','enabled')}},
 'members':sorted(n.name() for n in g.findNetworkBox('surface_sources').nodes()),
 'consumer':g.node('detail_material').evalParm('basecolorpath'),
 'output_inputs':[n.name() for n in g.node('OUT').inputs()],
 'assembly_inputs':[n.name() for n in g.node('assembly').inputs()],
 'note':g.findStickyNote('START').text()}}
''',True)

if '--reopen' in sys.argv:
    hip=Path(sys.argv[sys.argv.index('--reopen')+1]);hou.hipFile.load(str(hip),suppress_save_prompt=True)
    result={'view':inspect(),'layer':observe(),'pixels':pixel_hash()}
    (hip.parent/'reopen.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf8')
    print('isolated reopen observed');sys.exit(0)

with tempfile.TemporaryDirectory(prefix='dsh-asset-edit-entry-') as directory:
    hip=Path(directory)/'asset.hip'
    run(f"scene_save_as({str(hip)!r},expected_current_path={hou.hipFile.path()!r},reason='isolated asset edit-entry fixture')")
    run('''
g=tab_create('/obj','geo','editable_asset');c=tab_create(g,'null','CTRL')
create_spare_parms(c,spec=[{'type':'float','name':'width','label':'Width','default':1.4}])
base=tab_create(g,'copnet','base_images');color=tab_create(base,'layer','color',parms={'signature':'f3','f3':(.12,.2,.3),'setres':1,'res':(32,32)})
tab_create(base,'null','OUT_COLOR',inputs=[color])
s=tab_create(g,'grid','surface',parms={'orient':'xy','sizex':'ch("../CTRL/width")','rows':2,'cols':2})
uv=tab_create(g,'attribwrangle','coordinates',inputs=[s],parms={'class':'vertex','snippet':'v@uv=set(@P.x/ch("../CTRL/width")+.5,@P.y+.5,0);'})
old=tab_create(g,'coppreviewmaterial','base_material',inputs=[uv],parms={'basecolorsource':'cop','basecolorpath':base.path()+'/OUT_COLOR'})
out=tab_create(g,'null','OUT',inputs=[old]);sop_set_output(out)
network_boxes(g,[{'name':'controls','members':['CTRL']},{'name':'geometry','members':['surface','coordinates','base_material','OUT']},{'name':'surface_sources','members':['base_images']}])
network_notes(g,[{'name':'START','text':'Use CTRL for width; base_images supplies color.'}])
''')
    # A later independently developed module has its own implementation panel.
    run('''
g='/obj/editable_asset';d=tab_create(g,'copnet','detail_images');c=tab_create(d,'null','CTRL_DETAIL')
create_spare_parms(c,spec=[{'type':'float','name':'gain','label':'Gain','default':.25},{'type':'int','name':'repeat','label':'Repeat','default':3},{'type':'toggle','name':'enabled','label':'Enabled','default':True},{'type':'float','name':'technical_bias','label':'Technical bias','default':.125}])
set_parm(c,'gain',.63)
domain=tab_create(d,'layer','domain',parms={'setres':1,'res':(32,32),'signature':'f1'})
pattern=tab_create(d,'checkerboard','pattern',inputs=[domain],parms={'signature':'f3','cols':'ch("../CTRL_DETAIL/repeat")','rows':3,'evenr':'ch("../CTRL_DETAIL/gain")*ch("../CTRL_DETAIL/enabled")','eveng':.2,'evenb':.4,'oddr':0,'oddg':.4,'oddb':.1})
o=tab_create(d,'null','OUT_COLOR',inputs=[pattern])
s=tab_create(g,'xform','detail_surface',inputs=['coordinates'],parms={'tx':1.8})
m=tab_create(g,'coppreviewmaterial','detail_material',inputs=[s],parms={'basecolorsource':'cop','basecolorpath':o.path()})
assembly=tab_create(g,'merge','assembly',inputs=['base_material',m]);connect(assembly,g+'/OUT')
''')
    before=observe()['sha256'];existing_width=hou.parm(C+'/width').eval()
    run('''
g=hou.node('/obj/editable_asset');c=g.node('CTRL');local=g.node('detail_images/CTRL_DETAIL')
create_spare_parms(c,spec=[{'type':'folder','name':'appearance','label':'Appearance','parms':[
 {'type':'float','name':'map_gain','label':'Pattern gain','default':local.evalParm('gain')},
 {'type':'int','name':'map_repeat','label':'Pattern repeat','default':local.evalParm('repeat')},
 {'type':'toggle','name':'map_enabled','label':'Pattern enabled','default':local.evalParm('enabled')}]}])
bindings=[{'source':'map_gain','target':local.parm('gain').path()},{'source':'map_repeat','target':local.parm('repeat').path()}]
plan=bind_controls(c,bindings,dry_run=True);bind_controls(c,bindings,expected_plan=plan['plan_sha256'])
# Toggle is outside bind_controls' float/int target contract; use an explicit
# native reference after checking its actual type, rather than widening that API.
set_parm(local,'enabled',{'expression':'ch("../../CTRL/map_enabled")','language':'hscript'})
members=[n.name() for n in g.findNetworkBox('surface_sources').nodes()]
network_boxes(g,[{'name':'surface_sources','members':members+['detail_images']},
 {'name':'geometry','members':['surface','coordinates','base_material','detail_surface','detail_material','assembly','OUT']}])
layout_nodes(g,mode='handoff',boxes=['controls','geometry','surface_sources'],profile='readable')
network_notes(g,[{'name':'START','text':'Use CTRL for dimensions and Appearance. base_images and detail_images retain editable image sources; detail_images/CTRL_DETAIL retains technical controls.'}])
present_nodes([{'node':c.path(),'label':'Asset controls','role':'control','description':'Dimensions and common appearance edits'},
 {'node':g.node('base_images').path(),'label':'Base image source','role':'node'},
 {'node':g.node('detail_images').path(),'label':'Pattern implementation','role':'node'},
 {'node':g.node('OUT').path(),'label':'Asset output','role':'output'}])
''')
    assert observe()['sha256']==before,'promoting a literal module control must preserve its current output'
    state=inspect()
    assert state['controls']['width']==existing_width and state['controls']['map_gain']==.63
    assert state['local']['technical_bias']==.125 and state['members']==['base_images','detail_images']
    for local,source in [('gain','map_gain'),('repeat','map_repeat'),('enabled','map_enabled')]:
        assert '../../CTRL/'+source in state['expressions'][local],state
    assert state['references']['enabled']==C+'/map_enabled'
    assert state['consumer']==G+'/detail_images/OUT_COLOR' and state['output_inputs']==['assembly']
    assert state['assembly_inputs']==['base_material','detail_material']
    tested=run(f"__result__=test_cop_controls({C!r},{state['consumer']!r},["
        "{'id':'gain_from_public','values':{'map_gain':.2},'expectations':[{'metric':'mean','channel':0,'delta':[-.3,-.1]}]},"
        "{'id':'repeat_from_public','values':{'map_repeat':5},'expectations':[{'metric':'mean_abs_change','channel':0,'delta':[.01,.7]}]},"
        "{'id':'toggle_from_public','values':{'map_enabled':0},'expectations':[{'metric':'mean_abs_change','channel':0,'delta':[.1,.7]}]}])")
    assert tested['ok'] and tested['restored'] and observe()['sha256']==before,tested
    saved_layer=observe()
    saved_pixels=pixel_hash()
    run(f"scene_save(expected_path={str(hip)!r})")
    sys.path.insert(0,str(ROOT/'tools'))
    from houdini_test_environment import isolated_environment,launch_directory
    exe=Path(hou.text.expandString('$HFS'))/'bin/hython.exe'
    with tempfile.TemporaryDirectory(prefix='dsh-asset-edit-reopen-') as prefs:
        result=subprocess.run([str(exe),str(Path(__file__).resolve()),'--reopen',str(hip)],cwd=launch_directory(exe),env=isolated_environment(prefs,executable=exe),capture_output=True,text=True,encoding='utf8',errors='replace',timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode==0,(result.stdout,result.stderr)
    reopened=json.loads((hip.parent/'reopen.json').read_text(encoding='utf8'))
    assert reopened['view']==state,{'before':state,'after':reopened['view']}
    assert reopened['pixels']==saved_pixels,'complete COP pixels changed across reopen'
    for field in ('resolution','channels','storage_type','type_info','data_window','display_window','pixel_scale','pixel_aspect','image_to_world','projection','projection_transform','border','frame','runtime_version'):
        assert reopened['layer'][field]==saved_layer[field],field
    print('asset-level numeric/toggle controls, existing values, two COP sources, final consumer, grouping and fresh-process reopen passed on',hou.applicationVersionString())
