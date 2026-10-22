"""Opt-in real Karma CPU image through the isolated driver; no live GUI or model."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as bridge
spec = importlib.util.spec_from_file_location('isolated_check', ROOT / 'tools/isolated-houdini-check.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
root = Path(tempfile.mkdtemp(prefix='dsh-isolated-karma-'))
print('ISOLATED_RENDER_FIXTURE='+str(root), flush=True)
product_code = '''from pxr import UsdRender,Gf
s=hou.pwd().editableStage()
for p in s.Traverse():
    if p.GetTypeName() == 'RenderProduct':
        UsdRender.Product(p).CreateResolutionAttr(Gf.Vec2i(64,64))
'''
builder = '''g=tab_create('/obj','geo',name='framing_asset')
n=tab_create(g,'box',name='OUT')
c=tab_create('/obj','cam',name='framing_camera')
camera_fit(c,n,width=64,height=64)
imp=tab_create('/stage','sceneimport',name='scene')
set_parms(imp,{'objects':g.path()+' '+c.path(),'forceobjects':g.path()+' '+c.path()})
tab_apply('/stage','lop_karma_setup')
settings=hou.node('/stage/karmarendersettings')
rop=hou.node('/stage/usdrender_rop1')
connect(imp,settings)
# The CPU default is Automatic/Variance, where pathtracedsamples is inactive.
# Set the native settings resolution as well as the downstream products so
# checkpoint/delegate buffers use the same small image dimensions.
set_parms(settings,{'camera':'/framing_camera','engine':'cpu','convergence_mode':'Path Traced',
                    'pathtracedsamples':2,'res_mode':'autoheight','resolutionx':64})
set_parms(rop,{'husk_enable_headlight':1,'husk_headlight':'distant'})
product=tab_create('/stage','pythonscript',name='product')
connect(settings,product)
connect(product,rop)
set_parms(rop,{'loppath':product.path()})
'''
builder += 'set_parms(product,{"python":' + repr(product_code) + '})\n'
(root/'build.py').write_text(builder, encoding='utf-8')
manifest = {'script':'build.py', 'checks':[{'id':'cpu','kind':'render','node':'/stage/usdrender_rop1','frame':1,'file':'image.png'}]}
(root/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
result = runner.check(root/'manifest.json', Path(hou.text.expandString('$HFS'))/'bin/hython.exe',
                      root/'run', trusted=True, timeout=120)
assert result['ok'], result
pixels = h.render_check(str(root/'run/artifacts/cpu/image.png'))
assert pixels['width']==64 and pixels['height']==64 and pixels['nonblack_pct']>1, pixels
runner.write_json(root/'pixels.json', pixels)

# Exercise the native KarmaSetup's inherited RenderProducts without replacing
# outputimage. This process owns only a new temporary HIP; the first render
# above continues to cover the explicit-picture isolated-driver consumer.
native_hip=root/'inherited-native.hip'
native_code=(f"scene_save_as(path={native_hip.as_posix()!r},expected_current_path=scene_info()['hip_path'],reason='isolated native render fixture')\n"
             +builder
             +"set_parms(settings,{'outputcheckpoint':1,'savefrequency':60})\n"
              "set_parms(rop,{'outputimage':''})\n"
              "__result__=render_frame(rop,frame=3,timeout=110)\n")
native=bridge.run_code(native_code,owner_session='native-inherited-render',owner_call='karma-products')
runner.write_json(root/'native-execution.json',native)
assert native['ok'] and native['result']['fresh'] and not native['result']['errors'],native
rendered=native['result']
assert len(rendered['outputs'])==1 and rendered['output']==rendered['outputs'][0]['output'],rendered
assert Path(rendered['output']).parent==root/'dsh-artifacts/renders/inherited-native',rendered
assert Path(rendered['output']).name.endswith('.0003.exr'),rendered
assert any(row['product_type']=='karma:checkpoint' and row['status']=='unverified'
           for row in rendered['inherited_products']['unverified_products']),rendered
assert hou.node('/stage/usdrender_rop1').evalParm('outputimage')==''
assert hou.frame()==1
from pxr import Usd,UsdRender
native_stage=hou.node('/stage/product').stage()
native_settings=hou.node('/stage/karmarendersettings')
settings_prim=native_stage.GetPrimAtPath(rendered['inherited_products']['settings'])
settings_resolution=list(UsdRender.Settings(settings_prim).GetResolutionAttr().Get(Usd.TimeCode(3)))
assert settings_resolution==[64,64],settings_resolution
assert native_settings.evalParm('engine')=='cpu'
assert native_settings.evalParm('convergence_mode')=='Path Traced'
assert native_settings.evalParm('pathtracedsamples')==2
settings_evidence={'resolution':settings_resolution,
    'parameters':h.read_parms(native_settings,names=['engine','convergence_mode','pathtracedsamples','res_mode','resolution']),
    'sampling_attributes':{attr.GetName():str(attr.Get(Usd.TimeCode(3))) for attr in settings_prim.GetAttributes()
                           if 'sample' in attr.GetName().lower() or 'convergence' in attr.GetName().lower()}}
runner.write_json(root/'native-settings.json',settings_evidence)
import OpenImageIO as oiio
import numpy as np
native_image=oiio.ImageBuf(rendered['output'])
native_spec=native_image.spec()
native_array=native_image.get_pixels(oiio.FLOAT)
assert native_array is not None and np.isfinite(native_array).all(),native_image.geterror()
rgb=native_array[:,:,[native_spec.channelnames.index(name) for name in ('R','G','B')]]
native_pixels={'width':native_spec.width,'height':native_spec.height,'max_rgb':float(rgb.max()),
               'scope':'Raw linear EXR dimensions, finite RGB and nonzero content only; no display transform or visual quality claim'}
assert native_pixels['width']==64 and native_pixels['height']==64 and native_pixels['max_rgb']>0,native_pixels
runner.write_json(root/'native-pixels.json',native_pixels)
print('Real isolated Karma CPU explicit and inherited 64x64 images passed on '+hou.applicationVersionString(), flush=True)
