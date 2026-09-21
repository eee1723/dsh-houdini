"""Managed visual-check output allocation for dsh-houdini.

This module owns path policy only.  It does not render, inspect pixels, copy
media into the Host workspace, or delete historical captures.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import unicodedata


MANAGED_DIRECTORY = "dsh-visual-checks"
_PROCESS_PID = os.getpid()
if globals().get("_PROCESS_NONCE_PID") != _PROCESS_PID:
    _PROCESS_NONCE_PID = _PROCESS_PID
    _PROCESS_NONCE = secrets.token_hex(16)


def _real(path) -> str:
    return os.path.realpath(os.fspath(path))


def _inside(root: str, target: str) -> bool:
    try:
        return os.path.commonpath([_real(root), _real(target)]) == _real(root)
    except ValueError:
        return False


def _safe_component(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{field} must be a nonempty basename")
    if value != os.path.basename(value) or os.path.isabs(value) or os.path.splitdrive(value)[0]:
        raise ValueError(f"managed {field} accepts a basename only; use output_policy='explicit' for a path")
    if (any(mark in value for mark in ("/", "\\", ":", '<', '>', '"', '|', '?', '*'))
            or value in (".", "..") or value.endswith((" ", "."))):
        raise ValueError(f"managed {field} accepts a basename only; use output_policy='explicit' for a path")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"managed {field} cannot contain control characters")
    stem = value.split('.', 1)[0].upper()
    if stem in {'CON', 'PRN', 'AUX', 'NUL'} or re.fullmatch(r'(?:COM|LPT)[1-9]', stem):
        raise ValueError(f"managed {field} uses a reserved Windows filename")
    return value


def _label(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    value = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._-")
    return (value or "capture")[:80]


def _frame_tag(frame) -> str:
    number = float(frame)
    if not number == number or abs(number) == float("inf"):
        raise ValueError("frame must be finite")
    if number.is_integer():
        return str(int(number)).replace("-", "m")
    return ("%.6f" % number).rstrip("0").rstrip(".").replace("-", "m").replace(".", "p")


def _run_id(owner_session: str | None) -> str:
    authority = owner_session if isinstance(owner_session, str) and owner_session.strip() else "python-shell"
    digest = hashlib.sha256(f"{_PROCESS_NONCE}\x00{authority}".encode("utf-8")).hexdigest()[:12]
    return f"run-{digest}"


def _repository_guard(repository_root: str, target: str) -> None:
    if _inside(repository_root, target):
        raise ValueError("output cannot be written into the plugin repository; choose the HIP project directory")


def allocate_managed(
    hip_path,
    requested,
    *,
    frame,
    purpose: str,
    owner_session: str | None,
    repository_root,
    default_label: str,
    default_extension: str = ".png",
    allowed_extensions=(),
    expand=None,
) -> dict:
    """Allocate one collision-resistant capture path under a named HIP.

    ``requested`` is a label basename, never a directory.  Validation happens
    before the managed directory is created.  The caller remains responsible
    for producing the image and for reporting the actual emitted filename.
    """
    if not isinstance(hip_path, str) or not hip_path.strip():
        raise ValueError("managed visual checks require a named HIP; use scene_save_as with an authorized target first")
    hip = _real(os.path.dirname(hip_path))
    if not hip or not os.path.isdir(hip):
        raise ValueError("managed visual checks require an existing named HIP directory")
    repo = _real(repository_root)
    run_id = _run_id(owner_session)
    expected_base = os.path.abspath(os.path.join(hip, MANAGED_DIRECTORY))
    expected_root = os.path.abspath(os.path.join(expected_base, run_id))
    root = _real(expected_root)
    if not _inside(hip, root):
        raise ValueError("managed visual-check root escapes the HIP directory")
    _repository_guard(repo, root)

    raw = default_label if requested is None else os.fspath(requested)
    raw = _safe_component(raw, field="filename")
    if expand is not None:
        raw = _safe_component(os.fspath(expand(raw)), field="expanded filename")
    if '$' in raw:
        raise ValueError("managed filename contains an unexpanded variable")
    stem, extension = os.path.splitext(raw)
    extension = extension or default_extension
    if not extension.startswith(".") or len(extension) < 2:
        raise ValueError("managed output requires an image extension")
    extension = extension.lower()
    allowed = {str(item).lower() for item in allowed_extensions}
    if allowed and extension not in allowed:
        raise ValueError(f"unsupported managed image extension: {extension}")
    stem = _label(stem or default_label)
    tag = _frame_tag(frame)

    # Refuse an existing file/junction at either managed directory component;
    # this is checked before mkdir so invalid context produces no allocation.
    managed_base = expected_base
    for component in (managed_base, expected_root):
        if os.path.lexists(component) and not os.path.isdir(component):
            raise ValueError(f"managed visual-check directory is not a directory: {component}")
        if os.path.lexists(component) and not _inside(hip, component):
            raise ValueError("managed visual-check directory escapes the HIP directory")
        if os.path.lexists(component) and _real(component) != os.path.abspath(component):
            raise ValueError("managed visual-check directory is redirected; use the visible HIP tree")
    os.makedirs(expected_root, exist_ok=True)
    root = _real(expected_root)
    if (not _inside(hip, root)
            or os.path.normcase(root) != os.path.normcase(_real(expected_root))
            or os.path.normcase(root) != os.path.normcase(expected_root)):
        raise ValueError("managed visual-check directory resolves outside its visible HIP tree")

    # UUID-style random IDs make concurrent allocation independent.  The
    # reservation remains until the caller conclusively finishes or fails;
    # release_reservation removes only this allocation's token.
    for _ in range(32):
        capture_id = secrets.token_hex(8)
        filename = f"{stem}_f{tag}_{capture_id}{extension}"
        target = _real(os.path.join(root, filename))
        if not _inside(root, target):
            raise ValueError("managed capture path escapes its run directory")
        reservation = target + ".reserve"
        try:
            descriptor = os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        write_error = None
        try:
            token = secrets.token_hex(16)
            os.write(descriptor, token.encode('ascii'))
        except BaseException as error:
            write_error = error
        finally:
            os.close(descriptor)
        if write_error is not None:
            try:
                os.remove(reservation)
            except FileNotFoundError:
                pass
            raise write_error
        try:
            if os.path.lexists(target):
                os.remove(reservation)
                continue
            return {
                "purpose": str(purpose),
                "output_policy": "managed",
                "actual_path": target.replace("\\", "/"),
                "hip_relative_path": os.path.relpath(target, hip).replace("\\", "/"),
                "managed_root": root.replace("\\", "/"),
                "run_id": run_id,
                "capture_id": capture_id,
                "frame": float(frame),
                "_reservation_path": reservation,
                "_reservation_token": token,
            }
        except BaseException:
            try:
                os.remove(reservation)
            except FileNotFoundError:
                pass
            raise
    raise RuntimeError("could not allocate a unique managed visual-check filename")


def release_reservation(artifact: dict) -> list[str]:
    """Release only the reservation minted for ``artifact`` and hide internals."""
    reservation = artifact.pop('_reservation_path', None)
    token = artifact.pop('_reservation_token', None)
    if not reservation:
        return []
    try:
        with open(reservation, 'r', encoding='ascii') as source:
            observed = source.read(128)
        if observed != token:
            return [f'reservation ownership changed: {reservation}']
        os.remove(reservation)
        return []
    except FileNotFoundError:
        return []
    except Exception as error:
        return [f'reservation release failed: {error}']


def retain_reservation(artifact: dict) -> None:
    """Hide credentials while deliberately retaining an unresolved capture lock."""
    reservation = artifact.pop('_reservation_path', None)
    artifact.pop('_reservation_token', None)
    if reservation:
        artifact['reservation_retained'] = True


def explicit_artifact(hip_path, target, *, frame, purpose: str) -> dict:
    """Return additive metadata for a caller-resolved explicit destination."""
    actual = _real(target)
    hip_relative = None
    if isinstance(hip_path, str) and hip_path.strip():
        hip = _real(os.path.dirname(hip_path))
        if _inside(hip, actual):
            hip_relative = os.path.relpath(actual, hip).replace("\\", "/")
    return {
        "purpose": str(purpose),
        "output_policy": "explicit",
        "actual_path": actual.replace("\\", "/"),
        "hip_relative_path": hip_relative,
        "managed_root": None,
        "run_id": None,
        "capture_id": None,
        "frame": float(frame),
    }


def with_actual_path(artifact: dict, actual_path, hip_path) -> dict:
    """Update metadata when a backend emits a suffixed filename."""
    result = dict(artifact)
    result.pop('_reservation_path', None)
    result.pop('_reservation_token', None)
    actual = _real(actual_path)
    planned = os.path.abspath(os.fspath(result['actual_path']))
    planned_dir = os.path.dirname(planned)
    if result.get('output_policy') == 'managed':
        managed_root = os.path.abspath(os.fspath(result['managed_root']))
        if (os.path.normcase(planned_dir) != os.path.normcase(managed_root)
                or os.path.normcase(_real(managed_root)) != os.path.normcase(managed_root)):
            raise ValueError('managed preview directory was redirected after allocation')
    if os.path.normcase(os.path.dirname(actual)) != os.path.normcase(planned_dir):
        raise ValueError('emitted preview path left its validated output directory')
    if result.get('output_policy') == 'managed' and not _inside(result['managed_root'], actual):
        raise ValueError('emitted managed preview path left its run directory')
    result["actual_path"] = actual.replace("\\", "/")
    result["hip_relative_path"] = None
    if isinstance(hip_path, str) and hip_path.strip():
        hip = _real(os.path.dirname(hip_path))
        if _inside(hip, actual):
            result["hip_relative_path"] = os.path.relpath(actual, hip).replace("\\", "/")
    return result
