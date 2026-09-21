"""Simulated viewport capture lifecycle; no GUI or artistic-quality claim."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import struct
import sys
import tempfile
import threading
import time as _time
import zlib


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_preview_paths as preview_paths


_UNSET = object()


def tiny_png() -> bytes:
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00')) + chunk(b'IEND', b''))


class FlipbookSettings:
    def __init__(self, *, can_stash=True):
        self._output = 'original.png'; self._mplay = True
        self._range = (1, 24); self._leave = True
        if not can_stash: self.stash = None
    def stash(self):
        copied = FlipbookSettings()
        copied._output, copied._mplay = self._output, self._mplay
        copied._range, copied._leave = self._range, self._leave
        return copied
    def output(self, value=_UNSET):
        if value is _UNSET: return self._output
        self._output = value
    def outputToMPlay(self, value=_UNSET):
        if value is _UNSET: return self._mplay
        self._mplay = value
    def frameRange(self, value=_UNSET):
        if value is _UNSET: return self._range
        self._range = value
    def leaveFrameAtEnd(self, value=_UNSET):
        if value is _UNSET: return self._leave
        self._leave = value


class ReferencePlane:
    def __init__(self): self.visible = True
    def isVisible(self): return self.visible
    def setIsVisible(self, value): self.visible = bool(value)


class DisplaySettings:
    def __init__(self, *, guide_failure=None, noop_restore=False):
        self.guides = {'guide-one': True}; self.textures = True; self.backfaces = False
        self.guide_failure = guide_failure; self.noop_restore = noop_restore
    def guideEnabled(self, guide): return self.guides.get(guide, False)
    def enableGuide(self, guide, value):
        if value and self.noop_restore: return
        self.guides[guide] = bool(value)
        if self.guide_failure == 'partial-disable' and not value:
            raise RuntimeError('injected partial guide setter failure')
    def displayTextures(self): return self.textures
    def setDisplayTextures(self, value): self.textures = bool(value)
    def removeBackfaces(self): return self.backfaces
    def setRemoveBackfaces(self, value): self.backfaces = bool(value)


class Camera:
    def __init__(self, values=None):
        self.values = dict(values or {
            'translation': (1, 2, 3), 'rotation': (4, 5, 6), 'pivot': (0, 0, 0),
            'aperture': 41.4, 'aspectRatio': 1.0, 'clipPlanes': (.1, 1000),
            'focalLength': 50, 'focalUnitScale': 1, 'orthoWidth': 10,
            'windowOffset': (0, 0), 'windowSize': (1, 1), 'isOrthographic': False,
        })
    def stash(self): return Camera(self.values)
    def __getattr__(self, name):
        if name in self.values: return lambda: self.values[name]
        raise AttributeError(name)


class LinkedCamera:
    def __init__(self):
        self.parms = {'tx': 7.0, 'ry': 15.0}
        self.keys = {'tx': ((1, 7.0), (10, 9.0))}


class Viewport:
    def __init__(self, *, linked=False, guide_failure=None, noop_restore=False):
        self._default = Camera(); self._linked = LinkedCamera() if linked else None
        self._lock = bool(linked); self.framed = 0
        self._settings = DisplaySettings(guide_failure=guide_failure, noop_restore=noop_restore)
    def settings(self): return self._settings
    def name(self): return 'fake-viewport'
    def defaultCamera(self): return self._default
    def setDefaultCamera(self, camera):
        if self._linked is not None and self._lock:
            self._linked.parms['tx'] = -999
        self._default = camera
    def camera(self): return self._linked
    def setCamera(self, camera): self._linked = camera
    def useDefaultCamera(self): self._linked = None
    def isCameraLockedToView(self): return self._lock
    def lockCameraToView(self, value): self._lock = bool(value)
    def frameBoundingBox(self, _bbox):
        self.framed += 1; self._default.values['translation'] = (9, 9, 9)


class Viewer:
    def __init__(self, mode='write', *, linked=False, can_stash=True,
                 guide_failure=None, noop_restore=False):
        self.live = FlipbookSettings(can_stash=can_stash)
        self.viewport = Viewport(linked=linked, guide_failure=guide_failure, noop_restore=noop_restore)
        self.reference = ReferencePlane(); self.mode = mode; self.calls = 0
        self.writer_event = threading.Event(); self.writer_thread = None
    def curViewport(self): return self.viewport
    def flipbookSettings(self): return self.live
    def referencePlane(self): return self.reference
    def name(self): return 'fake-viewer'
    def flipbook(self, *, viewport, settings):
        assert viewport is self.viewport
        self.calls += 1; target = Path(settings.output())
        if self.mode == 'raise': raise RuntimeError('injected flipbook failure')
        if self.mode == 'raise-late':
            self.writer_thread = threading.Thread(
                target=lambda: (self.writer_event.wait(), target.write_bytes(tiny_png())), daemon=True)
            self.writer_thread.start()
            raise RuntimeError('injected post-dispatch failure')
        if self.mode == 'write': target.write_bytes(tiny_png())
        if self.mode == 'invalid': target.write_bytes(b'not-an-image')
        if self.mode == 'partial':
            target.write_bytes(tiny_png()[:20])
            threading.Thread(target=lambda: (_time.sleep(.25), target.write_bytes(tiny_png())), daemon=True).start()
        if self.mode == 'late':
            self.writer_thread = threading.Thread(
                target=lambda: (self.writer_event.wait(), target.write_bytes(tiny_png())), daemon=True)
            self.writer_thread.start()
        if self.mode == 'wrong-suffix':
            target.with_name(target.stem + '.0004' + target.suffix).write_bytes(tiny_png())
        if self.mode == 'ambiguous':
            target.write_bytes(tiny_png())
            target.with_name(target.stem + '.0005' + target.suffix).write_bytes(tiny_png())


class FakeHou:
    Vector2, Vector3, Vector4 = hou.Vector2, hou.Vector3, hou.Vector4
    Matrix3, Matrix4 = hou.Matrix3, hou.Matrix4
    def __init__(self, viewer):
        self._frame = 1.0; self.frame_calls = []; self.fail_restore = False
        self.paneTabType = SimpleNamespace(SceneViewer=object())
        self.viewportGuide = SimpleNamespace(**{name: ('guide-one' if index == 0 else f'guide-{index}')
                                               for index, name in enumerate(h._CLEAN_GUIDES)})
        desktop = SimpleNamespace(paneTabOfType=lambda _kind: viewer)
        self.ui = SimpleNamespace(curDesktop=lambda: desktop)
    def isUIAvailable(self): return True
    def frame(self): return self._frame
    def setFrame(self, value):
        value = float(value); self.frame_calls.append(value)
        if self.fail_restore and value == 1.0 and self._frame != 1.0:
            raise RuntimeError('injected frame restore failure')
        self._frame = value
    def expandStringAtFrame(self, value, _frame): return value


@contextmanager
def installed(viewer, hip):
    fake = FakeHou(viewer); bbox_frames = []
    old = (h.hou, h.scene_info, h._webview_was_minimized, h._restore_webview_window,
           h._resolve, h._display_bbox)
    h.hou = fake
    h.scene_info = lambda: {'has_named_path': True, 'hip_path': str(hip)}
    h._webview_was_minimized = lambda: False
    h._restore_webview_window = lambda _was=None: None
    h._resolve = lambda value: SimpleNamespace(path=lambda: str(value))
    h._display_bbox = lambda _node: (bbox_frames.append(fake.frame()) or object())
    try: yield fake, bbox_frames
    finally:
        (h.hou, h.scene_info, h._webview_was_minimized, h._restore_webview_window,
         h._resolve, h._display_bbox) = old


def run(viewer, hip, **kwargs):
    with installed(viewer, hip) as (fake, bbox_frames):
        result = h.viewport_screenshot(frame=5, **kwargs)
        return fake, bbox_frames, result


@contextmanager
def fast_timeout():
    old_time, old_sleep = h.time.time, h.time.sleep; clock = [0]
    h.time.time = lambda: (clock.__setitem__(0, clock[0] + 5) or clock[0])
    h.time.sleep = lambda _seconds: None
    try: yield
    finally: h.time.time, h.time.sleep = old_time, old_sleep


with tempfile.TemporaryDirectory(prefix='dsh-viewport-shot-') as tmp:
    base = Path(tmp); hip = base / 'scene.hip'; hip.touch()

    viewer = Viewer()
    fake, bbox_frames, result = run(viewer, hip, clean=True)
    assert result['ok'] and result['fresh'] and result['user_state_restored']
    assert fake.frame() == 1 and fake.frame_calls == [5, 1]
    assert viewer.live.output() == 'original.png' and viewer.live.leaveFrameAtEnd() is True
    assert viewer.viewport.settings().guideEnabled('guide-one') and viewer.reference.isVisible()
    assert result['artifact']['output_policy'] == 'managed'
    assert not list(Path(result['artifact']['managed_root']).glob('*.reserve'))

    linked = Viewer(linked=True); linked_camera = linked.viewport.camera()
    parms_before, keys_before = dict(linked_camera.parms), dict(linked_camera.keys)
    fake, bbox_frames, linked_result = run(linked, hip, clean=True, frame_target='target')
    assert linked_result['framed'] == 'target' and bbox_frames == [5]
    assert linked.viewport.camera() is linked_camera and linked.viewport.isCameraLockedToView()
    assert linked_camera.parms == parms_before and linked_camera.keys == keys_before
    assert linked.viewport.defaultCamera().values['translation'] == (1, 2, 3)

    viewer = Viewer(linked=True)
    with installed(viewer, hip) as (fake, bbox_frames):
        try: h.viewport_screenshot('../bad.png', frame=5, frame_target='target')
        except ValueError as error: assert 'basename' in str(error), error
        else: raise AssertionError('managed traversal should fail')
        assert bbox_frames == [] and fake.frame_calls == [] and viewer.calls == 0

    viewer = Viewer(can_stash=False)
    with installed(viewer, hip) as (fake, bbox_frames):
        try: h.viewport_screenshot('unsupported.png', frame=5)
        except RuntimeError as error: assert 'copied flipbook' in str(error), error
        else: raise AssertionError('missing settings stash should reject')
        assert fake.frame_calls == [] and viewer.calls == 0

    viewer = Viewer(linked=True, guide_failure='partial-disable')
    linked_camera = viewer.viewport.camera(); parms_before = dict(linked_camera.parms)
    with installed(viewer, hip):
        try: h.viewport_screenshot('guide-failure.png', frame=5, clean=True, frame_target='target')
        except h.CheckpointError as error:
            assert 'partial guide setter' in str(error)
            assert error.evidence['user_state_restored'] is True
            assert error.evidence['capture_unresolved'] is False
            assert not Path(error.evidence['path'] + '.reserve').exists()
        else: raise AssertionError('guide setter failure should propagate')
    assert linked_camera.parms == parms_before and viewer.viewport.settings().guideEnabled('guide-one')

    viewer = Viewer(noop_restore=True)
    with installed(viewer, hip):
        try: h.viewport_screenshot('noop.png', frame=5, clean=True)
        except h.CheckpointError as error:
            assert not error.evidence['user_state_restored']
            assert any('guide' in item for item in error.evidence['restore_errors'])
        else: raise AssertionError('no-op restoration should fail')

    stale = base / 'stale.png'; stale.write_bytes(tiny_png())
    with fast_timeout():
        try: run(Viewer(mode='none'), hip, path=str(stale), clean=False, output_policy='explicit')
        except h.CheckpointError as error: assert not error.evidence['fresh']
        else: raise AssertionError('stale screenshot should fail')

    # A managed timeout is unresolved: its exclusive reservation remains so a
    # late asynchronous writer cannot race a reused destination.
    unresolved_root = None
    original_token_hex = preview_paths.secrets.token_hex
    preview_paths.secrets.token_hex = lambda _size: 'lateforced'
    late_viewer = Viewer(mode='late')
    try:
        with fast_timeout():
            try: run(late_viewer, hip, path='unresolved.png', clean=False)
            except h.CheckpointError as error:
                assert error.evidence['capture_unresolved'] is True
                assert error.evidence['artifact']['reservation_retained'] is True
                unresolved_root = Path(error.evidence['artifact']['managed_root'])
                unresolved_path = Path(error.evidence['path'])
            else: raise AssertionError('managed timeout should fail')
        try:
            preview_paths.allocate_managed(str(hip), 'unresolved.png', frame=5,
                purpose='test', owner_session=None, repository_root=ROOT,
                default_label='viewport', allowed_extensions={'.png'})
        except RuntimeError as error:
            assert 'unique' in str(error), error
        else: raise AssertionError('unresolved reservation must block forced destination reuse')
        late_viewer.writer_event.set();late_viewer.writer_thread.join(timeout=2)
        assert not late_viewer.writer_thread.is_alive()
        assert unresolved_path.is_file() and h._screenshot_readable(str(unresolved_path))
    finally:
        preview_paths.secrets.token_hex = original_token_hex
    assert len(list(unresolved_root.glob('*.reserve'))) == 1

    # Dispatch can queue a late writer and still raise. Attempted dispatch is
    # completion-unknown and must retain exclusion until that writer finishes.
    original_token_hex = preview_paths.secrets.token_hex
    preview_paths.secrets.token_hex = lambda _size: 'dispatchforced'
    dispatch_viewer = Viewer(mode='raise-late')
    try:
        try: run(dispatch_viewer, hip, path='dispatch.png', clean=False)
        except h.CheckpointError as error:
            assert 'post-dispatch failure' in str(error)
            assert error.evidence['capture_unresolved'] is True
            assert error.evidence['artifact']['reservation_retained'] is True
            assert not any(key.startswith('_reservation') for key in error.evidence['artifact'])
            dispatch_path = Path(error.evidence['path'])
        else: raise AssertionError('dispatch-then-raise should fail unresolved')
        try:
            preview_paths.allocate_managed(str(hip), 'dispatch.png', frame=5,
                purpose='test', owner_session=None, repository_root=ROOT,
                default_label='viewport', allowed_extensions={'.png'})
        except RuntimeError as error: assert 'unique' in str(error), error
        else: raise AssertionError('post-dispatch reservation must block forced reuse')
        dispatch_viewer.writer_event.set(); dispatch_viewer.writer_thread.join(timeout=2)
        assert not dispatch_viewer.writer_thread.is_alive() and dispatch_path.is_file()
    finally:
        preview_paths.secrets.token_hex = original_token_hex

    # Polling interruption after a completed write is still unresolved because
    # the observer never established settlement.
    original_token_hex = preview_paths.secrets.token_hex
    preview_paths.secrets.token_hex = lambda _size: 'pollforced'
    real_readable = h._screenshot_readable
    h._screenshot_readable = lambda _candidate: (_ for _ in ()).throw(
        KeyboardInterrupt('injected polling interruption'))
    try:
        try: run(Viewer(), hip, path='poll-interrupt.png', clean=False)
        except h.CheckpointError as error:
            assert 'polling interruption' in str(error)
            assert error.evidence['capture_unresolved'] is True
            assert error.evidence['artifact']['reservation_retained'] is True
        else: raise AssertionError('poll interruption should fail unresolved')
        try:
            preview_paths.allocate_managed(str(hip), 'poll-interrupt.png', frame=5,
                purpose='test', owner_session=None, repository_root=ROOT,
                default_label='viewport', allowed_extensions={'.png'})
        except RuntimeError as error: assert 'unique' in str(error), error
        else: raise AssertionError('poll-interrupt reservation must block forced reuse')
    finally:
        h._screenshot_readable = real_readable
        preview_paths.secrets.token_hex = original_token_hex

    readable_calls = []
    real_readable = h._screenshot_readable
    h._screenshot_readable = lambda candidate: (readable_calls.append(candidate) or real_readable(candidate))
    try:
        with fast_timeout():
            try: run(Viewer(mode='invalid'), hip, path=str(base / 'invalid.png'), clean=False, output_policy='explicit')
            except h.CheckpointError as error: assert 'stable readable' in str(error), error
            else: raise AssertionError('invalid screenshot should fail')
    finally:
        h._screenshot_readable = real_readable
    assert readable_calls, 'invalid-image negative must exercise the decoder'
    with fast_timeout():
        try: run(Viewer(mode='wrong-suffix'), hip, path=str(base / 'wrong-suffix.png'), clean=False, output_policy='explicit')
        except h.CheckpointError as error: assert 'stable readable' in str(error), error
        else: raise AssertionError('wrong-frame screenshot should fail')
    assert (base / 'wrong-suffix.0004.png').is_file()
    try: run(Viewer(mode='ambiguous'), hip, path=str(base / 'ambiguous.png'), clean=False, output_policy='explicit')
    except h.CheckpointError as error: assert 'ambiguous' in str(error), error
    else: raise AssertionError('ambiguous screenshot should fail')

    _, _, partial = run(Viewer(mode='partial'), hip, path=str(base / 'partial.png'),
                        clean=False, output_policy='explicit')
    assert partial['fresh'] and Path(partial['path']).read_bytes() == tiny_png()

    _, _, globbed = run(Viewer(), hip, path=str(base / 'capture[1].png'),
                        clean=False, output_policy='explicit')
    assert Path(globbed['path']).name == 'capture[1].png'

    # A produced file whose emitted path fails policy revalidation is not
    # registered as an attachment.
    real_with_actual = preview_paths.with_actual_path
    preview_paths.with_actual_path = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        ValueError('injected emitted-path validation failure'))
    h._PRODUCED_IMAGES.clear()
    try:
        try: run(Viewer(), hip, path=str(base / 'invalid-emitted.png'), clean=False,
                 output_policy='explicit')
        except h.CheckpointError as error:
            assert 'emitted-path validation failure' in str(error)
            assert not error.evidence['fresh'] and not h._PRODUCED_IMAGES
        else: raise AssertionError('emitted path validation should fail')
    finally:
        preview_paths.with_actual_path = real_with_actual

    viewer = Viewer(mode='raise')
    try: run(viewer, hip, path=str(base / 'failure.png'), clean=False, output_policy='explicit')
    except h.CheckpointError as error:
        assert 'injected flipbook failure' in str(error) and error.evidence['user_state_restored']
    else: raise AssertionError('flipbook failure should propagate')

    viewer = Viewer(); fake = FakeHou(viewer); fake.fail_restore = True
    old = (h.hou, h.scene_info, h._webview_was_minimized, h._restore_webview_window)
    h.hou = fake; h.scene_info = lambda: {'has_named_path': True, 'hip_path': str(hip)}
    h._webview_was_minimized = lambda: False; h._restore_webview_window = lambda _was=None: None
    h._PRODUCED_IMAGES.clear()
    try:
        try: h.viewport_screenshot('restore.png', frame=5, clean=False)
        except h.CheckpointError as error:
            assert error.evidence['fresh'] and not error.evidence['user_state_restored']
            assert Path(error.evidence['path']).resolve() in {Path(item).resolve() for item in h._PRODUCED_IMAGES}
            assert not error.evidence['artifact'].get('reservation_retained')
            assert not Path(error.evidence['path'] + '.reserve').exists()
        else: raise AssertionError('restore failure should reject success')
    finally:
        h.hou, h.scene_info, h._webview_was_minimized, h._restore_webview_window = old

print('viewport screenshot lifecycle, decode, requested-frame and failure simulation passed (no GUI claim)')
