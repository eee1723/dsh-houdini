import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { registerHoudiniTools } from '../../lib/tools.js';

const definitions = new Map();
const ctx = {
  tools: {
    register(definition) {
      assert.equal(definitions.has(definition.name), false, definition.name);
      definitions.set(definition.name, definition);
      return () => definitions.delete(definition.name);
    },
  },
};

registerHoudiniTools(ctx, {});
assert.deepEqual([...definitions.keys()], [
  'houdini_exec',
  'houdini_query',
  'houdini_job_submit',
  'houdini_job_status',
  'houdini_job_cancel',
]);

const text = [{ type: 'text', text: 'fixture result' }];
const execValue = {
  ok: true,
  stdout: '',
  stderr: '',
  verbs: [{ verb: 'find_nodes' }, { verb: 'describe' }],
  media: [{ from: 'a.exr', to: 'a.exr' }],
};

const exec = definitions.get('houdini_exec');
const compactResult = exec.output.render({}, {
  ok:true,stdout:'[verb] repeated echo\nimportant user diagnostic',stderr:'',
  transaction:{status:'committed',nodes:[]},
  verbs:[{verb:'set_parm',ok:true,args:['/obj/a','tx',1],result:{value:1},ms:1}],
}).map(c=>c.text||'').join('\n');
assert(!compactResult.includes('repeated echo'));
assert(compactResult.includes('important user diagnostic'));
assert(compactResult.includes('transaction:') && compactResult.includes('verbs (1):'));
const execArgs = { code: 'set_parm(node, "tx", 1)', allow_raw: 'fixture gap' };
assert.deepEqual(exec.presentCall(execArgs), {
  card: 'generic',
  title: 'Execute Houdini Python',
  kind: 'edit',
  rawInput: execArgs,
});
const execMeta = exec.output.presentationMeta(execArgs, execValue);
assert.deepEqual(execMeta, { ok: true, verbCount: 2, mediaCount: 1 });
assert.deepEqual(exec.presentResult(execArgs, { content: text, isError: false, meta: execMeta }), {
  card: 'generic',
  title: 'Houdini execution succeeded',
  content: text,
});
assert.equal(exec.presentCall({}), undefined, 'invalid replay args must fall back safely');
const pendingChecks = {...execValue, checks: [{verb: 'set_parms', status: 'failed'}]};
const pendingMeta = exec.output.presentationMeta(execArgs, pendingChecks);
assert.match(exec.presentResult(execArgs, {content: text, isError: false, meta: pendingMeta}).title, /checks need attention/);
assert.match(exec.output.render(execArgs, pendingChecks)[0].text, /checks failed or contain warnings/);
const evidenceValue = {...pendingChecks, stdout:'long verbose node list', evidence:[
  {ledgerIndex:1,verb:'render_view',ok:false,output:'Z:/project/render/image.png',pixel_status:'failed',semantic_status:'unverified'},
]};
const evidenceText = exec.output.render(execArgs, evidenceValue)[0].text;
assert.ok(evidenceText.indexOf('operation-evidence:') < evidenceText.indexOf('stdout:'));
assert.match(evidenceText, /"pixel_status":"failed"/);
const baselineFailure = exec.output.render({}, {...execValue, stdout:'[]', evidence:[{
  ledgerIndex:1, verb:'test_controls', results:[], control_summary:{status:'fail', ok:false,
    restored:true, reason:'baseline outside declared absolute range', case_id:'reach',
    baseline:2, expectation:{range:[3,4]}, parameter_writes:0,
    case_counts:{pass:0,fail:0,unverified:0,not_run:1}},
}]}).map(c=>c.text||'').join('\n');
assert(baselineFailure.indexOf('control-test-summary') < baselineFailure.indexOf('stdout:'));
assert.match(baselineFailure, /not_run is not pass/);
assert.match(baselineFailure, /baseline outside declared absolute range/);
assert.match(baselineFailure, /"not_run":1/);
assert.match(baselineFailure, /"case_id":"reach"/);

const query = definitions.get('houdini_query');
assert.deepEqual(query.presentCall({ code: '__result__ = find_nodes(root="/obj")' }), {
  card: 'generic',
  title: 'Inspect Houdini scene',
  kind: 'read',
  rawInput: '__result__ = find_nodes(root="/obj")',
});
assert.equal(
  query.presentResult({ code: '__result__ = []' }, { content: text, isError: true }).title,
  'Houdini inspection failed',
);

const submit = definitions.get('houdini_job_submit');
const submitMeta = submit.output.presentationMeta({}, { jobId: 'job-7' });
assert.deepEqual(submitMeta, { jobId: 'job-7' });
assert.equal(
  submit.presentResult({ code: 'render_frame(rop)' }, { content: text, isError: false, meta: submitMeta }).title,
  'Started Houdini job job-7',
);

const status = definitions.get('houdini_job_status');
const jobValue = {
  jobId: 'job-7',
  status: 'running',
  ok: false,
  stdout: '',
  stderr: '',
  verbs: [],
};
const statusMeta = status.output.presentationMeta({ jobId: 'job-7', wait: 30 }, jobValue);
assert.deepEqual(statusMeta, {
  ok: false,
  jobId: 'job-7',
  status: 'running',
  verbCount: 0,
  mediaCount: 0,
});
assert.deepEqual(status.presentCall({ jobId: 'job-7', wait: 30 }), {
  card: 'generic',
  title: 'Inspect Houdini job job-7',
  kind: 'read',
  rawInput: { jobId: 'job-7', wait: 30 },
});
assert.equal(
  status.presentResult({ jobId: 'job-7' }, { content: text, isError: false, meta: statusMeta }).title,
  'Houdini job job-7: running',
);

const cancel = definitions.get('houdini_job_cancel');
assert.deepEqual(cancel.presentCall({ jobId: 'job-7' }), {
  card: 'generic',
  title: 'Cancel Houdini job job-7',
  kind: 'execute',
  rawInput: 'job-7',
});
assert.equal(
  cancel.presentResult({ jobId: 'job-7' }, { content: text, isError: true }).title,
  'Houdini job cancellation failed',
);

// Presentation is a replay-time pure projection: repeated calls are identical
// and do not mutate the durable args/result payloads.
const frozenArgs = Object.freeze({ jobId: 'job-7', wait: 1 });
assert.deepEqual(status.presentCall(frozenArgs), status.presentCall(frozenArgs));

// Relay names are content-addressed so same-basename images from different
// $HIP directories or frames cannot overwrite each other in the workspace.
const relayDefinitions = new Map();
const relayRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-media-relay-'));
registerHoudiniTools({ tools: { register(definition) { relayDefinitions.set(definition.name, definition); } } }, {
  async exec() {
    return {
      ok: true,
      stdout: '',
      stderr: '',
      images: ['C:/first/review.png', 'D:/second/review.png'],
    };
  },
  async fetchMedia(from) {
    return Buffer.from(from.includes('first') ? 'first-image' : 'second-image');
  },
  async hipDir() { return relayRoot; },
});
const relayed = await relayDefinitions.get('houdini_exec').execute(
  { code: '__result__ = 1' },
  { agent: { id: 'session-1', session: { header: { cwd: relayRoot } } }, callId: 'call-1' },
);
assert.equal(relayed.media.length, 2);
assert.notEqual(relayed.media[0].to, relayed.media[1].to);
for (const item of relayed.media) {
  assert.match(path.basename(item.to), /^[0-9a-f]{12}-review\.png$/);
  assert.equal(fs.statSync(item.to).size > 0, true);
}
fs.rmSync(relayRoot, { recursive: true });

console.log('houdini tool presentation tests passed');
