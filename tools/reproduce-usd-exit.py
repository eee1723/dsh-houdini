"""Compare native USD script completion and process exit in isolated hython.

python tools/reproduce-usd-exit.py --hython D:/Houdini22/bin/hython.exe --repeat 3
Repeat --hython to compare installations. No existing HIP, GUI, DSH Host,
network service or plugin is loaded by the child scripts. Evidence is retained
under a new temporary directory; no user preferences or installed files change.
"""
from pathlib import Path
import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

from houdini_test_environment import (
    isolated_environment, launch_directory, reexec_unpacked_test_cli,
)

IDENTITY = 'DSH_USD_REPRO_IDENTITY='
COMPLETE = 'DSH_USD_REPRO_BODY_COMPLETE'
HEADER = r'''
import os, json, sys
import hou
package = None
if os.name == 'nt':
    import ctypes
    from ctypes import wintypes
    get_name = ctypes.WinDLL('kernel32').GetCurrentPackageFullName
    get_name.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR]
    get_name.restype = wintypes.LONG
    size = wintypes.DWORD()
    status = get_name(ctypes.byref(size), None)
    if status == 122:
        value = ctypes.create_unicode_buffer(size.value)
        if get_name(ctypes.byref(size), value) != 0:
            raise RuntimeError('Could not read child package identity')
        package = value.value
    elif status != 15700:
        raise RuntimeError('Could not read child package identity: '+str(status))
print('DSH_USD_REPRO_IDENTITY='+json.dumps({
    'pid':os.getpid(), 'version':hou.applicationVersionString(),
    'hfs_env':os.environ.get('HFS'), 'hfs_hou':hou.getenv('HFS'),
    'cwd':os.getcwd(), 'path':os.environ.get('PATH'), 'package':package,
    'ui_available':hou.isUIAvailable(), 'hip_is_new':hou.hipFile.isNewFile(),
    'dsh_modules':[name for name in sys.modules if name.startswith('dsh_')],
}), flush=True)
if package is not None:
    raise RuntimeError('Packaged child identity would invalidate this isolation')
if any(name.startswith('dsh_') for name in sys.modules):
    raise RuntimeError('DSH modules unexpectedly loaded in the native-only child')
'''

# Keep the native LOP body self-contained and independent of mutable repo tests.
CASES = {
    'import-only': "from pxr import Usd, UsdLux\nprint('USD imports completed', flush=True)\n",
    'memory-stage': """from pxr import Usd, UsdLux
def check_memory():
    stage = Usd.Stage.CreateInMemory()
    UsdLux.DomeLight.Define(stage, '/Dome')
    assert stage.GetPrimAtPath('/Dome').HasAPI(UsdLux.LightAPI)
    print('In-memory USD stage completed', flush=True)
check_memory()
""",
    'native-lop': """from pxr import UsdLux
n = hou.node('/stage').createNode('pythonscript', 'fixture')
n.parm('python').set("from pxr import UsdLux,UsdGeom\\ns=hou.pwd().editableStage()\\nUsdLux.DomeLight.Define(s,'/Dome')\\nUsdLux.LightAPI.Apply(UsdGeom.Mesh.Define(s,'/EmissiveMesh').GetPrim())")
print([(str(p.GetPath()), p.HasAPI(UsdLux.LightAPI)) for p in n.stage().Traverse()], flush=True)
""",
}


def as_text(value):
    return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''


def run_case(executable, directory, case, repeat, timeout):
    directory.mkdir(parents=True)
    script = directory / 'probe.py'
    script.write_text(HEADER + '\n' + CASES[case] + '\nprint(' + repr(COMPLETE) + ', flush=True)\n', encoding='utf-8')
    env = isolated_environment(directory, executable=executable)
    if os.name == 'nt':
        system = Path(os.environ['SystemRoot'])
        env['PATH'] = os.pathsep.join(str(p) for p in (
            executable.parent, system / 'System32', system, system / 'System32/Wbem'))
    started = time.monotonic()
    start_utc = datetime.now(timezone.utc).isoformat()
    timed_out = False
    try:
        result = subprocess.run([str(executable), str(script)],
            cwd=launch_directory(executable), env=env, capture_output=True,
            text=True, encoding='utf-8', errors='replace', timeout=timeout,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        # subprocess.run kills and waits for only its own new child on timeout.
        timed_out = True
        code, stdout, stderr = None, as_text(error.stdout), as_text(error.stderr)
    (directory / 'stdout.txt').write_text(stdout, encoding='utf-8')
    (directory / 'stderr.txt').write_text(stderr, encoding='utf-8')
    identities = [json.loads(line[len(IDENTITY):]) for line in stdout.splitlines() if line.startswith(IDENTITY)]
    body_complete = COMPLETE in stdout.splitlines()
    unsigned = code & 0xffffffff if code is not None else None
    status = ('timeout' if timed_out else 'passed' if code == 0 and body_complete
              else 'abnormal_exit_after_body' if body_complete else 'startup_or_body_failed')
    return {'executable': str(executable), 'case': case, 'repeat': repeat,
            'started_utc': start_utc, 'seconds': round(time.monotonic() - started, 3),
            'identity': identities[-1] if identities else None,
            'body_complete': body_complete, 'timed_out': timed_out,
            'exit_code': code, 'exit_hex': f'0x{unsigned:08X}' if unsigned is not None else None,
            'status': status, 'directory': str(directory),
            'scope': 'Native isolated child only; body completion does not identify the crash stack or prove clean shutdown.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hython', required=True, action='append', type=Path,
                        help='Exact hython executable; repeat for version comparison')
    parser.add_argument('--repeat', type=int, default=1, help='Fresh processes per case, default 1')
    parser.add_argument('--case', action='append', choices=tuple(CASES), help='Default: all three controls')
    parser.add_argument('--timeout', type=int, default=45, help='Seconds per child; timeouts are reported separately')
    parser.add_argument('--out-root', type=Path, help='Optional parent for a new, unique evidence directory')
    args = parser.parse_args()
    if not 1 <= args.repeat <= 20 or not 5 <= args.timeout <= 300:
        parser.error('repeat must be 1..20 and timeout 5..300 seconds')
    executables = [p.resolve(strict=True) for p in args.hython]
    if any(not p.is_file() or p.name.lower() not in ('hython', 'hython.exe') for p in executables):
        parser.error('Each --hython must name the installation\'s hython executable')
    reexec_unpacked_test_cli()
    if args.out_root:
        args.out_root.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='dsh-usd-exit-', dir=args.out_root)).resolve()
    report = {'schema': 1, 'host': platform.platform(), 'output': str(output),
              'cases': [], 'scope': 'No existing Houdini process, HIP or user configuration was changed.'}
    print('Evidence:', output, flush=True)
    for index, executable in enumerate(executables, 1):
        for case in args.case or CASES:
            for repetition in range(1, args.repeat + 1):
                row = run_case(executable, output / f'installation-{index}' / f'{case}-{repetition}',
                               case, repetition, args.timeout)
                report['cases'].append(row)
                (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                version = (row['identity'] or {}).get('version', 'unknown')
                print(f"{version:12} {case:14} #{repetition}: {row['status']} "
                      f"body={row['body_complete']} exit={row['exit_hex']} ({row['exit_code']})", flush=True)
    print('REPORT=' + str(output / 'report.json'), flush=True)
    return 0 if all(row['status'] == 'passed' for row in report['cases']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
