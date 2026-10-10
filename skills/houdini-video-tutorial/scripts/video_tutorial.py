"""Local tutorial media/evidence and explicitly authorized compatible ASR. Python 3.11+, no HOM."""
import argparse
import base64
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from contextvars import ContextVar
from fractions import Fraction
from functools import partial, wraps
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import struct
import sys
from threading import Event, Lock
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ENDPOINT = "https://api.siliconflow.cn/v1/audio/transcriptions"
PACKAGE = Path(__file__).resolve().parents[3]
BASIS = "audio_chunk_bounds_not_sentence_or_word_alignment"
_READ_VALIDATION = ContextVar("video_read_validation", default=None)


class Failure(Exception):
    pass


def check(condition, message):
    if not condition:
        raise Failure(message)


def media_executable(name):
    """The default is the versioned private runtime, never a global PATH tool."""
    suffix = ".exe" if os.name == "nt" else ""
    return str(PACKAGE / "runtime" / "video" / "ffmpeg" / "bin" / (name + suffix))


def file_signature(path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validated_read(function):
    """Deduplicate one command's evidence reads; never trust a previous command."""
    @wraps(function)
    def run(*args, **kwargs):
        if _READ_VALIDATION.get() is not None:
            return function(*args, **kwargs)
        state = {"hashes": {}, "contexts": {}}
        token = _READ_VALIDATION.set(state)
        try:
            result = function(*args, **kwargs)
            # Metadata can be preserved across edits (Windows ctime is creation
            # time). Rehash each dependency once before returning a receipt;
            # repeated module references still share their initial validation.
            for path, (signature, digest) in state["hashes"].items():
                check(file_signature(path) == signature, "Evidence file changed during validation; retry the read")
                current = file_digest(path)  # Deliberately bypass the command cache.
                check(file_signature(path) == signature and current == digest,
                      "Evidence file changed during validation; retry the read")
            return result
        finally:
            _READ_VALIDATION.reset(token)
    return run


def sha(path):
    path = Path(path).absolute()
    state = _READ_VALIDATION.get()
    if state is None:
        return file_digest(path)
    signature = file_signature(path)
    cached = state["hashes"].get(path)
    if cached is not None:
        check(signature == cached[0], "Evidence file changed during validation; retry the read")
        return cached[1]
    digest = file_digest(path)
    check(file_signature(path) == signature, "Evidence file changed while hashing; retry the read")
    state["hashes"][path] = (signature, digest)
    return digest


def text_sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def read(path):
    check(not path.is_symlink(), "Symlink artifact rejected")
    return json.loads(path.read_text(encoding="utf-8"))


def directory(value, new=False):
    path = Path(value)
    check(path.is_absolute(), "Use an absolute task directory")
    resolved = path.resolve()
    check(not resolved.is_relative_to(PACKAGE), "Task artifacts must stay outside the plugin")
    check(resolved != Path(resolved.anchor), "A filesystem root is not a task directory")
    if new:
        resolved.mkdir(parents=True, exist_ok=False)
    else:
        check(resolved.is_dir(), "Task directory missing")
    return resolved


@contextmanager
def lock(work):
    path = work / ".lock"
    try:
        with path.open("x", encoding="ascii") as stream:
            stream.write(str(os.getpid()))
    except FileExistsError:
        raise Failure("Task locked; verify prior process before manually resolving stale lock") from None
    try:
        yield
    finally:
        path.unlink()


def run(command, *, stderr=False):
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=300)
    except FileNotFoundError:
        raise Failure(f"Executable unavailable: {Path(command[0]).name}; managed installs: repair the current version in "
                      "Version & Updates. Source checkout: run tools/prepare-video-runtime.py for private media dependencies, "
                      "or pass the explicit executable path") from None
    except subprocess.TimeoutExpired:
        raise Failure(f"{Path(command[0]).name} exceeded 300 seconds; inspect the media and narrow the requested operation") from None
    check(result.returncode == 0,
          f"{Path(command[0]).name} failed (exit {result.returncode}): "
          + result.stderr.decode("utf-8", errors="replace")[-2000:].strip())
    return result.stderr if stderr else result.stdout


def media_info(path, executable):
    data = json.loads(run([executable, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]))
    duration = float(data["format"]["duration"])
    check(math.isfinite(duration) and duration > 0, "Unknown/invalid media duration")
    streams = [{k: item[k] for k in ("index", "codec_type", "codec_name", "width", "height", "r_frame_rate", "start_time", "duration")
                if k in item} for item in data["streams"]]
    return {"duration": duration, "start_time": data["format"].get("start_time"), "streams": streams}


def probe(video, executable):
    info = media_info(video, executable)
    streams = info["streams"]
    check(any(item.get("codec_type") == "video" for item in streams), "Video stream required")
    return info["duration"], streams


def ingest(args):
    """Snapshot explicit or unambiguous local tracks; no download or cloud calls."""
    source_dir = getattr(args, "input", None)
    video_path, audio_path = getattr(args, "video", None), getattr(args, "audio", None)
    check(bool(source_dir) != bool(video_path), "Use --input directory or --video file")
    check(not source_dir or not audio_path, "Use --video with --audio for an explicit pair")
    ignored, candidates = [], []
    if source_dir:
        folder = Path(source_dir)
        check(folder.is_absolute() and folder.is_dir(), "Absolute input directory required")
        paths = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() != ".aria2"), key=lambda p: p.name)
    else:
        paths = [Path(video_path)] + ([Path(audio_path)] if audio_path else [])
    for path in paths:
        check(path.is_absolute() and path.is_file(), f"Local media file missing: {path}")
        path = path.resolve()
        signature = file_signature(path)
        try:
            info = media_info(path, args.ffprobe)
        except Failure as error:
            check(file_signature(path) == signature,
                  f"Source is changing (download may still be running): {path}; wait for completion, then ingest again")
            if not source_dir:
                raise
            marker = path.with_name(path.name + ".aria2")
            check(not marker.exists(),
                  f"Download-marked source is not readable yet: {path}; wait for completion or select --video/--audio explicitly")
            ignored.append({"path": str(path), "reason": str(error)})
            continue
        check(file_signature(path) == signature,
              f"Source is changing (download may still be running): {path}; wait for completion, then ingest again")
        types = {s.get("codec_type") for s in info["streams"]}
        if "video" not in types and "audio" not in types:
            ignored.append({"path": str(path), "reason": "No audio/video streams"})
            continue
        candidates.append({"path": path, "signature": signature, "info": info, "types": types})
    if source_dir:
        videos = [c for c in candidates if "video" in c["types"]]
        audios = [c for c in candidates if "audio" in c["types"] and "video" not in c["types"]]
        listing = "; ".join(f"{c['path'].name} ({'/'.join(sorted(c['types']))})" for c in candidates) or "none"
        check(len(videos) == 1 and len(audios) <= 1,
              f"No unique media pairing in directory: {listing}. Pass --video and optional --audio explicitly")
        selected_video = videos[0]
        check(not audios or "audio" not in selected_video["types"],
              f"Video already has audio and a separate audio candidate exists: {listing}. Choose explicit --video/--audio")
        selected_audio = audios[0] if audios else None
    else:
        selected_video = next((c for c in candidates if c["path"] == Path(video_path).resolve()), None)
        selected_audio = next((c for c in candidates if audio_path and c["path"] == Path(audio_path).resolve()), None)
        check(selected_video is not None and "video" in selected_video["types"], "--video must contain a video stream")
        check(not audio_path or selected_audio is not None and "audio" in selected_audio["types"],
              "--audio must contain an audio stream")
        check(not selected_audio or selected_audio["path"] != selected_video["path"],
              "Separate --video and --audio must name different files; omit --audio for an embedded track")
    selected = [selected_video] + ([selected_audio] if selected_audio else [])
    sources = []
    for index, item in enumerate(selected):
        digest = sha(item["path"])
        check(file_signature(item["path"]) == item["signature"],
              f"Source is changing (download may still be running): {item['path']}; wait for completion, then ingest again")
        marker = item["path"].with_name(item["path"].name + ".aria2")
        sources.append({"role": "video" if index == 0 else "audio", "path": str(item["path"]),
                        "sha256": digest, "bytes": item["signature"][2], **item["info"],
                        "download_marker": str(marker) if marker.exists() else None})
    output = directory(args.output, new=True)
    partial, destination = output / "media.partial.mp4", output / "media.mp4"
    command = [args.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-xerror",
               "-err_detect", "explode", "-i", str(selected_video["path"])]
    if selected_audio:
        command += ["-err_detect", "explode", "-i", str(selected_audio["path"])]
    command += ["-map", "0:v:0", "-map", "1:a:0" if selected_audio else "0:a:0?",
                "-c", "copy", "-map_metadata", "-1", "-movflags", "+faststart", str(partial)]
    try:
        run(command)
        result = media_info(partial, args.ffprobe)
        for item, source in zip(selected, sources):
            check(file_signature(item["path"]) == item["signature"] and sha(item["path"]) == source["sha256"],
                  f"Source changed while importing: {item['path']}; download may still be running; no completed snapshot was published")
        # A remux can exit successfully on an incomplete tail. Compare each selected
        # stream's declared span, allowing one encoded frame/packet at the boundary.
        duration_checks = []
        for kind, item in (("video", selected_video), ("audio", selected_audio or selected_video)):
            before = next((s for s in item["info"]["streams"] if s.get("codec_type") == kind), None)
            if before is None:
                continue
            after = next((s for s in result["streams"] if s.get("codec_type") == kind), None)
            check(after is not None, f"Imported media lost the {kind} stream")
            source_duration, output_duration = before.get("duration"), after.get("duration")
            basis = "stream"
            # For a single track starting at zero, the container duration is an
            # available declared bound when e.g. Matroska omits stream.duration.
            if source_duration in (None, "N/A") and item["types"] == {kind} and float(item["info"]["start_time"] or 0) == 0:
                source_duration, basis = item["info"]["duration"], "single_track_container"
                output_duration = output_duration or result["duration"]
            if source_duration not in (None, "N/A") and output_duration not in (None, "N/A"):
                frame_rate = before.get("r_frame_rate", "0/1")
                rate = Fraction(frame_rate) if frame_rate not in ("0/0", "N/A") else Fraction(0)
                tolerance = max(.1, float(1 / rate) if rate > 0 else .1)
                check(float(output_duration) + tolerance >= float(source_duration),
                      f"Imported {kind} ends before its declared source duration; source may be incomplete. Wait for the download to finish")
                duration_checks.append({"stream": kind, "status": "checked", "basis": basis,
                                        "source_seconds": float(source_duration), "output_seconds": float(output_duration)})
            else:
                duration_checks.append({"stream": kind, "status": "unverified", "reason": "Comparable declared stream duration unavailable"})
        media_hash = sha(partial)
        partial.rename(destination)
        manifest = {"schema": 1, "kind": "tutorial_media_ingest", "sources": sources,
                    "media": {"path": str(destination), "sha256": media_hash, **result},
                    "operation": "stream_copy", "timing": "Input starts normalized by FFmpeg; no content-based synchronization",
                    "integrity": {"packet_read": "ffmpeg_error_fatal", "duration_checks": duration_checks, "full_decode": "not_performed"},
                    "ignored": ignored, "semantic_inspection": "not_performed"}
        save(output / "source-manifest.json", manifest)
    except Failure as error:
        raise Failure(f"{error}. Incomplete import retained at {output}; original files were not modified") from None
    return {"status": "imported", "video": str(destination), "source_manifest": str(output / "source-manifest.json"),
            "source_sha256": media_hash, "duration": result["duration"],
            "has_audio": any(s.get("codec_type") == "audio" for s in result["streams"]),
            "sources": sources, "ignored": ignored,
            "note": "Stable stream-copy snapshot; a leftover download marker does not by itself establish incompleteness. Use video with prepare/scan."}


def ranges(start, duration, total, chunk, overlap):
    check(all(math.isfinite(v) for v in (start, duration, total, chunk, overlap)), "Non-finite range")
    check(0 <= start < total and duration > 0 and 1 <= chunk <= 120 and 0 <= overlap < chunk,
          "Invalid sample/chunk range")
    end = min(total, start + duration)
    result = []
    while start < end:
        stop = min(start + chunk, end)
        result.append((start, stop))
        check(len(result) <= 10000, "Too many chunks; increase stride or reduce scope")
        if stop >= end:
            break
        start = stop - overlap
    return result


def prepare(args):
    video = Path(args.video)
    check(video.is_absolute() and video.is_file(), "Absolute local video path required; URL download not supported")
    video = video.resolve()
    total, streams = probe(video, args.ffprobe)
    cuts = ranges(args.start, args.duration, total, args.chunk, args.overlap)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    source_hash = sha(video)
    work = directory(args.output, new=True)
    chunks = []
    for index, (start, end) in enumerate(cuts if has_audio else []):
        name = f"audio-{index:05d}.wav"
        audio = work / name
        run([args.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-ss", str(start),
             "-i", str(video), "-t", str(end - start), "-map", "0:a:0", "-vn", "-ac", "1", "-ar",
             "16000", "-c:a", "pcm_s16le", str(audio)])
        check(audio.stat().st_size < 50_000_000, "Audio exceeds upload bound")
        chunks.append({"id": f"{index:05d}", "start": start, "end": end, "audio": name, "sha256": sha(audio)})
    check(sha(video) == source_hash, "Source changed during preparation")
    save(work / "manifest.json", {"schema": 1, "source": str(video), "source_sha256": source_hash,
         "duration": total, "streams": streams, "has_audio": has_audio, "start": cuts[0][0], "end": cuts[-1][1],
         "chunk": args.chunk, "overlap": args.overlap, "timestamp_basis": BASIS, "chunks": chunks})
    return {"status": "prepared", "chunks": len(chunks), "has_audio": has_audio, "work": str(work)}


def load(work):
    manifest = read(work / "manifest.json")
    check(manifest["schema"] == 1 and manifest["timestamp_basis"] == BASIS, "Unsupported manifest")
    source = Path(manifest["source"])
    check(source.is_absolute() and source.is_file() and sha(source) == manifest["source_sha256"], "Source hash mismatch")
    cuts = ranges(manifest["start"], manifest["end"] - manifest["start"], manifest["duration"],
                  manifest["chunk"], manifest["overlap"])
    check(type(manifest["has_audio"]) is bool and cuts[-1][1] == manifest["end"], "Invalid manifest range/audio flag")
    expected = cuts if manifest["has_audio"] else []
    check(len(expected) == len(manifest["chunks"]), "Chunk plan mismatch")
    for index, ((start, end), item) in enumerate(zip(expected, manifest["chunks"])):
        check(item["id"] == f"{index:05d}" and item["audio"] == f"audio-{index:05d}.wav"
              and item["start"] == start and item["end"] == end, "Chunk bounds/identity mismatch")
        audio = work / item["audio"]
        check(not audio.is_symlink() and sha(audio) == item["sha256"], "Audio hash mismatch")
        check(audio.stat().st_size < 50_000_000, "Audio exceeds upload bound")
    return manifest


