"""Explicit candidate registration UI; never starts/stops a shared DSH Host.

Current menu launch stays unchanged. Registry selection is a user action; main
thread captures HIP/Bridge facts, worker owns file locks and publication.
"""
from pathlib import Path
import os
import threading
import atexit

_BUSY = False
_TIMER = None


def prepare_registration():
    import hou
    import dsh_bridge as bridge
    from dsh_managed_runtime import has_owned_frontend
    if threading.get_ident() != bridge._HOU_THREAD_ID:
        raise RuntimeError('登记必须从 Houdini 主线程发起')
    if has_owned_frontend():
        raise RuntimeError('当前 Houdini 已运行独立 DSH 服务。请先保存工作，再用新打开的 Houdini 登记共享执行端。')
    if bridge._request_registry.active_count() or bridge._job_activity()['activeJobs'] or not bridge._work_queue.empty():
        raise RuntimeError('请等待当前 Houdini 操作完成，再登记共享执行端。')
    hip = hou.hipFile.path()
    if hou.hipFile.isNewFile():
        raise RuntimeError('请先保存并命名工程，再登记共享执行端。')
    # Bind directly to port zero; keep the server socket, no probe/rebind race.
    server = bridge._server or bridge.start(0)
    return {'hip': hip, 'version': bridge._HOU_VERSION, 'executor_id': bridge._EXECUTOR_ID,
            'runtime_id': bridge._RUNTIME_ID, 'port': server.server_port,
            'installation': str(Path(__file__).resolve().parents[2])}


def publish_registration(root, facts):
    from dsh_executor_registry import activate, active_registration
    root = Path(root)
    if not root.is_absolute():
        raise ValueError('请填写共享 DSH 登记目录的完整路径。')
    if not Path(facts['hip']).is_file():
        raise ValueError('工程尚未保存到磁盘。')
    try:
        registration = active_registration()
    except RuntimeError:
        registration = activate(root, facts['executor_id'], installation=facts['installation'],
            version=facts['version'],port=facts['port'],runtime_id=facts['runtime_id'],hip=facts['hip'])
        atexit.register(registration.close)
    else:
        if registration.root != root.resolve() or registration.executor_id != facts['executor_id']:
            raise RuntimeError('当前 Houdini 已登记到其他共享服务，无法自动切换。')
    return registration.publish(facts['port'], facts['runtime_id'], hip=facts['hip'])


def repair_registration():
    """Owning thread only: repair this Bridge, never the shared frontend."""
    from dsh_executor_registry import active_registration
    from dsh_launcher import restart_bridge
    registration = active_registration()
    facts = prepare_registration()
    if registration.executor_id != facts['executor_id']:
        raise RuntimeError('共享执行端身份已变化，无法接管此进程。')
    if registration._task is not None:
        registration.require_writer(registration._task, facts['hip'])
    restart_bridge(port=facts['port'])
    return registration.root, prepare_registration()


def show_registration(*, repair=False):
    global _BUSY, _TIMER
    import hou
    from hutil.Qt import QtCore, QtWidgets
    from dsh_ui_style import style_dialog
    if _BUSY:
        return
    parent = hou.qt.mainWindow()

    def message(text, *, question=False):
        dialog = QtWidgets.QMessageBox(parent)
        style_dialog(dialog)
        dialog.setWindowTitle("DSH-Houdini · 共享执行端")
        dialog.setText(text)
        dialog.setTextFormat(QtCore.Qt.PlainText)
        if question:
            confirm = dialog.addButton("修复连接", QtWidgets.QMessageBox.AcceptRole)
            cancel = dialog.addButton("取消", QtWidgets.QMessageBox.RejectRole)
            dialog.setDefaultButton(cancel)
            dialog.setEscapeButton(cancel)
        else:
            confirm = dialog.addButton("知道了", QtWidgets.QMessageBox.AcceptRole)
        dialog.exec()
        return dialog.clickedButton() is confirm

    if repair:
        if not message("重新连接当前 Houdini？\n\n只重启当前执行端的连接，不会停止共享 DSH 服务或其他执行端。"
                       "正在执行的 Houdini 操作会阻止修复；之前尚未返回的结果无法重放。", question=True):
            return
        value = None
    else:
        dialog = QtWidgets.QInputDialog(parent)
        style_dialog(dialog)
        dialog.setWindowTitle("DSH-Houdini · 登记共享执行端")
        dialog.setLabelText("共享服务的登记目录\n填写共享 DSH 服务配置的同一目录。登记后还需在任务中选择当前工程。")
        dialog.setTextValue(os.environ.get('DSH_HOUDINI_EXECUTOR_REGISTRY', ''))
        dialog.setOkButtonText("登记")
        dialog.setCancelButtonText("取消")
        dialog.resize(560, 180)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        value = dialog.textValue().strip()
    try:
        if repair:
            value, facts = repair_registration()
        else:
            if not Path(value).is_absolute():
                raise ValueError('请填写登记目录的完整路径。')
            facts = prepare_registration()
    except Exception as error:
        message(str(error))
        return
    _BUSY = True
    state = {}

    def worker():
        try:
            state['result'] = publish_registration(value, facts)
        except Exception as error:
            state['error'] = str(error)
        finally:
            state['done'] = True

    def finish():
        global _BUSY, _TIMER
        if not state.get('done'):
            return
        _TIMER.stop()
        _TIMER = None
        _BUSY = False
        if state.get('error'):
            message("共享连接未完成：" + state['error'])
        else:
            message("共享执行端已登记。\n\n在共享 DSH 任务的「Houdini 执行端」中选择当前工程，即可建立任务连接。"
                    "登记本身不会授予修改其他作者节点的权限。")

    _TIMER = QtCore.QTimer(parent)
    _TIMER.timeout.connect(finish)
    _TIMER.start(100)
    threading.Thread(target=worker, daemon=True).start()
