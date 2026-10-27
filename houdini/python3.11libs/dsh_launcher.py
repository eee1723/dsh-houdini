"""Houdini-side Bridge maintenance and official DSH Desktop menu shortcuts.

This process never owns a DSH Host or a browser shell. The in-process Bridge
continues to serialize all HOM work on Houdini's main thread.
"""
from __future__ import annotations
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import hou

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
BRIDGE_HOST = '127.0.0.1'
BRIDGE_PORT = 0
_FALLBACK_WORKSPACE = str(Path(tempfile.gettempdir()) / 'dsh-houdini/workspaces')
_UNSAVED_WORKSPACE = globals().get('_UNSAVED_WORKSPACE')
_PROBLEM_WINDOW = None
_LAST_STARTUP_FAILURE = None
_HELPER_SWITCH_TIMER = None

def _hip_dir() -> str:
    """Resolve the current scene's workspace on Houdini's main thread.

    Unsaved scenes share this process's stable scratch workspace. Opening a
    named HIP selects its directory and retires the scratch reference, so the
    next unsaved workspace starts fresh. No HIP callbacks or scene writes.
    The native DSH client receives this explicit intent even with a warm Host.
    """
    global _UNSAVED_WORKSPACE
    from dsh_context import hip_file_identity
    hip = hip_file_identity()
    if hip['hip_dir']:
        _UNSAVED_WORKSPACE = None
        return hip['hip_dir']
    if _UNSAVED_WORKSPACE is None:
        os.makedirs(_FALLBACK_WORKSPACE, exist_ok=True)
        _UNSAVED_WORKSPACE = tempfile.mkdtemp(
            prefix=f"untitled-{os.getpid()}-", dir=_FALLBACK_WORKSPACE)
    return _UNSAVED_WORKSPACE


def _module_path_on_syspath() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.append(here)


def restart_bridge(*, port=None) -> str:
    """Main thread: stop/reload/start the in-process bridge without probing ports."""
    _module_path_on_syspath()
    target_port = BRIDGE_PORT if port is None else port
    if type(target_port) is not int or not (target_port == 0 or 1024 <= target_port <= 65535):
        raise ValueError('连接端口无效，请检查组件设置。')
    import dsh_bridge

    # Recheck on the owning thread: the worker's HTTP snapshot may already be old.
    # This uses only in-process counters; no socket/process probe on the GUI thread.
    registry = getattr(dsh_bridge, '_request_registry', None)
    activity = getattr(dsh_bridge, '_job_activity', None)
    if registry is None or not callable(activity):
        raise RuntimeError('当前连接无法安全修复。请先保存工程，再关闭并重新打开这个 Houdini 窗口。\n原因：连接未提供修复所需的活动状态。')
    jobs = activity().get('activeJobs')
    requests = registry.active_count()
    if (type(jobs) is not int or type(requests) is not int or jobs != 0 or requests != 0
            or not dsh_bridge._work_queue.empty()):
        raise RuntimeError('Houdini 仍有操作未完成，请等操作结束后再修复连接。\n本次未重启连接或重载模块。')
    dsh_bridge.stop()                      # 停进程内旧 server（线程）
    # Dependency order is explicit; helpers is the public export facade and
    # execution binds its functions only after every implementation is refreshed.
    # Ownership retains native identities across this idle, same-process repair.
    for module_name in (
        'dsh_errors',
        'dsh_service_constants',
        'dsh_node_access',
        'dsh_view_state',
        'dsh_code_analysis',
        'dsh_cook_control',
        'dsh_project_paths',
        'dsh_execution_results',
        'dsh_package_discovery',
        'dsh_geometry_observation',
        'dsh_bgeo_fingerprint',
        'dsh_image_pixels',
        'dsh_network_layout',
        'dsh_operation_cards',
        'dsh_requests',
        'dsh_ownership',
        'dsh_recovery_store',
        'dsh_load_warnings',
        'dsh_scene_recovery',
        'dsh_parameter_templates',
        'dsh_usd_inspection',
        'dsh_context',
        'dsh_preview_paths',
        'dsh_tool_packages',
        'dsh_geometry_evidence',
        'dsh_geometry_queries',
        'dsh_hda_interfaces',
        'dsh_node_types',
        'dsh_parameter_values',
        'dsh_tool_catalog',
        'dsh_modeling_units',
        'dsh_network_navigation',
        'dsh_scene',
        'dsh_hda_lifecycle',
        'dsh_hda_versions',
        'dsh_hda_sections',
        'dsh_camera_framing',
        'dsh_control_bindings',
        'dsh_keyframes',
        'dsh_parameter_ui',
        'dsh_network_boxes',
        'dsh_media_output',
        'dsh_hda_operations',
        'dsh_spare_parameters',
        'dsh_network_notes',
        'dsh_render_service',
        'dsh_ui_capture',
        'dsh_viewport',
        'dsh_node_layout',
        'dsh_render',
        'dsh_node_creation',
        'dsh_node_operations',
        'dsh_cop_contracts',
        'dsh_node_inspection',
        'dsh_quality_contracts',
        'dsh_curve_paths',
        'dsh_procedural_plans',
        'dsh_sop_contracts',
        'dsh_component_contracts',
        'dsh_hou_helpers',
        'dsh_execution',
    ):
        importlib.reload(importlib.import_module(module_name))
    importlib.reload(dsh_bridge)           # 拾取最新 bridge
    server = dsh_bridge.start(target_port, BRIDGE_HOST)
    return f"bridge restarted on {BRIDGE_HOST}:{server.server_port}"


