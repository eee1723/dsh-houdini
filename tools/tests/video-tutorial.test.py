"""Offline behavior tests; never upload video or require Houdini/API credentials."""
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import shutil
from types import SimpleNamespace as Args
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("video_tutorial", ROOT / "skills/houdini-video-tutorial/scripts/video_tutorial.py")
video = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video)


class VideoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dsh-video-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "input.mp4"
        self.source.write_bytes(b"synthetic source identity, not a real video")
        self.work = self.root / "work"
        self.work.mkdir()
        self.chunks = []
        for index, (start, end) in enumerate(video.ranges(2, 12, 14, 5, 1)):
            audio = self.work / f"audio-{index:05d}.wav"
            audio.write_bytes(f"synthetic test chunk {index}".encode())
            self.chunks.append({"id": f"{index:05d}", "start": start, "end": end,
                                "audio": audio.name, "sha256": video.sha(audio)})
        self.manifest = {"schema": 1, "source": str(self.source), "source_sha256": video.sha(self.source),
             "duration": 14, "start": 2, "end": 14, "chunk": 5, "overlap": 1,
             "has_audio": True, "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
             "timestamp_basis": video.BASIS, "chunks": self.chunks}
        video.save(self.work / "manifest.json", self.manifest)
        self.args = Args(work=str(self.work), model="test/asr", allow_upload=True, max_chunks=2, retry_failed=False)
        self.calls = []

    def sender(self, path, model, key):
        self.calls.append(path.name)
        return "Turn parameter to 0.2", "synthetic-trace"

    def transcribe(self, sender=None):
        return video.transcribe(self.args, sender=sender or self.sender, get_key=lambda: "test-only-secret")

    def write_manifest(self):
        (self.work / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_fractional_end_and_invalid_bounds(self):
        self.assertEqual(video.ranges(2, 99, 14.5, 5, 1), [(2, 7), (6, 11), (10, 14.5)])
        for inputs in [(0, 2, 9, 2, 2), (-1, 2, 9, 2, 1), (0, 2, 9, float("nan"), 0), (9, 2, 9, 2, 0)]:
            with self.assertRaises(video.Failure):
                video.ranges(*inputs)

    def test_authorization_precedes_key_and_network(self):
        self.args.allow_upload = False
        with self.assertRaises(video.Failure):
            video.transcribe(self.args, sender=lambda *a: self.fail("network"), get_key=lambda: self.fail("key"))
        self.assertFalse((self.work / "asr-config.json").exists())

    def test_resume_skips_success(self):
        self.assertEqual(self.transcribe()["submitted"], 2)
        self.assertEqual(self.transcribe(), {"submitted": 1, "remaining": 0})
        self.assertEqual(self.transcribe()["submitted"], 0)
        self.assertEqual(len(set(self.calls)), 3)
        self.assertEqual(len(self.calls), 3)

    def test_partial_export_honest(self):
        self.transcribe()
        summary = video.export(Args(work=str(self.work), output=str(self.root / "export")))
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(summary["missing"][0]["id"], "00002")
        self.assertEqual(summary["semantic_visual_inspection"], "unverified")
        self.assertEqual(summary["timestamp_basis"], video.BASIS)

    def test_complete_export_does_not_certify_text(self):
        self.args.max_chunks = 3
        self.transcribe()
        summary = video.export(Args(work=str(self.work), output=str(self.root / "export")))
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["text_accuracy"], "unverified")

    def test_unknown_request_not_automatically_retried(self):
        video.save(self.work / "attempt-00000-1.json", {"id": "00000", "attempt": 1,
                                                       "audio_sha256": self.chunks[0]["sha256"]})
        with self.assertRaises(video.Failure):
            self.transcribe()
        self.assertFalse(self.calls)
        self.args.retry_failed = True
        self.transcribe()
        self.assertTrue((self.work / "attempt-00000-2.json").exists())

    def test_failure_stops_and_retry_budget(self):
        def fail(*args):
            self.calls.append("failed")
            raise TimeoutError("secret must not be emitted")
        with self.assertRaisesRegex(video.Failure, "no automatic retry"):
            self.transcribe(fail)
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn("secret", (self.work / "outcome-00000-1.json").read_text())
        with self.assertRaises(video.Failure):
            self.transcribe(fail)
        self.assertEqual(len(self.calls), 1)
        self.args.retry_failed = True
        with self.assertRaises(video.Failure):
            self.transcribe(fail)
        with self.assertRaises(video.Failure):
            self.transcribe(fail)
        self.assertEqual(len(self.calls), 2)

    def test_changed_source_blocks_network(self):
        self.source.write_bytes(b"changed")
        with self.assertRaises(video.Failure):
            self.transcribe()
        self.assertFalse(self.calls)

    def test_changed_audio_blocks_network(self):
        (self.work / "audio-00000.wav").write_bytes(b"changed")
        with self.assertRaises(video.Failure):
            self.transcribe()
        self.assertFalse(self.calls)

    def test_changed_model_blocks_resume(self):
        self.transcribe()
        self.args.model = "different/model"
        with self.assertRaises(video.Failure):
            self.transcribe()
        self.assertEqual(len(self.calls), 2)

    def test_corrupt_response_is_not_missing(self):
        self.transcribe()
        path = self.work / "outcome-00000-1.json"
        outcome = video.read(path)
        outcome["text"] = "different transcript"
        path.write_text(json.dumps(outcome))
        with self.assertRaises(video.Failure):
            self.transcribe()
        self.assertEqual(len(self.calls), 2)

    def test_orphan_response_blocks_resubmission(self):
        video.save(self.work / "outcome-00000-1.json", {"status": "unknown"})
        with self.assertRaises(video.Failure):
            self.transcribe()
        self.assertFalse(self.calls)

    def test_silent_video_is_visual_only(self):
        self.manifest["has_audio"] = False
        self.manifest["chunks"] = []
        self.write_manifest()
        with self.assertRaisesRegex(video.Failure, "No audio"):
            self.transcribe()
        summary = video.export(Args(work=str(self.work), output=str(self.root / "export")))
        self.assertEqual(summary["status"], "no_audio")

    def test_frame_bounds_and_no_semantic_claim(self):
        args = Args(work=str(self.work), output=str(self.root / "frames"), times=[1, 14], ffmpeg="unused")
        with patch.object(video, "video_timing", return_value={"origin": "0", "end": 14}):
            with self.assertRaises(video.Failure):
                video.frames(args)
        self.assertFalse((self.root / "frames").exists())
        args.times = [1, 12]
        def fake_run(command, *, stderr=False):
            self.assertIn("-n", command)
            Path(command[-1]).write_bytes(b"synthetic PNG")
            seconds = float(command[command.index("-ss") + 1])
            return f"config in time_base: 1/1000, frame_rate: 25/1\nn: 0 pts: {int(seconds * 1000)} pts_time:{seconds}".encode()
        with patch.object(video, "run", fake_run), patch.object(video, "video_timing", return_value={"origin": "0", "end": 14}):
            self.assertEqual(video.frames(args)["frames"], 2)
        manifest = video.read(self.root / "frames/frames.json")
        self.assertEqual(manifest["semantic_inspection"], "not_performed")
        self.assertEqual(manifest["frames"][1]["requested_seconds"], 12)
        self.assertEqual(manifest["frames"][1]["actual_seconds"], 12)
        self.assertEqual(manifest["timestamp_basis"], "decoded_pts_minus_container_start")

    def test_scan_grid_tail_and_budget(self):
        self.assertEqual(video.sample_times(0, 95, 30, 10, tail=True), [0, 30, 60, 90, 94])
        self.assertEqual(video.sample_times(2.1, 3.2, .5, 48), [2.1, 2.6, 3.1])
        for start, end, interval, limit in [(0, 95, 30, 4), (0, 9, 0, 10), (0, 9, float("nan"), 10), (8, 2, 1, 10)]:
            with self.assertRaises(video.Failure):
                video.sample_times(start, end, interval, limit, tail=True)

    def test_pts_uses_first_encoded_frame_and_rational_base(self):
        log = b"config in time_base: 1/16000, frame_rate: 30/1\nn: 0 pts: 226134 pts_time:14.1334\nn: 1 pts: 226667 pts_time:14.1667"
        pts, base, actual = video.frame_pts(log)
        self.assertEqual(pts, 226134)
        self.assertEqual(base, "1/16000")
        self.assertEqual(actual, 14.133375)
        with self.assertRaises(video.Failure):
            video.frame_pts(b"pts_time:N/A")

    def test_pts_origin_and_no_silent_seek_mismatch(self):
        target = self.root / "frame.png"
        def fake_run(*args, **kwargs):
            target.write_bytes(b"png")
            return b"config in time_base: 1/10, frame_rate: 10/1\nn: 0 pts: 66 pts_time:6.6"
        with patch.object(video, "run", fake_run):
            row = video.extract_frame(str(self.source), target, 1.55, "5", "ffmpeg")
            self.assertAlmostEqual(row["actual_seconds"], 1.6)
            self.assertAlmostEqual(row["seek_delta_seconds"], .05)
            with self.assertRaises(video.Failure):
                video.extract_frame(str(self.source), target, 2, "5", "ffmpeg")

    def test_video_stream_span_handles_nonzero_origin(self):
        data = {"format": {"start_time": "5", "duration": "8"},
                "streams": [{"start_time": "5", "duration": "3"}]}
        with patch.object(video, "run", return_value=json.dumps(data).encode()):
            self.assertEqual(video.video_timing("source", "ffprobe"), {"origin": "5", "end": 3})

    def test_review_oversized_range_rejected_before_output(self):
        args = Args(work=str(self.work), start=0, duration=14, interval=.01, output=str(self.root / "review"), ffmpeg="unused")
        with patch.object(video, "video_timing", return_value={"origin": "0", "end": 14}):
            with self.assertRaises(video.Failure):
                video.frame_job(args, "review")
        self.assertFalse((self.root / "review").exists())

    def test_scan_does_not_require_audio_or_cloud(self):
        args = Args(video=str(self.source), work=None, start=0, duration=None, interval=5,
                    output=str(self.root / "scan"), ffmpeg="unused", ffprobe="unused")
        def fake_extract(source, path, requested, origin, ffmpeg):
            path.write_bytes(b"png")
            return {"requested_seconds": requested, "actual_seconds": requested, "file": path.name, "sha256": video.sha(path)}
        with patch.object(video, "video_timing", return_value={"origin": "0", "end": 14}), \
             patch.object(video, "extract_frame", fake_extract), patch.object(video, "thumbnail_font", return_value="font"), \
             patch.object(video, "contact_index", return_value=[]), patch.object(video, "post", side_effect=AssertionError("cloud")):
            result = video.frame_job(args, "scan")
        self.assertEqual(result["frames"], 4)
        data = video.read(self.root / "scan/frames.json")
        self.assertFalse(data["plan"]["operation_detection"])
        self.assertEqual(data["semantic_inspection"], "not_performed")

    def test_contact_sheet_sequence_and_links(self):
        output = self.root / "sheets"
        output.mkdir()
        items = [{"file": f"frame-{i:04d}.png", "actual_seconds": i + .123, "requested_seconds": i} for i in range(13)]
        commands = []
        def fake_run(command, **kwargs):
            commands.append(command)
            Path(command[-1]).write_bytes(b"png")
        with patch.object(video, "run", fake_run):
            sheets = video.contact_index(output, items, "ffmpeg", "font.ttf")
        self.assertEqual([s["count"] for s in sheets], [12, 1])
        self.assertIn("tile=1x1:nb_frames=1:padding=4:margin=4:color=black", commands[-1])
        content = (output / "index.md").read_text()
        self.assertIn("00:00:12.123", content)
        self.assertIn("frame-0012.png", content)
    def test_protect_source_tree_and_existing_output(self):
        with self.assertRaises(video.Failure):
            video.directory(ROOT / "tools/out/video-test", new=True)
        with self.assertRaises(FileExistsError):
            video.directory(self.work, new=True)
        self.assertEqual(self.source.read_bytes(), b"synthetic source identity, not a real video")

    def test_lock_blocks_concurrent_upload(self):
        with video.lock(self.work):
            with self.assertRaises(video.Failure):
                self.transcribe()
        self.assertFalse(self.calls)

    def test_credential_echo_rejected(self):
        with self.assertRaises(video.Failure):
            self.transcribe(lambda *args: ("test-only-secret", "trace"))
        self.assertNotIn("test-only-secret", (self.work / "outcome-00000-1.json").read_text())

    def test_empty_text_is_visible(self):
        self.args.max_chunks = 3
        self.transcribe(lambda *args: ("", "trace"))
        summary = video.export(Args(work=str(self.work), output=str(self.root / "export")))
        self.assertEqual(len(summary["empty_text_ids"]), 3)


class ChangeCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dsh-video-change-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.frames = self.root / "frames"
        self.frames.mkdir()
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"source")
        self.rows = []
        for i in range(3):
            path = self.frames / f"frame-{i:04d}.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + video.struct.pack(">II", 80, 40) + bytes([i]))
            self.rows.append({"file": path.name, "sha256": video.sha(path), "source_pts": i * 10,
                              "actual_seconds": i * 10, "time_base": "1"})
        self.index = {"schema": 2, "status": "complete", "timestamp_basis": "decoded_pts_minus_container_start",
                      "source": str(self.source), "source_sha256": video.sha(self.source), "origin_seconds": "0", "frames": self.rows}
        video.save(self.frames / "frames.json", self.index)
        self.args = Args(frames_dir=str(self.frames), output=str(self.root / "changes"), region=None,
                         analysis_width=32, analysis_height=32, pixel_threshold=.08, mean_threshold=.02,
                         fraction_threshold=.08, ffmpeg="unused")

    def rewrite(self):
        (self.frames / "frames.json").write_text(json.dumps(self.index), encoding="utf-8")

    def test_region_validation(self):
        self.assertEqual(video.parse_regions(None)[0]["name"], "full")
        for items in [["x:0:0:1.1:1"], ["x:0:0:nan:1"], ["x:0:0:0:1"], ["x:0:0:1:1", "x:0:0:1:1"], ["x;cmd:0:0:1:1"]]:
            with self.assertRaises((video.Failure, ValueError)):
                video.parse_regions(items)

    def test_region_excludes_viewport_and_retains_color_changes(self):
        before = bytes([0] * 4 * 2 * 3)
        after = bytearray(before)
        for y in range(2):
            for x in range(2):
                after[(y * 4 + x) * 3] = 255
        regions = video.parse_regions(["viewport:0:0:0.5:1", "parameters:0.5:0:0.5:1"])
        left = video.pixel_metrics(before, after, 4, 2, regions[0], .08)
        right = video.pixel_metrics(before, after, 4, 2, regions[1], .08)
        self.assertEqual(left["changed_fraction"], 1)
        self.assertEqual(left["mean_delta"], 1)
        self.assertEqual(right["mean_delta"], 0)

    def test_small_noise_below_threshold(self):
        before, after = bytes(12), bytes([1] * 12)
        score = video.pixel_metrics(before, after, 2, 2, video.parse_regions(None)[0], .08)
        self.assertEqual(score["changed_fraction"], 0)
        self.assertLess(score["mean_delta"], .02)

    def test_candidates_preserve_all_pairs_and_bracket(self):
        self.index["frames"][1]["actual_seconds"] = 30
        self.index["frames"][2]["actual_seconds"] = 60
        def decoder(path, *args):
            return bytes([255 if path.name == "frame-0002.png" else 0] * 32 * 32 * 3)
        pairs = video.compare_index(self.frames, self.index, self.args, video.parse_regions(None), decoder=decoder)
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0]["state"], "below_threshold")
        self.assertTrue(pairs[1]["candidate"])
        self.assertEqual(pairs[1]["range_seconds"], [30, 60])
        self.assertEqual(pairs[1]["operation_semantics"], "unverified")

    def test_duplicate_pts_has_no_event(self):
        self.index["frames"][1]["actual_seconds"] = 0
        pairs = video.compare_index(self.frames, self.index, self.args, video.parse_regions(None),
                                    decoder=lambda *args: bytes(32 * 32 * 3))
        self.assertEqual(pairs[0]["state"], "duplicate_pts")
        self.assertFalse(pairs[0]["candidate"])

    def test_tampered_frame_rejected_before_comparison(self):
        (self.frames / "frame-0001.png").write_bytes(b"corrupt")
        with self.assertRaises(video.Failure):
            video.checked_frame_index(self.frames)

    def test_timestamp_mismatch_or_nonchronological_rejected(self):
        self.index["frames"][1]["actual_seconds"] = 13
        self.rewrite()
        with self.assertRaises(video.Failure):
            video.checked_frame_index(self.frames)
        self.index["frames"][1]["actual_seconds"] = 30
        self.index["frames"][1]["source_pts"] = 30
        self.rewrite()
        with self.assertRaises(video.Failure):
            video.checked_frame_index(self.frames)

    def test_partial_or_legacy_index_rejected(self):
        for field, value in [("schema", 1), ("status", "partial")]:
            old = self.index[field]
            self.index[field] = value
            self.rewrite()
            with self.assertRaises(video.Failure):
                video.checked_frame_index(self.frames)
            self.index[field] = old

    def test_invalid_threshold_no_output(self):
        self.args.mean_threshold = float("nan")
        with self.assertRaises(video.Failure):
            video.changes(self.args)
        self.assertFalse(Path(self.args.output).exists())

    def test_zero_candidates_export_is_not_no_operations(self):
        # Patch at comparison layer; decoder itself is separately exercised with real PNG below.
        pairs = video.compare_index(self.frames, self.index, self.args, video.parse_regions(None),
                                    decoder=lambda *args: bytes(32 * 32 * 3))
        with patch.object(video, "compare_index", return_value=pairs), patch.object(video, "post", side_effect=AssertionError("network")):
            result = video.changes(self.args)
        self.assertEqual(result["candidates"], 0)
        report = video.read(Path(self.args.output) / "changes.json")
        self.assertEqual(len(report["pairs"]), 2)
        self.assertEqual(report["semantic_inspection"], "not_performed")
        self.assertIn("small_text_edits_can_be_missed", report["limitations"])
        self.assertIn("不构成", (Path(self.args.output) / "index.md").read_text(encoding="utf-8"))


