import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';

const ZSTD_MAGIC = [0x28, 0xb5, 0x2f, 0xfd];

/** Find the most recently modified trace under the DSH session store. */
export function newestSessionFile(root = path.join(os.homedir(), '.dsh', 'sessions')) {
  if (!fs.existsSync(root)) return null;
  let best = null;
  for (const workspace of fs.readdirSync(root)) {
    const workspaceDir = path.join(root, workspace);
    if (!fs.statSync(workspaceDir).isDirectory()) continue;
    for (const session of fs.readdirSync(workspaceDir)) {
      const file = path.join(workspaceDir, session, 'session.jsonl.zstd');
      if (!fs.existsSync(file)) continue;
      const modified = fs.statSync(file).mtimeMs;
      if (!best || modified > best.modified) best = { file, modified };
    }
  }
  return best?.file ?? null;
}

/** Resolve either a session directory or a session.jsonl.zstd file. */
export function resolveSessionFile(input) {
  if (!input) throw new Error('session path is required');
  const absolute = path.resolve(input);
  if (!fs.existsSync(absolute)) throw new Error(`session path does not exist: ${absolute}`);
  return fs.statSync(absolute).isDirectory()
    ? path.join(absolute, 'session.jsonl.zstd')
    : absolute;
}

/** Load every JSON event from a concatenated multi-frame zstd session. */
export function loadSessionEvents(input) {
  const file = resolveSessionFile(input);
  if (!fs.existsSync(file)) throw new Error(`session file does not exist: ${file}`);
  const buffer = fs.readFileSync(file);
  const starts = [];
  for (let i = 0; i + 4 <= buffer.length; i++) {
    if (ZSTD_MAGIC.every((byte, offset) => buffer[i + offset] === byte)) starts.push(i);
  }
  const events = [];
  const frameErrors = [];
  for (let i = 0; i < starts.length; i++) {
    const end = i + 1 < starts.length ? starts[i + 1] : buffer.length;
    try {
      const output = zlib.zstdDecompressSync(buffer.subarray(starts[i], end));
      for (const line of output.toString('utf8').split('\n')) {
        const text = line.trim();
        if (!text) continue;
        try { events.push(JSON.parse(text)); } catch {}
      }
    } catch (error) {
      frameErrors.push({ frame: i, offset: starts[i], error: String(error) });
    }
  }
  return { file, events, frames: starts.length, frameErrors };
}

/** Return the originating call id for a tool/result event, across known schemas. */
export function toolResultCallId(event) {
  if (event?.type !== 'tool/result') return null;
  const message = event.data?.message || {};
  return message.source?.callId || message.content?.[0]?.toolCallId || null;
}

/**
 * Keep one execution result per call id and report later history replays separately.
 *
 * DSH compaction can re-emit an old tool/result after `compaction/prune` so the
 * compacted history remains self-contained. That is history reconstruction, not a
 * second execution. Counting every result event inflates calls, verbs, failures and
 * timing. The first observed result is the execution evidence; later events with the
 * same call id are diagnostics only.
 */
export function uniqueToolResultEvents(events) {
  const firstByCallId = new Map();
  const uniqueResults = [];
  const replayedResults = [];
  for (const event of events) {
    if (event.type !== 'tool/result') continue;
    const callId = toolResultCallId(event);
    if (!callId) {
      // Consumers historically ignored uncorrelated results. Preserve them here so
      // callers can still decide whether a future schema makes them meaningful.
      uniqueResults.push(event);
      continue;
    }
    const first = firstByCallId.get(callId);
    if (!first) {
      firstByCallId.set(callId, event);
      uniqueResults.push(event);
      continue;
    }
    replayedResults.push({
      callId,
      originalSeq: first.seq ?? null,
      replaySeq: event.seq ?? null,
      originalTime: first.time ?? null,
      replayTime: event.time ?? null,
      turn: event.data?.turn ?? null,
      step: event.data?.step ?? null,
    });
  }
  return { uniqueResults, replayedResults };
}

export function sessionIdFromFile(file) {
  return path.basename(path.dirname(resolveSessionFile(file))).replace(/^session-/, '');
}

/** Provider-reported request accounting, separate from tools and scene effects.
 * Repeated cumulative usage for a request is replaced, never added twice.
 * Missing fields stay unknown. No inference about billing or retained messages.
 */
export function collectRequestTelemetry(events) {
  const fields = ['inputTokens', 'outputTokens', 'cacheReadTokens', 'cacheWriteTokens', 'totalTokens'];
  const requests = new Map();
  let duplicateUsageEvents = 0;
  let updatedUsageEvents = 0;
  const count = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
  for (const event of events) {
    const d = event.data;
    if (event.type !== 'assistant/chunk' || d?.chunk?.type !== 'usage') continue;
    const key = d.turn != null && d.step != null ? `${d.turn}/${d.step}` : `seq:${event.seq}`;
    const usage = Object.fromEntries(fields.map(f => [f, count(d.chunk.usage?.[f])]));
    const prior = requests.get(key);
    if (prior) {
      if (fields.every(f => prior[f] === usage[f])) duplicateUsageEvents++;
      else updatedUsageEvents++;
    }
    const sum = usage.inputTokens == null || usage.outputTokens == null ? null
      : usage.inputTokens + usage.outputTokens + (usage.cacheReadTokens ?? 0) + (usage.cacheWriteTokens ?? 0);
    const arithmeticMatches = sum == null || usage.totalTokens == null ? null : sum === usage.totalTokens;
    requests.set(key, {seq:event.seq, time:event.time, turn:d.turn ?? null, step:d.step ?? null, ...usage,
      arithmeticMatches,
      inputWithCache: arithmeticMatches === true ? sum - usage.outputTokens : null});
  }
  const rows = [...requests.values()];
  const measuredFields = Object.fromEntries(fields.map(f => [f, rows.filter(r => r[f] != null).length]));
  const totals = Object.fromEntries(fields.map(f => [f, measuredFields[f] ? rows.reduce((n,r) => n+(r[f] ?? 0),0) : null]));
  const turnEnds = events.filter(e => e.type === 'turn/end').map(e => ({seq:e.seq,time:e.time,
    turn:e.data?.turn ?? null, kind:e.data?.reason?.kind ?? 'unknown',
    code:e.data?.reason?.error?.code ?? null,
    // Only the error message, never request headers/credentials/config bodies.
    message: typeof e.data?.reason?.error?.message === 'string'
      ? e.data.reason.error.message.replace(/Bearer\s+\S+|sk-[A-Za-z0-9_-]+/gi, '[redacted]').slice(0,800) : null}));
  return {requests:rows, requestCount:rows.length, duplicateUsageEvents, updatedUsageEvents,
    totals, measuredFields, last:rows.at(-1) ?? null,
    arithmeticMismatchSeqs:rows.filter(r => r.arithmeticMatches === false).map(r => r.seq),
    turnEnds, upstreamTurnErrors:turnEnds.filter(e => e.kind === 'error'),
    compactionEvents:events.filter(e => e.type?.startsWith('compaction/')).map(e => ({seq:e.seq,time:e.time,type:e.type})),
    goalChanges:events.filter(e => e.type === 'goal/change').map(e => ({seq:e.seq,time:e.time,
      operation:e.data?.operation ?? null, phase:e.data?.goal?.phase ?? null,
      objective:e.data?.goal?.objective ?? null})),
    note:'Provider-reported cumulative fields per turn/step; totals repeatedly count history, not unique content or billing. Missing usage is unknown. Input plus cache is derived only when the reported arithmetic agrees (absent cache treated as zero for that check). No recorded compaction does not prove full message retention.'};
}
