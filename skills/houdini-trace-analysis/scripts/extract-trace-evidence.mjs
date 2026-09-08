#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { loadCatalog } from '../../../tools/catalog-lib.mjs';
import {
  loadSessionEvents,
  newestSessionFile,
  resolveSessionFile,
  sessionIdFromFile,
  collectRequestTelemetry,
} from '../../../tools/trace-session-lib.mjs';
import { normalizeTraceSteps } from '../../../tools/normalized-trace-steps.mjs';
import {
  collectValidationCoverage,
  collectRetryWork,
  collectQualityLoopEvidence,
  completedVisionTodoWithoutEvidence,
  classifyVisionEvidence,
  collectVerbAdoption,
  isStructuredHoudiniCall,
  extractAvailableSkills,
  findBatchSetParmOpportunities,
  findQueryMutationSteps,
  findSuppressedCookFailures,
  qualityLoopRisks,
  requestedGoalReportedUnverified,
} from './evidence-helpers.mjs';

const SKILL_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..');
const PACKAGE_ROOT = path.resolve(SKILL_ROOT, '..', '..');

function usage() {
  console.log(`Usage:
  node extract-trace-evidence.mjs [sessionDir|session.jsonl.zstd ...]
       [--catalog <tool-design.md>] [--out <evidence.json>]
       [--max-preview <chars>] [--compact]

With no session argument, analyzes the newest ~/.dsh/sessions trace.
Multiple inputs produce per-trace evidence plus cross-trace aggregate counts.`);
}

const argv = process.argv.slice(2);
const inputs = [];
let catalogPath = path.join(PACKAGE_ROOT, 'docs', 'tool-design.md');
let outPath = null;
let maxPreview = 3000;
let compact = false;
for (let i = 0; i < argv.length; i++) {
  const arg = argv[i];
  if (arg === '--help' || arg === '-h') { usage(); process.exit(0); }
  if (arg === '--catalog') catalogPath = path.resolve(argv[++i]);
  else if (arg === '--out') outPath = path.resolve(argv[++i]);
  else if (arg === '--max-preview') maxPreview = Number(argv[++i]);
  else if (arg === '--compact') compact = true;
  else if (arg.startsWith('--')) throw new Error(`unknown option: ${arg}`);
  else inputs.push(arg);
}
if (!Number.isSafeInteger(maxPreview) || maxPreview < 200) {
  throw new Error('--max-preview must be an integer >= 200');
}

const latest = inputs.length ? null : newestSessionFile();
if (!inputs.length && !latest) throw new Error('no session.jsonl.zstd under the DSH session store');
const sessionFiles = (inputs.length ? inputs : [latest]).map(resolveSessionFile);
const catalog = loadCatalog(catalogPath);
const catalogNames = catalog.flatMap((domain) => domain.verbs.map((verb) => verb.name));
const catalogByName = new Map();
for (const domain of catalog) {
  for (const verb of domain.verbs) catalogByName.set(verb.name, { domain: domain.domain, ...verb });
}

const clip = (value, max = maxPreview) => {
  const text = String(value ?? '');
  return text.length <= max ? text : `${text.slice(0, max)}…[+${text.length - max}ch]`;
};
const addCount = (target, key, amount = 1) => { target[key] = (target[key] || 0) + amount; };
const sortCounts = (counts) => Object.fromEntries(
  Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])),
);
const digest = (text) => crypto.createHash('sha256').update(text).digest('hex').slice(0, 16);

function directText(content) {
  return (content || []).filter((item) => item.type === 'text').map((item) => item.text).join('\n');
}

