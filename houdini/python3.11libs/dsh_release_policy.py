"""Read-only official release discovery; never fetch Git or install code.

Release metadata is a publication signal, not installation/compatibility
evidence. Artifact verification and transactional activation are separate gates.
This standard-library module has no Node, Qt, hou or repository dependency.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
import urllib.error
import urllib.request


REPOSITORY = "eee1723/dsh-houdini"
REPOSITORY_API = f"https://api.github.com/repos/{REPOSITORY}"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
_STABLE_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_JSON_LIMIT = 2 * 1024 * 1024


def stable_version(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("expected a stable major.minor.patch version")
    match = _STABLE_VERSION.fullmatch(value)
    if match is None:
        raise ValueError("expected a stable major.minor.patch version")
    return tuple(int(part) for part in match.groups())


def validate_published_release(data: dict) -> dict:
    """Fail closed on drafts, previews and malformed publication metadata."""
    if not isinstance(data, dict):
        raise ValueError("invalid GitHub release response")
    if data.get("draft") is not False or data.get("prerelease") is not False:
        raise ValueError("only explicitly published stable releases are discoverable")
    published_at = data.get("published_at")
    if type(data.get("id")) is not int or data["id"] <= 0 or not isinstance(published_at, str):
        raise ValueError("release has no publication identity")
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("release has no valid publication time") from exc
    if published.tzinfo is None:
        raise ValueError("release publication time must include a timezone")
    tag = data.get("tag_name")
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise ValueError("official release tags must use vMAJOR.MINOR.PATCH")
    version = tag[1:]
    stable_version(version)
    # Build a trusted URL instead of opening arbitrary html_url/body content.
    return {
        "id": data["id"], "version": version, "tag": tag,
        "url": f"{RELEASES_URL}/tag/{tag}",
        "installable": False,
    }


def _read_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "dsh-houdini-release-check",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read(_JSON_LIMIT + 1)
    if len(raw) > _JSON_LIMIT:
        raise ValueError("GitHub release metadata exceeds the size limit")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("invalid GitHub JSON object")
    return data


def latest_stable_release(fetch_json=None) -> dict | None:
    """Consult GitHub's designated latest stable Release, not main or tags.

    A missing latest endpoint means no stable release only after confirming
    that the repository itself is accessible. Rate limits/network errors must
    propagate as unavailable, never as 'up to date'. Call from a worker thread.
    """
    fetch = fetch_json or _read_json
    try:
        data = fetch(f"{REPOSITORY_API}/releases/latest")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        repository = fetch(REPOSITORY_API)
        if not isinstance(repository, dict) or repository.get("full_name", "").lower() != REPOSITORY.lower():
            raise ValueError("could not confirm the official release repository") from exc
        return None
    return validate_published_release(data)


class ReleaseCheck:
    """One in-memory discovery result shared by the workbench and its manager.

    No installation state is written. Concurrent readers never perform I/O;
    concurrent checks join the same request rather than race old results.
    """
    def __init__(self, fetch_release=None):
        self._fetch_release = fetch_release or latest_stable_release
        self._condition = threading.Condition()
        self._state = dict(checking=False, checked=False, release=None, error=None, revision=0)

    def snapshot(self):
        with self._condition:
            return {**self._state, 'release': dict(self._state['release']) if self._state['release'] else None}

    def _begin(self):
        self._state.update(checking=True, checked=False, release=None, error=None,
                           revision=self._state['revision'] + 1)

    def _fetch(self):
        try:
            release, error = self._fetch_release(), None
        except Exception as exc:
            release, error = None, str(exc).strip() or type(exc).__name__
        with self._condition:
            self._state.update(checking=False, checked=True, release=release, error=error,
                               revision=self._state['revision'] + 1)
            self._condition.notify_all()

    def check(self):
        """Worker-only refresh. Errors remain explicit in the shared snapshot."""
        with self._condition:
            if self._state['checking']:
                self._condition.wait_for(lambda: not self._state['checking'])
                return self.snapshot()
            self._begin()
        self._fetch()
        return self.snapshot()

    def start(self):
        """Start discovery without blocking Qt, startup or a status request."""
        with self._condition:
            if self._state['checking']:
                return
            self._begin()
        threading.Thread(target=self._fetch, daemon=True).start()


def update_notice(snapshot, versions):
    """Only a confirmed release newer than every selected version is offered."""
    quiet = {'available': False}
    if snapshot.get('checking') or not snapshot.get('checked') or snapshot.get('error'):
        return quiet
    release = snapshot.get('release')
    if not release or not versions:
        return quiet
    try:
        latest = stable_version(release['version'])
        if latest <= max(stable_version(version) for version in versions):
            return quiet
    except (ValueError, TypeError, KeyError):
        return quiet
    return {'available': True, 'version': release['version']}