class EvidenceNotesTests(unittest.TestCase):
    setUp = ChangeCandidateTests.setUp

    def packet(self):
        path = self.root / "transcript.json"
        video.save(path, {"source_sha256": self.index["source_sha256"], "timestamp_basis": video.BASIS,
                         "chunks": [{"start": 0, "end": 12, "text": "A setting"}, {"start": 15, "end": 25, "text": "Another setting"}]})
        packet = video.build_context(self.frames, path, 0, 20)
        context = self.root / "context.json"
        video.save(context, packet)
        return packet, context

    def notes(self, context):
        return {"schema": 1, "context_sha256": video.sha(context), "steps": [{
            "id": "step-one", "kind": "observed_state", "range_seconds": [0, 10], "intent": "Read the displayed mode",
            "speech_ids": ["speech-00000"], "visual": [{"frame_id": "frame-0000.png", "observed": "Mode shown in panel"}],
            "inferences": [], "conflicts": [], "unknowns": [], "evidence_state": "visual_checked",
            "reconstruction_readiness": "ready_for_runtime_check"}]}

    def test_context_extracts_overlaps_and_gaps(self):
        packet, path = self.packet()
        self.assertEqual(packet["speech_gaps"], [[12, 15]])
        self.assertEqual(len(packet["frames"]), 3)
        self.assertEqual(packet["speech"][1]["end"], 25)  # preserve original ASR bounds
        self.assertEqual(video.checked_context(path), packet)

    def test_foreign_video_transcript_rejected(self):
        path = self.root / "foreign.json"
        video.save(path, {"source_sha256": "wrong", "timestamp_basis": video.BASIS, "chunks": []})
        with self.assertRaises(video.Failure):
            video.build_context(self.frames, path, 0, 20)

    def test_silent_context_has_explicit_gap(self):
        packet = video.build_context(self.frames, None, 0, 20)
        self.assertEqual(packet["speech_gaps"], [[0, 20]])
        self.assertEqual(packet["speech"], [])

    def test_tampered_packet_is_not_evidence(self):
        packet, path = self.packet()
        packet["speech"][0]["text"] = "fabricated"
        path.write_text(json.dumps(packet))
        with self.assertRaises(video.Failure):
            video.checked_context(path)

    def test_changed_transcript_invalidates_context(self):
        packet, path = self.packet()
        Path(packet["transcript"]["path"]).write_text("{}")
        with self.assertRaises(video.Failure):
            video.checked_context(path)

    def test_pass_is_not_semantic_verification(self):
        packet, path = self.packet()
        receipt = video.validate_notes(self.notes(path), packet, video.sha(path))
        self.assertEqual(receipt["structural_validation"], "passed")
        self.assertEqual(receipt["semantic_validation"], "agent_assertions_not_independently_verified")
        self.assertEqual(receipt["runtime_verification"], "not_performed")

    def test_missing_frame_and_out_of_range_speech_rejected(self):
        packet, path = self.packet()
        notes = self.notes(path)
        notes["steps"][0]["visual"][0]["frame_id"] = "frame-9999.png"
        with self.assertRaises(video.Failure):
            video.validate_notes(notes, packet, video.sha(path))
        notes = self.notes(path)
        notes["steps"][0]["speech_ids"] = ["speech-00001"]
        with self.assertRaisesRegex(video.Failure, "step-one:.*speech-00001"):
            video.validate_notes(notes, packet, video.sha(path))

    def test_single_snapshot_cannot_be_operation(self):
        packet, path = self.packet()
        notes = self.notes(path)
        notes["steps"][0]["kind"] = "demonstrated_operation"
        with self.assertRaises(video.Failure):
            video.validate_notes(notes, packet, video.sha(path))

    def test_unresolved_conflict_and_unknown_cannot_be_ready(self):
        packet, path = self.packet()
        for key in ("conflicts", "unknowns"):
            notes = self.notes(path)
            notes["steps"][0][key] = ["not resolved"]
            with self.assertRaises(video.Failure):
                video.validate_notes(notes, packet, video.sha(path))

    def test_conflict_can_be_retained_without_certifying_it(self):
        packet, path = self.packet()
        notes = self.notes(path)
        notes["steps"][0].update(conflicts=["speech and panel disagree"], evidence_state="conflict",
                                  reconstruction_readiness="needs_more_evidence")
        self.assertEqual(video.validate_notes(notes, packet, video.sha(path))["needs_more_evidence"], ["step-one"])

    def test_check_notes_creates_readable_handoff(self):
        packet, path = self.packet()
        notes_path = self.root / "notes.json"
        video.save(notes_path, self.notes(path))
        output = self.root / "checked"
        result = video.check_notes(Args(context=str(path), notes=str(notes_path), output=str(output)))
        self.assertEqual(result["structural_validation"], "passed")
        self.assertIn("speech-00000", (output / "index.md").read_text(encoding="utf-8"))


