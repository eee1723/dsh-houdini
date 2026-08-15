"""dsh-houdini bridge: an HTTP server running INSIDE Houdini's Python.

The `hou` module only exists inside Houdini, so the dsh plugin talks to this
server and this server executes the agent's Python code in the live session.

Start from Houdini's Python Shell (Windows > Python Shell) — after installing the
package, `python3.11libs` is already on sys.path, so a plain import works:

    import dsh_bridge
    dsh_bridge.start()                      # serves http://127.0.0.1:8765

Or headless with hython:

    hython <path-to-repo>/houdini/python3.11libs/dsh_bridge.py [scene.hip]

Endpoints:
    GET  /health              {}            -> {"ok": true, "houVersion": "..."}
    POST /exec                {"code": str} -> ExecResult
    POST /jobs                {"code": str} -> {"jobId": str}
    POST /jobs/<id>/status    {}            -> JobStatus
    POST /jobs/<id>/cancel    {}            -> JobStatus

ExecResult: {"ok": bool, "stdout": str, "stderr": str,
             "result": <JSON value bound to `__result__`>, "error": <traceback>}

Threading note: `hou` is not thread-safe and must be called from Houdini's
main thread, so ALL code execution is marshaled onto the main thread through
a work queue drained by a pump (a QTimer in GUI mode, the __main__ loop in
headless hython). Execution is therefore strictly serial; background jobs
queue rather than run in parallel — they exist so the agent is not blocked on
renders / simulations. Cancellation is cooperative: a queued job is dropped
BEFORE its code runs (no scene side effects); a running job cannot be killed.
Note this freezes the GUI while code executes — exactly like a native cook.

Hardening: captured stdout/stderr and `__result__` are size-capped, deep
non-JSON values are coerced to `repr`, oversized request bodies are rejected,
and finished jobs are pruned so a long session cannot grow the registry
without bound.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import queue
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import hou  # noqa: F401  (imported so it is bound in the exec namespace)
import dsh_hou_helpers  # noqa: F401  (verb vocabulary: see docs/tool-design.md)

# --- limits (kept small so a runaway agent cannot exhaust Houdini) ----------
_MAX_STREAM_BYTES = 1024 * 1024          # cap captured stdout/stderr per exec
_MAX_RESULT_BYTES = 4 * 1024 * 1024      # cap the serialized __result__
_MAX_BODY_BYTES = 16 * 1024 * 1024       # reject oversized HTTP bodies
_MAX_RESULT_DEPTH = 20                   # recursion depth for __result__ coercion
_MAX_RESULT_ITEMS = 1000                 # items per container before repr fallback
_MAX_JOBS = 1000                         # terminal-job registry cap
_JOB_RETENTION_SECONDS = 600             # keep terminal job results for polling

_exec_lock = threading.Lock()
_jobs: dict[str, dict] = {}              # API-visible job payloads (schema-exact)
_job_meta: dict[str, float] = {}         # jobId -> created/finished timestamp
_jobs_lock = threading.Lock()


class _CappedStringIO(io.StringIO):
    """StringIO that stops growing past `limit`, appending a truncation marker."""

    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit
        self.overflowed = False

    def write(self, s) -> int:
        if self.overflowed:
            return len(s)
        remaining = self.limit - self.tell()
        if len(s) <= remaining:
            return super().write(s)
        super().write(s[:remaining])
        super().write("\n... [dsh-houdini: output truncated]\n")
        self.overflowed = True
        return len(s)


def _jsonable(value, _depth: int = 0):
    """Deep-coerce `value` to a JSON-safe object; non-JSON leaves become `repr`."""
    if _depth > _MAX_RESULT_DEPTH:
        return repr(value)
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_RESULT_ITEMS:
            return repr(value)
        return [_jsonable(v, _depth + 1) for v in value]
    if isinstance(value, dict):
        if len(value) > _MAX_RESULT_ITEMS:
            return repr(value)
        return {str(k): _jsonable(v, _depth + 1) for k, v in value.items()}
    try:
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError):
        return repr(value)


# --- verb tracing ------------------------------------------------------------
# 每个动词（verb）的运行时调用都会被记录：动词名 / 入参 / 出参 / 是否成功 / 耗时。
# 记录随 exec 结果返回（`verbs` 字段），供 agent 和将来的 houdinitrace 视图
# 消费——让动词词表的调用情况「是否成功 + 具体输入输出」清晰可见。
_VERBS: dict[str, object] = {
    "search_tab_menu": dsh_hou_helpers.search_tab_menu,
    "resolve_latest_type": dsh_hou_helpers.resolve_latest_type,
    "tab_create": dsh_hou_helpers.tab_create,
    "find_nodes": dsh_hou_helpers.find_nodes,
    "graph": dsh_hou_helpers.graph,
    "describe": dsh_hou_helpers.describe,
    "connect": dsh_hou_helpers.connect,
    "rename_node": dsh_hou_helpers.rename_node,
    "delete_node": dsh_hou_helpers.delete_node,
    "cook_node": dsh_hou_helpers.cook_node,
    "list_parms": dsh_hou_helpers.list_parms,
    "read_parms": dsh_hou_helpers.read_parms,
    "set_parm": dsh_hou_helpers.set_parm,
}

_VERB_ENTRY_LIMIT = 500       # 单次 exec 最多记录的动词调用数
_VERB_VALUE_CHARS = 2000      # 单个入参/出参序列化后的截断长度


def _verb_value(value, _depth: int = 0):
    """把动词的入参/出参转成紧凑 JSON 安全形式（hou.Node → path，逐层递归）。"""
    if _depth > 8:
        return repr(value)
    if isinstance(value, hou.Node):
        try:
            return {"node": value.path()}
        except Exception:
            return {"node": repr(value)}
    if isinstance(value, (hou.Vector2, hou.Vector3, hou.Vector4)):
        return [float(x) for x in value]
    if isinstance(value, hou.Color):
        return [float(value.r()), float(value.g()), float(value.b()), float(value.a())]
    if isinstance(value, (hou.Matrix3, hou.Matrix4)):
        return [[float(x) for x in row] for row in value]
    if isinstance(value, (list, tuple)):
        if len(value) > 50:
            return repr(value)
        return [_verb_value(v, _depth + 1) for v in value]
    if isinstance(value, dict):
        if len(value) > 50:
            return repr(value)
        return {str(k): _verb_value(v, _depth + 1) for k, v in value.items()}
    return _jsonable(value)


def _clip(obj) -> str:
    """序列化并截断，供 stdout 摘要行使用。"""
    try:
        text = json.dumps(obj, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):
        text = repr(obj)
    return text if len(text) <= _VERB_VALUE_CHARS else text[:_VERB_VALUE_CHARS] + "..."


def _make_tracer(name: str, fn, ledger: list):
    def wrapped(*args, **kwargs):
        if len(ledger) >= _VERB_ENTRY_LIMIT:
            return fn(*args, **kwargs)
        start = time.time()
        args_json = _verb_value(list(args))
        kwargs_json = {str(k): _verb_value(v) for k, v in kwargs.items()}
        try:
            result = fn(*args, **kwargs)
            entry = {
                "verb": name,
                "args": args_json,
                "kwargs": kwargs_json,
                "ok": True,
                "result": _verb_value(result),
                "ms": round((time.time() - start) * 1000, 1),
            }
            ledger.append(entry)
            print(f"[verb] {name}({_clip(args_json)}) -> {_clip(entry['result'])}  ({entry['ms']}ms)")
            return result
        except BaseException as e:  # 记录失败调用并原样抛出，不改变原语义
            ledger.append({
                "verb": name,
                "args": args_json,
                "kwargs": kwargs_json,
                "ok": False,
                "error": str(e),
                "ms": round((time.time() - start) * 1000, 1),
            })
            print(f"[verb] {name}({_clip(args_json)}) -> ERROR: {e}")
            raise
    return wrapped


def run_code(code: str) -> dict:
    """Execute code with `hou` available; capture stdout/stderr and `__result__`.

    Must run on Houdini's main thread (see module docstring) — callers route
    through `_execute`. BaseException is caught so agent code calling
    `sys.exit()` or raising KeyboardInterrupt cannot kill a handler/job thread
    or leave a job stuck in `running` forever.
    """
    verb_ledger: list = []
    namespace = {"hou": hou}
    for _name, _fn in _VERBS.items():
        namespace[_name] = _make_tracer(_name, _fn, verb_ledger)
    stdout = _CappedStringIO(_MAX_STREAM_BYTES)
    stderr = _CappedStringIO(_MAX_STREAM_BYTES)
    error = None
    with _exec_lock:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                exec(compile(code, "<dsh-houdini>", "exec"), namespace)
            except BaseException:
                error = traceback.format_exc()
    envelope = {
        "ok": error is None,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
    }
    if verb_ledger:
        envelope["verbs"] = verb_ledger
    if error is not None:
        envelope["error"] = error
    if "__result__" in namespace:
        result = _jsonable(namespace["__result__"])
        try:
            if len(json.dumps(result, allow_nan=False)) > _MAX_RESULT_BYTES:
                result = f"[dsh-houdini: __result__ serialized to more than {_MAX_RESULT_BYTES} bytes; omitted]"
        except (TypeError, ValueError):
            result = repr(result)
        envelope["result"] = result
    return envelope


# --- main-thread execution queue --------------------------------------------
# `hou` is only safe on Houdini's main thread. HTTP handler / job threads never
# touch `hou` directly: they enqueue work and block until the main-thread pump
# reports back. The pump is a QTimer in GUI mode and the __main__ loop headless.
_work_queue: queue.Queue = queue.Queue()
_pump_active = False   # whether a main-thread pump is draining _work_queue
_pump_timer = None     # GUI-mode QTimer (kept alive; stopped by stop())


def _pump() -> None:
    """Main-thread: run every queued work item, FIFO. Never raises."""
    while True:
        try:
            func, done, holder = _work_queue.get_nowait()
        except queue.Empty:
            return
        try:
            holder["result"] = func()
        except BaseException as exc:  # a failing task must not kill the pump
            holder["error"] = exc
        finally:
            done.set()


def _execute(func):
    """Run `func` on Houdini's main thread and wait for its return value.

    Falls back to inline execution only when no main-thread pump exists
    (interactive hython without the __main__ loop) — the documented entry
    points (GUI menu / Python Shell, `hython dsh_bridge.py`) always have one.
    """
    if not _pump_active:
        return func()
    done = threading.Event()
    holder: dict = {}
    _work_queue.put((func, done, holder))
    done.wait()
    if "error" in holder:
        raise holder["error"]
    return holder["result"]


def _install_gui_pump() -> bool:
    """GUI mode: drain the work queue with a QTimer owned by the main thread.

    Must be called from the main thread (the documented entry points are).
    """
    global _pump_active, _pump_timer
    try:
        try:
            from PySide6 import QtCore
        except ImportError:
            from PySide2 import QtCore
        app = QtCore.QCoreApplication.instance()
        if app is None:
            return False
        timer = QtCore.QTimer(app)
        timer.setInterval(30)
        timer.timeout.connect(_pump)
        timer.start()
        _pump_timer = timer
        _pump_active = True
        return True
    except Exception:
        return False


def _prune_jobs() -> None:
    """Drop expired terminal jobs and cap the registry; queued/running stay."""
    now = time.time()
    with _jobs_lock:
        for job_id in list(_jobs):
            if _jobs[job_id]["status"] in ("done", "failed", "cancelled"):
                if now - _job_meta.get(job_id, now) > _JOB_RETENTION_SECONDS:
                    _jobs.pop(job_id, None)
                    _job_meta.pop(job_id, None)
        if len(_jobs) > _MAX_JOBS:
            terminal = sorted(
                (jid for jid, j in _jobs.items()
                 if j["status"] in ("done", "failed", "cancelled")),
                key=lambda jid: _job_meta.get(jid, 0),
            )
            for job_id in terminal[: len(_jobs) - _MAX_JOBS]:
                _jobs.pop(job_id, None)
                _job_meta.pop(job_id, None)


def _job_body(job_id: str, code: str) -> dict | None:
    """Job work item, run on the main thread via `_execute`.

    Re-checks cancellation AT execution time: a job cancelled while waiting in
    the queue returns None and its code never runs — no scene side effects.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None or job["status"] == "cancelled":
            return None
        job["status"] = "running"
    return run_code(code)


