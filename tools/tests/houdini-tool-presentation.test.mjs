import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { HoudiniBridge } from '../../lib/bridge.js';
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
assert.deepEqual([...definitions.keys()].sort(), ['houdini_exec','houdini_inspect','houdini_ui_list','houdini_ui_screenshot','houdini_request','houdini_resource','houdini_capabilities','houdini_job_submit','houdini_job_status','houdini_job_cancel'].sort());

const text = [{ type: 'text', text: 'fixture result' }];
const execValue = {
  ok: true,
  stdout: '',
  stderr: '',
  verbs: [{ verb: 'find_nodes' }, { verb: 'describe' }],
  imageAttachments: [{ from: 'a.png', attachment: {attachmentId:'fixture'} }],
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
const candidateText = exec.output.render({}, {
  ok:true, stdout:'', stderr:'', artifactCandidates:[
    {path:'C:/project/final.hip',kind:'scene',role:'delivery-candidate',source:'scene_save',bytes:42},
    {path:'C:/project/check.png',kind:'image',role:'visual-check',source:'render_view',bytes:24},
  ],
})[0].text;
assert.match(candidateText, /artifact-candidates \(not delivered; verify requested final files, then call present\)/);
assert.match(candidateText, /"role":"visual-check"/);
const execArgs = { code: 'set_parm(node, "tx", 1)', allow_raw: 'fixture gap' };
assert.deepEqual(exec.presentCall(execArgs), {
  card: 'generic',
  title: '执行操作',
  kind: 'edit',
  rawInput: execArgs,
});
const execMeta = exec.output.presentationMeta(execArgs, execValue);
assert.deepEqual(execMeta, { ok: true, verbCount: 2, imageCount: 1, canonical: execValue });
assert.deepEqual(exec.presentResult(execArgs, { content: text, isError: false, meta: execMeta }), {
  card: 'generic',
  title: '执行操作 · 成功',
  content: text,
});
const pendingChecks = {...execValue, checks: [{verb: 'set_parms', status: 'failed'}]};
const pendingMeta = exec.output.presentationMeta(execArgs, pendingChecks);
assert.match(exec.presentResult(execArgs, {content: text, isError: false, meta: pendingMeta}).title, /检查需要关注/);
assert.match(exec.output.render(execArgs, pendingChecks)[0].text, /checks failed or contain warnings/);
const caughtRead = {...execValue, result:{fallback:'available'},
  outcome:{batch:'completed',operations:{total:2,failed:1},checks:{failed:0,warning:0,unverified:0}},
  verbs:[{verb:'describe',ok:false,error:'missing query node'}, {verb:'find_nodes',ok:true,result:[]}]};
const caughtMeta = exec.output.presentationMeta(execArgs,caughtRead);
assert.match(exec.presentResult(execArgs,{content:text,isError:false,meta:caughtMeta}).title,/批次完成，部分操作失败/);
const caughtText=exec.output.render(execArgs,caughtRead)[0].text;
assert.match(caughtText,/Batch completed; one or more operations raised errors/);
assert.match(caughtText,/missing query node/);
assert(caughtText.indexOf('operation-errors:') < caughtText.indexOf('__result__:'));
assert.match(caughtText,/"fallback":"available"/);
assert.doesNotMatch(caughtText,/Executed successfully/);
assert.match(statusTextForReceipt(),/unknown_transport/);
function statusTextForReceipt() {
  return exec.output.render({}, {ok:false,stdout:'',stderr:'',requestReceipt:{status:'unknown_transport'}})[0].text;
}
const evidenceValue = {...pendingChecks, stdout:'long verbose node list', evidence:[
  {ledgerIndex:1,verb:'render_view',ok:false,output:'Z:/project/render/image.png',pixel_status:'failed',semantic_status:'unverified'},
]};
const evidenceText = exec.output.render(execArgs, evidenceValue)[0].text;
assert.ok(evidenceText.indexOf('operation-evidence:') < evidenceText.indexOf('stdout:'));
assert.match(evidenceText, /"pixel_status":"failed"/);
// Domain evidence is displayed exactly as returned by the Bridge. Host output
// must neither promote scoped checks nor synthesize a second domain verdict.
const domainEvidence = [
  {verb:'test_controls',control_summary:{status:'fail',restored:false,
    case_counts:{pass:3,fail:1,not_run:1},coverage:{relationship_scope:'not_checked'},
    cases:[{id:'angle_90',status:'fail'}]},restore_errors:['channel drift']},
  {verb:'geo_check_interfaces',output:'/obj/part/OUT_ASSET1',status:'fail',results:[
    {id:'width',method:'physical_extent',status:'fail',expected_mm:100,observed_mm:100000},
    {id:'axis',method:'axis_passage',status:'unverified',reason:'unsupported surface'}]},
  {verb:'geo_piece_stats',group:'housing',status:'observed',risk_status:'needs_review',
    shell_orientation:{negative_count:1},planar_face_crossings:{status:'unverified',coverage:'partial'}},
  {verb:'verify_network',output:'/obj/model/FINAL',healthy:true,
    handoff_output:{display_flag:false,active_display_output:'/obj/model/CTRL'}},
];
for (const details of [undefined,{stored:true,sha256:'fixture'}]) {
  const rendered = exec.output.render({}, {ok:true,stdout:'diagnostic',stderr:'',evidence:domainEvidence,details})[0].text;
  for (const evidence of domainEvidence) assert(rendered.includes(JSON.stringify(evidence)));
  assert(rendered.indexOf('operation-evidence:') < rendered.indexOf('stdout:'));
  assert.doesNotMatch(rendered,/declared-interface-verdict:|polygon-integrity-verdict:|control-test-verdict:/);
}

const query = definitions.get('houdini_inspect');
assert.deepEqual(query.presentCall({ code: '__result__ = find_nodes(root="/obj")' }), {
  card: 'generic',
  title: '观察现场',
  kind: 'read',
  rawInput: '__result__ = find_nodes(root="/obj")',
});
assert.equal(
  query.presentResult({ code: '__result__ = []' }, { content: text, isError: true }).title,
  '观察现场 · 失败',
);

const submit = definitions.get('houdini_job_submit');
const submitMeta = submit.output.presentationMeta({}, { jobId: 'job-7' });
assert.deepEqual(submitMeta, { jobId: 'job-7', canonical: { jobId: 'job-7' } });
assert.equal(
  submit.presentResult({ code: 'render_frame(rop)' }, { content: text, isError: false, meta: submitMeta }).title,
  '提交长任务 · job-7',
);

const status = definitions.get('houdini_job_status');
const finishedCheckText = status.output.render({}, {...pendingChecks,jobId:'job-7',status:'done'})[0].text;
assert.match(finishedCheckText,/checks failed or contain warnings/,'finished jobs share the same check-aware completion summary');
assert.doesNotMatch(finishedCheckText,/finished successfully/);
const caughtJobMeta=status.output.presentationMeta({}, {...caughtRead,jobId:'job-7',status:'done'});
assert.match(status.presentResult({jobId:'job-7'}, {content:text,isError:false,meta:caughtJobMeta}).title,/批次完成，部分操作失败/);
await assert.rejects(status.execute({jobId:'update_placeholder'},{agent:{}}),/placeholders are never sent/);
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
  imageCount: 0,
  canonical: jobValue,
});
assert.deepEqual(status.presentCall({ jobId: 'job-7', wait: 30 }), {
  card: 'generic',
  title: '等待长任务 · job-7',
  kind: 'read',
  rawInput: { jobId: 'job-7', wait: 30 },
});
assert.equal(
  status.presentResult({ jobId: 'job-7' }, { content: text, isError: false, meta: statusMeta }).title,
  '长任务 job-7 · 执行中',
);

