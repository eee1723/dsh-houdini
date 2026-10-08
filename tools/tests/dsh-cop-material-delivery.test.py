"""Opt-in native COP -> disk textures -> MaterialX/Karma -> fresh-process reopen.

Run in isolated hython with --directory <new external directory> --mode build,
then in another isolated same-version hython with the same directory and mode
reopen. No model, GUI, user HIP, global preferences or external source images.
"""
from pathlib import Path
import argparse,json,sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge
import dsh_hou_helpers as h

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--directory',required=True,type=Path)
parser.add_argument('--mode',required=True,choices=('build','reopen'))
args=parser.parse_args()
directory=args.directory.resolve()
if directory.is_relative_to(ROOT):raise ValueError('delivery fixture must be outside the plugin')
hip=directory/'cop-material.hip'
owner='cop-material-delivery'
receipts=[]

def call(code):
    reply=bridge.run_code(code,owner_session=owner,owner_call=str(len(receipts)+1))
    receipts.append(reply)
    (directory/(args.mode+'-receipts.json')).write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf8')
    assert reply['ok'],reply.get('error')
    return reply.get('result')

def pixels(path):
    decoded=h._read_pixels_qt(str(path));assert decoded is not None,path
    width,height,rows=decoded
    image=rows.image
    raw=np.frombuffer(image.constBits(),dtype=np.uint8).reshape(height,image.bytesPerLine())
    return raw[:,:width*3].reshape(height,width,3).copy()

