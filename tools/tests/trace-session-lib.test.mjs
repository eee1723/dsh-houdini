import assert from 'node:assert/strict';
import { toolResultCallId, uniqueToolResultEvents } from '../trace-session-lib.mjs';

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

console.log('trace-session-lib dedupe: ok');