const cancel = definitions.get('houdini_job_cancel');
await assert.rejects(cancel.execute({jobId:'none'},{agent:{}}),/placeholders are never sent/);
assert.deepEqual(cancel.presentCall({ jobId: 'job-7' }), {
  card: 'generic',
  title: '取消长任务 · job-7',
  kind: 'execute',
  rawInput: 'job-7',
});
assert.equal(
  cancel.presentResult({ jobId: 'job-7' }, { content: text, isError: true }).title,
  '取消长任务 · 失败',
);

// Presentation is a replay-time pure projection: repeated calls are identical
// and do not mutate the durable args/result payloads.
const frozenArgs = Object.freeze({ jobId: 'job-7', wait: 1 });
assert.deepEqual(status.presentCall(frozenArgs), status.presentCall(frozenArgs));

// Workspace advice uses the operation's own observation, without a hidden
// health/exec round trip, and belongs to the agent rather than the Host process.
const workspaceDefinitions = new Map();
let workspaceExecutions = 0;
let workspaceResult = {ok:true,stdout:'',stderr:'',execution:{hip_dir:'C:/project'}};
registerHoudiniTools({tools:{register: d => workspaceDefinitions.set(d.name, d)}}, {
  async exec() { workspaceExecutions++; return workspaceResult; },
  async hipDir() { throw new Error('presentation must not probe Houdini'); },
});
const agentA = {id:'a',session:{header:{cwd:'C:/work'}}};
const agentB = {id:'b',session:{header:{cwd:'C:/work'}}};
const executeWorkspace = (agent, name = 'houdini_exec') =>
  workspaceDefinitions.get(name).execute({code:'pass'}, {agent,callId:`c${workspaceExecutions}`});
