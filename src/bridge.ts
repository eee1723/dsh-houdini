/**
 * HTTP client for the Houdini-side bridge (`houdini/dsh_bridge.py`).
 *
 * The bridge runs inside Houdini's own Python, where the `hou` module lives;
 * this client is the only channel the plugin uses to reach it.
 */
/** Bridge wire JSON is independent of DSH's version-specific type re-exports. */
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue }
import { EXPECTED_EXECUTION_CONTRACT_VERSION, EXPECTED_VERB_CATALOG_HASH, EXPECTED_VERB_NAMES } from './generated-verb-contract.js'

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
  transaction?: JsonValue
  /** Structured Raw Gate/read-only HOM classification produced by the bridge AST. */
  rawUsage?: JsonValue
  /** Advisory hint, present when the code bypassed the verb vocabulary with raw hou calls. */
  advisory?: string
  /** Absolute paths of images produced during this exec (render/screenshot verbs). */
  images?: JsonValue
  /** Native DSH image attachment references; no workspace file copies. */
  imageAttachments?: JsonValue
  /** Failed/warning operation checks despite successful Python execution. */
  checks?: JsonValue
  /** Compact operation evidence, retained independently of verbose ledger previews. */
  evidence?: JsonValue
  /** Bridge runtime/order and bounded impact observation; not a scene lock. */
  execution?: JsonValue
  /** Immutable returned-envelope reference, filled host-side for large results. */
  details?: JsonValue
  /** Same-runtime execution receipt, including uncertain transport outcomes. */
  requestReceipt?: JsonValue
}

/** Handle returned when a background job is accepted by the bridge. */
export interface JobHandle {
  jobId?: string
  requestReceipt?: JsonValue
  error?: string
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
  executorId?: string
  runtimeId?: string
  requestRef?: string
  houVersion?: string
  rawGate?: boolean
  executionContractVersion?: number
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

  constructor(baseUrl: string, private readonly timeoutMs: number, private readonly executorId?: string,
    private readonly lifetime?:AbortSignal) {
    this.baseUrl = normalizeBaseUrl(baseUrl)
    if (executorId !== undefined && !/^[0-9a-f]{32}$/.test(executorId)) throw new Error('Invalid Houdini executor identity')
  }

  private targetHeaders(): Record<string, string> {
    return this.executorId ? {'X-DSH-Houdini-Executor': this.executorId} : {}
  }

  /** Host routing identity, never a tool argument or node edit permission. */
  get targetExecutorId(): string | undefined { return this.executorId }

  /** Non-HOM identity/contract check for an explicit target selection. */
  async inspectExecutor(signal?: AbortSignal): Promise<BridgeHealth> {
    return this.checkContract(signal)
  }
  async claimWriter(taskId:string,registrationId:string,expectedHip:string,signal?:AbortSignal):Promise<void> {
    const result=await this.post<{ok:boolean;error?:string}>('/executor/claim',{
      task_id:taskId,registration_id:registrationId,expected_hip:expectedHip},signal)
    if(result.ok!==true) throw new Error(result.error||'Writer reservation failed')
  }

  /** Run Python code in the Houdini session and wait for completion.
   *  allowRaw: one-time raw-hou exemption reason when the bridge gate is on. */
  async exec(code: string, signal?: AbortSignal, allowRaw?: string, owner?: OwnershipScope, readOnly = false): Promise<ExecResult> {
    const { runtimeId, requestRef: ref } = await this.checkContract(signal, owner)
    const body: Record<string, unknown> = { code, expected_contract: this.expectedContract() }
    if (allowRaw) body.allow_raw = allowRaw
    if (owner) {
      body.owner_session = owner.sessionId
      body.owner_call = owner.callId
    }
    if (readOnly) body.read_only = 'true'
    // A Bridge-issued ticket can be admitted only once, even after its result expires.
    if (ref) body.request_ref = ref
    try {
      return await this.post<ExecResult>('/exec', body, signal)
    } catch (error) {
      if (!ref) throw error
      // HTTP status/body/JSON failures can all occur after side effects.
      return {ok:false,stdout:'',stderr:'',error:String(error),
        requestReceipt:{request_ref:ref,runtime_id:runtimeId!,status:'unknown_transport',
          ...(this.executorId ? {executor_id:this.executorId} : {}),
          next_action:'Use houdini_query(request_ref=...) to retrieve the admitted request. Do not resubmit the scene code.'}}
    }
  }

  /** Queue Python code as a bridge-side background job; returns immediately. */
  async submitJob(code: string, signal?: AbortSignal, allowRaw?: string, owner?: OwnershipScope): Promise<JobHandle> {
    const { runtimeId, requestRef: ref } = await this.checkContract(signal, owner)
    const body: Record<string, unknown> = { code, expected_contract: this.expectedContract() }
    if (allowRaw) body.allow_raw = allowRaw
    if (owner) {
      body.owner_session = owner.sessionId
      body.owner_call = owner.callId
    }
    if (ref) body.request_ref=ref
    try {
      const handle = await this.post<JobHandle>('/jobs', body, signal)
      if (handle.requestReceipt && this.executorId) {
        handle.requestReceipt = {...handle.requestReceipt as Record<string, JsonValue>, executor_id:this.executorId}
      }
      return handle
    }
    catch (error) {
      if (!ref) throw error
      return {error:String(error),requestReceipt:{request_ref:ref,runtime_id:runtimeId!,status:'unknown_transport',
        ...(this.executorId ? {executor_id:this.executorId} : {}),
        next_action:'Use houdini_query(request_ref=...) to recover the original jobId. Do not submit this job again.'}}
    }
  }

