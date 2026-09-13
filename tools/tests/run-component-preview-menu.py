"""Fresh Houdini GUI menu callback smoke with owned Host and disposable HIP."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
sys.modules.setdefault('hou', types.SimpleNamespace())
from houdini_test_environment import isolated_environment, launch_directory
import dsh_component_preview as preview

binary = str(Path(sys.argv[1]).resolve(strict=True))
for executable in sys.argv[2:]:
    houdini = Path(executable).resolve(strict=True)
    root = Path(tempfile.mkdtemp(prefix='component-preview-menu-', dir=ROOT / 'tools/out'))
    local = root / 'local'
    profile = local / 'DSH-Houdini/component-preview'
    run = profile / 'run'
    config = {'schema': 1, 'source': str(ROOT), 'bin': binary, 'python': sys.executable,
              'houdini': str(houdini), 'run': str(run),
              **{key: str(run / key) for key in ('home', 'workers', 'registry')}}
    preview._validate_config(config, profile)
    preview._ensure_profile(config, profile)
    hooks = root / 'hooks'
    for version in ('3.11', '3.13'):
        scripts = hooks / ('python' + version + 'libs')
        scripts.mkdir(parents=True)
        (scripts / 'uiready.py').write_text(
            'import sys\nsys.path.insert(0, ' + repr(str(ROOT / 'tools/tests')) + ')\n'
            'sys.path.insert(0, ' + repr(str(ROOT / 'houdini/python3.11libs')) + ')\n'
            'import dsh_component_preview_gui_fixture\ndsh_component_preview_gui_fixture.start()\n', encoding='utf-8')
    env = isolated_environment(root / 'environment', executable=houdini, gui=True)
    env['LOCALAPPDATA'] = str(local)
    env['DSH_COMPONENT_PREVIEW_GUI_FIXTURE'] = str(root)
    env['HOUDINI_PATH'] = str(hooks) + os.pathsep + str(ROOT / 'houdini') + os.pathsep + '&'
    log = (root / 'gui.log').open('wb')
    process = subprocess.Popen([str(houdini), '-foreground'], cwd=launch_directory(houdini),
                               env=env, stdout=log, stderr=subprocess.STDOUT,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 110
        while not (root / 'result.json').is_file():
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('Isolated GUI did not report its menu result; inspect fixture locally: ' + str(root))
            time.sleep(.2)
        result = json.loads((root / 'result.json').read_text(encoding='utf-8'))
        assert result['ok'], result
        assert result['frontend_owned'] and result['mode_choices'] == 1 and Path(result['hip']).is_file()
        process.wait(timeout=30)
        print('PASS', houdini.parent.parent.name, 'GUI menu callback, isolated HIP, owned Host, embedded dynamic page; no model')
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=15)
        log.close()
