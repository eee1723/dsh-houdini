import assert from 'node:assert/strict';
import {
  normalizeTraceSteps,
  parseToolArguments,
  toolResultFailed,
  toolResultText,
  unresolvedExecutionRequests,
} from '../normalized-trace-steps.mjs';

const call = (seq, callId, name, args) => ({
  seq,
  time: 1_000 + seq,
  type: 'tool/call',
  data: { callId, name, arguments: args },
});
const result = (seq, callId, text, isError = false) => ({
  seq,
  time: 1_000 + seq,
  type: 'tool/result',
  data: {
    turn: 2,
    step: 3,
    message: {
      source: { callId },
      content: [{ type: 'tool_result', isError, content: [{ type: 'text', text }] }],
    },
  },
});

const ledger = [
  'done',
  '',
  'verbs (1):',
  '1. [ok] set_parm(["/obj/a","tx",1]) -> {"ok":true} (1.5ms)',
  '',
  'raw-usage:',
  '{"coveredMutations":[{"name":"setInput","count":2}],"suspectedMutations":[]}',
  '',
  'rollback:',
  '{"attempted":true,"succeeded":true}',
  '',
  'hint:',
  'prefer the verb',
].join('\n');

const original = result(2, 'call-a', ledger);
const replay = result(7, 'call-a', ledger);
const events = [
  call(1, 'call-a', 'houdini_exec', '{"code":"hou.node(\\"/obj/a\\").setInput(0, None)"}'),
  original,
  replay,
  result(8, 'missing-call', 'orphan'),
  call(9, 'call-b', 'houdini_query', '{broken'),
  result(10, 'call-b', 'Error: query failed'),
];

const normalized = normalizeTraceSteps(events);
assert.equal(normalized.steps.length, 2);
assert.equal(normalized.replayedResults.length, 1);
assert.deepEqual(normalized.unmatchedResults, [{ callId: 'missing-call', resultSeq: 8, time: 1_008 }]);

const first = normalized.steps[0];
assert.equal(first.callSeq, 1);
assert.equal(first.resultSeq, 2);
assert.equal(first.tool, 'houdini_exec');
assert.equal(first.failed, false);
assert.deepEqual(first.verbs, [{
  ledgerIndex: 1,
  ok: true,
  verb: 'set_parm',
  args: '["/obj/a","tx",1]',
  result: { ok: true },
  resultText: '{"ok":true}',
  ms: 1.5,
}]);
assert.deepEqual(first.mutatingRawMethods, ['setInput', 'setInput']);
assert.deepEqual(first.rollback, { attempted: true, succeeded: true });
assert.equal(first.advisory, 'prefer the verb');

assert.deepEqual(normalized.steps[1].args, { _raw: '{broken' });
assert.equal(normalized.steps[1].failed, true);
assert.equal(toolResultText(original.data.message), ledger);
assert.equal(toolResultFailed(original.data.message, '\nExecution failed: later'), true);
assert.deepEqual(parseToolArguments({ x: 1 }), { x: 1 });
assert.deepEqual(parseToolArguments('null'), { _raw: 'null' });

console.log('normalized trace step tests passed');

const evidenceText = 'operation-evidence:\n' + JSON.stringify([
  {ledgerIndex:1,verb:'render_view',output:'Z:/project/render/a.png',frame:7,ok:false,pixel_status:'failed'},
]) + '\n\nverbs (1):\n1. [ok] render_view(["/obj/a/OUT"]) -> {"service":"a huge truncated… (1ms)';
const structured = normalizeTraceSteps([call(1,'e','houdini_exec',{code:'render_view(out)'}),result(2,'e',evidenceText)]).steps[0];
assert.equal(structured.verbs[0].ok, true, 'transport ledger success stays distinct from pixel failure');
assert.equal(structured.verbs[0].result.ok, false);
assert.equal(structured.verbs[0].result.frame, 7);
assert.equal(structured.verbs[0].result.output, 'Z:/project/render/a.png');
const rolled = normalizeTraceSteps([call(10,'r','houdini_exec',{}),result(15,'r','transaction:\n{"status":"rolled_back","nodes":[]}\n\n'+evidenceText,true)]).steps[0];
assert.equal(rolled.durationMs,5);
assert.equal(rolled.transaction.status,'rolled_back');

const receiptStep = (index, status, runtime='one', ref='request') => ({index,
  tool:'houdini_exec', canonical:{requestReceipt:{runtime_id:runtime,request_ref:ref,status}}});
assert.equal(unresolvedExecutionRequests([receiptStep(1,'unknown_transport')]).length,1);
assert.equal(unresolvedExecutionRequests([receiptStep(1,'unknown_transport'),receiptStep(2,'done')]).length,0);
assert.equal(unresolvedExecutionRequests([receiptStep(1,'unknown_transport'),receiptStep(2,'done','two')]).length,1);
assert.equal(unresolvedExecutionRequests([receiptStep(1,'unknown_transport'),receiptStep(2,'done','one','other')]).length,1);
assert.equal(unresolvedExecutionRequests([receiptStep(1,'done'),receiptStep(2,'unknown_transport')]).length,0);
assert.equal(unresolvedExecutionRequests([{index:1,resultText:'request-receipt:\n'+JSON.stringify({runtime_id:'one',request_ref:'q',status:'unknown_transport'})}]).length,1);