def asr_endpoint(value, protocol="openai-transcriptions"):
    check(isinstance(value, str) and value and not any(c.isspace() for c in value), "ASR endpoint must be an absolute HTTPS URL")
    try:
        parsed = urllib.parse.urlsplit(value)
        parsed.port  # Validate the port before recording any possibly billed attempt.
    except ValueError:
        raise Failure("ASR endpoint contains an invalid host or port") from None
    check(parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
          and (parsed.scheme == "https" or parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")),
          "ASR endpoint requires HTTPS (HTTP only for local loopback), without credentials, query or fragment")
    suffix = {"openai-transcriptions": "/audio/transcriptions", "qwen-chat-asr": "/chat/completions",
              "dashscope-asr": "/api/v1/services/aigc/multimodal-generation/generation"}.get(protocol)
    check(suffix is not None, "Unsupported ASR protocol")
    check(parsed.path.rstrip("/").endswith(suffix), f"ASR endpoint must end in {suffix}")
    return value


def config(work, model=None, endpoint=None, protocol=None, request_options=None):
    path = work / "asr-config.json"
    expected = {"endpoint": endpoint or ENDPOINT, "model": model, "manifest_sha256": sha(work / "manifest.json")}
    if protocol and protocol != "openai-transcriptions":
        expected["protocol"] = protocol
    if request_options:
        expected["request_options"] = request_options
    if path.exists():
        actual = read(path)
        if model is None:
            expected["model"] = actual["model"]
            if "protocol" in actual:
                expected["protocol"] = actual["protocol"]
            if "request_options" in actual:
                expected["request_options"] = actual["request_options"]
            if endpoint is None:
                expected["endpoint"] = asr_endpoint(actual["endpoint"], actual.get("protocol", "openai-transcriptions"))
        check(actual == expected, "ASR configuration/source changed; do not mix models or evidence")
        return actual
    if model is not None:
        save(path, expected)
        return expected
    return None


def latest(work, item):
    attempts = list(work.glob(f"attempt-{item['id']}-*.json"))
    for path in attempts:
        check(re.fullmatch(rf"attempt-{re.escape(item['id'])}-[1-9][0-9]*\.json", path.name),
              "Attempt sequence damaged")
    attempts.sort(key=lambda path: int(path.stem.rsplit("-", 1)[1]))
    expected_outcomes = {f"outcome-{item['id']}-{i}.json" for i in range(1, len(attempts) + 1)}
    check(all(path.name in expected_outcomes for path in work.glob(f"outcome-{item['id']}-*.json")), "Orphan outcome")
    outcome = None
    for index, path in enumerate(attempts, 1):
        check(path.name == f"attempt-{item['id']}-{index}.json", "Attempt sequence damaged")
        attempt = read(path)
        check(attempt == {"id": item["id"], "attempt": index, "audio_sha256": item["sha256"]}, "Attempt mismatch")
        outcome_path = work / f"outcome-{item['id']}-{index}.json"
        outcome = read(outcome_path) if outcome_path.exists() else {"status": "unknown"}
        check(outcome.get("status") in ("success", "unknown", "http_error"), "Invalid outcome state")
        if outcome.get("status") == "success":
            check(index == len(attempts), "Unexpected retry after success")
            check(isinstance(outcome.get("text"), str) and text_sha(outcome["text"]) == outcome["text_sha256"],
                  "Transcript hash mismatch")
            check(outcome["audio_sha256"] == item["sha256"], "Response audio mismatch")
    return len(attempts), outcome


def key_from_environment(name="SILICONFLOW_API_KEY"):
    check(isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name), "Invalid credential environment variable name")
    key = os.environ.get(name, "").strip()
    if not key and os.name == "nt" and name == "SILICONFLOW_API_KEY":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as handle:
                key = winreg.QueryValueEx(handle, "SILICONFLOW_API_KEY")[0].strip()
        except FileNotFoundError:
            pass
    check(bool(key), f"{name} missing; configure the credential through DSH model settings or this environment variable; do not put keys in command arguments")
    check(not any(c in key for c in "\r\n"), "Credential contains invalid line breaks")
    return key


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def timing_text(value):
    """Ignore only whitespace/case when checking coverage; never align edited text."""
    return re.sub(r"\s+", "", value).casefold()


def provider_timestamps(data, protocol, text):
    """Retain final native offsets without mistaking a current sentence for all audio."""
    result = {"basis": "provider_audio_offset_milliseconds", "unit": "seconds", "coverage": "none",
              "text_coverage": "unverified", "sentences": [], "diagnostics": []}
    if protocol != "dashscope-asr":
        result["diagnostics"].append("This protocol has no verified sentence/word timestamp adapter")
        return result
    output = data.get("output", {})
    details = output.get("output", output)
    values = details.get("sentences", output.get("sentences"))
    collection = isinstance(values, list)
    if not collection:
        values = [details["sentence"]] if isinstance(details.get("sentence"), dict) else []
    previous = -1
    invalid_sentences = False
    for index, sentence in enumerate(values):
        if not isinstance(sentence, dict):
            invalid_sentences = True
            result["diagnostics"].append(f"Sentence {index} is not an object")
            continue
        begin, end = sentence.get("begin_time"), sentence.get("end_time")
        if (sentence.get("sentence_end") is not True or type(begin) not in (int, float)
                or type(end) not in (int, float) or not all(math.isfinite(t) for t in (begin, end))
                or not 0 <= begin < end or begin < previous or not isinstance(sentence.get("text"), str)):
            invalid_sentences = True
            result["diagnostics"].append(f"Sentence {index} has incomplete/invalid/nonchronological timing")
            continue
        previous = begin
        row = {"provider_sentence_id": sentence.get("sentence_id"), "speaker_id": sentence.get("speaker_id"),
               "channel_id": sentence.get("channel_id"), "start": begin / 1000, "end": end / 1000,
               "text": sentence["text"], "words": []}
        words = sentence.get("words", [])
        if not isinstance(words, list):
            result["diagnostics"].append(f"Sentence {index} has no valid word array")
            words = []
        word_previous = begin
        for word_index, word in enumerate(words):
            if not isinstance(word, dict):
                result["diagnostics"].append(f"Sentence {index} word {word_index} is not an object")
                continue
            left, right = word.get("begin_time"), word.get("end_time")
            if (word.get("fixed") is not True or type(left) not in (int, float)
                    or type(right) not in (int, float) or not all(math.isfinite(t) for t in (left, right))
                    or not begin <= left < right <= end or left < word_previous
                    or not isinstance(word.get("text"), str) or not isinstance(word.get("punctuation", ""), str)):
                result["diagnostics"].append(f"Sentence {index} word {word_index} has unfinalized/invalid timing")
                continue
            word_previous = left
            row["words"].append({"start": left / 1000, "end": right / 1000, "text": word["text"],
                                 "punctuation": word.get("punctuation", ""), "fixed": True,
                                 "speaker_id": word.get("speaker_id")})
        row["word_text_coverage"] = ("full" if row["words"] and timing_text("".join(
            word["text"] + word["punctuation"] for word in row["words"])) == timing_text(row["text"])
            else "mismatch" if row["words"] else "none")
        if row["word_text_coverage"] == "mismatch":
            result["diagnostics"].append(f"Sentence {index} words differ from its text; do not align normalized text to these words")
        result["sentences"].append(row)
    if not result["sentences"]:
        result["coverage"] = "unverified" if values else "none"
        return result
    joined = timing_text("".join(row["text"] for row in result["sentences"]))
    full = timing_text(text)
    result["text_coverage"] = "full" if joined == full else "partial" if joined and joined in full else "mismatch"
    result["coverage"] = ("full" if result["text_coverage"] == "full" and not invalid_sentences
        else "partial" if result["text_coverage"] == "partial" else "unverified")
    if not collection and result["text_coverage"] != "full":
        result["diagnostics"].append("Only the current/last sentence was returned; its times do not cover the full transcript")
    if result["text_coverage"] == "mismatch":
        result["diagnostics"].append("Sentence text differs from the accumulated transcript; preserve both without invented alignment")
    return result


def validate_asr_options(value, model, protocol):
    check(isinstance(value, dict) and not set(value) - {"vocabulary", "speaker_diarization_enabled"},
          "ASR options support only vocabulary and speaker_diarization_enabled")
    check(not value or protocol == "dashscope-asr", "ASR options require the native DashScope protocol")
    if "vocabulary" in value:
        words = value["vocabulary"]
        check(isinstance(words, dict) and len(words) <= 2000 and all(
            isinstance(word, str) and bool(word.strip()) and type(weight) is int and weight in (1, 2, 3, 4, 5, 50)
            for word, weight in words.items()), "Vocabulary must contain at most 2000 words with weight 1..5 or 50")
        check(sum(weight == 50 for weight in words.values()) <= 50, "At most 50 super hotwords with weight 50 are supported")
    if "speaker_diarization_enabled" in value:
        check(type(value["speaker_diarization_enabled"]) is bool and model == "qwen-audio-3.1-asr-flash",
              "Speaker diarization requires qwen-audio-3.1-asr-flash and a boolean value")
    return value


def post(audio, model, key, endpoint=ENDPOINT, protocol="openai-transcriptions", request_options=None):
    """Upload the immutable, manifest-checked bytes supplied by transcribe."""
    check(isinstance(audio, bytes), "ASR upload requires prepared audio bytes, not a path")
    request_options = validate_asr_options({} if request_options is None else request_options, model, protocol)
    headers = {"Authorization": f"Bearer {key}"}
    if protocol in ("qwen-chat-asr", "dashscope-asr"):
        encoded = base64.b64encode(audio).decode("ascii")
        check(len(encoded) <= 10_000_000, "Qwen ASR Base64 audio exceeds 10 MB; prepare smaller chunks")
        messages = [{"role": "user", "content": [{"type": "input_audio",
                    "input_audio": {"data": "data:audio/wav;base64," + encoded}}]}]
        if protocol == "dashscope-asr":
            payload = {"model": model, "input": {"messages": messages},
                       "parameters": {"format": "wav", "sample_rate": "16000"}}
            payload["parameters"].update(request_options)
            headers["X-DashScope-SSE"] = "disable"
        else:
            payload = {"model": model, "messages": messages, "stream": False,
                       "asr_options": {"enable_itn": False}}
        body = json.dumps(payload).encode("utf-8")
        content_type = "application/json"
    else:
        boundary = "dsh" + uuid.uuid4().hex
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model}\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\n"
                "Content-Type: audio/wav\r\n\r\n").encode()
        body = head + audio + f"\r\n--{boundary}--\r\n".encode()
        content_type = f"multipart/form-data; boundary={boundary}"
    headers["Content-Type"] = content_type
    request = urllib.request.Request(asr_endpoint(endpoint, protocol), data=body, headers=headers, method="POST")
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=300) as response:
        payload = response.read(2_000_001)
        check(len(payload) <= 2_000_000, "ASR response too large")
        data = json.loads(payload)
        check(response.status == 200 and isinstance(data, dict), "Invalid ASR response")
        if protocol == "qwen-chat-asr":
            choices = data.get("choices")
            check(isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict)
                  and choices[0].get("finish_reason") == "stop" and isinstance(choices[0].get("message"), dict),
                  "Qwen ASR response incomplete or invalid")
            text = choices[0]["message"].get("content")
        elif protocol == "dashscope-asr":
            output = data.get("output")
            check(isinstance(output, dict), "DashScope ASR response incomplete or invalid")
            # The HTTP reference uses output.sentence; the Qianwen platform
            # documents output.output.sentence. output.text is the accumulated
            # full transcript in both; a current sentence cannot replace it.
            details = output.get("output", output)
            check(isinstance(details, dict), "DashScope ASR response incomplete or invalid")
            sentence = details.get("sentence")
            check(not isinstance(sentence, dict) or sentence.get("sentence_end") is not False,
                  "DashScope ASR response incomplete or invalid")
            text = output.get("text")
            check(isinstance(text, str), "DashScope ASR response lacks the complete transcript")
        else:
            text = data.get("text")
        check(isinstance(text, str), "Invalid ASR response text")
        # Only a validated successful body is retained; never response headers or
        # provider failure bodies. A credential echo in any field rejects it.
        trace = response.headers.get("x-request-id") or response.headers.get("x-siliconcloud-trace-id")
        if protocol == "dashscope-asr" and not trace:
            trace = data.get("request_id")
        evidence = {"schema": 1, "protocol": protocol, "raw_response": data,
                    "usage": data.get("usage") if isinstance(data.get("usage"), dict) else None,
                    "timestamps": provider_timestamps(data, protocol, text)}
        check(not key or key not in json.dumps([text, trace, evidence], ensure_ascii=False, allow_nan=False),
              "Credential echoed in response; response rejected")
        return text, trace, evidence


def concurrency_failure(error):
    """Only overload/server failures and actual transport loss can lower concurrency."""
    if isinstance(error, urllib.error.HTTPError):
        return error.code == 429 or 500 <= error.code <= 599
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        return False
    if isinstance(reason, socket.gaierror):
        return reason.errno == socket.EAI_AGAIN
    return isinstance(reason, (TimeoutError, ConnectionError, http.client.IncompleteRead))


