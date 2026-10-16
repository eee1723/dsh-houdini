"""Explicit command-line launch handshake after Houdini's GUI and HIP are ready."""
import os
from pathlib import Path
import threading


_SAVE_HOOKS = set()


def after_save(native_context, wrapper):
    import hou
    current = Path(wrapper).resolve()
    if current in _SAVE_HOOKS:
        return
    _SAVE_HOOKS.add(current)
    def execute(filename):
        arguments = native_context.get('kwargs')
        context = {**native_context, '__file__': str(filename),
                   'kwargs': dict(arguments) if isinstance(arguments, dict) else arguments}
        exec(compile(filename.read_bytes(), str(filename), 'exec'), context)
    try:
        original = next((Path(filename).resolve() for filename in hou.findFiles('scripts/afterscenesave.py')
                         if Path(filename).resolve() not in _SAVE_HOOKS), None)
        try:
            execute(Path(__file__).resolve().parents[1] / 'scripts/afterscenesave.py')
        finally:
            if original is not None:
                execute(original)
    finally:
        _SAVE_HOOKS.remove(current)


def attach():
    import hou
    import sys
    from dsh_deployment import read_json
    from dsh_workbench import running, control
    from dsh_workbench_projects import path_key
    ticket_path = os.environ.pop('DSH_HOUDINI_LAUNCH_TICKET', None)
    if not ticket_path:
        raise RuntimeError('没有收到工作台启动请求。')
    ticket = read_json(Path(ticket_path))
    root = Path(ticket['root']).resolve()
    if Path(ticket_path).resolve().parent != root / 'workbench/launches':
        raise RuntimeError('启动请求不属于当前工作台。')
    def report(error):
        record = running(root)
        if record and record['generation'] == ticket['generation']:
            control(record, 'projects/failed', {'id': ticket['id'], 'error': str(error)}, timeout=10)
    try:
        for name in ('dsh_bridge', 'dsh_launcher'):
            module = sys.modules.get(name)
            if module and not Path(module.__file__).resolve().is_relative_to(Path(ticket['plugin']).resolve()):
                raise RuntimeError('Houdini 已加载另一个插件版本，未混用运行环境。')
        if not hou.isUIAvailable() or path_key(os.environ['HFS']) != path_key(ticket['hfs']):
            raise RuntimeError('启动的 Houdini 与选择的版本不一致。')
        if ticket['hip'] and (hou.hipFile.isNewFile() or path_key(hou.hipFile.path()) != path_key(ticket['hip'])):
            raise RuntimeError('Houdini 没有打开所选工程；原对话未换绑。请检查文件和加载提示。')
        import dsh_launcher
        bootstrap = sys.modules.get('dsh_bootstrap')
        if dsh_launcher._MANAGED and bootstrap is not None:
            if bootstrap._PINNED != dsh_launcher._MANAGED['installId']:
                raise RuntimeError('Houdini 的安装版本选择与工作台不同，请先退出工作台后再使用新版。')
            bootstrap._CONTEXT = dsh_launcher._MANAGED
        from dsh_shared_executor import prepare_registration, publish_registration
        from dsh_workbench_client import install_observation
        if not ticket['hip']:
            dsh_launcher._UNSAVED_WORKSPACE = ticket['workspace']
        facts = prepare_registration(workbench=True, workspace=ticket['workspace'])
        install_observation()
        def finish():
            try:
                record = running(root)
                if not record or record['generation'] != ticket['generation']:
                    raise RuntimeError('工作台已退出或重开。请从此 Houdini 的 Open Workspace 重新连接。')
                registration = publish_registration(os.environ['DSH_HOUDINI_EXECUTOR_REGISTRY'], facts)
                control(record, 'projects/attached', {'id': ticket['id'], 'executorId': facts['executor_id'],
                    'registrationId': registration['registration_id'], 'expectedHip': facts['hip']})
            except Exception as error:
                report(error)
        threading.Thread(target=finish, daemon=True).start()
    except Exception as error:
        threading.Thread(target=lambda message=str(error): report(message), daemon=True).start()
