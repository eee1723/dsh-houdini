from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone

SCHEMA = 'dsh-houdini/support-v1'
ISSUES_URL = 'https://github.com/eee1723/dsh-houdini/issues/new?template=bug_report.yml'
MAX_INPUT = 6 * 1024 * 1024
MAX_LOG = 256 * 1024
MAX_TEXT = 64 * 1024
SECRET_KEY = re.compile(r'(?:api.?key|authorization|cookie|password|passwd|secret|credential|access.?token|refresh.?token|launch.?token|^token$)', re.I)

FILE_LABELS = {
    'environment.json': ('软件与版本', '插件和运行环境的版本，帮助判断是否与软件版本有关。'),
    'timeline.jsonl': ('出错前后发生了什么', '记录操作顺序和错误，帮助找到出问题的步骤。'),
    'session-content.jsonl': ('对话与操作细节', '所选范围内的聊天和 AI 操作内容，可能涉及你的项目。'),
    'issue.md': ('问题说明', '你填写的问题描述，发送给开发者时可以直接使用。'),
    'manifest.json': ('报告信息', '记录收集范围、缺少的资料和文件检查信息。'),
    'logs/current.log': ('当前运行记录', '插件最近的启动、连接和报错信息。'),
    'logs/source.log': ('当前运行记录', '插件最近的启动、连接和报错信息。'),
    'logs/previous.log': ('之前的运行记录', '可找到的另一次运行记录，便于排查重启前的问题。'),
    'logs/desktop.log': ('工作台窗口记录', '独立窗口的启动和显示问题，不包含工程文件。'),
}


class Redactor:
    def __init__(self):
        self.count = 0
        self.paths = {}

    def replace(self, _match):
        self.count += 1
        return '[REDACTED]'

    def path(self, match):
        value = match.group(0)
        self.count += 1
        if value not in self.paths:
            self.paths[value] = '<path-' + str(len(self.paths) + 1) + '>'
        return self.paths[value]

    def text(self, value):
        value = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', value)
        value = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|\Z)', self.replace, value, flags=re.S)
        value = re.sub(r'(?im)^(?:.*?)(?:authorization|set-cookie|cookie)\s*[=:].*$', self.replace, value)
        value = re.sub(r'(?i)\b(?:bearer|basic)\s+[^\s,;\"\']+', self.replace, value)
        value = re.sub(r'(?i)(?:https?|wss?)://[^\s<>\"\']+', self.replace, value)
        value = re.sub(r'(?i)[\"\']?(?:api[-_ ]?key|password|passwd|secret|access[-_ ]?token|refresh[-_ ]?token|launch[-_ ]?token|token)[\"\']?\s*(?:[:=]|\s)\s*(?:\"[^\"]*\"|\'[^\']*\'|[^\s,;}]+)', self.replace, value)
        value = re.sub(r'\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]+|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)', self.replace, value)
        value = re.sub(r'(?i)(?:[a-z]:[\\/]|\\\\)[^\r\n\t\"\'<>|]*|/(?:home|Users|tmp|var|mnt|opt)/[^\s\"\'<>]*', self.path, value)
        value = re.sub(r'\b[^\s@]+@[^\s@]+\.[A-Za-z]{2,}\b', self.replace, value)
        return value

    def clean(self, value, depth=0):
        if depth > 32:
            return '[DEPTH LIMIT]'
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if SECRET_KEY.search(key):
                    self.count += 1
                    result[self.text(key)] = '[REDACTED]'
                else:
                    result[self.text(key)] = self.clean(item, depth + 1)
            return result
        if isinstance(value, list):
            return [self.clean(item, depth + 1) for item in value]
        if isinstance(value, str):
            if value.lstrip().startswith(('{', '[')):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, (dict, list)):
                        return json.dumps(self.clean(parsed, depth + 1), ensure_ascii=False)
                except (ValueError, RecursionError):
                    pass
            cleaned = self.text(value)
            return cleaned if len(cleaned) <= MAX_TEXT else cleaned[:MAX_TEXT] + '\n[TRUNCATED]'
        return value