def transcribe(args, sender=None, get_key=None):
    check(args.allow_upload, "Cloud upload requires explicit user authorization and --allow-upload")
    check(re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", args.model), "Invalid model identifier")
    protocol = getattr(args, "protocol", "openai-transcriptions")
    endpoint = asr_endpoint(getattr(args, "endpoint", ENDPOINT), protocol)
    options_file = getattr(args, "asr_options_file", None)
    request_options = None
    if options_file is not None:
        path = Path(options_file)
        check(path.is_absolute() and path.is_file() and not path.is_symlink(), "Absolute ASR options JSON file required")
        check(path.stat().st_size <= 1_000_000, "ASR options file exceeds 1 MB")
        request_options = validate_asr_options(read(path), args.model, protocol)
    key_env = getattr(args, "key_env", "SILICONFLOW_API_KEY")
    check(isinstance(key_env, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key_env), "Invalid credential environment variable name")
    sender = sender or (lambda audio, model, key: post(audio, model, key, endpoint, protocol, request_options))
    get_key = get_key or (lambda: key_from_environment(key_env))
    check(type(args.max_chunks) is int and 1 <= args.max_chunks <= 100, "max-chunks must be 1..100")
    concurrency = getattr(args, "concurrency", 64)
    check(type(concurrency) is int and 1 <= concurrency <= 64, "concurrency must be 1..64")
    requests_per_second = getattr(args, "requests_per_second", 8)
    check(requests_per_second is None or type(requests_per_second) in (int, float)
          and math.isfinite(requests_per_second) and 0 < requests_per_second <= 100,
          "requests-per-second must be greater than 0 and at most 100")
    retry_budget = getattr(args, "max_retries", None)
    if retry_budget is None:
        retry_budget = 1 if args.retry_failed else 0
    check(type(retry_budget) is int and 0 <= retry_budget <= 100, "max-retries must be 0..100")
    check(args.retry_failed or retry_budget == 0, "A retry budget requires explicit --retry-failed authorization")
    requested = getattr(args, "chunks", None)
    check(requested is None or isinstance(requested, list) and requested
          and all(isinstance(value, str) for value in requested), "chunks must be a nonempty list of chunk IDs")
    check(requested is None or len(set(requested)) == len(requested), "Duplicate chunk IDs")
    work = directory(args.work)
    with lock(work):
        manifest = load(work)
        check(manifest["has_audio"], "No audio stream; use visual-only analysis")
        identities = {item["id"] for item in manifest["chunks"]}
        check(requested is None or set(requested) <= identities, "Unknown chunk ID")
        selected = identities if requested is None else set(requested)
        states = [(item, *latest(work, item)) for item in manifest["chunks"]]
        check(not any(count for _, count, _ in states) or (work / "asr-config.json").is_file(),
              "Missing ASR config for existing attempts; restore the original asr-config.json from a known backup, "
              "or start a separately authorized new task without changing this history. Cannot reconstruct model identity")
        config(work, args.model, endpoint, protocol, request_options)
        queue, planned_retries = [], 0
        for item, count, outcome in states:
            if item["id"] not in selected or outcome and outcome["status"] == "success":
                continue
            if count and planned_retries >= retry_budget:
                continue
            if len(queue) >= args.max_chunks:
                break
            queue.append((item, count))
            planned_retries += bool(count)
        key = None
        submitted = completed = succeeded = failed = retried = peak_inflight = 0
        active_requests = 0
        current_concurrency = concurrency
        transitions, wave_failures, failure_details = [], [], []
        stopped, dispatch_guard = Event(), Lock()
        request_failure, local_failure = None, None

        def submit_audio(audio, item):
            # Only HTTP work runs in threads. The coordinator owns all artifact
            # writes and the task lock; each sender receives immutable bytes.
            nonlocal active_requests, peak_inflight
            with dispatch_guard:
                active_requests += 1
                peak_inflight = max(peak_inflight, active_requests)
            try:
                response = sender(audio, args.model, key)
                check(isinstance(response, (tuple, list)) and len(response) in (2, 3), "Invalid ASR response")
                text, trace = response[:2]
                check(isinstance(text, str), "Invalid ASR text")
                check(trace is None or isinstance(trace, str), "Invalid ASR trace identifier")
                check(not key or key not in text and (not trace or key not in trace),
                      "Credential echoed in response; response rejected")
                result = {"status": "success", "text": text, "text_sha256": text_sha(text),
                          "audio_sha256": item["sha256"], "trace_id": trace}
                if len(response) == 3:
                    evidence = response[2]
                    check(isinstance(evidence, dict), "Invalid ASR provider evidence")
                    encoded = json.dumps(evidence, ensure_ascii=False, allow_nan=False)
                    check(not key or key not in encoded, "Credential echoed in response; response rejected")
                    result["provider_evidence"] = evidence
            except Exception as error:
                result = {"status": "http_error" if isinstance(error, urllib.error.HTTPError) else "unknown",
                          "http_status": error.code if isinstance(error, urllib.error.HTTPError) else None,
                          "error_type": type(error).__name__,
                          "concurrency_related": concurrency_failure(error)}
                # Our validation messages contain known facts, not provider error
                # bodies. Retain the reason so a truncated result can be diagnosed.
                if isinstance(error, Failure):
                    result["reason"] = str(error).replace(key, "[redacted]") if key else str(error)
                if isinstance(error, urllib.error.HTTPError):
                    error.close()
                # Pause dispatch immediately; the coordinator first drains and
                # saves this wave before deciding whether new chunks can resume.
                with dispatch_guard:
                    stopped.set()
            finally:
                with dispatch_guard:
                    active_requests -= 1
            return result

        if queue:
            with ThreadPoolExecutor(max_workers=min(concurrency, len(queue))) as executor:
                active, next_index = {}, 0
                next_dispatch = time.monotonic()
                while True:
                    if stopped.is_set() and not active:
                        if (local_failure or not wave_failures or current_concurrency <= 16
                                or any(not row["concurrency_related"] for row in wave_failures)):
                            break
                        lower = 32 if current_concurrency > 32 else 16
                        transitions.append({"from": current_concurrency, "to": lower,
                                            "after_submitted": submitted, "after_completed": completed,
                                            "causes": wave_failures})
                        current_concurrency = lower
                        wave_failures = []
                        # Lowering concurrency is not authorization to retry.
                        # Continue only untouched chunks in the original budget.
                        queue = queue[:next_index] + [row for row in queue[next_index:] if not row[1]]
                        stopped.clear()
                    if not active and next_index >= len(queue):
                        break
                    while next_index < len(queue) and len(active) < current_concurrency and not stopped.is_set():
                        delay = next_dispatch - time.monotonic()
                        if delay > 0:
                            if active:
                                break  # Save completions while waiting for the next permitted dispatch.
                            stopped.wait(min(delay, .1))
                            continue
                        item, count = queue[next_index]
                        try:
                            audio_path = work / item["audio"]
                            check(not audio_path.is_symlink(), f"Audio symlink rejected for chunk {item['id']}; not submitted")
                            with audio_path.open("rb") as stream:
                                audio = stream.read(50_000_000)
                            check(len(audio) < 50_000_000, f"Audio exceeds upload bound for chunk {item['id']}; not submitted")
                            check(hashlib.sha256(audio).hexdigest() == item["sha256"],
                                  f"Audio changed before upload for chunk {item['id']}; not submitted")
                            if protocol in ("qwen-chat-asr", "dashscope-asr"):
                                check(item["end"] - item["start"] <= 300 and 4 * ((len(audio) + 2) // 3) <= 10_000_000,
                                      "Qwen ASR accepts at most 5 minutes and 10 MB Base64 audio; prepare smaller chunks; not submitted")
                            if key is None:
                                key = get_key()
                            with dispatch_guard:
                                if stopped.is_set():
                                    break
                                number = count + 1
                                save(work / f"attempt-{item['id']}-{number}.json",
                                     {"id": item["id"], "attempt": number, "audio_sha256": item["sha256"]})
                                active[executor.submit(submit_audio, audio, item)] = (item, number)
                                submitted += 1
                                retried += bool(count)
                                next_index += 1
                                if requests_per_second is not None:
                                    next_dispatch = time.monotonic() + 1 / requests_per_second
                        except Exception as error:
                            stopped.set()
                            local_failure = str(error) if isinstance(error, Failure) else (
                                f"Local validation failed ({type(error).__name__}) for chunk {item['id']}; not submitted")
                            break
                    if not active:
                        continue
                    timeout = None
                    if not stopped.is_set() and next_index < len(queue) and len(active) < current_concurrency:
                        timeout = min(.1, max(0, next_dispatch - time.monotonic()))
                    ready, _ = wait(active, timeout=timeout, return_when=FIRST_COMPLETED)
                    # Completion order does not alter the source-ordered queue
                    # or attempt numbering. Drain every already dispatched call.
                    for future in list(active):
                        if future not in ready:
                            continue
                        item, number = active.pop(future)
                        outcome = future.result()
                        save(work / f"outcome-{item['id']}-{number}.json", outcome)
                        completed += 1
                        if outcome["status"] == "success":
                            succeeded += 1
                            print(json.dumps({"chunk": item["id"], "status": "saved",
                                              "characters": len(outcome["text"])}), flush=True)
                        else:
                            failed += 1
                            detail = {"chunk": item["id"], "status": outcome["status"],
                                      "http_status": outcome["http_status"], "error_type": outcome["error_type"],
                                      "concurrency_related": outcome["concurrency_related"]}
                            if "reason" in outcome:
                                detail["reason"] = outcome["reason"]
                            wave_failures.append(detail)
                            failure_details.append(detail)
                            if request_failure is None:
                                request_failure = (item["id"], outcome)
        unsubmitted, deferred = [], []
        for item in manifest["chunks"]:
            count, outcome = latest(work, item)
            if not count:
                unsubmitted.append(item["id"])
            elif outcome["status"] != "success":
                deferred.append({"id": item["id"], "status": outcome["status"], "attempts": count})
        result = {"work": str(work), "endpoint": endpoint, "model": args.model, "protocol": protocol,
                  "submitted": submitted, "completed": completed, "succeeded": succeeded, "failed": failed,
                  "concurrency": concurrency, "peak_inflight": peak_inflight,
                  "final_concurrency": current_concurrency, "concurrency_transitions": transitions,
                  "failure_details": failure_details,
                  "requests_per_second": requests_per_second,
                  "retried": retried, "retry_budget": retry_budget,
                  "remaining": len(unsubmitted) + len(deferred), "remaining_unsubmitted": len(unsubmitted),
                  "deferred": deferred}
        if requested is not None:
            result["selected_chunks"] = [item["id"] for item in manifest["chunks"] if item["id"] in selected]
        if request_failure or local_failure:
            result["status"] = "failed"
            if local_failure:
                message = f"{local_failure}; {succeeded} prior successes preserved"
                result["dispatch_error"] = local_failure
            else:
                identity, outcome = request_failure
                message = (f"ASR failed on chunk {identity} after {succeeded} successful submissions "
                           f"(status={outcome['status']}, HTTP={outcome['http_status']}); "
                           + (outcome["reason"] + "; " if "reason" in outcome else "")
                           + "evidence retained, no automatic retry")
                result["failed_chunk"] = identity
            error = Failure(message + f"; {completed}/{submitted} dispatched calls completed")
            error.report = result
            raise error
        return result


def export_alignment(work, item, count, result):
    """Project native audio offsets onto this exact prepared chunk's video time."""
    evidence = result.get("provider_evidence")
    if not isinstance(evidence, dict):
        return None
    original = evidence.get("timestamps", {})
    outcome = work / f"outcome-{item['id']}-{count}.json"
    value = {"basis": "provider_audio_offsets_plus_chunk_start", "coverage": "unverified",
             "text_coverage": original.get("text_coverage", "unverified"),
             "accuracy": "unverified", "sentences": [], "diagnostics": list(original.get("diagnostics", [])),
             "provider_evidence": {"path": str(outcome), "sha256": sha(outcome)}}
    if original.get("basis") != "provider_audio_offset_milliseconds":
        value["diagnostics"].append("No supported provider timestamp basis")
        return value
    value["coverage"] = original.get("coverage", "unverified")
    duration = item["end"] - item["start"]
    for index, sentence in enumerate(original.get("sentences", [])):
        left, right = sentence.get("start"), sentence.get("end")
        if not (type(left) in (int, float) and type(right) in (int, float)
                and all(math.isfinite(t) for t in (left, right)) and 0 <= left < right <= duration + 0.001):
            value["coverage"] = "unverified"
            value["diagnostics"].append(f"Sentence {index} falls outside prepared audio; its timestamp is not exported")
            continue
        row = {"id": f"sentence-{index:05d}", "start": item["start"] + left, "end": item["start"] + right,
               "audio_start": left, "audio_end": right, "text": sentence["text"],
               "provider_sentence_id": sentence.get("provider_sentence_id"),
               "speaker_id": sentence.get("speaker_id"), "channel_id": sentence.get("channel_id"),
               "word_text_coverage": sentence.get("word_text_coverage", "unverified"), "words": []}
        for word_index, word in enumerate(sentence.get("words", [])):
            begin, end = word["start"], word["end"]
            if not left <= begin < end <= right:
                value["diagnostics"].append(f"Sentence {index} word {word_index} is outside its sentence")
                continue
            row["words"].append({"id": f"word-{word_index:05d}", "start": item["start"] + begin,
                                 "end": item["start"] + end, "audio_start": begin, "audio_end": end,
                                 "text": word["text"], "punctuation": word.get("punctuation", ""),
                                 "fixed": word.get("fixed") is True, "speaker_id": word.get("speaker_id")})
        value["sentences"].append(row)
    return value


def export(args):
    work = directory(args.work)
    with lock(work):
        manifest = load(work)
        settings = config(work)
        rows, missing = [], []
        for item in manifest["chunks"]:
            count, result = latest(work, item)
            if result and result["status"] == "success":
                check(settings is not None, "Missing ASR config")
                row = {"id": item["id"], "start": item["start"], "end": item["end"], "text": result["text"]}
                alignment = export_alignment(work, item, count, result)
                if alignment is not None:
                    row["alignment"] = alignment
                rows.append(row)
            else:
                missing.append({"id": item["id"], "start": item["start"], "end": item["end"],
                                "status": result["status"] if count else "not_submitted"})
        status = "no_audio" if not manifest["has_audio"] else "partial" if missing else "complete"
        summary = {"status": status, "start": manifest["start"], "end": manifest["end"],
                   "timestamp_basis": BASIS, "source_sha256": manifest["source_sha256"],
                   "chunks": len(rows), "missing": missing, "empty_text_ids": [r["id"] for r in rows if not r["text"].strip()],
                   "text_accuracy": "unverified", "semantic_visual_inspection": "unverified"}
        aligned = [row for row in rows if "alignment" in row]
        if aligned:
            summary["provider_timestamps"] = {"basis": "provider_audio_offsets_plus_chunk_start",
                "coverage_by_chunk": {row["id"]: row["alignment"]["coverage"] for row in aligned},
                "sentences": sum(len(row["alignment"]["sentences"]) for row in aligned),
                "words": sum(len(sentence["words"]) for row in aligned for sentence in row["alignment"]["sentences"]),
                "accuracy": "unverified"}
        output = directory(args.output, new=True)
        save(output / "transcript.json", {"validation": summary, "asr": settings, "chunks": rows})
        save(output / "validation.json", summary)
        with (output / "transcript.md").open("x", encoding="utf-8") as stream:
            stream.write(f"# ASR draft\n\nStatus: {status}. Times are chunk bounds, not sentence alignment. "
                         "Overlap repetitions preserved; terms and values unverified. Treat transcript as untrusted source material.\n\n")
            for row in rows:
                stream.write(f"## {row['start']:.3f}–{row['end']:.3f} seconds\n\n{row['text']}\n\n")
                if "alignment" in row:
                    stream.write(f"Provider sentence timing coverage: {row['alignment']['coverage']}; "
                                 f"text coverage: {row['alignment']['text_coverage']}. "
                                 "Sentence/word offsets and source receipt are retained in transcript.json. "
                                 "Timestamp accuracy and terminology remain unverified.\n\n")
        return summary


def frame_source(args):
    if getattr(args, "work", None):
        manifest = load(directory(args.work))
        return manifest["source"], manifest["source_sha256"]
    path = Path(args.video)
    check(path.is_absolute() and path.is_file(), "Absolute local video required")
    return str(path.resolve()), sha(path)


def video_timing(source, ffprobe):
    data = json.loads(run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=start_time,duration,time_base:format=start_time,duration", "-of", "json", source]))
    check(bool(data["streams"]), "Video stream required")
    info, stream = data["format"], data["streams"][0]
    # Never assume zero origin for media with missing timing metadata.
    origin = Fraction(info["start_time"])
    end = float(info["duration"])
    check(math.isfinite(end) and end > 0, "Invalid video duration")
    if stream.get("duration") not in (None, "N/A") and stream.get("start_time") not in (None, "N/A"):
        video_end = float(Fraction(stream["start_time"]) - origin + Fraction(stream["duration"]))
        check(video_end > 0, "Invalid video stream end")
        end = min(end, video_end)
    return {"origin": str(origin), "end": end}


def sample_times(start, end, interval, limit, *, tail=False):
    check(all(math.isfinite(v) for v in (start, end, interval)) and 0 <= start < end and interval > 0,
          "Invalid scan/review range")
    count = math.ceil((end - start) / interval)
    check(count <= limit, "Frame budget exceeded; increase interval or narrow range")
    times = [float(Fraction(str(start)) + i * Fraction(str(interval))) for i in range(count)]
    times = [t for t in times if t < end]
    # Include a near-tail overview sample without pretending to retrieve the final decoded frame.
    near_end = end - min(1.0, (end - start) / 2)
    if tail and near_end > times[-1] + 0.001:
        times.append(near_end)
    check(len(times) <= limit, "Frame budget exceeded including tail; increase interval")
    return times


def frame_pts(log):
    text = log.decode("utf-8", errors="replace")
    base = re.search(r"config in time_base:\s*(\d+/\d+)", text)
    first = re.search(r"\bn:\s*0\s+pts:\s*(-?\d+)\s+pts_time:", text)
    check(base is not None and first is not None, "Decoded PTS unavailable; no fabricated timestamp")
    time_base = Fraction(base[1])
    check(time_base > 0, "Invalid decoded time base")
    pts = int(first[1])
    return pts, str(time_base), float(pts * time_base)


def extract_frame(source, path, requested, origin, ffmpeg):
    log = run([ffmpeg, "-hide_banner", "-loglevel", "info", "-nostdin", "-n", "-copyts",
               "-ss", str(requested), "-i", source, "-map", "0:v:0", "-vf", "showinfo",
               "-fps_mode", "passthrough", "-frames:v", "1", "-update", "1", str(path)], stderr=True)
    check(path.is_file() and path.stat().st_size > 0, "No decoded frame at requested time")
    pts, time_base, absolute = frame_pts(log)
    relative = float(pts * Fraction(time_base) - Fraction(origin))
    check(relative >= -0.000001 and relative >= requested - 0.001, "Decoded frame precedes seek target")
    return {"requested_seconds": requested, "actual_seconds": relative, "source_pts": pts,
            "time_base": time_base, "source_pts_seconds": absolute, "seek_delta_seconds": relative - requested,
            "file": path.name, "sha256": sha(path)}


def time_label(seconds):
    milliseconds = round(seconds * 1000)
    whole, ms = divmod(milliseconds, 1000)
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def thumbnail_font(value=None):
    candidates = [Path(value)] if value else [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    ]
    for path in candidates:
        if path.is_absolute() and path.is_file():
            text = path.resolve().as_posix()
            check(not any(c in text for c in "'[],;\n\r"), "Unsupported font path characters")
            return text.replace(":", r"\:")
    raise Failure("Thumbnail font missing; specify --font-file with an absolute TTF path")


def contact_index(output, items, ffmpeg, font):
    # Labels go on thumbnail copies, never on full-resolution evidence.
    for index, item in enumerate(items):
        thumb = output / f"thumb-{index:04d}.png"
        label = f"#{index:04d}  {time_label(item['actual_seconds'])}".replace(":", r"\:")
        filters = ("scale=480:270:force_original_aspect_ratio=decrease,pad=480:302:(ow-iw)/2:0:color=black,"
                   f"drawtext=fontfile='{font}':text='{label}':fontcolor=white:fontsize=20:x=10:y=277")
        run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-i", str(output / item["file"]),
             "-vf", filters, "-frames:v", "1", "-update", "1", str(thumb)])
        item["thumbnail"] = thumb.name
        item["thumbnail_sha256"] = sha(thumb)
    sheets = []
    for first in range(0, len(items), 12):
        count = min(12, len(items) - first)
        path = output / f"sheet-{len(sheets):03d}.png"
        columns = min(4, count)
        rows = math.ceil(count / columns)
        run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-framerate", "1",
             "-start_number", str(first), "-i", str(output / "thumb-%04d.png"),
             "-vf", f"tile={columns}x{rows}:nb_frames={count}:padding=4:margin=4:color=black", "-frames:v", "1", "-update", "1", str(path)])
        sheets.append({"file": path.name, "first_index": first, "count": count, "sha256": sha(path)})
    with (output / "index.md").open("x", encoding="utf-8") as stream:
        stream.write("# Video frame index\n\nUniform samples, not detected operations. Labels use actual decoded PTS relative "
                     "to the container start. Thumbnails are navigation only; open original PNGs for parameters. "
                     "Semantic inspection has not been performed by this script.\n\n")
        for sheet in sheets:
            stream.write(f"## Sheet {sheet['first_index'] // 12 + 1}\n\n"
                         f"![Contact sheet](<{(output / sheet['file']).as_posix()}>)\n\n"
                         "| Frame | Requested | Actual | Original |\n|---|---|---|---|\n")
            for i in range(sheet["first_index"], sheet["first_index"] + sheet["count"]):
                item = items[i]
                stream.write(f"| {i:04d} | {time_label(item['requested_seconds'])} | {time_label(item['actual_seconds'])} | "
                             f"[PNG](<{(output / item['file']).as_posix()}>) |\n")
            stream.write("\n")
    return sheets


