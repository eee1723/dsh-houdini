"""Deterministic managed visual-check path policy; no Houdini scene required."""

from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_preview_paths as paths


def reject(fn, expected):
    try:
        fn()
    except Exception as error:
        assert expected in str(error), str(error)
        return
    raise AssertionError('expected rejection: ' + expected)


def allocate(hip, requested=None, *, owner='session-a', frame=3):
    return paths.allocate_managed(
        str(hip), requested, frame=frame, purpose='test', owner_session=owner,
        repository_root=ROOT, default_label='架子 iso view',
        allowed_extensions={'.png', '.jpg'},
        expand=lambda value: value.replace('$F4', f'{int(frame):04d}'),
    )


with tempfile.TemporaryDirectory(prefix='dsh-managed-preview-') as tmp:
    base = Path(tmp)
    hip = base / '项目 scene.hip'
    hip.touch()
    first = allocate(hip)
    second = allocate(hip, '中文 wide view.$F4.png')
    third = allocate(hip, owner='session-b')
    assert first['output_policy'] == 'managed'
    assert Path(first['actual_path']).parent.parent.name == 'dsh-visual-checks'
    assert Path(first['managed_root']) == Path(first['actual_path']).parent
    assert first['hip_relative_path'].startswith('dsh-visual-checks/')
    assert first['actual_path'] != second['actual_path']
    assert '0003' in Path(second['actual_path']).name
    assert first['run_id'] != third['run_id']
    assert len(list(Path(first['managed_root']).glob('*.reserve'))) == 2
    with ThreadPoolExecutor(max_workers=8) as pool:
        concurrent = list(pool.map(lambda _index: allocate(hip, 'parallel.png'), range(24)))
    assert len({row['actual_path'] for row in concurrent}) == 24
    assert len(list(Path(first['managed_root']).glob('*.reserve'))) == 26
    for row in concurrent:
        assert paths.release_reservation(row) == []
    assert len(list(Path(first['managed_root']).glob('*.reserve'))) == 2

    # Force the capture-id generator to repeat while the first capture remains
    # in flight. The reservation must make a duplicate destination impossible.
    original_token_hex = paths.secrets.token_hex
    paths.secrets.token_hex = lambda _size: 'forced'
    forced = allocate(hip, 'forced.png')
    try:
        reject(lambda: allocate(hip, 'forced.png'), 'unique')
    finally:
        paths.secrets.token_hex = original_token_hex
        assert paths.release_reservation(forced) == []
    reserve_count = len(list(Path(first['managed_root']).glob('*.reserve')))
    original_write = paths.os.write
    paths.os.write = lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError('injected token write failure'))
    try:
        reject(lambda: allocate(hip, 'write-failure.png'), 'token write failure')
    finally:
        paths.os.write = original_write
    assert len(list(Path(first['managed_root']).glob('*.reserve'))) == reserve_count

    reject(lambda: allocate('', None), 'named HIP')
    for bad in ('../root.png', 'folder/image.png', r'C:\root.png', r'\\server\share.png',
                'alternate:stream.png'):
        reject(lambda bad=bad: allocate(hip, bad), 'basename')
    reject(lambda: allocate(hip, 'bad' + chr(0) + '.png'), 'basename')
    reject(lambda: allocate(hip, 'CON.png'), 'reserved')
    reject(lambda: allocate(hip, 'bad?.png'), 'basename')
    reject(lambda: allocate(hip, '$UNKNOWN.png'), 'unexpanded')
    reject(lambda: allocate(hip, 'image.exr'), 'unsupported')
    reject(lambda: paths.allocate_managed(
        str(hip), '$OUT.png', frame=1, purpose='test', owner_session='a',
        repository_root=ROOT, default_label='x', allowed_extensions={'.png'},
        expand=lambda _value: '../escaped.png'), 'basename')

    # A file occupying the visible managed root is a preflight failure and is
    # never deleted or silently bypassed.
    conflicting = base / 'blocked'
    conflicting.mkdir()
    blocked_hip = conflicting / 'scene.hip'
    blocked_hip.touch()
    marker = conflicting / 'dsh-visual-checks'
    marker.write_text('keep', encoding='utf-8')
    reject(lambda: allocate(blocked_hip), 'not a directory')
    assert marker.read_text(encoding='utf-8') == 'keep'

    # Save As changes only future allocation. Existing captures remain where
    # they were and no migration is attempted.
    other = base / 'save-as'
    other.mkdir()
    other_hip = other / 'renamed.hip'
    other_hip.touch()
    after_save_as = allocate(other_hip)
    assert Path(after_save_as['actual_path']).is_relative_to(other)
    assert Path(first['managed_root']).exists()

    # Redirecting the visible managed directory is rejected even when the link
    # target remains elsewhere inside the HIP directory. Symlink creation can
    # be unavailable on locked-down Windows hosts; that platform gap is explicit.
    redirected = base / 'redirected'
    redirected.mkdir()
    redirected_hip = redirected / 'scene.hip'
    redirected_hip.touch()
    real_store = redirected / 'other-store'
    real_store.mkdir()
    link = redirected / 'dsh-visual-checks'
    symlink_checked = False
    try:
        link.symlink_to(real_store, target_is_directory=True)
        symlink_checked = True
    except OSError:
        if os.name == 'nt':
            made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(real_store)],
                                  capture_output=True, text=True)
            symlink_checked = made.returncode == 0
    if symlink_checked:
        reject(lambda: allocate(redirected_hip), 'redirected')
        os.rmdir(link)
        outside_store = base / 'outside-store'
        outside_store.mkdir()
        if os.name == 'nt':
            made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside_store)],
                                  capture_output=True, text=True)
            if made.returncode == 0:
                reject(lambda: allocate(redirected_hip), 'escapes')
                os.rmdir(link)
        else:
            link.symlink_to(outside_store, target_is_directory=True)
            reject(lambda: allocate(redirected_hip), 'escapes')
            link.unlink()
    if not symlink_checked:
        print('managed preview path note: directory symlink/junction negative not available on this host')

    # Redirecting the run directory after allocation cannot move the output
    # boundary together with the emitted candidate.
    after_dir = base / 'redirect-after-allocation'
    after_dir.mkdir(); after_hip = after_dir / 'scene.hip'; after_hip.touch()
    after_artifact = allocate(after_hip, 'after.png')
    run_root = Path(after_artifact['managed_root'])
    saved_root = run_root.with_name(run_root.name + '-saved')
    redirected_target = after_dir / 'late-target'; redirected_target.mkdir()
    os.rename(run_root, saved_root)
    late_linked = False
    try:
        try:
            run_root.symlink_to(redirected_target, target_is_directory=True)
            late_linked = True
        except OSError:
            if os.name == 'nt':
                made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(run_root), str(redirected_target)],
                                      capture_output=True, text=True)
                late_linked = made.returncode == 0
        if late_linked:
            reject(lambda: paths.with_actual_path(after_artifact, after_artifact['actual_path'], str(after_hip)),
                   'redirected')
    finally:
        if late_linked:
            if run_root.is_symlink(): run_root.unlink()
            else: os.rmdir(run_root)
        os.rename(saved_root, run_root)
        assert paths.release_reservation(after_artifact) == []

    # Same-process reload preserves the private run identity; a new owner still
    # receives a distinct run directory.
    run_before = first['run_id']
    assert paths.release_reservation(first) == []
    assert paths.release_reservation(second) == []
    assert paths.release_reservation(third) == []
    assert paths.release_reservation(after_save_as) == []
    importlib.reload(paths)
    reloaded = allocate(hip)
    other_owner = allocate(hip, owner='session-c')
    assert reloaded['run_id'] == run_before
    assert other_owner['run_id'] != run_before
    assert paths.release_reservation(reloaded) == []
    assert paths.release_reservation(other_owner) == []

    explicit = paths.explicit_artifact(str(hip), base / 'delivery' / 'final.png',
                                       frame=1, purpose='delivery')
    assert explicit['output_policy'] == 'explicit'
    assert explicit['managed_root'] is None and explicit['capture_id'] is None

print('managed preview path policy passed')