def read_bounded(filename, limit, *, tail=False):
    filename = Path(filename)
    for parent in [filename, *filename.parents]:
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('linked_path_excluded')
    with filename.open('rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('non_regular_file_excluded')
        if not tail and info.st_size > limit:
            raise ValueError('file_size_limit')
        if tail and info.st_size > limit:
            stream.seek(info.st_size - limit)
        data = stream.read(limit)
    if tail and info.st_size > limit:
        data = data.partition(b'\n')[2]
    return data.decode('utf-8', errors='replace'), info.st_size > limit


def object_file(filename):
    value = json.loads(read_bounded(filename, MAX_LOG)[0])
    if not isinstance(value, dict):
        raise ValueError('invalid_object')
    return value


def runtime_context(package_root=None, managed=None):
    root = Path(package_root or Path(__file__).resolve().parents[2])
    missing = []
    if managed is None and os.environ.get('DSH_HOUDINI_MANAGED_CONTEXT'):
        try:
            managed = object_file(os.environ['DSH_HOUDINI_MANAGED_CONTEXT'])
        except (OSError, ValueError):
            managed = {}
            missing.append('managed_context_unreadable_no_source_fallback')
    if managed is None and os.environ.get('DSH_HOUDINI_WORKBENCH_CONTEXT'):
        try:
            managed = object_file(os.environ['DSH_HOUDINI_WORKBENCH_CONTEXT'])
        except (OSError, ValueError):
            managed = {}
            missing.append('workbench_context_unreadable_no_source_fallback')
    if managed is None and os.environ.get('DSH_HOUDINI_WORKBENCH_ROOT'):
        managed = {'root': os.environ['DSH_HOUDINI_WORKBENCH_ROOT'], 'workbench': True}
        missing.append('workbench_active_runtime_unknown')
    return {'packageRoot': str(root), 'managed': managed, 'missing': missing}


def build_report(payload, context=None):
    context = context or runtime_context()
    options = payload.get('options', {})
    redactor = Redactor()
    report_id = uuid.uuid4().hex
    files = {}
    missing = list(payload.get('missing', [])) + context.get('missing', [])
    observations = []
    package_root = Path(context['packageRoot'])
    managed = context.get('managed')
    offline = context.get('collectRecordedRuntime', True) is False
    environment = {'os': sys.platform if offline else platform.system(),
                   'os_release': 'not_collected' if offline else platform.release(),
                   'python': '.'.join(map(str, sys.version_info[:3])) if offline else platform.python_version(),
                   'collector_scope': 'host_launch_and_persisted_history', 'live_houdini_probe': 'not_performed',
                   **payload.get('environment', {})}
    try:
        environment['package_on_disk'] = object_file(package_root / 'package.json').get('version')
    except (OSError, ValueError):
        missing.append('package_metadata_unavailable')
    directories = []
    if context.get('collectRecordedRuntime', True) is False:
        # The offline connection report has only an explicit in-memory snapshot.
        # Never discover legacy runtime directories or official Desktop logs.
        pass
    elif managed is not None:
        environment['installation'] = {key: managed.get(key) for key in ('installId', 'version')}
        if managed.get('runtimeDir'):
            directories.append(('current', Path(managed['runtimeDir'])))
        if managed.get('workbench'):
            directories.append(('desktop', Path(managed['root']) / 'workbench'))
        if options.get('includePrevious', True):
            try:
                runtime_root = Path(managed['root']) / ('workbench' if managed.get('workbench') else 'runtime')
                pattern = r'[0-9a-f]{32}' if managed.get('workbench') else r'\d+-[0-9a-f]{8}'
                candidates = [entry for entry in runtime_root.iterdir() if re.fullmatch(pattern, entry.name)
                              and entry.is_dir() and not entry.is_symlink() and entry != Path(managed.get('runtimeDir', ''))]
                candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
                if candidates:
                    directories.append(('previous', candidates[0]))
            except (OSError, KeyError):
                missing.append('previous_runtime_unavailable')
    else:
        directories.append(('source', package_root))
    for label, directory in directories:
        marker = directory / ('.dsh-runtime.json' if label == 'source' else 'runtime.json')
        try:
            value = object_file(marker)
            observations.append({'scope': label, 'verification': 'recorded_not_live',
                                 **{key: value.get(key) for key in ('version', 'source', 'pid', 'startedAt', 'runtimeFixes')}})
        except (OSError, ValueError):
            missing.append(label + '_runtime_marker_unavailable')
        if options.get('includeLogs', True):
            filename = directory / ('.dsh-web.log' if label == 'source' else 'desktop.log' if label == 'desktop' else 'frontend.log')
            try:
                content, truncated = read_bounded(filename, MAX_LOG, tail=True)
                content = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|\Z)', redactor.replace, content, flags=re.S)
                content = re.sub(r'\A.*?-----END [^-]*PRIVATE KEY-----', redactor.replace, content, flags=re.S)
                lines = []
                for line in content.splitlines():
                    try:
                        parsed = json.loads(line)
                        lines.append(json.dumps(redactor.clean(parsed), ensure_ascii=False))
                    except (ValueError, RecursionError):
                        lines.append(redactor.text(line))
                files['logs/' + label + '.log'] = '\n'.join(lines)
                if truncated:
                    missing.append(label + '_log_tail_only')
            except (OSError, ValueError):
                missing.append(label + '_log_unavailable')
    session = redactor.clean(payload.get('session'))
    files['environment.json'] = json.dumps(redactor.clean({'environment': environment, 'runtime_observations': observations}), ensure_ascii=False, indent=2)
    files['timeline.jsonl'] = '\n'.join(json.dumps(redactor.clean(event), ensure_ascii=False) for event in payload.get('timeline', []))
    if options.get('includeContent') and payload.get('content') is not None:
        files['session-content.jsonl'] = '\n'.join(json.dumps(redactor.clean(event), ensure_ascii=False) for event in payload['content'])
    description = redactor.text(str(options.get('description', ''))[:4000])
    summary = '# DSH-Houdini 问题报告\n\n报告编号：' + report_id + '\n\n' + description + '\n\n'
    summary += '请补充预期结果、实际结果和复现步骤。\n\n'
    summary += '已收集：版本记录、故障时间线' + ('、运行日志' if options.get('includeLogs', True) else '') + '。\n'
    summary += '会话正文：' + ('已选择包含，请人工检查' if options.get('includeContent') else '未包含') + '。图片、附件、HIP/HDA、凭据文件均未收集。\n'
    if environment.get('collector_scope') == 'offline_connection':
        summary += '这是当前 Houdini 窗口的接入诊断，不是完整会话诊断。只记录加载版本和连接元数据，未查询场景、重启或恢复。缺失资料见 manifest.json。\n'
    else:
        summary += '这是历史证据；没有执行 Houdini 查询、重启或恢复。缺失资料见 manifest.json。\n'
    summary += '分享前请检查全部文件。自动脱敏不能保证识别任意文本中的商业内容或秘密。\n'
    files['issue.md'] = summary
    manifest = {'schema': SCHEMA, 'report_id': report_id, 'created_at': datetime.now(timezone.utc).isoformat(),
                'session': session, 'missing': redactor.clean(missing), 'redactions': redactor.count,
                'content_included': options.get('includeContent') is True, 'attachments_included': False,
                'files': [{'name': name, 'bytes': len(value.encode('utf-8')), 'sha256': hashlib.sha256(value.encode('utf-8')).hexdigest()}
                          for name, value in files.items()]}
    files['manifest.json'] = json.dumps(manifest, ensure_ascii=False, indent=2)
    if sum(len(value.encode('utf-8')) for value in files.values()) > MAX_INPUT:
        raise ValueError('report_size_limit')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value.encode('utf-8'))
    return {'reportId': report_id, 'filename': 'dsh-houdini-report-' + report_id + '.zip', 'issuesUrl': ISSUES_URL,
            'files': [{'name': name, 'text': value, 'label': FILE_LABELS.get(name, ('补充记录', '供开发者排查问题。'))[0],
                       'description': FILE_LABELS.get(name, ('补充记录', '供开发者排查问题。'))[1]} for name, value in files.items()],
            'archiveBase64': base64.b64encode(buffer.getvalue()).decode('ascii'), 'summary': summary}


