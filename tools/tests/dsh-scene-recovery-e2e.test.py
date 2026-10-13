"""A saved DSH task continues in another real Houdini through its browser UI."""
from pathlib import Path
import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
import importlib.util
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment,reexec_unpacked_test_cli
from dsh_managed_runtime import spawn_frontend,stop_owned


def main():
    reexec_unpacked_test_cli()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-cache',required=True,type=Path)
    parser.add_argument('--save-as',action='store_true',help='Follow a real cross-directory Save As in the same conversation')
    parser.add_argument('--original-choice',choices=('keep','open','auto'),help='GUI only: keep another HIP, choose the original, or resume from an untouched empty scene')
    parser.add_argument('--hython',required=True,type=Path)
    parser.add_argument('--save-hython',type=Path,help='Optional H22 producer; include its native Flipbook preview node in the saved HIP')
    parser.add_argument('--long-warning',action='store_true',help='Inject a long load diagnostic after a real successful load and verify resource pagination')
    parser.add_argument('--warning-archive-failure',action='store_true',help='Make only warning archival unavailable; recovery must still return bounded evidence')
    parser.add_argument('--browser-module',required=True,type=Path)
    parser.add_argument('--gui',action='store_true',help='Use the matching Houdini GUI; load HIP before plugin activation')
    parser.add_argument('--dirty-choice',choices=('keep','discard'),help='GUI only: change the loaded HIP before plugin activation and answer the native conversation question')
    args=parser.parse_args()
    if args.dirty_choice and not args.gui:
        parser.error('--dirty-choice requires --gui for reliable unsaved-change observation')
    if args.original_choice and (not args.gui or args.dirty_choice):
        parser.error('--original-choice requires --gui and cannot combine with --dirty-choice')
    folder=Path(tempfile.mkdtemp(prefix='dsh-scene-recovery-e2e-'))
    hip=folder/('saved-as/project.hip' if args.save_as else 'project.hip')
    if args.save_as:
        (folder/'original').mkdir();hip.parent.mkdir()
        (folder/'original/AGENTS.md').write_text('Original workspace fixture instructions.',encoding='utf-8')
        (hip.parent/'AGENTS.md').write_text('Saved-as workspace fixture instructions.',encoding='utf-8')
    cli=args.runtime_cache.resolve()/'node_modules/@deepseek-ai/dsh/lib/bin.js'
    node=shutil.which('node');hython=args.hython.resolve();task=str(uuid.uuid4())
    env=isolated_environment(folder/'env',executable=hython,gui=args.gui)
    env.update(DSH_RECOVERY_TEST_ROOT=str(folder),DSH_RECOVERY_TASK=task,
               DSH_HOUDINI_RECOVERY_ROOT=str(folder/'recovery'),
               DSH_RECOVERY_DIRTY_CHOICE=args.dirty_choice or '')
    env['DSH_RECOVERY_SAVE_AS']='1' if args.save_as else ''
    env['DSH_RECOVERY_ORIGINAL_CHOICE']=args.original_choice or ''
    env['DSH_RECOVERY_EXPECT_WARNING']='1' if args.save_hython else ''
    env['DSH_RECOVERY_LONG_WARNING']='1' if args.long_warning else ''
    env['DSH_RECOVERY_WARNING_ARCHIVE_FAILURE']='1' if args.warning_archive_failure else ''
    subprocess.run([node,str(ROOT/'tools/tests/prepare-shared-host-fixture.mjs'),str(cli),env['DSH_HOME'],str(ROOT)],cwd=ROOT,env=env,check=True,capture_output=True,timeout=60)
    overlay=folder/'fixture.json'
    overlay.write_text(json.dumps([{'insert':[{'id':'recovery-fixture','name':(ROOT/'tools/tests/dsh-scene-recovery-fixture.mjs').as_uri()}]}]),encoding='utf-8')
    def port():
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));return sock.getsockname()[1]
    def wait_file(path,process,seconds=90):
        deadline=time.monotonic()+seconds
        while True:
            try:
                return json.loads(path.read_text(encoding='utf-8'))
            except (FileNotFoundError,json.JSONDecodeError):
                pass  # A different process can still be completing its fixture JSON write.
            assert process.poll() is None and time.monotonic()<deadline, str(folder)+' waiting for '+path.name
            time.sleep(.1)
    for phase in ('save','resume'):
        if phase=='resume' and args.warning_archive_failure:
            (folder/'recovery/load-warnings').write_text('fixture: not a directory',encoding='utf-8')
        hython=(args.save_hython if phase=='save' and args.save_hython else args.hython).resolve()
        phase_env=isolated_environment(folder/(phase+'-env'),executable=hython,gui=args.gui)
        phase_env.update({key:value for key,value in env.items() if key.startswith('DSH_')})
        env=phase_env
        bridgeport,hostport=port(),port();env['DSH_RECOVERY_PHASE']=phase
        worker=folder/(phase+'-bridge.py');ready=folder/(phase+'-bridge-ready.json')
        load=f"hou.hipFile.load({hip.as_posix()!r},suppress_save_prompt=True)\n" if phase=='resume' else ''
        dirty="hou.node('/obj/asset/source').parm('sizex').set(9)\nassert hou.hipFile.hasUnsavedChanges()\n" if phase=='resume' and args.dirty_choice else ''
        if phase=='resume' and args.original_choice:
            load=("hou.hipFile.clear(suppress_save_prompt=True)\np=hou.node('/obj').createNode('geo','unrelated')\n"
                  +"p.createNode('box','source')\n"+f"hou.hipFile.save({(folder/'other.hip').as_posix()!r})\n")
            dirty="hou.node('/obj/unrelated/source').parm('sizex').set(9)\nassert hou.hipFile.hasUnsavedChanges()\n"
            if args.original_choice=='auto':
                load="hou.hipFile.clear(suppress_save_prompt=True)\n"
                dirty=''
        probe=''
        if phase=='resume' and (args.dirty_choice or args.original_choice):
            probe_node='/obj/unrelated/source' if args.original_choice=='keep' else '/obj/asset/source'
            probe=(f"def final_probe():\n"
                +f" if not Path({str(folder/'probe-request')!r}).exists():return\n"
                +f" value={{'size':hou.node({probe_node!r}).parm('sizex').eval(),'dirty':hou.hipFile.hasUnsavedChanges(),'hip_path':hou.hipFile.path()}}\n"
                +f" Path({str(folder/'final-probe.json')!r}).write_text(json.dumps(value))\n"
                +" hou.ui.removeEventLoopCallback(final_probe)\nhou.ui.addEventLoopCallback(final_probe)\n")
        worker.write_text("import sys,json,time\nfrom pathlib import Path\nimport hou\n"
            +(load if args.gui else '')
            +dirty
            +f"sys.path.insert(0,{str(ROOT/'houdini/python3.11libs')!r})\nimport dsh_bridge as b\n"
            +("preview=hou.node('/out').createNode('flipbook','__dsh_houdini_flipbook')\npreview.parm('skysaturation').set(0.73)\n" if phase=='save' and args.save_hython else '')
            +("original_load=hou.hipFile.load\ndef warning_load(*a,**k):\n"
              +" message='HEAD load diagnostic'\n try: original_load(*a,**k)\n except hou.LoadWarning as error: message=str(error)\n"
              +" raise hou.LoadWarning(message+'\\n'+('Repeated {parameter} warning 🚀\\n'*20000)+'MIDDLE_DIAGNOSTIC_MARKER'+('another warning\\n'*5000)+'TAIL_MISSING_ASSET')\nhou.hipFile.load=warning_load\n"
              if phase=='resume' and args.long_warning else '')
            +(load if not args.gui else '')
            +f"b.start({bridgeport});b._pump_active=True\nPath({str(ready)!r}).write_text(json.dumps({{'executor':b._EXECUTOR_ID,'dirty':hou.hipFile.hasUnsavedChanges(),'empty_new_scene':b._recovery.facts()['empty_new_scene']}}))\n"
            +probe
            +("" if args.gui else "while True:\n b._pump();time.sleep(.02)\n"),encoding='utf-8')
        with (folder/(phase+'-bridge.log')).open('wb') as blog,(folder/(phase+'-host.log')).open('wb') as hlog:
            job=None;command=[str(hython),str(worker)]
            if args.gui:
                spec=importlib.util.spec_from_file_location('gui_harness',ROOT/'tools/tests/dsh-source-webview.test.py')
                harness=importlib.util.module_from_spec(spec);spec.loader.exec_module(harness)
                job=harness.GuiProcessJob()
                hooks=folder/(phase+'-hooks')
                version='3.13' if '22' in str(hython.parent.parent) else '3.11'
                scripts=hooks/('python'+version+'libs');scripts.mkdir(parents=True)
                if phase=='resume' and (args.dirty_choice or args.original_choice):
                    # Houdini clears its startup dirty flag after uiready returns.
                    # Enter the ordinary event loop before creating real unsaved work.
                    startup_hook=("import hou,runpy\ndef start_fixture():\n hou.ui.removeEventLoopCallback(start_fixture)\n"
                                  +f" runpy.run_path({str(worker)!r})\nhou.ui.addEventLoopCallback(start_fixture)\n")
                else:
                    startup_hook=f'import runpy\nrunpy.run_path({str(worker)!r})\n'
                (scripts/'uiready.py').write_text(startup_hook,encoding='utf-8')
                env['HOUDINI_PATH']=hooks.as_posix()+';&'
                command=[str(hython.with_name('houdini.exe')),'-foreground','-geometry=1100x850+12000+12000']
            startup=subprocess.STARTUPINFO();startup.dwFlags=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
            process=subprocess.Popen(command,cwd=hython.parent,env=env,stdout=blog,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,startupinfo=startup)
            if job is not None:job.assign(process)
            host=None
            try:
                identity=wait_file(ready,process,40)
                if phase=='resume' and (args.dirty_choice or args.original_choice):
                    if args.original_choice=='auto':assert identity['empty_new_scene'],(str(folder),identity)
                    else:assert identity['dirty'],(str(folder),identity)
                env.update(DSH_HOUDINI_EXECUTOR_ID=identity['executor'],DSH_HOUDINI_BRIDGE_URL=f'http://127.0.0.1:{bridgeport}')
                host=spawn_frontend([node,str(cli),'web','--patch',str(overlay),'--port',str(hostport),'--no-open'],node=node,cwd=folder,env=env,stdout=hlog,stderr=subprocess.STDOUT)
                if phase=='resume' or args.save_as:
                    wait_file(folder/(phase+'-ready.json'),host)
                    browser=subprocess.run([node,str(ROOT/'tools/tests/scene-recovery-browser.mjs'),str(folder/(phase+'-host.log')),task,str(args.browser_module.resolve())],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
                    assert browser.returncode==0,(str(folder),browser.stdout,browser.stderr)
                    print(browser.stdout,flush=True)
                result=wait_file(folder/(phase+'-result.json'),host)
                assert result['ok'],(str(folder),result)
                if phase=='save':
                    checkpoint=result['receipts'][0]['execution']['scene_recovery']['checkpoint_id']
                    wait_file(folder/'recovery/checkpoints'/(checkpoint+'.json'),process,15)
                elif args.dirty_choice or args.original_choice:
                    (folder/'probe-request').touch()
                    observed=wait_file(folder/'final-probe.json',process,15)
                    keep=args.dirty_choice=='keep' or args.original_choice=='keep'
                    assert observed['size']==(9 if keep else 2.5),(str(folder),observed)
                    if args.original_choice:
                        assert Path(observed['hip_path']).name==('other.hip' if keep else 'project.hip'),observed
                    if keep:
                        assert observed['dirty'],(str(folder),observed)
                print(phase,'PASS',folder,flush=True)
            finally:
                if host is not None:stop_owned(host)
                # Terminate only the fixture Houdini, simulating process loss.
                if job is not None:job.close()
                else:process.terminate()
                process.wait(timeout=20)
    print('PASS cross-process DSH persistence/browser/native/PTC recovery:',folder,flush=True)


if __name__=='__main__':main()
