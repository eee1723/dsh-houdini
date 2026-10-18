"""Opt-in isolated SOP texture integration: layered COP, optional generated file,
shared channels, physical UV scale, proxy/viewport and fresh-process reopen.
No live session, paid generation, product target or artistic pass threshold.
"""
from pathlib import Path
import argparse,json,os,shutil,subprocess,sys,tempfile,traceback
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from houdini_test_environment import isolated_environment,launch_directory,reexec_unpacked_test_cli

def gui_run():
    import hou
    from hutil.Qt import QtGui
    sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
    import dsh_bridge as bridge
    out=Path(os.environ['DSH_TEXTURE_FIXTURE_OUT']);mode=os.environ['DSH_TEXTURE_FIXTURE_MODE']
    receipts=[];report={'version':hou.applicationVersionString(),'mode':mode,'semantic_status':'unverified'}
    def call(code):
        r=bridge.run_code(code,owner_session='surface-texture-fixture',owner_call=str(len(receipts)))
        receipts.append(r);(out/(mode+'-receipts.json')).write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8')
        assert r['ok'],r.get('error');return r.get('result')
    def capture(label,node='/obj/sample/appearance'):
        r=call(f"__result__=render_view({node!r},direction=(.8,.4,1.4),width=900,height=900,picture={label+'.png'!r})")
        assert r['ok'] and r['user_state_restored'],r
        report[label]=r['output'];return r['output']
    def changed(left,right):
        a=QtGui.QImage(left);b=QtGui.QImage(right)
        assert not a.isNull() and a.size()==b.size()
        changes=sum(a.pixel(x,y)!=b.pixel(x,y) for y in range(0,a.height(),4) for x in range(0,a.width(),4))
        assert changes>100,{'left':left,'right':right,'changed_sample_pixels':changes}
        return changes
    try:
        hip=out/'textures.hip'
        if mode=='build':
            call(f"__result__=scene_save_as({str(hip)!r},expected_current_path={hou.hipFile.path()!r},reason='isolated texture integration fixture')")
            call('''
g=tab_create('/obj','geo','sample');ctrl=tab_create(g,'null','CTRL')
create_spare_parms(ctrl,spec=[{'type':'int','name':'repeats','label':'Circumference tile count','default':3},{'type':'int','name':'motifs','label':'Motifs per tile','default':4}])
grid=tab_create(g,'grid','surface_domain',parms={'orient':'xy','size':(1,1),'rows':17,'cols':129})
uv=tab_create(g,'attribwrangle','surface_coordinates',inputs=[grid],parms={'class':'vertex','snippet':'float u=@P.x+.5; float v=@P.y+.5; v@uv=set(u*ch("../CTRL/repeats"),v*.3/.2,0);'})
shape=tab_create(g,'attribwrangle','cylindrical_surface',inputs=[uv],parms={'snippet':'float a=(@P.x+.5)*2*M_PI; float r=ch("../CTRL/repeats")*.2/(2*M_PI); @P=set(r*cos(a),(@P.y+.5)*.3,r*sin(a));'})
c=tab_create(g,'copnet','textures')
domain=tab_create(c,'layer','tile_domain',parms={'signature':'f1','setres':1,'res':(512,512),'setborder':1,'border':'wrap'})
pattern=tab_create(c,'wrangle','shared_pattern',inputs=[domain],parms={'aovs':3})
set_parms(pattern,{'type1':'vector','layer1':'base','type2':'float','layer2':'rough','type3':'float','layer3':'height','vexsnippet':
'vector2 uv=set(@P.x,@P.y)*.5+.5; vector2 q=frac(uv*ch("../../CTRL/motifs"))-.5; float r=length(q); float a=atan2(q.y,q.x); float contour=.29+.065*cos(a*6); float edge=abs(r-contour); float fill=1-smooth(contour-.008,contour+.008,r); float trim=1-smooth(.012,.024,edge); float lines=pow(abs(sin(uv.x*2*M_PI*32)*sin(uv.y*2*M_PI*32)),8); v@base=lerp(set(.68,.63,.50),set(.025,.09,.18),fill); v@base=lerp(v@base,set(.6,.30,.055),trim); f@rough=lerp(.78,.28,trim); f@height=.05*fill+.018*trim+.004*lines;'})
color=tab_create(c,'null','OUT_BASE');connect(pattern,color,output=0)
rough=tab_create(c,'null','OUT_ROUGHNESS');connect(pattern,rough,output=1)
height=tab_create(c,'null','OUT_HEIGHT');connect(pattern,height,output=2)
normal=tab_create(c,'heighttonormal','height_normals',inputs=[height],parms={'normaltype':'offset','scale':.3})
nout=tab_create(c,'null','OUT_NORMAL',inputs=[normal])
m=tab_create(g,'coppreviewmaterial','appearance',inputs=[shape],parms={'basecolorsource':'cop','basecolorpath':color.path(),'roughnesssource':'cop','roughnesspath':rough.path(),'normalssource':'cop','normalspath':nout.path(),'normalmap_scale':.3,'tintwithcdswitch':0})
sop_set_output(m)
__result__={name:cop_layer_stats(c.path()+'/'+name) for name in ['OUT_BASE','OUT_ROUGHNESS','OUT_HEIGHT','OUT_NORMAL']}
''')
            yield
            original=capture('procedural')
            call("set_parm('/obj/sample/appearance','normalmap_scale',0)")
            yield
            flat=capture('normal_off');report['normal_response_pixels']=changed(original,flat)
            call("set_parms('/obj/sample/appearance',{'normalmap_scale':.3,'roughnesssource':'constant','constantspecularroughness':.9})")
            yield
            flat=capture('constant_roughness');report['roughness_response_pixels']=changed(original,flat)
            call("set_parms('/obj/sample/appearance',{'normalmap_scale':.3,'roughnesssource':'cop'}); set_parm('/obj/sample/CTRL','motifs',5)")
            yield
            varied=capture('pattern_edit');report['pattern_response_pixels']=changed(original,varied)
            call("set_parms('/obj/sample/CTRL',{'motifs':4,'repeats':4})")
            yield
            capture('physical_scale_edit')
            report['uv']=call('''
import math
n=hou.node('/obj/sample/appearance');g=n.geometry();ratios=[];spans=[]
for prim in g.prims():
 vs=list(prim.vertices());spans.append(max(v.attribValue('uv')[0] for v in vs)-min(v.attribValue('uv')[0] for v in vs))
 for a,b in zip(vs,vs[1:]+vs[:1]):
  u=abs(a.attribValue('uv')[0]-b.attribValue('uv')[0]);d=a.point().position().distanceTo(b.point().position())
  if u>1e-6:ratios.append(d/(u*.2))
__result__={'u_spans':[min(spans),max(spans)],'chord_to_uv_distance':[min(ratios),max(ratios)],'vertex_uv':g.findVertexAttrib('uv') is not None}
''')
            assert report['uv']['vertex_uv'] and report['uv']['u_spans'][1]<.04,report['uv']
            assert .999<report['uv']['chord_to_uv_distance'][0]<=report['uv']['chord_to_uv_distance'][1]<1.001
            call('''
c='/obj/sample/textures'
for label in ['BASE','ROUGHNESS','NORMAL']:
 r=tab_create(c,'rop_image','export_'+label,parms={'coppath':c+'/OUT_'+label,'copoutput':'$HIP/dsh-artifacts/textures/'+label.lower()+'.exr','colorconversion':'raw','size1':'float32','raw1':1,'useport1':1,'port1':0})
 render_frame(r)
__result__=True
''')
            has_image=(out/'dsh-artifacts/textures/generated.png').exists()
            image_path='$HIP/dsh-artifacts/textures/generated.png' if has_image else '$HIP/dsh-artifacts/textures/base.exr'
            report['external_image_supplied']=has_image
            call(f'''
c='/obj/sample/textures'
f=tab_create(c,'file','image_source',parms={{'filename':{image_path!r},'colorspace':{'ocio' if has_image else 'raw'!r},'aovs':1,'border':'wrap'}})
set_parm(f,'type1','vector')
connect(f,c+'/OUT_BASE')
set_parms('/obj/sample/appearance',{{'normalssource':'constant','roughnesssource':'constant','constantspecularroughness':.6}})
__result__=cop_layer_stats(c+'/OUT_BASE')
''')
            yield
            capture('file_texture')
            call('''
g='/obj/sample';p=tab_create(g,'grid','repeat_plane',parms={'orient':'xy','size':(.4,.4),'rows':3,'cols':3})
uv=tab_create(g,'attribwrangle','repeat_coordinates',inputs=[p],parms={'class':'vertex','snippet':'v@uv=set(@P.x/.2+1,@P.y/.2+1,0);'})
m=tab_create(g,'coppreviewmaterial','repeat_preview',inputs=[uv],parms={'basecolorsource':'cop','basecolorpath':g+'/textures/OUT_BASE','constantspecularroughness':.8,'tintwithcdswitch':0})
__result__=render_view(m,direction='front',width=1000,height=1000,picture='repeat_check.png')
''')
            report['repeat_check']=receipts[-1]['result']['output']
            call('''
c='/obj/sample/textures'; blend=tab_create(c,'blend','image_with_pattern',parms={'signature':'rgb','mode':'blend','mask':.22})
connect(c+'/image_source',blend,0);connect(c+'/shared_pattern',blend,1,output=0);connect(blend,c+'/OUT_BASE')
__result__=cop_layer_stats(c+'/OUT_BASE')
''')
            yield
            capture('hybrid_texture')
            call(f"scene_save(expected_path={str(hip)!r}); __result__=True")
        else:
            hou.hipFile.load(str(hip),suppress_save_prompt=True)
            yield
        report['reopen_layer']=call("__result__=cop_layer_stats('/obj/sample/textures/OUT_BASE')")
        n=hou.node('/obj/sample/appearance');assert not n.errors() and len(n.geometry().prims())>0
        assert n.geometry().findPrimAttrib('shop_materialpath') is not None
        capture(mode+'_final')
        report['viewport']=call("__result__=viewport_screenshot('texture-viewport.png',frame_target='/obj/sample/appearance',textures=True)")
        assert report['viewport']['ok'] and report['viewport']['user_state_restored']
        report['scope']='layered COP channels, editable pattern, cylindrical vertex UV physical scale, file and hybrid sources, viewport and dependency reopen; pixels are transport/response evidence, artistic quality requires inspection'
        (out/(mode+'-result.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        hou.exit(exit_code=0,suppress_save_prompt=True)
    except Exception:
        (out/(mode+'-error.txt')).write_text(traceback.format_exc(),encoding='utf8')
        hou.exit(exit_code=1,suppress_save_prompt=True)

def main():
    reexec_unpacked_test_cli()
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--houdini',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--texture',type=Path);p.add_argument('--timeout',type=int,default=300);args=p.parse_args()
    exe=args.houdini.resolve(strict=True);out=args.output.resolve()
    if out.exists() or out.is_relative_to(ROOT):p.error('output must be a new external directory')
    out.mkdir(parents=True)
    if args.texture:
        (out/'dsh-artifacts/textures').mkdir(parents=True);shutil.copy2(args.texture.resolve(strict=True),out/'dsh-artifacts/textures/generated.png')
    with tempfile.TemporaryDirectory(prefix='dsh-texture-version-') as temp:
        h=exe.with_name('hython.exe');r=subprocess.run([str(h),'-c',"import hou;print('VERSION='+hou.applicationVersionString())"],cwd=launch_directory(h),env=isolated_environment(temp,executable=h),capture_output=True,text=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    import re
    version=re.search(r'VERSION=((21|22)\.0)\.\d+',r.stdout);assert r.returncode==0 and version,(r.stdout,r.stderr)
    for mode in ('build','reopen'):
        with tempfile.TemporaryDirectory(prefix='dsh-texture-gui-') as temp:
            env=isolated_environment(temp,executable=exe,gui=True)
            pref=Path(env['HOUDINI_USER_PREF_DIR'].replace('__HVER__',version[1]));hook=pref/('python3.11libs' if version[2]=='21' else 'python3.13libs')/'uiready.py';hook.parent.mkdir(parents=True)
            hook.write_text(f'import runpy\nrunpy.run_path({str(Path(__file__).resolve())!r})\n',encoding='utf8')
            env.update(DSH_TEXTURE_FIXTURE_OUT=str(out),DSH_TEXTURE_FIXTURE_MODE=mode)
            startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
            with (out/(mode+'-process.log')).open('w',encoding='utf8') as log:
                child=subprocess.Popen([str(exe),'-foreground','-geometry=1000x750+12000+12000'],env=env,cwd=launch_directory(exe),stdout=log,stderr=log,startupinfo=startup)
                import time
                deadline=time.monotonic()+args.timeout
                while child.poll() is None:
                    if (out/(mode+'-error.txt')).exists() or time.monotonic()>deadline:
                        child.kill();child.wait(timeout=20);break
                    try:child.wait(timeout=.5)
                    except subprocess.TimeoutExpired:pass
            assert child.returncode==0,(mode,child.returncode,(out/(mode+'-error.txt')).read_text(encoding='utf8') if (out/(mode+'-error.txt')).exists() else 'see process.log')
            assert (out/(mode+'-result.json')).is_file();print(mode,version[0],'passed',out,flush=True)
    a=json.loads((out/'build-result.json').read_text(encoding='utf8'));b=json.loads((out/'reopen-result.json').read_text(encoding='utf8'))
    assert a['reopen_layer']['sha256']==b['reopen_layer']['sha256'],'same-version COP output survives independent reopen'

if os.environ.get('DSH_TEXTURE_FIXTURE_OUT'):
    import hdefereval
    from hutil.Qt import QtCore
    steps=gui_run()
    def advance():
        try:next(steps)
        except StopIteration:return
        QtCore.QTimer.singleShot(50,lambda:hdefereval.executeDeferred(advance))
    hdefereval.executeDeferred(advance)
elif __name__=='__main__':main()
