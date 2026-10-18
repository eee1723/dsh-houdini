"""Explicit command-line launch handshake after Houdini's GUI and HIP are ready."""
import os
from pathlib import Path
import threading


_SAVE_HOOKS = set()


def after_save(native_context, wrapper):
    """Run DSH's notification and preserve the next native save script.

    Houdini executes only the first scripts/afterscenesave.py on its search
    path. The workbench forwarder adds DSH's notification, then forwards to
    the first remaining match. That script owns any further chaining; running
    all matches here would activate normally shadowed third-party scripts.
    """
    import hou
    current = Path(wrapper).resolve()
    outermost = not _SAVE_HOOKS
    _SAVE_HOOKS.add(current)
    arguments = native_context.get('kwargs')
    errors = []
    def execute(filename):
        path = Path(filename).resolve()
        if path in _SAVE_HOOKS:
            return
        _SAVE_HOOKS.add(path)
        context = {**native_context, '__file__': str(filename),
                   'kwargs': dict(arguments) if isinstance(arguments, dict) else arguments}
        exec(compile(path.read_bytes(), str(filename), 'exec'), context)
    def run(filename):
        try:
            execute(filename)
        # Still notify the native script if the plugin notification failed.
        except BaseException as error:
            errors.append((str(filename), error))
    try:
        plugin = (Path(__file__).resolve().parents[1] / 'scripts/afterscenesave.py').resolve()
        discovered = tuple(Path(filename) for filename in hou.findFiles('scripts/afterscenesave.py'))
        run(plugin)
        for filename in discovered:
            if filename.resolve() in _SAVE_HOOKS:
                continue
            run(filename)
            break
        if any(isinstance(error, KeyboardInterrupt) for _, error in errors):
            raise KeyboardInterrupt
        if errors:
            raise RuntimeError('保存脚本执行失败：' + '；'.join(
                f'{path}：{type(error).__name__}: {error}' for path, error in errors))
    finally:
        if outermost:
            _SAVE_HOOKS.clear()


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
        # Houdini can rewrite HFS to a Windows 8.3 path. Compare the actual
        # local installation, not its spelling; HIP path policy stays separate.
        if not hou.isUIAvailable() or not Path(os.environ['HFS']).samefile(ticket['hfs']):
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
