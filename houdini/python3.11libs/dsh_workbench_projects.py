"""Desktop-owned explicit project launches and non-HOM presence observations."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import threading
import time
import subprocess
import urllib.request
import uuid

from dsh_deployment import _process_started, atomic_json, read_json
from dsh_executor_registry import read_candidates
from dsh_houdini_installations import discover, installation, launch_environment

# Single timeout policy for the one on-demand GET /health probe. Stricter than
# any client-side staleness window; a slow answer is 'unknown', never 'offline'.
HEALTH_TIMEOUT_SECONDS = 1.5


def path_key(value):
    # Lexical key, matching dsh_project_paths: realpath/stat can hang on an
    # unavailable UNC share. A registry row with no HIP is a real new-file case.
    return None if value is None else os.path.normcase(os.path.normpath(value))


def dialog_request(payload):
    if not isinstance(payload, dict):
        raise ValueError('工程操作无效。')
    action = payload.get('action')
    if action in ('open', 'new') and set(payload) in ({'action'}, {'action', 'bindSessionId'}):
        if 'bindSessionId' not in payload or isinstance(payload['bindSessionId'], str) and 0 < len(payload['bindSessionId']) <= 256:
            return payload
    if action == 'reopen' and set(payload) == {'action', 'hip', 'sessionId', 'executorId'}:
        if (all(isinstance(payload[key], str) and 0 < len(payload[key]) <= 4096 for key in ('hip', 'sessionId', 'executorId'))
                and Path(payload['hip']).is_absolute() and len(payload['executorId']) == 32):
            return payload
    raise ValueError('工程操作无效。')


def endpoint_presence(record, registry):
    """Single presence interpreter: registry lifetime + one GET /health.

    A read-only poll never touches FileLease — it must not create locks. The
    registry record already carries pid/processStarted, so process lifetime is
    answered there; only a live process is worth one HTTP probe.
    """
    result = {'executorId': record['executor_id'], 'sceneEpoch': record.get('scene_epoch'),
              'hipPath': record.get('hip_path'), 'status': 'unknown', 'observedAt': time.time() * 1000}
    if record.get('state') != 'registered':
        return {**result, 'status': 'offline'}
    pid = record.get('pid')
    started = _process_started(pid) if isinstance(pid, int) and pid > 0 else None
    # A reused pid is not this executor: the recorded birth must still match.
    if started is None or (record.get('processStarted') is not None and started != record.get('processStarted')):
        return {**result, 'status': 'offline'}
    request = urllib.request.Request(record['bridge_url'] + '/health', headers={'X-DSH-Houdini-Executor': record['executor_id']})
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=HEALTH_TIMEOUT_SECONDS) as response:
            data = response.read(65537)
        if len(data) > 65536:
            return result
        health = json.loads(data)
        if health.get('ok') is not True or health.get('executorId') != record['executor_id'] or health.get('runtimeId') != record['runtime_id']:
            return result
        return {**result, 'status': 'online', 'sceneEpoch': health.get('sceneEpoch'),
                'busy': bool(health.get('activeRequests') or health.get('activeJobs')),
                'contractVersion': health.get('executionContractVersion')}
    except Exception:
        # A failed probe on a live process is unproven, never an exit proof.
        return result


class ProjectManager:
    def __init__(self, config, context, plugin, generation, rpc, intents):
        self.config, self.context, self.plugin = config, context, Path(plugin)
        self.generation, self.rpc, self.intents = generation, rpc, intents
        self.folder = Path(context['root']) / 'workbench/launches'
        self.folder.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._processes = {}

    def candidates(self):
        return read_candidates(self.context['executorRegistry'], installation=self.plugin)

    def presence(self):
        # On-demand only (menu open / target confirmation). No cache: a stale
        # answer here is how a closed Houdini still looked online.
        records = self.candidates()
        with ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(lambda record: endpoint_presence(record, self.context['executorRegistry']), records))

    def installations(self):
        items = discover(self.config['hfs'])
        if self.config.get('managed'):
            from dsh_deployment import Store
            supported = Store(self.config['root'], self.config['trustData']).manifest(self.config['installation'])['houdini']
            items = [item for item in items if item['series'] in supported]
        return items

    def _read(self, identifier):
        if not isinstance(identifier, str) or len(identifier) != 32 or any(character not in '0123456789abcdef' for character in identifier):
            raise ValueError('启动请求无效。')
        return read_json(self.folder / (identifier + '.json'))

    def _write(self, value):
        atomic_json(self.folder / (value['id'] + '.json'), value)
        print('[dsh-houdini] launch ' + value['id'] + ': ' + value['phase'] + (': ' + value['error'] if value.get('error') else ''), flush=True)

    def launch(self, action, hfs, hip=None, session_id=None, bind_session_id=None, should_navigate=lambda: True):
        if action not in ('open', 'new', 'reopen'):
            raise ValueError('未知的工程操作。')
        selected = next((item for item in self.installations() if path_key(item['hfs']) == path_key(hfs)), None)
        if selected is None:
            raise ValueError('所选 Houdini 不在可用版本中，请重新选择。')
        expected = None
        if action != 'new':
            expected = Path(hip).resolve()
            if expected.suffix.lower() not in ('.hip', '.hiplc', '.hipnc') or not expected.is_file():
                raise ValueError('请选择现有的 Houdini 工程文件。')
        with self._lock:
            if expected:
                located = [(record, endpoint_presence(record, self.context['executorRegistry'])['status'])
                           for record in self.candidates() if record.get('hip_path') and path_key(record['hip_path']) == path_key(expected)]
                if any(status == 'unknown' for record, status in located):
                    raise RuntimeError('这份工程已有窗口暂时无法确认连接。请从对应 Houdini 的 Open Workspace 接入，或确认它已退出后重试；没有再开同一文件。')
                matching = [record for record, status in located if status == 'online']
                if len(matching) > 1:
                    raise RuntimeError('这份文件已在多个 Houdini 中打开，请从要使用的那个窗口打开工作台；没有猜测目标。')
                if matching:
                    record = matching[0]
                    if record.get('houdini_version') != selected['version']:
                        raise RuntimeError('这份工程已在 Houdini ' + str(record.get('houdini_version')) + ' 中打开。请选择该版本继续使用；要换版本，请先保存并退出原 Houdini。')
                    result = self.rpc('houdiniTargets/openWorkspace', {'executorId': record['executor_id'],
                        'registrationId': record['registration_id'], 'expectedHip': record['hip_path'], 'requestId': uuid.uuid4().hex,
                        **({'sessionId': session_id} if session_id else {'bindSessionId': bind_session_id} if bind_session_id else {})})
                    if should_navigate():
                        self.intents.put(result)
                    return {'id': None, 'phase': 'ready', 'result': result}
                for filename in self.folder.glob('*.json'):
                    try:
                        pending = read_json(filename)
                    except (OSError, ValueError) as error:
                        # One torn ticket must not block a legitimate open.
                        print('[dsh-houdini] launch ticket unreadable, skipped: ' + filename.name + ': ' + str(error), flush=True)
                        continue
                    if not isinstance(pending, dict):
                        continue
                    # Only this workbench generation's unfinished ticket blocks a
                    # re-open. A prior generation's ticket is an orphan: its attach
                    # cannot succeed against this workbench, so it must not lock
                    # the HIP out of a legitimate open forever.
                    if (pending.get('generation') == self.generation and pending.get('hip')
                            and path_key(pending['hip']) == path_key(expected) and pending.get('pid')
                            and _process_started(pending['pid']) == pending.get('processStarted') and pending.get('phase') != 'ready'):
                        raise RuntimeError('这份工程已经在启动或等待连接。请查看对应 Houdini；没有重复启动。')
            identifier = uuid.uuid4().hex
            workspace = str(expected.parent) if expected else str(Path(self.context['root']) / 'workspaces' / ('unsaved-' + identifier))
            Path(workspace).mkdir(parents=True, exist_ok=True)
            ticket = {'id': identifier, 'generation': self.generation, 'root': self.context['root'], 'plugin': str(self.plugin),
                      'hfs': selected['hfs'], 'hip': str(expected) if expected else None, 'workspace': workspace,
                      'phase': 'starting', 'sessionId': session_id, 'bindSessionId': bind_session_id, 'navigate': bool(should_navigate()), 'createdAt': time.time()}
            self._write(ticket)
            ticket_path = self.folder / (identifier + '.json')
            args = [selected['executable'], '-foreground']
            if expected:
                args.append(str(expected))
            with (self.folder / (identifier + '.log')).open('ab') as output:
                process = subprocess.Popen(args, cwd=selected['hfs'] + '/bin', env=launch_environment(selected['hfs'], self.plugin, self.context, ticket_path),
                    stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, close_fds=True,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self._processes[identifier] = process
            ticket.update(pid=process.pid, processStarted=_process_started(process.pid), phase='waiting')
            self._write(ticket)
            return {'id': identifier, 'phase': 'waiting'}

    def status(self, identifier):
        with self._lock:
            ticket = self._read(identifier)
            process = self._processes.get(identifier)
            if ticket['phase'] == 'waiting' and process is not None and process.poll() is not None:
                ticket.update(phase='failed', error='Houdini 未完成启动，退出代码 ' + str(process.returncode) + '。请检查许可或运行报告。')
                self._write(ticket)
            return {**{key: ticket.get(key) for key in ('id', 'phase', 'error', 'result')}, 'elapsed': max(0, time.time() - ticket.get('createdAt', time.time()))}

    def detach(self, identifier):
        with self._lock:
            ticket = self._read(identifier)
            ticket['navigate'] = False
            self._write(ticket)

    def attached(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'id', 'executorId', 'registrationId', 'expectedHip'}:
            raise ValueError('启动回执无效。')
        with self._lock:
            ticket = self._read(payload['id'])
            if ticket['generation'] != self.generation:
                raise RuntimeError('工作台已重开，请在 Houdini 中重新打开工作区。')
            if ticket['phase'] == 'ready':
                if ticket.get('callback') != payload:
                    raise RuntimeError('启动回执与已完成的请求不一致。')
                return ticket['result']
            record = next((item for item in self.candidates() if item['executor_id'] == payload['executorId']), None)
            if (ticket['phase'] != 'waiting' or not record or record['pid'] != ticket.get('pid')
                    or _process_started(record['pid']) != ticket.get('processStarted')
                    or record['registration_id'] != payload['registrationId'] or path_key(record['hip_path']) != path_key(payload['expectedHip'])
                    or ticket['hip'] and path_key(record['hip_path']) != path_key(ticket['hip'])
                    or not ticket['hip'] and record.get('hip_is_new') is not True):
                raise RuntimeError('启动回执与选择的 Houdini 或工程不一致，未绑定其他工程。')
            result = self.rpc('houdiniTargets/openWorkspace', {'executorId': record['executor_id'],
                'registrationId': record['registration_id'], 'expectedHip': record['hip_path'], 'requestId': ticket['id'],
                **({'sessionId': ticket['sessionId']} if ticket.get('sessionId') else {'bindSessionId': ticket['bindSessionId']} if ticket.get('bindSessionId') else {})})
            ticket.update(phase='ready', result=result, callback=payload)
            self._write(ticket)
            if ticket['navigate']:
                self.intents.put(result)
            return result

    def failed(self, payload):
        with self._lock:
            ticket = self._read(payload.get('id'))
            if ticket['generation'] != self.generation or ticket['phase'] != 'waiting':
                return {}
            ticket.update(phase='failed', error=str(payload.get('error', 'Houdini 未完成连接。'))[:4000])
            self._write(ticket)
            return {}


def show_project_dialog(manager, parent, action, hip=None, session_id=None, executor_id=None, bind_session_id=None):
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFileDialog
    from dsh_ui_style import style_dialog
    dialog = QDialog(parent)
    dialog.setAttribute(Qt.WA_DeleteOnClose)
    dialog.setWindowTitle('新建 Houdini 工程' if action == 'new' else '打开 Houdini 工程')
    dialog.resize(440, 190)
    style_dialog(dialog)
    layout = QVBoxLayout(dialog)
    description = QLabel('在独立 Houdini 窗口中打开，不会替换当前其他工程。')
    description.setWordWrap(True)
    layout.addWidget(description)
    versions = QComboBox()
    versions.setObjectName('houdini-version')
    layout.addWidget(versions)
    file_label = QLabel(hip or ('新建未保存的工程，之后可随时另存。' if action == 'new' else '尚未选择工程文件'))
    file_label.setTextFormat(Qt.PlainText)
    file_label.setWordWrap(True)
    layout.addWidget(file_label)
    browse = QPushButton('选择工程…')
    browse.setObjectName('choose-hip')
    browse.setVisible(action == 'open')
    layout.addWidget(browse)
    status = QLabel('正在读取可用版本…')
    status.setTextFormat(Qt.PlainText)
    status.setWordWrap(True)
    layout.addWidget(status)
    buttons = QHBoxLayout()
    cancel, start = QPushButton('取消'), QPushButton('新建并连接' if action == 'new' else '打开并连接')
    start.setObjectName('primary')
    start.setEnabled(False)
    buttons.addStretch()
    buttons.addWidget(cancel)
    buttons.addWidget(start)
    layout.addLayout(buttons)
    state = {'file': hip, 'id': None, 'working': False, 'alive': True}
    results = []
    def worker(function, kind):
        def work():
            try:
                results.append((kind, function(), None))
            except Exception as error:
                results.append((kind, None, str(error)))
        threading.Thread(target=work, daemon=True).start()
    def choose():
        filename, unused = QFileDialog.getOpenFileName(dialog, '选择 Houdini 工程', state['file'] or '', 'Houdini 工程 (*.hip *.hiplc *.hipnc)')
        if filename:
            state['file'] = filename
            file_label.setText(filename)
    def launch():
        if state['working']:
            return
        if action != 'new' and not state['file']:
            choose()
            if not state['file']:
                return
        state['working'] = True
        start.setEnabled(False)
        browse.setEnabled(False)
        versions.setEnabled(False)
        status.setText('正在启动 Houdini，完成后会自动连接…')
        cancel.setText('后台打开')
        selected = versions.currentData()
        def launch_selected():
            value = manager.launch(action, selected, state['file'], session_id, bind_session_id, should_navigate=lambda: state['alive'])
            state['id'] = value.get('id')
            if not state['alive'] and state['id']:
                manager.detach(state['id'])
            return value
        worker(launch_selected, 'launch')
    def closed():
        state['alive'] = False
        if state['id']:
            worker(lambda: manager.detach(state['id']), 'detached')
    def tick():
        while results:
            kind, value, error = results.pop(0)
            if not state['alive']:
                if kind == 'launch' and value and value.get('id'):
                    worker(lambda identifier=value['id']: manager.detach(identifier), 'detached')
                continue
            if error:
                status.setText(error)
                state['working'] = False
                cancel.setText('关闭')
                versions.setEnabled(True)
                browse.setEnabled(True)
                start.setEnabled(bool(versions.count()) and not state['id'])
                continue
            if kind == 'catalog':
                for item in value['items']:
                    versions.addItem('Houdini ' + item['version'], item['hfs'])
                status.setText('选择版本后即可开始。' if value['items'] else '没有找到受支持的 Houdini，请先安装 Houdini 21 或 22。')
                start.setEnabled(bool(value['items']))
                if value['preferred']:
                    match = versions.findText('Houdini ' + value['preferred'])
                    if match >= 0:
                        versions.setCurrentIndex(match)
                    else:
                        status.setText('原工程使用 Houdini ' + value['preferred'] + '。该版本未找到，请确认所选版本能打开此工程。')
            elif kind in ('launch', 'status'):
                if value['phase'] == 'ready':
                    state['id'] = None
                    dialog.accept()
                elif value['phase'] == 'failed':
                    state['id'] = None
                    status.setText(value['error'])
                    cancel.setText('关闭')
                else:
                    state['id'] = value['id']
                    if value.get('elapsed', 0) > 45:
                        status.setText('Houdini 仍在启动或等待许可，请查看它的窗口。可以选择后台打开，不会重复启动或强制结束它。')
        if state['alive'] and state['id'] and not state.get('polling'):
            state['polling'] = True
            def poll():
                try:
                    return manager.status(state['id'])
                finally:
                    state['polling'] = False
            worker(poll, 'status')
    browse.clicked.connect(choose)
    start.clicked.connect(launch)
    cancel.clicked.connect(dialog.reject)
    dialog.finished.connect(closed)
    timer = QTimer(dialog)
    timer.timeout.connect(tick)
    timer.start(500)
    worker(lambda: {'items': manager.installations(), 'preferred': next((item.get('houdini_version')
        for item in manager.candidates() if item['executor_id'] == executor_id), None) if executor_id else None}, 'catalog')
    dialog.open()
    return dialog
