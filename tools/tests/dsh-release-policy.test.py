"""Offline publication-boundary tests; no Git, Node, Qt, hou or network needed."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import urllib.error
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))
import dsh_release_policy as policy


def rejects(fn, error=ValueError):
    try:
        fn()
    except error:
        return
    raise AssertionError("invalid publication was accepted")


published = {
    "id": 42, "draft": False, "prerelease": False,
    "published_at": "2026-09-09T00:00:00Z", "tag_name": "v0.2.0",
    "html_url": "https://untrusted.example/execute", "body": "not instructions",
}
release = policy.validate_published_release(published)
assert release["version"] == "0.2.0" and release["installable"] is False
assert release["url"] == "https://github.com/eee1723/dsh-houdini/releases/tag/v0.2.0"
for field, value in (
    ("draft", True), ("prerelease", True), ("draft", 0), ("prerelease", None),
    ("published_at", None), ("published_at", ""), ("published_at", "2026-09-09"),
    ("published_at", "not a date"), ("published_at", {}),
    ("id", True), ("id", -1), ("tag_name", "main"),
    ("tag_name", "v0.2.0-rc.1"), ("tag_name", "v0.2.0+local"),
    ("tag_name", "v01.2.0"), ("tag_name", "v0.2.0/../../main"),
):
    rejects(lambda: policy.validate_published_release({**published, field: value}))
for value in (None, [], {}, {"tag_name": "v0.2.0"}):
    rejects(lambda: policy.validate_published_release(value))
assert policy.stable_version("0.10.0") > policy.stable_version("0.9.9")
assert policy.stable_version("2.0.0") > policy.stable_version("1.99.99")
for value in ("latest", "1.2", "1.2.3\n", "v1.2.3", "1.2.3-beta", "9" * 70 + ".0.0", None):
    rejects(lambda: policy.stable_version(value))

calls = []
def fetch(url):
    calls.append(url)
    return published
assert policy.latest_stable_release(fetch) == release
assert calls == [policy.REPOSITORY_API + "/releases/latest"]

def http_error(url, status):
    return urllib.error.HTTPError(url, status, "fixture", {}, None)

calls.clear()
def no_release(url):
    calls.append(url)
    if url.endswith("/releases/latest"):
        raise http_error(url, 404)
    return {"full_name": policy.REPOSITORY}
assert policy.latest_stable_release(no_release) is None
assert calls == [policy.REPOSITORY_API + "/releases/latest", policy.REPOSITORY_API]

for code in (403, 404, 429, 500):
    def unavailable(url):
        raise http_error(url, code)
    rejects(lambda: policy.latest_stable_release(unavailable), urllib.error.HTTPError)
def timeout(url):
    raise TimeoutError("fixture")
rejects(lambda: policy.latest_stable_release(timeout), TimeoutError)

def wrong_repo(url):
    if url.endswith("/releases/latest"):
        raise http_error(url, 404)
    return {"full_name": "someone/else"}
rejects(lambda: policy.latest_stable_release(wrong_repo))

# Real JSON transport's resource limits and headers, without opening a socket.
requests = []
def open_fixture(request, timeout):
    requests.append((request, timeout))
    return io.BytesIO(json.dumps(published).encode())
with patch.object(policy.urllib.request, "urlopen", open_fixture):
    assert policy.latest_stable_release() == release
assert requests[0][1] == 15
assert requests[0][0].get_header("User-agent") == "dsh-houdini-release-check"
for raw in (b"[1]", b"not json", b" " * (policy._JSON_LIMIT + 1)):
    with patch.object(policy.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(raw)):
        rejects(lambda: policy.latest_stable_release())

print("release publication policy tests passed")
