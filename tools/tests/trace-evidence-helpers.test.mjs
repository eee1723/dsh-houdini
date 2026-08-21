import assert from 'node:assert/strict';
import {
  collectValidationCoverage,
  extractAvailableSkills,
  findBatchSetParmOpportunities,
  frameFromPath,
  parseLedgerArgs,
  parseVerbLedgerLine,
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
]);
assert.deepEqual(coverage.frames.geometry, [25, 31]);
assert.deepEqual(coverage.frames.render, [31]);
assert.deepEqual(coverage.frames.framing, [31]);
assert.deepEqual(coverage.frames.comparison, [25, 31]);
assert.deepEqual(coverage.frames.vision, [25, 31]);
assert.deepEqual(coverage.frames.all, [25, 31]);

console.log('trace evidence helper tests passed');