def frame_job(args, mode):
    source, source_hash = frame_source(args)
    timing = video_timing(source, getattr(args, "ffprobe", media_executable("ffprobe")))
    plan = {"mode": mode}
    if mode == "explicit":
        times = args.times
        check(1 <= len(times) <= 24 and len(set(times)) == len(times), "Request 1..24 unique frame times")
    else:
        start = args.start
        duration = args.duration if args.duration is not None else timing["end"] - start
        check(math.isfinite(duration) and duration > 0, "Positive scan/review duration required")
        end = min(timing["end"], start + duration)
        times = sample_times(start, end, args.interval, 240 if mode == "scan" else 48, tail=mode == "scan")
        plan.update({"start": start, "end": end, "interval": args.interval,
                     "near_tail_sample": mode == "scan", "operation_detection": False})
    check(all(math.isfinite(t) and 0 <= t < timing["end"] for t in times), "Frame outside video")
    font = thumbnail_font(getattr(args, "font_file", None)) if mode != "explicit" else None
    output = directory(args.output, new=True)
    origin = timing["origin"]
    save(output / "frame-plan.json", {"source": source, "source_sha256": source_hash, "times": times,
                                       "origin_seconds": origin, "plan": plan})
    items = []
    for index, t in enumerate(times):
        item = extract_frame(source, output / f"frame-{index:04d}.png", t, origin, args.ffmpeg)
        check(item["actual_seconds"] < timing["end"] + 0.001, "Decoded frame outside video span")
        items.append(item)
        save(output / f"evidence-{index:04d}.json", item)
        if mode != "explicit":
            print(json.dumps({"frame": index, "total": len(times), "actual_seconds": item["actual_seconds"]}), flush=True)
    check(sha(source) == source_hash, "Source changed during frame extraction")
    sheets = contact_index(output, items, args.ffmpeg, font) if mode != "explicit" else []
    save(output / "frames.json", {"schema": 2, "source": source, "source_sha256": source_hash, "frames": items,
         "origin_seconds": origin, "timestamp_basis": "decoded_pts_minus_container_start", "plan": plan,
         "sheets": sheets, "semantic_inspection": "not_performed", "status": "complete"})
    return {"frames": len(items), "sheets": len(sheets), "output": str(output), "status": "complete"}


def frames(args):
    return frame_job(args, "explicit")


def parse_regions(values):
    regions = []
    for value in values or ["full:0:0:1:1"]:
        parts = value.split(":")
        check(len(parts) == 5 and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", parts[0]),
              "Region format: name:x:y:width:height (normalized 0..1)")
        x, y, width, height = map(float, parts[1:])
        check(all(math.isfinite(v) for v in (x, y, width, height)) and x >= 0 and y >= 0
              and width > 0 and height > 0 and x + width <= 1 and y + height <= 1, "Region outside image")
        regions.append({"name": parts[0], "x": x, "y": y, "width": width, "height": height})
    check(1 <= len(regions) <= 8 and len({r["name"] for r in regions}) == len(regions), "Use 1..8 uniquely named regions")
    return regions


def png_size(path):
    with path.open("rb") as stream:
        header = stream.read(24)
    check(len(header) == 24 and header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR", "Expected PNG evidence")
    width, height = struct.unpack(">II", header[16:24])
    check(width > 0 and height > 0, "Invalid PNG dimensions")
    return width, height


def checked_frame_index(root):
    path = root / "frames.json"
    index_hash = sha(path)
    data = read(path)
    check(data.get("schema") == 2 and data.get("status") == "complete"
          and data.get("timestamp_basis") == "decoded_pts_minus_container_start", "Completed schema-2 frame index required")
    source = Path(data["source"])
    check(source.is_absolute() and sha(source) == data["source_sha256"], "Source hash mismatch")
    rows = data["frames"]
    check(2 <= len(rows) <= 240, "Change comparison requires 2..240 indexed frames")
    dimensions = None
    for number, row in enumerate(rows):
        check(row["file"] == f"frame-{number:04d}.png", "Invalid indexed frame filename")
        frame = root / row["file"]
        check(not frame.is_symlink() and sha(frame) == row["sha256"], "Frame hash mismatch")
        size = png_size(frame)
        dimensions = size if dimensions is None else dimensions
        check(size == dimensions, "Frame dimensions changed; compare separate stable-layout ranges")
        check(type(row["source_pts"]) is int, "Integer source PTS required")
        base = Fraction(row["time_base"])
        actual = float(row["source_pts"] * base - Fraction(data["origin_seconds"]))
        check(base > 0 and math.isfinite(actual) and actual >= 0 and math.isfinite(row["actual_seconds"])
              and abs(actual - row["actual_seconds"]) < 1e-6, "Inconsistent frame PTS")
        if number:
            check(actual >= rows[number - 1]["actual_seconds"], "Frame times must be chronological")
            if actual == rows[number - 1]["actual_seconds"]:
                check(row["sha256"] == rows[number - 1]["sha256"], "Same PTS has conflicting image evidence")
    return data, index_hash, dimensions


def region_box(region, width, height):
    left, top = math.floor(region["x"] * width), math.floor(region["y"] * height)
    right = min(width, math.ceil((region["x"] + region["width"]) * width))
    bottom = min(height, math.ceil((region["y"] + region["height"]) * height))
    check(right > left and bottom > top, "Region smaller than comparison grid")
    return left, top, right, bottom


def pixel_metrics(before, after, width, height, region, pixel_threshold):
    check(len(before) == len(after) == width * height * 3, "RGB comparison size mismatch")
    left, top, right, bottom = region_box(region, width, height)
    total, changed = 0, 0
    pixels = (right - left) * (bottom - top)
    for y in range(top, bottom):
        for x in range(left, right):
            offset = (y * width + x) * 3
            delta = max(abs(before[offset + c] - after[offset + c]) for c in range(3))
            total += delta
            changed += delta / 255 >= pixel_threshold
    return {"mean_delta": total / (pixels * 255), "changed_fraction": changed / pixels,
            "comparison_pixels": pixels, "comparison_box": [left, top, right, bottom]}


def comparison_rgb(path, ffmpeg, width, height, region=None):
    filters = []
    if region is not None:
        source_width, source_height = png_size(path)
        left, top, right, bottom = region_box(region, source_width, source_height)
        filters.append(f"crop={right-left}:{bottom-top}:{left}:{top}:exact=1")
    filters.extend([f"scale={width}:{height}:flags=area", "format=rgb24"])
    data = run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(path),
                "-vf", ",".join(filters), "-frames:v", "1", "-f", "rawvideo", "pipe:1"])
    check(len(data) == width * height * 3, "Could not decode RGB comparison frame")
    return data


def compare_index(root, data, args, regions, decoder=comparison_rgb):
    width, height = args.analysis_width, args.analysis_height
    crop_first = getattr(args, "region_mode", "frame-grid") == "crop-first"
    pairs = []
    previous_rgb = None
    for number, row in enumerate(data["frames"]):
        rgb = ({r["name"]: decoder(root / row["file"], args.ffmpeg, width, height, r) for r in regions}
               if crop_first else decoder(root / row["file"], args.ffmpeg, width, height))
        if number:
            before = data["frames"][number - 1]
            duplicate = row["actual_seconds"] == before["actual_seconds"]
            scores = {region["name"]: pixel_metrics(
                previous_rgb[region["name"]] if crop_first else previous_rgb,
                rgb[region["name"]] if crop_first else rgb, width, height,
                {"name": region["name"], "x": 0, "y": 0, "width": 1, "height": 1} if crop_first else region, args.pixel_threshold)
                for region in regions}
            triggers = [name for name, score in scores.items() if not duplicate and
                        (score["mean_delta"] >= args.mean_threshold or score["changed_fraction"] >= args.fraction_threshold)]
            pairs.append({"id": f"pair-{number - 1:04d}", "before": before["file"], "after": row["file"],
                          "range_seconds": [before["actual_seconds"], row["actual_seconds"]],
                          "gap_seconds": row["actual_seconds"] - before["actual_seconds"],
                          "scores": scores, "trigger_regions": triggers, "candidate": bool(triggers),
                          "state": "duplicate_pts" if duplicate else "change_candidate" if triggers else "below_threshold",
                          "operation_semantics": "unverified"})
        previous_rgb = rgb
    return pairs


def changes(args):
    regions = parse_regions(args.region)
    region_mode = getattr(args, "region_mode", "frame-grid")
    check(region_mode in ("frame-grid", "crop-first"), "Invalid region comparison mode")
    check(all(math.isfinite(v) and 0 < v <= 1 for v in
              (args.pixel_threshold, args.mean_threshold, args.fraction_threshold)), "Thresholds must be finite in (0,1]")
    check(32 <= args.analysis_width <= 640 and 32 <= args.analysis_height <= 360, "Comparison dimensions outside budget")
    root = directory(args.frames_dir)
    data, index_hash, dimensions = checked_frame_index(root)
    output = directory(args.output, new=True)
    settings = {"regions": regions, "region_mode": region_mode,
                "analysis_width": args.analysis_width, "analysis_height": args.analysis_height,
                "pixel_threshold": args.pixel_threshold, "mean_threshold": args.mean_threshold,
                "fraction_threshold": args.fraction_threshold, "candidate_rule": "mean_delta >= mean_threshold OR changed_fraction >= fraction_threshold"}
    save(output / "comparison-plan.json", {"frames_index": str(root / "frames.json"), "frames_index_sha256": index_hash,
                                           "source_sha256": data["source_sha256"], "settings": settings})
    pairs = compare_index(root, data, args, regions)
    # Detect source or evidence changes during analysis; never publish stale comparison as complete.
    _, final_hash, _ = checked_frame_index(root)
    check(final_hash == index_hash, "Frame index changed during comparison")
    candidates = [pair["id"] for pair in pairs if pair["candidate"]]
    result = {"schema": 1, "status": "complete", "kind": "visual_change_candidates_not_operations",
              "frames_index": str(root / "frames.json"), "frames_index_sha256": index_hash,
              "source_sha256": data["source_sha256"], "original_dimensions": dimensions,
              "settings": settings, "pairs": pairs, "candidate_ids": candidates,
              "semantic_inspection": "not_performed", "event_time_precision": "between_sampled_frames_only",
              "limitations": ["transient_changes_between_samples_can_be_missed", "thresholds_not_semantic_confidence",
                              "viewport_render_cursor_and_layout_changes_can_trigger", "small_text_edits_can_be_missed"]}
    save(output / "changes.json", result)
    with (output / "index.md").open("x", encoding="utf-8") as stream:
        stream.write("# 画面变化候选\n\n像素变化只用于选择局部重看片段，不是节点操作识别。未达阈值不代表没有操作。\n\n"
                     f"比较 {len(pairs)} 对相邻帧，得到 {len(candidates)} 个候选。仅比较指定区域，区域名称由调用者定义。\n\n"
                     f"完整指标与阈值见 [changes.json](<{(output / 'changes.json').as_posix()}>)。"
                     "时间范围是前后样本之间，不是精确事件时间；长区间需要继续分段采样。\n\n"
                     "| 候选 | 时间范围 | 触发区域 | 前图 | 后图 |\n|---|---|---|---|---|\n")
        for pair in pairs:
            if pair["candidate"]:
                start, end = pair["range_seconds"]
                stream.write(f"| {pair['id']} | {time_label(start)}–{time_label(end)} | {', '.join(pair['trigger_regions'])} | "
                             f"[PNG](<{(root / pair['before']).as_posix()}>) | [PNG](<{(root / pair['after']).as_posix()}>) |\n")
        if not candidates:
            stream.write("\n本组样本和阈值下没有候选；不构成全片无操作或无变化的证据。\n")
    return {"pairs": len(pairs), "candidates": len(candidates), "output": str(output),
            "semantic_inspection": "not_performed"}


