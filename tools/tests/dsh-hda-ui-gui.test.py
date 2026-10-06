"""Render the authored gallery in a separate native GUI. No desktop automation."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from houdini_test_environment import isolated_environment, launch_directory, reexec_unpacked_test_cli


def probe():
    import hou
    from hutil.Qt import QtCore, QtWidgets
    output=Path(os.environ['DSH_UI_GUI_OUTPUT'])
    module_spec=importlib.util.spec_from_file_location('gallery_builder',ROOT/'skills/houdini-parameter-ui/scripts/build-ui-gallery.py')
    gallery=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(gallery)
    window=hou.qt.mainWindow()
    state={'step':0,'shots':[]}
    timer=QtCore.QTimer(window)
    def advance():
        try:
            if state['step']==0:
                import dsh_bridge as bridge
                state['catalog']={}
                for kind in ('viewer_state','radial','panel'):
                    check=bridge.run_code(f'__result__=tool_catalog(kind={kind!r},limit=3)',
                        owner_session='ui-gallery-read',owner_call='catalog-'+kind,read_only=True)
                    assert check['ok'],check.get('error')
                    page=check['result']
                    assert not page['unavailable'] and page['total']>0,(kind,page)
                    state['catalog'][kind]=page
                state['report']=gallery.build(output)
                for path in state['report']['nodes'].values():
                    node=hou.node(path)
                    node.updateParmStates()
                    for name in ('label1','label2','label3','label4'):
                        # Parm.isHidden reports evaluated hide-when state; the
                        # persistent template flag is a separate native surface.
                        # Actual visibility still requires the screenshots below.
                        assert node.parmTemplateGroup().find(name).isHidden(), (path,name)
                        assert node.type().definition().parmTemplateGroup().find(name).isHidden(), (path,name)
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
            elif state['step']==4:
                target=output/'attribute-output.png'
                assert window.screen().grabWindow(window.winId()).save(str(target));state['shots'].append(str(target))
                window.resize(420,900)
            elif state['step']==5:
                target=output/'attribute-output-resized.png'
                assert window.screen().grabWindow(window.winId()).save(str(target));state['shots'].append(str(target))
                node=hou.node(state['report']['nodes']['artist_controls'])
                state['artist_node']=node
                state['floating']=hou.ui.curDesktop().createFloatingPanel(
                    hou.paneTabType.Parm,position=(100,100),size=(420,720))
                state['artist_parms']=state['floating'].paneTabs()[0]
                state['artist_parms'].setCurrentNode(node)
                state['dialog']=hou.qt.floatingPanelWindow(state['floating'])
            elif state['step']==6:
                target=output/'artist-controls-constant.png'
                assert state['dialog'].screen().grabWindow(state['dialog'].winId()).save(str(target));state['shots'].append(str(target))
                state['artist_node'].updateParmStates()
                visible={p.name() for p in state['artist_node'].parms() if not p.isHidden()}
                assert 'amount' in visible and 'attribute_name' not in visible and 'texture_file' not in visible,visible
                state['artist_node'].parm('value_source').set(1)
                state['artist_node'].parm('region_enabled1').set(0)
                state['artist_node'].updateParmStates()
            else:
                target=output/'artist-controls-attribute.png'
                assert state['dialog'].screen().grabWindow(state['dialog'].winId()).save(str(target));state['shots'].append(str(target))
                visible={p.name() for p in state['artist_node'].parms() if not p.isHidden()}
                assert 'amount' not in visible and 'attribute_name' in visible and 'texture_file' not in visible,visible
                assert state['artist_node'].parm('region_weight1').isDisabled()
                width=state['dialog'].width()
                assert width<=500, width
                hou.hipFile.save(str(output/'ui-gallery.hip'))
                timer.stop()
                report={'ok':True,'shots':state['shots'],
                    'requested_window_width':420,'actual_window_width':window.width(),
                    'narrow_width_reached':window.width()<=500,
                    'chinese_parameter_width':width,'mode_visibility_verified':True,
                    'region_disabled_verified':True,'tool_catalog':state['catalog']}
                pending=output/'gui-result.tmp'
                pending.write_text(json.dumps(report),encoding='utf-8')
                pending.replace(output/'gui-result.json')
                return
            state['step']+=1
        except Exception as error:
            (output/'gui-result.json').write_text(json.dumps({'ok':False,'error':str(error),'step':state['step']}),encoding='utf-8')
            timer.stop()
            # Only this owned, throwaway test scene may be saved during failure exit.
            hou.hipFile.save(str(output/'failed-gallery.hip'))
            window.close()
    timer.timeout.connect(advance);timer.start(1500)


def main():
    reexec_unpacked_test_cli()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--houdini',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if output.is_relative_to(ROOT) or output.exists() and any(output.iterdir()):
        parser.error('--output must be an empty directory outside the repository')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dsh-ui-gui-') as temp:
        env=isolated_environment(temp, executable=args.houdini, gui=True)
        prefs_pattern=env['HOUDINI_USER_PREF_DIR']
        script=f"import runpy\nrunpy.run_path({str(Path(__file__).resolve())!r})['probe']()\n"
        for major, version in (('21.0','3.11'),('22.0','3.13')):
            prefs=Path(prefs_pattern.replace('__HVER__',major))
            hook=prefs/f'python{version}libs/uiready.py';hook.parent.mkdir(parents=True);hook.write_text(script,encoding='utf-8')
        env['DSH_UI_GUI_OUTPUT']=str(output)
        info=subprocess.STARTUPINFO();info.dwFlags|=subprocess.STARTF_USESHOWWINDOW;info.wShowWindow=0
        with (output/'gui-process.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen([str(args.houdini.resolve()),'-foreground','-geometry=1100x900+12000+12000'],
                cwd=launch_directory(args.houdini),env=env,stdout=log,stderr=log,startupinfo=info)
            try:
                deadline=time.monotonic()+120
                while process.poll() is None and not (output/'gui-result.json').exists() and time.monotonic()<deadline:
                    time.sleep(0.2)
            finally:
                if process.poll() is None:
                    # Native floating panes can crash during a callback-driven
                    # Houdini shutdown. Reclaim only this disposable worker after
                    # its report, rather than claim graceful-close coverage.
                    process.terminate();process.wait(timeout=20)
        result_path=output/'gui-result.json'
        result=json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else {'ok':False,'error':'no GUI report'}
        result['exit_code']=process.returncode
        result['cleanup']='owned disposable GUI worker terminated after report'
        print(json.dumps(result,indent=2))
        if not result['ok']:
            raise SystemExit(1)


if __name__=='__main__':
    main()
