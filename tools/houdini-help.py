"""Read one exact page from an installed SideFX help archive. No hou or writes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

TOPICS = frozenset({"hom", "vex", "nodes"})
MAX_PAGE_BYTES = 4 * 1024 * 1024


def read_help(request: dict) -> dict:
    if not isinstance(request, dict) or set(request) - {"hfs", "version", "ref", "offset", "limit", "expected_sha256"}:
        raise ValueError("Unknown help request fields")
    ref = request.get("ref")
    if not isinstance(ref, str) or not 1 <= len(ref) <= 512 or not re.fullmatch(r"[A-Za-z0-9_./+-]+", ref):
        raise ValueError("Use an exact relative help reference, for example hom/hou/Node, vex/functions/noise or nodes/sop/box")
    parts = ref.split("/")
    if len(parts) < 2 or parts[0] not in TOPICS or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Help reference must name a page under hom/, vex/ or nodes/; traversal is not allowed")
    member = "/".join(parts[1:])
    if member.endswith(".txt"):
        member = member[:-4]
    member += ".txt"
    reference = parts[0] + "/" + member[:-4]
    offset, limit = request.get("offset", 0), request.get("limit", 6000)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 16000:
        raise ValueError("offset must be a nonnegative integer; limit must be 1..16000 characters")
    expected = request.get("expected_sha256")
    if expected is not None and (not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)):
        raise ValueError("expected_sha256 must be a lowercase SHA-256 returned by this help reader")
    hfs_value = request.get("hfs")
    if not isinstance(hfs_value, str) or not Path(hfs_value).is_absolute():
        raise ValueError("An exact installed Houdini directory is required")
    version = request.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"2[12]\.0\.\d+", version):
        raise ValueError("An exact supported Houdini build is required")
    hfs = Path(hfs_value).resolve(strict=True)
    archive = (hfs / "houdini" / "help" / (parts[0] + ".zip")).resolve(strict=True)
    if not archive.is_relative_to(hfs):
        raise ValueError("Help archive is outside the selected Houdini installation")
    with zipfile.ZipFile(archive) as bundle:
        matches = [info for info in bundle.infolist() if info.filename == member]
        if len(matches) != 1:
            raise ValueError("Exact help page was not found" if not matches else "Archive has duplicate entries for this help page")
        info = matches[0]
        if info.is_dir() or info.file_size > MAX_PAGE_BYTES:
            raise ValueError("Help page exceeds the supported 4 MiB page budget")
        with bundle.open(info) as stream:
            raw = stream.read(MAX_PAGE_BYTES + 1)
        if len(raw) > MAX_PAGE_BYTES:
            raise ValueError("Help page exceeds the supported 4 MiB page budget")
    digest = hashlib.sha256(raw).hexdigest()
    if expected is not None and expected != digest:
        raise ValueError("Help source changed since the preceding page; restart from offset 0")
    text = raw.decode("utf-8-sig")
    if offset > len(text):
        raise ValueError("offset is beyond this help page")
    end = min(offset + limit, len(text))
    source = {"hfs": str(hfs), "houdini_version": version, "archive": str(archive),
              "member": member, "sha256": digest, "bytes": len(raw),
              "authority": "SideFX help files from the selected installed Houdini build"}
    return {"reference": reference, "source": source, "text": text[offset:end],
            "offset": offset, "end_offset": end, "total_characters": len(text),
            "offset_unit": "Unicode code points", "truncated": end < len(text),
            "next": {"kind": "help", "ref": reference, "offset": end, "limit": limit,
                     "houdini_installation": str(hfs), "expected_sha256": digest} if end < len(text) else None,
            "scope": "Installed reference text only; no scene observation, HOM execution or semantic verification"}


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("Help request exceeds its input budget")
        result = read_help(json.loads(raw.decode("utf-8")))
        response, status = {"ok": True, "result": result}, 0
    except (ValueError, OSError, zipfile.BadZipFile, UnicodeError) as error:
        response, status = {"ok": False, "error": str(error)}, 1
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