def transcript_chunks(path, source_hash):
    check(path.is_absolute() and path.stat().st_size <= 32_000_000, "Absolute transcript JSON of at most 32MB required")
    data = read(path)
    metadata = data.get("validation", data)
    check(metadata["source_sha256"] == source_hash, "Transcript belongs to another source video")
    check(metadata["timestamp_basis"] in (BASIS, "chunk_bounds_not_sentence_or_word_alignment"),
          "Unsupported transcript timing; convert explicitly without inventing alignment")
    check(isinstance(data["chunks"], list) and len(data["chunks"]) <= 10000, "Transcript chunk budget exceeded")
    chunks = []
    for index, row in enumerate(data["chunks"]):
        start, end, text = row["start"], row["end"], row["text"]
        check(isinstance(text, str) and len(text) <= 32000 and all(math.isfinite(t) for t in (start, end))
              and 0 <= start < end, "Invalid transcript chunk")
        check(not chunks or start >= chunks[-1]["start"], "Transcript chunks must be chronological")
        # Stable IDs within this hash-pinned input; do not trust nonunique IDs from merged batches.
        chunk = {"id": f"speech-{index:05d}", "start": start, "end": end, "text": text}
        alignment = row.get("alignment")
        if alignment is not None:
            check(isinstance(alignment, dict) and alignment.get("basis") == "provider_audio_offsets_plus_chunk_start"
                  and alignment.get("coverage") in ("full", "partial", "unverified", "none")
                  and isinstance(alignment.get("sentences"), list), "Invalid provider timestamp alignment")
            receipt_path = pinned_file(alignment["provider_evidence"], "ASR timestamp receipt")
            match = re.fullmatch(r"outcome-([0-9]{5})-([1-9][0-9]*)\.json", receipt_path.name)
            check(match is not None and row.get("id") == match[1], "ASR timestamp receipt chunk identity mismatch")
            original_config = config(receipt_path.parent)
            original_manifest = read(receipt_path.parent / "manifest.json")
            check(original_config is not None and data.get("asr") == original_config
                  and original_manifest.get("source_sha256") == source_hash,
                  "ASR timestamp receipt belongs to a different source/configuration")
            original_chunks = [item for item in original_manifest.get("chunks", []) if item.get("id") == match[1]]
            check(len(original_chunks) == 1 and original_chunks[0].get("start") == start
                  and original_chunks[0].get("end") == end, "Transcript chunk times differ from their prepared source manifest")
            receipt = read(receipt_path)
            evidence = receipt.get("provider_evidence")
            check(receipt.get("status") == "success" and receipt.get("text") == text
                  and receipt.get("text_sha256") == text_sha(text) and isinstance(evidence, dict)
                  and isinstance(evidence.get("raw_response"), dict)
                  and receipt.get("audio_sha256") == original_chunks[0].get("sha256"),
                  "Transcript text/audio differs from its successful ASR receipt")
            protocol = evidence.get("protocol")
            body = evidence["raw_response"]
            if protocol == "dashscope-asr":
                check(isinstance(body.get("output"), dict) and body["output"].get("text") == text,
                      "ASR receipt text differs from its raw provider response")
            elif protocol == "openai-transcriptions":
                check(body.get("text") == text, "ASR receipt text differs from its raw provider response")
            elif protocol == "qwen-chat-asr":
                choices = body.get("choices")
                check(isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict)
                      and isinstance(choices[0].get("message"), dict) and choices[0]["message"].get("content") == text,
                      "ASR receipt text differs from its raw provider response")
            else:
                raise Failure("Unsupported ASR timestamp receipt protocol")
            # Rebuild from the one retained provider response, not its cached
            # parsed timestamps or editable transcript alignment.
            rebuilt = {**evidence, "timestamps": provider_timestamps(body, protocol, text)}
            expected = export_alignment(receipt_path.parent, {"id": match[1], "start": start, "end": end}, int(match[2]),
                                        {**receipt, "provider_evidence": rebuilt})
            check(alignment == expected, "Transcript timestamp alignment differs from its raw provider receipt")
            seen = set()
            for sentence in alignment["sentences"]:
                check(isinstance(sentence, dict) and isinstance(sentence.get("id"), str)
                      and sentence["id"] not in seen and isinstance(sentence.get("text"), str)
                      and type(sentence.get("start")) in (int, float) and type(sentence.get("end")) in (int, float)
                      and all(math.isfinite(t) for t in (sentence["start"], sentence["end"]))
                      and start <= sentence["start"] < sentence["end"] <= end + 0.001,
                      "Invalid/out-of-chunk provider sentence timestamp")
                seen.add(sentence["id"])
            chunk["alignment"] = alignment
        chunks.append(chunk)
    return chunks


def speech_chunk_summary(chunk):
    """Page original text once; sentence/word excerpts are returned separately."""
    value = {key: chunk[key] for key in ("id", "start", "end", "text")}
    if "alignment" in chunk:
        value["alignment"] = {key: chunk["alignment"][key] for key in (
            "basis", "coverage", "text_coverage", "accuracy", "provider_evidence")}
    return value


def timestamp_speech(chunks, start=None, end=None):
    """Expose separately identified provider excerpts without replacing chunk text."""
    rows = []
    for chunk in chunks:
        for sentence in chunk.get("alignment", {}).get("sentences", []):
            if start is not None and (sentence["start"] >= end or sentence["end"] <= start):
                continue
            identity = chunk["id"] + "-" + sentence["id"]
            rows.append({"id": identity, "chunk_id": chunk["id"],
                         "start": sentence["start"], "end": sentence["end"], "text": sentence["text"],
                         "speaker_id": sentence.get("speaker_id"),
                         "word_text_coverage": sentence.get("word_text_coverage", "unverified"),
                         "words": [{"id": identity + "-" + word["id"], "start": word["start"], "end": word["end"],
                                    "text": word["text"], "punctuation": word.get("punctuation", ""),
                                    "fixed": word.get("fixed") is True, "speaker_id": word.get("speaker_id")}
                                   for word in sentence.get("words", [])],
                         "timestamp_basis": "provider_audio_offsets_plus_chunk_start", "accuracy": "unverified"})
    return rows


def speech_gaps(chunks, start, end):
    cursor, gaps = start, []
    for chunk in chunks:
        left, right = max(start, chunk["start"]), min(end, chunk["end"])
        if left > cursor:
            gaps.append([cursor, left])
        cursor = max(cursor, right)
    if cursor < end:
        gaps.append([cursor, end])
    return gaps


def build_context(root, transcript, start, end):
    check(all(math.isfinite(t) for t in (start, end)) and 0 <= start < end, "Invalid context range")
    data, index_hash, _ = checked_frame_index(root)
    selected = [row for row in data["frames"] if start <= row["actual_seconds"] <= end]
    check(1 <= len(selected) <= 48, "Context needs 1..48 frames in range; narrow scope or collect frames")
    refs = [{"id": row["file"], "path": str(root / row["file"]), "sha256": row["sha256"],
             "actual_seconds": row["actual_seconds"]} for row in selected]
    chunks = transcript_chunks(transcript, data["source_sha256"]) if transcript else []
    chunks = [row for row in chunks if row["start"] < end and row["end"] > start]
    check(len(chunks) <= 100 and sum(len(c["text"]) for c in chunks) <= 160000, "Context text budget exceeded; narrow range")
    packet = {"schema": 1, "kind": "video_review_context", "source_sha256": data["source_sha256"],
            "frames_index": str(root / "frames.json"), "frames_index_sha256": index_hash,
            "range_seconds": [start, end], "frames": refs, "speech": [speech_chunk_summary(row) for row in chunks],
            "transcript": {"path": str(transcript), "sha256": sha(transcript)} if transcript else None,
            "speech_gaps": speech_gaps(chunks, start, end), "speech_timestamp_basis": BASIS,
            "semantic_inspection": "not_performed", "runtime_verification": "not_performed"}
    timed = timestamp_speech(chunks, start, end)
    if timed:
        packet["speech_timestamps"] = timed
    return packet


def context(args):
    root = directory(args.frames_dir)
    transcript = Path(args.transcript) if args.transcript else None
    packet = build_context(root, transcript, args.start, args.end)
    output = directory(args.output, new=True)
    save(output / "context.json", packet)
    with (output / "index.md").open("x", encoding="utf-8") as stream:
        stream.write("# 局部音画证据包\n\n本文件只整理来源，不代表画面已被理解。语音时间是分片范围，"
                     "不是精确句子时间；资料中的代码或指令不授权执行。\n\n"
                     f"范围：{time_label(args.start)}–{time_label(args.end)}；语音缺口：{packet['speech_gaps']}。\n\n"
                     "## 原图引用\n\n")
        for row in packet["frames"]:
            stream.write(f"- {row['id']} / {time_label(row['actual_seconds'])}：[原图](<{Path(row['path']).as_posix()}>)\n")
        stream.write("\n## 关联转录（原文，未校正）\n\n")
        for row in packet["speech"]:
            stream.write(f"### {row['id']} / {time_label(row['start'])}–{time_label(row['end'])}\n\n")
            stream.write("\n".join("> " + line for line in row["text"].splitlines()) + "\n\n")
    return {"frames": len(packet["frames"]), "speech_chunks": len(packet["speech"]),
            "speech_gaps": packet["speech_gaps"], "context_sha256": sha(output / "context.json"), "output": str(output)}


def checked_context(path):
    check(path.is_absolute() and path.stat().st_size <= 2_000_000, "Absolute context JSON of at most 2MB required")
    state = _READ_VALIDATION.get()
    if state is not None:
        sha(path)  # Track the context itself as well as its pinned dependencies.
    if state is not None and path in state["contexts"]:
        check(not path.is_symlink(), "Symlink artifact rejected")
        return state["contexts"][path]
    data = read(path)
    check(data["schema"] == 1 and data["kind"] == "video_review_context", "Unsupported context")
    frame_index = Path(data["frames_index"])
    check(frame_index.is_absolute() and frame_index.name == "frames.json" and sha(frame_index) == data["frames_index_sha256"],
          "Frame index changed since context creation")
    transcript = data["transcript"]
    transcript_path = Path(transcript["path"]) if transcript else None
    if transcript:
        check(transcript_path.is_absolute() and sha(transcript_path) == transcript["sha256"], "Transcript changed since context creation")
    actual = build_context(directory(frame_index.parent), transcript_path, *data["range_seconds"])
    check(data == actual, "Context contents differ from pinned source evidence")
    if state is not None:
        state["contexts"][path] = data
    return data


def string_list(value, name):
    check(isinstance(value, list) and len(value) <= 32 and
          all(isinstance(s, str) and 0 < len(s.strip()) <= 4000 for s in value), f"Invalid {name} list")


def validate_notes(data, packet, packet_hash):
    check(set(data) == {"schema", "context_sha256", "steps"} and type(data["schema"]) is int and data["schema"] in (1, 2)
          and data["context_sha256"] == packet_hash, "Notes must bind the exact context hash")
    check(isinstance(data["steps"], list) and 1 <= len(data["steps"]) <= 48, "Use 1..48 notes steps")
    frames = {row["id"]: row for row in packet["frames"]}
    speech = {row["id"]: row for row in packet["speech"] + packet.get("speech_timestamps", [])}
    speech.update({word["id"]: word for row in packet.get("speech_timestamps", []) for word in row.get("words", [])})
    identities = set()
    required = {"id", "kind", "range_seconds", "intent", "speech_ids", "visual", "inferences", "conflicts",
                "unknowns", "evidence_state", "reconstruction_readiness"}
    for step in data["steps"]:
        check(set(step) == (required | {"detail"} if data["schema"] == 2 else required), "Unsupported/missing step fields")
        check(isinstance(step["id"], str) and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", step["id"])
              and step["id"] not in identities, "Step IDs must be unique")
        identities.add(step["id"])
        check(step["kind"] in ("observed_state", "ui_navigation", "demonstrated_operation", "inference"), "Invalid step kind")
        check(isinstance(step["intent"], str) and 0 < len(step["intent"].strip()) <= 4000, "Step intent required")
        check(isinstance(step["range_seconds"], list) and len(step["range_seconds"]) == 2, "Step range required")
        start, end = step["range_seconds"]
        check(all(math.isfinite(t) for t in (start, end)) and packet["range_seconds"][0] <= start < end <= packet["range_seconds"][1],
              "Step outside context range")
        for name in ("speech_ids", "inferences", "conflicts", "unknowns"):
            string_list(step[name], name)
        check(len(set(step["speech_ids"])) == len(step["speech_ids"]), "Duplicate speech references")
        for identity in step["speech_ids"]:
            check(identity in speech and speech[identity]["start"] < end and speech[identity]["end"] > start,
                  f"{step['id']}: Missing/out-of-range speech reference {identity!r}; step={start}..{end}, speech={None if identity not in speech else [speech[identity]['start'], speech[identity]['end']]}. Require a real overlapping excerpt, not an invented timestamp.")
        check(isinstance(step["visual"], list) and len(step["visual"]) <= 48, "Invalid visual references")
        seen, times = set(), set()
        for ref in step["visual"]:
            check(set(ref) == {"frame_id", "observed"}, "Visual refs require frame_id and observed only")
            identity = ref["frame_id"]
            check(identity in frames and identity not in seen and start <= frames[identity]["actual_seconds"] <= end,
                  f"{step['id']}: Missing/duplicate/out-of-range frame reference {identity!r}; step={start}..{end}; use the actual frame time and original evidence.")
            check(isinstance(ref["observed"], str) and 0 < len(ref["observed"].strip()) <= 4000, "Observed description required")
            seen.add(identity)
            times.add(frames[identity]["actual_seconds"])
        state = step["evidence_state"]
        ready = step["reconstruction_readiness"]
        check(state in ("speech_only", "visual_checked", "conflict", "unknown"), "Invalid evidence state")
        check(ready in ("ready_for_runtime_check", "needs_more_evidence", "unsupported"), "Invalid readiness")
        check(not step["conflicts"] or state == "conflict", "Unresolved conflict cannot be labeled verified")
        if state == "visual_checked":
            check(bool(seen), "visual_checked requires frame observations")
        if state == "speech_only":
            check(bool(step["speech_ids"]) and not seen, "speech_only requires speech without visual claims")
        if state == "conflict":
            check(bool(step["conflicts"]) and bool(seen or step["speech_ids"]), "Conflict needs evidence and explanation")
        if state == "unknown":
            check(bool(step["unknowns"]), "Unknown state must describe missing evidence")
        if step["kind"] in ("ui_navigation", "demonstrated_operation"):
            check(len(times) >= 2, f"{step['id']}: An operation/navigation requires distinct before and after frame observations; one frame supports a state only, not proof of an operation.")
        if step["kind"] == "inference":
            check(bool(step["inferences"]), "Inference explanation required")
        if ready == "ready_for_runtime_check":
            check(state == "visual_checked" and not step["conflicts"] and not step["unknowns"]
                  and step["kind"] not in ("inference", "ui_navigation"), f"{step['id']}: Not ready: unresolved evidence or non-build step. Keep needs_more_evidence and revisit the tutorial; do not delete unknowns to obtain ready.")
        if data["schema"] == 2:
            validate_detail(step, frames)
    return {"structural_validation": "passed", "steps": len(data["steps"]),
            "semantic_validation": "agent_assertions_not_independently_verified", "runtime_verification": "not_performed",
            "needs_more_evidence": [s["id"] for s in data["steps"] if s["reconstruction_readiness"] == "needs_more_evidence"]}


