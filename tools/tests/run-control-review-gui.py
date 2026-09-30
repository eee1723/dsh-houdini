"""Isolated H21/H22 real GUI regression for fixed baseline/control captures.

Uses a new HIP and preferences, no model requests and no live user process.
Run once for each supported houdini.exe; retain the output directory as evidence.
"""
from pathlib import Path
import argparse
import json
import re
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from houdini_test_environment import isolated_environment,launch_directory


def verify(output):
    result=json.loads((output/'results.json').read_text(encoding='utf-8'))
    raw=json.loads((output/'raw-renders.json').read_text(encoding='utf-8'))
    shared=result['shared']['returned'];overflow=result['baseline_lock']['returned']
    assert result['real_gui'] is True
    assert shared['status']=='pass' and shared['capture_status']=='observed' and shared['restored'],shared
    captures=shared['baseline_captures']+shared['results'][0]['captures']
    assert len(captures)==2
    fields=('bounds','depth_bounds','frame','eye','coverage','projection','mode','direction')
    for key in fields:assert captures[0]['framing'][key]==captures[1]['framing'][key],key
    first=[r['result'] for r in raw[:2]]
    for key in ('matrix','near','far'):
        assert first[0]['framing'][key]==first[1]['framing'][key],key
    for capture in captures:
        path=Path(capture['output']).resolve(strict=True)
        assert path.is_relative_to(output) and path.stat().st_size>0,path
        assert Path(capture['artifact']['actual_path']).resolve()==path
        assert capture['semantic_status']=='unverified'
    assert overflow['status']=='unverified' and overflow['capture_status']=='unverified',overflow
    assert overflow['results'][0]['status']=='pass' and overflow['restored'],overflow
    rejected=overflow['results'][0]['captures'][0]
    assert rejected['render_started'] is False and rejected['user_state_restored'] is True,rejected
    assert rejected['framing_status']=='failed' and 'outside_safe_frame' in rejected['reasons'],rejected
    assert len(raw)==4 and raw[-1]['error_type']=='CheckpointError',raw
    for label in ('shared','baseline_lock'):
        assert result[label]['state_restored'] is True and result[label]['state_after']==result['baseline_state'],label
    assert len(result['baseline_state']['keys'])==2 and result['baseline_state']['frame']==7
    return {'version':result['version'],'paired_images':2,'fixed_camera':True,'overflow_not_rendered':True,
            'parameter_keys_frame_geometry_selection_flags_restored':True,'semantic_status':'unverified'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--houdini',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--timeout',type=float,default=180)
    args=parser.parse_args()
    binary=args.houdini.resolve(strict=True);hython=binary.with_name('hython.exe')
    output=args.output.resolve()
    if output.is_relative_to(ROOT) or (output.exists() and any(output.iterdir())):
        parser.error('--output must be a new or empty directory outside the repository')
    if args.timeout<=0 or not hython.is_file():parser.error('positive timeout and sibling hython.exe required')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dsh-control-gui-version-') as temp:
        probe=subprocess.run([str(hython),'-c',"import hou; print('DSH_VERSION='+'.'.join(map(str,hou.applicationVersion()[:2])))"],
            env=isolated_environment(temp,executable=hython),cwd=launch_directory(hython),
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
    match=re.search(r'DSH_VERSION=(21\.0|22\.0)\b',probe.stdout)
    if probe.returncode or not match:parser.error('working H21/H22 installation required: '+probe.stderr[-400:])
    version=match.group(1);python_version='3.11' if version=='21.0' else '3.13'
    fixture=ROOT/'tools/tests/dsh-control-review-gui-fixture.py'
    with tempfile.TemporaryDirectory(prefix='dsh-control-review-gui-') as temp:
        env=isolated_environment(temp,executable=binary,gui=True)
        hook=Path(env['HOUDINI_USER_PREF_DIR'].replace('__HVER__',version))/f'python{python_version}libs/uiready.py'
        hook.parent.mkdir(parents=True,exist_ok=True)
        hook.write_text(f'import runpy\nrunpy.run_path({str(fixture)!r})\n',encoding='utf-8')
        env['DSH_CONTROL_REVIEW_GUI_DIR']=str(output)
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
        with (output/'process.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen([str(binary),'-foreground','-geometry=900x700+12000+12000'],
                cwd=launch_directory(binary),env=env,stdout=log,stderr=log,startupinfo=startup)
            try:process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=20)
                raise RuntimeError('self-owned GUI fixture timed out; see '+str(output))
    assert process.returncode==0,process.returncode
    assert not (output/'error.txt').exists(),(output/'error.txt').read_text(encoding='utf-8')
    summary=verify(output)
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))
    print('Evidence:',output)


if __name__=='__main__':main()