if args.mode=='build':
    directory.mkdir(exist_ok=False)
    call(f"__result__=scene_save_as({str(hip)!r},expected_current_path={hou.hipFile.path()!r},reason='new isolated COP material project')")
    call('''
g=tab_create('/obj','geo','calibration')
surface=tab_create(g,'grid','surface',parms={'orient':'xy','size':(2,1),'rows':41,'cols':81})
uv=tab_create(g,'attribwrangle','texture_coordinates',inputs=[surface],parms={'class':'point','snippet':'v@uv=set(@P.x/2+0.5,@P.y+0.5,0); @P.z=-0.65*@P.x*@P.x;'})
out=tab_create(g,'null','OUT',inputs=[uv]);sop_set_output(out)
decal=tab_create('/obj','geo','decal')
decal_surface=tab_create(decal,'object_merge','surface',parms={'objpath1':out.path()})
decal_lift=tab_create(decal,'xform','lift',inputs=[decal_surface],parms={'tz':.003})
sop_set_output(decal_lift)
cam=tab_create('/obj','cam','calibration_camera',parms={'projection':'ortho'})
camera_fit(cam,out,direction='front',width=512,height=320,coverage=.82)
c=tab_create(g,'copnet','textures')
reference=tab_create(c,'layer','resolution',parms={'setres':1,'resx':256,'resy':128,'f1':1})
color=tab_create(c,'checkerboard','base_color',inputs=[reference],parms={'signature':'f3','cols':5,'rows':3,'evenr':.8,'eveng':.06,'evenb':.025,'oddr':.04,'oddg':.5,'oddb':.7,'tx':.13,'ty':.27})
rough=tab_create(c,'checkerboard','roughness',inputs=[reference],parms={'signature':'f1','cols':5,'rows':3,'evenr':.12,'oddr':.8,'tx':.13,'ty':.27})
alpha=tab_create(c,'ramp','decal_alpha',inputs=[reference],parms={'signature':'f1','rampType':'concentric','centerx':-.4,'centery':.15})
set_parms(alpha,{'rampmono':hou.Ramp((hou.rampBasis.Linear,)*6,(0,.18,.23,.38,.43,1),(0,0,1,1,0,0))})
__result__={'color':cop_layer_stats(color),'roughness':cop_layer_stats(rough)}
''')
    for name in ('base_color','roughness','decal_alpha'):
        written=call(f"""
r=tab_create('/obj/calibration/textures','rop_image','export_{name}')
set_parms(r,{{'coppath':'/obj/calibration/textures/{name}','copoutput':'$HIP/dsh-texture/{name}.exr','colorconversion':'raw','size1':'float32','raw1':1,'useport1':1,'port1':0}})
__result__=render_frame(r)
""")
        assert written['fresh'] and not written['errors'],written
        decoded=call(f"""
f=tab_create('/obj/calibration/textures','file','read_{name}')
set_parms(f,{{'filename':'$HIP/dsh-texture/{name}.exr','colorspace':'raw','aovs':1}})
set_parms(f,{{'aov1':'C','type1':{'"vector"' if name=='base_color' else '"float"'},'precision1':'file','raw1':1}})
__result__=cop_layer_stats(f)
""")
        assert decoded['resolution']==[256,128] and decoded['storage_type']=='Float32',decoded
        assert decoded['channels']==(3 if name=='base_color' else 1),decoded
        assert decoded['statistics'][0]['mean_abs_gradient_u']>0 and decoded['statistics'][0]['mean_abs_gradient_v']>0,decoded
    call(r'''
imp=tab_create('/stage','sceneimport','scene',parms={'objects':'/obj/calibration /obj/decal /obj/calibration_camera','forceobjects':'/obj/calibration /obj/decal /obj/calibration_camera'})
mat=tab_create('/stage','materiallibrary','materials',inputs=[imp])
tab_apply(mat,'vop_karmamtlxsubnet')
builder=mat.node('karmamaterial')
surface=builder.node('mtlxstandard_surface')
color=tab_create(builder,'mtlximage','base_color_texture',parms={'signature':'color3','file':'$HIP/dsh-texture/base_color.exr','filecolorspace':'Raw'})
rough=tab_create(builder,'mtlximage','roughness_texture',parms={'signature':'default','file':'$HIP/dsh-texture/roughness.exr','filecolorspace':'Raw'})
connect(color,surface,'base_color');connect(rough,surface,'specular_roughness')
set_parms(mat,{'matnode1':'karmamaterial','matpath1':'/materials/calibration','assign1':True,'geopath1':'/calibration'})
tab_apply(mat,'vop_karmamtlxsubnet')
decal_builder=mat.node('karmamaterial1')
decal_shader=decal_builder.node('mtlxstandard_surface')
decal_alpha=tab_create(decal_builder,'mtlximage','decal_alpha_texture',parms={'signature':'color3','file':'$HIP/dsh-texture/decal_alpha.exr','filecolorspace':'Raw'})
connect(decal_alpha,decal_shader,'opacity')
set_parms(decal_shader,{'base_color':(1,1,1),'specular_roughness':.4,'emission':.3,'emission_color':(1,1,1)})
set_parms(mat,{'materials':2})
set_parms(mat,{'matnode2':'karmamaterial1','matpath2':'/materials/decal','assign2':True,'geopath2':'/decal'})
dome=tab_create('/stage','domelight','calibration_dome',inputs=[mat])
tab_apply('/stage','lop_karma_setup')
settings=hou.node('/stage/karmarendersettings');rop=hou.node('/stage/usdrender_rop1')
connect(dome,settings)
set_parms(settings,{'camera':'/calibration_camera','engine':'cpu','pathtracedsamples':16})
set_parms(rop,{'outputimage':'$HIP/dsh-render/material.png'})
product=tab_create('/stage','pythonscript','product',inputs=[settings],parms={'python':"from pxr import UsdRender,UsdLux,UsdGeom,Gf\ns=hou.pwd().editableStage()\nfor p in s.Traverse():\n if p.IsA(UsdRender.Product): UsdRender.Product(p).CreateResolutionAttr(Gf.Vec2i(512,320))\nlight=UsdLux.RectLight.Define(s,'/calibration_key')\nlight.CreateIntensityAttr(8)\nlight.CreateWidthAttr(1.2)\nlight.CreateHeightAttr(.15)\nUsdGeom.Xformable(light).AddTransformOp().Set(UsdGeom.Xformable(s.GetPrimAtPath('/calibration_camera')).ComputeLocalToWorldTransform(0))\n"})
connect(product,rop);set_parms(rop,{'loppath':product.path()})
__result__=usd_stage_summary(product)
''')
else:
    assert hip.is_file(),hip
    hou.hipFile.load(str(hip),suppress_save_prompt=True,ignore_load_warnings=True)

# These are actual authored USD connections/asset paths, not names of upstream
# nodes or a copied dictionary declaring that a material is present.
stage=hou.node('/stage/product').stage()
from pxr import UsdShade,Sdf
material=UsdShade.Material(stage.GetPrimAtPath('/materials/calibration'))
assert material,stage.ExportToString()[:2000]
bound=[]
for prim in stage.Traverse():
    if prim.GetTypeName()=='Mesh':
        applied,_=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        assert str(applied.GetPath()) in ('/materials/calibration','/materials/decal'),prim.GetPath()
        bound.append(str(prim.GetPath()))
assert bound,'no material-bound geometry'
shader_facts=[]
for prim in stage.Traverse():
    if prim.GetTypeName()!='Shader':continue
    shader=UsdShade.Shader(prim)
    shader_facts.append({'path':str(prim.GetPath()),'id':shader.GetIdAttr().Get(),
        'inputs':{str(inp.GetBaseName()):{'value':str(inp.Get()),'color_space':str(inp.GetAttr().GetColorSpace()),
            'connections':[str(p) for p in inp.GetAttr().GetConnections()]} for inp in shader.GetInputs()}})
