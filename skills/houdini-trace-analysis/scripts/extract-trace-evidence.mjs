#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { loadCatalog } from '../../../tools/catalog-lib.mjs';
import {
  loadSessionEvents,
  resolveSessionFile,
  sessionIdFromFile,
} from '../../../tools/trace-session-lib.mjs';

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

function newestSession() {
  const root = path.join(os.homedir(), '.dsh', 'sessions');
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
  if (!best) throw new Error(`no session.jsonl.zstd under ${root}`);
  return best.file;
}

const sessionFiles = (inputs.length ? inputs : [newestSession()]).map(resolveSessionFile);
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

function messageText(message) {
  return (message?.content?.[0]?.content || [])
    .filter((item) => item.type === 'text')
    .map((item) => item.text)
    .join('\n');
}

function directText(content) {
  return (content || []).filter((item) => item.type === 'text').map((item) => item.text).join('\n');
}

function parseArgs(value) {
  try { return typeof value === 'string' ? JSON.parse(value) : (value || {}); }
  catch { return { _raw: String(value) }; }
}

function parseVerbLines(text) {
  const match = text.match(/verbs \((\d+)\):\n([\s\S]*?)(?:\n\n|$)/);
  if (!match) return [];
  const verbs = [];
  for (const line of match[2].split('\n')) {
    const parsed = line.match(/^(\d+)\. \[(ok|FAIL)\] (\w+)\((.*)\) -> (.*) \(([\d.]+)ms\)\s*$/);
    if (!parsed) continue;
    let result = parsed[5];
    try { result = JSON.parse(result); } catch {}
    verbs.push({
      ledgerIndex: Number(parsed[1]),
      ok: parsed[2] === 'ok',
      verb: parsed[3],
      args: clip(parsed[4]),
      result,
      ms: Number(parsed[6]),
    });
  }
  return verbs;
}

