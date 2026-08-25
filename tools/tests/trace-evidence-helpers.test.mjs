import assert from 'node:assert/strict';
import {
  collectValidationCoverage,
  execResultFromPreview,
  classifyVisionEvidence,
  collectVerbAdoption,
  extractAvailableSkills,
  findBatchSetParmOpportunities,
  findSuppressedCookFailures,
  frameFromPath,
  parseLedgerArgs,
  parseVerbLedgerLine,
  renderOutputsFromPreview,
} from '../../skills/houdini-trace-analysis/scripts/evidence-helpers.mjs';

assert.deepEqual(parseLedgerArgs('["/obj/a","tx",1]'), {
  positional: ['/obj/a', 'tx', 1], kwargs: {},
});
assert.deepEqual(parseLedgerArgs('["/obj/a"], {"frame": 12, "framing_frame": 20}'), {
  positional: ['/obj/a'], kwargs: { frame: 12, framing_frame: 20 },
});
assert.deepEqual(parseVerbLedgerLine(
  '1. [ok] verb_help(["set_keyframes"]) -> {"name":"set_keyframes","signature":"(node, channels: \'dict\', replace: \'bool\' = True) -> \'dict\'","doc":"x"} (0ms)',
), {
  ledgerIndex: 1,
  ok: true,
  verb: 'verb_help',
  args: '["set_keyframes"]',
  result: '{"name":"set_keyframes","signature":"(node, channels: \'dict\', replace: \'bool\' = True) -> \'dict\'","doc":"x"}',
  ms: 0,
});
assert.deepEqual(parseVerbLedgerLine(
  '2. [ok] set_parm(["/obj/a","label",") -> still arg"]) -> {"ok":true} (1.5ms)',
), {
  ledgerIndex: 2,
  ok: true,
  verb: 'set_parm',
  args: '["/obj/a","label",") -> still arg"]',
  result: '{"ok":true}',
  ms: 1.5,
});
assert.equal(parseVerbLedgerLine('not a ledger line'), null);
assert.equal(frameFromPath('E:/tmp/dsh_view_123_f25p5.png'), 25.5);
assert.equal(frameFromPath('E:/tmp/no_frame.png'), null);
assert.deepEqual(extractAvailableSkills(`
<available_skills>
- \`houdini-rig-animation-workflow\`: Rig work.
- \`houdini-trace-analysis\`: Trace work.
</available_skills>`), [
  'houdini-rig-animation-workflow', 'houdini-trace-analysis',
]);

const scattered = [{
  index: 7,
  time: 100,
  verbs: [
    ['a', 'x'], ['a', 'y'], ['b', 'x'], ['b', 'y'],
    ['c', 'x'], ['c', 'y'], ['d', 'x'], ['d', 'y'],
  ].map(([node, parm]) => ({ verb: 'set_parm', args: JSON.stringify([`/obj/${node}`, parm, 1]) })),
}];
assert.deepEqual(findBatchSetParmOpportunities(scattered), []);

const sameNode = [{
  index: 8,
  time: 200,
  verbs: [
    { verb: 'set_parms', args: JSON.stringify(['/obj/a', { tx: 1 }]) },
    ...['tx', 'ty', 'tz', 'rx'].map((parm) => ({
      verb: 'set_parm', args: JSON.stringify(['/obj/a', parm, 1]),
    })),
  ],
}];
assert.deepEqual(findBatchSetParmOpportunities(sameNode), [{
  index: 8,
  time: 200,
  node: '/obj/a',
  count: 3,
  parms: ['rx', 'ty', 'tz'],
}]);

const repeatedSameParm = [{
  index: 9,
  time: 300,
  verbs: [1, 2, 3].map((value) => ({
    verb: 'set_parm', args: JSON.stringify(['/obj/a', 'tx', value]),
  })),
}];
assert.deepEqual(findBatchSetParmOpportunities(repeatedSameParm), []);

assert.deepEqual(findSuppressedCookFailures([
  {
    index: 10, time: 400, tool: 'houdini_exec', isHoudini: true, failed: false,
    resultPreview: 'Executed successfully.\n\nstdout:\nBASE cook FAILED: Error while cooking.',
  },
  {
    index: 11, time: 500, tool: 'houdini_exec', isHoudini: true, failed: true,
    resultPreview: 'Execution failed: Error while cooking.',
  },
  {
    index: 12, time: 600, tool: 'houdini_exec', isHoudini: true, failed: false,
    resultPreview: 'Executed successfully.\n\nstdout:\ncook OK',
  },
]), [{
  index: 10,
  time: 400,
  tool: 'houdini_exec',
  resultPreview: 'Executed successfully.\n\nstdout:\nBASE cook FAILED: Error while cooking.',
}]);

