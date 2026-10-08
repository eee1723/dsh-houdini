"""Worker-side network diagnostics and explicit DSH-home proxy editing.

DSH owns environment precedence and network policy. This module never injects a
system proxy into a launcher, changes global environment, or restarts a Host.
"""
from pathlib import Path
import json
import os
import re
import subprocess
import urllib.parse
import uuid

DEFAULT_URL = 'https://www.sidefx.com/docs/houdini/hom/hou/Node.html'
_PROXY_ASSIGNMENT = re.compile(r'^\s*(?:export\s+)?(?P<name>https?_proxy)\s*=\s*(?P<value>.*)$', re.I)
_ASSIGNMENT = re.compile(r'^\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*(.*)$')
_WINDOW = None


def validate_proxy(value):
    value = value.strip()
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.port == 0:
            raise ValueError()
        if any(char in value for char in ('\n', '\r', '\x00', '"', "'", '\\')):
            raise ValueError()
    except ValueError:
        raise ValueError('代理地址须为有效的 http:// 或 https:// 地址；不支持 SOCKS/PAC。') from None
    return value


def redact_proxy(value):
    parsed = urllib.parse.urlsplit(validate_proxy(value))
    host = parsed.hostname
    if ':' in host:
        host = '[' + host + ']'
    authority = host + (':' + str(parsed.port) if parsed.port else '')
    if parsed.username is not None or parsed.password is not None:
        authority = 'redacted@' + authority
    return urllib.parse.urlunsplit((parsed.scheme, authority, '', '', ''))


def windows_proxy_suggestion():
    """Read WinINET's manual proxy as an editable suggestion, never an override."""
    if os.name != 'nt':
        return {'available': False, 'note': '此平台没有 Windows 系统代理建议。'}
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r'Software\Microsoft\Windows\CurrentVersion\Internet Settings') as key:
            enabled = winreg.QueryValueEx(key, 'ProxyEnable')[0]
            raw = winreg.QueryValueEx(key, 'ProxyServer')[0] if enabled else ''
    except OSError:
        raw = ''
    values = {}
    for item in raw.split(';'):
        if not item.strip():
            continue
        schemes, address = (item.split('=', 1) if '=' in item else ('http,https', item))
        address = address.strip()
        if '://' not in address:
            address = 'http://' + address
        try:
            address = validate_proxy(address)
        except ValueError:
            continue
        # Do not copy an OS-stored credential into a diagnostic result or form.
        if urllib.parse.urlsplit(address).username is not None:
            continue
        for scheme in schemes.split(','):
            if scheme.strip().lower() in ('http', 'https'):
                values[scheme.strip().lower()] = address
    return {'available': bool(values), 'values': values,
            'note': '仅作为建议，点击填入后仍需明确保存。' if values else
                    '未发现可用的手动 HTTP 系统代理；PAC/SOCKS 请使用 DSH 支持的显式 HTTP 代理。'}


