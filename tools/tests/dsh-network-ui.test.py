"""Isolated Qt network settings interaction; no live Host, browser or home writes."""
from pathlib import Path
import os
import sys
import tempfile
import threading
import time
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from hutil.Qt import QtCore, QtWidgets
import dsh_network_diagnostics as network
import dsh_ui_style as style

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
main_thread = threading.get_ident()


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline, 'Network UI worker did not finish'
        app.processEvents()
        time.sleep(.01)
    app.processEvents()


with tempfile.TemporaryDirectory(prefix='dsh-network-ui-') as raw:
    home = Path(raw)
    config = home / '.env'
    config.write_text('# keep\nOTHER=value\n', encoding='utf8')
    calls, confirmations = [], []
    allow_save = [False]

    def fake_probe(*args, **kwargs):
        assert threading.get_ident() != main_thread, 'Network probe blocked the GUI thread'
        calls.append(kwargs)
        report = {'home': str(home), 'envFile': str(config), 'scope': 'new_process_configuration',
                  'route': {'proxied': False, 'proxy': None}, 'proxyEntries': [], 'proxyDiagnostics': [],
                  'bridgeRoute': {'proxied': False}, 'search': {'componentInstalled': True, 'tested': False},
                  'systemProxy': {'available': True, 'values': {'http': 'http://127.0.0.1:7897',
                      'https': 'http://127.0.0.1:7897'}, 'note': '仅建议，未保存。'}}
        if not kwargs['inspect_only']:
            report['fetch'] = {'ok': False, 'code': 'WEB_BLOCKED_URL', 'message': 'non-public address',
                               'resolvedAddresses': ['198.18.0.1']}
        return report

    def confirm(*args):
        confirmations.append(args)
        return allow_save[0]

    with patch.object(network, 'probe', side_effect=fake_probe), patch.object(style, 'confirm_dialog', side_effect=confirm):
        window = network.show(node='fixture-node', cli='fixture-cli', cwd=home, env={})
        test = window.findChild(QtWidgets.QPushButton, 'network-test')
        wait_until(lambda: test.isEnabled())
        assert len(calls) == 1 and calls[0]['inspect_only']
        text = window.findChild(QtWidgets.QPlainTextEdit).toPlainText()
        assert '新进程测试' in text and '未调用' in text and '没有请求 Bridge' in text
        assert network.show(node='unused', cli='unused', cwd=home, env={}) is window
        suggest = next(b for b in window.findChildren(QtWidgets.QPushButton) if b.text() == '填入系统代理建议')
        suggest.click()
        assert config.read_text(encoding='utf8') == '# keep\nOTHER=value\n'
        http = window.findChild(QtWidgets.QLineEdit, 'proxy-http')
        https = window.findChild(QtWidgets.QLineEdit, 'proxy-https')
        http.setText('')
        https.setText('http://alice:private-fixture@127.0.0.1:7897')
        save = next(b for b in window.findChildren(QtWidgets.QPushButton) if b.text() == '保存到 DSH 用户配置…')
        save.click()
        assert config.read_text(encoding='utf8') == '# keep\nOTHER=value\n'
        assert 'private-fixture' not in str(confirmations) and 'alice' not in str(confirmations)
        allow_save[0] = True
        save.click()
        wait_until(lambda: save.isEnabled())
        assert config.read_text(encoding='utf8') == '# keep\nOTHER=value\nHTTPS_PROXY="http://alice:private-fixture@127.0.0.1:7897"\n'
        test.click()
        wait_until(lambda: test.isEnabled())
        text = window.findChild(QtWidgets.QPlainTextEdit).toPlainText()
        assert 'Fake-IP' in text and 'WEB_BLOCKED_URL' in text and '198.18.0.1' in text
        assert 'private-fixture' not in text
        # The write and its later diagnostic readback are separate effects.
        # A failed probe must still tell the user that the file was saved.
        https.setText('http://127.0.0.1:7898')
        with patch.object(network, 'probe', side_effect=RuntimeError('fixture readback unavailable')):
            save.click()
            wait_until(lambda: test.isEnabled())
        assert 'HTTPS_PROXY="http://127.0.0.1:7898"' in config.read_text(encoding='utf8')
        assert any('已保存到 DSH 用户配置' in label.text() and '重新读取失败' in label.text()
                   for label in window.findChildren(QtWidgets.QLabel))
        assert not save.isEnabled()
        window.close()
        app.processEvents()
        assert network._WINDOW is None
print('Network Qt UI: worker isolation, explicit save/cancel, credential redaction and accurate failure scope passed')
