"""Read-only Qt diagnostics: real event loop, no live Host, user config or network changes."""
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
from hutil.Qt import QtCore, QtWidgets, QtGui
import dsh_network_diagnostics as network

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
    original = b'# keep\nUNRELATED=private-fixture\n'
    config.write_bytes(original)
    calls = []
    def fake_probe(*args, **kwargs):
        assert threading.get_ident() != main_thread, 'Network probe blocked the GUI thread'
        calls.append(kwargs)
        report = {'home': str(home), 'envFile': str(config), 'scope': 'new_process_configuration',
                  'configuration': {'source': 'windows', 'manualProxy': False, 'autoConfig': False, 'autoDetect': False},
                  'route': {'proxied': False, 'proxy': None}, 'proxyEntries': [], 'proxyDiagnostics': [],
                  'bridgeRoute': {'proxied': False}, 'search': {'componentInstalled': True, 'tested': False}}
        if not kwargs['inspect_only']:
            report['fetch'] = {'ok': False, 'code': 'WEB_BLOCKED_URL', 'message': 'non-public address',
                               'resolvedAddresses': ['198.18.0.1']}
        return report

    with patch.object(network, 'probe', side_effect=fake_probe), \
         patch.object(QtGui.QDesktopServices, 'openUrl', return_value=True) as opened:
        window = network.show(node='fixture-node', cli='fixture-cli', cwd=home, env={})
        test = window.findChild(QtWidgets.QPushButton, 'network-test')
        wait_until(lambda: test.isEnabled())
        assert len(calls) == 1 and calls[0]['inspect_only']
        route = window.findChild(QtWidgets.QLabel, 'network-route-summary').text()
        assert str(config) in route and 'Windows 系统设置' in route and '直连' in route, route
        assert network.show(node='unused', cli='unused', cwd=home, env={}) is window
        assert len(window.findChildren(QtWidgets.QLineEdit)) == 1, 'only the diagnostic URL is editable'
        assert not window.findChildren(QtWidgets.QComboBox), 'plugin must not own routing mode'
        assert not any('保存' in b.text() or '填入' in b.text() for b in window.findChildren(QtWidgets.QPushButton))
        assert opened.call_count == 0, 'system settings must open only after a user click'
        window.findChild(QtWidgets.QPushButton, 'network-system-settings').click()
        assert opened.call_args.args[0].toString() == 'ms-settings:network-proxy'
        test.click()
        wait_until(lambda: test.isEnabled())
        text = window.findChild(QtWidgets.QPlainTextEdit).toPlainText()
        assert 'Fake-IP' in text and '198.18.0.1' in text and '未调用' in text
        assert 'private-fixture' not in text
        with patch.object(network, 'probe', side_effect=RuntimeError('fixture unavailable')):
            test.click()
            wait_until(lambda: test.isEnabled())
        assert '未知' in window.findChild(QtWidgets.QLabel, 'network-route-summary').text()
        assert config.read_bytes() == original
        window.close()
        app.processEvents()
        assert network._WINDOW is None
print('Read-only network UI: system source, worker isolation, explicit OS settings action and untouched configuration passed')
