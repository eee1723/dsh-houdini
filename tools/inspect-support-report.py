from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'houdini/python3.11libs'))
from dsh_support_report import inspect_report, report_html, save_reviewed_file


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
        save_reviewed_file(args.html.absolute(), report_html(files).encode('utf-8'), html_document=True)


if __name__ == '__main__':
    main()
