"""User-invoked local connection reports; no Host, scene or log discovery."""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path
import re
import sys
import threading
import webbrowser

from dsh_support_report import (FILE_LABELS, MAX_TEXT, build_connection_report,
                               inspect_report, report_html, save_reviewed_file)

_WINDOW = None


def capture_snapshot(launcher, hou_api):
    """Main thread: a whitelist of already loaded metadata, never filesystem I/O."""
    modules = {}
    for name in ('dsh_launcher', 'dsh_bridge', 'dsh_execution', 'dsh_executor_registry',
                 'dsh_workbench_client', 'dsh_workbench_entry', 'dsh_connection_operation',
                 'dsh_connection_diagnostics', 'dsh_support_report'):
        loaded = sys.modules.get(name)
        if loaded is not None:
            modules[name] = {'file': str(getattr(loaded, '__file__', 'unknown'))}
    bridge = sys.modules.get('dsh_bridge')
    server = getattr(bridge, '_server', None)
    address = getattr(server, 'server_address', None)
    bridge_facts = {'loaded': bridge is not None, 'listening': server is not None}
    if isinstance(address, tuple) and len(address) == 2 and type(address[1]) is int:
        bridge_facts['port'] = address[1]
    for public, attribute in (('execution_contract_version', '_EXECUTION_CONTRACT_VERSION'),
                              ('verb_catalog_hash', '_VERB_CATALOG_HASH')):
        value = getattr(bridge, attribute, None)
        if type(value) in (int, str):
            bridge_facts[public] = value
    registry = sys.modules.get('dsh_executor_registry')
    registration = getattr(registry, '_ACTIVE', None)
    registration_facts = {'active': registration is not None and not getattr(registration, '_closed', True)}
    if registration_facts['active']:
        for public, attribute in (('executor_id', 'executor_id'), ('runtime_id', '_runtime_id'), ('version', 'version')):
            value = getattr(registration, attribute, None)
            if isinstance(value, str):
                registration_facts[public] = value
    snapshot = {'houdini_version': hou_api.applicationVersionString(), 'process_id': os.getpid(),
            'loaded_component_root': str(launcher._PROJECT_ROOT), 'loaded_modules': modules,
            'bridge': bridge_facts, 'registration': registration_facts,
            'desktop_reachability': 'not_probed'}
    component_id = str(launcher._PROJECT_ROOT).replace('\\', '/').rstrip('/').rsplit('/', 1)[-1]
    if re.fullmatch('[0-9a-f]{16}', component_id):
        snapshot['component_content_id'] = component_id
    return snapshot


def prepare_report(snapshot, startup_error, package_root):
    """Worker: the preview and save use the exact same validated archive bytes."""
    report = build_connection_report(snapshot, startup_error, package_root)
    archive = base64.b64decode(report['archiveBase64'])
    manifest, files = inspect_report(io.BytesIO(archive))
    return {'manifest': manifest, 'files': files, 'archive': archive,
            'filename': report['filename'], 'generated': True}


def read_report(filename):
    """Worker: inspect a user-selected ZIP without extracting or executing it."""
    manifest, files = inspect_report(filename)
    return {'manifest': manifest, 'files': files, 'generated': False}


def save_report(result, filename, *, as_html=False):
    """Worker: only paths explicitly selected by the user are written."""
    data = report_html(result['files']).encode('utf-8') if as_html else result['archive']
    return save_reviewed_file(filename, data, html_document=as_html)


def save_and_view_html(result, filename):
    """The user explicitly chose this HTML path; browser startup stays off the GUI."""
    path = save_report(result, filename, as_html=True)
    return path, webbrowser.open(Path(path).as_uri())


