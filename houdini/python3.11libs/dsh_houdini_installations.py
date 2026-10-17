"""Installed Windows Houdini discovery without starting Houdini or importing HOM."""
from pathlib import Path
import ctypes
import os


def installation(hfs):
    hfs = Path(hfs).resolve()
    executable = hfs / 'bin/houdini.exe'
    if not executable.is_file():
        raise ValueError('所选目录没有 Houdini 程序。')
    library = ctypes.WinDLL('version', use_last_error=True)
    library.GetFileVersionInfoSizeW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p]
    library.GetFileVersionInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
    library.VerQueryValueW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint)]
    size = library.GetFileVersionInfoSizeW(str(executable), None)
    if not size:
        raise ValueError('无法读取 Houdini 版本。')
    data = ctypes.create_string_buffer(size)
    pointer, length = ctypes.c_void_p(), ctypes.c_uint()
    if not library.GetFileVersionInfoW(str(executable), 0, size, data) or not library.VerQueryValueW(data, '\\', ctypes.byref(pointer), ctypes.byref(length)):
        raise ValueError('无法确认 Houdini 程序版本。')
    info = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32 * 13)).contents
    version = [info[2] >> 16, info[2] & 65535, (info[3] >> 16) or (info[3] & 65535)]
    if version[:2] not in ([21, 0], [22, 0]):
        raise ValueError('当前工作台支持 Houdini 21.0 和 22.0。')
    python = next((candidate for candidate in hfs.glob('python3*/python.exe') if candidate.is_file()), None)
    if python is None:
        raise ValueError('Houdini 的 Python 运行环境不完整。')
    return {'hfs': str(hfs), 'executable': str(executable), 'python': str(python),
            'version': '.'.join(map(str, version)), 'series': '.'.join(map(str, version[:2]))}


def discover(preferred=None):
    candidates = [preferred, os.environ.get('HFS')]
    if os.name == 'nt':
        import winreg
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Side Effects Software', 0, winreg.KEY_READ | view) as parent:
                    for index in range(winreg.QueryInfoKey(parent)[0]):
                        name = winreg.EnumKey(parent, index)
                        if not name.startswith('Houdini '):
                            continue
                        try:
                            with winreg.OpenKey(parent, name) as child:
                                candidates.append(winreg.QueryValueEx(child, 'InstallPath')[0])
                        except OSError:
                            pass
            except OSError:
                pass
    standard = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Side Effects Software'
    if standard.is_dir():
        candidates.extend(standard.glob('Houdini *'))
    result, seen = [], set()
    for candidate in candidates:
        if not candidate or os.path.normcase(str(Path(candidate).resolve())) in seen:
            continue
        seen.add(os.path.normcase(str(Path(candidate).resolve())))
        try:
            result.append(installation(candidate))
        except (OSError, ValueError):
            pass
    return result


def _write_startup_hook(path, text):
    """Publish a startup hook only when complete; the spawned Houdini executes it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    os.replace(temporary, path)


def launch_environment(hfs, plugin, context, ticket):
    env = dict(os.environ)
    previous = env.get('HFS')
    python_paths = [part for part in env.get('PYTHONPATH', '').split(os.pathsep) if part
                    and (not previous or not os.path.normcase(part).startswith(os.path.normcase(previous) + os.sep))]
    startup = Path(ticket).with_suffix('')
    for version in ('3.11', '3.13'):
        hook = startup / ('python' + version + 'libs/uiready.py')
        _write_startup_hook(hook, 'from hutil.Qt import QtCore\nfrom dsh_workbench_entry import attach\nQtCore.QTimer.singleShot(0, attach)\n')
    save_hook = startup / 'scripts/afterscenesave.py'
    _write_startup_hook(save_hook, 'from dsh_workbench_entry import after_save\nafter_save(globals(), '
                        + repr(str(save_hook)) + ')\n')
    for key in list(env):
        if key.upper().startswith(('QT_', 'QTWEBENGINE_', 'QML', 'PYSIDE', 'SHIBOKEN')) or key in (
                'PYTHONHOME', 'PYTHONPATH', 'HFS', 'HB', 'HH', 'HHP', 'HHC', 'HDSO',
                'DSH_HOUDINI_EXECUTOR_ID', 'DSH_HOUDINI_BRIDGE_URL'):
            env.pop(key, None)
    paths = [part for part in env.get('PATH', '').split(os.pathsep)
             if part and (not previous or not os.path.normcase(part).startswith(os.path.normcase(previous) + os.sep))]
    env.update(HFS=str(hfs), PATH=str(Path(hfs) / 'bin') + os.pathsep + os.pathsep.join(paths),
               HOUDINI_PATH=str(startup) + os.pathsep + env.get('HOUDINI_PATH', '&'),
               PYTHONPATH=os.pathsep.join([str(Path(plugin) / 'houdini/python3.11libs'), *python_paths]),
               DSH_HOUDINI_LAUNCH_TICKET=str(ticket), DSH_HOUDINI_WORKBENCH_ROOT=context['root'],
               DSH_HOUDINI_WORKBENCH_CONTEXT=context['contextFile'], DSH_HOUDINI_EXECUTOR_REGISTRY=context['executorRegistry'],
               PYTHONDONTWRITEBYTECODE='1')
    if context.get('install'):
        env['DSH_HOUDINI_MANAGED_CONTEXT'] = context['contextFile']
    else:
        env.pop('DSH_HOUDINI_MANAGED_CONTEXT', None)
    return env
