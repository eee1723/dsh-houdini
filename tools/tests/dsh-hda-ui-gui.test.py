"""Render the authored gallery in a separate native GUI. No desktop automation."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]


def probe():
    import hou
    from hutil.Qt import QtCore
    output=Path(os.environ['DSH_UI_GUI_OUTPUT'])
    module_spec=importlib.util.spec_from_file_location('gallery_builder',ROOT/'skills/houdini-parameter-ui/scripts/build-ui-gallery.py')
    gallery=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(gallery)
    window=hou.qt.mainWindow()
    state={'step':0,'shots':[]}
    timer=QtCore.QTimer(window)
    def advance():
        try:
            if state['step']==0:
                state['report']=gallery.build(output)
                state['pane']=hou.ui.paneTabOfType(hou.paneTabType.Parm)
                state['pane'].pane().setIsMaximized(True)
                state['pane'].setCurrentNode(hou.node(state['report']['nodes']['shape_controls']))
                window.showNormal();window.move(30,30);window.resize(1100,900)
            elif state['step']==1:
                target=output/'shape-general.png'
                assert window.screen().grabWindow(window.winId()).save(str(target));state['shots'].append(str(target))
                n=hou.node(state['report']['nodes']['shape_controls'])
                next(p for p in n.parms() if p.parmTemplate().type()==hou.parmTemplateType.FolderSet
                     and 'Detail' in p.parmTemplate().folderNames()).set(1)
            elif state['step']==2:
                target=output/'shape-detail.png'
                assert window.screen().grabWindow(window.winId()).save(str(target));state['shots'].append(str(target))
                n=hou.node(state['report']['nodes']['attribute_controls'])
                state['pane'].setCurrentNode(n)
            elif state['step']==3:
                target=output/'attribute-controls.png'
                assert window.screen().grabWindow(window.winId()).save(str(target));state['shots'].append(str(target))
                n=hou.node(state['report']['nodes']['attribute_controls'])
                next(p for p in n.parms() if p.parmTemplate().type()==hou.parmTemplateType.FolderSet
                     and 'Output' in p.parmTemplate().folderNames()).set(1)
            else:
                target=output/'attribute-output.png'
                assert window.screen().grabWindow(window.winId()).save(str(target));state['shots'].append(str(target))
                (output/'gui-result.json').write_text(json.dumps({'ok':True,'shots':state['shots']}),encoding='utf-8')
                hou.hipFile.save(str(output/'ui-gallery.hip'))
                timer.stop();window.close();return
            state['step']+=1
        except Exception as error:
            (output/'gui-result.json').write_text(json.dumps({'ok':False,'error':str(error),'step':state['step']}),encoding='utf-8')
            timer.stop()
            # Only this owned, throwaway test scene may be saved during failure exit.
            hou.hipFile.save(str(output/'failed-gallery.hip'))
            window.close()
    timer.timeout.connect(advance);timer.start(1500)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--houdini',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if output.is_relative_to(ROOT) or output.exists() and any(output.iterdir()):
        parser.error('--output must be an empty directory outside the repository')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dsh-ui-gui-') as temp:
        prefs_pattern=str(Path(temp)/'prefs__HVER__')
        script=f"import runpy\nrunpy.run_path({str(Path(__file__).resolve())!r})['probe']()\n"
        for major, version in (('21.0','3.11'),('22.0','3.13')):
            prefs=Path(prefs_pattern.replace('__HVER__',major))
            hook=prefs/f'python{version}libs/uiready.py';hook.parent.mkdir(parents=True);hook.write_text(script,encoding='utf-8')
        env=dict(os.environ)
        for key in list(env):
            if key.upper().startswith('HOUDINI_') or key.upper() in ('PYTHONPATH','PYTHONHOME','HSITE','HFS','HB','HDSO','HHP'):
                env.pop(key)
        env.update(HOUDINI_PATH='&',HOUDINI_NO_ENV_FILE='1',HOUDINI_USER_PREF_DIR=prefs_pattern,
                   HOUDINI_PACKAGE_DIR=str(Path(temp)/'packages'),DSH_UI_GUI_OUTPUT=str(output),PYTHONNOUSERSITE='1')
        info=subprocess.STARTUPINFO();info.dwFlags|=subprocess.STARTF_USESHOWWINDOW;info.wShowWindow=0
        with (output/'gui-process.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen([str(args.houdini.resolve()),'-foreground','-geometry=1100x900+12000+12000'],
                cwd=args.houdini.resolve().parent,env=env,stdout=log,stderr=log,startupinfo=info)
            try:
                process.wait(timeout=120)
            finally:
                if process.poll() is None:
                    process.kill();process.wait(timeout=20)
        result_path=output/'gui-result.json'
        result=json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else {'ok':False,'error':'no GUI report'}
        result['exit_code']=process.returncode
        print(json.dumps(result,indent=2))
        if not result['ok'] or process.returncode!=0:
            raise SystemExit(1)


if __name__=='__main__':
    main()
