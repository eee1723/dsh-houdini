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
import dsh_project_paths as project_paths


def reject(fn, expected):
    try:
        fn()
    except Exception as error:
        assert expected in str(error), str(error)
        return
    raise AssertionError('expected rejection: ' + expected)


def allocate(hip, requested=None, *, owner='session-a', frame=3, output_policy='managed'):
    return paths.allocate_managed(
        str(hip), requested, frame=frame, purpose='test', owner_session=owner,
        repository_root=ROOT, default_label='架子 iso view',
        allowed_extensions={'.png', '.jpg'},
        expand=lambda value: value.replace('$F4', f'{int(frame):04d}'),
        output_policy=output_policy,
    )


with tempfile.TemporaryDirectory(prefix='dsh-managed-preview-') as tmp:
    base = Path(tmp)
    hip = base / '项目 scene.hip'
    hip.touch()
    # Metadata is a read-only observation of the named HIP, not a workspace
    # fallback, mkdir operation, or permission claim.
    layout = project_paths.project_layout(str(hip), has_named_path=True)
    assert layout['available'] and layout['schema_version'] == 1
    assert Path(layout['project_root']).samefile(base)
    assert set(layout['directories']) == {'reference_downloaded', 'reference_generated', 'texture', 'cache', 'analysis', 'render', 'visual_check'}
    assert Path(layout['directories']['reference_downloaded']) == base.resolve() / 'dsh-reference' / 'downloaded'
    assert Path(layout['directories']['reference_generated']) == base.resolve() / 'dsh-reference' / 'generated'
    assert Path(layout['directories']['texture']) == base.resolve() / 'dsh-texture'
    assert Path(layout['directories']['cache']) == base.resolve() / 'dsh-cache'
    assert Path(layout['directories']['analysis']) == base.resolve() / 'dsh-analysis'
    assert {entry.name for entry in base.iterdir()} == {hip.name}
    for filename, named in ((str(hip), False), (None, False), ('relative.hip', True)):
        missing = project_paths.project_layout(filename, has_named_path=named)
        assert missing['available'] is False and missing['directories'] == {}
        assert missing['hip_path'] is None and missing['project_root'] is None
    first = allocate(hip)
    second = allocate(hip, '中文 wide view.$F4.png')
    third = allocate(hip, owner='session-b')
    assert first['output_policy'] == 'managed'
    assert first['role'] == 'visual_check' and first['lifecycle'] == 'visual-check'
    assert first['project_root'] == layout['project_root']
    assert Path(first['actual_path']).parent.parent.name == 'dsh-visual-checks'
    assert Path(first['managed_root']) == Path(first['actual_path']).parent
    assert first['hip_relative_path'].startswith('dsh-visual-checks/')
    assert first['actual_path'] != second['actual_path']
    assert '0003' in Path(second['actual_path']).name
    assert first['run_id'] != third['run_id']
    assert len(list(Path(first['managed_root']).glob('*.reserve'))) == 2
    delivery = allocate(hip, '最终交付.png', output_policy='delivery')
    another_delivery = allocate(hip, '最终交付.png', output_policy='delivery')
    # Windows CI may expose TEMP through an 8.3 alias; the allocator resolves
    # that alias to the same directory's long spelling.
    assert Path(delivery['actual_path']).parent.samefile(base / 'dsh-render')
    assert delivery['output_policy'] == 'delivery' and delivery['hip_relative_path'].startswith('dsh-render/')
    assert delivery['role'] == 'render' and delivery['lifecycle'] == 'render-output'
    assert delivery['project_root'] == layout['project_root']
    assert delivery['actual_path'] != another_delivery['actual_path']
    assert paths.with_actual_path(delivery, delivery['actual_path'], str(hip))['output_policy'] == 'delivery'
    assert paths.release_reservation(delivery) == [] and paths.release_reservation(another_delivery) == []
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
    try:
        for policy in ('managed', 'delivery'):
            forced = allocate(hip, 'forced.png', output_policy=policy)
            reject(lambda: allocate(hip, 'forced.png', output_policy=policy), 'unique')
            # A finished published file also owns its name after its reservation
            # has gone; allocation cannot overwrite or bypass the existing file.
            published_file = Path(forced['actual_path'])
            published_file.write_bytes(b'published capture to preserve')
            assert paths.release_reservation(forced) == []
            reject(lambda: allocate(hip, 'forced.png', output_policy=policy), 'unique')
            assert published_file.read_bytes() == b'published capture to preserve'
    finally:
        paths.secrets.token_hex = original_token_hex
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

    # A basename is data. Never hand an accepted backtick expression to HOM's
    # filename expansion, which could execute an hscript/python expression.
    expression_directory = base / 'expression-preflight'
    expression_directory.mkdir()
    expression_hip = expression_directory / 'scene.hip'
    expression_hip.touch()
    expansion_calls = []
    for policy in ('managed', 'delivery'):
        reject(lambda: paths.allocate_managed(
            str(expression_hip), "`pythonexprs('str(hou.setFrame(20))')`.png",
            frame=1, purpose='test', owner_session='a', repository_root=ROOT,
            default_label='x', allowed_extensions={'.png'}, output_policy=policy,
            expand=lambda value: expansion_calls.append(value) or 'expanded.png'),
            'executable expressions')
    assert expansion_calls == []
    assert {p.name for p in expression_directory.iterdir()} == {'scene.hip'}

    # A file occupying the visible managed root is a preflight failure and is
    # never deleted or silently bypassed.
    conflicting = base / 'blocked'
    conflicting.mkdir()
    blocked_hip = conflicting / 'scene.hip'
    blocked_hip.touch()
    for policy, folder in (('managed', 'dsh-visual-checks'), ('delivery', 'dsh-render')):
        marker = conflicting / folder
        marker.write_text('keep', encoding='utf-8')
        reject(lambda: allocate(blocked_hip, output_policy=policy), 'not a directory')
        assert marker.read_text(encoding='utf-8') == 'keep'

    # Save As changes only future allocation. Existing captures remain where
    # they were and no migration is attempted.
    other = base / 'save-as'
    other.mkdir()
    other_hip = other / 'renamed.hip'
    other_hip.touch()
    after_save_as = allocate(other_hip)
    assert after_save_as['project_root'] != first['project_root']
    assert paths.with_actual_path(first, first['actual_path'], str(hip))['project_root'] == layout['project_root']
    # CI may create the fixture under an 8.3 short user path while the managed
    # allocator resolves it to the long spelling. Compare filesystem paths,
    # not those two lexical spellings of the same directory.
    assert Path(after_save_as['actual_path']).resolve().is_relative_to(other.resolve())
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
    for policy, folder in (('managed', 'dsh-visual-checks'), ('delivery', 'dsh-render')):
        link = redirected / folder
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
            visible = project_paths.project_layout(str(redirected_hip), has_named_path=True)
            role = 'visual_check' if policy == 'managed' else 'render'
            assert Path(visible['directories'][role]) == redirected.resolve() / folder
            reject(lambda: allocate(redirected_hip, output_policy=policy), 'redirected')
            os.rmdir(link)
            outside_store = base / ('outside-store-' + policy)
            outside_store.mkdir()
            if os.name == 'nt':
                made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside_store)],
                                      capture_output=True, text=True)
                if made.returncode == 0:
                    reject(lambda: allocate(redirected_hip, output_policy=policy), 'escapes')
                    os.rmdir(link)
            else:
                link.symlink_to(outside_store, target_is_directory=True)
                reject(lambda: allocate(redirected_hip, output_policy=policy), 'escapes')
                link.unlink()
        if not symlink_checked:
            print(policy + ' preview path note: directory symlink/junction negative not available on this host')

    # Redirecting the run directory after allocation cannot move the output
    # boundary together with the emitted candidate.
    after_dir = base / 'redirect-after-allocation'
    after_dir.mkdir(); after_hip = after_dir / 'scene.hip'; after_hip.touch()
    for policy in ('managed', 'delivery'):
        after_artifact = allocate(after_hip, 'after.png', output_policy=policy)
        reject(lambda: paths.with_actual_path(after_artifact, after_dir / 'escaped.png', str(after_hip)),
               'left its validated output directory')
        suffixed = Path(after_artifact['actual_path']).with_name(
            Path(after_artifact['actual_path']).stem + '_backend.png')
        emitted = paths.with_actual_path(after_artifact, str(suffixed), str(after_hip))
        assert emitted['output_policy'] == policy
        assert Path(emitted['actual_path']) == suffixed
        assert '_reservation_path' not in emitted and '_reservation_token' not in emitted
        run_root = Path(after_artifact['managed_root'])
        saved_root = run_root.with_name(run_root.name + '-saved')
        redirected_target = after_dir / ('late-target-' + policy); redirected_target.mkdir()
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
    assert explicit['role'] == 'visual_check' and explicit['project_root'] == layout['project_root']
    outside = paths.explicit_artifact(None, base / 'outside-named-project.png', frame=1, purpose='existing_ui')
    assert outside['project_root'] is None and outside['hip_relative_path'] is None

print('managed preview path policy passed')
