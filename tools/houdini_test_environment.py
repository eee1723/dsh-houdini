"""Environment isolation for authored test processes, not a security sandbox.

Only fixture preferences/packages and explicitly selected Houdini installations
are used. Keep licensing and OS essentials; never inherit another DSH runtime,
Python hook, Qt override or model credential. Does not touch the parent's env.
"""
from pathlib import Path
import os
import re


def windows_package_name(process_handle=None):
    """Read an owned/current process's package identity; None means unpackaged."""
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    function = kernel.GetCurrentPackageFullName if process_handle is None else kernel.GetPackageFullName
    function.argtypes = ([] if process_handle is None else [w.HANDLE]) + [ctypes.POINTER(w.DWORD), w.LPWSTR]
    function.restype = w.LONG
    size = w.DWORD()
    prefix = [] if process_handle is None else [process_handle]
    status = function(*prefix, ctypes.byref(size), None)
    if status == 15700:  # APPMODEL_ERROR_NO_PACKAGE
        return None
    if status != 122:  # ERROR_INSUFFICIENT_BUFFER
        raise ctypes.WinError(status, 'Could not read test process package identity')
    buffer = ctypes.create_unicode_buffer(size.value)
    status = function(*prefix, ctypes.byref(size), buffer)
    if status:
        raise ctypes.WinError(status, 'Could not read test process package identity')
    return buffer.value


def reexec_unpacked_test_cli():
    """Call at a test CLI entry before launching workers; ordinary CLI is a no-op.

    A Store-packaged terminal can give arbitrary descendants its MSIX identity.
    Windows then searches helper DLLs in the package graph/application directory,
    ignoring the Houdini bin entries in PATH and cwd. Re-execute this same CLI
    with the documented desktop-app policy, then retain its ordinary Popen/job
    code. No token, browser sandbox, environment, vendor file or job-breakaway
    setting is changed. The packaged wrapper exits with the child's exact code.
    """
    if windows_package_name() is None:
        return
    import sys
    for stream in (sys.stdout, sys.stderr):
        stream.flush()
    command = [sys.executable, *getattr(sys, 'orig_argv', [sys.executable, *sys.argv])[1:]]
    raise SystemExit(_run_unpacked_test_cli(command))


