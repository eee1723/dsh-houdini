import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

const ZSTD_MAGIC = [0x28, 0xb5, 0x2f, 0xfd];

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