def _report(detail):
    print('[dsh-houdini] ' + str(detail).replace('\n', '; '))


def require_local_modules():
    """An already loaded helper generation cannot be hot-mixed with another."""
    root = Path(__file__).resolve().parent
    for name in ('dsh_deployment', 'dsh_managed_runtime', 'dsh_executor_registry', 'dsh_bridge',
                 'dsh_execution', 'dsh_scene_recovery', 'dsh_workbench_client', 'dsh_workbench_entry'):
        module = sys.modules.get(name)
        filename = getattr(module, '__file__', None)
        if filename and not Path(filename).resolve().is_relative_to(root):
            raise RuntimeError('当前窗口的连接组件来自不同位置。请先保存工程，再关闭并重新打开这个 Houdini 窗口。\n模块：' + name + '\n加载位置：' + str(filename) + '\n预期位置：' + str(root))
    state = sys.modules.get('dsh_deployment')
    if state is not None and any(not callable(getattr(state, name, None))
                                 for name in ('FileLease', 'atomic_json', '_process_started')):
        raise RuntimeError('当前窗口仍在使用旧版连接组件。请先保存工程，再关闭并重新打开这个 Houdini 窗口。\n原因：旧版连接模块 dsh_deployment 缺少当前接口；未重载原模块。')


def _startup_failure(error):
    global _PROBLEM_WINDOW, _LAST_STARTUP_FAILURE
    detail = str(error) or repr(error)
    _LAST_STARTUP_FAILURE = detail
    _report(error)
    if hou.isUIAvailable():
        from dsh_ui_style import show_startup_problem
        _PROBLEM_WINDOW = show_startup_problem(detail.splitlines()[0], detail, hou.qt.mainWindow())


def open_workspace():
    try:
        require_local_modules()
        from dsh_workbench_client import open_workspace as open_desktop
        open_desktop(sys.modules[__name__])
    except Exception as error:
        _startup_failure(error)


def repair_current_runtime():
    try:
        require_local_modules()
        from dsh_workbench_client import open_workspace as open_desktop
        open_desktop(sys.modules[__name__], reload=True)
    except Exception as error:
        _startup_failure(error)


def show_plugin_info():
    manifest = Path(_PROJECT_ROOT) / 'package.json'
    try:
        version = json.loads(manifest.read_text(encoding='utf-8')).get('version', 'unknown')
    except (OSError, ValueError):
        version = 'unknown'
    selected = hou.ui.displayMessage(
        'Houdini 连接组件 ' + version + '\n\n'
        '“修复当前连接”只重启这个窗口的连接，工程保持不变。\n'
        '更新或切换组件版本后，请保存并重开这个 Houdini 窗口。',
        title='DSH-Houdini', buttons=('打开对话', '修复当前连接', '切换组件版本…', '移除本机组件…', '诊断…', '关闭'),
        default_choice=5, close_choice=5,
        details='当前加载位置：' + _PROJECT_ROOT + '\n对话、模型和插件更新在 DSH Desktop 中管理。\n组件版本切换在下次打开 Houdini 时生效，不替换当前已加载的 Python 模块。\n移除本机组件会停用菜单登记，保留组件文件和用户数据；完整卸载还需在 Desktop 插件页卸载插件。')
    if selected == 0:
        open_workspace()
    elif selected == 1:
        repair_current_runtime()
    elif selected == 2:
        select_helper_version()
    elif selected == 3:
        remove_local_components()
    elif selected == 4:
        show_connection_diagnostics()


def show_connection_diagnostics():
    from dsh_connection_diagnostics import show
    return show(sys.modules[__name__])


