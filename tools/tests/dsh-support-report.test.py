from pathlib import Path
import base64
import importlib.util
import io
import json
import os
import sys
import tempfile
import subprocess
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_support_report as reports

spec = importlib.util.spec_from_file_location('inspect_support', ROOT / 'tools/inspect-support-report.py')
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)
assert inspector.inspect_report is reports.inspect_report, 'CLI and installed helper must use one inspector'


def refused(function):
    try:
        function()
    except (ValueError, OSError, zipfile.BadZipFile):
        return
    raise AssertionError('unsafe input accepted')


with tempfile.TemporaryDirectory(prefix='dsh-support-') as temporary:
    root = Path(temporary)
    (root / 'package.json').write_text('{"version":"0.0.9"}')
    (root / '.dsh-runtime.json').write_text(json.dumps({'version':'0.2.1-rc.2','pid':123,'token':'MARKER_SECRET',
                                                      'bin':'C:/Users/Private/cli.js','runtimeFixes':{'secret':'FIX_SECRET'}}))
    secrets = ['TOKEN_SECRET', 'HEADER_SECRET', 'JSON_SECRET', 'ESCAPED_SECRET', 'PASSWORD_SECRET', 'PEM_BODY_SECRET',
               'sk-KEY_SECRET_SENTINEL', 'ghp_GITHUB_SECRET_SENTINEL', 'URL_PASSWORD_SECRET', 'MARKER_SECRET', 'FIX_SECRET', 'NESTED_SECRET', 'FIELD_NAME_SECRET']
    log = '\n'.join(['http://127.0.0.1:3081/?token=TOKEN_SECRET', 'Authorization: Bearer HEADER_SECRET',
                     '{"api_key":"JSON_SECRET"}', '{"\\u0074oken":"ESCAPED_SECRET"}',
                     json.dumps({'message':'{"\\u0074oken":"NESTED_SECRET"}'}),
                     json.dumps({'api_key=FIELD_NAME_SECRET':'value'}),
                     "password='PASSWORD_SECRET'", '-----BEGIN PRIVATE KEY-----\nPEM_BODY_SECRET\n-----END PRIVATE KEY-----',
                     'sk-KEY_SECRET_SENTINEL', 'ghp_GITHUB_SECRET_SENTINEL', 'https://user:URL_PASSWORD_SECRET@example.test/path',
                     'C:\\Users\\Private\\client-project\\scene.hip', 'public@example.test', 'normal diagnostic preserved'])
    (root / '.dsh-web.log').write_text(log, encoding='utf-8')
    payload = {'options':{'includeLogs':True,'includeContent':False,'description':'原工程接续失败'},
               'session':{'id':'selected'},'timeline':[{'seq':1,'error':'checkpoint unavailable'}],
               'content':[{'text':'CHAT_CONTENT_SENTINEL'}]}
    result = reports.build_report(payload, {'packageRoot':str(root),'managed':None})
    archive_path = root / result['filename']
    archive_path.write_bytes(base64.b64decode(result['archiveBase64']))
    manifest, files = inspector.inspect_report(archive_path)
    preview = {item['name']:item['text'] for item in result['files']}
    assert files == preview, 'reviewed bytes must be the exact archive bytes'
    all_text = json.dumps(files, ensure_ascii=False)
    for secret in secrets + ['CHAT_CONTENT_SENTINEL', 'client-project', 'public@example.test']:
        assert secret not in all_text, secret
    assert 'normal diagnostic preserved' in all_text
    assert 'checkpoint unavailable' in all_text
    assert manifest['redactions'] >= 10
    assert not manifest['attachments_included']
    payload['options']['includeContent'] = True
    complete = reports.build_report(payload, {'packageRoot':str(root),'managed':None})
    assert any('CHAT_CONTENT_SENTINEL' in item['text'] for item in complete['files'])
    payload['options']['includeLogs'] = False
    assert not any(item['name'].startswith('logs/') for item in reports.build_report(payload, {'packageRoot':str(root),'managed':None})['files'])
    payload['options']['includeLogs'] = True
    (root / '.dsh-runtime.json').write_text('damaged')
    (root / '.dsh-web.log').write_bytes(b'X'*(reports.MAX_LOG+100)+b'\nLATEST_ERROR\n')
    truncated = reports.build_report(payload, {'packageRoot':str(root),'managed':None})
    truncated_text = json.dumps(truncated['files'])
    assert 'source_log_tail_only' in truncated_text and 'LATEST_ERROR' in truncated_text
    assert 'source_runtime_marker_unavailable' in truncated_text
    (root/'.dsh-web.log').write_text('OLD_HEADER\n'+'X'*(reports.MAX_LOG+100)+'\nPARTIAL_PEM_SECRET\n-----END PRIVATE KEY-----\nAFTER_KEY_ERROR')
    partial_key = json.dumps(reports.build_report(payload, {'packageRoot':str(root),'managed':None})['files'])
    assert 'PARTIAL_PEM_SECRET' not in partial_key and 'AFTER_KEY_ERROR' in partial_key
    empty = reports.build_report({'options':{}}, {'packageRoot':str(root/'missing'),'managed':{'root':str(root/'absent')}})
    assert 'previous_runtime_unavailable' in json.dumps(empty['files'])
    for member in ['../escape','/absolute','C:/secret','logs/../../secret']:
        malicious = root / 'malicious.zip'
        with zipfile.ZipFile(malicious,'w') as archive:
            archive.writestr(member,'attack')
        refused(lambda:inspector.inspect_report(malicious))
    with zipfile.ZipFile(root/'tampered.zip','w') as archive:
        for name, value in files.items():
            archive.writestr(name,'tampered' if name=='timeline.jsonl' else value)
    refused(lambda:inspector.inspect_report(root/'tampered.zip'))
    with zipfile.ZipFile(root/'bomb.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('timeline.jsonl',b'X'*(9*1024*1024))
    refused(lambda:inspector.inspect_report(root/'bomb.zip'))
    # The offline report must not inherit an old context, scan its logs or ask
    # a running Host for session data. Only this helper's package metadata is read.
    read_object = reports.object_file
    observed = []
    def metadata_only(filename):
        observed.append(Path(filename))
        assert Path(filename) == root / 'package.json', filename
        return read_object(filename)
    with patch.dict(os.environ, {'DSH_HOUDINI_MANAGED_CONTEXT': str(root / 'DO_NOT_READ_SECRET.json'),
                                'DSH_HOUDINI_WORKBENCH_ROOT': str(root / 'DO_NOT_SCAN')}), \
         patch.object(reports, 'runtime_context', side_effect=AssertionError('offline cannot discover runtime context')), \
         patch.object(reports, 'object_file', metadata_only):
        offline = reports.build_connection_report({'houdini_version':'21.0.fixture', 'bridge':{'listening':False}},
            'actual startup error; token=OFFLINE_SECRET\n<script>alert("test")</script>', root)
    assert observed == [root / 'package.json']
    offline_bytes = base64.b64decode(offline['archiveBase64'])
    offline_manifest, offline_files = reports.inspect_report(io.BytesIO(offline_bytes))
    assert offline_files == {entry['name']:entry['text'] for entry in offline['files']}
    assert offline_manifest['session'] is None and not offline_manifest['content_included']
    assert not offline_manifest['attachments_included']
    assert set(offline_files) == {'manifest.json','environment.json','timeline.jsonl','issue.md'}
    assert {'native_host_logs_not_collected','session_history_not_collected','scene_contents_not_collected'} <= set(offline_manifest['missing'])
    environment = json.loads(offline_files['environment.json'])
    assert environment['environment']['collector_scope'] == 'offline_connection'
    assert 'OFFLINE_SECRET' not in json.dumps(offline_files)
    assert 'actual startup error' in offline_files['timeline.jsonl']
    html_document = reports.report_html(offline_files)
    assert '<script>' not in html_document and '&lt;script&gt;' in html_document
    assert "default-src 'none'" in html_document
    saved_zip, saved_html = root / 'offline.zip', root / 'offline.HTM'
    reports.save_reviewed_file(saved_zip, offline_bytes)
    reports.save_reviewed_file(saved_html, html_document.encode('utf-8'), html_document=True)
    assert saved_zip.read_bytes() == offline_bytes and saved_html.read_text(encoding='utf-8') == html_document
    protected = root / 'preserved.hip'
    protected.write_bytes(b'HIP_SENTINEL')
    refused(lambda:reports.save_reviewed_file(protected, b'wrong type'))
    refused(lambda:reports.save_reviewed_file(protected, b'wrong type', html_document=True))
    assert protected.read_bytes() == b'HIP_SENTINEL'
    assert not list(root.glob('.offline.*')), 'save may not leave partial files'
    try:
        (root/'linked').symlink_to(root/'.dsh-web.log')
    except OSError:
        print('symlink creation unavailable in this test environment')
    else:
        refused(lambda:reports.read_bounded(root/'linked',100))
    if os.name == 'nt':
        target = root/'junction-target'
        target.mkdir()
        (target/'data.log').write_text('JUNCTION_SECRET')
        junction = root/'junction'
        result = subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(junction),str(target)],capture_output=True)
        assert result.returncode == 0, result.stderr
        refused(lambda:reports.read_bounded(junction/'data.log',100))

