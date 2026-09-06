/** RETIRED v8 reference; not compiled or packaged. Session-bound delivery state. */
import type { OwnershipScope } from './bridge.js'

type Row = { id: string; kind: string; status: string; [key: string]: unknown }
type Receipt = { revision: string; checks: Row[]; [key: string]: unknown }
type Binding = { runtime: string; scene: number; hip: string }
export interface DeliveryReply {
  ok: boolean
  binding?: Binding
  receipt?: Receipt
  test?: Row | null
  inspection?: unknown
  error?: string
  reset_required?: boolean
  busy?: boolean
}
export interface DeliveryTransport {
  readonly mutationEpoch: number
  readonly pendingMutations: number
  readonly activityEpoch?: number
  delivery(request: unknown, owner: OwnershipScope, binding?: Binding, signal?: AbortSignal): Promise<DeliveryReply>
}
type ContractChanges = { removed: string[]; added: string[]; changed: string[] }
type State = { contract: unknown; binding: Binding; revision: string; controls: Map<string, Row>; receipt: Receipt; generation: number; changes: ContractChanges }

function contractChanges(before: unknown, after: unknown): ContractChanges {
  const entries=(value: unknown) => {
    const result=new Map<string,string>()
    if(value && typeof value==='object' && !Array.isArray(value)) {
      for(const kind of ['parts','controls','interfaces','topology','domain']) {
        const rows=(value as Record<string,unknown>)[kind]
        if(Array.isArray(rows))for(const row of rows)if(row && typeof row.id==='string')result.set(row.id,JSON.stringify({kind,row}))
      }
    }
    return result
  }
  const a=entries(before),b=entries(after)
  return {removed:[...a.keys()].filter(id=>!b.has(id)),added:[...b.keys()].filter(id=>!a.has(id)),
    changed:[...b.keys()].filter(id=>a.has(id) && a.get(id)!==b.get(id))}
}

export function deliveryRequest(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('delivery must be an object')
  const request = value as Record<string, unknown>
  const allowed: Record<string, string[]> = {
    inspect: ['action','scope'], register: ['action','contract'], check: ['action'], test_control: ['action','case_id'],
  }
  const keys = allowed[String(request.action)]
  if (!keys || Object.keys(request).some(k => !keys.includes(k)) || keys.some(k => !(k in request))) {
    throw new Error('delivery: inspect {scope}, register {contract}, check, or test_control {case_id}; do not submit results/owner/evidence')
  }
  if (JSON.stringify(value).length > 65536) throw new Error('delivery request exceeds 64KiB')
  return structuredClone(request)
}

export class DeliveryController {
  private readonly sessions = new Map<string, State>()
  private readonly running = new Set<string>()
  constructor(private readonly bridge: DeliveryTransport) {}

  /** Compact, explicitly stale reminder; not another geometry observation. */
  summary(sessionId: string): unknown {
    const state = this.sessions.get(sessionId)
    if (!state) return undefined
    const stale = state.generation !== this.bridge.mutationEpoch || this.bridge.pendingMutations > 0
    return {
      source: 'Host delivery state', stale, observationOnly: true,
      delivery_status: 'partial_pending_independent_review',
      next_action: stale ? 'Scene work invalidated cached evidence; use delivery.check, then rerun affected control cases.' : 'Use delivery.check for a fresh receipt before handoff.',
      pending: stale ? ['fresh final-output check', 'registered control cases'] : state.receipt.checks.filter(r=>r.status!=='pass').map(r=>r.id).slice(0,12),
    }
  }

  async execute(value: unknown, owner: OwnershipScope | undefined, signal?: AbortSignal): Promise<unknown> {
    if (!owner?.sessionId || !owner.callId) throw new Error('delivery requires trusted DSH session/call context')
    const request = deliveryRequest(value)
    const session = owner.sessionId
    if (this.running.has(session)) throw new Error('delivery operation already pending for this session; wait for its result')
    let state = this.sessions.get(session)
    if (this.bridge.pendingMutations) {
      if(state){state.controls.clear();state.generation=-1}
      throw new Error('scene mutation request pending; do not issue a delivery receipt yet')
    }
    if (request.action !== 'inspect' && request.action !== 'register' && !state) throw new Error('No delivery contract for this session; inspect then register first')
    const generation = this.bridge.mutationEpoch
    const activity = this.bridge.activityEpoch ?? generation
    this.running.add(session)
    try {
      // Frozen contract is supplied by Host, not replayed/modified model arguments.
      const command = request.action === 'check' || request.action === 'test_control'
        ? {...request, contract: structuredClone(state!.contract)} : request
      const reply = await this.bridge.delivery(command, owner,
        request.action==='register' || request.action==='inspect' ? undefined : state!.binding, signal)
      if (generation !== this.bridge.mutationEpoch || activity !== (this.bridge.activityEpoch ?? this.bridge.mutationEpoch) || this.bridge.pendingMutations) {
        if (state) {state.controls.clear(); state.generation=-1}
        throw new Error('scene work overlapped delivery observation; evidence discarded, check again after work settles')
      }
      if (reply.reset_required) {this.sessions.delete(session); throw new Error(reply.error || 'runtime/HIP changed; register again')}
      if (!reply.ok) throw new Error(reply.error || 'delivery observation did not complete')
      if (request.action==='inspect') {
        if(state && JSON.stringify(state.binding)!==JSON.stringify(reply.binding))this.sessions.delete(session)
        return {inspection:reply.inspection, semantic_status:'unverified'}
      }
      const receipt = reply.receipt
      if (!receipt || typeof receipt.revision!=='string' || !Array.isArray(receipt.checks) || !reply.binding) {
        throw new Error('malformed delivery evidence; no pass retained')
      }
      if (request.action==='register') {
        if (!state && this.sessions.size>=128) throw new Error('delivery session capacity reached; restart Host to clear volatile state')
        state = {contract:structuredClone(request.contract),binding:reply.binding,revision:receipt.revision,
          controls:new Map(),receipt:structuredClone(receipt),generation,changes:contractChanges(state?.contract,request.contract)}
        this.sessions.set(session,state)
      }
      const current = state!
      if (JSON.stringify(current.binding)!==JSON.stringify(reply.binding)) {
        this.sessions.delete(session); throw new Error('delivery binding changed; register again')
      }
      const invalidated = current.revision!==receipt.revision || current.generation!==generation ? [...current.controls.keys()] : []
      if (invalidated.length) current.controls.clear()
      current.revision=receipt.revision
      current.generation=generation
      if (request.action==='test_control' && reply.test) {
        if (reply.test.id!==request.case_id || reply.test.kind!=='control') throw new Error('control evidence identity mismatch')
        current.controls.set(reply.test.id,structuredClone(reply.test))
      }
      const checks = receipt.checks.map(row => row.kind==='control' && row.status==='unverified'
        ? structuredClone(current.controls.get(row.id) || row) : row)
      const status = checks.some(r=>r.status==='fail') ? 'fail' : checks.some(r=>r.status!=='pass') ? 'unverified' : 'pass'
      current.receipt = {...receipt,checks,status,ready_for_independent_review:status==='pass',
        contract_changes:structuredClone(current.changes),
        invalidated_control_cases:invalidated, reused_control_cases:checks.filter(r=>r.kind==='control' && current.controls.has(r.id) && r.id!==request.case_id).map(r=>r.id),
        delivery_status:'partial_pending_independent_review',semantic_status:'unverified'}
      return structuredClone(current.receipt)
    } catch(error) {
      const current=this.sessions.get(session)
      if(current){current.controls.clear(); current.generation=-1}
      throw error
    } finally {this.running.delete(session)}
  }
}
