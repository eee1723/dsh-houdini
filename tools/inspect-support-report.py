from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path
import zipfile


def inspect_report(filename):
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
    if manifest.get('schema') != 'dsh-houdini/support-v1':
        raise ValueError('unsupported support schema')
    declarations = manifest['files']
    if len({entry['name'] for entry in declarations}) != len(declarations) or {entry['name'] for entry in declarations} != set(files) - {'manifest.json'}:
        raise ValueError('manifest file set differs from archive')
    for entry in declarations:
        content = files[entry['name']]
        if len(content) != entry['bytes'] or hashlib.sha256(content).hexdigest() != entry['sha256']:
            raise ValueError('diagnostic file integrity mismatch')
    return manifest, {name: value.decode('utf-8') for name, value in files.items()}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Inspect an untrusted diagnostic ZIP without extraction or executing its contents.')
    parser.add_argument('archive', type=Path)
    parser.add_argument('--html', type=Path)
    args = parser.parse_args()
    manifest, files = inspect_report(args.archive)
    print(files['issue.md'])
    print(json.dumps({'session': manifest['session'], 'missing': manifest['missing'], 'redactions': manifest['redactions']}, ensure_ascii=False, indent=2))
    if args.html:
        body = ''.join('<details open><summary>' + html.escape(name) + '</summary><pre>' + html.escape(text) + '</pre></details>' for name, text in files.items())
        args.html.write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>DSH-Houdini diagnostic report</title><style>body{font:15px/1.6 system-ui;margin:32px;max-width:1100px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eee;padding:16px}details{margin:16px 0}</style><h1>DSH-Houdini 故障报告</h1>' + body + '</html>', encoding='utf-8')


if __name__ == '__main__':
    main()
