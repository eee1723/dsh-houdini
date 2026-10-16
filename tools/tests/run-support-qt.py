from pathlib import Path
import argparse
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from houdini_test_environment import isolated_environment, launch_directory, reexec_unpacked_test_cli


def main():
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser()
    parser.add_argument('--hython',type=Path,action='append',required=True)
    parser.add_argument('--startup-feedback',action='store_true')
    args = parser.parse_args()
    for executable in args.hython:
        fixture = Path(tempfile.mkdtemp(prefix='support-qt-',dir=ROOT/'tools/out'))
        env = isolated_environment(fixture/'env',executable=executable,gui=True)
        env.update(QT_QPA_PLATFORM='offscreen',DSH_SUPPORT_QT_ROOT=str(fixture))
        with (fixture/'process.log').open('wb') as output:
            script='dsh-startup-feedback-qt.test.py' if args.startup_feedback else 'dsh-support-qt.test.py'
            result = subprocess.run([str(executable),str(ROOT/'tools/tests'/script)],
                                    cwd=launch_directory(executable),env=env,stdout=output,stderr=subprocess.STDOUT,
                                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=90)
        print((fixture/'process.log').read_text(encoding='utf-8',errors='replace'),flush=True)
        if result.returncode:
            raise RuntimeError('Qt download regression failed: '+str(fixture))


if __name__ == '__main__':
    main()
