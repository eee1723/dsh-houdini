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
set_parms(settings,{'camera':'/framing_camera','pathtracedsamples':2,'engine':'cpu'})
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
print('Real isolated Karma CPU 64x64 image and byte integrity passed on '+hou.applicationVersionString(), flush=True)
