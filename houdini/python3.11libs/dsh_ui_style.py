"""Shared native theme and Chinese confirmations; no runtime/bootstrap dependency."""

# Also used by runtime diagnostics. Keep this dependency-free: the standalone
# installation manager must open without Node, DSH or an installed plugin.
STYLE = """
    QDialog { background: #24272b; color: #ECEDEF; }
    QWidget { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI'; font-size: 13px; }
    QLabel, QCheckBox { color: #ECEDEF; background: transparent; }
    QLabel#title { font-size: 22px; font-weight: 600; }
    QLabel#caption, QLabel#note, QLabel#column { color: #A1A6AF; font-size: 12px; }
    QLabel#version { color: #ECEDEF; font-size: 19px; font-weight: 600; }
    QLabel#name { font-weight: 600; }
    QLabel#summary { color: #C7CBD1; }
    QFrame#track, QFrame#rail, QFrame#advanced {
        background: #2d3136; border: 1px solid #3d434b; border-radius: 8px;
    }
    QPushButton {
        color: #E1E4E8; background: #30343A; border: 1px solid #484D55;
        border-radius: 8px; padding: 8px 16px;
    }
    QPushButton:hover { background: #3B4048; border-color: #666C76; }
    QPushButton:pressed { background: #272B31; }
    QPushButton:focus { border-color: #e5a263; }
    QPushButton:disabled { color: #737A84; background: #292C31; border-color: #363B42; }
    QPushButton#primary, QPushButton#update { background: #AE652F; border-color: #CB884E; color: #FFFFFF; }
    QPushButton#primary:hover, QPushButton#update:hover { background: #BC753C; }
    QPushButton#quiet { background: transparent; border-color: transparent; color: #AEB4BD; }
    QPushButton#quiet:hover { color: #ECEDEF; background: #2B2F35; }
    QPlainTextEdit {
        background: #24272b; color: #B8BEC7; border: 1px solid #3C4149;
        border-radius: 8px; padding: 8px; font-family: 'Consolas', 'Microsoft YaHei UI'; font-size: 12px;
    }
    QLineEdit { background: #24272b; color: #ECEDEF; border: 1px solid #484D55;
        border-radius: 8px; padding: 8px; selection-background-color: #AE652F; }
    QProgressBar { background: #353A42; border: none; border-radius: 2px; max-height: 4px; }
    QProgressBar::chunk { background: #e5a263; border-radius: 2px; }
    QMessageBox { background: #24272b; }
"""


def style_dialog(dialog, *, tool_window=True):
    """Style persistent tools consistently; confirmations retain dialog controls.

    Apply window hints before the first show. Houdini-owned top-level windows
    stay above their owner through the native window relationship, not system
    topmost. Other applications can cover them; background updates do not wake
    a minimized tool. Standalone tools remain normal application windows.
    """
    from PySide6 import QtCore, QtGui
    if tool_window:
        # Adding a minimize hint makes Qt use explicit caption controls. A
        # QWidget created with Qt.Window then loses its implicit close button;
        # on Windows SC_CLOSE becomes disabled even though an X is drawn.
        # Specify the complete tool caption before its first native show.
        dialog.setWindowFlags((dialog.windowFlags() & ~QtCore.Qt.WindowStaysOnTopHint)
                              | QtCore.Qt.WindowTitleHint
                              | QtCore.Qt.WindowSystemMenuHint
                              | QtCore.Qt.WindowMinimizeButtonHint
                              | QtCore.Qt.WindowCloseButtonHint)
    dialog.setFont(QtGui.QFont("Microsoft YaHei UI", 10))
    dialog.setStyleSheet(STYLE)


def show_tool_window(window):
    """Explicit user open: restore a minimized tool and give it focus once."""
    if window.isMinimized():
        window.showNormal()
    else:
        window.show()
    window.raise_()
    window.activateWindow()


_COMPONENT_INFO = None
_STARTUP_PROBLEM = None


