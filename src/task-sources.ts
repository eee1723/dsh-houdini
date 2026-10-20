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

export function taskSources(events: readonly Event[], claimed?: any): Source[] {
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
    const questionId = event.type === 'tool/call' ? d?.callId
      : event.type === 'tool/ptc-dispatch-start' ? d?.subCallId : undefined
    if (d?.name === 'ask_user_question' && typeof questionId === 'string') {
      questions.add(questionId)
      add('clarification_question', event, { text: typeof d.arguments === 'string'
        ? d.arguments : JSON.stringify(d.arguments ?? null), nontext_blocks: [] }, undefined, questionId)
    }
    const id = event.type === 'tool/result' ? d?.message?.source?.callId
      : event.type === 'tool/ptc-dispatch' ? d?.subCallId : undefined
    if (typeof id === 'string' && questions.has(id) && !settled.has(id)) {
      settled.add(id)
      const blocks = event.type === 'tool/result' ? d.message.content : d.content
      if (!Array.isArray(blocks) || d.message?.isError || d.isError || d.meta?.isError || blocks.some((b: any) => b.isError)) continue
      add('clarification_answer', event, content(blocks), d.message?.id, id)
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

export function readTaskSource(events: readonly Event[], ref: string, offset = 0, limit = 6000): ExecResult {
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
