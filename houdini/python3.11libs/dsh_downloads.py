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


def install_external_links(page, parent):
    """Open user web links in the browser, retaining DSH's delayed login popup."""
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWidgets import QMessageBox

    pending = set()

    def external(url):
        return (url.isValid() and url.scheme() in ('https', 'http')
                and bool(url.host()) and not url.userInfo())

    def open_browser(url):
        if not QDesktopServices.openUrl(url):
            QMessageBox.information(parent, 'DSH-Houdini · 打开浏览器',
                '未能打开系统浏览器。登录时请使用页面中的“复制登录链接”，粘贴到浏览器后完成登录。')

    class PendingLink(QWebEnginePage):
        def dispose(self):
            pending.discard(self)
            self.deleteLater()

        def acceptNavigationRequest(self, url, _kind, main_frame):
            if not main_frame:
                return False
            if url.toString() == 'about:blank':
                return True
            if external(url):
                open_browser(url)
            QTimer.singleShot(0, self.dispose)
            return False

    def requested(request):
        if not request.isUserInitiated():
            return
        url = request.requestedUrl()
        if external(url):
            open_browser(url)
        elif url.isEmpty() or url.toString() == 'about:blank':
            # DSH first window.open('about:blank'), then after account RPC
            # popup.location.replace(authorizeUrl). The opener needs a real
            # page until that navigation arrives; it never loads remote bytes.
            popup = PendingLink(page.profile(), page)
            pending.add(popup)
            popup.windowCloseRequested.connect(popup.dispose)
            request.openIn(popup)

    page.newWindowRequested.connect(requested)
    parent._dsh_external_links = pending