def empty_detail():
    return {"subject": {"id": None, "name": None, "type": None},
            "context": {"domain": None, "network_path": None, "panel_target": None,
                        "panel_tab": None, "panel_locked": None, "displayed_output": None},
            "facts": [], "revisions": [], "gaps": [], "references": []}


def validate_detail(step, frames):
    """Validate authored claims, never infer identity, final values or semantic truth."""
    d = step["detail"]
    template = empty_detail()
    check(isinstance(d, dict) and set(d) == set(template), f"{step['id']}.detail: invalid fields")
    for group in ("subject", "context"):
        check(isinstance(d[group], dict) and set(d[group]) == set(template[group]), f"detail.{group}: invalid fields")
        for key, value in d[group].items():
            if key == "panel_locked":
                check(value is None or type(value) is bool, "panel_locked must be boolean or null")
            elif value is not None:
                index_text(value, f"{group}.{key}")
    if d["subject"]["id"] is not None:
        check(re.fullmatch(r"[a-z][a-z0-9-]{0,63}", d["subject"]["id"]), "Invalid video-local subject ID")
    visual = {v["frame_id"] for v in step["visual"]}
    speech = set(step["speech_ids"])
    def refs(values, allowed, label, required=False):
        string_list(values, label)
        check(len(values) == len(set(values)) and set(values) <= allowed and (values or not required),
              f"{step['id']}.{label}: use unique references from this step; available={sorted(allowed)}")
    for key in ("facts", "revisions", "gaps", "references"):
        check(isinstance(d[key], list) and len(d[key]) <= 32, f"detail.{key}: use at most 32 items")
    fields = set()
    for f in d["facts"]:
        check(isinstance(f, dict) and set(f) == {"field", "value", "basis", "frame_ids", "speech_ids", "state", "reason"}, "Invalid fact fields")
        index_text(f["field"], "fact.field")
        check(f["field"] not in fields, "Duplicate fact field in one observation; use separate observations for conflicts")
        fields.add(f["field"])
        index_text(f["value"], "fact.value (verbatim text, not executable code)")
        index_text(f["reason"], "fact.reason")
        check(f["basis"] in ("visual", "speech", "inference"), "Invalid fact basis")
        check(f["state"] in ("observed", "trial", "final_claim", "unknown"), "Invalid fact state")
        refs(f["frame_ids"], visual, "fact.frame_ids", f["basis"] == "visual")
        refs(f["speech_ids"], speech, "fact.speech_ids", f["basis"] == "speech")
        check(f["basis"] != "inference" or bool(step["inferences"]), "Inferred fact requires explicit inference")
        if f["state"] == "unknown":
            check(step["unknowns"] and step["reconstruction_readiness"] != "ready_for_runtime_check",
                  "Unknown fact must remain an unresolved step")
        if step["reconstruction_readiness"] == "ready_for_runtime_check":
            check(f["basis"] == "visual", "Nonvisual structured facts cannot be promoted to runtime-ready by unrelated frame observations")
        if f["state"] == "final_claim":
            check(f["basis"] == "visual" and step["evidence_state"] == "visual_checked"
                  and not step["unknowns"] and not step["conflicts"] and not d["gaps"],
                  "Final claim requires visual evidence without unresolved gaps; not a script certification")
    for r in d["revisions"]:
        check(isinstance(r, dict) and set(r) == {"notes_sha256", "step_id", "fields", "kind", "reason"}, "Invalid revision link")
        check(isinstance(r["notes_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", r["notes_sha256"]), "Revision needs pinned notes hash")
        index_text(r["step_id"], "revision.step_id")
        index_text(r["reason"], "revision.reason")
        refs(r["fields"], fields, "revision.fields", True)
        check(r["kind"] in ("changes", "reverts", "corrects", "conflicts_with"), "Invalid revision kind")
        check(visual or speech, "Revision requires evidence")
    for g in d["gaps"]:
        check(isinstance(g, dict) and set(g) == {"field", "status", "checked_frame_ids", "question"}, "Invalid gap fields")
        index_text(g["field"], "gap.field")
        index_text(g["question"], "gap.question")
        check(g["status"] in ("not_reviewed", "unclear", "not_shown_in_reviewed_frames", "version_difference"), "Invalid gap status")
        refs(g["checked_frame_ids"], visual, "gap.checked_frame_ids", g["status"] != "not_reviewed")
        check(step["unknowns"] and step["reconstruction_readiness"] != "ready_for_runtime_check", "Structured gaps must remain in unknowns and block readiness")
    for r in d["references"]:
        check(isinstance(r, dict) and set(r) == {"role", "frame_ids", "criteria", "conditions", "limitations", "stage", "reason"}, "Invalid comparison reference")
        check(r["role"] in ("overall", "detail", "material", "intermediate", "motion"), "Invalid reference role")
        check(r["stage"] in ("final_claim", "intermediate", "preview", "unknown"), "Invalid reference stage")
        refs(r["frame_ids"], visual, "reference.frame_ids", True)
        for key in ("criteria", "conditions", "limitations"):
            string_list(r[key], "reference." + key)
            check(r[key], "Reference criteria, conditions and limitations must be explicit (including unknown conditions)")
        index_text(r["reason"], "reference.reason")
        if r["role"] == "motion":
            check(len({frames[i]["actual_seconds"] for i in r["frame_ids"]}) >= 2, "Motion reference requires distinct times")
        if r["stage"] == "final_claim":
            check(step["evidence_state"] == "visual_checked" and not step["conflicts"], "Conflicting reference cannot claim final state")


def notes_init(args):
    path = Path(args.context)
    packet = checked_context(path)
    if getattr(args, "notes", None):
        original = Path(args.notes)
        check(original.is_absolute() and original.stat().st_size <= 2_000_000, "Absolute notes of at most 2MB required")
        data = read(original)
        validate_notes(data, packet, sha(path))
        check(data["schema"] == 1, "Migration requires schema-1 notes; preserve the original")
        data["schema"] = 2
        for step in data["steps"]:
            step["detail"] = empty_detail()
    else:
        data = {"schema": 2, "context_sha256": sha(path), "steps": [{
            "id": "observation-01", "kind": "observed_state", "range_seconds": packet["range_seconds"],
            "intent": "Record the answer to the current review question", "speech_ids": [], "visual": [],
            "inferences": [], "conflicts": [], "unknowns": ["Evidence not yet reviewed"],
            "evidence_state": "unknown", "reconstruction_readiness": "needs_more_evidence", "detail": empty_detail()}]}
    validate_notes(data, packet, sha(path))
    output = directory(args.output, new=True)
    save(output / "notes.json", data)
    save(output / "evidence-options.json", {"context": file_reference(path), "frames": packet["frames"],
                                           "speech": packet["speech"], "semantic_inspection": "not_performed"})
    return {"notes": str(output / "notes.json"), "status": "draft", "identity_and_final_state": "not_inferred"}


def review_packet(args):
    """Render explicitly selected context frames/regions; originals remain evidence."""
    path = Path(args.context)
    packet = checked_context(path)
    lookup = {f["id"]: f for f in packet["frames"]}
    ids = args.frame_ids
    check(isinstance(ids, list) and 1 <= len(ids) <= 12 and len(set(ids)) == len(ids)
          and set(ids) <= set(lookup), f"Select 1..12 unique frames; available={list(lookup)}")
    regions = parse_regions(args.region)
    check(len(regions) == 1, "Use one explicit region per review packet; reassess after layout changes")
    index_text(args.question, "review question")
    output = directory(args.output, new=True)
    items = []
    for i, identity in enumerate(ids):
        frame = lookup[identity]
        width, height = png_size(Path(frame["path"]))
        region = regions[0]
        x, y, right, bottom = region_box(region, width, height)
        w, h = right - x, bottom - y
        target = output / f"detail-{i:02d}.png"
        run([args.ffmpeg, "-v", "error", "-i", frame["path"], "-vf", f"crop={w}:{h}:{x}:{y}",
             "-frames:v", "1", str(target)])
        items.append({"frame": frame, "region": region, "crop": file_reference(target)})
    save(output / "review.json", {"context": file_reference(path), "question": args.question,
                                  "items": items, "semantic_inspection": "not_performed"})
    with (output / "index.md").open("x", encoding="utf-8") as stream:
        stream.write("# Focused review\n\n" + args.question + "\n\nCrops are navigation, not new observations.\n\n")
        for item in items:
            f = item["frame"]
            stream.write(f"## {f['actual_seconds']}s\n\n[Original](<{Path(f['path']).as_posix()}>)\n\n"
                         f"![Region](<{Path(item['crop']['path']).as_posix()}>)\n\n")
    return {"output": str(output), "frames": len(items), "semantic_inspection": "not_performed"}


def check_notes(args):
    context_path, notes_path = Path(args.context), Path(args.notes)
    packet_hash = sha(context_path)
    packet = checked_context(context_path)
    check(notes_path.is_absolute() and notes_path.stat().st_size <= 2_000_000, "Absolute notes JSON of at most 2MB required")
    data = read(notes_path)
    validation = validate_notes(data, packet, packet_hash)
    output = directory(args.output, new=True)
    save(output / "checked-notes.json", {"notes": data, "validation": validation, "notes_sha256": sha(notes_path),
                                        "context_path": str(context_path)})
    with (output / "index.md").open("x", encoding="utf-8") as stream:
        stream.write("# 结构化教程记录\n\n来源引用和结构校验通过；以下语义为记录者的观察/推断，"
                     "不是脚本独立识图认证，也不代表 Houdini 已复现。\n\n"
                     f"转录原文与帧引用：[证据包](<{context_path.as_posix()}>)。\n\n")
        lookup = {row["id"]: row for row in packet["frames"]}
        for step in data["steps"]:
            stream.write(f"## {step['id']}\n\n{step['intent']}\n\n"
                         f"范围：{time_label(step['range_seconds'][0])}–{time_label(step['range_seconds'][1])}。\n\n"
                         f"类型：{step['kind']}；证据：{step['evidence_state']}；准备状态：{step['reconstruction_readiness']}。\n\n"
                         f"转录引用：{', '.join(step['speech_ids']) or '无'}。\n\n")
            for ref in step["visual"]:
                row = lookup[ref["frame_id"]]
                stream.write(f"- [{time_label(row['actual_seconds'])}](<{Path(row['path']).as_posix()}>)：{ref['observed']}\n")
            for name in ("inferences", "conflicts", "unknowns"):
                if step[name]:
                    stream.write(f"\n{name}：\n\n" + "\n".join("- " + text for text in step[name]) + "\n")
            if "detail" in step:
                stream.write("\nStructured observations (author assertions):\n\n```json\n" +
                             json.dumps(step["detail"], ensure_ascii=False, indent=2) + "\n```\n")
            stream.write("\n")
    return {**validation, "output": str(output)}


def pinned_file(value, label):
    check(isinstance(value, dict) and set(value) == {"path", "sha256"}, f"Invalid {label} reference")
    path = Path(value["path"])
    check(path.is_absolute() and sha(path) == value["sha256"], f"{label} changed; refresh references explicitly")
    return path


def file_reference(path):
    return {"path": str(path), "sha256": sha(path)}


def index_init(args):
    root = directory(args.frames_dir)
    frames, _, _ = checked_frame_index(root)
    source = Path(frames["source"])
    timing = video_timing(source, args.ffprobe)
    media_duration, _ = probe(source, args.ffprobe)
    transcript = Path(args.transcript) if args.transcript else None
    if transcript:
        transcript_chunks(transcript, frames["source_sha256"])
    data = {"schema": 1, "kind": "tutorial_index", "source": file_reference(source),
            "duration_seconds": media_duration, "video_duration_seconds": timing["end"],
            "overview": file_reference(root / "frames.json"),
            "transcript": file_reference(transcript) if transcript else None,
            "chapters": [], "modules": []}
    output = directory(args.output, new=True)
    save(output / "index.json", data)
    return {"index": str(output / "index.json"), "status": "draft",
            "next": "Read transcript pages and overview images; author chapters/modules, then check-index. No semantic analysis performed."}


def index_sources(path):
    check(path.is_absolute() and path.stat().st_size <= 4_000_000, "Absolute tutorial index of at most 4MB required")
    data = read(path)
    check(set(data) - {"video_duration_seconds"} == {"schema", "kind", "source", "duration_seconds", "overview", "transcript", "chapters", "modules"}
          and data["schema"] == 1 and data["kind"] == "tutorial_index", "Invalid tutorial index schema")
    source = pinned_file(data["source"], "Source")
    overview = pinned_file(data["overview"], "Overview")
    check(overview.name == "frames.json", "Overview must reference frames.json")
    frames, _, _ = checked_frame_index(overview.parent)
    check(Path(frames["source"]) == source and frames["source_sha256"] == data["source"]["sha256"],
          "Overview belongs to another video")
    duration = data["duration_seconds"]
    video_duration = data.get("video_duration_seconds", duration)
    check(type(duration) in (int, float) and math.isfinite(duration) and duration > 0
          and type(video_duration) in (int, float) and math.isfinite(video_duration) and 0 < video_duration <= duration + 0.001
          and all(f["actual_seconds"] < video_duration + 0.001 for f in frames["frames"]), "Invalid source duration")
    chunks = transcript_chunks(pinned_file(data["transcript"], "Transcript"), data["source"]["sha256"]) if data["transcript"] else []
    check(all(c["end"] <= duration + 0.001 for c in chunks),
          "Transcript exceeds media duration; legacy indexes may require regeneration with index-init (preserve original evidence)")
    return data, chunks


def index_ranges(values, duration):
    check(isinstance(values, list) and 1 <= len(values) <= 64, "Use 1..64 source ranges")
    previous = -1
    for pair in values:
        check(isinstance(pair, list) and len(pair) == 2
              and all(type(t) in (int, float) and math.isfinite(t) for t in pair), "Invalid source range")
        start, end = pair
        check(0 <= start < end <= duration and start >= previous, "Source ranges must be ordered, non-overlapping and inside video")
        previous = end


def index_text(value, name):
    check(isinstance(value, str) and 0 < len(value.strip()) <= 4000, f"Invalid {name}")


def checked_index(path):
    data, chunks = index_sources(path)
    chapters, modules = data["chapters"], data["modules"]
    check(isinstance(chapters, list) and 1 <= len(chapters) <= 256, "Author 1..256 chapters")
    check(isinstance(modules, list) and 1 <= len(modules) <= 128, "Author 1..128 modules")
    identities = set()
    previous = -1
    evidence = {}
    for group, rows in (("chapter", chapters), ("module", modules)):
        for row in rows:
            required = {"id", "title", "ranges"} if group == "chapter" else {
                "id", "title", "ranges", "purpose", "inputs", "outputs", "depends_on", "questions", "unknowns", "evidence"}
            check(isinstance(row, dict) and set(row) == required, f"Invalid {group} fields")
            identity = row["id"]
            check(isinstance(identity, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", identity)
                  and identity not in identities, "Index IDs must be unique")
            identities.add(identity)
            index_text(row["title"], "title")
            index_ranges(row["ranges"], data["duration_seconds"])
            if group == "chapter":
                check(len(row["ranges"]) == 1 and row["ranges"][0][0] >= previous, "Chapters must follow playback order without overlap")
                previous = row["ranges"][0][1]
                continue
            index_text(row["purpose"], "purpose")
            for name in ("inputs", "outputs", "depends_on", "questions", "unknowns"):
                string_list(row[name], name)
            check(len(set(row["depends_on"])) == len(row["depends_on"]), "Duplicate dependency")
            check(isinstance(row["evidence"], list) and len(row["evidence"]) <= 64, "Evidence reference budget exceeded")
            evidence[identity] = []
            for ref in row["evidence"]:
                check(isinstance(ref, dict) and set(ref) == {"context", "notes", "step_ids"}, "Invalid module evidence reference")
                context_path = pinned_file(ref["context"], "Context")
                notes_path = pinned_file(ref["notes"], "Notes")
                check(notes_path.stat().st_size <= 2_000_000, "Notes exceed 2MB budget")
                packet = checked_context(context_path)
                check(packet["source_sha256"] == data["source"]["sha256"], "Module evidence belongs to another video")
                check(packet["transcript"] == data["transcript"],
                      "Module evidence uses a different transcript revision")
                notes = read(notes_path)
                validate_notes(notes, packet, ref["context"]["sha256"])
                string_list(ref["step_ids"], "step_ids")
                check(ref["step_ids"] and len(set(ref["step_ids"])) == len(ref["step_ids"]), "Select unique evidence steps")
                lookup = {step["id"]: step for step in notes["steps"]}
                for step_id in ref["step_ids"]:
                    check(step_id in lookup, "Missing evidence step")
                    step = lookup[step_id]
                    check(any(start <= step["range_seconds"][0] < step["range_seconds"][1] <= end
                              for start, end in row["ranges"]), "Evidence step outside module ranges")
                    evidence[identity].append({"context": ref["context"], "notes": ref["notes"], "step": step,
                        "frames": [f for f in packet["frames"] if f["id"] in {v["frame_id"] for v in step["visual"]}]})
    lookup = {m["id"]: m for m in modules}
    visited, active = set(), set()
    def visit(identity):
        check(identity in lookup, "Unknown module dependency")
        check(identity not in active, "Module dependency cycle")
        if identity in visited:
            return
        active.add(identity)
        for dependency in lookup[identity]["depends_on"]:
            visit(dependency)
        active.remove(identity)
        visited.add(identity)
    for identity in lookup:
        visit(identity)
    validate_revision_links(evidence)
    return data, chunks, evidence


def evidence_rows(evidence):
    rows = {}
    for module, items in evidence.items():
        for item in items:
            key = (item["notes"]["sha256"], item["step"]["id"])
            if key not in rows:
                rows[key] = {**item, "module_ids": []}
            if module not in rows[key]["module_ids"]:
                rows[key]["module_ids"].append(module)
    return rows


def validate_revision_links(evidence):
    rows = evidence_rows(evidence)
    subjects = {}
    for key, item in rows.items():
        step = item["step"]
        d = step.get("detail", empty_detail())
        identity = d["subject"]["id"]
        if identity is not None:
            previous = subjects.setdefault(identity, {})
            for field in ("domain", "network_path"):
                value = d["context"][field]
                if value is not None:
                    check(field not in previous or previous[field] == value,
                          "Subject ID reused across contexts; assign distinct IDs or preserve identity as unknown")
                    previous[field] = value
        for link in d["revisions"]:
            target = (link["notes_sha256"], link["step_id"])
            check(target in rows and target != key, "Revision target must be included in module evidence with its exact notes hash")
            old = rows[target]["step"]
            prior = old.get("detail", empty_detail())
            check(d["subject"]["id"] is not None and d["subject"]["id"] == prior["subject"]["id"]
                  and d["context"]["domain"] == prior["context"]["domain"]
                  and d["context"]["network_path"] == prior["context"]["network_path"],
                  "Revision cannot silently merge different subjects/contexts")
            check(old["range_seconds"][1] <= step["range_seconds"][0], "Revision must follow its target; overlapping ranges need narrower evidence")
            check(set(link["fields"]) <= {f["field"] for f in prior["facts"]}, "Revision field missing in target")
    # Strict increasing source ranges above also prohibit cycles. Never erase old claims.


def final_claims(rows, field=None):
    """Conservative, query-scoped author-claim summaries; never infer from latest timestamp."""
    groups = {}
    for item in rows:
        s = item["step"]
        d = s.get("detail", empty_detail())
        for fact in d["facts"]:
            if field and fact["field"] != field:
                continue
            key = (d["subject"]["id"], d["context"]["domain"], d["context"]["network_path"], fact["field"])
            groups.setdefault(key, []).append((item, fact))
    summaries = []
    for (subject, domain, network, name), entries in groups.items():
        replaced = set()
        for item, _ in entries:
            for link in item["step"]["detail"]["revisions"]:
                if name in link["fields"] and link["kind"] != "conflicts_with":
                    replaced.add((link["notes_sha256"], link["step_id"]))
        active = [(i, f) for i, f in entries if (i["notes"]["sha256"], i["step"]["id"]) not in replaced]
        related = [i["step"] for i in rows if "detail" in i["step"]
                   and i["step"]["detail"]["subject"]["id"] == subject
                   and i["step"]["detail"]["context"]["domain"] == domain
                   and i["step"]["detail"]["context"]["network_path"] == network]
        uncertain = any(s["conflicts"] or s["unknowns"] or s["detail"]["gaps"]
                        or any(r["kind"] == "conflicts_with" for r in s["detail"]["revisions"]) for s in related)
        claimed = subject is not None and not uncertain and len(active) == 1 and active[0][1]["state"] == "final_claim"
        summaries.append({"subject": subject, "domain": domain, "network": network, "field": name,
                          "status": "author_final_claim" if claimed else "unknown",
                          "value": active[0][1]["value"] if claimed else None,
                          "candidates": [{"notes_sha256": i["notes"]["sha256"], "step_id": i["step"]["id"],
                                          "value": f["value"], "state": f["state"]} for i, f in active],
                          "scope": "matching indexed observations only; not completeness or semantic certification"})
    return summaries


def comparison_references(rows):
    """Project recorded references without selecting a winner or inventing finality."""
    result = []
    for item in rows:
        frames = {f["id"]: f for f in item["frames"]}
        for ref in item["step"].get("detail", {}).get("references", []):
            result.append({**ref, "notes": item["notes"], "step_id": item["step"]["id"],
                           "module_ids": item["module_ids"],
                           "frames": [frames[key] for key in ref["frame_ids"]]})
    return result


def reference_summary(references):
    final = [r for r in references if r["stage"] == "final_claim" and r["role"] != "intermediate"]
    return {"status": "final_candidates_present" if final else "no_final_reference",
            "reference_count": len(references), "final_candidate_count": len(final),
            "final_candidate_roles": sorted({r["role"] for r in final}),
            "selection": "not_performed",
            "scope": "indexed author claims only; not target coverage, visual similarity or reconstruction readiness",
            "next_action": "Open candidate originals; select the intended result and check overall/detail/material/motion coverage as applicable."
                           if final else "Locate the intended finished result in the source, including opening showcases and later corrections; do not promote the latest frame or a preview automatically."}


@validated_read
def query_notes(args):
    path = Path(args.index)
    revision = sha(path)
    check(getattr(args, "index_sha256", None) in (None, revision), "Index changed between pages")
    data, _, evidence = checked_index(path)
    module = getattr(args, "module", None)
    check(module is None or module in evidence, "Unknown module")
    start, end = getattr(args, "start", None), getattr(args, "end", None)
    check((start is None) == (end is None), "Use start and end together")
    if start is not None:
        index_ranges([[start, end]], data["duration_seconds"])
    rows = list(evidence_rows(evidence).values())
    selected = []
    for item in rows:
        step = item["step"]
        d = step.get("detail", empty_detail())
        if module and module not in item["module_ids"]:
            continue
        if any(getattr(args, option, None) is not None and getattr(args, option) != value for option, value in (
                ("subject", d["subject"]["id"]), ("network", d["context"]["network_path"]), ("domain", d["context"]["domain"]))):
            continue
        if start is not None and not (step["range_seconds"][0] < end and step["range_seconds"][1] > start):
            continue
        field = getattr(args, "field", None)
        if field and field not in {f["field"] for f in d["facts"]} | {g["field"] for g in d["gaps"]}:
            continue
        selected.append(item)
    selected.sort(key=lambda x: (x["step"]["range_seconds"][0], x["notes"]["sha256"], x["step"]["id"]))
    view = getattr(args, "view", "history")
    check(view in ("history", "issues", "references", "final"), "Invalid notes view")
    # Final view deliberately includes ALL matching observations, not only final claims.
    # A later trial/conflict must not disappear behind a previously asserted final value.
    if view == "issues":
        selected = [i for i in selected if i["step"]["unknowns"] or i["step"]["conflicts"] or i["step"].get("detail", {}).get("gaps")]
    elif view == "references":
        selected = [i for i in selected if i["step"].get("detail", {}).get("references")]
    offset, limit = getattr(args, "offset", 0), getattr(args, "limit", 8)
    check(type(offset) is int and 0 <= offset <= len(selected) and type(limit) is int and 1 <= limit <= 100, "Invalid notes page")
    stop = min(len(selected), offset + limit)
    scoped = [m for m in data["modules"] if module is None or m["id"] == module]
    result = {"index_sha256": revision, "source_sha256": data["source"]["sha256"], "view": view,
              "items": selected[offset:stop], "total_items": len(selected), "next_offset": stop if stop < len(selected) else None,
              "module_issues": [{"id": m["id"], "questions": m["questions"], "unknowns": m["unknowns"]} for m in scoped],
              "legacy_observations_without_context": sum("detail" not in i["step"] for i in rows),
              "final_state": "not_computed_review_full_history_and_revision_links",
              "semantic_validation": "agent_assertions_not_independently_verified", "runtime_verification": "not_performed"}
    if view == "final":
        result["field_claims"] = final_claims(selected, getattr(args, "field", None))
    if view == "references":
        # Summary covers the full filtered set, not just this page.
        result["reference_summary"] = reference_summary(comparison_references(selected))
    check(sha(path) == revision, "Index changed during read")
    return bounded_result(result, getattr(args, "max_chars", 24000))


@validated_read
def export_brief(args):
    """Derived navigation only: no new writable source of facts or completion certificate."""
    path = Path(args.index)
    revision = sha(path)
    data, _, evidence = checked_index(path)
    result = {"index": file_reference(path), "summary": index_summary(data, evidence),
              "modules": data["modules"], "observations": list(evidence_rows(evidence).values()),
              "final_state": "not_computed", "runtime_verification": "not_performed"}
    result["comparison_references"] = comparison_references(result["observations"])
    result["reference_summary"] = reference_summary(result["comparison_references"])
    if getattr(args, "require_final_reference", False):
        check(result["reference_summary"]["final_candidate_count"] > 0,
              "No indexed final reference candidate. Review source result images and record their stage/reason; preview/intermediate frames are not a finished target. No export written.")
    check(sha(path) == revision, "Index changed during export")
    output = directory(args.output, new=True)
    save(output / "brief.json", result)
    protocol = Path(__file__).resolve().parents[1] / "references" / "reconstruction.md"
    lines = ["# Tutorial evidence handoff", "", "Derived navigation; not semantic certification or permission to build.",
             "Do not edit this report as a second source of truth. Re-export after notes/index changes.", "",
             f"Source index: [{path.name}](<{path.as_posix()}>)", "",
             f"Reconstruction choices: read the installed skill's [reconstruction protocol](<{protocol.as_posix()}>).", "",
             "## Target reference candidates", "",
             result["reference_summary"]["status"], "", result["reference_summary"]["next_action"], "",
             "Candidate presence does not certify coverage or similarity.", ""]
    for ref in result["comparison_references"]:
        lines += [f"- {ref['role']} / {ref['stage']}: {ref['reason']}",
                  f"  - Source: [{ref['step_id']}](<{Path(ref['notes']['path']).as_posix()}>) / modules: {', '.join(ref['module_ids'])}",
                  "  - Criteria: " + "; ".join(ref["criteria"]),
                  "  - Conditions: " + "; ".join(ref["conditions"]),
                  "  - Limitations: " + "; ".join(ref["limitations"])]
        for f in ref["frames"]:
            lines += [f"  - [{f['actual_seconds']}s](<{Path(f['path']).as_posix()}>)"]

    def recorded(value):
        return "unknown (null)" if value is None else json.dumps(value, ensure_ascii=False)

    def frame_links(item, identities):
        frames = {f["id"]: f for f in item["frames"]}
        return ", ".join(f"[{key} @ {frames[key]['actual_seconds']}s](<{Path(frames[key]['path']).as_posix()}>)"
                         for key in identities) or "none"

    observations = {(i["notes"]["sha256"], i["step"]["id"]): i for i in result["observations"]}
    lines += ["", "## Modules", ""]
    for m in data["modules"]:
        lines += [f"### {m['id']}: {m['title']}", "", m["purpose"], "",
                  "Dependencies: " + ", ".join(m["depends_on"]), "",
                  "Inputs: " + "; ".join(m["inputs"]), "", "Outputs: " + "; ".join(m["outputs"]), ""]
        for issue in m["questions"] + m["unknowns"]:
            lines += ["- Open: " + issue]
        lines += [""]
        for item in result["observations"]:
            if m["id"] not in item["module_ids"]:
                continue
            s = item["step"]
            lines += [f"- [{s['id']}](<{Path(item['notes']['path']).as_posix()}>) {s['range_seconds']}: {s['intent']} "
                      f"(kind={s['kind']}; evidence_state={s['evidence_state']}; reconstruction_readiness={s['reconstruction_readiness']})"]
            if s["speech_ids"]:
                lines += ["  - Speech IDs: " + ", ".join(s["speech_ids"]) +
                          f"; [source transcript](<{Path(data['transcript']['path']).as_posix()}>)."]
            d = s.get("detail")
            if d is not None:
                for group in ("subject", "context"):
                    lines += [f"  - {group.title()} (source video): " + "; ".join(
                        f"{key}={recorded(value)}" for key, value in d[group].items())]
                for fact in d["facts"]:
                    lines += [f"  - Fact: field={recorded(fact['field'])}; value={recorded(fact['value'])}; "
                              f"basis={fact['basis']}; state={fact['state']}; reason={recorded(fact['reason'])}",
                              "    - Source frames: " + frame_links(item, fact["frame_ids"]) +
                              "; speech_ids: " + (", ".join(fact["speech_ids"]) or "none")]
                for gap in d["gaps"]:
                    lines += [f"  - Gap: field={recorded(gap['field'])}; status={gap['status']}; question={recorded(gap['question'])}",
                              "    - Checked source frames: " + frame_links(item, gap["checked_frame_ids"])]
                for link in d["revisions"]:
                    prior = observations[(link["notes_sha256"], link["step_id"])]
                    lines += [f"  - Revision: {link['kind']} [{link['step_id']}](<{Path(prior['notes']['path']).as_posix()}>)"
                              f"; fields: {', '.join(link['fields'])}; reason={recorded(link['reason'])}"
                              f"; notes_sha256={link['notes_sha256']}"]
            for visual in s["visual"]:
                label = "Legacy visual observation" if d is None else "Visual observation"
                lines += [f"  - {label}: {visual['observed']}; source: " + frame_links(item, [visual["frame_id"]])]
            for inference in s["inferences"]:
                lines += ["  - Inference (authored in source notes): " + inference]
            for issue in s["unknowns"]:
                lines += ["  - Unknown: " + issue]
            for issue in s["conflicts"]:
                lines += ["  - Conflict: " + issue]
        lines += [""]
    with (output / "brief.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    return {"output": str(output), "index_sha256": revision, "reference_summary": result["reference_summary"],
            "semantic_validation": "agent_assertions_not_independently_verified"}


@validated_read
def index_link(args):
    """Attach checked notes in a NEW index revision, retaining all earlier references."""
    path = Path(args.index)
    data, _, _ = checked_index(path)
    context_path, notes_path = Path(args.context), Path(args.notes)
    packet = checked_context(context_path)
    check(notes_path.is_absolute() and notes_path.stat().st_size <= 2_000_000, "Absolute notes of at most 2MB required")
    notes = read(notes_path)
    validate_notes(notes, packet, sha(context_path))
    check(packet["source_sha256"] == data["source"]["sha256"] and packet["transcript"] == data["transcript"], "Evidence source/transcript mismatch")
    modules = [m for m in data["modules"] if m["id"] == args.module]
    check(len(modules) == 1, "Unknown module")
    ids = args.step_ids
    string_list(ids, "step_ids")
    check(ids and len(ids) == len(set(ids)), "Select unique evidence steps")
    lookup = {s["id"]: s for s in notes["steps"]}
    for identity in ids:
        check(identity in lookup and any(a <= lookup[identity]["range_seconds"][0] < lookup[identity]["range_seconds"][1] <= b
                                        for a, b in modules[0]["ranges"]), "Selected step missing or outside module ranges")
    modules[0]["evidence"].append({"context": file_reference(context_path), "notes": file_reference(notes_path), "step_ids": ids})
    output = directory(args.output, new=True)
    target = output / "index.json"
    save(target, data)
    # Invalid links leave a diagnostic candidate file, never a success receipt or a replaced source.
    checked_index(target)
    return {"index": str(target), "index_sha256": sha(target), "structural_validation": "passed"}


def index_summary(data, evidence):
    chapter_ranges = [{"start": c["ranges"][0][0], "end": c["ranges"][0][1]} for c in data["chapters"]]
    return {"source_sha256": data["source"]["sha256"], "chapters": data["chapters"],
            "reference_summary": reference_summary(comparison_references(evidence_rows(evidence).values())),
            "chapter_gaps": speech_gaps(chapter_ranges, 0, data["duration_seconds"]),
            "modules": [{"id": m["id"], "title": m["title"], "ranges": m["ranges"],
                         "purpose": m["purpose"], "inputs": m["inputs"], "outputs": m["outputs"],
                         "depends_on": m["depends_on"], "questions": len(m["questions"]),
                         "unknowns": len(m["unknowns"]), "evidence_steps": len(evidence[m["id"]]),
                         "evidence_pending": sum(e["step"]["reconstruction_readiness"] != "ready_for_runtime_check" for e in evidence[m["id"]]),
                         "evidence_conflicts": sum(bool(e["step"]["conflicts"]) for e in evidence[m["id"]])} for m in data["modules"]],
            "structural_validation": "passed", "semantic_validation": "agent_assertions_not_independently_verified",
            "runtime_verification": "not_performed"}


def bounded_result(value, budget):
    check(type(budget) is int and 1000 <= budget <= 160000, "max-chars must be 1000..160000")
    check(len(json.dumps(value, ensure_ascii=False)) <= budget,
          "Read budget exceeded; select a module, reduce transcript page size, or explicitly increase max-chars. No content truncated.")
    return value


@validated_read
def check_index(args):
    data, _, evidence = checked_index(Path(args.index))
    return index_summary(data, evidence)


@validated_read
def read_index(args):
    path = Path(args.index)
    revision = sha(path)
    expected_revision = getattr(args, "index_sha256", None)
    check(expected_revision is None or expected_revision == revision, "Index changed between pages; restart reading the updated index")
    data, chunks, evidence = checked_index(path)
    section = getattr(args, "section", "all")
    offset, limit = getattr(args, "offset", 0), getattr(args, "limit", None)
    check(section in ("all", "speech", "observations"), "Invalid module section")
    check(type(offset) is int and offset >= 0 and (limit is None or type(limit) is int and 1 <= limit <= 100), "Invalid module page")
    check(section != "all" or offset == 0 and limit is None, "Select speech or observations for paging")
    if not args.module:
        check(section == "all" and offset == 0 and limit is None, "Module required for section reads")
        return bounded_result(index_summary(data, evidence), args.max_chars)
    modules = [m for m in data["modules"] if m["id"] == args.module]
    check(len(modules) == 1, "Unknown module")
    module = modules[0]
    selected = [c for c in chunks if any(c["start"] < end and c["end"] > start for start, end in module["ranges"])]
    result = {"module": module, "speech": [speech_chunk_summary(row) for row in selected], "speech_timestamp_basis": BASIS,
              "speech_gaps": [{"range": pair, "gaps": speech_gaps(
                  [c for c in selected if c["start"] < pair[1] and c["end"] > pair[0]], *pair)} for pair in module["ranges"]],
              "observations": evidence[module["id"]], "source_sha256": data["source"]["sha256"], "transcript": data["transcript"],
              "semantic_validation": "agent_assertions_not_independently_verified", "runtime_verification": "not_performed"}
    if section != "all":
        rows = selected if section == "speech" else evidence[module["id"]]
        check(offset <= len(rows), "Module page offset exceeds section length")
        stop = min(len(rows), offset + (limit or 8))
        result = {"module_id": module["id"], "module_title": module["title"], "ranges": module["ranges"],
                  "module_purpose": module["purpose"], "module_inputs": module["inputs"],
                  "module_outputs": module["outputs"], "module_depends_on": module["depends_on"],
                  "index_sha256": revision, "source_sha256": data["source"]["sha256"], "transcript": data["transcript"],
                  "section": section, "items": [speech_chunk_summary(row) for row in rows[offset:stop]] if section == "speech"
                      else rows[offset:stop], "total_items": len(rows), "offset": offset,
                  "next_offset": stop if stop < len(rows) else None, "module_questions": module["questions"],
                  "module_unknowns": module["unknowns"], "speech_timestamp_basis": BASIS,
                  "semantic_validation": "agent_assertions_not_independently_verified", "runtime_verification": "not_performed"}
    timed_chunks = selected if section == "all" else rows[offset:stop] if section == "speech" else []
    timed = [sentence for sentence in timestamp_speech(timed_chunks) if any(
        sentence["start"] < end and sentence["end"] > start for start, end in module["ranges"])]
    if timed:
        result["speech_timestamps"] = timed
    check(sha(path) == revision, "Index changed during read; restart reading the updated index")
    return bounded_result(result, args.max_chars)


@validated_read
def read_transcript(args):
    data, chunks = index_sources(Path(args.index))
    check(type(args.offset) is int and 0 <= args.offset <= len(chunks), "Invalid transcript offset")
    check(type(args.limit) is int and 1 <= args.limit <= 100, "Transcript limit must be 1..100")
    selected = chunks[args.offset:args.offset + args.limit]
    next_offset = args.offset + len(selected)
    result = {"source_sha256": data["source"]["sha256"], "transcript": data["transcript"],
        "speech_timestamp_basis": BASIS, "chunks": [speech_chunk_summary(row) for row in selected], "total_chunks": len(chunks),
        "next_offset": next_offset if next_offset < len(chunks) else None,
        "text_accuracy": "unverified"}
    timed = timestamp_speech(selected)
    if timed:
        result["speech_timestamps"] = timed
    return bounded_result(result, args.max_chars)


def main():
    # CLI JSON is consumed by agents and shell pipelines; Windows locale is not a wire encoding.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True,
                                    parser_class=partial(argparse.ArgumentParser, allow_abbrev=False))
    intake = commands.add_parser("ingest", help="Import a stable local video or separate video/audio tracks without changing originals")
    source = intake.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="Directory with one unambiguous video and optional separate audio")
    source.add_argument("--video", help="Explicit video file; extension is not required")
    intake.add_argument("--audio", help="Explicit separate audio file; only with --video")
    intake.add_argument("--output", required=True, help="New task directory for media.mp4 and source-manifest.json")
    intake.add_argument("--ffmpeg", default=media_executable("ffmpeg"))
    intake.add_argument("--ffprobe", default=media_executable("ffprobe"))
    p = commands.add_parser("prepare")
    p.add_argument("--video", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--start", type=float, default=0)
    p.add_argument("--duration", type=float, required=True)
    p.add_argument("--chunk", type=float, default=30)
    p.add_argument("--overlap", type=float, default=1)
    p.add_argument("--ffmpeg", default=media_executable("ffmpeg"))
    p.add_argument("--ffprobe", default=media_executable("ffprobe"))
    t = commands.add_parser("transcribe")
    t.add_argument("--work", required=True)
    t.add_argument("--model", required=True)
    t.add_argument("--endpoint", default=ENDPOINT, help="Exact ASR HTTPS endpoint for the selected protocol")
    t.add_argument("--protocol", choices=["openai-transcriptions", "qwen-chat-asr", "dashscope-asr"], default="openai-transcriptions")
    t.add_argument("--key-env", default="SILICONFLOW_API_KEY", help="Credential environment variable name, never the credential itself")
    t.add_argument("--allow-upload", action="store_true")
    t.add_argument("--retry-failed", action="store_true")
    t.add_argument("--max-chunks", type=int, default=100, help="Total submissions this invocation, default 100, 1..100")
    t.add_argument("--concurrency", type=int, default=64,
                   help="Concurrent HTTP requests, default 64, 1..64; overload/transport failure drains then lowers to 32/16 for new chunks; never retries failed chunks")
    t.add_argument("--requests-per-second", type=float, default=8,
                   help="Dispatch rate limit, default 8 requests/second, greater than 0 and at most 100")
    t.add_argument("--asr-options-file", help="Absolute JSON file for model-specific ASR options; no credentials")
    t.add_argument("--max-retries", type=int,
                   help="Retry requests authorized for this invocation, default 1 with --retry-failed, otherwise 0")
    t.add_argument("--chunks", nargs="+", help="Submit only these manifest chunk IDs; successes are always skipped")
    e = commands.add_parser("export")
    e.add_argument("--work", required=True)
    e.add_argument("--output", required=True)
    f = commands.add_parser("frames")
    f.add_argument("--work", required=True)
    f.add_argument("--output", required=True)
    f.add_argument("--times", type=float, nargs="+", required=True)
    f.add_argument("--ffmpeg", default=media_executable("ffmpeg"))
    f.add_argument("--ffprobe", default=media_executable("ffprobe"))
    for name in ("scan", "review"):
        s = commands.add_parser(name)
        src = s.add_mutually_exclusive_group(required=True)
        src.add_argument("--work")
        src.add_argument("--video")
        s.add_argument("--output", required=True)
        s.add_argument("--start", type=float, default=0)
        s.add_argument("--duration", type=float, required=name == "review")
        s.add_argument("--interval", type=float, default=30 if name == "scan" else 1)
        s.add_argument("--ffmpeg", default=media_executable("ffmpeg"))
        s.add_argument("--ffprobe", default=media_executable("ffprobe"))
        s.add_argument("--font-file", help="Absolute TTF for thumbnail labels; platform font is detected when omitted")
    c = commands.add_parser("changes")
    c.add_argument("--frames-dir", required=True)
    c.add_argument("--output", required=True)
    c.add_argument("--region", action="append", help="name:x:y:width:height normalized to 0..1; repeat for up to 8 ROIs")
    c.add_argument("--region-mode", choices=("frame-grid", "crop-first"), default="frame-grid",
                   help="crop-first preserves regional detail before scaling; thresholds are not comparable across modes")
    c.add_argument("--analysis-width", type=int, default=320)
    c.add_argument("--analysis-height", type=int, default=180)
    c.add_argument("--pixel-threshold", type=float, default=0.08)
    c.add_argument("--mean-threshold", type=float, default=0.02)
    c.add_argument("--fraction-threshold", type=float, default=0.08)
    c.add_argument("--ffmpeg", default=media_executable("ffmpeg"))
    ctx = commands.add_parser("context")
    ctx.add_argument("--frames-dir", required=True)
    ctx.add_argument("--transcript")
    ctx.add_argument("--start", type=float, required=True)
    ctx.add_argument("--end", type=float, required=True)
    ctx.add_argument("--output", required=True)
    notes = commands.add_parser("check-notes")
    notes.add_argument("--context", required=True)
    notes.add_argument("--notes", required=True)
    notes.add_argument("--output", required=True)
    draft = commands.add_parser("notes-init")
    draft.add_argument("--context", required=True)
    draft.add_argument("--notes", help="Explicitly migrate schema-1 notes into a new output directory")
    draft.add_argument("--output", required=True)
    focus = commands.add_parser("review-packet")
    focus.add_argument("--context", required=True)
    focus.add_argument("--frame-ids", nargs="+", required=True)
    focus.add_argument("--region", action="append", required=True)
    focus.add_argument("--question", required=True)
    focus.add_argument("--output", required=True)
    focus.add_argument("--ffmpeg", default=media_executable("ffmpeg"))
    brief = commands.add_parser("export-brief")
    brief.add_argument("--index", required=True)
    brief.add_argument("--output", required=True)
    brief.add_argument("--require-final-reference", action="store_true",
                       help="Refuse export without an indexed final-result reference candidate; does not certify semantic coverage")
    link = commands.add_parser("index-link")
    for flag in ("index", "module", "context", "notes", "output"):
        link.add_argument("--" + flag, required=True)
    link.add_argument("--step-ids", nargs="+", required=True)
    query = commands.add_parser("query-notes")
    query.add_argument("--index", required=True)
    for flag in ("module", "subject", "network", "domain", "field", "index-sha256"):
        query.add_argument("--" + flag)
    query.add_argument("--start", type=float)
    query.add_argument("--end", type=float)
    query.add_argument("--view", choices=("history", "issues", "references", "final"), default="history")
    query.add_argument("--offset", type=int, default=0)
    query.add_argument("--limit", type=int, default=8)
    query.add_argument("--max-chars", type=int, default=24000)
    init = commands.add_parser("index-init")
    init.add_argument("--frames-dir", required=True)
    init.add_argument("--transcript")
    init.add_argument("--output", required=True)
    init.add_argument("--ffprobe", default=media_executable("ffprobe"))
    for name in ("check-index", "read-index", "read-transcript"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--index", required=True)
        if name != "check-index":
            cmd.add_argument("--max-chars", type=int, default=24000)
        if name == "read-index":
            cmd.add_argument("--module")
            cmd.add_argument("--section", choices=("all", "speech", "observations"), default="all")
            cmd.add_argument("--offset", type=int, default=0)
            cmd.add_argument("--limit", type=int)
            cmd.add_argument("--index-sha256", help="Pin the index revision returned by the first section page")
        if name == "read-transcript":
            cmd.add_argument("--offset", type=int, default=0)
            cmd.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    try:
        if args.command in ("scan", "review"):
            result = frame_job(args, args.command)
        else:
            result = {"ingest": ingest, "prepare": prepare, "transcribe": transcribe, "export": export, "frames": frames,
                      "changes": changes, "context": context, "check-notes": check_notes,
                      "notes-init": notes_init, "query-notes": query_notes, "export-brief": export_brief,
                      "review-packet": review_packet,
                      "index-link": index_link,
                      "index-init": index_init, "check-index": check_index, "read-index": read_index,
                      "read-transcript": read_transcript}[args.command](args)
        print(json.dumps(result, ensure_ascii=False))
    except (Failure, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        # No arbitrary exception/body logging: network errors may contain private data.
        if isinstance(error, Failure) and hasattr(error, "report"):
            print(json.dumps(error.report, ensure_ascii=False))
        print(str(error) if isinstance(error, Failure) else f"Local validation failed ({type(error).__name__})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
