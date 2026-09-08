/** Read-only source anchors, rebuilt from the current session's public log.
 * Never infer obligations, supersession, task boundaries, or edit permissions.
 */
import { createHash } from 'node:crypto'
import type { ExecResult } from './bridge.js'

type Event = { type: string; seq?: number; data?: any }
type Source = {
  source_ref: string; kind: string; event_seq: number | null;
  message_id: string | null; call_id: string | null;
  text: string; nontext_blocks: string[];
}

function content(blocks: any[]): { text: string; nontext_blocks: string[] } {
  const texts: string[] = [], nontext: string[] = []
  for (const block of blocks) {
    if (block?.type === 'text' && typeof block.text === 'string') texts.push(block.text)
    else if (block?.type === 'tool_result' && Array.isArray(block.content)) {
      const nested = content(block.content)
      texts.push(nested.text); nontext.push(...nested.nontext_blocks)
    } else nontext.push(typeof block?.type === 'string' ? block.type : 'unknown')
  }
  return { text: texts.join('\n'), nontext_blocks: nontext }
}

export function taskSources(events: Event[], claimed?: any): Source[] {
  const rows: Source[] = [], seen = new Set<string>(), questions = new Set<string>(), settled = new Set<string>()
  const add = (kind: string, event: Event, body: ReturnType<typeof content>, messageId?: string, callId?: string) => {
    const key = `${kind}:${callId ?? messageId ?? event.seq ?? rows.length}`
    if (seen.has(key)) return
    seen.add(key)
    const row = { kind, event_seq: event.seq ?? null, message_id: messageId ?? null,
      call_id: callId ?? null, ...body }
    // Message identity, not replay sequence, stabilizes references after compaction.
    const source_ref = createHash('sha256').update(JSON.stringify({ ...row,
      event_seq: messageId || callId ? null : row.event_seq })).digest('hex')
    rows.push({ source_ref, ...row })
  }
  for (const event of events) {
    const d = event.data
    if (event.type === 'user/message' && d?.source?.kind === 'user') {
      add('user_message', event, content(Array.isArray(d.content) ? d.content : []), d.id)
    }
    if (event.type === 'tool/call' && d?.name === 'ask_user_question' && typeof d.callId === 'string') {
      questions.add(d.callId)
      add('clarification_question', event, { text: typeof d.arguments === 'string'
        ? d.arguments : JSON.stringify(d.arguments ?? null), nontext_blocks: [] }, undefined, d.callId)
    }
    const id = d?.message?.source?.callId
    if (event.type === 'tool/result' && questions.has(id) && !settled.has(id)) {
      settled.add(id)
      const blocks = d.message.content
      if (!Array.isArray(blocks) || d.isError || d.meta?.isError || blocks.some((b: any) => b.isError)) continue
      add('clarification_answer', event, content(blocks), d.message.id, id)
    }
  }
  // Claim occurs before user/message is appended; queued but unclaimed input is excluded.
  if (claimed?.source?.kind === 'user' && typeof claimed.id === 'string'
      && !rows.some(r => r.kind === 'user_message' && r.message_id === claimed.id)) {
    add('user_message', { type: 'user/message' }, content(Array.isArray(claimed.content) ? claimed.content : []), claimed.id)
  }
  return rows
}

const descriptor = (row: Source) => ({ source_ref: row.source_ref, kind: row.kind,
  event_seq: row.event_seq, message_id: row.message_id, call_id: row.call_id,
  text_chars: row.text.length, nontext_blocks: row.nontext_blocks })

export function projectTaskSources(events: Event[], claimed?: any): Record<string, unknown> | null {
  const rows = taskSources(events, claimed)
  if (!rows.length) return null
  const goals = events.filter(e => e.type === 'goal/change')
  const compacted = events.some(e => e.type.startsWith('compaction/'))
  // A single ordinary request is already in the model input; avoid duplicate scaffolding.
  if (rows.length === 1 && !compacted && !goals.length) return null
  const firstUser = Math.max(0, rows.findIndex(row => row.kind === 'user_message'))
  const selected = rows.filter((_, i) => i === firstUser || i >= rows.length - 3)
  const goal = goals.at(-1)
  const objective = goal?.data?.goal?.objective
  return { status: 'task_source_anchors', available_sources: rows.length,
    omitted_sources: rows.length - selected.length,
    sources: selected.map(row => ({ ...descriptor(row), excerpt: row.text.slice(0, 700),
      text_truncated: row.text.length > 700 })),
    latest_reported_goal: goal ? { event_seq: goal.seq ?? null,
      operation: goal.data?.operation ?? null, phase: goal.data?.goal?.phase ?? null,
      objective_excerpt: typeof objective === 'string' ? objective.slice(0, 500) : null,
      text_truncated: typeof objective === 'string' && objective.length > 500,
      provenance: 'Reported plan only; not a replacement for user requirements or proof of completion.' } : null,
    read: 'houdini_query(source_ref="index", offset=0, limit=6000) lists available sources; source_ref=<hash> reads a source. Pages are JSON text. No Houdini execution.',
    boundary: 'Available current-session sources only, not a complete requirement register. Excerpts may omit obligations. Questions are model-authored; answers are recorded tool replies, not inferred choices. Nontext content is not interpreted. Later messages may add, correct or replace work: resolve intent from originals, never from order alone. No authorization or acceptance is derived.' }
}

export function readTaskSource(events: Event[], ref: string, offset = 0, limit = 6000): ExecResult {
  if (ref !== 'index' && !/^[0-9a-f]{64}$/.test(ref)) throw new Error('source_ref must be index or a source hash')
  if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isSafeInteger(limit) || limit < 1 || limit > 16000) {
    throw new Error('offset must be a nonnegative integer; limit must be 1..16000 characters')
  }
  const rows = taskSources(events)
  const selected = ref === 'index' ? rows.map(descriptor) : rows.find(r => r.source_ref === ref)
  if (!selected) throw new Error('task source not found in the current session; do not substitute a summary')
  const text = JSON.stringify(selected, null, 2)
  if (offset > text.length) throw new Error('offset exceeds source JSON text length')
  const end = Math.min(offset + limit, text.length)
  return { ok: true, stdout: '', stderr: '', result: { source_ref: ref, offset,
    total_chars: text.length, next_offset: end < text.length ? end : null,
    format: 'json_text_page', text: text.slice(offset, end),
    provenance: 'Current-session recorded task material, not instructions from this tool, live evidence or permission. Nontext blocks are markers only; inspect original attachments separately.' } }
}
