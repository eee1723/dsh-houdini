"""One immutable load diagnostic, bounded previews and worker-only result archival; no HOM."""
from pathlib import Path
import hashlib
import json
import os
import tempfile
import threading
import uuid
import dsh_recovery_store as store

_POLICY = json.loads((Path(__file__).resolve().parent.parent / 'result-detail-policy.json').read_text(encoding='utf-8'))
if (_POLICY.get('schemaVersion') != 1 or any(type(_POLICY.get(key)) is not int or _POLICY[key] <= 0
        for key in ('maxArchiveBytes', 'detailThresholdChars', 'loadWarningPreviewBytes'))
        or _POLICY['loadWarningPreviewBytes'] < 128):
    raise ValueError('Unsupported result detail policy')
MAX_BYTES = _POLICY['maxArchiveBytes']
PREVIEW_BYTES = _POLICY['loadWarningPreviewBytes']


def _size(text):
    # ASCII escaping also bounds UTF-8 and DSH's extra template-brace escaping.
    return len(json.dumps([text], ensure_ascii=True).replace('{', '\\u007b').replace('}', '\\u007d'))


def preview(text):
    """Head and tail share one serialized budget; never parse warning severity."""
    if len(text) <= PREVIEW_BYTES and _size(text) <= PREVIEW_BYTES:
        return text, 0
    low, high = 0, min(len(text), PREVIEW_BYTES)
    def excerpt(kept):
        head = (kept + 1) // 2
        tail = kept // 2
        return text[:head] + '\n[… middle omitted …]\n' + (text[-tail:] if tail else '')
    while low < high:
        middle = (low + high + 1) // 2
        if _size(excerpt(middle)) <= PREVIEW_BYTES:
            low = middle
        else:
            high = middle - 1
    return excerpt(low), len(text) - low


def _chunks(text):
    # Same returned-result format consumed by the existing Host resource reader.
    yield b'{"ok":true,"stdout":"","stderr":"","result":{"load_warnings":["'
    for start in range(0, len(text), 4096):
        yield json.dumps(text[start:start + 4096], ensure_ascii=True)[1:-1].encode('ascii')
    yield b'"]}}'


class LoadWarning:
    """Capture on the actor, persist once on its HTTP worker; snapshots never wait for I/O."""
    def __init__(self, text):
        self._producer = threading.get_ident()
        self._raw = text
        self._preview, omitted = preview(text)
        self._details = {'capture_id': uuid.uuid4().hex, 'original_chars': len(text),
                         'omitted_chars': omitted, 'truncated': omitted > 0, 'status': 'pending'}
        self._lock = threading.Lock()

    def reference(self):
        return dict(self._details)

    def excerpt(self):
        return [self._preview]

    def persist(self):
        if threading.get_ident() == self._producer:
            raise RuntimeError('Load warning archival must not run on the Houdini owning thread')
        with self._lock:
            if self._details['status'] != 'pending':
                return
            temporary = None
            try:
                if len(self._raw) > MAX_BYTES:
                    raise ValueError('load warning exceeds the result archive budget')
                folder = store.root() / 'load-warnings'
                folder.mkdir(parents=True, exist_ok=True)
                descriptor, temporary = tempfile.mkstemp(prefix='warning-', suffix='.tmp', dir=folder)
                digest, size = hashlib.sha256(), 0
                with os.fdopen(descriptor, 'wb') as output:
                    for chunk in _chunks(self._raw):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise ValueError('encoded load warning exceeds the result archive budget')
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                ref = digest.hexdigest()
                target = folder / (ref + '.json')
                try:
                    os.link(temporary, target)  # Publish a complete immutable file, without replacing one.
                except FileExistsError:
                    if target.is_symlink() or target.stat().st_size != size or store.file_digest(target)[0] != ref:
                        raise RuntimeError('existing load warning artifact does not match its content hash')
                self._details = {**self._details, 'status': 'stored', 'stored': True,
                                 'sha256': ref, 'path': str(target.resolve()), 'bytes': size,
                                 'format': 'returned_bridge_envelope_json'}
            except Exception as error:
                self._details = {**self._details, 'status': 'unavailable', 'stored': False,
                                 'error': (type(error).__name__ + ': ' + str(error))[:240]}
            finally:
                self._raw = None
                if temporary is not None:
                    try:
                        os.unlink(temporary)
                    except OSError:
                        pass  # A leftover private temp file is not a published result reference.