with tempfile.TemporaryDirectory(prefix='workbench-support-') as temporary:
    folder = Path(temporary)
    runtime = folder / 'workbench' / ('a' * 32)
    runtime.mkdir(parents=True)
    (runtime / 'frontend.log').write_text('WORKBENCH_HOST_LOG', encoding='utf-8')
    (folder / 'workbench/desktop.log').write_text('WORKBENCH_WINDOW_LOG', encoding='utf-8')
    (folder / 'workbench/desktop.json').write_text('{"token":"NEVER_EXPORT_DESKTOP_CREDENTIAL"}', encoding='utf-8')
    report = reports.build_report({'options': {'includeLogs': True}}, reports.runtime_context(ROOT, {
        'root': str(folder), 'runtimeDir': str(runtime), 'workbench': True}))
    files = {entry['name']: entry['text'] for entry in report['files']}
    assert files['logs/current.log'] == 'WORKBENCH_HOST_LOG'
    assert files['logs/desktop.log'] == 'WORKBENCH_WINDOW_LOG'
    assert 'NEVER_EXPORT_DESKTOP_CREDENTIAL' not in json.dumps(files)
    archive_path = folder / 'report.zip'
    archive_path.write_bytes(base64.b64decode(report['archiveBase64']))
    inspector.inspect_report(archive_path)

print('support report: exact preview/archive, secrets, escaped JSON, private keys, opt-in, damaged/missing files, truncation, tamper and hostile ZIP passed')