function analyzeTrace(file) {
  const loaded = loadSessionEvents(file);
  const { events } = loaded;
  const normalized = normalizeTraceSteps(events);
  const { replayedResults, unmatchedResults } = normalized;

  const userMessages = [];
  const assistantMessages = [];
  const capabilitySnapshots = [];
  const skillCatalogSnapshots = [];
  const seenCapabilityHashes = new Set();
  const steps = [];
  const toolCounts = {};
  const verbCounts = {};
  const verbFailures = {};
  const rawMethodCounts = {};
  let firstTime = Infinity;
  let lastTime = 0;
  let lastToolTime = 0;
  let firstToolTime = Infinity;
  let lastAssistantTime = 0;

  for (const event of events) {
    if (Number.isFinite(event.time)) {
      firstTime = Math.min(firstTime, event.time);
      lastTime = Math.max(lastTime, event.time);
    }
    if (event.type === 'user/message') {
      const text = directText(event.data.content);
      const availableSkills = extractAvailableSkills(text);
      if (availableSkills.length) {
        skillCatalogSnapshots.push({
          seq: event.seq,
          time: event.time,
          turn: event.data?.turn,
          step: event.data?.step,
          skills: availableSkills,
        });
      }
      if (event.data?.source?.kind === 'user'
          && text && !text.startsWith('<system-reminder>')
          && !text.startsWith('Current runtime context')) {
        userMessages.push({ seq: event.seq, time: event.time, text });
      }
    } else if (event.type === 'assistant/message') {
      const text = directText(event.data?.message?.content);
      if (text.trim()) {
        assistantMessages.push({ seq: event.seq, time: event.time, text });
        lastAssistantTime = Math.max(lastAssistantTime, event.time || 0);
      }
    } else if (event.type === 'request/header') {
      const system = event.data?.header?.system || '';
      const hash = digest(system);
      if (system && !seenCapabilityHashes.has(hash)) {
        seenCapabilityHashes.add(hash);
        const listedSkills = [...system.matchAll(/^- `([^`]+)`: /gm)].map((match) => match[1]);
        capabilitySnapshots.push({
          seq: event.seq,
          time: event.time,
          turn: event.data?.turn,
          step: event.data?.step,
          model: event.data?.header?.config?.model || null,
          systemChars: system.length,
          systemHash: hash,
          personaLines: system.split('\n').filter(line => /^You are (?:a|an) /.test(line)).slice(0, 4),
          mentionedCatalogVerbs: catalogNames.filter(
            (name) => new RegExp(`\\b${name}\\b`).test(system),
          ),
          availableTools: (event.data?.header?.tools || [])
            .map((tool) => tool?.name || tool?.function?.name)
            .filter(Boolean)
            .sort(),
          // Some dsh runtimes expose the skill loader without embedding a skill catalog in
          // the request header. `[]` would falsely mean "no skills were available"; null means
          // "the header did not declare availability". Actual successful loads are reported
          // separately as skillActivations below.
          availableSkills: listedSkills.length ? listedSkills : null,
        });
      }
    }
  }

  for (const source of normalized.steps) {
    const code = source.code;
    const verbs = source.verbs.map((verb) => ({
      ledgerIndex: verb.ledgerIndex,
      ok: verb.ok,
      verb: verb.verb,
      args: clip(verb.args),
      result: verb.result,
      ms: verb.ms,
    }));
    const step = {
      index: source.index,
      callSeq: source.callSeq,
      resultSeq: source.resultSeq,
      time: source.time,
      callTime: source.callTime,
      durationMs: source.durationMs,
      canonical: compact ? undefined : source.canonical,
      canonicalStatus: source.canonicalStatus,
      turn: source.turn,
      step: source.step,
      tool: source.tool,
      isHoudini: source.isHoudini,
      failed: source.failed,
      args: compact && code ? { ...source.args, code: undefined } : source.args,
      codeChars: code.length,
      codeHash: code ? digest(code) : null,
      code: compact ? undefined : code,
      codePreview: code ? clip(code.replace(/\s+/g, ' '), 800) : null,
      resultPreview: clip(source.resultText),
      verbs,
      rawMethods: source.rawMethods,
      mutatingRawMethods: source.mutatingRawMethods,
      advisory: source.advisory,
      transaction: source.transaction,
      rollback: source.rollback?._raw ? { _raw: clip(source.rollback._raw) } : source.rollback,
      rawUsage: source.rawUsage?._raw ? { _raw: clip(source.rawUsage._raw) } : source.rawUsage,
    };
    // Keep the unabridged result only in memory for coverage extraction. It is
    // deliberately non-enumerable so compact/full evidence JSON does not
    // duplicate potentially huge tool output, while render paths and nested
    // render_check facts remain recoverable before serialization.
    Object.defineProperty(step, 'resultText', { value: source.resultText, enumerable: false });
    // Compact is a serialization choice, not an analysis input. Dropping code
    // here used to erase relationship probes from otherwise identical traces.
    Object.defineProperty(step, 'code', { value: code, enumerable: !compact });
    steps.push(step);
    firstToolTime = Math.min(firstToolTime, source.callTime ?? source.time ?? Infinity);
    lastToolTime = Math.max(lastToolTime, source.time || 0);
    addCount(toolCounts, step.tool);
    for (const method of source.rawMethods) addCount(rawMethodCounts, method);
    for (const verb of verbs) {
      addCount(verbCounts, verb.verb);
      if (!verb.ok) addCount(verbFailures, verb.verb);
    }
  }

  const failedCalls = steps.filter((step) => step.failed).map((step) => ({
    index: step.index,
    time: step.time,
    tool: step.tool,
    resultPreview: step.resultPreview,
  }));
  const failedVerbCalls = steps.flatMap((step) => step.verbs
    .filter((verb) => !verb.ok)
    .map((verb) => ({ index: step.index, time: step.time, ...verb })));
  const partialParameterFailures = steps.flatMap((step) => step.verbs
    .filter((verb) => verb.verb === 'set_parms' && verb.ok && verb.result?.failed && Object.keys(verb.result.failed).length)
    .map((verb) => ({index: step.index, time: step.time, failed: verb.result.failed})));
  const rawHoudiniNoVerb = steps.filter((step) => step.isHoudini && !isStructuredHoudiniCall(step) && !step.verbs.length).map((step) => ({
    index: step.index,
    time: step.time,
    tool: step.tool,
    codePreview: step.codePreview,
    rawMethods: step.rawMethods,
    mutatingRawMethods: step.mutatingRawMethods,
  }));
  const rawMutationSteps = steps.filter(
    (step) => step.isHoudini && step.mutatingRawMethods.length,
  ).map((step) => ({
    index: step.index,
    time: step.time,
    tool: step.tool,
    codePreview: step.codePreview,
    mutatingRawMethods: step.mutatingRawMethods,
    mixedWithVerbs: step.verbs.length > 0,
  }));
  const verblessMutations = rawMutationSteps.filter((step) => !step.mixedWithVerbs);
  const execUsedForReadOnly = rawHoudiniNoVerb.filter(
    (step) => step.tool === 'houdini_exec' && !step.mutatingRawMethods.length,
  );
  const queryWithMutation = findQueryMutationSteps(steps);
  const batchSetParmOpportunities = findBatchSetParmOpportunities(steps);
  const suppressedCookFailureSteps = findSuppressedCookFailures(steps);
  const renderEvidence = steps.flatMap((step) => step.verbs
    .filter((verb) => ['render_view', 'render_frame', 'render_check'].includes(verb.verb))
    .map((verb) => ({ index: step.index, time: step.time, verb: verb.verb, ok: verb.ok, result: verb.result })));
  const visionEvidence = steps.filter(
    (step) => step.tool.startsWith('vision_') || step.tool === 'read_image',
  ).map((step) => ({
    index: step.index,
    time: step.time,
    tool: step.tool,
    args: step.args,
    resultPreview: step.resultPreview,
    ...classifyVisionEvidence(step),
  }));
  const successfulVisionEvidence = visionEvidence.filter(
    (item) => item.role === 'inspection' && item.semanticOk === true,
  );
  const skillActivations = steps.filter((step) => step.tool === 'skill').map((step) => ({
    index: step.index,
    time: step.time,
    name: typeof step.args?.name === 'string' ? step.args.name : null,
    succeeded: !step.failed,
  }));
  const qualityLoopEvidence = collectQualityLoopEvidence({
    steps,
    userMessages,
    assistantMessages,
    availableTools: capabilitySnapshots.flatMap((snapshot) => snapshot.availableTools || []),
    activatedSkills: skillActivations.filter((item) => item.succeeded).map((item) => item.name),
  });
  const completionRisks = [];
  const turnEnd = [...events].reverse().find((event) => event.type === 'turn/end') || null;
  const terminalReason = turnEnd?.data?.reason || null;
  const terminalMessage = String(
    terminalReason?.error?.message
    || terminalReason?.failure?.message
    || terminalReason?.message
    || '',
  );
  const terminalCode = terminalReason?.error?.code || terminalReason?.failure?.code || terminalReason?.code || null;
  const terminalCategory = /insufficient_quota|quota has been exhausted/i.test(terminalMessage)
    ? 'quota_exhausted'
    : terminalReason?.kind === 'error'
      ? 'external_error'
      : terminalReason?.kind || null;
  if (terminalCategory === 'quota_exhausted') {
    completionRisks.push({
      code: 'quota_exhausted',
      detail: 'The run ended because the model/provider quota was exhausted, not because the task reached delivery.',
    });
  }
  if (renderEvidence.length && !successfulVisionEvidence.length) {
    completionRisks.push({
      code: 'render_without_successful_vision',
      detail: 'Render evidence exists, but no vision tool successfully inspected an image.',
    });
  }
  if (visionEvidence.some((item) => item.transportOk === false || item.reason)) {
    completionRisks.push({
      code: 'vision_tool_failed',
      detail: 'At least one attempted vision inspection failed.',
    });
  }
  const workStarted = steps.length > 0 || assistantMessages.length > 0;
  if (workStarted) completionRisks.push(...qualityLoopRisks(qualityLoopEvidence));
  const unverifiedRequestedGoals = requestedGoalReportedUnverified(userMessages, assistantMessages);
  if (unverifiedRequestedGoals.length) {
    completionRisks.push({
      code: 'requested_goal_reported_unverified',
      detail: `The final delivery presents the task as complete while user-requested dimension(s) remain unverified: ${unverifiedRequestedGoals.map((item) => item.signal).join(', ')}.`,
      items: unverifiedRequestedGoals,
    });
  }
  const validationCoverage = collectValidationCoverage(steps);
  const edgeContact = validationCoverage.comparisons.filter((item) => item.touches_edge === true);
  if (edgeContact.length) {
    completionRisks.push({
      code: 'render_framing_edge_contact',
      detail: `${edgeContact.length} render_check result(s) have content touching the image edge; fixed-camera evidence may be clipped.`,
      steps: [...new Set(edgeContact.map((item) => item.index))],
    });
  }
  const verbAdoption = collectVerbAdoption(steps);
  const repeatedCode = Object.entries(steps.reduce((groups, step) => {
    if (!step.codeHash) return groups;
    (groups[step.codeHash] ||= []).push(step.index);
    return groups;
  }, {})).filter(([, indices]) => indices.length > 1).map(([hash, indices]) => ({ hash, indices }));
  const gaps = [];
  for (let i = 1; i < steps.length; i++) {
    const ms = steps[i].time - steps[i - 1].time;
    if (ms >= 60_000) gaps.push({ after: steps[i - 1].index, before: steps[i].index, ms });
  }
  const usedVerbs = Object.keys(verbCounts);
  const usedDomains = [...new Set(usedVerbs.map((name) => catalogByName.get(name)?.domain).filter(Boolean))];
  let latestTodo = null;
  for (const step of steps) {
    if (step.tool !== 'todo_write' || !step.args?.todos) continue;
    latestTodo = step.args.todos;
  }
  const unfinishedTodoCount = latestTodo?.filter((item) => item.status !== 'completed').length ?? null;
  const completedVisionTodoRisk = completedVisionTodoWithoutEvidence(
    latestTodo,
    successfulVisionEvidence,
  );
  if (completedVisionTodoRisk) {
    completionRisks.push({
      code: 'completed_vision_todo_without_evidence',
      detail: 'A vision-related todo was marked complete without a successful semantic image inspection.',
    });
  }
  const assistantAfterLastTool = lastAssistantTime > lastToolTime;
  if (suppressedCookFailureSteps.length) {
    completionRisks.push({
      code: 'suppressed_cook_failure',
      detail: `${suppressedCookFailureSteps.length} successful tool envelope(s) printed a raw cook failure.`,
      steps: suppressedCookFailureSteps.map((item) => item.index),
    });
  }
  if (unfinishedTodoCount > 0) {
    completionRisks.push({
      code: 'unfinished_todos',
      detail: `${unfinishedTodoCount} todo item(s) were not completed when the trace ended.`,
    });
  }
  if (lastToolTime && !assistantAfterLastTool) {
    completionRisks.push({
      code: 'no_final_delivery_after_last_tool',
      detail: 'No assistant delivery message followed the final tool result.',
    });
  }
  const initialRequest = userMessages.find(
    (message) => message.time <= firstToolTime,
  ) || null;
  return {
    sessionId: sessionIdFromFile(file),
    file: loaded.file,
    frames: loaded.frames,
    frameErrors: loaded.frameErrors,
    replayedResults,
    unmatchedResults,
    eventCount: events.length,
    effectivePreset: {
      initial: events.find(e => e.type === 'session')?.agentPreset ?? null,
      changes: events.filter(e => e.type === 'agent-preset/selected').map(e => ({seq:e.seq,time:e.time,preset:e.data?.agentPreset})),
    },
    observationContexts: events.filter(e => e.type === 'user/message' && e.data?.source?.kind === 'plugin')
      .flatMap(e => (e.data?.source?.sections || []).filter(s => s.name === 'dsh-houdini:scene-context')
        .map(s => ({seq:e.seq,time:e.time,text:s.text}))),
    executionCost: {
      toolDurationSumMs: steps.reduce((n,s) => n + (s.durationMs ?? 0), 0),
      measuredToolDurations: steps.filter(s => s.durationMs !== null).length,
      resultChars: normalized.steps.reduce((n,s) => n+s.resultText.length,0),
      note: 'Call-to-result sum includes waits and possible overlap; gaps are not a direct model inference-time measurement.',
    },
    requestTelemetry: collectRequestTelemetry(events),
    startTime: Number.isFinite(firstTime) ? firstTime : null,
    endTime: lastTime || null,
    durationMs: Number.isFinite(firstTime) && lastTime ? lastTime - firstTime : null,
    taskTiming: {
      initialRequest,
      firstToolTime: Number.isFinite(firstToolTime) ? firstToolTime : null,
      lastToolTime: lastToolTime || null,
      firstToolLatencyMs: initialRequest && Number.isFinite(firstToolTime)
        ? firstToolTime - initialRequest.time
        : null,
      requestToLastToolMs: initialRequest && lastToolTime
        ? lastToolTime - initialRequest.time
        : null,
      toolSpanMs: Number.isFinite(firstToolTime) && lastToolTime
        ? lastToolTime - firstToolTime
        : null,
    },
    userMessages,
    capabilitySnapshots,
    skillCatalogSnapshots,
    skillActivations,
    assistantMessages: compact ? undefined : assistantMessages,
    toolCalls: steps.length,
    toolCounts: sortCounts(toolCounts),
    verbCalls: Object.values(verbCounts).reduce((sum, count) => sum + count, 0),
    verbCounts: sortCounts(verbCounts),
    verbFailures: sortCounts(verbFailures),
    verbAdoption,
    catalog: {
      total: catalogNames.length,
      used: usedVerbs.length,
      usedNames: usedVerbs.sort(),
      unusedNames: catalogNames.filter((name) => !verbCounts[name]),
      usedDomains: usedDomains.sort(),
    },
    failedCalls,
    failedVerbCalls,
    partialParameterFailures,
    rawHoudiniNoVerb,
    rawMutationSteps,
    verblessMutations,
    execUsedForReadOnly,
    queryWithMutation,
    rawMethodCounts: sortCounts(rawMethodCounts),
    advisorySteps: steps.filter((step) => step.advisory).map((step) => step.index),
    rollbackSteps: steps.filter((step) => step.rollback).map((step) => ({
      index: step.index, rollback: step.rollback,
    })),
    batchSetParmOpportunities,
    suppressedCookFailureSteps,
    renderEvidence,
    visionEvidence,
    completionRisks,
    qualityLoopEvidence,
    validationCoverage,
    repeatedCode,
    retryWork: collectRetryWork(normalized.steps),
    timelineGaps: gaps,
    totalCodeChars: steps.reduce((sum, step) => sum + step.codeChars, 0),
    execCodeChars: steps.filter((step) => step.tool === 'houdini_exec').reduce((sum, step) => sum + step.codeChars, 0),
    latestTodo,
    terminal: {
      lastEventType: events.at(-1)?.type || null,
      reason: terminalCategory,
      reasonCode: terminalCode,
      reasonMessage: terminalMessage || null,
      lastToolTime: lastToolTime || null,
      lastAssistantTime: lastAssistantTime || null,
      assistantAfterLastTool,
      unfinishedTodoCount,
    },
    steps,
  };
}

const traces = sessionFiles.map(analyzeTrace);
const aggregateToolCounts = {};
const aggregateVerbCounts = {};
const aggregateVerbFailures = {};
const verbTraceHits = {};
for (const trace of traces) {
  for (const [name, count] of Object.entries(trace.toolCounts)) addCount(aggregateToolCounts, name, count);
  for (const [name, count] of Object.entries(trace.verbCounts)) {
    addCount(aggregateVerbCounts, name, count);
    addCount(verbTraceHits, name);
  }
  for (const [name, count] of Object.entries(trace.verbFailures)) addCount(aggregateVerbFailures, name, count);
}
const output = {
  schemaVersion: 2,
  generatedAt: new Date().toISOString(),
  catalogPath: path.resolve(catalogPath),
  traceCount: traces.length,
  aggregate: {
    toolCalls: traces.reduce((sum, trace) => sum + trace.toolCalls, 0),
    verbCalls: traces.reduce((sum, trace) => sum + trace.verbCalls, 0),
    toolCounts: sortCounts(aggregateToolCounts),
    verbCounts: sortCounts(aggregateVerbCounts),
    verbFailures: sortCounts(aggregateVerbFailures),
    verbTraceHits: sortCounts(verbTraceHits),
    neverUsedCatalogVerbs: catalogNames.filter((name) => !aggregateVerbCounts[name]),
  },
  traces,
};
const json = `${JSON.stringify(output, null, 2)}\n`;
if (outPath) {
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, json, 'utf8');
  console.error(`wrote ${outPath}: ${traces.length} trace(s), ${output.aggregate.toolCalls} tool calls`);
} else {
  process.stdout.write(json);
}
