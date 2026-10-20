"""Real Qt startup feedback with isolated resources and no model/Houdini scene."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli
from dsh_workbench import desktop_environment


def worker_test(folder):
    import dsh_workbench as desktop
    dll_directory = os.add_dll_directory(str(Path(os.environ['HFS']) / 'bin'))
    from PySide6.QtCore import QCoreApplication, QThread, QTimer, Qt
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([])
    main_thread = threading.get_ident()
    observed = {'ticks': 0, 'firstPaint': None, 'phase': False, 'elapsed': False}
    began = time.monotonic()
    timer = QTimer()
    def tick():
        observed['ticks'] += 1
        for window in app.topLevelWidgets():
            if '正在打开工作台' not in window.windowTitle():
                continue
            assert QThread.currentThread() == app.thread()
            if observed['firstPaint'] is None and window.isVisible():
                observed['firstPaint'] = round(time.monotonic() - began, 3)
                window.move(12000, 12000)
            labels = [label.text() for label in window.findChildren(QLabel)]
            observed['phase'] |= '正在检查配套运行环境…' in labels
            observed['elapsed'] |= '已等待 1 秒' in labels
            if observed['phase'] and observed['elapsed'] and window.isVisible():
                window.grab().save(str(folder / 'startup-feedback.png'))
                next(button for button in window.findChildren(QPushButton) if button.text() == '后台打开').click()
    timer.timeout.connect(tick)
    timer.start(50)
    def start(config, progress):
        assert threading.get_ident() != main_thread, 'preparation ran on the GUI thread'
        progress('Checking the bundled Node, DSH and plugin')
        time.sleep(1.4)
        observed['workerFinished'] = round(time.monotonic() - began, 3)
        return 'ready fixture'
    config = {'root': str(folder), 'hfs': os.environ['HFS']}
    with patch.object(desktop, '_start_runtime', start), \
         patch.object(desktop, 'atomic_json', side_effect=PermissionError('optional progress path is locked')) as write_progress, \
         patch.object(desktop, 'read_json', side_effect=PermissionError('optional progress path is locked')) as read_progress:
        returned_app, dialog, ready = desktop._prepare_with_feedback(config)
        write_progress.assert_not_called()
        read_progress.assert_not_called()
    timer.stop()
    assert returned_app is app and ready == 'ready fixture'
    assert observed['ticks'] >= 15 and observed['firstPaint'] is not None, observed
    assert observed['firstPaint'] < observed['workerFinished'] and observed['phase'] and observed['elapsed'], observed
    assert not dialog.isVisible(), 'background open did not hide only the waiting window'
    assert not list(folder.glob('workbench/starting-*')), 'startup must not create auxiliary progress files'
    failure = RuntimeError('fixture preparation failed')
    with patch.object(desktop, '_start_runtime', side_effect=failure):
        try:
            desktop._prepare_with_feedback(config)
        except RuntimeError as error:
            assert error is failure
        else:
            raise AssertionError('startup failure was swallowed')
    # Opening the parent entry needs only the established desktop identity.
    # A locked legacy progress path cannot stop a successful child activation.
    parent_root = folder / 'parent-entry'
    child = Mock(pid=77123)
    record = {'pid': child.pid, 'installation': str(ROOT)}
    progress = Mock()
    parent_config = {'root': str(parent_root), 'installation': str(ROOT),
                     'hfs': os.environ['HFS'], 'python': sys.executable}
    with patch.object(desktop, 'running', side_effect=[None, record]), \
         patch.object(desktop, 'control', return_value={'record': record}), \
         patch.object(desktop, 'read_json', side_effect=PermissionError('optional progress path is locked')) as legacy_progress, \
         patch.object(desktop.subprocess, 'Popen', return_value=child):
        assert desktop.ensure(parent_config) == {'record': record}
        legacy_progress.assert_not_called()
    # Once the child owns startup, a slow preparation is still pending rather
    # than a parent timeout followed by an unexpected window opening later.
    child.poll.return_value = None
    with patch.object(desktop, 'running', side_effect=[None, None, record]), \
         patch.object(desktop, 'control', return_value={'record': record}), \
         patch.object(desktop.time, 'monotonic', side_effect=[0, 151]), \
         patch.object(desktop.time, 'sleep'), \
         patch.object(desktop.subprocess, 'Popen', return_value=child):
        assert desktop.ensure(parent_config) == {'record': record}
    launch_config = json.loads((parent_root / 'workbench/launch-config.json').read_text(encoding='utf-8'))
    assert 'startupId' not in launch_config
    assert not list((parent_root / 'workbench').glob('starting-*'))
    with patch.object(desktop, 'running', return_value=record), \
         patch.object(desktop, 'control', return_value={'record': record}):
        assert desktop.ensure(parent_config, progress=progress) == {'record': record}
    progress.assert_called_once_with('正在打开 DSH-Houdini 工作台…')
    # A UI initialization failure must reclaim the already-started Host/lease.
    import dsh_managed_runtime
    lease = Mock()
    host = object()
    with patch.object(desktop, '_prepare_with_feedback', return_value=(app, dialog, ({}, lease, ROOT, host, '', None, None))), \
         patch.object(desktop, '_run_window', side_effect=RuntimeError('fixture UI failed')), \
         patch.object(dsh_managed_runtime, 'stop_owned') as stop:
        try:
            desktop.run(config)
        except RuntimeError as error:
            assert str(error) == 'fixture UI failed'
        else:
            raise AssertionError('UI failure was swallowed')
        stop.assert_called_once_with(host)
        lease.close.assert_called_once_with()
    (folder / 'result.json').write_text(json.dumps(observed), encoding='utf-8')
    print('PASS real Qt initial feedback, responsive timer, truthful stage/elapsed, background waiting and startup failure: ' + json.dumps(observed), flush=True)


def main():
    reexec_unpacked_test_cli()
    if '--worker' in sys.argv:
        worker_test(Path(sys.argv[-1]))
        return
    hfs = Path(sys.argv[1] if len(sys.argv) > 1 else 'D:/houdini')
    python = next(hfs.glob('python3*/python.exe'))
    folder = Path(tempfile.mkdtemp(prefix='startup-feedback-', dir=ROOT / 'tools/out'))
    env = isolated_environment(folder / 'environment', gui=True)
    env.update(desktop_environment(hfs, python))
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONPATH'] += os.pathsep + str(ROOT / 'houdini/python3.11libs')
    result = subprocess.run([str(python), str(Path(__file__).resolve()), '--worker', str(folder)],
        cwd=hfs / 'bin', env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (folder / 'test.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    assert result.returncode == 0, str(folder) + '\n' + result.stdout + result.stderr
    print(result.stdout.strip() + '\nEvidence: ' + str(folder), flush=True)


if __name__ == '__main__':
    main()
