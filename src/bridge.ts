/**
 * HTTP client for the Houdini-side bridge (`houdini/dsh_bridge.py`).
 *
 * The bridge runs inside Houdini's own Python, where the `hou` module lives;
 * this client is the only channel the plugin uses to reach it.
 */
import type { JsonValue } from '@deepseek-ai/dsh-tools'

/** Result envelope returned by the bridge for `/exec` and job status polls. */
export interface ExecResult {
  ok: boolean
  stdout: string
  stderr: string
  /** JSON value the executed code bound to `__result__`, if any. */
  result?: JsonValue
  /** Runtime ledger of verb-vocabulary calls, when any were traced. */
  verbs?: JsonValue
  /** Python traceback, present when `ok` is false. */
  error?: string
  /** Advisory hint, present when the code bypassed the verb vocabulary with raw hou calls. */
  advisory?: string
}

/** Handle returned when a background job is accepted by the bridge. */
export interface JobHandle {
  jobId: string
}

/** Poll snapshot of a bridge-side background job. */
export interface JobStatus extends ExecResult {
  jobId: string
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
}

/** Normalize a user-supplied base URL so path joins never produce double slashes. */
function normalizeBaseUrl(url: string): string {
  return url.replace(/\/+$/, '')
}

export class HoudiniBridge {
  private readonly baseUrl: string

  constructor(baseUrl: string, private readonly timeoutMs: number) {
    this.baseUrl = normalizeBaseUrl(baseUrl)
  }

  /** Run Python code in the Houdini session and wait for completion. */
  exec(code: string, signal?: AbortSignal): Promise<ExecResult> {
    return this.post('/exec', { code }, signal)
  }

  /** Queue Python code as a bridge-side background job; returns immediately. */
  submitJob(code: string, signal?: AbortSignal): Promise<JobHandle> {
    return this.post('/jobs', { code }, signal)
  }

  /** Poll a bridge-side background job. Pass `wait` (seconds) to long-poll:
   *  the bridge holds the request until the job reaches a terminal state or
   *  the wait elapses, so callers get the outcome in one round trip. */
  jobStatus(jobId: string, wait?: number, signal?: AbortSignal): Promise<JobStatus> {
    const body = wait && wait > 0 ? { wait } : {}
    // Long polls must outlive the wait itself — extend the per-request
    // timeout past it (bridge caps the wait at 600s).
    const extraMs = wait && wait > 0 ? Math.min(wait, 600) * 1000 + 10000 : 0
    return this.post(`/jobs/${encodeURIComponent(jobId)}/status`, body, signal, extraMs)
  }

  /** Cooperatively cancel a queued or running bridge-side job. */
  cancelJob(jobId: string, signal?: AbortSignal): Promise<JobStatus> {
    return this.post(`/jobs/${encodeURIComponent(jobId)}/cancel`, {}, signal)
  }

  private withTimeout(signal: AbortSignal | undefined, extraMs = 0): AbortSignal {
    const timeout = AbortSignal.timeout(this.timeoutMs + extraMs)
    return signal ? AbortSignal.any([signal, timeout]) : timeout
  }

  private async post<T>(path: string, body: unknown, signal?: AbortSignal, extraMs = 0): Promise<T> {
    let res: Response
    try {
      res = await fetch(`${this.baseUrl}${path}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
        signal: this.withTimeout(signal, extraMs),
      })
    } catch (cause) {
      const reason = cause instanceof Error ? cause.message : String(cause)
      throw new Error(
        `cannot reach the Houdini bridge at ${this.baseUrl} (${reason}); `
        + 'start dsh_bridge.py inside Houdini first — see README',
      )
    }
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      throw new Error(`Houdini bridge ${path} returned HTTP ${res.status}${detail ? `: ${detail}` : ''}`)
    }
    try {
      return (await res.json()) as T
    } catch (cause) {
      const reason = cause instanceof Error ? cause.message : String(cause)
      throw new Error(`Houdini bridge ${path} returned a non-JSON response (${reason})`)
    }
  }
}