def probe(node, cli, cwd, *, env=None, url=DEFAULT_URL, bridge_url=None, inspect_only=False):
    """Use the exact installed DSH APIs in a disposable Node process, never live RPC."""
    command = [str(node), str(Path(__file__).with_name('dsh_network_probe.mjs')), str(cli)]
    request = {'url': url, 'inspectOnly': inspect_only}
    if bridge_url:
        request['bridgeUrl'] = bridge_url
    result = subprocess.run(command, input=json.dumps(request), cwd=cwd,
                            env=dict(os.environ) if env is None else env, capture_output=True,
                            text=True, encoding='utf8', errors='replace', timeout=35,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    marker = 'DSH_NETWORK_DIAGNOSTIC='
    reports = [line[len(marker):] for line in result.stdout.splitlines() if line.startswith(marker)]
    if result.returncode or not reports:
        raise RuntimeError('无法运行配套 DSH 网络探针；请检查 Node/DSH 安装。退出码：' + str(result.returncode))
    report = json.loads(reports[-1])
    report['systemProxy'] = windows_proxy_suggestion()
    return report


def update_home_proxy(home, changes):
    """Explicit UI save only. Preserve unrelated .env bytes/comments and key casing.

    Both case variants for each edited protocol are reconciled together, because
    DSH gives lowercase priority. Unedited protocols and ALL_PROXY/NO_PROXY stay.
    """
    if not changes or set(changes) - {'http', 'https'}:
        raise ValueError('请选择要保存的 HTTP 或 HTTPS 代理。')
    values = {name: validate_proxy(value) for name, value in changes.items()}
    home = Path(home).resolve()
    filename = home / '.env'
    raw = filename.read_bytes() if filename.exists() else b''
    bom = raw.startswith(b'\xef\xbb\xbf')
    text = raw.decode('utf-8-sig')
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines(keepends=True)
    written = set()
    output = []
    multiline_quote = None
    for line in lines:
        if multiline_quote is not None:
            output.append(line)
            if multiline_quote in line:
                multiline_quote = None
            continue
        match = _PROXY_ASSIGNMENT.match(line.rstrip('\r\n'))
        protocol = match['name'].lower().removesuffix('_proxy') if match else None
        if protocol not in values:
            output.append(line)
            assignment = _ASSIGNMENT.match(line.rstrip('\r\n'))
            value = assignment[1].strip() if assignment else ''
            if value.startswith(('"', "'", '`')) and value.count(value[0]) < 2:
                multiline_quote = value[0]
            continue
        old = match['value'].strip()
        if old.startswith(('"', "'", '`')) and old.count(old[0]) < 2:
            raise ValueError('已有代理使用多行值，请打开 DSH .env 手动编辑；未写入任何内容。')
        prefix = line[:match.start('value')]
        # Retain trailing comments outside a quoted or unquoted proxy value.
        comment = ''
        if old.startswith(('"', "'", '`')):
            tail = old[old.find(old[0], 1) + 1:]
            if '#' in tail:
                comment = ' ' + tail[tail.index('#'):]
        elif '#' in old:
            comment = ' ' + old[old.index('#'):]
        ending = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
        output.append(prefix + json.dumps(values[protocol], ensure_ascii=False) + comment + ending)
        written.add(protocol)
    for protocol, value in values.items():
        if protocol in written:
            continue
        if output and not output[-1].endswith(('\n', '\r')):
            output[-1] += newline
        output.append(protocol.upper() + '_PROXY=' + json.dumps(value, ensure_ascii=False) + newline)
    payload = ''.join(output).encode('utf8')
    if bom:
        payload = b'\xef\xbb\xbf' + payload
    home.mkdir(parents=True, exist_ok=True)
    temporary = filename.with_name('.env.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, filename)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {'path': str(filename), 'updated': sorted(values),
            'note': '已保存到 DSH 用户配置。仅下次启动的 DSH 进程生效；当前运行服务没有重启。'}


def describe_report(report):
    lines = ['此配置下的新进程测试；不代表已经运行的 Host 已加载这些配置。']
    if report.get('error'):
        return '\n'.join(lines + ['原生 DSH 配置读取失败：' + report['error']])
    lines.append('用户配置：' + report['envFile'])
    if report.get('cwd'):
        lines.append('测试工作目录：' + report['cwd'])
    entries = report.get('proxyEntries', [])
    for entry in entries:
        source = {'process': '启动环境', 'user-env': 'DSH 用户配置', 'project-env': '项目配置'}.get(entry['source'], entry['source'])
        lines.append(f"{entry['name']}（{source}）：{entry['display']}")
    route = report.get('route', {})
    lines.append('本次网页路由：' + (route.get('proxy') or '直连'))
    lines.extend(report.get('proxyDiagnostics', []))
    fetch = report.get('fetch')
    if fetch:
        if fetch.get('ok'):
            lines.append(f"网页抓取：HTTP {fetch['status']}，{fetch['bodyChars']} 字符" + ('，内容已截断' if fetch['truncated'] else ''))
        else:
            lines.append('网页抓取失败：' + str(fetch.get('code') or fetch.get('status')) + ' · ' + fetch.get('message', '网站返回非成功状态'))
            addresses = fetch.get('resolvedAddresses', [])
            if addresses:
                lines.append('本机解析：' + ', '.join(addresses))
            if fetch.get('code') == 'WEB_BLOCKED_URL' and not route.get('proxied'):
                lines.append('非公网目标被原生抓取器拒绝。若使用 Fake-IP 网络代理，请显式配置 DSH 的 HTTP 代理；不要关闭地址检查。')
    search = report.get('search', {})
    lines.append('搜索：' + ('配套组件已安装' if search.get('componentInstalled') else '配套组件未找到') + '；未调用，未检查会话凭据或产生模型费用。')
    if report.get('bridgeRoute'):
        lines.append('本地 Bridge 路由：' + ('代理' if report['bridgeRoute']['proxied'] else '直连') + '（仅核对路由，没有请求 Bridge）。')
    return '\n'.join(lines)


def show(*, node, cli, cwd, env, bridge_url=None, parent=None):
    """A small native dialog; all configuration/network work runs off the GUI thread."""
    global _WINDOW
    import queue
    import threading
    from hutil.Qt import QtCore, QtWidgets, QtGui
    from dsh_ui_style import style_dialog, show_tool_window, confirm_dialog
    if _WINDOW is not None:
        show_tool_window(_WINDOW)
        return _WINDOW
    window = QtWidgets.QDialog(parent)
    window.setWindowTitle('DSH-Houdini · 联网诊断与代理设置')
    window.setMinimumWidth(650)
    style_dialog(window)
    layout = QtWidgets.QVBoxLayout(window)
    note = QtWidgets.QLabel('测试当前启动配置下的新进程。不会续跑会话、调用搜索模型或重启现有服务。')
    note.setWordWrap(True)
    layout.addWidget(note)
    url = QtWidgets.QLineEdit(DEFAULT_URL)
    url.setObjectName('network-url')
    layout.addWidget(url)
    test = QtWidgets.QPushButton('测试网页抓取')
    test.setObjectName('network-test')
    layout.addWidget(test)
    details = QtWidgets.QPlainTextEdit()
    details.setReadOnly(True)
    details.setMinimumHeight(210)
    layout.addWidget(details)
    fields = {}
    form = QtWidgets.QFormLayout()
    for protocol in ('http', 'https'):
        edit = QtWidgets.QLineEdit()
        edit.setObjectName('proxy-' + protocol)
        edit.setPlaceholderText('http://127.0.0.1:端口；留空保持原配置')
        edit.setEchoMode(QtWidgets.QLineEdit.PasswordEchoOnEdit)
        fields[protocol] = edit
        form.addRow(protocol.upper() + ' 代理', edit)
    layout.addLayout(form)
    buttons = QtWidgets.QHBoxLayout()
    suggest = QtWidgets.QPushButton('填入系统代理建议')
    save = QtWidgets.QPushButton('保存到 DSH 用户配置…')
    folder = QtWidgets.QPushButton('打开配置目录')
    for button in (suggest, save, folder):
        buttons.addWidget(button)
    layout.addLayout(buttons)
    status = QtWidgets.QLabel('正在读取原生 DSH 配置…')
    status.setWordWrap(True)
    layout.addWidget(status)
    events = queue.Queue()
    state = {'busy': False, 'report': None}
    controls = (test, suggest, save, folder)

    def run(operation):
        if state['busy']:
            return
        state['busy'] = True
        for button in controls:
            button.setEnabled(False)
        def worker():
            try:
                events.put(('done', operation()))
            except Exception as error:
                events.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def inspect(fetch=False):
        target = url.text().strip()
        status.setText('正在测试网页抓取…' if fetch else '正在读取原生 DSH 配置…')
        run(lambda: {'report': probe(node, cli, cwd, env=env, url=target,
                                    bridge_url=bridge_url, inspect_only=not fetch)})

    def fill_suggestion():
        suggestion = state['report'].get('systemProxy', {})
        for protocol, value in suggestion.get('values', {}).items():
            fields[protocol].setText(value)
        status.setText(suggestion.get('note', '没有可用建议；未保存任何配置。'))

    def save_proxy():
        report = state['report']
        try:
            changes = {key: validate_proxy(edit.text()) for key, edit in fields.items() if edit.text().strip()}
            if not changes:
                raise ValueError('请先填写要保存的代理；留空不会删除现有配置。')
        except ValueError as error:
            status.setText(str(error))
            return
        preview = '\n'.join(key.upper() + '_PROXY=' + redact_proxy(value) for key, value in changes.items())
        inherited = any(entry['source'] == 'process' for entry in report.get('proxyEntries', []))
        message = report['envFile'] + '\n\n' + preview + '\n\n只更新所选协议的用户配置，保留其他内容。下次启动 DSH 生效，不自动重启。'
        if inherited:
            message += '\n已有启动环境变量仍具有优先级；保存不会覆盖启动环境的选择。'
        if not confirm_dialog(window, '保存 DSH 代理配置', message, '保存'):
            return
        def commit():
            result = update_home_proxy(report['home'], changes)
            try:
                refreshed = probe(node, cli, cwd, env=env, url=url_value, bridge_url=bridge_url, inspect_only=True)
            except Exception as error:
                # The disk write is already complete. A failing readback must
                # not turn it into an ambiguous "save failed" UI response.
                return {'report': {'error': str(error)},
                        'message': result['note'] + ' 配置重新读取失败；可再次测试网页抓取以核对。'}
            return {'report': refreshed, 'message': result['note']}
        url_value = url.text().strip()
        run(commit)

    def open_folder():
        if not QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(state['report']['home'])):
            status.setText('无法打开配置目录：' + state['report']['home'])

    def tick():
        while not events.empty():
            kind, value = events.get_nowait()
            state['busy'] = False
            if kind == 'error':
                status.setText(value)
            else:
                state['report'] = value['report']
                details.setPlainText(describe_report(state['report']))
                status.setText(value.get('message') or ('网页抓取测试完成。' if 'fetch' in state['report'] else '配置已读取；未发起搜索调用。'))
            test.setEnabled(True)
            ready = bool(state['report'] and not state['report'].get('error'))
            save.setEnabled(ready)
            folder.setEnabled(ready)
            suggest.setEnabled(ready and state['report'].get('systemProxy', {}).get('available', False))

    test.clicked.connect(lambda: inspect(True))
    suggest.clicked.connect(fill_suggestion)
    save.clicked.connect(save_proxy)
    folder.clicked.connect(open_folder)
    timer = QtCore.QTimer(window)
    timer.timeout.connect(tick)
    timer.start(100)
    def close(_code):
        global _WINDOW
        timer.stop()
        _WINDOW = None
    window.finished.connect(close)
    _WINDOW = window
    window.show()
    inspect()
    return window
