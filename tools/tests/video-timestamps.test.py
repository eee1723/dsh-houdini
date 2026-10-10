"""Offline provider timing retention and the real transcript consumer boundary."""
import importlib.util
import json
from pathlib import Path
from copy import deepcopy
import sys
import tempfile
from types import SimpleNamespace as Args
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("video_tutorial_timestamps", ROOT / "skills/houdini-video-tutorial/scripts/video_tutorial.py")
video = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video)


def sentence(identity, start, end, text, words):
    return {"sentence_id": identity, "sentence_end": True, "begin_time": start, "end_time": end,
            "text": text, "channel_id": 0, "speaker_id": 0, "words": words}


def word(start, end, text, punctuation=""):
    return {"begin_time": start, "end_time": end, "text": text, "punctuation": punctuation, "fixed": True}


class Response:
    status = 200
    headers = {}
    def __init__(self, value): self.value = value
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit): return json.dumps(self.value).encode("utf-8")


class TimestampTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dsh-asr-timestamps-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"source identity")
        self.work = self.root / "work"
        self.work.mkdir()
        self.audio = self.work / "audio-00000.wav"
        self.audio.write_bytes(b"prepared audio")
        self.item = {"id": "00000", "start": 20, "end": 25, "audio": self.audio.name, "sha256": video.sha(self.audio)}
        video.save(self.work / "manifest.json", {"schema": 1, "source": str(self.source),
            "source_sha256": video.sha(self.source), "duration": 30, "start": 20, "end": 25, "chunk": 5,
            "overlap": 0, "has_audio": True, "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
            "timestamp_basis": video.BASIS, "chunks": [self.item]})
        self.args = Args(work=str(self.work), model="qwen-audio-3.1-asr-flash", protocol="dashscope-asr",
            endpoint="https://maas.qianwenaiapi.com/api/v1/services/aigc/multimodal-generation/generation",
            allow_upload=True, max_chunks=1, retry_failed=False)
        self.sentences = [sentence(1, 200, 1200, "Houdini.", [word(200, 1200, "Houdini", ".")]),
                          sentence(2, 1500, 4200, "VEX wrangle.", [word(1500, 2200, "VEX"), word(2250, 4200, " wrangle", ".")])]
        self.text = "Houdini. VEX wrangle."
        self.body = {"output": {"text": self.text, "sentences": self.sentences, "sentence": self.sentences[-1]},
                     "usage": {"duration": 5, "input_tokens": 8, "output_tokens": 9, "total_tokens": 17},
                     "request_id": "provider-receipt"}

    def evidence(self, body=None):
        body = self.body if body is None else body
        return {"schema": 1, "protocol": "dashscope-asr", "raw_response": body, "usage": body["usage"],
                "timestamps": video.provider_timestamps(body, "dashscope-asr", body["output"]["text"])}

    def transcribe(self, body=None):
        evidence = self.evidence(body)
        return video.transcribe(self.args, sender=lambda *a: (self.text, "provider-receipt", evidence), get_key=lambda: "test-secret")

    def export(self):
        output = self.root / "export"
        video.export(Args(work=str(self.work), output=str(output)))
        return output, video.read(output / "transcript.json")

    def test_three_one_explicit_diarization_retains_all_sentence_result_and_complete_body(self):
        requests = []
        def open_request(request, timeout):
            requests.append((request, timeout))
            return Response(self.body)
        with patch.object(video.urllib.request, "build_opener", return_value=Args(open=open_request)):
            text, trace, evidence = video.post(b"prepared audio", self.args.model, "test-secret", self.args.endpoint,
                                               "dashscope-asr", {"speaker_diarization_enabled": True})
        self.assertEqual((text, trace), (self.text, "provider-receipt"))
        self.assertEqual(evidence["raw_response"], self.body)
        self.assertEqual(evidence["usage"]["total_tokens"], 17)
        self.assertEqual(evidence["timestamps"]["coverage"], "full")
        self.assertEqual(requests[0][1], 300)
        self.assertTrue(json.loads(requests[0][0].data)["parameters"]["speaker_diarization_enabled"])

    def test_three_one_default_does_not_enable_optional_diarization(self):
        requests = []
        def open_request(request, timeout):
            requests.append(request)
            return Response(self.body)
        with patch.object(video.urllib.request, "build_opener", return_value=Args(open=open_request)):
            video.post(b"prepared audio", self.args.model, "test-secret", self.args.endpoint, "dashscope-asr")
        self.assertNotIn("speaker_diarization_enabled", json.loads(requests[0].data)["parameters"])

    def test_explicit_three_one_options_preserve_false_and_inline_hotwords(self):
        requests = []
        def open_request(request, timeout):
            requests.append(request)
            return Response(self.body)
        options = {"speaker_diarization_enabled": False, "vocabulary": {"Houdini": 5, "VEX": 50}}
        with patch.object(video.urllib.request, "build_opener", return_value=Args(open=open_request)):
            video.post(b"prepared audio", self.args.model, "test-secret", self.args.endpoint, "dashscope-asr", options)
        self.assertEqual(json.loads(requests[0].data)["parameters"], {"format": "wav", "sample_rate": "16000", **options})
        self.assertFalse(options["speaker_diarization_enabled"])

    def test_three_zero_last_sentence_is_partial_without_fabricated_alignment(self):
        body = {"output": {"text": self.text, "sentence": self.sentences[-1]}}
        timing = video.provider_timestamps(body, "dashscope-asr", self.text)
        self.assertEqual(timing["coverage"], "partial")
        self.assertEqual(timing["text_coverage"], "partial")
        self.assertEqual(len(timing["sentences"]), 1)
        self.assertEqual(timing["sentences"][0]["start"], 1.5)
        self.assertTrue(any("last sentence" in item for item in timing["diagnostics"]))
        body["output"] = {"text": self.text, "output": {"sentence": self.sentences[-1]}}
        self.assertEqual(video.provider_timestamps(body, "dashscope-asr", self.text), timing)

    def test_normalized_or_polished_text_mismatch_remains_successful_and_diagnostic(self):
        self.body["output"]["text"] = "Houdini and VEX wrangle."
        self.text = self.body["output"]["text"]
        self.assertEqual(self.transcribe()["submitted"], 1)
        _, transcript = self.export()
        row = transcript["chunks"][0]
        self.assertEqual(row["text"], self.text)
        self.assertEqual(row["alignment"]["coverage"], "unverified")
        self.assertEqual(row["alignment"]["text_coverage"], "mismatch")
        self.assertEqual(row["alignment"]["sentences"][0]["text"], "Houdini.")

    def test_unfinalized_or_invalid_words_are_not_exported_but_original_body_is_retained(self):
        self.sentences[0]["words"][0]["fixed"] = False
        self.sentences[1]["words"].append(word(4300, 9000, "outside"))
        self.assertEqual(self.transcribe()["submitted"], 1)
        outcome = video.latest(self.work, self.item)[1]
        self.assertEqual(outcome["provider_evidence"]["raw_response"], self.body)
        _, transcript = self.export()
        rows = transcript["chunks"][0]["alignment"]["sentences"]
        self.assertEqual(rows[0]["words"], [])
        self.assertEqual(len(rows[1]["words"]), 2)
        self.assertTrue(transcript["chunks"][0]["alignment"]["diagnostics"])

    def test_export_offsets_and_real_receipt_reach_transcript_consumer(self):
        self.assertEqual(self.transcribe()["submitted"], 1)
        output, transcript = self.export()
        row = transcript["chunks"][0]
        self.assertEqual((row["start"], row["end"], row["text"]), (20, 25, self.text))
        aligned = row["alignment"]["sentences"]
        self.assertEqual((aligned[0]["start"], aligned[0]["end"]), (20.2, 21.2))
        self.assertEqual(aligned[1]["words"][1]["start"], 22.25)
        self.assertEqual(transcript["validation"]["timestamp_basis"], video.BASIS)
        self.assertEqual(transcript["validation"]["provider_timestamps"]["words"], 3)
        chunks = video.transcript_chunks(output / "transcript.json", video.sha(self.source))
        timing = video.timestamp_speech(chunks, 20, 22)
        self.assertEqual([item["id"] for item in timing], ["speech-00000-sentence-00000", "speech-00000-sentence-00001"])
        self.assertEqual(timing[0]["text"], "Houdini.")
        receipt = self.work / "outcome-00000-1.json"
        receipt.write_text(receipt.read_text() + " ", encoding="utf-8")
        with self.assertRaisesRegex(video.Failure, "changed"):
            video.transcript_chunks(output / "transcript.json", video.sha(self.source))

    def test_out_of_audio_timestamp_does_not_block_text_or_invent_clip(self):
        self.sentences[-1]["end_time"] = 8000
        self.transcribe()
        _, transcript = self.export()
        row = transcript["chunks"][0]
        self.assertEqual(row["text"], self.text)
        self.assertEqual(row["alignment"]["coverage"], "unverified")
        self.assertEqual(len(row["alignment"]["sentences"]), 1)
        self.assertTrue(any("outside prepared audio" in d for d in row["alignment"]["diagnostics"]))

    def test_timestamp_context_supports_real_sentence_reference_in_notes(self):
        self.transcribe()
        output, _ = self.export()
        frames = self.root / "frames"
        frames.mkdir()
        index = {"source_sha256": video.sha(self.source), "frames": [
            {"file": "frame.png", "sha256": "frame-hash", "actual_seconds": 22.0}]}
        with patch.object(video, "checked_frame_index", return_value=(index, "index-hash", None)):
            packet = video.build_context(frames, output / "transcript.json", 22, 24)
        self.assertEqual([row["id"] for row in packet["speech_timestamps"]], ["speech-00000-sentence-00001"])
        note = {"schema": 1, "context_sha256": "context-hash", "steps": [{"id": "term-check", "kind": "inference",
            "range_seconds": [22, 24], "intent": "Identify the named wrangle", "speech_ids": ["speech-00000-sentence-00001"],
            "visual": [], "inferences": ["The spoken name is VEX wrangle"], "conflicts": [], "unknowns": ["Parameter is not visible"],
            "evidence_state": "speech_only", "reconstruction_readiness": "needs_more_evidence"}]}
        self.assertEqual(video.validate_notes(note, packet, "context-hash")["structural_validation"], "passed")
        note["steps"][0]["speech_ids"] = ["speech-00000-sentence-00000"]
        with self.assertRaisesRegex(video.Failure, "Missing/out-of-range"):
            video.validate_notes(note, packet, "context-hash")

    def test_legacy_transcript_remains_chunk_only_and_can_resume_tuple_two(self):
        video.transcribe(self.args, sender=lambda *a: (self.text, "trace"), get_key=lambda: "test-secret")
        output, transcript = self.export()
        self.assertNotIn("alignment", transcript["chunks"][0])
        chunks = video.transcript_chunks(output / "transcript.json", video.sha(self.source))
        self.assertEqual(video.timestamp_speech(chunks), [])
        self.assertEqual(chunks[0]["text"], self.text)

    def test_module_and_page_reads_expose_real_sentence_times_in_the_selected_range(self):
        self.transcribe()
        output, _ = self.export()
        chunks = video.transcript_chunks(output / "transcript.json", video.sha(self.source))
        index_path = self.root / "index.json"
        module = {"id": "wrangle", "title": "Wrangle", "ranges": [[22, 24]],
                  "purpose": "Identify the spoken VEX operation", "inputs": ["source audio"],
                  "outputs": ["operation name"], "depends_on": [], "questions": [], "unknowns": [], "evidence": []}
        data = {"source": video.file_reference(self.source), "transcript": video.file_reference(output / "transcript.json"),
                "modules": [module]}
        video.save(index_path, data)
        args = Args(index=str(index_path), module="wrangle", max_chars=40000, section="speech", offset=0, limit=1)
        with patch.object(video, "checked_index", return_value=(data, chunks, {"wrangle": []})):
            result = video.read_index(args)
        self.assertEqual(result["items"][0]["text"], self.text)
        self.assertNotIn("sentences", result["items"][0]["alignment"])
        self.assertEqual([row["text"] for row in result["speech_timestamps"]], ["VEX wrangle."])
        self.assertEqual(result["speech_timestamps"][0]["words"][1]["start"], 22.25)
        with patch.object(video, "index_sources", return_value=(data, chunks)):
            page = video.read_transcript(args)
        self.assertEqual([row["start"] for row in page["speech_timestamps"]], [20.2, 21.5])

    def test_editable_export_cannot_invent_sentence_word_or_chunk_timing_with_a_real_receipt(self):
        self.transcribe()
        output, transcript = self.export()
        variants = []
        sentence_edit = deepcopy(transcript)
        sentence_edit["chunks"][0]["alignment"]["sentences"][0]["start"] = 20.8
        variants.append(sentence_edit)
        word_edit = deepcopy(transcript)
        word_edit["chunks"][0]["alignment"]["sentences"][0]["words"][0]["start"] = 20.9
        variants.append(word_edit)
        text_edit = deepcopy(transcript)
        text_edit["chunks"][0]["text"] = "Edited source words"
        variants.append(text_edit)
        offset_edit = deepcopy(transcript)
        offset_edit["chunks"][0]["start"] = 19
        variants.append(offset_edit)
        for index, variant in enumerate(variants):
            with self.subTest(index=index):
                path = output / f"edited-{index}.json"
                video.save(path, variant)
                with self.assertRaises(video.Failure):
                    video.transcript_chunks(path, video.sha(self.source))

    def test_receipt_canonical_timestamp_cache_cannot_override_raw_provider_offsets(self):
        self.transcribe()
        receipt_path = self.work / "outcome-00000-1.json"
        receipt = video.read(receipt_path)
        receipt["provider_evidence"]["timestamps"]["sentences"][0]["start"] = 0.8
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        output, _ = self.export()
        with self.assertRaisesRegex(video.Failure, "differs from its raw provider receipt"):
            video.transcript_chunks(output / "transcript.json", video.sha(self.source))

    def test_context_notes_can_reference_final_provider_word_without_repeating_words_in_chunk(self):
        self.transcribe()
        output, _ = self.export()
        frames = self.root / "frames"
        frames.mkdir()
        frame_index = {"source_sha256": video.sha(self.source), "frames": [
            {"file": "frame.png", "sha256": "frame-hash", "actual_seconds": 22.5}]}
        with patch.object(video, "checked_frame_index", return_value=(frame_index, "frame-index-hash", None)):
            packet = video.build_context(frames, output / "transcript.json", 22, 24)
        self.assertNotIn("sentences", packet["speech"][0]["alignment"])
        words = packet["speech_timestamps"][0]["words"]
        identity = words[1]["id"]
        self.assertEqual((words[1]["start"], words[1]["end"]), (22.25, 24.2))
        note = {"schema": 1, "context_sha256": "context-hash", "steps": [{"id": "term-check", "kind": "inference",
            "range_seconds": [22.25, 24], "intent": "Locate the spoken wrangle", "speech_ids": [identity],
            "visual": [], "inferences": ["The provider recognized wrangle"], "conflicts": [], "unknowns": ["Actual spelling not visually checked"],
            "evidence_state": "speech_only", "reconstruction_readiness": "needs_more_evidence"}]}
        self.assertEqual(video.validate_notes(note, packet, "context-hash")["structural_validation"], "passed")

    def test_credential_echo_in_nested_success_body_is_rejected_before_retention(self):
        self.body["usage"]["untrusted"] = {"echo": "test-secret"}
        with patch.object(video.urllib.request, "build_opener", return_value=Args(open=lambda *a, **kw: Response(self.body))):
            with self.assertRaisesRegex(video.Failure, "Credential echoed"):
                video.post(b"prepared audio", self.args.model, "test-secret", self.args.endpoint, "dashscope-asr")

    def test_hotword_options_are_real_protocol_fields_and_fixed_task_identity(self):
        options = {"vocabulary": {"Houdini": 5}}
        video.validate_asr_options(options, self.args.model, "dashscope-asr")
        actual = video.config(self.work, self.args.model, self.args.endpoint, "dashscope-asr", options)
        self.assertEqual(video.config(self.work), actual)
        with self.assertRaisesRegex(video.Failure, "configuration/source changed"):
            video.config(self.work, self.args.model, self.args.endpoint, "dashscope-asr", {"vocabulary": {"Houdini": 50}})
        for value in ({"api_key": "bad"}, {"vocabulary": {"Houdini": True}}, {"vocabulary": {"Houdini": 6}},
                      {"speaker_diarization_enabled": 1}):
            with self.subTest(value=value), self.assertRaises(video.Failure):
                video.validate_asr_options(value, self.args.model, "dashscope-asr")


if __name__ == "__main__":
    unittest.main()