def build_connection_report(snapshot, startup_error='', package_root=None):
    """No Host, history, environment or log discovery; use the same support-v1 bytes."""
    return build_report({
        'options': {'includeLogs': False, 'includePrevious': False, 'includeContent': False},
        'session': None,
        'environment': {'collector_scope': 'offline_connection',
                        'live_houdini_probe': 'main_thread_connection_metadata_only',
                        'connection_snapshot': snapshot},
        'timeline': ([{'type': 'startup_error', 'error': str(startup_error)}] if startup_error else []),
        'missing': ['native_host_logs_not_collected', 'session_history_not_collected',
                    'scene_contents_not_collected'],
    }, {'packageRoot': str(package_root or Path(__file__).resolve().parents[2]),
        'managed': None, 'collectRecordedRuntime': False})


def inspect_report(filename):
    """Inspect untrusted support-v1 ZIPs without extraction or executing contents."""
    with zipfile.ZipFile(filename) as archive:
        entries = archive.infolist()
        if len(entries) > 20 or sum(entry.file_size for entry in entries) > 8 * 1024 * 1024:
            raise ValueError('diagnostic archive exceeds limits')
        names = [entry.filename for entry in entries]
        allowed = {'manifest.json', 'environment.json', 'timeline.jsonl', 'session-content.jsonl', 'issue.md',
                   'logs/current.log', 'logs/previous.log', 'logs/source.log', 'logs/desktop.log'}
        if len(set(names)) != len(names) or not set(names) <= allowed:
            raise ValueError('unexpected or duplicate archive entries')
        if not {'manifest.json', 'environment.json', 'timeline.jsonl', 'issue.md'} <= set(names):
            raise ValueError('required diagnostic files missing')
        files = {name: archive.read(name) for name in names}
    manifest = json.loads(files['manifest.json'])
    if manifest.get('schema') != SCHEMA:
        raise ValueError('unsupported support schema')
    declarations = manifest['files']
    if len({entry['name'] for entry in declarations}) != len(declarations) or {entry['name'] for entry in declarations} != set(files) - {'manifest.json'}:
        raise ValueError('manifest file set differs from archive')
    for entry in declarations:
        content = files[entry['name']]
        if len(content) != entry['bytes'] or hashlib.sha256(content).hexdigest() != entry['sha256']:
            raise ValueError('diagnostic file integrity mismatch')
    return manifest, {name: value.decode('utf-8') for name, value in files.items()}


