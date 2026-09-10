"""Environment isolation for authored test processes, not a security sandbox.

Only fixture preferences/packages and explicitly selected Houdini installations
are used. Keep licensing and OS essentials; never inherit another DSH runtime,
Python hook, Qt override or model credential. Does not touch the parent's env.
"""
from pathlib import Path
import os
import re


def isolated_environment(fixture, *, executable=None, gui=False, base=None):
    fixture = Path(fixture).resolve()
    packages = fixture / 'packages'
    packages.mkdir(parents=True, exist_ok=True)
    env = {}
    for key, value in (os.environ if base is None else base).items():
        name = key.upper()
        if name == 'HOUDINI_LICENSE_SERVER':
            env[name] = value
            continue
        if (name.startswith(('HOUDINI_', 'PYTHON', 'QT_', 'QTWEBENGINE_', 'QML', 'DSH_', 'NODE_'))
                or name in {'HSITE', 'HFS', 'HHP', 'HB', 'HDSO'}
                or re.search(r'TOKEN|SECRET|PASSWORD|API_KEY|CREDENTIAL', name)):
            continue
        env[key] = value
    env.update(HOUDINI_PATH='&', HOUDINI_NO_ENV_FILE='1',
               HOUDINI_USER_PREF_DIR=str(fixture / 'prefs__HVER__'),
               HOUDINI_PACKAGE_DIR=str(packages), HOUDINI_MAXTHREADS='2',
               PYTHONNOUSERSITE='1', PYTHONIOENCODING='utf-8',
               PYTHONDONTWRITEBYTECODE='1', DSH_HOME=str(fixture / 'dsh-home'))
    if not gui:
        env['QT_QPA_PLATFORM'] = 'offscreen'
    if executable is not None:
        binary = Path(executable).resolve(strict=True)
        env['HFS'] = str(binary.parent.parent)
        # Case-insensitive environment keys on Windows; avoid duplicate PATHs
        # in injected dictionaries used by callers/tests.
        old_path = next((v for k, v in env.items() if k.upper() == 'PATH'), '')
        for key in list(env):
            if key.upper() == 'PATH':
                del env[key]
        env['PATH'] = str(binary.parent) + (os.pathsep + old_path if old_path else '')
    return env


def launch_directory(executable):
    """Match the vendor bin startup directory, including H22 Qt helper DLLs."""
    return Path(executable).resolve(strict=True).parent