class TutorialIndexTests(unittest.TestCase):
    packet = EvidenceNotesTests.packet
    notes = EvidenceNotesTests.notes

    def setUp(self):
        ChangeCandidateTests.setUp(self)
        _, self.context_path = self.packet()
        self.notes_path = self.root / "notes.json"
        video.save(self.notes_path, self.notes(self.context_path))
        with patch.object(video, "video_timing", return_value={"end": 30}), patch.object(video, "probe", return_value=(30.095, [])):
            result = video.index_init(Args(frames_dir=str(self.frames), transcript=str(self.root / "transcript.json"),
                output=str(self.root / "catalog"), ffprobe="unused"))
        self.path = Path(result["index"])
        self.catalog = video.read(self.path)
        self.catalog["chapters"] = [{"id": "chapter-a", "title": "Build", "ranges": [[0, 15]]},
                                    {"id": "chapter-b", "title": "Correction", "ranges": [[15, 30]]}]
        self.catalog["modules"] = [{"id": "module-a", "title": "Distribution", "ranges": [[0, 12], [15, 30]],
            "purpose": "Understand distribution and its later correction", "inputs": ["source geometry"],
            "outputs": ["points"], "depends_on": [], "questions": ["Which input is connected?"],
            "unknowns": ["Source of the offscreen wire"], "evidence": [{
                "context": video.file_reference(self.context_path), "notes": video.file_reference(self.notes_path),
                "step_ids": ["step-one"]}]}]
        self.write_catalog()
        self.query = Args(index=str(self.path), module="module-a", max_chars=24000)

    def write_catalog(self):
        self.path.write_text(json.dumps(self.catalog), encoding="utf-8")

    def test_discontinuous_module_reads_original_bounds_and_evidence(self):
        result = video.read_index(self.query)
        self.assertEqual([c["text"] for c in result["speech"]], ["A setting", "Another setting"])
        self.assertEqual(result["speech"][1]["end"], 25)
        self.assertEqual(result["speech_gaps"], [{"range": [0, 12], "gaps": []}, {"range": [15, 30], "gaps": [[25, 30]]}])
        self.assertEqual(result["module"]["unknowns"], ["Source of the offscreen wire"])
        self.assertEqual(result["observations"][0]["frames"][0]["actual_seconds"], 0)
        self.assertEqual(result["runtime_verification"], "not_performed")

    def test_audio_tail_uses_media_boundary_not_video_end(self):
        path = self.root / "transcript.json"
        transcript = video.read(path)
        transcript["chunks"].append({"start": 30, "end": 30.095, "text": "audio tail"})
        path.write_text(json.dumps(transcript), encoding="utf-8")
        self.catalog["transcript"] = video.file_reference(path)
        self.catalog["modules"][0]["evidence"] = []
        self.write_catalog()
        data, chunks = video.index_sources(self.path)
        self.assertEqual(data["video_duration_seconds"], 30)
        self.assertEqual(chunks[-1]["end"], 30.095)
        transcript["chunks"][-1]["end"] = 31
        path.write_text(json.dumps(transcript), encoding="utf-8")
        self.catalog["transcript"] = video.file_reference(path)
        self.write_catalog()
        with self.assertRaisesRegex(video.Failure, "exceeds media duration"):
            video.index_sources(self.path)

    def test_legacy_index_and_invalid_video_span(self):
        self.catalog.pop("video_duration_seconds")
        self.write_catalog()
        video.read_index(self.query)
        self.catalog["video_duration_seconds"] = 10
        self.write_catalog()
        with self.assertRaisesRegex(video.Failure, "Invalid source duration"):
            video.read_index(self.query)

    def test_module_pages_preserve_all_items_and_unknowns(self):
        self.query.section, self.query.offset, self.query.limit = "speech", 0, 1
        first = video.read_index(self.query)
        self.query.index_sha256 = first["index_sha256"]
        self.query.offset = first["next_offset"]
        second = video.read_index(self.query)
        self.assertEqual([r["id"] for r in first["items"] + second["items"]], ["speech-00000", "speech-00001"])
        self.assertIsNone(second["next_offset"])
        self.assertEqual(first["module_unknowns"], self.catalog["modules"][0]["unknowns"])
        self.query.section, self.query.offset = "observations", 0
        self.assertEqual(video.read_index(self.query)["items"][0]["step"]["id"], "step-one")

    def test_module_page_revision_change_and_invalid_paging(self):
        self.query.section, self.query.offset, self.query.limit = "speech", 0, 1
        self.query.index_sha256 = video.read_index(self.query)["index_sha256"]
        self.catalog["modules"][0]["questions"].append("New requirement")
        self.write_catalog()
        with self.assertRaisesRegex(video.Failure, "Index changed"):
            video.read_index(self.query)
        self.query.index_sha256 = None
        self.query.offset = 3
        with self.assertRaisesRegex(video.Failure, "offset exceeds"):
            video.read_index(self.query)
        self.query.section = "all"
        with self.assertRaisesRegex(video.Failure, "Select speech"):
            video.read_index(self.query)

    def test_overview_does_not_expand_transcript_or_observations(self):
        self.query.module = None
        result = video.read_index(self.query)
        self.assertNotIn("speech", result)
        self.assertNotIn("observations", result)
        self.assertEqual(result["modules"][0]["unknowns"], 1)
        self.assertEqual(result["semantic_validation"], "agent_assertions_not_independently_verified")

    def test_module_read_excludes_unrelated_speech_without_cutting_chunk(self):
        self.catalog["modules"][0]["ranges"] = [[0, 10]]
        self.write_catalog()
        result = video.read_index(self.query)
        self.assertEqual(len(result["speech"]), 1)
        self.assertEqual(result["speech"][0]["end"], 12)
        self.assertEqual(result["transcript"]["sha256"], video.sha(self.root / "transcript.json"))

    def test_paging_works_before_agent_authors_modules(self):
        self.catalog["chapters"], self.catalog["modules"] = [], []
        self.write_catalog()
        args = Args(index=str(self.path), offset=0, limit=1, max_chars=24000)
        first = video.read_transcript(args)
        args.offset = first["next_offset"]
        second = video.read_transcript(args)
        self.assertEqual(first["chunks"][0]["id"], "speech-00000")
        self.assertEqual(second["chunks"][0]["id"], "speech-00001")
        self.assertIsNone(second["next_offset"])
        with self.assertRaises(video.Failure):
            video.check_index(args)

    def test_budget_rejects_instead_of_truncating(self):
        self.query.max_chars = 1000
        with self.assertRaisesRegex(video.Failure, "No content truncated"):
            video.read_index(self.query)
        self.query.max_chars = 24000
        self.assertEqual(len(video.read_index(self.query)["speech"]), 2)

    def test_transcript_revision_invalidates_read(self):
        (self.root / "transcript.json").write_text("{}")
        with self.assertRaisesRegex(video.Failure, "Transcript changed"):
            video.read_index(self.query)

    def test_notes_revision_invalidates_read(self):
        self.notes_path.write_text("{}")
        with self.assertRaisesRegex(video.Failure, "Notes changed"):
            video.read_index(self.query)

    def test_cycle_missing_dependency_and_unknown_module_rejected(self):
        module = self.catalog["modules"][0]
        for dependency in ("module-a", "absent"):
            module["depends_on"] = [dependency]
            self.write_catalog()
            with self.assertRaises(video.Failure):
                video.read_index(self.query)
        module["depends_on"] = []
        self.write_catalog()
        self.query.module = "absent"
        with self.assertRaisesRegex(video.Failure, "Unknown module"):
            video.read_index(self.query)

    def test_ranges_and_evidence_scope_rejected(self):
        for ranges in ([[0, 31]], [[15, 25], [0, 12]], [[0, 20], [15, 25]], [[15, 25]]):
            self.catalog["modules"][0]["ranges"] = ranges
            self.write_catalog()
            with self.assertRaises(video.Failure):
                video.read_index(self.query)

    def test_conflicting_notes_remain_visible(self):
        notes = self.notes(self.context_path)
        notes["steps"][0].update(conflicts=["Panel differs from speech"], evidence_state="conflict",
                                  reconstruction_readiness="needs_more_evidence")
        self.notes_path.write_text(json.dumps(notes))
        self.catalog["modules"][0]["evidence"][0]["notes"] = video.file_reference(self.notes_path)
        self.write_catalog()
        step = video.read_index(self.query)["observations"][0]["step"]
        self.assertEqual(step["conflicts"], ["Panel differs from speech"])
        self.assertEqual(step["reconstruction_readiness"], "needs_more_evidence")
        self.query.module = None
        self.assertEqual(video.read_index(self.query)["modules"][0]["evidence_conflicts"], 1)

    def test_chapter_gaps_remain_visible(self):
        self.catalog["chapters"] = self.catalog["chapters"][:1]
        self.write_catalog()
        self.query.module = None
        self.assertEqual(video.read_index(self.query)["chapter_gaps"], [[15, 30.095]])

    def test_silent_index_has_no_invented_speech(self):
        self.catalog["transcript"] = None
        self.catalog["modules"][0]["evidence"] = []
        self.write_catalog()
        result = video.read_index(self.query)
        self.assertEqual(result["speech"], [])
        self.assertEqual(result["speech_gaps"][0]["gaps"], [[0, 12]])

    def test_foreign_transcript_cannot_be_pinned_as_same_source(self):
        path = self.root / "foreign.json"
        video.save(path, {"source_sha256": "other", "timestamp_basis": video.BASIS, "chunks": []})
        self.catalog["transcript"] = video.file_reference(path)
        self.write_catalog()
        with self.assertRaisesRegex(video.Failure, "another source"):
            video.read_index(self.query)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/ffprobe not installed; offline unit tests still run")
