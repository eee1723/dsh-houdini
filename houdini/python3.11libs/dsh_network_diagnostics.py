"""Read-only diagnostics for the selected DSH transport; Windows owns network settings."""
from pathlib import Path
import json
import os
import subprocess

DEFAULT_URL = 'https://www.sidefx.com/docs/houdini/hom/hou/Node.html'
_WINDOW = None


def probe(node, cli, cwd, *, env=None, url=DEFAULT_URL, bridge_url=None, inspect_only=False):
    """Inspect the exact DSH in a disposable worker process; never write user configuration."""
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
    return json.loads(reports[-1])


def describe_report(report):
    lines = ['此配置下的新进程测试；不代表已经运行的 Host 已加载同一版本和配置。']
    if report.get('error'):
        return '\n'.join(lines + ['DSH 网络配置读取失败：' + report['error']])
    lines.append('用户配置位置：' + report['envFile'])
    lines.append('测试工作目录：' + report.get('cwd', '未知'))
    source = report.get('configuration', {}).get('source')
    lines.append('网络设置来源：' + {'windows': 'Windows 系统设置', 'environment': '显式环境配置',
                                      'direct': '默认直连'}.get(source, '未知'))
    for entry in report.get('proxyEntries', []):
        origin = {'process': '启动环境', 'user-env': 'DSH 用户配置', 'project-env': '项目配置'}.get(entry['source'], entry['source'])
        lines.append(f"{entry['name']}（{origin}）：{entry['display']}")
    if source == 'environment':
        lines.append('显式代理环境配置优先于系统设置；关闭系统代理不会清除这些覆盖。')
    route = report.get('route', {})
    lines.append('此地址实际路线：' + (route.get('proxy') or '直连'))
    lines.append('应用直连仍经过系统网络；VPN/TUN 由系统管理。')
    lines.extend(report.get('proxyDiagnostics', []))
    fetch = report.get('fetch')
    if fetch:
        if fetch.get('ok'):
            lines.append(f"网页抓取：HTTP {fetch['status']}，{fetch['bodyChars']} 字符" + ('，内容已截断' if fetch['truncated'] else ''))
        else:
            lines.append('抓取失败：' + str(fetch.get('code') or fetch.get('status')) + ' · ' + fetch.get('message', '网站返回非成功状态'))
            if fetch.get('proxyUnavailable'):
                lines.append('配置的代理端口拒绝连接，尚未连接到目标网站。请检查系统代理软件是否退出或端口是否变化。')
            addresses = fetch.get('resolvedAddresses', [])
            if addresses:
                lines.append('本机解析：' + ', '.join(addresses))
            if fetch.get('code') == 'WEB_BLOCKED_URL' and not route.get('proxied'):
                lines.append('非公网目标被抓取器拒绝。Fake-IP/TUN 场景请核对系统代理或 DNS 设置；不会关闭地址检查。')
    search = report.get('search', {})
    lines.append('搜索：' + ('配套组件已安装' if search.get('componentInstalled') else '配套组件未找到') + '；未调用，未检查凭据或产生模型费用。')
    if report.get('bridgeRoute'):
        lines.append('本地 Bridge 路由：' + ('代理' if report['bridgeRoute']['proxied'] else '直连') + '（仅核对路由，没有请求 Bridge）。')
    return '\n'.join(lines)


def show_current(parent=None):
    import dsh_launcher
    import dsh_managed_runtime
    command, shell, _source, _timeout = dsh_launcher._frontend_command()
    if shell or not isinstance(command, list):
        raise RuntimeError('请先准备配套 DSH；联网诊断不会自动下载或运行 npx。')
    return show(node=command[0], cli=command[1], cwd=dsh_launcher._hip_dir(),
                env=dsh_managed_runtime.environment(),
                bridge_url=f'http://127.0.0.1:{dsh_launcher.BRIDGE_PORT}', parent=parent)


def show(*, node, cli, cwd, env, bridge_url=None, parent=None):
    """All native/system/network inspection happens on a worker, never the Houdini GUI thread."""
    global _WINDOW
    import queue
    import threading
    from hutil.Qt import QtCore, QtWidgets, QtGui
    from dsh_ui_style import style_dialog, show_tool_window
    if _WINDOW is not None:
        show_tool_window(_WINDOW)
        return _WINDOW
    window = QtWidgets.QDialog(parent)
    window.setWindowTitle('DSH-Houdini · 联网诊断')
    window.setMinimumWidth(650)
    style_dialog(window)
    layout = QtWidgets.QVBoxLayout(window)
    note = QtWidgets.QLabel('网络由系统和 DSH 运行环境管理。此窗口只读诊断，不修改代理、不续跑会话、不重启服务。')
    note.setWordWrap(True)
    layout.addWidget(note)
    route_label = QtWidgets.QLabel('正在读取实际网络来源…')
    route_label.setObjectName('network-route-summary')
    route_label.setWordWrap(True)
    route_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    layout.addWidget(route_label)
    url = QtWidgets.QLineEdit(DEFAULT_URL)
    url.setObjectName('network-url')
    layout.addWidget(url)
    test = QtWidgets.QPushButton('测试此地址')
    test.setObjectName('network-test')
    layout.addWidget(test)
    details = QtWidgets.QPlainTextEdit()
    details.setReadOnly(True)
    details.setMinimumHeight(230)
    layout.addWidget(details)
    system = QtWidgets.QPushButton('打开 Windows 网络设置')
    system.setObjectName('network-system-settings')
    system.setVisible(os.name == 'nt')
    layout.addWidget(system)
    status = QtWidgets.QLabel('正在读取原生 DSH 网络配置…')
    status.setWordWrap(True)
    layout.addWidget(status)
    events = queue.Queue()
    state = {'busy': False}

    def inspect(fetch=False):
        if state['busy']:
            return
        state['busy'] = True
        test.setEnabled(False)
        target = url.text().strip()
        status.setText('正在测试此地址…' if fetch else '正在读取配置和解析路由…')
        def worker():
            try:
                events.put(probe(node, cli, cwd, env=env, url=target,
                                 bridge_url=bridge_url, inspect_only=not fetch))
            except Exception as error:
                events.put({'error': str(error)})
        threading.Thread(target=worker, daemon=True).start()

    def tick():
        while not events.empty():
            report = events.get_nowait()
            state['busy'] = False
            test.setEnabled(True)
            source = {'windows': 'Windows 系统设置', 'environment': '显式环境配置', 'direct': '默认直连'}.get(
                report.get('configuration', {}).get('source'), '未知')
            route_label.setText('网络状态未知：读取失败' if report.get('error') else
                '来源：' + source + '\n此地址路线：' + (report.get('route', {}).get('proxy') or '直连') +
                '\n配置位置：' + report.get('envFile', '未知'))
            details.setPlainText(describe_report(report))
            status.setText('诊断失败；详情见上方。' if report.get('error') else
                           '测试完成。' if 'fetch' in report else '配置已读取；未发起目标网页或搜索调用。')

    def open_system():
        if not QtGui.QDesktopServices.openUrl(QtCore.QUrl('ms-settings:network-proxy')):
            status.setText('无法打开 Windows 设置；可从系统设置进入“网络和 Internet → 代理”。')

    test.clicked.connect(lambda: inspect(True))
    system.clicked.connect(open_system)
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
