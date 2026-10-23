"""Current-workbench diagnostics; installation and updates belong to install UI."""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import queue
import re
import threading
import urllib.request

import hou
from dsh_deployment import read_json

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
_WINDOW = None
_TIMER = None


def _workbench_runtime_status(registration):
    """Worker-only inspection of the explicitly registered desktop and Bridge."""
    from pathlib import Path
    from dsh_workbench import running, control
    context_file = os.environ.get('DSH_HOUDINI_WORKBENCH_CONTEXT')
    if not context_file:
        raise RuntimeError('当前工作台尚未连接，请先使用 Open Workspace。')
    context = read_json(Path(context_file))
    record = running(context['root'])
    desktop = control(record, 'status', timeout=5) if record else None
    port = registration._port
    request = urllib.request.Request(f'http://127.0.0.1:{port}/health',
        headers={'X-DSH-Houdini-Executor': registration.executor_id})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as response:
        health = json.load(response)
    if health.get('ok') is not True or health.get('executorId') != registration.executor_id:
        raise RuntimeError('当前 Houdini 连接身份未能核验。')
    source = Path(_PROJECT_ROOT) / 'lib/generated-verb-contract.js'
    matched = re.search(r'EXPECTED_EXECUTION_CONTRACT_VERSION\s*=\s*(\d+)', source.read_text(encoding='utf-8'))
    if not matched:
        raise RuntimeError('本机 Host 构建尚未就绪，请先完成 npm run build。')
    return {'desktop': desktop, 'health': health, 'expected': int(matched[1]), 'bridgePort': port}


def _show_workbench_diagnostics(registration):
    """The desktop has its own Host lifetime; don't inspect legacy fixed ports."""
    global _WINDOW, _TIMER
    from hutil.Qt import QtCore, QtGui, QtWidgets
    from dsh_ui_style import style_dialog, confirm_dialog, show_tool_window
    if _WINDOW is not None and _WINDOW.isVisible():
        show_tool_window(_WINDOW)
        return
    workbench = registration is not None and registration.workbench
    dialog = QtWidgets.QDialog(hou.qt.mainWindow())
    dialog.setWindowTitle('DSH-Houdini · 运行诊断')
    dialog.setMinimumWidth(600)
    style_dialog(dialog)
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(24, 24, 24, 20)
    summary = QtWidgets.QLabel('正在检查当前工作台与 Houdini…')
    summary.setWordWrap(True)
    summary.setObjectName('summary')
    layout.addWidget(summary)
    note = QtWidgets.QLabel(('重新加载本机文件会重开此安装的工作台，并更新当前 Houdini 的连接。'
        '工程内容和其他 Houdini 窗口保持不变；有任务执行时需等待完成。'
        '\n更换安装包版本、菜单或 Package 后，仍需按版本面板提示重开相关 Houdini。') if workbench else
        '先打开当前 Houdini 的工作台，即可查看实际运行状态并重新加载本机更新。' if registration is None else
        '当前连接使用开发用共享 DSH 服务。这里只重新加载当前 Houdini 连接；外部 Host 由其所属服务维护。')
    note.setWordWrap(True)
    layout.addWidget(note)
    row = QtWidgets.QHBoxLayout()
    apply_button = QtWidgets.QPushButton('重新加载本机更新…' if workbench else
        '打开工作台' if registration is None else '重新加载当前连接…')
    apply_button.setObjectName('primary')
    refresh = QtWidgets.QPushButton('刷新状态')
    log = QtWidgets.QPushButton('打开运行日志')
    for button in (apply_button, refresh, log):
        row.addWidget(button)
    layout.addLayout(row)
    details = QtWidgets.QPlainTextEdit()
    details.setReadOnly(True)
    details.setFixedHeight(160)
    layout.addWidget(details)
    for widget in (refresh, log, details):
        widget.setVisible(workbench)
    events = queue.Queue()
    state = {}

    def check():
        if not workbench:
            summary.setText('当前 Houdini 尚未连接工作台' if registration is None else '当前为开发共享执行端')
            return
        refresh.setEnabled(False)
        def worker():
            try:
                events.put((_workbench_runtime_status(registration), None))
            except Exception as error:
                events.put((None, str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def apply():
        if not workbench:
            dialog.close()
            if registration is None:
                import dsh_launcher
                dsh_launcher.open_workspace()
            else:
                from dsh_shared_executor import show_registration
                show_registration(repair=True)
            return
        if not confirm_dialog(dialog, '重新加载本机更新',
                '在空闲时重开当前安装的工作台并重新加载当前 Houdini 连接？\n\n'
                '已保存的对话及本工作台的输入草稿会保留，不保存、加载或改动 HIP。', '重新加载'):
            return
        import dsh_launcher
        importlib.reload(dsh_launcher)
        import dsh_workbench_client
        if dsh_workbench_client._BUSY:
            summary.setText('工作台操作尚未结束，请稍后重试。')
            return
        import dsh_workbench
        importlib.reload(dsh_workbench)
        importlib.reload(dsh_workbench_client)
        dialog.close()
        dsh_workbench_client.open_workspace(dsh_launcher, reload=True)

    def tick():
        if events.empty():
            return
        value, error = events.get_nowait()
        refresh.setEnabled(True)
        if error:
            summary.setText('运行状态未能核验')
            details.setPlainText(error)
            return
        state.update(value)
        desktop, health = value['desktop'], value['health']
        loaded, expected = health['executionContractVersion'], value['expected']
        runtime = desktop.get('runtime', {}) if desktop else {}
        summary.setText(('工作台已连接' if desktop else '工作台已关闭') +
            (f' · Houdini 接口版本 {loaded}' if loaded == expected else f' · Houdini 接口需重新加载：{loaded} → {expected}'))
        details.setPlainText(f"当前 Houdini：127.0.0.1:{value['bridgePort']}\n"
            + (f"当前工作台：127.0.0.1:{desktop['context']['frontendPort']}\n" if desktop else '')
            + f"DSH：{runtime.get('version', '未核验')}\n启动时间：{runtime.get('startedAt', '未核验')}\n"
            + f"Houdini 实例：{health['runtimeId']}\n"
            + '接口版本相同只说明接口约定一致；源码构建后需重新加载才能应用实现与提示词。')

    def open_log():
        desktop = state.get('desktop')
        if desktop:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(os.path.join(desktop['context']['runtimeDir'], 'frontend.log')))

    timer = QtCore.QTimer(dialog)
    timer.timeout.connect(tick)
    timer.start(100)
    def cleanup(*_):
        global _WINDOW, _TIMER
        timer.stop()
        _WINDOW = _TIMER = None
    dialog.finished.connect(cleanup)
    apply_button.clicked.connect(apply)
    refresh.clicked.connect(check)
    log.clicked.connect(open_log)
    _WINDOW, _TIMER = dialog, timer
    show_tool_window(dialog)
    check()


def show_version_manager() -> None:
    """Inspect the current registration; never guess an embedded Host port."""
    from dsh_executor_registry import is_shared_executor, active_registration
    registration = active_registration() if is_shared_executor() else None
    return _show_workbench_diagnostics(registration)


if __name__ == '__main__':
    show_version_manager()
