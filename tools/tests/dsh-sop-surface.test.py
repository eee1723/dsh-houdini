"""Opt-in H21/H22 SOP surface GUI/preview and fresh-process reopen regression.

python tools/tests/dsh-sop-surface.test.py --houdini D:/houdini/bin/houdini.exe --output <new external directory>
Owns isolated preferences/processes; never connects to a live user HIP or model.
"""
from pathlib import Path
import argparse,json,os,subprocess,sys,tempfile,traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from houdini_test_environment import isolated_environment,launch_directory,reexec_unpacked_test_cli

def gui_run():
    import hou
    from hutil.Qt import QtGui
    sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
    import dsh_bridge as bridge
    out=Path(os.environ['DSH_SURFACE_FIXTURE_OUT'])
    mode=os.environ['DSH_SURFACE_FIXTURE_MODE']
    receipts=[]
    def call(code):
        reply=bridge.run_code(code,owner_session='surface-fixture',owner_call=str(len(receipts)+1))
        receipts.append(reply)
        (out/(mode+'-receipts.json')).write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8')
        assert reply['ok'],reply.get('error')
        return reply.get('result')
    def colors(filename):
        image=QtGui.QImage(str(filename));assert not image.isNull(),filename
        counts={'red':0,'blue':0,'green':0}
        for y in range(0,image.height(),2):
            for x in range(0,image.width(),2):
                c=image.pixelColor(x,y);r,g,b=c.red(),c.green(),c.blue()
                counts['red']+=r>g*1.5 and r>b*1.5 and r>45
                counts['blue']+=b>r*1.5 and b>g*1.2 and b>45
                counts['green']+=g>r*1.5 and g>b*1.5 and g>45
        return counts
    def observe(label,node,preview=True):
        if preview:
            result=call(f"__result__=render_view({node!r},direction='front',width=640,height=400,picture={label+'.png'!r})")
            assert result['ok'] and result['user_state_restored'],result
            image=result['output']
        else:
            result=call(f"__result__=viewport_screenshot({label+'.png'!r},frame_target={node!r},textures=True)")
            assert result['ok'] and result['fresh'] and result['user_state_restored'],result
            image=result['path']
        return {'image':image,'pixels':colors(image),'capture':result}
    try:
        report={'version':hou.applicationVersionString(),'mode':mode,'gui':hou.isUIAvailable(),'semantic_status':'unverified'}
        hip=out/'surface.hip'
        if mode=='build':
            call(f"__result__=scene_save_as({str(hip)!r},expected_current_path={hou.hipFile.path()!r},reason='isolated SOP surface fixture')")
            call('''
g=tab_create('/obj','geo','surface')
b=tab_create(g,'box','constant_shape')
c=tab_create(g,'copnet','textures')
color=tab_create(c,'layer','base_color',parms={'setres':1,'resx':4,'resy':4,'signature':'f3','f3':(.03,.7,.06)})
color_out=tab_create(c,'null','OUT_color',inputs=[color])
m=tab_create(g,'coppreviewmaterial','appearance',inputs=[b],parms={'basecolorsource':'cop','basecolorpath':color_out.path(),'roughnesssource':'constant','constantspecularroughness':.65,'tintwithcdswitch':0})
sop_set_output(m)
__result__={'uv':m.geometry().findVertexAttrib('uv') is not None or m.geometry().findPointAttrib('uv') is not None,'material':m.geometry().findPrimAttrib('shop_materialpath') is not None}
''')
            yield
            report['constant']=observe('constant','/obj/surface/appearance')
            assert report['constant']['pixels']['green']>200,report['constant']['pixels']
            call('''
g=hou.node('/obj/surface')
p=tab_create(g,'grid','shape',parms={'orient':'xy','size':(2,1),'rows':21,'cols':41})
uv=tab_create(g,'attribwrangle','coordinates',inputs=[p],parms={'class':'vertex','snippet':'v@uv=set(@P.x/2+0.5,@P.y+0.5,0);'})
s=tab_create(g,'xform','dimensions',inputs=[uv])
c=hou.node('/obj/surface/textures')
r=tab_create(c,'layer','resolution',parms={'setres':1,'resx':128,'resy':64,'f1':1})
t=tab_create(c,'checkerboard','pattern',inputs=[r],parms={'signature':'f3','cols':5,'rows':3,'evenr':.8,'eveng':.04,'evenb':.02,'oddr':.02,'oddg':.09,'oddb':.8,'tx':.13,'ty':.27})
m=hou.node('/obj/surface/appearance')
connect(s,m,0);connect(t,c.node('OUT_color'),0)
sop_set_output(m)
__result__=verify_network(g,output=m)
''')
            yield
            report['cop']=observe('cop','/obj/surface/appearance')
            report['cop_viewport']=observe('cop-viewport','/obj/surface/appearance',preview=False)
            (out/'cop-observation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
            assert min(report['cop']['pixels'][x] for x in ('red','blue'))>200,report['cop']['pixels']
            call('''
r=tab_create('/obj/surface/textures','rop_image','export_pattern',parms={'coppath':'/obj/surface/textures/pattern','copoutput':'$HIP/dsh-texture/pattern.exr','colorconversion':'raw','size1':'float32','raw1':1,'useport1':1,'port1':0})
__result__=render_frame(r)
''')
            call("set_parms('/obj/surface/appearance',{'basecolorsource':'file','basecolorfile':'$HIP/dsh-texture/pattern.exr'});__result__=verify_network('/obj/surface',output='/obj/surface/appearance')")
            yield
            report['file']=observe('file','/obj/surface/appearance')
            assert min(report['file']['pixels'][x] for x in ('red','blue'))>200,report['file']['pixels']
            before=hou.node('/obj/surface/appearance').geometry()
            uv_before=list(before.vertexFloatAttribValues('uv'))
            call("set_parms('/obj/surface/dimensions',{'sx':1.5});__result__=verify_network('/obj/surface',output='/obj/surface/appearance')")
            yield
            after=hou.node('/obj/surface/appearance').geometry()
            assert list(after.vertexFloatAttribValues('uv'))==uv_before
            assert abs(after.boundingBox().sizevec()[0]-3)<1e-5
            report['resized']=observe('resized','/obj/surface/appearance')
            assert min(report['resized']['pixels'][x] for x in ('red','blue'))>200,report['resized']['pixels']
            call(f"__result__=scene_save(expected_path={str(hip)!r})")
        else:
            # Loading is limited to this runner's newly authored fixture in a new process.
            hou.hipFile.load(str(hip),suppress_save_prompt=True)
            yield
        node=hou.node('/obj/surface/appearance')
        assert node.type().name()=='coppreviewmaterial'
        assert node.evalParm('basecolorfile')==str(out/'dsh-texture/pattern.exr').replace('\\','/')
        assert len(node.geometry().prims())>0 and not node.errors(),node.errors()
        material=node.geometry().findPrimAttrib('shop_materialpath')
        assert material,'actual SOP material assignment missing'
        report['material_paths']=sorted(set(node.geometry().primStringAttribValues('shop_materialpath')))
        assert all(hou.node(p) is not None for p in report['material_paths']),report['material_paths']
        report['viewport']=observe(mode+'-viewport',node.path(),preview=False)
        assert min(report['viewport']['pixels'][x] for x in ('red','blue'))>100,report['viewport']['pixels']
        report['scope']='constant COP/pattern/file on one SOP material, vertex UV across dimension edit, proxy preview, viewport and saved dependency reopen; not autonomous model quality or Karma'
        (out/(mode+'-result.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        hou.exit(exit_code=0,suppress_save_prompt=True)
    except Exception:
        (out/(mode+'-error.txt')).write_text(traceback.format_exc(),encoding='utf8')
        hou.exit(exit_code=1,suppress_save_prompt=True)

def main():
    reexec_unpacked_test_cli()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--houdini',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--timeout',type=int,default=240)
    args=parser.parse_args()
    exe=args.houdini.resolve(strict=True);out=args.output.resolve()
    if out.is_relative_to(ROOT) or out.exists():parser.error('output must be a new external directory')
    out.mkdir(parents=True)
    hython=exe.with_name('hython.exe')
    with tempfile.TemporaryDirectory(prefix='dsh-surface-version-') as temp:
        r=subprocess.run([str(hython),'-c',"import hou; print('VERSION='+hou.applicationVersionString())"],env=isolated_environment(temp,executable=hython),cwd=launch_directory(hython),capture_output=True,text=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert r.returncode==0,(r.stdout,r.stderr)
    import re
    version=re.search(r'VERSION=((21|22)\.0)\.\d+',r.stdout)
    assert version,r.stdout
    for mode in ('build','reopen'):
        with tempfile.TemporaryDirectory(prefix='dsh-sop-surface-') as temp:
            env=isolated_environment(temp,executable=exe,gui=True)
            pref=Path(env['HOUDINI_USER_PREF_DIR'].replace('__HVER__',version[1]))
            hook=pref/('python3.11libs' if version[2]=='21' else 'python3.13libs')/'uiready.py'
            hook.parent.mkdir(parents=True)
            hook.write_text(f'import runpy\nrunpy.run_path({str(Path(__file__).resolve())!r})\n',encoding='utf8')
            env.update(DSH_SURFACE_FIXTURE_OUT=str(out),DSH_SURFACE_FIXTURE_MODE=mode)
            startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
            with (out/(mode+'-process.log')).open('w',encoding='utf8') as log:
                p=subprocess.Popen([str(exe),'-foreground','-geometry=1000x750+12000+12000'],env=env,cwd=launch_directory(exe),stdout=log,stderr=log,startupinfo=startup)
                try:p.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:p.kill();p.wait(timeout=20);raise
            assert p.returncode==0,(mode,p.returncode,(out/(mode+'-error.txt')).read_text(encoding='utf8') if (out/(mode+'-error.txt')).exists() else 'see process.log')
            assert (out/(mode+'-result.json')).is_file()
            print(mode,version[0],'passed',out,flush=True)

if os.environ.get('DSH_SURFACE_FIXTURE_OUT'):
    import hdefereval
    from hutil.Qt import QtCore
    steps=gui_run()
    def advance():
        try:next(steps)
        except StopIteration:return
        # Real tool requests arrive on distinct UI turns. Return from Python
        # so Houdini can process native shader notifications before capturing.
        QtCore.QTimer.singleShot(50,lambda:hdefereval.executeDeferred(advance))
    hdefereval.executeDeferred(advance)
elif __name__=='__main__':main()