class MediaTimingTests(unittest.TestCase):
    def test_silent_cli_scan_index_evidence_and_crop_comparison(self):
        with tempfile.TemporaryDirectory(prefix="dsh-video-cli-") as folder:
            root = Path(folder)
            source = root / "静音.mp4"
            video.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-f", "lavfi",
                       "-i", "testsrc2=size=96x64:rate=10:duration=3", "-c:v", "mpeg4", str(source)])
            def cli(*args):
                result = video.run([sys.executable, str(Path(video.__file__)), *map(str, args)])
                return json.loads(result.decode("utf-8").splitlines()[-1])
            frames = root / "frames"
            cli("scan", "--video", source, "--output", frames, "--interval", 1)
            result = cli("index-init", "--frames-dir", frames, "--output", root / "catalog")
            index = Path(result["index"])
            data = video.read(index)
            data["chapters"] = [{"id": "chapter", "title": "Silent demonstration", "ranges": [[0, 3]]}]
            packet = cli("context", "--frames-dir", frames, "--start", 0, "--end", 2, "--output", root / "evidence")
            context = root / "evidence/context.json"
            notes = {"schema": 1, "context_sha256": packet["context_sha256"], "steps": [{
                "id": "state", "kind": "observed_state", "range_seconds": [0, 2], "intent": "Synthetic fixture only",
                "speech_ids": [], "visual": [{"frame_id": "frame-0000.png", "observed": "Synthetic test pattern"}],
                "inferences": [], "conflicts": [], "unknowns": ["No actual tutorial semantics in fixture"],
                "evidence_state": "visual_checked", "reconstruction_readiness": "needs_more_evidence"}]}
            notes_path = root / "notes.json"
            video.save(notes_path, notes)
            cli("check-notes", "--context", context, "--notes", notes_path, "--output", root / "checked")
            data["modules"] = [{"id": "module", "title": "Silent module", "ranges": [[0, 3]], "purpose": "Exercise CLI",
                "inputs": [], "outputs": [], "depends_on": [], "questions": [], "unknowns": [],
                "evidence": [{"context": video.file_reference(context), "notes": video.file_reference(notes_path), "step_ids": ["state"]}]}]
            index.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(cli("check-index", "--index", index)["modules"][0]["evidence_pending"], 1)
            self.assertEqual(cli("read-transcript", "--index", index)["chunks"], [])
            self.assertEqual(cli("read-index", "--index", index, "--module", "module")["observations"][0]["step"]["id"], "state")
            compared = cli("changes", "--frames-dir", frames, "--output", root / "changes", "--region-mode", "crop-first",
                           "--region", "panel:0.1:0.1:0.5:0.5")
            self.assertEqual(compared["semantic_inspection"], "not_performed")
            self.assertEqual(video.read(root / "changes/changes.json")["settings"]["region_mode"], "crop-first")

    def test_crop_first_preserves_small_region_change(self):
        with tempfile.TemporaryDirectory(prefix="dsh-video-crop-") as folder:
            root = Path(folder)
            before, after = root / "before.png", root / "after.png"
            for path, draw in ((before, None), (after, "drawbox=x=960:y=540:w=4:h=10:color=white:t=fill")):
                command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-f", "lavfi",
                           "-i", "color=black:size=1920x1080"]
                if draw:
                    command += ["-vf", draw]
                video.run(command + ["-frames:v", "1", "-update", "1", str(path)])
            region = video.parse_regions(["parameter:0.5:0.5:0.025:0.025"])[0]
            full = video.parse_regions(None)[0]
            grid = [video.comparison_rgb(p, "ffmpeg", 32, 32) for p in (before, after)]
            crop = [video.comparison_rgb(p, "ffmpeg", 32, 32, region) for p in (before, after)]
            grid_score = video.pixel_metrics(*grid, 32, 32, region, .08)
            crop_score = video.pixel_metrics(*crop, 32, 32, full, .08)
            self.assertLess(grid_score["mean_delta"], .02)
            self.assertGreater(crop_score["mean_delta"], .02)
            outside = video.parse_regions(["other:0:0:0.025:0.025"])[0]
            self.assertEqual(video.comparison_rgb(before, "ffmpeg", 32, 32, outside),
                             video.comparison_rgb(after, "ffmpeg", 32, 32, outside))

    def test_real_rgb_decoder(self):
        with tempfile.TemporaryDirectory(prefix="dsh-change-rgb-") as folder:
            image = Path(folder) / "red.png"
            video.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-f", "lavfi",
                       "-i", "color=red:size=80x40", "-frames:v", "1", "-update", "1", str(image)])
            rgb = video.comparison_rgb(image, "ffmpeg", 32, 32)
            self.assertEqual(len(rgb), 32 * 32 * 3)
            self.assertGreater(rgb[0], 240)
            self.assertLess(rgb[1], 10)
            self.assertEqual(video.png_size(image), (80, 40))

    def test_real_vfr_offset_and_original_pixels(self):
        with tempfile.TemporaryDirectory(prefix="dsh-video-vfr-") as folder:
            root = Path(folder)
            source = root / "非零时间.mp4"
            video.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-f", "lavfi",
                       "-i", "testsrc2=size=96x64:rate=10:duration=3", "-vf", "select='not(eq(mod(n,3),1))',setpts=PTS+5/TB",
                       "-fps_mode", "vfr", "-c:v", "mpeg4", "-bf", "2", str(source)])
            timing = video.video_timing(str(source), "ffprobe")
            self.assertEqual(timing["origin"], "5")
            self.assertAlmostEqual(timing["end"], 3)
            frame = root / "frame.png"
            item = video.extract_frame(str(source), frame, .31, timing["origin"], "ffmpeg")
            self.assertAlmostEqual(item["actual_seconds"], .5)
            # Independently decode sequentially from the beginning, not by input seeking.
            expected = root / "expected.png"
            video.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-copyts", "-i", str(source),
                       "-vf", "select='gte(t,5.31)'", "-fps_mode", "passthrough", "-frames:v", "1", "-update", "1", str(expected)])
            self.assertEqual(video.sha(frame), video.sha(expected))


if __name__ == "__main__":
    unittest.main()