def show(launcher):
    global _WINDOW
    from hutil.Qt import QtCore, QtWidgets
    from dsh_ui_style import style_dialog, show_tool_window
    if _WINDOW is not None:
        show_tool_window(_WINDOW)
        return _WINDOW

    window = QtWidgets.QDialog(launcher.hou.qt.mainWindow())
    window.setWindowTitle('DSH-Houdini 接入诊断')
    window.setAttribute(QtCore.Qt.WA_DeleteOnClose)
    style_dialog(window)
    layout = QtWidgets.QVBoxLayout(window)
    note = QtWidgets.QLabel('连接不上 Desktop 时，也可以导出此窗口的接入诊断。\n'
        '只包含组件与连接信息、最近启动错误，不收集会话正文、凭据或工程文件。')
    note.setWordWrap(True)
    layout.addWidget(note)
    actions = QtWidgets.QHBoxLayout()
    generate = QtWidgets.QPushButton('生成接入诊断')
    inspect = QtWidgets.QPushButton('查看已有诊断包…')
    actions.addWidget(generate)
    actions.addWidget(inspect)
    layout.addLayout(actions)
    status = QtWidgets.QLabel('生成后可先查看内容，再选择保存位置。')
    status.setWordWrap(True)
    status.setTextFormat(QtCore.Qt.PlainText)
    status.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    layout.addWidget(status)
    selector = QtWidgets.QComboBox()
    selector.hide()
    layout.addWidget(selector)
    preview = QtWidgets.QPlainTextEdit()
    preview.setReadOnly(True)
    preview.setMinimumHeight(220)
    preview.hide()
    layout.addWidget(preview)
    footer = QtWidgets.QHBoxLayout()
    save = QtWidgets.QPushButton('保存诊断包…')
    view = QtWidgets.QPushButton('保存并查看 HTML…')
    close = QtWidgets.QPushButton('关闭')
    save.setEnabled(False)
    view.setEnabled(False)
    footer.addWidget(save)
    footer.addWidget(view)
    footer.addStretch()
    footer.addWidget(close)
    layout.addLayout(footer)
    state = {'busy': False, 'closed': False, 'result': None, 'completion': None}
    timer = QtCore.QTimer(window)

    def refresh_buttons():
        idle = not state['busy']
        generate.setEnabled(idle)
        inspect.setEnabled(idle)
        save.setEnabled(idle and bool(state['result'] and state['result'].get('generated')))
        view.setEnabled(idle and state['result'] is not None)

    def begin(task, done, message):
        if state['busy'] or state['closed']:
            return
        state['busy'] = True
        state['completion'] = None
        status.setText(message)
        refresh_buttons()
        def worker():
            try:
                value = task()
                state['completion'] = (done, value, None)
            except Exception as error:
                state['completion'] = (done, None, str(error) or repr(error))
        threading.Thread(target=worker, daemon=True).start()
        timer.start(100)

    def tick():
        completion = state['completion']
        if state['closed'] or completion is None:
            return
        timer.stop()
        state['completion'] = None
        state['busy'] = False
        done, value, error = completion
        if error:
            status.setText('操作未完成：' + error)
        else:
            done(value)
        refresh_buttons()

    def select_preview(*_args):
        result = state['result']
        name = selector.currentData()
        if result and name in result['files']:
            text = result['files'][name]
            preview.setPlainText(text[:MAX_TEXT] + ('\n\n[预览已截短，保存的文件保留完整内容。]' if len(text) > MAX_TEXT else ''))

    def ready(result):
        state['result'] = result
        selector.clear()
        for name in result['files']:
            selector.addItem(FILE_LABELS.get(name, (name, ''))[0] + ' — ' + name, name)
        selector.show()
        preview.show()
        select_preview()
        status.setText('接入诊断已生成，尚未保存。这不是完整会话诊断，未收集 Desktop 日志。分享前请检查全部内容。'
            if result.get('generated') else '诊断包的格式和文件校验通过。可能包含原作者选择的会话正文，分享前请检查内容。')
        window.resize(740, 590)

    def generate_report():
        if state['busy']:
            return
        try:
            snapshot = capture_snapshot(launcher, launcher.hou)
            startup_error = str(launcher._LAST_STARTUP_FAILURE or '')
            package_root = launcher._PROJECT_ROOT
        except Exception as error:
            status.setText('无法取得当前窗口信息：' + str(error))
            return
        begin(lambda: prepare_report(snapshot, startup_error, package_root), ready, '正在整理接入诊断…')

    def inspect_existing():
        if state['busy']:
            return
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(window, '选择诊断包', '', '诊断包 (*.zip)')
        if filename:
            begin(lambda: read_report(filename), ready, '正在检查诊断包…')

    def save_selected(as_html=False):
        if state['busy'] or state['result'] is None:
            return
        result = state['result']
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(window,
            '保存并查看诊断 HTML' if as_html else '保存接入诊断包',
            'dsh-houdini-report.html' if as_html else result['filename'],
            'HTML (*.html *.htm)' if as_html else '诊断包 (*.zip)')
        if not filename:
            return
        def saved(value):
            path, opened = value if as_html else (value, True)
            status.setText('已保存：' + path)
            if not opened:
                status.setText('HTML 已保存，但未能打开浏览器。请手动打开：' + path)
        begin(lambda: save_and_view_html(result, filename) if as_html else save_report(result, filename), saved, '正在保存…')

    def disposed(*_args):
        global _WINDOW
        state['closed'] = True
        timer.stop()
        if _WINDOW is window:
            _WINDOW = None

    timer.timeout.connect(tick)
    generate.clicked.connect(generate_report)
    inspect.clicked.connect(inspect_existing)
    selector.currentIndexChanged.connect(select_preview)
    save.clicked.connect(lambda: save_selected(False))
    view.clicked.connect(lambda: save_selected(True))
    close.clicked.connect(window.close)
    window.finished.connect(disposed)
    window.destroyed.connect(disposed)
    _WINDOW = window
    show_tool_window(window)
    return window