def _run_unpacked_test_cli(command):
    """One owned hidden CLI with inherited stdio, verified before it executes."""
    import ctypes
    from ctypes import wintypes as w
    import msvcrt
    import subprocess
    from contextlib import ExitStack

    class StartupInfo(ctypes.Structure):
        _fields_ = [('cb', w.DWORD), ('reserved', w.LPWSTR), ('desktop', w.LPWSTR), ('title', w.LPWSTR),
                    ('x', w.DWORD), ('y', w.DWORD), ('x_size', w.DWORD), ('y_size', w.DWORD),
                    ('x_chars', w.DWORD), ('y_chars', w.DWORD), ('fill', w.DWORD), ('flags', w.DWORD),
                    ('show', w.WORD), ('reserved_size', w.WORD), ('reserved_ptr', ctypes.c_void_p),
                    ('stdin', w.HANDLE), ('stdout', w.HANDLE), ('stderr', w.HANDLE)]
    class StartupInfoEx(ctypes.Structure):
        _fields_ = [('startup', StartupInfo), ('attributes', ctypes.c_void_p)]
    class ProcessInfo(ctypes.Structure):
        _fields_ = [('process', w.HANDLE), ('thread', w.HANDLE), ('pid', w.DWORD), ('tid', w.DWORD)]
    class JobBasic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64), ('flags', w.DWORD),
                    ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t), ('active', w.DWORD),
                    ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
    class JobExtended(ctypes.Structure):
        _fields_ = [('basic', JobBasic), ('io', ctypes.c_uint64 * 6), ('process_memory', ctypes.c_size_t),
                    ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    def api(name, arguments, result=w.BOOL):
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
        return function
    def require(value, operation):
        if not value:
            raise ctypes.WinError(ctypes.get_last_error(), operation)
        return value
    close = api('CloseHandle', [w.HANDLE])
    current = api('GetCurrentProcess', [], w.HANDLE)()
    get_standard = api('GetStdHandle', [w.DWORD], w.HANDLE)
    duplicate = api('DuplicateHandle', [w.HANDLE, w.HANDLE, w.HANDLE, ctypes.POINTER(w.HANDLE),
                                        w.DWORD, w.BOOL, w.DWORD])
    initialize = api('InitializeProcThreadAttributeList', [ctypes.c_void_p, w.DWORD, w.DWORD,
                                                         ctypes.POINTER(ctypes.c_size_t)])
    update = api('UpdateProcThreadAttribute', [ctypes.c_void_p, w.DWORD, ctypes.c_size_t,
                                              ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p])
    delete_attributes = api('DeleteProcThreadAttributeList', [ctypes.c_void_p], None)
    create = api('CreateProcessW', [w.LPCWSTR, w.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, w.BOOL,
                                    w.DWORD, ctypes.c_void_p, w.LPCWSTR, ctypes.POINTER(StartupInfoEx),
                                    ctypes.POINTER(ProcessInfo)])
    wait = api('WaitForSingleObject', [w.HANDLE, w.DWORD], w.DWORD)
    terminate = api('TerminateProcess', [w.HANDLE, w.UINT])
    resume = api('ResumeThread', [w.HANDLE], w.DWORD)
    exit_code = api('GetExitCodeProcess', [w.HANDLE, ctypes.POINTER(w.DWORD)])
    create_job = api('CreateJobObjectW', [ctypes.c_void_p, w.LPCWSTR], w.HANDLE)
    set_job = api('SetInformationJobObject', [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD])
    assign_job = api('AssignProcessToJobObject', [w.HANDLE, w.HANDLE])
    info, job, attributes, handles = ProcessInfo(), None, None, []
    with ExitStack() as resources:
        try:
            for number, mode in ((-10, 'rb'), (-11, 'wb'), (-12, 'wb')):
                source = get_standard(number)
                if source in (None, 0, ctypes.c_void_p(-1).value):
                    fallback = resources.enter_context(open(os.devnull, mode))
                    source = msvcrt.get_osfhandle(fallback.fileno())
                inherited = w.HANDLE()
                require(duplicate(current, source, current, ctypes.byref(inherited), 0, True, 2),
                        'Could not inherit test CLI standard stream')
                handles.append(inherited.value)
            size = ctypes.c_size_t()
            initialize(None, 2, 0, ctypes.byref(size))
            buffer = ctypes.create_string_buffer(size.value)
            require(initialize(buffer, 2, 0, ctypes.byref(size)), 'Could not initialize test launch attributes')
            attributes = buffer
            policy = w.DWORD(1)  # PROCESS_CREATION_DESKTOP_APP_BREAKAWAY_ENABLE_PROCESS_TREE
            require(update(attributes, 0, 0x20012, ctypes.byref(policy), ctypes.sizeof(policy), None, None),
                    'Could not select unpackaged desktop-app test runtime')
            inherited_handles = (w.HANDLE * len(handles))(*handles)
            require(update(attributes, 0, 0x20002, inherited_handles, ctypes.sizeof(inherited_handles), None, None),
                    'Could not restrict test CLI handle inheritance')
            startup = StartupInfoEx()
            startup.startup.cb = ctypes.sizeof(startup)
            startup.startup.flags = 0x100  # STARTF_USESTDHANDLES
            startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = handles
            startup.attributes = ctypes.addressof(attributes)
            job = require(create_job(None, None), 'Could not create test wrapper process-tree owner')
            limits = JobExtended()
            limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE; no breakaway or resource cap
            require(set_job(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)), 'Could not own test wrapper descendants')
            line = ctypes.create_unicode_buffer(subprocess.list2cmdline(command))
            # Suspend only our new child until package identity and ownership
            # are checked. Never attach to, adopt or terminate an existing PID.
            require(create(command[0], line, None, None, True, 0x80000 | 0x08000000 | 4,
                           None, os.getcwd(), ctypes.byref(startup), ctypes.byref(info)),
                    'Could not re-execute test CLI outside the packaged runtime')
            require(assign_job(job, info.process), 'Could not own re-executed test process tree')
            if windows_package_name(info.process) is not None:
                raise RuntimeError('Test CLI still has a package identity; refusing recursive re-execution')
            if resume(info.thread) == 0xffffffff:
                raise ctypes.WinError(ctypes.get_last_error(), 'Could not resume owned test CLI')
            while True:
                status = wait(info.process, 100)
                if status == 0:
                    break
                if status != 258:
                    raise ctypes.WinError(ctypes.get_last_error(), 'Could not wait for owned test CLI')
            code = w.DWORD()
            require(exit_code(info.process, ctypes.byref(code)), 'Could not read test CLI exit code')
            return ctypes.c_int32(code.value).value
        except BaseException:
            if info.process:
                terminate(info.process, 1)
                wait(info.process, 5000)
            raise
        finally:
            if job:
                close(job)  # Also removes any remaining owned descendants.
            for handle in (info.thread, info.process, *handles):
                if handle:
                    close(handle)
            if attributes is not None:
                delete_attributes(attributes)


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
