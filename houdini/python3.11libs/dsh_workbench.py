"""Independent desktop lifetime and authenticated local activation, without HOM."""
from __future__ import annotations

import argparse
import hmac
import json
import os
from pathlib import Path
import queue
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dsh_deployment import FileLease, LeaseBusyError, Store, _process_started, atomic_json, read_json, runtime_env


def desktop_environment(hfs, python, debug_port=None):
    hfs, python = Path(hfs), Path(python)
    env = dict(os.environ)
    for key in list(env):
        if key.upper().startswith(('QT_', 'QTWEBENGINE_', 'QML', 'PYSIDE', 'SHIBOKEN')):
            env.pop(key)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH',
                'QTWEBENGINEPROCESS_PATH', 'QTWEBENGINE_RESOURCES_PATH', 'QTWEBENGINE_LOCALES_PATH'):
        env.pop(key, None)
    env.update(HFS=str(hfs), PYTHONDONTWRITEBYTECODE='1',
               QT_QPA_PLATFORM='windows',
               PYTHONPATH=str(python.parent / 'lib/site-packages-forced'),
               PATH=str(hfs / 'bin') + os.pathsep + env.get('PATH', ''),
               QT_PLUGIN_PATH=str(hfs / 'qt/plugins'),
               QTWEBENGINEPROCESS_PATH=str(hfs / 'qt/bin/QtWebEngineProcess.exe'),
               QTWEBENGINE_RESOURCES_PATH=str(hfs / 'qt/resources'),
               QTWEBENGINE_LOCALES_PATH=str(hfs / 'qt/translations/qtwebengine_locales'))
    if debug_port is not None:
        if type(debug_port) is not int or not 1024 <= debug_port <= 65535:
            raise ValueError('Invalid explicit desktop debug port')
        env['QTWEBENGINE_REMOTE_DEBUGGING'] = '127.0.0.1:' + str(debug_port)
    return env


