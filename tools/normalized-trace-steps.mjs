import {
  isMutatingRawMethodName,
  mutatingRawMethodNames,
  parseVerbLedgerLine,
  rawMethodNames,
} from '../skills/houdini-trace-analysis/scripts/evidence-helpers.mjs';
import { toolResultCallId, uniqueToolResultEvents } from './trace-session-lib.mjs';

function nestedResultContent(message) {
  return (message?.content || [])
    .filter((item) => item?.type === 'tool_result' || Array.isArray(item?.content))
    .flatMap((item) => item.content || []);
}

export function toolResultText(message) {
  return nestedResultContent(message)
    .filter((item) => item?.type === 'text')
    .map((item) => String(item.text || ''))
    .join('\n');
}

export function parseToolArguments(value) {
  if (value && typeof value === 'object') return value;
  try {
    const parsed = JSON.parse(value || '{}');
    return parsed && typeof parsed === 'object' ? parsed : { _raw: String(value ?? '') };
  }
  catch { return { _raw: String(value ?? '') }; }
}

function parseJsonBlock(text, label) {
  const match = text.match(new RegExp(`${label}:\\n([\\s\\S]*?)(?:\\n\\n|$)`));
  if (!match) return null;
  try { return JSON.parse(match[1]); }
  catch { return { _raw: match[1] }; }
}

export function parseVerbLedger(text) {
  const match = text.match(/verbs \((\d+)\):\n([\s\S]*?)(?:\n\n|$)/);
  if (!match) return [];
  return match[2].split('\n').flatMap((line) => {
    const parsed = parseVerbLedgerLine(line);
    if (!parsed) return [];
    let result = parsed.result;
    try { result = JSON.parse(parsed.result); } catch {}
    return [{
      ledgerIndex: parsed.ledgerIndex,
      ok: parsed.ok,
      verb: parsed.verb,
      args: parsed.args,
      result,
      resultText: parsed.result,
      ms: parsed.ms,
    }];
  });
}

export function toolResultFailed(message, text = toolResultText(message)) {
  return Boolean(message?.isError || message?.content?.some((item) => item?.isError))
    || /^Execution failed\b/.test(text)
    || /\nExecution failed:/.test(text)
    || /^Error:/.test(text);
}

/**
 * Correlate tool calls with their first execution result and expose one stable,
 * consumer-neutral step shape. Compaction replays remain diagnostics and never
 * become a second step.
 */
export function normalizeTraceSteps(events) {
  const calls = new Map();
  for (const event of events || []) {
    if (event?.type === 'tool/call' && event.data?.callId) {
      calls.set(event.data.callId, {
        ...event.data,
        eventSeq: event.seq,
        time: event.time,
      });
    }
  }

  const { uniqueResults, replayedResults } = uniqueToolResultEvents(events || []);
  const steps = [];
  const unmatchedResults = [];
  for (const event of uniqueResults) {
    const callId = toolResultCallId(event);
    const call = calls.get(callId);
    if (!call) {
      unmatchedResults.push({
        callId,
        resultSeq: event.seq ?? null,
        time: event.time ?? null,
      });
      continue;
    }

    const message = event.data?.message || {};
    const args = parseToolArguments(call.arguments);
    const code = typeof args.code === 'string' ? args.code : '';
    const resultText = toolResultText(message);
    const rawUsage = parseJsonBlock(resultText, 'raw-usage');
    const mutatingRawMethods = rawUsage && !rawUsage._raw
      ? [...(rawUsage.coveredMutations || []), ...(rawUsage.suspectedMutations || [])]
        .filter((item) => isMutatingRawMethodName(item?.name))
        .flatMap((item) => Array(Number(item.count) || 1).fill(String(item.name)))
      : mutatingRawMethodNames(code);
    const advisoryMatch = resultText.match(/hint:\n([\s\S]*?)$/);

    steps.push({
      index: steps.length + 1,
      callId,
      callSeq: call.eventSeq ?? null,
      resultSeq: event.seq ?? null,
      time: event.time ?? null,
      turn: event.data?.turn ?? null,
      step: event.data?.step ?? null,
      tool: call.name || '?',
      isHoudini: String(call.name || '').startsWith('houdini_'),
      failed: toolResultFailed(message, resultText),
      args,
      code,
      resultText,
      verbs: parseVerbLedger(resultText),
      rawMethods: rawMethodNames(code),
      mutatingRawMethods,
      advisory: advisoryMatch ? advisoryMatch[1].trim() : null,
      rollback: parseJsonBlock(resultText, 'rollback'),
      rawUsage,
    });
  }

  return { steps, replayedResults, unmatchedResults };
}