def report_html(files):
    """Only escaped text in a local HTML document; no script or remote resources."""
    body = ''.join('<details open><summary>' + html.escape(name) + '</summary><pre>' + html.escape(text)
                   + '</pre></details>' for name, text in files.items())
    return ('<!doctype html><html lang="zh"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" '
            'content="default-src \'none\'; style-src \'unsafe-inline\'"><title>DSH-Houdini diagnostic report</title>'
            '<style>body{font:15px/1.6 system-ui;margin:32px;max-width:1100px}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eee;padding:16px}'
            'details{margin:16px 0}</style><h1>DSH-Houdini 故障报告</h1>' + body + '</html>')


def save_reviewed_file(filename, content, *, html_document=False):
    """Worker-only save of explicitly selected bytes, published as one complete file."""
    target = Path(filename)
    suffixes = {'.html', '.htm'} if html_document else {'.zip'}
    if not target.is_absolute() or target.suffix.lower() not in suffixes:
        raise ValueError('请选择以 ' + (' .html 或 .htm' if html_document else ' .zip') + ' 结尾的完整保存路径。')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.' + target.name + '.', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return str(target)


if __name__ == '__main__':
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ValueError('input_size_limit')
        result = build_report(json.loads(raw))
        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
    except Exception as error:
        sys.stderr.write('support_report_failed:' + type(error).__name__)
        sys.exit(1)
