"""Shared native theme and Chinese confirmations; no runtime/bootstrap dependency."""

# Also used by runtime diagnostics. Keep this dependency-free: the standalone
# installation manager must open without Node, DSH or an installed plugin.
STYLE = """
    QDialog { background: #24272b; color: #ECEDEF; }
    QWidget { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI'; font-size: 13px; }
    QLabel { color: #ECEDEF; background: transparent; }
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
    from hutil.Qt import QtCore, QtGui
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


def confirm_dialog(parent, title, message, accept_text):
    """Explicit Chinese labels, independent of the Houdini Qt locale."""
    from hutil.Qt import QtCore, QtWidgets
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
