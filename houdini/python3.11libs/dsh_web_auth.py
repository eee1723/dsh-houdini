"""Browser-session authentication for DSH Web loopback RPC clients.

DSH 0.1.2 protects every ``/api`` request with the same signed cookie used by
the browser.  The Web process prints a per-process root URL containing a
launch token; visiting that URL once mints the cookie.  This module performs
that documented exchange for the Houdini-side RPC client and exposes the same
URL so QtWebEngine can establish its independent browser cookie.

The launch token is read from the frontend log but is never copied into the
runtime marker or an exception message.  The marker stores only the byte
offset of the corresponding launch attempt, preventing an old process token
from being selected after a restart.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request


class AuthenticationNotReady(RuntimeError):
    """The current DSH process has not announced its launch URL yet."""


_ANNOUNCED_URL_RE = re.compile(r"(?m)^dsh web:\s+(https?://[^\s()]+)")


class DshWebSession:
    """One cookie jar shared by Houdini's launcher and diagnostics manager."""

    def __init__(self, base_url: str, log_path: str, runtime_state_path: str):
        self.base_url = base_url.rstrip("/")
        self.log_path = log_path
        self.runtime_state_path = runtime_state_path
        self._lock = threading.RLock()
        self._log_offset: int | None = None
        self._launch_url: str | None = None
        self._replace_opener()

    def _replace_opener(self) -> None:
        self._cookies = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(self._cookies),
        )

    def reset(self, *, log_offset: int | None = None) -> None:
        """Forget the previous process cookie and select a new log generation."""
        with self._lock:
            self._log_offset = log_offset
            self._launch_url = None
            self._replace_opener()

    def _runtime_log_offset(self) -> int:
        if self._log_offset is not None:
            return self._log_offset
        try:
            with open(self.runtime_state_path, "r", encoding="utf-8") as handle:
                value = json.load(handle).get("authLogOffset", 0)
            return value if isinstance(value, int) and value >= 0 else 0
        except (OSError, ValueError, AttributeError):
            return 0

    def _valid_launch_url(self, candidate: str) -> bool:
        try:
            expected = urllib.parse.urlsplit(self.base_url)
            parsed = urllib.parse.urlsplit(candidate)
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            return (
                parsed.scheme == expected.scheme
                and parsed.hostname == expected.hostname
                and parsed.port == expected.port
                and parsed.path == "/"
                and len(query.get("token", [])) == 1
                and bool(query["token"][0])
            )
        except (TypeError, ValueError):
            return False

    def launch_url(self) -> str | None:
        """Return the newest valid token URL for this frontend generation."""
        with self._lock:
            if self._launch_url is not None:
                return self._launch_url
            try:
                size = os.path.getsize(self.log_path)
                offset = self._runtime_log_offset()
                if offset > size:
                    offset = 0
                with open(self.log_path, "rb") as handle:
                    handle.seek(offset)
                    text = handle.read().decode("utf-8", errors="replace")
            except OSError:
                return None
            matches = _ANNOUNCED_URL_RE.findall(text)
            for candidate in reversed(matches):
                if self._valid_launch_url(candidate):
                    self._launch_url = candidate
                    return candidate
            return None

    def authorize(self, timeout: int) -> str:
        """Exchange the current process token for a signed cookie."""
        with self._lock:
            launch_url = self.launch_url()
            if launch_url is None:
                raise AuthenticationNotReady(
                    "DSH Web authentication is not ready; waiting for its launch URL"
                )
            request = urllib.request.Request(launch_url, method="GET")
            try:
                with self._opener.open(request, timeout=timeout) as response:
                    response.read()
            except urllib.error.HTTPError as exc:
                # Never include the token-bearing URL or response body here.
                raise RuntimeError(
                    f"DSH Web authentication failed over HTTP {exc.code}"
                ) from exc
            return launch_url

    def open(self, request: urllib.request.Request, *, timeout: int):
        """Open one request with this process's no-proxy cookie jar."""
        with self._lock:
            return self._opener.open(request, timeout=timeout)


_CLIENTS: dict[tuple[str, str, str], DshWebSession] = {}
_CLIENTS_LOCK = threading.Lock()


def shared_session(base_url: str, log_path: str, runtime_state_path: str) -> DshWebSession:
    """Return the process-wide session for one DSH Web endpoint."""
    key = (base_url.rstrip("/"), os.path.abspath(log_path), os.path.abspath(runtime_state_path))
    with _CLIENTS_LOCK:
        session = _CLIENTS.get(key)
        if session is None:
            session = DshWebSession(*key)
            _CLIENTS[key] = session
        return session
