import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { createHash } from 'node:crypto';

// Legacy traces remain readable without DSH installed. V3 is certified only
// by the public native validator; absence is reported as unknown, not emulated.
let nativeSurfaceApi = null;
try {
  const [session, surface] = await Promise.all([
    import('@deepseek-ai/dsh-session'), import('@deepseek-ai/dsh-session/surface'),
  ]);
  nativeSurfaceApi = {SurfaceManager:surface.SurfaceManager,
    snapshot:session.snapshotSessionEvent, message:session.deriveEventMessage,
    version:session.SESSION_FORMAT_VERSION};
} catch { /* collectRequestContexts reports the unavailable validator explicitly */ }

const ZSTD_MAGIC = [0x28, 0xb5, 0x2f, 0xfd];

/** Find the most recently modified trace under the DSH session store. */
export function newestSessionFile(root = path.join(os.homedir(), '.dsh', 'sessions')) {
  if (!fs.existsSync(root)) return null;
  let best = null;
  for (const workspace of fs.readdirSync(root)) {
    const workspaceDir = path.join(root, workspace);
    if (!fs.statSync(workspaceDir).isDirectory()) continue;
    for (const session of fs.readdirSync(workspaceDir)) {
      for (const name of ['session.v3.jsonl.zstd', 'session.jsonl.zstd']) {
        const file = path.join(workspaceDir, session, name);
        if (!fs.existsSync(file)) continue;
        const modified = fs.statSync(file).mtimeMs;
        if (!best || modified > best.modified) best = { file, modified };
      }
    }
  }
  return best?.file ?? null;
}

/** Resolve either a session directory or a session.jsonl.zstd file. */
export function resolveSessionFile(input) {
  if (!input) throw new Error('session path is required');
  const absolute = path.resolve(input);
  if (!fs.existsSync(absolute)) throw new Error(`session path does not exist: ${absolute}`);
  if (!fs.statSync(absolute).isDirectory()) return absolute;
  const v3 = path.join(absolute, 'session.v3.jsonl.zstd');
  return fs.existsSync(v3) ? v3 : path.join(absolute, 'session.jsonl.zstd');
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
  const fields = ['inputTokens', 'outputTokens', 'cacheReadTokens', 'cacheWriteTokens', 'totalTokens', 'reasoningTokens'];
  const requests = new Map();
  let duplicateUsageEvents = 0;
  let updatedUsageEvents = 0;
  const count = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
  for (const event of events) {
    const d = event.data;
    // V3 persists settled usage on the message, including interrupted messages.
    // Keep legacy chunk logs readable; mixed records share one turn/step key.
    const reportedUsage = event.type === 'assistant/message' ? d?.usage
      : event.type === 'assistant/chunk' && d?.chunk?.type === 'usage' ? d.chunk.usage : null;
    if (!reportedUsage || typeof reportedUsage !== 'object') continue;
    const key = d.turn != null && d.step != null ? `${d.turn}/${d.step}` : `seq:${event.seq}`;
    const usage = Object.fromEntries(fields.map(f => [f, count(reportedUsage[f])]));
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
    note:'Provider-reported cumulative fields per turn/step; totals repeatedly count history, not unique content or billing. reasoningTokens is a subset of outputTokens, never added to totalTokens. Missing usage is unknown. Input plus cache is derived only when the reported arithmetic agrees (absent cache treated as zero for that check). No recorded compaction does not prove full message retention.'};
}

/** Request-prefix surface accounting. Never includes streams, usage or canonical
 * metadata as model text. Text sizes are characters, not provider token counts.
 * V3 replacements use their exact visible endpoints; malformed/missing history
 * is marked unknown instead of certifying a stale system prompt.
 */