def _run_job(job_id: str, code: str) -> None:
    outcome = _execute(lambda: _job_body(job_id, code))
    if outcome is None:
        return  # cancelled while queued: code never ran, scene untouched
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None or job["status"] == "cancelled":
            return
        job.update(outcome)
        job["status"] = "done" if outcome["ok"] else "failed"
        _job_meta[job_id] = time.time()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep Houdini's console quiet
        pass

    def handle_one_request(self) -> None:  # noqa: N802 (http.server naming)
        try:
            super().handle_one_request()
        except (ConnectionError, TimeoutError):
            # A client (probe, killed browser tab, health check) went away
            # mid-request. Harmless — drop the connection and keep serving.
            self.close_connection = True

    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        if self.path == "/health":
            try:
                self._send({"ok": True, "houVersion": hou.applicationVersionString()})
            except Exception:
                self._send({"ok": False, "error": traceback.format_exc()}, status=500)
            return
        self._send({"ok": False, "error": f"unknown endpoint {self.path}"}, status=404)

    def do_POST(self) -> None:  # noqa: N802 (http.server naming)
        try:
            length = int(self.headers.get("content-length") or 0)
            if length > _MAX_BODY_BYTES:
                self._send(
                    {"ok": False, "error": f"request body too large ({length} > {_MAX_BODY_BYTES})"},
                    status=413,
                )
                return
            body = json.loads(self.rfile.read(length) or b"{}")
            self._route(body)
        except Exception:
            self._send({"ok": False, "error": traceback.format_exc()}, status=500)

    def _route(self, body: dict) -> None:
        if self.path == "/exec":
            code = str(body.get("code", ""))
            self._send(_execute(lambda: run_code(code)))
            return
        if self.path == "/jobs":
            job_id = uuid.uuid4().hex[:12]
            with _jobs_lock:
                _jobs[job_id] = {
                    "jobId": job_id, "status": "queued",
                    "ok": False, "stdout": "", "stderr": "",
                }
                _job_meta[job_id] = time.time()
            threading.Thread(target=_run_job, args=(job_id, str(body.get("code", ""))), daemon=True).start()
            _prune_jobs()
            self._send({"jobId": job_id})
            return
        parts = [p for p in self.path.split("/") if p]
        if len(parts) == 3 and parts[0] == "jobs":
            with _jobs_lock:
                job = _jobs.get(parts[1])
                if job is None:
                    self._send({"ok": False, "error": f"unknown job {parts[1]}"}, status=404)
                    return
                if parts[2] == "cancel" and job["status"] in ("queued", "running"):
                    job["status"] = "cancelled"
                    _job_meta[parts[1]] = time.time()
                if parts[2] in ("status", "cancel"):
                    self._send(dict(job))
                    return
        self._send({"ok": False, "error": f"unknown endpoint {self.path}"}, status=404)


