"""Opt-in disposable real Karma smoke. No source HIP, no live bridge, no GUI claim.

Run: hython tools/camera-karma-smoke.py
Images and JSON go to a newly allocated OS temporary directory printed at start.
"""
from pathlib import Path
import json
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h

output=Path(tempfile.mkdtemp(prefix='dsh-camera-karma-'))
print('SMOKE_DIR='+str(output),flush=True)
geo=hou.node('/obj').createNode('geo','framing_asset')
box=geo.createNode('box','OUT');box.parmTuple('size').set((3.023,3.023,3.023))
cam=hou.node('/obj').createNode('cam','framing_camera')
stage=hou.node('/stage')
imp=stage.createNode('sceneimport','scene')
imp.parm('objects').set(geo.path()+' '+cam.path())
imp.parm('forceobjects').set(geo.path()+' '+cam.path())
setup=h.tab_apply(stage,'lop_karma_setup')
settings=stage.node('karmarendersettings');rop=stage.node('usdrender_rop1')
settings.setInput(0,imp)
settings.parm('camera').set('/framing_camera')
settings.parm('pathtracedsamples').set(8)
settings.parm('engine').set('cpu')
rop.parm('husk_enable_headlight').set(1)
rop.parm('husk_headlight').set('distant')
# Explicit USD product resolution: keep camera aspect and actual product in sync,
# without unlocking Karma Setup's derived resolutiony parameter.
product=stage.createNode('pythonscript','product')
product.setInput(0,settings)
rop.setInput(0,product)
rop.parm('loppath').set(product.path())
records=[]
for name,size,res,direction,projection in (
    ('cube_iso',(3.023,3.023,3.023),(640,360),'iso','perspective'),
    ('tall_portrait',(1,5,.7),(360,640),[1,.3,1],'perspective'),
    ('ortho_oblique',(4,.8,2),(640,360),'iso','ortho')):
    box.parmTuple('size').set(size)
    cam.parm('projection').set(projection)
    fit=h.camera_fit(cam,box,direction=direction,width=res[0],height=res[1])
    product.parm('python').set('from pxr import UsdRender,Gf\ns=hou.pwd().editableStage()\n'
        'for p in s.Traverse():\n'
        f'    if p.GetTypeName() == "RenderProduct": UsdRender.Product(p).CreateResolutionAttr(Gf.Vec2i({res[0]},{res[1]}))\n')
    image_path=output/(name+'.png')
    print('RENDER '+name,flush=True)
    result=h.render_frame(rop,picture=str(image_path),timeout=110,
                          framing={'target':'/framing_asset','coverage':.82})
    assert result['fresh'] and not result['errors'],result
    pixels=h.render_check(str(image_path))
    assert pixels['width']==res[0] and pixels['height']==res[1],pixels
    bbox=pixels['content_bbox']
    assert bbox is not None and pixels['nonblack_pct']>1,pixels
    x0,y0,x1,y1=bbox
    assert x0>=res[0]*.09-3 and x1<=res[0]*.91+3 and y0>=res[1]*.09-3 and y1<=res[1]*.91+3,pixels
    records.append({'case':name,'fit':fit,'render':result,'pixels':pixels})
    print('PASS '+name+' bbox='+str(bbox),flush=True)
(output/'results.json').write_text(json.dumps({'version':hou.applicationVersionString(),
    'scope':'real Karma CPU pixel bounds; not GUI OpenGL or model quality acceptance','cases':records},indent=2),encoding='utf8')
print('SMOKE_PASS='+str(output/'results.json'),flush=True)
