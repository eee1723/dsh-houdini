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
  title: 'Execute Houdini Python',
  kind: 'edit',
  rawInput: execArgs,
});
const execMeta = exec.output.presentationMeta(execArgs, execValue);
assert.deepEqual(execMeta, { ok: true, verbCount: 2, imageCount: 1 });
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
const compactControlFailure = exec.output.render({}, {
  ok:true,stdout:'',stderr:'',details:{stored:true,sha256:'fixture'},
  evidence:[{ledgerIndex:1,verb:'test_controls',control_summary:{
    status:'fail',restored:true,requested_cases:4,
    case_counts:{pass:3,fail:1,unverified:0,not_run:0},
    coverage:{relationship_scope:'not_checked',declared_interfaces:0,
      baseline_interface_status:'not_checked',cases_with_interface_checks:0,
      executed_interface_checks:0,declared_topology_contracts:0},
    cases:[{id:'angle_90',status:'fail'}],
  }}],
  verbs:[{verb:'test_controls',ok:true,check_status:'failed',result:{ok:false,status:'fail'}}],
})[0].text;
assert.match(compactControlFailure.split('\n')[0], /control-test-verdict.*"pass":3.*"fail":1.*angle_90/,
  'compact control failures must lead the model-facing result, not hide behind a successful verb call');
assert.match(compactControlFailure, /restored only means test changes were undone/);
assert.match(compactControlFailure.split('\n')[0], /"relationship_scope":"not_checked".*"declared_interfaces":0/,
  'a passing measurement count must not imply component relationships were checked');
