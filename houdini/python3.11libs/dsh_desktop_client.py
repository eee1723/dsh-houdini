"""Worker-only client for the Houdini plugin inside official DSH Desktop.

The descriptor is plugin state, not a DSH login credential. This module only
reads it and invokes the fixed local actions; it never starts a DSH Host or
changes a profile, Session, model setting, or dependency link.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
from dsh_deployment import read_json


_ACTIONS = {'status', 'ticket-current', 'open-workspace', 'launch-progress', 'launch-attached', 'launch-failed'}
_ID = re.compile(r'^[0-9a-f]{32}$')


class DesktopRefusal(RuntimeError):
    """A current Host explicitly refused a fixed business action."""
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class DesktopUnavailable(RuntimeError):
    """Transport did not confirm an outcome within the operation budget."""


def descriptor_path():
    explicit = os.environ.get('DSH_HOUDINI_DESKTOP_DESCRIPTOR')
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            raise ValueError('DSH Desktop 连接文件必须使用完整路径。')
        return path
    home = os.environ.get('DSH_HOME', '').strip()
    if home and not Path(home).expanduser().is_absolute():
        raise ValueError('DSH_HOME 必须是完整路径，或从 Desktop 内主动打开 Houdini。')
    return (Path(home).expanduser() if home else Path.home() / '.dsh') / 'dsh-houdini/desktop.json'


def read_descriptor(filename=None):
    path = Path(filename) if filename is not None else descriptor_path()
    value = read_json(path, limit=32768)
    if (not isinstance(value, dict) or value.get('schemaVersion') != 1
            or type(value.get('pid')) is not int or value['pid'] <= 0
            or type(value.get('port')) is not int or not 1024 <= value['port'] <= 65535
            or not isinstance(value.get('generation'), str) or not value['generation']
            or not isinstance(value.get('token'), str) or not re.fullmatch(r'[0-9a-f]{64}', value['token'])
            or any(not isinstance(value.get(key), str) or not Path(value[key]).is_absolute()
                   for key in ('pluginRoot', 'executorRegistry', 'launchesRoot'))):
        raise ValueError('DSH Desktop 的 Houdini 插件连接信息无效。请在 Desktop 中重新启用插件。')
    return value


def request(record, action, payload, *, timeout=15):
    if action not in _ACTIONS:
        raise ValueError('未知的 Houdini Desktop 操作。')
    message = urllib.request.Request(
        'http://127.0.0.1:' + str(record['port']) + '/' + action,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'), method='POST',
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + record['token']})
    # This is a local authenticated plugin channel. System proxies must not
    # receive its token or decide whether another local application is trusted.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        response = opener.open(message, timeout=timeout)
    except urllib.error.HTTPError as response_error:
        # Business refusals use non-2xx HTTP while retaining the same bounded
        # JSON envelope. Preserve their useful reason instead of "Bad Request".
        with response_error:
            raw = response_error.read(1048577)
            status = response_error.code
    else:
        with response:
            raw = response.read(1048577)
            status = response.status
    if len(raw) > 1048576:
        raise RuntimeError('DSH Desktop 返回内容过大。')
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise DesktopRefusal('DSH Desktop 返回格式无效，未确认操作结果。', status) from error
    if not isinstance(value, dict) or value.get('ok') is not True:
        raise DesktopRefusal(value.get('error', 'DSH Desktop 没有完成此操作。') if isinstance(value, dict)
                             else 'DSH Desktop 返回内容无效。', status)
    return value.get('value')


def activate_desktop():
    if os.name != 'nt' or not hasattr(os, 'startfile'):
        raise RuntimeError('请先打开官方 DSH Desktop，并在其中安装和启用 Houdini 插件。')
    try:
        os.startfile('dsh://open')
    except OSError as error:
        raise RuntimeError('未找到官方 DSH Desktop。请先安装 Desktop 和 Houdini 插件，再从此菜单接入。') from error


class DesktopConnection:
    """One bounded delivery channel; retries retain the original action payload.

    A launch operation may outlive a Host generation. Its immutable admission
    facts are checked again whenever this channel authenticates a successor.
    No retry captures HOM, creates a Bridge, or republishes a registration.
    """
    def __init__(self, *, timeout=30, activate=False, filename=None):
        self.deadline = time.monotonic() + timeout
        self.activate = activate
        self.filename = filename
        self.record = None
        self.admission = None
        self.admitted_generation = None
        self.activated = False

    def _remaining(self, maximum=15):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise DesktopUnavailable('DSH Desktop 接入结果尚未确认。请确认插件已启用，或从此 Houdini 的 Open Workspace 重新接入；没有重发场景操作。')
        return min(maximum, remaining)

    def _wait(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            self._remaining()
        time.sleep(min(.2, remaining))

    def current(self):
        while self.record is None:
            try:
                record = read_descriptor(self.filename)
                status = request(record, 'status', {}, timeout=self._remaining(2))
                if not isinstance(status, dict) or status.get('generation') != record['generation']:
                    raise OSError('Desktop generation changed during authentication')
                self.record = record
            except DesktopUnavailable:
                raise
            except DesktopRefusal as error:
                if error.status not in (401, 503):
                    raise
                self._wait()
            except (OSError, ValueError):
                if self.activate and not self.activated:
                    activate_desktop()
                    self.activated = True
                self._wait()
        return self.record

    def current_admitted(self):
        record = self.current()
        if self.admission is not None and self.admitted_generation != record['generation']:
            self.call('ticket-current', self.admission)
        return self.record

    def call(self, action, payload):
        # Snapshot once: an HTTP timeout may mean the Host already committed it.
        retained = json.loads(json.dumps(payload, ensure_ascii=False))
        while True:
            record = self.current()
            try:
                if self.admission is not None and action != 'ticket-current' and self.admitted_generation != record['generation']:
                    request(record, 'ticket-current', self.admission, timeout=self._remaining())
                    self.admitted_generation = record['generation']
                value = request(record, action, retained, timeout=self._remaining())
                if action == 'ticket-current':
                    self.admission = retained
                    self.admitted_generation = record['generation']
                return value
            except DesktopRefusal as error:
                if error.status not in (401, 503):
                    raise
                self.record = None
            except OSError:
                self.record = None
            self._wait()

    def progress(self, identifier, stage):
        """Advisory stage feedback never becomes an extra connection gate."""
        if self.record is None:
            return
        try:
            request(self.record, 'launch-progress', {'id': identifier, 'stage': stage}, timeout=self._remaining(2))
        except (OSError, DesktopRefusal, DesktopUnavailable):
            self.record = None


def connect(*, timeout=30, activate=True, filename=None):
    return DesktopConnection(timeout=timeout, activate=activate, filename=filename).current()


def read_launch_ticket(filename, record):
    path = Path(filename).resolve()
    if path.parent != Path(record['launchesRoot']).resolve() or not _ID.fullmatch(path.stem) or path.suffix != '.json':
        raise ValueError('启动请求不属于当前 DSH Desktop 插件。')
    value = read_json(path, limit=32768)
    if (not isinstance(value, dict) or value.get('id') != path.stem
            or not isinstance(value.get('generation'), str) or not _ID.fullmatch(value['generation'])
            or not isinstance(value.get('hfs'), str) or not Path(value['hfs']).is_absolute()
            or not isinstance(value.get('workspace'), str) or not Path(value['workspace']).is_absolute()
            or value.get('hip') is not None and (not isinstance(value['hip'], str) or not Path(value['hip']).is_absolute())):
        raise ValueError('Houdini 启动请求与当前 Desktop 不一致。')
    return value
