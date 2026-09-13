"""Dimension and all-point color checks on an actual public SOP HDA output."""
import importlib.util,json,tempfile,sys
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('delivery',ROOT/'tools/hda-delivery-check.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
with tempfile.TemporaryDirectory(prefix='delivery-geometry-') as tmp:
 p=Path(tmp);g=hou.node('/obj').createNode('geo','delivery_geometry')
 s=g.createNode('subnet','asset')
 for c in s.children():c.destroy()
 box=s.createNode('box');color=s.createNode('color');color.setInput(0,box)
 color.parmTuple('color').set((.2,.4,.8))
 out=s.createNode('output');out.setInput(0,color)
 asset=s.createDigitalAsset(name='delivery_geometry::1.0',hda_file_name=str(p/'asset.hda'))
 manifest={'assets':['asset.hda'],'category':'Sop','type':'delivery_geometry::1.0','cases':[
  {'id':'dimensions-color','expect_geometry':{'output':'.','bounds_size':[1,1,1],'point_cd':[.2,.4,.8]}}]}
 source=p/'manifest.json';source.write_text(json.dumps(manifest),encoding='utf-8-sig')
 exe=Path(hou.text.expandString('$HFS'))/'bin/hython.exe'
 r=runner.check(source,exe);assert r['ok'],r
 manifest['cases'][0]['expect_geometry']['point_cd']=[.8,.4,.2]
 source.write_text(json.dumps(manifest),encoding='utf-8')
 r=runner.check(source,exe);assert not r['ok'] and 'point_cd differs' in json.dumps(r),r
 g.destroy()
print('PASS public geometry dimension/Cd positive and wrong-color negative '+hou.applicationVersionString())