export function collectRequestContexts(events, {includeSystemText = false} = {}) {
  const fileVersion = events[0]?.type === 'session' ? events[0].version : undefined;
  const v3 = fileVersion >= 3 || events.some(e => e.surfaceOp !== undefined);
  const eligible = new Set(['system/message', 'user/message', 'assistant/message', 'tool/result']);
  const surface = [], rows = [], seenRequests = new Set();
  const nativeLog = [];
  const manager = v3 && typeof nativeSurfaceApi?.SurfaceManager === 'function'
    ? new nativeSurfaceApi.SurfaceManager(nativeLog) : null;
  let header = {}, complete = !v3 || !!manager, projectionError = complete ? null : 'Native V3 surface validator unavailable';
  if (v3 && fileVersion > nativeSurfaceApi?.version) {
    complete = false; projectionError = 'Session format is newer than the installed native validator';
  }
  const message = e => v3 ? nativeSurfaceApi.message(e)
    : e.type === 'user/message' ? e.data : e.data?.message;
  const reject = (event, error) => {
    complete = false;
    const text = String(error?.message || '');
    const category = /surfaceOp/.test(text) ? 'invalid or missing surface marker'
      : /sourceEventSeqs/.test(text) ? 'invalid replacement provenance'
      : /tool\/result.*replace/.test(text) ? 'illegal tool-result replacement'
      : /system prompt|node 0/.test(text) ? 'protected system head replacement'
      : /seq|contiguous/.test(text) ? 'noncontiguous event sequence' : 'invalid event/message invariant';
    projectionError ??= `Native V3 validation rejected seq ${event.seq}: ${category}`;
  };
  const snapshot = (event, boundary = 'before_assistant_message') => {
    const parts = {system:0,user:0,plugin:0,skill_catalog:0,assistant_text:0,reasoning:0,tool_arguments:0,tool_results:0};
    const systems = [];
    let messageCount = 0;
    const visible = complete ? (v3 ? manager.nodes.map(seq=>nativeLog[seq]) : surface) : [];
    for (const e of visible) {
      const m = message(e);
      if (!m) continue;
      if (['system/message','assistant/message'].includes(e.type) && !m.content?.length) continue;
      messageCount++;
      const category = e.type === 'system/message' ? 'system'
        : e.type === 'tool/result' ? 'tool_results'
        : e.type === 'assistant/message' ? 'assistant_text'
        : m.source?.kind === 'user' ? 'user' : m.source?.kind === 'skill-catalog' ? 'skill_catalog' : 'plugin';
      const walk = blocks => {
        for (const b of blocks || []) {
          if (typeof b.text === 'string') {
            parts[b.type === 'reasoning' ? 'reasoning' : category] += b.text.length;
            if (category === 'system' && b.type === 'text') systems.push(b.text);
          }
          if (b.type === 'tool-call') parts.tool_arguments += typeof b.arguments === 'string' ? b.arguments.length : JSON.stringify(b.arguments ?? {}).length;
          if (b.type === 'tool-result' || b.type === 'tool_result') walk(b.content);
        }
      };
      walk(m.content);
    }
    const system = systems.length ? systems.join('\n') : !v3 ? header.system || '' : '';
    if (!systems.length) parts.system = system.length;
    const tools = header.tools || [];
    rows.push({seq:event.seq,time:event.time,turn:event.data?.turn ?? null,step:event.data?.step ?? null,
      boundary,projectionComplete:complete,projectionError,model:complete ? header.config?.model ?? null : null,
      systemChars:complete ? system.length : null,
      systemHash:complete ? createHash('sha256').update(system).digest('hex').slice(0,16) : null,
      systemSource:!complete ? 'unknown_invalid_surface' : systems.length ? 'surface_system_messages' : v3 ? 'no_visible_system_message' : 'legacy_header',
      toolsSchemaChars:complete ? JSON.stringify(tools).length : null,
      availableTools:complete ? tools.map(t=>t.name || t.function?.name).filter(Boolean).sort() : null,
      surfaceMessageCount:complete ? messageCount : null,
      contentChars:complete ? Object.values(parts).reduce((a,b)=>a+b,0) : null,
      charactersByKind:complete ? parts : null,
      ...(includeSystemText ? {systemText:complete ? system : null} : {}),
      scope:'Reconstructed logged request prefix; characters are not tokens or billing. Excludes transport transforms and unlogged middleware.'});
  };
  for (const [eventIndex,raw] of events.entries()) {
    if (raw.type === 'session' && raw.seq == null) {
      if (eventIndex !== 0) reject(raw,new Error('duplicate file header'));
      continue;
    }
    let e = raw;
    if (v3 && complete) {
      try {
        e = nativeSurfaceApi.snapshot(raw);
        manager.validateNext(e); // validate BEFORE certifying this request prefix
      } catch (error) { reject(raw,error); }
    }
    if (e.type === 'request/header') header = e.data?.header || {};
    if (e.type === 'assistant/message') {
      const key = e.data?.turn != null && e.data?.step != null ? `${e.data.turn}/${e.data.step}` : `seq:${e.seq}`;
      if (!seenRequests.has(key)) { snapshot(e); seenRequests.add(key); }
    }
    if (v3) {
      if (complete) {
        nativeLog.push(e);
        try { void manager.nodes; } catch (error) { reject(e,error); }
      }
    } else if (eligible.has(e.type)) surface.push(e);
  }
  if (!rows.length) snapshot(events.at(-1) || {}, 'header_only_no_observed_response');
  return rows;
}
