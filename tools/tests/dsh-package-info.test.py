"""Read-only package projection and unavailable boundaries, not GUI loading."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h
assert h.package_info()['status']=='unavailable'
old=hou.isUIAvailable
from types import SimpleNamespace
old_ui=getattr(hou,'ui',None)
hou.ui=SimpleNamespace()
try:
 hou.isUIAvailable=lambda:True
 hou.ui.packageInfo=lambda:json.dumps({'sample':{'Active':False,'File path':'/packages/sample.json',
  'Environment Variables':{'SECRET':['never-return']},'Resources':{'Digital Assets':['a','b']}}})
 r=b.run_code('__result__=package_info()',owner_session='package-reader',read_only=True)
 assert r['ok'],r
 assert r['result']['packages'][0]['active'] is False
 assert 'never-return' not in json.dumps(r['result'])
 detail=h.package_info('sample',1)
 assert detail['packages'][0]['resources_truncated']
 assert detail['packages'][0]['resource_counts']['Digital Assets']==2
 assert h.package_info('missing')['status']=='not_found'
 for value in (True,0,257):
  try:h.package_info(limit=value);raise AssertionError('accepted invalid limit')
  except ValueError:pass
finally:
 hou.isUIAvailable=old
 if old_ui is None:del hou.ui
 else:hou.ui=old_ui
print('PASS package read-only projection '+hou.applicationVersionString())