def control(record, action, payload=None, timeout=120):
    request = urllib.request.Request('http://127.0.0.1:' + str(record['controlPort']) + '/' + action,
        data=json.dumps(payload or {}).encode(), headers={'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + record['token']}, method='POST')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        value = json.load(response)
    if value.get('generation') != record['generation']:
        raise RuntimeError('工作台启动身份已变化，请重新打开工作区。')
    if not value.get('ok'):
        raise RuntimeError(value.get('error', '工作台没有完成此操作。'))
    return value['result']


def running(root):
    filename = Path(root) / 'workbench/desktop.json'
    try:
        if filename.stat().st_size > 32768:
            raise ValueError('工作台登记超过读取范围。')
        record = read_json(filename)
    except FileNotFoundError:
        return None
    if (record.get('schema') != 1 or type(record.get('pid')) is not int
            or not isinstance(record.get('processStarted'), str)
            or not isinstance(record.get('token'), str) or len(record['token']) != 64
            or type(record.get('controlPort')) is not int or not 1024 <= record['controlPort'] <= 65535):
        raise RuntimeError('工作台登记损坏；未连接其他程序，也未结束任何进程。')
    if _process_started(record['pid']) != record['processStarted']:
        return None
    return record


def reject_legacy_frontend(marker):
    marker = Path(marker)
    if marker.is_file():
        record = read_json(marker)
        if type(record.get('pid')) is int and _process_started(record['pid']) is not None:
            raise RuntimeError('旧版内嵌工作区的后台可能仍在运行。请先保存任务并正常退出原 Houdini，再打开独立工作台；没有启动第二个后台或结束原进程。')


def ensure(config):
    root = Path(config['root'])
    root.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 150
    while True:
        try:
            lease = FileLease(root / 'workbench/start.lock')
            break
        except LeaseBusyError:
            if time.monotonic() >= deadline:
                raise RuntimeError('工作台仍在启动，请稍后重试；没有重复启动后台。')
            time.sleep(.1)
    try:
        record = running(root)
        if record:
            if record['installation'] != config['installation']:
                raise RuntimeError('工作台正在使用另一个插件版本。请先结束工作台中的任务并退出工作台，再打开新版；Houdini 不会被关闭。')
            if config.get('managed') and config['houdiniVersion'] not in Store(root, config['trustData']).manifest(config['installation'])['houdini']:
                raise RuntimeError('当前工作台版本不支持这个 Houdini 版本，未加载不兼容的执行端。')
            return control(record, 'status', timeout=5)
        atomic_json(root / 'workbench/launch-config.json', config)
        attempt = uuid.uuid4().hex
        request = root / 'workbench' / ('launch-' + attempt + '.json')
        atomic_json(request, config)
        python = Path(config['python'])
        env = desktop_environment(config['hfs'], python, config.get('debugPort'))
        with (root / 'workbench/desktop.log').open('ab') as output:
            output.write(('\nDesktop Python: ' + str(python) + '\nHoudini runtime: ' + config['hfs'] + '\n').encode('utf-8'))
            output.flush()
            process = subprocess.Popen([str(python), '-X', 'faulthandler', str(Path(__file__).resolve()), '--config', str(request)],
                cwd=Path(config['hfs']) / 'bin', env=env, stdin=subprocess.DEVNULL,
                stdout=output, stderr=subprocess.STDOUT, close_fds=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            while time.monotonic() < deadline:
                record = running(root)
                if record and record['pid'] == process.pid:
                    return control(record, 'status', timeout=5)
                if process.poll() is not None:
                    failure = root / 'workbench' / ('failed-' + attempt + '.json')
                    error = read_json(failure)['error'] if failure.exists() else '启动程序退出，代码 ' + str(process.returncode) + '。请通过报告问题查看启动记录。'
                    raise RuntimeError('独立工作台未启动：' + error)
                time.sleep(.1)
            raise RuntimeError('工作台启动尚未完成。进程未被强制结束，请稍后重新打开工作区。')
        finally:
            request.unlink(missing_ok=True)
    finally:
        lease.close()


def prepare(config):
    root = Path(config['root'])
    runtime = root / 'workbench' / uuid.uuid4().hex
    runtime.mkdir(parents=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    context_file = runtime / 'context.json'

    def prepare_managed(context, progress):
        context.update(frontendPort=port, runtimeDir=str(runtime), workbench=True,
                       executorRegistry=str(root / 'workbench/executors'))
        atomic_json(context_file, context)
        install = Path(context['install'])
        result = subprocess.run([str(install / 'node/node.exe'), str(install / 'app/prepare-profile.mjs'), str(context_file)],
            cwd=install / 'app', env=runtime_env(context), capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise RuntimeError('工作台配置准备失败：' + result.stderr[-3000:])

    if config.get('managed'):
        store = Store(root, config['trustData'])
        context, lease = store.activate(config['installation'], config['houdiniVersion'], prepare=prepare_managed,
                                        owner={'application': 'DSH-Houdini Workbench'})
        plugin = Path(context['install']) / 'app/node_modules/dsh-houdini'
        node = Path(context['install']) / 'node/node.exe'
        binary = Path(context['install']) / 'app/node_modules/@deepseek-ai/dsh/lib/bin.js'
        env = runtime_env(context)
        env['DSH_HOUDINI_MANAGED_CONTEXT'] = str(context_file)
        os.environ['DSH_HOUDINI_MANAGED_CONTEXT'] = str(context_file)
    else:
        lease = FileLease(root / 'runtime.lock')
        plugin, node, binary = Path(config['plugin']), Path(config['node']), Path(config['binary'])
        context = {'root': str(root), 'home': config['home'], 'frontendPort': port,
                   'runtimeDir': str(runtime), 'workbench': True,
                   'executorRegistry': str(root / 'workbench/executors')}
        env = dict(os.environ, DSH_HOME=config['home'])
        env.pop('DSH_HOUDINI_MANAGED_CONTEXT', None)
        sys.path.insert(0, str(plugin / 'houdini/python3.11libs'))
        from dsh_profile_sync import sync_profile_plugins
        sync_profile_plugins([str(node), str(binary)], use_shell=False, project_root=plugin, env=env)
    env.update(DSH_HOUDINI_EXECUTOR_REGISTRY=context['executorRegistry'], DSH_HOUDINI_WORKBENCH='1')
    context['contextFile'] = str(context_file)
    atomic_json(context_file, context)
    env['DSH_HOUDINI_WORKBENCH_CONTEXT'] = str(context_file)
    env.pop('DSH_HOUDINI_EXECUTOR_ID', None)
    env.pop('DSH_HOUDINI_BRIDGE_URL', None)
    return context, lease, plugin, node, binary, env


def run(config):
    context, lease, plugin, node, binary, env = prepare(config)
    sys.path.insert(0, str(plugin / 'houdini/python3.11libs'))
    from dsh_managed_runtime import spawn_frontend, stop_owned
    from dsh_web_auth import DshWebSession
    runtime = Path(context['runtimeDir'])
    base = 'http://127.0.0.1:' + str(context['frontendPort'])
    intents = queue.Queue()
    generation, token = uuid.uuid4().hex, secrets.token_hex(32)
    auth = DshWebSession(base, str(runtime / 'frontend.log'), str(runtime / 'runtime.json'))

    def rpc(method, payload, argument='input', timeout=90):
        request = urllib.request.Request(base + '/api/' + method, data=json.dumps({
            'type': 'client-request', 'rpcId': uuid.uuid4().hex, 'method': method,
            'payload': {'args': {} if method == 'houdiniTargets/activity' else {argument: payload}}}).encode(), headers={'Content-Type': 'application/json'})
        with auth.open(request, timeout=timeout) as response:
            value = json.load(response)['result']
        if not value['ok']:
            raise RuntimeError(value['error']['message'])
        return value['value']

    from dsh_workbench_projects import ProjectManager, show_project_dialog, dialog_request
    projects = ProjectManager(config, context, plugin, generation, rpc, intents)
    dialogs = queue.Queue()
    window_requests = queue.Queue()

    class Control(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            status, result = 200, {'ok': False, 'generation': generation}
            try:
                if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                    status = 403
                    raise RuntimeError('工作台请求未认证。')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 16384:
                    raise ValueError('工作台请求过大。')
                payload = json.loads(self.rfile.read(length) or b'{}')
                if self.path == '/status' and payload == {}:
                    value = {'record': record, 'context': context, 'plugin': str(plugin)}
                elif self.path == '/open':
                    value = rpc('houdiniTargets/openWorkspace', payload)
                    intents.put(value)
                elif self.path == '/show' and isinstance(payload, dict) and (payload == {} or
                        set(payload) == {'sessionId'} and isinstance(payload['sessionId'], str) and 0 < len(payload['sessionId']) <= 256):
                    value = payload
                    intents.put(value)
                elif self.path == '/projects/presence' and payload == {}:
                    value = projects.presence()
                elif self.path == '/window/pin':
                    if (not isinstance(payload, dict) or set(payload) - {'pinned'}
                            or ('pinned' in payload and type(payload['pinned']) is not bool)):
                        raise ValueError('无效的窗口置顶请求。')
                    reply = Future()
                    window_requests.put((payload, reply))
                    try:
                        value = reply.result(timeout=4)
                    finally:
                        reply.cancel()  # A timed-out queued command must not run later.
                elif self.path == '/projects/dialog':
                    dialogs.put(dialog_request(payload))
                    value = {'accepted': True}
                elif self.path == '/projects/attached':
                    value = projects.attached(payload)
                elif self.path == '/projects/failed':
                    value = projects.failed(payload)
                else:
                    raise ValueError('未知的工作台操作。')
                result.update(ok=True, result=value)
            except Exception as error:
                # Product errors carry the user-facing message; anything else
                # surfaces its type and detail instead of an opaque fallback.
                detail = str(error).strip()
                result['error'] = detail if isinstance(error, (ValueError, RuntimeError)) else (
                    type(error).__name__ + ': ' + (detail or '未知错误'))
            data = json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Control)
    record = {'schema': 1, 'pid': os.getpid(), 'processStarted': _process_started(os.getpid()),
              'controlPort': server.server_port, 'generation': generation, 'token': token,
              'installation': config['installation']}
    host = None
    serving = False
    try:
        with (runtime / 'frontend.log').open('wb') as output:
            host = spawn_frontend([str(node), str(binary), 'web', '--patch', str(plugin / 'shared-host.cordis.yml'),
                '--port', str(context['frontendPort']), '--no-open'], node=str(node), cwd=plugin,
                env=env, stdout=output, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        atomic_json(runtime / 'runtime.json', {'pid': host.pid, 'source': 'workbench', 'authLogOffset': 0,
            'version': read_json(binary.parent.parent / 'package.json')['version'],
            'startedAt': time.strftime('%Y-%m-%dT%H:%M:%S%z')})
        deadline = time.monotonic() + 90
        while True:
            if host.poll() is not None:
                raise RuntimeError('DSH 后台在启动时退出，请查看诊断记录。')
            try:
                auth.authorize(2)
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError('DSH 后台未在等待时间内就绪。')
                time.sleep(.2)
        if os.name == 'nt':
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('DSH.Houdini.Workbench')
            dll_directory = os.add_dll_directory(str(Path(config['hfs']) / 'bin'))
        if config.get('initialWorkspace'):
            rpc('houdiniTargets/prepareWorkspace', {'path': config['initialWorkspace'], 'isNew': config.get('initialWorkspaceIsNew') is True})
        else:
            workspace = Path(context['root']) / 'workspaces/工作台'
            workspace.mkdir(parents=True, exist_ok=True)
            rpc('houdiniTargets/prepareWorkspace', {'path': str(workspace), 'isNew': False, 'onlyIfEmpty': True})
        from PySide6.QtCore import QTimer, QObject, QEvent
        from PySide6.QtWidgets import QApplication, QMessageBox
        import dsh_webview
        app = QApplication.instance() or QApplication([])
        app.setApplicationName('DSH-Houdini')
        from PySide6.QtGui import QIcon
        icon = QIcon(str(plugin / 'assets/dsh-houdini.ico'))
        app.setWindowIcon(icon)
        dsh_webview.show_webview(authenticated_url=auth.launch_url(), frontend_url=base, standalone=True)
        dsh_webview._window.setWindowIcon(icon)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        serving = True
        atomic_json(Path(config['root']) / 'workbench/desktop.json', record)
        closing = queue.Queue()

        class CloseGuard(QObject):
            allowed = False
            checking = False

            def eventFilter(self, watched, event):
                if event.type() != QEvent.Close or self.allowed:
                    return False
                event.ignore()
                if not self.checking:
                    self.checking = True
                    def check():
                        try:
                            closing.put(rpc('houdiniTargets/activity', {}, timeout=3))
                        except Exception as error:
                            closing.put({'error': str(error)})
                    threading.Thread(target=check, daemon=True).start()
                return True

        guard = CloseGuard(dsh_webview._window)
        dsh_webview._window.installEventFilter(guard)
        project_dialog = {'value': None}

        def drain():
            while not window_requests.empty():
                request, reply = window_requests.get_nowait()
                if reply.set_running_or_notify_cancel():
                    try:
                        reply.set_result(dsh_webview.window_pin(request.get('pinned')))
                    except Exception as error:
                        reply.set_exception(error)
            while not dialogs.empty():
                request = dialogs.get_nowait()
                if project_dialog['value'] is not None:
                    project_dialog['value'].raise_()
                    project_dialog['value'].activateWindow()
                    continue
                dialog = show_project_dialog(projects, dsh_webview._window, request['action'], request.get('hip'), request.get('sessionId'), request.get('executorId'), request.get('bindSessionId'))
                project_dialog['value'] = dialog
                dialog.finished.connect(lambda *_: project_dialog.update(value=None))
            if not closing.empty():
                activity = closing.get_nowait()
                guard.checking = False
                accepted = activity is not None and activity.get('activeConversations') == 0
                if not accepted:
                    dialog = QMessageBox(dsh_webview._window)
                    from dsh_ui_style import style_dialog
                    style_dialog(dialog)
                    dialog.setWindowTitle('退出 DSH-Houdini')
                    dialog.setText(('还有对话或后台任务尚未结束。' if activity and activity.get('activeConversations') else '暂时无法确认后台及对话保存状态。')
                                   + '退出将停止工作台后台，但不会关闭 Houdini；已经开始的工程操作不会因此撤销。')
                    if activity and activity.get('error'):
                        dialog.setDetailedText(activity['error'])
                    leave = dialog.addButton('退出工作台', QMessageBox.AcceptRole)
                    cancel = dialog.addButton('继续保留', QMessageBox.RejectRole)
                    dialog.setDefaultButton(cancel)
                    dialog.exec()
                    accepted = dialog.clickedButton() is leave
                if accepted:
                    guard.allowed = True
                    dsh_webview._window.close()
                    return
            latest = None
            while not intents.empty():
                latest = intents.get_nowait()
            if latest is not None:
                session_id = latest.get('sessionId')
                if session_id:
                    target = dsh_webview._navigation_url(None, session_id, base)
                    dsh_webview._view.page().runJavaScript(dsh_webview._launch_intent_js(target))
                dsh_webview._window.showNormal()
                dsh_webview._window.raise_()
                dsh_webview._window.activateWindow()

        timer = QTimer()
        timer.timeout.connect(drain)
        timer.start(100)
        app.exec()
        dsh_webview._dispose_webview()
    finally:
        if serving:
            server.shutdown()
        server.server_close()
        if host is not None:
            stop_owned(host)
        lease.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = read_json(args.config)
    try:
        run(config)
    except Exception as error:
        atomic_json(args.config.with_name(args.config.name.replace('launch-', 'failed-')), {'error': str(error)})
        raise


if __name__ == '__main__':
    main()
