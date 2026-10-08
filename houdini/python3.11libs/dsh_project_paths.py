"""Read-only project directory roles shared by Houdini and the Node Host.

The installed JSON is the only directory/lifecycle source. These observations
do not create directories, prove write permission, follow child-directory
redirects, or manage the lifetime of files already written there.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


with (Path(__file__).resolve().parent.parent / 'project-layout.json').open(encoding='utf-8') as source:
    _LAYOUT = json.load(source)


def directory_path(role: str) -> str:
    """Return the declared project-relative path for one output role."""
    return _LAYOUT['directories'][role]['path']


def lifecycle(role: str) -> str:
    """Describe a role, without authorizing cleanup or declaring delivery."""
    return _LAYOUT['directories'][role]['lifecycle']


def project_layout(hip_path, *, has_named_path: bool) -> dict:
    """Observe one HIP anchor; a default/relative HIP never falls back to cwd."""
    available = (has_named_path and isinstance(hip_path, str)
                 and bool(hip_path.strip()) and os.path.isabs(hip_path))
    root = os.path.realpath(os.path.dirname(hip_path)) if available else None
    return {
        'schema_version': _LAYOUT['schemaVersion'],
        'available': bool(available),
        'hip_path': os.path.abspath(hip_path).replace('\\', '/') if available else None,
        'project_root': root.replace('\\', '/') if root is not None else None,
        # Keep visible child paths: the actual writer checks redirection and
        # permission at use time. Resolving children here would conceal links.
        'directories': {role: os.path.join(root, entry['path']).replace('\\', '/')
                        for role, entry in _LAYOUT['directories'].items()} if available else {},
    }
