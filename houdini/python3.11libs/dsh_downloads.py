from __future__ import annotations

from pathlib import Path
import re


def safe_filename(value):
    name = re.split(r'[\\/]', value or '')[-1]
    name = re.sub(r'[\x00-\x1f<>:"|?*]', '_', name).strip(' .')
    if not name or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', name):
        return 'download.bin'
    return name[:180]


def install(profile, parent):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout
    active = set()

    def requested(download):
        filename, _filter = QFileDialog.getSaveFileName(parent, '保存下载文件', safe_filename(download.suggestedFileName()))
        if not filename:
            download.cancel()
            return
        destination = Path(filename)
        dialog = QDialog(parent)
        from dsh_ui_style import style_dialog
        style_dialog(dialog)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.setWindowTitle('DSH-Houdini · 文件下载')
        layout = QVBoxLayout(dialog)
        label = QLabel(destination.name)
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
        progress = QProgressBar()
        progress.setRange(0, 0)
        layout.addWidget(progress)
        status = QLabel('正在下载…')
        status.setTextFormat(Qt.PlainText)
        status.setWordWrap(True)
        layout.addWidget(status)
        cancel = QPushButton('取消下载')
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(cancel)
        layout.addLayout(row)
        active.add(download)
        closed = {'value': False}

        def update():
            if closed['value']:
                return
            total = download.totalBytes()
            if total > 0:
                progress.setRange(0, 100)
                progress.setValue(min(100, int(download.receivedBytes() * 100 / total)))
            if download.isFinished():
                active.discard(download)
                state = download.state()
                if state == download.DownloadState.DownloadCompleted:
                    status.setText('已保存：' + str(destination))
                    progress.setRange(0, 100)
                    progress.setValue(100)
                elif state == download.DownloadState.DownloadCancelled:
                    status.setText('下载已取消。')
                else:
                    status.setText('下载失败：' + download.interruptReasonString())
                cancel.setText('关闭')

        def stop():
            if not download.isFinished():
                download.cancel()
            dialog.close()

        def dispose():
            closed['value'] = True
            active.discard(download)
            if not download.isFinished():
                download.cancel()

        download.receivedBytesChanged.connect(update)
        download.totalBytesChanged.connect(update)
        download.stateChanged.connect(update)
        download.isFinishedChanged.connect(update)
        cancel.clicked.connect(stop)
        dialog.finished.connect(dispose)
        download.setDownloadDirectory(str(destination.parent))
        download.setDownloadFileName(destination.name)
        dialog.show()
        if not destination.is_absolute() or not destination.parent.is_dir() or destination.is_dir() or Path(download.downloadDirectory()) != destination.parent or download.downloadFileName() != destination.name:
            download.cancel()
            status.setText('下载失败：无法使用所选文件位置，请选择已存在且可写的目录。')
            return
        download.accept()

    profile.downloadRequested.connect(requested)
    parent._dsh_downloads = active


def open_issue_window(request):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    from dsh_support_report import ISSUES_URL
    if request.isUserInitiated() and request.requestedUrl() == QUrl(ISSUES_URL):
        QDesktopServices.openUrl(QUrl(ISSUES_URL))