const MUTATING_METHOD = /^(?:set|add|create|delete|destroy|remove|rename|save|cook|render|bake|lock|unlock|install|copy|move|enable|disable|press)(?:$|[A-Z_])/;
const READ_ONLY_PREFIX_COLLISIONS = new Set(['displayNode', 'renderNode']);
function rawMethods(code) {
  const methods = [];
  for (const match of code.matchAll(/\.([A-Za-z_]\w*)\s*\(/g)) methods.push(match[1]);
  return methods;
}

function analyzeTrace(file) {
  const loaded = loadSessionEvents(file);
  const { events } = loaded;
  const calls = new Map();
  for (const event of events) {
    if (event.type === 'tool/call') calls.set(event.data.callId, { ...event.data, eventSeq: event.seq, time: event.time });
  }

  const userMessages = [];
  const assistantMessages = [];
  const capabilitySnapshots = [];
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
    if (event.type === 'user/message' && event.data?.source?.kind === 'user') {
      const text = directText(event.data.content);
      if (text && !text.startsWith('<system-reminder>') && !text.startsWith('Current runtime context')) {
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
          mentionedCatalogVerbs: catalogNames.filter(
            (name) => new RegExp(`\\b${name}\\b`).test(system),
          ),
          // Some dsh runtimes expose the skill loader without embedding a skill catalog in
          // the request header. `[]` would falsely mean "no skills were available"; null means
          // "the header did not declare availability". Actual successful loads are reported
          // separately as skillActivations below.
          availableSkills: listedSkills.length ? listedSkills : null,
        });
      }
    }
    if (event.type !== 'tool/result') continue;
    const message = event.data?.message || {};
    const callId = message.source?.callId || message.content?.[0]?.toolCallId;
    const call = calls.get(callId);
    if (!call) continue;
    const args = parseArgs(call.arguments);
    const text = messageText(message);
    const code = typeof args.code === 'string' ? args.code : '';
    const verbs = parseVerbLines(text);
    const methods = rawMethods(code);
    const mutatingMethods = methods.filter(
      (name) => MUTATING_METHOD.test(name) && !READ_ONLY_PREFIX_COLLISIONS.has(name),
    );
    const isHoudini = String(call.name).startsWith('houdini_');
    const failed = Boolean(message.content?.some((item) => item.isError))
      || text.startsWith('Execution failed')
      || /\nExecution failed:/.test(text);
    const advisoryMatch = text.match(/hint:\n([\s\S]*?)$/);
    const rollbackMatch = text.match(/rollback:\n([\s\S]*?)(?:\n\n|$)/);
    let rollback = null;
    if (rollbackMatch) {
      try { rollback = JSON.parse(rollbackMatch[1]); }
      catch { rollback = { _raw: clip(rollbackMatch[1]) }; }
    }
    const step = {
      index: steps.length + 1,
      callSeq: call.eventSeq,
      resultSeq: event.seq,
      time: event.time,
      turn: event.data?.turn,
      step: event.data?.step,
      tool: call.name || '?',
      isHoudini,
      failed,
      args: compact && code ? { ...args, code: undefined } : args,
      codeChars: code.length,
      codeHash: code ? digest(code) : null,
      code: compact ? undefined : code,
      codePreview: code ? clip(code.replace(/\s+/g, ' '), 800) : null,
      resultPreview: clip(text),
      verbs,
      rawMethods: methods,
      mutatingRawMethods: mutatingMethods,
      advisory: advisoryMatch ? advisoryMatch[1].trim() : null,
      rollback,
    };
    steps.push(step);
    firstToolTime = Math.min(firstToolTime, event.time || Infinity);
    lastToolTime = Math.max(lastToolTime, event.time || 0);
    addCount(toolCounts, step.tool);
    for (const method of methods) addCount(rawMethodCounts, method);
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
  const rawHoudiniNoVerb = steps.filter((step) => step.isHoudini && !step.verbs.length).map((step) => ({
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
  const queryWithMutation = rawHoudiniNoVerb.filter(
    (step) => step.tool === 'houdini_query' && step.mutatingRawMethods.length,
  );
  const batchSetParmOpportunities = steps.filter(
    (step) => step.verbs.filter((verb) => verb.verb === 'set_parm').length >= 3,
  ).map((step) => ({
    index: step.index,
    time: step.time,
    count: step.verbs.filter((verb) => verb.verb === 'set_parm').length,
  }));
  const renderEvidence = steps.flatMap((step) => step.verbs
    .filter((verb) => ['render_view', 'render_frame', 'render_check'].includes(verb.verb))
    .map((verb) => ({ index: step.index, time: step.time, verb: verb.verb, ok: verb.ok, result: verb.result })));
  const visionEvidence = steps.filter((step) => step.tool.startsWith('vision_')).map((step) => ({
    index: step.index,
    time: step.time,
    tool: step.tool,
    args: step.args,
    resultPreview: step.resultPreview,
  }));
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
  const initialRequest = [...userMessages].reverse().find(
    (message) => message.time <= firstToolTime,
  ) || null;
  const skillActivations = steps.filter((step) => step.tool === 'skill').map((step) => ({
    index: step.index,
    time: step.time,
    name: typeof step.args?.name === 'string' ? step.args.name : null,
    succeeded: !step.failed,
  }));

  return {
    sessionId: sessionIdFromFile(file),
    file: loaded.file,
    frames: loaded.frames,
    frameErrors: loaded.frameErrors,
    eventCount: events.length,
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
    skillActivations,
    assistantMessages: compact ? undefined : assistantMessages,
    toolCalls: steps.length,
    toolCounts: sortCounts(toolCounts),
    verbCalls: Object.values(verbCounts).reduce((sum, count) => sum + count, 0),
    verbCounts: sortCounts(verbCounts),
    verbFailures: sortCounts(verbFailures),
    catalog: {
      total: catalogNames.length,
      used: usedVerbs.length,
      usedNames: usedVerbs.sort(),
      unusedNames: catalogNames.filter((name) => !verbCounts[name]),
      usedDomains: usedDomains.sort(),
    },
    failedCalls,
    failedVerbCalls,
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
    renderEvidence,
    visionEvidence,
    repeatedCode,
    timelineGaps: gaps,
    totalCodeChars: steps.reduce((sum, step) => sum + step.codeChars, 0),
    execCodeChars: steps.filter((step) => step.tool === 'houdini_exec').reduce((sum, step) => sum + step.codeChars, 0),
    latestTodo,
    terminal: {
      lastEventType: events.at(-1)?.type || null,
      lastToolTime: lastToolTime || null,
      lastAssistantTime: lastAssistantTime || null,
      assistantAfterLastTool: lastAssistantTime > lastToolTime,
      unfinishedTodoCount: latestTodo?.filter((item) => item.status !== 'completed').length ?? null,
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
  schemaVersion: 1,
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
