"""Explicit component-worker supervisor. JSON readiness on stdout, STOP on stdin.

No model or live-engine discovery. A caller supplies the executable, new work
directory and registry. EOF reclaims only the owned process tree, never a port.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from dsh_worker_limits import WorkerJob
from houdini_test_environment import isolated_environment, launch_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True, type=Path)
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--registry', required=True, type=Path)
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--show', action='store_true', help='Show the GUI for an explicitly interactive assembly test')
    parser.add_argument('--memory-mb', type=int, required=True)
    parser.add_argument('--threads', type=int, required=True)
    parser.add_argument('--startup-timeout', type=float, required=True)
    args = parser.parse_args()
    if args.show and not args.gui:
        raise ValueError('--show requires --gui')
    if not 128 <= args.memory_mb <= 65536 or not 1 <= args.threads <= 64 or not 0 < args.startup_timeout <= 600:
        raise ValueError('invalid component resource limits')
    for p in (args.executable, args.directory, args.registry):
        if not p.is_absolute():
            raise ValueError('absolute paths required')
        for ancestor in (p, *p.parents):
            if ancestor.is_symlink() or (hasattr(ancestor, 'is_junction') and ancestor.is_junction()):
                raise ValueError('worker paths must not traverse links or junctions')
    executable = args.executable.resolve(strict=True)
    directory = args.directory.resolve()
    directory.mkdir(exist_ok=False)
    workspace = directory / 'workspace'
    workspace.mkdir()
    request = {'workspace': str(workspace), 'registry': str(args.registry.resolve()),
               'startup_timeout': args.startup_timeout, 'show_ui': args.show}
    request_file = directory / 'request.json'
    request_file.write_text(json.dumps(request), encoding='utf-8')
    env = isolated_environment(directory / 'environment', executable=executable, gui=args.gui)
    env['HOUDINI_MAXTHREADS'] = str(args.threads)
    env['DSH_COMPONENT_WORKER_REQUEST'] = str(request_file)
    module = ROOT / 'houdini/python3.11libs/dsh_component_worker.py'
    if args.gui:
        hooks = directory / 'hooks'
        for version in ('3.11', '3.13'):
            scripts = hooks / ('python' + version + 'libs')
            scripts.mkdir(parents=True)
            (scripts / 'uiready.py').write_text(
                'import sys\nsys.path.insert(0, ' + repr(str(module.parent)) + ')\n'
                'import dsh_component_worker\ndsh_component_worker.start()\n', encoding='utf-8')
        env['HOUDINI_PATH'] = str(hooks) + os.pathsep + '&'
        command = [str(executable), '-foreground']
    else:
        command = [str(executable), str(module)]
    closing = threading.Event()
    def read_commands():
        for line in sys.stdin:
            if line.strip() == 'STOP':
                closing.set()
                return
        closing.set()
    threading.Thread(target=read_commands, daemon=True).start()
    process = None
    job = None
    try:
        with (directory / 'worker.log').open('xb') as log:
            process = subprocess.Popen(command, cwd=launch_directory(executable), env=env,
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            job = WorkerJob(process, args.memory_mb)
            if closing.is_set():
                raise RuntimeError('worker cancelled before initialization')
            (directory / 'go').touch(exist_ok=False)
            deadline = time.monotonic() + args.startup_timeout
            ready = directory / 'ready.json'
            while not ready.exists():
                if closing.is_set() or process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('component worker did not become ready; inspect worker.log')
                time.sleep(.05)
            # The writer closes ready.json before publishing complete JSON; retry
            # partial reads only here, never retry a Houdini mutation.
            while True:
                try:
                    result = json.loads(ready.read_text(encoding='utf-8'))
                    break
                except json.JSONDecodeError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.01)
            if not result['ok']:
                raise RuntimeError(result['error'])
            print(json.dumps(result), flush=True)
            while not closing.wait(.1):
                if process.poll() is not None:
                    raise RuntimeError('component worker exited unexpectedly; no restart attempted')
            (directory / 'stop').touch(exist_ok=True)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                raise RuntimeError('worker could not stop at an idle checkpoint; owned tree will be reclaimed, outcome unknown')
            if process.returncode != 0:
                raise RuntimeError('component worker exited with code ' + str(process.returncode))
    finally:
        if job:
            job.close()
        if process and process.poll() is None:
            process.kill()
            process.wait(timeout=15)


if __name__ == '__main__':
    main()
