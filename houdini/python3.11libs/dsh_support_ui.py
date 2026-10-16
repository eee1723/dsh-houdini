from __future__ import annotations

import base64
from pathlib import Path
import queue
import threading

import dsh_support_report as reports


def show(*, parent=None, source_root=None, managed=None, startup_error=None):
    from hutil.Qt import QtCore, QtGui, QtWidgets
    from dsh_ui_style import style_dialog
    dialog = QtWidgets.QDialog(parent)
    dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose)
    dialog.setWindowTitle('DSH-Houdini · 报告问题')
    dialog.resize(720, 590)
    dialog.setMinimumSize(520, 480)
    style_dialog(dialog)
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(14)

    def label(text, name=None):
        widget = QtWidgets.QLabel(text)
        widget.setTextFormat(QtCore.Qt.PlainText)
        widget.setWordWrap(True)
        if name:
            widget.setObjectName(name)
        return widget

    heading = QtWidgets.QHBoxLayout()
    heading.addWidget(label('报告问题', 'title'))
    heading.addStretch()
    close_button = QtWidgets.QPushButton('关闭')
    close_button.setObjectName('quiet')
    heading.addWidget(close_button)
    layout.addLayout(heading)
    pages = QtWidgets.QStackedWidget()
    layout.addWidget(pages, 1)
    form_scroll = QtWidgets.QScrollArea()
    form_scroll.setWidgetResizable(True)
    form_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
    form_scroll.setStyleSheet('QScrollArea, QScrollArea > QWidget > QWidget { background: #24272b; }')
    form = QtWidgets.QWidget()
    form_layout = QtWidgets.QVBoxLayout(form)
    form_layout.setContentsMargins(0, 0, 8, 0)
    form_layout.setSpacing(10)
    form_layout.addWidget(label('把问题和相关记录保存成一个文件，发给开发者帮助排查。', 'summary'))
    form_layout.addWidget(label('遇到了什么问题？', 'name'))
    description = QtWidgets.QPlainTextEdit()
    description.setPlaceholderText('例如：点击打开工作区后一直没有反应。也可以留空。')
    description.setFixedHeight(90)
    form_layout.addWidget(description)
    form_layout.addWidget(label('附带哪些信息', 'name'))

    def option(title, note):
        checkbox = QtWidgets.QCheckBox(title)
        checkbox.setChecked(True)
        form_layout.addWidget(checkbox)
        explanation = label(note, 'note')
        explanation.setContentsMargins(24, 0, 0, 8)
        form_layout.addWidget(explanation)
        return checkbox

    include_logs = option('当前运行情况', '插件最近的启动、连接和报错记录，用来排查卡住或操作失败。')
    previous = option('之前的运行情况', '有记录时补充之前的报错，适合重启后再来反馈。')
    form_layout.addWidget(label('包含软件版本，不附带工程文件或图片。要附上聊天内容，请在对应对话中选择「报告问题」。', 'note'))
    form_layout.addStretch()
    form_scroll.setWidget(form)
    pages.addWidget(form_scroll)

    details_page = QtWidgets.QWidget()
    detail_layout = QtWidgets.QVBoxLayout(details_page)
    detail_layout.setContentsMargins(0, 0, 0, 0)
    toolbar = QtWidgets.QHBoxLayout()
    toolbar.addWidget(label('报告内容', 'name'))
    toolbar.addStretch()
    collapse = QtWidgets.QPushButton('收起详情')
    collapse.setObjectName('quiet')
    collapse.setEnabled(False)
    toolbar.addWidget(collapse)
    detail_layout.addLayout(toolbar)
    detail_layout.addWidget(label('这些记录供开发者排查问题。你可以按需查看，分享前确认没有私人或项目敏感内容。', 'note'))
    detail_scroll = QtWidgets.QScrollArea()
    detail_scroll.setWidgetResizable(True)
    detail_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
    detail_scroll.setStyleSheet(form_scroll.styleSheet())
    entries = QtWidgets.QWidget()
    entries_layout = QtWidgets.QVBoxLayout(entries)
    entries_layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
    entries_layout.setContentsMargins(0, 0, 8, 0)
    entries_layout.setSpacing(8)
    detail_scroll.setWidget(entries)
    detail_layout.addWidget(detail_scroll, 1)
    pages.addWidget(details_page)

    status = label('只保存到你的电脑，不会自动发送。', 'note')
    layout.addWidget(status)
    sharing = QtWidgets.QPushButton('如何发送给开发者？')
    sharing.setObjectName('quiet')
    sharing.setCheckable(True)
    sharing.setStyleSheet('text-align: left; padding-left: 0;')
    layout.addWidget(sharing)
    sharing_panel = QtWidgets.QWidget()
    sharing_layout = QtWidgets.QVBoxLayout(sharing_panel)
    sharing_layout.setContentsMargins(0, 0, 0, 0)
    sharing_layout.addWidget(label('保存后，把文件发给开发者，也可以在 GitHub 反馈页面附上文件。GitHub 的内容公开可见，涉及项目资料时请私下发送。常见密钥和个人路径会自动隐藏，分享前仍请检查。', 'note'))
    issue = QtWidgets.QPushButton('前往反馈页面')
    issue.setObjectName('quiet')
    sharing_layout.addWidget(issue)
    sharing_panel.hide()
    layout.addWidget(sharing_panel)
    actions = QtWidgets.QHBoxLayout()
    actions.addStretch()
    inspect = QtWidgets.QPushButton('查看报告内容')
    save = QtWidgets.QPushButton('保存报告…')
    save.setObjectName('primary')
    actions.addWidget(inspect)
    actions.addWidget(save)
    layout.addLayout(actions)
    events = queue.Queue()
    state = {'report': None, 'closed': False, 'revision': 0, 'busy': False, 'file_rows': []}

    def set_busy(busy, action=None):
        state['busy'] = busy
        save.setEnabled(not busy)
        inspect.setEnabled(not busy)
        save.setText('正在整理并保存…' if busy and action == 'save' else '保存报告…')
        inspect.setText('正在整理…' if busy and action == 'preview' else '返回填写' if pages.currentIndex() == 1 else '查看报告内容')

    def collapse_all():
        for button, body, title in state['file_rows']:
            button.setChecked(False)
            button.setText(title + '    查看')
            body.hide()
        collapse.setEnabled(False)

    def invalidate():
        state['revision'] += 1
        state['report'] = None
        collapse_all()
        pages.setCurrentIndex(0)
        set_busy(False)
        status.setText('只保存到你的电脑，不会自动发送。')

    def populate(report):
        while entries_layout.count():
            item = entries_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        state['file_rows'] = []
        for item in report['files']:
            title = item.get('label', '补充记录')
            button = QtWidgets.QPushButton(title + '    查看')
            button.setCheckable(True)
            button.setStyleSheet('text-align: left; padding: 12px;')
            button.setToolTip(item.get('description', '供开发者排查问题。'))
            body = QtWidgets.QWidget()
            body_layout = QtWidgets.QVBoxLayout(body)
            body_layout.setContentsMargins(8, 0, 8, 8)
            body_layout.addWidget(label(item.get('description', ''), 'note'))
            body_layout.addWidget(label(item['name'], 'note'))
            text = QtWidgets.QPlainTextEdit()
            text.setReadOnly(True)
            text.setPlainText(item['text'])
            text.setFixedHeight(220)
            text.setAccessibleName(title + '详情')
            body_layout.addWidget(text)
            body.hide()
            entries_layout.addWidget(button)
            entries_layout.addWidget(body)
            state['file_rows'].append((button, body, title))

            def toggle(checked=False, selected=button, content=body, name=title):
                checked = selected.isChecked()
                collapse_all()
                selected.setChecked(checked)
                selected.setText(name + ('    收起' if checked else '    查看'))
                content.setVisible(checked)
                collapse.setEnabled(checked)
            button.clicked.connect(toggle)
        entries_layout.addStretch()

    def write_report(report, filename):
        import os
        import tempfile
        try:
            destination = Path(filename)
            descriptor, temporary = tempfile.mkstemp(prefix='.dsh-report-', dir=destination.parent)
            try:
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(base64.b64decode(report['archiveBase64'], validate=True))
                os.replace(temporary, destination)
            finally:
                Path(temporary).unlink(missing_ok=True)
            status.setText('报告已保存。把这个文件发给开发者即可。')
        except OSError as error:
            status.setText('没能保存，请换个位置重试。')
            status.setToolTip(type(error).__name__)

    def finish_action(report, action, filename):
        if action == 'save':
            write_report(report, filename)
        else:
            populate(report)
            pages.setCurrentIndex(1)
            inspect.setText('返回填写')
            status.setText('分享前请确认内容。查看详情不会上传或修改你的工程。')

    def prepare(action, filename=None):
        if state['busy']:
            return
        if state['report']:
            finish_action(state['report'], action, filename)
            return
        revision = state['revision']
        set_busy(True, action)
        status.setText('正在整理报告，请稍候…')
        payload = {'options': {'description': description.toPlainText()[:4000], 'includeLogs': include_logs.isChecked(),
                               'includePrevious': previous.isChecked(), 'includeContent': False},
                   'missing': ['session_not_collected_from_native_window'],
                   'timeline': [{'type': 'bootstrap/error', 'error': str(startup_error)}] if startup_error else []}
        context = {'packageRoot': str(source_root or Path(__file__).resolve().parents[2]), 'managed': managed}

        def worker():
            try:
                events.put((revision, reports.build_report(payload, context), None, action, filename))
            except Exception as error:
                events.put((revision, None, type(error).__name__, action, filename))
        threading.Thread(target=worker, daemon=True).start()

    def poll():
        while not events.empty():
            revision, result, error, action, filename = events.get_nowait()
            if state['closed'] or revision != state['revision']:
                continue
            set_busy(False)
            if error:
                status.setText('暂时没能整理好报告，请重试。')
                status.setToolTip(error)
                continue
            state['report'] = result
            finish_action(result, action, filename)

    def save_report():
        if state['busy']:
            return
        report = state['report']
        filename, _filter = QtWidgets.QFileDialog.getSaveFileName(dialog, '保存报告',
            report['filename'] if report else 'dsh-houdini-report.zip', 'ZIP (*.zip)')
        if filename and not state['closed']:
            prepare('save', filename)

    def inspect_report():
        if pages.currentIndex() == 1:
            collapse_all()
            pages.setCurrentIndex(0)
            inspect.setText('查看报告内容')
        else:
            prepare('preview')

    def open_issue():
        if state['report']:
            QtWidgets.QApplication.clipboard().setText(state['report']['summary'])
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(reports.ISSUES_URL))
        status.setText('请在反馈页面描述问题，并附上保存的报告。' + ('问题说明已复制。' if state['report'] else ''))

    def close():
        state['closed'] = True
        state['revision'] += 1
        timer.stop()

    description.textChanged.connect(invalidate)
    include_logs.toggled.connect(invalidate)
    previous.toggled.connect(invalidate)
    sharing.toggled.connect(sharing_panel.setVisible)
    collapse.clicked.connect(collapse_all)
    inspect.clicked.connect(inspect_report)
    save.clicked.connect(save_report)
    close_button.clicked.connect(dialog.close)
    issue.clicked.connect(open_issue)
    timer = QtCore.QTimer(dialog)
    timer.timeout.connect(poll)
    timer.start(100)
    dialog.finished.connect(close)
    dialog.show()
    return dialog
