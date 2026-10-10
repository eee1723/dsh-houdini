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
    GET  /health              {}            -> version, raw gate, and active job counts
    POST /exec                admission envelope -> ExecResult
    POST /jobs                admission envelope -> {"jobId": str}
    POST /jobs/<id>/status    identity + contract envelope -> JobStatus
    POST /jobs/<id>/cancel    identity + contract envelope -> JobStatus

The admission envelope is {"code", "owner_session", "owner_call",
"expected_contract", "request_ref"}: every execution and job submission carries
the Host session identity, the expected contract and a one-time ticket prepared
via /requests/prepare. Missing or mistyped fields return 400; a well-formed
envelope from a different Host generation returns 409; untracked HTTP execution
is not supported. Job status/cancel carry {"owner_session", "owner_call",
"expected_contract"} and are authorized by the owning session only.

ExecResult includes ``ok/stdout/stderr/result/error`` plus the verb ledger,
Raw Gate classification, rollback outcome, advisory text and produced image
paths. The Host relays images through DSH native attachments without creating
workspace image copies.

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

import hashlib
import json
import os
import sys
import queue
import threading
import time
import traceback
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import hou  # noqa: F401  (imported so it is bound in the exec namespace)
import dsh_hou_helpers  # noqa: F401  (verb vocabulary: see docs/tool-design.md)

# Cached while this module is imported on Houdini's owning thread. HTTP handler
# threads must not call HOM, including for seemingly harmless health metadata.
_HOU_VERSION = hou.applicationVersionString()
_HOU_THREAD_ID = threading.get_ident()
# sys.exec_prefix is the interpreter actually embedded by this Houdini process;
# sys.executable is houdini/hython, not the standalone Python used by media work.
# Cache HOM once here. Health handlers only read these installation facts.
_PYTHON_RUNTIME = {
    "hfs": hou.getenv("HFS") or "",
    "python": os.path.normpath(os.path.join(sys.exec_prefix, "python.exe") if os.name == "nt" else
                               os.path.join(sys.exec_prefix, "bin", "python3")),
    "pythonVersion": ".".join(str(value) for value in sys.version_info[:3]),
    "executable": sys.executable,
}
# Bump when operation semantics change without renaming verbs. Host generation
# reads the matching version declaration in docs/tool-design.md.
_EXECUTION_CONTRACT_VERSION = 98
from dsh_managed_runtime import executor_identity
_EXECUTOR_ID = executor_identity()
_RUNTIME_ID = uuid.uuid4().hex
from dsh_requests import RequestRegistry
_request_registry = RequestRegistry(_RUNTIME_ID)
# --- limits (kept small so a runaway agent cannot exhaust Houdini) ----------
_MAX_BODY_BYTES = 16 * 1024 * 1024       # reject oversized HTTP bodies
_MAX_JOBS = 1000                         # terminal-job registry cap
_MAX_ACTIVE_JOBS = 32                    # bound queued workers, not only history
_JOB_RETENTION_SECONDS = 600             # keep terminal job results for polling

_jobs: dict[str, dict] = {}              # API-visible job payloads (schema-exact)
_job_meta: dict[str, float] = {}         # jobId -> created/finished timestamp
_jobs_lock = threading.Lock()

# /media 端点（图片字节回传）的限制
_MEDIA_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".webp"}
_MEDIA_MAX_BYTES = 64 * 1024 * 1024
_MEDIA_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".bmp": "image/bmp", ".tga": "image/x-tga", ".webp": "image/webp",
}


# Execution vocabulary and completed facts belong to the Houdini runtime.
# Private aliases preserve existing fixtures and Python Shell diagnostics.
from dsh_execution import ExecutionRuntime, _VERBS, _verb_help, _make_tracer
from dsh_execution_results import _artifact_candidates, _operation_summary
from dsh_code_analysis import (
    _raw_hou_calls, _raw_usage_analysis, _gate_message, _blocking_host_traversal_message,
)

_runtime = ExecutionRuntime(_HOU_THREAD_ID, _RUNTIME_ID, _EXECUTOR_ID)
_VERB_NAMES = tuple(sorted(_VERBS))
_VERB_CATALOG_HASH = hashlib.sha256("\n".join(_VERB_NAMES).encode("utf-8")).hexdigest()
_raw_gate = True