assert.match(compactControlFailure.split('\n')[0], /"baseline_interface_status":"not_checked".*"cases_with_interface_checks":0.*"executed_interface_checks":0/);
const integrityWarning = exec.output.render({}, {
  ok:true,stdout:'',stderr:'',details:{stored:true,sha256:'fixture'},
  evidence:[{ledgerIndex:1,verb:'geo_piece_stats',method:'bounded polygon surface integrity',
    status:'observed',risk_status:'needs_review',risk_reasons:['nonmanifold_edges'],
    boundary_edges:4,boundary_review_status:'open_boundary_unreviewed'}],
})[0].text;
assert.match(integrityWarning.split('\n')[0], /polygon-integrity-verdict.*needs_review.*nonmanifold_edges/);
assert.match(integrityWarning, /open ports may be intentional/);
const shadingCandidate = exec.output.render({}, {
  ok:true,stdout:'',stderr:'',evidence:[{ledgerIndex:1,verb:'geo_piece_stats',
    method:'bounded polygon surface integrity',status:'observed',
    risk_status:'no_detected_integrity_risk',planar_repeated_point_ngons:2,
    shading_review_status:'needs_visual_review'}],
})[0].text;
assert.match(shadingCandidate.split('\n')[0], /polygon-integrity-verdict.*"planar_repeated_point_ngons":2.*"shading_review_status":"needs_visual_review"/);
assert.match(shadingCandidate, /not integrity failures/);
const groupOnlyIntegrity = exec.output.render({}, {
  ok:true,stdout:'',stderr:'',evidence:[
    {ledgerIndex:1,verb:'geo_piece_stats',method:'bounded polygon surface integrity',
      group:'g_gasket',status:'observed',risk_status:'no_detected_integrity_risk'},
    {ledgerIndex:2,verb:'geo_piece_stats',method:'bounded polygon surface integrity',
      group:'g_shell_base',status:'observed',risk_status:'no_detected_integrity_risk'},
  ],
})[0].text;
assert.match(groupOnlyIntegrity.split('\n')[0], /polygon-integrity-coverage.*"selected_groups":2.*"whole_output_checked_in_this_call":false/);
assert.match(groupOnlyIntegrity, /coincident faces across different groups/);
assert.match(groupOnlyIntegrity, /polygon-integrity-verdict:.*"group":"g_gasket"/);
const invertedShell = exec.output.render({}, {
  ok:true,stdout:'',stderr:'',evidence:[{ledgerIndex:1,verb:'geo_piece_stats',
    method:'bounded polygon surface integrity',group:'g_shell',status:'observed',
    risk_status:'needs_review',risk_reasons:['negative_closed_shell_winding_requires_review'],
    orientation_review_status:'negative_closed_shells_present',
    shell_orientation:{positive_count:0,negative_count:1,unverified_count:0},
    shading_normals:{opposed_count:3}}],
})[0].text;
assert.match(invertedShell, /"negative_closed_shells":1/);
assert.match(invertedShell, /"opposed_shading_normals":3/);
assert.match(invertedShell, /Normal N is not polygon winding/);
const finalOutputRisk = exec.output.render({}, {
  ok:true,stdout:'',stderr:'',evidence:[{ledgerIndex:1,verb:'verify_network',ok:true,
    output:'/obj/reel/OUT_ASSET',healthy:true,warning_free:true,
    geometry:{points:4040,prims:3768,bbox_size:[.315,.2083,.1696]},
    scene_unit_length_meters:1,
    surface_integrity:{status:'observed',risk_status:'needs_review',boundary_edges:96,
      negative_closed_shells:3,unverified_shells:1}}],
})[0].text;
assert.match(finalOutputRisk.split('\n')[0], /final-output-review:.*"bbox_size_sop_local":\[0\.315,0\.2083,0\.1696\].*"negative_closed_shells":3/);
assert.match(finalOutputRisk, /healthy cook does not certify assembly or appearance/);
const lateInversion = exec.output.render({}, {
  ok:true,stdout:'',stderr:'',evidence:[...Array.from({length:5}, (_,index) => ({
    ledgerIndex:index+1,verb:'geo_piece_stats',method:'bounded polygon surface integrity',
    group:`g_${index}`,status:'observed',risk_status:'no_detected_integrity_risk',
  })),{ledgerIndex:6,verb:'geo_piece_stats',method:'bounded polygon surface integrity',
    group:'g_late_inverted',status:'observed',risk_status:'needs_review',
    shell_orientation:{negative_count:1},risk_reasons:['negative_closed_shell_winding_requires_review']}],
})[0].text;
assert.match(lateInversion.split('Executed successfully.')[0], /g_late_inverted/,
  'a late risk must not be clipped behind earlier clean group results');

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
await assert.rejects(cancel.execute({jobId:'none'},{agent:{}}),/placeholders are never sent/);
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
assert.match((await executeWorkspace(agentB, 'houdini_query')).advisory, /Open Workspace/, 'other agent gets its own advice');
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
  {seq:1, type:'user/message', data:{source:{kind:'plugin', plugin:'dsh-houdini', sections:[bindingSection]}}},
], append: () => {}});
const goodExec = {agent:{id:'session-1',session:makeStrictSession()}, callId:'call-9'};
for (const bad of badIdentities) {
  await assert.rejects(strictDefs.get('houdini_exec').execute({code:'pass'},bad),/identity/);
  await assert.rejects(strictDefs.get('houdini_query').execute({code:'pass'},bad),/identity/);
  await assert.rejects(strictDefs.get('houdini_query').execute({request_ref:'index'},bad),/identity/);
  await assert.rejects(strictDefs.get('houdini_job_submit').execute({code:'pass'},bad),/identity/);
  await assert.rejects(strictDefs.get('houdini_job_status').execute({jobId:'a'.repeat(12)},bad),/identity/);
  await assert.rejects(strictDefs.get('houdini_job_cancel').execute({jobId:'a'.repeat(12)},bad),/identity/);
}
assert.equal(resolved, 0, 'identity failures must precede executor resolution');
assert.equal(flushed, 0, 'identity failures must precede writer claims');
assert.equal(sent, 0, 'identity failures must precede any Houdini request');
await assert.rejects(strictDefs.get('houdini_query').execute({result_ref:'f'.repeat(64)},identity(undefined,'c')),
  /workspace/, 'historical result reads keep their local boundary and need no bridge identity');
assert.equal(resolved, 0, 'result_ref still never resolves an executor');
// A valid identity flows verbatim through every code/job branch — no coercion,
// no trimming — and shared tool instances never borrow another session's identity.
await strictDefs.get('houdini_exec').execute({code:'pass'}, goodExec);
assert.deepEqual(seenOwner, {sessionId:'session-1', callId:'call-9'});
await strictDefs.get('houdini_query').execute({code:'pass'}, goodExec);
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
    await assert.rejects(realDefs.get('houdini_query').execute({code:'pass'},bad),/identity/);
    await assert.rejects(realDefs.get('houdini_query').execute({request_ref:'index'},bad),/identity/);
    await assert.rejects(realDefs.get('houdini_job_submit').execute({code:'pass'},bad),/identity/);
    await assert.rejects(realDefs.get('houdini_job_status').execute({jobId:'a'.repeat(12)},bad),/identity/);
    await assert.rejects(realDefs.get('houdini_job_cancel').execute({jobId:'a'.repeat(12)},bad),/identity/);
  }
  assert.equal(networkRequests, 0, 'identity failures must reach no real Bridge endpoint');
} finally {
  await new Promise((resolve) => countingServer.close(resolve));
}

console.log('houdini tool presentation tests passed');
