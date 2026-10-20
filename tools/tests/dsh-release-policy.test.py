"""Offline publication-boundary tests; no Git, Node, Qt, hou or network needed."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import threading
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


# The workbench and Version & Updates share one process-local observation. A
# slow/offline discovery must not become a prerequisite for opening the page.
checker = policy.ReleaseCheck(fetch_release=lambda: release)
initial = checker.snapshot()
assert initial["checking"] is False and initial["checked"] is False
assert initial["release"] is None and not initial["error"]
checker.check()
ready = checker.snapshot()
assert ready["checking"] is False and ready["checked"] is True
assert ready["release"] == release and not ready["error"]
assert ready["revision"] > initial["revision"]
ready["release"]["version"] = "99.99.99"
assert checker.snapshot()["release"]["version"] == release["version"], "a consumer changed shared release evidence"

entered, finish, completed, manual_started = (threading.Event() for _ in range(4))
discovery_calls = []
def delayed_discovery():
    discovery_calls.append(True)
    entered.set()
    assert finish.wait(5), "fixture failed to release the background query"
    return release

slow = policy.ReleaseCheck(fetch_release=delayed_discovery)
slow.start()
assert entered.wait(2), "background release discovery did not start"
inflight = slow.snapshot()
assert inflight["checking"] is True and inflight["release"] is None
# A second page and a manual refresh may reach the same in-flight observation.
# Neither may launch a second network query or queue another one for later.
slow.start()
def manual_refresh():
    manual_started.set()
    try:
        slow.check()
    finally:
        completed.set()
manual = threading.Thread(target=manual_refresh, daemon=True)
manual.start()
assert manual_started.wait(2)
completed.wait(.03)  # Give the manual reader its turn while discovery is held.
assert len(discovery_calls) == 1
finish.set()
assert completed.wait(3)
manual.join(1)
# check() may return immediately when another worker owns the request. Wait for
# its completion through the public snapshot rather than requiring a Future.
deadline = threading.Event()
for _ in range(100):
    if not slow.snapshot()["checking"]:
        break
    deadline.wait(.02)
assert slow.snapshot()["release"] == release
assert len(discovery_calls) == 1, "in-flight refresh was repeated after completion"

answers = iter([release, TimeoutError("offline release fixture"), None])
def sequential_discovery():
    answer = next(answers)
    if isinstance(answer, Exception):
        raise answer
    return answer
flaky = policy.ReleaseCheck(fetch_release=sequential_discovery)
flaky.check()
before_failure = flaky.snapshot()
flaky.check()
failed = flaky.snapshot()
assert failed["checking"] is False and failed["checked"] is True
assert failed["release"] is None and "offline release fixture" in failed["error"]
assert failed["revision"] > before_failure["revision"]
assert policy.update_notice(failed, ["0.1.0"]) == {"available": False}, "offline is not an actionable release"
flaky.check()
absent = flaky.snapshot()
assert absent["checked"] is True and absent["release"] is None and not absent["error"]
assert policy.update_notice(absent, ["0.1.0"]) == {"available": False}

available = {**initial, "checking": False, "checked": True, "release": release, "error": None}
assert policy.update_notice(initial, ["0.1.0"]) == {"available": False}
assert policy.update_notice(available, ["0.1.0"]) == {"available": True, "version": "0.2.0"}
assert policy.update_notice(available, ["0.2.0"]) == {"available": False}
assert policy.update_notice(available, ["0.3.0"]) == {"available": False}
assert policy.update_notice(available, ["0.1.0", "0.2.0"]) == {"available": False}, "pending latest must not prompt duplicate installation"
assert policy.update_notice(available, ["0.1.0", "0.1.9"]) == {"available": True, "version": "0.2.0"}
assert policy.update_notice(available, ["0.3.0", "0.1.0"]) == {"available": False}, "loaded/current order cannot offer a downgrade"
numeric_release = {**release, "version": "0.10.0", "tag": "v0.10.0"}
assert policy.update_notice({**available, "release": numeric_release}, ["0.9.9"]) == {"available": True, "version": "0.10.0"}
assert policy.update_notice({**available, "release": numeric_release}, ["0.9.9", "0.10.0"]) == {"available": False}

print("shared release observation: nonblocking start, in-flight coalescing, immutable snapshots, offline clearing and pending/loaded version comparisons passed")