def _begin_helper_maintenance(script_name, state, on_ready):
    """One bounded worker and a native idle timer for local helper maintenance."""
    global _HELPER_SWITCH_TIMER
    if _HELPER_SWITCH_TIMER is not None:
        return None
    root = os.environ.get('DSH_HOUDINI_INSTALL_ROOT')
    script = Path(_PROJECT_ROOT) / 'installer' / script_name
    if not root or not Path(root).is_absolute():
        _startup_failure('当前窗口没有组件安装信息。请在 Desktop 的 Houdini 模式安装组件，再保存并重开这个窗口。')
        return None
    import subprocess
    import threading
    from hutil.Qt import QtCore
    powershell = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
    active = True

    def execute(arguments):
        try:
            if not script.is_file():
                raise RuntimeError('组件维护文件不完整。请在 Desktop 的 Houdini 模式重新安装组件。\n缺少文件：' + str(script))
            if script_name == 'uninstall.ps1':
                import re
                helper = Path(_PROJECT_ROOT).resolve()
                if helper.parent != Path(root).resolve() / 'helpers' or not re.fullmatch('[0-9a-f]{16}', helper.name):
                    raise RuntimeError('无法确认这个窗口的组件安装位置，未移除任何组件。请先保存并重开 Houdini，再试一次。\n诊断：当前目录不属于该安装根的不可变 helper。\n当前目录：' + str(helper) + '\n安装根：' + root)
            result = subprocess.run([powershell, '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-File', str(script), '-Root', root, *arguments], cwd=_PROJECT_ROOT,
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout).strip())
            state['output'] = result.stdout
        except Exception as error:
            state['error'] = str(error)
        finally:
            state['ready'] = True

    def close():
        nonlocal active
        global _HELPER_SWITCH_TIMER
        active = False
        timer.stop()
        if callable(getattr(timer, 'deleteLater', None)):
            timer.deleteLater()
        if _HELPER_SWITCH_TIMER is timer:
            _HELPER_SWITCH_TIMER = None

    def submit(arguments):
        state.update(ready=False)
        state.pop('error', None)
        threading.Thread(target=lambda: execute(arguments), daemon=True).start()

    def tick():
        if not active or not state.get('ready'):
            return
        if state.get('error'):
            close()
            _startup_failure(state['error'])
            return
        try:
            on_ready(state, submit, close)
        except Exception as error:
            close()
            _startup_failure(error)

    timer = QtCore.QTimer(hou.qt.mainWindow())
    _HELPER_SWITCH_TIMER = timer
    timer.timeout.connect(tick)
    timer.start(100)
    return submit


def select_helper_version():
    """Explicitly select retained helpers for the next Houdini start, never hot-swap."""
    def ready(state, submit, close):
        if state['phase'] == 'list':
            rows = [row for row in json.loads(state['output']) if row.get('valid')]
            if not rows:
                raise RuntimeError('没有可切换的完整组件版本。请先在 Desktop 的 Houdini 模式重新安装组件。')
            labels = [str(row.get('version') or '未知版本') + ('（当前加载）' if Path(row['path']) == Path(_PROJECT_ROOT) else '') for row in rows]
            chosen = hou.ui.selectFromList(labels, exclusive=True, title='选择下次启动使用的 Houdini 连接版本',
                message='选择后在下次打开 Houdini 时生效。当前工程保持不变，完成后请保存并重开这个窗口。')
            if not chosen:
                close()
                return
            state['phase'] = 'select'
            submit(['-SelectHelper', rows[chosen[0]]['id']])
        else:
            close()
            hou.ui.displayMessage('已选择组件版本。保存工程并重开这个 Houdini 窗口后生效。', title='DSH-Houdini', details=state['output'])

    submit = _begin_helper_maintenance('install.ps1', {'phase': 'list'}, ready)
    if submit is not None:
        submit(['-ListHelpers'])


def remove_local_components():
    """Unregister this installed helper only; the current process keeps running."""
    if _HELPER_SWITCH_TIMER is not None:
        return
    selected = hou.ui.displayMessage(
        '移除本机 Houdini 组件？\n\n'
        '下次打开 Houdini 后不再显示本插件菜单。当前窗口继续使用，组件文件、工程和历史均保留。\n'
        '完整卸载还需到 Desktop 插件页卸载插件；从仍启用插件的 Desktop 新开 Houdini 会重新安装组件。',
        title='DSH-Houdini', buttons=('移除组件', '取消'), default_choice=1, close_choice=1,
        details='当前加载位置：' + _PROJECT_ROOT + '\n此操作只解除本机 Package 登记，不结束 Houdini 或 Desktop，不删除凭据、会话、HIP、旧运行包或组件版本。')
    if selected != 0:
        return

    def ready(state, submit, close):
        close()
        hou.ui.displayMessage(
            '本机组件已停用。下次打开 Houdini 后不再显示菜单，当前工程可继续使用。\n'
            '如需完整卸载，请到 Desktop 插件页卸载插件。',
            title='DSH-Houdini', details=state['output'])

    submit = _begin_helper_maintenance('uninstall.ps1', {}, ready)
    if submit is not None:
        submit([])


def launch():
    open_workspace()