  private expectedContract() {
    return { version: EXPECTED_EXECUTION_CONTRACT_VERSION, hash: EXPECTED_VERB_CATALOG_HASH }
  }

  private async checkContract(signal?: AbortSignal, owner?: OwnershipScope): Promise<BridgeHealth> {
    // No cached handshake: the process can restart on the same port. Preparing
    // a ticket also returns the contract, so admission costs no extra round trip.
    const health = owner
      ? await this.post<BridgeHealth>('/requests/prepare', { owner_session: owner.sessionId }, signal)
      : await this.get<BridgeHealth>('/health', signal)
    const actual = health.verbCatalog
    if (this.executorId && health.executorId !== this.executorId) {
      throw new Error('Houdini executor mismatch: no scene code was submitted. The connection belongs to another Houdini process. Restore the intended target; do not retry scene operations or automatically rebind by port/HIP path.')
    }
    if (health.ok && actual?.hash === EXPECTED_VERB_CATALOG_HASH
        && health.executionContractVersion === EXPECTED_EXECUTION_CONTRACT_VERSION) {
      if (owner && (typeof health.runtimeId !== 'string' || typeof health.requestRef !== 'string'
          || !/^[0-9a-f]{32}\.[0-9a-f]{32}$/.test(health.requestRef)
          || !health.requestRef.startsWith(health.runtimeId + '.'))) {
        throw new Error('Houdini bridge did not prepare a valid same-runtime request ticket; no scene code was submitted. Repair and restart runtime before retrying.')
      }
      return health
    }

    const expectedNames = new Set<string>(EXPECTED_VERB_NAMES)
    const actualNames = new Set(Array.isArray(actual?.names) ? actual.names : [])
    const missing = [...expectedNames].filter((name) => !actualNames.has(name))
    const extra = [...actualNames].filter((name) => !expectedNames.has(name))
    const detail = [
      `host=${EXPECTED_VERB_CATALOG_HASH.slice(0, 12)} (${EXPECTED_VERB_NAMES.length})`,
      `bridge=${actual?.hash?.slice(0, 12) ?? 'missing'} (${actual?.count ?? 'unknown'})`,
      `semantics=host:${EXPECTED_EXECUTION_CONTRACT_VERSION}/bridge:${health.executionContractVersion ?? 'missing'}`,
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
   * workspace) cannot; the caller commits bytes to native DSH attachments.
   */
  async fetchMedia(path: string, signal?: AbortSignal, maxBytes = 32 * 1024 * 1024): Promise<Buffer> {
    const url = `${this.baseUrl}/media?path=${encodeURIComponent(path)}`
    let res: Response
    try {
      res = await fetch(url, { headers: this.targetHeaders(), signal: this.withTimeout(signal) })
    } catch (cause) {
      const reason = cause instanceof Error ? cause.message : String(cause)
      throw new Error(`cannot reach the Houdini bridge at ${this.baseUrl} (${reason})`)
    }
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      throw new Error(`bridge /media returned HTTP ${res.status}${detail ? `: ${detail}` : ''}`)
    }
    if (Number(res.headers.get('content-length')) > maxBytes) { await res.body?.cancel(); throw new Error('image exceeds attachment byte limit') }
    const chunks: Uint8Array[] = []
    let length = 0
    if (!res.body) throw new Error('empty image response')
    const reader = res.body.getReader()
    try {
      while (true) {
        const {done,value} = await reader.read()
        if (done) break
        length += value.length
        if (length > maxBytes) { await reader.cancel(); throw new Error('image exceeds attachment byte limit') }
        chunks.push(value)
      }
    } finally { reader.releaseLock() }
    return Buffer.concat(chunks)
  }

  /** Fixed, non-evaluating metadata route; old bridges degrade without executing code. */
  async sceneContext(signal?: AbortSignal): Promise<unknown> {
    const timeout = AbortSignal.timeout(2000)
    return this.post('/context', { schema_version: 1 },
      signal ? AbortSignal.any([signal, timeout]) : timeout)
  }

  requestStatus(ref: string, owner: OwnershipScope, signal?: AbortSignal): Promise<ExecResult> {
    if (ref !== 'index' && !/^[0-9a-f]{32}\.[0-9a-f]{32}$/.test(ref)) throw new Error('request_ref must be index or an execution receipt returned by Houdini')
    return this.post('/requests/status',{request_ref:ref,owner_session:owner.sessionId},signal)
  }

  private withTimeout(signal: AbortSignal | undefined, extraMs = 0): AbortSignal {
    const timeout = AbortSignal.timeout(this.timeoutMs + extraMs)
    return AbortSignal.any([timeout,...(signal?[signal]:[]),...(this.lifetime?[this.lifetime]:[])])
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
        headers: {...Object.fromEntries(new Headers(init.headers)), ...this.targetHeaders()},
        signal: this.withTimeout(signal, extraMs),
      })
    } catch (cause) {
      const reason = cause instanceof Error ? cause.message : String(cause)
      throw new Error(
        `Houdini bridge request ${path} at ${this.baseUrl} failed (${reason}); `
        + (init.method === 'POST' && (path === '/exec' || path === '/jobs')
          ? 'execution may still be queued/running or already applied; inspect scene/job state before retrying, and do not blindly resubmit.'
          : 'check bridge availability; see README'),
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