def set_raw_gate(on: bool) -> str:
    """开关 raw-hou gate（不进 exec 命名空间，用户从 Python Shell 调）。"""
    global _raw_gate
    _raw_gate = bool(on)
    return f"raw-hou gate {'ON' if _raw_gate else 'OFF'}"


def run_code(code: str, allow_raw: str | None = None,
             owner_session: str | None = None, owner_call: str | None = None,
             read_only: bool = False) -> dict:
    """Main-thread execution entry shared by HTTP and isolated Python callers."""
    return _runtime.run_code(code, allow_raw, owner_session, owner_call, read_only, raw_gate=_raw_gate)


def _contract_error(expected) -> tuple[int, str] | None:
    """Shared contract-envelope validation for execution and job control.

    A missing or malformed envelope is a 400 (bad request shape); a well-formed
    envelope from a different Host generation is a 409 that must fire before any
    scene execution, ticket consumption or job state change. The version must be
    a strict integer: Python bools are int subclasses and are rejected here so a
    mistyped field reads as 400, not as a version mismatch.
    """
    version = expected.get("version") if isinstance(expected, dict) else None
    if (not isinstance(expected, dict) or set(expected) != {"version", "hash"}
            or type(version) is not int
            or not isinstance(expected.get("hash"), str)):
        return 400, "expected_contract with integer version and hash string is required"
    if expected != {"version": _EXECUTION_CONTRACT_VERSION, "hash": _VERB_CATALOG_HASH}:
        return 409, "execution contract mismatch; Repair and restart runtime"
    return None


def _owner_error(body: dict) -> tuple[int, str] | None:
    """Host session identity validation; values are taken verbatim, never coerced."""
    owner_session = body.get("owner_session")
    owner_call = body.get("owner_call")
    if (not isinstance(owner_session, str) or not owner_session.strip()
            or not isinstance(owner_call, str) or not owner_call.strip()):
        return 400, "owner_session and owner_call must be nonempty strings from the Host tool context"
    return None


# --- main-thread execution queue --------------------------------------------
# `hou` is only safe on Houdini's main thread. HTTP handler / job threads never
# touch `hou` directly: they enqueue work and block until the main-thread pump
# reports back. The pump is a QTimer in GUI mode and the __main__ loop headless.
_work_queue: queue.Queue = queue.Queue()
_pump_active = False   # whether a main-thread pump is draining _work_queue
_pump_timer = None     # GUI-mode QTimer (kept alive; stopped by stop())


def _pump() -> None:
    """Main-thread FIFO, yielding between tasks after an 8ms GUI time slice.

    A single HOM operation can exceed the slice; it is never interrupted here.
    """
    if threading.get_ident() != _HOU_THREAD_ID:
        raise RuntimeError("Houdini pump must run on its owning thread")
    deadline = time.monotonic() + 0.008
    while time.monotonic() < deadline:
        try:
            func, done, holder = _work_queue.get_nowait()
        except queue.Empty:
            return
        if holder.get("cancelled"):
            done.set()
            continue
        try:
            holder["result"] = func()
        except BaseException as exc:  # a failing task must not kill the pump
            holder["error"] = exc
        finally:
            done.set()


def _execute(func, timeout=None):
    """Run `func` on Houdini's main thread and wait for its return value.

    Owning-thread callers may execute inline (including disposable hython).
    Worker callers must have a live pump; never fall back to worker-thread HOM.
    """
    if threading.get_ident() == _HOU_THREAD_ID:
        return func()
    if not _pump_active:
        raise RuntimeError("Houdini main-thread pump is unavailable; refusing execution on a worker thread")
    done = threading.Event()
    holder: dict = {}
    _work_queue.put((func, done, holder))
    deadline = time.monotonic() + timeout if timeout is not None else None
    while not done.wait(0.25):
        if deadline is not None and time.monotonic() >= deadline:
            holder['cancelled'] = True
            raise TimeoutError('Houdini main-thread queue is busy; metadata observation expired')
        if not _pump_active:
            holder["cancelled"] = True
            raise RuntimeError("Houdini main-thread pump stopped before queued execution completed")
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


def _public_job(job: dict) -> dict:
    """API-visible snapshot of a job record; internal owner fields never leak
    into status/cancel responses or tool output schemas."""
    return {key: value for key, value in job.items() if key not in ("owner_session", "owner_call")}