_server: ThreadingHTTPServer | None = None


def stop() -> None:
    """Stop the in-process bridge server and GUI pump (if any); idempotent."""
    global _server, _pump_active, _pump_timer
    server = _server
    _server = None
    if server is not None:
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass
    timer = _pump_timer
    _pump_timer = None
    _pump_active = False
    if timer is not None:
        try:
            timer.stop()
        except Exception:
            pass


def start(port: int = 8765, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """Start the bridge in a daemon thread; restarts if one is already running.

    In GUI mode call this from the main thread (Python Shell / menu — the
    documented entry points are) so the execution pump binds to the Qt loop.
    """
    global _server
    stop()
    server = ThreadingHTTPServer((host, port), _Handler)
    _server = server
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True).start()
    try:
        ui = hou.isUIAvailable()
    except Exception:
        ui = False
    if ui and not _install_gui_pump():
        print("[dsh-houdini] WARNING: no main-thread pump; code will run on "
              "handler threads, which is NOT safe for hou in GUI mode")
    print(f"[dsh-houdini] bridge serving on http://{host}:{port}")
    return server


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        hou.hipFile.load(sys.argv[1])
        print(f"[dsh-houdini] loaded scene {sys.argv[1]}")
    start()
    _pump_active = True  # headless: the main thread below IS the pump
    while True:  # hython exits when the script returns; keep the session alive
        _pump()
        time.sleep(0.05)
