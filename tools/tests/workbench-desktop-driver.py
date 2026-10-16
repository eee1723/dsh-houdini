import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_workbench_projects as projects
import dsh_workbench

folder = Path(os.environ['DSH_WORKBENCH_TEST_ROOT'])
original = projects.show_project_dialog
original_spawn = projects.subprocess.Popen


def observed_spawn(args, **kwargs):
    if str(args[0]).lower().endswith('houdini.exe'):
        (folder / 'launch-environment.json').write_text(json.dumps({'args': args, 'environment': {
            key: kwargs['env'].get(key) for key in ('HFS', 'HOUDINI_PATH', 'HOUDINI_USER_PREF_DIR', 'HOUDINI_PACKAGE_DIR', 'PYTHONPATH', 'DSH_HOUDINI_LAUNCH_TICKET')}}), encoding='utf-8')
    return original_spawn(args, **kwargs)


projects.subprocess.Popen = observed_spawn


def automated_dialog(*args, **kwargs):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QComboBox, QPushButton, QFileDialog
    choice = json.loads((folder / 'dialog-choice.json').read_text(encoding='utf-8'))
    dialog = original(*args, **kwargs)
    dialog.finished.connect(lambda result: (folder / 'dialog-finished').write_text(str(result), encoding='utf-8'))
    dialog.move(12000, 12000)
    timer = QTimer(dialog)
    def select():
        if choice.get('cancel'):
            timer.stop()
            dialog.reject()
            (folder / 'dialog-cancelled').touch()
            return
        button = dialog.findChild(QPushButton, 'primary')
        combo = dialog.findChild(QComboBox, 'houdini-version')
        if not button.isEnabled() or not combo.count():
            return
        matching = next((index for index in range(combo.count()) if os.path.normcase(combo.itemData(index)) == os.path.normcase(choice['hfs'])), None)
        if matching is None:
            raise AssertionError('Requested installed version missing from actual dialog')
        combo.setCurrentIndex(matching)
        assert not dialog.windowIcon().isNull(), 'the desktop must supply the custom application icon'
        dialog.grab().save(str(folder / ('native-dialog-' + choice['hfs'].replace(':', '').replace('/', '-').replace('\\', '-') + '.png')))
        if choice.get('hip'):
            original_picker = QFileDialog.getOpenFileName
            def pick(parent, title, initial, filters):
                picker = QFileDialog(parent, title, str(Path(choice['hip']).parent), filters)
                picker.setOption(QFileDialog.DontUseNativeDialog)
                picker.setFileMode(QFileDialog.ExistingFile)
                picker.selectFile(choice['hip'])
                QTimer.singleShot(100, picker.accept)
                return (picker.selectedFiles()[0], '') if picker.exec() else ('', '')
            QFileDialog.getOpenFileName = pick
            try:
                dialog.findChild(QPushButton, 'choose-hip').click()
            finally:
                QFileDialog.getOpenFileName = original_picker
        timer.stop()
        button.click()
        button.click()
    timer.timeout.connect(select)
    timer.start(100)
    return dialog


projects.show_project_dialog = automated_dialog
config = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
dsh_workbench.run(config)