def _request_status(ref, owner):
    """Admission retention and execution-result retention are separate facts."""
    receipt = _request_registry.status(ref, owner)
    if receipt.get('jobId'):
        with _jobs_lock:
            job = _jobs.get(receipt['jobId'])
            if job is not None and job.get('owner_session') == owner:
                receipt['job_status'] = job['status']
                receipt['job_result_available'] = job['status'] in ('done', 'failed', 'cancelled')
            elif receipt.get('job_finished'):
                receipt['job_result_available'] = False
    return receipt


def _job_activity() -> dict:
    """Return non-terminal job counts without exposing job payloads."""
    with _jobs_lock:
        queued = sum(1 for job in _jobs.values() if job.get("status") == "queued")
        running = sum(1 for job in _jobs.values() if job.get("status") == "running")
    return {
        "activeJobs": queued + running,
        "queuedJobs": queued,
        "runningJobs": running,
    }


def _job_body(job_id: str, code: str, allow_raw: str | None = None,
              owner_session: str | None = None,
              owner_call: str | None = None) -> dict | None:
    """Job work item, run on the main thread via `_execute`.

    Re-checks cancellation AT execution time: a job cancelled while waiting in
    the queue returns None and its code never runs — no scene side effects.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None or job["status"] == "cancelled":
            return None
        job["status"] = "running"
    return run_code(code, allow_raw, owner_session, owner_call)


def _run_job(job_id: str, code: str, allow_raw: str | None = None,
             owner_session: str | None = None,
             owner_call: str | None = None, request_ref: str | None = None) -> None:
    try:
        try:
            outcome = _execute(
                lambda: _job_body(job_id, code, allow_raw, owner_session, owner_call)
            )
        except BaseException:
            outcome = {"ok": False, "stdout": "", "stderr": "", "error": traceback.format_exc()}
        if outcome is None:
            return  # cancelled while queued: code never ran, scene untouched
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None or job["status"] == "cancelled":
                return
            job.update(outcome)
            job["status"] = "done" if outcome["ok"] else "failed"
            _job_meta[job_id] = time.time()
    finally:
        if request_ref is not None:
            _request_registry.finish_job(request_ref)


def _capture_ui(options, owner_session, request_ref, owner_call=None):
    """Worker orchestration only: HOM stays in staged queue entries.

    A normal GUI event-loop turn builds native controls between preparation
    and capture. The per-request state is a local closure, not a new registry.
    """
    state = None
    facts = None
    error = None
    try:
        import dsh_ui_capture as capture
        def prepare():
            if not _request_registry.running(request_ref):
                raise RuntimeError('UI capture request is no longer queued; no new capture dispatched')
            import dsh_hou_helpers as helpers
            with helpers._execution_owner(owner_session, owner_call):
                return capture.prepare_ui_capture(**options)
        state = _execute(prepare)
        if not state['ready'].wait(10):
            raise TimeoutError('Houdini native UI did not finish a normal GUI refresh before capture')
        _execute(lambda: capture.refresh_ui_capture(state))
        if not state['ready'].wait(10):
            raise TimeoutError('Houdini native controls did not finish displaying their bound values')
        facts = _execute(lambda: capture.finish_ui_capture(state))
    except BaseException as exc:
        error = str(exc)
        facts = getattr(exc, 'evidence', None)
        if state is not None and not state.get('closed'):
            try:
                cleanup = _execute(lambda: capture.abort_ui_capture(state))
                if isinstance(cleanup, dict):
                    facts = {**(facts or {}), **cleanup}
            except BaseException as cleanup_error:
                facts = {**(facts or {}), 'user_state_restored': False,
                    'restore_errors': [str(cleanup_error)]}
                error += '; owned UI cleanup failed: ' + str(cleanup_error)
    try:
        return _execute(lambda: _runtime.ui_observation_result(facts, error, owner_session))
    except BaseException as observation_error:
        # No worker-thread HOM fallback and no invented execution identity.
        # The HTTP route still completes a dispatched request's real error.
        return {'ok': False, 'stdout': '', 'stderr': '', 'result': facts or {},
            'error': (error + '; ' if error else '') + 'UI observation unavailable: ' + str(observation_error)}


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

    def _health(self) -> dict:
        return {
            "ok": True, "houVersion": _HOU_VERSION, "rawGate": _raw_gate,
            "executionContractVersion": _EXECUTION_CONTRACT_VERSION, "runtimeId": _RUNTIME_ID,
            "executorId": _EXECUTOR_ID,
            "runtime": _PYTHON_RUNTIME,
            "verbCatalog": {"hash": _VERB_CATALOG_HASH, "count": len(_VERB_NAMES), "names": list(_VERB_NAMES)},
            "activeRequests": _request_registry.active_count(),
            **_job_activity(),
        }

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        if not self._check_executor():
            return
        if self.path == "/health":
            try:
                self._send(self._health())
            except Exception:
                self._send({"ok": False, "error": traceback.format_exc()}, status=500)
            return
        # Relay request-produced image bytes to Host native attachments; no HOM.
        if urllib.parse.urlparse(self.path).path == "/media":
            try:
                params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                target = os.path.abspath(params.get("path", [""])[0])
                ext = os.path.splitext(target)[1].lower()
                if ext not in _MEDIA_EXTS:
                    self._send({"ok": False, "error": f"media type not allowed: {ext or '(none)'}"}, status=403)
                    return
                if not os.path.isfile(target):
                    self._send({"ok": False, "error": f"no such file: {target}"}, status=404)
                    return
                size = os.path.getsize(target)
                if size > _MEDIA_MAX_BYTES:
                    self._send({"ok": False, "error": f"file too large ({size} > {_MEDIA_MAX_BYTES})"}, status=413)
                    return
                with open(target, "rb") as fh:
                    data = fh.read(_MEDIA_MAX_BYTES + 1)
                if len(data) > _MEDIA_MAX_BYTES:
                    self._send({"ok": False, "error": "media grew beyond size limit"}, status=413)
                    return
                self.send_response(200)
                self.send_header("content-type", _MEDIA_MIME.get(ext, "application/octet-stream"))
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self._send({"ok": False, "error": traceback.format_exc()}, status=500)
            return
        self._send({"ok": False, "error": f"unknown endpoint {self.path}"}, status=404)

    def _check_executor(self):
        expected = self.headers.get('X-DSH-Houdini-Executor')
        if expected is not None and expected != _EXECUTOR_ID:
            self.close_connection = True
            self._send({'ok': False, 'error': 'executor_mismatch: this Houdini is not the bound target; no operation dispatched',
                        'executorId': _EXECUTOR_ID}, status=409)
            return False
        return True

    def do_POST(self) -> None:  # noqa: N802 (http.server naming)
        if not self._check_executor():
            return
        try:
            # Reject browser simple-request CSRF against this trusted loopback
            # execution service. No CORS permission is granted. This does not
            # make arbitrary local Python or the Raw Gate a security sandbox.
            if self.headers.get('origin') is not None or self.headers.get_content_type() != 'application/json':
                self.close_connection = True
                self._send({"ok": False, "error": "JSON requests from trusted local clients only (no browser Origin)"}, status=403)
                return
            length = int(self.headers.get("content-length") or 0)
            if length < 0 or length > _MAX_BODY_BYTES or self.headers.get('transfer-encoding'):
                self.close_connection = True
                self._send(
                    {"ok": False, "error": f"invalid request body length/encoding ({length}, max {_MAX_BODY_BYTES})"},
                    status=413,
                )
                return
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                self._send({"ok": False, "error": "JSON body must be an object"}, status=400)
                return
            self._route(body)
        except (ValueError, UnicodeError) as error:
            self.close_connection = True
            self._send({"ok": False, "error": str(error)}, status=400)
        except Exception:
            self._send({"ok": False, "error": traceback.format_exc()}, status=500)

    def _route(self, body: dict) -> None:
        if self.path == '/ui/list':
            rejection = _owner_error(body) or _contract_error(body.get('expected_contract'))
            fields = {'owner_session', 'owner_call', 'expected_contract', 'request_ref'}
            if rejection is None and (set(body) != fields or not isinstance(body.get('request_ref'), str)):
                rejection = 400, 'UI discovery accepts only the explicit request envelope'
            if rejection is not None:
                self._send({'ok': False, 'error': rejection[1]}, status=rejection[0])
                return
            ref, owner_session = body['request_ref'], body['owner_session']
            try:
                admitted = _request_registry.reserve(ref, owner_session, {**body, 'request_kind': 'ui_list'})
            except ValueError as error:
                self._send({'ok': False, 'error': str(error)}, status=409)
                return
            if not admitted:
                receipt = _request_registry.status(ref, owner_session)
                self._send(receipt['result'] if receipt['status'] == 'done' else {
                    'ok': False, 'stdout': '', 'stderr': '', 'requestReceipt': receipt,
                    'error': 'UI discovery already admitted; retrieve its original result'})
                return
            def discover():
                if not _request_registry.running(ref):
                    return {'ok': False, 'stdout': '', 'stderr': '',
                        'error': 'UI discovery no longer queued',
                        'requestReceipt': _request_registry.status(ref, owner_session)}
                facts, error = None, None
                try:
                    import dsh_ui_capture as capture
                    facts = capture.discover_ui_surfaces()
                except BaseException as exc:
                    facts, error = getattr(exc, 'evidence', None), str(exc)
                try:
                    result = _runtime.ui_observation_result(facts, error, owner_session, operation='ui_list')
                except BaseException as exc:
                    result = {'ok': False, 'stdout': '', 'stderr': '', 'result': facts or {},
                        'error': (error + '; ' if error else '') + 'UI observation unavailable: ' + str(exc)}
                result['requestReceipt'] = {'request_ref': ref, 'runtime_id': _RUNTIME_ID, 'status': 'done'}
                _request_registry.complete(ref, result)
                return result
            try:
                result = _execute(discover)
            except BaseException as exc:
                _request_registry.fail_before_dispatch(ref, exc)
                raise
            self._send(result)
            return
        if self.path == '/ui/capture':
            rejection = _owner_error(body) or _contract_error(body.get('expected_contract'))
            required = {'owner_session', 'owner_call', 'expected_contract', 'request_ref'}
            optional = {'target', 'path', 'output_policy'}
            target = body.get('target')
            valid_target = isinstance(target, str) and bool(target.strip())
            if rejection is None and (not required <= set(body) or set(body) - required - optional
                    or not valid_target
                    or not isinstance(body.get('request_ref'), str)):
                rejection = 400, 'Choose the exact displayed target returned by houdini_ui_list; capture does not accept node/view/width/height or change the UI'
            if rejection is not None:
                self._send({'ok': False, 'error': rejection[1]}, status=rejection[0])
                return
            ref, owner_session = body['request_ref'], body['owner_session']
            try:
                admitted = _request_registry.reserve(ref, owner_session, {**body, 'request_kind': 'ui_capture'})
            except ValueError as error:
                self._send({'ok': False, 'error': str(error)}, status=409)
                return
            if not admitted:
                receipt = _request_registry.status(ref, owner_session)
                self._send(receipt['result'] if receipt['status'] == 'done' else {
                    'ok': False, 'stdout': '', 'stderr': '', 'requestReceipt': receipt,
                    'error': 'UI capture already admitted; retrieve its original result instead of recapturing'})
                return
            options = {key: body[key] for key in optional if key in body}
            result = _capture_ui(options, owner_session, ref, body['owner_call'])
            if _request_registry.status(ref, owner_session)['status'] == 'queued':
                _request_registry.fail_before_dispatch(ref, result.get('error', 'UI capture could not enter the main-thread queue'))
                result['requestReceipt'] = _request_registry.status(ref, owner_session)
                self._send(result)
                return
            result['requestReceipt'] = {'request_ref': ref, 'runtime_id': _RUNTIME_ID, 'status': 'done'}
            _request_registry.complete(ref, result)
            self._send(result)
            return
        if self.path == '/executor/claim':
            if set(body) != {'task_id', 'registration_id', 'expected_hip'} or not all(isinstance(v,str) and v for v in body.values()):
                self._send({'ok':False,'error':'Expected task_id, registration_id and expected_hip'},status=400)
                return
            from dsh_executor_registry import active_registration
            registration = active_registration()
            actual = _execute(lambda: hou.hipFile.path())
            result = registration.claim(body['task_id'], body['registration_id'], body['expected_hip'], actual)
            self._send({'ok':True,'result':result})
            return
        if self.path == '/requests/prepare':
            if (set(body) not in ({'owner_session'}, {'owner_session', 'request_kind'})
                    or not isinstance(body.get('owner_session'), str) or not body['owner_session'].strip()
                    or ('request_kind' in body and body['request_kind'] != 'node_navigation')):
                self._send({'ok': False, 'error': 'owner_session required'}, status=400)
                return
            # POST shares the JSON/no-Origin boundary. A health probe never
            # allocates tickets, and preparing one never enters the HOM queue.
            self._send({**self._health(), 'requestRef': _request_registry.issue(
                body['owner_session'], body.get('request_kind', 'exec'))})
            return
        if self.path == '/requests/status':
            if set(body)!={'request_ref','owner_session'} or not all(isinstance(v,str) and v.strip() for v in body.values()):
                self._send({'ok':False,'error':'request_ref and owner_session required'},status=400)
                return
            self._send({'ok':True,'stdout':'','stderr':'',
                        'requestReceipt':(_request_registry.recent(body['owner_session']) if body['request_ref']=='index'
                                          else _request_status(body['request_ref'],body['owner_session']))})
            return
        if self.path == '/context':
            if type(body.get('schema_version')) is not int or body.get('schema_version') != 1 or set(body) != {'schema_version'}:
                self._send({'ok': False, 'error': 'context requires schema_version=1 only'}, status=400)
                return
            from dsh_context import scene_context
            try:
                self._send({'ok': True, 'result': _execute(
                    lambda: scene_context(_RUNTIME_ID, _HOU_THREAD_ID), timeout=1.5)})
            except (TimeoutError, RuntimeError) as exc:
                self._send({'ok': False, 'status': 'unavailable', 'reason': str(exc)})
            return
        if self.path in ('/nodes/navigate', '/nodes/cancel'):
            # UI navigation has a fixed payload and its own cancellable tickets.
            # Generic /exec and job admission/cancellation retain their contract.
            rejection = _owner_error(body) or _contract_error(body.get('expected_contract'))
            fields = {'owner_session', 'owner_call', 'expected_contract', 'request_ref'}
            if self.path == '/nodes/navigate':
                fields |= {'reference', 'expected_hip'}
            if rejection is None and (set(body) != fields or not isinstance(body.get('request_ref'), str)):
                rejection = 400, 'Expected an explicit node navigation request envelope'
            if rejection is not None:
                self._send({'ok': False, 'error': rejection[1]}, status=rejection[0])
                return
            owner_session, ref = body['owner_session'], body['request_ref']
            if self.path == '/nodes/cancel':
                try:
                    cancelled = _request_registry.cancel_navigation(ref, owner_session)
                except ValueError as error:
                    self._send({'ok': False, 'error': str(error)}, status=409)
                    return
                self._send({'ok': True, 'request_ref': ref, **cancelled})
                return
            reference, expected_hip = body.get('reference'), body.get('expected_hip')
            identifier = reference.get('id') if isinstance(reference, dict) else None
            if (not isinstance(reference, dict) or set(reference) != {'id'}
                    or not isinstance(identifier, str) or len(identifier) != 32
                    or any(char not in '0123456789abcdef' for char in identifier)
                    or not isinstance(expected_hip, str) or not expected_hip.strip()):
                self._send({'ok': False, 'error': 'Node navigation requires a persistent id and expected HIP'}, status=400)
                return
            try:
                admitted = _request_registry.reserve(ref, owner_session, {**body, 'request_kind': 'node_navigation'})
            except ValueError as error:
                self._send({'ok': False, 'error': str(error)}, status=409)
                return
            if not admitted:
                receipt = _request_registry.status(ref, owner_session)
                if receipt['status'] == 'done':
                    self._send(receipt['result'])
                else:
                    self._send({'ok': False, 'stdout': '', 'stderr': '', 'requestReceipt': receipt,
                                'error': 'Node navigation is no longer pending; no new navigation dispatched'})
                return
            def navigate():
                if not _request_registry.running(ref):
                    return {'ok': False, 'stdout': '', 'stderr': '',
                            'requestReceipt': _request_registry.status(ref, owner_session),
                            'error': 'Node navigation cancelled before dispatch'}
                code = '__result__=focus_node(' + json.dumps(reference) + ', expected_hip=' + json.dumps(expected_hip) + ')'
                try:
                    result = run_code(code, None, owner_session, body['owner_call'], True)
                except BaseException:
                    result = {'ok': False, 'stdout': '', 'stderr': '', 'error': traceback.format_exc()}
                result['requestReceipt'] = {'request_ref': ref, 'runtime_id': _RUNTIME_ID, 'status': 'done'}
                _request_registry.complete(ref, result)
                return result
            try:
                result = _execute(navigate)
            except BaseException as error:
                _request_registry.fail_before_dispatch(ref, error)
                raise
            self._send(result)
            return
        if self.path in ("/exec", "/jobs"):
            # Complete admission envelope before anything is queued or consumed:
            # Host identity, contract and a one-time ticket. Untracked execution
            # (formerly the no-ticket compatibility branch) no longer exists.
            rejection = _owner_error(body)
            if rejection is None:
                rejection = _contract_error(body.get("expected_contract"))
            if rejection is None and not isinstance(body.get("code"), str):
                rejection = 400, "code must be a string"
            if rejection is None and (not isinstance(body.get("request_ref"), str) or not body["request_ref"]):
                rejection = 400, "request_ref ticket is required; untracked HTTP execution is not supported"
            if rejection is None and body.get('request_kind') == 'node_navigation':
                rejection = 400, 'Node navigation tickets are accepted only by the fixed node navigation route'
            if rejection is not None:
                self._send({"ok": False, "error": rejection[1]}, status=rejection[0])
                return
        if self.path == "/exec":
            code = body["code"]
            allow_raw = body.get("allow_raw")
            allow_raw = str(allow_raw) if allow_raw else None
            owner_session = body["owner_session"]
            owner_call = body["owner_call"]
            ref = body["request_ref"]
            read_only_value = body.get("read_only")
            if type(read_only_value) not in (bool, str, type(None)) or read_only_value not in (None, True, False, "true", "false"):
                self._send({"ok": False, "error": "read_only must be a boolean or true/false string"}, status=400)
                return
            read_only = read_only_value is True or str(read_only_value).strip().lower() in ("1", "true", "yes", "on")
            invoke=lambda: run_code(code, allow_raw, owner_session, owner_call, read_only)
            try:
                admitted=_request_registry.reserve(ref,owner_session,body)
            except ValueError as error:
                self._send({'ok':False,'error':str(error)},status=409)
                return
            if not admitted:
                receipt=_request_registry.status(ref,owner_session)
                if receipt['status']=='done':self._send(receipt['result'])
                else:self._send({'ok':False,'stdout':'','stderr':'','requestReceipt':receipt,
                                'error':'Request already admitted; retrieve status instead of resubmitting.'})
                return
            def tracked():
                if not _request_registry.running(ref):
                    return {'ok':False,'stdout':'','stderr':'',
                            'requestReceipt':_request_registry.status(ref,owner_session),
                            'error':'Request no longer queued; original code was not started again.'}
                try:result=invoke()
                except BaseException:
                    result={'ok':False,'stdout':'','stderr':'','error':traceback.format_exc()}
                result['requestReceipt']={'request_ref':ref,'runtime_id':_RUNTIME_ID,'status':'done'}
                _request_registry.complete(ref,result)
                return result
            try:
                result=_execute(tracked)
            except BaseException as error:
                # Only a still queued receipt proves that HOM never began.
                if _request_registry.status(ref,owner_session)['status']=='queued':
                    _request_registry.fail_before_dispatch(ref,error)
                raise
            self._send(result)
            return
        if self.path == "/jobs":
            ref = body["request_ref"]
            owner_session = body["owner_session"]
            owner_call = body["owner_call"]
            try:admitted=_request_registry.reserve(ref,owner_session,{**body,'request_kind':'job_submit'})
            except ValueError as error:
                self._send({'ok':False,'error':str(error)},status=409);return
            if not admitted:
                receipt=_request_registry.status(ref,owner_session)
                self._send(receipt['result'] if receipt['status']=='done' else {'requestReceipt':receipt})
                return
            job_id = uuid.uuid4().hex[:12]
            with _jobs_lock:
                overloaded = sum(j['status'] in ('queued', 'running') for j in _jobs.values()) >= _MAX_ACTIVE_JOBS
                if not overloaded:
                    # owner_session/owner_call are internal authorization fields:
                    # they must never reach a public snapshot (see _public_job).
                    _jobs[job_id] = {
                        "jobId": job_id, "status": "queued",
                        "ok": False, "stdout": "", "stderr": "",
                        "owner_session": owner_session, "owner_call": owner_call,
                    }
                    _job_meta[job_id] = time.time()
            if overloaded:
                _request_registry.fail_before_dispatch(ref,'job admission refused: active job limit')
                self._send({"ok": False, "error": "too many active Houdini jobs; await existing work"}, status=429)
                return
            allow_raw = body.get("allow_raw")
            allow_raw = str(allow_raw) if allow_raw else None
            worker=threading.Thread(
                target=_run_job,
                args=(
                    job_id,
                    body["code"],
                    allow_raw,
                    owner_session,
                    owner_call,
                    ref,
                ),
                daemon=True,
            )
            try:worker.start()
            except BaseException:
                with _jobs_lock:
                    job = _jobs.get(job_id)
                    not_started = job is None or job['status'] == 'queued'
                    if not_started:
                        _jobs.pop(job_id,None);_job_meta.pop(job_id,None)
                if not_started:
                    _request_registry.fail_before_dispatch(ref,'job worker did not start')
                else:
                    # Starting a thread can fail after it claimed the job.
                    # Preserve that job/result, not a false nonexecution receipt.
                    _request_registry.complete(ref,{'jobId':job_id})
                raise
            handle={'jobId':job_id,
                    'requestReceipt':{'request_ref':ref,'runtime_id':_RUNTIME_ID,
                                      'status':'job_submitted','jobId':job_id,
                                      'note':'Admission confirmed, not execution completion; collect with houdini_job_status.'}}
            _request_registry.complete(ref,handle)
            _prune_jobs()
            self._send(handle)
            return
        parts = [p for p in self.path.split("/") if p]
        if len(parts) == 3 and parts[0] == "jobs":
            job_id = parts[1]
            # Job control carries the same identity/contract envelope as
            # execution. A new Host must refuse an old Bridge (and vice versa)
            # before any job state is read or changed; missing identity is 400,
            # a well-formed foreign contract is 409.
            rejection = _owner_error(body)
            if rejection is None:
                rejection = _contract_error(body.get("expected_contract"))
            if rejection is not None:
                self._send({"ok": False, "error": rejection[1]}, status=rejection[0])
                return
            owner_session = body["owner_session"]
            if parts[2] == "cancel":
                # Ownership check and mutation share one lock acquisition: a
                # foreign session can neither change state, timestamps nor
                # advisory, and gets no existence signal (uniform 404).
                authorized = False
                with _jobs_lock:
                    job = _jobs.get(job_id)
                    if job is not None and job.get("owner_session") == owner_session:
                        authorized = True
                        if job["status"] == "queued":
                            job["status"] = "cancelled"
                            _job_meta[job_id] = time.time()
                        elif job["status"] == "running":
                            job["advisory"] = "Running HOM cannot be interrupted; job remains running and its actual result will be retained."
                if not authorized:
                    self._send({"ok": False, "error": f"no job {job_id} for this session"}, status=404)
                    return
            elif parts[2] == "status":
                with _jobs_lock:
                    job = _jobs.get(job_id)
                    authorized = job is not None and job.get("owner_session") == owner_session
                if not authorized:
                    self._send({"ok": False, "error": f"no job {job_id} for this session"}, status=404)
                    return
                # 长轮询：body 带 wait（秒，上限 600）时在本 handler 线程里
                # 等到终态或超时一次返回——调用方不必 sleep 循环刷状态。
                # 注意必须在 _jobs_lock 之外等待：持锁等待会把 _run_job
                # 标记终态的路堵死（plain Lock，且内层再取同锁即自死锁）。
                wait = body.get("wait")
                if isinstance(wait, (int, float)) and wait > 0:
                    deadline = time.time() + min(float(wait), 600.0)
                    while time.time() < deadline:
                        with _jobs_lock:
                            terminal = job["status"] not in ("queued", "running")
                        if terminal:
                            break
                        time.sleep(0.25)
            else:
                self._send({"ok": False, "error": f"unknown endpoint {self.path}"}, status=404)
                return
            with _jobs_lock:
                snapshot = _public_job(job)
            self._send(snapshot)
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
    while True:
        try:
            _func, done, holder = _work_queue.get_nowait()
        except queue.Empty:
            break
        holder["cancelled"] = True
        holder["error"] = RuntimeError("Houdini bridge stopped before queued work executed")
        done.set()
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
    global _server, _RUNTIME_ID, _request_registry, _runtime
    if threading.get_ident() != _HOU_THREAD_ID:
        raise RuntimeError("start must run on Houdini's owning thread")
    stop()
    _RUNTIME_ID=uuid.uuid4().hex
    _request_registry=RequestRegistry(_RUNTIME_ID)
    _runtime=ExecutionRuntime(_HOU_THREAD_ID, _RUNTIME_ID, _EXECUTOR_ID)
    if hou.isUIAvailable() and not _install_gui_pump():
        raise RuntimeError("Cannot start bridge without a Houdini GUI main-thread pump")
    try:
        server = ThreadingHTTPServer((host, port), _Handler)
    except BaseException:
        stop()
        raise
    _server = server
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True).start()
    print(f"[dsh-houdini] bridge serving on http://{host}:{server.server_port}")
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
