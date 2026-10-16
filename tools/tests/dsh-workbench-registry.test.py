from pathlib import Path
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
from dsh_executor_registry import ExecutorRegistration


def refused(action):
    try:
        action()
    except RuntimeError:
        return
    raise AssertionError('conflicting operation was accepted')


with tempfile.TemporaryDirectory(prefix='workbench-reservations-') as temporary:
    folder = Path(temporary)
    original, other, destination = (folder / name for name in ('original.hip', 'other.hip', 'new.hip'))
    original.write_bytes(b'original')
    other.write_bytes(b'other')
    first = ExecutorRegistration(folder, 'a' * 32, installation=ROOT, version='21.0.440', workbench=True)
    second = ExecutorRegistration(folder, 'b' * 32, installation=ROOT, version='22.0.368', workbench=True)
    third = ExecutorRegistration(folder, 'c' * 32, installation=ROOT, version='22.0.368', workbench=True)
    fourth = ExecutorRegistration(folder, '9' * 32, installation=ROOT, version='22.0.368', workbench=True)
    scene = {'scene_id': 'd' * 32, 'scene_epoch': 'e' * 32, 'hip_is_new': False, 'workspace_path': str(folder)}
    try:
        first.publish(18001, '1' * 32, hip=original, scene=scene)
        second.publish(18002, '2' * 32, hip=other, scene=scene)
        first.claim('task-a', first._generation, str(original), str(original), idle=True)
        second.claim('task-b', second._generation, str(other), str(other), idle=True)
        refused(lambda: first.claim('task-c', first._generation, str(original), str(original)))
        first.claim('task-c', first._generation, str(original), str(original), idle=True)
        refused(lambda: first.require_writer('task-a', str(original)))
        entered = []
        try:
            with first.save_target(other):
                entered.append(True)
        except RuntimeError:
            pass
        assert not entered and other.read_bytes() == b'other'
        try:
            with first.save_target(destination):
                raise ValueError('save failed')
        except ValueError:
            pass
        assert first.registered_hip() == str(original)
        with first.save_target(destination):
            destination.write_bytes(b'saved')
        assert first.registered_hip() == str(destination)
        alias = folder / 'hardlink.hip'
        os.link(destination, alias)
        refused(lambda: third.claim_writer('alias-task', alias))
        third.claim_writer('original-now-free', original)
        first.require_writer('task-c', str(destination))
        next_target = folder / 'published-later.hip'
        with patch('dsh_executor_registry.atomic_json', side_effect=OSError('publication failed')):
            try:
                with first.save_target(next_target):
                    next_target.write_bytes(b'saved despite publication failure')
            except OSError:
                pass
        refused(lambda: fourth.claim_writer('other-task', next_target))
        first.observe(str(next_target), {**scene, 'scene_epoch': '7' * 32})
        assert first._task == 'task-c', 'reloading the same HIP must not release its writer between recovery phases'
        refused(lambda: fourth.claim_writer('other-task', next_target))
        assert first.observe(str(original), scene, is_current=lambda:False) is False
        assert first.registered_hip() == str(next_target) and first._task == 'task-c', 'late observations must not roll back newer project selection'
        old_generation = first._generation
        first.observe(str(other), {**scene, 'scene_epoch': 'f' * 32})
        assert first._generation != old_generation and first._task is None
        refused(lambda: first.claim('stale', old_generation, str(other), str(other), idle=True))
    finally:
        first.close()
        second.close()
        third.close()
        fourth.close()
    unsaved = folder / 'untitled.hip'
    registrations = [ExecutorRegistration(folder, identity * 32, installation=ROOT, version='21.0.440', workbench=True)
                     for identity in ('4', '5')]
    try:
        for index, registration in enumerate(registrations):
            registration.publish(18100 + index, '6' * 32, hip=unsaved, scene={**scene, 'hip_is_new': True})
            registration.claim('unsaved-' + str(index), registration._generation, str(unsaved), str(unsaved), idle=True)
        assert not registrations[0]._writers and not registrations[1]._writers
    finally:
        for registration in registrations:
            registration.close()
print('PASS workbench writer boundaries: active task, occupied Save As, failed save, new file identity/hardlink, retained locks after publication failure, scene generation and independent unsaved scenes')
