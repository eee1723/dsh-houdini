"""Authoritative file candidates stay distinct from final user delivery."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import dsh_bridge as bridge


with tempfile.TemporaryDirectory(prefix='dsh-artifacts-中文 空格-') as temporary:
    root = Path(temporary)
    paths = {name: root / name for name in ('scene.hip', 'piece.dshcomponent', 'preview.png',
                                           'final.exr', 'viewport.png', 'unreported.png')}
    for item in paths.values():
        item.write_bytes(b'fixture')
    missing = root / 'missing.png'
    ledger = [
        {'verb': 'scene_save', 'ok': True, 'result': {'path': str(paths['scene.hip']), 'bytes': 7}},
        {'verb': 'component_export', 'ok': True, 'result': {'ok': True, 'file': str(paths['piece.dshcomponent'])}},
        {'verb': 'render_view', 'ok': True, 'result': {'ok': True, 'output': str(paths['preview.png']),
            'artifact': {'actual_path': str(paths['preview.png']), 'output_policy': 'managed'}}},
        {'verb': 'render_frame', 'ok': True, 'result': {'output': str(paths['final.exr']), 'fresh': True}},
        {'verb': 'viewport_screenshot', 'ok': True, 'result': {'ok': True, 'path': str(paths['viewport.png']),
            'artifact': {'actual_path': str(paths['viewport.png']), 'output_policy': 'managed'}}},
        {'verb': 'render_frame', 'ok': True, 'result': {'output': str(missing), 'fresh': True}},
    ]
    images = [str(paths['preview.png']), str(paths['unreported.png'])]
    candidates = bridge._artifact_candidates(ledger, images, True)
    by_name = {Path(item['path']).name: item for item in candidates}
    assert set(by_name) == set(paths), candidates
    assert by_name['scene.hip']['role'] == 'delivery-candidate'
    assert by_name['piece.dshcomponent']['kind'] == 'component'
    assert by_name['preview.png']['role'] == 'visual-check'
    assert by_name['viewport.png']['role'] == 'diagnostic'
    assert by_name['final.exr']['role'] == 'delivery-candidate'
    assert by_name['unreported.png']['source'] == 'reported-image'
    assert all(item['bytes'] == 7 and Path(item['path']).is_absolute() for item in candidates)
    assert all(item['role'] == 'diagnostic' for item in bridge._artifact_candidates(ledger, images, False))
    rejected = bridge._artifact_candidates([
        {'verb': 'render_frame', 'ok': True, 'result': {'output': str(paths['final.exr']), 'fresh': False}},
        {'verb': 'scene_save', 'ok': False, 'result': {'path': str(paths['scene.hip'])}},
        {'verb': 'scene_save', 'ok': True, 'result': {'path': str(root / 'bad\x00scene.hip')}},
        {'verb': 'render_view', 'ok': True, 'result': {'output': str(paths['preview.png']),
            'ok': True, 'warnings': ['fixture warning'],
            'artifact': {'actual_path': str(paths['preview.png']), 'output_policy': 'explicit'}}},
    ], [], True)
    assert len(rejected) == 2 and all(item['role'] == 'diagnostic' for item in rejected)
    link = root / 'linked.png'
    try:
        link.symlink_to(paths['preview.png'])
    except (OSError, NotImplementedError):
        pass
    else:
        assert bridge._artifact_candidates([], [str(link)], True) == []

    # One actual Bridge execution proves the envelope surfaces the candidate;
    # the scene and its new HIP live only in this isolated hython fixture.
    scene = root / 'saved-by-bridge.hip'
    code = ("__result__ = scene_save_as(path=" + repr(str(scene))
            + ", expected_current_path=scene_info()['hip_path'], reason='isolated fixture')")
    executed = bridge.run_code(code, owner_session='artifact-fixture', owner_call='save-scene')
    assert executed['ok'], executed.get('error')
    actual = executed.get('artifactCandidates') or []
    assert len(actual) == 1 and actual[0]['path'] == str(scene)
    assert actual[0]['kind'] == 'scene' and actual[0]['role'] == 'delivery-candidate'
    assert scene.is_file() and scene.stat().st_size > 0

print('artifact candidates: authoritative paths, roles, missing/link rejection and failed-call downgrade passed')
