import assert from 'node:assert/strict';
import {
  normalizeTraceSteps,
  parseToolArguments,
  toolResultFailed,
  toolResultText,
  unresolvedExecutionRequests,
} from '../normalized-trace-steps.mjs';
import {isStructuredHoudiniCall,collectVerbAdoption,nativeImageEvidence} from '../../skills/houdini-trace-analysis/scripts/evidence-helpers.mjs';

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
const currentResult = {role:'tool',source:{kind:'tool',callId:'v4'},
  content:[{type:'text',text:ledger}]};
assert.equal(toolResultText(currentResult), ledger, 'DSH 0.2 role=tool text is preserved');
assert.equal(toolResultText({content:[{type:'tool-result',content:[{type:'text',text:ledger}]}]}), ledger);
const current = normalizeTraceSteps([call(11,'v4','houdini_inspect',{code:'scene_info()'}),
  {seq:12,time:1012,type:'tool/result',data:{message:currentResult}}]).steps[0];
assert.equal(current.resultText.length,ledger.length);
assert.equal(current.verbs[0].verb,'set_parm');
assert.equal(toolResultFailed(original.data.message, '\nExecution failed: later'), true);
assert.deepEqual(parseToolArguments({ x: 1 }), { x: 1 });
assert.deepEqual(parseToolArguments('null'), { _raw: 'null' });

const childId='parent:ptc:1', nestedValue={ok:true,result:{observed:1},verbs:[{verb:'scene_info',ok:true,args:[],kwargs:{},result:{},ms:1}]};
const nestedEvents=[
  {seq:20,time:20,type:'tool/ptc-dispatch-start',data:{subCallId:childId,parentCallId:'parent',name:'houdini_inspect',arguments:{code:'__result__=scene_info()'}}},
  {seq:21,time:21,type:'tool/ptc-dispatch',data:{subCallId:childId,parentCallId:'parent',name:'houdini_inspect',content:[{type:'text',text:JSON.stringify({kind:'dsh-houdini/execution-v1',callId:childId,tool:'houdini_inspect',value:nestedValue})}]}},
];
const nested=normalizeTraceSteps(nestedEvents).steps[0];
assert.deepEqual(nested.canonical,nestedValue);
assert.equal(nested.parentCallId,'parent');
assert.equal(nested.canonicalStatus,'retained_in_dispatch');
assert.equal(nested.verbs[0].verb,'scene_info');
const unrelated=structuredClone(nestedEvents);
unrelated[1].data.content[0].text=unrelated[1].data.content[0].text.replace(childId,'wrong-id');
assert.equal(normalizeTraceSteps(unrelated).steps[0].canonical,null, 'other sub-call records cannot become execution facts');

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

const captureValue={ok:true,result:{node:'/obj/demo/CTRL',path:'C:/capture.png',scene_writes:0,semantic_status:'unverified'},
  images:['C:/capture.png'],imageAttachments:[{from:'C:/capture.png',attachment:{attachmentId:'ui-image'}}],
  evidence:[{operation:'ui_capture',scene_writes:0,semantic_status:'unverified'}],
  outcome:{batch:'completed',operations:{total:1,failed:0},checks:{failed:0,warning:0,unverified:0}},
  transaction:{status:'no_scene_change'},execution:{runtime_id:'ui-runtime',sequence:1,observed_at:30},
  requestReceipt:{request_ref:'ui-ref',runtime_id:'ui-runtime',owner_call:'capture',status:'done'}};
const captureNative=result(31,'capture','Native pane captured; visual interpretation unverified.');
captureNative.data.meta={canonical:captureValue};
const captureRecovery=result(35,'recover-ui','Original native capture recovered.');
captureRecovery.data.meta={canonical:{...captureValue,requestReceipt:{...captureValue.requestReceipt,retrieved:true}}};
const captureNestedId='program:capture';
const captures=normalizeTraceSteps([
  call(30,'capture','houdini_ui_screenshot',{node:'/obj/demo/CTRL',view:'parameters'}),captureNative,
  {seq:32,time:32,type:'tool/ptc-dispatch-start',data:{subCallId:captureNestedId,parentCallId:'program',name:'houdini_ui_screenshot',arguments:{node:'/obj/demo',view:'network'}}},
  {seq:33,time:33,type:'tool/ptc-dispatch',data:{subCallId:captureNestedId,parentCallId:'program',name:'houdini_ui_screenshot',content:[{type:'text',text:JSON.stringify({
    kind:'dsh-houdini/execution-v1',callId:captureNestedId,tool:'houdini_ui_screenshot',value:{...captureValue,execution:{...captureValue.execution,sequence:2}}})}]}},
]);
assert.equal(captures.steps.length,2);
assert.equal(captures.uniqueExecutions.length,2);
assert.deepEqual(captures.uniqueExecutions.map(row=>row.verbCalls),[0,0],'capture has no fabricated Python verb ledger');
for(const step of captures.steps){
  assert.equal(step.code,'');assert.deepEqual(step.verbs,[]);assert.equal(step.transaction.status,'no_scene_change');
  assert.equal(isStructuredHoudiniCall(step),true);
  assert.deepEqual(step.canonical.images,['C:/capture.png']);
  assert.equal(step.canonical.result.semantic_status,'unverified');
  assert.equal(step.canonical.evidence[0].operation,'ui_capture');
}
const captureAdoption=collectVerbAdoption(captures.steps);
assert.equal(captureAdoption.structuredCalls,2);assert.equal(captureAdoption.pythonCalls,0);
assert.equal(captureAdoption.rawUnknownEffectCalls,0);assert.equal(captureAdoption.rawFailedCalls,0);
assert.equal(captureAdoption.execCalls,0);
assert.equal(nativeImageEvidence(captures.steps).filter(row=>row.delivered).length,2);
assert(nativeImageEvidence(captures.steps).every(row=>row.semanticStatus==='unverified'));
const recoveredTrace=normalizeTraceSteps([
  call(30,'capture','houdini_ui_screenshot',{node:'/obj/demo/CTRL'}),captureNative,
  call(34,'recover-ui','houdini_request',{request_ref:'ui-ref'}),captureRecovery,
]);
assert.equal(recoveredTrace.uniqueExecutions.length,1,'request recovery does not invent a second capture');
assert.equal(recoveredTrace.steps[1].executionReplay,true);
assert.equal(recoveredTrace.steps[1].recoveredExecution,true);
assert.deepEqual(recoveredTrace.steps[1].canonical.images,captureValue.images);
assert.deepEqual(recoveredTrace.steps[1].verbs,[]);
const unknownCapture={index:1,tool:'houdini_ui_screenshot',canonical:{requestReceipt:{request_ref:'ui-q',runtime_id:'ui-runtime',status:'unknown_transport'}}};
const recoveredCapture={index:2,tool:'houdini_request',canonical:{...captureValue,requestReceipt:{request_ref:'ui-q',runtime_id:'ui-runtime',status:'done',retrieved:true}}};
assert.equal(unresolvedExecutionRequests([unknownCapture]).length,1);
assert.equal(unresolvedExecutionRequests([unknownCapture,recoveredCapture]).length,0);
console.log('UI capture trace: native/nested canonical images, structured non-Python classification and recovery passed');
