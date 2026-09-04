"""Standard-library regression for DSH 0.1.2 browser-session auth."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

from dsh_web_auth import AuthenticationNotReady, DshWebSession


TOKEN = "current-process-token"
COOKIE = "dsh_browser_test=signed-cookie"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        pass

    def do_GET(self):
        if self.path == f"/?token={TOKEN}":
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", COOKIE + "; Path=/; HttpOnly; SameSite=Strict")
            self.end_headers()
            return
        if self.path == "/" and COOKIE in (self.headers.get("Cookie") or ""):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(401)
        self.end_headers()

    def do_POST(self):
        if self.path != "/api/session.list" or COOKIE not in (self.headers.get("Cookie") or ""):
            self.send_response(401)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        request = json.loads(self.rfile.read(length))
        body = json.dumps({
            "type": "server-response",
            "rpcId": request["rpcId"],
            "result": {"ok": True, "value": {"items": []}},
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory() as raw_dir:
        root = Path(raw_dir)
        log = root / "frontend.log"
        marker = root / "runtime.json"
        stale = "dsh web: http://127.0.0.1:1/?token=stale\n"
        log.write_text(stale, encoding="utf-8")
        offset = log.stat().st_size
        marker.write_text(json.dumps({"authLogOffset": offset}), encoding="utf-8")

        client = DshWebSession(base_url, str(log), str(marker))
        assert client.launch_url() is None
        try:
            client.authorize(2)
        except AuthenticationNotReady as exc:
            assert TOKEN not in str(exc)
        else:
            raise AssertionError("authorization must wait for the current launch URL")

        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"dsh web: {base_url}/?token={TOKEN}\n")
        assert client.launch_url() == f"{base_url}/?token={TOKEN}"

        request = urllib.request.Request(
            base_url + "/api/session.list",
            data=json.dumps({
                "type": "client-request", "rpcId": "fixture",
                "method": "session.list", "payload": {},
            }).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            client.open(request, timeout=2)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
            exc.close()
        else:
            raise AssertionError("RPC must be unauthorized before token exchange")

        client.authorize(2)
        with client.open(request, timeout=2) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        assert decoded["result"] == {"ok": True, "value": {"items": []}}

        client.reset(log_offset=log.stat().st_size)
        assert client.launch_url() is None
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


print("dsh web auth tests passed")
