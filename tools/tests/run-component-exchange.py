"""Run component regressions in disposable, environment-isolated Houdini processes."""
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from houdini_test_environment import isolated_environment, launch_directory

executables = [a for a in sys.argv[1:] if not a.startswith('--')]
for executable in executables:
    fixture = Path(tempfile.mkdtemp(prefix='dsh-component-env-'))
    for mode in (('--parameters',) if '--parameters-only' in sys.argv else (None, '--parameters', 'export', 'import', 'reopen')):
        result = subprocess.run([executable, str(Path(__file__).with_name('dsh-component-exchange.test.py'))]
                                + ([mode] if mode == '--parameters' else [mode, str(fixture)] if mode else []),
                                env=isolated_environment(fixture / (mode or 'unit'), executable=executable),
                                cwd=launch_directory(executable), timeout=120, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                creationflags=subprocess.CREATE_NO_WINDOW)
        print(result.stdout, flush=True)
        print(result.stderr, flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)
    if '--boundaries' in sys.argv:
        for test in ('dsh-bridge-raw-gate.test.py', 'dsh-node-ownership.test.py',
                     'dsh-bridge-caught-failure.test.py', 'dsh-tab-create-failure.test.py',
                     'dsh-object-parenting.test.py', 'dsh-scene-network-render-contract.test.py',
                     'dsh-output-publication.test.py', 'dsh-module-integration.test.py'):
            script = Path(__file__).with_name(test)
            if not script.is_file():
                raise FileNotFoundError(script)
            result = subprocess.run([executable, str(script)],
                                    env=isolated_environment(fixture / test, executable=executable),
                                    cwd=launch_directory(executable), timeout=180, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            print(test, result.stdout, result.stderr, flush=True)
            if result.returncode:
                raise SystemExit(result.returncode)
    script = Path(__file__).with_name('dsh-component-public-help.test.py')
    result = subprocess.run([executable, str(script)],
                            env=isolated_environment(fixture / script.name, executable=executable),
                            cwd=launch_directory(executable), timeout=120, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
    print(result.stdout, result.stderr, flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
