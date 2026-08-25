/**
 * HTTP client for the Houdini-side bridge (`houdini/dsh_bridge.py`).
 *
 * The bridge runs inside Houdini's own Python, where the `hou` module lives;
 * this client is the only channel the plugin uses to reach it.
 */
import type { JsonValue } from '@deepseek-ai/dsh-tools'
import { EXPECTED_VERB_CATALOG_HASH, EXPECTED_VERB_NAMES } from './generated-verb-contract.js'

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
  /** Failure-time Houdini undo rollback outcome, when execution reached Python. */
  rollback?: JsonValue
  /** Structured Raw Gate/read-only HOM classification produced by the bridge AST. */
  rawUsage?: JsonValue
  /** Advisory hint, present when the code bypassed the verb vocabulary with raw hou calls. */
  advisory?: string
  /** Absolute paths of images produced during this exec (render/screenshot verbs). */
  images?: JsonValue
  /** Media relay outcome, filled host-side: bridge paths copied into the session workspace. */
  media?: JsonValue
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

/** Host-authenticated provenance attached to one bridge execution. */
export interface OwnershipScope {
  sessionId: string
  callId: string
}

interface BridgeHealth {
  ok: boolean
  houVersion?: string
  rawGate?: boolean
  verbCatalog?: {
    hash?: string
    count?: number
    names?: string[]
  }
  error?: string
}

/** Normalize a user-supplied base URL so path joins never produce double slashes. */
function normalizeBaseUrl(url: string): string {
  return url.replace(/\/+$/, '')
}

export class HoudiniBridge {
  private readonly baseUrl: string
  private contractCheckedAt = 0
  private contractCheck: Promise<void> | null = null

  constructor(baseUrl: string, private readonly timeoutMs: number) {
    this.baseUrl = normalizeBaseUrl(baseUrl)
  }

  /** Run Python code in the Houdini session and wait for completion.
   *  allowRaw: one-time raw-hou exemption reason when the bridge gate is on. */
  async exec(code: string, signal?: AbortSignal, allowRaw?: string, owner?: OwnershipScope): Promise<ExecResult> {
    await this.ensureCompatible(signal)
    const body: Record<string, string> = { code }
    if (allowRaw) body.allow_raw = allowRaw
    if (owner) {
      body.owner_session = owner.sessionId
      body.owner_call = owner.callId
    }
    return this.post('/exec', body, signal)
  }

  /** Queue Python code as a bridge-side background job; returns immediately. */
  async submitJob(code: string, signal?: AbortSignal, allowRaw?: string, owner?: OwnershipScope): Promise<JobHandle> {
    await this.ensureCompatible(signal)
    const body: Record<string, string> = { code }
    if (allowRaw) body.allow_raw = allowRaw
    if (owner) {
      body.owner_session = owner.sessionId
      body.owner_call = owner.callId
    }
    return this.post('/jobs', body, signal)
  }

  /** Refuse scene work when the host catalog and in-process bridge differ. */
  private async ensureCompatible(signal?: AbortSignal): Promise<void> {
    if (Date.now() - this.contractCheckedAt < 30_000) return
    if (this.contractCheck) return this.contractCheck
    const pending = this.checkContract(signal)
    this.contractCheck = pending
    try {
      await pending
      this.contractCheckedAt = Date.now()
    } finally {
      if (this.contractCheck === pending) this.contractCheck = null
    }
  }

  private async checkContract(signal?: AbortSignal): Promise<void> {
    const health = await this.get<BridgeHealth>('/health', signal)
    const actual = health.verbCatalog
    if (health.ok && actual?.hash === EXPECTED_VERB_CATALOG_HASH) return

    const expectedNames = new Set<string>(EXPECTED_VERB_NAMES)
    const actualNames = new Set(Array.isArray(actual?.names) ? actual.names : [])
    const missing = [...expectedNames].filter((name) => !actualNames.has(name))
    const extra = [...actualNames].filter((name) => !expectedNames.has(name))
    const detail = [
      `host=${EXPECTED_VERB_CATALOG_HASH.slice(0, 12)} (${EXPECTED_VERB_NAMES.length})`,
      `bridge=${actual?.hash?.slice(0, 12) ?? 'missing'} (${actual?.count ?? 'unknown'})`,
      missing.length ? `missing=${missing.join(',')}` : '',
      extra.length ? `extra=${extra.join(',')}` : '',
      health.error ? `health=${health.error}` : '',
    ].filter(Boolean).join('; ')
    throw new Error(
      `Houdini bridge contract mismatch: ${detail}. `
      + 'The host and the running Houdini bridge are different generations; '
      + 'open DSH-Houdini > Version & Diagnostics > Advanced diagnostics and run '
      + 'Repair and restart runtime before retrying.',
    )
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

  /**
   * Fetch image bytes from the bridge's `/media` endpoint. The bridge process
   * can read $HIP-side outputs that dsh-side tools (sandboxed to the session
   * workspace) cannot; the caller writes the bytes into the workspace.
   */
  async fetchMedia(path: string, signal?: AbortSignal): Promise<Buffer> {
    const url = `${this.baseUrl}/media?path=${encodeURIComponent(path)}`
    let res: Response
    try {
      res = await fetch(url, { signal: this.withTimeout(signal) })
    } catch (cause) {
      const reason = cause instanceof Error ? cause.message : String(cause)
      throw new Error(`cannot reach the Houdini bridge at ${this.baseUrl} (${reason})`)
    }
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      throw new Error(`bridge /media returned HTTP ${res.status}${detail ? `: ${detail}` : ''}`)
    }
    return Buffer.from(await res.arrayBuffer())
  }

  private hipCache: { dir: string | null; at: number } | null = null

  /** Directory of the live hip file ($HIP), 60s cache; null when unreachable
   *  or the scene was never saved (untitled.hip — no meaningful $HIP, the
   *  preset persona already tells the agent to ask the user first).
   *  Used to detect sessions whose workspace does not match the live scene. */
  async hipDir(): Promise<string | null> {
    if (this.hipCache && Date.now() - this.hipCache.at < 60_000) return this.hipCache.dir
    let dir: string | null = null
    try {
      const r = await this.exec(
        "import os, hou\n_p = hou.hipFile.path()\n__result__ = '' if os.path.basename(_p).lower() == 'untitled.hip' else os.path.dirname(_p)",
      )
      if (r.ok && typeof r.result === 'string' && r.result) dir = r.result
    } catch {
      // bridge down — the exec itself already reported that; no note needed
    }
    this.hipCache = { dir, at: Date.now() }
    return dir
  }

  private withTimeout(signal: AbortSignal | undefined, extraMs = 0): AbortSignal {
    const timeout = AbortSignal.timeout(this.timeoutMs + extraMs)
    return signal ? AbortSignal.any([signal, timeout]) : timeout
  }

  private async get<T>(path: string, signal?: AbortSignal): Promise<T> {
    return this.requestJson<T>(path, { method: 'GET' }, signal)
  }

  private async post<T>(path: string, body: unknown, signal?: AbortSignal, extraMs = 0): Promise<T> {
    return this.requestJson<T>(path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }, signal, extraMs)
  }

  private async requestJson<T>(
    path: string,
    init: RequestInit,
    signal?: AbortSignal,
    extraMs = 0,
  ): Promise<T> {
    let res: Response
    try {
      res = await fetch(`${this.baseUrl}${path}`, {
        ...init,
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
