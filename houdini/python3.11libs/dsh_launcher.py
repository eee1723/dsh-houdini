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
        raise ValueError('Invalid Bridge restart port')
    import dsh_bridge

    # Recheck on the owning thread: the worker's HTTP snapshot may already be old.
    # This uses only in-process counters; no socket/process probe on the GUI thread.
    registry = getattr(dsh_bridge, '_request_registry', None)
    activity = getattr(dsh_bridge, '_job_activity', None)
    if registry is None or not callable(activity):
        raise RuntimeError('Bridge cannot verify restart safety; fully reopen Houdini after saving your work')
    jobs = activity().get('activeJobs')
    requests = registry.active_count()
    if (type(jobs) is not int or type(requests) is not int or jobs != 0 or requests != 0
            or not dsh_bridge._work_queue.empty()):
        raise RuntimeError('Bridge restart deferred: scene work arrived after preflight; no modules were reloaded')
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
            raise RuntimeError('当前 Houdini 已加载另一版本的连接模块。请先保存工程并完整退出此 Houdini，再重新打开；未混用或重载原模块。')
    state = sys.modules.get('dsh_deployment')
    if state is not None and any(not callable(getattr(state, name, None))
                                 for name in ('FileLease', 'atomic_json', '_process_started')):
        raise RuntimeError('当前 Houdini 仍保留旧版连接模块。请先保存并重开此 Houdini；不能在同一进程内混合升级或回退。')


def _startup_failure(error):
    global _PROBLEM_WINDOW, _LAST_STARTUP_FAILURE
    _LAST_STARTUP_FAILURE = str(error)
    _report(error)
    if hou.isUIAvailable():
        from dsh_ui_style import show_startup_problem
        _PROBLEM_WINDOW = show_startup_problem(str(error), str(error), hou.qt.mainWindow())


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
        'Houdini 连接插件 ' + version + '\n\n'
        '对话、模型、工作区和插件更新由官方 DSH Desktop 管理。\n'
        'Houdini 已加载的 Python 代码保持到退出；更新菜单或 Package 后请保存并重开本端。\n'
        '“修复当前连接”只重新加载本 Houdini 的 Bridge，不重启 Desktop 或其他工程。\n'
        '已安装的连接版本可以明确切换或回退，保存并重开 Houdini 后生效。\n'
        '卸载时可先移除本机组件，再到 Desktop 插件页卸载插件；当前工程和全部用户数据保留。',
        title='DSH-Houdini', buttons=('打开 Desktop', '修复当前连接', '切换连接版本…', '移除本机组件…', '关闭'),
        default_choice=4, close_choice=4,
        details='当前 helper：' + _PROJECT_ROOT)
    if selected == 0:
        open_workspace()
    elif selected == 1:
        repair_current_runtime()
    elif selected == 2:
        select_helper_version()
    elif selected == 3:
        remove_local_components()


def _begin_helper_maintenance(script_name, state, on_ready):
    """One bounded worker and a native idle timer for local helper maintenance."""
    global _HELPER_SWITCH_TIMER
    if _HELPER_SWITCH_TIMER is not None:
        return None
    root = os.environ.get('DSH_HOUDINI_INSTALL_ROOT')
    script = Path(_PROJECT_ROOT) / 'installer' / script_name
    if not root or not Path(root).is_absolute():
        _startup_failure('当前窗口没有已安装组件的登记信息。请在 Desktop 的 Houdini 模式准备组件，再保存并重开本窗口。')
        return None
    import subprocess
    import threading
    from hutil.Qt import QtCore
    powershell = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
    active = True

    def execute(arguments):
        try:
            if not script.is_file():
                raise RuntimeError('当前 helper 缺少维护脚本。请在 Desktop 的 Houdini 模式重新准备组件。')
            if script_name == 'uninstall.ps1':
                import re
                helper = Path(_PROJECT_ROOT).resolve()
                if helper.parent != Path(root).resolve() / 'helpers' or not re.fullmatch('[0-9a-f]{16}', helper.name):
                    raise RuntimeError('当前窗口没有从该安装根的不可变 helper 加载；未移除任何组件。请保存并重开安装后的 Houdini。')
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
                raise RuntimeError('没有可选择的完整 helper 快照。请在 Desktop 的 Houdini 模式重新准备组件。')
            labels = [str(row.get('version') or '未知版本') + ('（当前加载）' if Path(row['path']) == Path(_PROJECT_ROOT) else '') for row in rows]
            chosen = hou.ui.selectFromList(labels, exclusive=True, title='选择下次启动使用的 Houdini 连接版本',
                message='此操作仅切换本端连接。请保存并重开 Houdini，不在当前进程内混合升级或回退。')
            if not chosen:
                close()
                return
            state['phase'] = 'select'
            submit(['-SelectHelper', rows[chosen[0]]['id']])
        else:
            close()
            hou.ui.displayMessage('已选择连接版本。请先保存工程，再完整退出并重开此 Houdini。当前已加载的模块、工程和 Desktop 会话均保持不变。', title='DSH-Houdini')

    submit = _begin_helper_maintenance('install.ps1', {'phase': 'list'}, ready)
    if submit is not None:
        submit(['-ListHelpers'])


def remove_local_components():
    """Unregister this installed helper only; the current process keeps running."""
    if _HELPER_SWITCH_TIMER is not None:
        return
    selected = hou.ui.displayMessage(
        '移除本机 Houdini 组件？\n\n'
        '仅停用本插件的菜单和连接登记，下次启动 Houdini 后生效。\n'
        '当前 Houdini、工程、Bridge 和 Desktop 继续运行；旧运行包、凭据、会话和 HIP 全部保留。\n'
        '之后可到 Desktop 插件页卸载插件。若继续从 Desktop 新开 Houdini，组件会按正常流程重新准备。',
        title='DSH-Houdini', buttons=('移除组件', '取消'), default_choice=1, close_choice=1,
        details='当前 helper：' + _PROJECT_ROOT)
    if selected != 0:
        return

    def ready(state, submit, close):
        close()
        hou.ui.displayMessage(
            '本机组件已解除登记。当前窗口与工程保持不变；保存并重新打开后菜单移除。\n'
            '可继续到 Desktop 插件页卸载插件，所有 helper、旧数据、会话和 HIP 均保留。',
            title='DSH-Houdini', details=state['output'])

    submit = _begin_helper_maintenance('uninstall.ps1', {}, ready)
    if submit is not None:
        submit([])


def launch():
    open_workspace()
