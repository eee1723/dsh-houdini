import assert from 'node:assert/strict';
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

console.log('houdini tool presentation tests passed');