const coverage = collectValidationCoverage([
  {
    index: 1, time: 1, tool: 'houdini_query', args: {}, verbs: [{
      verb: 'geo_frame_diff', ok: true, args: '["/obj/a/OUT",25,31]', result: {},
    }],
  },
  {
    index: 2, time: 2, tool: 'houdini_exec', args: {}, verbs: [{
      verb: 'render_view', ok: true,
      args: '["/obj/a/OUT"], {"frame": 31, "framing_frame": 31}',
      result: { output: 'E:/tmp/dsh_view_1_f31p0.png' },
    }],
  },
  {
    index: 3, time: 3, tool: 'houdini_exec', args: {}, verbs: [{
      verb: 'render_check', ok: true,
      args: '["E:/tmp/dsh_view_1_f31p0.png"], {"ref":"E:/tmp/dsh_view_0_f25p0.png"}',
      result: {},
    }],
  },
  {
    index: 4, time: 4, tool: 'vision_glance', verbs: [],
    args: { images: ['E:/tmp/dsh_view_0_f25p0.png', 'E:/tmp/dsh_view_1_f31p0.png'] },
  },
  {
    index: 5, time: 5, tool: 'read_image', failed: true, verbs: [],
    args: { path: 'E:/tmp/dsh_view_2_f40p0.png' },
  },
]);
assert.deepEqual(coverage.frames.geometry, [25, 31]);
assert.deepEqual(coverage.frames.render, [31]);
assert.deepEqual(coverage.frames.framing, [31]);
assert.deepEqual(coverage.frames.comparison, [25, 31]);
assert.deepEqual(coverage.frames.vision, [25, 31, 40]);
assert.deepEqual(coverage.frames.visionInspection, [25, 31, 40]);
assert.deepEqual(coverage.frames.all, [25, 31, 40]);
assert.equal(coverage.vision[1].ok, false);

const recovered = execResultFromPreview([
  'Executed successfully.',
  '',
  '__result__:',
  '{"output":"E:/tmp/dsh_view_9_f52p0.png","frame":52,"framing":{"frame":1}}',
  '',
  'verbs (1):',
  '1. [ok] render_view(["/obj/a/OUT"], {"frame":52}) -> {"output":"E:/tmp/dsh_view_9_f52p0.png"鈥 (10ms)',
].join('\n'));
assert.equal(recovered.output, 'E:/tmp/dsh_view_9_f52p0.png');
assert.deepEqual(renderOutputsFromPreview(
  'stdout: {"output":"E:/tmp/a_f1p0.png"} then {"output":"E:/tmp/a_f21p0.png"} and {"output":"E:/tmp/a_f1p0.png"}',
), ['E:/tmp/a_f1p0.png', 'E:/tmp/a_f21p0.png']);

const recoveredCoverage = collectValidationCoverage([{
  index: 6,
  time: 6,
  tool: 'houdini_exec',
  resultPreview: 'Executed successfully.\n\n__result__:\n{"output":"E:/tmp/dsh_view_9_f52p0.png","frame":52,"framing":{"frame":1}}\n\nverbs (1):',
  verbs: [{
    verb: 'render_view', ok: true,
    args: '["/obj/a/OUT"], {"frame":52,"framing_frame":1}',
    result: '{"output":"E:/tmp/dsh_view_9_f52p0.png"鈥',
  }],
}, {
  index: 7,
  time: 7,
  tool: 'houdini_exec',
  resultPreview: 'Executed successfully.\n\n__result__:\n{"path":"E:/tmp/dsh_view_9_f52p0.png","size":[1280,720],"content_bbox":[186,0,1119,717]}\n\nverbs (1):',
  verbs: [{ verb: 'render_check', ok: true, args: '["E:/tmp/dsh_view_9_f52p0.png"]', result: '{}' }],
}]);
assert.equal(recoveredCoverage.renders[0].output, 'E:/tmp/dsh_view_9_f52p0.png');
assert.equal(recoveredCoverage.renders[0].frame, 52);
assert.equal(recoveredCoverage.renders[0].framing_frame, 1);
assert.equal(recoveredCoverage.comparisons[0].touches_edge, true);

const bootstrapFailure = classifyVisionEvidence({
  tool: 'vision_bootstrap', failed: false, args: { paths: ['E:/tmp/a_f1p0.png'] },
  resultPreview: '{"ok":false,"code":"STRUCTURED_BOOTSTRAP_DISABLED"}',
});
assert.equal(bootstrapFailure.role, 'setup');
assert.equal(bootstrapFailure.ok, false);
assert.equal(bootstrapFailure.reason, 'STRUCTURED_BOOTSTRAP_DISABLED');

const describeRefusal = classifyVisionEvidence({
  tool: 'vision_describe', failed: false, args: { paths: ['E:/tmp/a_f13p0.png'] },
  resultPreview: '由于我无法查看图像（模型仅接受文本输入，且图片已被省略），无法分析。',
});
assert.equal(describeRefusal.role, 'inspection');
assert.equal(describeRefusal.semanticOk, false);
assert.equal(describeRefusal.reason, 'textual_image_access_refusal');

const presentation = classifyVisionEvidence({
  tool: 'vision_present', failed: false, args: { image: 'E:/tmp/a_f13p0.png' }, resultPreview: '{}',
});
assert.equal(presentation.role, 'presentation');
assert.equal(presentation.semanticOk, null);

assert.deepEqual(collectVerbAdoption([
  { tool: 'houdini_exec', isHoudini: true, failed: false, verbs: [{ verb: 'tab_create' }], mutatingRawMethods: [] },
  { tool: 'houdini_query', isHoudini: true, failed: false, verbs: [], mutatingRawMethods: [] },
  { tool: 'houdini_exec', isHoudini: true, failed: true, verbs: [], mutatingRawMethods: ['cook'], resultPreview: 'raw-hou gate: blocked BEFORE execution' },
]), {
  houdiniCalls: 3,
  callsWithVerbs: 1,
  callCoveragePct: 33.3,
  verbCalls: 1,
  verbDensity: 0.33,
  rawReadOnlyCalls: 1,
  execCalls: 2,
  successfulExecCalls: 1,
  successfulExecWithVerbs: 1,
  successfulExecVerbCoveragePct: 100,
  blockedVerblessRawMutationCalls: 1,
  successfulVerblessRawMutationCalls: 0,
});

console.log('trace evidence helper tests passed');