assert.match((await executeWorkspace(agentA)).advisory, /Open Workspace/);
assert.equal((await executeWorkspace(agentA)).advisory, undefined, 'same agent/pair is deduplicated');
assert.match((await executeWorkspace(agentB, 'houdini_inspect')).advisory, /Open Workspace/, 'other agent gets its own advice');
workspaceResult = {...workspaceResult, execution:{hip_dir:'c:\\WORK\\'}};
assert.equal((await executeWorkspace(agentA)).advisory, undefined, 'Windows slashes/case do not cause false mismatch');
workspaceResult = {...workspaceResult, execution:{hip_dir:'C:/project'}};
assert.match((await executeWorkspace(agentA)).advisory, /Open Workspace/, 'a newly changed workspace is explained again');
workspaceResult = {...workspaceResult, execution:{hip_dir:null}};
assert.equal((await executeWorkspace(agentA)).advisory, undefined, 'unnamed HIP is not a known project');
workspaceResult = {ok:false,stdout:'',stderr:'',requestReceipt:{status:'unknown_transport'}};
assert.equal((await executeWorkspace(agentA)).advisory, undefined, 'uncertain receipt must not trigger another queued observation');
assert.equal(workspaceExecutions, 7, 'each user tool call executes exactly once');

// Execution identity is mandatory Host context. Missing, blank or mistyped
// agent.id/callId must fail before executor resolution, writer claims, ticket
// preparation or any Houdini request — legal tool arguments stay untouched.
const strictDefs = new Map();
let resolved = 0, flushed = 0, sent = 0, seenOwner;
const strictBridge = {
  targetExecutorId: 'e'.repeat(32),
  async exec(code, owner) { sent++; seenOwner = owner; return {ok:true,stdout:'',stderr:''}; },
  async submitJob(code, owner) { sent++; seenOwner = owner; return {jobId:'a'.repeat(12)}; },
  async jobStatus(jobId, owner) { sent++; seenOwner = owner; return {jobId, status:'done', ok:true, stdout:'', stderr:''}; },
  async cancelJob(jobId, owner) { sent++; seenOwner = owner; return {jobId, status:'cancelled', ok:true, stdout:'', stderr:''}; },
};
registerHoudiniTools({tools:{register:d=>strictDefs.set(d.name,d)},
  sessions:{flush:async()=>{flushed++;return true}}},
  {resolve: async () => {resolved++;return strictBridge}});
const identity = (agentId, callId) => ({agent: agentId === undefined ? undefined : {id: agentId}, callId});
const badIdentities = [
  identity(undefined, 'c'), identity('session', undefined), identity('session', ''),
  identity('session', '   '), identity('session', 7), identity('', 'c'), identity('   ', 'c'),
  identity(7, 'c'), {}, undefined,
];
const bindingSection = {name:'dsh-houdini:executor-binding', text:'Houdini task target binding (routing data, not node ownership or permission).\n'
  + JSON.stringify({schema:1, kind:'executor_binding', executor_id:'e'.repeat(32)})};