def show_component_info(version, location, actions, parent=None):
    """Explicit menu-only local maintenance; no status probing or Desktop ownership."""
    global _COMPONENT_INFO
    from PySide6 import QtCore, QtWidgets
    if _COMPONENT_INFO is not None:
        show_tool_window(_COMPONENT_INFO)
        return _COMPONENT_INFO
    dialog = QtWidgets.QDialog(parent)
    style_dialog(dialog)
    dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose)
    dialog.setWindowTitle('DSH-Houdini · 连接与维护')
    dialog.setFixedWidth(540)
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(24, 22, 24, 18)
    layout.setSpacing(16)
    layout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)

    def label(text, name='summary'):
        widget = QtWidgets.QLabel(text)
        widget.setObjectName(name)
        widget.setTextFormat(QtCore.Qt.PlainText)
        widget.setWordWrap(True)
        return widget

    def action(text, key, name=''):
        button = QtWidgets.QPushButton(text)
        button.setObjectName(name)
        button.setAutoDefault(False)
        def invoke():
            dialog.close()
            actions[key]()
        button.clicked.connect(invoke)
        return button

    heading = QtWidgets.QHBoxLayout()
    heading.addWidget(label('连接与维护', 'title'), 1)
    heading.addWidget(label('连接组件 ' + version, 'caption'))
    layout.addLayout(heading)
    layout.addWidget(label('对话、模型和插件更新，都在 DSH Desktop 中管理。'))
    layout.addWidget(action('打开 Desktop 工作区', 'open', 'primary'))

    layout.addWidget(label('连接遇到问题时', 'name'))
    repair = QtWidgets.QHBoxLayout()
    repair_button = action('重新连接', 'repair')
    repair_button.setFixedWidth(122)
    repair.addWidget(repair_button)
    repair.addSpacing(6)
    repair.addWidget(label('重新建立当前窗口的连接，工程内容保留。', 'caption'), 1)
    layout.addLayout(repair)
    diagnose = QtWidgets.QHBoxLayout()
    diagnose_button = action('连接诊断…', 'diagnose')
    diagnose_button.setFixedWidth(122)
    diagnose.addWidget(diagnose_button)
    diagnose.addSpacing(6)
    diagnose.addWidget(label('查看接入信息，按需导出诊断报告。', 'caption'), 1)
    layout.addLayout(diagnose)

    toggle = QtWidgets.QPushButton('更多维护选项  ▸')
    toggle.setObjectName('quiet')
    toggle.setAutoDefault(False)
    toggle.setCheckable(True)
    toggle.setAccessibleName('展开或收起更多维护选项')
    layout.addWidget(toggle, 0, QtCore.Qt.AlignLeft)
    advanced = QtWidgets.QFrame()
    advanced.setObjectName('advanced')
    advanced_layout = QtWidgets.QVBoxLayout(advanced)
    advanced_layout.setContentsMargins(16, 14, 16, 14)
    advanced_layout.setSpacing(12)
    advanced_layout.addWidget(label('本机连接组件', 'name'))
    advanced_layout.addWidget(label('这里仅管理 Houdini 端组件，不用于下载插件更新。\n更新或切换版本后，请保存工程并重开此 Houdini 窗口。', 'caption'))
    advanced_layout.addWidget(action('切换已安装组件版本…', 'switch'))
    advanced_layout.addWidget(action('移除本机组件…', 'remove'))
    advanced_layout.addWidget(label('当前加载位置', 'caption'))
    path = QtWidgets.QPlainTextEdit(str(location))
    path.setReadOnly(True)
    path.setFixedHeight(66)
    path.setAccessibleName('当前连接组件加载位置')
    advanced_layout.addWidget(path)
    advanced.hide()
    layout.addWidget(advanced)
    def fit_content():
        layout.activate()
        dialog.setFixedHeight(layout.totalHeightForWidth(dialog.width()))
    def expanded(checked):
        advanced.setVisible(checked)
        toggle.setText('收起维护选项  ▾' if checked else '更多维护选项  ▸')
        fit_content()
    toggle.toggled.connect(expanded)

    footer = QtWidgets.QHBoxLayout()
    footer.addStretch()
    close = QtWidgets.QPushButton('关闭')
    close.setObjectName('quiet')
    close.setAutoDefault(False)
    close.clicked.connect(dialog.close)
    footer.addWidget(close)
    layout.addLayout(footer)
    _COMPONENT_INFO = dialog
    def disposed():
        global _COMPONENT_INFO
        if _COMPONENT_INFO is dialog:
            _COMPONENT_INFO = None
    dialog.destroyed.connect(disposed)
    fit_content()
    show_tool_window(dialog)
    return dialog


def clear_startup_problem():
    global _STARTUP_PROBLEM
    current, _STARTUP_PROBLEM = _STARTUP_PROBLEM, None
    if current is not None:
        current.close()


def show_startup_problem(message, detail='', parent=None):
    global _STARTUP_PROBLEM
    from PySide6 import QtCore, QtWidgets
    clear_startup_problem()
    dialog = QtWidgets.QDialog(parent)
    style_dialog(dialog)
    dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose)
    dialog.setWindowTitle('DSH-Houdini · 操作未完成')
    dialog.setMinimumWidth(520)
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(24, 20, 24, 20)
    title = QtWidgets.QLabel('操作未完成')
    title.setObjectName('title')
    layout.addWidget(title)
    summary = QtWidgets.QLabel(message)
    summary.setTextFormat(QtCore.Qt.PlainText)
    summary.setWordWrap(True)
    summary.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    layout.addWidget(summary)
    toggle = QtWidgets.QPushButton('查看技术详情')
    toggle.setObjectName('quiet')
    toggle.setCheckable(True)
    details = QtWidgets.QPlainTextEdit(detail)
    details.setReadOnly(True)
    details.setFixedHeight(150)
    details.hide()
    toggle.toggled.connect(details.setVisible)
    layout.addWidget(toggle)
    layout.addWidget(details)
    close = QtWidgets.QPushButton('知道了')
    close.setObjectName('primary')
    close.clicked.connect(dialog.close)
    layout.addWidget(close)
    dialog.show()
    show_tool_window(dialog)
    _STARTUP_PROBLEM = dialog
    def disposed():
        global _STARTUP_PROBLEM
        if _STARTUP_PROBLEM is dialog:
            _STARTUP_PROBLEM = None
    dialog.destroyed.connect(disposed)
    return dialog


def confirm_dialog(parent, title, message, accept_text):
    """Explicit Chinese labels, independent of the Houdini Qt locale."""
    from PySide6 import QtCore, QtWidgets
    dialog = QtWidgets.QMessageBox(parent)
    style_dialog(dialog, tool_window=False)
    dialog.setWindowTitle(title)
    dialog.setTextFormat(QtCore.Qt.PlainText)
    dialog.setText(message)
    accept = dialog.addButton(accept_text, QtWidgets.QMessageBox.AcceptRole)
    cancel = dialog.addButton("取消", QtWidgets.QMessageBox.RejectRole)
    dialog.setDefaultButton(cancel)
    dialog.setEscapeButton(cancel)
    dialog.exec()
    return dialog.clickedButton() is accept
