"""Isolated native package discovery. Run with ordinary Python --houdini EXE."""
import argparse,json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from houdini_test_environment import isolated_environment,launch_directory

def probe():
 import hou
 from PySide6 import QtCore
 def inspect():
  result={}
  try:
   sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
   import dsh_bridge as b
   before=(hou.hipFile.path(),hou.hipFile.hasUnsavedChanges(),hou.frame(),tuple(hou.selectedNodes()))
   def query(code):
    r=b.run_code(code,owner_session='package-gui-test',read_only=True)
    assert r['ok'],r
    return r['result']
   a=query('__result__=package_info()');c=query('__result__=package_info()')
   assert a['packages']==c['packages']
   enabled=query("__result__=package_info('fixture_enabled')")
   assert enabled['packages'][0]['active'] is True,enabled
   disabled=query("__result__=package_info('fixture_disabled')")
   assert disabled['status']=='not_found' or disabled['packages'][0]['active'] is False,disabled
   assert 'fixture_module.py' in json.dumps(enabled),enabled
   assert before==(hou.hipFile.path(),hou.hipFile.hasUnsavedChanges(),hou.frame(),tuple(hou.selectedNodes()))
   result={'ok':True,'version':hou.applicationVersionString(),'enabled':enabled,'disabled':disabled,'repeated_equal':True}
  except Exception:
   import traceback
   result={'ok':False,'error':traceback.format_exc()}
  Path(os.environ['DSH_PACKAGE_REPORT']).write_text(json.dumps(result),encoding='utf-8')
  # The scene is empty and unchanged; normal Qt shutdown avoids teardown from
  # inside the native package query itself.
  QtCore.QTimer.singleShot(100,hou.ui.mainQtWindow().close)
 QtCore.QTimer.singleShot(2000,inspect)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--houdini',type=Path,required=True)
 args=p.parse_args();exe=args.houdini.resolve()
 with tempfile.TemporaryDirectory(prefix='dsh-package-gui-') as tmp:
  root=Path(tmp);env=isolated_environment(root,executable=exe,gui=True)
  resources=root/'resources';(resources/'scripts/python').mkdir(parents=True)
  (resources/'scripts/python/fixture_module.py').write_text('VALUE = 1\n')
  for name,enabled in [('fixture_enabled',True),('fixture_disabled',False)]:
   (root/'packages'/f'{name}.json').write_text(json.dumps({'enable':enabled,'path':str(resources)}))
  for major,python in [('21.0','3.11'),('22.0','3.13')]:
   hook=Path(env['HOUDINI_USER_PREF_DIR'].replace('__HVER__',major))/f'python{python}libs/uiready.py'
   hook.parent.mkdir(parents=True);hook.write_text('import runpy\nrunpy.run_path('+repr(str(Path(__file__).resolve()))+')["probe"]()\n')
  report=root/'report.json';env['DSH_PACKAGE_REPORT']=str(report)
  info=subprocess.STARTUPINFO();info.dwFlags|=subprocess.STARTF_USESHOWWINDOW;info.wShowWindow=0
  with (root/'process.log').open('w') as log:
   process=subprocess.Popen([str(exe),'-foreground','-geometry=800x600+12000+12000'],cwd=launch_directory(exe),env=env,stdout=log,stderr=log,startupinfo=info)
   try:process.wait(timeout=100)
   finally:
    if process.poll() is None:process.kill();process.wait()
  result=json.loads(report.read_text()) if report.exists() else {'ok':False,'error':'no GUI report'}
  result['exit_code']=process.returncode
  print(json.dumps(result,ensure_ascii=False))
  sys.exit(0 if result['ok'] and process.returncode==0 else 1)
