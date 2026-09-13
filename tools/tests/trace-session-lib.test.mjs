import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { newestSessionFile, resolveSessionFile, toolResultCallId, uniqueToolResultEvents, collectRequestTelemetry } from '../trace-session-lib.mjs';

const result = (seq, callId, turn = 1, step = 1) => ({
  seq,
  time: 1_000 + seq,
  type: 'tool/result',
  data: {
    turn,
    step,
    message: {
      source: { callId },
      content: [{ type: 'tool_result', content: [] }],
    },
  },
});

const alternateSchema = {
  seq: 9,
  time: 1_009,
  type: 'tool/result',
  data: { message: { content: [{ toolCallId: 'call-alt', content: [] }] } },
};

const original = result(2, 'call-a');
const replay = result(7, 'call-a');
const other = result(8, 'call-b', 2, 4);
const input = [
  { seq: 1, type: 'tool/call', data: { callId: 'call-a' } },
  original,
  { seq: 6, type: 'compaction/prune', data: {} },
  replay,
  other,
  alternateSchema,
];

const usageEvent = (seq, turn, step, usage) => ({seq, type:'assistant/chunk', data:{turn,step,chunk:{type:'usage',usage}}});
const measured = usageEvent(10,1,1,{inputTokens:10,outputTokens:2,cacheReadTokens:80,totalTokens:92});
const telemetry = collectRequestTelemetry([measured, {...measured,seq:11},
  usageEvent(12,1,2,{inputTokens:5,outputTokens:1,totalTokens:6}),
  usageEvent(13,1,2,{inputTokens:5,outputTokens:3,totalTokens:8}),
  usageEvent(14,2,1,{totalTokens:100}),
  usageEvent(15,2,2,{inputTokens:20,outputTokens:2,cacheReadTokens:10,totalTokens:22}),
  {seq:16,type:'turn/end',data:{turn:1,reason:{kind:'error',error:{code:'INVALID_REQUEST',message:'model unavailable'}}}},
  {seq:17,type:'turn/end',data:{turn:2,reason:{kind:'completed'}}},
  {seq:18,type:'compaction/prune'},
]);
assert.equal(telemetry.requestCount,4);
assert.equal(telemetry.duplicateUsageEvents,1);
assert.equal(telemetry.updatedUsageEvents,1);
assert.equal(telemetry.totals.inputTokens,35);
assert.equal(telemetry.totals.outputTokens,7);
assert.equal(telemetry.requests[0].inputWithCache,90);
assert.equal(telemetry.requests[2].inputTokens,null);
assert.equal(telemetry.requests[2].inputWithCache,null);
assert.equal(telemetry.last.inputWithCache,null,'do not double count provider-inclusive cache fields');
assert.deepEqual(telemetry.arithmeticMismatchSeqs,[15]);
assert.equal(telemetry.upstreamTurnErrors.length,1,'later completed turn does not erase startup error');
assert.equal(telemetry.compactionEvents.length,1);
assert.equal(collectRequestTelemetry([]).totals.inputTokens,null);

const settled = (seq, turn, step, usage, interrupted) => ({seq, type:'assistant/message',
  data:{turn,step,message:{role:'assistant',content:[]},stream:[],usage,interrupted}});
const v3 = collectRequestTelemetry([
  settled(20,1,1,measured.data.chunk.usage),
  settled(21,1,2,undefined), // Missing is unknown, not a zero-token request.
  settled(22,1,3,{inputTokens:5,outputTokens:1,totalTokens:6},true),
]);
assert.equal(v3.requestCount,2);
assert.equal(v3.totals.totalTokens,98);
assert.equal(v3.requests[0].inputWithCache,90);
const mixed = collectRequestTelemetry([measured,settled(23,1,1,measured.data.chunk.usage)]);
assert.equal(mixed.requestCount,1);
assert.equal(mixed.totals.totalTokens,92);
assert.equal(mixed.duplicateUsageEvents,1);
assert.equal(collectRequestTelemetry([settled(24,1,1,{outputTokens:-1})]).last.outputTokens,null);

assert.equal(toolResultCallId(original), 'call-a');
assert.equal(toolResultCallId(alternateSchema), 'call-alt');
assert.equal(toolResultCallId(input[0]), null);

const deduped = uniqueToolResultEvents(input);
assert.deepEqual(deduped.uniqueResults, [original, other, alternateSchema]);
assert.deepEqual(deduped.replayedResults, [{
  callId: 'call-a',
  originalSeq: 2,
  replaySeq: 7,
  originalTime: 1_002,
  replayTime: 1_007,
  turn: 1,
  step: 1,
}]);

const sessionRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-trace-test-'));
const older = path.join(sessionRoot, 'workspace', 'session-old', 'session.jsonl.zstd');
const newer = path.join(sessionRoot, 'workspace', 'session-new', 'session.jsonl.zstd');
fs.mkdirSync(path.dirname(older), { recursive: true });
fs.mkdirSync(path.dirname(newer), { recursive: true });
fs.writeFileSync(older, 'old');
fs.writeFileSync(newer, 'new');
fs.utimesSync(older, new Date(1_000), new Date(1_000));
fs.utimesSync(newer, new Date(2_000), new Date(2_000));
assert.equal(newestSessionFile(sessionRoot), newer);
const v3File = path.join(path.dirname(newer), 'session.v3.jsonl.zstd');
fs.writeFileSync(v3File, 'v3');
fs.utimesSync(v3File, new Date(3_000), new Date(3_000));
assert.equal(newestSessionFile(sessionRoot), v3File);
assert.equal(resolveSessionFile(path.dirname(newer)), v3File);
assert.equal(resolveSessionFile(path.dirname(older)), older);
assert.equal(resolveSessionFile(newer), newer, 'explicit legacy file remains selectable');
assert.ok(path.resolve(sessionRoot).startsWith(path.resolve(os.tmpdir())));
fs.rmSync(sessionRoot, { recursive: true });

console.log('trace-session-lib dedupe: ok');
