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
    """Return a role's declared base; use directory_for_hip for a destination."""
    return _LAYOUT['directories'][role]['path']


def hip_name(hip_path: str) -> str:
    """Match native $HIPNAME, preserving version suffixes and Unicode spelling."""
    filename = os.path.basename(hip_path)
    stem, extension = os.path.splitext(filename)
    return stem if extension.lower() in ('.hip', '.hiplc', '.hipnc') else filename


def directory_for_hip(role: str, hip_path: str) -> str:
    """Project-relative destination for one captured HIP; creates nothing."""
    entry = _LAYOUT['directories'][role]
    if entry.get('scope') == 'hip_name':
        if not isinstance(hip_path, str) or not hip_path.strip() or not os.path.isabs(hip_path):
            raise ValueError('HIP-scoped output requires a named absolute HIP')
        return os.path.join(entry['path'], hip_name(hip_path)).replace('\\', '/')
    return entry['path']


def directory_expression(role: str) -> str:
    """Native persistent path, reevaluated by Houdini after Save As."""
    entry = _LAYOUT['directories'][role]
    return '$HIP/' + entry['path'] + ('/$HIPNAME' if entry.get('scope') == 'hip_name' else '')


def lifecycle(role: str) -> str:
    """Describe a role, without authorizing cleanup or declaring delivery."""
    return _LAYOUT['directories'][role]['lifecycle']


def project_layout(hip_path, *, has_named_path: bool) -> dict:
    """Observe one HIP anchor; a default/relative HIP never falls back to cwd."""
    available = (has_named_path and isinstance(hip_path, str)
                 and bool(hip_path.strip()) and os.path.isabs(hip_path))
    # Metadata is a lexical projection of the captured HIP. realpath/stat can
    # wait indefinitely on an unavailable UNC share or mapped network drive.
    # Writers resolve and validate the actual filesystem at their I/O boundary.
    root = os.path.abspath(os.path.dirname(hip_path)) if available else None
    return {
        'schema_version': _LAYOUT['schemaVersion'],
        'available': bool(available),
        'hip_path': os.path.abspath(hip_path).replace('\\', '/') if available else None,
        'hip_name': hip_name(hip_path) if available else None,
        'project_root': root.replace('\\', '/') if root is not None else None,
        # Keep visible child paths: the actual writer checks redirection and
        # permission at use time. Resolving children here would conceal links.
        'directories': {role: os.path.join(root, directory_for_hip(role, hip_path)).replace('\\', '/')
                        for role in _LAYOUT['directories']} if available else {},
    }