const makeStrictSession = () => ({snapshotEvents: () => [
  {seq:1, type:'user/message', data:{source:{kind:'dsh-houdini', sections:[bindingSection]}}},
], append: () => {}});
const goodExec = {agent:{id:'session-1',session:makeStrictSession()}, callId:'call-9'};
for (const bad of badIdentities) {
  await assert.rejects(strictDefs.get('houdini_exec').execute({code:'pass'},bad),/identity/);
  await assert.rejects(strictDefs.get('houdini_inspect').execute({code:'pass'},bad),/identity/);
  await assert.rejects(strictDefs.get('houdini_request').execute({request_ref:'index'},bad),/identity/);
  await assert.rejects(strictDefs.get('houdini_job_submit').execute({code:'pass'},bad),/identity/);
  await assert.rejects(strictDefs.get('houdini_job_status').execute({jobId:'a'.repeat(12)},bad),/identity/);
  await assert.rejects(strictDefs.get('houdini_job_cancel').execute({jobId:'a'.repeat(12)},bad),/identity/);
}
assert.equal(resolved, 0, 'identity failures must precede executor resolution');
assert.equal(flushed, 0, 'identity failures must precede writer claims');
assert.equal(sent, 0, 'identity failures must precede any Houdini request');
await assert.rejects(strictDefs.get('houdini_resource').execute({kind:'result',ref:'f'.repeat(64)},identity(undefined,'c')),
  /workspace/, 'historical result reads keep their local boundary and need no bridge identity');
assert.equal(resolved, 0, 'result_ref still never resolves an executor');
// A valid identity flows verbatim through every code/job branch — no coercion,
// no trimming — and shared tool instances never borrow another session's identity.
await strictDefs.get('houdini_exec').execute({code:'pass'}, goodExec);
assert.deepEqual(seenOwner, {sessionId:'session-1', callId:'call-9'});
await strictDefs.get('houdini_inspect').execute({code:'pass'}, goodExec);
assert.deepEqual(seenOwner, {sessionId:'session-1', callId:'call-9'});
await strictDefs.get('houdini_job_status').execute({jobId:'a'.repeat(12)}, goodExec);
assert.deepEqual(seenOwner, {sessionId:'session-1', callId:'call-9'});
const padded = {agent:{id:' padded id ',session:makeStrictSession()},callId:' padded call '};
await strictDefs.get('houdini_exec').execute({code:'pass'}, padded);
assert.deepEqual(seenOwner, {sessionId:' padded id ', callId:' padded call '}, 'legal values are sent verbatim');
const other = {agent:{id:'session-2',session:makeStrictSession()}, callId:'call-10'};
await strictDefs.get('houdini_exec').execute({code:'pass'}, other);
assert.deepEqual(seenOwner, {sessionId:'session-2', callId:'call-10'}, 'no cross-session identity reuse');
assert.equal(sent, 5);

// The same tool-level identity rejections produce zero traffic against a REAL
// HoudiniBridge: every endpoint (health, prepare, exec, jobs, job control)
// would be counted; none is reached.
const realDefs = new Map();
let networkRequests = 0;
const countingServer = http.createServer((request, response) => {
  networkRequests++;
  response.setHeader('content-type', 'application/json');
  response.end('{}');
});
await new Promise((resolve) => countingServer.listen(0, '127.0.0.1', resolve));
try {
  const realBridge = new HoudiniBridge(`http://127.0.0.1:${countingServer.address().port}`, 1000);
  registerHoudiniTools({tools:{register:d=>realDefs.set(d.name,d)}}, realBridge);
  for (const bad of badIdentities) {
    await assert.rejects(realDefs.get('houdini_exec').execute({code:'pass'},bad),/identity/);
    await assert.rejects(realDefs.get('houdini_inspect').execute({code:'pass'},bad),/identity/);
    await assert.rejects(realDefs.get('houdini_request').execute({request_ref:'index'},bad),/identity/);
    await assert.rejects(realDefs.get('houdini_job_submit').execute({code:'pass'},bad),/identity/);
    await assert.rejects(realDefs.get('houdini_job_status').execute({jobId:'a'.repeat(12)},bad),/identity/);
    await assert.rejects(realDefs.get('houdini_job_cancel').execute({jobId:'a'.repeat(12)},bad),/identity/);
  }
  assert.equal(networkRequests, 0, 'identity failures must reach no real Bridge endpoint');
} finally {
  await new Promise((resolve) => countingServer.close(resolve));
}

console.log('houdini tool presentation tests passed');