surface=next(row for row in shader_facts if row['id']=='ND_standard_surface_surfaceshader' and row['path'].startswith('/materials/calibration/'))
assert surface['inputs']['base_color']['connections'] and surface['inputs']['specular_roughness']['connections'],surface
for role,filename,shader_type in [('base_color','base_color.exr','ND_image_color3'),('specular_roughness','roughness.exr','ND_image_float')]:
    connection=surface['inputs'][role]['connections'];assert len(connection)==1,connection
    source=str(Sdf.Path(connection[0]).GetPrimPath())
    reader=next(row for row in shader_facts if row['path']==source)
    assert reader['id']==shader_type and filename in reader['inputs']['file']['value'],(role,reader)
decal_surface=next(row for row in shader_facts if row['id']=='ND_standard_surface_surfaceshader' and row['path'].startswith('/materials/decal/'))
alpha_source=str(Sdf.Path(decal_surface['inputs']['opacity']['connections'][0]).GetPrimPath())
alpha_reader=next(row for row in shader_facts if row['path']==alpha_source)
assert 'decal_alpha.exr' in alpha_reader['inputs']['file']['value'],alpha_reader
light_summary=h.usd_stage_summary('/stage/product')
assert light_summary['counts']['lights']>=1,light_summary

image=directory/'dsh-render'/('material.png' if args.mode=='build' else 'material-reopened.png')
if args.mode=='build':
    rendered=call(f"__result__=render_frame('/stage/usdrender_rop1',picture={str(image)!r},timeout=110)")
    assert rendered['fresh'] and not rendered['errors'],rendered
    # Change only the image driving roughness, rerender in a fresh husk, then
    # restore the authored COP and exported dependency before saving the HIP.
    rough_control=directory/'dsh-render/roughness-control.png'
    call("set_parms('/obj/calibration/textures/roughness',{'evenr':.98,'oddr':.98}); __result__=render_frame('/obj/calibration/textures/export_roughness')")
    call(f"__result__=render_frame('/stage/usdrender_rop1',picture={str(rough_control)!r},timeout=110)")
    rough_difference=np.abs(pixels(image).astype(np.int16)-pixels(rough_control).astype(np.int16))
    assert np.count_nonzero(np.max(rough_difference,axis=2)>5)>200, 'Roughness file change had no visible material effect'
    call("set_parms('/obj/calibration/textures/roughness',{'evenr':.12,'oddr':.8}); __result__=render_frame('/obj/calibration/textures/export_roughness')")
    call(f"__result__=scene_save(expected_path={str(hip)!r})")
else:
    # Invoke the same saved ROP through the public temporary-output/restoration
    # contract; the new process does not claim or modify the authored network.
    rendered=call(f"__result__=render_frame('/stage/usdrender_rop1',picture={str(image)!r},timeout=110)")
    assert rendered['fresh'] and not rendered['errors'],rendered
rgb=pixels(image)
assert rgb.shape==(320,512,3),rgb.shape
red=(rgb[:,:,0]>rgb[:,:,1]*1.5)&(rgb[:,:,0]>rgb[:,:,2]*1.5)&(rgb[:,:,0]>40)
blue=(rgb[:,:,2]>rgb[:,:,0]*1.5)&(rgb[:,:,1]>rgb[:,:,0]*1.5)&(rgb[:,:,2]>40)
white=(rgb.min(axis=2)>180)&((rgb.max(axis=2)-rgb.min(axis=2))<15)
assert red.sum()>1000 and blue.sum()>1000,{'red_pixels':int(red.sum()),'blue_pixels':int(blue.sum())}
assert white.sum()>1000,'The white alpha decal was not visible'
facts={'version':hou.applicationVersionString(),'mode':args.mode,'hip':str(hip),'image':str(image),
    'material_bindings':bound,'shaders':shader_facts,'lights':light_summary['prims']['lights'],
    'red_pixels':int(red.sum()),'blue_pixels':int(blue.sum()),'white_decal_pixels':int(white.sum()),'render':rendered,
    'scope':'same-version native COP data, portable files, actual MaterialX bindings and Karma pixels; not a natural-model task or GUI interaction'}
if args.mode=='reopen':
    previous=pixels(directory/'dsh-render/material.png')
    diff=np.abs(rgb.astype(np.int16)-previous.astype(np.int16))
    facts['reopen_pixel_difference']={'max':int(diff.max()),'mean':float(diff.mean()),'changed_pixels':int(np.any(diff,axis=2).sum())}
    assert diff.max()<=2 and diff.mean()<=.05,facts['reopen_pixel_difference']
else:
    facts['roughness_control']={'image':str(rough_control),'changed_pixels_above_5':int(np.count_nonzero(np.max(rough_difference,axis=2)>5)),
                               'mean_abs_difference':float(rough_difference.mean()),'source_and_export_restored':True}
(directory/(args.mode+'-result.json')).write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf8')
print('COP_MATERIAL_PASS='+json.dumps({'version':facts['version'],'mode':args.mode,'directory':str(directory),'image':str(image)},ensure_ascii=False),flush=True)
